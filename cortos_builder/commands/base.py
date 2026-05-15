from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from pathlib import Path


class Command(ABC):
   name: str = ""
   help: str = ""

   @abstractmethod
   def configure_parser(self, parser: ArgumentParser) -> None:
      pass

   @abstractmethod
   def run(self, args: Namespace) -> int:
      pass


# Generic arguments
def add_root_arg(parser: ArgumentParser, *, required: bool = False) -> None:
   parser.add_argument(
      "--root",
      type=Path,
      required=required,
      help="Path to the CoRTOS project root. Defaults to the current working directory.",
   )

def add_profile_arg(parser: ArgumentParser, *, required: bool = False) -> None:
   parser.add_argument(
      "-p", "--profile",
      type=Path,
      required=required,
      help="Path to a CoRTOS build profile TOML file.",
   )

def add_toolchain_arg(parser: ArgumentParser, *, required: bool = False) -> None:
   parser.add_argument(
      "-t", "--toolchain",
      type=str,
      required=required,
      help="Toolchain name, e.g. gcc-debug, gcc-release, clangd. If not specified, defaults to toolchain within profile.",
   )

def add_config_arg(parser: ArgumentParser, *, required: bool = False) -> None:
   parser.add_argument(
      "-c", "--config",
      type=str,
      required=required,
      help="Path to CoRTOS configuration header. If not specified, defaults to config_header within profile.",
   )

def add_jobs_arg(parser: ArgumentParser) -> None:
   parser.add_argument(
      "--jobs", "-j",
      type=int,
      default=1,
      help="Maximum number of parallel jobs (Default: 1).",
   )

def add_verbose_arg(parser: ArgumentParser) -> None:
   parser.add_argument(
      "--verbose", "-v",
      action="store_true",
      help="Print detailed command execution output.",
   )
