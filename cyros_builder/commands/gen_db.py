from __future__ import annotations
from argparse import ArgumentParser, Namespace
from pathlib import Path

from cyros_builder.actions import CompileAction
from cyros_builder.commands.base import (
   Command,
   add_config_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
   step,
)
from cyros_builder.compdb import CompileCommand, activate_compile_commands, write_compile_commands
from cyros_builder.include_tree import populate_include_tree
from cyros_builder.output import compile_db_path
from cyros_builder.planner import plan_build
from cyros_builder.resolve import resolve_invocation


class GenDbCommand(Command):
   name = "gen-db"
   help = "Generate compile_commands.json for the selected profile and toolchain."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_profile_arg(parser)
      add_toolchain_arg(parser)
      add_config_arg(parser)
      add_output_arg(parser)

      parser.add_argument(
         "--activate",
         action="store_true",
         help=(
            "Symlink the generated compile_commands.json into the source root "
            "so editors pick it up automatically."
         ),
      )
      parser.add_argument(
         "--db-path",
         type=Path,
         required=False,
         help="Explicit output path for the generated database (overrides default location).",
      )

   def run(self, args: Namespace) -> int:
      with step("Failed to resolve invocation"):
         resolved = resolve_invocation(args)

      with step("Failed to populate include tree"):
         populate_include_tree(resolved)

      db_path = args.db_path.resolve() if args.db_path else compile_db_path(resolved)

      with step("Failed to generate compile database"):
         commands = self._generate_compile_commands(resolved)
         write_compile_commands(db_path, commands)

      print(f"Wrote compile database: {db_path}")

      if args.activate:
         with step("Failed to activate compile database"):
            activate_compile_commands(resolved.profile.layout.source_root, db_path)
         print(f"Activated: {resolved.profile.layout.source_root.parent / 'compile_commands.json'}")

      return 0

   def _generate_compile_commands(self, resolved) -> list[CompileCommand]:
      actions = plan_build(resolved)
      return [
         CompileCommand(
            directory=resolved.profile.layout.source_root,
            file=action.source,
            arguments=action.arguments,
            output=action.output,
         )
         for action in actions
         if isinstance(action, CompileAction)
      ]