from cyros_builder.manifest import BuildManifest
from cyros_builder.output import include_dir, lib_dir, module_dir
from cyros_builder.project_model import (
   collect_public_headers,
   collect_public_modules,
   collect_system_libraries,
   select_project,
)
from cyros_builder.resolve import ResolvedInvocation


def build_manifest(resolved: ResolvedInvocation) -> BuildManifest:
   selected = select_project(resolved.profile)
   family = resolved.toolchain.settings.family
   module_format = "gcm.cache" if family == "gcc" else "pcm"

   declared_modules = collect_public_modules(selected)
   public_headers = tuple(str(export.destination) for export in collect_public_headers(selected))
   system_libraries = collect_system_libraries(selected)

   selection = {
      "port": selected.port.name,
      "time_driver": selected.time_driver.name if selected.time_driver is not None else None,
      "libcyros_features": sorted(selected.features),
   }

   built_groups = (
      selected.kernel.name,
      selected.port.name,
      *([selected.time_driver.name] if selected.time_driver is not None else []),
      *sorted(selected.features),
   )

   return BuildManifest(
      name="cyros",
      profile_name=resolved.profile.name,
      toolchain_name=resolved.selected_toolchain_name,
      compiler_family=family,
      archive=lib_dir(resolved) / resolved.profile.output.archive,
      module_root=module_dir(resolved),
      module_format=module_format,
      include_root=include_dir(resolved),
      public_headers=public_headers,
      public_modules=declared_modules,
      link={
         "system_libraries": list(system_libraries),
      },
      selection=selection,
      built_groups=built_groups,
   )