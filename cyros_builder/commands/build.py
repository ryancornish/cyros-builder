from argparse import ArgumentParser, Namespace

from cyros_builder.commands.base import (
   Command,
   add_config_arg,
   add_force_arg,
   add_jobs_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
   add_verbose_arg,
   step,
)
from cyros_builder.executor import execute_actions
from cyros_builder.include_tree import populate_include_tree
from cyros_builder.manifest import write_manifest
from cyros_builder.output import include_dir, manifest_path
from cyros_builder.package import build_manifest
from cyros_builder.planner import plan_build
from cyros_builder.resolve import resolve_invocation
from cyros_builder.staleness import prune_actions, record_state
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
      add_force_arg(parser)
      add_verbose_arg(parser)

      parser.add_argument(
         "--clean-first",
         action="store_true",
         help="Clean outputs for this profile/toolchain before building.",
      )

   def run(self, args: Namespace) -> int:
      with step("Failed to resolve invocation"):
         resolved = resolve_invocation(args)

      with step("Failed to populate include tree"):
         populate_include_tree(resolved)
      print(f"Populated include tree: {include_dir(resolved)}")

      with step("Failed to plan build"):
         actions = plan_build(resolved)

      print_action_plan(actions)

      # Prune between plan and execute. The planner still described a full
      # build; gen-db still consumes that full plan.
      with step("Failed to determine what needs rebuilding"):
         pruned = prune_actions(resolved, actions, force=args.force)

      if pruned.skipped:
         print(f"Up to date: {pruned.skipped}/{pruned.total} action(s) skipped")

      if pruned.all_up_to_date:
         print("Nothing to do.")
      else:
         with step("Build failed"):
            execute_actions(pruned.actions, verbose=args.verbose, jobs=args.jobs)

         # Only after a clean run: see record_state's docstring for why a failed
         # build deliberately records nothing.
         with step("Build succeeded, but failed to record build state"):
            record_state(resolved, actions, pruned.actions)

      with step("Build succeeded, but failed to write manifest"):
         manifest = build_manifest(resolved)
         out = manifest_path(resolved)
         write_manifest(out, manifest)
      print(f"Wrote manifest: {out}")

      return 0
