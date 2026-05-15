from pathlib import Path

from cortos_builder.actions import ArchiveAction, CompileAction, ObjcopyAction, PartialLinkAction
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
   tc = resolved.toolchain
   selected = select_project(resolved.profile)

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
      obj = _object_path_for(objects_root, src.path, Path.cwd(), src.kind)

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
      actions.extend(
         _plan_archive_pipeline(
            resolved=resolved,
            object_files=archive_object_files,
            working_directory=Path.cwd(),
            libraries_root=libraries_root,
         )
      )

   return actions


def _plan_archive_pipeline(
   *,
   resolved: ResolvedInvocation,
   object_files: list[Path],
   working_directory: Path,
   libraries_root: Path,
) -> list:
   strategy = resolved.toolchain.archive.strategy
   if strategy == "simple":
      return _plan_simple_archive(
         resolved=resolved,
         object_files=object_files,
         working_directory=working_directory,
         libraries_root=libraries_root,
      )
   if strategy == "lto_merged":
      return _plan_lto_merged_archive(
         resolved=resolved,
         object_files=object_files,
         working_directory=working_directory,
         libraries_root=libraries_root,
      )

   raise ValueError(f"Unsupported archive strategy: {strategy}")


def _plan_simple_archive(
   *,
   resolved: ResolvedInvocation,
   object_files: list[Path],
   working_directory: Path,
   libraries_root: Path,
) -> list:
   archive = (libraries_root / resolved.profile.output.archive).resolve()
   archive_args = (
      resolved.toolchain.tools.ar,
      "rcs",
      str(archive),
      *[str(obj.resolve()) for obj in object_files],
   )
   return [
      ArchiveAction(
         inputs=tuple(object_files),
         output=archive,
         arguments=archive_args,
         working_directory=working_directory,
      )
   ]


def _plan_lto_merged_archive(
   *,
   resolved: ResolvedInvocation,
   object_files: list[Path],
   working_directory: Path,
   libraries_root: Path,
) -> list:
   tc = resolved.toolchain
   preserve_lto = resolved.toolchain.archive.preserve_lto_sections
   linker_output = "rel" if preserve_lto else "nolto-rel"
   archive_name = resolved.profile.output.archive
   archive = (libraries_root / archive_name).resolve()

   pipeline_root = (obj_dir(resolved) / "archive").resolve()
   final_object_stem = "cortos"

   mega = (pipeline_root / f"{final_object_stem}.mega_combined.o").resolve()
   filtered = (pipeline_root / f"{final_object_stem}.filtered.o").resolve()
   final_obj = (pipeline_root / f"{final_object_stem}.o").resolve()

   export_file = _resolve_exported_symbols_file(resolved)

   actions: list = []

   merge_args = (
      tc.tools.cxx,
      "-no-pie",
      "-nostdlib",
      "-flto",
      "-flinker-output=" + linker_output,
      "-fuse-linker-plugin",
      "-Wl,-r",
      "-o",
      str(mega),
      *[str(obj.resolve()) for obj in object_files],
   )
   actions.append(
      PartialLinkAction(
         inputs=tuple(object_files),
         output=mega,
         arguments=merge_args,
         working_directory=working_directory,
      )
   )

   current_input = mega

   if tc.archive.filter_exported_symbols:
      filter_args = (
         "objcopy",
         f"--keep-global-symbols={export_file}",
         str(current_input),
         str(filtered),
      )
      actions.append(
         ObjcopyAction(
            input=current_input,
            output=filtered,
            arguments=filter_args,
            working_directory=working_directory,
         )
      )
      current_input = filtered

   if current_input != final_obj:
      rename_args = (
         "objcopy",
         str(current_input),
         str(final_obj),
      )
      actions.append(
         ObjcopyAction(
            input=current_input,
            output=final_obj,
            arguments=rename_args,
            working_directory=working_directory,
         )
      )
      current_input = final_obj

   archive_args = (
      tc.tools.ar,
      "rcs",
      str(archive),
      str(current_input),
   )
   actions.append(
      ArchiveAction(
         inputs=(current_input,),
         output=archive,
         arguments=archive_args,
         working_directory=working_directory,
      )
   )

   return actions
def _resolve_exported_symbols_file(resolved: ResolvedInvocation) -> Path:
   configured = resolved.toolchain.archive.exported_symbols_file
   if configured:
      candidate = Path(configured)
      if not candidate.is_absolute():
         candidate = (resolved.profile.path.parent / ".." / candidate).resolve()
      else:
         candidate = candidate.resolve()
      return candidate

   return (resolved.profile.path.parent / "../exports" / "public_symbols.txt").resolve()


def _load_exported_symbols(path: Path) -> list[str]:
   if not path.is_file():
      raise FileNotFoundError(
         f"Missing exported symbols file for archive pipeline: {path}"
      )

   result: list[str] = []
   for line in path.read_text(encoding="utf-8").splitlines():
      text = line.strip()
      if not text or text.startswith("#"):
         continue
      result.append(text)

   seen: set[str] = set()
   ordered: list[str] = []
   for sym in result:
      if sym not in seen:
         seen.add(sym)
         ordered.append(sym)

   return ordered


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