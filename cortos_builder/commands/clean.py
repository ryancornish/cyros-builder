from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import Command


class CleanCommand(Command):
   name = "clean"
   help = "Remove build outputs for a selected profile/toolchain or everything."

   def configure_parser(self, parser: ArgumentParser) -> None:
      from cortos_builder.cli import add_profile_arg, add_toolchain_arg

      add_profile_arg(parser, required=False)
      add_toolchain_arg(parser, required=False)

      parser.add_argument(
         "-a", "--all",
         action="store_true",
         help="Remove all build outputs and generated databases.",
      )

   def run(self, args: Namespace) -> int:
      print(f"[clean] profile={args.profile} toolchain={args.toolchain} all={args.all}")
      return 0
