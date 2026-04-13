from dataclasses import dataclass
from pathlib import Path


@dataclass
class Profile:
   name: str
   port: str
   time_driver: str
   config: Path
   tests: bool
   assertions: bool
   default_toolchain: str | None = None