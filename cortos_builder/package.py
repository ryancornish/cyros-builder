from cortos_builder.component import collect_public_modules, load_components
from cortos_builder.manifest import BuildManifest
from cortos_builder.output import include_dir, lib_dir, module_dir
from cortos_builder.resolve import ResolvedInvocation


def build_manifest(resolved: ResolvedInvocation) -> BuildManifest:
   components = load_components(resolved.project_root)
   family = resolved.toolchain.settings.family
   module_format = "gcm.cache" if family == "gcc" else "pcm"

   return BuildManifest(
      name="cortos",
      profile_name=resolved.profile.name,
      toolchain_name=resolved.selected_toolchain_name,
      compiler_family=family,
      archive=lib_dir(resolved) / resolved.profile.output.archive,
      module_root=module_dir(resolved),
      module_format=module_format,
      include_root=include_dir(resolved),
      public_modules=collect_public_modules(components),
   )