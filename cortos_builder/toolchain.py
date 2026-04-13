from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path
from cortos_builder.project import toolchains_dir


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
   use_modules: bool


@dataclass(frozen=True)
class Toolchain:
   path: Path
   name: str
   extends: str | None
   tools: ToolPaths
   flags: ToolchainFlags
   settings: ToolchainSettings


# -----------------------------------------------------------------------------
# Raw parsed model
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class RawToolchain:
   path: Path
   name: str
   extends: str | None
   data: dict


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def find_toolchain_paths(root: Path | None = None) -> list[Path]:
   directory = toolchains_dir(root)
   if not directory.is_dir():
      return []
   return sorted(
      p for p in directory.iterdir()
      if p.is_file() and p.suffix == ".toml"
   )


def list_toolchain_names(root: Path | None = None) -> list[str]:
   names: list[str] = []
   for path in find_toolchain_paths(root):
      raw = load_raw_toolchain(path)
      names.append(raw.name)
   return sorted(names)


def resolve_toolchain(name: str, root: Path | None = None) -> Toolchain:
   index = _build_toolchain_index(root)
   merged = _resolve_toolchain_dict(name, index, stack=[])
   return _validate_and_build_toolchain(index[name].path, merged)


# -----------------------------------------------------------------------------
# Loading raw TOML
# -----------------------------------------------------------------------------

def load_raw_toolchain(path: Path) -> RawToolchain:
   toolchain_path = path.resolve()

   with toolchain_path.open("rb") as f:
      raw = tomllib.load(f)

   if not isinstance(raw, dict):
      raise ValueError(f"{toolchain_path}: root TOML document must be a table")

   _validate_top_level_keys(raw, toolchain_path)

   name = _require_str(raw, "name", toolchain_path)
   extends = _optional_str(raw, "extends", toolchain_path)

   return RawToolchain(
      path=toolchain_path,
      name=name,
      extends=extends,
      data=raw,
   )


def _build_toolchain_index(root: Path | None = None) -> dict[str, RawToolchain]:
   index: dict[str, RawToolchain] = {}

   for path in find_toolchain_paths(root):
      raw = load_raw_toolchain(path)
      if raw.name in index:
         raise ValueError(
               f"Duplicate toolchain name '{raw.name}' in:\n"
               f"  {index[raw.name].path}\n"
               f"  {raw.path}"
         )
      index[raw.name] = raw

   return index


# -----------------------------------------------------------------------------
# Inheritance resolution
# -----------------------------------------------------------------------------

def _resolve_toolchain_dict(
   name: str,
   index: dict[str, RawToolchain],
   stack: list[str],
) -> dict:
   if name not in index:
      known = ", ".join(sorted(index))
      raise ValueError(f"Unknown toolchain '{name}'. Known toolchains: {known}")

   if name in stack:
      cycle = " -> ".join([*stack, name])
      raise ValueError(f"Toolchain inheritance cycle detected: {cycle}")

   raw = index[name]
   parent_name = raw.extends

   if parent_name is None:
      return _deep_copy_dict(raw.data)

   parent = _resolve_toolchain_dict(parent_name, index, [*stack, name])
   child = _deep_copy_dict(raw.data)

   merged = _merge_toolchain_dicts(parent, child, raw.path)
   return merged


def _merge_toolchain_dicts(parent: dict, child: dict, path: Path) -> dict:
   result = _deep_copy_dict(parent)

   for key, child_value in child.items():
      if key not in result:
         result[key] = _deep_copy_value(child_value)
         continue

      parent_value = result[key]

      if isinstance(parent_value, dict) and isinstance(child_value, dict):
         result[key] = _merge_toolchain_tables(parent_value, child_value, path, table_name=key)
      else:
         # Scalar or list: full override.
         result[key] = _deep_copy_value(child_value)

   return result


def _merge_toolchain_tables(parent: dict, child: dict, path: Path, table_name: str) -> dict:
   result = _deep_copy_dict(parent)

   for key, child_value in child.items():
      if key not in result:
         result[key] = _deep_copy_value(child_value)
         continue

      parent_value = result[key]

      if isinstance(parent_value, dict) and isinstance(child_value, dict):
         result[key] = _merge_toolchain_tables(parent_value, child_value, path, table_name)
      else:
         # Lists and scalars override completely here.
         result[key] = _deep_copy_value(child_value)

   # Apply explicit add/remove semantics for [flags].
   if table_name == "flags":
      _apply_flag_add_remove(result, path)

   return result


def _apply_flag_add_remove(flags: dict, path: Path) -> None:
   bases = ["common", "c", "cxx", "asm", "link"]

   for base in bases:
      base_value = flags.get(base, [])
      add_value = flags.get(f"{base}_add", [])
      remove_value = flags.get(f"{base}_remove", [])

      _ensure_str_list(base_value, f"[flags].{base}", path)
      _ensure_str_list(add_value, f"[flags].{base}_add", path)
      _ensure_str_list(remove_value, f"[flags].{base}_remove", path)

      result = list(base_value)

      if remove_value:
         remove_set = set(remove_value)
         result = [x for x in result if x not in remove_set]

      if add_value:
         result.extend(add_value)

      flags[base] = result

   # The resolved dict should no longer expose these operational keys.
   for base in bases:
      flags.pop(f"{base}_add", None)
      flags.pop(f"{base}_remove", None)


# -----------------------------------------------------------------------------
# Validation + final conversion
# -----------------------------------------------------------------------------

def _validate_and_build_toolchain(path: Path, data: dict) -> Toolchain:
   _validate_top_level_keys(data, path)

   tools = data.get("tools", {})
   flags = data.get("flags", {})
   settings = data.get("settings", {})

   if not isinstance(tools, dict):
      raise ValueError(f"{path}: expected [tools] table")
   if not isinstance(flags, dict):
      raise ValueError(f"{path}: expected [flags] table")
   if not isinstance(settings, dict):
      raise ValueError(f"{path}: expected [settings] table")

   _validate_tools_table(tools, path)
   _validate_flags_table(flags, path)
   _validate_settings_table(settings, path)

   return Toolchain(
      path=path,
      name=_require_str(data, "name", path),
      extends=_optional_str(data, "extends", path),
      tools=ToolPaths(
         cc=_require_str(tools, "cc", path),
         cxx=_require_str(tools, "cxx", path),
         ar=_require_str(tools, "ar", path),
         asm=_optional_str(tools, "asm", path),
      ),
      flags=ToolchainFlags(
         common=tuple(_require_str_list(flags, "common", path)),
         c=tuple(_require_str_list(flags, "c", path)),
         cxx=tuple(_require_str_list(flags, "cxx", path)),
         asm=tuple(_require_str_list(flags, "asm", path)),
         link=tuple(_require_str_list(flags, "link", path)),
      ),
      settings=ToolchainSettings(
         family=_require_str(settings, "family", path),
         debug=_require_bool(settings, "debug", path),
         optimization=_require_str(settings, "optimization", path),
         warnings_as_errors=_require_bool(settings, "warnings_as_errors", path),
         use_modules=_require_bool(settings, "use_modules", path),
      ),
   )


# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------

_ALLOWED_TOP_LEVEL_KEYS = {"name", "extends", "tools", "flags", "settings"}
_ALLOWED_TOOL_KEYS = {"cc", "cxx", "ar", "asm"}
_ALLOWED_FLAG_KEYS = {
   "common", "common_add", "common_remove",
   "c", "c_add", "c_remove",
   "cxx", "cxx_add", "cxx_remove",
   "asm", "asm_add", "asm_remove",
   "link", "link_add", "link_remove",
}
_ALLOWED_SETTINGS_KEYS = {
   "family",
   "debug",
   "optimization",
   "warnings_as_errors",
   "use_modules",
}


def _validate_top_level_keys(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_TOP_LEVEL_KEYS
   if unknown:
      names = ", ".join(sorted(unknown))
      raise ValueError(f"{path}: unknown top-level keys: {names}")


def _validate_tools_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_TOOL_KEYS
   if unknown:
      names = ", ".join(sorted(unknown))
      raise ValueError(f"{path}: unknown keys in [tools]: {names}")


def _validate_flags_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_FLAG_KEYS
   if unknown:
      names = ", ".join(sorted(unknown))
      raise ValueError(f"{path}: unknown keys in [flags]: {names}")


def _validate_settings_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_SETTINGS_KEYS
   if unknown:
      names = ", ".join(sorted(unknown))
      raise ValueError(f"{path}: unknown keys in [settings]: {names}")


def _require_str(data: dict, key: str, path: Path) -> str:
   value = data.get(key)
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string")
   return value


def _optional_str(data: dict, key: str, path: Path) -> str | None:
   value = data.get(key)
   if value is None:
      return None
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string if present")
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