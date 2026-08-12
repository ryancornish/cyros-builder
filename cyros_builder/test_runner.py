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

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from cyros_builder.actions import RunTestAction
from cyros_builder.executor import execute_actions
from cyros_builder.include_tree import populate_include_tree
from cyros_builder.planner import plan_build
from cyros_builder.resolve import ResolvedInvocation
from cyros_builder.test_model import TestCase
from cyros_builder.staleness import prune_actions, record_state
from cyros_builder.test_planner import make_test_resolved, plan_test


@dataclass
class TestResult:
   name: str
   passed: bool
   skipped: bool = False
   skip_reason: str = ""
   build_duration_s: float = 0.0
   run_duration_s: float = 0.0
   error_message: str = ""
   log_path: Path | None = None


def run_all_tests(
   *,
   resolved: ResolvedInvocation,
   tests: list[TestCase],
   verbose: bool = False,
   filter_str: str | None = None,
   jobs: int = 1,
   force: bool = False,
   timeout: float = 0.0,
) -> list[TestResult]:
   """
   Build all tests, then run all tests.
   Returns one TestResult per test; never raises — failures are captured.
   """
   selected = _apply_filter(tests, filter_str)

   if not selected:
      print("No tests matched the filter." if filter_str else "No tests found.")
      return []

   # Partition into runnable vs skipped based on per-test requirements.
   active_port = resolved.profile.components.port
   runnable: list[TestCase] = []
   skipped_results: list[TestResult] = []
   for test in selected:
      skip_reason = _skip_reason(test, active_port=active_port)
      if skip_reason is not None:
         skipped_results.append(TestResult(
            name=test.name, passed=True, skipped=True, skip_reason=skip_reason,
         ))
      else:
         runnable.append(test)

   # --- Phase 1: build ---
   print(f"Building {len(runnable)} test(s)...\n")

   for r in skipped_results:
      print(f"  [skip] {r.name} ({r.skip_reason})")

   build_results: dict[str, tuple[bool, str, float, RunTestAction | None]] = {}
   for test in runnable:
      passed, error, duration, run_action = _build_one(
         resolved=resolved, test=test, verbose=verbose, jobs=jobs, force=force,
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
      results = skipped_results + [
         TestResult(
            name=test.name,
            passed=build_results[test.name][0],
            build_duration_s=build_results[test.name][2],
            error_message=build_results[test.name][1],
         )
         for test in runnable
      ]
      _print_summary(results)
      return results

   print(f"\nRunning {len(runnable)} test(s)...\n")

   results = list(skipped_results)
   for test in runnable:
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
      run_passed, run_error, run_dur, run_log = _run_one(run_action, verbose=verbose, timeout=timeout)
      results.append(TestResult(
         name=test.name,
         passed=run_passed,
         build_duration_s=build_dur,
         run_duration_s=run_dur,
         error_message=run_error,
         log_path=run_log,
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


def _skip_reason(test: TestCase, *, active_port: str) -> str | None:
   """
   Return a human-readable reason to skip this test, or None to run it.

   Port is a filter (Design A): the test always builds against the profile's
   port. If the test declares a port filter and the active profile port is not
   among the allowed set, the test is skipped — it is locked to a port the
   current profile does not provide.
   """
   if test.port_filter and active_port not in test.port_filter:
      want = ", ".join(test.port_filter)
      return f"locked to port {want}, active port is {active_port}"
   return None


def _build_one(
   *,
   resolved: ResolvedInvocation,
   test: TestCase,
   verbose: bool,
   jobs: int = 1,
   force: bool = False,
) -> tuple[bool, str, float, RunTestAction | None]:
   """
   Build the cortos archive and compile+link the test binary.
   Returns (success, error_message, duration_s, run_action | None).
   """
   start = time.monotonic()
   test_resolved = make_test_resolved(resolved, test)

   # This used to unconditionally rmtree the test's output root, which defeated
   # cross-run reuse by construction. It is safe to drop now that staleness is
   # tracked: the old wipe existed because the output path does not encode the
   # component configuration (features/time_driver), so a changed test.toml
   # could otherwise reuse objects built for a different configuration. Content
   # hashing plus the argv hash covers exactly that — a changed configuration
   # changes the source set and the command lines, so affected objects rebuild,
   # the archive's member set changes so it re-archives, and any object left
   # over from the old configuration is simply never referenced again. `--force`
   # rebuilds without deleting; `clean` deletes.
   try:
      populate_include_tree(test_resolved)
   except Exception as exc:
      return False, f"Failed to populate include tree: {exc}", time.monotonic() - start, None

   try:
      archive_actions = plan_build(test_resolved)
      test_actions = plan_test(resolved=test_resolved, test=test)
   except Exception as exc:
      return False, f"Planning failed: {exc}", time.monotonic() - start, None

   build_actions = [a for a in test_actions if not isinstance(a, RunTestAction)]
   run_action = next(a for a in test_actions if isinstance(a, RunTestAction))

   # Two prune/execute rounds, in this order and not merged: the link consumes
   # the archive, so its staleness can only be judged once the archive on disk
   # is current. Pruning both up front would compare the link against the
   # previous archive and could wrongly skip it.
   try:
      pruned_archive = prune_actions(test_resolved, archive_actions, force=force)
      execute_actions(pruned_archive.actions, verbose=verbose, jobs=jobs)
   except Exception as exc:
      return False, f"Archive build failed: {exc}", time.monotonic() - start, None

   try:
      pruned_test = prune_actions(test_resolved, build_actions, force=force)
      execute_actions(pruned_test.actions, verbose=verbose, jobs=jobs)
   except Exception as exc:
      return False, f"Compile/link failed: {exc}", time.monotonic() - start, None

   # One state file per build root, so it must be written from the combined
   # plan. Recording each round separately would drop the other's entries.
   try:
      record_state(
         test_resolved,
         archive_actions + build_actions,
         pruned_archive.actions + pruned_test.actions,
      )
   except Exception as exc:
      return False, f"Failed to record build state: {exc}", time.monotonic() - start, None

   return True, "", time.monotonic() - start, run_action


def _launch_prefix() -> list[str]:
   """
   Run the test unbuffered when stdbuf is available.

   Load-bearing, not a tidiness measure. Test output goes to a log file below,
   and a file makes libc block-buffer stdout, and abort() does not flush. So a
   KERNEL PANIC raised by a failing assertion is written into a buffer that is
   then discarded, and the failure that most wants a diagnostic is the one that
   arrives with none. That trap is recorded in CLAUDE_cyros.md section 0 and
   this is the same workaround it prescribes.
   """
   stdbuf = shutil.which("stdbuf")
   return [stdbuf, "-o0", "-e0"] if stdbuf else []


def _log_tail(path: Path, lines: int = 40) -> str:
   try:
      captured = path.read_text(errors="replace").splitlines()
   except OSError:
      return ""
   return "\n".join(captured[-lines:])


def _run_one(
   action: RunTestAction,
   *,
   verbose: bool,
   timeout: float = 0.0,
) -> tuple[bool, str, float, Path]:
   """
   Execute a test binary. Returns (passed, error_message, duration_s, log_path).
   Kept as a thin wrapper so a future coverage pass can intercept cleanly.

   Output goes to <binary>.log rather than the terminal, and the tail is
   replayed on failure. A run that fails once in a few hundred is the only kind
   worth investigating here, and streaming loses it: anything that pipes this
   command keeps the summary and drops the gtest assertion or panic that says
   what actually happened. The log is per test and overwritten each run, so it
   is always the most recent attempt.
   """
   binary = action.binary.resolve()
   log_path = binary.with_name(binary.name + ".log")
   start = time.monotonic()

   if verbose:
      print(f"  $ {binary}")

   try:
      with log_path.open("w") as log:
         result = subprocess.run(
            [*_launch_prefix(), str(binary)],
            cwd=str(action.working_directory),
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout if timeout > 0 else None,
         )
      duration = time.monotonic() - start
      if result.returncode == 0:
         if verbose:
            print(_log_tail(log_path))
         return True, "", duration, log_path
      return False, f"exited with code {result.returncode}", duration, log_path
   except subprocess.TimeoutExpired:
      # A hang, not a failure. Distinguished because the two want different
      # investigations: a deadlock or lost wakeup rather than a bad assertion.
      return False, f"timed out after {timeout:g}s", time.monotonic() - start, log_path
   except Exception as exc:
      return False, f"failed to launch: {exc}", time.monotonic() - start, log_path


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
            # The tail, not just the exit code. An intermittent that shows up
            # once in a few hundred runs is unidentifiable without it, and by
            # then the run is over.
            if r.log_path is not None:
               tail = _log_tail(r.log_path)
               if tail:
                  print(f"    output ({r.log_path}):")
                  for line in tail.splitlines():
                     print(f"      {line}")