"""Tests for consumer projects, the top layer of the suite (T1 decision 4).

A consumer builds against the EXPORTED tree and links the archive the way a real
user does, which makes it the only thing in the suite that can see a break in
the exported surface. All three real ones were unbuildable for several commits
in 2026-09 and nobody noticed, because nothing ran them. These tests pin the
machinery that now does.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import FIXTURE_ROOT

from cyros_builder.consumer_model import (
   discover_consumers, find_consumer_root, load_consumer,
)
from cyros_builder.test_runner import _build_consumer, _blocking_layer

CONSUMER = FIXTURE_ROOT / "tests" / "consumer" / "mini_consumer" / "consumer.toml"


@pytest.fixture
def consumer_copy(tmp_path):
   """A writable copy, so a build actually runs without dirtying the fixture."""
   dest = tmp_path / "mini_consumer"
   shutil.copytree(CONSUMER.parent, dest)
   return dest


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_consumers_are_discovered_from_the_source_root():
   found = discover_consumers(FIXTURE_ROOT / "src")
   assert [c.name for c in found] == ["mini_consumer"]
   assert found[0].layer == 9
   assert found[0].kind == "integration"


def test_a_tree_with_no_consumers_is_not_an_error(tmp_path):
   assert discover_consumers(tmp_path) == []


def test_the_consumer_root_sits_beside_the_unit_test_root():
   assert find_consumer_root(FIXTURE_ROOT / "src").name == "consumer"


def test_a_consumer_without_a_layer_is_an_error(consumer_copy):
   """Consumers are ordinary members of the chain and declare a layer like
   everything else in it."""
   path = consumer_copy / "consumer.toml"
   path.write_text(path.read_text().replace("layer = 9\n", ""))
   with pytest.raises(ValueError, match="'consumer.layer' is required"):
      load_consumer(path)


def test_a_missing_build_script_is_caught_at_load_time(consumer_copy):
   (consumer_copy / "build.sh").unlink()
   with pytest.raises(Exception):
      load_consumer(consumer_copy / "consumer.toml")


def test_the_port_is_a_filter_so_a_consumer_builds_once_not_twice():
   """Each consumer builds its own profile with its own port, so running it
   under every suite would build the same thing repeatedly."""
   assert discover_consumers(FIXTURE_ROOT / "src")[0].port_filter == ("porta",)


# ---------------------------------------------------------------------------
# Interface parity with TestCase
# ---------------------------------------------------------------------------

def test_a_consumer_exposes_what_the_layered_runner_reads():
   """The runner orders and blocks both kinds through the same code, so it must
   be able to read the same attributes off either without knowing which it has."""
   c = discover_consumers(FIXTURE_ROOT / "src")[0]
   for attr in ("name", "layer", "kind", "harness_debt", "run_rank", "port_filter"):
      assert hasattr(c, attr), attr
   assert c.run_rank == c.layer


def test_a_consumer_is_blocked_by_a_lower_failure_like_anything_else():
   c = discover_consumers(FIXTURE_ROOT / "src")[0]
   assert _blocking_layer(c, {4}) == 4
   assert _blocking_layer(c, set()) is None


# ---------------------------------------------------------------------------
# Building one
# ---------------------------------------------------------------------------

def test_a_successful_build_yields_a_run_action(consumer_copy):
   case = load_consumer(consumer_copy / "consumer.toml")
   ok, error, _, action = _build_consumer(consumer=case, verbose=False)
   assert ok, error
   assert action is not None
   assert action.binary.is_file()


def test_a_failing_build_script_is_reported_with_its_output(consumer_copy):
   """The rot scenario: a consumer that no longer compiles must fail the suite
   rather than be quietly skipped."""
   (consumer_copy / "build.sh").write_text(
      "#!/usr/bin/env bash\necho 'main.cpp:1: error: something broke'\nexit 1\n"
   )
   case = load_consumer(consumer_copy / "consumer.toml")
   ok, error, _, action = _build_consumer(consumer=case, verbose=False)
   assert not ok
   assert action is None
   assert "exited with code 1" in error
   assert "something broke" in error, "the script's output must reach the report"


def test_a_script_that_produces_no_binary_is_a_failure(consumer_copy):
   """Declaring a binary and not producing one is a broken build, not a pass."""
   (consumer_copy / "build.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
   case = load_consumer(consumer_copy / "consumer.toml")
   ok, error, _, _ = _build_consumer(consumer=case, verbose=False)
   assert not ok
   assert "produced no binary" in error


def test_a_consumer_may_declare_no_binary_at_all(consumer_copy):
   """Then building IS the assertion: what it proves is that the exported tree
   compiles and links."""
   path = consumer_copy / "consumer.toml"
   path.write_text(path.read_text().replace('binary = "out/bin/main"\n', ""))
   case = load_consumer(path)
   assert case.binary is None
   ok, error, _, action = _build_consumer(consumer=case, verbose=False)
   assert ok, error
   assert action is None


def test_the_build_leaves_no_stray_log_in_the_source_tree(consumer_copy):
   """Output is captured in memory. A log file here would be an untracked
   artefact sitting in the repo next to the project."""
   case = load_consumer(consumer_copy / "consumer.toml")
   _build_consumer(consumer=case, verbose=False)
   assert not (consumer_copy / "build.log").exists()
