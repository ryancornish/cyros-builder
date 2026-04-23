from argparse import ArgumentParser, Namespace
import json

from cortos_builder.commands.base import Command, add_profile_arg, add_root_arg, add_toolchain_arg
from cortos_builder.resolve import resolve_profile_and_toolchain


class ShowCommand(Command):
   name = "show"
   help = "Show the resolved effective configuration for a profile/toolchain."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_root_arg(parser, required=False)
      add_profile_arg(parser, required=True)
      add_toolchain_arg(parser, required=False)
      parser.add_argument(
         "--format",
         choices=["text", "json"],
         default="text",
         help="Output format.",
      )

   def run(self, args: Namespace) -> int:
      try:
         resolved = resolve_profile_and_toolchain(args)
      except Exception as exc:
         print(f"Failed to resolve invocation: {exc}")
         return 1

      profile = resolved.profile
      toolchain = resolved.toolchain

      if args.format == "json":
         data = {
            "project_root": str(resolved.project_root),
            "profile": {
               "path": str(profile.path),
               "name": profile.name,
               "default_toolchain": profile.default_toolchain,
               "build": {
                  "port": profile.build.port,
                  "time_driver": profile.build.time_driver,
                  "config_header": str(profile.build.config_header),
               },
               "features": {
                  "enable": list(profile.features.enable),
               },
               "layout": {
                  "project_root": str(profile.layout.project_root),
                  "build_root": str(profile.layout.build_root),
                  "source_root": str(profile.layout.source_root),
                  "output_root": str(profile.layout.output_root),
               },
               "output": {
                  "archive": profile.output.archive,
               },
            },
            "toolchain": {
               "path": str(toolchain.path),
               "name": toolchain.name,
               "extends": toolchain.extends,
               "tools": {
                  "cc": toolchain.tools.cc,
                  "cxx": toolchain.tools.cxx,
                  "ar": toolchain.tools.ar,
                  "asm": toolchain.tools.asm,
               },
               "flags": {
                  "common": list(toolchain.flags.common),
                  "c": list(toolchain.flags.c),
                  "cxx": list(toolchain.flags.cxx),
                  "asm": list(toolchain.flags.asm),
                  "link": list(toolchain.flags.link),
               },
               "settings": {
                  "family": toolchain.settings.family,
                  "debug": toolchain.settings.debug,
                  "optimization": toolchain.settings.optimization,
                  "warnings_as_errors": toolchain.settings.warnings_as_errors,
                  "use_modules": toolchain.settings.use_modules,
               },
            },
            "resolved": {
               "selected_toolchain": resolved.selected_toolchain_name,
               "cli_overrode_toolchain": resolved.cli_overrode_toolchain,
            },
         }
         print(json.dumps(data, indent=2))
         return 0

      print("Resolved Invocation")
      print(f"  project root:       {resolved.project_root}")
      print(f"  selected toolchain: {resolved.selected_toolchain_name}")
      print(f"  cli override:       {resolved.cli_overrode_toolchain}")
      print()

      print("Profile")
      print(f"  path:               {profile.path}")
      print(f"  name:               {profile.name}")
      print(f"  default toolchain:  {profile.default_toolchain}")
      print(f"  port:               {profile.build.port}")
      print(f"  time driver:        {profile.build.time_driver}")
      print(f"  config header:      {profile.build.config_header}")
      print(f"  features enable:    {list(profile.features.enable)}")
      print(f"  project root:       {profile.layout.project_root}")
      print(f"  build root:         {profile.layout.build_root}")
      print(f"  source root:        {profile.layout.source_root}")
      print(f"  output root:        {profile.layout.output_root}")
      print(f"  archive:            {profile.output.archive}")
      print()

      print("Toolchain")
      print(f"  path:               {toolchain.path}")
      print(f"  name:               {toolchain.name}")
      print(f"  extends:            {toolchain.extends}")
      print(f"  family:             {toolchain.settings.family}")
      print(f"  cc:                 {toolchain.tools.cc}")
      print(f"  cxx:                {toolchain.tools.cxx}")
      print(f"  ar:                 {toolchain.tools.ar}")
      print(f"  asm:                {toolchain.tools.asm}")
      print(f"  debug:              {toolchain.settings.debug}")
      print(f"  optimization:       {toolchain.settings.optimization}")
      print(f"  warnings as errors: {toolchain.settings.warnings_as_errors}")
      print(f"  use modules:        {toolchain.settings.use_modules}")
      print(f"  common flags:       {list(toolchain.flags.common)}")
      print(f"  c flags:            {list(toolchain.flags.c)}")
      print(f"  cxx flags:          {list(toolchain.flags.cxx)}")
      print(f"  asm flags:          {list(toolchain.flags.asm)}")
      print(f"  link flags:         {list(toolchain.flags.link)}")

      return 0