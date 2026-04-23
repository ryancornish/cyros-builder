from pathlib import Path


def resolve_project_root(root: Path | None) -> Path:
   return (root or Path.cwd()).resolve()


def profiles_dir(root: Path | None) -> Path:
   resolved = resolve_project_root(root)
   modern = resolved / "build" / "profiles"
   if modern.is_dir():
      return modern
   return resolved / "profiles"


def toolchains_dir(root: Path | None) -> Path:
   resolved = resolve_project_root(root)
   modern = resolved / "build" / "toolchains"
   if modern.is_dir():
      return modern
   return resolved / "toolchains"
