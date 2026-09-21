import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from cyros_builder import tomlutil
from cyros_builder.profile import Profile


@dataclass(frozen=True)
class HeaderExport:
   source: Path
   destination: Path


@dataclass(frozen=True)
class SourceGroup:
   path: Path
   name: str
   description: str
   dependencies: tuple[str, ...]
   public_headers: tuple[HeaderExport, ...]
   # Directories laid out as an include namespace (e.g. <root>/cyros/port/port.h)
   # that go on the include path of every compile in the project AND its unit
   # tests, but are never copied anywhere and never exported. Nothing outside the
   # project can reach them. See _validate_header_visibility.
   internal_include_roots: tuple[Path, ...]
   public_modules: tuple[str, ...]
   private_modules: tuple[str, ...]
   source_roots: tuple[Path, ...]
   sources: tuple[Path, ...]
   sources_excluded_from_archive: tuple[Path, ...]
   generated_includes: bool
   private_includes: tuple[Path, ...]   # -I dirs applied only to this group's sources


@dataclass(frozen=True)
class Kernel(SourceGroup):
   pass


@dataclass(frozen=True)
class PortComponent(SourceGroup):
   variants: tuple[str, ...]


@dataclass(frozen=True)
class Port(SourceGroup):
   system_libraries: tuple[str, ...]
   # Name of another port variant this one builds on, or None. A port contract
   # is layered (core, then MCU), and `extends` is how a target variant picks up
   # the core layer that implements the half it does not. Resolved away by
   # _resolve_extends before anything else sees the Port, so every consumer
   # below deals in one flat group.
   extends: str | None


@dataclass(frozen=True)
class TimeComponent(SourceGroup):
   variants: tuple[str, ...]


@dataclass(frozen=True)
class TimeDriver(SourceGroup):
   pass


@dataclass(frozen=True)
class Feature(SourceGroup):
   pass


@dataclass(frozen=True)
class SelectedProject:
   kernel: Kernel
   port_component: PortComponent
   port: Port
   time_component: TimeComponent | None   # None when no time driver is selected
   time_driver: TimeDriver | None         # None when no time driver is selected
   features: dict[str, Feature]


def _load_source_group(
   path: Path,
   cls: type,
   *,
   source_roots_default: list[str] | None = None,
   extra_str_list_fields: tuple[str, ...] = (),
   extra_optional_str_fields: tuple[str, ...] = (),
):
   raw = tomlutil.load_toml(path, must_exist=True)
   kwargs = dict(
      path=path,
      name=tomlutil.require_str(raw, "name", path),
      description=tomlutil.optional_str_default(raw, "description", path, default=""),
      dependencies=tuple(tomlutil.optional_str_list(raw, "dependencies", path)),
      public_headers=_parse_header_exports(raw, path, "public_headers"),
      internal_include_roots=_resolve_dirs(
         meta_path=path,
         values=tomlutil.optional_str_list(raw, "internal_include_roots", path),
      ),
      public_modules=tuple(tomlutil.optional_str_list(raw, "public_modules", path)),
      private_modules=tuple(tomlutil.optional_str_list(raw, "private_modules", path)),
      source_roots=_resolve_source_roots(
         meta_path=path,
         values=tomlutil.optional_str_list(raw, "source_roots", path, default=source_roots_default),
      ),
      sources=_resolve_sources(
         meta_path=path,
         values=tomlutil.optional_str_list(raw, "sources", path),
      ),
      sources_excluded_from_archive=_resolve_sources(
         meta_path=path,
         values=tomlutil.optional_str_list(raw, "sources_excluded_from_archive", path),
      ),
      generated_includes=tomlutil.optional_bool(raw, "generated_includes", path, default=True),
      private_includes=_resolve_dirs(
         meta_path=path,
         values=tomlutil.optional_str_list(raw, "private_includes", path),
      ),
   )
   for field in extra_str_list_fields:
      kwargs[field] = tuple(tomlutil.optional_str_list(raw, field, path))
   for field in extra_optional_str_fields:
      kwargs[field] = tomlutil.optional_nonempty_str(raw, field, path)
   return cls(**kwargs)


def _load_source_group_dir(
   base: Path,
   glob: str,
   cls: type,
   *,
   noun: str,
   source_roots_default: list[str] | None = None,
   extra_str_list_fields: tuple[str, ...] = (),
   extra_optional_str_fields: tuple[str, ...] = (),
) -> dict[str, SourceGroup]:
   result: dict[str, SourceGroup] = {}
   if not base.is_dir():
      return result

   for meta in sorted(base.glob(glob)):
      item = _load_source_group(
         meta.resolve(),
         cls,
         source_roots_default=source_roots_default,
         extra_str_list_fields=extra_str_list_fields,
         extra_optional_str_fields=extra_optional_str_fields,
      )
      if item.name in result:
         raise ValueError(f"Duplicate {noun} '{item.name}'")
      result[item.name] = item

   return result


def load_kernel(profile) -> Kernel:
   path = (profile.layout.source_root / "kernel" / "component.toml").resolve()
   return _load_source_group(path, Kernel, source_roots_default=["."])


def load_port_component(profile) -> PortComponent:
   path = (profile.layout.source_root / "port" / "component.toml").resolve()
   return _load_source_group(
      path, PortComponent, source_roots_default=[], extra_str_list_fields=("variants",)
   )


def load_ports(profile) -> dict[str, Port]:
   base = (profile.layout.source_root / "port").resolve()
   return _load_source_group_dir(
      base,
      "**/port.toml",
      Port,
      noun="port",
      source_roots_default=["."],
      extra_str_list_fields=("system_libraries",),
      extra_optional_str_fields=("extends",),
   )


def _extends_chain(port: Port, ports: dict[str, Port]) -> list[Port]:
   """The selected port and its bases, ROOT FIRST.

   Root-first is what makes the merge below read the way inheritance does: a
   base contributes first and the derived variant appends to or overrides it.
   """
   chain: list[Port] = []
   seen: list[str] = []
   current: Port | None = port

   while current is not None:
      if current.name in seen:
         cycle = " -> ".join([*seen[seen.index(current.name):], current.name])
         raise ValueError(
            f"{current.path}: 'extends' forms a cycle: {cycle}"
         )
      seen.append(current.name)
      chain.append(current)

      if current.extends is None:
         break
      base = ports.get(current.extends)
      if base is None:
         known = ", ".join(sorted(n for n in ports if n != current.name)) or "<none>"
         raise ValueError(
            f"{current.path}: port '{current.name}' extends unknown port "
            f"'{current.extends}'. Known ports: {known}"
         )
      current = base

   chain.reverse()
   return chain


def _resolve_extends(port: Port, ports: dict[str, Port]) -> Port:
   """Flatten a port and its bases into one group.

   Everything below the model deals in a single Port, so the layering is a
   MANIFEST concept only: nothing in the planner, the archiver or the staleness
   tracker learns that a port can have a base. Paths are already absolute by the
   time they reach here, so the merge is a plain ordered union.

   Two rules worth stating, because they are what makes the split useful:
     * `sources` and the include/library lists ACCUMULATE, so a core layer's
       sources and its header directory come along automatically.
     * `public_headers` OVERRIDE by destination, so a target's port_traits.h
       replaces its base's rather than colliding with it. That is how an MCU
       layer sets CYROS_PORT_CORE_COUNT, which the core layer cannot know.
   """
   chain = _extends_chain(port, ports)
   if len(chain) == 1:
      return port

   def union(attr: str) -> tuple:
      seen: set = set()
      ordered: list = []
      for link in chain:
         for value in getattr(link, attr):
            if value not in seen:
               seen.add(value)
               ordered.append(value)
      return tuple(ordered)

   # Keyed by destination, so a later (more derived) link replaces an earlier
   # one in place rather than appending a second export of the same header.
   headers: dict[Path, HeaderExport] = {}
   for link in chain:
      for export in link.public_headers:
         headers[export.destination] = export

   return Port(
      # Identity stays the DERIVED variant's: it is what the profile named, what
      # the object tree is namespaced under, and what an error should blame.
      path=port.path,
      name=port.name,
      description=port.description,
      dependencies=union("dependencies"),
      public_headers=tuple(headers.values()),
      internal_include_roots=union("internal_include_roots"),
      public_modules=union("public_modules"),
      private_modules=union("private_modules"),
      source_roots=union("source_roots"),
      sources=union("sources"),
      sources_excluded_from_archive=union("sources_excluded_from_archive"),
      generated_includes=port.generated_includes,
      private_includes=union("private_includes"),
      system_libraries=union("system_libraries"),
      extends=None,   # resolved
   )


def load_time_component(profile) -> TimeComponent:
   path = (profile.layout.source_root / "time" / "component.toml").resolve()
   return _load_source_group(
      path, TimeComponent, source_roots_default=[], extra_str_list_fields=("variants",)
   )


def load_time_drivers(profile) -> dict[str, TimeDriver]:
   base = (profile.layout.source_root / "time").resolve()
   return _load_source_group_dir(
      base, "*/time_driver.toml", TimeDriver, noun="time driver", source_roots_default=["."]
   )


def load_features(profile) -> dict[str, Feature]:
   base = (profile.layout.source_root / "userlib").resolve()
   return _load_source_group_dir(
      base, "*/feature.toml", Feature, noun="feature", source_roots_default=["."]
   )


def select_project(profile: Profile) -> SelectedProject:
   kernel = load_kernel(profile)
   port_component = load_port_component(profile)

   ports = load_ports(profile)
   if profile.components.port not in ports:
      # SELECTABLE ports, not every port.toml on disk. A base layer has a
      # port.toml and is loaded (something has to extend it) but is deliberately
      # absent from variants, so offering it here would name something the very
      # next check refuses.
      selectable = sorted(set(port_component.variants) & set(ports)) or sorted(ports)
      known = ", ".join(selectable) or "<none>"
      raise ValueError(f"Unknown port '{profile.components.port}'. Known ports: {known}")
   port = ports[profile.components.port]

   if port_component.variants and port.name not in port_component.variants:
      known = ", ".join(port_component.variants)
      raise ValueError(
         f"Selected port '{port.name}' is not declared in port/component.toml variants. "
         f"Declared variants: {known}"
      )

   # After the variants gate, so that a base LAYER (which is deliberately absent
   # from variants) still cannot be selected on its own, only extended.
   port = _resolve_extends(port, ports)

   # Time driver is optional. When components.time_driver is None, no time
   # driver (and no time component metadata) is loaded or compiled into the
   # archive. A feature that depends on "time" will fail validation below.
   time_component: TimeComponent | None = None
   time_driver: TimeDriver | None = None

   if profile.components.time_driver is not None:
      time_component = load_time_component(profile)

      time_drivers = load_time_drivers(profile)
      if profile.components.time_driver not in time_drivers:
         known = ", ".join(sorted(time_drivers)) or "<none>"
         raise ValueError(
            f"Unknown time driver '{profile.components.time_driver}'. "
            f"Known time drivers: {known}"
         )
      time_driver = time_drivers[profile.components.time_driver]

      if time_component.variants and time_driver.name not in time_component.variants:
         known = ", ".join(time_component.variants)
         raise ValueError(
            f"Selected time driver '{time_driver.name}' is not declared in "
            f"time/component.toml variants. Declared variants: {known}"
         )

   all_features = load_features(profile)
   selected_features: dict[str, Feature] = {}

   for name in profile.features.enable:
      if name not in all_features:
         known = ", ".join(sorted(all_features)) or "<none>"
         raise ValueError(f"Unknown feature '{name}'. Known features: {known}")
      selected_features[name] = all_features[name]

   _validate_feature_dependencies(selected_features, has_time_driver=time_driver is not None)
   _validate_source_separation(kernel)
   _validate_source_separation(port_component)
   _validate_source_separation(port)
   if time_component is not None:
      _validate_source_separation(time_component)
   if time_driver is not None:
      _validate_source_separation(time_driver)
   for feat in selected_features.values():
      _validate_source_separation(feat)

   selected = SelectedProject(
      kernel=kernel,
      port_component=port_component,
      port=port,
      time_component=time_component,
      time_driver=time_driver,
      features=selected_features,
   )
   _validate_header_visibility(selected)
   return selected


def _header_groups(selected: SelectedProject) -> list[SourceGroup]:
   """Every selected group that can contribute headers, in export order."""
   groups: list[SourceGroup] = [selected.kernel, selected.port_component, selected.port]
   if selected.time_component is not None:
      groups.append(selected.time_component)
   if selected.time_driver is not None:
      groups.append(selected.time_driver)
   for name in sorted(selected.features):
      groups.append(selected.features[name])
   return groups


def collect_public_headers(selected: SelectedProject) -> tuple[HeaderExport, ...]:
   """Headers copied into the exported include tree."""
   return tuple(e for g in _header_groups(selected) for e in g.public_headers)


def collect_internal_include_roots(selected: SelectedProject) -> tuple[Path, ...]:
   """Include directories the project's own compiles and unit tests see.

   Deduplicated, first declaration wins, so the order is stable for goldens.
   Never exported: they are source directories, not generated ones, so there is
   nothing in the build output for a consumer to stumble into.
   """
   seen: set[Path] = set()
   ordered: list[Path] = []
   for group in _header_groups(selected):
      for root in group.internal_include_roots:
         if root not in seen:
            seen.add(root)
            ordered.append(root)
   return tuple(ordered)


def collect_public_modules(selected: SelectedProject) -> tuple[str, ...]:
   modules: list[str] = []
   modules.extend(selected.kernel.public_modules)
   modules.extend(selected.port_component.public_modules)
   modules.extend(selected.port.public_modules)
   if selected.time_component is not None:
      modules.extend(selected.time_component.public_modules)
   if selected.time_driver is not None:
      modules.extend(selected.time_driver.public_modules)
   for name in sorted(selected.features):
      modules.extend(selected.features[name].public_modules)
   return tuple(modules)


def iter_source_groups(selected: SelectedProject):
   yield selected.kernel
   yield selected.port
   if selected.time_driver is not None:
      yield selected.time_driver
   for name in sorted(selected.features):
      yield selected.features[name]


def collect_system_libraries(selected: SelectedProject) -> tuple[str, ...]:
   seen: set[str] = set()
   ordered: list[str] = []
   for lib in selected.port.system_libraries:
      if lib not in seen:
         seen.add(lib)
         ordered.append(lib)
   return tuple(ordered)


def _validate_feature_dependencies(
   selected_features: dict[str, Feature],
   *,
   has_time_driver: bool,
) -> None:
   selected_names = set(selected_features)
   for feature in selected_features.values():
      for dep in feature.dependencies:
         if dep == "time":
            # 'time' is satisfied only if a time driver is selected.
            if not has_time_driver:
               raise ValueError(
                  f"Selected feature '{feature.name}' depends on 'time', "
                  f"but no time driver is selected. Set components.time_driver "
                  f"in the profile, or (for unit tests) in the test's test.toml."
               )
            continue
         if dep in {"kernel", "port"}:
            continue
         if dep not in selected_names:
            raise ValueError(
               f"Selected feature '{feature.name}' depends on '{dep}', "
               f"but '{dep}' is not enabled"
            )


def _validate_source_separation(group: SourceGroup) -> None:
   normal = set(group.sources)
   excluded = set(group.sources_excluded_from_archive)
   overlap = sorted(normal & excluded)
   if overlap:
      names = ", ".join(str(p) for p in overlap)
      raise ValueError(
         f"{group.path}: sources and sources_excluded_from_archive overlap: {names}"
      )


# `#include <x>` or `#include "x"` at the start of a line. Anchored so that a
# commented-out include (`// #include <x>`) does not count. A `/* ... */` block
# that happens to start a line with #include would count, which errs toward
# reporting a leak rather than missing one.
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.MULTILINE)


def _validate_header_visibility(selected: SelectedProject) -> None:
   """Enforce the rule that makes internal headers actually internal.

   No PUBLIC header may include an INTERNAL one. It would compile inside the
   project, where the internal roots are on the include path, and break every
   consumer, who only ever gets the exported tree. That failure would surface far
   from its cause, so it is caught here, naming the file.

   An include counts as internal when it resolves under one of the internal
   roots and NOT next to the including header (where a quote include looks
   first). Scanning each public header directly also covers chains: a public
   header reaching an internal one through another public header is caught at
   that other header.
   """
   roots = collect_internal_include_roots(selected)
   if not roots:
      return

   for root in roots:
      if not root.is_dir():
         raise ValueError(
            f"internal_include_roots entry does not exist or is not a directory: {root}"
         )

   leaks: list[str] = []
   for export in collect_public_headers(selected):
      if not export.source.is_file():
         continue  # populate_include_tree reports a missing header with its own message
      for target in _INCLUDE_RE.findall(export.source.read_text(errors="replace")):
         if (export.source.parent / target).is_file():
            continue  # resolves next to the includer, so it is not the internal one
         hit = next((root / target for root in roots if (root / target).is_file()), None)
         if hit is not None:
            leaks.append(
               f"{export.source}: public header '{export.destination.as_posix()}' "
               f"includes internal header '{target}'"
            )

   if leaks:
      raise ValueError(
         "Public header(s) include internal header(s), which are never exported, so "
         "every consumer including them would fail to compile:\n  "
         + "\n  ".join(sorted(leaks))
         + "\nMove the include into a source file, make the includer internal too, "
         "or export the included header."
      )


def _resolve_source_roots(meta_path: Path, values: list[str]) -> tuple[Path, ...]:
   base = meta_path.parent
   return tuple((base / value).resolve() for value in values)


def _resolve_sources(meta_path: Path, values: list[str]) -> tuple[Path, ...]:
   base = meta_path.parent
   return tuple((base / value).resolve() for value in values)


def _resolve_dirs(meta_path: Path, values: list[str]) -> tuple[Path, ...]:
   """
   Resolve a list of directory paths relative to a TOML file. Unlike sources,
   we don't require them to exist at load time — they may be generated later,
   or live alongside an optional external dependency.
   """
   base = meta_path.parent
   return tuple((base / value).resolve() for value in values)


def _parse_header_exports(data: dict, path: Path, key: str) -> tuple[HeaderExport, ...]:
   """Parse a `key = ["source -> destination", ...]` list (public or internal)."""
   values = tomlutil.optional_str_list(data, key, path)
   exports: list[HeaderExport] = []

   for value in values:
      if "->" not in value:
         raise ValueError(
            f"{path}: expected {key} entry in 'source -> destination' form, got: {value!r}"
         )
      source_part, destination_part = value.split("->", 1)
      source_text = source_part.strip()
      destination_text = destination_part.strip()
      if not source_text or not destination_text:
         raise ValueError(
            f"{path}: expected {key} entry in 'source -> destination' form, got: {value!r}"
         )
      exports.append(
         HeaderExport(
            source=(path.parent / source_text).resolve(),
            destination=Path(destination_text),
         )
      )

   return tuple(exports)


