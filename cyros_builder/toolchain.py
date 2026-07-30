from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from cyros_builder import tomlutil


# -----------------------------------------------------------------------------
# Final resolved model
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolPaths:
   cc: str
   cxx: str
   ar: str
   asm: str | None = None


@dataclass(frozen=True)
class ToolchainFlags:
   common: tuple[str, ...]
   c: tuple[str, ...]
   cxx: tuple[str, ...]
   asm: tuple[str, ...]
   link: tuple[str, ...]


@dataclass(frozen=True)
class ToolchainSettings:
   family: str
   debug: bool
   optimization: str
   warnings_as_errors: bool


@dataclass(frozen=True)
class ArchiveSettings:
   strategy: str
   exported_symbols_file: str | None
   filter_exported_symbols: bool
   preserve_lto_sections: bool


@dataclass(frozen=True)
class Toolchain:
   path: Path
   name: str
   extends: Path | None   # resolved absolute path to parent .toml, or None
   tools: ToolPaths
   flags: ToolchainFlags
   settings: ToolchainSettings
   archive: ArchiveSettings


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def resolve_toolchain(toolchain_path: Path) -> Toolchain:
   """
   Resolve a toolchain from a path to a .toml file.
   Inheritance is resolved by following `extends` as a path relative to the
   child toolchain file — no directory scanning or name-based lookup.
   """
   toolchain_path = toolchain_path.resolve()
   if not toolchain_path.is_file():
      raise FileNotFoundError(f"Toolchain file not found: {toolchain_path}")

   merged, extends_path = _load_and_merge(toolchain_path, stack=[])
   return _build_toolchain(toolchain_path, merged, extends_path)


# -----------------------------------------------------------------------------
# Loading and inheritance
# -----------------------------------------------------------------------------

def _load_and_merge(path: Path, stack: list[Path]) -> tuple[dict, Path | None]:
   """
   Recursively load a toolchain file and merge it with its parent.
   Returns (merged_data, direct_parent_path | None).
   """
   if path in stack:
      cycle = " -> ".join(str(p) for p in [*stack, path])
      raise ValueError(f"Toolchain inheritance cycle detected: {cycle}")

   raw = tomlutil.load_toml(path)
   _validate_top_level_keys(raw, path)
   _validate_declared_tables(raw, path)

   extends_str = tomlutil.optional_str_or_none(raw, "extends", path)
   if extends_str is None:
      return _deep_copy_dict(raw), None

   extends_path = (path.parent / extends_str).resolve()
   if not extends_path.is_file():
      raise FileNotFoundError(
         f"{path}: extends target not found: {extends_path}\n"
         f"  (resolved from extends = {extends_str!r})"
      )

   parent_data, _ = _load_and_merge(extends_path, [*stack, path])
   child_data = _deep_copy_dict(raw)
   merged = _merge_dicts(parent_data, child_data, path)
   return merged, extends_path


def _merge_dicts(parent: dict, child: dict, path: Path) -> dict:
   result = _deep_copy_dict(parent)

   for key, child_value in child.items():
      if key not in result:
         result[key] = _deep_copy_value(child_value)
         continue

      parent_value = result[key]
      if isinstance(parent_value, dict) and isinstance(child_value, dict):
         result[key] = _merge_table(parent_value, child_value, path, table_name=key)
      else:
         result[key] = _deep_copy_value(child_value)

   return result


def _merge_table(parent: dict, child: dict, path: Path, table_name: str) -> dict:
   result = _deep_copy_dict(parent)

   for key, child_value in child.items():
      if key not in result:
         result[key] = _deep_copy_value(child_value)
         continue

      parent_value = result[key]
      if isinstance(parent_value, dict) and isinstance(child_value, dict):
         result[key] = _merge_table(parent_value, child_value, path, table_name)
      else:
         result[key] = _deep_copy_value(child_value)

   if table_name == "flags":
      _apply_flag_add_remove(result, path)

   return result


def _apply_flag_add_remove(flags: dict, path: Path) -> None:
   bases = ["common", "c", "cxx", "asm", "link"]

   for base in bases:
      base_value   = flags.get(base, [])
      add_value    = flags.get(f"{base}_add", [])
      remove_value = flags.get(f"{base}_remove", [])

      _ensure_str_list(base_value,   f"[flags].{base}",        path)
      _ensure_str_list(add_value,    f"[flags].{base}_add",    path)
      _ensure_str_list(remove_value, f"[flags].{base}_remove", path)

      result = list(base_value)
      if remove_value:
         remove_set = set(remove_value)
         result = [x for x in result if x not in remove_set]
      if add_value:
         result.extend(add_value)

      flags[base] = result

   for base in bases:
      flags.pop(f"{base}_add", None)
      flags.pop(f"{base}_remove", None)


# -----------------------------------------------------------------------------
# Validation + final model construction
# -----------------------------------------------------------------------------

def _build_toolchain(path: Path, data: dict, extends_path: Path | None) -> Toolchain:
   # Each contributing file's [tools]/[flags]/[settings]/[archive] tables were
   # already validated, against that file's own path, in _load_and_merge via
   # _validate_declared_tables. The merged dict here carries only keys that
   # passed validation somewhere in the extends chain, so there is nothing
   # left to check against this (possibly unrelated) leaf path.
   tools    = data.get("tools", {})
   flags    = data.get("flags", {})
   settings = data.get("settings", {})
   archive  = data.get("archive", {})

   strategy = tomlutil.optional_str_or_none(archive, "strategy", path) or "simple"

   return Toolchain(
      path=path,
      name=tomlutil.require_str(data, "name", path),
      extends=extends_path,
      tools=ToolPaths(
         cc=tomlutil.require_str(tools, "cc", path),
         cxx=tomlutil.require_str(tools, "cxx", path),
         ar=tomlutil.require_str(tools, "ar", path),
         asm=tomlutil.optional_str_or_none(tools, "asm", path),
      ),
      flags=ToolchainFlags(
         common=tuple(tomlutil.require_str_list(flags, "common", path)),
         c=tuple(tomlutil.require_str_list(flags, "c", path)),
         cxx=tuple(tomlutil.require_str_list(flags, "cxx", path)),
         asm=tuple(tomlutil.require_str_list(flags, "asm", path)),
         link=tuple(tomlutil.require_str_list(flags, "link", path)),
      ),
      settings=ToolchainSettings(
         family=tomlutil.require_str(settings, "family", path),
         debug=tomlutil.require_bool(settings, "debug", path),
         optimization=tomlutil.require_str(settings, "optimization", path),
         warnings_as_errors=tomlutil.require_bool(settings, "warnings_as_errors", path),
      ),
      archive=ArchiveSettings(
         strategy=strategy,
         exported_symbols_file=tomlutil.optional_str_or_none(archive, "exported_symbols_file", path),
         filter_exported_symbols=tomlutil.optional_bool(archive, "filter_exported_symbols", path, default=False),
         preserve_lto_sections=tomlutil.optional_bool(archive, "preserve_lto_sections", path, default=False),
      ),
   )


# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------

_ALLOWED_TOP_LEVEL_KEYS = {"name", "extends", "tools", "flags", "settings", "archive"}
_ALLOWED_TOOL_KEYS      = {"cc", "cxx", "ar", "asm"}
_ALLOWED_FLAG_KEYS = {
   "common", "common_add", "common_remove",
   "c",      "c_add",      "c_remove",
   "cxx",    "cxx_add",    "cxx_remove",
   "asm",    "asm_add",    "asm_remove",
   "link",   "link_add",   "link_remove",
}
_ALLOWED_SETTINGS_KEYS = {"family", "debug", "optimization", "warnings_as_errors"}
_ALLOWED_ARCHIVE_KEYS  = {
   "strategy", "exported_symbols_file",
   "filter_exported_symbols", "preserve_lto_sections",
}
_ALLOWED_ARCHIVE_STRATEGIES = {"simple", "lto_merged"}


def _validate_top_level_keys(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_TOP_LEVEL_KEYS
   if unknown:
      raise ValueError(f"{path}: unknown top-level keys: {', '.join(sorted(unknown))}")


def _validate_declared_tables(data: dict, path: Path) -> None:
   """
   Validate this file's own [tools]/[flags]/[settings]/[archive] tables against
   this file's own path, before inheritance merges them into anything else.
   Doing this per-file (rather than once on the merged result in
   _build_toolchain) is what lets a bad key be blamed on the file that
   actually declared it, even when that file is a parent in an extends chain.
   """
   for key, validator in (
      ("tools", _validate_tools_table),
      ("flags", _validate_flags_table),
      ("settings", _validate_settings_table),
      ("archive", _validate_archive_table),
   ):
      if key not in data:
         continue
      table = data[key]
      if not isinstance(table, dict):
         raise ValueError(f"{path}: expected [{key}] table")
      validator(table, path)


def _validate_tools_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_TOOL_KEYS
   if unknown:
      raise ValueError(f"{path}: unknown keys in [tools]: {', '.join(sorted(unknown))}")


def _validate_flags_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_FLAG_KEYS
   if unknown:
      raise ValueError(f"{path}: unknown keys in [flags]: {', '.join(sorted(unknown))}")


def _validate_settings_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_SETTINGS_KEYS
   if unknown:
      raise ValueError(f"{path}: unknown keys in [settings]: {', '.join(sorted(unknown))}")


def _validate_archive_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_ARCHIVE_KEYS
   if unknown:
      raise ValueError(f"{path}: unknown keys in [archive]: {', '.join(sorted(unknown))}")

   strategy = data.get("strategy")
   if strategy is not None:
      if not isinstance(strategy, str):
         raise ValueError(f"{path}: expected [archive].strategy to be a string")
      if strategy not in _ALLOWED_ARCHIVE_STRATEGIES:
         known = ", ".join(sorted(_ALLOWED_ARCHIVE_STRATEGIES))
         raise ValueError(f"{path}: unknown [archive].strategy '{strategy}'. Known: {known}")


# -----------------------------------------------------------------------------
# Type helpers local to flag merging
# -----------------------------------------------------------------------------

def _ensure_str_list(value: object, key: str, path: Path) -> None:
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")


# -----------------------------------------------------------------------------
# Deep-copy helpers
# -----------------------------------------------------------------------------

def _deep_copy_dict(data: dict) -> dict:
   return {k: _deep_copy_value(v) for k, v in data.items()}


def _deep_copy_value(value):
   if isinstance(value, dict):
      return _deep_copy_dict(value)
   if isinstance(value, list):
      return [_deep_copy_value(v) for v in value]
   return value