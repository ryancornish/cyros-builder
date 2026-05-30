"""
coverage.py — post-run coverage report generation.

Called after all tests have passed when --coverage is active. Expects that
the test binaries were built with a coverage-instrumented toolchain
(e.g. --coverage / -fprofile-arcs -ftest-coverage) so that .gcno files
exist alongside the object files and .gcda files were written during test
execution.

Flow:
  1. For each test output directory, run `lcov --capture` to produce a
     per-test .info file.
  2. Merge all per-test .info files with `lcov --add-tracefile`.
  3. Filter to only include files under source_root (strips system headers,
     gtest internals, etc.).
  4. Run `genhtml` to produce an HTML report.

The merged .info file and the HTML tree both land under:
  <output_root>/coverage/
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from cyros_builder.resolve import ResolvedInvocation
from cyros_builder.test_model import TestCase
from cyros_builder.test_planner import test_build_root, test_output_root


def generate_coverage_report(
   *,
   resolved: ResolvedInvocation,
   tests: list[TestCase],
   verbose: bool = False,
) -> None:
   """
   Collect coverage data from all test output directories and generate a
   merged HTML report. Raises on any failure.
   """
   coverage_root = resolved.output_root / "coverage"
   coverage_root.mkdir(parents=True, exist_ok=True)

   source_root = resolved.profile.layout.source_root

   # --- Step 1: capture per-test .info files ---
   info_files: list[Path] = []
   for test in tests:
      # Build a minimal resolved invocation just to get the right build root.
      from cyros_builder.resolve import ResolvedInvocation as RI
      test_resolved = RI(
         profile_root=resolved.profile_root,
         profile=resolved.profile,
         toolchain=resolved.toolchain,
         selected_toolchain_name=resolved.selected_toolchain_name,
         cli_overrode_toolchain=resolved.cli_overrode_toolchain,
         config_header=test.config,
         cli_overrode_config=True,
         output_root=test_output_root(resolved, test),
         cli_overrode_output=True,
      )
      build_root = test_build_root(test_resolved, test)
      info_file  = coverage_root / f"{test.name}.info"

      _run(
         ["lcov",
          "--capture",
          "--directory", str(build_root),
          "--output-file", str(info_file),
          "--gcov-tool", _gcov_tool(resolved),
          "--rc", "branch_coverage=1",
          "--rc", "geninfo_unexecuted_blocks=1",
          "--ignore-errors", "mismatch,unused",
         ],
         verbose=verbose,
         desc=f"lcov capture ({test.name})",
      )
      info_files.append(info_file)

   # --- Step 2: merge ---
   merged_info = coverage_root / "merged.info"
   merge_args = ["lcov", "--output-file", str(merged_info), "--rc", "branch_coverage=1"]
   for info in info_files:
      merge_args += ["--add-tracefile", str(info)]
   _run(merge_args, verbose=verbose, desc="lcov merge")

   # --- Step 3: filter to source_root only ---
   filtered_info = coverage_root / "filtered.info"
   _run(
      ["lcov",
       "--extract", str(merged_info),
       str(source_root / "*"),      # glob pattern — lcov interprets this
       "--output-file", str(filtered_info),
       "--rc", "branch_coverage=1",
      ],
      verbose=verbose,
      desc="lcov filter",
   )

   # --- Step 4: HTML report ---
   html_dir = coverage_root / "html"
   _run(
      ["genhtml",
       str(filtered_info),
       "--output-directory", str(html_dir),
       "--branch-coverage",
       "--title", "Cyros Unit Test Coverage",
      ],
      verbose=verbose,
      desc="genhtml",
   )

   print(f"\nCoverage report: {html_dir / 'index.html'}")


def _gcov_tool(resolved: ResolvedInvocation) -> str:
   """
   Derive the gcov tool name from the toolchain's C compiler.
   e.g. 'gcc-15' -> 'gcov-15', 'gcc' -> 'gcov'.
   """
   cc = resolved.toolchain.tools.cc   # e.g. 'gcc-15'
   if cc.startswith('gcc'):
      return 'gcov' + cc[3:]          # 'gcov-15'
   # For other compilers fall back to plain gcov and let lcov sort it out.
   return 'gcov'


def _run(args: list[str], *, verbose: bool, desc: str) -> None:
   if verbose:
      print(f"$ {' '.join(args)}")
   else:
      print(f"  {desc}")

   result = subprocess.run(args, capture_output=not verbose)
   if result.returncode != 0:
      # Surface stderr even in non-verbose mode so the failure is diagnosable.
      if not verbose and result.stderr:
         print(result.stderr.decode(errors="replace"))
      raise RuntimeError(
         f"Coverage step failed ({desc}): "
         f"exited with code {result.returncode}"
      )