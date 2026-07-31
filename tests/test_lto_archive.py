"""End-to-end tests for the `lto_merged` archive strategy.

These execute the real pipeline (partial-link, objcopy, ar) and inspect the
result with `nm`, because the thing under test is whether the *toolchain* honours
what the planner asked for. Asserting only on the plan would have missed the two
defects that actually broke this strategy:

  * the exported-symbol list had drifted to `_ZN6cortos…` after the CoRTOS→Cyros
    rename, so it matched nothing and `--keep-global-symbols` localized the
    entire archive — a plan-level test cannot see that;
  * `preserve_lto_sections` (i.e. `-flinker-output=rel`) leaves symbol
    resolution to the LTO plugin, which ignores the ELF symbol table objcopy
    edits, so hiding silently did nothing.

Uses the `lto_portb` fixture profile. The older `lto` profile targets `porta`,
which cannot be executed: its asm tool is `as`, and build_compile_args emits `-c`
and `-D`, which GNU as rejects.
"""
from __future__ import annotations

import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import FIXTURE_ROOT

from cyros_builder.actions import ArchiveAction, ObjcopyAction, PartialLinkAction
from cyros_builder.executor import execute_actions
from cyros_builder.include_tree import populate_include_tree
from cyros_builder.planner import plan_build
from cyros_builder.resolve import resolve_invocation

HAVE_TOOLS = all(shutil.which(t) for t in ("g++", "gcc", "objcopy", "ar", "nm"))
needs_tools = pytest.mark.skipif(not HAVE_TOOLS, reason="g++/objcopy/ar/nm not all on PATH")

pytestmark = needs_tools


@pytest.fixture
def built(tmp_path):
   """Build the lto_portb fixture profile and hand back (archive, resolved)."""
   repo = tmp_path / "mini"
   shutil.copytree(FIXTURE_ROOT, repo)
   resolved = resolve_invocation(Namespace(
      profile=str(repo / "build" / "profiles" / "lto_portb.toml"),
      toolchain=None, config=None, output=str(tmp_path / "out"),
   ))
   populate_include_tree(resolved)
   actions = plan_build(resolved)
   execute_actions(actions)
   archive = next(a for a in actions if isinstance(a, ArchiveAction)).output
   assert archive.is_file(), archive
   return archive, resolved, repo


def symbols(path: Path) -> dict[str, str]:
   """name -> nm type letter, for defined symbols only."""
   out = subprocess.run(["nm", "--defined-only", str(path)],
                        capture_output=True, text=True, check=True).stdout
   result = {}
   for line in out.splitlines():
      parts = line.split()
      if len(parts) == 3:
         result[parts[2]] = parts[1]
   return result


def find(table: dict[str, str], needle: str) -> list[tuple[str, str]]:
   return [(n, t) for n, t in table.items() if needle in n]


# ---------------------------------------------------------------------------

def test_archive_holds_exactly_one_merged_member(built):
   archive, _, _ = built
   members = subprocess.run(["ar", "t", str(archive)],
                            capture_output=True, text=True, check=True).stdout.split()
   assert members == ["libmini.o"], members


def test_public_symbol_stays_global_and_internal_becomes_local(built):
   """The whole point. kernel_entry is marked MINI_PUBLIC; port_init is not."""
   archive, _, _ = built
   table = symbols(archive)

   public = find(table, "kernel_entry")
   internal = find(table, "port_init")
   assert public, f"kernel_entry missing entirely: {sorted(table)[:20]}"
   assert internal, f"port_init missing entirely: {sorted(table)[:20]}"

   assert all(t == "T" for _, t in public), f"public symbol was localized: {public}"
   assert all(t == "t" for _, t in internal), f"internal stayed global: {internal}"


def test_something_is_actually_hidden(built):
   """Guards against the archive simply exporting everything (which would make
   the test above pass for the wrong reason) and against the opposite failure,
   where a stale symbol list localized absolutely everything."""
   archive, _, _ = built
   table = symbols(archive)
   globals_ = [n for n, t in table.items() if t == "T"]
   locals_ = [n for n, t in table.items() if t == "t"]
   assert globals_, "nothing is exported at all — this was the original breakage"
   assert locals_, "nothing was hidden — localization did not happen"


def test_consumer_links_against_the_public_api(built, tmp_path):
   """The check the broken pipeline could never pass."""
   archive, resolved, _ = built
   include = Path(resolved.output_root) / resolved.profile.name / \
      resolved.selected_toolchain_name / "include"

   src = tmp_path / "consumer.cpp"
   src.write_text('#include "mini/kernel.hpp"\nint main() { return mini::kernel_entry() == 1 ? 0 : 1; }\n')
   binary = tmp_path / "consumer"

   result = subprocess.run(
      ["g++", "-std=c++20", "-I", str(include), str(src), str(archive), "-o", str(binary)],
      capture_output=True, text=True,
   )
   assert result.returncode == 0, result.stderr
   assert binary.is_file()


def test_consumer_cannot_reach_a_hidden_symbol(built, tmp_path):
   """Localization must be real, not cosmetic."""
   archive, _, _ = built
   src = tmp_path / "reaching.cpp"
   src.write_text("namespace mini { void port_init(); }\nint main() { mini::port_init(); return 0; }\n")

   result = subprocess.run(
      ["g++", "-std=c++20", str(src), str(archive), "-o", str(tmp_path / "reaching")],
      capture_output=True, text=True,
   )
   assert result.returncode != 0, "linked against a symbol that should be hidden"
   assert "undefined reference" in result.stderr, result.stderr


def test_merge_uses_nolto_rel_so_localization_can_work(built):
   """`rel` would retain LTO IR and make the objcopy step a silent no-op."""
   _, resolved, _ = built
   partial = next(a for a in plan_build(resolved) if isinstance(a, PartialLinkAction))
   assert "-flinker-output=nolto-rel" in partial.arguments
   assert "-flinker-output=rel" not in partial.arguments

   objcopy = next(a for a in plan_build(resolved) if isinstance(a, ObjcopyAction))
   assert "--localize-hidden" in objcopy.arguments


def test_dropping_the_visibility_flag_stops_hiding(built, tmp_path):
   """Proves the toolchain flag is what drives this, not something incidental:
   without -fvisibility=hidden there is nothing marked hidden, so
   --localize-hidden has no effect and the internal stays global."""
   _, _, repo = built
   toolchain = repo / "build" / "toolchains" / "lto.toml"
   toolchain.write_text(
      toolchain.read_text()
      .replace('c_add   = ["-fvisibility=hidden"]', "c_add   = []")
      .replace('cxx_add = ["-fvisibility=hidden", "-fvisibility-inlines-hidden"]', "cxx_add = []")
   )

   out = tmp_path / "out_novis"
   resolved = resolve_invocation(Namespace(
      profile=str(repo / "build" / "profiles" / "lto_portb.toml"),
      toolchain=None, config=None, output=str(out),
   ))
   populate_include_tree(resolved)
   actions = plan_build(resolved)
   execute_actions(actions)
   archive = next(a for a in actions if isinstance(a, ArchiveAction)).output

   internal = find(symbols(archive), "port_init")
   assert internal, "port_init vanished"
   assert all(t == "T" for _, t in internal), (
      f"expected the internal to stay global without the flag, got {internal}"
   )
