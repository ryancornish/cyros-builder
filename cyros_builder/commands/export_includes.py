from argparse import ArgumentParser, Namespace

from cyros_builder.commands.base import (
   Command,
   add_config_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
)
from cyros_builder.include_tree import populate_include_tree
from cyros_builder.output import include_dir
from cyros_builder.resolve import resolve_invocation


class ExportIncludesCommand(Command):
   name = "export-includes"
   help = "Generate the public include tree for the selected profile without compiling."

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

      try:
         populate_include_tree(resolved)
      except Exception as exc:
         print(f"Failed to populate include tree: {exc}")
         return 1

      print(f"Wrote include tree: {include_dir(resolved)}")
      return 0