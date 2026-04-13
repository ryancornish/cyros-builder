from pathlib import Path


def resolve_project_root(root: Path | None) -> Path:
   return (root or Path.cwd()).resolve()

def profiles_dir(root: Path | None) -> Path:
   return resolve_project_root(root) / "profiles"

def toolchains_dir(root: Path | None) -> Path:
   return resolve_project_root(root) / "toolchains"
