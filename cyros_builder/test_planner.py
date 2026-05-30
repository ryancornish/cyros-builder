"""
test_planner.py — produce the action sequence for a single unit test case.

For each test the sequence is:
   1. Build cyros archive  (reuses plan_build — handled by the runner)
   2. CompileTestAction     — compile the test .cpp into a .o
   3. LinkTestAction        — link test.o + libcyros.a + system libs → binary
   4. RunTestAction         — execute the binary

The runner builds the cyros archive once per test (each test gets its own
isolated output directory because configs differ), then calls plan_test to
get steps 2-4.
"""

from __future__ import annotations

from pathlib import Path

from cyros_builder.actions import CompileTestAction, LinkTestAction, RunTestAction
from cyros_builder.output import include_dir, lib_dir
from cyros_builder.resolve import ResolvedInvocation
from cyros_builder.test_model import TestCase


def test_output_root(resolved: ResolvedInvocation, test: TestCase) -> Path:
   """
   Isolated output root for a single test case.

     <output_root>/tests/<test_name>/
   """
   return resolved.output_root / "tests" / test.name


def test_build_root(resolved: ResolvedInvocation, test: TestCase) -> Path:
   """
   The toolchain-scoped build root inside the test's output directory.
   Expects a per-test resolved invocation (output_root already set to
   <base>/tests/<test_name>/) — just appends the toolchain name, mirroring
   what output.build_root() does for normal builds.

     <output_root>/tests/<test_name>/<toolchain_name>/
   """
   return resolved.output_root / resolved.selected_toolchain_name


def plan_test(
   *,
   resolved: ResolvedInvocation,
   test: TestCase,
) -> list:
   """
   Return [CompileTestAction, LinkTestAction, RunTestAction] for one test.

   The cyros archive is assumed to already exist at the path returned by
   lib_dir() for the per-test resolved invocation — the runner is responsible
   for building it first.
   """
   tc = resolved.toolchain
   tbuild = test_build_root(resolved, test)

   obj_path  = (tbuild / "obj" / test.source.name).with_suffix(".o")
   bin_dir   = tbuild / "bin"
   binary    = bin_dir / test.name
   archive   = lib_dir(resolved) / resolved.profile.output.archive

   # --- compile ---
   compile_args: tuple[str, ...] = (
      tc.tools.cxx,
      *tc.flags.common,
      *tc.flags.cxx,
      "-I", str(include_dir(resolved).resolve()),
      "-c", str(test.source.resolve()),
      "-o", str(obj_path.resolve()),
   )

   compile_action = CompileTestAction(
      test_name=test.name,
      source=test.source,
      output=obj_path,
      arguments=compile_args,
      working_directory=tbuild,
   )

   # --- link ---
   lib_flags: tuple[str, ...] = tuple(
      f"-l{lib}" for lib in test.system_libraries
   )

   link_args: tuple[str, ...] = (
      tc.tools.cxx,
      *tc.flags.common,
      *tc.flags.link,
      *test.extra_link_flags,
      str(obj_path.resolve()),
      str(archive.resolve()),
      *lib_flags,
      "-o", str(binary.resolve()),
   )

   link_action = LinkTestAction(
      test_name=test.name,
      inputs=(obj_path, archive),
      output=binary,
      arguments=link_args,
      working_directory=bin_dir,
   )

   # --- run ---
   run_action = RunTestAction(
      test_name=test.name,
      binary=binary,
      working_directory=test.path,   # run from the test's own directory
   )

   return [compile_action, link_action, run_action]