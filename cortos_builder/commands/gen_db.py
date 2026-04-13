from __future__ import annotations
from argparse import ArgumentParser, Namespace
from pathlib import Path
from cortos_builder.commands.base import Command, add_profile_arg, add_root_arg, add_toolchain_arg
from cortos_builder.compdb import CompileCommand, activate_compile_commands, write_compile_commands
from cortos_builder.output import compile_db_path
from cortos_builder.resolve import resolve_profile_and_toolchain


class GenDbCommand(Command):
   name = "gen-db"
   help = "Generate compile_commands.json for the selected profile and toolchain."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_root_arg(parser, required=False)
      add_profile_arg(parser, required=True)
      add_toolchain_arg(parser, required=False)

      parser.add_argument(
         "--activate",
         action="store_true",
         help="Activate the generated compile_commands.json in the project root.",
      )
      parser.add_argument(
         "--output",
         type=Path,
         required=False,
         help="Optional explicit output path for the generated database.",
      )

   def run(self, args: Namespace) -> int:
      try:
         resolved = resolve_profile_and_toolchain(args)
      except Exception as exc:
         print(f"Failed to resolve invocation: {exc}")
         return 1

      out_path = args.output.resolve() if args.output else compile_db_path(resolved)

      try:
         commands = self._generate_compile_commands(resolved)
         write_compile_commands(out_path, commands)
      except Exception as exc:
         print(f"Failed to generate compile database: {exc}")
         return 1

      print(f"Wrote compile database: {out_path}")

      if args.activate:
         try:
               activate_compile_commands(resolved.project_root, out_path)
         except Exception as exc:
               print(f"Failed to activate compile database: {exc}")
               return 1
         print(f"Activated compile database: {resolved.project_root / 'compile_commands.json'}")

      return 0

   def _generate_compile_commands(self, resolved) -> list[CompileCommand]:
      """
      Temporary stub generator.

      For now, emit one synthetic command for the profile's config header.
      This proves the plumbing works. Later this should come from the real
      build graph/planner.
      """
      tc = resolved.toolchain
      profile = resolved.profile
      root = resolved.project_root

      # This is deliberately a stub. Replace later with planner output.
      return [
         CompileCommand(
               directory=root,
               file=profile.build.config,
               arguments=(
                  tc.tools.cxx,
                  *tc.flags.common,
                  *tc.flags.cxx,
                  "-c",
                  str(profile.build.config),
                  "-o",
                  str(root / "build" / "stub.o"),
               ),
               output=root / "build" / "stub.o",
         )
      ]
