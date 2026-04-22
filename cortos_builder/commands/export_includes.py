from argparse import ArgumentParser, Namespace

from cortos_builder.commands.base import Command, add_profile_arg, add_root_arg, add_toolchain_arg
from cortos_builder.include_tree import populate_include_tree
from cortos_builder.output import include_dir
from cortos_builder.resolve import resolve_profile_and_toolchain


class ExportIncludesCommand(Command):
   name = "export-includes"
   help = "Generate the selected public include tree without compiling sources."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_root_arg(parser, required=False)
      add_profile_arg(parser, required=True)
      add_toolchain_arg(parser, required=False)

   def run(self, args: Namespace) -> int:
      try:
         resolved = resolve_profile_and_toolchain(args)
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