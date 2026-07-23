# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

### API surface delta

* `solver_settings(vorticity_drag_boundaries=...)` is optional again
  (a relaxation, so no caller breaks). Omitted on a script that has not
  selected yet, it emits no selection command and the snapshot records
  the flag as `default` with an empty selection and its citation, or as
  `unknown` on a FlightStream version where the command has no recorded
  evidence; omitted on a second settings call of the same script, the
  selection of the earlier call stands, in the script and in the
  snapshot. An empty sequence is refused.

### Added

* House conventions page on the docs site
  (`reference.conventions_markdown`, the same source as the offline
  `help()` conventions section), wired into the generator and nav.
* Automated PyPI release through trusted publishing (OIDC):
  `.github/workflows/release.yml` builds, checks the tag against the
  `pyproject.toml` version, and publishes from the GitHub `pypi`
  environment on a `v*` tag, so no API token is stored in the
  repository (mirrors the ITACA release workflow). Development process:
  a mandatory role-review push/release gate now blocks a `git push`
  until the specialist reviewer agents have run and attested the
  pushed commit (`.claude/` hooks and skills; internal tooling, not a
  package surface).

### Fixed

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
  declared as a pyflightstream `[itaca]` extra (ITACA stays
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
