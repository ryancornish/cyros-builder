"""Tests for the T1 layered test model and runner.

The layering exists to make a failure attributable: if every layer below N
passes and a test at N fails, the defect is in that test's subject. These tests
pin the three mechanisms that deliver it, which are the blocking rule, the run
order, and the reporting of tests that never ran.

The runner is exercised with `_build_one` and `_run_one` stubbed out. What is
under test is the scheduling and reporting logic, not the compiler.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import FIXTURE_ROOT

from cyros_builder import test_runner
# TestCase aliased: pytest tries to collect any imported name starting with Test.
from cyros_builder.test_model import HarnessDebt, load_test_case
from cyros_builder.test_model import TestCase as _Case
from cyros_builder.test_runner import _blocking_layer, run_all_tests


def make_case(name: str, layer: int, *, kind: str = "unit", debt: HarnessDebt | None = None) -> _Case:
   return _Case(
      path=Path("/nowhere"), name=name, sources=(Path("/nowhere/x.cpp"),),
      config=Path("/nowhere/c.hpp"), system_libraries=(), extra_link_flags=(),
      port_filter=(), time_driver=None, features=(),
      layer=layer, kind=kind, harness_debt=debt,
   )


# ---------------------------------------------------------------------------
# The blocking rule
# ---------------------------------------------------------------------------

def test_a_test_is_blocked_by_any_failed_layer_below_it():
   assert _blocking_layer(make_case("t", 5), {2}) == 2


def test_the_lowest_failed_layer_is_the_one_reported():
   """The first cause, not the nearest one. Everything between is already noise."""
   assert _blocking_layer(make_case("t", 8), {6, 2, 4}) == 2


def test_a_failure_above_does_not_block():
   assert _blocking_layer(make_case("t", 3), {5}) is None


def test_a_sibling_at_the_same_layer_does_not_block():
   """Tests sharing a layer prove different subjects, so one failing says
   nothing about another. Without this rule a single L1 failure would block
   every other L1 test and hide independent defects."""
   assert _blocking_layer(make_case("t", 4), {4}) is None


def test_harness_debt_makes_a_higher_layer_blocking():
   """The payoff of naming the harness floor: a bring-up failure must void the
   spinlock verdict even though spinlock sits BELOW bring-up, because spinlock's
   contract cannot be observed without cores running."""
   spinlock = make_case("test_spinlock", 1, debt=HarnessDebt(layer=2, reason="needs cores"))
   assert _blocking_layer(spinlock, {2}) == 2
   # ... and without the debt the same failure would not block it at all.
   assert _blocking_layer(make_case("test_spinlock", 1), {2}) is None


def test_debt_does_not_block_on_the_tests_own_layer():
   spinlock = make_case("test_spinlock", 1, debt=HarnessDebt(layer=2, reason="needs cores"))
   assert _blocking_layer(spinlock, {1}) is None


# ---------------------------------------------------------------------------
# Run order
# ---------------------------------------------------------------------------

def test_run_rank_is_the_layer_unless_there_is_debt():
   assert make_case("a", 3).run_rank == 3
   assert make_case("a", 1, debt=HarnessDebt(layer=2, reason="r")).run_rank == 2


# ---------------------------------------------------------------------------
# The runner, with the compiler stubbed out
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_runner(monkeypatch):
   """Drive run_all_tests without compiling. `outcomes` maps a test name to
   "pass", "fail" or "buildfail"."""
   def install(outcomes: dict[str, str]):
      def fake_build(*, resolved, test, verbose, jobs=1, force=False):
         if outcomes.get(test.name) == "buildfail":
            return False, "compile error", 0.1, None
         return True, "", 0.1, object()

      def fake_run(action, *, verbose, timeout=0.0):
         return True, "", 0.01, Path("/nowhere/x.log")

      ran: list[str] = []

      def tracking_run(action, *, verbose, timeout=0.0):
         name = getattr(action, "_name", "?")
         ran.append(name)
         if outcomes.get(name) == "fail":
            return False, "exited with code 1", 0.01, Path("/nowhere/x.log")
         return True, "", 0.01, Path("/nowhere/x.log")

      def naming_build(*, resolved, test, verbose, jobs=1, force=False):
         ok, err, dur, _ = fake_build(resolved=resolved, test=test, verbose=verbose)
         if not ok:
            return ok, err, dur, None
         action = type("A", (), {})()
         action._name = test.name
         return True, "", dur, action

      monkeypatch.setattr(test_runner, "_build_one", naming_build)
      monkeypatch.setattr(test_runner, "_run_one", tracking_run)
      return ran
   return install


class _Resolved:
   """Only the fields the runner reads off the resolved invocation."""
   class profile:
      class components:
         port = "porta"

   class toolchain:
      class settings:
         # These layering tests are all about ordering and blocking, so they
         # model a host toolchain and every case is hosted. The freestanding
         # path is covered in test_runner_command.py.
         hosted = True


def test_a_failure_blocks_higher_layers_and_they_are_not_run(stub_runner):
   cases = [make_case("low", 1), make_case("mid", 2), make_case("high", 3)]
   ran = stub_runner({"mid": "fail"})

   results = run_all_tests(resolved=_Resolved(), tests=cases)
   by_name = {r.name: r for r in results}

   assert by_name["low"].passed
   assert not by_name["mid"].passed and by_name["mid"].ran
   assert by_name["high"].blocked
   assert "layer 2" in by_name["high"].blocked_by
   assert "high" not in ran, "a blocked test must not be executed"


def test_keep_going_runs_the_blocked_layers_anyway(stub_runner):
   cases = [make_case("mid", 2), make_case("high", 3)]
   ran = stub_runner({"mid": "fail"})

   results = run_all_tests(resolved=_Resolved(), tests=cases, keep_going=True)
   assert "high" in ran
   assert not any(r.blocked for r in results)


def test_tests_run_lowest_layer_first(stub_runner):
   cases = [make_case("c", 7), make_case("a", 1), make_case("b", 4)]
   ran = stub_runner({})
   run_all_tests(resolved=_Resolved(), tests=cases)
   assert ran == ["a", "b", "c"]


def test_a_debted_test_runs_after_the_layer_it_borrows_from(stub_runner):
   """spinlock is layer 1 but cannot run until layer 2 has started the cores."""
   cases = [
      make_case("spinlock", 1, debt=HarnessDebt(layer=2, reason="needs cores")),
      make_case("bringup", 2),
   ]
   ran = stub_runner({})
   run_all_tests(resolved=_Resolved(), tests=cases)
   assert ran == ["bringup", "spinlock"]


def test_a_test_that_did_not_build_is_never_reported_as_passed(stub_runner):
   """The regression that motivated the rewrite.

   The old runner abandoned the run phase as soon as any test failed to build,
   then reported every test that HAD built as passing at 0.00s. One broken file
   turned the rest of the suite into a false green: a real run of four tests
   with one compile error printed "Results: 3/4 passed" with three tests that
   never executed."""
   cases = [make_case("broken", 1), make_case("innocent", 1)]
   ran = stub_runner({"broken": "buildfail"})

   results = run_all_tests(resolved=_Resolved(), tests=cases)
   by_name = {r.name: r for r in results}

   assert by_name["broken"].build_failed
   assert not by_name["broken"].passed
   assert not by_name["broken"].ran
   # The innocent test is at the SAME layer, so it is not blocked, and it must
   # actually run rather than inherit a verdict.
   assert "innocent" in ran
   assert by_name["innocent"].passed


def test_a_build_failure_blocks_the_layers_above_it(stub_runner):
   cases = [make_case("broken", 1), make_case("above", 2)]
   ran = stub_runner({"broken": "buildfail"})

   results = run_all_tests(resolved=_Resolved(), tests=cases)
   by_name = {r.name: r for r in results}
   assert by_name["above"].blocked
   assert "above" not in ran


def test_soaks_and_measurements_are_skipped_unless_asked_for(stub_runner):
   cases = [
      make_case("u", 1),
      make_case("s", 1, kind="soak"),
      make_case("m", 1, kind="measurement"),
      make_case("i", 1, kind="integration"),
   ]
   ran = stub_runner({})
   run_all_tests(resolved=_Resolved(), tests=cases)
   assert sorted(ran) == ["i", "u"]

   ran2 = stub_runner({})
   run_all_tests(resolved=_Resolved(), tests=cases, kinds=("soak",))
   assert ran2 == ["s"]


# ---------------------------------------------------------------------------
# Declaration, which is enforcement tier 1
# ---------------------------------------------------------------------------

MINI = FIXTURE_ROOT / "tests" / "unit" / "mini_case" / "test.toml"


@pytest.fixture
def mini_copy(tmp_path):
   """A writable copy of the fixture case, so a malformed test.toml is rejected
   for the reason under test rather than for a missing source file."""
   import shutil
   dest = tmp_path / "mini_case"
   shutil.copytree(MINI.parent, dest)
   # The config lives outside the case directory, so point at the real one.
   def write(text: str) -> Path:
      (dest / "test.toml").write_text(
         text.replace('config = "../../../build/configs/mini.hpp"',
                      f'config = "{MINI.parent.parent.parent.parent / "build" / "configs" / "mini.hpp"}"')
      )
      return dest / "test.toml"
   write.original = MINI.read_text()
   return write


def test_the_fixture_declares_a_layer():
   assert load_test_case(MINI).layer == 1


def test_a_test_without_a_layer_is_an_error(mini_copy):
   """A new test cannot quietly opt out of the chain."""
   path = mini_copy(mini_copy.original.replace("layer  = 1\n", ""))
   with pytest.raises(ValueError, match="'test.layer' is required"):
      load_test_case(path)


@pytest.mark.parametrize("bad", ["-1", '"two"', "true"])
def test_a_layer_must_be_a_non_negative_integer(mini_copy, bad):
   path = mini_copy(mini_copy.original.replace("layer  = 1", f"layer  = {bad}"))
   with pytest.raises(ValueError, match="non-negative integer"):
      load_test_case(path)


def test_an_unknown_kind_is_an_error(mini_copy):
   path = mini_copy(mini_copy.original.replace("layer  = 1", 'layer  = 1\nkind = "smoke"'))
   with pytest.raises(ValueError, match="test.kind"):
      load_test_case(path)


def test_harness_debt_must_name_a_reason(mini_copy):
   """An undeclared debt is a false attribution claim, and a declared one is a
   known cost. The reason is the whole difference, so an empty one is rejected."""
   path = mini_copy(mini_copy.original.replace(
      "layer  = 1", 'layer  = 1\nharness_debt = { layer = 3, reason = "" }'))
   with pytest.raises(ValueError, match="reason"):
      load_test_case(path)


def test_harness_debt_must_point_upward(mini_copy):
   """Depending on a LOWER layer is ordinary and needs no declaration. Only
   borrowing from above is a debt."""
   path = mini_copy(mini_copy.original.replace(
      "layer  = 1", 'layer  = 4\nharness_debt = { layer = 2, reason = "backwards" }'))
   with pytest.raises(ValueError, match="must be ABOVE"):
      load_test_case(path)


def test_the_upper_fixture_declares_its_debt():
   upper = load_test_case(FIXTURE_ROOT / "tests" / "unit" / "mini_upper" / "test.toml")
   assert upper.layer == 3
   assert upper.harness_debt is not None
   assert upper.run_rank == 4
   assert upper.kind == "integration"


# ---------------------------------------------------------------------------
# Enforcement tier 2: the static upward-trust check
# ---------------------------------------------------------------------------

from cyros_builder.test_model import (          # noqa: E402
   LayerPolicy, load_layer_policy, validate_layering,
)

UNIT_ROOT = FIXTURE_ROOT / "tests" / "unit"


def policy(**overrides) -> LayerPolicy:
   base = dict(
      headers={"mini/kernel.hpp": 1, "mini/upper.hpp": 5},
      ungraded=frozenset({"mini/config.hpp"}),
      path=Path("layers.toml"),
      prefix="mini/",
   )
   base.update(overrides)
   return LayerPolicy(**base)


def case_including(tmp_path, includes: list[str], layer: int, debt: HarnessDebt | None = None) -> _Case:
   source = tmp_path / "t.cpp"
   source.write_text("".join(f'#include <{i}>\n' for i in includes) + "int main(){}\n")
   c = make_case("t", layer, debt=debt)
   return _Case(**{**c.__dict__, "sources": (source,)})


def test_a_test_may_include_its_own_subjects_header(tmp_path):
   """The comparison is strictly greater, not greater-or-equal: a test at layer
   N obviously includes the header of the unit it is proving."""
   validate_layering([case_including(tmp_path, ["mini/kernel.hpp"], 1)], policy())


def test_a_test_may_include_anything_below_it(tmp_path):
   validate_layering([case_including(tmp_path, ["mini/kernel.hpp"], 4)], policy())


def test_reaching_upward_is_refused(tmp_path):
   with pytest.raises(ValueError, match="belongs to layer 5"):
      validate_layering([case_including(tmp_path, ["mini/upper.hpp"], 2)], policy())


def test_the_message_names_both_sides_and_the_way_out(tmp_path):
   """A1's header-visibility error set the shape: say what reached, what it
   reached for, and what to do."""
   with pytest.raises(ValueError) as exc:
      validate_layering([case_including(tmp_path, ["mini/upper.hpp"], 2)], policy())
   text = str(exc.value)
   assert "is at layer 2" in text
   assert "mini/upper.hpp" in text
   assert "harness debt" in text


def test_a_declared_harness_debt_raises_the_ceiling(tmp_path):
   """This is exactly test_spinlock: layer 1, but allowed to reach the harness
   it cannot observe its own contract without."""
   debt = HarnessDebt(layer=5, reason="cannot observe the contract without it")
   validate_layering([case_including(tmp_path, ["mini/upper.hpp"], 1, debt)], policy())


def test_debt_only_raises_the_ceiling_as_far_as_declared(tmp_path):
   debt = HarnessDebt(layer=3, reason="needs the layer 3 harness")
   with pytest.raises(ValueError, match="ceiling raised to 3"):
      validate_layering([case_including(tmp_path, ["mini/upper.hpp"], 1, debt)], policy())


def test_an_ungraded_header_is_legal_at_every_layer(tmp_path):
   validate_layering([case_including(tmp_path, ["mini/config.hpp"], 0)], policy())


def test_includes_outside_the_prefix_are_not_graded(tmp_path):
   """gtest, the standard library and the tests' own helpers carry no layer."""
   validate_layering([case_including(tmp_path, ["gtest/gtest.h", "vector"], 0)], policy())


def test_an_ungraded_project_header_is_an_error_not_a_silent_pass(tmp_path):
   """Otherwise a new header escapes the check forever, which is how a rule
   quietly stops being enforced."""
   with pytest.raises(ValueError, match="does not grade"):
      validate_layering([case_including(tmp_path, ["mini/mystery.hpp"], 3)], policy())


def test_a_header_cannot_be_both_graded_and_ungraded(tmp_path):
   path = tmp_path / "layers.toml"
   path.write_text('[headers]\n"a/b.hpp" = 1\n\n[ungraded]\nheaders = ["a/b.hpp"]\n')
   (tmp_path / "x").mkdir()
   with pytest.raises(ValueError, match="both"):
      load_layer_policy(tmp_path)


def test_the_check_is_off_when_a_project_has_no_policy(tmp_path):
   """A project that has not adopted the layering still builds."""
   assert load_layer_policy(tmp_path) is None


def test_the_fixture_policy_loads():
   loaded = load_layer_policy(UNIT_ROOT)
   assert loaded is not None
   assert loaded.prefix == "mini/"
   assert loaded.headers["mini/kernel.hpp"] == 1
