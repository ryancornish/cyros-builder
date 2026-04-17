from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class BuildConfig:
   port: str
   time_driver: str
   config: Path


@dataclass(frozen=True)
class LibcortosConfig:
   enable: tuple[str, ...]


@dataclass(frozen=True)
class OutputConfig:
   root: Path
   archive: str


@dataclass(frozen=True)
class Profile:
   path: Path
   name: str
   default_toolchain: str | None
   build: BuildConfig
   libcortos: LibcortosConfig
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


def _resolve_profile_path(profile_path: Path, value: str) -> Path:
   return (profile_path.parent / value).resolve()


def load_profile(path: Path) -> Profile:
   profile_path = path.resolve()

   with profile_path.open("rb") as f:
      raw = tomllib.load(f)

   if not isinstance(raw, dict):
      raise ValueError(f"{profile_path}: root TOML document must be a table")

   build_raw = _expect_table(raw, "build", profile_path)
   libcortos_raw = _expect_table(raw, "libcortos", profile_path)
   output_raw = _expect_table(raw, "output", profile_path)

   return Profile(
      path=profile_path,
      name=_require_str(raw, "name", profile_path),
      default_toolchain=_optional_str(raw, "default_toolchain", profile_path),
      build=BuildConfig(
         port=_require_str(build_raw, "port", profile_path),
         time_driver=_require_str(build_raw, "time_driver", profile_path),
         config=_resolve_profile_path(profile_path, _require_str(build_raw, "config", profile_path)),
      ),
      libcortos=LibcortosConfig(
         enable=tuple(_require_str_list(libcortos_raw, "enable", profile_path)),
      ),
      output=OutputConfig(
         root=_resolve_profile_path(profile_path, _require_str(output_raw, "root", profile_path)),
         archive=_require_str(output_raw, "archive", profile_path),
      ),
   )

def find_profiles(root: Path | None = None) -> list[Path]:
   project_root = (root or Path.cwd()).resolve()
   profiles_dir = project_root / "profiles"

   if not profiles_dir.is_dir():
      return []

   return sorted(
      p for p in profiles_dir.iterdir()
      if p.is_file() and p.suffix == ".toml"
   )