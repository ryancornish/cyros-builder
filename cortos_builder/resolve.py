from dataclasses import dataclass
from argparse import Namespace
from pathlib import Path
from cortos_builder.profile import Profile, load_profile
from cortos_builder.project import resolve_project_root
from cortos_builder.toolchain import Toolchain, resolve_toolchain


@dataclass(frozen=True)
class ResolvedInvocation:
   project_root: Path
   profile: Profile
   toolchain: Toolchain
   selected_toolchain_name: str
   cli_overrode_toolchain: bool


def resolve_profile_and_toolchain(args: Namespace) -> ResolvedInvocation:
   project_root = resolve_project_root(getattr(args, "root", None))
   profile = load_profile(args.profile)

   toolchain_name = args.toolchain or profile.default_toolchain
   if toolchain_name is None:
      raise ValueError(
         "No toolchain specified. "
         "Provide --toolchain or set default_toolchain in the profile."
      )

   toolchain = resolve_toolchain(toolchain_name, project_root)

   return ResolvedInvocation(
      project_root=project_root,
      profile=profile,
      toolchain=toolchain,
      selected_toolchain_name=toolchain_name,
      cli_overrode_toolchain=(args.toolchain is not None),
   )
