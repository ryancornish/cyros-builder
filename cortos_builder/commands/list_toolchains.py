import json
from argparse import ArgumentParser, Namespace
from cortos_builder.commands.base import Command, add_root_arg
from cortos_builder.project import resolve_project_root
from cortos_builder.toolchain import list_toolchain_names, resolve_toolchain


class ListToolchainsCommand(Command):
   name = "list-toolchains"
   help = "List available toolchains from <project-root>/toolchains."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_root_arg(parser, required=False)
      parser.add_argument(
         "--format",
         choices=["text", "json"],
         default="text",
         help="Output format.",
      )
      parser.add_argument(
         "--names-only",
         action="store_true",
         help="Only print toolchain names.",
      )

   def run(self, args: Namespace) -> int:
      project_root = resolve_project_root(args.root)

      try:
         names = list_toolchain_names(project_root)
      except Exception as exc:
         print(f"Failed to list toolchains: {exc}")
         return 1

      if not names:
         print(f"No toolchains found in {project_root / 'toolchains'}")
         return 1

      if args.names_only:
         for name in names:
            print(name)
         return 0

      resolved = []
      for name in names:
         try:
            resolved.append(resolve_toolchain(name, project_root))
         except Exception as exc:
            print(f"Warning: failed to load toolchain '{name}': {exc}")

      if args.format == "json":
         data = [
            {
               "name": tc.name,
               "path": str(tc.path),
               "extends": tc.extends,
               "family": tc.settings.family,
               "cc": tc.tools.cc,
               "cxx": tc.tools.cxx,
               "ar": tc.tools.ar,
               "asm": tc.tools.asm,
               "debug": tc.settings.debug,
               "optimization": tc.settings.optimization,
               "warnings_as_errors": tc.settings.warnings_as_errors,
               "use_modules": tc.settings.use_modules,
            }
            for tc in resolved
         ]
         print(json.dumps(data, indent=2))
         return 0

      print(f"Project root: {project_root}")
      print()

      for tc in resolved:
         print(tc.name)
         print(f"  path:               {tc.path}")
         print(f"  extends:            {tc.extends}")
         print(f"  family:             {tc.settings.family}")
         print(f"  cc:                 {tc.tools.cc}")
         print(f"  cxx:                {tc.tools.cxx}")
         print(f"  ar:                 {tc.tools.ar}")
         print(f"  asm:                {tc.tools.asm}")
         print(f"  debug:              {tc.settings.debug}")
         print(f"  optimization:       {tc.settings.optimization}")
         print(f"  warnings as errors: {tc.settings.warnings_as_errors}")
         print(f"  use modules:        {tc.settings.use_modules}")
         print()

      return 0