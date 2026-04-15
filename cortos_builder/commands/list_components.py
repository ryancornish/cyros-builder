from argparse import ArgumentParser, Namespace
import json

from cortos_builder.commands.base import Command, add_root_arg
from cortos_builder.component import load_components
from cortos_builder.project import resolve_project_root


class ListComponentsCommand(Command):
   name = "list-components"
   help = "List source components from <project-root>/src."

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

      try:
         components = load_components(project_root)
      except Exception as exc:
         print(f"Failed to load components: {exc}")
         return 1

      if not components:
         print(f"No components found under {project_root / 'src'}")
         return 1

      ordered = [components[name] for name in sorted(components)]

      if args.format == "json":
         data = [
            {
               "name": c.name,
               "path": str(c.path),
               "description": c.description,
               "dependencies": list(c.dependencies),
               "public_modules": list(c.public_modules),
               "private_modules": list(c.private_modules),
               "source_roots": [str(p) for p in c.source_roots],
               "generated_includes": c.generated_includes,
            }
            for c in ordered
         ]
         print(json.dumps(data, indent=2))
         return 0

      print(f"Project root: {project_root}")
      print()

      for c in ordered:
         print(c.name)
         print(f"  path:               {c.path}")
         print(f"  description:        {c.description}")
         print(f"  dependencies:       {list(c.dependencies)}")
         print(f"  public modules:     {list(c.public_modules)}")
         print(f"  private modules:    {list(c.private_modules)}")
         print(f"  source roots:       {[str(p) for p in c.source_roots]}")
         print(f"  generated includes: {c.generated_includes}")
         print()

      return 0