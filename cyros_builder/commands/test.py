from argparse import ArgumentParser, Namespace

from cyros_builder.commands.base import (
   Command,
   add_force_arg,
   add_jobs_arg,
   add_profile_arg,
   add_toolchain_arg,
   add_verbose_arg,
   step,
)
from cyros_builder.errors import BuilderError
from cyros_builder.resolve import resolve_invocation
from cyros_builder.test_model import discover_tests, find_unit_test_root
from cyros_builder.test_runner import run_all_tests


class TestCommand(Command):
   name = "test"
   help = "Build and run CoRTOS unit tests."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_profile_arg(parser)
      add_toolchain_arg(parser)
      # --config and --output are intentionally NOT exposed here:
      # each test brings its own config header, and output is derived
      # per-test from the profile's output_root.  Exposing them would
      # be misleading.
      add_jobs_arg(parser)
      add_force_arg(parser)
      add_verbose_arg(parser)

      parser.add_argument(
         "--filter",
         type=str,
         default=None,
         metavar="SUBSTRING",
         help="Only run tests whose name contains SUBSTRING.",
      )
      parser.add_argument(
         "--test-timeout",
         type=float,
         default=60.0,
         metavar="SECONDS",
         help=(
            "Kill a test binary that runs longer than this and report it as a "
            "TIMEOUT (default: 60). Use 0 to wait indefinitely. gtest has no "
            "per-test timeout of its own, so this is the only thing standing "
            "between a hung test and a stalled suite run."
         ),
      )
      parser.add_argument(
         "--list",
         action="store_true",
         help="List discovered tests without building or running them.",
      )
      parser.add_argument(
         "--coverage",
         action="store_true",
         help=(
            "After all tests pass, collect gcda/gcno data and generate a "
            "merged lcov HTML report. Requires a coverage-instrumented "
            "toolchain (e.g. gcc-coverage.toml)."
         ),
      )

   def run(self, args: Namespace) -> int:
      # Resolve the base invocation. Config header is not required here
      # because each test supplies its own — we defer that check.
      with step("Failed to resolve invocation"):
         resolved = resolve_invocation(args, require_config=False)

      source_root = resolved.profile.layout.source_root

      # Discover tests.
      try:
         tests = discover_tests(source_root)
      except FileNotFoundError as exc:
         raise BuilderError(f"Test discovery failed: {exc}") from exc
      except Exception as exc:
         raise BuilderError(f"Error loading test cases: {exc}") from exc

      if not tests:
         unit_root = find_unit_test_root(source_root)
         print(f"No test.toml files found under {unit_root}")
         return 1

      # --list mode: just print discovered tests and exit.
      if args.list:
         print(f"Discovered {len(tests)} test(s):")
         for t in tests:
            print(f"  {t.name:<40} {t.path}")
         return 0

      # Build and run.
      results = run_all_tests(
         resolved=resolved,
         tests=tests,
         verbose=args.verbose,
         filter_str=args.filter,
         jobs=args.jobs,
         force=args.force,
         timeout=args.test_timeout,
      )

      failed = sum(1 for r in results if not r.passed and not r.skipped)
      if failed:
         return 1

      # Coverage report — only for tests that actually built and ran.
      # Skipped tests (e.g. port-locked tests under a non-matching profile)
      # never produced a build directory, so lcov has nothing to capture there.
      if args.coverage:
         ran_names = {r.name for r in results if not r.skipped}
         covered_tests = [t for t in tests if t.name in ran_names]

         print(f"\nCollecting coverage data ({len(covered_tests)} test(s), "
               f"{len(tests) - len(covered_tests)} skipped)...")
         with step("Coverage report failed"):
            from cyros_builder.coverage import generate_coverage_report
            generate_coverage_report(
               resolved=resolved,
               tests=covered_tests,
               verbose=args.verbose,
            )

      return 0
