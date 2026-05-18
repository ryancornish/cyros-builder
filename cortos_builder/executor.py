import subprocess
from pathlib import Path

from cortos_builder.actions import (
   ArchiveAction,
   CompileAction,
   CompileTestAction,
   LinkAction,
   LinkTestAction,
   ObjcopyAction,
   PartialLinkAction,
   RunTestAction,
)


def execute_actions(actions: list, *, verbose: bool = False) -> None:
   total = len(actions)
   width = len(str(total))

   for i, action in enumerate(actions, start=1):
      # RunTestAction is handled by the test runner directly (so results can
      # be captured per-test). It must not appear in a regular action list.
      if isinstance(action, RunTestAction):
         raise TypeError(
            "RunTestAction must not be passed to execute_actions; "
            "use test_runner._execute_test() instead."
         )

      output = getattr(action, "output", None)
      if output is not None:
         output.parent.mkdir(parents=True, exist_ok=True)

      cwd = getattr(action, "working_directory", None)
      if cwd is not None:
         cwd.mkdir(parents=True, exist_ok=True)

      if verbose:
         print(f"$ {' '.join(action.arguments)}")
      else:
         print(f"[{i:{width}}/{total}] {_progress_label(action)}")

      subprocess.run(action.arguments, check=True, cwd=str(cwd) if cwd is not None else None)


def _progress_label(action) -> str:
   if isinstance(action, CompileAction):
      return f"compile       [{action.component}] {_name(action.source)}"
   if isinstance(action, CompileTestAction):
      return f"compile-test  [{action.test_name}] {_name(action.source)}"
   if isinstance(action, ArchiveAction):
      return f"archive       {_name(action.output)}"
   if isinstance(action, LinkAction):
      return f"link          {_name(action.output)}"
   if isinstance(action, LinkTestAction):
      return f"link-test     [{action.test_name}] {_name(action.output)}"
   if isinstance(action, PartialLinkAction):
      return f"partial-link  {_name(action.output)}"
   if isinstance(action, ObjcopyAction):
      return f"objcopy       {_name(action.output)}"
   return type(action).__name__


def _name(path: Path) -> str:
   return path.name