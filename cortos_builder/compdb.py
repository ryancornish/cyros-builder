from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CompileCommand:
   directory: Path
   file: Path
   arguments: tuple[str, ...]
   output: Path | None = None

   def to_json(self) -> dict:
      data = {
         "directory": str(self.directory.resolve()),
         "file": str(self.file.resolve()),
         "arguments": list(self.arguments),
      }
      if self.output is not None:
         data["output"] = str(self.output.resolve())
      return data


def write_compile_commands(path: Path, commands: list[CompileCommand]) -> None:
   path.parent.mkdir(parents=True, exist_ok=True)

   data = [cmd.to_json() for cmd in commands]

   tmp = path.with_suffix(path.suffix + ".tmp")
   with tmp.open("w", encoding="utf-8") as f:
      json.dump(data, f, indent=2)
      f.write("\n")
   tmp.replace(path)


def activate_compile_commands(project_root: Path, db_path: Path) -> None:
   link_path = project_root / "compile_commands.json"

   if not db_path.exists():
      raise ValueError(f"Cannot activate missing compile database: {db_path}")

   if link_path.exists() or link_path.is_symlink():
      link_path.unlink()

   rel_target = os.path.relpath(db_path, project_root)
   link_path.symlink_to(rel_target)
