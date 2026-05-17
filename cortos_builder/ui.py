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


def print_action_plan(actions: list) -> None:
   print(f"Planned {len(actions)} build actions")
   print()

   for i, action in enumerate(actions):
      is_last = i == len(actions) - 1
      branch = "\u2514\u2500" if is_last else "\u251c\u2500"
      indent = "   " if is_last else "\u2502  "

      if isinstance(action, CompileAction):
         _print_compile_action(action, branch, indent)
      elif isinstance(action, ArchiveAction):
         _print_archive_action(action, branch, indent)
      elif isinstance(action, LinkAction):
         _print_link_action(action, branch, indent)
      elif isinstance(action, PartialLinkAction):
         _print_partial_link_action(action, branch, indent)
      elif isinstance(action, ObjcopyAction):
         _print_objcopy_action(action, branch, indent)
      elif isinstance(action, CompileTestAction):
         _print_compile_test_action(action, branch, indent)
      elif isinstance(action, LinkTestAction):
         _print_link_test_action(action, branch, indent)
      elif isinstance(action, RunTestAction):
         _print_run_test_action(action, branch, indent)
      else:
         print(f"{branch} unknown action: {type(action).__name__}")


def _print_compile_action(action: CompileAction, branch: str, indent: str) -> None:
   print(f"{branch} compile        [{action.component}] {_rel(action.source)}")
   print(f"{indent}├─ output:      {_rel(action.output)}")
   print(f"{indent}└─ language:    {action.language}")


def _print_archive_action(action: ArchiveAction, branch: str, indent: str) -> None:
   print(f"{branch} archive")
   print(f"{indent}├─ output:      {_rel(action.output)}")
   print(f"{indent}└─ inputs:      {len(action.inputs)} objects")


def _print_link_action(action: LinkAction, branch: str, indent: str) -> None:
   print(f"{branch} link")
   print(f"{indent}├─ output:      {_rel(action.output)}")
   print(f"{indent}└─ inputs:      {len(action.inputs)} objects")


def _print_partial_link_action(action: PartialLinkAction, branch: str, indent: str) -> None:
   print(f"{branch} partial-link")
   print(f"{indent}├─ output:      {_rel(action.output)}")
   print(f"{indent}└─ inputs:      {len(action.inputs)} objects")


def _print_objcopy_action(action: ObjcopyAction, branch: str, indent: str) -> None:
   print(f"{branch} objcopy")
   print(f"{indent}├─ input:       {_rel(action.input)}")
   print(f"{indent}└─ output:      {_rel(action.output)}")


def format_command(arguments: tuple[str, ...] | list[str]) -> str:
   return " ".join(_pretty_arg(arg) for arg in arguments)


def _pretty_arg(arg: str) -> str:
   p = Path(arg)
   if p.is_absolute():
      try:
         return str(p.relative_to(Path.cwd()))
      except ValueError:
         return str(p)
   return arg


def _rel(path: Path) -> str:
   try:
      return str(path.resolve().relative_to(Path.cwd().resolve()))
   except ValueError:
      return str(path.resolve())

def _print_compile_test_action(action: CompileTestAction, branch: str, indent: str) -> None:
   print(f"{branch} compile-test   [{action.test_name}] {_rel(action.source)}")
   print(f"{indent}└─ output:      {_rel(action.output)}")


def _print_link_test_action(action: LinkTestAction, branch: str, indent: str) -> None:
   print(f"{branch} link-test      [{action.test_name}]")
   print(f"{indent}├─ output:      {_rel(action.output)}")
   print(f"{indent}└─ inputs:      {len(action.inputs)} files")


def _print_run_test_action(action: RunTestAction, branch: str, indent: str) -> None:
   print(f"{branch} run-test       [{action.test_name}] {_rel(action.binary)}")