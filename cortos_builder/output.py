from pathlib import Path
from cortos_builder.resolve import ResolvedInvocation


def compile_db_path(resolved: ResolvedInvocation) -> Path:
   return (
      resolved.project_root
      / "build"
      / "db"
      / resolved.selected_toolchain_name
      / "compile_commands.json"
   )
