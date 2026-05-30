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

      db_path = args.db_path.resolve() if args.db_path else compile_db_path(resolved)

      try:
         commands = self._generate_compile_commands(resolved)
         write_compile_commands(db_path, commands)
      except Exception as exc:
         print(f"Failed to generate compile database: {exc}")
         return 1

      print(f"Wrote compile database: {db_path}")

      if args.activate:
         try:
            activate_compile_commands(resolved.profile.layout.source_root, db_path)
            print(f"Activated: {resolved.profile.layout.source_root.parent / 'compile_commands.json'}")
         except Exception as exc:
            print(f"Failed to activate compile database: {exc}")
            return 1

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