"""Golden tests over loader and validation diagnostics.

The loaders are deliberately strict and their messages are part of the
contract — a user's first encounter with a malformed manifest is the error
text. All cases are pinned into one golden mapping so the whole diagnostic
surface reviews as a single diff.

Broken inputs are built at test time by copying the fixture into tmp_path and
patching it, rather than committing broken manifests that a reader would have
to be told to ignore.
"""
from __future__ import annotations

import re
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import FIXTURE_ROOT, assert_golden

from cyros_builder.planner import plan_build
from cyros_builder.resolve import resolve_invocation


def _copy_fixture(tmp_path: Path) -> Path:
   root = tmp_path / "mini"
   shutil.copytree(FIXTURE_ROOT, root)
   return root


def _resolve(root: Path, profile: str = "full"):
   return resolve_invocation(Namespace(
      profile=str(root / "build" / "profiles" / f"{profile}.toml"),
      toolchain=None, config=None, output=None,
   ))


def _capture(root: Path, fn) -> str:
   """Run fn, return its exception message with volatile paths normalised."""
   try:
      fn()
   except Exception as exc:
      text = f"{type(exc).__name__}: {exc}"
   else:
      raise AssertionError("expected an exception, none was raised")

   text = text.replace(str(root), "<FIXTURE>")
   # tmp_path leaks in a couple of FileNotFoundError reprs.
   text = re.sub(r"/tmp/[^\s'\"]*", "<TMP>", text)
   return text


def _patch(path: Path, old: str, new: str) -> None:
   text = path.read_text()
   assert old in text, f"{path}: pattern not present: {old!r}"
   path.write_text(text.replace(old, new, 1))


# Each case: name -> callable(root) that triggers the diagnostic.
def _unknown_port(root):
   _patch(root / "build/profiles/full.toml", 'port = "porta"', 'port = "nope"')
   return lambda: plan_build(_resolve(root))


def _port_not_in_variants(root):
   _patch(root / "src/port/component.toml",
          'variants = ["porta", "portb"]', 'variants = ["portb"]')
   return lambda: plan_build(_resolve(root))


def _unknown_time_driver(root):
   _patch(root / "build/profiles/full.toml", 'time_driver = "tick"', 'time_driver = "nope"')
   return lambda: plan_build(_resolve(root))


def _time_driver_not_in_variants(root):
   _patch(root / "src/time/component.toml", 'variants = ["tick"]', 'variants = ["other"]')
   return lambda: plan_build(_resolve(root))


def _unknown_feature(root):
   _patch(root / "build/profiles/full.toml",
          'enable = ["alpha", "beta", "timed"]', 'enable = ["alpha", "ghost"]')
   return lambda: plan_build(_resolve(root))


def _feature_needs_time_but_none_selected(root):
   # 'timed' depends on "time"; no_time.toml selects no driver.
   _patch(root / "build/profiles/no_time.toml", 'enable = ["alpha"]', 'enable = ["timed"]')
   return lambda: plan_build(_resolve(root, "no_time"))


def _feature_depends_on_disabled_feature(root):
   # 'beta' depends on 'alpha'; enable beta alone.
   _patch(root / "build/profiles/full.toml",
          'enable = ["alpha", "beta", "timed"]', 'enable = ["beta"]')
   return lambda: plan_build(_resolve(root))


def _sources_overlap_excluded(root):
   _patch(root / "src/kernel/component.toml",
          'sources_excluded_from_archive = [\n   "validate.cpp",\n]',
          'sources_excluded_from_archive = [\n   "kernel.cpp",\n]')
   return lambda: plan_build(_resolve(root))


def _malformed_public_header(root):
   _patch(root / "src/kernel/component.toml",
          '"include/mini/kernel.hpp -> mini/kernel.hpp"',
          '"include/mini/kernel.hpp"')
   return lambda: plan_build(_resolve(root))


def _toolchain_unknown_top_level_key(root):
   _patch(root / "build/toolchains/base.toml", 'name = "mini-base"',
          'name = "mini-base"\nmystery = 1')
   return lambda: plan_build(_resolve(root))


def _toolchain_unknown_flag_key(root):
   _patch(root / "build/toolchains/base.toml", 'c      = ["-std=c17"]',
          'c      = ["-std=c17"]\ncxxx   = ["-oops"]')
   return lambda: plan_build(_resolve(root))


def _toolchain_unknown_archive_strategy(root):
   _patch(root / "build/toolchains/base.toml", 'strategy = "simple"', 'strategy = "zip"')
   return lambda: plan_build(_resolve(root))


def _toolchain_extends_missing(root):
   _patch(root / "build/toolchains/child.toml",
          'extends = "base.toml"', 'extends = "ghost.toml"')
   return lambda: plan_build(_resolve(root))


def _toolchain_extends_cycle(root):
   _patch(root / "build/toolchains/base.toml", 'name = "mini-base"',
          'name = "mini-base"\nextends = "child.toml"')
   return lambda: plan_build(_resolve(root))


def _profile_missing_table(root):
   p = root / "build/profiles/full.toml"
   text = p.read_text().replace('[output]\narchive = "libmini.a"\n', "")
   p.write_text(text)
   return lambda: plan_build(_resolve(root))


def _profile_source_root_missing(root):
   _patch(root / "build/profiles/full.toml",
          'source_root = "../../src"', 'source_root = "../../nowhere"')
   return lambda: plan_build(_resolve(root))


def _profile_no_toolchain(root):
   _patch(root / "build/profiles/full.toml",
          'toolchain = "../toolchains/child.toml"\n', "")
   return lambda: plan_build(_resolve(root))


def _profile_no_config_header(root):
   _patch(root / "build/profiles/full.toml",
          'config_header = "../configs/mini.hpp"\n', "")
   return lambda: plan_build(_resolve(root))


def _lto_filter_without_exports_file(root):
   _patch(root / "build/toolchains/lto.toml",
          'exported_symbols_file = "exports.txt"\n', "")
   return lambda: plan_build(_resolve(root, "lto"))


CASES = {
   "unknown_port": _unknown_port,
   "port_not_in_variants": _port_not_in_variants,
   "unknown_time_driver": _unknown_time_driver,
   "time_driver_not_in_variants": _time_driver_not_in_variants,
   "unknown_feature": _unknown_feature,
   "feature_needs_time_but_none_selected": _feature_needs_time_but_none_selected,
   "feature_depends_on_disabled_feature": _feature_depends_on_disabled_feature,
   "sources_overlap_excluded": _sources_overlap_excluded,
   "malformed_public_header": _malformed_public_header,
   "toolchain_unknown_top_level_key": _toolchain_unknown_top_level_key,
   "toolchain_unknown_flag_key": _toolchain_unknown_flag_key,
   "toolchain_unknown_archive_strategy": _toolchain_unknown_archive_strategy,
   "toolchain_extends_missing": _toolchain_extends_missing,
   "toolchain_extends_cycle": _toolchain_extends_cycle,
   "profile_missing_table": _profile_missing_table,
   "profile_source_root_missing": _profile_source_root_missing,
   "profile_no_toolchain": _profile_no_toolchain,
   "profile_no_config_header": _profile_no_config_header,
   "lto_filter_without_exports_file": _lto_filter_without_exports_file,
}


def test_diagnostics_match_golden(tmp_path):
   messages = {}
   for name, build_case in CASES.items():
      root = _copy_fixture(tmp_path / name)
      messages[name] = _capture(root, build_case(root))
   assert_golden("diagnostics", messages)


def test_merged_table_diagnostics_misattribute_the_declaring_file(tmp_path):
   """KNOWN DEFECT, pinned so it stays visible.

   `_validate_top_level_keys` runs inside `_load_and_merge`, once per file, so
   it names the file that actually declared the bad key. The four table
   validators (`tools`, `flags`, `settings`, `archive`) instead run in
   `_build_toolchain` against the *merged* dict carrying the *leaf* path, so a
   bad key inherited from a parent is reported against the child.

   Here the bad key is planted in base.toml and blamed on child.toml. When this
   is fixed, this test will fail — replace it with the correct expectation and
   regenerate the diagnostics golden.
   """
   root = _copy_fixture(tmp_path / "misattribution")
   _patch(root / "build/toolchains/base.toml",
          'c      = ["-std=c17"]', 'c      = ["-std=c17"]\ncxxx   = ["-oops"]')

   message = _capture(root, lambda: plan_build(_resolve(root)))

   assert "unknown keys in [flags]: cxxx" in message
   assert message.endswith("unknown keys in [flags]: cxxx")
   assert "child.toml" in message, "current behaviour: blamed on the leaf"
   assert "base.toml" not in message, "the file that declared it is not named"


def test_top_level_key_diagnostics_name_the_right_file(tmp_path):
   """The contrast case: top-level validation attributes correctly."""
   root = _copy_fixture(tmp_path / "attribution_ok")
   _patch(root / "build/toolchains/base.toml",
          'name = "mini-base"', 'name = "mini-base"\nmystery = 1')

   message = _capture(root, lambda: plan_build(_resolve(root)))
   assert "base.toml" in message
   assert "child.toml" not in message


@pytest.mark.parametrize("name", sorted(CASES))
def test_each_case_actually_raises(tmp_path, name):
   """Guards the golden: a case that stopped raising would otherwise just
   record a new message and look like an intentional change."""
   root = _copy_fixture(tmp_path / name)
   with pytest.raises(Exception):
      CASES[name](root)()
