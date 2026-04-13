import json
from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import *
from cortos_builder.profile import load_profile


class ShowCommand(Command):
   name = "show"
   help = "Show the resolved effective configuration for a profile/toolchain."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_profile_arg(parser, required=True)
      add_toolchain_arg(parser, required=False)
      parser.add_argument(
         "--format",
         choices=["text", "json"],
         default="text",
         help="Output format.",
      )

   def run(self, args: Namespace) -> int:
      profile = load_profile(args.profile)
      toolchain = args.toolchain or profile.default_toolchain

      if args.format == "json":
         data = {
            "profile_path": str(profile.path),
            "name": profile.name,
            "toolchain": toolchain,
            "build": {
               "port": profile.build.port,
               "time_driver": profile.build.time_driver,
               "config": str(profile.build.config),
            },
            "features": {
               "tests": profile.features.tests,
               "assertions": profile.features.assertions,
            },
            "output": {
               "root": str(profile.output.root),
            },
         }
         print(json.dumps(data, indent=2))
         return 0

      print(f"name:            {profile.name}")
      print(f"profile path:    {profile.path}")
      print(f"toolchain:       {toolchain}")
      print(f"port:            {profile.build.port}")
      print(f"time driver:     {profile.build.time_driver}")
      print(f"config:          {profile.build.config}")
      print(f"tests:           {profile.features.tests}")
      print(f"assertions:      {profile.features.assertions}")
      print(f"output root:     {profile.output.root}")
      return 0

