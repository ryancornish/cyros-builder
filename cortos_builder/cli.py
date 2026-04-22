import argparse
from pathlib import Path
from typing import Iterable
from cortos_builder.commands import *


def build_parser() -> argparse.ArgumentParser:
   parser = argparse.ArgumentParser(
      prog="build-cortos",
      description="Build tool for CoRTOS.",
   )

   subparsers = parser.add_subparsers(
      dest="command_name",
      required=True,
      metavar="<command>",
   )

   commands = [
      BuildCommand(),
      CleanCommand(),
      TestCommand(),
      GenDbCommand(),
      ExportIncludesCommand(),
      ShowCommand(),
      ListProfilesCommand(),
      ListToolchainsCommand(),
      ListComponentsCommand(),
   ]

   for cmd in commands:
      subparser = subparsers.add_parser(
         cmd.name,
         help=cmd.help,
         description=cmd.help,
      )
      cmd.configure_parser(subparser)
      subparser.set_defaults(_command_obj=cmd)

   return parser


def main() -> int:
   parser = build_parser()
   args = parser.parse_args()

   cmd = args._command_obj
   return cmd.run(args)


if __name__ == "__main__":
   raise SystemExit(main())
