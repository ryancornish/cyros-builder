from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import Command


class ListToolchainsCommand(Command):
   name = "ls-toolchains"
   help = "List available toolchains."

   def configure_parser(self, parser: ArgumentParser) -> None:
      parser.add_argument(
         "-f", "--format",
         choices=["text", "json"],
         default="text",
         help="Output format.",
      )

   def run(self, args: Namespace) -> int:
      print(f"[list-toolchains] format={args.format}")
      return 0
