import shutil
from argparse import ArgumentParser, Namespace

from cyros_builder.commands.base import (
   Command,
   add_config_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
)
from cyros_builder.output import build_root
from cyros_builder.resolve import resolve_invocation


class CleanCommand(Command):
   name = "clean"
   help = "Remove build outputs for the selected profile and toolchain."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_profile_arg(parser)
      add_toolchain_arg(parser)
      add_config_arg(parser)
      add_output_arg(parser)

   def run(self, args: Namespace) -> int:
      try:
         resolved = resolve_invocation(args)
      except Exception as exc:
         print(f"Failed to resolve invocation: {exc}")
         return 1

      target = build_root(resolved)

      if not target.exists():
         print(f"Nothing to clean: {target}")
         return 0

      shutil.rmtree(target)
      print(f"Cleaned: {target}")
      return 0