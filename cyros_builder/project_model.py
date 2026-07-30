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
):
   raw = tomlutil.load_toml(path, must_exist=True)
   kwargs = dict(
      path=path,
      name=tomlutil.require_str(raw, "name", path),
      description=tomlutil.optional_str_default(raw, "description", path, default=""),
      dependencies=tuple(tomlutil.optional_str_list(raw, "dependencies", path)),
      public_headers=_parse_public_headers(raw, path),
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
   return cls(**kwargs)


def _load_source_group_dir(
   base: Path,
   glob: str,
   cls: type,
   *,
   noun: str,
   source_roots_default: list[str] | None = None,
   extra_str_list_fields: tuple[str, ...] = (),
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
      "*/port.toml",
      Port,
      noun="port",
      source_roots_default=["."],
      extra_str_list_fields=("system_libraries",),
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
      known = ", ".join(sorted(ports)) or "<none>"
      raise ValueError(f"Unknown port '{profile.components.port}'. Known ports: {known}")
   port = ports[profile.components.port]

   if port_component.variants and port.name not in port_component.variants:
      known = ", ".join(port_component.variants)
      raise ValueError(
         f"Selected port '{port.name}' is not declared in port/component.toml variants. "
         f"Declared variants: {known}"
      )

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

   return SelectedProject(
      kernel=kernel,
      port_component=port_component,
      port=port,
      time_component=time_component,
      time_driver=time_driver,
      features=selected_features,
   )


def collect_public_headers(selected: SelectedProject) -> tuple[HeaderExport, ...]:
   exports: list[HeaderExport] = []
   exports.extend(selected.kernel.public_headers)
   exports.extend(selected.port_component.public_headers)
   exports.extend(selected.port.public_headers)
   if selected.time_component is not None:
      exports.extend(selected.time_component.public_headers)
   if selected.time_driver is not None:
      exports.extend(selected.time_driver.public_headers)
   for name in sorted(selected.features):
      exports.extend(selected.features[name].public_headers)
   return tuple(exports)


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


def _parse_public_headers(data: dict, path: Path) -> tuple[HeaderExport, ...]:
   values = tomlutil.optional_str_list(data, "public_headers", path)
   exports: list[HeaderExport] = []

   for value in values:
      if "->" not in value:
         raise ValueError(
            f"{path}: expected public_headers entry in 'source -> destination' form, got: {value!r}"
         )
      source_part, destination_part = value.split("->", 1)
      source_text = source_part.strip()
      destination_text = destination_part.strip()
      if not source_text or not destination_text:
         raise ValueError(
            f"{path}: expected public_headers entry in 'source -> destination' form, got: {value!r}"
         )
      exports.append(
         HeaderExport(
            source=(path.parent / source_text).resolve(),
            destination=Path(destination_text),
         )
      )

   return tuple(exports)


