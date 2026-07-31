import shutil
from argparse import ArgumentParser, Namespace
from pathlib import Path

from cyros_builder.commands.base import (
   Command,
   add_config_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
   step,
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
      with step("Failed to resolve invocation"):
         # No config header needed to delete a directory, and requiring one made
         # `clean` unusable with the unit_test_* profiles, which deliberately
         # omit it. That matters now that `clean` is the only thing that removes
         # per-test build trees.
         resolved = resolve_invocation(args, require_config=False)

      # Per-test build roots as well as the main one. The test runner used to
      # wipe its own output tree on every run; now that it reuses it across runs
      # for incremental builds, `clean` is the only thing that deletes it, so it
      # has to reach there or those trees would be unreachable from the CLI.
      targets = [build_root(resolved)]
      tests_root = resolved.output_root / "tests"
      if tests_root.is_dir():
         suffix = Path(resolved.profile.name) / resolved.selected_toolchain_name
         targets.extend(
            path for path in (child / suffix for child in sorted(tests_root.iterdir()))
            if path.is_dir()
         )

      removed = 0
      for target in targets:
         if not target.exists():
            continue
         shutil.rmtree(target)
         print(f"Cleaned: {target}")
         removed += 1

      if not removed:
         print(f"Nothing to clean: {build_root(resolved)}")
      return 0