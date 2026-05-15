import subprocess

from cortos_builder.ui import format_command


def execute_actions(actions: list, *, verbose: bool = False, project_root=None) -> None:
   for action in actions:
      output = getattr(action, "output", None)
      if output is not None:
         output.parent.mkdir(parents=True, exist_ok=True)

      cwd = getattr(action, "working_directory", None)
      if cwd is not None:
         cwd.mkdir(parents=True, exist_ok=True)

      if verbose:
         # if project_root is not None:
         #    if cwd is not None:
         #       print(f"$ (cd {format_command((str(cwd),), project_root)})")
         #    print(f"$ {format_command(action.arguments, project_root)}")
         # else:
            print(f"$ {' '.join(action.arguments)}")

      subprocess.run(action.arguments, check=True, cwd=str(cwd) if cwd is not None else None)
