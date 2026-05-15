from pathlib import Path

from cortos_builder.actions import (
   ArchiveAction,
   CompileAction,
   LinkAction,
   ObjcopyAction,
   PartialLinkAction,
)


def print_action_plan(actions: list) -> None:
   print(f"Planned {len(actions)} build actions")
   print()

   for i, action in enumerate(actions):
      is_last = i == len(actions) - 1
      branch = "└─" if is_last else "├─"
      indent = "   " if is_last else "│  "

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
      else:
         print(f"{branch} unknown action: {type(action).__name__}")


def _print_compile_action(action: CompileAction, branch: str, indent: str) -> None:
   label = "compile-module" if action.kind == "module_interface" else "compile"
   print(f"{branch} {label:<14} [{action.component}] {_rel(action.source)}")
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