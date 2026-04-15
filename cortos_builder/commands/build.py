from argparse import ArgumentParser, Namespace

from cortos_builder.commands.base import (
   Command,
   add_jobs_arg,
   add_profile_arg,
   add_root_arg,
   add_toolchain_arg,
   add_verbose_arg,
)
from cortos_builder.executor import execute_actions
from cortos_builder.manifest import write_manifest
from cortos_builder.output import manifest_path
from cortos_builder.output import include_dir
from cortos_builder.package import build_manifest
from cortos_builder.planner import plan_build
from cortos_builder.resolve import resolve_profile_and_toolchain
from cortos_builder.include_tree import populate_include_tree


class BuildCommand(Command):
   name = "build"
   help = "Build the full CoRTOS artifact set for the selected profile."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_root_arg(parser, required=False)
      add_profile_arg(parser, required=True)
      add_toolchain_arg(parser, required=False)
      add_jobs_arg(parser)
      add_verbose_arg(parser)

      parser.add_argument(
         "--clean-first",
         action="store_true",
         help="Clean outputs for this profile/toolchain before building.",
      )
      parser.add_argument(
         "--activate-db",
         action="store_true",
         help="Activate the generated compile_commands.json after build.",
      )

   def run(self, args: Namespace) -> int:
      try:
         resolved = resolve_profile_and_toolchain(args)
      except Exception as exc:
         print(f"Failed to resolve invocation: {exc}")
         return 1

      try:
         actions = plan_build(resolved)
      except Exception as exc:
         print(f"Failed to plan build: {exc}")
         return 1

      print(f"Planned {len(actions)} build actions")
      for action in actions:
         print(action)

      try:
         execute_actions(actions, verbose=args.verbose)
      except Exception as exc:
         print(f"Build failed: {exc}")
         return 1

      try:
         populate_include_tree(resolved)
         print(f"Populated include tree: {include_dir(resolved)}")
      except Exception as exc:
         print(f"Build succeeded, but failed to populate include tree: {exc}")
         return 1

      try:
         manifest = build_manifest(resolved)
         out = manifest_path(resolved)
         write_manifest(out, manifest)
         print(f"Wrote manifest: {out}")
      except Exception as exc:
         print(f"Build succeeded, but failed to write manifest: {exc}")
         return 1

      return 0