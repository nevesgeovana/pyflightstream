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
    argument differences, and exactly one evidence citation: a manual
    page, or a committed probe report for a command the solver accepts
    and no manual edition documents.

    A page citation is RE-READABLE against the edition it names, and a
    tool re-reads it (`pyfs-manual citations`). Amended 2026-08-10: a
    citation was written once from a reading and nothing looked at it
    again, so when the 25.000 manual's pagination moved under ten rows
    they went on naming real pages of a real manual and no guard could
    see it. The requirement is now that the claim be checkable, not only
    that it be present. Read its reach with it: the check reports how
    many rows it could re-read at all. Two reasons put a row out of
    reach and they are not the same: a row citing no page of its own
    cannot be checked, and a `removed` row's citation addresses an
    ABSENCE, so re-reading it would report every honest removal record
    as a defect. 26.120 shows both at once and is the build worth
    knowing about: none of its 381 rows is read, 363 of them because
    they rest on the entry's own citation and the other 18 because they
    are removals. Attributing all 381 to the first reason is the swap
    the code comment beside the counter warns about.

!!! requirement "FR-02 Launch version set and ordering <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-07, BRF-19. Evidence: milestone M1; `versions` tests.*

    The database covers versions 26.0, 26.1, and 26.12 at launch,
    with an explicit ordered version list. Version ordering never
    relies on string or float comparison ("26.1" < "26.12" fails
    both).

!!! requirement "FR-02a Canonical YY.XXX identifiers <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-19. Evidence: milestone M1; amended 2026-08-09 when the
    25 series was registered.*

    The canonical version identifier is `YY.XXX`: the vendor's two-digit
    major, then exactly three fractional digits of which the first two
    carry the official minor release and the last indexes builds within
    it (0 = the release the vendor named). The last digit is an ORDERING
    position and not a claim of descent, which is why whether a build
    carries its base release's command evidence is stated per build
    rather than derived from it.
    Launch set: 26.000, 26.100, 26.120. The registry stores
    the vendor release name of each build as a display alias, and a
    user may write that name wherever it names exactly one build.

    Amendment of 2026-08-09: the major was written `26` here while 26
    was the only registered major. Registering the 25 series made it a
    variable, which is what the scheme always meant; nothing about the
    three fractional digits changed and no identifier was reassigned.
    Registering an EARLIER series is admitted by the append-only rule
    (BRF-19 forbids dropping a version, not inserting one), and the
    ordered list places it by release order, so the 25 builds sit at the
    front rather than at the end.

!!! requirement "FR-02c Ambiguous vendor names are refused <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03, BRF-19. Evidence: PFS-8 (2026-08-02); the
    ambiguous-alias tests in `tests/test_versions.py`.*

    The vendor reuses a release name across builds, so a display alias
    can name more than one registered build. Resolution refuses such a
    name rather than returning any of the builds carrying it, and the
    refusal names every candidate so the caller can choose. The
    candidates are not enumerated in this requirement: two families
    exist and they exist for different reasons, one release with its
    hotfixes sharing a name and two separate releases that happen to
    share one, and which builds sit in either is a fact about the
    registry rather than about this requirement. A canonical identifier
    is matched across the whole registry before any alias is considered,
    so a build is never shadowed by an earlier entry whose alias equals
    its canonical.

    THE ENUMERATION WAS REMOVED on 2026-08-18, the author's decision,
    and it is a correction rather than a simplification. This requirement
    used to list the members and the list went stale twice by
    construction, once per registration; the same enumeration was removed
    from six other committed homes on 2026-08-17 for the same reason,
    which left the requirement text as the last stale copy. The refusal
    itself enumerates from the registry, so the message a caller reads is
    correct on the day they read it, and the generated build page carries
    the tally.

    THE PARAGRAPH BREAK MATTERS HERE, which is not obvious and cost a
    published sentence for one commit. `scripts/gen_requirements_index.py`
    publishes a requirement's FIRST paragraph as its statement, so the
    first version of this rewrite, which opened a second paragraph before
    the shadowing sentence, silently dropped that sentence from
    `reports/requirements-index.json` with the whole suite green. Anything
    NORMATIVE belongs above the first blank line.

    This makes the vendor name a breaking input wherever it became
    ambiguous, which is accepted: the alternative is returning a
    solver build the caller did not choose.

    The refusal has a run-time counterpart, and needs one. Refusing at
    build time only settles which build the run ASKED for; it cannot
    show which one actually ran, and the version string the solver
    prints does not either, because every registered 26.1x prints
    "26.1". So the registry records each version's vendor build number,
    from a committed report and never guessed, and results parsing
    compares it against the build printed in the output, warning when
    they differ. Where a version has no registered build and shares its
    vendor name, the parse says so rather than reporting agreement it
    cannot establish.

!!! requirement "FR-03 Evidence-backed per-version statuses <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03. Evidence: milestone M1 (schema), M3 (first
    promotions); committed compat reports.*

    Each command carries a per-version status: `documented`,
    `verified`, `broken`, or `removed`. Documented and verified are
    distinct because the manual and the solver disagree in practice.
    Statuses that rest on a run are promoted only by committed probe reports.

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
    registry view, so two scripts build concurrently without
    interference. This is the script-construction consequence of
    [AD-03](architecture-srs.md), which is the single home of the
    no-global-mutable-state rule.

!!! requirement "FR-06 Curated helpers <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-04. Evidence: milestone M2; helper goldens
    ([glossary](index.md#glossary)).*

    A curated set of thin helpers covers the common steady and
    unsteady workflows, and each helper emits only database-validated
    commands, adding no emitted line the command database does not
    define.

    Reworded 2026-07-27: "adds no hidden logic" stated an intention no
    test could fail. What replaces it is the same promise as a property
    of the emitted script, which a golden can check.

!!! requirement "FR-07 Recorded escape hatch <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-12. Evidence: milestone M2; the manifest raw flag.*

    A raw-emission escape hatch allows arbitrary lines, and its use
    is recorded in the run manifest, so no run silently depends on
    unvalidated commands.

!!! requirement "FR-08 Clean-room emitter <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-10. Evidence: the `Clean-room` commit trailer,
    asserted for every commit under review by
    `tests/test_clean_room.py`; repository invariant; contribution
    policy.*

    The emitter layer is specified exclusively from the official
    manual and from probe evidence, and its clean-room provenance is
    declared per change in a `Clean-room` commit trailer, which a Tier 1
    test asserts for every commit a push makes new. No code, structure,
    or docstrings derive from the AGPL ecosystem predecessor.

    Reworded 2026-07-27 to name its verification honestly. No test can
    observe how a line of code came to be written, so a requirement that
    implied one was promising evidence that does not exist; the
    attestation is the evidence that does.

    THE MECHANISM NOW EXISTS, which it did not when that rewording was
    made. Measured 2026-07-28 (review finding PYFS-021): 200 commits, 0
    `Signed-off-by` trailers, no per-change attestation of any kind, so
    the evidence line named an artifact that had never been in this
    repository. The author chose on 2026-08-03 to make it exist rather
    than to reword the requirement to promise less.

    What it proves, and the limit is the point rather than a caveat.
    Nothing can prove the absolute negative "the predecessor was never
    read". What a process CAN preserve is a declaration and an auditable
    record of who made it: the trailer is the declaration, the commit's
    author and date are the record, and the test makes the declaration
    unskippable for work under review. The repository's own push gate is
    deliberately NOT cited here: it records that a review happened and
    says so about itself, and it is silent on provenance, so pointing
    this requirement at it would be a second overclaim narrower than the
    first.

    The check starts at a baseline commit and is not retroactive. The
    200 commits before it carry no trailer, and adding one to them would
    mean rewriting history to manufacture a declaration nobody made.

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
    and executable path per [AD-04](architecture-srs.md), which is the
    single home of the explicit-never-guessed rule.

!!! requirement "FR-10 Run-matrix reader, forever <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-08. Evidence: milestone M2; the verified 16-column
    layout and its fixtures, including
    `tests/fixtures/workflow_rotor_matrix.fs`. The layout gained its
    sixteenth column on 2026-08-19; a fifteen-column file is recognised
    and refused rather than misread, which is what keeps this
    requirement's forever promise honest.*

    A dedicated reader consumes the documented pipe-delimited
    run-matrix format: rows with RUN = 1 are active, the sweep columns
    define alpha, beta, or advance-ratio sweeps, and the variables
    column holds KEY:VALUE pairs. A column the reader does not
    recognize is preserved and reported rather than silently dropped.

    Reworded 2026-07-27. "Forever" is scoped to the EXTERNAL format,
    which is the promise that matters to the author's existing files,
    rather than reading as a promise never to change the reader. The
    unknown-column clause is new and closes a silent-loss path the
    original left unstated.

!!! requirement "FR-11 Lossless one-command conversion <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-08, BRF-16. Evidence: milestone M2; TOML round-trip
    tests ([glossary](index.md#glossary)); the `pyfs-matrix convert`
    CLI (v0.3 line).*

    A convert command turns a run matrix into the native campaign
    format in one optional invocation, and a reverse conversion
    reproduces every field of the original matrix, verified by a
    round-trip ([glossary](index.md#glossary)) test. The matrix POL
    column maps to the native `sim_id`; the matrix reference codes are
    preserved verbatim.

    Reworded 2026-07-27: "lossless" named a property without saying how
    anyone would know. The reverse conversion is what makes it
    checkable, and it is the same claim stated as a test.

    A WIDER FORM OF THIS SENTENCE WAS WRITTEN ON 2026-08-19 AND
    WITHDRAWN THE SAME DAY, and it is recorded rather than reverted in
    silence because the question it was answering is still open. It said
    POL identifies the sims a row GENERATES, "exactly one for a row that
    is not fanned", against the possibility that a rotation sweep turns
    one row into one sim per blade position. A review pass measured the
    tree: `cases.matrix` writes `sim_id=row.pol` one to one, a sweep's
    values become POINTS inside that one sim, and the word "fanned"
    appeared nowhere else in the repository. So the sentence described
    behaviour the package does not have, in a term it defined nowhere,
    which sends an engineer looking for a switch that is not there.

    The one-to-one form above is what the code does today and is what
    binds. The question returns if the matrix half of PFS-2025.14 lands:
    the emitter that rotates about a named point exists, and the matrix
    column that would sweep it does not.

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
    uses `shell=True` ([glossary](index.md#glossary)).

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

    The result-array API provides labeled multidimensional arrays,
    interpolation along named axes, axis re-parameterization, and trim
    extraction by interpolating a moment coefficient to zero.

    De-narrated 2026-07-27: the requirement states the capability, and
    how much of it exists today belongs to the status tag and the
    roadmap, which is where a reader looks for progress. What was
    narrated here and is not lost: sweep assembly landed as FR-32, field
    data as the far-field ledgers of FR-38, and interpolation and trim
    are the open half, which AD-06 sends to the sister library.

!!! requirement "FR-21 Established plot-file writers <span class='srs-pending'>pending</span>"
    *Origin: BRF-01.*

    Plot files byte-compatible with the author's established plot
    format, with a reader making the pair round-trip testable. Not
    yet started; VTK and Tecplot probe-data writers exist in `post/`
    but that plot format is not among them.

    Probe field data is a separate matter and already ships: the VTK
    legacy and Tecplot point writers of `post/writers.py` export it
    with a documented field-to-column mapping
    (`tests/test_post_writers.py`). Recorded here rather than under an
    identifier of its own because that is where the author folded it
    when she accepted it, against the option of making it a public
    functional requirement.

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
    sanity per release. Each guarded coefficient is compared against a
    committed reference with a per-coefficient error metric, absolute
    for coefficients that pass through zero and relative otherwise, and
    with WARN and FAIL band values derived from measured run-to-run
    repeatability rather than chosen. A reference update states its
    reason.

    Reworded 2026-07-27 to say which metric, which basis, and that the
    bands are measured. The band VALUES stay in the committed reference
    files rather than being copied here, because they are per case and
    per coefficient and this requirement would go stale the first time
    one moved.

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
    manifest, and a script can be regenerated from it. The set of
    physics-material flags carried as unknown is confirmed complete per
    supported version, and the confirmation is recorded in that
    version's compatibility report.

    The completeness clause was accepted 2026-07-27 and is the half
    that needs licensed evidence: an unknown flag nobody has enumerated
    is indistinguishable from one that does not exist. Split into FR-31a
    and FR-31b for the two claims a test can falsify separately.

!!! requirement "FR-32 Tabular results <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback. Evidence: the v0.3 line; table tests on
    the sanitized fixtures.*

    Every parser result converts to a tidy table
    ([glossary](index.md#glossary)) and to csv; a run merges into one
    wide row (identity, conditions, coefficients, with identity
    cross-checks); a whole sweep assembles from the manifest alone.

    The tidy table is a pandas DataFrame today and stops being one at
    v0.5.0 ([AD-06](architecture-srs.md) is the decision;
    [NFR-06](nonfunctional-requirements.md) is the home of the release
    number). The shape is the
    requirement, not the library holding it, and the column schema that
    survives the change is [NFR-19](nonfunctional-requirements.md).

!!! requirement "FR-33 Input-artifact library and naming templates <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-20. Evidence: the v0.3 line; artifact and
    no-parse-back tests.*

    The workspace organizes inputs: declarative TOML artifacts
    (references, setups, groups, geometries, profiles, executables by
    build id) resolved by stable id with didactic misses. Output
    naming is templatable and output-only: the manifest stays the
    sole identity authority and no parse-back API exists. A case whose
    sweep points would render the same output name is blocked before
    it runs, because every point of a case executes in one simulation
    folder and a shared name destroys the evidence of all but the last
    (incident INC-20260723-2113).

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

## Phase 5 consolidation (2026-07-27)

The requirements below complete the author's Phase 4 acceptance batch.
Three groups: the singular claims split out of an existing requirement,
which keep their base's identifier plus a letter; the identifiers the
batch created; and the identifiers this session allocated for
acceptances that arrived without one. The
[mapping register](../requirement-mapping.md) records which accepted
item became which identifier, so the check that produced this section is
re-runnable.

### Splits

A split does not change what the base requires. It gives each claim
inside it an identifier that a single test can falsify, which is what
the base could not offer while it bundled several.

!!! requirement "FR-02b Version ordering authority <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-02, accepted 2026-07-27. Evidence:
    milestone M1; `tests/test_versions.py`.*

    Version ordering never relies on string or float comparison, and
    the ordered list in `commands/_meta.yaml` is the sole ordering
    authority, so that 26.100 sorts before 26.120.

!!! requirement "FR-22a Not-computed induced-drag sentinel <span class='srs-deferred'>deferred</span>"
    *Origin: Phase 4 split of FR-22, accepted 2026-07-27.*

    A boundary without a user-defined trailing-edge condition, once
    assigned to the vorticity induced-drag list, returns a not-computed
    sentinel distinguishable from a physical zero.

    Deferred, not implemented, and the correction is worth stating
    because the first draft of this box claimed otherwise. Parsed
    coefficients are plain floats today, so a solver-reported zero and
    a not-computed value are the same bytes; the distinction this
    requirement asks for does not exist in the code. Its own acceptance
    also gated the sentinel VALUE on the FR-22 probe promotion, which
    the same batch deferred for lack of licensed evidence, so promoting
    it here would have run ahead of the evidence it depends on.

!!! requirement "FR-22b Vorticity selection is an explicit input <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-22, accepted 2026-07-27. Evidence: the
    v0.3 line; solver-setup snapshot tests.*

    The vorticity induced-drag selection is an explicit solver-settings
    input, and leaving it unset is recorded in the solver-setup snapshot
    as the documented default, which is surface-pressure integration on
    every boundary.

!!! requirement "FR-22c Unknown rather than assumed default <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-22, accepted 2026-07-27. Evidence: the
    v0.3 line; solver-setup snapshot tests.*

    On a FlightStream version with no recorded evidence for the
    selection command, the snapshot states unknown rather than the
    default.

!!! requirement "FR-30a Entities carry labels, not positions <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-30, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/test_script_entities.py`.*

    The builder registry identifies frames, actuators, motions, and
    boundaries by optional label rather than by the solver's positional
    index.

!!! requirement "FR-30b Index or label, everywhere <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-30, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/test_script_entities.py`.*

    Every entity-citing argument accepts either an index or a label.

!!! requirement "FR-30c Declared inventories are range-checked <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-30, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/test_script_entities.py`.*

    A declared boundary inventory is range-checked, and an undeclared
    inventory stays permissive, because the total lives in the geometry
    file rather than in the script.

!!! requirement "FR-31a Solver settings are one entry point with provenance <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-31, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/test_solver_setup.py`.*

    The solver-settings helper is the single entry point for every
    solver flag and returns a snapshot recording each flag's effective
    value with its provenance: explicit, evidence-cited default, or
    unknown, never guessed.

!!! requirement "FR-31b The snapshot rides the manifest <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-31, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/test_solver_setup.py`.*

    The snapshot rides the manifest, and a runnable script is
    regenerated from it.

!!! requirement "FR-31c The unknown set is confirmed complete <span class='srs-deferred'>deferred</span>"
    *Origin: the FR-31 flag-completeness acceptance, 2026-07-27,
    allocated its own identifier here.*

    The set of physics-material flags carried as unknown in the
    solver-setup snapshot is confirmed complete per supported version,
    and the confirmation is recorded in that version's compatibility
    report.

    It has its own identifier because it is the half that needs
    licensed evidence, and leaving it inside a box badged implemented
    is exactly what splitting a requirement is for: an unknown flag
    nobody has enumerated is indistinguishable from one that does not
    exist.

!!! requirement "FR-33a Input-artifact library <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-33, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/test_workspace.py`.*

    The workspace organizes declarative TOML input artifacts
    (references, setups, groups, geometries, profiles, and executables
    by build id) resolved by stable id, with a didactic message when an
    id misses.

!!! requirement "FR-33b Naming is output-only <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-33, accepted 2026-07-27. Evidence: the
    v0.3 line; the no-parse-back guard in `tests/test_workspace.py`.*

    Output naming is templatable and output-only; the manifest is the
    sole identity authority and no parse-back API exists.

!!! requirement "FR-33c Colliding output names are blocked before the run <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-33, accepted 2026-07-27, giving the
    incident guard its own identifier. Widened 2026-08-19
    (OPS-2005.10.03, PFS-2011.02), the author's decision. Evidence:
    incident INC-20260723-2113; `tests/test_run_campaign.py`;
    `tests/test_silent_overwrites.py`.*

    A write that would destroy a record without saying so is refused
    before it happens, and there are three shapes of it. A case whose
    sweep points would render the same output name is blocked before it
    runs, because every point of the case executes in one simulation
    folder. A writer handed a destination that already exists refuses
    rather than replacing it, and `overwrite=True` is the only way
    through. A run folder that already holds a previous run's history
    with no state beside it is refused rather than appended to.

    The three were one requirement's worth of behaviour written as one,
    because they are one class: a record destroyed while the record says
    nothing happened. THE SIGNAL DIFFERS PER SHAPE and the requirement
    says so rather than implying a single mechanism: a file write can
    ask whether the destination exists, a command that asks the SOLVER
    to write cannot, and a log that appends by design is identified by
    the pair it forms with the state file beside it.

    Widened because the code made all three refusals while this sentence
    described one, which reads as the package refusing less than it
    does.

### New identifiers from the batch

!!! requirement "FR-37 Convergence status <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27. Resolved by the author
    2026-08-03. Evidence: `RunStatus.COMPLETED_MAX_ITER` and
    `RunStatus.FAILED_INCOMPLETE_OUTPUT` in `pyflightstream.workspace`, the
    judgment rules of `run.LoadsAssessor`, and the status tests in
    `tests/test_run_campaign.py`.*

    A datapoint whose recorded residual does not reach the configured
    convergence threshold terminates with a status distinct from the
    CONVERGED status, even when the output footer is structurally
    complete.

    **Restated 2026-08-03, and the restatement is the requirement.** It
    read "distinct from a completed one" until the review pass measured
    that the delivered value is `COMPLETED_MAX_ITER`, whose name says
    completed, so the requirement was being closed under a reading
    rather than as written. The author's decision was to keep the six
    statuses; the honest consequence is that the requirement says what
    the library guarantees, which is that a run failing its threshold
    never wears the status that means it met it. The disclosed
    restatement is recorded in the
    [requirement mapping](../requirement-mapping.md), which is this
    project's own convention for exactly this.

    **Resolved by the author on 2026-08-03: the six values stand and
    this requirement closes as covered.** It was pending because it
    collided with FR-46, which closes the terminal-status set at the six
    values `RunStatus` carries: a run reaching the iteration cap without
    converging lands in `COMPLETED_MAX_ITER`, and adding the value this
    requirement originally implied would have made seven. Of the two
    acceptances, FR-46's set is the one that holds.

    What makes that defensible rather than convenient, and it is worth
    stating because the requirement's own wording pulls the other way.
    `COMPLETED_MAX_ITER` is not a success value in this package: the
    campaign loop, the manifest and the assessor all treat CONVERGED as
    the only converged outcome, and the name says the solver reached its
    iteration cap, which is precisely the condition the requirement is
    about. A run whose residual is non-finite is `FAILED_DIVERGED`
    rather than either, so the two ways of not converging are already
    distinguished.

    The residual is a naming one and is recorded rather than closed:
    `COMPLETED_MAX_ITER` reads as a completed status to someone meeting
    it for the first time. Renaming it is a manifest-visible break with
    no functional gain, so it is not done. The cost is that a reader
    must learn one name, and the assessor's docstring is where the
    package explains it.

    Two branches satisfy this requirement, not one, and saying so is
    the correction the closing analysis owed. A run that reaches the
    cap without converging is `COMPLETED_MAX_ITER`, as above. A run
    whose loop did not complete at all, because it forced every
    iteration and stopped early, is `FAILED_INCOMPLETE_OUTPUT`: the
    reasoning about the cap does not reach that case, and it does not
    need to, because that value is also distinct from a completed one.
    What the requirement asks for is the distinction, and both branches
    give it.

!!! requirement "FR-38 Far-field conservation ledgers <span class='srs-deferred'>deferred</span>"
    *Origin: Phase 4 review, accepted 2026-07-27, absorbing the C11
    acceptance of the same subject. Evidence for the delivered half:
    milestone M7; the G0 synthetic gate in `tests/test_farfield.py`.*

    The far-field subpackage computes the mass, momentum, swirl,
    crossflow-kinetic-energy, and rothalpy conservation ledgers on the
    survey lattice, evaluates gates G1, G3, and G4 and the near-field
    versus far-field spurious diagnostic, and records each ledger and
    gate outcome in the run outputs.

    Deferred rather than implemented because the ledgers and the G0
    synthetic gate ship while G1, G3, and G4 need licensed solver
    evidence that does not exist yet. Scope note: AD-06 moves the
    generic half of this machinery to the sister library, so what stays
    here is the FlightStream-side application and the lattice adapter.

!!! requirement "FR-39 Public exception hierarchy <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27, absorbing the C2
    catalog acceptance and the M1 typed-hierarchy mirror. Evidence:
    PFS-2 (2026-08-02); the sweep of 2026-08-03 and 2026-08-04, 137
    sites over three widenings of the walk;
    `src/pyflightstream/exceptions.py`;
    `tests/test_exceptions_catalog.py`, whose third guard walks every
    exported public name, and every module-private helper an exported
    one calls, for bare standard-library raises.*

    Every exception raised by the public API derives from a single
    documented base exception, each type is documented with the
    condition that raises it, and every exception and warning is
    re-exported from one catalog module, so that a class defined
    outside the catalog fails the suite.

    The base is `PyflightstreamError`. Each exception keeps the
    standard-library base it derived from before, as a second base, so
    the change is purely widening: `except ValueError` and
    `except RuntimeError` catch exactly what they used to, and
    `except PyflightstreamError` now catches the catalog. The CATALOG,
    not the package, and the difference is the residual this requirement
    discloses in bold below. THREE guards,
    not one: membership in the catalog, descent from the base, and the
    absence of a bare standard-library `raise` inside any exported
    public name, asserted separately, because a class can join `__all__`
    and still be invisible to a single except clause, and a function can
    raise past the catalog entirely.

    The third guard was added 2026-08-03 and it is what makes the first
    clause measurable. The two class-level guards inspect CLASSES and
    never a `raise` statement, so bare `ValueError`, `RuntimeError`,
    `TypeError` and `KeyError` raises stood in the public surface while
    this requirement read implemented. An independent review found three
    of them; walking the tree found seventy; widening the walk to the
    modules that declare no `__all__` found 46 more; widening it again
    to REACHABILITY, since a bare raise inside a module-private helper
    that a public function calls reaches the caller exactly as an
    exported one does, found 21 more.

    113 of those sites raised a catalogued class as measured at v0.4.0,
    a figure this requirement carries as the measurement of that date
    rather than as a running total, and nine classes
    were added for conditions that had no home: `MalformedOutputError`
    and `FieldNotInExportError` (results), `ProbeGeometryError`
    (probes), `CampaignConfigError` (cases), `FarfieldInputError` (far
    field), `QaEvidenceError` (QA evidence), `UnknownExtraError`
    (extras), `CommandDatabaseError` (the command database itself) and
    `FsiInputError` (the coupling). Every one keeps its
    standard-library base, so no handler in the wild caught less
    afterwards than before.

    **18 sites remain and this requirement does not claim them.** They
    are named one by one in a ratchet in
    `tests/test_exceptions_catalog.py`, so the residual is countable and
    any site THE WALK REACHES that is not on that list fails today:
    three raise `TypeError` for an argument of an unaccepted type, which
    needs a base class this catalogue does not have
    (`PLN-20260803-2340`), and 15 are the reachability tranche, deferred
    to v0.5 by the author on 2026-08-04 with the measurement taken first
    rather than the promise trimmed to fit (`PLN-20260804-0130`).

    The arithmetic, since this paragraph published a number that had
    stopped being true. The ratchet held 29 entries going into v0.5.0,
    not the 24 this requirement said: it grew by five over that
    development cycle and the sentence above it did not move, which is
    the drift NFR-11 exists to catch and which nothing mechanical
    catches here, the count living in a test comment the requirement
    merely describes. Eleven entries then closed, leaving 18. Of the
    eleven, six were debt carried from v0.4.0 and five were sites this
    cycle WROTE and exempted, which is a ratchet being used as a drawer
    and is the reason the growth is stated here rather than netted away.

    Eight of the eleven were the whole
    `commands._check_layout_rules` group, re-based onto the already
    catalogued `CommandDatabaseError`, which is `ValueError`-based, so
    pydantic's validation protocol is unaffected and a caller's
    `except ValueError` catches what it always did. The other three were
    the whole of `qa.compat._rewrite_version_line`: one turned out to
    report an evidence defect rather than a malformed line, and the two
    beside it refuse to promote a committed report's evidence, which is
    what the catalogued `QaEvidenceError` is for.

    That group also measured a WEAKNESS OF THE RATCHET ITSELF, which is
    recorded here rather than only in the test file, because it bounds
    what "countable" is worth. Entries are keyed by line number. Adding
    code above a debt site shifts every site below it, and the shifted
    set can OVERLAP the recorded one, so an entry keeps matching while
    silently naming a different raise. That happened to one of the eight
    at v0.5.0 and was caught only because the other seven failed loudly
    around it. Emptying the ratchet is the fix; re-keying it is not.

    The emphasis on what the walk reaches is a correction, not a
    flourish. This sentence read "any site not on that list fails today"
    and that was false when written: a definition omitted from its own
    module's `__all__` is invisible to the walk, and a review of
    2026-08-04 measured exactly two such definitions holding a bare
    raise out of nine omitted across the 52 public modules.
    `qa.physics.read_physics_report` was one and is fixed here, since
    the four sibling refusals in its only caller already raise
    `QaEvidenceError`. The other is `script.solver_setup.build_setup`,
    whose `RuntimeError` reports that the package's own flag table has
    fallen behind the command database; it is reachable only through a
    cross-module caller, and pricing the fourth widening against the
    eight escape shapes that review enumerated is v0.5 work
    (`PLN-20260804-0130`). The residual this requirement publishes is
    therefore the residual of a walk whose reach is stated, which is the
    honest form of the claim and the one a reader can check.

    The status stays `implemented` because
    the mechanism, the catalogue and the guard are delivered and the
    remainder is enumerated; a reader who needs the exact residual reads
    the ratchet, which is the only place it cannot go stale.

    The base parents the exceptions and not the one catalogued warning.
    The first clause of this requirement says exception, the third says
    exception and warning, and those are deliberately different sets: a
    warning is delivered through the warnings machinery and selected by
    category, and naming it an `Error` would mislead the reader of a
    traceback.

    The family names are this package's own (version, physics, IO,
    evidence). Only the pattern is borrowed from the sister library,
    which is what the M1 acceptance said in its own text.

!!! requirement "FR-40 Options and parameter registry <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review, accepted 2026-07-27, absorbing the C1
    acceptance of the same subject.*

    Every user-facing option or parameter is declared in a single
    registry recording its type, default, and validation rule, and the
    CLIs and the Python API resolve options through that registry;
    setting an unknown option, or a value outside its declared domain,
    raises an error naming the option and its allowed values. Every
    registered option name is a stable public contract, which is the
    form she chose against the review's recommended narrowing.

    Pending on its quantifier. The registry exists and its refusal
    behaviour is tested (`src/pyflightstream/options.py`,
    `tests/test_options.py`), but it holds three keys, all under `qa`,
    with one CLI consuming it and no Python-API parameter resolving
    through it. "Every" is the promise; a first consumer is what
    shipped.

!!! requirement "FR-41 ITACA adapter <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review, accepted 2026-07-27.*

    The package emits ITACA datasets from the manifest and the results
    schema, with a documented field mapping.

    Restated on the day it was written, because the draft accepted in
    this batch placed the adapter "behind the optional `[itaca]` extra"
    and a decision of the same batch removed that boundary: AD-07 makes
    the sister library a core dependency, so there is no extra to sit
    behind and no missing-extra hint to give. The capability is
    unchanged; only its packaging boundary is, and the requirement
    states the capability.

!!! requirement "FR-42 Reference-frame and sign conventions <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27. Evidence:
    `reference.CONVENTIONS`, rendered offline and on the docs site from
    one source; `tests/test_conventions.py`. The implemented status
    covers the STATING half: the conventions are published from one
    home and guarded there. That every emitted coefficient conforms to
    them is asserted by no test, and saying so here is the alternative
    to a badge that implies one.*

    *Amended 2026-08-19. The rotor half of this requirement was badged
    implemented while `CONVENTIONS` carried no rotor entry at all: the
    sign a reader was told is published was published nowhere, and a
    reviewer pass found it rather than a guard. The entry "Rotor signs
    are recorded, not derived" now states the split between the derived
    azimuth-increment sign and the measured rotor-speed sign, and names
    RPT-036 for what is still open. The badge did not move, because the
    STATING half is what it claims and that half is now true FOR THE
    ROTOR SIGN. The other two the requirement names are not in
    `CONVENTIONS`: the positive axis directions are stated per surface
    in the data model, and the moment reference point is stated on the
    artifact that carries it. Whether those belong in `CONVENTIONS` too
    is open, and this paragraph names them rather than letting the
    amendment imply the whole half moved.*

    The package states the reference-frame and sign conventions for
    reported forces, moments, and rotor quantities, naming the positive
    axis directions, the moment reference point, and the rotor-rotation
    sign, and every coefficient the results layer emits conforms to
    them.

### Identifiers allocated by this consolidation

The five below carry acceptances that arrived with no requirement id.
The allocation is recorded in the
[mapping register](../requirement-mapping.md).

!!! requirement "FR-43 Conservation imbalance acceptance band <span class='srs-deferred'>deferred</span>"
    *Origin: Phase 4 review, accepted 2026-07-27, recorded in the
    [mapping register](../requirement-mapping.md) as blocked by
    evidence. Written into this chapter 2026-08-02, on review finding
    PYFS-022: the identifier was allocated in the mapping and the
    requirement box was never transcribed, so an accepted item existed
    with no requirement anywhere.*

    A conservation ledger's imbalance is reported against a stated
    acceptance band, and a run whose imbalance leaves the band is
    reported as such rather than as a number the reader must judge.

    Deferred, and the band is deliberately unnamed here for the same
    reason NFR-16's floor was until it was measured: the sister library
    computes the imbalance and returns no acceptance criterion, because
    what counts as acceptable depends on the case, the mesh and the
    solver context, which live on this side. Setting the number is the
    numerical-analyst seat, which is not delegable, and it needs
    licensed solver evidence that does not exist yet.

    Read with FR-38, which delivers the ledgers this band would judge.

!!! requirement "FR-44 Console entry-point contract <span class='srs-pending'>pending</span>"
    *Origin: the C4 acceptance, 2026-07-27, in the FULL-contract form
    she chose against the review's own recommendation of a narrower
    one.*

    The package provides one documented console entry point per
    operational concern, and their commands and flags change only
    under the deprecation policy of NFR-20.

    Pending, and precisely: every entry point exists and is
    exercised, so the first half ships. The second half is the one she
    strengthened, and nothing enforces it. NFR-20 is itself pending and
    does not bind before 1.0, so today a CLI flag can change with only
    a changelog line behind it. An earlier draft of this box wrote that
    weaker form, which was the option she declined.

!!! requirement "FR-45 Strict manifest record <span class='srs-implemented'>implemented</span>"
    *Origin: the C5 acceptance, 2026-07-27. Evidence: both halves
    pinned in `tests/test_workspace.py`, the unknown-field refusal by a
    test added with this consolidation after review found the clause
    resting on a model-config line no assertion observed.*

    The manifest record rejects unknown fields and duplicate run
    identifiers; its field set is fixed and validated at construction.

!!! requirement "FR-46 Closed terminal-status set <span class='srs-implemented'>implemented</span>"
    *Origin: the C6 acceptance, 2026-07-27. Evidence: the member set
    of `RunStatus` pinned in `tests/test_workspace.py`, added with this
    consolidation; using the members, which the campaign tests do, does
    not notice an addition.*

    Every executed point terminates in exactly one value of a closed
    set of six status values, and a seventh cannot be introduced
    silently.

    Read with FR-37, which the author closed as covered by this set on 2026-08-03: this set stays closed at six and FR-37 was restated to ask for a status distinct from CONVERGED, which two of these six give.


!!! requirement "FR-47 Public test-support assertions <span class='srs-implemented'>implemented</span>"
    *Origin: the C8 acceptance, 2026-07-27. Evidence:
    `src/pyflightstream/testing.py`; `tests/test_testing.py`.*

    The package exposes public assertion helpers that compare records
    and scripts and report the quantified violation on failure, so a
    user can assert against this package's outputs in their own tests.

## Independent review remediation (2026-08-02)

!!! requirement "FR-48 Broken commands are refused, and waivers are recorded <span class='srs-implemented'>implemented</span>"
    *Origin: the independent review's finding PYFS-002, reproduced
    2026-07-28 and again at HEAD on 2026-08-02. Evidence:
    `Script.allow_broken` and the emission refusal in
    `src/pyflightstream/script/__init__.py`; `broken_commands` on
    `RunRecord`; the database-driven refusal guard and the waiver
    guards in `tests/test_script.py`,
    `tests/test_script_helpers.py` and `tests/test_run_campaign.py`.*

    Emitting a command whose per-version record is `broken` raises at
    build time. The refusal has one documented way through: a waiver
    naming the command and the caller's justification, which lets the
    command emit and records the command, TWO versions, the committed
    probe report and the justification in the script and in the run
    manifest. Two, because a hotfix build inherits its base release's
    record: `version` is the build the script targeted and
    `source_version` is the build whose record is broken, which is the
    build the cited report was run on. A record that carried one field
    for both would make an inherited waiver cite a report run on a
    version the manifest never names.

    Why this is not covered by FR-04, which refuses a command absent
    from the target version: an absent command produces no run at all,
    whereas a broken one produces a complete run with wrong numbers in
    it. `AIR_ALTITUDE` on 26.120 is the measured case, its METERS
    argument read as feet
    (`reports/compat/CMP-26120_2026-07-23_pln012.yaml`). Until this
    requirement landed, `broken` was the only status backed by a probe
    that watched the command fail and the only status the emitter did
    not act on.

    The waiver is registered on the script rather than passed per call,
    so it reaches the curated helper layer without every helper
    growing an argument for it, and a waiver for a command that is not
    broken in the target version is accepted and records nothing,
    because one recipe is meant to run against several versions.

!!! requirement "FR-49 Named per-version support levels <span class='srs-implemented'>implemented</span>"
    *Origin: the independent review's finding PYFS-019, reproduced
    2026-07-28 and again at HEAD on 2026-08-02. Evidence:
    `src/pyflightstream/support.py`; `tests/test_support.py`.*

    A registered version reports its support level as one of four named
    values, ascending: `registered` (ordered, no command carries
    evidence, nothing can be built), `documented` (commands drafted
    from the manual, none measured against a running solver),
    `verified` (probe evidence REACHABLE for this version, measured on
    it or carried from its base release by declared hotfix
    inheritance; amended 2026-08-10, the definition having said
    "measured on this version" while the derivation counted inherited
    evidence, which the paragraph below now depends on) and
    `operational` (verified, and the minimal end-to-end workflow builds
    for it). Every level is derived from the command database; none is
    declared.

    The level is reported by the public surface, at the top of the
    package, and the published claims agree with it by test rather than
    by care.

    `operational` is the level whose claim is checked by performing it:
    a documented minimal workflow from geometry to a loads file is
    built, in a tier 1 test, for every version reported at that level.
    That is what separates it from `verified`, where a version can
    carry probe evidence for a scattering of commands while a link of
    the chain is missing.

    Why the taxonomy is a requirement rather than a docs improvement:
    registering a version made every surface call it supported, and the
    distance between two versions wearing that one word was measured.
    On 2026-08-02, 26.000 was registered, was accepted by
    `Script(version="26.000")` and by a campaign, and carried evidence
    for zero of the database's commands, so nothing whatever could be
    built for it. That build's own manual was read on 2026-08-10 and it
    now derives `documented`, which is the mechanism working rather than
    the example expiring: the level moved because the evidence did, with
    nobody editing a claim. Read with FR-02: versions are only ever
    added, never dropped, so the registry accumulates entries whose
    evidence has not caught up, and this requirement is what keeps that
    honest as the list grows.

    THE LEVEL IS DERIVED FROM REACHABLE EVIDENCE, WHICH INCLUDES
    INHERITED EVIDENCE, and 26.122 is the first build to make that
    distinction matter. Amended 2026-08-10, and dated because the instance expired:
    between 2026-08-10 and 2026-08-11 it derived `operational` on
    records inherited from its base release 26.120, with no command
    probed on it at all; the first probe run on the build closed that
    gap and the rule stands for the next registered hotfix. That is what declaring a build a genuine hotfix
    means and the derivation is not weakened by it, but a reader taking
    `operational` as a statement about measurements made on THAT BUILD
    would be wrong. Anything presenting the level to a user states what
    it rests on where the two differ.
