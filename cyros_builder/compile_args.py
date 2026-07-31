from pathlib import Path


def depfile_path(output: Path) -> Path:
   """The `.d` a compile writes next to its object.

   THE one definition of this convention. The planner uses it to build `-MF`,
   and staleness.py uses it to find the header set afterwards; if those two ever
   disagreed, header edits would stop invalidating objects and the failure would
   be silent. Appending rather than replacing the suffix keeps `foo.o` and
   `foo.d` from colliding for two sources that differ only in extension.
   """
   return output.with_suffix(output.suffix + ".d")


def build_compile_args(
   tool: str,
   common_flags: tuple[str, ...],
   lang_flags: tuple[str, ...],
   include_dirs: tuple[Path, ...],
   source: Path,
   output: Path,
   depfile: Path | None = None,
) -> tuple[str, ...]:
   """
   The one place a compile command line gets assembled, used by both a
   real archive compile (planner.py) and a test compile (test_planner.py).
   include_dirs becomes one `-I <dir>` per entry, in order.

   depfile, when given, adds `-MMD -MF <depfile>` so the compiler records the
   header set it actually read. That file is what lets the incremental build
   invalidate an object when a header it includes changes; without it a header
   edit is invisible. `-MMD` (not `-MD`) deliberately omits system headers.

   Callers pass depfile only for C and C++. Assembly is excluded on purpose: the
   asm tool is `tools.asm`, which may be a bare assembler rather than a compiler
   driver — the test fixture uses `as`, which does not understand `-MMD` at all.
   Assembly sources here do not include headers, so nothing is lost.
   """
   include_args: tuple[str, ...] = ()
   for inc in include_dirs:
      include_args += ("-I", str(inc))

   dep_args: tuple[str, ...] = ()
   if depfile is not None:
      dep_args = ("-MMD", "-MF", str(depfile))

   return (
      tool,
      *common_flags,
      *lang_flags,
      *include_args,
      *dep_args,
      "-c", str(source),
      "-o", str(output),
   )
