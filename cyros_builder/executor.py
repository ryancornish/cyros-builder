import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cyros_builder.actions import (
   ArchiveAction,
   CompileAction,
   CompileTestAction,
   LinkAction,
   LinkTestAction,
   ObjcopyAction,
   PartialLinkAction,
   RunTestAction,
)


# Actions that cannot observe one another: each reads sources plus the
# generated include tree and writes one object nobody else in the batch reads.
# Everything else (archive, partial-link, objcopy, link) consumes the outputs of
# earlier actions and must stay in plan order.
_INDEPENDENT = (CompileAction, CompileTestAction)


def execute_actions(actions: list, *, verbose: bool = False, jobs: int = 1) -> None:
   """
   Run a planned action list in order.

   With jobs > 1, each maximal run of consecutive independent actions is
   executed concurrently; everything else stays serial. Batching neighbours
   rather than hoisting every compile to the front keeps the ordering decision
   with the planner: the executor only overlaps actions that are already
   adjacent, so a plan that interleaves compiles with archive steps still runs
   exactly as it was planned.
   """
   # RunTestAction is handled by the test runner directly (so results can be
   # captured per-test). Reject the whole list up front rather than partway
   # through, so a bad plan cannot half-execute.
   for action in actions:
      if isinstance(action, RunTestAction):
         raise TypeError(
            "RunTestAction must not be passed to execute_actions; "
            "use test_runner._execute_test() instead."
         )

   total = len(actions)
   width = len(str(total))
   jobs = max(1, jobs)

   index = 0
   while index < total:
      if jobs > 1 and isinstance(actions[index], _INDEPENDENT):
         end = index
         while end < total and isinstance(actions[end], _INDEPENDENT):
            end += 1
         _run_batch(
            actions[index:end],
            first_number=index + 1,
            total=total,
            width=width,
            verbose=verbose,
            jobs=jobs,
         )
         index = end
      else:
         _run_serial(
            actions[index],
            number=index + 1,
            total=total,
            width=width,
            verbose=verbose,
         )
         index += 1


def _run_serial(action, *, number: int, total: int, width: int, verbose: bool) -> None:
   """Run one action with its streams inherited, exactly as an unparallelised
   build always has. This is the jobs == 1 path, kept byte-identical so the
   default invocation is unchanged."""
   _prepare(action)
   _print_label(action, number=number, total=total, width=width, verbose=verbose)
   subprocess.run(action.arguments, check=True, cwd=_cwd_str(action))


def _run_batch(
   batch: list,
   *,
   first_number: int,
   total: int,
   width: int,
   verbose: bool,
   jobs: int,
) -> None:
   """Run a batch of independent actions concurrently.

   Output is captured per action and emitted whole once that action finishes,
   so two compilers can never interleave a diagnostic. The progress number
   stays the action's position in the plan, so labels remain meaningful even
   though they appear in completion order.
   """
   # Serially, before anything is submitted: concurrent mkdir of a shared
   # parent is a race worth not having.
   for action in batch:
      _prepare(action)

   numbered = list(enumerate(batch, start=first_number))

   with ThreadPoolExecutor(max_workers=min(jobs, len(batch))) as pool:
      futures = {
         pool.submit(_run_captured, action): (number, action)
         for number, action in numbered
      }

      for future in as_completed(futures):
         number, action = futures[future]
         completed = future.result()

         _print_label(action, number=number, total=total, width=width, verbose=verbose)
         _echo(completed)

         if completed.returncode != 0:
            # Fail fast: drop everything still queued. Actions already running
            # are left to finish, which the pool's exit will wait for.
            pool.shutdown(wait=False, cancel_futures=True)
            raise subprocess.CalledProcessError(completed.returncode, action.arguments)


def _run_captured(action) -> subprocess.CompletedProcess:
   """Run one action, capturing both streams. Does not raise on a non-zero
   exit: the caller prints the output first, so a compiler error is visible
   before the build aborts."""
   return subprocess.run(
      action.arguments,
      cwd=_cwd_str(action),
      capture_output=True,
      text=True,
   )


def _prepare(action) -> None:
   output = getattr(action, "output", None)
   if output is not None:
      output.parent.mkdir(parents=True, exist_ok=True)

   cwd = getattr(action, "working_directory", None)
   if cwd is not None:
      cwd.mkdir(parents=True, exist_ok=True)


def _cwd_str(action) -> str | None:
   cwd = getattr(action, "working_directory", None)
   return str(cwd) if cwd is not None else None


def _print_label(action, *, number: int, total: int, width: int, verbose: bool) -> None:
   if verbose:
      print(f"$ {' '.join(action.arguments)}")
   else:
      print(f"[{number:{width}}/{total}] {_progress_label(action)}")


def _echo(completed: subprocess.CompletedProcess) -> None:
   if completed.stdout:
      print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
   if completed.stderr:
      print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n")


def _progress_label(action) -> str:
   if isinstance(action, CompileAction):
      return f"compile       [{action.component}] {_name(action.source)}"
   if isinstance(action, CompileTestAction):
      return f"compile-test  [{action.test_name}] {_name(action.source)}"
   if isinstance(action, ArchiveAction):
      return f"archive       {_name(action.output)}"
   if isinstance(action, LinkAction):
      return f"link          {_name(action.output)}"
   if isinstance(action, LinkTestAction):
      return f"link-test     [{action.test_name}] {_name(action.output)}"
   if isinstance(action, PartialLinkAction):
      return f"partial-link  {_name(action.output)}"
   if isinstance(action, ObjcopyAction):
      return f"objcopy       {_name(action.output)}"
   return type(action).__name__


def _name(path: Path) -> str:
   return path.name
