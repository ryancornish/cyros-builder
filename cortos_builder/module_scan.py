from dataclasses import dataclass
from pathlib import Path
import re


_EXPORT_MODULE_RE = re.compile(r"^\s*export\s+module\s+([A-Za-z_][A-Za-z0-9_.:]*)\s*;")
_MODULE_RE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z0-9_.:]*)\s*;")
_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_.:]*)\s*;")


@dataclass(frozen=True)
class ModuleInfo:
   source: Path
   provided_module: str | None
   is_interface: bool
   implementation_of: str | None
   imports: tuple[str, ...]


def scan_module_info(path: Path) -> ModuleInfo:
   provided_module: str | None = None
   is_interface = False
   implementation_of: str | None = None
   imports: list[str] = []

   text = path.read_text(encoding="utf-8")

   for line in text.splitlines():
      if provided_module is None:
         m = _EXPORT_MODULE_RE.match(line)
         if m:
            provided_module = m.group(1)
            is_interface = True
            continue

      if implementation_of is None and provided_module is None:
         m = _MODULE_RE.match(line)
         if m:
            implementation_of = m.group(1)
            continue

      m = _IMPORT_RE.match(line)
      if m:
         imports.append(m.group(1))

   return ModuleInfo(
      source=path.resolve(),
      provided_module=provided_module,
      is_interface=is_interface,
      implementation_of=implementation_of,
      imports=tuple(imports),
   )
