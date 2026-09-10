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
    ambiguous-alias tests in `tests/tier1_offline/test_versions.py`.*

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

    Read with PFS-2031.13 at 0.13.0 (GOAL-012): the child script a helper parks for a SCRIPT action is written by the run before the solver starts, so a helper's promise about the run is kept by the run.

    A curated set of thin helpers covers the common steady and
    unsteady workflows, and each helper emits only database-validated
    commands, adding no emitted line the command database does not
    define.

    Reworded 2026-07-27: "adds no hidden logic" stated an intention no
    test could fail. What replaces it is the same promise as a property
    of the emitted script, which a golden can check.

!!! requirement "FR-07 Recorded escape hatch <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-12. Evidence: milestone M2; the manifest raw flag.*

    Read with PFS-2033.01, PFS-2033.02 and PFS-2033.03 at 0.14.0 (GOAL-013): a setup artifact states raw solver commands before a named phase, each through the emitter's own checks; the run record and the provenance carry the lines the script took, and one tier-3 row on a registered build proves the record.

    A raw-emission escape hatch allows arbitrary lines, and its use
    is recorded in the run manifest, so no run silently depends on
    unvalidated commands.

!!! requirement "FR-08 Clean-room emitter <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-10. Evidence: the `Clean-room` commit trailer,
    asserted for every commit under review by
    `tests/tier1_offline/test_clean_room.py`; repository invariant; contribution
    policy.*

    The emitter layer is specified exclusively from the official
    manual and from probe evidence, and its clean-room provenance is
    declared per change in a `Clean-room` commit trailer, or on a
    commit's behalf by a later commit's `Clean-room-for` trailer naming
    it, which a Tier 1 test asserts for every commit a push makes new.
    No code, structure, or docstrings derive from the AGPL ecosystem
    predecessor.

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

    A commit that missed its own trailer is covered by a later commit
    declaring on its behalf, in a `Clean-room-for` trailer naming it.
    Added 2026-08-24, because the remedy this requirement's guard had
    been printing since 2026-08-03 could not work: the assertion is a
    walk over every commit since the baseline, and a follow-up commit
    adds to that population without removing the commit that failed. The
    declaration is unchanged in what it claims and in what it is worth;
    only its author moves, and the follow-up is held to every rule a
    first-hand declaration is held to, including declaring for itself.

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
    *Origin: BRF-08. Evidence: milestone M2; the verified 15-column
    layout and its fixtures. The layout has broken twice and each older
    LAYOUT is recognised by its HEADER ROW, never by its width, and
    refused naming `pyfs-matrix upgrade` rather than misread, which is
    what keeps this requirement's forever promise honest. Width could
    not serve: two of the three layouts are fifteen columns wide. The
    fixtures carrying that claim are
    `tests/tier1_offline/fixtures/pfs202512_matrix15.fs` and
    `tests/tier1_offline/fixtures/pfs202701_matrix16.fs`.*

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

    AMENDED 2026-08-24, and the amendment is owed rather than optional.
    An independent review found this requirement carrying the word
    "forever" in its own title while the external format had broken
    twice with nothing here saying so. What "forever" means is now
    stated as a mechanism rather than as a promise:

    **No file this reader ever accepted is left unreadable, except
    where reading it would require inventing a run identity, and no file
    is silently misread.** The one exception arrived with the fourth
    break, is refused by name rather than guessed, and is described
    below. A matrix at a superseded width is recognised
    BY that width, told which release it predates, and refused naming
    `upgrade_matrix`, which converts it losslessly in content. That is
    the guarantee; it is not, and since 2026-07-27 has not claimed to
    be, a promise that the column list never changes.

    The two breaks: 0.8.0 added `WORKFLOW` (PFS-2025.01); 0.9.0 removed
    `RE` and `MACH` and replaced them with the mandatory
    `FLIGHT_CONDITION` cell (PFS-2027.01). The second is the larger one,
    because a row's flow condition is now stated rather than typed into
    two fixed columns, and which quantity the resolver solves for
    follows from which keys the row names.

    A THIRD BREAK SHIPPED AT 0.11.0 and travelled through the same
    mechanism: PFS-2029.04 drops `FS_SCRIPT` and PFS-2029.07.02 renames
    `ENTRY` to `PPROC` and moves the output cells out of the row, one
    layout and one `upgrade` for both.

    A FOURTH BREAK SHIPPED AT 0.15.0 and travelled through the same
    mechanism, carried by PFS-2035.14 and stated by FR-69, "A sweep is one
    variable of the flight condition, and the angles are always written":
    `SWEEP_TYPE` left the layout, because the flight-condition cell says
    which variable varies by carrying the word `sweep` on it. The verified
    layout is 13 columns and the 14-column one is frozen beside the three
    older ones, recognised by its header and refused naming the converter.

    One thing about this break is unlike the three before it, and it is
    NARROWER than this paragraph first said. It said the conversion of a
    PAIRED `AL/BE` sweep is one row per sideslip, so such a file's upgrade
    changes its ROW COUNT. What was measured instead: a paired code whose
    second axis holds ONE value is one swept variable written in two
    columns, and it folds with the same rows. Only a code whose two halves
    BOTH vary changes the row count, and that the converter REFUSES rather
    than doing, because each new row needs a POL of its own and a POL is
    run identity. So the upgrade is lossless in content AND row for row,
    or it stops and names the rows a person has to split.

!!! requirement "FR-11 Lossless one-command conversion <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-08, BRF-16. Evidence: milestone M2; TOML round-trip
    tests ([glossary](index.md#glossary)); the `pyfs-matrix convert`
    CLI (v0.3 line).*

    Read with PFS-2031.20 at 0.13.0 (GOAL-012): the conversion emits the matrix identity as `matrix_stem`, so the round trip through the campaign file stays lossless with the field named apart from the path the conversion read.

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

    Read with PFS-2033.02 at 0.14.0 (GOAL-013): the record gains `raw_commands`, the setup's raw lines the script carried, and `aliases`, the setup's boundary aliases the polar tables resolve by (her decision of 2026-09-09), both absent on older records and read as empty.

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

    THE FORMAT NOW HAS A REFERENCE, named 2026-09-02: the products the
    author's master's driver wrote from her recorded campaign, one polar
    file per boundary group carrying a parameter block, a point count, a
    column count and one row per point in body, stability and wind axes,
    plus per-point sectional-loads and unsteady-plots files of the same
    shape. Their location is machine-local
    (`GeoverseSetup/local/reference_runs.json`). PFS-2029.15.01 and
    PFS-2029.15.02 carry the writers; FR-52 is where they run, and
    FR-53's offline parity arm is what moves this requirement off
    pending.

    Probe field data is a separate matter and already ships: the VTK
    legacy and Tecplot point writers of `post/writers.py` export it
    with a documented field-to-column mapping
    (`tests/tier1_offline/test_post_writers.py`). Recorded here rather than under an
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

    Read with PFS-2031.02, PFS-2031.06 and PFS-2031.01 at 0.13.0 (GOAL-012): the suite is organized by tier, tier 1 plans and builds the tier-3 matrices without a solver, and the goal's checker is its own falsifiable command.

    A CI-runnable suite covers database integrity, emission
    validation including removed and renamed command scenarios,
    parser fixtures, golden scripts, and matrix reader equivalence.
    FlightStream itself is never required in CI.

!!! requirement "FR-25 Probe harness <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03. Evidence: milestone M3; the committed compat
    reports and the promotion mechanism.*

    Read with PFS-2031.08 and PFS-2031.09 at 0.13.0 (GOAL-012): the action re-read probe runs as a row of the tier-3 matrix and writes its verdict into the command database, and the pyfs-qa study decides where the probe harness lives beside the workspace; PFS-2031.17 carries her answer, pyfs-qa physics reading the workspace, and PFS-2031.18 the unsteady actions design the probe confirmed.

    A probe harness runs per-command probe scripts on a licensed
    machine, asserts real effects, and promotes results into database
    statuses through committed compatibility reports.

!!! requirement "FR-26 Physics regression matrix <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-12, BRF-17. Evidence: milestones M4 onward; the
    banded-reference reports. Expansion (mesh refinement, solver-flag
    cases) queued for licensed sessions.*

    Read with PFS-2031.05, PFS-2031.07 and PFS-2031.09 at 0.13.0 (GOAL-012): the four physics cases become rows of the tier-3 matrices judged against the same references from the campaign products, every synthetic row carries a physical verification, and the pyfs-qa study puts the command's future to the author.

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

    Read with PFS-2030.07 at 0.11.0: the comparison report of the
    author's recorded campaign uses the same per-coefficient shape, with
    the solver's measured repeatability as its band.

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

!!! requirement "FR-29a A staged geometry is a link, not a copy <span class='srs-pending'>pending</span>"
    *Origin: the author's run log of 2026-09-02, on finding a byte copy of
    every geometry under every point. Carried by PFS-2029.17. Evidence
    owed: the staging tests that node names.*

    Staging a geometry into a point's `inputs/` makes a directory
    junction on Windows and a symbolic link elsewhere rather than a copy;
    the manifest still records the opened path and its hash, so FR-29's
    promise about what ran is kept; a filesystem that refuses the link
    falls back to a copy and the record says so with the reason; and
    archive and cleanup treat the link as a link and never cross it.

    Measured 2026-09-02: `workspace/__init__.py:1272` stages with
    `shutil.copy2`, and the author's meshes are large enough that the
    workspace readme sends every saved simulation to cloud storage rather
    than to version control, so a copy per point is the cost she met. The
    estate's own incident stands behind the last clause: a scan that
    crossed sixteen junctions reported more duplicate bytes than the tree
    held.

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

    Read with PFS-2033.01 and PFS-2034.01 at 0.14.0 (GOAL-013): a setup artifact defines custom coordinate systems and raw solver commands, both consumed out of its settings, so the snapshot of solver flags stays what it was and the raw lines are recorded beside it rather than inside it.

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

    Read with PFS-2031.16 and PFS-2031.19 at 0.13.0 (GOAL-012): a product refused by design is a recorded skip in products.json, the other simulations' products are written, and pyfs-matrix post --strict makes such a skip exit 2.

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

    Read with PFS-2034.01, PFS-2034.02, PFS-2034.03, PFS-2034.04 and PFS-2034.05 at 0.14.0 (GOAL-013): the row turns the mesh (`ROTATE`, a list of records in the order written, one row per angle), the setup defines the frames the row cites, the refusals name the cell, and her seat run measures the rotated propeller on the solver.

    Read with PFS-2031.03, PFS-2031.04, PFS-2031.05, PFS-2031.06, PFS-2031.07, PFS-2031.12, PFS-2031.14 and PFS-2031.20 at 0.13.0 (GOAL-012): the tier-3 folder is a workspace, several matrices share it with their own plan, sweep and products under post/<matrix>/, every token the package defines is a row that plans offline and runs on the licensed machine, an executable override with no default version is refused naming the option, and the matrix identity of a campaign and a record is matrix_stem.

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
    milestone M1; `tests/tier1_offline/test_versions.py`.*

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

    Read with PFS-2030.03.03 at 0.11.0, which lets the selection be
    written as family names in a setup and resolved through the
    geometry's inventory, as the author's own scripts did.

!!! requirement "FR-22c Unknown rather than assumed default <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-22, accepted 2026-07-27. Evidence: the
    v0.3 line; solver-setup snapshot tests.*

    On a FlightStream version with no recorded evidence for the
    selection command, the snapshot states unknown rather than the
    default.

!!! requirement "FR-30a Entities carry labels, not positions <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-30, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/tier1_offline/test_script_entities.py`.*

    The builder registry identifies frames, actuators, motions, and
    boundaries by optional label rather than by the solver's positional
    index.

!!! requirement "FR-30b Index or label, everywhere <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-30, accepted 2026-07-27. Taken off
    implemented and put back the same day, 2026-09-02 (PFS-2028.00): the
    claim was true at the script layer and false at the surface a user
    writes, because nothing declared a boundary inventory there. Evidence:
    the v0.3 line; `tests/tier1_offline/test_script_entities.py` for the script layer;
    `tests/tier1_offline/test_workflows.py`, whose rotor-row tests fail on 0.10.0 because
    the inventory is never declared, for a MATRIX ROW built by hand;
    `tests/tier1_offline/test_tier3_offline.py`
    (`test_a_rotor_row_cites_its_moving_boundaries_by_name_at_the_matrix_surface`)
    for a matrix row planned against a STAGED geometry and its inventory
    sidecar, where `MOVING_BOUNDARIES: Blade1,S` is refused as the
    inventory says and `Blade1` and `3` both move the third boundary
    (2026-09-09, PFS-2028.00); and
    `tests/tier1_offline/test_workspace.py` for a named boundary group, whose members
    may now be written as names.*

    Every entity-citing argument accepts either an index or a label.

!!! requirement "FR-30c Declared inventories are range-checked <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-30, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/tier1_offline/test_script_entities.py`.*

    A declared boundary inventory is range-checked, and an undeclared
    inventory stays permissive, because the total lives in the geometry
    file rather than in the script.

    Read with PFS-2005.04.01, "boundary aliases live in the setup and
    are read wherever a boundary is cited", at 0.14.0 (GOAL-013), her
    decision of 2026-09-09: a boundary cited by a row may be a name the
    row's setup defines under `[aliases]`, standing for the boundary
    names or families listed after it and resolved against the same
    declared inventory. A member the inventory lacks is left out rather
    than refused, so one preset serves a wing-body and a rotor; an alias
    no member of which the inventory carries resolves to nothing and is
    refused as an absent name, naming the alias.

    Amended 2026-09-10, carried by PFS-2035.01, pending until it ships:
    the `[aliases]` table moves to the REFERENCE artifact (FR-59, "The
    reference holds the vocabulary of a study's boundaries"), a member may
    be another alias, and a cycle is refused naming both sides. The rule
    above that a member the inventory lacks is left out survives the move
    unchanged. THE RULE THAT DOES NOT SURVIVE UNSTATED is the one in the
    sentence before this paragraph: whether an alias none of whose members
    the inventory carries is still refused as an absent name is what
    PFS-2035.13 asks, and it is the author's, so FR-59 is deliberately
    silent on it rather than quietly reversing it.

    Amended 2026-09-02, carried by PFS-2029.12, pending until it ships:
    an inventory that could not be declared says why. When a row cites a
    label and the opened geometry carries no mesh block, the refusal
    names the file and says it carries no mesh block; when an inventory
    was declared and lacks the label, the refusal names the inventory it
    read. Measured 2026-09-02: `_fsm.py` returns None in silence at
    `:160-168` when the file cannot be opened and at `:171-174` when it
    carries no `$MESH_START$` marker, and the user then meets a message
    that blames their row.

!!! requirement "FR-31a Solver settings are one entry point with provenance <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-31, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/tier1_offline/test_solver_setup.py`.*

    The solver-settings helper is the single entry point for every
    solver flag and returns a snapshot recording each flag's effective
    value with its provenance: explicit, evidence-cited default, or
    unknown, never guessed.

!!! requirement "FR-31b The snapshot rides the manifest <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-31, accepted 2026-07-27. Evidence: the
    v0.3 line; `tests/tier1_offline/test_solver_setup.py`.*

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
    v0.3 line; `tests/tier1_offline/test_workspace.py`.*

    Read with PFS-2031.03 and PFS-2031.15 at 0.13.0 (GOAL-012): the tier-3 library holds synthetic geometries only, each with a mesh block and a boundary sidecar, and a gitignored `inputs/executables.local.toml` supplies this machine's paths over the committed registry's placeholders.

    The workspace organizes declarative TOML input artifacts
    (references, setups, groups, geometries, profiles, and executables
    by build id) resolved by stable id, with a didactic message when an
    id misses.

    Amended 2026-09-02 by FR-52 and FR-55, both pending: the `group` kind
    becomes `pproc` and a geometry resolves by file name with its
    extension rather than by bare stem. Until they ship this sentence
    describes the 0.10.1 library; the amendment is recorded here so the
    two requirements and this one are read together.

!!! requirement "FR-33b Naming is output-only <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-33, accepted 2026-07-27. Evidence: the
    v0.3 line; the no-parse-back guard in `tests/tier1_offline/test_workspace.py`.*

    Output naming is templatable and output-only; the manifest is the
    sole identity authority and no parse-back API exists.

    Read with PFS-2029.19.01 at 0.11.0: the default template becomes the
    author's own convention, carrying the polar, the Mach, the angles
    and the advance ratio, and the record names the template that
    rendered each name.

!!! requirement "FR-33c Colliding output names are blocked before the run <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-33, accepted 2026-07-27, giving the
    incident guard its own identifier. Widened 2026-08-19
    (OPS-2005.10.03, PFS-2011.02), the author's decision. Evidence:
    incident INC-20260723-2113; `tests/tier1_offline/test_run_campaign.py`;
    `tests/tier1_offline/test_silent_overwrites.py`.*

    A write that would destroy a record without saying so is refused
    before it happens, and this requirement carries three shapes of it. A
    case whose sweep points would render the same output name is blocked
    before it runs, because every point of the case executes in one
    simulation folder. A writer handed a destination that already exists
    refuses rather than replacing it, and `overwrite=True` is the only
    way through. A run folder that already holds a previous run's history
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

    THE CLASS IS WIDER THAN THIS REQUIREMENT and the boundary is drawn
    here rather than left to a reader, because a refusal covered by two
    requirements is as unreadable as one covered by none. The three
    shapes above are the ones a CASE or a WRITER produces. The shapes a
    declared NAME produces, where the workspace renders that name or
    collects or stages a file it did not itself write, are FR-33d, FR-33e
    and FR-33f,
    and every refusal named in those four boxes belongs to exactly one of
    them. The one a reader is most likely to file twice: collection
    landing on a name already held in `raw/` is FR-33e and not the writer
    shape above, because it MOVES a file rather than writing one and
    takes no `overwrite` argument, so the way through is a per-point name
    or an archived simulation.

    ONE REFUSAL OF THE CLASS IS COVERED BY NONE OF THE FOUR, and the gap
    is published rather than left to be found. `collect_outputs` also
    refuses a declared output that RESOLVES inside the campaign root but
    outside this simulation's own folder, or under one of that folder's
    four managed subdirectories (PFS-2011.01 and PFS-2011.03, announced
    in `CHANGELOG.md` against FR-28 and FR-29, neither of which states
    it). That rule is about where a collected file may come FROM
    rather than about what it is named, it is decided on the resolved
    path rather than on the declared string, and whether it is widened
    into FR-29 or given an identifier beside these is an acceptance
    decision rather than a consequence of this split.

    Read with PFS-2029.19.02 at 0.11.0, which adds Mach and advance
    ratio to the rendered name so two rows that differ only there stop
    rendering one name; the collision refusal itself is unchanged.

!!! requirement "FR-33d A declared output name is a name, not a route <span class='srs-implemented'>implemented</span>"
    *Origin: OPS-2005.10.03, accepted 2026-08-20, giving the containment
    half of review finding PYFS-005 the identifier it had never had.
    Evidence: `_check_output_containment` in
    `pyflightstream.workspace.naming`, raising `NamingTemplateError`,
    reached from `NamingTemplate.render_output`;
    `tests/tier1_offline/test_error_messages.py::test_an_escaping_output_name_says_that_collection_moves`;
    the behavioural cases in `tests/tier1_offline/test_workspace.py`.*

    A declared output name that is empty, that is absolute, or that
    climbs out of the simulation folder with `..` is refused when the
    name is rendered, before any run can collect it. A subdirectory is
    not an escape and stays legal, because a solver export may
    legitimately land in one. The name is checked as declared and again
    after rendering, so a placeholder value cannot reintroduce an escape
    the template itself did not contain.

    The refusal is `NamingTemplateError` and NOT `WorkspaceError`, and
    that is a fact about the public surface rather than an implementation
    detail. The refusal comes from the naming template, so a caller
    already handling naming errors around `render_output` catches this
    one where it is raised, and a caller keying on `WorkspaceError`
    alone does not see it at all. Both derive from
    `PyflightstreamError`, which is what FR-39 asks of every refusal this
    package makes.

    Why containment is a naming rule and not a path rule. Collection
    MOVES a declared output into `raw/` rather than copying it, so a name
    that resolves outside the run does not read a file the run does not
    own, it takes it, and the manifest then records it as evidence the
    run produced. Deciding that on the declared string rather than on a
    resolved path is deliberate: the refusal then reads the same on every
    platform and does not depend on what happens to exist on disk at the
    moment the name is rendered.

!!! requirement "FR-33e A collected name never lands on a record <span class='srs-implemented'>implemented</span>"
    *Origin: OPS-2005.10.03, accepted 2026-08-20, giving the collection
    half of review finding PYFS-005 the identifier it had never had.
    Evidence: `CampaignWorkspace.collect_outputs` in
    `pyflightstream.workspace`, raising `WorkspaceError`;
    `tests/tier1_offline/test_error_messages.py::test_two_outputs_collecting_to_one_name_offer_the_placeholder_remedy`;
    the behavioural cases in `tests/tier1_offline/test_workspace.py`.*

    Two declared outputs of one collection whose base names agree are
    refused, and so is a declared output whose base name is already held
    in `raw/` from an earlier point or run. Neither refusal has an
    overwrite argument, deliberately, because the record either would
    replace is a run's evidence rather than a product a caller can choose
    to regenerate; the remedies are a per-point output name and an
    archived simulation, and both refusals name them.

    One rule in two shapes, because collection MOVES each output into
    `raw/` under its base name and both shapes end in one file where the
    manifest records two: the first would overwrite within a single call
    and the manifest would carry one name twice, the second would destroy
    evidence a previous point or run already collected.

    THE TWO SHAPES DIFFER IN WHEN THEY ARE DECIDED, and the requirement
    says so because the difference is visible to a caller. The first is a
    pre-scan over the whole call, so a refusal leaves every source exactly
    where it was. The second is asked of each destination immediately
    before that file is moved, so a call whose third output lands on a
    held name refuses with the first two already collected. That is
    measured rather than assumed (three outputs, the third colliding: two
    arrive in `raw/` and the refusal names the third). It is stated as a
    property rather than a defect because no record is destroyed either
    way, which is what this requirement guarantees; making the second
    shape a pre-scan too would be a behaviour change and is an acceptance
    decision, not a consequence of publishing the sentence.

!!! requirement "FR-33f Two staged inputs may not share a base name <span class='srs-implemented'>implemented</span>"
    *Origin: OPS-2005.10.03, accepted 2026-08-20, giving the staging half
    of review finding PYFS-005 the identifier it had never had.
    Evidence: `CampaignWorkspace.stage_inputs` in
    `pyflightstream.workspace`, raising `WorkspaceError`;
    `tests/tier1_offline/test_error_messages.py::test_two_inputs_sharing_a_base_name_name_both_sources`;
    the behavioural cases in `tests/tier1_offline/test_workspace.py`.*

    Two declared inputs whose base names agree are refused before any
    file is staged, and the refusal names both sources. Two references
    written as the SAME path are not a collision and stage as one input;
    two different spellings of one file are refused like any other pair,
    because the rule is decided on the declared path rather than on what
    it resolves to.

    Staging copies each source into `inputs/` under its base name, so
    without this the second copy won and the returned digest map carried
    ONE entry for what the case declared as two inputs. The manifest then
    recorded a single hash for two inputs and the run claimed to be
    reproducible from a file that was never staged at all, which is the
    same harm as an overwritten output arriving through the input side
    (NFR-07 is what the digest map exists for).

### New identifiers from the batch

!!! requirement "FR-37 Convergence status <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27. Resolved by the author
    2026-08-03. Evidence: `RunStatus.COMPLETED_MAX_ITER` and
    `RunStatus.FAILED_INCOMPLETE_OUTPUT` in `pyflightstream.workspace`, the
    judgment rules of `run.LoadsAssessor`, and the status tests in
    `tests/tier1_offline/test_run_campaign.py`.*

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
    milestone M7; the G0 synthetic gate in `tests/tier1_offline/test_farfield.py`.*

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
    `tests/tier1_offline/test_exceptions_catalog.py`, whose third guard walks every
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
    `tests/tier1_offline/test_exceptions_catalog.py`, so the residual is countable and
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

    The catalogue has TWO roots: `PyflightstreamError` parents every
    exception, and `PyflightstreamWarning` parents every warning, so a
    caller selects either family with one category. This sentence said
    the base parents the exceptions and not the one catalogued warning,
    which was true before the warning base existed and describes a
    package with one warning rather than three.
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

    Every command-line option is declared in a single registry
    recording its type, default, and validation rule, or is recorded
    with the reason it is not a knob of the machine, and the CLIs and
    the Python API resolve options through that registry; setting an
    unknown option, or a value outside its declared domain, raises an
    error naming the option and its allowed values. Every registered
    option name is a stable public contract, which is the form she
    chose against the review's recommended narrowing.

    The quantifier was "every user-facing option or parameter" until
    2026-09-09 and nothing could hold a console script to it; it is
    "every command-line option" on the decision of design/68 section
    PFS-2022.06, and `tests/tier1_offline/test_cli_options_registry.py`
    holds every console script named in `pyproject.toml` to it: each
    option either reads its default from a registry key, which the
    test measures by moving the key, or carries in the test the reason
    it is not a knob (the subject of the command, a case fact the
    manifest records, a mode switch, an output place, licensed
    material named per call). A new option must choose in the commit
    that adds it (PFS-2022.06.01).

    Pending on the Python-API half. The registry exists and its refusal
    behaviour is tested (`src/pyflightstream/options.py`,
    `tests/tier1_offline/test_options.py`), it holds three keys, all
    under `qa`, six flags of one CLI resolve through them and every
    other flag of every script is recorded with its reason; no
    Python-API parameter resolves through it yet.

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
    one source; `tests/tier1_offline/test_conventions.py`. The implemented status
    covers the STATING half: the conventions are published from one
    home and guarded there. That every emitted coefficient conforms to
    them is asserted by no test, and saying so here is the alternative
    to a badge that implies one.*

    Read with PFS-2028.09 at 0.14.0 (GOAL-013): the sense of rotation derived into the reference of her record is hers to confirm, and it is asked in writing rather than decided.

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
    pinned in `tests/tier1_offline/test_workspace.py`, the unknown-field refusal by a
    test added with this consolidation after review found the clause
    resting on a model-config line no assertion observed.*

    Read with PFS-2033.02 at 0.14.0 (GOAL-013): the strict record gains two fields, `raw_commands` and `aliases` (the setup's boundary aliases, her decision of 2026-09-09), and the manifest schema stays at 3 because an absent key reads as empty.

    The manifest record rejects unknown fields and duplicate run
    identifiers; its field set is fixed and validated at construction.

!!! requirement "FR-46 Closed terminal-status set <span class='srs-implemented'>implemented</span>"
    *Origin: the C6 acceptance, 2026-07-27. Evidence: the member set
    of `RunStatus` pinned in `tests/tier1_offline/test_workspace.py`, added with this
    consolidation; using the members, which the campaign tests do, does
    not notice an addition.*

    Every executed point terminates in exactly one value of a closed
    set of six status values, and a seventh cannot be introduced
    silently.

    Read with FR-37, which the author closed as covered by this set on 2026-08-03: this set stays closed at six and FR-37 was restated to ask for a status distinct from CONVERGED, which two of these six give.


!!! requirement "FR-47 Public test-support assertions <span class='srs-implemented'>implemented</span>"
    *Origin: the C8 acceptance, 2026-07-27. Evidence:
    `src/pyflightstream/testing.py`; `tests/tier1_offline/test_testing.py`.*

    The package exposes public assertion helpers that compare records
    and scripts and report the quantified violation on failure, so a
    user can assert against this package's outputs in their own tests.

## Independent review remediation (2026-08-02)

!!! requirement "FR-48 Broken commands are refused, and waivers are recorded <span class='srs-implemented'>implemented</span>"
    *Origin: the independent review's finding PYFS-002, reproduced
    2026-07-28 and again at HEAD on 2026-08-02. Evidence:
    `Script.allow_broken` and the emission refusal in
    `src/pyflightstream/script/__init__.py`; `waived_commands` on
    `RunRecord` (`broken_commands` until 0.13.0, PFS-2022.01.05); the
    database-driven refusal guard and the waiver
    guards in `tests/tier1_offline/test_script.py`,
    `tests/tier1_offline/test_script_helpers.py` and `tests/tier1_offline/test_run_campaign.py`.*

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
    `src/pyflightstream/support.py`; `tests/tier1_offline/test_support.py`.*

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

## The workspace interface the author specified (2026-09-02)

The requirements below were derived on 2026-09-02 from two sources read
side by side: the author's own driver for her master's campaign, which
ran a matrix with no mandatory input, exported eight kinds of file per
point and wrote her plot-format products afterwards; and the 0.10.1
tree, pre-flighted on her rows with zero solver time and diffed against
the scripts that produced her recorded results. Each requirement names
the planning nodes that carry it, so the plan points here and this page
points back. Her words are preserved verbatim in the coordination
record `RSH-HND-040` and its appendix; the measurements are on the
nodes.

!!! requirement "FR-50 A matrix runs with no mandatory command-line input <span class='srs-pending'>pending</span>"
    *Origin: the author's item #1 of 2026-09-02, "nao quero nenhum input
    obrigatorio aqui". Carried by PFS-2029.01, PFS-2029.02, PFS-2029.03
    and its two children, and PFS-2029.04. Evidence owed: the tests each
    node names.*

    Read with PFS-2031.11 at 0.13.0 (GOAL-012): a LEGACY row whose RECIPE cell carries a module:function reference plans and runs with no --recipe option.

    `pyfs-matrix run matriz.fs` and `pyfs-matrix plan matriz.fs` need no
    option beyond the matrix path: the solver build comes from each row's
    `FS_BUILD` cell, with the version option remaining as the default for
    rows that leave the cell empty; the run type comes from the `WORKFLOW`
    column wherever it names a registered type, with the recipe option
    remaining for `LEGACY` rows; the campaign name comes from the workspace
    directory, recorded as such, with the name option remaining as an
    override; and the `FS_SCRIPT` column is no longer part of the layout,
    the reader recognising the older layout by its header row and refusing
    it naming `pyfs-matrix upgrade`.

    Measured 2026-09-02 in the 0.10.1 tree: `run/cli.py:136` and `:138`
    mark the name and the version required, while
    `cases/matrix.py:720` already computes the only condition under which
    a default version answers for anything and says in its own message
    that today it answers for nothing. The version half is therefore a
    defect against the design recorded on PFS-2009.08 rather than new
    scope, and the requirement records both halves so the command line
    and the library stop disagreeing.

!!! requirement "FR-51 A run leaves the study's export set, named for the point <span class='srs-pending'>pending</span>"
    *Origin: the author's run log of 2026-09-02 and her master's driver,
    which exported eight kinds per point and named every file for the
    point it came from. Carried by PFS-2029.14 and its children,
    PFS-2029.18 and PFS-2029.19 and its children. Evidence owed: the
    export goldens and the script-parity arm of GOAL-011.*

    Read with PFS-2031.18.01 and PFS-2034.05 at 0.14.0 (GOAL-013): the stamped per-step exports of a windowed point are tabled as a series under the matrix's products, and her seat run reads them for the rotated propeller.

    Every point of a workflow campaign leaves, beside the loads table and
    the log it leaves today, the saved simulation, the tecplot export, the
    surface sections, the surface sectional loads and the probe points,
    and an unsteady point additionally its unsteady plots; the sections,
    sectional loads and probe points are updated and computed before they
    are exported, so no export is of a previous state; the saved
    simulation is written first, as the author's driver did; a
    post-processing artifact may deselect a kind; a kind whose command
    carries no row on the row's build is refused at pre-flight naming the
    build; and every export is named after the point in the author's
    convention, `POLAR-{pol}_M{mach}AL{alpha}BE{beta}` with a `J{ratio}`
    suffix for a rotor point, so two rows differing only in Mach or in
    advance ratio never render one name.

    Measured 2026-09-02: the 0.10.1 builders emit `EXPORT_LOG` once and
    `EXPORT_SOLVER_ANALYSIS_SPREADSHEET` at six sites and nothing else
    (`grep -c EXPORT_ src/pyflightstream/cases/workflows.py`); the
    default point name `a+00.0_b+00.0` carries the angles alone. Every
    export command the author's driver emits carries a row on 26.120 and
    on 26.123 in the command database, six of them verified.

!!! requirement "FR-52 Post-processing is declared in the pproc artifact and runs as part of the campaign <span class='srs-pending'>pending</span>"
    *Origin: the author's item #3 of 2026-09-02 and her decision of the
    same day that the groups artifact becomes `pproc`, and her
    clarification that post-processing means both the data treatment and
    the files and data types available. Carried by PFS-2029.07 and its
    children, PFS-2029.15 and its children, and PFS-2029.16. Evidence
    owed: the tests each node names and the offline parity arm of
    GOAL-011.*

    Read with PFS-2031.18.01 and PFS-2015.04.01 at 0.14.0 (GOAL-013): the series tables join the products beside the reductions, and the blade count of a sector is read from `PERIODIC_COPIES` when `BLADES` is absent, so the per-blade reductions of her isolated propeller are written.

    Read with PFS-2005.10, "an empty pproc group is every family, her verdict on the question PFS-2005.02 left to the domain seat", PFS-2005.04.01, "boundary aliases live in the setup and are read wherever a boundary is cited", and PFS-2029.07.04, "a pproc families entry may be a bare word", at 0.14.0 (GOAL-013), her decisions of 2026-09-09: an empty `[groups]` entry is every family the geometry carries; a `[groups]` member or a `families` entry may name an alias the row's setup defines, read as FR-30c states it; and a `families` entry may be a bare word, read as a selector, then as an alias, then as a family name, while an entry's `frame` may name a frame the setup defines or, on a row with several rotors, that rotor's own.

    Amended 2026-09-10, carried by PFS-2035.08 and PFS-2035.19, pending
    until it ships: the frames an entry may cite are the REFERENCE's
    (FR-72, "A custom frame is declared in the reference, where the
    geometry is"), and how an entry expands is decided by the frame it
    cites rather than by an `each_blade` word (FR-65, "The frame decides
    how a post-processing entry expands"). The sentence above stays true
    of every artifact written against 0.14.0 and names a home that empties
    at 0.15.0, which is why the amendment is here rather than only in the
    requirements that move it.

    The artifact kind `group` becomes `pproc`, kept under `inputs/pproc`
    with ids `p###`, and carries the whole post-processing definition of a
    study in six tables: the boundary groups, the export kinds a point
    writes, the surface-section distributions, the unsteady force plots,
    the probe lines, and the products the campaign writes; a matrix row
    names the artifact in its `PPROC` column, which replaces `ENTRY`, and
    the `OUTPUTS` and `LOG_OUTPUT` cells leave the row; the builders
    consume the definition, emitting one section distribution per family
    and plane, one force plot per group and frame, and one fluid plot per
    probe vertex and parameter; and a post-processing stage runs inside
    the campaign after each case's outputs are collected, writing the
    products under `post/` and naming them in the manifest, with
    `pyfs-matrix post` re-running the stage from the manifest alone. A
    setup artifact carries solver settings only, and a setup key naming
    post-processing is refused pointing at the pproc artifact.

    Measured 2026-09-02: the `ENTRY` column resolves a group artifact at
    `workspace/matrix.py:1030`, the result reaches the caller at `:1117`
    and no builder consumes it; `src/pyflightstream/post` holds four
    modules and nothing on the run path reaches them. The author's driver
    read a post-processing table off the same module as the solver setup
    and wrote her products after every polar.

!!! requirement "FR-53 The author's recorded campaign reproduces through the workflow scheme <span class='srs-pending'>pending</span>"
    *Origin: the author's instruction of 2026-09-02, "nao para ate
    reproduzir EXATAMENTE corridas selecionadas que fiz no meu script do
    mestrado, com posproc e tudo", and her clarification that the
    guarantee she wants is that exactly the same post-processing is
    produced. Carried by PFS-2030.01 to PFS-2030.07, under PFS-2030. Evidence owed:
    `GeoversePlan/goals/check_goal_011.py`, item one of GOAL-011.*

    Read with PFS-2028.08 at 0.14.0 (GOAL-013): the installed full model of her record is one row whose symmetry, rotation sign and moving boundaries are asked in writing and run on her seat.

    One recorded point per registered run type of the author's master's
    campaign, run on the solver build that produced the record, is
    reproduced by a workspace the package plans with nothing on the
    command line: the emitted script differs from the recorded script only
    on an enumerated allow-list of paths, comments, scene verbs and
    edition grammar; the run leaves the same export set under the same
    names; the package's post-processing, fed the author's recorded
    exports, writes her plot-format products equal to hers except the
    timestamp line; and the reproduced loads are compared coefficient by
    coefficient against the recorded ones with the solver's own measured
    repeatability as the arbiter of any difference.

    The reference set is machine-local, because the folder that holds it
    carries an identifier the content guard refuses in versioned files:
    the checker reads its root from `GeoverseSetup/local/reference_runs.json`
    and prints NOT YET naming that file when it is absent. The build is
    26.120, FlightStream 26.1 build #7012026, read off the recorded loads
    tables and matched to `commands/_meta.yaml` on 2026-09-02. The seat
    cost is five solver executions, authorised by the author on
    2026-09-02: three selected points and two controls.

!!! requirement "FR-54 Every solver setting a reference script states has a home and reaches the script <span class='srs-pending'>pending</span>"
    *Origin: the script diff of 2026-09-02 between the 0.10.1 pre-flight
    of the author's rows and her recorded scripts. Carried by PFS-2030.02,
    PFS-2030.03 and its four children, and PFS-2028.05 on her decision of
    2026-09-02. Evidence owed: the tests each node names.*

    A matrix row can state the fluid constants its author pinned
    (density, viscosity, sonic velocity, temperature, pressure) as
    flight-condition keys that override the standard atmosphere and are
    recorded as pinned; every builder states the reference velocity, the
    sideslip and the initialisation flag on the opened simulation; the
    reference artifact's moment point becomes the analysis loads frame and
    the moments model is stated; a setup's vorticity-drag families resolve
    through the geometry's inventory; significant digits and the wake
    termination in time steps have emitters; and a setup that states
    `symmetry_loads` emits it as stated, an absent key remaining
    recorded-only and warning as before.

    Measured 2026-09-02: the verbs only the author's scripts emit, beyond
    the export block, are `SET_ANALYSIS_SYMMETRY_LOADS`,
    `SET_SOLVER_ANALYSIS_LOADS_FRAME`, `SET_ANALYSIS_MOMENTS_MODEL`,
    `SET_SIGNIFICANT_DIGITS`, `SOLVER_SET_REF_VELOCITY`,
    `SET_VORTICITY_DRAG_BOUNDARIES`, `SOLVER_SET_SIDESLIP`,
    `LOAD_SOLVER_INITIALIZATION DISABLE` and, on the no-rotor unsteady
    run, `SET_WAKE_TERMINATION_TIME_STEPS`; the fluid state differs in the
    fourth digit because her scripts pin viscosity 1.789e-5 and sonic
    velocity 340.29 where the package derives both from the standard
    atmosphere. The consequence of the first verb is already measured: the
    isolated-rotor row of the 0.10.1 reproduction workspace reported loads
    six times the author's, the periodic copy count, because her setup
    stated the symmetry loads off and the package emitted nothing.

!!! requirement "FR-55 A row states its geometry as a file, and the geometry carries its own boundary inventory <span class='srs-pending'>pending</span>"
    *Origin: the author's items #2 and #6 of 2026-09-02. Carried by
    PFS-2029.06 and its children, PFS-2029.09 and its children, and
    PFS-2029.10. Evidence owed: the tests each node names. AMENDS FR-33a's
    resolution of a geometry by stable id, and the acceptance sentence of
    PFS-2009.01, in the same change.*

    Read with PFS-2034.02 and PFS-2034.03 at 0.14.0 (GOAL-013): the rotation's families resolve by name against the geometry's inventory, never by index, and a name the inventory lacks is refused naming the cell.

    The `GEOMETRY` cell of a matrix row carries a file name with its
    extension, a bare stem being refused naming the files that carry it,
    so that a saved simulation and a bare mesh are told apart by the row
    and not guessed; in this release the builders accept a saved
    simulation and refuse a mesh file naming the release that defines its
    boundary conditions; a geometry's boundary inventory has one source,
    the geometry file, with an optional sidecar written by
    `pyfs-matrix inventory` and never by a run, and a sidecar that
    disagrees with the file is refused naming both; `mesh_order_list` is
    refused in a setup rather than recorded; and a row or artifact may
    name the mesh families the base-region autodetect is allowed to
    consider.

    This reverses a rule the 0.10.1 library defends in four arms at
    `workspace/matrix.py:566-637`, which is why it is a minor release and
    why the migration of every shipped matrix travels with it.

!!! requirement "FR-56 The reference artifact states only what rows share, with one length per quantity <span class='srs-pending'>pending</span>"
    *Origin: the author's items #4 and #5 of 2026-09-02. Carried by
    PFS-2029.05 and PFS-2029.08. Evidence owed: the tests each node names.*

    Read with PFS-2028.09 at 0.14.0 (GOAL-013): the sign the reference's derived rotation produced for her rows is hers to confirm.

    The reference artifact carries the propeller diameter and no radius,
    refusing a file that states both with values that disagree; and it
    carries no `blade_travel`, `rotation`, `rpm_sign_installed` or
    `rpm_sign_isolated`, because the hand of a rotor is a property of the
    mesh a row opens and is stated in the row, a file still carrying them
    being refused naming the row keys.

    Measured 2026-09-02: `propeller_diameter_m` is read at
    `cases/workflows.py:832`; `radius_m` is required at
    `workspace/inputs.py:299` and read by no emitter; the four rotor
    fields at `:306-308` appear in no emitter.

!!! requirement "FR-57 A row states as many rotors as the study has <span class='srs-pending'>pending</span>"
    *Origin: the author's item #4 of 2026-09-02, the multirotor syntax.
    Carried by PFS-2029.11 and its children. Evidence owed: the tests each
    node names.*

    Read with PFS-2028.08 and PFS-2015.04.01 at 0.14.0 (GOAL-013): the installed model's row is hers to state, and a sector meshed as one blade takes its blade count from its periodic copies.

    A matrix row states its motions as a list of records in one cell, each
    record carrying its moving boundaries, its rotor speed sign, its axis
    and its origin point, the cell parser reading one level of nesting; a
    row with the flat single-motion keys of 0.10.1 reads unchanged; each
    motion creates its own fixed frame at its named point and its own
    moving frame that follows it, with its own motion block in the script;
    and a reference point declares that it is an engine point explicitly,
    a motion naming a point of another kind being refused.

    Measured 2026-09-02: a row states one motion at
    `cases/workflows.py:167-175`; named reference points already resolve
    by name (PFS-2025.15, evidenced), so what is new is the nesting and
    the repetition, not the points.

    **SUPERSEDED on 2026-09-10 by FR-60 and FR-61**, and superseded rather
    than met: the half of this requirement that shipped is the nesting, the
    list of records in one cell, which 0.11.0 built (CHANGELOG.md, the
    PFS-2029.11 entry under `## [0.11.0] - 2026-09-03`). The other half said each
    record carries its own moving boundaries, speed sign, axis and origin
    point, and her design of 2026-09-10 moves all four OUT of the record and
    into the reference's engine block, so the row states an alias and nothing
    else about the rotor. What this requirement asked for is therefore
    delivered by a different division of the same subject: FR-60 states the
    rotor, FR-61 states the row, and the keys named above are deprecated by
    FR-61 rather than implemented here.

    IT KEEPS THE `pending` MARKER DELIBERATELY, and the reason is written
    here so the published dashboard's reading is a choice rather than an
    oversight: this specification's status vocabulary is implemented,
    pending, deferred and deprecated, and none of the four says
    superseded. Introducing a fifth costs a generator and a stylesheet;
    marking this one implemented would claim its second half shipped;
    leaving it pending counts work that will never be done under this
    identifier. The three cost different things and choosing is the
    author's, asked in writing on 2026-09-10. Until she answers the marker
    stays, and this paragraph is what a reader meets beside it.

!!! requirement "FR-58 The fluid constants of a campaign have one home <span class='srs-implemented'>implemented</span>"
    *Origin: the author's instruction of 2026-09-04, 'vamos trabalhar com
    valores default ... dessa forma nao precisa inputar na matrix, eles podem
    ficar no s001'. Carried by PFS-2030.08. Evidence:
    `tests/tier1_offline/test_flight_condition.py` (the resolver, its refusals and each
    refusal's own reason), `tests/tier1_offline/test_matrix_run.py` (the file, the record
    the run layer writes, and the equal-render arm below), scored against
    nineteen mutants with an unmutated control.*

    A setup artifact may carry a `[flight_condition]` table holding the five
    pins of FR-54 and nothing else, its pin names matching case-insensitively
    as a `FLIGHT_CONDITION` cell's do. A row that states a pin overrides the
    setup's, key by key; a row that states none inherits it; and the resolved
    state is the same state either way, which
    `tests/tier1_offline/test_matrix_run.py::test_a_workspace_renders_the_same_script_whichever_file_states_the_pins`
    holds to the strongest available form: one workspace built twice from the
    same numbers, pins on the rows and pins in the setup, and the rendered
    script text equal BYTE FOR BYTE with nothing allowed to differ. A velocity key or a Reynolds number
    there is refused, because those are what a point IS and a preset several
    rows share cannot state them; an altitude or an ISA deviation is refused,
    because those locate a point in the atmosphere the pins exist to replace.
    A setup pinning a density under a row stating a Reynolds number has that
    one default dropped rather than refused. The run record carries the pins
    the setup supplied beside the condition as written, so it stays
    recomputable once the constants leave the row.

    Measured 2026-09-04: the author's three reproduction rows each repeat the
    same four constants, and her thirteen-point polar would repeat them
    thirteen times; the package's own sea-level atmosphere gives viscosity
    1.7892976260350732e-05 and sonic velocity 340.293988026089 where her tool
    states 1.789e-5 and 340.29, so the pins cannot be dropped in favour of the
    standard atmosphere. Those two figures are
    RE-MEASURED by
    `tests/tier1_offline/test_atmosphere.py::test_the_sea_level_state_is_stated_to_the_digit_the_srs_quotes`
    rather than left as prose: a full-precision literal that nothing pins goes
    silently false the moment a floor constant moves.

## The rotor vocabulary she designed (2026-09-10)

Fourteen requirements from one design, written out as a use case
workspace before a line of it was built, which the author read three times
and changed at every reading. The nineteen leaves
of PFS-2035 are that design one decision per node, and the requirements below
are those decisions stated as behaviour. Her sentence of that night defines
the release around them: the use case is what defines the scope of 0.15.0.

The shape they share, and the reason the set is worth reading as one: **a
study's vocabulary lives in the reference, a row states which of it moves and
at what operating point, and the mesh says what was actually meshed.** Every
requirement below is one seam of that division.

!!! requirement "FR-59 The reference holds the vocabulary of a study's boundaries <span class='srs-implemented'>implemented</span>"
    *Origin: her decisions of 2026-09-09 and 2026-09-10, "todos os aliases vao
    para referencia". Carried by PFS-2035.01 and PFS-2035.13. Evidence owed:
    the tests those nodes name. SUPERSEDES the `[aliases]` table of
    FR-30c, "Declared inventories are range-checked", which shipped it in the
    setup preset one release earlier. Evidence:
    `tests/tier1_offline/test_reference_vocabulary.py` (the table, a nested alias, a ring, and
    the self-reference that is not one) and
    `tests/tier1_offline/test_matrix_run.py::test_the_reference_aliases_reach_the_record`;
    commits f0032d3 and 661dd5d.*

    An `[aliases]` table of the REFERENCE artifact declares every name a study
    gives to a set of boundaries. A member may be a mesh family, a boundary
    name or another alias; the reader resolves to the end and refuses a cycle
    naming both sides. A member the opened mesh does not carry is ignored, so
    one reference serves the full aircraft and a cut of it. The setup preset's
    `[aliases]` table of 0.14.0 is read with a deprecation warning naming the
    reference to move it to, and is removed at 0.17.0.

    Only `all` and `each` remain the package's own words. `airframe`, `blades`
    and `blade_pattern` leave, because a study declares its own names and a
    built-in word that means one thing to the package and another to the
    author is the defect this requirement removes.

    Why the reference and not the preset: a boundary name is not a solver
    setting. A preset is per condition and a reference is per configuration,
    and the words a study uses for its own geometry belong with the
    configuration.

!!! requirement "FR-60 A rotor is one engine block of the reference, and the block is its alias <span class='srs-implemented'>implemented</span>"
    *Origin: her design of 2026-09-10. Carried by PFS-2035.02 and PFS-2035.16.
    Evidence: `tests/tier1_offline/test_reference_vocabulary.py` (the block, the blade count, the union the name stands for, and every refusal it carries). Commits f0032d3 and 45b9b6b.*

    A block of the reference whose `kind` is `engine` declares one rotor: its
    hub coordinates, `axis`, `rpm_sign`, `families_general` (what turns and is
    not a blade), `families_blades` (one entry per blade, in order), `blade1`
    (the azimuth of blade one and the axis its zero is measured from) and
    `diameter_m`. The BLADE COUNT is the length of `families_blades`, so a
    row states no blade count and a sector mesh carrying one blade of four
    still reduces over four.

    The block's NAME IS AN ALIAS over everything the rotor owns, the union of
    `families_general` and `families_blades` in that order: what a row moves
    when it cites it, and what a group summing the rotor sums. The name is
    free, and what it may not be is a name of one of the frames the package
    builds from it: a rotor carrying `_SMRP` or `_RMRP` in its own name is
    refused, because then a rotor and a frame spell the same.

    THE RULE PFS-2035.02 STATED WAS NARROWER AND WOULD HAVE REFUSED HER OWN
    STUDY, and it is corrected here rather than quietly widened. The node
    said a name is refused when it ENDS IN A DIGIT, "because a number after a
    radical always means a blade", which was true of the frame names of
    0.14.0 (`PROP_MRP<k>`, `BladeAxis<k>`) and is not true of these. A
    rotor's frames are `<ALIAS>_SMRP`, `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>`,
    so the number sits after `RMRP` and never after the alias, and no two
    distinct aliases can produce one frame name. Measured 2026-09-10 against
    the use case she read three times: eight of its ten blocks are named
    `LIFT_L1` to `LIFT_R4` and every one of them ends in a digit. `rpm_sign` is `+1` by the right-hand rule
    about `axis`, which is the one reading that does not depend on where the
    reader stands.

    The block also carries `alias`, equal to the block's name when it is
    written; a block whose two names disagree, case folded, is refused
    naming both. **OPTIONAL IN THE FILE AND REQUIRED ON THE MODEL**, and
    the distinction is where the two earlier readings of this paragraph
    both went wrong. A reference file may omit it and the reader fills it
    in from the name, which is what the interface lens of 2026-09-10
    asked for: the refusal for a disagreement told the user to drop a
    field the model then refused as missing. Making the MODEL field
    optional too was the fix that shipped, and a type check found what it
    cost: everything downstream reads the alias as the rotor's identity,
    so a block built in Python without one built frames named
    `None_RMRP1` rather than refusing. The reader fills the name in before
    the block is built, so the file's freedom is unchanged. Whether the
    field is worth keeping at all is the author's open question.

    The campaign's propulsor count is therefore the number of engine blocks,
    rather than the point kind and its `ERP`/`ARP` fallback that answer it
    today (0.11.0, PFS-2029.11.02).

!!! requirement "FR-61 A row names a rotor by its alias and states nothing else about it <span class='srs-implemented'>implemented</span>"
    *Origin: her design of 2026-09-10, "vamos mudar MOVING_BOUNDARIES para
    MOVING_BC_ALIAS". Carried by PFS-2035.03. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py`, where the alias moves that rotor's
    boundaries, an unknown alias is refused naming the engines the reference
    does declare, and a record stating both spellings is refused; commit
    45b9b6b.*

    `MOVING_BC_ALIAS` names an engine block of the row's reference and is the
    only rotor identity a motion record carries. `MOVING_BOUNDARIES`,
    `ROTOR_AXIS`, `ROTOR_ORIGIN`, `RPM_SIGN` and `BLADES` are what it
    replaces, because the reference states each once; a record stating any
    of them BESIDE the alias is refused naming both, and a record stating
    them without an alias is read as it always was, which is what keeps
    every row written before this release working. They are removed at
    0.17.0.

    `PERIODIC_COPIES` is NOT among them and the earlier wording said it
    was: it states what the MESH is, a sector of a wheel, which is a
    property of the file the row opens rather than of the rotor the
    reference declares. What the reference replaces is the blade COUNT
    that `PERIODIC_COPIES` was also read for (FR-68). `SYMMETRY` stays, because what was meshed is a property of the
    file the row opens.

    A sector row stating no `PERIODIC_COPIES` takes the count from the two
    files, and that is not a departure from the line above: the count is
    the wheel's blade families divided by the ones THIS GEOMETRY CARRIES,
    so the divisor is read from the file the row opens and the number
    stays the mesh's. A rotor declared with four blade families, meshed as
    a sector carrying one of them, stands for four copies; the same rotor
    meshed as a half, carrying two, stands for two. A pair that does not
    divide evenly is refused rather than rounded, as is a geometry
    carrying none of the rotor's blade families, because neither can be a
    slice that repeats a whole number of times. Reading the reference's
    blade count ALONE was the first writing of this rule and it answered
    four for the half, which is the SRS and the code saying different
    things about one key.

    A cell naming an alias the reference does not declare as an engine is
    refused at plan time, naming the alias and the engines the reference does
    declare.

!!! requirement "FR-62 The frames a rotor instantiates take its alias as their radical <span class='srs-implemented'>implemented</span>"
    *Origin: her design of 2026-09-10, "<ALIAS>_SMRP para o eixo local
    estatico e <ALIAS>_RMRP para o eixo rodando junto com o movimento".
    Carried by PFS-2035.04, absorbing PFS-2029.21. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py`, where the frames take the radical, the blade
    frames TURN with the blades, a record naming no engine keeps the 0.14.0
    names, and a blade the mesh lacks gets no frame while the count stays;
    commits 6288aaf and 927ef8b.*

    A rotor creates `<ALIAS>_SMRP` at its hub, static; `<ALIAS>_RMRP` turning
    with the motion; and `<ALIAS>_RMRP<k>` per blade of `families_blades`,
    turning with blade k and numbered from the `blade1` datum. A family of
    `families_general` has no local axis of its own: its local frame IS the
    rotor's, `SMRP` when static and `RMRP` when turning.

    `PROP_MRP<k>`, `RotorAxis<k>` and `BladeAxis<k>` are the names these
    replace, and a post-processing entry citing them is read with a
    deprecation warning until 0.17.0.

    This is what makes a multirotor row possible at all: the frame names carry
    the rotor's identity, so nine rotors instantiate nine sets rather than
    colliding on one radical.

!!! requirement "FR-63 The rotor speed lives in the motion record, resolved against that rotor's own diameter <span class='srs-implemented'>implemented</span>"
    *Origin: her design of 2026-09-10 and her reminder of the same night, "a
    razao de avanco vira RPM usando o diametro de cada rotor". Carried by
    PFS-2035.05 and PFS-2035.18. Evidence: `tests/tier1_offline/test_rotor_by_alias.py::test_one_ratio_gives_two_rotors_two_speeds_when_their_diameters_differ`, which asserts the two speeds are in the inverse ratio of the diameters. Commit 45b9b6b.
    AMENDS FR-56, "The reference artifact states only what rows share, with
    one length per quantity", whose single `propeller_diameter_m` is the
    advance-ratio length today.*

    A motion record states `RPM` or `ADVANCE_RATIO`, never both and never
    neither, refused PER ROTOR with the message the row-level refusal carries
    today.

    An advance ratio is resolved rotor by rotor, against the `diameter_m` of
    the engine block the motion names: `n = V / (J * diameter_m)` and
    `rpm = 60 n`, with `V` the freestream speed of the flight condition. One
    ratio therefore yields a DIFFERENT speed per rotor whenever the diameters
    differ, which is what a row of eight 1.20 m lifters and one 1.80 m pusher
    needs. A motion whose block states no `diameter_m` is refused at plan
    time naming the block, the row and the key, because there is nothing to
    resolve against.

    The top-level `propeller_diameter_m` of the reference therefore stops
    being the advance-ratio length: it is one number for a whole
    configuration, and a second rotor of another size cannot be resolved by
    it.

!!! requirement "FR-64 Every rotor row names the motion that owns the clock <span class='srs-pending'>pending</span>"
    *Origin: her design of 2026-09-10, "o setup temporal exige qual o
    movimento de referencia". Carried by PFS-2035.07. Evidence owed: the tests
    it names.*

    `CLOCK_MOTION` is a cell key, required on every row that states a motion,
    even a row with one, and it names a motion the same row states. The time
    step and the run length are that motion's. `rotor_speed` becomes
    `rotor_speed_ref` so the call site says which speed it is.

    A row of SEVERAL motions without the key is read with a warning naming
    the motion assumed, until 0.17.0; a row of ONE is silent, because there
    is nothing to choose between. Today the clock follows the fastest rotor
    by the package's own arithmetic, which is an inference the author never
    wrote down; a declaration replaces it.

    IMPLEMENTED IN PART at 0.15.0, and the part that is owed is named here
    rather than left for a reader to discover: the key is read, the named
    motion owns the clock, and a row of several motions that states none
    warns. What is NOT done is the rename of `rotor_speed` to
    `rotor_speed_ref` at the call site, and the key is not yet REQUIRED on
    a row of one motion. Evidence for the part that shipped:
    `tests/tier1_offline/test_rotor_by_alias.py` (the clock follows the
    named motion and not the fastest; a clock naming no motion of the row
    is refused); commit 91a7302.

    Measured 2026-09-10: `cases/workflows.py:4649` reads
    `fastest = max(speeds, key=lambda each: abs(each.rpm))`, and nothing in
    the row says which rotor that is.

!!! requirement "FR-65 The frame decides how a post-processing entry expands <span class='srs-implemented'>implemented</span>"
    *Origin: her design of 2026-09-10 and her spinner decision of the same
    night. Carried by PFS-2035.08, absorbing PFS-2029.20. Evidence:
    `tests/tier1_offline/test_pproc_by_frame.py`, which reads the rule off
    the model (an entry in a rotor frame is one per rotor, one in the local
    axis is one per blade, one in a common frame is one, the placeholder is
    present exactly when there is more than one emission, `each` stays and
    `each_blade` warns) and ends by validating HER OWN
    `pfs0150/inputs/pproc/p010.toml`, which is the file the requirement was
    written from. Measured 2026-09-10: with the rule in place her two
    matrices plan 39 points with none blocked, where the artifact would not
    validate at all before it.*

    An entry citing `MRP` or a frame the reference declares emits ONCE over
    the whole cited set, and an engine name in that set is its own union, so a
    propulsor's total carries its hub and spinner with its blades. An entry
    citing `SMRP` or `RMRP` emits one per ROTOR, in that rotor's frame. An
    entry citing `LOCAL_AXIS` emits one per BLADE, in that blade's frame, plus
    one for the rotor's general families, which ride the rotor's own frame.

    There is no `expand` key: the frame already says it. `each` stays, because
    one emission per family in a common frame is a reading no frame implies;
    `each_blade` is read with a deprecation warning until 0.17.0. `{family}`
    is the only placeholder and means WHAT THE EMISSION IS ABOUT: the alias on
    a per-rotor entry, the blade's label on a per-blade one, the family on an
    `each` one.

    An entry citing `LOCAL_AXIS` over a set holding no rotor OF THE
    REFERENCE is refused at plan time, naming the entry, the set and the
    engines the reference declares. It is a writing error rather than a
    configuration difference: unlike an entry that resolves to nothing, it
    cannot come right on another mesh.

    THE OTHER HALF OF THAT SENTENCE, which the implementation forced and
    which is the line the two cases fall on: an entry whose rotors the
    reference DOES declare, but whose frames THIS RUN did not place, is
    LEFT OUT with a warning, exactly as an entry whose families the
    geometry lacks is. A steady row places no rotor frames and a row that
    turns only the lifters places no pusher frames, and one artifact serves
    all three; that entry comes right on the next row, which is precisely
    what the refused one cannot do. Measured 2026-09-10 on her own
    workspace: the distinction is 19 of her 39 points.

    THE SAME RULE REACHES THE SECTIONS AND THE PROBES, through one helper
    rather than three: a distribution measured in a blade's own axes is one
    per blade, and a probe table naming one rotor's frame is left out on a
    row that does not turn that rotor.

    A probe table's `rotor_radius` is the radius OF THE ROTOR WHOSE FRAME
    IT NAMES. That question had no answer before this release, because the
    reference carried one diameter for the whole configuration; it carries
    one per rotor now (FR-60), and reading the configuration's would lay a
    lifter's probes out over a pusher's disk without saying so. The word
    was `propeller_radius` and is read with a warning until 0.17.0.

!!! requirement "FR-66 A row may state the symmetry-loads flag, overriding the preset with a warning <span class='srs-implemented'>implemented</span>"
    *Origin: her decision of 2026-09-10, "vale promover ele para flag sim e
    vamos manter isso na matriz". Carried by PFS-2035.09. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py`, where the row overrides the preset and warns,
    agreeing warns nothing, and a value that is not a yes or a no is refused;
    commit 91a7302.*

    `SYMMETRY_LOADS` is a row key registered on every run type. A row stating
    it overrides the preset's value and warns, naming both files and the value
    used; a row stating nothing inherits the preset silently, as today.

    Whether the solver reports the loads of the meshed sector or of the whole
    wheel is a per-row choice, because the same preset serves a sector row and
    a full-wheel row. The override warns rather than refusing, which is her
    second answer of that hour: the first was to refuse both stating it, as
    the rotor speed is refused.

!!! requirement "FR-67 A row may state raw solver commands, after the preset's at the same seam <span class='srs-implemented'>implemented</span>"
    *Origin: her decision of 2026-09-10, "a linha ganha um jeito de passar
    comando bruto, mantendo a feature original preservada". Carried by
    PFS-2035.10. Evidence: `tests/tier1_offline/test_raw_on_the_row.py` (the cell
    states one record and several; a file path survives the record separator; a
    record stating both forms, neither form, no phase, or a key a raw command
    does not read is refused; a row stating none carries none; a file becomes
    one command per line in order; a blank line and a comment are skipped; each
    line carries the file and its line number; the row's cell line comes after
    the row's file; a file the workspace does not carry and a file outside the
    inputs are refused) and
    `test_the_record_and_the_provenance_carry_the_raw_commands_of_the_setup` of
    `tests/tier1_offline/test_matrix_run.py` (the record names each line's
    source). EXTENDS the preset-level `[[raw]]`
    table of FR-31, "Solver-setup provenance", to the row.*

    A cell's `RAW` list states solver commands, each before a named phase, in
    either of two forms: `COMMAND`, the line written in the cell, and `FILE`,
    a text file of the workspace whose lines are emitted in order. Both pass
    the same emitter checks the preset's `[[raw]]` table passes, line by line,
    so a file carrying a command the build lacks is refused naming the FILE
    and the LINE NUMBER rather than the cell. A blank line and a line opening
    with `#` are skipped, so a raw file may explain itself.

    At one seam the preset's lines come first and the row's after, on her
    answer that the shared lines are the ground and the specific ones come
    over them.

    The run record names each line's source, the setup's id, the word
    `matrix`, or the file's path, and a file's lines are recorded AS EMITTED,
    so a record still reproduces the run after the file has changed.

    ONE THING THIS TEXT DID NOT ANTICIPATE, and her own row 9209 is where it
    showed: a record's key and value pairs are separated by a slash, and a PATH
    carries slashes, so `FILE: raw/pusher_extra.txt / BEFORE: init` was cut at
    the path's own separator and refused as not a pair. A raw record splits on
    a SPACED separator, because its two values are a path and a command line
    and both carry punctuation of their own. Every other record kind is
    unchanged.

!!! requirement "FR-68 The reductions read each rotor's blade count from its own declaration <span class='srs-implemented'>implemented</span>"
    *Origin: her design of 2026-09-10. Carried by PFS-2035.11. Evidence:
    `tests/tier1_offline/test_reduce_by_rotor.py` (a row stating its speeds in
    motions reduces at all; each rotor's passage is its own and the two are
    asserted UNEQUAL before either is pinned; the per-blade windows are
    contiguous and end at the run's last step; a several-rotor row says where
    its reductions went instead of naming a count; a one-rotor row takes the
    count from that rotor's block; a sector row reduces over the whole wheel; a
    motion naming no rotor of the reference leaves the others reducing) and
    `tests/tier1_offline/test_post_products.py` (the files name the rotor, and a
    one-rotor row keeps the names it has always had). AMENDS PFS-2015.04.01,
    which reads the count from `PERIODIC_COPIES` at 0.14.0.*

    A HALF THAT IS NOT IN THE TEXT BELOW, because nothing had measured it until
    the implementation: a row stating its speeds in MOTIONS carries no `RPM` of
    its own, so the window reader found no speed and EVERY reduction of the
    point was skipped, the time average included, with the sentence "states no
    rotor speed, and a rotary motion turns at one" on a row that states two. The
    row's window is the CLOCK motion's (FR-64), which is the same rotor whose
    revolutions already set the row's step and its length.

    The per-blade and phase-locked reductions of a point are computed PER
    ROTOR, each from the blade count of its own engine block, so a transition
    row reduces the lifters and the pusher in one run and the reduction files
    name the rotor. A row stating no motion reduces as today.

    A sector mesh needs nothing of its own: the count is the length of
    `families_blades` and not a property of the file, so a mesh carrying one
    blade of four still reduces over four, and `PERIODIC_COPIES` is not
    replaced by another key but by a fact the reference already states.

!!! requirement "FR-69 A sweep is one variable of the flight condition, and the angles are always written <span class='srs-implemented'>implemented</span>"
    *Origin: her rule of 2026-09-10, "um sweep e aplicado a uma variavel que
    DEFINE a condicao de voo e a apenas uma variavel". Carried by PFS-2035.14,
    which closes PFS-2035.12 and bounds PFS-2035.06. Evidence:
    `tests/tier1_offline/test_matrix.py` (the axis is read off the cell; a row
    with no swept key, with two, with a key this release cannot vary, or with
    an empty values cell is refused; the fourth stage folds the column and
    changes no other cell; the 0.11.0 layout is recognised and refused naming
    its converter; and the upgrade does not rename a run) and
    `tests/tier1_offline/test_matrix_upgrade.py` (both older layouts land on
    the same bytes). SUPERSEDES the `SWEEP_TYPE` column of FR-10, "Run-matrix
    reader, forever".*

    `FLIGHT_CONDITION` states `ALPHA` and `BETA` on every row, so no run
    reaches the solver at an angle nobody wrote. The swept variable is the one
    whose value is the word `sweep`, EXACTLY ONE key carries it, and
    `SWEEP_VALUES` holds its values. Any key of the flight condition may be
    the one: the five that fix the state (`MACH`, `TASmps`, `REmi`, `ALTFT`,
    `dISA`), the five pins (`RHOkgm3`, `MUPas`, `ASMPS`, `TK`, `PPA`), the two
    angles, and the advance ratio when the row states it there. **Of those,
    this release implements ALPHA, BETA and ADVANCE_RATIO**; every other key
    is refused NAMING those three and saying it may carry the word in a
    later release, because accepted-and-ignored is how the advance-ratio
    sweep failed before this release.

    The `SWEEP_TYPE` column is removed, because the cell already says which
    variable varies. A row with no `sweep`, with two of them, or with a
    `sweep` on a key that does not define the condition is refused at plan
    time naming the keys.

    THE COST, stated once and not hedged: the paired `AL/BE` sweep is two
    swept variables and retires with the column. The sweep type `alpha_beta`
    is deprecated with it, and stays readable from a hand-written
    `campaign.toml`, which is a door of its own.

    Measured 2026-09-10, and it is SMALLER than the estimate this paragraph
    first carried. That estimate said eleven rows of the licensed matrices
    use the paired code and each becomes one row per sideslip. Counting them
    instead: a paired code whose second axis holds ONE value is one swept
    variable written in two columns, which is what the reader always did with
    it, so it folds automatically. **Exactly one row in the whole repository VARIED both
    angles** before this release, POL 9008 of
    `tests/tier1_offline/fixtures/pfs202609_matrix14.fs` at 54d8187, a
    fixture built for the feature this release retires; the 13-column
    layout cannot express such a row at all, so none exists at the tip.
    The other 9 of the 10 live matrices converted with no hand edit.

    Counted by reading the `SWEEP_TYPE` and `SWEEP_VALUES` cells of every
    matrix in the tree at 54d8187 and asking of each paired code whether
    BOTH its groups hold more than one value.

    THE ONE ROW WAS NOT SPLIT, and saying so is the point of naming it
    here. Splitting is what this release asks of a USER, because only the
    author of a study can allocate the new POLs. That fixture was built to
    exercise the paired reader and its three diagonal points meant nothing
    physically, so it was rewritten as a swept incidence at a held
    sideslip, which changes two of its three points' sideslip. That is a
    decision about a test fixture, taken deliberately and recorded here
    rather than presented as a conversion.

    THE UPGRADE DOES NOT RENAME A RUN, which is a stronger promise than
    lossless content and is the one that costs seats if it is broken. A
    paired row tagged its points with BOTH angles, and those tags end the
    `run_id` of every record in every manifest written before this release.
    So an angle the row HOLDS is carried at every point of the sweep
    (`SweepAxis.held`), the tags are unchanged, and a resume after the upgrade
    finds its records. Only the two angles are carried: they are the only
    coordinates a tag has ever held.

    Measured 2026-09-10: the matrix reader accepted two sweep codes and only
    two, `{"AL": "alpha", "BE": "beta"}`, so a sweep of Mach, of Reynolds, of
    altitude or of a pinned temperature is new surface rather than a rename.
    What this release implements is `ALPHA`, `BETA` and `ADVANCE_RATIO`; every
    other key is refused NAMING those three and saying it may carry the word
    in a later release, because accepted-and-ignored is how the advance-ratio
    sweep failed before this release.

!!! requirement "FR-70 An advance ratio in the flight condition governs the motions that state no speed <span class='srs-implemented'>implemented</span>"
    *Origin: her decision of 2026-09-10 and its widening the same night,
    "entao o sweep vale so para o movimento que nao tem advance ratio
    declarado". Carried by PFS-2035.15. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py` (a swept ratio reaches the
    motion that states no speed and halving the ratio doubles that rotor's
    rev/min, a record stating its own ratio holds it against the sweep, and
    a record writing the word is refused naming where sweeping is stated).*

    `ADVANCE_RATIO` may be stated in `FLIGHT_CONDITION`, as a value or as
    `sweep`, and it then reaches every motion of the row THAT STATES NO SPEED
    OF ITS OWN. A motion stating its own `RPM` or `ADVANCE_RATIO` holds that
    value and the condition's ratio passes it by. A motion may not state the
    word `sweep`: sweeping is the condition's job, and a record that writes it
    is refused at plan time naming the cell, the record and the key.

    The rule is precedence, record over condition, and it exists for one case
    she named: a transition sweeps the pusher while the lifters hold. Eight
    records carrying an RPM and one carrying nothing but its alias is that
    row, and the held motions hold at EVERY point of the sweep.

    A SWEPT RATIO IS THE POINT'S, NOT THE ROW'S, and that is the half a
    variable lookup could not reach. The swept key is deliberately kept out
    of the row's variables, because the row states only the word and the
    value is what varies; so a row writing `ADVANCE_RATIO: sweep` had no
    ratio among its variables and the condition's ratio reached no motion
    at all. Measured 2026-09-10 on her own `matriz_transicao.fs`: 9 of 16
    points blocked on "states no rotor speed", which is the sentence this
    requirement removes.

    The key stays optional precisely so that a row may prescribe the speed per
    motion instead, which is FR-63.

!!! requirement "FR-71 A rotation cites an alias, carries its frames, and keeps the frame it turned from <span class='srs-pending'>pending</span>"
    *Origin: her decision of 2026-09-10, "o comando de rotate tambem tem que
    ser atualizado para ficar compativel com o do movimento". Carried by
    PFS-2035.17. Evidence: `tests/tier1_offline/test_rotor_by_alias.py` (the
    rotation cites the alias and turns that rotor's boundaries and no other's;
    the frames the alias owns turn with it, by name; an undeclared alias is
    refused naming it; a record stating both spellings is refused naming both;
    a record stating neither is refused; the 0.14.0 spelling warns and turns
    the same boundaries). PENDING ON ONE HALF, and it is the half the author
    owes rather than the one the code owes: see the SMRP_ORIGINAL paragraph
    below. AMENDS the `ROTATE` record of FR-35, "Matrix as first-class
    interface", whose `FAMILIES` and `AUX_FRAMES` keys this replaces.*

    A `ROTATE` record states `ALIAS` where it stated `FAMILIES`, so a rotation
    and a motion cite a set of boundaries the same way. `AUX_FRAMES` retires:
    every frame the alias owns turns with its boundaries, which for a rotor is
    `<ALIAS>_SMRP`, `<ALIAS>_RMRP` and every `<ALIAS>_RMRP<k>`, and for a
    non-rotor alias is none.

    **NOT BUILT, AND THE REASON IS NOT THAT IT IS HARD.** Before the first
    rotation of an alias the builder creates `<ALIAS>_SMRP_ORIGINAL`, a copy
    of that frame as it stood, which nothing turns and which a
    post-processing entry may cite, so a study of an installed propeller
    keeps the frame it turned FROM. Today that frame is lost the moment the
    mesh moves.

    PFS-2035.17 records the choice as the author's: once per ALIAS, before
    the first rotation, or once per RECORD, which would also keep the frame
    BETWEEN two rotations of the same alias. The two differ in what a study
    of a pitch and then a toe can read afterwards, which is a question about
    what a user wants to measure and not one the code can answer. Building
    one of them and writing it down where it would look decided is the
    failure this estate names design-first, so this half waits.

    Measured 2026-09-10, before the rest of this requirement was built: the
    builder emits `ROTATE_COORDINATE_SYSTEM` and keeps no copy of a frame
    anywhere; `grep -c "_ORIGINAL" src/pyflightstream/cases/workflows.py`
    answers 0. It still answers 0.

    A rotation citing an alias the reference does not declare is refused
    naming the alias, and listing the words the reference does declare.

    `ALIAS` names EXACTLY ONE declared word, and that is not an arbitrary
    limit: a rotation carries the frames of what it turns, and those belong
    to one rotor. A word naming two declared rotors is refused telling the
    author to write one record per rotor, which is the shape a `FAMILIES`
    list spanning two rotors converts to and the one case the conversion
    cannot do by substitution.

    The `FAMILIES` spelling is read with a deprecation warning until 0.17.0,
    so every matrix written before this release keeps working, and the
    warning names the words the reference declares, because the key changes
    AND SO DOES THE VALUE and the warn site holds that information.
    `AUX_FRAMES` beside it still names frames that turn, because what the
    alias makes unnecessary it does not forbid; it is not deprecated and
    carries no removal promise. A record stating `ALIAS` and `FAMILIES`
    both is refused: one rotation turns ONE set, and picking one of two
    statements silently is how the wrong half of a study gets turned.

    NO FRAME TURNS TWICE, however many names it answers to. A rotor's hub
    is `<ALIAS>_SMRP` and `PROP_MRP<k>` at one index, and its moving frame
    is both a frame the alias owns and a follower of the hub, so an
    emission list keyed on NAMES applied the row's angle twice and the
    blades then spun about an axis at twice the stated incidence. The
    emission is keyed on the frame.

    After this requirement a row names a set of boundaries one way, whether it
    moves them, turns them or measures them, which is what makes the fourteen
    requirements of this section one vocabulary rather than fourteen features.

!!! requirement "FR-72 A custom frame is declared in the reference, where the geometry is <span class='srs-implemented'>implemented</span>"
    *Origin: her decision of 2026-09-10, "definicao de eixo customizado como o
    NAC_FL vai para o ref, onde fica dados geometricos". Carried by
    PFS-2035.19. Evidence: `tests/tier1_offline/test_reference_vocabulary.py` and `tests/tier1_offline/test_matrix_run.py` (the frames reach the case, a preset still stating them warns and the reference wins, a LEGACY row leaves them out and says so). Commits f0032d3, 661dd5d and 2840078. SUPERSEDES the
    `[[frames]]` table of FR-31, "Solver-setup provenance", which places it in
    the setup preset.*

    The `[[frames]]` table moves from the setup preset to the reference
    artifact, keeping the shape it has: `name`, `origin`, and optionally
    `x_axis` and `y_axis`, the third axis being the right-handed cross
    product. A row's `ROTATE` axis token and a post-processing entry's frame
    resolve against the reference's frames, the package's own names staying
    reserved. A preset still stating `[[frames]]` is read with a deprecation
    warning naming the reference to move it to, and the table is removed at
    0.17.0.

    A coordinate system is geometric data, so it belongs beside the lengths
    and the rotors. It also puts the two halves of one subject in one file:
    the frames a rotor instantiates were always derived from the reference's
    rotor block, while the hand-written ones sat in the preset.
