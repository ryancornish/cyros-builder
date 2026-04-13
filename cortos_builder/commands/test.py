from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import Command


class TestCommand(Command):
   name = "test"
   help = "Build and run CoRTOS tests for the selected profile."

   def configure_parser(self, parser: ArgumentParser) -> None:
      from cortos_builder.cli import (
         add_jobs_arg,
         add_profile_arg,
         add_toolchain_arg,
         add_verbose_arg,
      )

      add_profile_arg(parser, required=True)
      add_toolchain_arg(parser, required=False)
      add_jobs_arg(parser)
      add_verbose_arg(parser)

      parser.add_argument(
         "-c", "--clean-first",
         action="store_true",
         help="Clean outputs for this profile/toolchain before building tests.",
      )
      parser.add_argument(
         "-n", "--no-build",
         action="store_true",
         help="Run tests without rebuilding first.",
      )

   def run(self, args: Namespace) -> int:
      print(f"[test] profile={args.profile} toolchain={args.toolchain} no_build={args.no_build}")
      return 0
