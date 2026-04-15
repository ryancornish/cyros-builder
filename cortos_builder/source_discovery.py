from dataclasses import dataclass
from pathlib import Path

from cortos_builder.component import Component


@dataclass(frozen=True)
class DiscoveredSource:
   component: str
   path: Path
   language: str       # "c", "c++", "asm"
   kind: str           # "source" or "module_interface"


def discover_component_sources(component: Component) -> list[DiscoveredSource]:
   results: list[DiscoveredSource] = []

   for root in component.source_roots:
      if not root.is_dir():
         continue

      for path in sorted(root.rglob("*")):
         if not path.is_file():
            continue

         if _is_ignored(path):
            continue

         discovered = _classify_source(component.name, path)
         if discovered is not None:
            results.append(discovered)

   return results


def _is_ignored(path: Path) -> bool:
   ignored_dir_names = {"build", "out", ".git", ".cache", "__pycache__"}
   return any(part in ignored_dir_names for part in path.parts)


def _classify_source(component_name: str, path: Path) -> DiscoveredSource | None:
   suffix = path.suffix.lower()

   if suffix == ".cppm":
      return DiscoveredSource(
         component=component_name,
         path=path,
         language="c++",
         kind="module_interface",
      )

   if suffix in {".cpp", ".cc", ".cxx"}:
      return DiscoveredSource(
         component=component_name,
         path=path,
         language="c++",
         kind="source",
      )

   if suffix == ".c":
      return DiscoveredSource(
         component=component_name,
         path=path,
         language="c",
         kind="source",
      )

   if suffix in {".s", ".S"}:
      return DiscoveredSource(
         component=component_name,
         path=path,
         language="asm",
         kind="source",
      )

   return None
