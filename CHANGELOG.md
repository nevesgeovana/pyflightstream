# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

### API surface delta

* **The FSI and probe paths are declared experimental, behind an
  explicit boundary** (author's decision, 2026-08-03; REV010-017).
  Documentation only.

  The README gains a **Capability status** table saying, per
  capability, what is supported, what is experimental, what is not
  validated, and what evidence stands behind each. Experimental means
  the interface may change without NFR-20's deprecation window and
  that the evidence is narrower than the supported rows: replaying
  archived fixtures shows the machine runs, not that its physics is
  right for a case nobody has measured. The rotary two-way coupling
  is listed as **not validated**, which `reports/RPT-007` and the
  roadmap's M6 row have said since 2026-07-21 and which no page a
  reader lands on repeated.
* **Six documentation claims corrected, and guarded** (REV010-017,
  REV010-018).

  `pyflightstream.files` was removed at v0.4.0 and three surfaces
  still described it as surviving. NFR-18 said "the manifest carries
  no version field today" while the field had been live since
  `c7cfdad`, so it now reads **implemented**. The README said the
  worked examples reach "coupled aeroelastic runs" and no example
  calls the coupling driver. The index generator documented three
  emitted fields while writing six. NFR-25's evidence line still named
  `require_extra` after the rename to `missing_extra`. And the
  role-review skill called the attestation "the mechanical proof that
  the real agents ran", which the hook implementing it explicitly
  refuses to claim about itself: the `passes` field is recorded and
  never checked, the file is local and gitignored, and any process
  that can write it clears the gate.

  New `tests/test_claim_currency.py` compares each of these claims
  with its subject, so the next drift fails tier 1 instead of waiting
  for a reader.
* **The far-field coverage metric counts what it says it counts**
  (REV010-011). **Breaking** for readers of `masked_fraction`, whose
  value changes when inputs are non-finite.

  `irreversible_deficit` masked on `radicand < 0`, and every
  comparison against NaN is False, so a NaN radicand was neither
  masked nor counted while `sqrt` returned NaN anyway. For radicands
  `[-1, NaN, 1]` two of three outputs were NaN and `masked_fraction`
  reported 1/3, overstating how much of the field the evaluation had
  honored, which is the one thing the metric exists to prevent.

  The dataset now carries `negative_radicand_fraction` (a physical
  statement about the solution: the local state is unreachable on an
  isentropic rothalpy-conserving streamline) and
  `invalid_input_fraction` (a statement about the input), with
  `masked_fraction` their non-overlapping union.
* **NFR-07 says what the implementation delivers** (REV010-013).
  Requirement text only; no code change.

  It promised inputs and invocation "reproducible from its manifest
  entry alone", while `RunRecord` stores hashes and paths rather than
  content and `reconstruct()` requires the workspace and refuses when
  the staged script is absent. The implementation was sound under a
  "manifest plus preserved artifacts" contract, which is what the code
  docstrings had said all along; the requirement now says it too. The
  entry alone identifies and verifies the artifacts by hash and states
  when one is missing or changed.
* **FSI state and loads are bound to the physical model they belong
  to** (REV010-008, REV010-009, REV010-010). **Breaking** for runs
  that were relying on any of the three.

  `FsiState` gains `config_hash`, and a resume across a different
  configuration is refused. Shape compatibility is not physical
  identity: a state saved at `stiffness_scale_factor=1` was accepted
  by a configuration with 999, because blade and station counts
  survive a change of stiffness, mass, rotational speed, offsets or
  relaxation policy. Pass `allow_config_change=True` to carry the
  memory across deliberately. The shape check still runs first, so a
  moved station keeps its specific message.

  `to_elastic_axis` now requires the sections to **cover** the
  configured blade, not merely to fit inside it. `numpy.interp`
  extrapolates constantly from the endpoints, so sections covering
  `[0.8, 1.2] m` were spread across a blade spanning `[0.25, 1.85] m`
  and the structural model received an applied load over a domain the
  evidence never measured, while the logged integral covered only the
  measured interval. The allowed margin is 5% of span at each end,
  calibrated from the committed WP1 export, whose real margins are
  2.49% and 2.31%.

  Phase 3 now requires **both** of its documented criteria before
  phase 4 begins: tip twist settled *and* integrated normal force
  stable between revolutions, the latter against the new
  `PhaseSchedule.thrust_tolerance_fraction` (default 0.02).
  `RevolutionSample.total_normal_force_n` carries the force that was
  previously computed, written to the convergence log, and never
  compared with anything. The configuration docstring had described
  this two-criterion model all along.
* **Publication is coupled to the gates, and to the exact wheel they
  tested** (REV010-016, REV010-019). Release process only; no runtime
  change.

  `publish` depended on `build` alone, so a tag could publish while CI
  was failing, and what shipped had never been exercised: CI installs
  the source in editable mode and tests that instead. The release
  workflow now builds once, records the wheel's SHA-256, installs
  **that wheel** into clean jobs on Linux and Windows at both declared
  Pythons, runs the tier-1 suite and the executable examples against
  it, runs the lint, type, coverage and docs gates, and re-checks the
  digest immediately before publishing. `publish` waits for all of it.

  Every action in all three workflows is pinned by commit digest: a tag
  is mutable and can be repointed at new code with nothing appearing in
  this repository's diff. The release build installs pinned `pip`,
  `build` and `twine` rather than whatever is current. The docs
  workflow no longer grants `pages: write` and `id-token: write` at
  workflow scope, where the dependency-installing build job also
  received them; only `deploy` asks for them.

  New `tests/test_workflow_supply_chain.py` holds all of this as
  repository guards, so a regression fails tier 1 rather than waiting
  for a reviewer to notice.
* **The development tree no longer identifies as the last release**
  (REV010-015). `pyproject.toml` and `CITATION.cff` read
  `0.4.0.dev0`; the release commit sets `0.4.0`.

  HEAD was 66 commits past `v0.3.0` and carried landed v0.4.0 breaking
  removals while every identity still said `0.3.0`, so two
  behaviorally incompatible artifacts answered to one number and no
  bug report, manifest, cached environment or citation could tell them
  apart. A wheel built from this tree now reports `0.4.0.dev0`,
  verified on the built artifact rather than on source metadata.

  New `tests/test_version_identity.py` refuses the combination that
  causes it: a **final** version and a non-empty `Unreleased`
  changelog section may not coexist. It is deliberately conditional.
  The obvious form of this check, "the version must name the current
  commit", is red on every ordinary commit because ordinary commits
  are not tagged, and a suite that is red by construction is worse
  than no suite (`PLN-20260803-1650` recorded that trap before the
  guard existed).

  Choosing the versioning **scheme**, a static development version as
  now or a VCS-derived one such as `setuptools_scm`, remains the
  author's release-time decision and is not made here.
* **A historical manifest row is no longer rewritten as current**
  (REV010-014). **Breaking**: `RunRecord.manifest_schema` is
  `str | None` with default `None`, and `reconstruct` refuses a row
  that carries no schema.

  `manifest_schema` defaulted to `MANIFEST_SCHEMA`, so reading a
  historical manifest stamped every row in it with a positive claim
  about a layout that never described it, and `append_record`
  re-serialized the validated models back to disk, persisting the
  claim: appending one run rewrote each older row with more than
  twenty defaulted fields. `None` now means "predates the field",
  which is a different fact from "asserts the current schema".

  `CampaignWorkspace.read_raw_manifest()` is new and returns the rows
  as written, with nothing defaulted; `append_record` writes through
  it, so existing rows are carried across byte for byte. Migrating a
  manifest is a separate, deliberate act rather than a side effect of
  recording the next run.

  **Correction to the record.** The commit message of `4beb710`
  (v0.4.0 development, pushed) states that this default became `None`
  in that commit. It did not: the only change that commit made to
  `workspace/__init__.py` was an `__all__` sort-order move, and the
  default was still `MANIFEST_SCHEMA` until the present change. The
  claim described work that was intended and not done. History is not
  being rewritten, so the correction is recorded here and in the plan
  ledger instead.
* **An ambiguous export is refused instead of resolved by position**
  (REV010-003, REV010-006). **Breaking** for files that were being
  silently half-read.

  `parse_probe_points` did not require unique header names, while
  `ProbePointsReport.field` returns the first tuple index of a name and
  `fields()` collapses duplicates into one key. A header rewritten from
  `Mach, Cp_ref` to `Cp_ref, Cp_ref` was accepted and
  `field("Cp_ref")[0]` returned the Mach value. The loads parser has
  refused this since PYFS-009; both call the shared
  `results.reject_duplicate_columns` now, which also compares case
  folded, so `Cp_ref` and `CP_REF` no longer count as different fields.

  Two concatenated exports were accepted as one: the software footer is
  located with a first-match search and the table helper stops at the
  first closing separator, so a second complete export was invisible
  even to the duplicate-`Total` guard that exists for this class of
  confusion. `results.reject_trailing_export` refuses a second footer
  in both parsers, because which export a file is evidence of must not
  be decided by position.
* **Non-finite values are refused at the choke points that emit and
  place geometry** (REV010-004, REV010-005, REV010-012). **Breaking**
  for code that passed NaN or an infinity into any of the three.

  `Script.emit` type checked a FLOAT and NaN *is* a float, so
  `emit("SOLVER_SET_CONVERGENCE", math.nan)` rendered
  `SOLVER_SET_CONVERGENCE nan`. `SolverSettings` guards finiteness one
  layer up; `emit` is a documented public interface that goes past it.
  Scalars and every element of a FLOAT_LIST are checked now.

  `ProbeLattice` gains `allow_inf_nan=False`, which is not redundant
  with its validator but what makes it work: every check there is an
  inequality and every inequality against NaN is False, so a NaN tip
  radius, station or ring edge passed by not being caught. The lateral
  closure cylinder gains the domain checks it never had, a positive
  radius and strictly increasing stations.

  `campbell_sweep` built each point with `model_copy(update=...)`,
  which assigns without validating, so a negative or non-finite Omega
  reached the modal solve although `FsiConfig` refuses both at
  construction. Each sweep point is validated through that same model
  now, before the first solve rather than after two of them.
* **A result is now bound to the operating point it claims**
  (REV010-001; independent review REV-010 of commit `4beb710`).
  **Breaking**: a collected export whose printed conditions disagree
  with the requested point is `FAILED_INCOMPLETE_OUTPUT` instead of
  `CONVERGED`.

  `LoadsAssessor` received the `SimCase` and never read it. A valid,
  complete, genuinely converged export printing `alpha=2 deg` was
  accepted as the evidence of a point requesting `alpha=0 deg`, and
  the manifest recorded `CONVERGED` for the wrong engineering case.
  Nothing about such a file is malformed, which is why no parser guard
  could see it. The comparison existed in the tabular layer, which the
  manifest never consults, so the status was authorized long before
  anything disagreed.

  New `pyflightstream.results.conditions` holds the comparison once:
  `bind_conditions`, `ConditionBinding`, `ConditionCheck` and the
  `FIELD_BINDINGS` table (alpha and beta in deg, free-stream velocity
  in m/s, each with a tolerance that is print resolution rather than
  an allowance for drift). Both consumers call it: the assessor before
  a status is decided, and `run_table`/`parse_run_loads` when reading
  a recorded run back.

  `Assessment.conditions` and `RunRecord.conditions` persist the
  decision on **every** outcome: axis, requested, reported, deviation,
  tolerance, unit and whether it was accepted. `None` means an
  assessor that does not compare, including every row written before
  the field existed; an empty list means the comparison ran with
  nothing to compare. A reader must be able to tell "checked and
  agreed" from "never checked".
* **An impossible count and an unrecognized solver mode are no longer
  successful outcomes** (REV010-002, REV010-007; independent review
  REV-010 of commit `4beb710`). **Breaking** for anything that fed the
  parsers malformed exports and got a number back.

  `parse_count` refused a fractional count and accepted `-1`, which is
  a perfectly whole number and not a possible iteration. It takes a
  `minimum` now, defaulting to 0 for iteration NUMBERS and passed as 1
  where the field is a requested budget, because a solve of zero
  iterations did not produce the export the number is printed in.

  The loads assessor tested for `"steady"` and let every other value
  fall through to the unsteady branch, which returns
  `COMPLETED_MAX_ITER` with no error: a mode this package has never
  seen became a successful terminal state. The vocabulary is now
  explicit as `results.SOLVER_MODES`, `results.classify_solver_mode`
  answers whether a printed mode is one of them, and an unrecognized
  one is `FAILED_INCOMPLETE_OUTPUT` before any judgment rule is
  chosen, including the residual path. The printed string stays on the
  report as evidence; only the judgment changed.

  `fsi/loads.py` kept its own `int(parse_number(...))` after the
  results parser had already centralized the exact form, so a declared
  `100.9` sections truncated to `100` and then agreed with the 100 rows
  below it. Both sites use the shared parser now. That is the review's
  own diagnosis of this repository's recurring shape: a guard added at
  one layer while the same invariant stays false at another.
* **FR-08's evidence line names a mechanism that exists** (SRS FR-08,
  reworded; new `tests/test_clean_room.py`). No runtime change.

  The requirement said clean-room provenance "is verified by the
  contribution attestation recorded per change". Measured: 200 commits,
  0 `Signed-off-by` trailers, no per-change attestation of any kind.
  The evidence line named an artifact that had never been in this
  repository.

  Every commit now carries a `Clean-room` trailer, and a tier-1 test
  asserts it for every commit since a stated baseline, with the
  declaration's text pinned so it cannot degrade to a bare "yes". The
  push gate is deliberately NOT cited as the evidence: it records that
  a review happened, says so about itself, and is silent on
  provenance, so pointing FR-08 at it would be a second overclaim
  narrower than the first.

  The limit is stated in the requirement rather than left to a reader:
  nothing can prove "the predecessor was never read". What a process
  can preserve is a declaration and an auditable record of who made it.
* **Two guides join the docs**: [Getting
  started](docs/getting-started.md), which goes from `pip install` to a
  read result with the solver appearing only at the last step, and
  [Replaying a recorded run](docs/tutorial-replay.md), which is what
  the manifest keeps, how to rebuild the exact invocation from it, how
  to tell whether the evidence still matches, and what a record cannot
  give you.

  Sybil gains its `SkipParser` on the docs tree so a page can hold an
  illustrative block that needs a licensed solver or a populated
  workspace, marked and still syntax highlighted. Every block NOT
  marked is executed, so the default stays "checked".
* **The v0.4.0 tabular renames and the keyword-only conversion have
  landed** (PLN-067; SRS NFR-20's accepted consequences). **Breaking**,
  directly, with no aliases and no warning release, exactly as the
  v0.3.0 notes announced them:

  ```python
  to_table(result)                                        # was to_dataframe
  run_table(record, *, loads=None)                        # was run_frame
  sweep_table(workspace, *, loads_file=None)              # was sweep_frame
  parse_run_loads(workspace, record, *, loads_file=None)  # name unchanged
  plan_campaign(campaign, workspace, *, recipes=None, write_plan=True)
  ```

  The word "frame" carried the pandas sense on the public surface while
  this package writes about aerodynamic reference frames in the same
  sentence. The run row's `frame` COLUMN keeps its name, and that is the
  point: once the functions stop using the word, the column means what
  it says.

  `plan_campaign` joins the same window. Its selectors become
  keyword-only, matching `run_campaign` and killing the `write_plan`
  boolean trap: `plan_campaign(campaign, workspace, None, False)` said
  nothing about which False that was.

  No deprecation cycle, per DEP-1: NFR-20's policy takes effect at 1.0,
  so nothing before it owes a warning release.
* **`pyfs-qa` speaks `--fs-version` like every other console command.**
  **Breaking**: `--version` becomes `--fs-version` on `probe` and
  `physics`, and `--versions` becomes `--fs-versions` on `drift`.

  `--version` collides with the convention where it prints the tool's
  own version, and `--versions` differed from its sibling by one letter.
  `pyfs-matrix` already used `--fs-version`, so this is the odd one out
  joining the rest rather than a new convention.
* **The requirement index says how each requirement is verified, and a
  test can now declare which requirement it falsifies** (SRS NFR-13,
  partially delivered and still pending; NFR-25 moves to implemented).
  No runtime change.

  The index published `id`, `text` and `priority`, so a consumer could
  not tell an implemented requirement from a pending one nor find what
  backs either. It now carries `status`, `evidence` and a
  `verification` method, where the distinction that matters is `test`
  (something fails when the requirement stops holding) against `review`
  (a human checks it and nothing fails). The generated
  `reports/requirements-index.json` is the home of record for that
  distribution; the four numbers are deliberately not copied here,
  because a hand-copied count beside a generated artifact is the exact
  drift this bullet is about, and it drifted within this same Unreleased
  block when NFR-18 moved from pending to implemented.

  A `requirement` pytest marker declares that a test falsifies a
  requirement. Every marker must resolve to a live identifier, and the
  covered set is a ratchet. NFR-13 stays **pending** on purpose: 96
  requirements exist and 8 are marked. Marking one on a test that does
  not actually falsify it would be worse than leaving it unmarked,
  because the index would then count a trace that is not one.
* **The package is type checked, and the worked examples run**
  (SRS NFR-27, new; NFR-01d's evidence line corrected). No runtime
  change; `mypy` joins `[dev]` and a `types` job joins CI.

  The four `examples/*.py` were in no CI step. NFR-01d's evidence line
  said they ran under Sybil, and Sybil runs docstring doctests and
  markdown code blocks: the first code a new user runs was the code
  nothing checked. A tier-1 test now runs each one and holds each to
  the extras it declares, so an example that reaches into `[fsi]`
  without saying so fails here rather than in a reader's base install.

  The type check is a **ratchet**, and the measurement is why: the
  first run reported 223 errors in 21 of 53 modules. Those 21 are
  exempted by name, the other 32 are held clean, and a newly dirty
  module fails. The exemption list is the debt, written down.
  `py.typed` is deliberately not shipped: it would tell every
  downstream checker to trust annotations that 223 errors say are not
  trustworthy, and PEP 561 is promised nowhere here, so nothing is
  broken by the absence.
* **Every optional extra refuses the same way, and every dependency
  has a license card** (SRS NFR-02; new public
  `pyflightstream.extras` with `MissingExtraError`, `EXTRAS` and
  `missing_extra`). **Breaking within 0.x** for one narrow clause: the
  `[fsi]` import gate raised a bare `ModuleNotFoundError` and now
  raises `MissingExtraError`, which is an `ImportError` but not a
  `ModuleNotFoundError`.

  Three gated paths raised three different types with three
  hand-written remedy strings, so handling "an extra is missing" meant
  knowing all three, and nothing checked that the remedy printed was
  the remedy that works. There is one type now, and its `remedy` is
  composed from the extra's own name rather than typed, so a message
  cannot name an extra that does not exist.
  `GeometryEngineMissingError` becomes a SUBCLASS rather than
  disappearing: the geometry gate is the one extra whose absence is
  recoverable, so a caller has a reason to single it out.

  The license half: `reports/RPT-016` cards the five runtime
  dependencies and `[plot]`, which had none. The runtime set is the one
  that reaches every user. `xarray` is Apache-2.0, the only non-BSD,
  non-MIT term in it, and the card states why that is accepted rather
  than leaving a reader to re-derive it. Tests now hold the coverage:
  every extra's distributions and every runtime dependency must be
  named in a committed report.
* **The SRS stops being the only judge of its own shape** (SRS
  FR-43, new and deferred; a new `tests/test_srs_consistency.py`). No
  runtime change.

  The document stated its own shape in several places, each maintained
  by hand: the chapter list's identifier range, the acceptance mapping,
  the roadmap backlog. One parser now derives the set and the tests
  assert the prose against it, so a claim about the requirement set can
  no longer be true only on the day it was written.

  It found a seventh drift instance on its first run, past the six the
  review listed: the acceptance mapping recorded an accepted item
  against `FR-43` and no such requirement had ever been written. FR-43
  is added rather than the mapping row removed, because deleting the
  row would hide an acceptance. Its band stays unnamed and the
  requirement is `deferred`: the sister library computes the imbalance
  and returns no acceptance criterion, and setting the number is the
  numerical-analyst seat.
* **A recorded run reconstructs from the manifest alone** (new
  `run.reconstruct()` and `run.Reconstruction`; `RunRecord` gains
  `manifest_schema`, `fs_exe`, `fs_exe_sha256`, `argv`, `cwd`,
  `timeout_s`, `recipe`, `recipe_sha256` and `script_path`;
  `ExecutionResult` gains `argv`, `cwd` and `timeout_s`). Additive.

  NFR-07 promised that the record plus the staged inputs reproduce the
  run. The record held 17 fields and none of them was the command line,
  the working directory, the effective timeout, the executable, or the
  identity of the recipe that built the script, so "reproduce" meant
  re-deriving all of it from executor code that may have changed since.

  `reconstruct()` returns the invocation, the script text, and a
  per-artifact verdict on whether each file still hashes to what the
  record says, with `faithful` as the summary. It refuses a record
  written under a manifest schema it does not know, and one whose
  script is gone, rather than rebuilding something that is not the run.

  `recipe_sha256` is the one that needed a decision: a recipe is user
  code resolved by a dotted name and editable between two runs that
  record the same name, so the name says which function and the hash
  says which version of it. A callable with no retrievable source
  records None, because hashing the repr would make two identical runs
  look different.
* **An unconverged twist iterate is no longer flown.** **Breaking
  within 0.x**: the FSI driver raises the new `TwistIterationError`
  where it used to write the displacements.

  `solve_rotating_static` returns its last iterate whatever happens,
  and above tolerance that iterate is not a solution: the twist was
  still moving when the solve budget ran out. The driver read
  `result.solution` and never `result.twist_residual_rad`, so those
  deflections went into `FSIDisp.txt`, the solver flew a blade shape
  the structural model never settled on, and the only trace was a
  `logger.warning` nobody reads in a batch run. The refusal sits one
  line above the write, because the write is the irreversible act.

  `RotatingSolution` gains `tolerance_rad` and a `converged` property,
  and the convergence log gains `twist_residual_rad` and
  `twist_tolerance_rad` beside the inner-solve count it already
  carried. Phase 1 leaves both cells empty rather than zero: no solve
  ran, and a zero would read as a perfectly converged iteration.
* **CI runs on Windows for the first time, and the coverage floor of
  SRS NFR-16 exists.** No public API change; both are build and
  process.

  NFR-05 has always said Windows is the primary execution target,
  because FlightStream runs on Windows, and CI ran on `ubuntu-latest`
  alone: the platform every user is on was the one platform nothing
  tested. The test job is now two platforms by the two declared Python
  bounds, four legs, with `fail-fast` off so a failure on one leg does
  not hide the others. The docs build and the repository guards moved
  to their own Linux-only jobs, because they test the repository rather
  than the package on a platform.

  NFR-16 has been pending since 2026-07-27 with its floor deliberately
  unnamed until a first measurement. Here it is, whole tier 1 suite:
  6774 statements with 515 missing, 2058 branches with 213 partial, a
  branch-mode total of **90.69%**. The floor is set below that, at 87, in
  `pyproject.toml` where the tool reads it, and it moves as a ratchet
  in a commit that explains it. The margin absorbs the difference
  between the Windows measurement and the Linux enforcement.
* **`RunRecord` records which commit of this package ran**
  (`package_commit`, `package_dirty`), from the new public
  `run.package_vcs_state()`. Additive.

  `package_version` reads the installed distribution's metadata, a
  static string, so every commit between two tags reports the earlier
  tag: measured at 28 commits and 85 files past `v0.3.0` with every
  identity still `0.3.0`. A campaign run from a development tree was
  indistinguishable, in its own manifest, from one run against the
  release. Both fields are None together for a wheel install, and None
  means "not knowable here" rather than "clean".

  The rest of that finding is a versioning-scheme change (a dev version
  carrying the sha, and a guard refusing a final version string off a
  tag). It is release mechanics and is registered, not taken here.
* **Six ways a malformed solver export produced a plausible number are
  refused.** **Breaking within 0.x** for a file with any of them; every
  one used to parse clean and return a number, which is why none was
  noticed.

  * A repeated column in the loads header. Measured: a header naming
    `CL` twice built the row with `CL` winning twice, so the report lost
    `CDi` entirely and published `CDi`'s value under `CL`.
  * A second `Total` row, and a repeated surface name. The later row
    replaced the earlier in silence, so which total the run produced
    was not determined by the file.
  * A fractional value in an iteration field. `int(parse_number(...))`
    truncated, so a printed `312.9` became `312`, and 312 is a
    perfectly ordinary count. The new `results.parse_count` refuses it
    and names the field.
  * An unrecognised token for a printed solver flag. The reading was
    `token.upper().startswith("T")`, so `yes`, `0` and `banana` all
    read as OFF with the same confidence as a real `F`. The tokens are
    now enumerated. A flag read wrongly as off is worse than an
    unreadable one, and `LoadsAssessor` now depends on this exact flag.
  * A residual-history counter that repeats or decreases. `[1, 2, 1574,
    2]` parsed clean, and that shape is two logs concatenated. The
    convergence judgment reads the LAST row, so the run would be judged
    on a residual from an earlier iteration of a different solve.
  * An interior empty cell in an FSI row. Both readers dropped empty
    cells BEFORE counting them, so `1,,2,3` passed the three-field
    check as the triple `(1, 2, 3)` with every value after the hole
    shifted one slot left. The single TRAILING separator the solver
    writes is still accepted, because that is the file format rather
    than a hole, and both cases are tested.
* **A file that was already in the simulation folder is no longer
  collected as a point's evidence.** **Breaking within 0.x**: a point
  whose declared outputs already exist when it starts is refused
  (`FAILED_INCOMPLETE_OUTPUT`) instead of running.

  Every point of a case shares one folder and collection asked only
  whether the declared output existed. Measured with a solver that
  wrote nothing at all: the point was published `CONVERGED`, its record
  named `raw/loads_a+00.0.txt` as its evidence, and that file held
  whatever had been left in the folder. Nothing distinguished the
  record from a real one. The remedy the refusal names is to archive
  the simulation or remove the leftover.
* **`RunRecord` carries a sha256 per collected output**
  (`outputs_sha256`), keyed by the same relative name as `outputs`.
  Additive; empty on manifests written before v0.4.0. Inputs have
  carried a hash since the first manifest and outputs carried a name
  and nothing else, so evidence edited, truncated or replaced after the
  run still matched its record.
* **Archiving a simulation twice refuses instead of replacing the first
  archive.** The archive name derives from the sim id, so the second
  render collides; the zip was opened truncating and the source folder
  deleted afterwards, so both copies of the earlier run were gone and
  nothing was raised. The operation that exists to preserve a run was
  the one that lost it. The refusal names the remedy: move the existing
  archive, or give the workspace an archive template that
  distinguishes the runs.
* **A run that forced all its iterations is no longer called CONVERGED
  for stopping early.** **Breaking within 0.x**: with
  `SOLVER_SET_FORCED_ITERATIONS` enabled, no declared solver log, and
  an iteration counter below the requested budget, `LoadsAssessor` now
  returns `FAILED_INCOMPLETE_OUTPUT` where it returned `CONVERGED`.

  The no-log judgment infers convergence from an early stop, and that
  inference holds only while the convergence threshold is what can stop
  the solver. Forcing all iterations turns the threshold off, so an
  early stop means the opposite. `LoadsReport.forced_iterations` was
  parsed and never consulted, so a run that stopped at 312 of a forced
  500 was published converged, indistinguishable in the manifest from
  one that genuinely met the threshold at 312.

  Narrow on purpose, and the three unchanged cases are tested as
  controls: an unforced early stop is still `CONVERGED`, a forced run
  that reaches its budget is still `COMPLETED_MAX_ITER`, and a footer
  that does not print the line at all still gets the count judgment,
  because not knowing is not the same as knowing it was forced.

  The status is a constrained choice rather than the right name for it,
  and the assessor's docstring says so: the terminal set is closed at
  six (SRS FR-46) and whether it opens to a seventh is the product
  owner's undecided question (FR-37).
* **"Supported" was one word covering four states, and is now four
  named values** (SRS FR-49, new). New public names at the top of the
  package: `SupportLevel`, `support_table()`, `version_support()`,
  `support_level()`, plus the `pyflightstream.support` module with
  `minimal_workflow()`. Purely additive.

  ```python
  >>> import pyflightstream
  >>> pyflightstream.support_level("26.000")
  <SupportLevel.REGISTERED: 'registered'>
  ```

  Registering a version made every public surface call it supported.
  26.000 is registered, is accepted by `Script(version="26.000")` and
  by a campaign, and carries evidence for zero of the database's
  commands, so nothing whatever can be built for it. The README said so
  in a sentence; nothing said it in a value a caller could read.

  The levels ascend `registered`, `documented`, `verified`,
  `operational`, and every one is derived from the command database
  rather than declared in a file, for the same reason a command status
  is: a hand-set level outlives the fact behind it. Today that reads
  26.000 registered, 26.100 documented, 26.120 and 26.121 operational.

  `operational` is the level that claims a user can get from geometry
  to a loads file, and its claim is checked by performing it:
  `minimal_workflow(version)` builds the shortest complete script, and
  a tier 1 test builds it for every version reported operational. The
  README's version table is pinned to the derived values by a test, so
  the published claim and the computed fact cannot drift.
* **A command a probe measured broken is refused at emission, and the
  way through is recorded** (SRS FR-48, new). **Breaking within 0.x**:
  a recipe that emitted `AIR_ALTITUDE`, `NEW_OFF_BODY_STREAMLINE`,
  `SET_MOTION_START_TIME` or `SWEEPER_REF_VELOCITY_SAME` against a
  version whose record is `broken` now raises `BrokenCommandError`
  where it used to build a script.

  `broken` is the one status backed by a probe that WATCHED the command
  fail, and it was the one status the emitter did not act on. The
  consequence is not a crash. An absent command produces no run at all;
  a broken one produces a complete run with wrong numbers in it. On
  26.120 the solver reads AIR_ALTITUDE's METERS argument as feet
  (`reports/compat/CMP-26120_2026-07-23_pln012.yaml`), so
  `atmosphere(script, altitude=1000.0)` would have asked for 1000 in
  whatever unit the solver defaulted to, and written a manifest
  calling the script fully validated. The measurement is at one
  altitude only: at 5000 the default read as feet.

  ```python
  script.allow_broken("AIR_ALTITUDE", reason="reproducing a 2026-07 run")
  helpers.atmosphere(script, altitude=1000.0)
  ```

  The waiver emits the command and records it: `script.broken_commands`
  and the new `broken_commands` field of `RunRecord` carry the command,
  the version, the committed report, the recorded observation and the
  justification. The same promise `raw_flag` makes for unvalidated
  text, for a case that is worse, because a raw line at least looks
  unusual. `reason` is required; it is the only field nothing
  automated can supply.

  Registered on the script rather than passed per call, so it reaches
  the curated helpers without every helper growing an argument, and a
  waiver for a command that is not broken in the target version is
  accepted and records nothing: AIR_ALTITUDE is broken in 26.120 and
  verified in 26.121, and one recipe is meant to run against both.

  Two of this repository's own goldens were pinning the mistake and
  were corrected in the same change, which is the part worth reading
  before dismissing this as defensive: the actuator polar golden pinned
  `altitude=1000.0` on 26.120, and the rotor unsteady golden pinned
  `SET_MOTION_START_TIME`, at which the solver ABORTS script
  processing, so everything after it never ran. The altitude rendering
  is still pinned, on 26.121, where the command is recorded verified.
  Not "where the hotfix fixed it": RPT-014 refuses that attribution in
  its own words, because three variables separate the two runs (the
  build, the harness and the session file) and the disambiguating
  probe has not been made.
* **A truncated evidence note now says that it is truncated.** The
  `note` a compat promotion writes into the command database is capped
  at one line, and the cap used to cut mid-word with nothing to show
  for it: AIR_ALTITUDE's read "reports the 5000 m standa", losing the
  measured diagnosis that followed. The cut is now made at a word
  boundary and marked `[...]`, because that note is what the new
  `BrokenCommandError` shows the caller, and a refusal that looks like
  a corrupt database is a refusal that gets worked around.

* **Research geometry can no longer enter the repository unnoticed**
  (SRS NFR-14, which was pending). A tier-1 guard walks every tracked
  path and fails on any geometry or mesh extension outside a small
  allowlist of provably synthetic fixtures, and a `forbid-geometry`
  pre-commit hook refuses the same class at commit time.

  This closes the one breach this project calls irreversible: a push
  publishes, and deleting the file afterwards does not unpublish it from
  any clone that already fetched. It was enforced by discipline alone
  until now, and discipline was measured to be all there was: a 37 kB
  mesh added under `examples/` and staged passed the entire tier-1 suite
  and the CI guard job, which looks only for pdf, notebook and
  `_private/` paths.

  The suffix set is derived rather than invented: `IMPORT`'s
  `file_type` enum in the command database, plus the saved simulation
  `.fsm`, plus the CAD interchange formats research geometry arrives in.
  Stated as a residual rather than hidden: the guard keys on extension,
  so geometry carried in a generic container (a node list in a `.csv`)
  is outside it, and NFR-08 stays a discipline for that.
* **`PyflightstreamError` is the package base exception, and every
  exception the package raises now descends from it** (SRS FR-39, which
  was pending on exactly this clause). One except clause catches the
  package:

  ```python
  from pyflightstream.exceptions import PyflightstreamError
  ```

  Purely additive, and deliberately so: every type keeps the
  standard-library base it already had as a second base, so
  `UnknownVersionError` is still a `ValueError`, `WorkspaceError` still
  a `RuntimeError`, `OptionError` still a `KeyError`. No `except` clause
  that worked before stops working, and a table in
  `tests/test_exceptions_catalog.py` pins each of those builtin bases so
  a later edit cannot quietly move one.

  The base parents the exceptions and not `VersionMismatchWarning`,
  which is a warning: it stays in the catalog, because the catalog
  covers exceptions and warnings alike, and it stays out of the
  hierarchy, because calling it an `Error` would mislead whoever reads
  the traceback. Two separate guards now run: one fails when a class
  does not join the catalog, one fails when it joins the catalog
  without joining the hierarchy.

  Why it lands before any renaming: a name is the dispatch key only
  while there is no base to catch. With the base in place, renaming a
  leaf stops costing a deprecation cycle, so the naming questions the
  API vocabulary review raised get answered later and more cheaply.
  The cause-versus-rule split in the current names is therefore left
  open on purpose, not overlooked.
* House conventions gain two entries, in the same `CONVENTIONS` home
  that feeds `help()` and the docs site: **diagnostics are nouns and
  validators say `check_`** (`sample_coverage` beside `check_recipe`),
  and **a validator takes the values it compares where the object would
  reverse the dependency direction**. The second is a layering rule
  wearing a naming hat: `check_state_matches_config` takes two integer
  counts rather than the config object, so `fsi.state` keeps its import
  surface to pydantic, and those counts are keyword-only because
  same-typed scalars transpose silently. Both halves that can be checked
  mechanically now are: a `check_` function returning a value fails the
  suite, and so does `fsi.state` importing `fsi.config`.
* **FlightStream 26.121 is registered, and the vendor name "26.12" stops
  resolving.** The vendor ships the hotfix build under the same release
  name as 26.120, so that name now identifies two registered builds.
  `versions.resolve` refuses it with the new
  `AmbiguousVersionAliasError` (catalogued, carrying `alias` and
  `candidates`) naming both candidates, instead of returning one of
  them. Every caller that passed the vendor name must pass a canonical
  identifier: `Script(version="26.120")`, `--fs-version 26.120`,
  `fs_version = "26.120"`.

  Incompatible by intent, and the alternative was worse: `resolve`
  matched canonical-or-alias and returned the first hit in release
  order, so once 26.121 was registered the vendor name would have
  handed back the pre-hotfix solver silently. A caller who wrote the
  vendor name meaning "the current 26.12" would have got the build
  before the hotfix, with no error anywhere. The refusal is loud; the
  old behaviour was not.

  Resolution also matches canonical identifiers across the whole
  registry before considering any alias, so an entry can no longer be
  shadowed by an earlier one carrying its canonical as an alias.
  Registered versions are now 26.000, 26.100, 26.120, 26.121; the last
  digit indexes vendor hotfix builds, so 26.121 is hotfix build 1 of
  the 26.12 release (SRS FR-02c, new).
* **A campaign pointed at the wrong FlightStream installation now stops
  before its first point**, not after its last. `run.check_solver_identity`
  is new and public: it runs the cheapest possible script (a sentinel, a
  log export, and close), reads the build number out of the exported
  log, and refuses when it is not the build the campaign's version
  declares. `run_campaign` calls it once, lazily, just before the first
  point that will really execute, so a resume with nothing pending still
  spends no solver process, and takes `preflight=False` to skip it.

  Layered rather than sole. A mismatch is refused there on positive
  evidence; an identity the check cannot read warns and falls through to
  the parse-time comparison below, because refusing on an unreadable log
  would make the guard's own failure mode "no campaign runs at all".
  Nothing is checked, and no solver process spent, for a version with no
  registered build.
* **A run can now tell which solver build actually produced it.** The
  registry records each version's vendor build number (`FsVersion.build`,
  new, read from `commands/_meta.yaml`), and parsing a loads or probe
  export compares it against the build the output printed, warning when
  they differ.

  This is the run-time half of the alias refusal above, and without it
  that refusal was only half a guard: it settled which build the run
  ASKED for and could not show which one ran. The version string cannot
  show it either, because 26.120 and 26.121 both print "26.1" and they
  carry different records, `AIR_ALTITUDE` being the measured case. So a user
  who took the refusal seriously, moved to 26.121 and left `fs_exe`
  pointing at the 26.120 install got no warning at all, on exactly the
  command whose units defect that build carries.

  Build numbers are evidence, not configuration: each is taken from a
  committed report's `solver_identity` for its own version, and a
  tier-1 guard fails if a registered build appears in no such report.
  26.000 has none registered, because no committed report records one;
  there the version-string check remains, unchanged.
* `pyfs-qa probe`, `physics` and `drift` now refuse an unresolvable
  `--fs-version` (`--fs-versions` on `drift`) with the library's own message on stderr and exit code 2,
  instead of a traceback. Both refusals it covers are ordinary user
  error: an unregistered identifier, and a vendor name shared by several
  builds. A wrapper keying on the exit code sees 2 where it used to see
  1.
* **The 26.121 manual edition is registered as SRC-740**, a separate
  source rather than a re-issue of SRC-003, and the edition entry says
  why: its scripting reference is shifted by three pages throughout, so
  an SRC-003 page number does not address the same page in it.

  Two of the commands it documents join the database with a 26.121
  status only, so a 26.120 script still refuses them:
  `DELETE_SURFACES` (p.315) and `NEW_UNSTEADY_SOLVER_SURFACE_PROBE`
  (p.350), the latter being where the six boundary-layer parameters
  enter the unsteady vocabulary. `UNSTEADY_SOLVER_NEW_FLUID_PLOT` gains
  a 26.121 grammar override for the same six values SRC-740 adds to its
  `PARAMETER` enum.

  `DELETE_SURFACES` is registered narrow, with the single index its
  parameter table declares, because one of its samples passes three
  bare integers under a multiple-surface heading and the two readings
  delete different surfaces.

  The other four are **not** landed, and the reason is worth stating:
  they belong to the settings families, where a command is not
  registered by a database entry alone. A tier-1 guard requires every
  such command to carry a snapshot flag and a keyword on the public
  `solver_settings()` helper, because a solver setting the snapshot
  does not know is a run whose manifest describes the solver state
  incompletely. They are backed out rather than shipped half-wired.
* `UNSTEADY_SOLVER_DELETE_ALL_PLOTS` joins the command database
  (`documented`, SRC-003 p.347). It was documented in the 26.12 manual
  and never registered; the gap surfaced while diffing the 26.121
  manual against the database.
* Solver toggles read the solver's own vocabulary as well as Python
  booleans: `ENABLE` and `DISABLE` (any case) are accepted by every
  helper argument and every `cases.SolverSettings` field that switches a
  flag, resolved before the helper emits anything, and stored and
  snapshotted as bools. New public module
  `pyflightstream.script.toggles` (`resolve_toggle`,
  `SOLVER_TOGGLE_WORDS`, the `Toggle` annotation), used by both the
  helpers and the case models so the vocabulary has one home, plus
  `cases.SolverToggle`, the annotated field type any settings model can
  reuse.
* `LoadsAssessor()` now takes no argument by default and reads the
  case's first declared output as the loop rendered it for that point,
  which is what a swept case needs; naming the file explicitly still
  works.
* Incompatible changes: a toggle value in neither vocabulary is refused
  where a truthy string used to pass silently (a helper call passing
  `'yes'`, and a settings file or preset whose flag reads `"true"`,
  `"on"`, `"1"` or `0`, which pydantic's lax bool parsing used to
  accept); a multi-point case whose declared output names lack the
  `{point}` placeholder is refused, because those points would
  overwrite each other's evidence; and a recipe reference whose
  callable does not take `(case, script)` is refused at resolution
  instead of raising a bare `TypeError` once per point.
* `solver_settings(vorticity_drag_boundaries=...)` is optional again
  (a relaxation, so no caller breaks). Omitted on a script that has not
  selected yet, it emits no selection command and the snapshot records
  the flag as `default` with an empty selection and its citation, or as
  `unknown` on a FlightStream version where the command has no recorded
  evidence; omitted on a second settings call of the same script, the
  selection of the earlier call stands, in the script and in the
  snapshot. An empty sequence is refused.

### Removed

* **`pyflightstream.files` and `pyflightstream.cases.matrix_legacy` are
  gone**, on the horizon their own deprecation-ledger entries recorded:
  `removal_version="0.4.0"`, set when they were introduced in v0.3.0.
  Import `pyflightstream.workspace` and `pyflightstream.cases.matrix`
  instead; `LegacyMatrixError` was already `MatrixError` and `LegacyRow`
  already `MatrixRow` through the shim, so only the module path moves.

  Kept rather than extended because NFR-20 says a promise already
  recorded is kept regardless of version, and because the deadline guard
  would otherwise have turned the suite red at the release commit's
  version bump, which is the worst moment to discover a removal window.
  The deprecation ledger is now empty and the machinery stays: the
  policy binds from 1.0 and the next shim registers there.

### Added

* **A tracked file may no longer name the workspace container's
  absolute path.** CLAUDE.md has always said machine configuration is
  never a literal path in a committed file; a tier-1 guard now holds
  it, alongside the email-address and user-profile-path checks that
  landed on 2026-07-28.

  Not an absolute-path shape, which was measured to be the wrong guard:
  32 tracked files match one and 30 of them are illustrative solver
  paths in examples, goldens and fixtures (`C:/cases/wing.fsm`). The
  guard keys on the container directory's name, which is what separates
  a path that teaches from a path that leaks, and is the same on any
  clone. The two files that carry it today are hash-pinned vendored kit
  bodies this repository cannot edit, so they are allowlisted by name
  with their kit rows, the allowlist itself is checked for stale
  entries, and the fix is routed to the level that owns those bodies.
* **FlightStream 26.121 is onboarded with solver evidence, not just
  registration**: `reports/compat/CMP-26121_2026-08-02_full.yaml` is a
  licensed tier-2 run of 109 probe specifications against solver build
  #7262026, and 68 statuses are promoted from it.

  One command changed for the better: `AIR_ALTITUDE` was `broken` on
  26.120 because its `METERS` argument read as ignored (5000 m gave the
  5000 *foot* standard density, 1.056 kg/m^3, observed twice on the
  pre-hotfix build); on 26.121 the same assertion observes
  0.736 kg/m^3, the 5000 m value. Anyone setting altitude in metres on
  26.120 was solving at the wrong density, silently, and that half
  stands on the 26.120 evidence alone.

  One changed the other way: `SWEEPER_REF_VELOCITY_SAME` ran without a
  script abort on 26.120 and aborts on 26.121.
  `NEW_OFF_BODY_STREAMLINE` and `SET_MOTION_START_TIME` are broken on
  both builds.

  Attribution is deliberately withheld, because three things differ
  between the two runs and not one: the solver build, the probe harness
  (0.0.1.dev0 to 0.3.0, with the specifications changing inside that
  window), and the session file. The run establishes what was observed
  on each build, not what the vendor changed. The disambiguating run,
  this harness against the 26.120 executable, was not made.
* `reports/RPT-015_bulk-separation-family-acceptance_2026-08-02.md`:
  the bulk-separation family probed on both builds, because RPT-014's
  rename checklist held one item that was a physics question rather than
  a naming one. It turned out to rest on a false premise and is
  withdrawn rather than answered.
  `CREATE_STRATFORD_BULK_SEPARATION` is **not new in 26.121**: the
  26.120 solver accepts it too, where no manual documents it, so the new
  edition documented an existing command rather than introducing one.
  And `CREATE_BULK_SEPARATION`, which the database records as
  `documented` for 26.120, is **refused by the 26.120 solver in every
  documented form**, including the three-argument one RPT-012 ran
  successfully on 26.100. No status moves on this report: it came from
  an ad-hoc probe rather than the harness, so `apply-compat` cannot read
  it, and a status promoted outside that path is what invariant 3
  forbids. Registered instead.
* `reports/RPT-014_26121-manual-diff-and-probe_2026-08-02.md`: the
  26.121 onboarding record. It documents that the hotfix carries its own
  manual edition (413 pages against 410, every scripting-reference
  citation shifted by +3) while the vendor release-notes PDF is
  byte-identical between the two installs and documents none of it; the
  six commands the new edition adds and the three it drops; two
  signature changes on commands already in the database; four defects in
  the vendor's own document; and the human decision checklist for three
  suspected renames, one of which (`FLAT_PLATE` bulk separation to
  Stratford) is a physics question and not a naming one.
* User guide section on migrating a loose script builder to the
  `ScriptRecipe` protocol: the before and after of
  `build(workdir) -> Script` becoming `build(case, script) -> None`,
  with the five moves it takes (do not create the Script, open
  `case.geometry` so the run identity is the staged file, read the
  point from the case, export the rendered `case.outputs` names, and
  give the function an importable address). This is the path of
  everyone arriving from a driver script, and it was documented
  nowhere (feedback channel item 4, PLN-074).
* House conventions gain "Toggles read both vocabularies", rendered in
  `help()` and on the docs site from the same `CONVENTIONS` home.
* House conventions page on the docs site
  (`reference.conventions_markdown`, the same source as the offline
  `help()` conventions section), wired into the generator and nav.
* Automated PyPI release through trusted publishing (OIDC):
  `.github/workflows/release.yml` builds, checks the tag against the
  `pyproject.toml` version, and publishes from the GitHub `pypi`
  environment on a `v*` tag, so no API token is stored in the
  repository (mirrors the ITACA release workflow). Development process:
  a mandatory role-review push/release gate now blocks a `git push`
  until the specialist reviewer agents have run and attested every
  commit the push would make new, plus the ref being pushed, and denies
  any push while the incident ledger shared with ITACA has an open
  blocking incident for this repository; a new `incident-analyst`
  charter owns the structural-cause analysis, and `tests/test_push_gate.py`
  pins the gate's decisions (`.claude/` hooks, agents and skills;
  internal tooling, not a package surface).
* Development process: the session documents (state file, handoffs,
  logbook, inbox, progress reports) moved out of the repository-local
  private tree into the coordination hub, where they gain version
  control, and are located by a new `PYFS_SESSION_ROOT` environment
  variable read by the `handoff`, `plan`, `audit` and
  `derive-requirements` skills. Unlike the two existing
  machine-configuration variables it is documented as stop-on-unset
  rather than skip-on-unset, because a session that cannot find its
  state file would otherwise close by writing its record nowhere. The
  plan ledger and the design documents deliberately did NOT move: a
  repository's own plan and architecture are its own facts. Two new
  tier-1 guards came with it, `tests/test_env_contract.py` (the
  documented variables and their consumers agree, and no skill prints
  the bash-form variable as a path, which in PowerShell expands to
  nothing silently) and a house-style check that no committed file
  re-hardcodes a migrated session path; `tests/test_plan_checker.py`
  now also pins the plan checker's exit taxonomy, seven tests over the
  six documented outcomes plus the usage branch that shares an exit code
  with one of them, including two weaknesses recorded rather than hidden
  (an empty ledger directory exits zero, and a DELETED exemption list
  stays silent while every legacy id fails at once) (`.claude/` skills
  and `CLAUDE.md`; internal tooling, not a package surface).
* Documentation and process: the shared process kit is re-vendored from
  0.2.2 to 0.2.3 for the plan checker and its mutation companion, a
  promotion this repository's own adoption review produced and then ran
  three days behind. The hardening it brings is that a `legacy_ids.txt`
  which exists but cannot be read is now a named `CONFIG ERROR` at exit
  2 before validation, instead of being swallowed into an empty
  exemption set and reported as 88 ledger defects pointing at the one
  fix the plan rules forbid. Also recorded, because the drift test's
  green is easy to over-read: that test detects a hand-edit and cannot
  detect falling behind, which is why the lag was invisible. The drift
  test also gained pins on the two provenance-header fields that sit
  outside the body hash and that no assertion previously reached: the
  `note:` target of each vendored copy, and the `canonical-source:`
  line, which is where a copy records that its body was built for the
  kit rather than adapted from the AGPL predecessor (`.claude/tools/`,
  `tests/test_kit_drift.py`; internal tooling, not a package surface).
* Documentation and process: the push gate is re-vendored from the kit at
  0.2.16, alone, to close a FAIL-OPEN it carried at 0.2.4
  (`INC-20260802-1450-shared`). `_strip_heredocs` removes heredoc bodies
  before tokenizing so a commit message that merely describes a push is
  not misread as one; its opener pattern matched anywhere in a line,
  including inside a quoted commit message, and when no matching
  delimiter ever arrived it dropped every remaining line. A real push on
  the next line went with them, and the gate returned without requiring
  an attestation, reading the ledger, or checking for a release tag. Not
  a weaker refusal: no refusal, reachable in two lines of ordinary shell
  with no heredoc anywhere in them. Measured here against the deployed
  0.2.4 body before it was replaced: three reduced reproductions each
  produced no decision at all while a bare unattested push denied; on the
  0.2.16 body all four deny, and neither pinned heredoc behaviour moved.
  The cases are now permanent in `tests/test_push_gate.py` and were
  proven by mutation, failing on the 0.2.4 body restored from git.
  TWO THINGS RIDE THIS VENDOR that are not the heredoc fix, both from kit
  0.2.8, and both change behaviour. The incident-ledger variable the gate
  reads is renamed from `PYFS_INCIDENT_LEDGER` to
  `COORD_INCIDENT_LEDGER`, retiring the last per-repo difference between
  a vendored body and its master; `PYFS_INCIDENT_LEDGER` stays live for
  the `incident-analyst` agent, whose charter is a hash-pinned body on a
  kit row NOT taken here, so a clone now sets both to the same directory.
  And an unset variable now DENIES a push where it used to mean the check
  did not apply, which sounds like a courtesy to a fork and was measured
  to be something else: the level that writes the incidents pushed past a
  blocking incident of its own authorship, on a variable name that had
  never existed. Order matters on a fresh clone and is the reverse of the
  obvious one: export the variable BEFORE this body is in place, since a
  PreToolUse hook without its configuration denies every command. The
  rest of the kit is deliberately NOT adopted; see below (`.claude/`,
  `CLAUDE.md`, `tests/`; internal tooling, not a package surface).
* Measured and NOT adopted, recorded so the gap is a decision rather than
  a discovery: against kit master 0.2.17 on 2026-08-02, six of the nine
  kit artifacts this repository vendors are behind their masters and the
  kit manifest carries 25 further rows never vendored here, an adoption
  surface of 31 artifacts. Only the push gate was taken, because it alone
  was blocking. The earlier estimate of "17 findings across 8 files" was
  measured against kit 0.2.7 in July and is superseded by this one
  (`tests/test_kit_drift.py` records the same numbers next to the pins;
  internal tooling, not a package surface).
* Documentation and process: the shared process kit is re-vendored to
  0.2.4 for the push gate, the incident-analyst charter and the private
  snapshot tool, a promotion whose reason is privacy rather than
  behaviour. `.claude/tools/snap.sh` is tracked and this remote is
  public, and its hashed body set the snapshot repositories' git
  identity from a personal name and a personal email address and located
  the shared ledger at an absolute path under a personal user profile.
  The 0.2.4 body reads the ambient git configuration with a neutral
  fallback and locates the shared tree through a new
  `COORD_SHARED_LEDGER_TREE`; three occurrences of a personal first name
  in the gate's deny messages and one in the analyst charter now read
  "the author", as do one line each in the `handoff` and `plan` skills.
  No allow or deny decision changed, which was verified per replacement
  rather than assumed: each sits inside a deny message string, none in a
  condition, a return value, a constant set or a comparison. Removing
  the identifiers from HEAD stops them spreading and does not unpublish
  them; they remain in this repository's published history, and the
  address is in the author metadata of every commit already on the
  remote. Two things arrived with the promotion and are recorded rather
  than smoothed. The new variable is documented in `CLAUDE.md`, which is
  the only place it CAN be documented because the body that introduced
  it is hash-pinned. And the 0.2.4 body's claim that an unset variable
  skips the shared tree is false once the snapshot repository exists,
  where it instead reports a snapshot it did not take; that is a kit
  defect, registered against the coordination level that owns the
  master, with the interim mitigation in `CLAUDE.md`
  (`.claude/`, `CLAUDE.md`, `README.md`, `tests/`; internal tooling, not
  a package surface).
* The rule that machine-specific values never appear in a committed file
  stops being prose. A tier-1 guard now fails on an email address or a
  user-profile path in any TRACKED file, scanning `git ls-files` rather
  than Markdown and Python only, which is how the file that leaked sat
  outside every house-style guard by file type. The author's name is
  deliberately NOT guarded: it is published on purpose in `LICENSE`,
  `CITATION.cff`, `pyproject.toml`, the SRS and the guide, and guarding
  a string that is meant to be published would need an allow-list long
  enough to be its own defect. The guard carries its own falsification,
  asserting that it fires on both shapes and stays quiet on the
  impersonal forms the tree legitimately holds (a reserved
  documentation domain, a loopback address, a forge no-reply sender, and
  an action version pin, which is the mail shape without a dotted
  top-level domain). Separately, `tests/test_env_contract.py` now reads
  the vendored shell tools and the `COORD_` prefix, closing the two
  independent reasons a new machine variable stayed invisible to the
  guard built for exactly that (`tests/test_house_style.py`,
  `tests/test_env_contract.py`; internal tooling, not a package
  surface).
* SRS 1.2.0 to 1.3.0: the author's Phase 4 acceptance batch, landed in full.
  NFR-19 (result column-schema stability), NFR-20 (deprecation policy),
  NFR-22 (dependency version envelope, with the pre-1.0 pin form and
  the Python-ceiling propagation), NFR-23 (layering guard) and NFR-24
  (software jargon glossed) are added; two of them were sharpened by
  seat answers the same day, so NFR-20 now states as the author's own
  decision that within 0.x a break lands only in a MINOR release and a
  patch never changes the public surface, which is what lets a user
  write a version specifier against a 0.x package, and NFR-19 states
  that its column schema lives in the `results/tables.py` docstrings and
  that no rendered API reference is planned. AD-05, AD-06 and AD-07 are
  restated; the glossary gains the software terms NFR-24 requires.

    Phase 5 consolidation, same day: the batch is now written in full
    rather than in part. Twenty-six identifiers are added, covering the
    far-field ledgers (FR-38), the public exception hierarchy (FR-39),
    the options registry (FR-40), the ITACA adapter (FR-41), the
    reference-frame and sign conventions (FR-42), the console
    entry-point contract (FR-44), the strict manifest record (FR-45),
    the closed terminal-status set (FR-46), the probe-data export
    writers (FR-47), the public test-support assertions (FR-48),
    traceability closure (NFR-13), a confidentiality commit guard
    (NFR-14), manifest hash canonicalization (NFR-15), a coverage floor
    (NFR-16), one float-comparison convention (NFR-17), a manifest
    schema version (NFR-18), the support window (NFR-21), the
    optional-dependency error shape (NFR-25), and one term per level for
    the unit of work (NFR-26), plus the accepted splits of FR-02, FR-22,
    FR-30, FR-31, FR-33 and NFR-01 into singular claims that a single
    test can falsify. Ten requirements are reworded to say something
    checkable: FR-06 drops "no hidden logic" for a property of the
    emitted script, FR-08 names the attestation that verifies it rather
    than implying a test that cannot exist, FR-10 scopes "forever" to
    the external format and stops an unknown column being dropped
    silently, FR-11 replaces "lossless" with a reverse conversion, FR-20
    loses its status narration, FR-26 states its metric and that its
    bands are measured, FR-31 adds the per-version completeness
    confirmation, NFR-07 scopes reproducibility to the inputs and names
    the solver determinism boundary it does not control, and NFR-08
    defines "aggregated" as a line rather than a judgment.

    Two of her acceptances contradict each other and the SRS says so
    rather than silently picking one: FR-46 closes the terminal-status
    set at six values and FR-37 asks for a status the set does not
    contain. Which one moves is the product owner's call.

    The
  user-facing consequences are in Deprecated below.

* The requirement set is published as a machine-readable index at
  `reports/requirements-index.json`, generated from `docs/srs` by
  `scripts/gen_requirements_index.py` and checked against it by a Tier 1
  test, carrying each requirement's id, statement and mandatory or
  deferred priority plus the two traceability counts (how many
  requirement ids any test cites, over the total). It exists because the
  external dashboard that consumes those numbers was maintaining them by
  hand and had fallen behind the SRS. New public page: the
  [acceptance mapping](https://nevesgeovana.github.io/pyflightstream/requirement-mapping/),
  which records which accepted item became which identifier, including
  the twenty-four that arrived without an identifier of their own.

### Deprecated

Keep a Changelog's sense of the word, soon-to-be removed, and NOT the
runtime-warning sense: nothing below emits a warning, because the
policy that would require one takes effect at 1.0 (SRS NFR-20). This
section is the notice, and for the removals it is the only one there
will be.

* **pandas and xarray leave the runtime dependencies at v0.5.0, and
  ITACA becomes a core dependency in their place** (SRS AD-06 and
  AD-07, the author's decision of 2026-07-27). Nothing changes in this
  release: both are still declared, still imported, and everything
  works exactly as it does today.

    What actually breaks at v0.5.0, stated in full rather than by its
    most visible case. The tabular layer (`results.tables`) stops
    returning pandas DataFrames. AND the far-field and plot-writer
    surface goes with it: `farfield` takes and returns
    `xarray.Dataset`/`DataArray` in the signatures of some fifteen
    public functions (`lattice_dataset`, `mass_closure`, `shaft_torque`,
    `azimuthal_harmonics` and the rest of the ledgers), and
    `post.writers` consumes those structures. A rotor or far-field user
    is affected as much as a table user.

    What survives: the column NAMES and their units are unchanged (SRS
    NFR-19); the container type is what changes. What to do if that is
    not your schedule: pin `pyflightstream<0.5` and stay on the
    pandas/xarray surface.

* **The tabular layer rename has LANDED**, so the forward notice that
  stood here is now a record rather than a warning. What it announced
  is in this release's API surface delta above; the notice as it was
  written stands unaltered in the v0.3.0 notes, which is where a reader
  looking for the warning they were given will find it.
* **Erratum to the 0.3.0 notes**, which said the ITACA data adapter
  "is declared as a pyflightstream `[itaca]` extra". It was not: no
  such extra was ever added to `pyproject.toml`, and none will be.
  ITACA arrives as a core, non-optional dependency instead (AD-07).
  A released entry is never rewritten, so that one carries a
  supersession note in place and the correction itself lives here,
  which is what this file already does for three 0.3.0 entries.

### Fixed

* **`pyfs-qa apply-compat` could not promote the first probe run of a
  newly registered FlightStream version**, which is the one run a
  version onboarding exists to produce. It rewrote an existing
  single-line version entry and refused when the command had none, but
  a version starts life recorded only in `commands/_meta.yaml`, so on
  its first run every judged command has no line to rewrite. The whole
  run was unpromotable, and the only route left was a hand edit, which
  invariant 3 forbids. It now inserts the entry at the version's release
  position among the lines already there. A command whose version block
  holds no single-line entry to pattern on is still refused loudly.
* **Two commands were emitted with no count-versus-list check at all,
  which the solver turns into a corrupted script rather than an error.**
  A command that declares how many indices follow makes the solver read
  that many tokens; a count disagreeing with its list therefore makes it
  consume the next command line as data. The check keyed on the
  argument's NAME against a hand-kept set, because the vendor spells the
  count differently per command, so `UNSTEADY_SOLVER_NEW_FORCE_PLOT`
  (count spelled `boundaries`) and `ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS`
  (spelled `num_index`) escaped it entirely: `boundaries=3` with two
  indices rendered without complaint.

  Both names join the set, and the class is closed rather than the two
  instances: a tier-1 guard now walks the whole database and fails on
  any integer argument that introduces a list from outside the known
  set, so the next new spelling fails the suite instead of shipping
  unchecked. Found while diffing the 26.121 manual; the second instance
  was found by the guard, not by reading.
* **The eight blocker findings of the independent review are fixed, and
  every release up to and including v0.3.0 carries all of them.** They
  are one class in eight places, which is why they are listed together:
  a step that reduced, rendered or resumed its input before validating
  it, and so produced a plausible result from data that could not
  support one. **None of them raised, warned, set a flag or returned a
  non-zero status**, so a user of 0.3.0 cannot tell the failing case
  from the correct one from the library's own output. Each fix is at
  the structural cause and carries a guard proven by mutation against
  the pre-fix body.

  * *Command injection through any string or path argument.* A newline
    inside an emitted argument became a line boundary, so the text
    after it became the next command while `raw_flag` stayed False, the
    flag whose only job is to record that a script holds something
    unvalidated. `comment()` had the same hole. Text arguments now
    refuse a line terminator (new `ScriptLineBreakError`, subclassing
    `CommandArgumentError`), `comment()` prefixes every physical line,
    and `emit()` re-checks the rendered block so a future argument type
    cannot reopen it. `Script.raw()` remains the sanctioned route for
    unvalidated text, and still sets the flag.
  * *A NaN residual published as CONVERGED.* `max(velocity, pressure)`
    was tested for NaN after the fact, but every comparison against NaN
    is False, so `max` returned the other column: a NaN pressure
    residual was swallowed and the point converged on a residual that
    is not the one that decided it. An infinite residual reported
    `COMPLETED_MAX_ITER`, a status asserting the solver merely ran out
    of iterations. Both are now `FAILED_DIVERGED`.
  * *Missing far-field samples became a physical reduction.*
    `plane_integral` inherited xarray's `skipna=True`, so an absent
    sample left the sum while its ring weight stayed in the geometry,
    shrinking flux, force, torque and energy in exact proportion to how
    much data was missing. It now propagates NaN, and the new
    `farfield.sample_coverage` reports the finite fraction so the
    result is diagnosable rather than merely opaque.
  * *A cross-check that could not fail.* The harmonic transverse-flux
    path summed azimuthal orders up to `n/2 - 1`, omitting Nyquist, so
    on the one signal class where the two documented-independent paths
    disagree the check returned zero. It now sums the true half-band
    with Nyquist counted once.
  * *`resume` corrupted the manifest it protects.* Inputs were staged
    before the already-recorded test, so a resume with nothing to do
    called the solver zero times and still replaced the staged input
    while the manifest kept the old hash. Pending points are now
    decided before anything is prepared, and a partial resume whose
    input changed is refused.
  * *Declared outputs could leave the run, and collisions destroyed
    data.* An output name such as `../outside.txt` skipped validation
    entirely and was then collected with a MOVE, taking a file the run
    did not own. Two outputs, or two staged inputs, sharing a base name
    silently overwrote each other while the manifest recorded both.
    Names are now contained, and every collision is refused before
    anything moves.
  * *Two sweep points could share one `run_id`.* Point tags format at
    one decimal, so alpha 1.01 and 1.04 collide; nothing refused it and
    the duplicate surfaced only when the second point tried to record,
    leaving a half-executed campaign. Ambiguous sweeps and duplicate
    `sim_id`s are refused at load. The tag format is deliberately
    unchanged: it is run identity and appears in every existing
    manifest.
  * *An all-NaN blade passed every structural check.* Each validator is
    a comparison, and NaN fails them all, so it satisfied
    increasing-radii, positive-chord, positive-stiffness and
    nonnegative-inertia at once. Non-finite values are now refused
    first. Separately, a resumed FSI `state.json` was validated for
    types but never for shape, so a run resumed on memory from a
    differently shaped blade; new `fsi.state.check_state_matches_config`
    refuses it.

  Incompatible by intent: input that used to be accepted and produce a
  wrong answer is now refused. If a campaign, blade configuration or
  recipe starts failing to load, the refusal names the value and what
  it would have produced.
* The author's given name no longer ships inside the wheel. It sat in
  the `reason:` field of `qa/references/PHY-06.yaml`, which is declared
  package data, so it travelled to every machine that installed the
  library. The field itself is kept, including the probe reports it
  cites, which are the provenance that makes the reference defensible;
  only the attribution is rewritten. The name stays where it is
  authorship rather than incident (`LICENSE`, `CITATION.cff`, `README`,
  the docs), and a tier-1 guard now scopes the refusal to `src/`.
* The role-review push gate no longer lets a release reach PyPI with no
  release attestation. Its release detection was a denylist of exact
  option spellings (`--tags`, `--follow-tags`) plus a version-tag
  pattern that did not accept the `refs/tags/vX` form, so
  `git push --follow-tag origin main` (git accepts any unambiguous
  option prefix) and `git push origin HEAD:refs/tags/vX` both cleared as
  ordinary branch pushes and, with the branch already pushed and
  review-attested, shipped the tag with no release attestation into the
  live trusted-publishing workflow. The hardened gate and multi-ref
  attestation writer were promoted from the sister library as one
  matched change: option handling is now a fail-closed allowlist that
  denies any leading-dash token it cannot prove ref-neutral, release
  classification reads both sides of a refspec, push scope is resolved
  per ref (and per the remote the command would actually use), the
  repository identity for the incident query comes from
  `pyproject.toml` rather than the checkout folder, and
  `write_attestation.py` validates the pass names and covers every named
  ref in one run so a branch-and-tag release is attestable. Both
  original inputs were reproduced allowing against the pre-port gate and
  denying against the ported gate. `tests/test_push_gate.py` grows to
  the sister library's end-to-end case set and a new
  `tests/test_write_attestation.py` pins the writer. Incident
  INC-20260724-0839-pyflightstream (`.claude/` hooks; internal tooling,
  not a package surface).
* The push gate no longer falsely blocks a commit whose message is a
  heredoc that mentions a push. The gate's `_strip_heredocs`, which is
  meant to drop heredoc bodies before tokenizing, carried a stray
  U+0001 control byte at the end of its opener regex (invisible in an
  editor), so the pattern matched nothing, the stripper was dead, and
  the body was tokenized: a routine `git commit` documenting a push was
  denied. The byte is removed and a test pins all three delimiter
  forms. Same control-byte class as INC-20260724-0410-shared. Incident
  INC-20260724-0912-pyflightstream (`.claude/` hooks; internal tooling,
  not a package surface).
* A settings preset written in the solver's own words no longer fails
  to convert, and the same words can no longer invert a run in silence.
  `viscous_coupling = 'DISABLE'` in a settings file was refused with a
  bool-parsing message that named neither the vocabulary nor the
  translation; passing the same string to `solver_settings` emitted
  `ENABLE`, because a non-empty Python string is truthy and the toggle
  renderer only tested truthiness. Both directions of the vocabulary now
  live in one place (`script.toggles.resolve_toggle`), the helpers read their
  toggles before the first emission, and a word in neither vocabulary is
  refused naming the helper and the argument. Every release up to and
  including v0.3.0 is affected: a toggle passed as `'DISABLE'` emitted
  ENABLE, and the solver-setup snapshot recorded the inverted value as
  if it had been chosen. Runs whose recipes passed Python booleans are
  unaffected; to check an archived campaign, read the toggle lines of
  the rendered scripts under the managed simulation folders, or the
  `solver_setup` block of `runs.json`. Incident
  INC-20260723-2027-pyflightstream (feedback channel item 2, PLN-074).
* A swept case no longer loses the evidence of every point but the
  last. All points of a case run in the same simulation folder and are
  collected into `raw/` under their own names, so a declared output
  without the `{point}` placeholder was written, collected, and
  overwritten once per point, while the manifest listed the surviving
  file for all of them. The campaign loop now renders every point's
  output names before running the case and blocks it when two points
  would write the same one, so the check judges the actual collision
  rather than the presence of a particular placeholder (any template
  that distinguishes the points passes, and `{mach}`, which does not,
  is caught). The campaign example and the guide teach
  `outputs = ["loads_{point}.txt"]` with the recipe exporting
  `case.outputs[0]`, and `LoadsAssessor()` finds the loads table by
  content, so per-point evidence and convergence judgment are no longer
  exclusive. Incident INC-20260723-2113-pyflightstream.
* The user guide's flagship campaign listing imported `LoadsAssessor`
  from `pyflightstream.results`, where it does not exist; the guard
  below now checks every `from pyflightstream... import ...` line the
  guide teaches.
* The user guide taught `case.staged_geometry`, which `SimCase` never
  had: the campaign loop stages the geometry and rewrites
  `case.geometry`. A reader copying the campaign recipe got an
  `AttributeError` on their first point. Both occurrences corrected, and
  `tests/test_guide_api_names.py` now asserts that every `case.`,
  `helpers.` and `script.` name the guide teaches exists, and that every
  import line it shows resolves, so an unexecutable sample cannot ship
  again. Incident INC-20260723-2041-pyflightstream (PLN-084).
* `solver_settings(vorticity_drag_boundaries=...)` is optional again,
  and the guard that made it mandatory in v0.3.0 is gone: it stated the
  inverse of the manual page it cited. Boundaries left off the vorticity
  CDi list use the solver's surface pressure integration, a complete
  induced-drag calculation; the zero-drag pitfall happens the other way
  around, to a bluff body without a user-defined trailing edge that is
  put *on* the list, which also made the guard's suggested remedy
  (`"all"`) the very trap it claimed to prevent (SRC-003 p.202).
  Omitting the argument now emits no selection command and the
  solver-setup snapshot records the flag as a `default` with an empty
  selection and the citation, so the manifest still says which
  boundaries used vorticity integration (none). An empty sequence is
  refused (the same refusal now guards the deprecated `analysis_setup`
  keyword) with a message pointing at the omission that means the
  solver default. This restores the pre-v0.3.0 reproduction path (a
  legacy setup that never sets the list), which the guard had broken.
  The documentation carrying the inverted claim moved with it: the
  helper docstrings, the user guide (including the pitfalls slide),
  SRS FR-22 and its revision history, the command-database note, the
  examples, and the api-designer reviewer charter, which cited the
  guard as a didactic precedent (PLN-075).
* The deprecated `analysis_setup(vorticity_drag_boundaries=...)` no
  longer leaves the solver-setup snapshot describing a script that was
  never built: it now restamps the induced-drag record it overrides,
  records resolved boundary indices like the settings path rather than
  raw labels, and resolves and emits before touching the snapshot, so a
  bad label leaves the script, the deferred selection, and the record
  untouched. The corrected snapshot is `script.solver_setup`; a
  snapshot returned by an earlier `solver_settings` call is frozen at
  its own state. `Script` declares `solver_setup` and its induced-drag
  state as real attributes instead of carrying them as patched-on
  names.
* CI lint stage restored to green: the `ruff` dev dependency is pinned
  to `0.15.22` (matching the pre-commit hook) and Markdown files are
  excluded from ruff via `extend-exclude`. An unpinned ruff had begun
  reformatting the Python code samples inside `fsi/README.md` (an
  illustrative developer README, not a `.py` source the formatter
  owns), failing `ruff format --check`. The pin restores the known-good
  formatter and keeps CI, the hook, and developer machines identical;
  the `*.md` exclude makes the formatter's scope version-independent for
  any later ruff (PLN-024).
* Role-review gate before lane D caught residual user-guide staleness
  the v0.3.0 refresh missed: the Tier 2 pitfalls slide still listed
  `NEW_SURFACE_SECTION_DISTRIBUTION` as broken (it was promoted to
  verified in the licensed session), the install slide said "not yet
  on PyPI", the runtime-dependency list omitted xarray, and `post`
  and `fsi` were called reserved seams though both shipped; all
  corrected. The `NEW_SURFACE_SECTION_DISTRIBUTION` database note
  dropped its pending-re-probe language now that the re-probe decided,
  the `campaign_matrix` example's licensed `run_campaign` call names
  the required `assess`, and the `[plot]` extra records its
  matplotlib license note.
* Post-release front-page currency: README and the docs home announce
  v0.3.0 as public (they lagged at v0.2.0), the SRS roadmap moves the
  v0.3.0 release to Delivered, the standards page moves the Sybil
  executable-examples row to Adopted, the README DOI badge points at
  the Zenodo concept DOI, the CHANGELOG gains its `[Unreleased]` and
  `[0.3.0]` link references, and the user guide architecture labels
  use `workspace` (not the deprecated `files`).

## [0.3.0] - 2026-07-23

The v0.3.0 line: the usage-feedback workstreams (PLN-022) triaged from
the author's first outside-the-repo use of 0.2.0, delivered 2026-07-22,
plus the protocol and library-review adoptions of the ultraplan week.

### API surface delta

* New public names: the `workspace` package (renamed from `files`);
  `options` (plus top-level `get_option`, `set_option`,
  `reset_option`, `describe_option`, `option_context`); `exceptions`
  (the 25-class catalog); `testing` (`assert_records_close`,
  `assert_scripts_equal`); `overview()`; `solver_settings`,
  `SolverSetup`, `script_from_setup`; `cases.matrix` (`MatrixError`,
  `MatrixRow`, `resolve_matrix`, `plan_matrix`, `run_matrix`,
  `convert_matrix`, `to_campaign`); the pandas tables (`to_dataframe`,
  `to_csv`, `run_frame`, `sweep_frame`); `reference.CONVENTIONS`;
  `EntityRegistry`; the `pyfs-workspace` and `pyfs-matrix` CLIs.
* Incompatible changes: `solver_settings` requires
  `vorticity_drag_boundaries` (superseded: the requirement rested on a
  misread of SRC-003 p.202 and was removed, see Unreleased); the
  behavior selectors of `help`, `overview`, `run_campaign`,
  `register_option`, and `read_matrix` are keyword-only;
  `pyflightstream.files` and
  `pyflightstream.cases.matrix_legacy` are renamed (import shims kept
  through v0.4.0); converted campaigns carry `matrix_*` variable keys
  (were `legacy_*`).
* Deprecations: `pyflightstream.files` and
  `pyflightstream.cases.matrix_legacy` (removal v0.4.0,
  deadline-guarded); the `analysis_setup(vorticity_drag_boundaries=...)`
  path toward `solver_settings`.
* Removed: none (the `Legacy*` names survive as shim aliases).

Known gaps named for the next window: the formal `verified`
promotions of the version-sensitive commands (PLN-015) and the
aeroelastic family (PLN-019), and the unsteady-chapter backfill of
PHY-05/06 across versions.

### Added

* `workspace` package (renamed from `files`): the campaign workspace
  now organizes inputs as well as outputs, with a declarative
  input-artifact library under `inputs/` (references, solver-setup
  presets, boundary groups, geometries, profiles, and an executables
  registry by build id with an explicit-override rule), output naming
  templates (`NamingTemplate`, output-only by design: the manifest
  stays the sole identity authority and no parse-back API exists),
  `CampaignWorkspace.init()` behind the new `pyfs-workspace` CLI,
  campaign pre-flight (`plan_campaign`, zero solver time), and
  resumable incremental sweeps (`run_campaign(resume=True)`).
* Entity label registry in the script builder: frames, actuators,
  motions, and boundaries can carry user labels; every entity-citing
  argument accepts index or label; `declare_existing` accepts named
  boundary inventories; boundary range checks apply once declared.
* Solver-setup provenance: `solver_settings` becomes the single entry
  point for all 28 commands of the runtime, solver, and advanced
  settings families and returns a `SolverSetup` snapshot recording
  every flag's effective value with provenance (explicit,
  evidence-backed default, or unknown, never guessed); the snapshot
  rides the run manifest and `script_from_setup` regenerates the
  script from it.
* Tabular results layer on pandas: `to_dataframe`/`to_csv` for every
  parser, `run_frame` (one wide row per run), and `sweep_frame` (the
  whole sweep from the manifest).
* The run matrix as a first-class interface: `resolve_matrix`,
  `plan_matrix`, and `run_matrix` bind the matrix columns to the
  workspace input library; new `pyfs-matrix` CLI (convert, plan);
  the matrix fixture grows to eight rows.
* Two-level help: `pyflightstream.overview()` renders the
  architecture from the live module docstrings (docs Architecture
  page from the same source), and the command reference gains a
  manual-coverage section with explicit gap notes.
* `pyfs-qa cases`: the Tier 3 physics registry printed as a numbered
  test matrix.
* Command schema: optional evidence-cited default metadata.
* Deprecation ledger (`pyflightstream._deprecations`): every shim's
  removal promise recorded as a concrete version, with a Tier 1
  deadline guard that fails the suite when a shim survives past its
  recorded removal version or its warning stops citing it. Both live
  shims (`files`, `cases.matrix_legacy`) are registered with removal
  at v0.4.0, and their warnings now state that exact version instead
  of "a future minor release".
* `pyflightstream.options`: the declared-knob registry in the pandas
  `register_option` model (D1 adoption), with per-key validators,
  `option_context`, and `describe_option`. Keys are exact by design
  (never pattern-matched) and refusals follow the openmdao message
  contract (unknown keys list every registered key; rejected values
  name the option, the value, and the accepted form). First
  registered knobs: `qa.scratch_root`, `qa.probe_timeout_s`,
  `qa.case_timeout_s`; the `pyfs-qa` CLI scratch and timeout defaults
  now read from them. `get_option`, `set_option`, `reset_option`,
  `describe_option`, and `option_context` are re-exported at the
  package top level (pandas-style access); path options accept
  `pathlib.Path`.
* The public import surface is now affirmed by test (scipy
  `_public_api` model): `tests/test_public_api.py` declares every
  public module; a new module must join the list consciously or carry
  a leading underscore, deprecated modules are documented by the
  ledger alone, and every public module must import cleanly (or
  refuse with the install remedy) and carry its pipeline docstring.
  Lazy loading deliberately not adopted (D3 resolution).
* Tier 1 wording pins for the main didactic refusals
  (`tests/test_error_messages.py`, xarray pattern): versions,
  `solver_settings` (mandatory vorticity selection with the
  zero-induced-drag cause, mode regime, unsteady time stepping),
  workspace input library (id model, empty-library remedy, available
  ids listing), and the run-matrix reader (verified codes and layout).
  A refactor that keeps the exception type but drops the explanation
  now fails the suite. The mandatory-selection pin is superseded in
  Unreleased by the empty-selection refusal (SRC-003 p.202).
* `pyflightstream.exceptions`: single public catalog of all 25
  exception and warning classes (pandas errors model); completeness
  is test-asserted mechanically, so a new exception class must join
  the catalog in its defining commit. Structured refusals:
  `UnknownVersionError` now carries `version` and `known`,
  `InputArtifactError` carries `kind`, `artifact_id`, and
  `available`, so callers react without parsing messages.
* `pyflightstream.testing`: public assertions with quantified
  violation reports under the golden philosophy split;
  `assert_records_close` (count, violating keys, worst offender) and
  `assert_scripts_equal` (first differing line, total differing
  count, exact by policy).
* House conventions get a single home: `reference.CONVENTIONS`
  (naming, unit suffixes, keyword-only selectors, refusal style)
  rendered by `pyflightstream.help()` with a tier 1 adherence audit
  (`tests/test_conventions.py`) sweeping the code against the
  mechanical rules.
* Test-isolation hygiene: an autouse fixture snapshots every
  module-level registry and cached mutable default (physics and SMI
  cases, probe specs, derived flag map, sweep codes, entity nouns,
  the cached command database and manual-edition map) before each
  test and restores it after, so a mutating test cannot leak state;
  the inventory lives in one place in `tests/conftest.py` and the
  mechanism is itself tested.

### Changed

* `solver_settings` now requires `vorticity_drag_boundaries`
  (breaking; forgetting the selection silently zeroes the
  induced-drag accounting. Superseded: that rationale states the
  inverse of SRC-003 p.202, the requirement was removed in Unreleased,
  and boundaries left off the list keep the solver's surface pressure
  integration) and emits `SOLVER_MINIMUM_CP -100` by
  default when the flag is not passed, retiring the earlier
  reference-velocity workaround for rotor Cp clipping (override by
  passing the parameter). The PHY references were re-validated under
  the emitted default on a licensed 26.120 machine (build 7012026):
  all 30 metrics reproduce bit-identically, so no reference value
  changed (report
  `reports/physics/PHY-26120_2026-07-23_reseed-cp100-2026-07-23.md`).
* The run-matrix vocabulary drops the word "legacy" everywhere users
  see it: `LegacyMatrixError` and `LegacyRow` are renamed
  `MatrixError` and `MatrixRow`, and `to_campaign`/`convert_matrix`
  now preserve the matrix codes as `matrix_*` case variables
  (previously `legacy_*`; campaign files converted earlier keep their
  old keys and stay loadable, test-pinned). `read_matrix` makes
  `active_only` keyword-only, matching the rest of the module.
* Behavior-selecting arguments are keyword-only where the naming
  conventions already claim it (breaking, inside the unreleased v0.3
  window): `help(version, *, path, open_browser)`,
  `overview(*, path, open_browser)`, `run_campaign(campaign,
  executor, workspace, *, assess, recipes, resume)`, and
  `register_option(key, *, default, doc, validator)`. Positional
  calls to these selectors now raise `TypeError`.
* The motivation narrative (README, docs home, SRS introduction, user
  guide) now frames version drift as the natural counterpart of an
  actively developed solver whose team is responsive and consolidates
  user requests through intermediate hotfix builds into stable
  releases, instead of reading as criticism of the changelog; the
  documented facts and citations are unchanged.
* The docs toolchain migrated from MkDocs to ProperDocs, the
  maintained fork (license evidence RPT-009), after a green test:
  drop-in at the config and CLI level, with strict build and an
  identical page set and content on the same sources. The config
  file is renamed `properdocs.yml`, CI builds with
  `properdocs build --strict`, and the `[dev]` extra gains
  `properdocs` (the material theme and the nav plugins keep their
  mkdocs package names during the ecosystem transition; the build
  hook now imports from the `properdocs` namespace).

### Deprecated

* `pyflightstream.files`, in favor of `pyflightstream.workspace`: the
  shim re-exports everything with a DeprecationWarning until its
  recorded removal at v0.4.0 (deprecation ledger, deadline-guarded).
  The `analysis_setup(vorticity_drag_boundaries=...)` path is
  deprecated toward `solver_settings`.
* `pyflightstream.cases.matrix_legacy`, in favor of
  `pyflightstream.cases.matrix`: the shim re-exports everything until
  its recorded removal at v0.4.0 (deprecation ledger,
  deadline-guarded), keeping `LegacyMatrixError` and `LegacyRow` as
  aliases of the renamed classes. Both shims attribute their
  DeprecationWarning to the importing line on Python 3.12+, so plain
  script runs see it too.

### Fixed

* `__version__` now derives from the installed metadata (the
  published 0.2.0 wheel answered `0.0.1.dev0`), and the package
  docstring no longer describes the M0 skeleton.
* The public documentation caught up with the code after a full
  staleness audit: README rewritten to the released state, docs home
  updated, all three examples rendered on the site, CONTRIBUTING
  setup corrected.
* `pyflightstream.exceptions` now imports on a base install without
  the `[fsi]` extra: `StaleLoadsError` moved to `pyflightstream.fsi.state`
  (still re-exported by `fsi.driver`) so the catalog no longer pulls
  PyNite through the FSI modules on import.

### Evidence (licensed 26.1x session, 2026-07-23)

* `NEW_SURFACE_SECTION_DISTRIBUTION` moves broken to verified on
  26.120: the phase and `INCLUDE_SYMMETRY` grammar correction is
  confirmed by a re-probe (`CMP-26120_2026-07-23_pln012`);
  `AIR_ALTITUDE`, `SET_MOTION_START_TIME`, and
  `NEW_OFF_BODY_STREAMLINE` are re-confirmed broken.
* The bulk-separation spelling is resolved (`RPT-012`): the 26.100
  solver accepts `CREATE_BULK_SEPARATION` and rejects the manual
  sample-block spelling `CREARE` as unrecognized, so the database
  keeps the header spelling and no alias is added.
* Two research findings backing future features: `EXPORT_SURFACE_MESH`
  OBJ writes one named object block per boundary from the source mesh
  solid name (`RPT-010`, a fsm-to-obj boundary inspector is feasible),
  and the settings-and-status export exposes only the steady-mode
  default, not the wake and viscous toggles (`RPT-011`, their
  provenance stays honestly unknown).

### Added (documentation and process)

* Executable documentation examples in CI (Sybil): the docstring
  doctests and the python code blocks in the root README and `docs/`
  run as a CI step with warnings promoted to errors, so a stale
  example fails the build; `sybil` joins the `[dev]` extra. Three
  path-scoped Sybils leave the default `pytest` run untouched;
  CONTRIBUTING documents the local command. The README quickstart and
  the four example blocks execute green on 3.11 and 3.12.
* The user guide (`guide/`) is refreshed to the v0.3 surface
  (PLN-030): version 0.3.0, sixteen curated helpers (with
  `start_solver` and `coordinate_frame`), 144 commands, the current
  26.120 evidence counts, the `workspace` import path, and a
  four-tool command-line cheat sheet (`pyfs-qa` including `cases`,
  `pyfs-workspace`, `pyfs-matrix`, `pyfs-fsi`).
* New worked example `examples/campaign_matrix.py` (rendered on the
  docs site): the campaign side end to end without a license, run
  matrix to `campaign.toml` to a zero-solver `plan_campaign`
  pre-flight reporting the ready sweep points.
* Mesh inputs and GUI-only operations policy page in the docs
  (PLN-028): the supported GUI-once-then-script workflow when a step
  has no scripting command, the two canonical mesh input routes
  (geometry meshed inside FlightStream carried as a saved `.fsm`
  artifact, or a direct OBJ mesh), and the mesh format policy (OBJ
  as the reference format; further formats only ever behind a
  project-owned adapter).
* The Software Requirements Specification is published as a living
  document in the docs (`docs/srs/`): founding requirements with
  implementation statuses, the usage-feedback requirements, explicit
  non-requirements, architectural rules, standards alignment with
  verified references, and the roadmap.
* Documentation-currency policy (SRS NFR-11) with Tier 1 guards:
  version-bearing metadata files must agree, the changelog always
  carries its Unreleased section, SRS requirement ids never repeat.
* CONTRIBUTING discloses the AI-assisted development model and the
  process safeguards around it (evidence discipline, role-based
  review, the author's non-delegable seats, the clean-room rule
  extended to the AI), per the pyOpenSci disclosure item.
* README opens with status badges and a runnable quickstart snippet
  (validated build plus the didactic version refusal), and its
  feature list caught up with the cycle (options registry, exceptions
  catalog, testing assertions); live counts now stay with the
  generated compatibility matrix instead of hardcoded prose.
* Published package metadata completed per the PyPA well-known
  guidance (audit 2026-07-23): trove classifiers (beta status,
  science audience, Python versions, physics topic) and the
  Documentation, Changelog, and Issues project URLs join the
  Repository link.
* The documentation site is published to GitHub Pages on every push
  to main (`nevesgeovana.github.io/pyflightstream`), so the generated
  command reference, compatibility matrix, and architecture pages are
  reachable without a local build. The unused `mkdocstrings[python]`
  dev dependency was dropped (it was never wired into the build; the
  offline `help()` and `overview()` remain the docstring surface).
* Repository top level reduced to the public essentials: the
  author's session records left Git versioning (history preserved),
  and a `deprecated/` folder now groups discontinued public items.
* Role-based review process: five reviewer charters in
  `.claude/agents/` (architect, QA engineer, V&V engineer, technical
  writer, API designer) and the `role-review` skill that runs the
  applicable passes on a work item's diff before it closes, per the
  team-role model adopted 2026-07-23; the definition of done cites
  the passes, the author keeps the non-delegable seats (product
  owner, domain expert, numerical analyst), and the standards
  alignment chapter records the model's public anchors.
* Co-development with the sister library ITACA (AD-07): the two
  libraries may generate requirements for each other, the docs gain
  the sister library page describing the division of labor and the
  cross-requirement convention, and the future data adapter is
  declared as a pyflightstream `[itaca]` extra (superseded: no such
  extra was ever added to `pyproject.toml` and none will be; ITACA
  arrives as a core dependency, see Unreleased) (ITACA stays
  solver-agnostic and never imports this package).

## [0.2.0] - 2026-07-22

First public release (PyPI and Zenodo). Milestones M6 (FSI) and M7
(far-field probes) landed between the tags, together with the Tier 3
matrix growth and a round of solver findings, every one backed by a
committed report.

### Added

* `fsi` subpackage (optional `[fsi]` extra, PyNiteFEA): validated
  `FsiConfig` with canonical hashing; sectional loads parser with the
  SI assertion, family-per-blade attribution with geometric
  cross-checks, and the pitch-axis to elastic-axis moment transfer;
  PyNite beam of the (w, theta) blade with exact massless-DOF
  condensation and clamped-beam benchmarks; centrifugal terms
  (tension through P-Delta, propeller moment with inner twist
  iteration) with the Campbell/Southwell verification; twist encoded
  as three-node differential translations with the exact inverse;
  node file, ordering map, and FSIDisp writer/reader from one
  generator, embedding sections at the local blade angle on spinning
  blades; four-phase coupling driver (wake, averaged relaxed
  coupling, convergence watch, unrelaxed recording) with atomic
  state, per-call freshness assertions, frozen replay mode, and a
  hash-carrying convergence log; `pyfs-fsi` executable dispatching
  between the coupled driver and the interface-evidence dummy.
* `probes` and `farfield` (far-field extraction line): serializable
  cylindrical lattice with version-aware emission; planar Cartesian
  probe grids on explicit frames with element-size and
  cosine/geometric distributions; geometry gate (optional `[geom]`
  extra) with containment culling, boundary-layer band refinement,
  and a wall standoff margin; single quadrature, azimuthal FFT
  harmonic spine, and the conservation ledgers with the synthetic G0
  gate in Tier 1; probe-export parser with the row-order contract
  check; `run.export_surface_mesh` pre-processing; `post` VTK and
  Tecplot probe-data writers.
* `qa`: PHY-05 (generic-blade unsteady periodic propeller) and
  PHY-06 (steady-versus-unsteady polar trend, 16 metrics) in the
  Tier 3 matrix with a per-version evidence gate; the `BladeSpec`
  generic propeller blade generator (public analytic shape laws).
* Command database grown from 116 to 144 entries: motion, unsteady
  solver, scenes, and advanced-settings backfill from the
  case-reproduction run; the mesh-import family; the Aeroelastic Coupling
  Toolbox family; per-version argument grammars
  (`versions.<v>.args`) with hotfix inheritance for the 26.1/26.12
  manual delta.
* Examples: FSI Campbell diagram and the wing static deflection
  worked cases; the beamer user guide source under `guide/`.

### Changed

* Two emission phases corrected on reproduction evidence
  (`SET_ANALYSIS_SYMMETRY_LOADS` and
  `NEW_SURFACE_SECTION_DISTRIBUTION` are in-solve consumers and
  precede `START_SOLVER`).
* `xarray` promoted to a runtime dependency (the far-field ledgers
  live on labeled arrays).

### Evidence

* FSI interface established on 26.120 build 7012026
  (`reports/RPT-005` to `RPT-007`): the implemented scripting
  interface is the Aeroelastic Coupling Toolbox family (the manual's
  `SET_MOTION_FSI` pair is unrecognized, candidate broken); the
  sectional loads export carries line densities and a three-decimal
  time-increment header (both folded back as code); the coupled loop
  ran 54/54 and 90/90 calls with the full phase machine and frozen
  replay reproducing held deformations to 5e-6.
* Probe round trip on 26.120 (`reports/RPT-004`): imported probe
  count and row order preserved exactly; boundary-layer export
  columns are geometric (erratum), motivating the standoff margin.
* PHY-05 bit-identical to its shareable-case baseline; PHY-06 polar
  trend 16 pass with monotonic steady-versus-unsteady deltas.

### Known limitations

* Two-way rotor FSI is blocked on FlightStream 26.120 build 7012026:
  the solver silently does not apply `FSIDisp.txt` morphing to
  boundaries attached to a rotary motion, while a motionless boundary
  morphs correctly with the same command sequence
  (`reports/RPT-007`; vendor report prepared). The coupling loop
  mechanics, the structural side, and the motionless path are fully
  functional.

## [0.1.0] - 2026-07-21

First tagged release, private phase. Everything below landed between
the repository seeding and this tag (milestones M0 through M5).

### Added

* `versions`: canonical 26.XXX version scheme with the ordered
  registry in `commands/_meta.yaml` as the only ordering authority;
  display aliases; registered manual editions (SRC-003 for 26.120,
  SRC-725 for 26.100).
* `commands`: version-aware command database, 116 commands drafted
  from the manual with a page citation each, typed argument
  specifications, script layout grammars, emission phases, and
  per-version evidence statuses (documented, verified, broken,
  removed) enforced at load time; hotfix builds inherit their base
  release record.
* `script`: builder with validating emit against the per-version
  database view, phase ordering, five layout renderers, and curated
  workflow helpers with a cross-reference ledger.
* `files` and `run`: managed campaign workspace with staging hashes
  and an append-only run manifest; local headless executor using the
  documented `-hidden --script` invocation.
* `cases`: SIM campaign model with TOML loading, recipe registry,
  campaign loop with six run statuses, and the pipe-delimited
  15-column run-matrix reader with lossless code preservation and
  TOML round-trip conversion.
* `results`: loads and residual-history parsers with sanitized
  fixtures from real 26.120 output; version cross-check recording the
  solver-reported version and build verbatim.
* `qa`: three-tier evidence harness. Tier 2 probe suite (109 specs)
  with committed compat reports and status promotion only through
  `pyfs-qa apply-compat`; Tier 3 physics regression matrix (PHY-01
  wing polar, PHY-02 symmetry equivalence) against banded references,
  plus the cross-version drift suite with the local-only SMI class
  behind an explicit `--smi-root`; `pyfs-qa` CLI with probe,
  apply-compat, physics, drift, and update-reference.
* `reference`: single rendering source for the command reference.
  `pyflightstream.help()` writes a self-contained HTML page offline;
  the mkdocs site renders the same database into a per-chapter
  command reference and a version compatibility matrix at build time
  (nothing generated is committed).
* Docs site (mkdocs-material, strict): generated reference and
  matrix, evidence-discipline overview, and the steady polar example
  rendered from its percent-format source.
* `examples/steady_polar.py`: synthetic NACA 0012 wing, one
  version-validated script per angle, the didactic refusal for a
  version without evidence, optional solver execution behind an
  explicit executable path; executed on 26.120 build 7012026 with
  lift slope 4.83 per rad against the finite-wing anchor 5.03.

### Evidence

* 26.120 (build 7012026): 64 commands verified, 4 broken, full
  physics matrix 10 pass (`reports/compat/CMP-26120_2026-07-21_full`,
  `reports/physics/PHY-26120_2026-07-21_full`).
* 26.100 (build 5012026): 28 commands documented from the 26.1 manual
  (SRC-725), one removal; first real cross-version drift 17 pass
  1 warn (`reports/physics/DRF-26100-26120_2026-07-21_complete`); the
  warn triaged as a deterministic solver change between builds
  (`reports/physics/TRI-SMI01-CMy_2026-07-21`).
* 26.000: registered, no recorded evidence yet (honest empty column;
  backfill planned for v0.2+).

[Unreleased]: https://github.com/nevesgeovana/pyflightstream/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.3.0
[0.2.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.2.0
[0.1.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.1.0
