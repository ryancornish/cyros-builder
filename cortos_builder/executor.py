import subprocess

from cortos_builder.actions import RunTestAction


def execute_actions(actions: list, *, verbose: bool = False) -> None:
   for action in actions:
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

      subprocess.run(action.arguments, check=True, cwd=str(cwd) if cwd is not None else None)