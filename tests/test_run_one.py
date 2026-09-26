"""Tests for executing one test binary: result, exit code, and timeout.

`_run_one` is stubbed out everywhere else in the suite, so this is the only
place its real subprocess handling is exercised. The case that matters most is
the timeout, because a test can start processes of its own. A gtest death test
re-executes the binary as a child, and a cross test runs under an emulator.
Killing only the process the runner launched leaves those running, holding the
log open, after the runner has already reported the timeout. Found 2026-09-24:
a hung death-test child outlived its suite by twelve minutes.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from cyros_builder.actions import RunTestAction
from cyros_builder.test_runner import _run_one


def fake_test(tmp_path: Path, body: str) -> RunTestAction:
   script = tmp_path / "fake_test"
   script.write_text("#!/bin/sh\n" + body)
   script.chmod(0o755)
   return RunTestAction(test_name="fake_test", binary=script, working_directory=tmp_path)


def alive(pid: int) -> bool:
   """True while `pid` exists and is not a zombie. A killed child that has not
   been reaped yet still answers kill(pid, 0), so /proc is the honest check."""
   try:
      state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
   except (FileNotFoundError, ProcessLookupError):
      return False
   return state not in ("Z", "X")


def test_a_passing_binary_passes(tmp_path: Path):
   passed, error, _, _ = _run_one(fake_test(tmp_path, "exit 0\n"), verbose=False)
   assert passed and error == ""


def test_a_failing_binary_reports_its_exit_code(tmp_path: Path):
   passed, error, _, _ = _run_one(fake_test(tmp_path, "exit 3\n"), verbose=False)
   assert not passed
   assert error == "exited with code 3"


def test_a_timeout_kills_everything_the_test_started(tmp_path: Path):
   pid_file = tmp_path / "grandchild.pid"
   action = fake_test(tmp_path, f"sleep 60 &\necho $! > {pid_file}\nsleep 60\n")

   start = time.monotonic()
   passed, error, _, _ = _run_one(action, verbose=False, timeout=1.0)

   assert not passed
   assert error == "timed out after 1s"
   assert time.monotonic() - start < 10, "the runner waited on something it should have killed"

   grandchild = int(pid_file.read_text())
   deadline = time.monotonic() + 5
   while alive(grandchild) and time.monotonic() < deadline:
      time.sleep(0.05)
   still_alive = alive(grandchild)
   if still_alive:
      os.kill(grandchild, 9)   # do not leave it behind even when failing
   assert not still_alive, "a process the test started outlived the timeout"
