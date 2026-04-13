from argparse import ArgumentParser, Namespace
from pathlib import Path
from cortos_builder.commands.base import Command


class GenDbCommand(Command):
   name = "gen-db"
   help = "Generate compile_commands.json for the selected profile and toolchain."

   def configure_parser(self, parser: ArgumentParser) -> None:
      from cortos_builder.cli import add_profile_arg, add_toolchain_arg

      add_profile_arg(parser, required=True)
      add_toolchain_arg(parser, required=False)

      parser.add_argument(
         "-a", "--activate",
         action="store_true",
         help="Activate the generated compile_commands.json in the project root.",
      )
      parser.add_argument(
         "-o", "--output",
         type=Path,
         required=False,
         help="Optional explicit output path for the generated database.",
      )

   def run(self, args: Namespace) -> int:
      print(f"[gen-db] profile={args.profile} toolchain={args.toolchain} output={args.output}")
      return 0
