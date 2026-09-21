"""`extends` on a port variant: a target built on a base LAYER.

A port contract is layered. One half belongs to the processor core and is
identical across every MCU that uses that core; the other half belongs to the
MCU and varies. `extends` is how a selectable target variant picks up a base
layer that implements the half it does not, without either of them being a
separate selectable component.

The fixture is `corelayer` (the base layer, which no profile ever selects) and
`portc` (the target that extends it).

What each test pins, in one line:

   sources accumulate            the base's TUs reach the archive
   private includes accumulate   the base's headers are reachable from the target
   system libraries accumulate   the link line is the union
   public headers OVERRIDE       the target's port_traits wins, once, not twice
   the base is not selectable    `variants` still gates selection
   unknown base                  names the offender and what is known
   a cycle                       is reported rather than hung on
   chains                        work to arbitrary depth, root-first

The override rule is the one with teeth: `CYROS_PORT_CORE_COUNT` is an MCU-level
fact while `CYROS_PORT_STACK_ALIGN` is core-level, and both live in
`port_traits.h`, so a target has to be able to replace its base's copy of that
header rather than export a second one.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from conftest import FIXTURE_ROOT, resolve_fixture

from cyros_builder.planner import plan_build
from cyros_builder.actions import CompileAction
from cyros_builder.project_model import (
   Port,
   _resolve_extends,
   collect_public_headers,
   collect_system_libraries,
   load_ports,
   select_project,
)


PORT_SRC = FIXTURE_ROOT / "src" / "port"


def _selected(profile: str = "portc"):
   return select_project(resolve_fixture(profile).profile)


# ---------------------------------------------------------------------------
# What accumulates
# ---------------------------------------------------------------------------

def test_sources_accumulate_base_first():
   port = _selected().port
   names = [p.name for p in port.sources]
   assert names == ["corelayer.cpp", "portc.cpp"], (
      "base sources must come first, so the merge reads the way inheritance does"
   )


def test_base_source_is_compiled_and_archived():
   resolved = resolve_fixture("portc")
   compiles = [a for a in plan_build(resolved) if isinstance(a, CompileAction)]
   sources = {Path(a.source).name for a in compiles}
   assert {"corelayer.cpp", "portc.cpp"} <= sources


def test_private_includes_accumulate():
   """The reason portc.cpp can say `#include "corelayer.hpp"` at all."""
   port = _selected().port
   assert (PORT_SRC / "corelayer").resolve() in port.private_includes


def test_base_private_include_reaches_the_derived_compile():
   """Not just present on the group, but on the argv of the derived TU."""
   resolved = resolve_fixture("portc")
   compile_actions = [
      a for a in plan_build(resolved)
      if isinstance(a, CompileAction) and Path(a.source).name == "portc.cpp"
   ]
   assert len(compile_actions) == 1
   assert str((PORT_SRC / "corelayer").resolve()) in compile_actions[0].arguments


def test_system_libraries_accumulate():
   selected = _selected()
   assert collect_system_libraries(selected) == ("m", "pthread")


# ---------------------------------------------------------------------------
# What overrides
# ---------------------------------------------------------------------------

def test_public_header_override_is_by_destination():
   """The target's port_traits replaces the base's rather than joining it."""
   exports = collect_public_headers(_selected())
   traits = [e for e in exports if e.destination == Path("mini/port_traits.hpp")]
   assert len(traits) == 1, "two exports to one destination would be a race in the copy"
   assert traits[0].source.name == "target_traits.hpp"


def test_unextended_port_is_returned_unchanged():
   """No `extends` must mean no merge at all, not an equal-looking rebuild."""
   ports = load_ports(resolve_fixture("portb").profile)
   portb = ports["portb"]
   assert _resolve_extends(portb, ports) is portb


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------

def test_base_layer_is_not_selectable():
   """`variants` still gates selection, so a layer cannot be built on its own.

   This is why the resolve happens AFTER the variants check rather than before.
   """
   profile = resolve_fixture("portc").profile
   profile = dataclasses.replace(
      profile, components=dataclasses.replace(profile.components, port="corelayer")
   )
   with pytest.raises(ValueError, match="not declared in port/component.toml variants"):
      select_project(profile)


def _port(name: str, extends: str | None) -> Port:
   return Port(
      path=PORT_SRC / name / "port.toml",
      name=name,
      description="",
      dependencies=(),
      public_headers=(),
      internal_include_roots=(),
      public_modules=(),
      private_modules=(),
      source_roots=(),
      sources=(),
      sources_excluded_from_archive=(),
      generated_includes=True,
      private_includes=(),
      system_libraries=(),
      extends=extends,
   )


def test_unknown_base_is_named():
   ports = {"leaf": _port("leaf", "nosuch")}
   with pytest.raises(ValueError, match="extends unknown port 'nosuch'"):
      _resolve_extends(ports["leaf"], ports)


def test_cycle_is_reported_not_hung_on():
   ports = {
      "a": _port("a", "b"),
      "b": _port("b", "a"),
   }
   with pytest.raises(ValueError, match="forms a cycle"):
      _resolve_extends(ports["a"], ports)


def test_self_cycle_is_reported():
   ports = {"a": _port("a", "a")}
   with pytest.raises(ValueError, match="forms a cycle"):
      _resolve_extends(ports["a"], ports)


# ---------------------------------------------------------------------------
# Depth
# ---------------------------------------------------------------------------

def test_chain_of_three_merges_root_first():
   base = _port("base", None)
   mid = _port("mid", "base")
   leaf = _port("leaf", "mid")
   base = Port(**{**base.__dict__, "sources": (Path("/b.cpp"),)})
   mid = Port(**{**mid.__dict__, "sources": (Path("/m.cpp"),)})
   leaf = Port(**{**leaf.__dict__, "sources": (Path("/l.cpp"),)})

   merged = _resolve_extends(leaf, {"base": base, "mid": mid, "leaf": leaf})

   assert [p.name for p in merged.sources] == ["b.cpp", "m.cpp", "l.cpp"]
   assert merged.name == "leaf", "identity stays the variant the profile named"
   assert merged.extends is None, "the chain is resolved away, not carried forward"


def test_unknown_port_lists_only_selectable_ones():
   """A base layer must not be offered as a suggestion it would then refuse.

   `load_ports` finds every port.toml including the layers, because something
   has to be able to extend them. The diagnostic must still speak in terms of
   what a profile may actually name.
   """
   profile = resolve_fixture("portc").profile
   profile = dataclasses.replace(
      profile, components=dataclasses.replace(profile.components, port="nope")
   )
   with pytest.raises(ValueError) as excinfo:
      select_project(profile)
   assert "Known ports: porta, portb, portc" in str(excinfo.value)
   assert "corelayer" not in str(excinfo.value)
