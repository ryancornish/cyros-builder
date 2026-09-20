from argparse import ArgumentParser, Namespace

from cyros_builder.commands.base import (
   Command,
   add_force_arg,
   add_jobs_arg,
   add_profile_arg,
   add_toolchain_arg,
   add_verbose_arg,
   format_tomls,
   step,
)
from cyros_builder.errors import BuilderError
from cyros_builder.resolve import resolve_invocation
from cyros_builder.consumer_model import discover_consumers
from cyros_builder.test_model import KINDS, DEFAULT_RUN_KINDS, discover_tests, find_unit_test_root
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
         "--no-consumers",
         action="store_true",
         help=(
            "Skip the consumer projects. They sit at the top of the chain and "
            "are the only test of the EXPORTED tree, but each one shells out to "
            "its own build script, so this is the escape hatch when that is in "
            "the way."
         ),
      )
      parser.add_argument(
         "--keep-going",
         action="store_true",
         help=(
            "Run every layer even after a lower one fails. Off by default "
            "because a test standing on a broken layer produces a verdict that "
            "means nothing, so it is reported BLOCKED instead. Turn this on "
            "when you want the whole picture rather than the first cause."
         ),
      )
      parser.add_argument(
         "--kind",
         action="append",
         choices=list(KINDS),
         default=None,
         metavar="KIND",
         help=(
            "Which kinds of test to run, repeatable. Default: "
            f"{', '.join(DEFAULT_RUN_KINDS)}. A soak is only meaningful as a "
            "rate over many runs and a measurement asserts nothing, so neither "
            "runs unless asked for."
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

      format_tomls(resolved)

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

      # Consumers join the same layered run. They are ordinary members of the
      # chain, at the top of it, and are blocked by a lower failure like
      # anything else.
      unit_tests = tests
      if not args.no_consumers:
         try:
            tests = tests + discover_consumers(source_root)
         except Exception as exc:
            raise BuilderError(f"Error loading consumer projects: {exc}") from exc

      # --list mode: just print discovered tests and exit.
      if args.list:
         print(f"Discovered {len(tests)} test(s), by layer:")
         width = max((len(t.name) for t in tests), default=0)
         last: int | None = None
         for t in sorted(tests, key=lambda c: (c.layer, c.name)):
            if t.layer != last:
               last = t.layer
               print(f"  layer {t.layer}")
            note = f"  [{t.kind}]" if t.kind != "unit" else ""
            if t.harness_debt:
               note += f"  [runs at layer {t.run_rank}: {t.harness_debt.reason}]"
            print(f"    {t.name:<{width}}{note}")
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
         keep_going=args.keep_going,
         kinds=tuple(args.kind) if args.kind else DEFAULT_RUN_KINDS,
      )

      failed = sum(1 for r in results if not r.passed and not r.skipped)
      if failed:
         return 1

      # Coverage report — only for tests that actually built and ran.
      # Skipped tests (e.g. port-locked tests under a non-matching profile)
      # never produced a build directory, so lcov has nothing to capture there.
      if args.coverage:
         # Consumers are excluded: they are built by their own scripts, not by
         # an instrumented toolchain, so they produce no gcda for lcov.
         ran_names = {r.name for r in results if not r.skipped}
         covered_tests = [t for t in unit_tests if t.name in ran_names]

         print(f"\nCollecting coverage data ({len(covered_tests)} test(s), "
               f"{len(unit_tests) - len(covered_tests)} skipped)...")
         with step("Coverage report failed"):
            from cyros_builder.coverage import generate_coverage_report
            generate_coverage_report(
               resolved=resolved,
               tests=covered_tests,
               verbose=args.verbose,
            )

      return 0
