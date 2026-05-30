from argparse import ArgumentParser, Namespace
import json

from cyros_builder.commands.base import (
   Command,
   add_config_arg,
   add_output_arg,
   add_profile_arg,
   add_toolchain_arg,
)
from cyros_builder.resolve import resolve_invocation


class ShowCommand(Command):
   name = "show"
   help = "Show the resolved effective configuration for a profile and toolchain."

   def configure_parser(self, parser: ArgumentParser) -> None:
      add_profile_arg(parser)
      add_toolchain_arg(parser)
      add_config_arg(parser)
      add_output_arg(parser)
      parser.add_argument(
         "--format",
         choices=["text", "json"],
         default="text",
         help="Output format.",
      )

   def run(self, args: Namespace) -> int:
      try:
         resolved = resolve_invocation(args)
      except Exception as exc:
         print(f"Failed to resolve invocation: {exc}")
         return 1

      profile  = resolved.profile
      toolchain = resolved.toolchain

      if args.format == "json":
         data = {
            "profile": {
               "path": str(profile.path),
               "name": profile.name,
               "toolchain": str(profile.toolchain) if profile.toolchain else None,
               "config_header": str(profile.config_header) if profile.config_header else None,
               "layout": {
                  "source_root": str(profile.layout.source_root),
                  "output_root": str(profile.layout.output_root),
               },
               "components": {
                  "port": profile.components.port,
                  "time_driver": profile.components.time_driver,
               },
               "features": list(profile.features.enable),
               "output": {
                  "archive": profile.output.archive,
               },
            },
            "toolchain": {
               "path": str(toolchain.path),
               "name": toolchain.name,
               "extends": str(toolchain.extends) if toolchain.extends else None,
               "tools": {
                  "cc":  toolchain.tools.cc,
                  "cxx": toolchain.tools.cxx,
                  "ar":  toolchain.tools.ar,
                  "asm": toolchain.tools.asm,
               },
               "flags": {
                  "common": list(toolchain.flags.common),
                  "c":      list(toolchain.flags.c),
                  "cxx":    list(toolchain.flags.cxx),
                  "asm":    list(toolchain.flags.asm),
                  "link":   list(toolchain.flags.link),
               },
               "settings": {
                  "family":             toolchain.settings.family,
                  "debug":              toolchain.settings.debug,
                  "optimization":       toolchain.settings.optimization,
                  "warnings_as_errors": toolchain.settings.warnings_as_errors,
               },
               "archive": {
                  "strategy":                toolchain.archive.strategy,
                  "filter_exported_symbols": toolchain.archive.filter_exported_symbols,
                  "preserve_lto_sections":   toolchain.archive.preserve_lto_sections,
               },
            },
            "resolved": {
               "output_root":           str(resolved.output_root),
               "config_header":         str(resolved.config_header),
               "cli_overrode_toolchain": resolved.cli_overrode_toolchain,
               "cli_overrode_config":    resolved.cli_overrode_config,
               "cli_overrode_output":    resolved.cli_overrode_output,
            },
         }
         print(json.dumps(data, indent=2))
         return 0

      # --- text output ---
      _section("Profile")
      _field("path",         profile.path)
      _field("name",         profile.name)
      _field("toolchain",    profile.toolchain    or "(none — must be specified via -t)")
      _field("config header", profile.config_header or "(none — must be specified via -c)")
      _field("source root",  profile.layout.source_root)
      _field("output root",  profile.layout.output_root)
      _field("port",         profile.components.port)
      _field("time driver",  profile.components.time_driver)
      _field("features",     list(profile.features.enable) or "[]")
      _field("archive",      profile.output.archive)
      print()

      _section("Toolchain")
      _field("path",               toolchain.path)
      _field("name",               toolchain.name)
      _field("extends",            toolchain.extends or "(none)")
      _field("family",             toolchain.settings.family)
      _field("cc",                 toolchain.tools.cc)
      _field("cxx",                toolchain.tools.cxx)
      _field("ar",                 toolchain.tools.ar)
      _field("asm",                toolchain.tools.asm or "(uses cc)")
      _field("debug",              toolchain.settings.debug)
      _field("optimization",       toolchain.settings.optimization)
      _field("warnings as errors", toolchain.settings.warnings_as_errors)
      _field("archive strategy",   toolchain.archive.strategy)
      _field("common flags",       list(toolchain.flags.common))
      _field("c flags",            list(toolchain.flags.c))
      _field("cxx flags",          list(toolchain.flags.cxx))
      _field("asm flags",          list(toolchain.flags.asm))
      _field("link flags",         list(toolchain.flags.link))
      print()

      _section("Resolved")
      _field("output root",   resolved.output_root,
             " (cli override)" if resolved.cli_overrode_output   else "")
      _field("config header", resolved.config_header,
             " (cli override)" if resolved.cli_overrode_config   else "")
      _field("toolchain",     resolved.selected_toolchain_name,
             " (cli override)" if resolved.cli_overrode_toolchain else "")

      return 0


def _section(title: str) -> None:
   print(title)


def _field(label: str, value, suffix: str = "") -> None:
   print(f"  {label:<22} {value}{suffix}")