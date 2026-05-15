from cortos_builder.manifest import BuildManifest
from cortos_builder.module_map import collect_provided_modules
from cortos_builder.output import include_dir, lib_dir, module_dir
from cortos_builder.project_model import (
   collect_public_headers,
   collect_public_modules,
   collect_system_libraries,
   select_project,
)
from cortos_builder.resolve import ResolvedInvocation


def build_manifest(resolved: ResolvedInvocation) -> BuildManifest:
   selected = select_project(resolved.profile)
   family = resolved.toolchain.settings.family
   module_format = "gcm.cache" if family == "gcc" else "pcm"

   provided_modules = collect_provided_modules(resolved) if resolved.toolchain.settings.use_modules else {}

   modules_json = {
      name: {
         "component": record.component,
         "provider_source": record.provider_source,
         "kind": record.kind,
         "artifact_hint": record.artifact_hint,
      }
      for name, record in sorted(provided_modules.items())
   }

   declared_modules = collect_public_modules(selected)
   resolved_public_modules = tuple(name for name in declared_modules if name in provided_modules)
   public_headers = tuple(str(export.destination) for export in collect_public_headers(selected))
   system_libraries = collect_system_libraries(selected)

   selection = {
      "port": selected.port.name,
      "time_driver": selected.time_driver.name,
      "libcortos_features": sorted(selected.features),
   }

   built_groups = (
      selected.kernel.name,
      selected.port.name,
      selected.time_driver.name,
      *sorted(selected.features),
   )

   return BuildManifest(
      name="cortos",
      profile_name=resolved.profile.profile.name,
      toolchain_name=resolved.selected_toolchain_name,
      compiler_family=family,
      archive=lib_dir(resolved) / resolved.profile.output.archive,
      module_root=module_dir(resolved),
      module_format=module_format,
      include_root=include_dir(resolved),
      public_headers=public_headers,
      public_modules=declared_modules,
      resolved_public_modules=resolved_public_modules,
      modules=modules_json,
      link={
         "system_libraries": list(system_libraries),
      },
      selection=selection,
      built_groups=built_groups,
   )
