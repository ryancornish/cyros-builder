import argparse
from cyros_builder.commands import (
   BuildCommand,
   CleanCommand,
   ExportIncludesCommand,
   GenDbCommand,
   ShowCommand,
   TestCommand,
)
from cyros_builder.errors import BuilderError


def build_parser() -> argparse.ArgumentParser:
   parser = argparse.ArgumentParser(
      prog="cyros-builder",
      description="Build tool for Cyros.",
   )
   parser.add_argument(
      "--debug",
      action="store_true",
      help="On failure, show the full traceback instead of a one-line message.",
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
   try:
      return args._command_obj.run(args)
   except BuilderError as exc:
      if args.debug:
         raise
      print(exc)
      return 1


if __name__ == "__main__":
   raise SystemExit(main())