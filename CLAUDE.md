# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cyros-builder` is a standalone Python CLI that builds **Cyros**, a C++ RTOS kernel living in a
*separate* repository (`../cyros`). This repo contains no C++ worth building — the real
component metadata, build profiles, and toolchains live in the consumer repo under `cyros/build/`
and `cyros/src/`. Treat `../cyros` as the primary integration test for any change here.

There are no unit tests for the builder itself. Verification means running it against `../cyros`.

## Commands

Install (editable, from the parent directory of this repo):

```bash
pipx install -e cyros-builder
```

`./cyros-builder` at the repo root is a stub that calls `cyros_builder.cli:main` directly, useful
when the pipx install is stale.

Every subcommand takes `-p/--profile` (required) and optionally `-t/--toolchain`, `-c/--config`,
`-o/--output` — the latter three override what the profile declares.

```bash
# Build the archive + public include tree + manifest.json
cyros-builder build -p build/profiles/linux_boost_sim.toml [-v] [--clean-first]

# Inspect the fully-resolved profile+toolchain without building
cyros-builder show -p build/profiles/linux_boost_sim.toml [--format json]

# Public headers only, no compilation
cyros-builder export-includes -p <profile>

# compile_commands.json (reuses the real build plan, so it can't drift)
cyros-builder gen-db -p <profile> --activate

cyros-builder clean -p <profile>
```

Unit tests (run from the `cyros` repo root, since profile paths are relative):

```bash
cyros-builder test -p build/profiles/unit_test_preempt.toml
cyros-builder test -p <profile> --list                    # discover only
cyros-builder test -p <profile> --filter multicore        # substring match on test name
cyros-builder test -p build/profiles/unit_test_coverage.toml --coverage
```

`--coverage` requires a coverage-instrumented toolchain (`gcc-coverage.toml`) and `lcov`/`genhtml`
on PATH; the HTML report lands at `<output_root>/coverage/html/index.html`.

`-j/--jobs` is accepted by `build` and `test` but **is not implemented** — `execute_actions` runs
strictly sequentially and never reads it.

## Architecture

### The pipeline

Every command is a thin composition of the same stages:

```
resolve_invocation  →  select_project  →  populate_include_tree  →  plan_build  →  execute_actions  →  build_manifest
   (resolve.py)      (project_model.py)    (include_tree.py)       (planner.py)    (executor.py)      (package.py)
```

- **`resolve.py`** merges profile + CLI overrides into a frozen `ResolvedInvocation`. Everything
  downstream takes this one object; it also records *which* values the CLI overrode, purely so
  `show` can report it.
- **`project_model.py`** reads the component TOMLs under `source_root` and validates the
  selection into a `SelectedProject`. This is where "unknown port", "feature depends on time but
  no time driver", and variant-declaration checks are enforced.
- **`planner.py`** produces a list of frozen action dataclasses (`actions.py`), each carrying a
  *fully materialised argv tuple*. Planners never spawn processes; the executor never makes
  decisions. That split is what lets `gen-db` call `plan_build` and read `CompileAction.arguments`
  to emit `compile_commands.json` guaranteed to match a real build.
- **`executor.py`** runs actions in order via `subprocess.run(check=True)`. It creates output and
  working directories, prints progress, and nothing else.

There is **no incremental build and no dependency tracking**. Every invocation recompiles
everything. Adding staleness checks means adding it to the executor, not the planner.

### Three layers of TOML

| File | Answers | Loaded by |
|---|---|---|
| `profiles/*.toml` | *What* to build: port, time driver, features, layout roots, archive name | `profile.py` |
| `toolchains/*.toml` | *How* to compile: tools, flags, archive strategy | `toolchain.py` |
| `src/**/component.toml`, `port.toml`, `time_driver.toml`, `feature.toml` | *Which* sources and public headers each group owns | `project_model.py` |

All paths inside a TOML resolve relative to **that file's own directory**, never to CWD. Profiles
in `cyros/build/profiles/` therefore reach the source tree as `../../src`.

Toolchain `extends` is a path (not a name lookup) resolved relative to the child file. Merging is
a deep dict merge, with the extra rule that `[flags]` supports `<key>_add` / `<key>_remove` lists
that are flattened into the base list at merge time and then dropped
(`toolchain.py:_apply_flag_add_remove`). Unknown keys in any table are hard errors everywhere —
these loaders are deliberately strict.

### Component selection model

The source tree has a fixed shape that `project_model.py` hardcodes:

- `src/kernel/component.toml` — always built
- `src/port/component.toml` declares `variants`; `src/port/<name>/port.toml` is the selected one
- `src/time/component.toml` + `src/time/<name>/time_driver.toml` — **optional**; when
  `components.time_driver` is unset, no time code is compiled at all and any enabled feature that
  depends on `"time"` is a validation error
- `src/userlib/<name>/feature.toml` — opt-in features, selected by `[features].enable`

Only kernel, the selected port, the selected time driver, and enabled features are compiled. The
`component.toml` files for `port`/`time`/`userlib` are container metadata (variants, shared public
headers) — they contribute headers, not objects.

`sources_excluded_from_archive` compiles a translation unit but keeps it out of the `.a`
(e.g. `validate_config.cpp`, which exists to fail the build on a bad config).

### The generated include tree

`include_tree.py` wipes and rebuilds `<build_root>/include/` on every run, copying each
`public_headers` entry per its `"source -> destination"` mapping, plus the profile's config header
to a fixed `cyros/config/config.hpp`. Compiles get exactly **one** `-I` (that tree) plus any
`private_includes` declared by the owning group. So a source file can see its own directory, its
group's private includes, and the public headers — nothing else. That isolation is intentional;
if a source can't find a header, the fix is usually a missing `public_headers` or
`private_includes` entry, not another `-I`.

### Output layout

```
<output_root>/<profile.name>/<toolchain.name>/
   obj/       mirrors src/ layout; out-of-tree sources go to obj/_external/<component>/
   lib/       the archive (profile output.archive)
   include/   generated public include tree
   manifest.json
```

`output.py` owns every path in that tree — never join build paths by hand elsewhere.

### Archive strategies

`simple` is `ar rcs`. `lto_merged` (see `gcc-release.toml`) partial-links all objects into one
LTO object, optionally runs `objcopy --keep-global-symbols=<exported_symbols_file>` to hide
internals, then archives the single result.

### Unit tests

`test_model.py` / `test_planner.py` / `test_runner.py` are **production modules, not pytest
files** — the `test_` prefix refers to the C++ tests they orchestrate.

Tests are discovered by globbing `<source_root>/../tests/unit/**/test.toml` (hardcoded). Because
each test brings its own config header, each test gets a **complete isolated rebuild of the whole
archive** under `<output_root>/tests/<name>/<profile>/<toolchain>/`. That directory is wiped first.

How a `test.toml` interacts with the profile (`test_runner._make_test_resolved`):

- `[components].port` is a **filter**, not a selection — the test always builds against the
  profile's port, and is *skipped* if the profile's port isn't in its list.
- `[components].time_driver` overrides the profile's. If neither sets one but the test enables
  features, `"simulation"` is the fallback.
- `[components].features` **replaces** the profile's feature set outright.

Execution is two-phase on purpose: build every test first, then run them all, so compiler noise
never interleaves with gtest output. `RunTestAction` is deliberately excluded from
`execute_actions` (it raises if passed one) so the runner can capture per-test results.

## Conventions

- **Three-space indentation** throughout the Python.
- Frozen dataclasses for every model; loaders validate and raise `ValueError` with the offending
  file path as the message prefix.
- Commands are `Command` subclasses in `cyros_builder/commands/`, registered in `cli.py` and
  re-exported from `commands/__init__.py`. Shared flags come from `commands/base.py` helpers.
- Command `run()` methods catch broadly and return `1` with a printed message rather than
  propagating tracebacks.

## Known dead ends

Don't assume these work just because the code mentions them:

- `component.py` is superseded by `project_model.py` and is imported by nothing.
- C++20 modules are half-plumbed: `public_modules`/`private_modules` are parsed and reported in
  `manifest.json`, and `output.module_dir()` exists, but no planner emits a module compile.
  `LinkAction` is likewise defined and handled but never planned.
- The project was renamed CoRTOS → Cyros; `cortos` survives in docstrings, and as the hardcoded
  intermediate object stem in `_plan_lto_merged_archive`.
- The tracked `src/`, `profiles/`, `configs/`, `toolchains/` at this repo's root are stale
  leftovers from before the source moved to `../cyros` — `profiles/example1.toml` points at a
  `source_root` that no longer exists, and the local `component.toml`s declare no `sources`.
  Use `../cyros` for anything real.

---

# Planned work

Three tracks, in this order: **test harness → cleanup → performance**. The ordering is load-bearing:
the cleanup is a large behaviour-preserving refactor and the performance work introduces caching
(the classic source of "stale artifact" bugs). Both need a regression net that does not exist today,
and building that net first is what makes the other two safe to do quickly.

## Measured baseline (2026-07-29, against `../cyros`)

| | |
|---|---|
| Unit tests | 17 |
| Distinct `(config, port, time_driver, features)` tuples | 12 |
| Distinct config header contents | 5 |
| TUs per archive | ~10 (kernel 6 + port 2 + driver 0–1 + features 0–3) |
| Archive builds per `test` run | 17 (one per test, always from scratch) |
| Compiles per `test` run | ~170, sequential, no reuse within or across runs |

Re-measure after each phase; these numbers are the success criteria.

## Track 1 — Test strategy

### The problem with both current options

Testing only against `../cyros` is slow, needs a working GCC 15 + Boost + gtest, and — the real
issue — it exercises exactly one point in the builder's configuration space. Most of what can
regress here (flag merging, path resolution, component selection, validation errors, archive
strategies) never gets touched by one real profile. A hand-maintained mock repo fixes the coverage
gap but reintroduces the maintenance burden that motivated dropping it.

### Recommendation: test the plan, not the artifacts

The plan/execute split is the asset. `plan_build()` is a **pure function** from
`ResolvedInvocation` to a list of frozen dataclasses with fully materialised argv. Assert on that
list and you get near-total coverage of the builder's decision-making with no compiler, no
filesystem writes, and no flakiness. This is the answer to "doesn't always catch regressions":
plan-level tests catch precisely the regressions an end-to-end run misses.

Split the suite three ways:

1. **Plan-level golden tests (the bulk).** Serialise `plan_build()` / `plan_test()` output to JSON
   golden files, with paths made repo-relative so they're stable. Cover: both archive strategies,
   toolchain `extends` chains with `_add`/`_remove`, absent time driver, feature dependency
   failures, port variant validation, `sources_excluded_from_archive`, out-of-tree sources landing
   in `obj/_external/`, header export mapping. Also golden the *error messages* — the loaders'
   strictness is a feature and its diagnostics are part of the contract.
2. **A minimal synthetic fixture repo** at `tests/fixtures/` mirroring the real layout but with
   trivial C++ (empty TUs, one function). It exists to give the golden tests something structurally
   realistic to chew on, and to let a handful of genuinely end-to-end tests compile in well under a
   second. Deliberately richer than `../cyros` in *shape* (two ports, a driver-less profile, an
   external source, both archive strategies) while being far smaller in content.
3. **Conformance tests against `../cyros`, skipped when absent.** Two cheap ones carry most of the
   value: parse every TOML under `../cyros` and assert it loads (catches schema drift in one
   second, and the strict loaders make drift a hard error rather than silent misbehaviour), and
   golden the *plan* for each real profile without executing it. Full compile-and-run stays a
   manual/CI step, not something on the inner loop.

### Keeping the fixture honest

The fixture drifts if nothing pulls it forward. Two mitigations, both cheap:

- The `../cyros` TOML-parse conformance test fails the moment the real repo grows a key the
  loaders don't know — which is exactly when the fixture needs updating too.
- Convention to record here once it exists: **a new TOML key is not done until the fixture uses it
  and a golden test covers it.**

### Mechanics

- `pytest` as the runner; add `[tool.pytest.ini_options] testpaths = ["tests"]` to `pyproject.toml`
  **before writing any test** — otherwise pytest collects `cyros_builder/test_model.py`,
  `test_planner.py`, and `test_runner.py` as test modules and fails on import. Renaming those to a
  `cyros_builder/suite/` subpackage is the clean fix; it's listed under cleanup as optional churn.
- Add a `dev` extra in `pyproject.toml` (currently `dependencies = []`, which should stay true for
  the runtime package — `tomllib` is stdlib and it's worth keeping it that way).

## Track 2 — Cleanup

Do this **after** the golden tests exist and **before** the performance work, verifying at each step
that the golden plans are byte-identical. All of it is behaviour-preserving.

**High value:**

- **Collapse `project_model.py`'s six near-identical loaders.** `load_kernel`, `load_port_component`,
  `load_ports`, `load_time_component`, `load_time_drivers`, `load_features` are ~30 lines each
  differing only in filename, `source_roots` default, and one or two extra fields. One
  `_load_source_group(path, cls, *, source_roots_default, **extra)` replaces ~180 lines with ~30.
  This file is where new component features get added, so the duplication has an ongoing tax.
- **Extract the TOML helpers.** `_require_str` / `_optional_str` / `_optional_str_list` /
  `_require_bool` and friends are copy-pasted across `profile.py`, `toolchain.py`,
  `project_model.py`, `test_model.py`, and `component.py` — five divergent copies with subtly
  different empty-string and default handling. One `tomlutil.py` with accessors that carry the
  source path for error messages.
- **Unify error handling.** Every command repeats `try/except Exception → print → return 1`, which
  discards tracebacks; `build.py` calls `traceback.print_exc()` in one branch and not the others.
  Introduce a `BuilderError` raised by loaders/planners, handle it once in `cli.py`, and re-raise
  everything on `--debug`. Deletes ~60 lines of boilerplate and makes failures debuggable.
- **Delete `component.py`** — dead, superseded by `project_model.py`, imported by nothing.
- **Fix `commands/test.py:_resolve_without_config`.** It duplicates `resolve_invocation` and
  fabricates `config_header=Path("/dev/null")`. Make `ResolvedInvocation.config_header` a
  `Path | None` and give `resolve_invocation` a `require_config: bool` parameter.
- **De-duplicate the per-test invocation.** `coverage.py` hand-rebuilds a `ResolvedInvocation`
  that must stay in lockstep with `test_runner._make_test_resolved`; they will diverge. One shared
  constructor in `test_planner.py`.
- **Unify compile-argv construction.** `planner._compile_args` and `test_planner.plan_test` build
  compiler command lines independently — test compiles already silently miss `private_includes`,
  and the incremental work needs `-MMD` added in exactly one place.

**Lower priority:**

- Type the action lists. `plan_build`, `execute_actions`, and `print_action_plan` all take/return
  bare `list`. A `BuildAction | TestAction` union alias would surface at type-check time what
  `execute_actions` currently enforces at runtime by raising on `RunTestAction`.
- `ui.print_action_plan` and `executor._progress_label` are parallel isinstance-chains that must be
  updated in lockstep for every new action type. A `describe()` / `label()` method on the action
  dataclasses removes the coupling.
- Hoist function-local imports (`import dataclasses` inside `_make_test_resolved`, the `coverage`
  import inside `TestCommand.run`, the `ResolvedInvocation` re-import inside `coverage.py`).
- A small `log.py` with quiet/normal/verbose levels; `executor`, `test_runner`, and `coverage` each
  reimplement verbose handling.
- Dead branch in `planner._language_for`: the `source.suffix == ".S"` check is unreachable because
  the preceding check already lowercased.
- Purge the remaining `cortos` strings, including the hardcoded object stem in
  `_plan_lto_merged_archive`.
- Optional churn: move `test_model` / `test_planner` / `test_runner` into `cyros_builder/suite/`.

## Track 3 — Performance

Ordered by value-per-effort, not by architectural tidiness. Phase A alone should be the single
biggest wall-clock improvement and carries essentially no correctness risk.

### Phase A — actually implement `-j`

`-j/--jobs` is already parsed and documented; the executor ignores it. All ~170 compiles in a run
are independent — only the archive chain has ordering constraints. A `ThreadPoolExecutor` over the
`CompileAction`s followed by the serial archive chain is a small change for a 4–8× wall-clock win
on a multicore box, and because nothing is being *skipped*, it cannot produce a stale artifact.

Watch for: interleaved compiler stderr (buffer per action and emit atomically on completion), and
fail-fast semantics — the first non-zero exit should cancel pending work rather than letting the
rest of the pool run.

### Phase B — cross-run incrementality

This is the actual complaint. Today, changing one test's `.cpp` recompiles all ~170 TUs.

**Blocker first:** `include_tree.populate_include_tree` does `shutil.rmtree` then re-copies on
*every* invocation. Every generated header therefore gets a fresh mtime on every run, so every
object would look stale and no amount of staleness logic would help. Make it idempotent — write
only when content differs, and remove files no longer in the export set. This must land before
anything else in this phase.

Then:

- Add `-MMD -MF <obj>.d` to compile actions (single place, once Track 2 unifies argv construction)
  so the real header dependency set is recorded.
- Add a `<build_root>/.build-state.json` mapping output path → `{argv_hash, inputs: {path: hash}}`.
- Add a **prune stage between plan and execute** — `prune_actions(actions) -> actions` in a new
  `staleness.py`. This preserves the plan/execute split: the planner still decides *what a full
  build is*, the executor still just runs what it's given, and the new stage owns the single
  question "what changed". `gen-db` keeps consuming the unpruned plan, so the compile database
  stays complete.
- An action is stale if its output is missing, its argv hash changed (catches flag and toolchain
  edits), or any input's content hash changed. **Use content hashes, not mtimes** — the generated
  include tree and git checkouts both make mtimes lie.
- Staleness is transitive along the archive chain: a stale object forces partial-link → objcopy →
  `ar`. Also re-archive when the member *set* changes, not just member contents.
- `--clean-first` already exists as the escape hatch; add `--force` to bypass pruning without
  deleting.

### Phase C — share archives across tests

12 distinct configurations across 17 tests, so this removes 5 of 17 archive builds — around 30% of
a cold `test` run, and less than that once Phase B makes warm runs cheap. Worth doing, but it is
not the headline and should not be attempted before A and B.

Key the archive directory on a hash of the resolved configuration (toolchain name + full flag set,
port, time driver, feature set, config header *content*, archive name) at
`<output_root>/archives/<hash>/`, and have each test link the archive for its configuration. This
also removes the unconditional `shutil.rmtree` of the per-test output root in
`test_runner._build_one`, which currently defeats reuse by construction.

### Phase D — incremental testing

Skipping *compilation* of unchanged tests falls out of Phase B for free and is safe.

Skipping *execution* is a different risk class — it hides flaky and order-dependent tests, and this
is a concurrency-heavy SMP kernel where those are exactly the failures worth catching. Recommend:
**always run every selected test binary by default**, and put run-skipping behind an explicit
`--only-changed` flag backed by a `.test-state.json` of last-known-green binary hashes. Test
execution is fast relative to compilation, so the default costs little.
