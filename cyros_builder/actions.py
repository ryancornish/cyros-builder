from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildAction:
   pass


# ---------------------------------------------------------------------------
# Test actions — separate hierarchy so the executor and planner can treat
# them distinctly (important for coverage instrumentation later).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TestAction:
   pass


@dataclass(frozen=True)
class CompileTestAction(TestAction):
   """Compile a single test translation unit into an object file."""
   test_name: str
   source: Path
   output: Path
   arguments: tuple[str, ...]
   working_directory: Path


@dataclass(frozen=True)
class LinkTestAction(TestAction):
   """Link a compiled test object + cyros archive into a test binary."""
   test_name: str
   inputs: tuple[Path, ...]   # [test.o, libcyros.a]
   output: Path               # the executable
   arguments: tuple[str, ...]
   working_directory: Path


@dataclass(frozen=True)
class RunTestAction(TestAction):
   """Execute a test binary and capture its result.

   Kept as a discrete action type so a future coverage pass can wrap or
   replace execution (e.g. run under lcov, valgrind, etc.) without changing
   the surrounding pipeline.
   """
   test_name: str
   binary: Path
   working_directory: Path


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