import subprocess


def execute_actions(actions: list, *, verbose: bool = False) -> None:
   for action in actions:
      output = getattr(action, "output", None)
      if output is not None:
         output.parent.mkdir(parents=True, exist_ok=True)

      cwd = getattr(action, "working_directory", None)
      if cwd is not None:
         cwd.mkdir(parents=True, exist_ok=True)

      if verbose:
         print(f"$ {' '.join(action.arguments)}")

      subprocess.run(action.arguments, check=True, cwd=str(cwd) if cwd is not None else None)