"""
tomlfmt.py — canonical formatting for the project's TOML files.

Runs on every build, unconditionally, with no opt-out (see commands/base.py).
The point is that a manifest edited in any order is rewritten into the canonical
one, so the next commit carries the formatted file and the ordering question
never comes up in review.

Three properties this must never violate, all covered by tests:

1. **It never changes meaning.** The result is re-parsed and compared with the
   original parse. If they differ the file is left exactly as it was and a
   warning is printed. A formatter that can corrupt a manifest is worse than no
   formatter.
2. **It never loses anything.** Comments stay attached to what they document,
   and keys the schema does not know are kept (sorted, after the known ones).
   `project_model.py` ignores unknown keys, so dropping them here would delete a
   typo'd key silently rather than leaving it to be noticed.
3. **It is idempotent.** Formatting formatted text is a no-op, so a build never
   rewrites a file that is already canonical, and no file churns mtime.

Style: three-space indent (the project's convention in Python and C++), one
blank line between sections, a blank line before any key that carries its own
comment. An array keeps its exploded, one-per-line form when it was written with
a trailing comma (the "magic trailing comma" rule, as Black uses it), so a list
the author deliberately spread out stays that way. Otherwise it collapses onto
one line when it fits.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

INDENT = "   "
MAX_WIDTH = 88

# Canonical order. "" is the top level (keys before any [section]). Sections and
# keys not listed keep their data and sort alphabetically after the known ones,
# so an unrecognised key is visible rather than lost.
_MANIFEST_KEYS = [
   "name", "kind", "description", "dependencies", "variants",
   "source_roots", "sources", "sources_excluded_from_archive",
   "private_includes", "internal_include_roots",
   "public_headers", "public_modules", "private_modules",
   "system_libraries", "generated_includes",
]

SCHEMAS: dict[str, dict[str, list[str]]] = {
   "manifest": {
      "__sections__": [""],
      "": _MANIFEST_KEYS,
   },
   "profile": {
      "__sections__": ["", "profile", "layout", "components", "features", "output"],
      "": [],
      "profile": ["name", "toolchain", "config_header"],
      "layout": ["project_root", "build_root", "source_root", "output_root"],
      "components": ["port", "time_driver"],
      "features": ["enable"],
      "output": ["archive"],
   },
   "toolchain": {
      "__sections__": ["", "tools", "flags", "settings", "archive"],
      "": ["name", "extends"],
      "tools": ["cc", "cxx", "ar", "asm", "objcopy"],
      "flags": ["common", "common_add", "common_remove", "c", "c_add", "c_remove",
                "cxx", "cxx_add", "cxx_remove", "asm", "asm_add", "asm_remove",
                "link", "link_add", "link_remove"],
      "settings": ["family", "debug", "optimization", "warnings_as_errors"],
      "archive": ["strategy", "localize_hidden", "preserve_lto_sections"],
   },
   "test": {
      "__sections__": ["", "test", "components", "link"],
      "": [],
      "test": ["name", "layer", "kind", "harness_debt", "source", "config"],
      "components": ["port", "time_driver", "features"],
      "link": ["system_libraries", "extra_link_flags"],
   },
}


def detect_kind(text: str) -> str:
   """Which schema a file follows, from its own content rather than its path.

   Content, because the same shape appears under several names: profiles live in
   `profiles/` here and next to a consumer's main.cpp there.
   """
   if "[profile]" in text:
      return "profile"
   if "[test]" in text:
      return "test"
   if "[tools]" in text or "[flags]" in text:
      return "toolchain"
   return "manifest"


class _Entry:
   """One key and the comment block attached above it."""

   def __init__(self, key: str, comments: list[str], value_lines: list[str],
                blank_before: bool = False):
      self.key = key
      self.comments = comments
      self.value_lines = value_lines
      # The author separated this from what came before. Preserved, so grouping
      # written on purpose survives reordering.
      self.blank_before = blank_before


class _Section:
   def __init__(self, name: str, header_comments: list[str]):
      self.name = name                      # "" for the top level
      self.header_comments = header_comments
      self.entries: list[_Entry] = []
      self.trailing_comments: list[str] = []


def _split_sections(text: str) -> list[_Section]:
   sections = [_Section("", [])]
   pending: list[str] = []
   lines = text.splitlines()
   i = 0
   blank_run = False           # a blank line seen since the last item
   blank_after_comments = False  # ... specifically after the pending comment block

   while i < len(lines):
      line = lines[i]
      stripped = line.strip()

      if not stripped:
         blank_run = True
         if pending:
            blank_after_comments = True
         i += 1
         continue

      if stripped.startswith("#"):
         if blank_after_comments:
            # A blank line split one comment block from another: the earlier one
            # documents nothing that follows, so it stays where it is.
            sections[-1].trailing_comments.extend(pending)
            pending = []
            blank_after_comments = False
         pending.append(stripped)
         i += 1
         continue

      if stripped.startswith("["):
         # A comment block separated from this header by a blank line belongs to
         # the section it sits IN, not to the one starting here. Without this a
         # note like "config_header is intentionally omitted" migrates into the
         # next section, which reads as documenting the wrong thing.
         header_comments = pending
         if blank_after_comments:
            sections[-1].trailing_comments.extend(pending)
            header_comments = []
         sections.append(_Section(stripped.strip("[]").strip(), header_comments))
         pending = []
         blank_run = False
         blank_after_comments = False
         i += 1
         continue

      # A key. Consume continuation lines until brackets balance, so a
      # multi-line array (and any comment inside it) arrives intact.
      key = stripped.split("=", 1)[0].strip()
      value_lines = [stripped]
      depth = _bracket_depth(stripped)
      while depth > 0 and i + 1 < len(lines):
         i += 1
         value_lines.append(lines[i].strip())
         depth += _bracket_depth(lines[i])

      if blank_after_comments:
         sections[-1].trailing_comments.extend(pending)
         pending = []
      sections[-1].entries.append(_Entry(key, pending, value_lines, blank_before=blank_run))
      pending = []
      blank_run = False
      blank_after_comments = False
      i += 1

   if pending:
      sections[-1].trailing_comments = pending
   return sections


def _bracket_depth(line: str) -> int:
   """Net bracket depth of a line, ignoring brackets inside strings/comments."""
   depth = 0
   in_string = False
   quote = ""
   for index, char in enumerate(line):
      if in_string:
         if char == quote and line[index - 1] != "\\":
            in_string = False
         continue
      if char in "\"'":
         in_string = True
         quote = char
         continue
      if char == "#":
         break
      if char == "[":
         depth += 1
      elif char == "]":
         depth -= 1
   return depth


def _render_entry(entry: _Entry) -> list[str]:
   out = list(entry.comments)

   if len(entry.value_lines) == 1:
      out.append(_normalise_assignment(entry.value_lines[0]))
      return out

   # Multi-line. Elements are kept verbatim (so a comment inside an array
   # survives) and re-indented.
   head = _normalise_assignment(entry.value_lines[0])
   body = entry.value_lines[1:-1]
   tail = entry.value_lines[-1]

   has_comment = any(part.lstrip().startswith("#") for part in body)
   trailing_comma = bool(body) and body[-1].rstrip().endswith(",")

   if not has_comment and not trailing_comma:
      collapsed = f"{head}{' '.join(body)}{tail}"
      collapsed = " ".join(collapsed.split())
      collapsed = collapsed.replace("[ ", "[").replace(" ]", "]")
      if len(collapsed) <= MAX_WIDTH:
         out.append(collapsed)
         return out

   out.append(head)
   out.extend(f"{INDENT}{part}" for part in body)
   out.append(tail)
   return out


def _normalise_assignment(line: str) -> str:
   """`key   =  value` -> `key = value`, leaving the value text untouched."""
   if "=" not in line:
      return line
   key, value = line.split("=", 1)
   return f"{key.strip()} = {value.strip()}"


def _order(names: list[str], known: list[str]) -> list[str]:
   known_present = [n for n in known if n in names]
   unknown = sorted(n for n in names if n not in known)
   return known_present + unknown


def format_text(text: str, kind: str | None = None) -> str:
   """Return `text` in canonical form. Raises nothing: on any doubt, see format_file."""
   kind = kind or detect_kind(text)
   schema = SCHEMAS.get(kind, SCHEMAS["manifest"])

   sections = _split_sections(text)
   by_name: dict[str, _Section] = {}
   for section in sections:
      if section.name in by_name:
         # Duplicate table: leave the file alone rather than guess a merge.
         raise ValueError(f"duplicate section [{section.name}]")
      by_name[section.name] = section

   section_order = _order(list(by_name), schema.get("__sections__", [""]))

   rendered: list[str] = []
   for name in section_order:
      section = by_name[name]
      if not section.entries and not section.header_comments and not section.trailing_comments:
         continue

      if rendered:
         rendered.append("")
      rendered.extend(section.header_comments)
      if name:
         rendered.append(f"[{name}]")

      keys = _order([e.key for e in section.entries], schema.get(name, []))
      entries = {e.key: e for e in section.entries}
      for index, key in enumerate(keys):
         entry = entries[key]
         if index > 0 and (entry.comments or entry.blank_before):
            rendered.append("")
         rendered.extend(_render_entry(entry))

      if section.trailing_comments:
         rendered.append("")
         rendered.extend(section.trailing_comments)

   return "\n".join(rendered).rstrip("\n") + "\n"


def format_file(path: Path) -> bool:
   """Format `path` in place. Returns True when the file changed.

   Never raises on a malformed or surprising file: it warns and leaves it alone,
   because a build must not be blocked by, or silently corrupt, a file the
   formatter did not understand.
   """
   try:
      original = path.read_text()
   except OSError as exc:
      print(f"  tomlfmt: cannot read {path}: {exc}")
      return False

   try:
      before = tomllib.loads(original)
   except tomllib.TOMLDecodeError:
      return False  # the loaders will report the syntax error with better context

   try:
      formatted = format_text(original)
   except Exception as exc:  # noqa: BLE001 - never let formatting break a build
      print(f"  tomlfmt: skipped {path}: {exc}")
      return False

   if formatted == original:
      return False

   try:
      after = tomllib.loads(formatted)
   except tomllib.TOMLDecodeError as exc:
      print(f"  tomlfmt: skipped {path}: formatting would not re-parse ({exc})")
      return False

   if after != before:
      print(f"  tomlfmt: skipped {path}: formatting would change its meaning")
      return False

   try:
      path.write_text(formatted)
   except OSError as exc:
      print(f"  tomlfmt: cannot write {path}: {exc}")
      return False
   return True


def format_project(*, source_root: Path, profile_path: Path, extra: tuple[Path, ...] = ()) -> list[Path]:
   """Format every TOML this project owns, and return the ones that changed.

   Deliberately broad: all manifests under source_root, everything alongside the
   profile and in a sibling toolchains/ directory, and the unit tests'
   test.toml files. A file only gets rewritten if formatting actually changes
   it, so the common case touches nothing.
   """
   candidates: list[Path] = []

   for pattern in ("**/component.toml", "**/port.toml", "**/time_driver.toml", "**/feature.toml"):
      candidates.extend(source_root.glob(pattern))

   tests_root = source_root.parent / "tests"
   if tests_root.is_dir():
      candidates.extend(tests_root.glob("**/test.toml"))

   profile_dir = profile_path.parent
   candidates.extend(profile_dir.glob("*.toml"))
   toolchains = profile_dir.parent / "toolchains"
   if toolchains.is_dir():
      candidates.extend(toolchains.glob("*.toml"))
   candidates.extend(extra)

   changed: list[Path] = []
   for path in sorted({c.resolve() for c in candidates}):
      if format_file(path):
         changed.append(path)
   return changed
