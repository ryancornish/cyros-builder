from dataclasses import dataclass
from pathlib import Path
import tomllib

from cortos_builder.profile import Profile


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


def load_kernel(profile) -> Kernel:
   path = (profile.layout.source_root / "kernel" / "component.toml").resolve()
   raw = _load_toml(path)
   return Kernel(
      path=path,
      name=_require_str(raw, "name", path),
      description=_optional_str(raw, "description", path, default=""),
      dependencies=tuple(_optional_str_list(raw, "dependencies", path)),
      public_headers=_parse_public_headers(raw, path),
      public_modules=tuple(_optional_str_list(raw, "public_modules", path)),
      private_modules=tuple(_optional_str_list(raw, "private_modules", path)),
      source_roots=_resolve_source_roots(
         meta_path=path,
         values=_optional_str_list(raw, "source_roots", path, default=["."]),
      ),
      sources=_resolve_sources(
         meta_path=path,
         values=_optional_str_list(raw, "sources", path),
      ),
      sources_excluded_from_archive=_resolve_sources(
         meta_path=path,
         values=_optional_str_list(raw, "sources_excluded_from_archive", path),
      ),
      generated_includes=_optional_bool(raw, "generated_includes", path, default=True),
   )


def load_port_component(profile) -> PortComponent:
   path = (profile.layout.source_root / "port" / "component.toml").resolve()
   raw = _load_toml(path)
   return PortComponent(
      path=path,
      name=_require_str(raw, "name", path),
      description=_optional_str(raw, "description", path, default=""),
      dependencies=tuple(_optional_str_list(raw, "dependencies", path)),
      public_headers=_parse_public_headers(raw, path),
      public_modules=tuple(_optional_str_list(raw, "public_modules", path)),
      private_modules=tuple(_optional_str_list(raw, "private_modules", path)),
      source_roots=_resolve_source_roots(
         meta_path=path,
         values=_optional_str_list(raw, "source_roots", path, default=[]),
      ),
      sources=_resolve_sources(
         meta_path=path,
         values=_optional_str_list(raw, "sources", path),
      ),
      sources_excluded_from_archive=_resolve_sources(
         meta_path=path,
         values=_optional_str_list(raw, "sources_excluded_from_archive", path),
      ),
      generated_includes=_optional_bool(raw, "generated_includes", path, default=True),
      variants=tuple(_optional_str_list(raw, "variants", path)),
   )


def load_ports(profile) -> dict[str, Port]:
   result: dict[str, Port] = {}
   base = (profile.layout.source_root / "port").resolve()
   if not base.is_dir():
      return result

   for meta in sorted(base.glob("*/port.toml")):
      raw = _load_toml(meta)
      port = Port(
         path=meta.resolve(),
         name=_require_str(raw, "name", meta),
         description=_optional_str(raw, "description", meta, default=""),
         dependencies=tuple(_optional_str_list(raw, "dependencies", meta)),
         public_headers=_parse_public_headers(raw, meta),
         public_modules=tuple(_optional_str_list(raw, "public_modules", meta)),
         private_modules=tuple(_optional_str_list(raw, "private_modules", meta)),
         source_roots=_resolve_source_roots(
            meta_path=meta,
            values=_optional_str_list(raw, "source_roots", meta, default=["."]),
         ),
         sources=_resolve_sources(
            meta_path=meta,
            values=_optional_str_list(raw, "sources", meta),
         ),
         sources_excluded_from_archive=_resolve_sources(
            meta_path=meta,
            values=_optional_str_list(raw, "sources_excluded_from_archive", meta),
         ),
         generated_includes=_optional_bool(raw, "generated_includes", meta, default=True),
         system_libraries=tuple(_optional_str_list(raw, "system_libraries", meta)),
      )
      if port.name in result:
         raise ValueError(f"Duplicate port '{port.name}'")
      result[port.name] = port

   return result


def load_time_component(profile) -> TimeComponent:
   path = (profile.layout.source_root / "time" / "component.toml").resolve()
   raw = _load_toml(path)
   return TimeComponent(
      path=path,
      name=_require_str(raw, "name", path),
      description=_optional_str(raw, "description", path, default=""),
      dependencies=tuple(_optional_str_list(raw, "dependencies", path)),
      public_headers=_parse_public_headers(raw, path),
      public_modules=tuple(_optional_str_list(raw, "public_modules", path)),
      private_modules=tuple(_optional_str_list(raw, "private_modules", path)),
      source_roots=_resolve_source_roots(
         meta_path=path,
         values=_optional_str_list(raw, "source_roots", path, default=[]),
      ),
      sources=_resolve_sources(
         meta_path=path,
         values=_optional_str_list(raw, "sources", path),
      ),
      sources_excluded_from_archive=_resolve_sources(
         meta_path=path,
         values=_optional_str_list(raw, "sources_excluded_from_archive", path),
      ),
      generated_includes=_optional_bool(raw, "generated_includes", path, default=True),
      variants=tuple(_optional_str_list(raw, "variants", path)),
   )


def load_time_drivers(profile) -> dict[str, TimeDriver]:
   result: dict[str, TimeDriver] = {}
   base = (profile.layout.source_root / "time").resolve()
   if not base.is_dir():
      return result

   for meta in sorted(base.glob("*/time_driver.toml")):
      raw = _load_toml(meta)
      td = TimeDriver(
         path=meta.resolve(),
         name=_require_str(raw, "name", meta),
         description=_optional_str(raw, "description", meta, default=""),
         dependencies=tuple(_optional_str_list(raw, "dependencies", meta)),
         public_headers=_parse_public_headers(raw, meta),
         public_modules=tuple(_optional_str_list(raw, "public_modules", meta)),
         private_modules=tuple(_optional_str_list(raw, "private_modules", meta)),
         source_roots=_resolve_source_roots(
            meta_path=meta,
            values=_optional_str_list(raw, "source_roots", meta, default=["."]),
         ),
         sources=_resolve_sources(
            meta_path=meta,
            values=_optional_str_list(raw, "sources", meta),
         ),
         sources_excluded_from_archive=_resolve_sources(
            meta_path=meta,
            values=_optional_str_list(raw, "sources_excluded_from_archive", meta),
         ),
         generated_includes=_optional_bool(raw, "generated_includes", meta, default=True),
      )
      if td.name in result:
         raise ValueError(f"Duplicate time driver '{td.name}'")
      result[td.name] = td

   return result


def load_features(profile) -> dict[str, Feature]:
   result: dict[str, Feature] = {}
   base = (profile.layout.source_root / "libcortos").resolve()
   if not base.is_dir():
      return result

   for meta in sorted(base.glob("*/feature.toml")):
      raw = _load_toml(meta)
      feat = Feature(
         path=meta.resolve(),
         name=_require_str(raw, "name", meta),
         description=_optional_str(raw, "description", meta, default=""),
         dependencies=tuple(_optional_str_list(raw, "dependencies", meta)),
         public_headers=_parse_public_headers(raw, meta),
         public_modules=tuple(_optional_str_list(raw, "public_modules", meta)),
         private_modules=tuple(_optional_str_list(raw, "private_modules", meta)),
         source_roots=_resolve_source_roots(
            meta_path=meta,
            values=_optional_str_list(raw, "source_roots", meta, default=["."]),
         ),
         sources=_resolve_sources(
            meta_path=meta,
            values=_optional_str_list(raw, "sources", meta),
         ),
         sources_excluded_from_archive=_resolve_sources(
            meta_path=meta,
            values=_optional_str_list(raw, "sources_excluded_from_archive", meta),
         ),
         generated_includes=_optional_bool(raw, "generated_includes", meta, default=True),
      )
      if feat.name in result:
         raise ValueError(f"Duplicate feature '{feat.name}'")
      result[feat.name] = feat

   return result


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


def _load_toml(path: Path) -> dict:
   if not path.is_file():
      raise FileNotFoundError(path)
   with path.open("rb") as f:
      raw = tomllib.load(f)
   if not isinstance(raw, dict):
      raise ValueError(f"{path}: root TOML document must be a table")
   return raw


def _resolve_source_roots(meta_path: Path, values: list[str]) -> tuple[Path, ...]:
   base = meta_path.parent
   return tuple((base / value).resolve() for value in values)


def _resolve_sources(meta_path: Path, values: list[str]) -> tuple[Path, ...]:
   base = meta_path.parent
   return tuple((base / value).resolve() for value in values)


def _parse_public_headers(data: dict, path: Path) -> tuple[HeaderExport, ...]:
   values = _optional_str_list(data, "public_headers", path)
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


def _require_str(data: dict, key: str, path: Path) -> str:
   value = data.get(key)
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string")
   return value


def _optional_str(data: dict, key: str, path: Path, default: str = "") -> str:
   value = data.get(key)
   if value is None:
      return default
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string")
   return value


def _optional_bool(data: dict, key: str, path: Path, default: bool = False) -> bool:
   value = data.get(key)
   if value is None:
      return default
   if not isinstance(value, bool):
      raise ValueError(f"{path}: expected '{key}' to be a bool")
   return value


def _optional_str_list(data: dict, key: str, path: Path, default: list[str] | None = None) -> list[str]:
   value = data.get(key)
   if value is None:
      return [] if default is None else list(default)
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")
   return list(value)