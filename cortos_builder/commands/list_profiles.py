from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import Command


class ListProfilesCommand(Command):
   name = "ls-profiles"
   help = "List available build profiles."

   def configure_parser(self, parser: ArgumentParser) -> None:
      parser.add_argument(
         "-f", "--format",
         choices=["text", "json"],
         default="text",
         help="Output format.",
      )

   def run(self, args: Namespace) -> int:
      print(f"[list-profiles] format={args.format}")
      return 0