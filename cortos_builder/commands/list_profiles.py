import json
from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import Command, add_root_arg
from cortos_builder.profile import find_profiles, load_profile
from cortos_builder.project import resolve_project_root


class ListProfilesCommand(Command):
   name = "list-profiles"
   help = "List available build profiles from <project-root>/profiles."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_root_arg(parser, required=False)
      parser.add_argument(
         "--format",
         choices=["text", "json"],
         default="text",
         help="Output format.",
      )

   def run(self, args: Namespace) -> int:
      project_root = resolve_project_root(args.root)
      profile_paths = find_profiles(project_root)

      if not profile_paths:
         print(f"No profiles found in {project_root / 'profiles'}")
         return 1

      profiles = []
      for path in profile_paths:
         try:
            profiles.append(load_profile(path))
         except Exception as exc:
            print(f"Warning: failed to load profile {path}: {exc}")

      if args.format == "json":
         data = [
            {
               "name": p.name,
               "path": str(p.path),
               "default_toolchain": p.default_toolchain,
               "port": p.build.port,
               "time_driver": p.build.time_driver,
            }
            for p in profiles
         ]
         print(json.dumps(data, indent=2))
         return 0

      print(f"Project root: {project_root}")
      print()

      for p in profiles:
         print(p.name)
         print(f"  path:              {p.path}")
         print(f"  default toolchain: {p.default_toolchain}")
         print(f"  port:              {p.build.port}")
         print(f"  time driver:       {p.build.time_driver}")
         print()

      return 0
