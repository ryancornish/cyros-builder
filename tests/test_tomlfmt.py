"""Tests for the TOML formatter (tomlfmt.py).

It runs on every build with no opt-out, so it is held to three properties, and
each has tests here: it never changes a file's meaning, it never loses a key or
a comment, and it is idempotent. The fourth group checks the canonical style
itself (order, indent, array form).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from conftest import FIXTURE_ROOT

from cyros_builder.tomlfmt import detect_kind, format_file, format_project, format_text


# ---------------------------------------------------------------------------
# Meaning is never changed
# ---------------------------------------------------------------------------

REAL_ISH = '''name = "port"
kind = "port"

variants = [
  "linux_coop",
  "linux_preempt",
]

# The kernel-to-port contract.
internal_include_roots = [
  "internal_headers",
]
'''


def test_formatting_preserves_the_parsed_document():
   assert tomllib.loads(format_text(REAL_ISH)) == tomllib.loads(REAL_ISH)


@pytest.mark.parametrize("name", [
   "src/kernel/component.toml",
   "src/port/component.toml",
   "src/port/porta/port.toml",
   "build/profiles/full.toml",
   "build/toolchains/base.toml",
   "tests/unit/mini_case/test.toml",
])
def test_every_fixture_toml_keeps_its_meaning(name):
   """Run over the real fixture files, which carry comments, nested tables and
   both indent styles."""
   text = (FIXTURE_ROOT / name).read_text()
   assert tomllib.loads(format_text(text)) == tomllib.loads(text)


def test_a_file_that_cannot_be_formatted_is_left_alone(tmp_path):
   """Never block a build, never corrupt a file the formatter did not follow."""
   path = tmp_path / "dup.toml"
   original = '[a]\nx = 1\n\n[a]\ny = 2\n'   # duplicate table: invalid TOML anyway
   path.write_text(original)
   assert format_file(path) is False
   assert path.read_text() == original


# ---------------------------------------------------------------------------
# Nothing is lost
# ---------------------------------------------------------------------------

def test_comments_stay_attached_to_their_key():
   text = 'name = "x"\n\n# why this is here\n# second line\nsources = ["a.cpp"]\n'
   out = format_text(text)
   lines = out.splitlines()
   i = lines.index("# why this is here")
   assert lines[i + 1] == "# second line"
   assert lines[i + 2].startswith("sources =")


def test_unknown_keys_are_kept_and_sorted_after_known_ones():
   """project_model ignores unknown keys, so dropping one here would delete a
   typo silently instead of leaving it visible."""
   text = 'zzz_unknown = 1\nname = "x"\naaa_unknown = 2\n'
   out = format_text(text)
   assert tomllib.loads(out) == tomllib.loads(text)
   keys = [line.split(" =")[0] for line in out.splitlines() if " = " in line]
   assert keys == ["name", "aaa_unknown", "zzz_unknown"]


def test_unknown_sections_are_kept():
   text = '[profile]\nname = "p"\n\n[mystery]\nk = 1\n'
   out = format_text(text)
   assert tomllib.loads(out) == tomllib.loads(text)
   assert "[mystery]" in out


def test_a_comment_inside_an_array_survives():
   text = 'sources = [\n  "a.cpp",\n  # keep me\n  "b.cpp",\n]\n'
   out = format_text(text)
   assert "# keep me" in out
   assert tomllib.loads(out) == tomllib.loads(text)


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
   "src/kernel/component.toml",
   "build/profiles/full.toml",
   "build/toolchains/child.toml",
   "tests/unit/mini_case/test.toml",
])
def test_formatting_is_idempotent(name):
   once = format_text((FIXTURE_ROOT / name).read_text())
   assert format_text(once) == once


def test_an_already_formatted_file_is_not_rewritten(tmp_path):
   """A build must not churn mtimes on files that are already canonical."""
   path = tmp_path / "c.toml"
   path.write_text(format_text(REAL_ISH))
   before = path.stat().st_ctime_ns
   assert format_file(path) is False
   assert path.stat().st_ctime_ns == before


# ---------------------------------------------------------------------------
# The canonical style
# ---------------------------------------------------------------------------

def test_keys_are_reordered_into_schema_order():
   text = 'sources = ["a.cpp"]\nkind = "core"\nname = "kernel"\n'
   out = format_text(text)
   keys = [line.split(" =")[0] for line in out.splitlines() if " = " in line]
   assert keys == ["name", "kind", "sources"]


def test_sections_are_reordered_into_schema_order():
   text = '[output]\narchive = "libx.a"\n\n[profile]\nname = "p"\n\n[layout]\nsource_root = "../s"\n'
   out = format_text(text)
   assert [l for l in out.splitlines() if l.startswith("[")] == [
      "[profile]", "[layout]", "[output]",
   ]


def test_multi_line_arrays_are_indented_three_spaces():
   text = 'sources = [\n      "a.cpp",\n  "b.cpp",\n]\n'
   out = format_text(text)
   assert '\n   "a.cpp",\n   "b.cpp",\n' in out


def test_a_trailing_comma_keeps_an_array_exploded():
   """The author spread it out on purpose, so it stays that way even though it
   would fit on one line (the 'magic trailing comma' rule)."""
   text = 'variants = [\n  "a",\n  "b",\n]\n'
   assert format_text(text).count("\n") > 2


def test_an_array_without_a_trailing_comma_collapses_when_it_fits():
   text = 'sources_excluded_from_archive = [\n  "validate_config.cpp"\n]\n'
   out = format_text(text)
   assert out.strip() == 'sources_excluded_from_archive = ["validate_config.cpp"]'


def test_spacing_around_equals_is_normalised():
   text = 'name    =    "x"\n'
   assert format_text(text).strip() == 'name = "x"'


@pytest.mark.parametrize("text,kind", [
   ('[profile]\nname = "p"\n', "profile"),
   ('[test]\nname = "t"\n', "test"),
   ('name = "tc"\n[tools]\ncc = "gcc"\n', "toolchain"),
   ('name = "kernel"\nsources = []\n', "manifest"),
])
def test_kind_is_detected_from_content_not_path(text, kind):
   assert detect_kind(text) == kind


# ---------------------------------------------------------------------------
# Project sweep
# ---------------------------------------------------------------------------

def test_format_project_covers_manifests_profiles_toolchains_and_tests(tmp_path):
   import shutil
   root = tmp_path / "mini"
   shutil.copytree(FIXTURE_ROOT, root)

   # Scramble one file of each kind.
   (root / "src/kernel/component.toml").write_text(
      'sources = ["kernel.cpp"]\nname = "kernel"\n'
   )
   (root / "build/profiles/full.toml").write_text(
      (root / "build/profiles/full.toml").read_text().replace("[profile]", "[profile]\n")
   )

   changed = format_project(
      source_root=root / "src",
      profile_path=root / "build" / "profiles" / "full.toml",
   )
   changed_names = {p.name for p in changed}
   assert "component.toml" in changed_names

   # And running again changes nothing: the sweep is idempotent too.
   assert format_project(
      source_root=root / "src",
      profile_path=root / "build" / "profiles" / "full.toml",
   ) == []


def test_a_comment_ending_a_section_stays_in_that_section():
   """A blank line between the comment and the next header means the comment
   documents the section it sits in. Without this rule the note below migrates
   above [layout] and reads as documenting the wrong table, which is what the
   first version of the formatter did to unit_test_preempt.toml."""
   text = (
      '[profile]\n'
      'name = "p"\n'
      '\n'
      '# config_header is intentionally omitted. Each test supplies its own.\n'
      '\n'
      '[layout]\n'
      'source_root = "../s"\n'
   )
   lines = format_text(text).splitlines()
   note = next(i for i, l in enumerate(lines) if l.startswith("# config_header"))
   layout = lines.index("[layout]")
   assert note < layout
   assert lines[layout - 1] == "", "the note was glued onto [layout]"
   assert "[profile]" in lines[:note]
   assert not any(l.startswith("[") for l in lines[lines.index("[profile]") + 1:note])


def test_a_comment_directly_above_a_section_header_stays_with_it():
   """The other half of the rule: no blank line means it documents what follows."""
   text = '[profile]\nname = "p"\n\n# how the tree is laid out\n[layout]\nsource_root = "../s"\n'
   lines = format_text(text).splitlines()
   note = lines.index("# how the tree is laid out")
   assert lines[note + 1] == "[layout]"


def test_blank_lines_between_key_groups_are_preserved():
   """Grouping written on purpose survives reordering, so a component.toml does
   not come back from a build as one dense block."""
   text = 'name = "kernel"\nkind = "core"\n\nsources = ["a.cpp"]\npublic_headers = ["b.hpp"]\n'
   out = format_text(text)
   assert out == 'name = "kernel"\nkind = "core"\n\nsources = ["a.cpp"]\npublic_headers = ["b.hpp"]\n'
