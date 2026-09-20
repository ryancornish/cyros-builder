"""
test_model.py — schema and discovery for cortos unit tests.

Each test case is a directory under tests/unit/** that contains a test.toml.
The test.toml declares what is unique to that test: its source file(s), the
config header it needs, and any extra system libraries to link.

Everything else (toolchain, compiler flags, cortos archive) comes from the
resolved build invocation passed in by the test runner.

Layout convention (hardcoded — unit tests are internal to cortos):

   <source_root>/             e.g. cortos/src/
   <source_root>/../tests/unit/
      kernel/
         test_function/
            test.toml
            test_function.cpp
            test_function_config.hpp
         test_multicore_multithread/
            test.toml
            ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cyros_builder import tomlutil

# The kinds of evidence a test binary produces. See T1 section 4: a unit test is
# deterministic and asserts a contract, an integration test exercises several
# layers together under realistic timing, a soak is only meaningful as a RATE so
# it does not run by default, and a measurement reports a number and asserts
# nothing.
KINDS = ("unit", "integration", "soak", "measurement")
DEFAULT_KIND = "unit"

# What a plain `test` run executes. A soak is meaningful only as a rate over
# many runs and a measurement asserts nothing, so both are noise in a pass/fail
# suite and are asked for explicitly with --kind.
DEFAULT_RUN_KINDS = ("unit", "integration")


@dataclass(frozen=True)
class HarnessDebt:
   """A test that cannot observe its subject without machinery from a HIGHER layer.

   The canonical case is `spinlock`: its contract is interrupt masking on the
   holding core and exclusion across cores, and neither exists until the kernel
   has started the cores. No rearrangement observes it earlier, so the debt is
   declared rather than pretended away. See T1 sections 3b and 3d.

   Declaring it does two things. It moves the test's RUN order up to the debt
   layer, since the machinery has to be proved first, and it makes a failure in
   that layer BLOCK this test, even though this test sits below it.
   """
   layer: int
   reason: str


@dataclass(frozen=True)
class TestCase:
   """A single discovered and validated unit test."""
   path: Path              # directory containing test.toml
   name: str               # unique name, e.g. "test_function"
   sources: tuple[Path, ...]  # resolved absolute paths to the .cpp file(s)
   config: Path            # resolved absolute path to the config header
   system_libraries: tuple[str, ...]   # e.g. ["boost_context", "gtest", "gtest_main"]
   extra_link_flags: tuple[str, ...]   # optional extra flags beyond the toolchain default
   port_filter: tuple[str, ...]        # Skip test if not belonging to filter
   # time_driver and features OVERRIDE/EXTEND the profile for this test.
   time_driver: str | None             # locked driver, or None to use the default
   features: tuple[str, ...]           # features to compile into the archive
   # T1 layering. `layer` is where the test's SUBJECT sits, which is what a
   # failure is attributed to and what blocks the layers above.
   layer: int
   kind: str
   harness_debt: HarnessDebt | None

   @property
   def run_rank(self) -> int:
      """The layer this test can first honestly be RUN at.

      Normally its own layer. A test with declared harness debt runs later,
      because the machinery it borrows has to be proved first, but it is still
      ATTRIBUTED to `layer`. Keeping the two apart is what lets spinlock sit
      below the kernel in the chain while running after it.
      """
      return max(self.layer, self.harness_debt.layer) if self.harness_debt else self.layer


def find_unit_test_root(source_root: Path) -> Path:
   """
   Return the unit test root directory.
   Hardcoded as <source_root>/../tests/unit — unit tests are internal to cortos
   and are not part of the configurable build tree.
   """
   return (source_root / ".." / "tests" / "unit").resolve()


# ---------------------------------------------------------------------------
# T1 enforcement tier 2: the static upward-trust check
#
# MECHANISM lives here, POLICY lives in cyros. The builder knows how to compare
# a test's includes against a layer table, and knows nothing about what cyros's
# units are. The table is <unit root>/layers.toml, and with no such file the
# check is simply off, so a project that has not adopted the layering still
# builds.
# ---------------------------------------------------------------------------

_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.MULTILINE)


@dataclass(frozen=True)
class LayerPolicy:
   headers: dict[str, int]          # include path -> the layer that owns it
   ungraded: frozenset[str]         # carries no layer, legal everywhere
   path: Path
   prefix: str                      # only includes under this root are graded


def load_layer_policy(unit_root: Path) -> LayerPolicy | None:
   """Read <unit_root>/layers.toml, or None when the project has no policy."""
   policy_path = unit_root / "layers.toml"
   if not policy_path.is_file():
      return None

   raw = tomlutil.load_toml(policy_path)
   # Which include root this policy governs. Everything outside it (the standard
   # library, gtest, the tests' own shared helpers) carries no layer by
   # construction and is never checked.
   prefix = tomlutil.optional_str_default(raw, "prefix", policy_path, "cyros/")
   headers_raw = raw.get("headers", {})
   if not isinstance(headers_raw, dict):
      raise ValueError(f"{policy_path}: expected [headers] to be a table")

   headers: dict[str, int] = {}
   for key, value in headers_raw.items():
      if not isinstance(value, int) or isinstance(value, bool) or value < 0:
         raise ValueError(
            f"{policy_path}: [headers] {key!r} must be a non-negative integer layer"
         )
      headers[key] = value

   ungraded_raw = raw.get("ungraded", {})
   if not isinstance(ungraded_raw, dict):
      raise ValueError(f"{policy_path}: expected [ungraded] to be a table")
   ungraded = frozenset(tomlutil.optional_str_list(ungraded_raw, "headers", policy_path))

   overlap = ungraded & headers.keys()
   if overlap:
      raise ValueError(
         f"{policy_path}: {', '.join(sorted(overlap))} appear in both [headers] "
         f"and [ungraded]. A header either carries a layer or it does not."
      )
   return LayerPolicy(headers=headers, ungraded=ungraded, path=policy_path, prefix=prefix)


def _project_includes(source: Path, prefix: str) -> list[str]:
   try:
      text = source.read_text(errors="replace")
   except OSError:
      return []
   return [m for m in _INCLUDE_RE.findall(text) if m.startswith(prefix)]


def validate_layering(cases: list[TestCase], policy: LayerPolicy) -> None:
   """Refuse a test that includes a header from a layer at or above its own.

   This is the rule that makes the layering more than a naming convention. A
   test may include its own subject's header, which is why the comparison is
   `>` and not `>=`, and a declared harness debt raises the ceiling to the debt
   layer.

   Only INCLUDES are checked, not enabled features. Feature granularity does not
   match unit granularity: the `sync` feature carries both semaphore (L6) and
   mutex (L7), so a feature-based rule would reject the semaphore tests for
   enabling the feature that contains their own subject. Includes are the
   precise signal and the feature list is not.
   """
   problems: list[str] = []

   for case in cases:
      ceiling = case.harness_debt.layer if case.harness_debt else case.layer
      for source in case.sources:
         for include in _project_includes(source, policy.prefix):
            if include in policy.ungraded:
               continue
            if include not in policy.headers:
               problems.append(
                  f"  {case.name}: includes <{include}>, which {policy.path.name} "
                  f"does not grade.\n"
                  f"    Add it to [headers] with the layer that owns it, or to "
                  f"[ungraded] if it carries no layer."
               )
               continue
            owner = policy.headers[include]
            if owner > ceiling:
               debt_note = (
                  f" (ceiling raised to {ceiling} by its declared harness debt)"
                  if case.harness_debt else ""
               )
               problems.append(
                  f"  {case.name} is at layer {case.layer}{debt_note} but includes "
                  f"<{include}>, which belongs to layer {owner}.\n"
                  f"    A test must not stand on something proved above it, or a "
                  f"failure in the scaffolding is misattributed to the subject.\n"
                  f"    Either use something lower, move the test up, or declare a "
                  f"harness debt in its test.toml saying why it cannot be observed "
                  f"any lower."
               )

   if problems:
      raise ValueError(
         "Test layering violations (see ~/cyros-claude/test-layering-proposal.md "
         "section 3):\n" + "\n".join(problems)
      )


def discover_tests(source_root: Path) -> list[TestCase]:
   """
   Walk the unit test tree and return all valid test cases, sorted by name.
   Raises if any test.toml is malformed.
   """
   unit_root = find_unit_test_root(source_root)

   if not unit_root.is_dir():
      raise FileNotFoundError(
         f"Unit test root not found: {unit_root}\n"
         f"  (resolved from source_root: {source_root})"
      )

   cases: list[TestCase] = []
   for toml_path in sorted(unit_root.rglob("test.toml")):
      cases.append(load_test_case(toml_path))

   policy = load_layer_policy(unit_root)
   if policy is not None:
      validate_layering(cases, policy)

   return cases


def load_test_case(path: Path) -> TestCase:
   """Load and validate a single test.toml."""
   toml_path = path.resolve()
   base = toml_path.parent

   raw = tomlutil.load_toml(toml_path)

   test_raw = tomlutil.expect_table(raw, "test", toml_path)

   link_raw = raw.get("link", {})
   if not isinstance(link_raw, dict):
      raise ValueError(f"{toml_path}: expected [link] to be a table if present")

   components_raw = raw.get("components", {})
   if not isinstance(components_raw, dict):
      raise ValueError(f"{toml_path}: expected [components] to be a table if present")

   name = tomlutil.require_str(test_raw, "name", toml_path)

   source_values = tomlutil.optional_str_or_str_list(test_raw, "source", toml_path)
   if not source_values:
      raise ValueError(f"{toml_path}: 'test.source' must list at least one source file")
   sources = tuple(
      tomlutil.require_existing_file((base / value).resolve(), "test.source", toml_path)
      for value in source_values
   )

   config = tomlutil.require_existing_file(
      (base / tomlutil.require_str(test_raw, "config", toml_path)).resolve(),
      "test.config", toml_path,
   )

   system_libraries = tuple(tomlutil.optional_str_list(link_raw, "system_libraries", toml_path))
   extra_link_flags = tuple(tomlutil.optional_str_list(link_raw, "flags", toml_path))

   layer = _require_layer(test_raw, toml_path)
   kind = _require_kind(test_raw, toml_path)
   harness_debt = _optional_harness_debt(test_raw, toml_path, layer=layer)

   port_filter = tuple(tomlutil.optional_str_or_str_list(components_raw, "port", toml_path))
   time_driver = tomlutil.optional_nonempty_str(components_raw, "time_driver", toml_path)
   features = tuple(tomlutil.optional_str_list(components_raw, "features", toml_path))

   return TestCase(
      path=base,
      name=name,
      sources=sources,
      config=config,
      system_libraries=system_libraries,
      extra_link_flags=extra_link_flags,
      port_filter=port_filter,
      time_driver=time_driver,
      features=features,
      layer=layer,
      kind=kind,
      harness_debt=harness_debt,
   )


# ---------------------------------------------------------------------------
# T1 layering keys
# ---------------------------------------------------------------------------

def _require_layer(test_raw: dict, toml_path: Path) -> int:
   """`layer` is mandatory, so a new test cannot quietly opt out of the chain.

   That is T1 enforcement tier 1. An unlayered test is not merely unordered, it
   is a test whose failure cannot be attributed, and the whole model rests on
   every test declaring where it sits.
   """
   if "layer" not in test_raw:
      raise ValueError(
         f"{toml_path}: 'test.layer' is required.\n"
         f"  Every test declares which layer its SUBJECT sits at, so a failure "
         f"can be attributed and the layers above it can be blocked rather than "
         f"reported as failures of their own.\n"
         f"  See ~/cyros-claude/test-layering-proposal.md section 3."
      )
   value = test_raw["layer"]
   if not isinstance(value, int) or isinstance(value, bool) or value < 0:
      raise ValueError(f"{toml_path}: 'test.layer' must be a non-negative integer, got {value!r}")
   return value


def _require_kind(test_raw: dict, toml_path: Path) -> str:
   kind = tomlutil.optional_str_default(test_raw, "kind", toml_path, DEFAULT_KIND)
   if kind not in KINDS:
      raise ValueError(
         f"{toml_path}: 'test.kind' must be one of {', '.join(KINDS)}, got {kind!r}"
      )
   return kind


def _optional_harness_debt(test_raw: dict, toml_path: Path, *, layer: int) -> HarnessDebt | None:
   raw = test_raw.get("harness_debt")
   if raw is None:
      return None
   if not isinstance(raw, dict):
      raise ValueError(f"{toml_path}: 'test.harness_debt' must be a table if present")

   debt_layer = raw.get("layer")
   if not isinstance(debt_layer, int) or isinstance(debt_layer, bool):
      raise ValueError(f"{toml_path}: 'test.harness_debt.layer' must be an integer")

   reason = tomlutil.require_str(raw, "reason", toml_path).strip()
   if not reason:
      raise ValueError(
         f"{toml_path}: 'test.harness_debt.reason' must not be empty.\n"
         f"  An undeclared debt is a false attribution claim and a declared one "
         f"is a known cost, so the reason is what makes the difference."
      )

   if debt_layer <= layer:
      raise ValueError(
         f"{toml_path}: 'test.harness_debt.layer' ({debt_layer}) must be ABOVE "
         f"the test's own layer ({layer}).\n"
         f"  Debt means borrowing machinery from a HIGHER layer. Depending on a "
         f"lower layer is ordinary and needs no declaration."
      )
   return HarnessDebt(layer=debt_layer, reason=reason)
