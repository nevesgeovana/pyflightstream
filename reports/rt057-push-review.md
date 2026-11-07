<!--
GEOVERSE_HEADER
file_version: 1.0.0
artifact_id: reports/rt057-push-review.md
last_modified_at: 2026-11-07T21:50:05.819391+00:00
last_modified_by: OpenAI / Codex / GPT-6 / gated-reviewer
dependencies: [FR-3769, FR-3770, PFS-2201.01, PFS-2201.03]
authority: pyflightstream
status: active
confidentiality: internal
change_summary: Record one PUSH review, F1 and F2 fixes, measured checks and remaining findings.
revision_source: git
-->

# RT057 PUSH review

Reviewed range: `3b288d875..edb978e85`. Review branch: `review/rt057-r1`,
initially clean at `edb978e85`, in `C:/WORK/rt057-review` supplied by the owner.
One round, QA, V&V and architecture lenses. No push, merge, licensed solver run,
or owner-reserved naming/default decision. F1 and F2 were the explicitly requested
repairs. Additional findings below are registered, not silently treated as fixed.
This report is not a clean landing attestation: F3 and F4 remain behavior gaps.

## Findings, most severe first

### F3: Local grouped runtime requests are rejected (medium, registered)

- Anchor: `src/pyflightstream/run/_executors.py:1728-1731`, reached by
  `_points._prepare_point_script`; `run/_batch_run.py:707` constructs the adapter.
- Defect: the new concrete `isinstance(executor, LocalExecutor)` check treats
  `GroupingExecutor(LocalExecutor(...))` as a nonlocal launch.
- Consequence: an otherwise local `--batch` or `--polar-sweep` run with a runtime
  request is refused before emission. The diagnostic incorrectly says it needs
  a local launch, which it already has.
- Contract: FR-3770, Launch runtime setup; the documented restriction is to
  local solver-machine execution, not to unwrapped executor objects.
- Evidence: a real `GroupingExecutor` wrapping a real, solver-free constructed
  `LocalExecutor`, passed to `_with_the_profile_s_log` with `max_threads=3`, raises
  `CampaignConfigError: [runtime] requires a local launch on the solver machine`.
- Fix shape: resolve against the actual local launch executor, carry the result
  into grouped emission, and bind the environment again at each actual job
  launch. Group compatibility must include the effective runtime policy; simply
  unwrapping the staging adapter would leave the last staged row's mutable
  executor policy in place for later jobs. Test two groups with different policies.

### F4: Grouped unsteady steps have no timing evidence (medium, registered)

- Anchor: `src/pyflightstream/cases/workflows/_batch_actions.py:321-330` and
  `src/pyflightstream/run/_batch_run.py:423-425`; compare the new timing read at
  `src/pyflightstream/run/collect.py:1078-1081`.
- Defect: the grouped route executes `render_job_counter_program`, whose separate
  template writes only counts, rather than either modified per-point template.
- Consequence: completed unsteady steps in grouped runs have no timestamps,
  intervals or mean in the run/cost evidence. Collection cannot recover data the
  callback never recorded.
- Contract: FR-3769, Per-step run timing, and docs/solver-cost.md's unqualified
  statement that unsteady records carry the new measurements.
- Evidence: executing the generated grouped counter twice with a one-point,
  two-step synthetic schedule produces exactly `{"count": 2}` in that point's
  counter; `read_step_timing` returns `{}`.
- Fix shape: record timing in the grouped callback's per-point state and cost
  sidecar; reset interval origin at point transitions without assigning a prior
  point's elapsed time to the next. Test at least two points through collection,
  including the documented unknown-origin first interval.

### F2: Non-integer Linux core_type aborts detection (medium, fixed)

- Anchor: `src/pyflightstream/run/_runtime.py:159-163`.
- Defect: the reviewed `int(kind.read_text())` propagates `ValueError` for a
  non-integer class instead of using the requested unknown-class fallback.
- Consequence: runtime resolution aborts an otherwise usable local launch.
- Contract: the owner's F2 instruction and FR-3770's launch topology resolution.
- Property written before editing: non-integer core-type text becomes class 0;
  valid integers, missing metadata and unrelated topology errors retain their behavior.
- Fix: catch only `ValueError` around that conversion. Commit `973f43482`.
- RED: `test_linux_non_integer_core_type_falls_back_to_zero` failed at the reviewed
  production code on its fallback assertion, with `invalid literal for int()` for
  `unknown`. It reaches the actual parser through a temporary sysfs tree.
- GREEN: runtime suite after F2: `3 passed, 8 subtests passed`.

### F1: Native topology parsers were untested (medium, fixed)

- Anchor: `src/pyflightstream/run/_runtime.py:87` and `:146`; new controls in
  `tests/tier1_offline/test_rt057_runtime.py:169`.
- Defect: the reviewed tests inject normalized topology dictionaries and never
  exercise native relationship decoding, sysfs reading or detector dispatch.
- Consequence: wrong class offsets, lost processor groups or merged package/core
  identities pass the existing tier-1 gate and can resolve the wrong resources.
- Contract: PUSH V&V non-vacuity and CONTRIBUTING.md's falsifiable regressions.
- Property written before editing: offline tests assert decoding of fixed raw
  inputs; production parsing and public behavior are unchanged by this test fix.
- Fix: three parse-level tests, with four malformed-buffer subcases. Windows uses
  a fixed synthetic x64 byte buffer and fake two-call API/registry transport;
  Linux uses raw sysfs/cpuinfo text in a temporary tree. Both reach `detect_topology`.
  No native host or solver is needed. The buffer is explicitly synthetic, not a
  claimed hardware capture.
- Coverage: Windows core class, SMT masks, package count, nonzero processor group,
  overlapping legacy/extended NUMA records, record bounds and incomplete data;
  Linux online filtering, missing online/core-type files, SMT siblings, repeated
  core IDs across sockets, NUMA membership and fallback, vendor and summary.
- The fixed Windows buffer uses the documented layouts of
  [PROCESSOR_RELATIONSHIP](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-processor_relationship),
  [NUMA_NODE_RELATIONSHIP](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-numa_node_relationship)
  and [GROUP_AFFINITY](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-group_affinity).
- Discrimination: all five in-memory mutants below pass the two original runtime
  tests, but each fails one assertion in the new parser tests, with zero test
  errors. The unmutated reviewed parser passes all three new tests. That last
  result is expected for a coverage repair, not represented as a behavior RED.

| Mutant of reviewed source | New parser-test result |
| --- | --- |
| Windows class offset `row[9]` to `row[8]` | 1 assertion failure |
| Windows processor ID `group * 64 + bit` to `bit` | 1 assertion failure |
| Ignore relation 6, NUMA-Ex | 1 assertion failure |
| Linux core key `(socket, core)` to `(0, core)` | 1 assertion failure, `2 != 4` cores |
| Replace rather than append Linux SMT sibling | 1 assertion failure, `4 != 5` logical CPUs |

Mutations were compiled from `git show edb978e85:src/pyflightstream/run/_runtime.py`
into the module dictionary under a restoring mock context; no tracked source or
other worktree was changed for these controls.

### F5: Unrecorded fields are serialized despite absence claims (low, registered)

- Anchor: `src/pyflightstream/workspace/manifest.py:814-821,964-966`;
  `src/pyflightstream/script/solver_setup.py:598-609`;
  `docs/solver-cost.md:169`.
- Defect: new optional timing fields and `solver_setup.runtime` are omitted from
  the existing serializers' omission rules, so unstated values serialize as null.
- Consequence: reserializing a legacy record or an ordinary no-runtime setup adds
  keys; the statement that old records keep timing fields absent is false.
  No solver-thread behavior change is claimed from this serialization difference.
- Contract: the stated absent-field compatibility in docs/solver-cost.md and the
  serializers' existing unrecorded-key contracts.
- Evidence: an unstated RunRecord serializes all three `step_wall_*` keys to
  `None`; `SolverSetup(fs_version="26.124", flags={})` serializes `runtime: None`.
- Fix shape: extend the omission rules for unrecorded values and test the legacy
  serialized key set alongside a populated timing/runtime round trip.

### F6: Documentation leaves decided defaults open (low, text, registered)

- Anchor: `docs/setup-standards.md:315-316`.
- Defect: the page says the owner's choice of future defaults is still open,
  although this review's authoritative instruction settles opt-in/unset defaults.
- Consequence: readers can mistake the implemented defaults for an unresolved choice.
- Contract: the owner's explicit opt-in decision; PUSH text findings are registered.
- Fix shape: remove the unresolved-decision sentence and retain the existing unset
  default description. No naming/default decision is requested or made by this review.

## Clean areas and evidence limits

- Resolution: examined hybrid Intel, homogeneous SMT/non-SMT and multi-NUMA
  branches; explicit positive thread counts; strict invalid-value refusal;
  affinity-only legacy thread handling; legacy-count conflict checks; local versus
  submitting behavior. No additional direct-local resolution defect found beyond F2.
- Environment: nine mocked subprocess-boundary checks passed: progress Popen,
  coupled Popen and direct subprocess.run, each with auto, all and unset affinity.
  They assert exact effective KMP keys, preservation of an unrelated license
  sentinel and unchanged parent environment. No real executable starts.
- No block: the existing test proves no topology detection, no derived thread
  emission and executor-policy reset; direct launch checks preserve inherited KMP
  variables when affinity is unset. The serialization difference is separately F5.
- Timing: both per-point generated programs execute 23 callbacks; tests assert
  count, every interval, last-20 mean, sidecar, record round trip and cost values.
  The unknown first interval is checked. These are discriminating component tests,
  but manually constructing the record does not cover the local/collect wiring.
  Both clocks receive the same mocked values, so clock-adjustment independence is
  established by code inspection here, not by those tests. F4 covers the omitted route.
- Architecture: settings belong in cases, detection/resolution and execution in
  run, record storage in workspace, and cost reading in qa. No new upward import
  found. Eight relevant layer/import guard tests pass.
- Claims: homogeneous policies are explicitly labeled inferred, not measured.
  Parsing fixtures, environment transport and script emission do not prove actual
  solver affinity or throughput. No licensed acceptance/performance claim is added.

## Test results

All pytest commands used `PYTHONPATH=C:/WORK/rt057-review/src`.

| Measurement | Result |
| --- | --- |
| Five requested files at reviewed head | 62 passed, 10 subtests passed |
| Five requested files after F1/F2 | 66 passed, 14 subtests passed |
| test_conventions.py, `-k 'layer or import'` | 8 passed, 9 deselected |
| Ruff check and format on changed source/test | passed |
| mypy on run/_runtime.py and cases/runtime.py | no issues in 2 source files |
| Subprocess-boundary environment probes | 9 passed |
| F1 original-test mutation control | all 5 mutants survived |
| F1 new-test mutation control | all 5 mutants failed assertions; zero errors |

The five requested files are `test_rt057_runtime.py`, `test_rt057_step_timing.py`,
`test_qa_cost.py`, `test_goal031_g08_glossary_claims.py` and `test_suite_packages.py`,
all under `tests/tier1_offline`. The final run took 20.58 seconds and reported one
external dateutil `utcfromtimestamp` deprecation warning. Mypy reported notes about
unchecked untyped bodies, not errors. F2's commit hooks passed.

Not run: full tier 1, complete CI/release gate, docs build, real Linux/Windows
native API execution, licensed tiers 2/3, or target-machine performance/affinity
measurements. The diff of all 25 files was reviewed; broader source reading was
limited to the execution, grouping, collection, serialization and guard seams above.

## Session boundary receipt

Root AGENTS.md, SESSION-BOOTSTRAP.md, header/identity standards, workspace/provider
registries and the named pillar sources were consulted. The repository remote
matches `https://github.com/nevesgeovana/pyflightstream.git`. The current-file
pillar manifest is not certified current: three required source hashes differ
(bootstrap, architecture, pyproject), and its accepted HEAD predates this range.
The owner's explicit worktree/review instruction supplied the working authority;
no control-plane pin or other worktree was edited. Provider registry lists Codex
as pending-adoption; this review does not claim native provider-gate enforcement.
The staged-content hook reported routing disabled for this review worktree while
its content check and repository pre-commit checks passed.

Observed pillar SHA-256 values, in canonical order. These are exact working-file
byte diagnostics, not portable Git-index completion attestations:

| Pillar | SHA-256 |
| --- | --- |
| Root contract | 4bc2e5db73ac5a5683555bb700322c8b653fac6023cd6364a4d8cc96dd19d2b2 |
| Bootstrap (drift) | 0d0bfcf427f56e0b5ca348e9b2fc9dcfb708d5c8db4b485e416874a6bdc26f4a |
| Workspace registry | 4ac06070e12e3aea610b9e09a2f09f93433527c54dfa67fd00e3a71332c49e92 |
| Provider registry | d5cbdcfdb87c7ad01309609df79d0d21cfc903e74f0a4243f4ee752d59ca4184 |
| Shell dialect | d213f0c1ca5d0c157fdf7935f51c2c542770fe8705450bedaf0194b445fff686 |
| VCS boundary | 29c34fc9657040b7466e4dc1a7e116046dfc07f46b6086052c1840b13551f48c |
| Reviewer policy | 55b713378dacaf7f8d89b6a134bafe01f9f8ec0c795d0817296d6ca7ebff125e |
| Develop capability | 6a5f4c664a6b532c246f2a8d764f3d2ab4daf0af70a87a0e162c20bd13a0ef75 |
| README | 0bd9ed0805644373abe3743233f657d605af04483849042188dfa6ac2959f0a3 |
| Architecture (drift) | f55ff87c29d429ab8f0be48cdd06813f8c0627cd9a58ee807d7c5385eda39e69 |
| CONTRIBUTING | dd49c69a4d0c79f58148324df6fc294ecd9eb18b6f035d5111bd3a37e8cc5797 |
| pyproject (drift) | 9fc0ed6f981ece0d7f1a6627410d8213a286987966763d54e169fd7e0aba8f55 |
| Handoff (historical context only) | de7b2a60b390d0d34ba9ca4e4f99d06de46fb838f257d99a0fdc4831c892d572 |
