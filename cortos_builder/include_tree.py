from pathlib import Path
from typing import cast
import shutil

from cortos_builder.output import include_dir
from cortos_builder.project_model import collect_public_headers, select_project
from cortos_builder.resolve import ResolvedInvocation


def populate_include_tree(resolved: ResolvedInvocation) -> None:
   """Populate the single generated public include tree for the selected build."""
   selected = select_project(resolved.profile)
   out_include = include_dir(resolved).resolve()

   if out_include.exists():
      shutil.rmtree(out_include)
   out_include.mkdir(parents=True, exist_ok=True)

   for export in collect_public_headers(selected):
      _copy_file(export.source, out_include / export.destination, "public header")

   config_src = resolved.profile.profile.config_header
   config_dst = out_include / "cortos"/ "config" / "config.hpp"
   _copy_file(cast(Path, config_src), config_dst, "profile config header")


def _copy_file(src: Path, dst: Path, desc: str) -> None:
   if not src.is_file():
      raise FileNotFoundError(f"Missing {desc}: {src}")
   dst.parent.mkdir(parents=True, exist_ok=True)
   shutil.copy2(src, dst)