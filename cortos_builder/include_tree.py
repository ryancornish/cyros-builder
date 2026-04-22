from pathlib import Path
import shutil

from cortos_builder.output import include_dir
from cortos_builder.project_model import collect_public_headers, select_project
from cortos_builder.resolve import ResolvedInvocation


def populate_include_tree(resolved: ResolvedInvocation) -> None:
   """Populate the single generated public include tree for the selected build."""
   root = resolved.project_root
   selected = select_project(root, resolved.profile)
   out_include = include_dir(resolved).resolve()

   if out_include.exists():
      shutil.rmtree(out_include)
   out_include.mkdir(parents=True, exist_ok=True)

   for export in collect_public_headers(selected):
      _copy_file(export.source, out_include / export.destination, "public header")

   config_src = resolved.profile.build.config
   config_dst = out_include / "cortos" / "config.hpp"
   _copy_file(config_src, config_dst, "profile config header")

   port_contract_src = _resolve_port_contract_header(root)
   port_contract_dst = out_include / "cortos" / "port.h"
   _copy_file(port_contract_src, port_contract_dst, "port contract header")

   port_traits_src = _resolve_port_traits_header(root, resolved.profile.build.port)
   port_traits_dst = out_include / "cortos" / "port" / "port_traits.h"
   _copy_file(port_traits_src, port_traits_dst, "port traits header")

   simulation_src = _resolve_optional_simulation_header(root, resolved.profile.build.time_driver)
   if simulation_src is not None:
      simulation_dst = out_include / "cortos" / "time" / "simulation.hpp"
      _copy_file(simulation_src, simulation_dst, "simulation time header")


def _resolve_port_contract_header(project_root: Path) -> Path:
   path = project_root / "src" / "port" / "port.h"
   if not path.is_file():
      raise FileNotFoundError(f"Missing common port contract header at: {path}")
   return path.resolve()


def _resolve_port_traits_header(project_root: Path, port_name: str) -> Path:
   path = project_root / "src" / "port" / port_name / "port_traits.h"
   if not path.is_file():
      raise FileNotFoundError(
         f"Selected port '{port_name}' does not provide port_traits.h at: {path}"
      )
   return path.resolve()


def _resolve_optional_simulation_header(project_root: Path, time_driver_name: str) -> Path | None:
   path = project_root / "src" / "time" / time_driver_name / "simulation.hpp"
   if path.is_file():
      return path.resolve()
   return None


def _copy_file(src: Path, dst: Path, desc: str) -> None:
   if not src.is_file():
      raise FileNotFoundError(f"Missing {desc}: {src}")
   dst.parent.mkdir(parents=True, exist_ok=True)
   shutil.copy2(src, dst)
