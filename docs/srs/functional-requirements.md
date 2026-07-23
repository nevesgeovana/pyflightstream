# Functional requirements

Numbering is stable: a deprecated requirement keeps its identifier
forever. Each requirement cites its origin (BRF and PP items, see the
[introduction](introduction.md)) and carries a status with evidence.
Milestones and session records are listed in the
[roadmap](roadmap.md).

## Version-aware command database

!!! requirement "FR-01 Command database <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03, PP-8. Evidence: milestone M1; the database and
    its Tier 1 schema tests.*

    The package ships a machine-readable database of FlightStream
    script commands. Each entry records name, layout grammar, typed
    arguments, the version span in which it exists, per-version
    argument differences, and a manual page citation.

!!! requirement "FR-02 Launch version set and ordering <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-07, BRF-19. Evidence: milestone M1; `versions` tests.*

    The database covers versions 26.0, 26.1, and 26.12 at launch,
    with an explicit ordered version list. Version ordering never
    relies on string or float comparison ("26.1" < "26.12" fails
    both).

!!! requirement "FR-02a Canonical 26.XXX identifiers <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-19. Evidence: milestone M1.*

    The canonical version identifier is `26.XXX` with exactly three
    fractional digits: the first two carry the official minor release,
    the last indexes intermediate hotfix builds (0 = the official
    release). Launch set: 26.000, 26.100, 26.120. The registry stores
    display aliases so users may write "26.12" and get 26.120.

!!! requirement "FR-03 Evidence-backed per-version statuses <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03. Evidence: milestone M1 (schema), M3 (first
    promotions); committed compat reports.*

    Each command carries a per-version status: `documented`,
    `verified`, `broken`, or `removed`. Documented and verified are
    distinct because the manual and the solver disagree in practice.
    Statuses are promoted only by committed probe reports.

!!! requirement "FR-04 Build-time version refusal <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03, PP-8. Evidence: milestone M1; refusal tests and
    the worked example's didactic 26.0 refusal.*

    Building a script with a command that does not exist in the
    target version fails at build time, before any solver run, with
    an error that cites the manual and suggests the successor command
    when one is known.

## Script construction

!!! requirement "FR-05 No global state <span class='srs-implemented'>implemented</span>"
    *Origin: PP-2. Evidence: milestone M2; concurrent-build tests.*

    Script construction uses an object bound to a version-specific
    registry view. Two scripts can be built concurrently without
    interference.

!!! requirement "FR-06 Curated helpers <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-04. Evidence: milestone M2; helper goldens.*

    A curated set of thin helpers covers the common steady and
    unsteady workflows. Helpers emit database-validated commands and
    add no hidden logic.

!!! requirement "FR-07 Recorded escape hatch <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-12. Evidence: milestone M2; the manifest raw flag.*

    A raw-emission escape hatch allows arbitrary lines, and its use
    is recorded in the run manifest, so no run silently depends on
    unvalidated commands.

!!! requirement "FR-08 Clean-room emitter <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-10. Evidence: repository invariant; contribution
    policy.*

    The emitter layer is specified exclusively from the official
    manual and from probe evidence. No code, structure, or docstrings
    derive from the AGPL ecosystem predecessor.

!!! requirement "FR-08a Phase ordering enforced <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-13. Evidence: milestone M1 (phases in the schema),
    M2 (builder enforcement); phase tests.*

    Database entries carry a script phase. The builder validates
    ordering at build time: pre-solver definitions emitted after
    solver initialization are rejected with a didactic error, and
    referencing an undefined entity fails at build time, not run time.

## Case and campaign model

!!! requirement "FR-09 Typed, simulation-centric model <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-01, BRF-16. Evidence: milestone M2.*

    Cases and campaigns are typed data objects. The unit of work is a
    SIM with a `sim_id`. A campaign declares its FlightStream version
    and executable path explicitly; neither is guessed.

!!! requirement "FR-10 Run-matrix reader, forever <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-08. Evidence: milestone M2; the verified 15-column
    layout and its fixtures.*

    A dedicated reader consumes the pipe-delimited run-matrix
    format unchanged, forever. Rows with RUN = 1 are
    active; the sweep columns define alpha, beta, or advance-ratio
    sweeps; the variables column holds KEY:VALUE pairs.

!!! requirement "FR-11 Lossless one-command conversion <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-08, BRF-16. Evidence: milestone M2; TOML round-trip
    tests; the `pyfs-matrix convert` CLI (v0.3 line).*

    A convert command turns a run matrix into the native campaign
    format, one command, optional, and lossless. The matrix POL
    column maps to the native `sim_id`; the matrix reference codes
    are preserved verbatim.

!!! requirement "FR-12 Recipes as explicit protocol <span class='srs-implemented'>implemented</span>"
    *Origin: PP-7. Evidence: milestone M2; recipe registry tests.*

    Script recipes are explicitly imported functions conforming to a
    documented protocol, replacing the predecessor's runtime file
    lookup by numeric code.

## Execution

!!! requirement "FR-13 Safe headless execution <span class='srs-implemented'>implemented</span>"
    *Origin: PP-5. Evidence: milestone M2; the executor tests and the
    documented headless invocation (SRC-003 pp.279-280).*

    Execution goes through an executor interface. The local executor
    uses subprocess with a timeout, checks return codes, and never
    uses shell=True.

!!! requirement "FR-14 Every point terminates in a status <span class='srs-implemented'>implemented</span>"
    *Origin: PP-5, BRF-12. Evidence: milestone M2; campaign-loop
    tests.*

    A campaign run records every datapoint outcome. Failures are
    collected and reported at the end as a structured error; a silent
    skip is structurally impossible.

!!! requirement "FR-15 HPC executor <span class='srs-pending'>pending</span>"
    *Origin: BRF-01.*

    An HPC executor submits runs through a cluster submission path.
    The executor interface must allow this without changes to the
    campaign model. Deferred; no cluster path ships today.

## Results and provenance

!!! requirement "FR-16 Anchor-based parsing <span class='srs-implemented'>implemented</span>"
    *Origin: PP-4. Evidence: milestone M2; parser fixtures from real
    solver output.*

    Output parsers locate data by anchors (labeled values, delimited
    tables), never by absolute line offsets.

!!! requirement "FR-17 Structural completeness checks <span class='srs-implemented'>implemented</span>"
    *Origin: PP-5. Evidence: milestone M2; incomplete-output tests.*

    An output file without its expected footer is
    FAILED_INCOMPLETE_OUTPUT, not a shorter table.

!!! requirement "FR-18 Version cross-check <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03. Evidence: milestone M2; the lax cross-check
    recording string and build verbatim.*

    The FlightStream version reported in outputs is cross-checked
    against the requested version; a mismatch raises a warning
    recorded in the manifest.

!!! requirement "FR-19 The manifest <span class='srs-implemented'>implemented</span>"
    *Origin: PP-6. Evidence: milestone M2; manifest tests; extended
    by FR-31.*

    Every campaign writes `runs.json` recording per run: identity,
    case point, versions and build, package version, input and script
    hashes, status, iterations, residual, wall time, outputs, and
    error text. Folder names are never authoritative.

## Post-processing

!!! requirement "FR-20 Labeled result arrays <span class='srs-pending'>pending</span>"
    *Origin: BRF-01, BRF-18.*

    The result-array API for multidimensional post-processing:
    labeled arrays, interpolation along named axes, axis
    re-parameterization, and trim extraction by interpolating a
    moment coefficient to zero. Partially covered today: sweep
    assembly landed as tabular results (FR-32) and field data as the
    far-field ledgers on xarray; the interpolation and trim API
    remains open.

!!! requirement "FR-21 Established plot-file writers <span class='srs-pending'>pending</span>"
    *Origin: BRF-01.*

    Plot files byte-compatible with the author's established plot
    format, with a reader making the pair round-trip testable. Not
    yet started; VTK and Tecplot probe-data writers exist in `post/`
    but that plot format is not among them.

!!! requirement "FR-22 Per-boundary drag honesty <span class='srs-implemented'>implemented</span>"
    *Origin: PP-5. Evidence: the v0.3 line, corrected by PLN-075 after
    a re-reading of the manual page; the vorticity selection of
    `solver_settings` with its two drag methods documented and
    snapshotted (SRC-003 p.202).*

    Per-boundary drag bookkeeping respects the documented vorticity
    CDi pitfall: a boundary without a user-defined trailing-edge
    condition reports zero induced drag once it is assigned to the
    vorticity CDi list. The API does not aggregate blindly, the
    vorticity selection is an explicit input of the solver settings,
    and leaving it unset is the documented solver default (surface
    pressure integration on every boundary), recorded as such in the
    solver-setup snapshot rather than refused. On a FlightStream
    version where the selection command has no recorded evidence, the
    snapshot states unknown instead of claiming the default.

## FSI

!!! requirement "FR-23 FSI seam at v0.1 <span class='srs-deprecated'>deprecated</span>"
    *Origin: BRF-11. Superseded by FR-23a; kept as the accurate v0.1
    record.*

    At v0.1 the package exposed only the coupling seam: the FSI
    command family in the database and a structural-solver protocol
    stub. No structural solver shipped.

!!! requirement "FR-23a In-package FSI subpackage <span class='srs-implemented'>implemented</span>"
    *Origin: amendment of 2026-07-21. Evidence: milestone M6; the
    coupled near-rigid pilot report and the frozen replay.*

    From M6 the structural coupling tool is the `fsi` subpackage:
    config schema, loads parser, beam builder, centrifugal terms,
    kinematics, node generation, coupling driver, and the `pyfs-fsi`
    entry point. The structural dependency enters only as the
    optional `[fsi]` extra, never vendored, with committed license
    evidence.

## Quality assurance

!!! requirement "FR-24 CI-runnable test suite <span class='srs-implemented'>implemented</span>"
    *Origin: PP-9. Evidence: the Tier 1 suite in CI on every push.*

    A CI-runnable suite covers database integrity, emission
    validation including removed and renamed command scenarios,
    parser fixtures, golden scripts, and matrix reader equivalence.
    FlightStream itself is never required in CI.

!!! requirement "FR-25 Probe harness <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03. Evidence: milestone M3; the committed compat
    reports and the promotion mechanism.*

    A probe harness runs per-command probe scripts on a licensed
    machine, asserts real effects, and promotes results into database
    statuses through committed compatibility reports.

!!! requirement "FR-26 Physics regression matrix <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-12, BRF-17. Evidence: milestones M4 onward; the
    banded-reference reports. Expansion (mesh refinement, solver-flag
    cases) queued for licensed sessions.*

    A physics regression matrix on synthetic geometry guards physical
    sanity per release with WARN and FAIL tolerance bands; reference
    updates demand a stated reason.

!!! requirement "FR-27 Two geometry classes for drift <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-17. Evidence: milestone M4; the drift suite and its
    committed reports.*

    Version-comparison cases come in two classes: synthetic
    geometries, committable and generated by the suite; and local
    research cases whose geometry never enters the repository, with
    only aggregated coefficients in the committed reports.

## File management

!!! requirement "FR-28 The package owns the layout <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-15, BRF-14. Evidence: milestone M2; extended by
    FR-33.*

    The package creates and names per-campaign and per-simulation
    folder trees itself, standardized English names derived from
    `sim_id` and the manifest. No user hand-builds a run folder.

!!! requirement "FR-29 Staging, hashing, archiving <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-15, PP-6, PP-7. Evidence: milestone M2; archive
    refusal tests.*

    The package stages inputs into the run folder, records their
    hashes in the manifest, collects outputs to declared locations,
    and provides archive and cleanup operations that refuse to touch
    folders whose manifest is missing or inconsistent.

## Usage-feedback requirements (2026-07-22)

Requirements added from the author's first outside-the-repo use of
the public 0.2.0, through the five-stage triage process recorded in
the session records.

!!! requirement "FR-30 Entity labels <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback. Evidence: the v0.3 line; registry tests.
    The fsm-to-obj boundary inspector is
    <span class='srs-deferred'>deferred</span> behind a licensed
    probe (does the OBJ export write one named group per boundary?).*

    FlightStream is index-parameterized; pyflightstream identifies
    entities by label. The builder registry tracks frames, actuators,
    motions, and boundaries with optional labels; every entity-citing
    argument accepts index or label; declared boundary inventories
    are range-checked; undeclared stays permissive because the total
    lives in the geometry file.

!!! requirement "FR-31 Solver-setup provenance <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback. Evidence: the v0.3 line; snapshot
    round-trip tests. Evidence for the remaining unknown defaults is
    <span class='srs-deferred'>deferred</span> to the licensed queue.*

    The solver settings helper is the single entry point for every
    solver flag and returns a snapshot recording each flag's
    effective value with provenance: explicit, evidence-cited
    default, or unknown (never guessed). The snapshot rides the
    manifest, and a script can be regenerated from it.

!!! requirement "FR-32 Tabular results <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback. Evidence: the v0.3 line; table tests on
    the sanitized fixtures.*

    Every parser result converts to a tidy DataFrame and to csv; a
    run merges into one wide row (identity, conditions, coefficients,
    with identity cross-checks); a whole sweep assembles from the
    manifest alone.

!!! requirement "FR-33 Input-artifact library and naming templates <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-20. Evidence: the v0.3 line; artifact and
    no-parse-back tests.*

    The workspace organizes inputs: declarative TOML artifacts
    (references, setups, groups, geometries, profiles, executables by
    build id) resolved by stable id with didactic misses. Output
    naming is templatable and output-only: the manifest stays the
    sole identity authority and no parse-back API exists.

!!! requirement "FR-34 Pre-flight and resume <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback. Evidence: the v0.3 line; pre-flight and
    resume tests.*

    A campaign can be pre-flighted with zero solver time (recipes
    resolved, scripts dry-run built, folders allocated, geometry
    verified, plan written) and re-run with resume semantics that
    skip manifest-recorded points, enabling incremental sweeps.

!!! requirement "FR-35 Matrix as first-class interface <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback, amending the posture of FR-10/FR-11.
    Evidence: the v0.3 line; resolution hit and miss tests.*

    The run matrix is a first-class interface of the file-managed
    modality: its reference columns resolve against the workspace
    input library, and one call takes a matrix through conversion,
    pre-flight, and execution. The native campaign format remains
    the canonical internal form.

!!! requirement "FR-36 Two-level help <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback. Evidence: the v0.3 line; overview and
    coverage tests.*

    Help has two zoom levels: the command reference (with a
    manual-coverage section stating what the database does and does
    not yet cover) and the architecture overview generated from the
    live module docstrings. Both render offline and in the docs from
    single sources.
