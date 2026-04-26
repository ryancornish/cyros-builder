from pathlib import Path

from cortos_builder.actions import ArchiveAction, CompileAction
from cortos_builder.output import include_dir, lib_dir, module_dir, obj_dir
from cortos_builder.project_model import iter_source_groups, select_project
from cortos_builder.resolve import ResolvedInvocation


class PlannedSource:
   def __init__(self, component: str, path: Path, language: str, kind: str, archive: bool):
      self.component = component
      self.path = path
      self.language = language
      self.kind = kind
      self.archive = archive


def plan_build(resolved: ResolvedInvocation) -> list:
   root = resolved.project_root.resolve()
   tc = resolved.toolchain
   selected = select_project(root, resolved.profile)

   if tc.settings.use_modules:
      raise NotImplementedError(
         "Explicit-source planner currently supports non-module builds only. "
         "Reintroduce module scanning/ordering before enabling use_modules=true."
      )

   objects_root = obj_dir(resolved)
   libraries_root = lib_dir(resolved)
   modules_root = module_dir(resolved)

   planned_sources: list[PlannedSource] = []
   for group in iter_source_groups(selected):
      planned_sources.extend(_planned_sources_for_group(group))

   ordered_sources = sorted(planned_sources, key=lambda s: (s.component, str(s.path)))

   actions = []
   archive_object_files: list[Path] = []

   for src in ordered_sources:
      obj = _object_path_for(objects_root, src.path, root, src.kind)

      args = _compile_args(tc, resolved, src.path, obj)
      cwd = modules_root.resolve()

      actions.append(
         CompileAction(
            component=src.component,
            source=src.path,
            output=obj,
            language=src.language,
            kind=src.kind,
            arguments=args,
            working_directory=cwd,
         )
      )

      if src.archive:
         archive_object_files.append(obj)

   if archive_object_files:
      archive = (libraries_root / resolved.profile.output.archive).resolve()
      archive_args = (
         tc.tools.ar,
         "rcs",
         str(archive),
         *[str(obj.resolve()) for obj in archive_object_files],
      )
      actions.append(
         ArchiveAction(
            inputs=tuple(archive_object_files),
            output=archive,
            arguments=archive_args,
            working_directory=root,
         )
      )

   return actions


def _planned_sources_for_group(group) -> list[PlannedSource]:
   result: list[PlannedSource] = []
   seen: set[Path] = set()

   for src in group.sources:
      resolved = src.resolve()
      if resolved in seen:
         continue
      seen.add(resolved)
      result.append(
         PlannedSource(
            component=group.name,
            path=resolved,
            language=_language_for(resolved),
            kind="translation_unit",
            archive=True,
         )
      )

   for src in group.sources_excluded_from_archive:
      resolved = src.resolve()
      if resolved in seen:
         continue
      seen.add(resolved)
      result.append(
         PlannedSource(
            component=group.name,
            path=resolved,
            language=_language_for(resolved),
            kind="translation_unit",
            archive=False,
         )
      )

   return result


def _language_for(source: Path) -> str:
   suffix = source.suffix.lower()
   if suffix == ".c":
      return "c"
   if suffix in {".s", ".asm"}:
      return "asm"
   if source.suffix == ".S":
      return "asm"
   return "c++"


def _compile_args(tc, resolved: ResolvedInvocation, source: Path, output: Path) -> tuple[str, ...]:
   generated_include_root = include_dir(resolved).resolve()
   source = source.resolve()
   output = output.resolve()

   include_flags = ("-I", str(generated_include_root))

   if source.suffix.lower() == ".c":
      return (
         tc.tools.cc,
         *tc.flags.common,
         *tc.flags.c,
         *include_flags,
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
         *include_flags,
         "-c",
         str(source),
         "-o",
         str(output),
      )

   return (
      tc.tools.cxx,
      *tc.flags.common,
      *tc.flags.cxx,
      *include_flags,
      "-c",
      str(source),
      "-o",
      str(output),
   )


def _object_path_for(obj_dir: Path, source: Path, project_root: Path, kind: str) -> Path:
   rel = source.resolve().relative_to(project_root.resolve())
   suffix = ".ifc.o" if kind == "module_interface" else ".o"
   return (obj_dir / rel).with_suffix(suffix)