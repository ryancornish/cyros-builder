"""
test_runner.py — orchestrate build, compile, link, and execution for all
discovered unit tests, then print a summary.

Each test gets a fully isolated output directory so differing config headers
never pollute each other's archives. The flow per test is:

   1. Construct a per-test ResolvedInvocation (same profile/toolchain, but
      config_header and output_root overridden for this test).
   2. Populate the include tree for that config.
   3. Run plan_build → execute_actions  to produce libcortos.a.
   4. Run plan_test  → execute compile + link actions.
   5. Execute the RunTestAction, capture result.

Results are collected and printed as a summary table at the end.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from cortos_builder.actions import CompileTestAction, LinkTestAction, RunTestAction
from cortos_builder.executor import execute_actions
from cortos_builder.include_tree import populate_include_tree
from cortos_builder.output import lib_dir
from cortos_builder.planner import plan_build
from cortos_builder.resolve import ResolvedInvocation
from cortos_builder.test_model import TestCase
from cortos_builder.test_planner import plan_test, test_build_root, test_output_root
from cortos_builder.ui import format_command


@dataclass
class TestResult:
   name: str
   passed: bool
   skipped: bool = False
   skip_reason: str = ""
   duration_s: float = 0.0
   error_message: str = ""


def run_all_tests(
   *,
   resolved: ResolvedInvocation,
   tests: list[TestCase],
   verbose: bool = False,
   filter_str: str | None = None,
) -> list[TestResult]:
   """
   Build and run all (filtered) test cases.
   Returns one TestResult per test; never raises — failures are captured.
   """
   selected = _apply_filter(tests, filter_str)

   if not selected:
      print("No tests matched the filter." if filter_str else "No tests found.")
      return []

   print(f"Running {len(selected)} test(s)...\n")

   results: list[TestResult] = []
   for test in selected:
      result = _run_one(resolved=resolved, test=test, verbose=verbose)
      results.append(result)
      _print_inline_result(result)

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


def _run_one(
   *,
   resolved: ResolvedInvocation,
   test: TestCase,
   verbose: bool,
) -> TestResult:
   start = time.monotonic()
   name = test.name

   # Build a per-test resolved invocation: same profile/toolchain, but
   # override config_header and output_root for this test's isolation.
   test_resolved = _make_test_resolved(resolved, test)

   # 1. Build the cortos archive.
   try:
      _build_archive(resolved=test_resolved, verbose=verbose)
   except Exception as exc:
      return TestResult(
         name=name,
         passed=False,
         duration_s=time.monotonic() - start,
         error_message=f"Archive build failed: {exc}",
      )

   # 2. Compile + link the test binary.
   test_actions = plan_test(resolved=test_resolved, test=test)
   build_actions = [a for a in test_actions if not isinstance(a, RunTestAction)]

   try:
      execute_actions(build_actions, verbose=verbose)
   except Exception as exc:
      return TestResult(
         name=name,
         passed=False,
         duration_s=time.monotonic() - start,
         error_message=f"Test compile/link failed: {exc}",
      )

   # 3. Run the test binary.
   run_action = next(a for a in test_actions if isinstance(a, RunTestAction))
   passed, error_message = _execute_test(run_action, verbose=verbose)

   return TestResult(
      name=name,
      passed=passed,
      duration_s=time.monotonic() - start,
      error_message=error_message,
   )


def _make_test_resolved(base: ResolvedInvocation, test: TestCase) -> ResolvedInvocation:
   """
   Return a copy of the resolved invocation with config_header and output_root
   overridden for this specific test case.
   """
   from cortos_builder.resolve import ResolvedInvocation as RI
   return RI(
      profile_root=base.profile_root,
      profile=base.profile,
      toolchain=base.toolchain,
      selected_toolchain_name=base.selected_toolchain_name,
      cli_overrode_toolchain=base.cli_overrode_toolchain,
      config_header=test.config,
      cli_overrode_config=True,
      output_root=test_output_root(base, test),
      cli_overrode_output=True,
   )


def _build_archive(*, resolved: ResolvedInvocation, verbose: bool) -> None:
   populate_include_tree(resolved)
   actions = plan_build(resolved)
   execute_actions(actions, verbose=verbose)


def _execute_test(action: RunTestAction, *, verbose: bool) -> tuple[bool, str]:
   """
   Run the test binary. Returns (passed, error_message).
   This is intentionally kept as a thin wrapper around subprocess so that
   a future coverage pass can intercept or augment it cleanly.
   """
   binary = action.binary.resolve()
   cwd = action.working_directory

   if verbose:
      print(f"$ {binary}")

   try:
      result = subprocess.run(
         [str(binary)],
         cwd=str(cwd),
         capture_output=False,   # let gtest output flow to the terminal
      )
      if result.returncode == 0:
         return True, ""
      return False, f"exited with code {result.returncode}"
   except Exception as exc:
      return False, f"failed to launch: {exc}"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"


def _print_inline_result(result: TestResult) -> None:
   status = _SKIP if result.skipped else (_PASS if result.passed else _FAIL)
   duration = f"{result.duration_s:.2f}s"
   print(f"  [{status}] {result.name:<50} {duration}")
   if not result.passed and not result.skipped and result.error_message:
      print(f"         {result.error_message}")


def _print_summary(results: list[TestResult]) -> None:
   total   = len(results)
   passed  = sum(1 for r in results if r.passed)
   failed  = sum(1 for r in results if not r.passed and not r.skipped)
   skipped = sum(1 for r in results if r.skipped)

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