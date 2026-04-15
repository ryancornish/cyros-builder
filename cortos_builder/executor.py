import subprocess

from cortos_builder.actions import ArchiveAction, CompileAction, LinkAction


def execute_actions(actions: list, *, verbose: bool = False) -> None:
   for action in actions:
      output = getattr(action, "output", None)
      if output is not None:
         output.parent.mkdir(parents=True, exist_ok=True)

      if verbose:
         print(" ".join(action.arguments))

      subprocess.run(action.arguments, check=True)
