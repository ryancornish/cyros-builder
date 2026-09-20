"""
consumer_model.py — discovery for consumer projects, the top layer of the suite.

A consumer is a small standalone project that builds against the EXPORTED tree
and links the archive, exactly as a real user would. That makes it the only
thing in the suite that can catch a break in the exported surface: every unit
test compiles against the same generated include tree as the library itself, so
a header that fails to be exported, or exports something it should not, is
invisible to all of them.

They are built by shelling out to each project's own `build.sh` rather than by
the builder linking an executable itself. That is a deliberate, cheap choice
(T1 decision 4, taken 2026-09-20): the builder has never produced an executable
and teaching it to is a real new capability with its own flags, system
libraries and output kinds. The cost of the cheap version is that each
build.sh hardcodes its compiler, so a consumer run inherits whatever pins those
scripts carry.

The reason they are in the runner at all: all three were unbuildable for several
commits in 2026-09 and nobody noticed, because nothing ran them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cyros_builder import tomlutil
from cyros_builder.test_model import DEFAULT_KIND, KINDS, HarnessDebt


@dataclass(frozen=True)
class ConsumerCase:
   """One consumer project.

   Deliberately exposes the same attributes the layered runner reads off a
   TestCase (`name`, `layer`, `kind`, `harness_debt`, `run_rank`,
   `port_filter`), so the runner orders and blocks both kinds the same way
   without knowing which it is holding.
   """
   path: Path                    # directory containing consumer.toml
   name: str
   layer: int
   kind: str
   harness_debt: HarnessDebt | None
   port_filter: tuple[str, ...]
   script: Path                  # the project's own build script
   binary: Path | None           # what to run afterwards, None to only build

   @property
   def run_rank(self) -> int:
      return max(self.layer, self.harness_debt.layer) if self.harness_debt else self.layer


def find_consumer_root(source_root: Path) -> Path:
   """<source_root>/../tests/consumer, alongside the unit test root."""
   return (source_root / ".." / "tests" / "consumer").resolve()


def discover_consumers(source_root: Path) -> list[ConsumerCase]:
   """Every consumer project, sorted by name. Empty when the tree has none."""
   root = find_consumer_root(source_root)
   if not root.is_dir():
      return []
   return [load_consumer(p) for p in sorted(root.glob("*/consumer.toml"))]


def load_consumer(path: Path) -> ConsumerCase:
   toml_path = path.resolve()
   base = toml_path.parent

   raw = tomlutil.load_toml(toml_path)
   consumer_raw = tomlutil.expect_table(raw, "consumer", toml_path)

   name = tomlutil.require_str(consumer_raw, "name", toml_path)

   if "layer" not in consumer_raw:
      raise ValueError(
         f"{toml_path}: 'consumer.layer' is required, like every other test in "
         f"the chain. See ~/cyros-claude/test-layering-proposal.md section 3."
      )
   layer = consumer_raw["layer"]
   if not isinstance(layer, int) or isinstance(layer, bool) or layer < 0:
      raise ValueError(f"{toml_path}: 'consumer.layer' must be a non-negative integer")

   kind = tomlutil.optional_str_default(consumer_raw, "kind", toml_path, DEFAULT_KIND)
   if kind not in KINDS:
      raise ValueError(f"{toml_path}: 'consumer.kind' must be one of {', '.join(KINDS)}")

   script = tomlutil.require_existing_file(
      (base / tomlutil.require_str(consumer_raw, "script", toml_path)).resolve(),
      "consumer.script", toml_path,
   )

   # The binary is produced BY the script, so it cannot be checked for existence
   # here. It is checked after the build, where a missing one is a real failure.
   binary_value = tomlutil.optional_nonempty_str(consumer_raw, "binary", toml_path)
   binary = (base / binary_value).resolve() if binary_value else None

   components_raw = raw.get("components", {})
   if not isinstance(components_raw, dict):
      raise ValueError(f"{toml_path}: expected [components] to be a table if present")
   port_filter = tuple(tomlutil.optional_str_or_str_list(components_raw, "port", toml_path))

   return ConsumerCase(
      path=base, name=name, layer=layer, kind=kind, harness_debt=None,
      port_filter=port_filter, script=script, binary=binary,
   )
