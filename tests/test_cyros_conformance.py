"""Conformance tests against the real `~/cyros` checkout.

Skipped wholesale when that checkout is absent, so the suite stays runnable on
a machine that only has the builder.

These do NOT byte-golden the real plans. The plan for a real profile changes
whenever the kernel gains or loses a source file, which is a routine event in
`~/cyros` and says nothing about the builder — a golden here would cry wolf on
every kernel commit and get regenerated without being read, which is worse than
no test. The fixture goldens already pin the builder's decision-making exactly.
What is worth asserting against the real repo is that the strict loaders still
accept it, and that the plans it produces satisfy the structural invariants the
executor and `gen-db` rely on.
"""
from __future__ import annotations

import tomllib
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import CYROS_ROOT, requires_cyros

from cyros_builder.actions import ArchiveAction, CompileAction
from cyros_builder.planner import plan_build
from cyros_builder.profile import load_profile
from cyros_builder.resolve import resolve_invocation
from cyros_builder.test_model import discover_tests
from cyros_builder.toolchain import resolve_toolchain

pytestmark = requires_cyros

PROFILE_DIR = CYROS_ROOT / "build" / "profiles"
# unit-test profiles deliberately omit config_header (each test brings its own),
# so resolve_invocation refuses them without -c. They are covered by the
# test-discovery check below instead.
BUILDABLE = sorted(
   p for p in PROFILE_DIR.glob("*.toml")
   if load_profile(p).config_header is not None
) if PROFILE_DIR.is_dir() else []

ALL_PROFILES = sorted(PROFILE_DIR.glob("*.toml")) if PROFILE_DIR.is_dir() else []


def _resolve(profile: Path, output=None):
   return resolve_invocation(Namespace(
      profile=str(profile), toolchain=None, config=None,
      output=str(output) if output else None,
   ))


# ---------------------------------------------------------------------------
# Schema drift
# ---------------------------------------------------------------------------

def test_every_toml_in_cyros_parses():
   """Catches schema drift in about a second. The strict loaders make a new
   key a hard error rather than silent misbehaviour, so this fails exactly when
   the fixture needs updating too."""
   tomls = [
      p for p in CYROS_ROOT.rglob("*.toml")
      if "out" not in p.relative_to(CYROS_ROOT).parts
   ]
   assert len(tomls) > 20, "suspiciously few TOMLs — is the checkout complete?"

   for path in tomls:
      with path.open("rb") as f:
         tomllib.load(f)


@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.stem)
def test_every_profile_loads(profile):
   load_profile(profile)


@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.stem)
def test_every_referenced_toolchain_resolves(profile):
   loaded = load_profile(profile)
   if loaded.toolchain is None:
      pytest.skip("profile declares no toolchain")
   resolve_toolchain(loaded.toolchain)


def test_test_discovery_finds_the_suite():
   any_profile = load_profile(PROFILE_DIR / "unit_test_preempt.toml")
   tests = discover_tests(any_profile.layout.source_root)
   assert len(tests) >= 15, f"expected the full unit suite, found {len(tests)}"

   names = [t.name for t in tests]
   assert len(names) == len(set(names)), "duplicate test names"
   for test in tests:
      for source in test.sources:
         assert source.is_file(), source
      assert test.config.is_file(), test.config


# ---------------------------------------------------------------------------
# Structural invariants of the real plans
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("profile", BUILDABLE, ids=lambda p: p.stem)
def test_real_profile_plans(profile, tmp_path):
   resolved = _resolve(profile, output=tmp_path)
   actions = plan_build(resolved)
   assert actions, "empty plan"

   compiles = [a for a in actions if isinstance(a, CompileAction)]
   assert compiles, "no compiles planned"

   # Every source must exist — a plan referencing a missing file is a manifest
   # bug the builder should not be able to emit.
   for action in compiles:
      assert action.source.is_file(), action.source

   # Object paths must be unique, or one compile silently clobbers another.
   outputs = [a.output for a in compiles]
   assert len(outputs) == len(set(outputs)), "duplicate object output paths"

   # argv must be fully materialised: the executor never fills anything in.
   for action in actions:
      assert action.arguments, type(action).__name__
      assert all(isinstance(x, str) and x for x in action.arguments)

   # Everything written must land under the requested output root.
   for action in actions:
      output = getattr(action, "output", None)
      if output is not None:
         assert str(output).startswith(str(tmp_path)), output

   # The archive is the last thing planned and draws only on planned objects.
   assert isinstance(actions[-1], ArchiveAction), type(actions[-1]).__name__
   if resolved.toolchain.archive.strategy == "simple":
      assert set(actions[-1].inputs) <= set(outputs)


@pytest.mark.parametrize("profile", BUILDABLE, ids=lambda p: p.stem)
def test_real_profile_plan_is_deterministic(profile, tmp_path):
   first = plan_build(_resolve(profile, output=tmp_path))
   second = plan_build(_resolve(profile, output=tmp_path))
   assert [a.arguments for a in first] == [a.arguments for a in second]


def test_excluded_sources_stay_out_of_the_real_archive():
   """validate_config.cpp is the reason sources_excluded_from_archive exists."""
   resolved = _resolve(PROFILE_DIR / "linux_preempt_sim.toml")
   actions = plan_build(resolved)
   compiles = [a for a in actions if isinstance(a, CompileAction)]

   validate = [a for a in compiles if a.source.name == "validate_config.cpp"]
   assert len(validate) == 1, "expected validate_config.cpp to be compiled"

   archive = next(a for a in actions if isinstance(a, ArchiveAction))
   assert validate[0].output not in archive.inputs


def test_vendored_sigctx_lands_under_external():
   """sigctx is vendored outside src/, so its objects must be namespaced."""
   resolved = _resolve(PROFILE_DIR / "linux_preempt_sim.toml")
   compiles = [a for a in plan_build(resolved) if isinstance(a, CompileAction)]

   sigctx = [a for a in compiles if a.source.name.startswith("sigctx")]
   assert sigctx, "expected the vendored sigctx sources in the preempt plan"
   for action in sigctx:
      assert "_external" in action.output.parts, action.output
