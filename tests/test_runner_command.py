"""Tests for the toolchain [runner] table.

A cross toolchain produces binaries the build machine cannot execute. The
runner is how the toolchain says what does execute them - for the Cortex-M
port, QEMU. These tests pin the two things that decide whether a cross test
runs at all: where the binary lands in the emulator's argv, and that a
malformed runner is refused at load rather than surfacing as "Exec format
error" from a subprocess much later.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cyros_builder.toolchain import RunnerSettings, Toolchain, resolve_toolchain


def make_toolchain(runner: RunnerSettings | None) -> Toolchain:
   """A Toolchain carrying only what run_command reads."""
   from cyros_builder.toolchain import (
      ArchiveSettings, ToolchainFlags, ToolchainSettings, ToolPaths,
   )
   return Toolchain(
      path=Path("/nowhere/tc.toml"), name="tc", extends=None,
      tools=ToolPaths(cc="cc", cxx="cxx", ar="ar"),
      flags=ToolchainFlags(common=(), c=(), cxx=(), asm=(), link=()),
      settings=ToolchainSettings(
         family="gcc", debug=True, optimization="0", warnings_as_errors=False,
      ),
      archive=ArchiveSettings(
         strategy="simple", localize_hidden=False, preserve_lto_sections=False,
      ),
      runner=runner,
   )


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------

def test_no_runner_execs_the_binary_directly():
   """The host path. Every existing profile relies on this staying unchanged."""
   tc = make_toolchain(None)
   assert tc.run_command(Path("/out/bin/test_function")) == ["/out/bin/test_function"]


def test_placeholder_is_substituted_in_place():
   """QEMU needs the image after -kernel, not at the end of argv. Appending
   would make it a positional argument, which qemu-system-arm rejects."""
   tc = make_toolchain(RunnerSettings(
      command=("qemu-system-arm", "-M", "mps2-an505", "-kernel", "{binary}"),
      timeout=None,
   ))
   assert tc.run_command(Path("/out/bin/bringup.elf")) == [
      "qemu-system-arm", "-M", "mps2-an505", "-kernel", "/out/bin/bringup.elf",
   ]


def test_binary_is_appended_when_no_placeholder_is_given():
   """A plain wrapper (a chroot, a trace tool) wants the binary last, and
   should not have to spell out a placeholder to say so."""
   tc = make_toolchain(RunnerSettings(command=("valgrind", "-q"), timeout=None))
   assert tc.run_command(Path("/out/bin/t")) == ["valgrind", "-q", "/out/bin/t"]


def test_placeholder_is_substituted_in_every_element_that_carries_it():
   tc = make_toolchain(RunnerSettings(
      command=("runner", "--image={binary}", "--symbols={binary}"), timeout=None,
   ))
   assert tc.run_command(Path("/x.elf")) == [
      "runner", "--image=/x.elf", "--symbols=/x.elf",
   ]


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------

BASE = """\
name = "probe"
[tools]
cc = "cc"
cxx = "cxx"
ar = "ar"
[flags]
common = []
c = []
cxx = []
asm = []
link = []
[settings]
family = "gcc"
debug = true
optimization = "0"
warnings_as_errors = false
"""


def write_toolchain(tmp_path: Path, extra: str) -> Path:
   path = tmp_path / "tc.toml"
   path.write_text(BASE + extra)
   return path


def test_runner_round_trips_from_toml(tmp_path: Path):
   path = write_toolchain(tmp_path, """
[runner]
command = ["qemu-system-arm", "-kernel", "{binary}"]
timeout = 30
""")
   tc = resolve_toolchain(path)
   assert tc.runner is not None
   assert tc.runner.command == ("qemu-system-arm", "-kernel", "{binary}")
   assert tc.runner.timeout == 30.0


def test_absent_runner_is_none(tmp_path: Path):
   assert resolve_toolchain(write_toolchain(tmp_path, "")).runner is None


def test_timeout_is_optional(tmp_path: Path):
   path = write_toolchain(tmp_path, '\n[runner]\ncommand = ["qemu"]\n')
   assert resolve_toolchain(path).runner.timeout is None


def test_empty_command_is_refused(tmp_path: Path):
   """The failure this prevents is silent: an empty runner falls back to
   exec'ing a cross-built ELF on the host."""
   path = write_toolchain(tmp_path, "\n[runner]\ncommand = []\n")
   with pytest.raises(ValueError, match="non-empty"):
      resolve_toolchain(path)


def test_unknown_runner_key_is_refused(tmp_path: Path):
   path = write_toolchain(tmp_path, '\n[runner]\ncommand = ["q"]\nmachine = "an505"\n')
   with pytest.raises(ValueError, match=r"unknown keys in \[runner\]"):
      resolve_toolchain(path)


def test_non_positive_timeout_is_refused(tmp_path: Path):
   path = write_toolchain(tmp_path, '\n[runner]\ncommand = ["q"]\ntimeout = 0\n')
   with pytest.raises(ValueError, match="must be > 0"):
      resolve_toolchain(path)


def test_runner_is_inherited_through_extends(tmp_path: Path):
   """A debug and a release cross toolchain should not each respell the
   emulator invocation, which is a target fact, not a build-type one."""
   parent = write_toolchain(tmp_path, """
[runner]
command = ["qemu-system-arm", "-kernel", "{binary}"]
timeout = 30
""")
   child = tmp_path / "child.toml"
   child.write_text('name = "child"\nextends = "tc.toml"\n')
   tc = resolve_toolchain(child)
   assert tc.runner.command == ("qemu-system-arm", "-kernel", "{binary}")
   assert tc.runner.timeout == 30.0


# ---------------------------------------------------------------------------
# hosted vs freestanding
#
# A cross toolchain cannot run the gtest-based suite, and saying so with a port
# filter would mean listing every Linux port in all 28 of those files, then
# listing them again whenever a port is added. The predicate is not which port,
# it is whether there is an OS underneath.
# ---------------------------------------------------------------------------

from cyros_builder.test_runner import _skip_reason


class _Case:
   def __init__(self, *, hosted=True, port_filter=(), kind="unit"):
      self.hosted = hosted
      self.port_filter = port_filter
      self.kind = kind


KINDS = ("unit", "integration")


def test_a_hosted_test_is_skipped_on_a_freestanding_toolchain():
   reason = _skip_reason(
      _Case(hosted=True), active_port="cortex_m33", kinds=KINDS, hosted_toolchain=False,
   )
   assert reason is not None and "freestanding" in reason


def test_a_freestanding_test_runs_on_a_freestanding_toolchain():
   assert _skip_reason(
      _Case(hosted=False), active_port="cortex_m33", kinds=KINDS, hosted_toolchain=False,
   ) is None


def test_a_hosted_test_runs_on_a_hosted_toolchain():
   assert _skip_reason(
      _Case(hosted=True), active_port="linux_preempt", kinds=KINDS, hosted_toolchain=True,
   ) is None


def test_a_freestanding_test_is_still_subject_to_the_port_filter():
   """The two filters are independent. A bare-metal test locked to one port
   must not run on a different bare-metal port just because both are
   freestanding."""
   reason = _skip_reason(
      _Case(hosted=False, port_filter=("cortex_m33",)),
      active_port="cortex_m4", kinds=KINDS, hosted_toolchain=False,
   )
   assert reason is not None and "locked to port" in reason


def test_hosted_defaults_to_true_so_existing_toolchains_are_unaffected(tmp_path: Path):
   assert resolve_toolchain(write_toolchain(tmp_path, "")).settings.hosted is True


def test_hosted_can_be_declared_false(tmp_path: Path):
   path = write_toolchain(tmp_path, "")
   path.write_text(path.read_text().replace(
      "warnings_as_errors = false", "warnings_as_errors = false\nhosted = false"))
   assert resolve_toolchain(path).settings.hosted is False


# ---------------------------------------------------------------------------
# The summary counts what RAN
# ---------------------------------------------------------------------------

# TestResult aliased: pytest tries to collect any imported name starting with
# Test, the same trap test_layering.py records for TestCase.
from cyros_builder.test_runner import TestResult as _Result
from cyros_builder.test_runner import _print_summary


def test_summary_does_not_count_skipped_tests_as_passed(capsys):
   """A skipped test carries passed=True so it does not fail the run. Totalling
   that against every discovered test reported "32/32 passed" for a suite where
   24 ran and 8 were skipped, and "32/32" for the Cortex-M33 profile where two
   ran and thirty were skipped."""
   results = [
      _Result(name="ran_ok", passed=True, layer=0),
      _Result(name="ran_ok2", passed=True, layer=0),
      *[_Result(name=f"skipped{i}", passed=True, skipped=True,
                   skip_reason="needs a hosted toolchain", layer=1)
        for i in range(30)],
   ]
   _print_summary(results)
   out = capsys.readouterr().out
   assert "Results: 2/2 passed, 30 skipped" in out
   assert "32/32" not in out


def test_summary_still_reports_failures_against_what_ran(capsys):
   results = [
      _Result(name="ok", passed=True, layer=0),
      _Result(name="bad", passed=False, layer=1),
      _Result(name="gone", passed=True, skipped=True, skip_reason="x", layer=2),
   ]
   _print_summary(results)
   out = capsys.readouterr().out
   assert "Results: 1/2 passed, 1 skipped, 1 FAILED" in out
