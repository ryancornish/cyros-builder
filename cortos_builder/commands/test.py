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


class TestCommand(Command):
   name = "test"
   help = "Build and run CoRTOS unit tests for the selected profile."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_profile_arg(parser)
      add_toolchain_arg(parser)
      add_config_arg(parser)
      add_output_arg(parser)
      add_jobs_arg(parser)
      add_verbose_arg(parser)

      parser.add_argument(
         "--no-build",
         action="store_true",
         help="Run tests without rebuilding first.",
      )
      parser.add_argument(
         "--filter",
         type=str,
         default=None,
         help="Only run tests whose component name contains this string.",
      )

   def run(self, args: Namespace) -> int:
      print("test command not yet implemented")
      return 1