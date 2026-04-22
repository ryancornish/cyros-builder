from collections import deque
from pathlib import Path

from cortos_builder.actions import ArchiveAction, CompileAction
from cortos_builder.output import include_dir, lib_dir, module_dir, obj_dir
from cortos_builder.project_model import iter_source_groups, select_project
from cortos_builder.resolve import ResolvedInvocation
from cortos_builder.source_discovery import DiscoveredSource, discover_component_sources


def plan_build(resolved: ResolvedInvocation) -> list:
   root = resolved.project_root
   tc = resolved.toolchain
   selected = select_project(root, resolved.profile)

   objects_root = obj_dir(resolved)
   libraries_root = lib_dir(resolved)
   modules_root = module_dir(resolved)

   discovered_sources: list[DiscoveredSource] = []
   for group in iter_source_groups(selected):
      discovered_sources.extend(discover_component_sources(group, use_modules=tc.settings.use_modules))

   if tc.settings.use_modules:
      ordered_sources = _order_sources_by_module_dependencies(discovered_sources)
   else:
      ordered_sources = sorted(discovered_sources, key=lambda s: (s.component, str(s.path)))

   actions = []
   object_files: list[Path] = []

   for src in ordered_sources:
      obj = _object_path_for(objects_root, src.path, root, src.kind)
      object_files.append(obj)

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

   if object_files:
      archive = (libraries_root / resolved.profile.output.archive).resolve()
      archive_args = (
         tc.tools.ar,
         "rcs",
         str(archive),
         *[str(obj.resolve()) for obj in object_files],
      )
      actions.append(
         ArchiveAction(
            inputs=tuple(object_files),
            output=archive,
            arguments=archive_args,
            working_directory=root.resolve(),
         )
      )

   return actions


def _order_sources_by_module_dependencies(sources: list[DiscoveredSource]) -> list[DiscoveredSource]:
   sources = sorted(sources, key=lambda s: (s.component, str(s.path)))

   provider_for_module: dict[str, DiscoveredSource] = {}

   for src in sources:
      info = src.module_info
      if info is None:
         continue
      if info.provided_module is not None:
         mod = info.provided_module
         if mod in provider_for_module:
            raise ValueError(
               f"Multiple sources provide module '{mod}':\n"
               f"  {provider_for_module[mod].path}\n"
               f"  {src.path}"
            )
         provider_for_module[mod] = src

   edges: dict[Path, set[Path]] = {src.path: set() for src in sources}
   indegree: dict[Path, int] = {src.path: 0 for src in sources}
   by_path: dict[Path, DiscoveredSource] = {src.path: src for src in sources}

   def add_edge(before: DiscoveredSource, after: DiscoveredSource) -> None:
      if after.path not in edges[before.path]:
         edges[before.path].add(after.path)
         indegree[after.path] += 1

   for src in sources:
      info = src.module_info
      if info is None:
         continue

      if info.implementation_of is not None:
         provider = provider_for_module.get(info.implementation_of)
         if provider is None:
            raise ValueError(
               f"{src.path}: implementation unit for module "
               f"'{info.implementation_of}' has no known provider"
            )
         add_edge(provider, src)

      for imported in info.imports:
         provider = provider_for_module.get(imported)
         if provider is not None:
            add_edge(provider, src)

   ready = deque(sorted(
      (path for path, deg in indegree.items() if deg == 0),
      key=lambda p: str(p),
   ))

   ordered_paths: list[Path] = []

   while ready:
      current = ready.popleft()
      ordered_paths.append(current)

      for nxt in sorted(edges[current], key=lambda p: str(p)):
         indegree[nxt] -= 1
         if indegree[nxt] == 0:
            ready.append(nxt)

   if len(ordered_paths) != len(sources):
      remaining = [str(path) for path, deg in indegree.items() if deg > 0]
      raise ValueError(
         "Module dependency cycle or unresolved ordering among:\n  "
         + "\n  ".join(sorted(remaining))
      )

   return [by_path[path] for path in ordered_paths]


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
