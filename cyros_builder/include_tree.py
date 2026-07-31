from pathlib import Path
from typing import cast
import shutil

from cyros_builder.output import include_dir
from cyros_builder.project_model import collect_public_headers, select_project
from cyros_builder.resolve import ResolvedInvocation


def populate_include_tree(resolved: ResolvedInvocation) -> None:
   """Populate the single generated public include tree for the selected build.

   Idempotent: a header is only written when its content differs from what is
   already there, and anything no longer in the export set is removed. The
   previous implementation did `rmtree` then re-copied unconditionally.

   Note for anyone reading the Phase B plan in the docs: this was listed as a
   hard *blocker* for incremental builds, on the grounds that re-copying gives
   every generated header a fresh mtime so every object would look stale. That
   reasoning does not hold — `shutil.copy2` copies mtime from the source, so the
   old code already produced stable mtimes, and staleness here is decided on
   content hashes, which makes mtime irrelevant either way. This is done because
   rewriting a tree on every invocation is pointless I/O and needlessly disturbs
   anything watching those files, not because incrementality depends on it.
   """
   selected = select_project(resolved.profile)
   out_include = include_dir(resolved).resolve()
   out_include.mkdir(parents=True, exist_ok=True)

   written: set[Path] = set()

   for export in collect_public_headers(selected):
      destination = out_include / export.destination
      _sync_file(export.source, destination, "public header")
      written.add(destination.resolve())

   config_destination = out_include / "cyros" / "config" / "config.hpp"
   _sync_file(cast(Path, resolved.config_header), config_destination, "profile config header")
   written.add(config_destination.resolve())

   _remove_unlisted(out_include, written)


def _sync_file(src: Path, dst: Path, desc: str) -> None:
   if not src.is_file():
      raise FileNotFoundError(f"Missing {desc}: {src}")

   if dst.is_file() and dst.read_bytes() == src.read_bytes():
      return

   dst.parent.mkdir(parents=True, exist_ok=True)
   shutil.copy2(src, dst)


def _remove_unlisted(root: Path, keep: set[Path]) -> None:
   """Delete files the export set no longer contains, then prune empty dirs.

   This is the part `rmtree` used to get for free, and it is not optional: a
   header dropped from `public_headers` must stop being visible to compiles, or
   a source keeps including something the build no longer declares.
   """
   for path in root.rglob("*"):
      if path.is_file() and path.resolve() not in keep:
         path.unlink()

   # Deepest first, so a directory emptied by the pass above is also removed.
   for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
      if path.is_dir() and not any(path.iterdir()):
         path.rmdir()
