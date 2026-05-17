"""
test_model.py — schema and discovery for cortos unit tests.

Each test case is a directory under tests/unit/** that contains a test.toml.
The test.toml declares what is unique to that test: its source file, the
config header it needs, and any extra system libraries to link.

Everything else (toolchain, compiler flags, cortos archive) comes from the
resolved build invocation passed in by the test runner.

Layout convention (hardcoded — unit tests are internal to cortos):

   <source_root>/             e.g. cortos/src/
   <source_root>/../tests/unit/
      kernel/
         test_function/
            test.toml
            test_function.cpp
            test_function_config.hpp
         test_multicore_multithread/
            test.toml
            ...
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCase:
   """A single discovered and validated unit test."""
   path: Path          # directory containing test.toml
   name: str           # unique name, e.g. "test_function"
   source: Path        # resolved absolute path to the .cpp file
   config: Path        # resolved absolute path to the config header
   system_libraries: tuple[str, ...]   # e.g. ["boost_context", "gtest", "gtest_main"]
   extra_link_flags: tuple[str, ...]   # optional extra flags beyond the toolchain default


def find_unit_test_root(source_root: Path) -> Path:
   """
   Return the unit test root directory.
   Hardcoded as <source_root>/../tests/unit — unit tests are internal to cortos
   and are not part of the configurable build tree.
   """
   return (source_root / ".." / "tests" / "unit").resolve()


def discover_tests(source_root: Path) -> list[TestCase]:
   """
   Walk the unit test tree and return all valid test cases, sorted by name.
   Raises if any test.toml is malformed.
   """
   unit_root = find_unit_test_root(source_root)

   if not unit_root.is_dir():
      raise FileNotFoundError(
         f"Unit test root not found: {unit_root}\n"
         f"  (resolved from source_root: {source_root})"
      )

   cases: list[TestCase] = []
   for toml_path in sorted(unit_root.rglob("test.toml")):
      cases.append(load_test_case(toml_path))

   return cases


def load_test_case(path: Path) -> TestCase:
   """Load and validate a single test.toml."""
   toml_path = path.resolve()
   base = toml_path.parent

   with toml_path.open("rb") as f:
      raw = tomllib.load(f)

   if not isinstance(raw, dict):
      raise ValueError(f"{toml_path}: root TOML document must be a table")

   test_raw = _expect_table(raw, "test", toml_path)
   link_raw = raw.get("link", {})
   if not isinstance(link_raw, dict):
      raise ValueError(f"{toml_path}: expected [link] to be a table if present")

   name   = _require_str(test_raw, "name",   toml_path)
   source = _require_existing_file(
      (base / _require_str(test_raw, "source", toml_path)).resolve(),
      "test.source", toml_path,
   )
   config = _require_existing_file(
      (base / _require_str(test_raw, "config", toml_path)).resolve(),
      "test.config", toml_path,
   )

   system_libraries = tuple(_optional_str_list(link_raw, "system_libraries", toml_path))
   extra_link_flags = tuple(_optional_str_list(link_raw, "flags", toml_path))

   return TestCase(
      path=base,
      name=name,
      source=source,
      config=config,
      system_libraries=system_libraries,
      extra_link_flags=extra_link_flags,
   )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expect_table(data: dict, key: str, path: Path) -> dict:
   value = data.get(key)
   if not isinstance(value, dict):
      raise ValueError(f"{path}: expected [{key}] table")
   return value


def _require_str(data: dict, key: str, path: Path) -> str:
   value = data.get(key)
   if not isinstance(value, str):
      raise ValueError(f"{path}: expected '{key}' to be a string")
   return value


def _optional_str_list(data: dict, key: str, path: Path) -> list[str]:
   value = data.get(key)
   if value is None:
      return []
   if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
      raise ValueError(f"{path}: expected '{key}' to be a list of strings")
   return list(value)


def _require_existing_file(path: Path, desc: str, toml_path: Path) -> Path:
   if not path.is_file():
      raise ValueError(
         f"{toml_path}: resolved {desc} does not exist or is not a file: {path}"
      )
   return path