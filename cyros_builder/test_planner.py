"""
test_planner.py — produce the action sequence for a single unit test case.

For each test the sequence is:
   1. Build cortos archive  (reuses plan_build — handled by the runner)
   2. CompileTestAction     — compile the test .cpp into a .o
   3. LinkTestAction        — link test.o + libcortos.a + system libs → binary
   4. RunTestAction         — execute the binary

The runner builds the cortos archive once per test (each test gets its own
isolated output directory because configs differ), then calls plan_test to
get steps 2-4.
"""

from __future__ import annotations

from pathlib import Path

from cyros_builder.actions import CompileTestAction, LinkTestAction, RunTestAction
from cyros_builder.output import build_root, include_dir, lib_dir
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
   The build root for a test's own object/binary, kept in lockstep with the
   cyros archive location by delegating to output.build_root(). Expects a
   per-test resolved invocation (output_root already set to
   <base>/tests/<test_name>/), so the result is:

     <output_root>/tests/<test_name>/<profile_name>/<toolchain_name>/

   Using build_root() here guarantees the test binary lives in the same tree
   as the archive it links against — they must never diverge.
   """
   return build_root(resolved)


def plan_test(
   *,
   resolved: ResolvedInvocation,
   test: TestCase,
) -> list:
   """
   Return [CompileTestAction, ..., LinkTestAction, RunTestAction] for one test.
   One CompileTestAction is emitted per file in test.sources; all resulting
   objects are linked together with the cortos archive into a single binary.

   The cortos archive is assumed to already exist at the path returned by
   lib_dir() for the per-test resolved invocation — the runner is responsible
   for building it first.
   """
   tc = resolved.toolchain
   tbuild = test_build_root(resolved, test)

   test_obj_dir = tbuild / "obj"
   bin_dir = tbuild / "bin"
   binary  = bin_dir / test.name
   archive = lib_dir(resolved) / resolved.profile.output.archive

   # Object files are named after the source's basename, so two sources with
   # the same filename (even in different subdirectories) would silently
   # overwrite each other's object file. Guard against that up front.
   _check_no_basename_collisions(test)

   # --- compile: one action per source file ---
   compile_actions: list[CompileTestAction] = []
   obj_paths: list[Path] = []

   for source in test.sources:
      obj_path = (test_obj_dir / source.name).with_suffix(".o")
      obj_paths.append(obj_path)

      compile_args: tuple[str, ...] = (
         tc.tools.cxx,
         *tc.flags.common,
         *tc.flags.cxx,
         "-I", str(include_dir(resolved).resolve()),
         "-c", str(source.resolve()),
         "-o", str(obj_path.resolve()),
      )

      compile_actions.append(
         CompileTestAction(
            test_name=test.name,
            source=source,
            output=obj_path,
            arguments=compile_args,
            working_directory=tbuild,
         )
      )

   # --- link: every compiled object + the cortos archive ---
   lib_flags: tuple[str, ...] = tuple(
      f"-l{lib}" for lib in test.system_libraries
   )

   link_args: tuple[str, ...] = (
      tc.tools.cxx,
      *tc.flags.common,
      *tc.flags.link,
      *test.extra_link_flags,
      *[str(obj.resolve()) for obj in obj_paths],
      str(archive.resolve()),
      *lib_flags,
      "-o", str(binary.resolve()),
   )

   link_action = LinkTestAction(
      test_name=test.name,
      inputs=(*obj_paths, archive),
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

   return [*compile_actions, link_action, run_action]


def _check_no_basename_collisions(test: TestCase) -> None:
   seen: dict[str, Path] = {}
   for source in test.sources:
      key = source.name
      if key in seen:
         raise ValueError(
            f"Test '{test.name}' has two source files with the same name "
            f"'{key}':\n  {seen[key]}\n  {source}\n"
            f"Object file names are derived from the basename, so these would "
            f"collide. Rename one of the files."
         )
      seen[key] = source