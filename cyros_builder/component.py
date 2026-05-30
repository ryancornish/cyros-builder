from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Component:
   path: Path
   name: str
   description: str
   dependencies: tuple[str, ...]
   public_modules: tuple[str, ...]
   private_modules: tuple[str, ...]
   source_roots: tuple[Path, ...]
   generated_includes: bool


_ALLOWED_TOP_LEVEL_KEYS = {
   "name",
   "description",
   "dependencies",
   "public_modules",
   "private_modules",
   "source_roots",
   "generated_includes",
}


def find_component_paths(root: Path | None = None) -> list[Path]:
   project_root = (root or Path.cwd()).resolve()
   src_dir = project_root / "src"
   if not src_dir.is_dir():
      return []

   return sorted(src_dir.rglob("component.toml"))


def list_component_names(root: Path | None = None) -> list[str]:
   return sorted(load_component(path).name for path in find_component_paths(root))


def load_component(path: Path) -> Component:
   component_path = path.resolve()

   with component_path.open("rb") as f:
      raw = tomllib.load(f)

   if not isinstance(raw, dict):
      raise ValueError(f"{component_path}: root TOML document must be a table")

   _validate_top_level_keys(raw, component_path)

   base_dir = component_path.parent

   source_root_values = _require_str_list(raw, "source_roots", component_path)

   return Component(
      path=component_path,
      name=_require_str(raw, "name", component_path),
      description=_require_str(raw, "description", component_path),
      dependencies=tuple(_require_str_list(raw, "dependencies", component_path)),
      public_modules=tuple(_require_str_list(raw, "public_modules", component_path)),
      private_modules=tuple(_require_str_list(raw, "private_modules", component_path)),
      source_roots=tuple((base_dir / value).resolve() for value in source_root_values),
      generated_includes=_require_bool(raw, "generated_includes", component_path),
   )


def load_components(root: Path | None = None) -> dict[str, Component]:
   components: dict[str, Component] = {}

   for path in find_component_paths(root):
      component = load_component(path)
      if component.name in components:
         raise ValueError(
            f"Duplicate component name '{component.name}' in:\n"
            f"  {components[component.name].path}\n"
            f"  {component.path}"
         )
      components[component.name] = component

   _validate_component_dependencies(components)
   return components

def collect_public_modules(components: dict[str, Component]) -> tuple[str, ...]:
   modules: list[str] = []
   for name in sorted(components):
      modules.extend(components[name].public_modules)
   return tuple(modules)

def _validate_component_dependencies(components: dict[str, Component]) -> None:
   for component in components.values():
      for dep in component.dependencies:
         if dep not in components:
            raise ValueError(
               f"{component.path}: unknown component dependency '{dep}'"
            )


def _validate_top_level_keys(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_TOP_LEVEL_KEYS
   if unknown:
      names = ", ".join(sorted(unknown))
      raise ValueError(f"{path}: unknown top-level keys: {names}")


def _require_str(data: dict, key: str, path: Path) -> str:
   value = data.get(key)
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string")
   return value


def _require_bool(data: dict, key: str, path: Path) -> bool:
   value = data.get(key)
   if not isinstance(value, bool):
      raise ValueError(f"{path}: expected '{key}' to be a bool")
   return value


def _require_str_list(data: dict, key: str, path: Path) -> list[str]:
   value = data.get(key)
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")
   return value
