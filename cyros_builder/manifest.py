from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class BuildManifest:
   name: str
   profile_name: str
   toolchain_name: str
   compiler_family: str

   archive: Path
   module_root: Path
   module_format: str
   include_root: Path

   selection: dict
   built_groups: tuple[str, ...]

   public_headers: tuple[str, ...]
   public_modules: tuple[str, ...]
   link: dict


def write_manifest(path: Path, manifest: BuildManifest) -> None:
   path.parent.mkdir(parents=True, exist_ok=True)

   data = {
      "name": manifest.name,
      "profile_name": manifest.profile_name,
      "toolchain_name": manifest.toolchain_name,
      "compiler_family": manifest.compiler_family,
      "archive": str(manifest.archive.resolve()),
      "module_root": str(manifest.module_root.resolve()),
      "module_format": manifest.module_format,
      "include_root": str(manifest.include_root.resolve()),
      "selection": manifest.selection,
      "built_groups": list(manifest.built_groups),
      "public_headers": list(manifest.public_headers),
      "public_modules": list(manifest.public_modules),
      "link": manifest.link,
   }

   tmp = path.with_suffix(path.suffix + ".tmp")
   with tmp.open("w", encoding="utf-8") as f:
      json.dump(data, f, indent=2)
      f.write("\n")
   tmp.replace(path)