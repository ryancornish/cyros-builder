from dataclasses import dataclass
from argparse import Namespace
from pathlib import Path
from cortos_builder.profile import Profile, load_profile
from cortos_builder.toolchain import Toolchain, resolve_toolchain


@dataclass(frozen=True)
class ResolvedInvocation:
   profile_root: Path
   profile: Profile
   toolchain: Toolchain
   selected_toolchain_name: str
   cli_overrode_toolchain: bool
   config_header: Path
   cli_overrode_config: bool


def resolve_profile_and_toolchain(args: Namespace) -> ResolvedInvocation:
   profile = load_profile(Path(args.profile))

   toolchain_path = args.toolchain or profile.toolchain
   if toolchain_path is None:
      raise ValueError(
         "No toolchain specified. "
         "Provide --toolchain or set toolchain in the profile."
      )
   toolchain = resolve_toolchain(toolchain_path)

   config_header_path = args.config or profile.config_header
   if config_header_path is None:
      raise ValueError(
         "No configuration header specified. "
         "Provide --config or set config_header in the profile."
      )

   return ResolvedInvocation(
      profile_root=profile.path.parent,
      profile=profile,
      toolchain=toolchain,
      selected_toolchain_name=toolchain.name,
      cli_overrode_toolchain=(args.toolchain is not None),
      config_header=Path(config_header_path).resolve(),
      cli_overrode_config=(args.config is not None)
   )
