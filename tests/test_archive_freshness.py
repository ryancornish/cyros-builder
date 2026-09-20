"""The archive is a function of the current manifest, not of build history.

`ar rcs` adds and replaces members but never removes one that is no longer part
of the build. Without deleting the archive first, an object whose source was
deleted, or dropped from a manifest, stays in it and keeps contributing
symbols.

Found 2026-09-21 on the Cortex-M33 port: a file removed from `port.toml` AND
deleted from disk was still supplying a weak `std::__throw_out_of_range_fmt`
several builds later, which silently defeated the `-nostdlib++` check that
exists to keep cyros free of libstdc++ symbols. A build that succeeds on code
that no longer exists is the worst kind of stale, because everything about it
looks correct.
"""
from __future__ import annotations

from pathlib import Path

from cyros_builder.actions import ArchiveAction, CompileAction, LinkAction
from cyros_builder.executor import _prepare


def make_archive_action(output: Path) -> ArchiveAction:
   return ArchiveAction(
      inputs=(), output=output, arguments=("ar", "rcs", str(output)),
      working_directory=output.parent,
   )


def test_an_existing_archive_is_removed_before_it_is_rebuilt(tmp_path: Path):
   archive = tmp_path / "lib" / "libcyros.a"
   archive.parent.mkdir(parents=True)
   archive.write_bytes(b"!<arch>\nstale member from a source that no longer exists")

   _prepare(make_archive_action(archive))

   assert not archive.exists(), (
      "a stale archive must be deleted, or ar merges the new objects into it "
      "and yesterday's members survive"
   )


def test_preparing_a_missing_archive_is_not_an_error(tmp_path: Path):
   """The first build of a profile has no archive to remove."""
   archive = tmp_path / "lib" / "libcyros.a"
   _prepare(make_archive_action(archive))
   assert archive.parent.is_dir(), "the output directory is still created"


def test_a_compile_output_is_NOT_deleted(tmp_path: Path):
   """Only archives. Deleting a compile or link output would defeat the
   staleness tracking that decides whether to run the action at all."""
   obj = tmp_path / "obj" / "kernel.o"
   obj.parent.mkdir(parents=True)
   obj.write_bytes(b"object")

   _prepare(CompileAction(
      component="kernel", source=Path("k.cpp"), output=obj, language="c++",
      kind="source", arguments=(), working_directory=tmp_path,
   ))

   assert obj.exists(), "a compile output must survive _prepare"


def test_a_link_output_is_NOT_deleted(tmp_path: Path):
   binary = tmp_path / "bin" / "app"
   binary.parent.mkdir(parents=True)
   binary.write_bytes(b"binary")

   _prepare(LinkAction(
      inputs=(), output=binary, arguments=(), working_directory=tmp_path,
   ))

   assert binary.exists(), "a link output must survive _prepare"
