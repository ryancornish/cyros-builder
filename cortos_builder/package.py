from cortos_builder.manifest import BuildManifest
from cortos_builder.module_map import collect_provided_modules
from cortos_builder.output import include_dir, lib_dir, module_dir
from cortos_builder.project_model import collect_public_modules, select_project
from cortos_builder.resolve import ResolvedInvocation


def build_manifest(resolved: ResolvedInvocation) -> BuildManifest:
   selected = select_project(resolved.project_root, resolved.profile)
   family = resolved.toolchain.settings.family
   module_format = "gcm.cache" if family == "gcc" else "pcm"

   provided_modules = collect_provided_modules(resolved)

   modules_json = {
      name: {
         "component": record.component,
         "provider_source": record.provider_source,
         "kind": record.kind,
         "artifact_hint": record.artifact_hint,
      }
      for name, record in sorted(provided_modules.items())
   }

   declared = collect_public_modules(selected)
   resolved_public = tuple(name for name in declared if name in provided_modules)

   return BuildManifest(
      name="cortos",
      profile_name=resolved.profile.name,
      toolchain_name=resolved.selected_toolchain_name,
      compiler_family=family,
      archive=lib_dir(resolved) / resolved.profile.output.archive,
      module_root=module_dir(resolved),
      module_format=module_format,
      include_root=include_dir(resolved),
      public_modules=declared,
      modules=modules_json,
      resolved_public_modules=resolved_public,
   )