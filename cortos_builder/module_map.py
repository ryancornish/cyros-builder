from dataclasses import dataclass

from cortos_builder.output import module_dir
from cortos_builder.project_model import iter_source_groups, select_project
from cortos_builder.resolve import ResolvedInvocation
from cortos_builder.source_discovery import discover_component_sources


@dataclass(frozen=True)
class ProvidedModule:
   name: str
   component: str
   provider_source: str
   kind: str
   artifact_hint: str


def collect_provided_modules(resolved: ResolvedInvocation) -> dict[str, ProvidedModule]:
   selected = select_project(resolved.project_root, resolved.profile)
   modules_root = module_dir(resolved).resolve()

   provided: dict[str, ProvidedModule] = {}

   for group in iter_source_groups(selected):
      sources = discover_component_sources(group)

      for src in sources:
         info = src.module_info
         if info is None or info.provided_module is None:
               continue

         mod = info.provided_module
         if mod in provided:
               raise ValueError(
                  f"Multiple sources provide module '{mod}':\n"
                  f"  {provided[mod].provider_source}\n"
                  f"  {src.path}"
               )

         provided[mod] = ProvidedModule(
               name=mod,
               component=src.component,
               provider_source=str(src.path.resolve()),
               kind=src.kind,
               artifact_hint=_artifact_hint_for_module(resolved, mod, modules_root),
         )

   return provided


def _artifact_hint_for_module(resolved: ResolvedInvocation, module_name: str, modules_root) -> str:
   family = resolved.toolchain.settings.family

   if family == "gcc":
      return str((modules_root / "gcm.cache" / f"{module_name}.gcm").resolve())

   if family == "clang":
      return str((modules_root / f"{module_name}.pcm").resolve())

   return str(modules_root.resolve())
