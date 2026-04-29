from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildAction:
   pass


@dataclass(frozen=True)
class CompileAction(BuildAction):
   component: str
   source: Path
   output: Path
   language: str
   kind: str
   arguments: tuple[str, ...]
   working_directory: Path


@dataclass(frozen=True)
class ArchiveAction(BuildAction):
   inputs: tuple[Path, ...]
   output: Path
   arguments: tuple[str, ...]
   working_directory: Path


@dataclass(frozen=True)
class LinkAction(BuildAction):
   inputs: tuple[Path, ...]
   output: Path
   arguments: tuple[str, ...]
   working_directory: Path


@dataclass(frozen=True)
class PartialLinkAction(BuildAction):
   inputs: tuple[Path, ...]
   output: Path
   arguments: tuple[str, ...]
   working_directory: Path


@dataclass(frozen=True)
class ObjcopyAction(BuildAction):
   input: Path
   output: Path
   arguments: tuple[str, ...]
   working_directory: Path