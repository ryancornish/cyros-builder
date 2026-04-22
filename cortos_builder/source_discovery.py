from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cortos_builder.module_scan import ModuleInfo, scan_module_info


class SourceDiscoverable(Protocol):
   @property
   def name(self) -> str:
      ...

   @property
   def source_roots(self) -> tuple[Path, ...]:
      ...


@dataclass(frozen=True)
class DiscoveredSource:
   component: str
   path: Path
   language: str
   kind: str
   module_info: ModuleInfo | None = None


def discover_component_sources(component: SourceDiscoverable, *, use_modules: bool) -> list[DiscoveredSource]:
   results: list[DiscoveredSource] = []

   for root in component.source_roots:
      if not root.is_dir():
         continue

      for path in sorted(root.rglob("*")):
         if not path.is_file():
            continue

         if _is_ignored(path):
            continue

         discovered = _classify_source(component.name, path, use_modules=use_modules)
         if discovered is not None:
            results.append(discovered)

   return results


def _is_ignored(path: Path) -> bool:
   ignored_dir_names = {"build", "out", ".git", ".cache", "__pycache__"}
   return any(part in ignored_dir_names for part in path.parts)


def _classify_source(component_name: str, path: Path, *, use_modules: bool) -> DiscoveredSource | None:
   suffix = path.suffix.lower()

   if suffix == ".cppm":
      if not use_modules:
         return None
      return DiscoveredSource(
         component=component_name,
         path=path.resolve(),
         language="c++",
         kind="module_interface",
         module_info=scan_module_info(path),
      )

   if suffix in {".cpp", ".cc", ".cxx"}:
      return DiscoveredSource(
         component=component_name,
         path=path.resolve(),
         language="c++",
         kind="source",
         module_info=scan_module_info(path) if use_modules else None,
      )

   if suffix == ".c":
      return DiscoveredSource(
         component=component_name,
         path=path.resolve(),
         language="c",
         kind="source",
         module_info=None,
      )

   if suffix in {".s", ".S"}:
      return DiscoveredSource(
         component=component_name,
         path=path.resolve(),
         language="asm",
         kind="source",
         module_info=None,
      )

   return None
