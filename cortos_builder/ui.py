from pathlib import Path

from cortos_builder.actions import (
   ArchiveAction,
   CompileAction,
   LinkAction,
   ObjcopyAction,
   PartialLinkAction,
)


def print_action_plan(actions: list, project_root: Path) -> None:
   print(f"Planned {len(actions)} build actions")
   print()

   for i, action in enumerate(actions):
      is_last = i == len(actions) - 1
      branch = "└─" if is_last else "├─"
      indent = "   " if is_last else "│  "

      if isinstance(action, CompileAction):
         _print_compile_action(action, project_root, branch, indent)
      elif isinstance(action, ArchiveAction):
         _print_archive_action(action, project_root, branch, indent)
      elif isinstance(action, LinkAction):
         _print_link_action(action, project_root, branch, indent)
      elif isinstance(action, PartialLinkAction):
         _print_partial_link_action(action, project_root, branch, indent)
      elif isinstance(action, ObjcopyAction):
         _print_objcopy_action(action, project_root, branch, indent)
      else:
         print(f"{branch} unknown action: {type(action).__name__}")


def _print_compile_action(action: CompileAction, project_root: Path, branch: str, indent: str) -> None:
   label = "compile-module" if action.kind == "module_interface" else "compile"
   print(f"{branch} {label:<14} [{action.component}] {_rel(action.source, project_root)}")
   print(f"{indent}├─ output:      {_rel(action.output, project_root)}")
   print(f"{indent}└─ language:    {action.language}")


def _print_archive_action(action: ArchiveAction, project_root: Path, branch: str, indent: str) -> None:
   print(f"{branch} archive")
   print(f"{indent}├─ output:      {_rel(action.output, project_root)}")
   print(f"{indent}└─ inputs:      {len(action.inputs)} objects")


def _print_link_action(action: LinkAction, project_root: Path, branch: str, indent: str) -> None:
   print(f"{branch} link")
   print(f"{indent}├─ output:      {_rel(action.output, project_root)}")
   print(f"{indent}└─ inputs:      {len(action.inputs)} objects")


def _print_partial_link_action(action: PartialLinkAction, project_root: Path, branch: str, indent: str) -> None:
   print(f"{branch} partial-link")
   print(f"{indent}├─ output:      {_rel(action.output, project_root)}")
   print(f"{indent}└─ inputs:      {len(action.inputs)} objects")


def _print_objcopy_action(action: ObjcopyAction, project_root: Path, branch: str, indent: str) -> None:
   print(f"{branch} objcopy")
   print(f"{indent}├─ input:       {_rel(action.input, project_root)}")
   print(f"{indent}└─ output:      {_rel(action.output, project_root)}")


def format_command(arguments: tuple[str, ...] | list[str], project_root: Path) -> str:
   return " ".join(_pretty_arg(arg, project_root) for arg in arguments)


def format_cwd(cwd: Path, project_root: Path) -> str:
   return _rel(cwd, project_root)


def _pretty_arg(arg: str, project_root: Path) -> str:
   p = Path(arg)
   if p.is_absolute():
      try:
         return str(p.relative_to(project_root))
      except ValueError:
         return str(p)
   return arg


def _rel(path: Path, project_root: Path) -> str:
   try:
      return str(path.resolve().relative_to(project_root.resolve()))
   except ValueError:
      return str(path.resolve())