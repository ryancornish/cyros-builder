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
   # Only used by the lto_merged archive strategy. Configurable because a cross
   # toolchain needs its own binutils (arm-none-eabi-objcopy for the STM32 port);
   # it was hardcoded to "objcopy", which silently pinned the pipeline to the host.
   objcopy: str | None = None


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
   # Does this toolchain target an environment with an OS and a full hosted
   # runtime? True for every host toolchain, and the DEFAULT, so that adding
   # the key changed nothing for the toolchains that already existed.
   #
   # It is what lets a bare-metal profile run the whole suite without drowning
   # in failures. The 28 host unit tests link gtest and assume a hosted main,
   # and none of that exists on a Cortex-M33. Expressing that as a port filter
   # would mean naming every Linux port in every one of those files, and
   # naming them again whenever a port is added. The real predicate is not
   # which port, it is whether there is an OS underneath.
   hosted: bool = True


@dataclass(frozen=True)
class ArchiveSettings:
   strategy: str
   localize_hidden: bool
   preserve_lto_sections: bool


@dataclass(frozen=True)
class RunnerSettings:
   """
   How to EXECUTE a binary this toolchain produced.

   A host toolchain has no runner: the binary is a host executable and the
   runner just execs it. A cross toolchain's output cannot run on the build
   machine at all, so the toolchain has to say what does run it - for the
   Cortex-M port, QEMU. It belongs to the toolchain rather than the profile
   because it is decided by the target triple, and every profile sharing a
   toolchain shares the answer.

   `command` is the argv to run. The binary is substituted for the
   "{binary}" placeholder, or appended when no element contains one, since
   an emulator usually wants it in a specific position (`-kernel <path>`)
   while a plain wrapper wants it last.
   """
   command: tuple[str, ...]
   timeout: float | None


@dataclass(frozen=True)
class Toolchain:
   path: Path
   name: str
   extends: Path | None   # resolved absolute path to parent .toml, or None
   tools: ToolPaths
   flags: ToolchainFlags
   settings: ToolchainSettings
   archive: ArchiveSettings
   runner: RunnerSettings | None = None

   def run_command(self, binary: Path) -> list[str]:
      """
      The argv that executes `binary`. Without a runner this is the binary
      itself, which is what every host toolchain wants.
      """
      if self.runner is None:
         return [str(binary)]
      if any("{binary}" in arg for arg in self.runner.command):
         return [arg.replace("{binary}", str(binary)) for arg in self.runner.command]
      return [*self.runner.command, str(binary)]


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

   runner_raw = data.get("runner", {})
   runner = None
   if runner_raw:
      timeout_raw = runner_raw.get("timeout")
      runner = RunnerSettings(
         command=tuple(tomlutil.require_str_list(runner_raw, "command", path)),
         timeout=float(timeout_raw) if timeout_raw is not None else None,
      )

   return Toolchain(
      path=path,
      name=tomlutil.require_str(data, "name", path),
      extends=extends_path,
      tools=ToolPaths(
         cc=tomlutil.require_str(tools, "cc", path),
         cxx=tomlutil.require_str(tools, "cxx", path),
         ar=tomlutil.require_str(tools, "ar", path),
         asm=tomlutil.optional_str_or_none(tools, "asm", path),
         objcopy=tomlutil.optional_str_or_none(tools, "objcopy", path),
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
         hosted=tomlutil.optional_bool(settings, "hosted", path, default=True),
      ),
      archive=ArchiveSettings(
         strategy=strategy,
         localize_hidden=tomlutil.optional_bool(archive, "localize_hidden", path, default=False),
         preserve_lto_sections=tomlutil.optional_bool(archive, "preserve_lto_sections", path, default=False),
      ),
      runner=runner,
   )


# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------

_ALLOWED_TOP_LEVEL_KEYS = {"name", "extends", "tools", "flags", "settings", "archive", "runner"}
_ALLOWED_TOOL_KEYS      = {"cc", "cxx", "ar", "asm", "objcopy"}
_ALLOWED_RUNNER_KEYS    = {"command", "timeout"}
_ALLOWED_FLAG_KEYS = {
   "common", "common_add", "common_remove",
   "c",      "c_add",      "c_remove",
   "cxx",    "cxx_add",    "cxx_remove",
   "asm",    "asm_add",    "asm_remove",
   "link",   "link_add",   "link_remove",
}
_ALLOWED_SETTINGS_KEYS = {"family", "debug", "optimization", "warnings_as_errors", "hosted"}
_ALLOWED_ARCHIVE_KEYS  = {
   "strategy", "localize_hidden", "preserve_lto_sections",
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
      ("runner", _validate_runner_table),
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


def _validate_runner_table(data: dict, path: Path) -> None:
   unknown = set(data) - _ALLOWED_RUNNER_KEYS
   if unknown:
      raise ValueError(f"{path}: unknown keys in [runner]: {', '.join(sorted(unknown))}")

   _ensure_str_list(data.get("command", []), "[runner].command", path)
   if not data.get("command"):
      raise ValueError(
         f"{path}: [runner].command must be a non-empty list of strings. "
         f"A declared but empty runner would silently exec a cross-built binary "
         f"on the host, which fails as 'Exec format error' far from its cause."
      )

   timeout = data.get("timeout")
   if timeout is not None and not isinstance(timeout, (int, float)):
      raise ValueError(f"{path}: expected [runner].timeout to be a number of seconds")
   if isinstance(timeout, (int, float)) and timeout <= 0:
      raise ValueError(f"{path}: [runner].timeout must be > 0")


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

   # These two cannot both hold, and the failure would otherwise be silent.
   # preserve_lto_sections selects -flinker-output=rel, which keeps the GIMPLE IR
   # in the object. Verified empirically: objcopy --localize-hidden then finds
   # nothing marked hidden (the visibility lives in the IR, not the ELF symtab),
   # the symbol stays global, and a consumer referencing an "internal" symbol
   # links fine. Hiding requires nolto-rel, where localization is authoritative.
   if data.get("localize_hidden") and data.get("preserve_lto_sections"):
      raise ValueError(
         f"{path}: [archive].localize_hidden and [archive].preserve_lto_sections "
         f"cannot both be true. Retaining LTO sections leaves symbol resolution to "
         f"the LTO plugin, which ignores the ELF symbol table objcopy edits, so the "
         f"hiding would silently do nothing. FIX: set preserve_lto_sections = false "
         f"to hide internals, or localize_hidden = false to keep LTO sections."
      )


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