from pathlib import Path


def build_compile_args(
   tool: str,
   common_flags: tuple[str, ...],
   lang_flags: tuple[str, ...],
   include_dirs: tuple[Path, ...],
   source: Path,
   output: Path,
) -> tuple[str, ...]:
   """
   The one place a compile command line gets assembled, used by both a
   real archive compile (planner.py) and a test compile (test_planner.py).
   include_dirs becomes one `-I <dir>` per entry, in order.
   """
   include_args: tuple[str, ...] = ()
   for inc in include_dirs:
      include_args += ("-I", str(inc))

   return (
      tool,
      *common_flags,
      *lang_flags,
      *include_args,
      "-c", str(source),
      "-o", str(output),
   )
