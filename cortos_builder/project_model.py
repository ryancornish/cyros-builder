from dataclasses import dataclass
from pathlib import Path
import tomllib


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
   generated_includes: bool


@dataclass(frozen=True)
class Kernel(SourceGroup):
   pass


@dataclass(frozen=True)
class Port(SourceGroup):
   system_libraries: tuple[str, ...]


@dataclass(frozen=True)
class TimeDriver(SourceGroup):
   pass


@dataclass(frozen=True)
class Feature(SourceGroup):
   pass


@dataclass(frozen=True)
class SelectedProject:
   kernel: Kernel
   port: Port
   time_driver: TimeDriver
   features: dict[str, Feature]


def load_kernel(root: Path) -> Kernel:
   path = (root / "src" / "kernel" / "component.toml").resolve()
   raw = _load_toml(path)
   return Kernel(
      path=path,
      name=_require_str(raw, "name", path),
      description=_require_str(raw, "description", path),
      dependencies=tuple(_require_str_list(raw, "dependencies", path)),
      public_headers=_parse_public_headers(raw, path),
      public_modules=tuple(_optional_str_list(raw, "public_modules", path)),
      private_modules=tuple(_optional_str_list(raw, "private_modules", path)),
      source_roots=_resolve_source_roots(path, _require_str_list(raw, "source_roots", path)),
      generated_includes=_require_bool(raw, "generated_includes", path),
   )


def load_ports(root: Path) -> dict[str, Port]:
   result: dict[str, Port] = {}
   base = (root / "src" / "port").resolve()
   if not base.is_dir():
      return result

   for meta in sorted(base.glob("*/port.toml")):
      raw = _load_toml(meta)
      port = Port(
         path=meta.resolve(),
         name=_require_str(raw, "name", meta),
         description=_require_str(raw, "description", meta),
         dependencies=tuple(_require_str_list(raw, "dependencies", meta)),
         public_headers=_parse_public_headers(raw, meta),
         public_modules=tuple(_optional_str_list(raw, "public_modules", meta)),
         private_modules=tuple(_optional_str_list(raw, "private_modules", meta)),
         source_roots=_resolve_source_roots(meta, _require_str_list(raw, "source_roots", meta)),
         generated_includes=_require_bool(raw, "generated_includes", meta),
         system_libraries=tuple(_require_str_list(raw, "system_libraries", meta)),
      )
      if port.name in result:
         raise ValueError(f"Duplicate port '{port.name}'")
      result[port.name] = port

   return result


def load_time_drivers(root: Path) -> dict[str, TimeDriver]:
   result: dict[str, TimeDriver] = {}
   base = (root / "src" / "time").resolve()
   if not base.is_dir():
      return result

   for meta in sorted(base.glob("*/time_driver.toml")):
      raw = _load_toml(meta)
      td = TimeDriver(
         path=meta.resolve(),
         name=_require_str(raw, "name", meta),
         description=_require_str(raw, "description", meta),
         dependencies=tuple(_require_str_list(raw, "dependencies", meta)),
         public_headers=_parse_public_headers(raw, meta),
         public_modules=tuple(_optional_str_list(raw, "public_modules", meta)),
         private_modules=tuple(_optional_str_list(raw, "private_modules", meta)),
         source_roots=_resolve_source_roots(meta, _require_str_list(raw, "source_roots", meta)),
         generated_includes=_require_bool(raw, "generated_includes", meta),
      )
      if td.name in result:
         raise ValueError(f"Duplicate time driver '{td.name}'")
      result[td.name] = td

   return result


def load_features(root: Path) -> dict[str, Feature]:
   result: dict[str, Feature] = {}
   base = (root / "src" / "libcortos").resolve()
   if not base.is_dir():
      return result

   for meta in sorted(base.glob("*/feature.toml")):
      raw = _load_toml(meta)
      feat = Feature(
         path=meta.resolve(),
         name=_require_str(raw, "name", meta),
         description=_require_str(raw, "description", meta),
         dependencies=tuple(_require_str_list(raw, "dependencies", meta)),
         public_headers=_parse_public_headers(raw, meta),
         public_modules=tuple(_optional_str_list(raw, "public_modules", meta)),
         private_modules=tuple(_optional_str_list(raw, "private_modules", meta)),
         source_roots=_resolve_source_roots(meta, _require_str_list(raw, "source_roots", meta)),
         generated_includes=_require_bool(raw, "generated_includes", meta),
      )
      if feat.name in result:
         raise ValueError(f"Duplicate feature '{feat.name}'")
      result[feat.name] = feat

   return result


def select_project(root: Path, profile) -> SelectedProject:
   kernel = load_kernel(root)

   ports = load_ports(root)
   if profile.build.port not in ports:
      known = ", ".join(sorted(ports)) or "<none>"
      raise ValueError(f"Unknown port '{profile.build.port}'. Known ports: {known}")
   port = ports[profile.build.port]

   time_drivers = load_time_drivers(root)
   if profile.build.time_driver not in time_drivers:
      known = ", ".join(sorted(time_drivers)) or "<none>"
      raise ValueError(
         f"Unknown time driver '{profile.build.time_driver}'. Known time drivers: {known}"
      )
   time_driver = time_drivers[profile.build.time_driver]

   all_features = load_features(root)
   selected_features: dict[str, Feature] = {}

   for name in profile.libcortos.enable:
      if name not in all_features:
         known = ", ".join(sorted(all_features)) or "<none>"
         raise ValueError(f"Unknown libcortos feature '{name}'. Known features: {known}")
      selected_features[name] = all_features[name]

   _validate_feature_dependencies(selected_features)

   return SelectedProject(
      kernel=kernel,
      port=port,
      time_driver=time_driver,
      features=selected_features,
   )


def collect_public_headers(selected: SelectedProject) -> tuple[HeaderExport, ...]:
   exports: list[HeaderExport] = []
   exports.extend(selected.kernel.public_headers)
   exports.extend(selected.port.public_headers)
   exports.extend(selected.time_driver.public_headers)
   for name in sorted(selected.features):
      exports.extend(selected.features[name].public_headers)
   return tuple(exports)


def collect_public_modules(selected: SelectedProject) -> tuple[str, ...]:
   modules: list[str] = []
   modules.extend(selected.kernel.public_modules)
   modules.extend(selected.port.public_modules)
   modules.extend(selected.time_driver.public_modules)
   for name in sorted(selected.features):
      modules.extend(selected.features[name].public_modules)
   return tuple(modules)


def iter_source_groups(selected: SelectedProject):
   yield selected.kernel
   yield selected.port
   yield selected.time_driver
   for name in sorted(selected.features):
      yield selected.features[name]


def _validate_feature_dependencies(selected_features: dict[str, Feature]) -> None:
   selected_names = set(selected_features)

   for feature in selected_features.values():
      for dep in feature.dependencies:
         if dep in {"kernel", "port", "time"}:
            continue
         if dep not in selected_names:
            raise ValueError(
               f"Selected libcortos feature '{feature.name}' depends on '{dep}', "
               f"but '{dep}' is not enabled"
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


def _require_bool(data: dict, key: str, path: Path) -> bool:
   value = data.get(key)
   if not isinstance(value, bool):
      raise ValueError(f"{path}: expected '{key}' to be a bool")
   return value


def _require_str_list(data: dict, key: str, path: Path) -> list[str]:
   value = data.get(key)
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")
   return value


def _optional_str_list(data: dict, key: str, path: Path) -> list[str]:
   value = data.get(key)
   if value is None:
      return []
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")
   return list(value)


def collect_system_libraries(selected: SelectedProject) -> tuple[str, ...]:
   libs: list[str] = []
   libs.extend(selected.port.system_libraries)

   seen: set[str] = set()
   ordered: list[str] = []
   for lib in libs:
      if lib not in seen:
         seen.add(lib)
         ordered.append(lib)

   return tuple(ordered)
