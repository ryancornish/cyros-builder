from pathlib import Path

from cyros_builder.resolve import ResolvedInvocation


def build_root(resolved: ResolvedInvocation) -> Path:
   return resolved.output_root / resolved.profile.name / resolved.selected_toolchain_name


def obj_dir(resolved: ResolvedInvocation) -> Path:
   return build_root(resolved) / "obj"


def lib_dir(resolved: ResolvedInvocation) -> Path:
   return build_root(resolved) / "lib"


def module_dir(resolved: ResolvedInvocation) -> Path:
   return build_root(resolved) / "modules"


def include_dir(resolved: ResolvedInvocation) -> Path:
   return build_root(resolved) / "include"


def manifest_path(resolved: ResolvedInvocation) -> Path:
   return build_root(resolved) / "manifest.json"


def compile_db_path(resolved: ResolvedInvocation) -> Path:
   return build_root(resolved) / "compile_commands.json"


def build_state_path(resolved: ResolvedInvocation) -> Path:
   """Where incremental-build bookkeeping lives. Inside build_root, so it is
   scoped to one (profile, toolchain) and removed by `clean`."""
   return build_root(resolved) / ".build-state.json"