from pathlib import Path

from cortos_builder.actions import ArchiveAction, CompileAction
from cortos_builder.component import load_components
from cortos_builder.output import lib_dir, obj_dir
from cortos_builder.resolve import ResolvedInvocation
from cortos_builder.source_discovery import discover_component_sources


def plan_build(resolved: ResolvedInvocation) -> list:
   root = resolved.project_root
   tc = resolved.toolchain
   components = load_components(root)

   objects_root = obj_dir(resolved)
   libraries_root = lib_dir(resolved)

   actions = []
   object_files: list[Path] = []

   for component_name in sorted(components):
      component = components[component_name]
      sources = discover_component_sources(component)

      for src in sources:
         obj = _object_path_for(objects_root, src.path, root, src.kind)
         object_files.append(obj)

         args = _compile_args(tc, src.path, obj)
         actions.append(
            CompileAction(
               source=src.path,
               output=obj,
               language=src.language,
               kind=src.kind,
               arguments=args,
            )
         )

   if object_files:
      archive = libraries_root / resolved.profile.output.archive
      archive_args = (
         tc.tools.ar,
         "rcs",
         str(archive),
         *[str(obj) for obj in object_files],
      )
      actions.append(
         ArchiveAction(
            inputs=tuple(object_files),
            output=archive,
            arguments=archive_args,
         )
      )

   return actions


def _compile_args(tc, source: Path, output: Path) -> tuple[str, ...]:
   if source.suffix.lower() == ".c":
      return (
         tc.tools.cc,
         *tc.flags.common,
         *tc.flags.c,
         "-c",
         str(source),
         "-o",
         str(output),
      )

   if source.suffix in {".s", ".S"}:
      asm = tc.tools.asm or tc.tools.cc
      return (
         asm,
         *tc.flags.common,
         *tc.flags.asm,
         "-c",
         str(source),
         "-o",
         str(output),
      )

   return (
      tc.tools.cxx,
      *tc.flags.common,
      *tc.flags.cxx,
      "-c",
      str(source),
      "-o",
      str(output),
   )


def _object_path_for(obj_dir: Path, source: Path, project_root: Path, kind: str) -> Path:
   rel = source.resolve().relative_to(project_root.resolve())
   suffix = ".ifc.o" if kind == "module_interface" else ".o"
   return (obj_dir / rel).with_suffix(suffix)
