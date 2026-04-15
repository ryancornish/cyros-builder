from pathlib import Path

from cortos_builder.resolve import ResolvedInvocation


def build_root(resolved: ResolvedInvocation) -> Path:
   return resolved.profile.output.root / resolved.selected_toolchain_name


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