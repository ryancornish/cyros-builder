from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class LayoutConfig:
   source_root: Path
   output_root: Path


@dataclass(frozen=True)
class ComponentsConfig:
   port: str
   time_driver: str | None   # None means no time driver — omitted from the archive


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
   toolchain: Path | None    # resolved absolute path, or None if not set
   config_header: Path | None  # resolved absolute path, or None if not set
   layout: LayoutConfig
   components: ComponentsConfig
   features: FeaturesConfig
   output: OutputConfig


def load_profile(path: Path) -> Profile:
   profile_path = path.resolve()

   with profile_path.open("rb") as f:
      raw = tomllib.load(f)

   if not isinstance(raw, dict):
      raise ValueError(f"{profile_path}: root TOML document must be a table")

   profile_raw    = _expect_table(raw, "profile",    profile_path)
   layout_raw     = _expect_table(raw, "layout",     profile_path)
   components_raw = _expect_table(raw, "components", profile_path)
   features_raw   = _expect_table(raw, "features",   profile_path)
   output_raw     = _expect_table(raw, "output",     profile_path)

   # All paths are resolved relative to the profile file's own directory.
   base = profile_path.parent

   toolchain_str = _optional_str(profile_raw, "toolchain", profile_path)
   toolchain_path: Path | None = None
   if toolchain_str is not None:
      toolchain_path = _require_existing_file(
         (base / toolchain_str).resolve(),
         "profile.toolchain",
         profile_path,
      )

   config_header_str = _optional_str(profile_raw, "config_header", profile_path)
   config_header_path: Path | None = None
   if config_header_str is not None:
      config_header_path = _require_existing_file(
         (base / config_header_str).resolve(),
         "profile.config_header",
         profile_path,
      )

   source_root = _require_existing_dir(
      (base / _require_str(layout_raw, "source_root", profile_path)).resolve(),
      "layout.source_root",
      profile_path,
   )
   output_root = (base / _require_str(layout_raw, "output_root", profile_path)).resolve()

   return Profile(
      path=profile_path,
      name=_require_str(profile_raw, "name", profile_path),
      toolchain=toolchain_path,
      config_header=config_header_path,
      layout=LayoutConfig(
         source_root=source_root,
         output_root=output_root,
      ),
      components=ComponentsConfig(
         port=_require_str(components_raw, "port", profile_path),
         time_driver=_optional_str(components_raw, "time_driver", profile_path),
      ),
      features=FeaturesConfig(
         enable=tuple(_require_str_list(features_raw, "enable", profile_path)),
      ),
      output=OutputConfig(
         archive=_require_str(output_raw, "archive", profile_path),
      ),
   )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

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
   if value is None or value == "":
      return None
   if not isinstance(value, str):
      raise ValueError(f"{profile_path}: expected '{key}' to be a non-empty string if present")
   return value


def _require_str_list(data: dict, key: str, profile_path: Path) -> list[str]:
   value = data.get(key)
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{profile_path}: expected '{key}' to be a list of strings")
   return value


def _require_existing_dir(path: Path, desc: str, profile_path: Path) -> Path:
   if not path.is_dir():
      raise ValueError(
         f"{profile_path}: resolved {desc} does not exist or is not a directory: {path}"
      )
   return path


def _require_existing_file(path: Path, desc: str, profile_path: Path) -> Path:
   if not path.is_file():
      raise ValueError(
         f"{profile_path}: resolved {desc} does not exist or is not a file: {path}"
      )
   return path