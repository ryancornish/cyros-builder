from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from pathlib import Path

from cyros_builder.errors import BuilderError


class Command(ABC):
   name: str = ""
   help: str = ""

   @abstractmethod
   def configure_parser(self, parser: ArgumentParser) -> None:
      pass

   @abstractmethod
   def run(self, args: Namespace) -> int:
      pass


def add_profile_arg(parser: ArgumentParser, *, required: bool = True) -> None:
   parser.add_argument(
      "-p", "--profile",
      type=Path,
      required=required,
      help="Path to a Cyros build profile TOML file.",
   )


def add_toolchain_arg(parser: ArgumentParser, *, required: bool = False) -> None:
   parser.add_argument(
      "-t", "--toolchain",
      type=Path,
      required=required,
      help="Path to a toolchain TOML file. Overrides the toolchain set in the profile.",
   )


def add_config_arg(parser: ArgumentParser, *, required: bool = False) -> None:
   parser.add_argument(
      "-c", "--config",
      type=Path,
      required=required,
      help="Path to a Cyros configuration header (.hpp). Overrides config_header in the profile.",
   )


def add_output_arg(parser: ArgumentParser, *, required: bool = False) -> None:
   parser.add_argument(
      "-o", "--output",
      type=Path,
      required=required,
      help="Output root directory. Overrides output_root in the profile layout.",
   )


def add_jobs_arg(parser: ArgumentParser) -> None:
   parser.add_argument(
      "-j", "--jobs",
      type=int,
      default=1,
      help="Maximum number of parallel jobs (default: 1).",
   )


def add_force_arg(parser: ArgumentParser) -> None:
   parser.add_argument(
      "--force",
      action="store_true",
      help=(
         "Rebuild everything, bypassing the incremental up-to-date check. "
         "Unlike --clean-first this deletes nothing, so it is the safe way to "
         "rule out stale build state."
      ),
   )


def add_verbose_arg(parser: ArgumentParser) -> None:
   parser.add_argument(
      "-v", "--verbose",
      action="store_true",
      help="Print each command before executing it.",
   )


@contextmanager
def step(action_desc: str):
   """
   Wrap a command step: on any exception, re-raise as a BuilderError prefixed
   with action_desc, chained from the original so --debug can still show it.
   """
   try:
      yield
   except Exception as exc:
      raise BuilderError(f"{action_desc}: {exc}") from exc