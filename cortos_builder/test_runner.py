"""
test_runner.py — orchestrate build, compile, link, and execution for all
discovered unit tests, then print a summary.

Each test gets a fully isolated output directory so differing config headers
never pollute each other's archives. The flow is two-phase:

  Phase 1 — Build all tests:
    For each test:
      a. Construct a per-test ResolvedInvocation (same profile/toolchain, but
         config_header and output_root overridden for this test).
      b. Populate the include tree for that config.
      c. plan_build → execute_actions  to produce libcortos.a.
      d. plan_test  → execute compile + link actions to produce the binary.

  Phase 2 — Run all tests:
    Execute each binary sequentially, capture results, print summary.

Separating the phases means all compilation noise is out of the way before
any test output appears, making failures easier to read.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from cortos_builder.actions import RunTestAction
from cortos_builder.executor import execute_actions
from cortos_builder.include_tree import populate_include_tree
from cortos_builder.planner import plan_build
from cortos_builder.resolve import ResolvedInvocation
from cortos_builder.test_model import TestCase
from cortos_builder.test_planner import plan_test, test_output_root


@dataclass
class TestResult:
   name: str
   passed: bool
   skipped: bool = False
   skip_reason: str = ""
   build_duration_s: float = 0.0
   run_duration_s: float = 0.0
   error_message: str = ""


def run_all_tests(
   *,
   resolved: ResolvedInvocation,
   tests: list[TestCase],
   verbose: bool = False,
   filter_str: str | None = None,
) -> list[TestResult]:
   """
   Build all tests, then run all tests.
   Returns one TestResult per test; never raises — failures are captured.
   """
   selected = _apply_filter(tests, filter_str)

   if not selected:
      print("No tests matched the filter." if filter_str else "No tests found.")
      return []

   # --- Phase 1: build ---
   print(f"Building {len(selected)} test(s)...\n")

   build_results: dict[str, tuple[bool, str, float, RunTestAction | None]] = {}
   for test in selected:
      passed, error, duration, run_action = _build_one(
         resolved=resolved, test=test, verbose=verbose,
      )
      build_results[test.name] = (passed, error, duration, run_action)
      status = "ok" if passed else "FAILED"
      print(f"  [{status}] {test.name}")
      if not passed:
         print(f"         {error}")

   # --- Phase 2: run ---
   build_failures = [name for name, (ok, _, _, _) in build_results.items() if not ok]
   if build_failures:
      print(f"\n{len(build_failures)} test(s) failed to build — skipping run phase.")
      return [
         TestResult(
            name=test.name,
            passed=build_results[test.name][0],
            build_duration_s=build_results[test.name][2],
            error_message=build_results[test.name][1],
         )
         for test in selected
      ]

   print(f"\nRunning {len(selected)} test(s)...\n")

   results: list[TestResult] = []
   for test in selected:
      passed, error, build_dur, run_action = build_results[test.name]

      if not passed:
         results.append(TestResult(
            name=test.name,
            passed=False,
            build_duration_s=build_dur,
            error_message=error,
         ))
         continue

      print(f"  {test.name}")
      # passed implies the build succeeded, which guarantees run_action is set.
      assert run_action is not None
      run_passed, run_error, run_dur = _run_one(run_action, verbose=verbose)
      results.append(TestResult(
         name=test.name,
         passed=run_passed,
         build_duration_s=build_dur,
         run_duration_s=run_dur,
         error_message=run_error,
      ))

   print()
   _print_summary(results)
   return results


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _apply_filter(tests: list[TestCase], filter_str: str | None) -> list[TestCase]:
   if not filter_str:
      return tests
   return [t for t in tests if filter_str in t.name]


def _build_one(
   *,
   resolved: ResolvedInvocation,
   test: TestCase,
   verbose: bool,
) -> tuple[bool, str, float, RunTestAction | None]:
   """
   Build the cortos archive and compile+link the test binary.
   Returns (success, error_message, duration_s, run_action | None).
   """
   start = time.monotonic()
   test_resolved = _make_test_resolved(resolved, test)

   try:
      populate_include_tree(test_resolved)
      execute_actions(plan_build(test_resolved), verbose=verbose)
   except Exception as exc:
      return False, f"Archive build failed: {exc}", time.monotonic() - start, None

   test_actions = plan_test(resolved=test_resolved, test=test)
   build_actions = [a for a in test_actions if not isinstance(a, RunTestAction)]
   run_action = next(a for a in test_actions if isinstance(a, RunTestAction))

   try:
      execute_actions(build_actions, verbose=verbose)
   except Exception as exc:
      return False, f"Compile/link failed: {exc}", time.monotonic() - start, None

   return True, "", time.monotonic() - start, run_action


def _run_one(
   action: RunTestAction,
   *,
   verbose: bool,
) -> tuple[bool, str, float]:
   """
   Execute a test binary. Returns (passed, error_message, duration_s).
   Kept as a thin wrapper so a future coverage pass can intercept cleanly.
   """
   binary = action.binary.resolve()
   start = time.monotonic()

   if verbose:
      print(f"  $ {binary}")

   try:
      result = subprocess.run(
         [str(binary)],
         cwd=str(action.working_directory),
         capture_output=False,   # let gtest output flow to the terminal
      )
      duration = time.monotonic() - start
      if result.returncode == 0:
         return True, "", duration
      return False, f"exited with code {result.returncode}", duration
   except Exception as exc:
      return False, f"failed to launch: {exc}", time.monotonic() - start


def _make_test_resolved(base: ResolvedInvocation, test: TestCase) -> ResolvedInvocation:
   """
   Build a per-test ResolvedInvocation.

   The config header and output root are always overridden per-test. The
   time driver is resolved with this precedence:
     1. test.toml [components].time_driver, if set
     2. the profile's components.time_driver, if set
     3. None — no time driver compiled in (fine for kernel/port tests)

   If the test.toml overrides the time driver, the profile is rebuilt with
   an updated ComponentsConfig so select_project() picks it up.
   """
   import dataclasses

   profile = base.profile
   if test.time_driver is not None:
      new_components = dataclasses.replace(
         profile.components, time_driver=test.time_driver
      )
      profile = dataclasses.replace(profile, components=new_components)

   return ResolvedInvocation(
      profile_root=base.profile_root,
      profile=profile,
      toolchain=base.toolchain,
      selected_toolchain_name=base.selected_toolchain_name,
      cli_overrode_toolchain=base.cli_overrode_toolchain,
      config_header=test.config,
      cli_overrode_config=True,
      output_root=test_output_root(base, test),
      cli_overrode_output=True,
   )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_summary(results: list[TestResult]) -> None:
   total   = len(results)
   passed  = sum(1 for r in results if r.passed)
   failed  = sum(1 for r in results if not r.passed and not r.skipped)
   skipped = sum(1 for r in results if r.skipped)

   name_w = max((len(r.name) for r in results), default=0)

   print("─" * 60)
   for r in results:
      if r.skipped:
         status = "SKIP"
      elif r.passed:
         status = "PASS"
      else:
         status = "FAIL"
      duration = f"{r.run_duration_s:.2f}s"
      print(f"  [{status}] {r.name:<{name_w}}  {duration}")
      if not r.passed and not r.skipped and r.error_message:
         print(f"         {r.error_message}")

   print("─" * 60)
   print(f"Results: {passed}/{total} passed", end="")
   if skipped:
      print(f", {skipped} skipped", end="")
   if failed:
      print(f", {failed} FAILED", end="")
   print()

   if failed:
      print("\nFailed tests:")
      for r in results:
         if not r.passed and not r.skipped:
            print(f"  • {r.name}")
            if r.error_message:
               print(f"    {r.error_message}")