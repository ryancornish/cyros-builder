from pathlib import Path
import shutil

from cortos_builder.output import include_dir
from cortos_builder.resolve import ResolvedInvocation


def populate_include_tree(resolved: ResolvedInvocation) -> None:
   """
   Populate the generated include tree for the selected build.

   For v1 this copies:
   - the selected profile config header to include/cortos/config.hpp
   - the selected port traits header to include/cortos/port_traits.h
   """
   root = resolved.project_root
   out_include = include_dir(resolved) / "cortos"
   out_include.mkdir(parents=True, exist_ok=True)

   config_src = resolved.profile.build.config
   config_dst = out_include / "config.hpp"
   _copy_file(config_src, config_dst, "profile config header")

   port_traits_src = _resolve_port_traits_header(root, resolved.profile.build.port)
   port_traits_dst = out_include / "port_traits.h"
   _copy_file(port_traits_src, port_traits_dst, "port traits header")


def _resolve_port_traits_header(project_root: Path, port_name: str) -> Path:
   path = project_root / "src" / "port" / port_name / "port_traits.h"
   if not path.is_file():
      raise FileNotFoundError(
         f"Selected port '{port_name}' does not provide port_traits.h at: {path}"
      )
   return path.resolve()


def _copy_file(src: Path, dst: Path, desc: str) -> None:
   if not src.is_file():
      raise FileNotFoundError(f"Missing {desc}: {src}")
   dst.parent.mkdir(parents=True, exist_ok=True)
   shutil.copy2(src, dst)