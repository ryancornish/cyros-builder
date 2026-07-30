"""Shared TOML loading/validation accessors.

profile.py, toolchain.py, project_model.py, and test_model.py each declared
their own is-a-string / is-a-list / is-a-bool checks. This module is the one
place those live now.

Several loaders wanted an "optional string" with genuinely different
semantics (does an empty string count as absent? does absence return None or
a caller-supplied default?), and the exact wording of these messages is
pinned by tests/test_errors_golden.py. Rather than force one behaviour, the
three shapes are kept as distinctly named functions so each caller's prior
behaviour and message text carry over unchanged.
"""

from pathlib import Path
import tomllib


def load_toml(path: Path, *, must_exist: bool = False) -> dict:
   if must_exist and not path.is_file():
      raise FileNotFoundError(path)
   with path.open("rb") as f:
      raw = tomllib.load(f)
   if not isinstance(raw, dict):
      raise ValueError(f"{path}: root TOML document must be a table")
   return raw


def expect_table(data: dict, key: str, path: Path) -> dict:
   value = data.get(key)
   if not isinstance(value, dict):
      raise ValueError(f"{path}: expected [{key}] table")
   return value


def require_str(data: dict, key: str, path: Path) -> str:
   value = data.get(key)
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string")
   return value


def require_bool(data: dict, key: str, path: Path) -> bool:
   value = data.get(key)
   if not isinstance(value, bool):
      raise ValueError(f"{path}: expected '{key}' to be a bool")
   return value


def require_str_list(data: dict, key: str, path: Path) -> list[str]:
   value = data.get(key)
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")
   return value


def optional_bool(data: dict, key: str, path: Path, default: bool = False) -> bool:
   value = data.get(key)
   if value is None:
      return default
   if not isinstance(value, bool):
      raise ValueError(f"{path}: expected '{key}' to be a bool")
   return value


def optional_str_list(data: dict, key: str, path: Path, default: list[str] | None = None) -> list[str]:
   value = data.get(key)
   if value is None:
      return [] if default is None else list(default)
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")
   return list(value)


def optional_str_or_str_list(data: dict, key: str, path: Path) -> list[str]:
   """Accept either a single string or a list of strings; return a list."""
   value = data.get(key)
   if value is None:
      return []
   if isinstance(value, str):
      return [value] if value else []
   if isinstance(value, list) and all(isinstance(x, str) for x in value):
      return list(value)
   raise ValueError(f"{path}: expected '{key}' to be a string or list of strings")


def optional_str_default(data: dict, key: str, path: Path, default: str = "") -> str:
   """None -> default. Empty string is a valid, distinct value."""
   value = data.get(key)
   if value is None:
      return default
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string")
   return value


def optional_str_or_none(data: dict, key: str, path: Path) -> str | None:
   """None -> None. Empty string is a valid, distinct value."""
   value = data.get(key)
   if value is None:
      return None
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string if present")
   return value


def optional_nonempty_str(data: dict, key: str, path: Path) -> str | None:
   """None or "" -> None. Used where an empty string means "not set"."""
   value = data.get(key)
   if value is None or value == "":
      return None
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a non-empty string if present")
   return value


def require_existing_file(path: Path, desc: str, source_path: Path) -> Path:
   if not path.is_file():
      raise ValueError(f"{source_path}: resolved {desc} does not exist or is not a file: {path}")
   return path


def require_existing_dir(path: Path, desc: str, source_path: Path) -> Path:
   if not path.is_dir():
      raise ValueError(f"{source_path}: resolved {desc} does not exist or is not a directory: {path}")
   return path
