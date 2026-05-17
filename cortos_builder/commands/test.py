from argparse import ArgumentParser, Namespace

from cortos_builder.commands.base import (
   Command,
   add_config_arg,
   add_jobs_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
   add_verbose_arg,
)
from cortos_builder.resolve import resolve_invocation
from cortos_builder.test_model import discover_tests, find_unit_test_root
from cortos_builder.test_runner import run_all_tests


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
      add_verbose_arg(parser)

      parser.add_argument(
         "--filter",
         type=str,
         default=None,
         metavar="SUBSTRING",
         help="Only run tests whose name contains SUBSTRING.",
      )
      parser.add_argument(
         "--list",
         action="store_true",
         help="List discovered tests without building or running them.",
      )

   def run(self, args: Namespace) -> int:
      # Resolve the base invocation.  Config header is not required here
      # because each test supplies its own — we defer that check.
      try:
         resolved = _resolve_without_config(args)
      except Exception as exc:
         print(f"Failed to resolve invocation: {exc}")
         return 1

      source_root = resolved.profile.layout.source_root

      # Discover tests.
      try:
         tests = discover_tests(source_root)
      except FileNotFoundError as exc:
         print(f"Test discovery failed: {exc}")
         return 1
      except Exception as exc:
         print(f"Error loading test cases: {exc}")
         return 1

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
      )

      failed = sum(1 for r in results if not r.passed and not r.skipped)
      return 0 if failed == 0 else 1


def _resolve_without_config(args: Namespace):
   """
   Resolve the invocation but skip the config_header requirement.
   Each unit test brings its own config header, so we don't want the
   resolver to fail because none was set on the profile or CLI.
   """
   from cortos_builder.profile import load_profile
   from cortos_builder.toolchain import resolve_toolchain
   from cortos_builder.resolve import ResolvedInvocation
   from pathlib import Path

   profile = load_profile(Path(args.profile))

   cli_overrode_toolchain = getattr(args, "toolchain", None) is not None
   if cli_overrode_toolchain:
      toolchain_path = Path(args.toolchain).resolve()
   elif profile.toolchain is not None:
      toolchain_path = profile.toolchain
   else:
      raise ValueError(
         "No toolchain specified. "
         "Provide -t/--toolchain <path> or set toolchain in the profile."
      )
   toolchain = resolve_toolchain(toolchain_path)

   output_root = profile.layout.output_root

   # config_header is set to a sentinel None — the test runner will override
   # it per-test via _make_test_resolved before any build is attempted.
   return ResolvedInvocation(
      profile_root=profile.path.parent,
      profile=profile,
      toolchain=toolchain,
      selected_toolchain_name=toolchain.name,
      cli_overrode_toolchain=cli_overrode_toolchain,
      config_header=Path("/dev/null"),   # never used; overridden per-test
      cli_overrode_config=False,
      output_root=output_root,
      cli_overrode_output=False,
   )