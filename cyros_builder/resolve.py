from dataclasses import dataclass
from argparse import Namespace
from pathlib import Path

from cyros_builder.profile import Profile, load_profile
from cyros_builder.toolchain import Toolchain, resolve_toolchain


@dataclass(frozen=True)
class ResolvedInvocation:
   profile_root: Path
   profile: Profile
   toolchain: Toolchain
   selected_toolchain_name: str
   cli_overrode_toolchain: bool
   config_header: Path
   cli_overrode_config: bool
   output_root: Path
   cli_overrode_output: bool


def resolve_invocation(args: Namespace) -> ResolvedInvocation:
   profile = load_profile(Path(args.profile))

   # --- toolchain ---
   cli_overrode_toolchain = getattr(args, "toolchain", None) is not None
   if cli_overrode_toolchain:
      toolchain_path = Path(args.toolchain).resolve()
   elif profile.toolchain is not None:
      toolchain_path = profile.toolchain
   else:
      raise ValueError(
         "No toolchain specified. "
         "Provide -t/--toolchain <path> or set toolchain in the profile."
      )
   toolchain = resolve_toolchain(toolchain_path)

   # --- config header ---
   cli_overrode_config = getattr(args, "config", None) is not None
   if cli_overrode_config:
      config_header = Path(args.config).resolve()
      if not config_header.is_file():
         raise ValueError(f"Config header not found: {config_header}")
   elif profile.config_header is not None:
      config_header = profile.config_header
   else:
      raise ValueError(
         "No configuration header specified. "
         "Provide -c/--config <path> or set config_header in the profile."
      )

   # --- output root ---
   cli_overrode_output = getattr(args, "output", None) is not None
   if cli_overrode_output:
      output_root = Path(args.output).resolve()
   else:
      output_root = profile.layout.output_root

   return ResolvedInvocation(
      profile_root=profile.path.parent,
      profile=profile,
      toolchain=toolchain,
      selected_toolchain_name=toolchain.name,
      cli_overrode_toolchain=cli_overrode_toolchain,
      config_header=config_header,
      cli_overrode_config=cli_overrode_config,
      output_root=output_root,
      cli_overrode_output=cli_overrode_output,
   )