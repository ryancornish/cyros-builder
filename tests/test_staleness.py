"""Tests for the incremental build stage (staleness.py).

These do run a real compiler, because the thing under test is partly gcc's
behaviour: the `.d` file it writes is what makes a header edit invalidate an
object, and asserting on a hand-written .d would test a mock instead. The
fixture is tiny, so a full build here is well under a second.

The failure mode being guarded against is the dangerous one: an action that
*should* rebuild and does not. Every test that asserts something is skipped is
paired with one asserting it is not skipped when the corresponding input moves.

These use the `portb` profile because it is the only fixture profile that can
actually be *executed*. `porta` includes an asm TU whose tool is `as`, and
build_compile_args emits `-c` plus the toolchain's `-D` flags, neither of which
GNU as accepts (real cyros uses gcc-15 as its asm tool, which does). The fixture
keeps `asm = "as"` deliberately so the plan goldens can prove `tools.asm` is
used rather than `tools.cc`; the cost is that porta is plan-testable but not
runnable. The asm and out-of-tree-C argv paths are covered by the goldens.
"""
from __future__ import annotations

import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import FIXTURE_ROOT

from cyros_builder.actions import ArchiveAction, CompileAction
from cyros_builder.compile_args import depfile_path
from cyros_builder.executor import execute_actions
from cyros_builder.include_tree import populate_include_tree
from cyros_builder.output import build_state_path
from cyros_builder.planner import plan_build
from cyros_builder.resolve import resolve_invocation
from cyros_builder.staleness import (
   declared_inputs,
   load_state,
   prune_actions,
   record_state,
)

HAVE_GCC = shutil.which("gcc") is not None and shutil.which("g++") is not None
needs_gcc = pytest.mark.skipif(not HAVE_GCC, reason="gcc/g++ not on PATH")


@pytest.fixture
def repo(tmp_path):
   """A private copy of the fixture, so tests can edit its sources."""
   root = tmp_path / "mini"
   shutil.copytree(FIXTURE_ROOT, root)
   return root


def resolve(repo: Path, out: Path, profile: str = "portb"):
   # portb: no out-of-tree C source and no asm TU, so every compile is C++ and
   # carries a depfile. The asm/C paths are covered by the plan goldens.
   return resolve_invocation(Namespace(
      profile=str(repo / "build" / "profiles" / f"{profile}.toml"),
      toolchain=None, config=None, output=str(out),
   ))


def build(resolved, *, force=False):
   """One full build cycle: include tree, plan, prune, execute, record.
   Returns (executed_actions, pruned)."""
   populate_include_tree(resolved)
   actions = plan_build(resolved)
   pruned = prune_actions(resolved, actions, force=force)
   execute_actions(pruned.actions)
   record_state(resolved, actions, pruned.actions)
   return actions, pruned


def names(actions):
   return sorted(a.output.name for a in actions if hasattr(a, "output"))


# ---------------------------------------------------------------------------
# Pure prune logic, no compiler needed
# ---------------------------------------------------------------------------

def test_first_build_runs_everything(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   populate_include_tree(resolved)
   actions = plan_build(resolved)
   pruned = prune_actions(resolved, actions)
   assert pruned.actions == actions
   assert pruned.skipped == 0


def test_force_runs_everything_even_when_current(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   actions, _ = build(resolved)
   _, pruned = build(resolved, force=True)
   assert len(pruned.actions) == len(actions)
   assert pruned.skipped == 0


def test_missing_state_file_is_a_full_rebuild(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)
   build_state_path(resolved).unlink()
   _, pruned = build(resolved)
   assert pruned.skipped == 0


def test_state_version_mismatch_invalidates_everything(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)
   path = build_state_path(resolved)
   path.write_text(path.read_text().replace('"version": 2', '"version": 99', 1))
   assert load_state(resolved) == {}
   _, pruned = build(resolved)
   assert pruned.skipped == 0


def test_corrupt_state_file_is_a_full_rebuild(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)
   build_state_path(resolved).write_text("{ not json")
   _, pruned = build(resolved)
   assert pruned.skipped == 0


# ---------------------------------------------------------------------------
# The real thing
# ---------------------------------------------------------------------------

@needs_gcc
def test_second_build_skips_everything(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   actions, first = build(resolved)
   assert first.skipped == 0

   _, second = build(resolved)
   assert second.actions == [], f"expected a no-op, still ran {names(second.actions)}"
   assert second.skipped == second.total == len(actions)


@needs_gcc
def test_editing_one_source_rebuilds_only_it_and_the_archive(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)

   target = repo / "src" / "time" / "tick" / "tick.cpp"
   target.write_text(target.read_text().replace("return 0u;", "return 7u;"))

   _, pruned = build(resolved)
   assert names(pruned.actions) == ["libmini.a", "tick.o"], names(pruned.actions)


@needs_gcc
def test_editing_a_header_rebuilds_its_dependents_via_the_depfile(repo, tmp_path):
   """The load-bearing case: nothing in the plan mentions the header, so only
   the .d gcc wrote can connect it to kernel.o."""
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)

   header = repo / "src" / "kernel" / "include" / "mini" / "kernel.hpp"
   assert header.is_file()
   header.write_text(header.read_text() + "\nnamespace mini { int extra(); }\n")

   _, pruned = build(resolved)
   rebuilt = names(pruned.actions)
   assert "kernel.o" in rebuilt, rebuilt
   assert "validate.o" in rebuilt, "validate.cpp also includes it"
   assert "libmini.a" in rebuilt, "the archive must follow its members"
   assert "portb.o" not in rebuilt, "portb.cpp does not include kernel.hpp"


@needs_gcc
def test_editing_a_private_header_rebuilds_only_its_group(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)

   private = repo / "src" / "kernel" / "private" / "kernel_detail.hpp"
   private.write_text(private.read_text().replace("return 1;", "return 2;"))

   _, pruned = build(resolved)
   rebuilt = names(pruned.actions)
   assert "kernel.o" in rebuilt
   assert "portb.o" not in rebuilt
   assert "tick.o" not in rebuilt


@needs_gcc
def test_depfile_records_the_generated_config_header(repo, tmp_path):
   """Every TU sees the generated include tree, so a config change must be
   able to invalidate objects."""
   resolved = resolve(repo, tmp_path / "out")
   actions, _ = build(resolved)

   kernel = next(a for a in actions
                 if isinstance(a, CompileAction) and a.source.name == "kernel.cpp")
   deps = declared_inputs(kernel)
   assert depfile_path(kernel.output).is_file()
   assert any(p.name == "kernel.hpp" for p in deps), deps
   assert any("private" in str(p) for p in deps), deps


@needs_gcc
def test_toolchain_flag_change_rebuilds_via_argv_hash(repo, tmp_path):
   """No input file changed, only the command line — the argv hash must catch
   it, since content hashing alone would not."""
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)

   toolchain = repo / "build" / "toolchains" / "base.toml"
   toolchain.write_text(toolchain.read_text().replace('common = ["-DBASE"', 'common = ["-DBASE", "-DNEWFLAG"'))

   resolved2 = resolve(repo, tmp_path / "out")
   _, pruned = build(resolved2)
   assert pruned.skipped == 0, "a flag change must rebuild every compile"


@needs_gcc
def test_deleting_an_object_rebuilds_just_that_object_and_the_archive(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   actions, _ = build(resolved)

   tick = next(a for a in actions
               if isinstance(a, CompileAction) and a.source.name == "tick.cpp")
   tick.output.unlink()

   _, pruned = build(resolved)
   assert names(pruned.actions) == ["libmini.a", "tick.o"], names(pruned.actions)


@needs_gcc
def test_deleting_the_archive_rebuilds_only_the_archive(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   actions, _ = build(resolved)

   archive = next(a for a in actions if isinstance(a, ArchiveAction))
   archive.output.unlink()

   _, pruned = build(resolved)
   assert names(pruned.actions) == ["libmini.a"]


@needs_gcc
def test_archive_rebuilds_when_the_member_set_changes(repo, tmp_path):
   """Adding a feature changes the archive's members without touching any
   existing member's content."""
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)

   profile = repo / "build" / "profiles" / "portb.toml"
   profile.write_text(profile.read_text().replace("enable = []", 'enable = ["alpha"]'))

   resolved2 = resolve(repo, tmp_path / "out")
   _, pruned = build(resolved2)
   rebuilt = names(pruned.actions)
   assert "alpha.o" in rebuilt, "the new member must compile"
   assert "libmini.a" in rebuilt, "member set changed, so re-archive"
   assert "tick.o" not in rebuilt, "an untouched member must not recompile"


@needs_gcc
def test_archive_rebuilds_when_a_member_is_removed(repo, tmp_path):
   """The case where the member-set check is the *only* signal.

   Removing a feature builds no new object and changes no surviving object's
   content, so neither the missing-output rule nor transitivity fires. Only
   comparing the recorded member set against the current one notices — and if
   nothing notices, the archive keeps a member the build no longer declares.
   (Mutation testing found this gap: the add-a-member test passes even with the
   set check deleted, because a new object triggers transitivity instead.)
   """
   profile = repo / "build" / "profiles" / "portb.toml"
   profile.write_text(profile.read_text().replace("enable = []", 'enable = ["alpha"]'))

   resolved = resolve(repo, tmp_path / "out")
   build(resolved)
   archive = next(a for a in plan_build(resolved) if isinstance(a, ArchiveAction))
   assert any("alpha" in str(p) for p in archive.inputs)

   profile.write_text(profile.read_text().replace('enable = ["alpha"]', "enable = []"))
   resolved2 = resolve(repo, tmp_path / "out")
   _, pruned = build(resolved2)

   assert "libmini.a" in names(pruned.actions), (
      f"archive must re-archive when a member is dropped, ran {names(pruned.actions)}"
   )
   archive2 = next(a for a in plan_build(resolved2) if isinstance(a, ArchiveAction))
   assert not any("alpha" in str(p) for p in archive2.inputs)


@needs_gcc
def test_object_without_a_depfile_is_rebuilt(repo, tmp_path):
   """An object whose .d is missing has an unknown header set, so it cannot be
   trusted. This is the real upgrade path: state and objects produced by a
   builder from before `-MMD` existed, where skipping would make header edits
   invisible until something else forced a rebuild."""
   resolved = resolve(repo, tmp_path / "out")
   actions, _ = build(resolved)

   _, clean_run = build(resolved)
   assert clean_run.actions == [], "sanity: should be a no-op before we meddle"

   removed = 0
   for action in actions:
      depfile = depfile_path(action.output) if isinstance(action, CompileAction) else None
      if depfile is not None and depfile.is_file():
         depfile.unlink()
         removed += 1
   assert removed, "expected some depfiles to remove"

   _, pruned = build(resolved)
   assert len(pruned.actions) >= removed, (
      f"objects without a .d must rebuild, only ran {names(pruned.actions)}"
   )


@needs_gcc
def test_touching_a_source_without_changing_content_skips(repo, tmp_path):
   """Content hashes, not mtimes — the whole reason the plan insists on it."""
   resolved = resolve(repo, tmp_path / "out")
   build(resolved)

   target = repo / "src" / "time" / "tick" / "tick.cpp"
   target.write_text(target.read_text())          # new mtime, identical bytes
   subprocess.run(["touch", str(target)], check=True)

   _, pruned = build(resolved)
   assert pruned.actions == [], f"mtime-only change rebuilt {names(pruned.actions)}"


@needs_gcc
def test_reverting_an_edit_returns_to_a_no_op(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   target = repo / "src" / "time" / "tick" / "tick.cpp"
   original = target.read_text()

   build(resolved)
   target.write_text(original.replace("return 0u;", "return 7u;"))
   build(resolved)
   target.write_text(original)

   _, pruned = build(resolved)
   assert names(pruned.actions) == ["libmini.a", "tick.o"]

   _, again = build(resolved)
   assert again.actions == []


@needs_gcc
def test_failed_build_records_nothing(repo, tmp_path):
   """A build that dies partway must not record success for what did compile,
   or the next run would trust objects whose siblings never built."""
   resolved = resolve(repo, tmp_path / "out")
   populate_include_tree(resolved)

   broken = repo / "src" / "port" / "portb" / "portb.cpp"
   broken.write_text("this is not valid C++\n")

   actions = plan_build(resolved)
   pruned = prune_actions(resolved, actions)
   with pytest.raises(subprocess.CalledProcessError):
      execute_actions(pruned.actions)

   assert load_state(resolved) == {}, "no state may be written for a failed build"

   broken.write_text("#include \"mini/port.hpp\"\nnamespace mini { void port_init() {} }\n")
   _, pruned2 = build(resolved)
   assert pruned2.skipped == 0, "everything is re-examined after a failure"


@needs_gcc
def test_the_incremental_object_matches_a_clean_build(repo, tmp_path):
   """The point of all this: an incrementally-produced archive must be
   byte-identical to one built from scratch."""
   incremental_out = tmp_path / "inc"
   scratch_out = tmp_path / "scratch"

   resolved = resolve(repo, incremental_out)
   build(resolved)

   target = repo / "src" / "time" / "tick" / "tick.cpp"
   target.write_text(target.read_text().replace("return 0u;", "return 7u;"))
   build(resolved)                                  # incremental

   scratch = resolve(repo, scratch_out)
   build(scratch)                                   # from nothing

   a = next(a for a in plan_build(resolved) if isinstance(a, ArchiveAction)).output
   b = next(a for a in plan_build(scratch) if isinstance(a, ArchiveAction)).output
   assert a.read_bytes() == b.read_bytes(), "incremental archive differs from a clean one"


# ---------------------------------------------------------------------------
# Idempotent include tree
# ---------------------------------------------------------------------------

def test_include_tree_is_idempotent(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   populate_include_tree(resolved)

   header = next(p for p in (tmp_path / "out").rglob("kernel.hpp"))
   # Must be ctime, not mtime: shutil.copy2 copies mtime from the source, so a
   # rewrite leaves mtime identical and an mtime-based assert here is vacuous.
   # Mutation testing caught exactly that — deleting the write-if-different
   # guard left this test passing. ctime is set by the OS on write.
   before = (header.read_bytes(), header.stat().st_ctime_ns)

   populate_include_tree(resolved)
   assert (header.read_bytes(), header.stat().st_ctime_ns) == before, (
      "an unchanged header was rewritten"
   )


def test_include_tree_updates_changed_headers(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   populate_include_tree(resolved)

   source = repo / "src" / "kernel" / "include" / "mini" / "kernel.hpp"
   source.write_text(source.read_text() + "\n// changed\n")
   populate_include_tree(resolved)

   copied = next(p for p in (tmp_path / "out").rglob("kernel.hpp"))
   assert "// changed" in copied.read_text()


def test_include_tree_removes_dropped_headers(repo, tmp_path):
   """A header removed from public_headers must stop being visible, or sources
   keep including something the build no longer declares."""
   resolved = resolve(repo, tmp_path / "out")
   populate_include_tree(resolved)
   assert list((tmp_path / "out").rglob("port.hpp"))

   component = repo / "src" / "port" / "component.toml"
   component.write_text(
      component.read_text().replace('   "include/mini/port.hpp -> mini/port.hpp",\n', "")
   )

   resolved2 = resolve(repo, tmp_path / "out")
   populate_include_tree(resolved2)
   assert not list((tmp_path / "out").rglob("port.hpp")), "dropped header still present"


def test_include_tree_prunes_emptied_directories(repo, tmp_path):
   resolved = resolve(repo, tmp_path / "out")
   populate_include_tree(resolved)

   stray_dir = next(p for p in (tmp_path / "out").rglob("mini") if p.is_dir())
   stray = stray_dir / "leftover.hpp"
   stray.write_text("// not in the export set\n")
   orphan = stray_dir / "orphan"
   orphan.mkdir()
   (orphan / "junk.hpp").write_text("// junk\n")

   populate_include_tree(resolved)
   assert not stray.exists(), "unlisted file survived"
   assert not orphan.exists(), "emptied directory survived"
