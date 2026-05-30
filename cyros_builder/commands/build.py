from argparse import ArgumentParser, Namespace
import traceback

from cyros_builder.commands.base import (
   Command,
   add_config_arg,
   add_jobs_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
   add_verbose_arg,
)
from cyros_builder.executor import execute_actions
from cyros_builder.include_tree import populate_include_tree
from cyros_builder.manifest import write_manifest
from cyros_builder.output import include_dir, manifest_path
from cyros_builder.package import build_manifest
from cyros_builder.planner import plan_build
from cyros_builder.resolve import resolve_invocation
from cyros_builder.ui import print_action_plan


class BuildCommand(Command):
   name = "build"
   help = "Build the full Cyros artifact set for the selected profile."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_profile_arg(parser)
      add_toolchain_arg(parser)
      add_config_arg(parser)
      add_output_arg(parser)
      add_jobs_arg(parser)
      add_verbose_arg(parser)

      parser.add_argument(
         "--clean-first",
         action="store_true",
         help="Clean outputs for this profile/toolchain before building.",
      )

   def run(self, args: Namespace) -> int:
      try:
         resolved = resolve_invocation(args)
      except Exception as exc:
         print(f"Failed to resolve invocation: {exc}")
         return 1

      try:
         populate_include_tree(resolved)
         print(f"Populated include tree: {include_dir(resolved)}")
      except Exception as exc:
         print(f"Failed to populate include tree: {exc}")
         traceback.print_exc()
         return 1

      try:
         actions = plan_build(resolved)
      except Exception as exc:
         print(f"Failed to plan build: {exc}")
         return 1

      print_action_plan(actions)

      try:
         execute_actions(actions, verbose=args.verbose)
      except Exception as exc:
         print(f"Build failed: {exc}")
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