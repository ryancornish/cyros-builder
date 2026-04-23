from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class LayoutConfig:
   project_root: Path
   build_root: Path
   source_root: Path
   output_root: Path


@dataclass(frozen=True)
class BuildConfig:
   port: str
   time_driver: str
   config_header: Path


@dataclass(frozen=True)
class FeaturesConfig:
   enable: tuple[str, ...]


@dataclass(frozen=True)
class OutputConfig:
   archive: str


@dataclass(frozen=True)
class Profile:
   path: Path
   name: str
   default_toolchain: str | None
   layout: LayoutConfig
   build: BuildConfig
   features: FeaturesConfig
   output: OutputConfig


def _expect_table(data: dict, key: str, profile_path: Path) -> dict:
   value = data.get(key)
   if not isinstance(value, dict):
      raise ValueError(f"{profile_path}: expected [{key}] table")
   return value


def _require_str(data: dict, key: str, profile_path: Path) -> str:
   value = data.get(key)
   if not isinstance(value, str):
      raise ValueError(f"{profile_path}: expected '{key}' to be a string")
   return value


def _optional_str(data: dict, key: str, profile_path: Path) -> str | None:
   value = data.get(key)
   if value is None:
      return None
   if not isinstance(value, str):
      raise ValueError(f"{profile_path}: expected '{key}' to be a string if present")
   return value


def _require_str_list(data: dict, key: str, profile_path: Path) -> list[str]:
   value = data.get(key)
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{profile_path}: expected '{key}' to be a list of strings")
   return value


def _resolve_relative(profile_path: Path, value: str) -> Path:
   return (profile_path.parent / value).resolve()


def _require_existing_dir(path: Path, desc: str, profile_path: Path) -> Path:
   if not path.is_dir():
      raise ValueError(f"{profile_path}: resolved {desc} does not exist or is not a directory: {path}")
   return path


def _require_existing_file(path: Path, desc: str, profile_path: Path) -> Path:
   if not path.is_file():
      raise ValueError(f"{profile_path}: resolved {desc} does not exist or is not a file: {path}")
   return path


def load_profile(path: Path) -> Profile:
   profile_path = path.resolve()

   with profile_path.open("rb") as f:
      raw = tomllib.load(f)

   if not isinstance(raw, dict):
      raise ValueError(f"{profile_path}: root TOML document must be a table")

   layout_raw = _expect_table(raw, "layout", profile_path)
   build_raw = _expect_table(raw, "build", profile_path)
   features_raw = _expect_table(raw, "features", profile_path)
   output_raw = _expect_table(raw, "output", profile_path)

   project_root = _require_existing_dir(
      _resolve_relative(profile_path, _require_str(layout_raw, "project_root", profile_path)),
      "layout.project_root",
      profile_path,
   )
   build_root = _require_existing_dir(
      _resolve_relative(profile_path, _require_str(layout_raw, "build_root", profile_path)),
      "layout.build_root",
      profile_path,
   )
   source_root = _require_existing_dir(
      _resolve_relative(profile_path, _require_str(layout_raw, "source_root", profile_path)),
      "layout.source_root",
      profile_path,
   )
   output_root = _resolve_relative(profile_path, _require_str(layout_raw, "output_root", profile_path))

   config_header = _require_existing_file(
      (build_root / "configs" / _require_str(build_raw, "config_header", profile_path)).resolve(),
      "build.config_header",
      profile_path,
   )

   toolchain_name = _optional_str(raw, "default_toolchain", profile_path)
   if toolchain_name is not None:
      toolchain_path = (build_root / "toolchains" / f"{toolchain_name}.toml").resolve()
      if not toolchain_path.is_file():
         raise ValueError(
            f"{profile_path}: default_toolchain '{toolchain_name}' was not found at {toolchain_path}"
         )

   return Profile(
      path=profile_path,
      name=_require_str(raw, "name", profile_path),
      default_toolchain=toolchain_name,
      layout=LayoutConfig(
         project_root=project_root,
         build_root=build_root,
         source_root=source_root,
         output_root=output_root,
      ),
      build=BuildConfig(
         port=_require_str(build_raw, "port", profile_path),
         time_driver=_require_str(build_raw, "time_driver", profile_path),
         config_header=config_header,
      ),
      features=FeaturesConfig(
         enable=tuple(_require_str_list(features_raw, "enable", profile_path)),
      ),
      output=OutputConfig(
         archive=_require_str(output_raw, "archive", profile_path),
      ),
   )


def find_profiles(root: Path | None = None) -> list[Path]:
   project_root = (root or Path.cwd()).resolve()
   candidates = [
      project_root / "build" / "profiles",
      project_root / "profiles",
   ]

   for profiles_dir in candidates:
      if profiles_dir.is_dir():
         return sorted(
            p for p in profiles_dir.iterdir()
            if p.is_file() and p.suffix == ".toml"
         )

   return []
