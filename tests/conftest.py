"""Shared fixtures and helpers for the cyros-builder test suite.

The suite asserts on what the *planner* decides, not on artifacts it produces.
`plan_build()` and `plan_test()` are pure functions from a `ResolvedInvocation`
to a list of frozen action dataclasses carrying fully materialised argv, so
serialising that list and diffing it against a golden file covers the builder's
decision-making with no compiler, no filesystem writes and no flakiness.

Golden files are regenerated with:

    CYROS_UPDATE_GOLDENS=1 pytest

Always read the resulting diff. A golden that changed because behaviour changed
is a finding; a golden that changed because a path leaked in is a bug in the
normalisation below.
"""
from __future__ import annotations

import dataclasses
import json
import os
from argparse import Namespace
from pathlib import Path

import pytest

from cyros_builder.resolve import ResolvedInvocation, resolve_invocation

TESTS_ROOT = Path(__file__).parent
FIXTURE_ROOT = (TESTS_ROOT / "fixtures" / "mini").resolve()
GOLDEN_DIR = TESTS_ROOT / "goldens"

# The real kernel repo. Conformance tests skip when it is absent, so the suite
# stays runnable on a machine that only has the builder checked out.
CYROS_ROOT = (Path.home() / "cyros").resolve()
HAVE_CYROS = (CYROS_ROOT / "src" / "kernel" / "component.toml").is_file()

requires_cyros = pytest.mark.skipif(
   not HAVE_CYROS, reason=f"real cyros checkout not present at {CYROS_ROOT}"
)


# ---------------------------------------------------------------------------
# Building a ResolvedInvocation without going through the CLI
# ---------------------------------------------------------------------------

def fixture_profile(name: str) -> Path:
   return FIXTURE_ROOT / "build" / "profiles" / f"{name}.toml"


def resolve_fixture(
   profile: str,
   *,
   toolchain: Path | None = None,
   config: Path | None = None,
   output: Path | None = None,
) -> ResolvedInvocation:
   """Resolve a fixture profile exactly as the CLI would."""
   return resolve_invocation(Namespace(
      profile=str(fixture_profile(profile)),
      toolchain=str(toolchain) if toolchain else None,
      config=str(config) if config else None,
      output=str(output) if output else None,
   ))


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _replacements(resolved: ResolvedInvocation | None) -> list[tuple[str, str]]:
   """Substitution pairs, longest needle first.

   The order is load-bearing and not merely nesting: these roots also share
   *prefixes*. `~/cyros` is a string prefix of `~/cyros-builder`, so
   substituting it first turns the builder checkout into `<CYROS>-builder`,
   which then differs between machines and layouts. Sorting by descending
   needle length makes the longest, most specific root always win and covers
   both nesting (out inside fixture inside cwd) and prefix collisions.
   """
   pairs: list[tuple[str, str]] = []
   if resolved is not None:
      pairs.append((str(resolved.output_root.resolve()), "<OUT>"))
   pairs.append((str(FIXTURE_ROOT), "<FIXTURE>"))
   if HAVE_CYROS:
      pairs.append((str(CYROS_ROOT), "<CYROS>"))
   pairs.append((str(Path.cwd().resolve()), "<CWD>"))
   return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def normalise(text: str, resolved: ResolvedInvocation | None = None) -> str:
   for needle, token in _replacements(resolved):
      text = text.replace(needle, token)
   return text


def _scrub(value, resolved):
   if isinstance(value, Path):
      return normalise(str(value), resolved)
   if isinstance(value, str):
      return normalise(value, resolved)
   if isinstance(value, (list, tuple)):
      return [_scrub(v, resolved) for v in value]
   if isinstance(value, dict):
      return {k: _scrub(v, resolved) for k, v in value.items()}
   return value


def plan_to_jsonable(actions: list, resolved: ResolvedInvocation | None = None) -> list:
   """Serialise a planned action list into stable, path-independent JSON."""
   out = []
   for action in actions:
      entry = {"action": type(action).__name__}
      for field in dataclasses.fields(action):
         entry[field.name] = _scrub(getattr(action, field.name), resolved)
      out.append(entry)
   return out


# ---------------------------------------------------------------------------
# Golden comparison
# ---------------------------------------------------------------------------

UPDATING = os.environ.get("CYROS_UPDATE_GOLDENS") == "1"


def assert_golden(name: str, payload) -> None:
   """Compare `payload` against tests/goldens/<name>.json."""
   GOLDEN_DIR.mkdir(exist_ok=True)
   path = GOLDEN_DIR / f"{name}.json"
   rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"

   if UPDATING:
      path.write_text(rendered)
      return

   if not path.exists():
      raise AssertionError(
         f"missing golden {path}. Create it with CYROS_UPDATE_GOLDENS=1 pytest"
      )

   expected = path.read_text()
   if expected != rendered:
      raise AssertionError(
         f"{path} does not match the current plan.\n"
         f"If the change is intended: CYROS_UPDATE_GOLDENS=1 pytest, then read the diff.\n"
         f"--- expected\n{expected}\n--- actual\n{rendered}"
      )
