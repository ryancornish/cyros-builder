from dataclasses import dataclass
from pathlib import Path

from cortos_builder.output import module_dir
from cortos_builder.project_model import iter_source_groups, select_project
from cortos_builder.resolve import ResolvedInvocation


@dataclass(frozen=True)
class ProvidedModule:
   name: str
   component: str
   provider_source: str
   kind: str
   artifact_hint: str


def collect_provided_modules(resolved) -> dict[str, Path]:
   """
   Return a mapping of provided module name -> source/provider path.

   In the current explicit-source, non-module build flow, this is only relevant
   when use_modules=true. For now, return an empty mapping for normal builds and
   fail clearly if module builds are re-enabled before the module path is rebuilt.
   """
   if not resolved.toolchain.settings.use_modules:
      return {}

   raise NotImplementedError(
      "collect_provided_modules() for module builds has not been reimplemented "
      "for the explicit-source planner yet."
   )


def _artifact_hint_for_module(resolved: ResolvedInvocation, module_name: str, modules_root) -> str:
   family = resolved.toolchain.settings.family

   if family == "gcc":
      return str((modules_root / "gcm.cache" / f"{module_name}.gcm").resolve())

   if family == "clang":
      return str((modules_root / f"{module_name}.pcm").resolve())

   return str(modules_root.resolve())
