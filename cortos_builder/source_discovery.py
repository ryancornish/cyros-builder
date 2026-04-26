from pathlib import Path

from cortos_builder.project_model import SourceGroup


SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".cppm", ".S", ".s", ".asm"}


def discover_sources(group: SourceGroup, use_modules: bool) -> list[Path]:
   explicit = list(group.sources) + list(group.sources_excluded_from_archive)
   if explicit:
      return _filter_and_validate_sources(explicit, use_modules=use_modules)

   discovered: list[Path] = []
   for root in group.source_roots:
      if not root.is_dir():
         continue
      for path in sorted(root.rglob("*")):
         if not path.is_file():
            continue
         if path.suffix not in SOURCE_SUFFIXES:
            continue
         discovered.append(path.resolve())

   return _filter_and_validate_sources(discovered, use_modules=use_modules)


def discover_archive_sources(group: SourceGroup, use_modules: bool) -> list[Path]:
   if group.sources or group.sources_excluded_from_archive:
      return _filter_and_validate_sources(list(group.sources), use_modules=use_modules)

   all_sources = discover_sources(group, use_modules=use_modules)
   excluded = {p.resolve() for p in group.sources_excluded_from_archive}
   return [p for p in all_sources if p.resolve() not in excluded]


def _filter_and_validate_sources(paths: list[Path], use_modules: bool) -> list[Path]:
   resolved: list[Path] = []
   seen: set[Path] = set()

   for path in paths:
      p = path.resolve()
      if not p.is_file():
         raise FileNotFoundError(f"Missing source file: {p}")

      if not use_modules and p.suffix == ".cppm":
         continue

      if p not in seen:
         seen.add(p)
         resolved.append(p)

   resolved.sort()
   return resolved