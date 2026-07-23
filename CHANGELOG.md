# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

The v0.3.0 line: the usage-feedback workstreams (PLN-022) triaged from
the author's first outside-the-repo use of 0.2.0, delivered 2026-07-22,
plus the protocol and library-review adoptions of the ultraplan week.
Deprecation messages naming v0.3.0 refer to this release.

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
  now read from them.
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
  now fails the suite.
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
  induced-drag accounting) and emits `SOLVER_MINIMUM_CP -100` by
  default when the flag is not passed, retiring the earlier
  reference-velocity workaround for rotor Cp clipping (override by
  passing the parameter; PHY reference re-validation queued).
* The run-matrix vocabulary drops the word "legacy" everywhere users
  see it: `LegacyMatrixError` and `LegacyRow` are renamed
  `MatrixError` and `MatrixRow`, and `to_campaign`/`convert_matrix`
  now preserve the matrix codes as `matrix_*` case variables
  (previously `legacy_*`; campaign files converted earlier keep their
  old keys and stay loadable, test-pinned). `read_matrix` makes
  `active_only` keyword-only, matching the rest of the module.
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

### Added (documentation and process)

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
* README opens with status badges and a runnable quickstart snippet
  (validated build plus the didactic version refusal), and its
  feature list caught up with the cycle (options registry, exceptions
  catalog, testing assertions); live counts now stay with the
  generated compatibility matrix instead of hardcoded prose.
* Published package metadata completed per the PyPA well-known
  guidance (audit 2026-07-23): trove classifiers (beta status,
  science audience, Python versions, physics topic) and the
  Changelog and Issues project URLs join the Repository link.
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

[0.2.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.2.0
[0.1.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.1.0
