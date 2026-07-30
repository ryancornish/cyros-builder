from dataclasses import dataclass
from pathlib import Path

from cyros_builder import tomlutil


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
   raw = tomlutil.load_toml(profile_path)

   profile_raw    = tomlutil.expect_table(raw, "profile",    profile_path)
   layout_raw     = tomlutil.expect_table(raw, "layout",     profile_path)
   components_raw = tomlutil.expect_table(raw, "components", profile_path)
   features_raw   = tomlutil.expect_table(raw, "features",   profile_path)
   output_raw     = tomlutil.expect_table(raw, "output",     profile_path)

   # All paths are resolved relative to the profile file's own directory.
   base = profile_path.parent

   toolchain_str = tomlutil.optional_nonempty_str(profile_raw, "toolchain", profile_path)
   toolchain_path: Path | None = None
   if toolchain_str is not None:
      toolchain_path = tomlutil.require_existing_file(
         (base / toolchain_str).resolve(),
         "profile.toolchain",
         profile_path,
      )

   config_header_str = tomlutil.optional_nonempty_str(profile_raw, "config_header", profile_path)
   config_header_path: Path | None = None
   if config_header_str is not None:
      config_header_path = tomlutil.require_existing_file(
         (base / config_header_str).resolve(),
         "profile.config_header",
         profile_path,
      )

   source_root = tomlutil.require_existing_dir(
      (base / tomlutil.require_str(layout_raw, "source_root", profile_path)).resolve(),
      "layout.source_root",
      profile_path,
   )
   output_root = (base / tomlutil.require_str(layout_raw, "output_root", profile_path)).resolve()

   return Profile(
      path=profile_path,
      name=tomlutil.require_str(profile_raw, "name", profile_path),
      toolchain=toolchain_path,
      config_header=config_header_path,
      layout=LayoutConfig(
         source_root=source_root,
         output_root=output_root,
      ),
      components=ComponentsConfig(
         port=tomlutil.require_str(components_raw, "port", profile_path),
         time_driver=tomlutil.optional_nonempty_str(components_raw, "time_driver", profile_path),
      ),
      features=FeaturesConfig(
         enable=tuple(tomlutil.require_str_list(features_raw, "enable", profile_path)),
      ),
      output=OutputConfig(
         archive=tomlutil.require_str(output_raw, "archive", profile_path),
      ),
   )