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
          'variants = ["porta", "portb", "portc"]', 'variants = ["portb"]')
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


def _missing_internal_include_root(root):
   # A typo'd root would otherwise fail much later, as a missing header in every
   # source that includes through it.
   _patch(root / "src/port/component.toml", '"internal_headers",', '"nowhere",')
   return lambda: plan_build(_resolve(root))


def _public_header_includes_internal(root):
   # Compiles inside the project, breaks every consumer: caught at load instead.
   header = root / "src/port/include/mini/port.hpp"
   header.write_text(header.read_text() + "#include <mini/port_internal.hpp>\n")
   return lambda: plan_build(_resolve(root))


def _public_header_includes_internal_quoted(root):
   # The quote form with a path. It resolves under the internal root exactly as
   # the angle form does, so it leaks exactly the same way.
   header = root / "src/port/include/mini/port.hpp"
   header.write_text(header.read_text() + '#include "mini/port_internal.hpp"\n')
   return lambda: plan_build(_resolve(root))


def _feature_source_includes_internal(root):
   # Userlib builds on the PUBLIC API alone (roadmap A1). A feature source
   # reaching an internal header compiles fine inside the project and leaves no
   # trace in the exported tree, so nothing downstream would ever notice.
   source = root / "src/userlib/alpha/alpha.cpp"
   source.write_text(source.read_text() + "#include <mini/port_internal.hpp>\n")
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


def _localize_hidden_with_preserved_lto(root):
   # The combination that used to produce a silent no-op: retaining LTO sections
   # leaves resolution to the plugin, which ignores objcopy's symtab edits.
   _patch(root / "build/toolchains/lto.toml",
          "preserve_lto_sections = false", "preserve_lto_sections = true")
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
   "missing_internal_include_root": _missing_internal_include_root,
   "public_header_includes_internal": _public_header_includes_internal,
   "public_header_includes_internal_quoted": _public_header_includes_internal_quoted,
   "feature_source_includes_internal": _feature_source_includes_internal,
   "toolchain_unknown_top_level_key": _toolchain_unknown_top_level_key,
   "toolchain_unknown_flag_key": _toolchain_unknown_flag_key,
   "toolchain_unknown_archive_strategy": _toolchain_unknown_archive_strategy,
   "toolchain_extends_missing": _toolchain_extends_missing,
   "toolchain_extends_cycle": _toolchain_extends_cycle,
   "profile_missing_table": _profile_missing_table,
   "profile_source_root_missing": _profile_source_root_missing,
   "profile_no_toolchain": _profile_no_toolchain,
   "profile_no_config_header": _profile_no_config_header,
   "localize_hidden_with_preserved_lto": _localize_hidden_with_preserved_lto,
}


def test_diagnostics_match_golden(tmp_path):
   messages = {}
   for name, build_case in CASES.items():
      root = _copy_fixture(tmp_path / name)
      messages[name] = _capture(root, build_case(root))
   assert_golden("diagnostics", messages)


def test_merged_table_diagnostics_name_the_declaring_file(tmp_path):
   """Table validators (`tools`, `flags`, `settings`, `archive`) run per-file in
   `_load_and_merge`, against that file's own path, before inheritance merges
   it into anything else. A bad key planted in a parent is blamed on the
   parent, not on the child that merely extends it.

   (Formerly a known defect: these validators used to run once in
   `_build_toolchain` against the merged dict carrying the leaf path, so a key
   inherited from a parent was misattributed to the child. Fixed 2026-07-30.)
   """
   root = _copy_fixture(tmp_path / "misattribution")
   _patch(root / "build/toolchains/base.toml",
          'c      = ["-std=c17"]', 'c      = ["-std=c17"]\ncxxx   = ["-oops"]')

   message = _capture(root, lambda: plan_build(_resolve(root)))

   assert "unknown keys in [flags]: cxxx" in message
   assert message.endswith("unknown keys in [flags]: cxxx")
   assert "base.toml" in message, "the file that declared it is named"
   assert "child.toml" not in message, "not blamed on the leaf"


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



# ---------------------------------------------------------------------------
# The internal-header leak check, from the side that must NOT fire
# ---------------------------------------------------------------------------

def test_a_commented_out_include_of_an_internal_header_is_not_a_leak(tmp_path):
   root = _copy_fixture(tmp_path / "commented")
   header = root / "src/port/include/mini/port.hpp"
   header.write_text(header.read_text() + "// #include <mini/port_internal.hpp>\n")
   plan_build(_resolve(root))  # must not raise


def test_an_include_that_resolves_next_to_the_includer_is_not_a_leak(tmp_path):
   """A quote include resolves next to the includer FIRST, so a name that also
   exists under an internal root is not a leak: the compiler never reaches the
   root. Set up as a genuine shadow, otherwise the rule is not exercised at all
   (mutation testing caught that: without the shadow the check passes either
   way)."""
   root = _copy_fixture(tmp_path / "sibling")
   (root / "src/port/include/mini/shadow.hpp").write_text("#pragma once\n")
   (root / "src/port/internal_headers/shadow.hpp").write_text("#pragma once\n")
   header = root / "src/port/include/mini/port.hpp"
   header.write_text(header.read_text() + '#include "shadow.hpp"\n')
   plan_build(_resolve(root))  # must not raise


def test_a_public_header_including_another_public_header_is_not_a_leak(tmp_path):
   """Negative control for the matcher: it must key on INTERNAL destinations,
   not fire on any include at all."""
   root = _copy_fixture(tmp_path / "public_to_public")
   header = root / "src/kernel/include/mini/kernel.hpp"
   header.write_text(header.read_text() + "#include <mini/port.hpp>\n")
   plan_build(_resolve(root))  # must not raise


def test_every_leaking_public_header_is_reported_not_just_the_first(tmp_path):
   root = _copy_fixture(tmp_path / "two_leaks")
   for rel in ("src/port/include/mini/port.hpp", "src/kernel/include/mini/kernel.hpp"):
      header = root / rel
      header.write_text(header.read_text() + "#include <mini/port_internal.hpp>\n")

   message = _capture(root, lambda: plan_build(_resolve(root)))
   assert "'mini/port.hpp' includes internal header" in message
   assert "'mini/kernel.hpp' includes internal header" in message
