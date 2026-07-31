"""Golden tests over plan_build() / plan_test().

Each test does two things: it pins the whole plan against a golden file (broad
coverage, catches anything), and it asserts the specific decision it exists to
protect (so a failure names the behaviour instead of just saying "the golden
moved").
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import (
   FIXTURE_ROOT,
   assert_golden,
   plan_to_jsonable,
   resolve_fixture,
)

from cyros_builder.actions import (
   ArchiveAction,
   CompileAction,
   CompileTestAction,
   LinkTestAction,
   ObjcopyAction,
   PartialLinkAction,
   RunTestAction,
)
from cyros_builder.planner import plan_build
from cyros_builder.project_model import collect_public_headers, select_project
from cyros_builder.test_model import discover_tests
from cyros_builder.test_planner import plan_test
from cyros_builder.test_planner import make_test_resolved

ALL_PROFILES = ["full", "no_time", "portb", "lto"]


# ---------------------------------------------------------------------------
# Whole-plan goldens
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_plan_build_matches_golden(profile):
   resolved = resolve_fixture(profile)
   actions = plan_build(resolved)
   assert_golden(f"plan_{profile}", plan_to_jsonable(actions, resolved))


def test_plan_test_matches_golden():
   resolved = resolve_fixture("full")
   tests = discover_tests(resolved.profile.layout.source_root)
   assert [t.name for t in tests] == ["mini_case"]

   test_resolved = make_test_resolved(resolved, tests[0])
   actions = plan_test(resolved=test_resolved, test=tests[0])
   assert_golden("plan_test_mini_case", plan_to_jsonable(actions, test_resolved))


# ---------------------------------------------------------------------------
# The specific decisions the goldens are protecting
# ---------------------------------------------------------------------------

def compiles(actions):
   return [a for a in actions if isinstance(a, CompileAction)]


def test_absent_time_driver_compiles_no_time_sources():
   """components.time_driver unset means nothing under src/time is compiled."""
   with_time = compiles(plan_build(resolve_fixture("full")))
   without = compiles(plan_build(resolve_fixture("no_time")))

   assert any(a.component == "tick" for a in with_time)
   assert not any(a.component == "tick" for a in without)
   assert not any("time" in str(a.source.parent) for a in without)


def test_selected_port_is_the_only_port_compiled():
   porta = compiles(plan_build(resolve_fixture("full")))
   portb = compiles(plan_build(resolve_fixture("portb")))

   assert {a.component for a in porta} & {"porta", "portb"} == {"porta"}
   assert {a.component for a in portb} & {"porta", "portb"} == {"portb"}


def test_excluded_source_is_compiled_but_not_archived():
   """sources_excluded_from_archive: compile it, keep it out of the .a."""
   actions = plan_build(resolve_fixture("full"))
   archive = next(a for a in actions if isinstance(a, ArchiveAction))

   validate_obj = [
      a.output for a in compiles(actions) if a.source.name == "validate.cpp"
   ]
   assert len(validate_obj) == 1, "validate.cpp should still be compiled"
   assert validate_obj[0] not in archive.inputs, "validate.cpp must not be archived"

   kernel_obj = [a.output for a in compiles(actions) if a.source.name == "kernel.cpp"]
   assert kernel_obj[0] in archive.inputs


def test_out_of_tree_source_lands_under_external():
   """A source outside source_root is namespaced by owning component."""
   actions = plan_build(resolve_fixture("full"))
   vendor = next(a for a in compiles(actions) if a.source.name == "vendor.c")

   parts = vendor.output.parts
   assert "_external" in parts, vendor.output
   assert parts[parts.index("_external") + 1] == "porta"
   assert vendor.output.name == "vendor.o"


def test_in_tree_object_mirrors_source_layout():
   actions = plan_build(resolve_fixture("full"))
   kernel = next(a for a in compiles(actions) if a.source.name == "kernel.cpp")
   assert kernel.output.parts[-2:] == ("kernel", "kernel.o")
   assert "_external" not in kernel.output.parts


def test_language_selection_picks_the_right_tool():
   """C, C++ and asm sources each get their own tool and flag set."""
   actions = compiles(plan_build(resolve_fixture("full")))
   by_name = {a.source.name: a for a in actions}

   assert by_name["vendor.c"].language == "c"
   assert by_name["vendor.c"].arguments[0] == "gcc"
   assert "-std=c17" in by_name["vendor.c"].arguments

   assert by_name["kernel.cpp"].language == "c++"
   assert by_name["kernel.cpp"].arguments[0] == "g++"
   assert "-std=c++20" in by_name["kernel.cpp"].arguments

   assert by_name["asm_bits.S"].language == "asm"
   assert by_name["asm_bits.S"].arguments[0] == "as"
   assert "-DASM" in by_name["asm_bits.S"].arguments


def test_toolchain_extends_add_and_remove_are_applied():
   """child.toml adds -DCHILD, removes -DDROP_ME, and inherits -DBASE."""
   child = compiles(plan_build(resolve_fixture("full")))[0].arguments
   assert "-DBASE" in child
   assert "-DCHILD" in child
   assert "-DDROP_ME" not in child

   base = compiles(plan_build(resolve_fixture("portb")))[0].arguments
   assert "-DBASE" in base
   assert "-DDROP_ME" in base, "base toolchain keeps the flag the child removes"
   assert "-DCHILD" not in base


def test_private_includes_apply_only_to_their_own_group():
   actions = compiles(plan_build(resolve_fixture("full")))
   kernel = next(a for a in actions if a.source.name == "kernel.cpp")
   alpha = next(a for a in actions if a.source.name == "alpha.cpp")

   private = str((FIXTURE_ROOT / "src" / "kernel" / "private").resolve())
   assert private in kernel.arguments
   assert private not in alpha.arguments


def test_every_compile_gets_exactly_one_generated_include_root():
   for profile in ALL_PROFILES:
      resolved = resolve_fixture(profile)
      for action in compiles(plan_build(resolved)):
         includes = [
            action.arguments[i + 1]
            for i, a in enumerate(action.arguments)
            if a == "-I"
         ]
         generated = [i for i in includes if i.endswith("/include")]
         assert len(generated) == 1, (profile, action.source, includes)


def test_simple_archive_strategy():
   actions = plan_build(resolve_fixture("full"))
   assert not any(isinstance(a, (PartialLinkAction, ObjcopyAction)) for a in actions)

   archive = [a for a in actions if isinstance(a, ArchiveAction)]
   assert len(archive) == 1
   assert archive[0].arguments[:2] == ("ar", "rcs")
   assert archive[0].output.name == "libmini.a"
   assert actions[-1] is archive[0], "archive must be planned last"


def test_lto_merged_archive_strategy():
   """partial-link -> objcopy(--localize-hidden) -> ar, in that order.

   There used to be a second, purely cosmetic objcopy that renamed the filtered
   object; the merge now writes a name the single objcopy can consume directly.
   """
   actions = plan_build(resolve_fixture("lto"))
   tail = [type(a).__name__ for a in actions if not isinstance(a, CompileAction)]
   assert tail == ["PartialLinkAction", "ObjcopyAction", "ArchiveAction"], tail

   partial = next(a for a in actions if isinstance(a, PartialLinkAction))
   assert "-flto" in partial.arguments
   # nolto-rel, not rel: localization only takes effect on real machine code.
   assert "-flinker-output=nolto-rel" in partial.arguments

   objcopy = next(a for a in actions if isinstance(a, ObjcopyAction))
   assert "--localize-hidden" in objcopy.arguments
   assert not any("keep-global-symbols" in x for x in objcopy.arguments), (
      "the hand-maintained symbol list is gone; hiding is compiler-driven now"
   )

   archive = next(a for a in actions if isinstance(a, ArchiveAction))
   assert len(archive.inputs) == 1, "lto archive holds one merged object"
   # Stem comes from the archive name, not a hardcoded "cortos".
   assert archive.inputs[0].name == "libmini.o", archive.inputs[0]


def test_lto_objcopy_uses_the_toolchain_tool():
   """objcopy was hardcoded, which pinned the pipeline to the host binutils and
   would have broken any cross toolchain (arm-none-eabi-objcopy for STM32)."""
   actions = plan_build(resolve_fixture("lto"))
   objcopy = next(a for a in actions if isinstance(a, ObjcopyAction))
   assert objcopy.arguments[0] == "objcopy", "fixture sets no tools.objcopy, so default"

   custom = resolve_fixture("lto", toolchain=FIXTURE_ROOT / "build" / "toolchains" / "lto_cross.toml")
   actions = plan_build(custom)
   objcopy = next(a for a in actions if isinstance(a, ObjcopyAction))
   assert objcopy.arguments[0] == "my-cross-objcopy", objcopy.arguments[0]


def test_archive_contains_every_archivable_object_and_nothing_else():
   for profile in ALL_PROFILES:
      resolved = resolve_fixture(profile)
      actions = plan_build(resolved)
      archive = next(a for a in actions if isinstance(a, ArchiveAction))
      produced = {a.output for a in compiles(actions)}
      excluded = {
         a.output for a in compiles(actions) if a.source.name == "validate.cpp"
      }
      if resolved.toolchain.archive.strategy == "simple":
         assert set(archive.inputs) == produced - excluded, profile


def test_header_export_mapping():
   """public_headers 'source -> destination' maps into the generated tree."""
   selected = select_project(resolve_fixture("full").profile)
   exports = collect_public_headers(selected)
   mapping = {e.source.name: str(e.destination) for e in exports}

   assert mapping == {
      "kernel.hpp": "mini/kernel.hpp",
      "visibility.hpp": "mini/visibility.hpp",
      "port.hpp": "mini/port.hpp",
   }
   for export in exports:
      assert export.source.is_file(), export.source
      assert not export.destination.is_absolute()


def test_plan_test_shape():
   resolved = resolve_fixture("full")
   test = discover_tests(resolved.profile.layout.source_root)[0]
   test_resolved = make_test_resolved(resolved, test)
   actions = plan_test(resolved=test_resolved, test=test)

   assert [type(a).__name__ for a in actions] == [
      "CompileTestAction", "LinkTestAction", "RunTestAction",
   ]

   link = next(a for a in actions if isinstance(a, LinkTestAction))
   assert any(str(i).endswith("libmini.a") for i in link.inputs)
   assert "-lpthread" in link.arguments


def test_test_toml_features_replace_profile_features():
   """[components].features in a test.toml REPLACES the profile's set."""
   resolved = resolve_fixture("full")
   assert resolved.profile.features.enable == ("alpha", "beta", "timed")

   test = discover_tests(resolved.profile.layout.source_root)[0]
   test_resolved = make_test_resolved(resolved, test)
   assert test_resolved.profile.features.enable == ("alpha",)

   components = {a.component for a in compiles(plan_build(test_resolved))}
   assert "alpha" in components
   assert "beta" not in components and "timed" not in components


def test_test_port_is_a_filter_not_a_selection():
   """The test declares port = ["porta"] but never selects it; the profile does."""
   resolved = resolve_fixture("portb")
   test = discover_tests(resolved.profile.layout.source_root)[0]
   assert test.port_filter == ("porta",)

   test_resolved = make_test_resolved(resolved, test)
   assert test_resolved.profile.components.port == "portb", (
      "the test must not override the profile's port"
   )


def test_plan_is_deterministic():
   """Same input, same plan — goldens would be worthless otherwise."""
   for profile in ALL_PROFILES:
      first = plan_to_jsonable(plan_build(resolve_fixture(profile)))
      second = plan_to_jsonable(plan_build(resolve_fixture(profile)))
      assert first == second, profile


def test_output_override_relocates_every_output(tmp_path):
   """-o moves all outputs and nothing else."""
   resolved = resolve_fixture("full", output=tmp_path)
   for action in plan_build(resolved):
      output = getattr(action, "output", None)
      if output is not None:
         assert str(output).startswith(str(tmp_path)), output
