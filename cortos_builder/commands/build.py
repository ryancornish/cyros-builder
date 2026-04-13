from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import *


class BuildCommand(Command):
   name = "build"
   help = "Build the full CoRTOS artifact set for the selected profile."

   def configure_parser(self, parser: ArgumentParser) -> None:
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
      print(f"[build] profile={args.profile} toolchain={args.toolchain} jobs={args.jobs}")
      print(f"[build] clean_first={args.clean_first} activate_db={args.activate_db}")

      # Future:
      # profile = ProfileLoader.load(args.profile)
      # toolchain = ToolchainRegistry.resolve(args.toolchain or profile.default_toolchain)
      # planner = BuildPlanner(...)
      # plan = planner.plan_build(...)
      # executor = BuildExecutor(...)
      # executor.run(plan)

      return 0
