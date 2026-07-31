"""Incremental build support: decide which planned actions actually need to run.

This is a distinct stage *between* plan and execute, and that placement is the
whole point. The planner still decides what a full build is; the executor still
just runs what it is handed; this module owns the single question "what
changed". `gen-db` keeps consuming the unpruned plan, so the compile database
stays complete even when a build skips most of it.

Staleness is decided on **content hashes, never mtimes**. Generated files and
git checkouts both make mtimes lie, and the include tree is rewritten (or at
least re-examined) on every run.

An action is stale when any of these hold:
  * its output is missing
  * it has no recorded state
  * its argv hash changed (catches flag, toolchain and tool-path edits)
  * any declared input's content hash changed, or an input appeared/disappeared
  * an earlier action in this same plan is stale and produces one of its inputs

That last rule is what makes staleness transitive along the archive chain: one
recompiled object forces partial-link, then objcopy, then ar.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cyros_builder.actions import (
   ArchiveAction,
   CompileAction,
   CompileTestAction,
   LinkAction,
   LinkTestAction,
   ObjcopyAction,
   PartialLinkAction,
)
from cyros_builder.compile_args import depfile_path
from cyros_builder.output import build_state_path
from cyros_builder.resolve import ResolvedInvocation

STATE_VERSION = 2

_COMPILES = (CompileAction, CompileTestAction)
_CONSUMERS = (ArchiveAction, PartialLinkAction, LinkAction, LinkTestAction)


@dataclass(frozen=True)
class PruneResult:
   actions: list          # what to execute, in plan order
   skipped: int           # how many were up to date
   total: int

   @property
   def all_up_to_date(self) -> bool:
      return not self.actions and self.total > 0


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> str | None:
   try:
      with path.open("rb") as f:
         digest = hashlib.sha256()
         for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
      return digest.hexdigest()
   except OSError:
      return None


def _hash_argv(arguments: tuple[str, ...]) -> str:
   return hashlib.sha256("\0".join(arguments).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Declared inputs per action type
# ---------------------------------------------------------------------------

def depfile_for(action) -> Path | None:
   """Path of the `-MMD -MF` dependency file a compile writes, if it has one.

   Assembly compiles are planned without `-MMD`, so no .d is produced for them
   and none is expected here — the check is whether the argv actually asked for
   one, not merely whether the action is a compile.
   """
   if isinstance(action, _COMPILES) and "-MMD" in action.arguments:
      return depfile_path(action.output)
   return None


def _parse_depfile(path: Path) -> list[Path]:
   """Read a make-style .d and return its prerequisites.

   Format is `target: prereq prereq \\\n  prereq ...`. Only the prerequisites
   matter. Escaped spaces are handled; anything else exotic is not, because gcc
   does not emit it for the paths this builder generates.
   """
   try:
      text = path.read_text()
   except OSError:
      return []

   _, _, rhs = text.partition(":")
   if not rhs:
      return []

   rhs = rhs.replace("\\\n", " ").replace("\\\r\n", " ")
   parts: list[str] = []
   current = ""
   index = 0
   while index < len(rhs):
      char = rhs[index]
      if char == "\\" and index + 1 < len(rhs) and rhs[index + 1] == " ":
         current += " "
         index += 2
         continue
      if char.isspace():
         if current:
            parts.append(current)
            current = ""
      else:
         current += char
      index += 1
   if current:
      parts.append(current)

   return [Path(p) for p in parts]


def declared_inputs(action) -> list[Path]:
   """Every file whose content this action's output depends on.

   For a compile that has already run once, this includes the header set gcc
   recorded in the .d file — which is the only way header edits can invalidate
   an object.
   """
   if isinstance(action, _COMPILES):
      inputs = [action.source]
      depfile = depfile_for(action)
      if depfile is not None:
         inputs.extend(_parse_depfile(depfile))
      # Deduplicate while preserving order; gcc lists the source itself too.
      seen: set[Path] = set()
      ordered: list[Path] = []
      for path in inputs:
         resolved = path.resolve()
         if resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)
      return ordered

   if isinstance(action, _CONSUMERS):
      return [p.resolve() for p in action.inputs]

   if isinstance(action, ObjcopyAction):
      return [action.input.resolve()]

   return []


def _first_run_unknown_deps(action) -> bool:
   """True when a compile has never produced a .d, so its header set is unknown
   and it must be treated as stale regardless of what state says."""
   depfile = depfile_for(action)
   return depfile is not None and not depfile.is_file()


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------

def load_state(resolved: ResolvedInvocation) -> dict:
   path = build_state_path(resolved)
   try:
      raw = json.loads(path.read_text())
   except (OSError, json.JSONDecodeError):
      return {}
   if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
      # A version bump invalidates everything, which is the conservative and
      # correct response to not knowing how the old records were computed.
      return {}
   entries = raw.get("actions")
   return entries if isinstance(entries, dict) else {}


def write_state(resolved: ResolvedInvocation, entries: dict) -> None:
   path = build_state_path(resolved)
   path.parent.mkdir(parents=True, exist_ok=True)
   payload = {"version": STATE_VERSION, "actions": entries}
   tmp = path.with_suffix(".json.tmp")
   tmp.write_text(json.dumps(payload, indent=1, sort_keys=True))
   tmp.replace(path)


# ---------------------------------------------------------------------------
# The prune stage
# ---------------------------------------------------------------------------

def prune_actions(
   resolved: ResolvedInvocation,
   actions: list,
   *,
   force: bool = False,
) -> PruneResult:
   """Return the subset of `actions` that must run, in plan order."""
   total = len(actions)
   if force:
      return PruneResult(actions=list(actions), skipped=0, total=total)

   state = load_state(resolved)
   rebuilt_outputs: set[Path] = set()
   keep: list = []

   for action in actions:
      output = getattr(action, "output", None)
      if output is None:
         keep.append(action)          # nothing to reason about; always run
         continue

      output = output.resolve()
      if _is_stale(action, output, state, rebuilt_outputs):
         keep.append(action)
         rebuilt_outputs.add(output)

   return PruneResult(actions=keep, skipped=total - len(keep), total=total)


def _is_stale(action, output: Path, state: dict, rebuilt_outputs: set[Path]) -> bool:
   if not output.is_file():
      return True
   if _first_run_unknown_deps(action):
      return True

   record = state.get(str(output))
   if not isinstance(record, dict):
      return True
   if record.get("argv") != _hash_argv(action.arguments):
      return True

   recorded_inputs = record.get("inputs")
   if not isinstance(recorded_inputs, dict):
      return True

   current = declared_inputs(action)

   # An input produced by an action already deemed stale in this same plan.
   # This is the load-bearing one for the archive: at prune time the object on
   # disk is still the old one, so its hash would match and the archive would be
   # wrongly skipped. Only knowing that a member is *about to* be rebuilt saves
   # it.
   if any(path in rebuilt_outputs for path in current):
      return True

   # Appeared or disappeared. For archive-like actions this is exactly the
   # "member set changed" check, since the members *are* the declared inputs.
   #
   # Mutation testing showed this and _first_run_unknown_deps are each redundant
   # *given the other rules*, and each catches the other's mutation:
   #   - a dropped archive member also changes argv (`ar rcs <a> <objs...>`
   #     enumerates them), so the argv hash catches it;
   #   - a deleted .d shrinks declared_inputs to just the source, so this
   #     set comparison catches it.
   # Both are kept as defence in depth, because each assumes something about a
   # *different* rule holding: this one stops mattering only while every archive
   # strategy enumerates members in argv (an `ar @filelist` variant would not),
   # and the .d check stops mattering only while the recorded input set always
   # includes the headers. Disabling either alone leaves the suite green;
   # disabling both makes test_object_without_a_depfile_is_rebuilt fail. Do not
   # delete one as "dead code" without re-reading that reasoning.
   if {str(p) for p in current} != set(recorded_inputs):
      return True

   for path in current:
      digest = _hash_file(path)
      if digest is None or digest != recorded_inputs.get(str(path)):
         return True

   return False


# ---------------------------------------------------------------------------
# Recording, after a successful execute
# ---------------------------------------------------------------------------

def record_state(resolved: ResolvedInvocation, actions: list, executed: list) -> None:
   """Persist state for the whole plan.

   Called only after a fully successful execute. Entries for executed actions
   are recomputed now (a compile's .d only exists *after* it ran, so its header
   set is not knowable any earlier); entries for skipped actions are carried
   forward untouched.

   On failure this is not called at all, so the previous state survives and the
   next run re-examines everything it had not yet confirmed. That recompiles
   some work that had in fact succeeded, which is the conservative direction:
   never record a success that did not happen.
   """
   previous = load_state(resolved)
   executed_ids = {id(a) for a in executed}
   entries: dict = {}

   for action in actions:
      output = getattr(action, "output", None)
      if output is None:
         continue
      key = str(output.resolve())

      if id(action) not in executed_ids and key in previous:
         entries[key] = previous[key]
         continue

      inputs: dict[str, str] = {}
      for path in declared_inputs(action):
         digest = _hash_file(path)
         if digest is not None:
            inputs[str(path)] = digest

      entries[key] = {"argv": _hash_argv(action.arguments), "inputs": inputs}

   write_state(resolved, entries)
