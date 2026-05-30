import argparse
from cyros_builder.commands import (
   BuildCommand,
   CleanCommand,
   ExportIncludesCommand,
   GenDbCommand,
   ShowCommand,
   TestCommand,
)


def build_parser() -> argparse.ArgumentParser:
   parser = argparse.ArgumentParser(
      prog="cyros-builder",
      description="Build tool for Cyros.",
   )

   subparsers = parser.add_subparsers(
      dest="command_name",
      required=True,
      metavar="<command>",
   )

   commands = [
      BuildCommand(),
      CleanCommand(),
      GenDbCommand(),
      ExportIncludesCommand(),
      ShowCommand(),
      TestCommand(),
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
   return args._command_obj.run(args)


if __name__ == "__main__":
   raise SystemExit(main())