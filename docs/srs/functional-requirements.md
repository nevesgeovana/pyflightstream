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

    THE ENUMERATION WAS REMOVED on 2026-08-18, by design decision,
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

    Read with PFS-2001.05, PFS-2003.06, PFS-2054, PFS-2054.09, PFS-2059 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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

    Read with PFS-2059, PFS-2059.01, PFS-2060, PFS-2060.01, PFS-2061, PFS-2061.01, PFS-2061.02, PFS-2061.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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
    repository. The owning seat chose on 2026-08-03 to make it exist rather
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

    Read with PFS-2056, PFS-2056.05, PFS-2057, PFS-2057.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    A dedicated reader consumes the documented pipe-delimited
    run-matrix format: rows with RUN = 1 are active, the sweep columns
    define alpha, beta, or advance-ratio sweeps, and the variables
    column holds KEY:VALUE pairs. A column the reader does not
    recognize is preserved and reported rather than silently dropped.

    Reworded 2026-07-27. "Forever" is scoped to the EXTERNAL format,
    which is the promise that matters to the existing files,
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
    layout was 13 columns and the 14-column one is frozen beside the three
    older ones, recognised by its header and refused naming the converter.

    A FIFTH BREAK SHIPPED AT 0.17.0 and travelled through the same
    mechanism, stated by FR-93, "The run matrix carries nineteen columns":
    six columns arrive (`CONFIGURATION`, `GEOMETRY`, `SYMMETRY`,
    `SYMMETRY_LOADS`, `NCPUS` and `WALLTIME`) and two move (`HIDDEN` and
    `RUN`, to sit directly after `POL`). THE VERIFIED LAYOUT IS NOW 19
    COLUMNS, and the 13-column one is frozen beside the older ones with its
    own rung on the ladder. Each of the six was already expressible, four
    inside the free variables cell and two inside the setup artifact, so
    the break moves WHERE a fact lives and makes no fact required.

    This is the break that most tested the promise this requirement is
    named for. A conversion may not rename a run, because the point tag is
    run identity and ends every `run_id` in every existing manifest, so the
    upgrade carries POL, the flight condition and the sweep values across
    verbatim and a resume still finds its records.

    **Two clauses of this requirement are superseded, and the format promise
    is not.** The point tag called run identity in the paragraph above is what
    0.20.x wrote: a point is named by its flight condition since 0.21.0
    (FR-102), and an existing workspace is moved to those names by
    `pyfs-matrix rename` (FR-103), which is the one command allowed to do what
    the upgrade may not. And "alpha, beta, or advance-ratio sweeps" was the
    whole of what a row could sweep until 0.21.0; any variable the
    `FLIGHT_CONDITION` cell declares can be swept now (FR-104). The
    pipe-delimited format itself, and the unknown-column clause, stand.

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

    Read with PFS-2056, PFS-2056.11 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    A campaign run records every datapoint outcome. Failures are
    collected and reported at the end as a structured error; a silent
    skip is structurally impossible.

!!! requirement "FR-15 HPC executor <span class='srs-pending'>pending</span>"
    *Origin: BRF-01.*

    Read with PFS-2056, PFS-2056.07, PFS-2056.09, PFS-2057, PFS-2057.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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

    Read with PFS-2056, PFS-2056.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2033.02 at 0.14.0 (GOAL-013): the record gains `raw_commands`, the setup's raw lines the script carried, and `aliases`, the setup's boundary aliases the polar tables resolve by (the design decision of 2026-09-09), both absent on older records and read as empty.

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

    Plot files byte-compatible with the established plot
    format, with a reader making the pair round-trip testable. Not
    yet started; VTK and Tecplot probe-data writers exist in `post/`
    but that plot format is not among them.

    THE FORMAT NOW HAS A REFERENCE, named 2026-09-02: the products the
    reference driver wrote from the reference campaign, one polar
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
    identifier of its own because that is where it was folded
    when it was accepted, against the option of making it a public
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

    Read with PFS-2054, PFS-2054.05, PFS-2054.06, PFS-2054.07, PFS-2068, PFS-2068.04 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2031.02, PFS-2031.06 and PFS-2031.01 at 0.13.0 (GOAL-012): the suite is organized by tier, tier 1 plans and builds the tier-3 matrices without a solver, and the goal's checker is its own falsifiable command.

    A CI-runnable suite covers database integrity, emission
    validation including removed and renamed command scenarios,
    parser fixtures, golden scripts, and matrix reader equivalence.
    FlightStream itself is never required in CI.

!!! requirement "FR-25 Probe harness <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-03. Evidence: milestone M3; the committed compat
    reports and the promotion mechanism.*

    Read with PFS-2001.05, PFS-2003.06, PFS-2054, PFS-2054.09, PFS-2059 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2031.08 and PFS-2031.09 at 0.13.0 (GOAL-012): the action re-read probe runs as a row of the tier-3 matrix and writes its verdict into the command database, and the pyfs-qa study decides where the probe harness lives beside the workspace; PFS-2031.17 carries the decision, pyfs-qa physics reading the workspace, and PFS-2031.18 the unsteady actions design the probe confirmed.

    A probe harness runs per-command probe scripts on a licensed
    machine, asserts real effects, and promotes results into database
    statuses through committed compatibility reports.

!!! requirement "FR-26 Physics regression matrix <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-12, BRF-17. Evidence: milestones M4 onward; the
    banded-reference reports. Expansion (mesh refinement, solver-flag
    cases) queued for licensed sessions.*

    Read with PFS-2031.05, PFS-2031.07 and PFS-2031.09 at 0.13.0 (GOAL-012): the four physics cases become rows of the tier-3 matrices judged against the same references from the campaign products, every synthetic row carries a physical verification, and the pyfs-qa study puts the command's future to the owning seat.

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
    reference campaign uses the same per-coefficient shape, with
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

    Read with PFS-2056, PFS-2056.01, PFS-2056.10, PFS-2056.12, PFS-2057, PFS-2057.01, PFS-2057.02, PFS-2057.04, PFS-2057.05 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    The package stages inputs into the run folder, records their
    hashes in the manifest, collects outputs to declared locations,
    and provides archive and cleanup operations that refuse to touch
    folders whose manifest is missing or inconsistent.

!!! requirement "FR-29a A staged geometry is a link, not a copy <span class='srs-pending'>pending</span>"
    *Origin: the recorded run log of 2026-09-02, on finding a byte copy of
    every geometry under every point. Carried by PFS-2029.17. Evidence
    owed: the staging tests that node names.*

    Staging a geometry into a point's `inputs/` makes a directory
    junction on Windows and a symbolic link elsewhere rather than a copy;
    the manifest still records the opened path and its hash, so FR-29's
    promise about what ran is kept; a filesystem that refuses the link
    falls back to a copy and the record says so with the reason; and
    archive and cleanup treat the link as a link and never cross it.

    Measured 2026-09-02: `workspace/__init__.py:1272` stages with
    `shutil.copy2`, and production meshes are large enough that the
    workspace readme sends every saved simulation to cloud storage rather
    than to version control, so a copy per point is the cost the project met. The
    estate's own incident stands behind the last clause: a scan that
    crossed sixteen junctions reported more duplicate bytes than the tree
    held.

## Usage-feedback requirements (2026-07-22)

Requirements added from the first outside-the-repo use of
the public 0.2.0, through the five-stage triage process recorded in
the session records.

!!! requirement "FR-30 Entity labels <span class='srs-implemented'>implemented</span>"
    *Origin: usage feedback. Evidence: the v0.3 line; registry tests.
    The fsm-to-obj boundary inspector is
    <span class='srs-deferred'>deferred</span> behind a licensed
    probe (does the OBJ export write one named group per boundary?).*

    Read with PFS-2061, PFS-2061.02, PFS-2067, PFS-2067.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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

    Read with PFS-2062, PFS-2062.04 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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

    Read with PFS-2054, PFS-2054.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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

    Read with PFS-2056, PFS-2056.05, PFS-2056.08, PFS-2057, PFS-2057.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2034.01, PFS-2034.02, PFS-2034.03, PFS-2034.04 and PFS-2034.05 at 0.14.0 (GOAL-013): the row turns the mesh (`ROTATE`, a list of records in the order written, one row per angle), the setup defines the frames the row cites, the refusals name the cell, and the licensed seat run measures the rotated propeller on the solver.

    Read with PFS-2031.03, PFS-2031.04, PFS-2031.05, PFS-2031.06, PFS-2031.07, PFS-2031.12, PFS-2031.14 and PFS-2031.20 at 0.13.0 (GOAL-012): the tier-3 folder is a workspace, several matrices share it with their own plan, sweep and products under post/<matrix>/, every token the package defines is a row that plans offline and runs on the licensed machine, an executable override with no default version is refused naming the option, and the matrix identity of a campaign and a record is matrix_stem.

    Read with PFS-2031.21 at 0.18.1: A POL IS STATED ONCE IN THE WHOLE
    WORKSPACE. `plan` and `run` read every `*.fs` in the workspace root and
    the matrix being planned wherever it is, every row of each including rows
    with RUN = 0, and refuse with one message naming every repeated POL and
    every row stating it, because a POL names the simulation folder and the
    run ids of the one manifest. `pyfs-matrix plan --update-ids` rewrites the
    planned matrix alone, moving each repeated row to the next free POL above
    every POL, run record and simulation folder of the workspace; inside one
    matrix the first row stating a POL keeps it, and a row whose POL another
    matrix also states and which already has runs of the planned matrix is
    refused rather than moved.

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

The requirements below complete the Phase 4 acceptance batch.
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

!!! requirement "FR-22a Not-computed induced-drag sentinel <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-22, accepted 2026-07-27; deferred until
    0.27.0 (PFS-2006.03). Evidence:
    `tests/tier1_offline/test_pfs2006_declined_induced_drag.py` (a listed
    surface printed at zero is `NA` in the polar and named in a warning
    that reaches `post.log`, a surface off the list keeps its printed zero,
    and each recorded selection read one way).*

    A boundary without a user-defined trailing-edge condition, once
    assigned to the vorticity induced-drag list, returns a not-computed
    sentinel distinguishable from a physical zero.

    The sentinel is `NA`: a surface the run record puts on the list and
    whose printed `CDi` is exactly zero makes every sum the package
    computes over it `NA` -- the group's `CDI` and every axis column the
    export's x force reaches -- while the solver's Total row and the
    parsed per-surface value keep the printed number and a warning names
    the surfaces. The parsed coefficients stay plain floats, so there a
    printed zero and a value not computed are the same bytes; the list in
    the run record is what tells them apart, which is why the rule reads
    it.

!!! requirement "FR-22b Vorticity selection is an explicit input <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-22, accepted 2026-07-27. Evidence: the
    v0.3 line; solver-setup snapshot tests.*

    The vorticity induced-drag selection is an explicit solver-settings
    input, and leaving it unset is recorded in the solver-setup snapshot
    as the documented default, which is surface-pressure integration on
    every boundary.

    Read with PFS-2030.03.03 at 0.11.0, which lets the selection be
    written as family names in a setup and resolved through the
    geometry's inventory, as the reference scripts did. The default and
    its citation live in the command entry, where the database's
    validator sees them (PFS-2006.01).

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
    are read wherever a boundary is cited", at 0.14.0 (GOAL-013), the reference
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
    PFS-2035.13 asks, and it is a seat decision, so FR-59 is deliberately
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
    standard  convention, carrying the polar, the Mach, the angles
    and the advance ratio, and the record names the template that
    rendered each name.

!!! requirement "FR-33c Colliding output names are blocked before the run <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of FR-33, accepted 2026-07-27, giving the
    incident guard its own identifier. Widened 2026-08-19
    (OPS-2005.10.03, PFS-2011.02), by design decision. Evidence:
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
    in the destination folder from an earlier run. Neither refusal has an
    overwrite argument, deliberately, because the record either would
    replace is a run's evidence rather than a product a caller can choose
    to regenerate; the remedies are a per-point output name and an
    archived simulation, and both refusals name them.

    AMENDED AT 0.16.0 BY FR-92, which moves the folder and keeps both
    refusals. The destination is that point's own
    `sims/<sim>/datapoints/DP-<point>/`, not the `raw/` this sentence was
    written against nor the `outputs/` FR-84 renamed it to, so the second
    refusal below reads "already held from an earlier run OF THIS POINT".
    Two POINTS sharing a collected name are still refused, at plan time,
    and the reason moved with the folder: they no longer collide where
    they are collected, and they would collide in the product tree, which
    names a point's products after the loads file's stem.

    One rule in two shapes, because collection MOVES each output into
    `raw/` under its base name and both shapes end in one file where the
    manifest records two: the first would overwrite within a single call
    and the manifest would carry one name twice, the second would destroy
    evidence a previous point or run already collected.

    BOTH SHAPES ARE PRE-SCANS FROM 0.17.0, and this paragraph used to say
    they were not. The second was asked of each destination immediately
    before that file was moved, so a call whose third output landed on a
    held name refused with the first two already collected: sources gone,
    destinations written, no manifest record, and a recovery to do by
    hand. The sentence stated it as a property rather than a defect,
    because no record is destroyed either way, and said outright that
    making it a pre-scan too was an acceptance decision. That decision was
    taken on the GEO-039 triage. The whole destination set is now resolved
    before the first move, and the refusal names every held file rather
    than the first one it meets.

    NOTHING THAT SUCCEEDED BEFORE REFUSES NOW. What changed is only that a
    refusal leaves every byte on both sides where it was.

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
    *Origin: Phase 4 review, accepted 2026-07-27. Resolved
    2026-08-03. Evidence: `RunStatus.COMPLETED_MAX_ITER` and
    `RunStatus.FAILED_INCOMPLETE_OUTPUT` in `pyflightstream.workspace`, the
    judgment rules of `run.LoadsAssessor`, and the status tests in
    `tests/tier1_offline/test_run_campaign.py`.*

    A datapoint whose recorded residual does not reach the configured
    convergence threshold terminates with a status distinct from the
    CONVERGED status, even when the output footer is structurally
    complete.

    **THE RECORDED RESIDUAL WAS THE WRONG ROW UNTIL 0.16.0, so this
    requirement does not hold over manifests written before it.** The log's
    residual table is paged and the reader stopped at the first page, so a
    run that outlasted its first page was judged on the residual it held at
    that page's end. The consequence is not a wrong number but a wrong
    STATUS, which is what this requirement guarantees, and there is a
    measured instance: the point at `pfs0160/runs.json` recorded
    `COMPLETED_MAX_ITER` with `iterations: 100` and residual `1.256467e-05`,
    which is line 295 of its own log, while that log's last row is iteration
    206 at `1.3470951E-6`. The run converged at 206 and the manifest says it
    hit its cap. `COMPLETED_MAX_ITER` asserts the solver reached the
    iteration limit, and this one did not.

    The reader is fixed and the manifests are not rewritten, so the claim is
    scoped rather than withdrawn: it holds for a run whose status was
    recorded by 0.16.0 or later, and for an earlier one only where the run
    did not outlast its first page. Every affected log is on disk and a
    status can be re-derived from it; whether the affected manifests are
    re-derived or annotated is a seat decision and is not taken here.

    **Restated 2026-08-03, and the restatement is the requirement.** It
    read "distinct from a completed one" until the review pass measured
    that the delivered value is `COMPLETED_MAX_ITER`, whose name says
    completed, so the requirement was being closed under a reading
    rather than as written. The design decision was to keep the six
    statuses; the honest consequence is that the requirement says what
    the library guarantees, which is that a run failing its threshold
    never wears the status that means it met it. The disclosed
    restatement is recorded in the
    [requirement mapping](../requirement-mapping.md), which is this
    project's own convention for exactly this.

    **Resolved on 2026-08-03: the six values stand and
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

    Read with PFS-2070, PFS-2070.04 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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
    to v0.5 on 2026-08-04 with the measurement taken first
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
    option name is a stable public contract, which is the form the decision
    took against the review's recommended narrowing.

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
    home and guarded there. The CONFORMING half is decided by RPT-063
    (0.27.0, OPS-2011.01): each family is scored against the solver's own
    recorded output or published as not scored. Scored: the body-axis
    forces, the wind-axis drag and the stability and wind lift of the
    emitted polar row, against 48 recorded loads exports
    (`tests/tier1_offline/test_goal028_axes_recorded_exports.py`), and the
    body-rate sense against the recorded rate probes
    (`tests/tier1_offline/test_ops2011_rate_sense_against_recorded_probes.py`,
    all three axes since G13 of 0.27.0 gave roll and yaw their own sign;
    until then they read reversed). Not
    scored, each waiting for a recorded export that could tell a right
    sign from a wrong one: the stability- and wind-axis moments and side
    force, the rotor coefficients, the sectional loads, the unsteady
    history and the far field. The conventions entry "Axes and signs of
    every emitted coefficient" says the same, per family.*

    Read with PFS-2062, PFS-2062.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2028.09 at 0.14.0 (GOAL-013): the sense of rotation derived into the reference of the recorded campaign is for the domain seat to confirm, and it is asked in writing rather than decided.

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

    Read with PFS-2070, PFS-2070.04 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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
    *Origin: the C4 acceptance, 2026-07-27, taken in the FULL-contract
    form against the review's own recommendation of a narrower one.*

    Read with PFS-2054, PFS-2054.03, PFS-2055, PFS-2055.01, PFS-2055.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    The package provides one documented console entry point per
    operational concern, and their commands and flags change only
    under the deprecation policy of NFR-20.

    Pending, and precisely: every entry point exists and is
    exercised, so the first half ships. The second half is the one the owning seat
    strengthened, and nothing enforces it. NFR-20 is itself pending and
    does not bind before 1.0, so today a CLI flag can change with only
    a changelog line behind it. An earlier draft of this box wrote that
    weaker form, and that option was declined.

!!! requirement "FR-45 Strict manifest record <span class='srs-implemented'>implemented</span>"
    *Origin: the C5 acceptance, 2026-07-27. Evidence: both halves
    pinned in `tests/tier1_offline/test_workspace.py`, the unknown-field refusal by a
    test added with this consolidation after review found the clause
    resting on a model-config line no assertion observed.*

    Read with PFS-2056, PFS-2056.01, PFS-2056.02, PFS-2056.03, PFS-2056.04, PFS-2056.06, PFS-2056.10, PFS-2057, PFS-2057.02, PFS-2057.04, PFS-2058, PFS-2058.01, PFS-2058.02, PFS-2058.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2033.02 at 0.14.0 (GOAL-013): the strict record gains two fields, `raw_commands` and `aliases` (the setup's boundary aliases, the design decision of 2026-09-09), and the manifest schema stays at 3 because an absent key reads as empty.

    The manifest record rejects unknown fields and duplicate run
    identifiers; its field set is fixed and validated at construction.

!!! requirement "FR-46 Closed terminal-status set <span class='srs-implemented'>implemented</span>"
    *Origin: the C6 acceptance, 2026-07-27. Evidence: the member set
    of `RunStatus` pinned in `tests/tier1_offline/test_workspace.py`, added with this
    consolidation; using the members, which the campaign tests do, does
    not notice an addition.*

    Read with PFS-2056, PFS-2056.11 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Every executed point terminates in exactly one value of a closed
    set of six status values, and a seventh cannot be introduced
    silently.

    Read with FR-37, which was closed as covered by this set on 2026-08-03: this set stays closed at six and FR-37 was restated to ask for a status distinct from CONVERGED, which two of these six give.


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

## The workspace interface specified (2026-09-02)

The requirements below were derived on 2026-09-02 from two sources read
side by side: the reference driver for the reference campaign, which
ran a matrix with no mandatory input, exported eight kinds of file per
point and wrote the reference plot-format products afterwards; and the 0.10.1
tree, pre-flighted on the reference rows with zero solver time and diffed against
the scripts that produced the recorded results. Each requirement names
the planning nodes that carry it, so the plan points here and this page
points back. The wordings are preserved verbatim in the coordination
record `RSH-HND-040` and its appendix; the measurements are on the
nodes.

!!! requirement "FR-50 A matrix runs with no mandatory command-line input <span class='srs-pending'>pending</span>"
    *Origin: feedback item #1 of 2026-09-02, no input is to be mandatory here. Carried by PFS-2029.01, PFS-2029.02, PFS-2029.03
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
    *Origin: the recorded run log of 2026-09-02 and the reference driver,
    which exported eight kinds per point and named every file for the
    point it came from. Carried by PFS-2029.14 and its children,
    PFS-2029.18 and PFS-2029.19 and its children. Evidence owed: the
    export goldens and the script-parity arm of GOAL-011.*

    Read with PFS-2064, PFS-2064.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2031.18.01 and PFS-2034.05 at 0.14.0 (GOAL-013): the stamped per-step exports of a windowed point are tabled as a series under the matrix's products, and the licensed seat run reads them for the rotated propeller.

    Every point of a workflow campaign leaves, beside the loads table and
    the log it leaves today, the saved simulation, the tecplot export, the
    surface sections, the surface sectional loads and the probe points,
    and an unsteady point additionally its unsteady plots; the sections,
    sectional loads and probe points are updated and computed before they
    are exported, so no export is of a previous state; the saved
    simulation is written first, as the reference driver did; a
    post-processing artifact may deselect a kind; a kind whose command
    carries no row on the row's build is refused at pre-flight naming the
    build; and every export is named after the point in the reference
    convention, `POLAR-{pol}_M{mach}AL{alpha}BE{beta}` with a `J{ratio}`
    suffix for a rotor point, so two rows differing only in Mach or in
    advance ratio never render one name.

    Measured 2026-09-02: the 0.10.1 builders emit `EXPORT_LOG` once and
    `EXPORT_SOLVER_ANALYSIS_SPREADSHEET` at six sites and nothing else
    (`grep -c EXPORT_ src/pyflightstream/cases/workflows.py`); the
    default point name `a+00.0_b+00.0` carries the angles alone. Every
    export command the reference driver emits carries a row on 26.120 and
    on 26.123 in the command database, six of them verified.

    AMENDED 0.27.0 (G04), pending with it: a steady point also saves the
    solver's own residual and load plots, and its section Cp plot where
    the post-processing artifact declares sections, each chosen with
    `SET_PLOT_TYPE` and saved with `SAVE_PLOT_TO_FILE` after the other
    exports and before the log, named for the point
    (`_plot_residuals.txt`, `_plot_loads.txt`, `_plot_cp_sections.txt`),
    collected and hashed like every export and never read as a source of
    a coefficient; the artifact may deselect each; an unsteady point
    saves the same plots once after the march, never per step, and an
    artifact stating one on an unsteady row is accepted (FR-133; the code:
    `cases/__init__.py:default_outputs` leaves out of an unsteady point
    only `STEADY_ONLY_EXPORT_KINDS`, which holds `probes` alone, and
    `cases/workflows.py:END_OF_RUN_EXPORT_KINDS` saves the plots once at
    the end of the run). Measured on 26.124 (RPT-067): the files are the plotted
    series as text, and the solve and its exports are unchanged by the
    saves.

    AMENDED 0.27.0 (G10), pending with it: the artifact may opt a row of
    any run type into the per-panel force distribution of every surface
    (`force_distributions`, `_force_distributions.txt`), off by default as
    the VTK and CSV surface exports are, and exported once at the end of
    the run, never by an unsteady row's per-step exports.

!!! requirement "FR-52 Post-processing is declared in the pproc artifact and runs as part of the campaign <span class='srs-pending'>pending</span>"
    *Origin: feedback item #3 of 2026-09-02 and the design decision of the
    same day that the groups artifact becomes `pproc`, and the reference
    clarification that post-processing means both the data treatment and
    the files and data types available. Carried by PFS-2029.07 and its
    children, PFS-2029.15 and its children, and PFS-2029.16. Evidence
    owed: the tests each node names and the offline parity arm of
    GOAL-011.*

    Read with PFS-2063, PFS-2063.01, PFS-2063.02, PFS-2065, PFS-2065.01, PFS-2066, PFS-2066.01, PFS-2070, PFS-2070.05 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2031.18.01 and PFS-2015.04.01 at 0.14.0 (GOAL-013): the series tables join the products beside the reductions, and the blade count of a sector is read from `PERIODIC_COPIES` when `BLADES` is absent, so the per-blade reductions of the reference isolated propeller are written.

    Read with PFS-2005.10, "an empty pproc group is every family, the verdict on the question PFS-2005.02 left to the domain seat", PFS-2005.04.01, "boundary aliases live in the setup and are read wherever a boundary is cited", and PFS-2029.07.04, "a pproc families entry may be a bare word", at 0.14.0 (GOAL-013), the design decisions of 2026-09-09: an empty `[groups]` entry is every family the geometry carries; a `[groups]` member or a `families` entry may name an alias the row's setup defines, read as FR-30c states it; and a `families` entry may be a bare word, read as a selector, then as an alias, then as a family name, while an entry's `frame` may name a frame the setup defines or, on a row with several rotors, that rotor's own.

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
    modules and nothing on the run path reaches them. The reference driver
    read a post-processing table off the same module as the solver setup
    and wrote the reference products after every polar.

!!! requirement "FR-53 The reference campaign reproduces through the workflow scheme <span class='srs-pending'>pending</span>"
    *Origin: the instruction of 2026-09-02: the work does not stop until selected recorded runs
    are reproduced EXACTLY, end to end and post-processing included, and the
    clarification that the
    guarantee the requirement asks is that exactly the same post-processing is
    produced. Carried by PFS-2030.01 to PFS-2030.07, under PFS-2030. Evidence owed:
    `GeoversePlan/goals/check_goal_011.py`, item one of GOAL-011.*

    Read with PFS-2028.08 at 0.14.0 (GOAL-013): the installed full model of the reference record is one row whose symmetry, rotation sign and moving boundaries are asked in writing and run on the licensed seat.

    One recorded point per registered run type of the reference
    campaign, run on the solver build that produced the record, is
    reproduced by a workspace the package plans with nothing on the
    command line: the emitted script differs from the recorded script only
    on an enumerated allow-list of paths, comments, scene verbs and
    edition grammar; the run leaves the same export set under the same
    names; the package's post-processing, fed the recorded
    exports, writes the reference plot-format products equal to the recorded ones except the
    timestamp line; and the reproduced loads are compared coefficient by
    coefficient against the recorded ones with the solver's own measured
    repeatability as the arbiter of any difference.

    The reference set is machine-local, because the folder that holds it
    carries an identifier the content guard refuses in versioned files:
    the checker reads its root from `GeoverseSetup/local/reference_runs.json`
    and prints NOT YET naming that file when it is absent. The build is
    26.120, FlightStream 26.1 build #7012026, read off the recorded loads
    tables and matched to `commands/_meta.yaml` on 2026-09-02. The seat
    cost is five solver executions, authorised by the owning seat on
    2026-09-02: three selected points and two controls.

!!! requirement "FR-54 Every solver setting a reference script states has a home and reaches the script <span class='srs-pending'>pending</span>"
    *Origin: the script diff of 2026-09-02 between the 0.10.1 pre-flight
    of the reference rows and the recorded scripts. Carried by PFS-2030.02,
    PFS-2030.03 and its four children, and PFS-2028.05 on the design decision of
    2026-09-02. Evidence owed: the tests each node names.*

    Read with PFS-2064, PFS-2064.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    A matrix row can state the fluid constants its writer pinned
    (density, viscosity, sonic velocity, temperature, pressure) as
    flight-condition keys that override the standard atmosphere and are
    recorded as pinned; every builder states the reference velocity, the
    sideslip and the initialisation flag on the opened simulation; the
    reference artifact's moment point becomes the analysis loads frame and
    the moments model is stated, both before the solver starts, so the step
    exports an unsteady row writes during the march carry them (RPT-064);
    a setup's vorticity-drag families resolve
    through the geometry's inventory; significant digits and the wake
    termination in time steps have emitters; and a setup that states
    `symmetry_loads` emits it as stated, an absent key remaining
    recorded-only and warning as before.

    Measured 2026-09-02: the verbs only the reference scripts emit, beyond
    the export block, are `SET_ANALYSIS_SYMMETRY_LOADS`,
    `SET_SOLVER_ANALYSIS_LOADS_FRAME`, `SET_ANALYSIS_MOMENTS_MODEL`,
    `SET_SIGNIFICANT_DIGITS`, `SOLVER_SET_REF_VELOCITY`,
    `SET_VORTICITY_DRAG_BOUNDARIES`, `SOLVER_SET_SIDESLIP`,
    `LOAD_SOLVER_INITIALIZATION DISABLE` and, on the no-rotor unsteady
    run, `SET_WAKE_TERMINATION_TIME_STEPS`; the fluid state differs in the
    fourth digit because the reference scripts pin viscosity 1.789e-5 and sonic
    velocity 340.29 where the package derives both from the standard
    atmosphere. The consequence of the first verb is already measured: the
    isolated-rotor row of the 0.10.1 reproduction workspace reported loads
    six times the recorded value, the periodic copy count, because the reference setup
    stated the symmetry loads off and the package emitted nothing.

    AMENDED 0.27.0 (G09), pending with it: a setup may select the
    families that enter the loads (`analysis_families`, resolved like the
    other family lists), the unit the loads table prints (`load_units`,
    one of the tokens `SET_LOADS_AND_MOMENTS_UNITS` takes, refused when the
    preset is read otherwise) and the inviscid loads (`inviscid_loads`),
    each emitted after `START_SOLVER` and before the exports of every
    point of a steady row; a row of an unsteady run type stating any of
    them is refused at plan; and a point whose loads table is not in
    coefficients writes no product row, the post stage naming the unit.

    AMENDED 0.27.0 (G14), pending with it: a setup may state the vorticity
    lift model (`vorticity_lift_model`, every run type) and the step at
    which an unsteady run couples its boundary layer
    (`unsteady_viscous_coupling_iteration`, the unsteady run types, refused
    on a steady row), each emitted before `INITIALIZE_SOLVER` and validated
    against the command database for the row's build, so a build that does
    not carry the command refuses the row at plan naming the build; 26.124
    answers both names as unrecognized (RPT-068), and a setup stating the
    lift model beside `kutta_joukowski_lift` is planned with a warning.

!!! requirement "FR-55 A row states its geometry as a file, and the geometry carries its own boundary inventory <span class='srs-pending'>pending</span>"
    *Origin: feedback items #2 and #6 of 2026-09-02. Carried by
    PFS-2029.06 and its children, PFS-2029.09 and its children, and
    PFS-2029.10. Evidence owed: the tests each node names. AMENDS FR-33a's
    resolution of a geometry by stable id, and the acceptance sentence of
    PFS-2009.01, in the same change.*

    Read with PFS-2059, PFS-2059.01, PFS-2060, PFS-2060.01, PFS-2061, PFS-2061.01, PFS-2067, PFS-2067.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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

    AMENDED 0.27.0 (G01), and pending acceptance as the requirement it
    amends is. The builders no longer refuse every mesh file: a raw mesh
    (`.obj`, `.stl`) is imported in the length unit the `[import]` table
    of its sidecar states (`units`, one of the units `IMPORT` takes on the
    row's build), into a simulation whose length unit is metres, the unit
    of every length the reference and the row state; a raw mesh whose
    sidecar states no such table is refused before any seat is spent,
    naming the table, the key and the sidecar, and naming no release; a
    saved simulation whose sidecar states one is refused; the raw mesh's
    boundary inventory is the sidecar's `boundaries`, written by hand in
    the file's order, since the file carries no mesh block to read it
    from; and the run record carries the table as `mesh_import`. Whether
    `IMPORT` converts the file's unit into the simulation's is not
    measured on any build. The clause above is left standing, as a
    requirement records what was believed when it was written.

    AMENDED 0.27.0 (G03), pending with it: the same table declares the
    mesh operations of the import, `[[import.operations]]` (scale,
    rename, mirror joined to its source, translate in the table's unit,
    rotate), applied in the order written right after `IMPORT`, in the
    reference frame, each citing a surface by the file's name or by the
    name an earlier rename gave it and never by position; an order the
    script's phases cannot emit is refused naming both operations, never
    reordered; and the boundary inventory a row cites is the sidecar's as
    the renames leave it.

    AMENDED 0.27.0 (G02), pending with it: the same sidecar declares the
    raw mesh's trailing edge in a `[trailing_edges]` table, and a raw mesh
    whose sidecar declares none is refused before any seat is spent. The
    default route is `file`, a points file of trailing-edge mesh-edge
    mid-points under a unit line, checked against the mesh at binding,
    converted to the simulation's metres and imported with
    `IMPORT_WAKE_EDGES_FROM_FILE` on 26.124, the one build it was measured
    on, other builds being refused; a row on that route declares its solver
    log among its outputs, and the run is recorded `FAILED_SCRIPT` when the
    count the solver logs as imported differs from the points written.
    Detection (`detect = "auto"`, or by surface with an optional sweep
    angle) applies only when written, and a table stating both routes or
    neither is refused. `[wake_termination]` (automatic or by surface) and
    `[base_regions]` (automatic) apply only when written, the first
    unverified on every geometry tried; and a saved simulation whose
    sidecar states any of the three tables is refused.

    AMENDED 0.27.0 (RPT-066), pending with it: the families a row or
    artifact names for base-region detection are the boundaries that
    become the base regions, never the body that carries them, because
    `DETECT_BASE_REGIONS_BY_SURFACE` given the body's own boundary marks
    nothing and says nothing; the key's page states it.

    This reverses a rule the 0.10.1 library defends in four arms at
    `workspace/matrix.py:566-637`, which is why it is a minor release and
    why the migration of every shipped matrix travels with it.

!!! requirement "FR-56 The reference artifact states only what rows share, with one length per quantity <span class='srs-pending'>pending</span>"
    *Origin: feedback items #4 and #5 of 2026-09-02. Carried by
    PFS-2029.05 and PFS-2029.08. Evidence owed: the tests each node names.*

    Read with PFS-2028.09 at 0.14.0 (GOAL-013): the sign the reference's derived rotation produced for the reference rows is for the domain seat to confirm.

    The reference artifact carries the rotor diameter and no radius,
    refusing a file that states both with values that disagree; and it
    carries no `blade_travel`, `rotation`, `rpm_sign_installed` or
    `rpm_sign_isolated`, because the hand of a rotor is a property of the
    mesh a row opens and is stated in the row, a file still carrying them
    being refused naming the row keys.

    AMENDED 0.22.0, and it is the REASON that was amended rather than the
    rule. The four named fields are still absent from the reference and are
    still refused, because each named a CONFIGURATION -- installed against
    isolated -- which is not a property reference data several rows share.
    But "the hand of a rotor is stated in the row" is no longer true: it is
    `rpm_sign` on that ROTOR's own block, which is per-rotor rather than
    per-configuration and so answers the case the four fields were reaching
    for. See FR-60 and FR-61. A row states the hand only where it names no
    rotor block. This clause is left standing rather than rewritten because
    a requirement records what was believed when it was written; the
    amendment is where the correction lives.

    Measured 2026-09-02: `rotor_diameter_m` is read at
    `cases/workflows.py:832`; `radius_m` is required at
    `workspace/inputs.py:299` and read by no emitter; the four rotor
    fields at `:306-308` appear in no emitter.

!!! requirement "FR-57 A row states as many rotors as the study has <span class='srs-pending'>pending</span>"
    *Origin: feedback item #4 of 2026-09-02, the multirotor syntax.
    Carried by PFS-2029.11 and its children. Evidence owed: the tests each
    node names.*

    Read with PFS-2028.08 and PFS-2015.04.01 at 0.14.0 (GOAL-013): the installed model's row is for the owning seat to state, and a sector meshed as one blade takes its blade count from its periodic copies.

    A matrix row states its motions as a list of records in one cell, each
    record carrying its moving boundaries, its rotor speed sign, its axis
    and its origin point, the cell parser reading one level of nesting; a
    row with the flat single-motion keys of 0.10.1 reads unchanged; each
    motion creates its own fixed frame at its named point and its own
    moving frame that follows it, with its own motion block in the script;
    and a reference point declares that it is a rotor point explicitly,
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
    point, and the design of 2026-09-10 moves all four OUT of the record and
    into the reference's rotor block, so the row states an alias and nothing
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
    identifier. The three cost different things and choosing is a
    seat decision, asked in writing on 2026-09-10. Until the owning seat answers the marker
    stays, and this paragraph is what a reader meets beside it.

!!! requirement "FR-58 The fluid constants of a campaign have one home <span class='srs-implemented'>implemented</span>"
    *Origin: the instruction of 2026-09-04: work from default values, so
    that they need not be entered in the matrix and can live in the setup
    artifact instead. Carried by PFS-2030.08. Evidence:
    `tests/tier1_offline/test_flight_condition.py` (the resolver, its refusals and each
    refusal's own reason), `tests/tier1_offline/test_matrix_run.py` (the file, the record
    the run layer writes, and the equal-render arm below), scored against
    nineteen mutants with an unmutated control.*

    Read with PFS-2054, PFS-2054.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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

    Measured 2026-09-04: the reference three reproduction rows each repeat the
    same four constants, and the reference thirteen-point polar would repeat them
    thirteen times; the package's own sea-level atmosphere gives viscosity
    1.7892976260350732e-05 and sonic velocity 340.293988026089 where the reference tool
    states 1.789e-5 and 340.29, so the pins cannot be dropped in favour of the
    standard atmosphere. Those two figures are
    RE-MEASURED by
    `tests/tier1_offline/test_atmosphere.py::test_the_sea_level_state_is_stated_to_the_digit_the_srs_quotes`
    rather than left as prose: a full-precision literal that nothing pins goes
    silently false the moment a floor constant moves.

## The rotor vocabulary the design of (2026-09-10)

Fourteen requirements from one design, written out as a use case
workspace before a line of it was built, which the reviewed use case
and changed at every reading. The nineteen leaves
of PFS-2035 are that design one decision per node, and the requirements below
are those decisions stated as behaviour. The reference sentence of that night defines
the release around them: the use case is what defines the scope of 0.15.0.

The shape they share, and the reason the set is worth reading as one: **a
study's vocabulary lives in the reference, a row states which of it moves and
at what operating point, and the mesh says what was actually meshed.** Every
requirement below is one seam of that division.

!!! requirement "FR-59 The reference holds the vocabulary of a study's boundaries <span class='srs-implemented'>implemented</span>"
    *Origin: the design decisions of 2026-09-09 and 2026-09-10, "todos os aliases vao
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
    `[aliases]` table of 0.14.0 is REFUSED when a row binds it, naming the
    reference to move it to. This paragraph promised a warning and a 0.17.0
    removal until the instruction of 2026-09-10; the refusal is
    what the package does.

    AMENDED BY FR-73, "A run chooses whether a family the mesh does not
    carry is a skip or a refusal": ignoring a member the opened mesh does
    not carry is the DEFAULT from 0.15.0 rather than the only reading, and
    `--ignore-missing-families false` turns it into a refusal on a
    post-processing `families` selection.

    Only `all` and `each` remain the package's own words. `airframe`, `blades`
    and `blade_pattern` leave, because a study declares its own names and a
    built-in word that means one thing to the package and another to the
    owning seat is the defect this requirement removes.

    Why the reference and not the preset: a boundary name is not a solver
    setting. A preset is per condition and a reference is per configuration,
    and the words a study uses for its own geometry belong with the
    configuration.

!!! requirement "FR-60 A rotor is one rotor block of the reference, and the block is its alias <span class='srs-implemented'>implemented</span>"
    *Origin: the design of 2026-09-10. Carried by PFS-2035.02 and PFS-2035.16.
    Evidence: `tests/tier1_offline/test_reference_vocabulary.py` (the block, the blade count, the union the name stands for, and every refusal it carries). Commits f0032d3 and 45b9b6b.*

    A block of the reference whose `kind` is `rotor` declares one rotor: its
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

    THE RULE PFS-2035.02 STATED WAS NARROWER AND WOULD HAVE REFUSED THE REFERENCE OWN
    STUDY, and it is corrected here rather than quietly widened. The node
    said a name is refused when it ENDS IN A DIGIT, "because a number after a
    radical always means a blade", which was true of the frame names of
    0.14.0 (`ROTOR_MRP<k>`, `BladeAxis<k>`) and is not true of these. A
    rotor's frames are `<ALIAS>_SMRP`, `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>`,
    so the number sits after `RMRP` and never after the alias, and no two
    distinct aliases can produce one frame name. Measured 2026-09-10 against
    the use case the reviewed use case: eight of its ten blocks are named
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
    field is worth keeping at all is a seat decision open question.

    The campaign's propulsor count is therefore the number of rotor blocks,
    rather than the point kind and its `ERP`/`ARP` fallback that answer it
    today (0.11.0, PFS-2029.11.02).

!!! requirement "FR-61 A row names a rotor by its alias and states nothing else about it <span class='srs-implemented'>implemented</span>"
    *Origin: the design of 2026-09-10: `MOVING_BOUNDARIES` becomes `MOVING_BC_ALIAS`. Carried by PFS-2035.03. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py`, where the alias moves that rotor's
    boundaries, an unknown alias is refused naming the rotors the reference
    does declare, and a record stating both spellings is refused; commit
    45b9b6b.*

    `MOVING_BC_ALIAS` names a rotor block of the row's reference and is the
    only rotor identity a motion record carries. `MOVING_BOUNDARIES`,
    `ROTOR_AXIS`, `ROTOR_ORIGIN`, `RPM_SIGN` and `BLADES` are what it
    replaces, because the reference states each once; a record stating any
    of them BESIDE the alias is refused naming both, and a record stating
    them without an alias is read as it always was, which is what keeps
    every row written before this release working. They are removed at
    0.17.0.

    AMENDED 0.22.0, and the amendment is the whole of what the reference
    declaring the hand is FOR. `RPM_SIGN` is the reference's, and it reaches
    the row's view for EVERY speed form: a row's `RPM` is a MAGNITUDE and a
    negative one is refused by name, so the row says how fast and the block
    says which way. Until 0.21.1 the hand was filled only when the row stated
    no speed of its own, so a row stating rev/min turned whichever way its
    number was written and the reference's hand was dropped in SILENCE -- no
    refusal, no warning, and a rotor turning backwards converges and reports
    numbers. The point's NAME writes `RPM` in magnitude for the same reason:
    the hand belongs to the rotor and naming it in the point would give one
    operating point two identities. Evidence:
    `tests/tier1_offline/test_workflows.py` (the stated speed taking the
    rotor's hand, and the negative row refused).

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

    A cell naming an alias the reference does not declare as a rotor is
    refused at plan time, naming the alias and the rotors the reference does
    declare.

!!! requirement "FR-62 The frames a rotor instantiates take its alias as their radical <span class='srs-implemented'>implemented</span>"
    *Origin: the design of 2026-09-10, "<ALIAS>_SMRP para o eixo local
    estatico e <ALIAS>_RMRP para o eixo rodando junto com o movimento".
    Carried by PFS-2035.04, absorbing PFS-2029.21. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py`, where the frames take the radical, the blade
    frames TURN with the blades, a record naming no rotor keeps the 0.14.0
    names, and a blade the mesh lacks gets no frame while the count stays;
    commits 6288aaf and 927ef8b.*

    A rotor creates `<ALIAS>_SMRP` at its hub, static; `<ALIAS>_RMRP` turning
    with the motion; and `<ALIAS>_RMRP<k>` per blade of `families_blades`,
    turning with blade k and numbered from the `blade1` datum. A family of
    `families_general` has no local axis of its own: its local frame IS the
    rotor's, `SMRP` when static and `RMRP` when turning.

    `ROTOR_MRP<k>`, `RotorAxis<k>` and `BladeAxis<k>` are the names these
    replace, and a post-processing entry citing them is REFUSED, naming the
    replacement. This paragraph said "read with a deprecation warning until
    0.17.0" until the instruction of 2026-09-10: an old spelling is to
    RAISE, with a message saying which name it became and how to correct
    it. This package has no stable release, so it
    owes no compatibility window for a word it chose badly. The refusal
    arrives when the ROW is built, at `plan`, because which frames exist is
    a question about the row.

    This is what makes a multirotor row possible at all: the frame names carry
    the rotor's identity, so nine rotors instantiate nine sets rather than
    colliding on one radical.

!!! requirement "FR-63 The rotor speed lives in the motion record, resolved against that rotor's own diameter <span class='srs-implemented'>implemented</span>"
    *Origin: the design of 2026-09-10 and the reference reminder of the same night, "a
    razao de avanco vira RPM usando o diametro de cada rotor". Carried by
    PFS-2035.05 and PFS-2035.18. Evidence: `tests/tier1_offline/test_rotor_by_alias.py::test_one_ratio_gives_two_rotors_two_speeds_when_their_diameters_differ`, which asserts the two speeds are in the inverse ratio of the diameters. Commit 45b9b6b.
    AMENDS FR-56, "The reference artifact states only what rows share, with
    one length per quantity", whose single `rotor_diameter_m` is the
    advance-ratio length today.*

    Read with PFS-2066, PFS-2066.02, PFS-2070, PFS-2070.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    A motion record states `RPM` or `ADVANCE_RATIO`, never both and never
    neither, refused PER ROTOR with the message the row-level refusal carries
    today.

    An advance ratio is resolved rotor by rotor, against the `diameter_m` of
    the rotor block the motion names: `n = V / (J * diameter_m)` and
    `rpm = 60 n`, with `V` the freestream speed of the flight condition. One
    ratio therefore yields a DIFFERENT speed per rotor whenever the diameters
    differ, which is what a row of eight 1.20 m lifters and one 1.80 m pusher
    needs. A motion whose block states no `diameter_m` is refused at plan
    time naming the block, the row and the key, because there is nothing to
    resolve against.

    The top-level `rotor_diameter_m` of the reference therefore stops
    being the advance-ratio length: it is one number for a whole
    configuration, and a second rotor of another size cannot be resolved by
    it.

!!! requirement "FR-64 Every rotor row names the motion that owns the clock <span class='srs-implemented'>implemented</span>"
    *Origin: the design of 2026-09-10, "o setup temporal exige qual o
    movimento de referencia". Carried by PFS-2035.07. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py` (the clock follows the named
    motion and not the fastest; a row stating a `MOTIONS` list without the key
    is refused naming the motions it could choose; the flat pre-0.15.0 form is
    exempt) and `tests/tier1_offline/test_reduce_by_rotor.py`. Commit 91a7302
    and the decisions commit that made the key required. TWO OF THE REFERENCE
    DECISIONS OF 2026-09-10 CHANGED THIS TEXT, and both are recorded in
    `GeoversePlan/coordination/decisions/DEC-010`.*

    `CLOCK_MOTION` is a cell key, REQUIRED on every row that states a
    `MOTIONS` list, and it names a motion the same row states. The time step
    and the run length are that motion's.

    `rotor_speed` KEEPS ITS NAME. The draft of this requirement renamed it
    `rotor_speed_ref`; asked, the decision was to leave it, and the rename is
    struck rather than deferred.

    THE SCOPE IS THE `MOTIONS` LIST AND NOT EVERY ROW WITH A MOTION, which
    is the second decision and it was taken with the consequence measured in
    front of the reference. The list is the 0.15.0 vocabulary and it is where a row
    has something to choose between; the flat pre-0.15.0 form names one
    rotor in its own keys, has nothing to choose, and is how the reference
    case 9001 is written. Refusing that row would have cost the comparison
    that release rests on to buy a key that decides nothing.

    A row that states a `MOTIONS` list and no key is REFUSED, naming the
    motions it could have named. Before this release the clock followed the
    fastest rotor by the package's own arithmetic, which is an inference nobody
    wrote   down; a declaration replaces it.

    Measured 2026-09-10, before the refusal was built: `_clock_speed` in
    `cases/workflows.py` read `fastest = max(speeds, key=lambda each:
    abs(each.rpm))`, and nothing in the row said which rotor that was. The
    locator is the SYMBOL and not a line number, because this release moved
    that statement by about fourteen hundred lines and a bare number in a
    requirement decays on every edit (the verification lens of 2026-09-10).

!!! requirement "FR-65 The frame decides how a post-processing entry expands <span class='srs-implemented'>implemented</span>"
    *Origin: the design of 2026-09-10 and the reference spinner decision of the same
    night. Carried by PFS-2035.08, absorbing PFS-2029.20. Evidence:
    `tests/tier1_offline/test_pproc_by_frame.py`, which reads the rule off
    the model (an entry in a rotor frame is one per rotor, one in the local
    axis is one per blade, one in a common frame is one, the placeholder is
    present exactly when there is more than one emission, `each` stays and
    `each_blade` is refused) and ends by validating, WHERE THE WORKSPACE IS ON
    THE MACHINE and skipping with that reason where it is not, which is
    every clone and every CI run, THE REFERENCE OWN
    `pfs0150/inputs/pproc/p010.toml`, which is the file the requirement was
    written from. Measured 2026-09-10: with the rule in place the reference two
    matrices plan 39 points with none blocked, where the artifact would not
    validate at all before it.*

    An entry citing `MRP` or a frame the reference declares emits ONCE over
    the whole cited set, and a rotor name in that set is its own union, so a
    propulsor's total carries its hub and spinner with its blades. An entry
    citing `SMRP` or `RMRP` emits one per ROTOR, in that rotor's frame. An
    entry citing `LOCAL_AXIS` emits one per BLADE, in that blade's frame, plus
    one for the rotor's general families, which ride the rotor's own frame.

    There is no `expand` key: the frame already says it. `each` stays, because
    one emission per family in a common frame is a reading no frame implies;
    `each_blade` is REFUSED, naming `frame = "LOCAL_AXIS"`. `{family}`
    is the only placeholder and means WHAT THE EMISSION IS ABOUT: the alias on
    a per-rotor entry, the blade's label on a per-blade one, the family on an
    `each` one.

    An entry citing `LOCAL_AXIS` over a set holding no rotor OF THE
    REFERENCE is refused at plan time, naming the entry, the set and the
    rotors the reference declares. It is a writing error rather than a
    configuration difference: unlike an entry that resolves to nothing, it
    cannot come right on another mesh.

    THE OTHER HALF OF THAT SENTENCE, which the implementation forced and
    which is the line the two cases fall on: an entry whose rotors the
    reference DOES declare, but whose frames THIS RUN did not place, is
    LEFT OUT with a warning, exactly as an entry whose families the
    geometry lacks is. A steady row places no rotor frames and a row that
    turns only the lifters places no pusher frames, and one artifact serves
    all three; that entry comes right on the next row, which is precisely
    what the refused one cannot do. Measured 2026-09-10 on the reference
    workspace: the distinction is 19 of the reference 39 points.

    THE SAME RULE REACHES THE SECTIONS AND THE PROBES, through one helper
    rather than three: a distribution measured in a blade's own axes is one
    per blade, and a probe table naming one rotor's frame is left out on a
    row that does not turn that rotor.

    A probe table's `rotor_radius` is the radius OF THE ROTOR WHOSE FRAME
    IT NAMES. That question had no answer before this release, because the
    reference carried one diameter for the whole configuration; it carries
    one per rotor now (FR-60), and reading the configuration's would lay a
    lifter's probes out over a pusher's disk without saying so. The word
    was `propeller_radius` and is REFUSED, naming `rotor_radius`.

!!! requirement "FR-66 A row may state the symmetry-loads flag, overriding the preset with a warning <span class='srs-implemented'>implemented</span>"
    *Origin: the design decision of 2026-09-10: it is worth promoting to a flag, and the matrix
    keeps carrying it. Carried by PFS-2035.09. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py`, where the row overrides the preset and warns,
    agreeing warns nothing, and a value that is not a yes or a no is refused;
    commit 91a7302.*

    `SYMMETRY_LOADS` is a row key registered on every run type. A row stating
    it overrides the preset's value and warns, naming both files and the value
    used; a row stating nothing inherits the preset silently, as today.

    Whether the solver reports the loads of the meshed sector or of the whole
    wheel is a per-row choice, because the same preset serves a sector row and
    a full-wheel row. The override warns rather than refusing, which is a seat decision
    second answer of that hour: the first was to refuse both stating it, as
    the rotor speed is refused.

!!! requirement "FR-67 A row may state raw solver commands, after the preset's at the same seam <span class='srs-implemented'>implemented</span>"
    *Origin: the design decision of 2026-09-10, "a linha ganha um jeito de passar
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

    Read with PFS-2067, PFS-2067.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    A cell's `RAW` list states solver commands, each before a named phase, in
    either of two forms: `COMMAND`, the line written in the cell, and `FILE`,
    a text file of the workspace whose lines are emitted in order. Both pass
    the same emitter checks the preset's `[[raw]]` table passes, line by line,
    so a file carrying a command the build lacks is refused naming the FILE
    and the LINE NUMBER rather than the cell. A blank line and a line opening
    with `#` are skipped, so a raw file may explain itself.

    At one seam the preset's lines come first and the row's after, on the reference
    answer that the shared lines are the ground and the specific ones come
    over them.

    The run record names each line's source, the setup's id, the word
    `matrix`, or the file's path WITH ITS LINE NUMBER, `<path>:<line>`, and a file's lines are recorded AS EMITTED,
    so a record still reproduces the run after the file has changed.

    ONE THING THIS TEXT DID NOT ANTICIPATE, and the reference row 9209 is where it
    showed: a record's key and value pairs are separated by a slash, and a PATH
    carries slashes, so `FILE: raw/pusher_extra.txt / BEFORE: init` was cut at
    the path's own separator and refused as not a pair. A raw record splits on
    a SPACED separator, because its two values are a path and a command line
    and both carry punctuation of their own. Every other record kind is
    unchanged.

!!! requirement "FR-68 The reductions read each rotor's blade count from its own declaration <span class='srs-implemented'>implemented</span>"
    *Origin: the design of 2026-09-10. Carried by PFS-2035.11. Evidence:
    `tests/tier1_offline/test_reduce_by_rotor.py` (a row stating its speeds in
    motions reduces at all; each rotor's passage is its own and the two are
    asserted UNEQUAL before either is pinned; the per-blade windows are
    contiguous and end at the run's last step; a several-rotor row says where
    its reductions went instead of naming a count; a one-rotor row takes the
    count from that rotor's block; a sector row reduces over the whole wheel; a
    motion naming no rotor of the reference is a skip and not an absence; a row
    with no rotor carries no per-rotor block, which is the sentence that
    protects every workspace written before 0.15.0; a rotor at rest, a run
    holding no whole revolution of a rotor, and a window shorter than one
    passage of a rotor are each skipped naming that rotor; a rotor turning the
    other way reduces over the same passage; a period whose fraction decides is
    rounded and not truncated; the phase-locked passages of each rotor start at
    the row's window; and a record spelling its alias loosely still names the
    reference's rotor) and
    `tests/tier1_offline/test_post_products.py` (the files name the rotor, and a
    one-rotor row keeps the names it has always had). AMENDS PFS-2015.04.01,
    which reads the count from `PERIODIC_COPIES` at 0.14.0.*

    Read with PFS-2070, PFS-2070.05 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    The per-blade and phase-locked reductions of a point are computed PER
    ROTOR, each from the blade count of its own rotor block, so a transition
    row reduces the lifters and the pusher in one run and the reduction files
    name the rotor. A row stating no motion reduces as today.

    A sector mesh needs nothing of its own: the count is the length of
    `families_blades` and not a property of the file, so a mesh carrying one
    blade of four still reduces over four, and `PERIODIC_COPIES` is not
    replaced by another key but by a fact the reference already states.

    The reduction files name the rotor on every row that names its rotors,
    one rotor or nine: `<point>_per_blade_<ALIAS>.csv`. Gating the name on
    there being SEVERAL rotors made the rotor COUNT a file-naming input, so
    the day a second rotor joined a row every script pointing at the flat
    file stopped finding its input and the stale one-rotor file stayed on
    disk beside a record calling it skipped (the interface lens,
    2026-09-10). A row stating no motion keeps the flat names, which is the
    sentence above about reducing as today.

    A HALF THIS TEXT DID NOT STATE, because nothing had measured it until the
    implementation: a row stating its speeds in MOTIONS carries no `RPM` of
    its own, so the window reader found no speed and EVERY reduction of the
    point was skipped, the time average included, with the sentence "states no
    rotor speed, and a rotary motion turns at one" on a row that states two.
    The row's window is the CLOCK motion's (FR-64), which is the same rotor
    whose revolutions already set the row's step and its length.

    ONE ANSWER PER ROTOR, from one rule. The blade count is read through the
    motion's view, where `_motion_view` has already set it from the block's
    own `blade_count`, so the per-rotor number and the flat number cannot
    differ for one rotor. Opening the block's list a second time in the
    reduction was a second home for a rule the model states (the architecture
    lens, 2026-09-10).

!!! requirement "FR-69 A sweep is one variable of the flight condition, and the angles are always written <span class='srs-implemented'>implemented</span>"
    *Origin: the rule of 2026-09-10, "um sweep e aplicado a uma variavel que
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
    angles, and the advance ratio when the row states it there. **Since 0.21.0
    every one of them is implemented**; until 0.20.x a row sweeping any but
    the two angles and the advance ratio was refused NAMING those three and
    saying it might carry the word in a later release, because
    accepted-and-ignored is how the advance-ratio sweep failed before 0.15.0.
    A key that does not define the condition is still refused.

    A SWEPT FLOW VARIABLE IS RESOLVED PER POINT: the row's cell with the swept
    key at that point's value, resolved against the row's reference length and
    its setup's pins, so each point carries its own density, velocity and
    Mach number. A row that sweeps one is therefore ONE JOB PER POINT and not
    one warm job: the air state is a setup command, taken before the solver is
    initialised, so one process cannot hold two of them. A row that sweeps an
    attitude is the warm job it always was.

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
    owning seat of a study can allocate the new POLs. That fixture was built to
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
    *Origin: the design decision of 2026-09-10 and its widening the same
    night: the sweep governs only the motion that declares no advance ratio
    of its own. Carried by PFS-2035.15. Evidence:
    `tests/tier1_offline/test_rotor_by_alias.py` (a swept ratio reaches the
    motion that states no speed and halving the ratio doubles that rotor's
    rev/min, a record stating its own ratio holds it against the sweep, and
    a record writing the word is refused naming where sweeping is stated).*

    Read with PFS-2070, PFS-2070.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    `ADVANCE_RATIO` may be stated in `FLIGHT_CONDITION`, as a value or as
    `sweep`, and it then reaches every motion of the row THAT STATES NO SPEED
    OF ITS OWN. A motion stating its own `RPM` or `ADVANCE_RATIO` holds that
    value and the condition's ratio passes it by. A motion may not state the
    word `sweep`: sweeping is the condition's job, and a record that writes it
    is refused at plan time naming the cell, the record and the key.

    The rule is precedence, record over condition, and it exists for one case
    the requirement named: a transition sweeps the pusher while the lifters hold. Eight
    records carrying an RPM and one carrying nothing but its alias is that
    row, and the held motions hold at EVERY point of the sweep.

    A SWEPT RATIO IS THE POINT'S, NOT THE ROW'S, and that is the half a
    variable lookup could not reach. The swept key is deliberately kept out
    of the row's variables, because the row states only the word and the
    value is what varies; so a row writing `ADVANCE_RATIO: sweep` had no
    ratio among its variables and the condition's ratio reached no motion
    at all. Measured 2026-09-10 on the reference `matriz_transicao.fs`: 9 of 16
    points blocked on "states no rotor speed", which is the sentence this
    requirement removes.

    The key stays optional precisely so that a row may prescribe the speed per
    motion instead, which is FR-63.

!!! requirement "FR-71 A rotation cites an alias, carries its frames, and keeps the frame it turned from <span class='srs-implemented'>implemented</span>"
    *Origin: the design decision of 2026-09-10, "o comando de rotate tambem tem que
    ser atualizado para ficar compativel com o do movimento". Carried by
    PFS-2035.17. Evidence: `tests/tier1_offline/test_rotor_by_alias.py` (the
    rotation cites the alias and turns that rotor's boundaries and no other's;
    the frames the alias owns turn with it, by name; an undeclared alias is
    refused naming it; a record stating both spellings is refused naming both;
    a record stating neither is refused; the 0.14.0 spelling is REFUSED with
    the replacement named, which is what this requirement's own body settles
    and what the evidence line said the opposite of until 2026-09-10; three cases over `SMRP_ORIGINAL` in that module,
    one copy per alias for a row that turns the same alias twice, nothing
    turns it, and a non-rotor alias gets none) and
    `tests/tier1_offline/test_pproc_by_frame.py` (five cases over the
    doubling: both frames for a rotated hub, one for a rotor this row did
    not turn, none at all for a row that turned nothing, the turning frames
    never doubled, and the same answer when the entry names the hub frame
    itself). AMENDS the
    `ROTATE` record of FR-35, "Matrix as first-class interface", whose
    `FAMILIES` and `AUX_FRAMES` keys this replaces.*

    A `ROTATE` record states `ALIAS` where it stated `FAMILIES`, so a rotation
    and a motion cite a set of boundaries the same way. `AUX_FRAMES` retires:
    every frame the alias owns turns with its boundaries, which for a rotor is
    `<ALIAS>_SMRP`, `<ALIAS>_RMRP` and every `<ALIAS>_RMRP<k>`, and for a
    non-rotor alias is none.

    ONCE PER ALIAS, before the FIRST rotation of that alias, the builder
    creates `<ALIAS>_SMRP_ORIGINAL`, a copy of the frame as it stood, which
    nothing turns and which a post-processing entry may cite, so a study of
    an installed propeller keeps the frame it turned FROM. Before this
    release that frame was lost the moment the mesh moved.

    AN ENTRY DOES NOT HAVE TO CITE THE COPY, which is the rule of the same
    night: "no posproc, se eu indicar um SMRP que foi rotacionado, ele
    escreve os outputs tanto no SMRP quanto no original". A post-processing
    entry naming a hub frame this row rotated is emitted TWICE, once in the
    turned frame and once in the copy, and the two plots differ by the same
    `_ORIGINAL` suffix so neither overwrites the other. An entry says which
    ROTOR it is about and the ROW's rotation decides how many readings of
    it exist, which is the rule FR-65 already applies to the frame; the
    alternative was a second entry written by hand on every row that
    rotates, which is a second home for one question. A rotor this row did
    not turn has no copy and doubles nothing, so every artifact written
    before this release emits exactly what it emitted. `<ALIAS>_RMRP` and
    `<ALIAS>_RMRP<k>` never double: they turn WITH the motion at every
    step, so "the frame it turned from" is not a thing they have.

    ONCE PER ALIAS IS THE REFERENCE ANSWER OF 2026-09-10 and the alternative was real:
    once per RECORD would also have kept the frame BETWEEN two rotations of
    the same alias, so a row stating a pitch and then a toe could read each
    stage in the frame it started from. The two differ in what such a study
    can measure afterwards, which is a question about what a user wants and
    not one the code can answer, so it waited for the reference rather than being
    built and written down where it would look decided.

    Measured 2026-09-10, before this half was built: the builder emitted
    `ROTATE_COORDINATE_SYSTEM` and kept no copy of a frame anywhere, and
    `grep -c "_ORIGINAL" src/pyflightstream/cases/workflows.py` answered 0.

    A rotation citing an alias the reference does not declare is refused
    naming the alias, and listing the words the reference does declare.

    `ALIAS` names EXACTLY ONE declared word, and that is not an arbitrary
    limit: a rotation carries the frames of what it turns, and those belong
    to one rotor. A word naming two declared rotors is refused telling a
    user to write one record per rotor, which is the shape a `FAMILIES`
    list spanning two rotors converts to and the one case the conversion
    cannot do by substitution.

    The `FAMILIES` spelling is REFUSED since 0.15.0, naming `ALIAS` as the
    word to write, on the instruction of 2026-09-10. This paragraph
    promised a warning and that every matrix written before this release
    keeps working; neither is true, and a matrix stating `FAMILIES` is
    refused with the replacement named, because the key changes AND SO DOES
    THE VALUE and the refusal site holds that information.
    `AUX_FRAMES` beside it still names frames that turn, because what the
    alias makes unnecessary it does not forbid; it is not deprecated and
    carries no removal promise. A record stating `ALIAS` and `FAMILIES`
    both is refused: one rotation turns ONE set, and picking one of two
    statements silently is how the wrong half of a study gets turned.

    NO FRAME TURNS TWICE, however many names it answers to. A rotor's hub
    is `<ALIAS>_SMRP` and `ROTOR_MRP<k>` at one index, and its moving frame
    is both a frame the alias owns and a follower of the hub, so an
    emission list keyed on NAMES applied the row's angle twice and the
    blades then spun about an axis at twice the stated incidence. The
    emission is keyed on the frame.

    After this requirement a row names a set of boundaries one way, whether it
    moves them, turns them or measures them, which is what makes the fourteen
    requirements of this section one vocabulary rather than fourteen features.

!!! requirement "FR-72 A custom frame is declared in the reference, where the geometry is <span class='srs-implemented'>implemented</span>"
    *Origin: the design decision of 2026-09-10: a custom axis definition such as
    `NAC_FL` belongs in the reference, which is where geometric data lives. Carried by
    PFS-2035.19. Evidence: `tests/tier1_offline/test_reference_vocabulary.py` and `tests/tier1_offline/test_matrix_run.py` (the frames reach the case, a preset still stating them warns and the reference wins, a LEGACY row leaves them out and says so). Commits f0032d3, 661dd5d and 2840078. SUPERSEDES the
    `[[frames]]` table of FR-31, "Solver-setup provenance", which places it in
    the setup preset.*

    The `[[frames]]` table moves from the setup preset to the reference
    artifact, keeping the shape it has: `name`, `origin`, and optionally
    `x_axis` and `y_axis`, the third axis being the right-handed cross
    product. A row's `ROTATE` axis token and a post-processing entry's frame
    resolve against the reference's frames, the package's own names staying
    reserved. A preset still stating `[[frames]]` is REFUSED when a row binds
    it, naming the reference to move it to. This paragraph promised a warning
    and a 0.17.0 removal until the instruction of 2026-09-10; the
    refusal is what the package does.

    A coordinate system is geometric data, so it belongs beside the lengths
    and the rotors. It also puts the two halves of one subject in one file:
    the frames a rotor instantiates were always derived from the reference's
    rotor block, while the hand-written ones sat in the preset.

!!! requirement "FR-73 A run chooses whether a family the mesh does not carry is a skip or a refusal <span class='srs-implemented'>implemented</span>"
    *Origin: the design decision of 2026-09-10: a command-line flag
    `--ignore-missing-families` the user may pass as false, defaulting to
    true. Carried by PFS-2035.13,
    recorded in `GeoversePlan/coordination/decisions/DEC-010`. Evidence:
    `tests/tier1_offline/test_missing_families_choice.py` (forty-two cases
    over the three layers, and the lane's mutation scoring recorded in
    `GeoversePlan/coordination/projects/pyflightstream/IMPL-0150-DECISIONS_rounds.ledger`
    and `REL-0150_rounds.ledger`, which name each mutant, its verdict and
    the one that survives). AMENDS FR-59, "A reference
    declares the names a study gives to its boundaries", whose rule that a
    member the opened mesh does not carry is ignored becomes the DEFAULT
    rather than the only reading.*

    A post-processing artifact names families, and one artifact is meant to
    serve a wing-body and an isolated rotor: a family the opened mesh does
    not carry is left out, which is what lets one file cover several
    geometries. From the emitted script that skip and a MISSPELLED family
    are the same event. This requirement lets the run say which of the two
    it is looking at.

    `pyfs-matrix plan` and `pyfs-matrix run` take
    `--ignore-missing-families`, whose default is true and which reads a
    word, so `--ignore-missing-families false` is what a shell writes; a
    word outside the vocabulary is REFUSED rather than read as the default,
    because reading it as the default would give the user the behaviour
    they were turning off and say nothing. The value reaches each case as
    the variable `IGNORE_MISSING_FAMILIES`, which the builders read like
    any other and which a matrix CELL may not state. At the default nothing
    at all is written onto a case, so every recorded run keeps its identity
    and every emitted script its bytes.

    With false, three silences become refusals ON A POST-PROCESSING
    `families` SELECTION, and each names the geometry's own boundaries
    beside what was cited. An ALIAS MEMBER no boundary answers, which the
    resolver drops so quietly that an alias of six members over a mesh
    carrying five still expands and writes its plot; the message names the
    alias that DECLARES the member, which on a nested alias is not the word
    the entry cited and is the table row to edit. A LIST MEMBER that names
    nothing, which is worse, because a list aggregates into one set that is
    non-empty as soon as one member resolves, so `["WING", "BLADE_1"]` over
    a mesh with no blade selects the wing and passes. And an ENTRY that
    selects nothing at all, which is left out of the products. The first
    two are reported before the third, because they are the ones a PASSING
    entry hides.

    THE SCOPE IS THAT SELECTION AND NOT EVERY CITED SET, stated because the
    first draft of this requirement claimed the resolver generally. An
    alias cited by `MOVING_BC_ALIAS`, by `BASE_REGIONS` or by a `[groups]`
    member still drops an absent member in silence with the flag false.
    Widening it is a separate call, and it is registered rather than
    implied.

    `convert` does not take the flag. It writes a campaign file that is read
    later by something that never saw this command line, and a
    per-invocation choice frozen into an artifact stops being one.

    WHY IT IS AN INVOCATION'S CHOICE AND NOT A CELL. The skip is what lets
    one reference and one post-processing artifact serve a wing-body and an
    isolated rotor, and from the emitted script that skip and a MISSPELLED
    family are the same event: both leave the entry out and say nothing.
    Which of the two a user is looking at is not a property of the row or of
    the artifact, both of which are written to serve several geometries. It
    is a property of what this run was for: a study planned across two
    geometries wants the skip, and the same matrix planned against the one
    geometry that should carry everything wants to hear about it.

!!! requirement "FR-74 A setup declares custom flags, so a row sets a solver command by name <span class='srs-implemented'>implemented</span>"

    Read with PFS-2061, PFS-2061.03, PFS-2064, PFS-2064.01, PFS-2067, PFS-2067.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the instruction of 2026-09-10: the setup gains a declaration of custom
    flags, so that raw commands are left for genuinely particular cases. Carried by PFS-2035.20. Evidence:
    `tests/tier1_offline/test_custom_flags.py`, and the worked example
    `tests/tier3_licensed/inputs/setups/s006.toml` with row 8006 of
    `matriz_vocab.fs` and its committed golden.*

    WHAT IT IS FOR, before how it is written. A setting that varies from point
    to point has no column of its own and does not belong in a preset, and
    reaching it meant `[[raw]]`, which fixes a whole command line so every row
    citing that preset emits the same one. A flag names the COMMAND and lets
    the ROW state the value, so one preset serves a sweep over it. That is what
    leaves `[[raw]]` to the particular case its name promises rather than
    making it the ordinary way to reach any setting this package does not
    curate.

    A setup preset declares, once per flag, the FlightStream COMMAND and the
    WORD a matrix row writes for it:

    ```toml
    [[flags]]
    name = "digits"
    command = "SET_SIGNIFICANT_DIGITS"
    ```

    After that, any row citing that preset may write `digits: 6` in its
    `VAR_NAMES_VALUES` cell and the builder emits `SET_SIGNIFICANT_DIGITS 6`.
    The word is read case folded, as every other key of a row is.

    WHY THIS IS NOT THE `[[raw]]` TABLE, which already exists and which a
    reader will otherwise ask about. A raw entry is a whole command LINE with
    its arguments, fixed in the preset, so every row citing that preset emits
    the same one. A flag names the command and the ROW states the value, so
    one preset serves a SWEEP over that value. That difference is the whole
    point of the feature: it leaves RAW to the particular case its name
    promises, rather than making it the ordinary way to reach any setting
    this package does not curate.

    IT PASSES THE SAME EMIT CHECK EVERY CURATED EMISSION PASSES, and that is
    what makes it a declaration rather than a string substitution. The line
    goes out through the emitter, so the command database's grammar, version,
    argument and phase checks apply to it unchanged: a flag naming a command
    this build cannot emit, or given a value of the wrong type, is refused
    when the row is PLANNED and never at the licensed machine, which is the
    one place a refusal costs a seat.

    A FLAG REACHES THREE SEAMS, the three a raw entry reaches: before the
    control, geometry and setup phases. A flag with no `before` takes the
    phase its command's own database entry declares, which is the answer for
    every command that has one; a control command, whose phase the database
    leaves open, is emitted in the control phase. A flag whose command
    belongs to a LATER phase is refused naming that phase rather than
    quietly not appearing: a later command is part of the RUN rather than of
    its setting up, this package emits those itself, and emitting one early
    would advance the script past its phase so that the order guard then
    refused the phase's own commands.

    A declaration whose `command` carries arguments is refused, because the
    value would then be stated twice and the two could disagree; two
    declarations giving one word two commands are refused, because a row
    stating the word would mean whichever record was read last; and a cell
    written with an EMPTY value states nothing, because a half-finished edit
    read as a value reaches the emitter as a bare command and is refused
    there for its arity, which is a true sentence about the command and says
    nothing about the row the user is holding.

    A declared flag's word is a key the row MAY state: the preset registered
    it by declaring it, so the guard that refuses a key no run type reads
    leaves it alone. A word no flag declares is still refused, which is the
    control that keeps the guard a guard.

    A LEGACY row takes no flags table, for the reason it takes no raw table:
    its own recipe is the reader of its keys and reads neither, so the
    entries would reach no script while the record claimed them.

!!! requirement "FR-75 A section distribution over a rotor cuts its blades and not the rotor <span class='srs-implemented'>implemented</span>"

    Read with PFS-2054, PFS-2054.02, PFS-2066, PFS-2066.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the design decision of 2026-09-10: a section distribution over a
    whole rotor makes no sense, so a rotor declaring three blades takes three
    cuts and not one, unlike the plots, which keep the total. Carried by PFS-2035.22.
    Evidence: tests/tier1_offline/test_workflows.py.*

    WHAT IT IS FOR, before how it is written. `LOCAL_AXIS` means one emission
    per blade, and on a `[[plots.groups]]` entry it also emits the rotor's own
    total in the frame that turns with it, which is a real quantity. A
    sectional CUT of the whole rotor is not: the blades lie at different
    azimuths, so one plane through the set crosses each of them somewhere
    different, and the station it reports is a station of nothing.

    Measured on the template's row 1003, which turns three rotors:
    `families = ["PUSHER"]` with `frame = "LOCAL_AXIS"` emits FOUR
    distributions, three in `PUSHER_RMRP1` to `RMRP3` and a fourth in
    `PUSHER_RMRP`; `families = "all"` emits ten, seven blades and three
    rotors.

    A `[[sections.distributions]]` entry citing a rotor alias in `LOCAL_AXIS`
    emits one distribution per BLADE of that rotor and none over the rotor as
    a whole. A `[[plots.groups]]` entry citing the same alias and frame is
    UNCHANGED and still emits the rotor total beside the blades: the two
    paths differ because the quantities differ, and one test pins both counts
    so they cannot drift apart unnoticed. An entry citing a NAMED rotor frame
    is unchanged and still groups, emitting one distribution over every
    surface the alias owns.

!!! requirement "FR-76 A section distribution may state its own cut count <span class='srs-implemented'>implemented</span>"

    *Origin: the instruction of 2026-09-10, "sobre o surface section,
    registra no backlog para deixarmos a opcao de especificar por distribuicao
    mantendo preservando a opcao geral que tem hoje". Carried by PFS-2035.23.
    Evidence: tests/tier1_offline/test_workflows.py.*

    WHAT IT IS FOR. `count` is a field of `[sections]` and governs every
    distribution in the artifact: measured, `count = 25` emitted
    `NUM_SECTIONS 25` on both entries of a two-entry artifact and
    `count = 120` emitted 120 on both, and absent, both took the default 50.
    So a study wanting a hundred stations along a blade and thirty along a
    wing needs two pproc artifacts and a second PPROC code on the rows that
    want the other density. That splits a file for a number rather than for a
    question.

    A `[[sections.distributions]]` entry may carry its own `count`, and the
    emitted `NUM_SECTIONS` for that entry is its value. THE ARTIFACT-LEVEL
    SETTING IS KEPT: `[sections] count` remains, and remains the default for
    every entry stating none, and an artifact stating neither keeps 50. A
    test emits one artifact holding two distributions with different counts
    and reads both numbers out of one script, because a per-entry setting
    that is only ever tested alone is a global setting with extra syntax.

    `plot_direction` GAINS THE SAME SHAPE and `include_symmetry` does not, on
    the design decision of 2026-09-10. Both keep their artifact-level value
    as the default. The asymmetry is deliberate and it has a reason a reader can
    check: a plot direction is a property of the CUT, so two distributions
    can honestly want different ones, while symmetry is a property of the
    CASE, and one artifact whose entries disagreed about it would be
    describing two cases.

!!! requirement "FR-77 Probe lines are a list of tables, so one artifact probes several frames <span class='srs-implemented'>implemented</span>"

    Read with PFS-2062, PFS-2062.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the design decision of 2026-09-10: `[probes]` becomes `[[probes]]`, as an
    item of the next release. Carried by
    PFS-2035.24. Evidence:
    tests/tier1_offline/test_workflows.py.*

    WHAT IT IS FOR. A pproc artifact declares ONE `[probes]` table, so every
    probe line it carries is measured in one frame. Measured, all three ways
    a reader would ask for a second are refused: a second `[probes]` table,
    `[[probes]]` written as an array, and a `frame` on an individual
    `[[probes.lines]]` entry. `ProbeLine` carries `start` and `end` and
    nothing else.

    OF THE FAMILIES THAT EXPAND PER ENTRY, probes alone is not a list.
    `[[plots.groups]]` is a list, each group with its own name, frame and
    families; `[[sections.distributions]]` is a list with its own frame and
    planes. Probes alone keep the frame that belongs to an entry on the
    artifact instead. `[groups]` is a table and is not a counter-example to
    that: it maps a group name to the surfaces it holds, and carries no
    frame or scale of its own for a second one to differ from.

    A pproc artifact declares `[[probes]]` as a LIST, each entry carrying its
    own `frame`, `scale`, `parameters`, `points` and `lines`, and one artifact
    emits probe lines in two different frames on one row.

    THIS IS A FORMAT CHANGE AND NOT A PRECEDENCE ONE, which is why it is
    separate from FR-76: every existing artifact that declares probes stops
    parsing. This package has no stable release, so the 0.15.0 `[probes]`
    spelling is REFUSED with the new one named, on the rule FR-71 established,
    and the refusal names the edit because whoever meets it is holding a
    workspace that planned yesterday. The shipped template and the
    reproduction workspace are migrated in the same change: a published
    example that no longer parses is a defect this project has already paid
    for once.

!!! requirement "FR-78 A run says on the console which stage it is in, and its warnings arrive while it runs <span class='srs-implemented'>implemented</span>"

    Read with PFS-2055, PFS-2055.01, PFS-2055.03, PFS-2055.04, PFS-2055.05, PFS-2055.06 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the request of 2026-09-10 for a log in the terminal while a
    campaign runs, saying which stage it is on and carrying any warning it
    raises on the way. Carried by PFS-2035.25.
    Evidence: tests/tier1_offline/test_run_campaign.py.*

    WHAT IT IS FOR. A run of an unsteady rotor row is long and it is the
    scarce resource, and silence is indistinguishable from a hang. Measured:
    `run_campaign` takes no progress callback, `logging` is imported in the
    fsi subpackage alone and nowhere on the run path, `pyfs-matrix run --help`
    offers no verbose, quiet or log switch, and the run path reports through
    bare `print()`, none of it per point. A campaign of forty points prints
    its first line when the last one is done.

    THE WARNINGS ARE THE SHARPER HALF. A pproc entry left out because the row
    created none of its frames, a `symmetry_loads` a row overrode, a family
    the mesh lacks: these are findings, and they reach the reader after the
    seat is spent rather than while it is still worth stopping.

    Running a campaign of more than one point prints a line as each point
    STARTS, naming the point and the stage, and a line as it ends naming its
    status; a warning raised while a point is built or run reaches the console
    at that moment. A test captures the stream of a two-point run and asserts
    that the first point's lines appear before the second point's begin, which
    is what distinguishes streaming from a buffer flushed at the end. The
    verbosity is switchable through the run layer's `quiet` parameter, and
    its default is what a person at a console wants, because a switch nobody
    turns on is not a feature. NO COMMAND-LINE FLAG IS OFFERED, and this
    sentence read as promising one until the technical writing lens measured
    that `--quiet` appears nowhere in the package (2026-09-11); whether a
    console program should carry one is a seat decision.

    WHERE THE LINES GO is decided before any is written: everything the run
    prints today that a caller consumes is on stdout and its errors are on
    stderr, so stderr is the shape that does not break a pipeline reading
    records.

!!! requirement "FR-79 A probe entry prescribes a rectangular or a circular plane, not only a line <span class='srs-implemented'>implemented</span>"

    Read with PFS-2064, PFS-2064.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the request of 2026-09-10: a rectangular plane can be prescribed by
    its vertices and its discretisation, and a circular one by a
    discretisation in polar coordinates.
    Carried by PFS-2035.26. Evidence:
    tests/tier1_offline/test_workflows.py.*

    WHAT IT IS FOR. A probe entry declares a start and an end, and the
    package emits one `NEW_PROBE_LINE` for it. A survey of a rotor disk, or
    of a rectangular window in the flow, is then a list of lines whose
    coordinates were computed by hand outside the file, and the file records
    the result rather than the intent.

    A PLANE IS NOT A SOLVER COMMAND THIS PACKAGE IS FAILING TO REACH, and
    that decides the shape of the work. The solver's probe vocabulary is
    `NEW_PROBE_POINT` and `NEW_PROBE_LINE` and nothing else: the other four
    verbs of `probe_points.yaml` are UPDATE, IMPORT, EXPORT and DELETE. A
    plane is a shape the PACKAGE lays out and emits as solver commands.

    AND THE PACKAGE ALREADY LAYS ONE OUT, in a subpackage this seam cannot
    reach. `pyflightstream.probes.planar.PlanarProbeGrid` is a frame plus two
    in-plane `AxisSpec` distributions with `local_points()`, which is this
    requirement's rectangle under another name;
    `pyflightstream.probes.ProbeLattice` carries ring edges and `n_psi`
    uniform azimuths, which is the ring-and-azimuth parameterization the
    circle needs, inside a cylindrical far-field survey rather than a flat
    disk. Measured 2026-09-10: NOTHING under `cases/` imports anything from
    `probes/`, so the pproc artifact genuinely cannot reach either today.

    THAT MAKES THE OPEN QUESTION A STRUCTURAL ONE and not a geometry one:
    whether the pproc plane reuses those types or whether a second layout is
    written beside them. It is not settled here, and it is settled before any
    coordinate is computed, because two homes for one geometry is the defect
    this project is cheapest at preventing right now.

    A probe entry may declare a RECTANGLE by three vertices and two division
    counts, the third corner removing the ambiguity four coplanar-or-not
    corners would carry; or a CIRCLE by a centre, a radius, a count of radial
    stations and a count of azimuthal ones, which is the shape a disk survey
    actually has. Both honour the entry's `frame` and `scale`, so a plane
    declared in rotor radii follows the size of the rotor it belongs to,
    which is the property that lets one table serve rotors of unlike size.

    It lands on top of FR-77: a plane is a third kind of entry beside the
    line, so the list and the shapes are designed together rather than
    shipping a format change twice.

    THE EMISSION IS POINT BY POINT, on the design decision of 2026-09-10.
    A rectangle and a circle both emit `NEW_PROBE_POINT` per vertex rather
    than a line per grid row, and the reason is transparency rather than
    geometry: on the unsteady path the points reach the solver one at a time
    whatever the shape was, so emitting lines on one path and points on the
    other would make one declaration produce two different exports.

    A test builds one artifact holding a line, a rectangle and a circle and
    asserts the emitted vertex count and the first and last coordinate of
    each against values computed in the test, because a geometry test that
    reads its expectation from the thing it tests asserts nothing.

!!! requirement "FR-80 A probe entry may cite a points file the user wrote, under inputs/profiles <span class='srs-implemented'>implemented</span>"

    Read with PFS-2064, PFS-2064.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the request of 2026-09-10: a user may write a text file of the
    points they want and cite it from the pproc artifact; the file belongs
    in `profiles`. Carried by
    PFS-2035.27. Evidence:
    tests/tier1_offline/test_workflows.py.*

    WHAT IT IS FOR. A lattice the package computes from a rectangle or a
    circle covers the regular cases. A survey whose points come from somewhere
    else, a rig, a previous study, a colleague's table, has no shape to
    declare, and rewriting it as lines loses both the points and the reason
    they are where they are.

    `inputs/profiles/` ALREADY EXISTS as a workspace kind and is reached by
    nothing. It registers by file-name stem, the way `inputs/geometries/`
    does, and the workspace documents it as input profile files. No workspace
    in this estate has one, so this is the first use of a directory the layout
    already reserved rather than a new one.

    A probe entry may cite a points file by STEM, resolved under
    `inputs/profiles/`, and its points reach the solver through
    `PROBE_POINTS_IMPORT` in the entry's frame. A stem the directory does not
    hold is refused when the ROW is planned, naming the stems it does hold,
    the way an unknown geometry already is.

    THE IMPORT PATH IS BUILT AND UNREACHED, which is a different statement
    from the one this entry would otherwise make. `pyflightstream.probes`
    declares its role as emitting the version-validated lines that create and
    export probes, and exports `emit_probe_points`, `emit_probe_import` and
    `emit_probe_export`; `write_probe_csv` writes the file those read.
    Measured 2026-09-10: nothing under `cases/` imports anything from
    `probes/`, so the pproc seam reaches none of it. What this requirement
    adds is therefore the CITATION and the resolution, not the emission, and
    a second emitter written beside the existing one would be the finding.

    THE SURVEY IS IMPORTED BY ABSOLUTE PATH (0.18.1). The path is resolved when
    the row binds, the way a geometry is, and a name `inputs/profiles/` does
    not hold is refused then, naming what it does hold. A builder handed a
    citation nothing resolved refuses rather than emitting an import of
    nothing.

    A CITED PROFILE IS INPUT AND A GENERATED LATTICE IS OUTPUT, and the
    difference is where each lives: the profile under `inputs/profiles/`,
    which a run must never write over, and the generated file inside the
    simulation's own folder. A test asserts the cited file's bytes are
    unchanged after a run.

!!! requirement "FR-81 A script never exports probe points nothing in it created <span class='srs-implemented'>implemented</span>"

    *Origin: measured on 2026-09-10 while building the probe-plane design.
    Carried by PFS-2035.28. Evidence:
    tests/tier1_offline/test_workflows.py.*

    WHAT IS WRONG TODAY. A STEADY row citing a pproc artifact whose
    `[probes]` table is valid, and whose frame is one the row DOES create,
    emits no creation command at all: not `NEW_PROBE_POINT`, not
    `NEW_PROBE_LINE`, not `PROBE_POINTS_IMPORT`. It nevertheless emits
    `UPDATE_PROBE_POINTS` and `EXPORT_PROBE_POINTS`. Measured on the
    template's rows 1001 and 1004 with one artifact whose probes are in `MRP`:

        steady   row 1001 -> probe creation verbs NONE, exports probes TRUE
        unsteady row 1004 -> probe creation verbs NONE, exports probes TRUE

    NEITHER ROW CREATES A PROBE POINT, and saying so is the correction of a
    first reading of this measurement. The unsteady row emits 45
    `UNSTEADY_SOLVER_NEW_FLUID_PLOT`, which is a fluid plot per vertex per
    parameter and not a probe point, so it is not the creation the steady row
    is missing. What the unsteady row has is a CONSUMER of the table, not a
    creator, and the export is unpaired on both.

    The only consumer of a probe entry's lines on the campaign path is the
    unsteady fluid-plot emitter. So the `[probes]` table is unsteady-only in
    practice while reading as though it serves both, and a steady study that
    declares probes gets an export of nothing, with no warning and no
    refusal.

    A STEADY ROW CREATES THE POINTS IT EXPORTS, on the design decision of
    2026-09-10: a steady row creates the points, since a line
    distribution command for probes exists on the steady path, so the two
    paths become transparent to each other.
    The alternative considered and not taken was refusing a probes
    table on a steady row; what neither of them is, is the third state the
    package is in now, where the script asks the solver to export a thing
    nobody made.

    The consequence named is the one that matters to a reader: a steady
    row and an unsteady row citing the same artifact produce the same probe
    export, so nothing downstream has to know which of the two ran.

    No script emits `EXPORT_PROBE_POINTS` when nothing in it created a probe
    point, and a test asserts that pairing over every workflow the package
    builds, because the defect is the PAIRING and not the run type.

!!! requirement "FR-82 A plan flag tables what each polar will cost, and what it is expected to take <span class='srs-implemented'>implemented</span>"

    Read with PFS-2066, PFS-2066.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the request of 2026-09-10 for a plan flag that also returns a
    summary of the expected execution time per polar, with a stated column
    set that includes the number of processors configured. Carried by
    PFS-2035.29. The decision of 2026-09-11 on what the estimate may rest
    on: an estimate of the run time is wanted now, from whatever the
    workspace already holds; a fuller scalability study will follow and can
    calibrate the model later. Evidence: tests/tier1_offline/test_plan_cost.py,
    18 cases, and tests/tier1_offline/test_cli_options_registry.py for the
    flag.*

    WHAT IT IS FOR. `plan` answers whether a row will run. It does not answer
    what running it will cost, and the cost is a licence seat and an
    afternoon. A study is budgeted before it is spent or it is budgeted by
    watching it.

    `pyfs-matrix plan` gains a flag that prints, beside the READY and BLOCKED
    report, one row per polar carrying: mesh size, trailing edges marked,
    farfield layers, viscous coupling, steady or unsteady, temporal
    iterations, processors, and an expected time. The flag spends NO solver
    time: everything in the table comes from the workspace and the mesh.

    EVERY COLUMN BUT THE TIME IS A READING, and each is read from the thing
    that owns it. The run type is the row's WORKFLOW; `viscous_coupling`, the
    farfield layers and `max_parallel_threads` are setup settings; the
    temporal iterations follow from `DELTA_THETA` and `REVOLUTIONS` through
    the same resolver the builder uses, so a rotor row answers 36 where 1.5
    turns are taken 15 degrees at a time. Trailing edges are the families the
    row marks for vorticity drag INTERSECTED with the inventory the opened
    geometry declares, which is what the builder does with them.

    THE MESH SIZE IS THE FILE'S OWN STATEMENT and the caveat travels with it.
    An earlier draft of this paragraph said the mesh reader exposes no panel
    or vertex count and the column would need it extended; that was true of
    the NAME reader and not of the file. The mesh block states an element
    count two lines above the boundary count, and `_fsm` steps over that line
    on purpose, because one campaign geometry states 7848 where every array
    holds 7784. So the column can be off by about a percent, the alternative
    is walking a 9 MB file once per row, and the number is barred from
    arithmetic: the fit is linear in the time steps and in nothing else.

    THREE OF THESE COLUMNS WERE READINGS OF THE WRONG THING before they were
    held against a real workspace, and each rendered perfectly. `panels` was
    the BOUNDARY count, so a wing-body read 2 where its mesh states 14266;
    `procs` and `TEs` each read a variable key no row writes, so each printed
    one value for every row in the table and neither could have printed
    another. A column that cannot be wrong is a column nobody is measuring,
    which is why each of them is now guarded by a case that DISCRIMINATES:
    the fixture geometry's element count differs from its boundary count, and
    the marked families include one the geometry does not carry.

    EVERY CELL THE PACKAGE CANNOT DERIVE PRINTS AS `-`, and `unknown` is
    reserved for the one column that is an extrapolation: a time with no
    comparable recorded run. **THIS TABLE IS PRINTED AND NEVER PARSED**, which
    is why it keeps `-` while every CSV PRODUCT writes `NA` from 0.23.0 (see
    `NOT_APPLICABLE`): the rule that one token means "does not apply"
    exists because a second spelling breaks a reader, and nothing reads this
    one but a person, for whom `-` scans better in a column of numbers. The
    boundary is written here and beside the constant because it was written
    nowhere at all until the closing round of FIX-0230 asked which surface
    used which. This paragraph said `unknown` everywhere while
    the paragraphs above and below it were being corrected, which is how a
    surviving sentence outlives its own requirement. A test
    asserts that a mesh with no countable panels prints `-` in that
    column rather than a zero. A zero is a measurement and an absence is not.

    THE EXPECTED TIME IS FITTED ON RECORDED RUNS AND SAYS SO. The data
    exists and it has a home: `runs.json` has carried `wall_time_s` per point
    since the v0.3 line, and `pyflightstream.qa.cost` already reads it, with
    `docs/solver-cost.md` as its page. This requirement adds a consumer, not
    a second reader, and it inherits that module's rule that an absent time
    is `None` and never zero rather than restating it.

    Counted over `GeoverseResearch/tools/fts_workspace/*/runs.json` on
    2026-09-10: 83 points carrying a `wall_time_s`, across ten workspaces,
    pfs0100 2, pfs0101 2, pfs0110 4, pfs0120 4, pfs0130 11, pfs0131 25,
    pfs0140 25, pfs0150-repro 4, pfs040 4 and pfs090 2, spanning 4.7 to
    1292.2 seconds. The four of pfs0150-repro show why a rule of thumb will
    not do: they took 6.8, 7.1, 289.9 and 412.3 seconds, two orders of
    magnitude apart, so the run type and the mesh dominate whatever else is
    true.

    ONE HALF OF THAT SENTENCE WAS AN ARTIFACT AND IS WITHDRAWN. It also said
    all four record 100 iterations, and they do, but 100 was not a
    measurement: the residual reader stopped at the first page of the solver
    log, so a run longer than its first page reported that page's last row as
    its iteration count.

    AND THE FIRST WRITING OF THIS CORRECTION OVERREACHED IN ITS TURN, which
    the verification lens caught and which is recorded here rather than
    quietly narrowed. It said EVERY recorded point in this estate carries a
    page boundary. Measured over every `runs.json` in
    `GeoverseResearch/tools/fts_workspace`: 95 points carry an iteration
    count, 89 of them read 100 or 81, and SIX DO NOT. Four are `pfs040` at
    1575 and two are an archived `pfs090` run at 1363 and 1368. The
    counter-example was inside this very paragraph: `pfs040` is named in the
    workspace list four sentences above, and 1575 is the last row of a
    one-page log, where there is no page boundary to mistake.

    So the rule is not a universal but a condition: AN ITERATION COUNT
    RECORDED BEFORE 0.16.0 IS UNTRUSTWORTHY WHERE THE RUN OUTLASTED ITS FIRST
    PAGE, which is 89 of the 95 recorded points. This requirement asked the
    model to re-derive them from the logs or exclude them and say so.

    IT DOES NEITHER, BECAUSE IT NEVER READS THEM, and that is a better answer
    than the one this paragraph asked for rather than a way around it. The
    work a recorded run did is the step count ITS OWN ROW asks for, resolved
    by the same function that resolves it for a point about to be planned, so
    a record carrying the first page's last row moves no estimate. A test
    hands the fit a record whose `iterations` is the classic wrong 100 and
    asserts the estimate does not move.

    A SAMPLE WHOSE WORK CANNOT BE RESOLVED IS LEFT OUT, never counted as one
    solve, and the basis says how many were dropped. That sentence is here
    because the first writing did count them as one solve: the recorded rotor
    run carries a null step count, since every reduction of that point was
    skipped, and the point was tabled at 7013.5s against its own recorded
    194.8s.

    THE COMPARABLE RUNS ARE THOSE OF THE SAME RUN TYPE, read from the
    record's own `recipe` and not inferred from whether it carries a
    reduction block. The proxy survives only for a manifest schema that
    states no recipe, and it is wrong for exactly the case that broke it: an
    unsteady run nobody planned a reduction for reads as steady and moves
    every steady estimate in the table.

    The estimate prints the size of the calibration set beside it, and a test
    scores the fit against a HELD-OUT point, because a model measured on its
    own training set measures nothing. THE PLURAL THIS PARAGRAPH ASKED FOR IS
    ONE POINT, and that narrowing is marked here rather than made silently in
    a requirement whose every other correction is announced: one hold-out over
    two training runs of different lengths is what discriminates a model that
    reads the steps from one that averages, and a second would add samples
    rather than evidence. The hold-out discriminates: the two
    training runs are of different lengths, so a model that answered the mean
    of their wall times would be wrong by a factor of two.

    AND THE WHOLE THING IS PROVISIONAL BY INSTRUCTION, not by hedging.
    The table says so where it cannot be missed, under every printing:
    "EXPECTED TIME IS AN EXTRAPOLATION AND NOT A MEASUREMENT", with one line
    per run type naming the sample size behind that run type's number. A
    point with no comparable recorded run prints `unknown` rather than a
    figure with no basis.

!!! requirement "FR-83 A section distribution is created after the solver is initialised <span class='srs-implemented'>implemented</span>"

    Read with PFS-2054, PFS-2054.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: usage feedback of 2026-09-10. Carried by PFS-2036.01. Evidence:
    tests/tier1_offline/test_workflows.py.*

    WHAT IT IS FOR. A run came back with fifty surface sections that say
    nothing. Measured over the nineteen committed licensed runs of
    `tests/tier3_licensed/`, which is the locator this sentence carried
    nowhere while every other measured claim of this range names its
    artifact (the verification lens at the release boundary, 2026-09-11): 19 of 19
    declare twenty sections and write twenty blocks, 19 of the 20 identical,
    and 11 of the 19 came back with all twenty EMPTY. So every sectional
    result this package produced before 0.16.0 is one cut repeated, and more
    than half are one EMPTY cut repeated.

    THE COMMAND IS NOT THE PROBLEM, and the first diagnosis of this defect
    said it was. `NEW_SURFACE_SECTION_DISTRIBUTION` works, takes the count the
    artifact already declares, and needs no extent: the reference driver
    runs it and gets real cuts, and the report is that it always has.

    THE POSITION IS THE PROBLEM. The working script,
    `SCRIPT-POLAR-3267_M20AL+000BE+000.txt`, creates its twelve distributions
    AFTER the solver is initialised:

        12779  INITIALIZE_SOLVER
        12880  NEW_SURFACE_SECTION_DISTRIBUTION   x 12, NUM_SECTIONS 50
        13022  START_SOLVER
        13027  UPDATE_ALL_SURFACE_SECTIONS
        13060  EXPORT_ALL_SURFACE_SECTIONS

    This package created them BEFORE `INITIALIZE_SOLVER`, against a solver
    that had not initialised. Both positions are the same script PHASE, so
    nothing in the phase ordering could have caught it, and both produce a
    script the solver accepts. One returns cuts and the other returns fifty of
    nothing.

    A section distribution is emitted between `INITIALIZE_SOLVER` and
    `START_SOLVER`, where the reference scripts put it. A test asserts the
    position against both boundaries, and the shipped goldens carry it.

    `INCLUDE_SYMMETRY` IS KEPT AND IS NOT THE CAUSE. The twelve reference blocks carry
    six keywords and no `INCLUDE_SYMMETRY`, which made it the other candidate:
    a keyword a build does not expect would shift the rest of the block and
    put `SURFACES` in the wrong field. It is not the cause, because those
    scripts predate the keyword and the first edition to document it is
    26.121. The owning seat settled it: the keyword is emitted, being an
    evolution of the command rather than a change of meaning. A test pins it
    as emitted, so a later reader of those scripts cannot reintroduce the
    candidate.

    HOW THE FIRST DIAGNOSIS WENT WRONG IS RECORDED HERE, because the same
    mistake was made twice in one investigation and the record is the only
    thing that makes it visible. A licensed probe compared the distribution
    emitted PRE-SOLVE against explicit creates emitted POST-SOLVE, concluded
    from the difference that the command did not distribute, and the
    conclusion was attributed to the command. Two variables moved and one was
    named. The technical-writing review caught it once, on the station; the
    owning seat caught it the second time, on the phase. The probe's own artifacts
    are kept under
    `GeoverseResearch/tools/fts_workspace/pfs0160-probe-fr83/`, a private
    research workspace held outside this repository.

    WHAT IS STILL OWED AND IS NOT THIS REQUIREMENT. Sections cut against a
    MOVING boundary freeze at the pose they were created in. The reference
    answer is to create them in the rotating auxiliary frames, so they turn
    with the geometry and need only an UPDATE per step rather than a
    re-creation, and that is what the export-after-N-revolutions actions are
    for. That is a separate requirement at 0.17.0.


!!! requirement "FR-84 A simulation's collected outputs live under outputs, not raw <span class='srs-implemented'>implemented</span>"

    *Origin: the second feedback item of 2026-09-10, "trocar
    sims\sim_<>\raw por sims\sim_<>\outputs". Carried by PFS-2036.02.
    Evidence: tests/tier1_offline/test_sim_outputs_dir.py.*

    WHAT IT IS FOR. `raw` names how the data arrived; `outputs` names what it
    is. A reader opening a simulation folder wants the second.

    THE WORD MEANS THREE DIFFERENT THINGS IN THIS PACKAGE and only one is
    renamed, which is the whole risk of this requirement and the reason it is
    stated before the edit: the SUBDIRECTORY of a simulation is renamed; the
    `data_origin` value `raw`, whose companion is `reduced`, is UNCHANGED; and
    the setup key for the verbatim solver commands a row states is UNCHANGED.
    A sweep that renamed all three would change the meaning of every recorded
    result and of every setup, and neither was asked for.

    SUPERSEDED AT 0.16.0 BY FR-92, WITHIN THIS SAME RELEASE, and the
    sentence below is kept as the history it is rather than rewritten: a
    run now writes each point's collected outputs to
    `sims/<sim>/datapoints/DP-<point>/`, one folder per point, and
    creates neither older folder. `outputs/` never reached a tag. What
    survives of this requirement is its reasoning about the WORD, which
    FR-92 inherits: `outputs` named what the files are where `raw` named
    how they arrived, and `datapoints` names whose they are.

    As stated at 0.16.0: a run writes its collected outputs to
    `sims/<sim>/outputs/` and creates no `sims/<sim>/raw/`. A workspace that already holds `sims/<sim>/raw/` is
    still READ, so no recorded point is orphaned, and a test asserts a collect
    over such a workspace returns the points it returned before. A test also
    asserts a result row still carries `data_origin = raw` after the rename,
    because that reading is what this change is most likely to break by
    accident.

!!! requirement "FR-85 A polar table is named by the standard convention and says what was swept <span class='srs-implemented'>implemented</span>"

    *Origin: the third feedback item of 2026-09-10, the names
    `<>_M<>_g<>.csv` and `<>_M<>_g<>.dat` must be the standard convention,
    with the word `sweep` in the swept variable's field. Carried by PFS-2036.03. Evidence: tests/tier1_offline/test_products_layout.py.*

    WHAT IT IS FOR. The package writes one point under two conventions.
    Measured in the reference workspace, for one point of one run:

        scripts      POLAR-0001_M15AL+000BE+000J+100.txt
        polar table  0001_M15_g01.csv

    The second is built by `post/products.py` and carries neither the alpha
    and beta the standard convention carries nor the advance ratio the run
    actually swept.

    WORSE THAN THE NAME, THE CONTENTS CANNOT TELL THE ROWS APART. Measured on
    the reference `0001_M15_g01.csv`: the three rows of a three-value sweep carry
    identical `ALPHA`, `BETA`, `MACH` and `RE` and NO column naming the swept
    value, so the only thing distinguishing the first row from the third is
    its position in the file. A table whose rows are told apart by order is
    not a table.

    A polar table is named by the standard convention with the swept
    variable's field written as the literal word `sweep`, and the `.dat`
    beside it takes the same stem:

        POLAR-0001_M15AL+000BE+000J+sweep_g01.csv

    The table carries a COLUMN for the swept variable, and a test asserts that
    two rows of one sweep differ in it. A workspace holding tables under the
    old name is still read.

    **The file convention of this requirement is superseded by FR-102
    (0.21.0).** The `POLAR-` stem above is what 0.20.x wrote; the stem is
    `P<sim>-<name>` now, where the name carries every variable the row's
    `FLIGHT_CONDITION` cell declares, and the swept field is still written
    `<code>+sweep`. An existing workspace is moved to it by `pyfs-matrix
    rename` (FR-103). Everything else this requirement states stands,
    including that a table under the old name is still read.

!!! requirement "FR-86 A provenance file is named by the same convention as everything beside it <span class='srs-implemented'>implemented</span>"

    *Origin: the fourth feedback item of 2026-09-10, "nomes arquivos
    em post\matriz\provenance fora do padrao". Carried by PFS-2036.04.
    Evidence: tests/tier1_offline/test_products_layout.py.*

    WHAT IT IS FOR. Two conventions sit in one run for one point:

        sims/sim_0001/scripts/    POLAR-0001_M15AL+000BE+000J+100.txt
        post/matriz/provenance/   pfs0150-eve_sim_0001_a+00.0_b+00.0_j+01.0.prov.json

    The second is the run id, which is a good identifier and is simply not the
    name every other generated file in the workspace carries. A reader sorting
    the two directories side by side cannot line them up, which is the job a
    naming convention exists to do.

    A provenance file is named by the same convention as the script and the
    export of the same point, with its own suffix. NOTHING RENAMES A RUN: the
    run id the file records is unchanged and stays a field of the document,
    and a test asserts the id read back from a renamed file is the string it
    was before.

    **The convention this requirement points at is superseded by FR-102
    (0.21.0).** It says the provenance file takes the same name as the script
    and the export beside it, and that convention is now the point name,
    `P<sim>-<name>`, rather than the `POLAR-` stem of the example above. The
    requirement is unchanged by that: it names no convention of its own, which
    is the whole of what it asks for. An existing workspace is moved by
    `pyfs-matrix rename` (FR-103), and NOTHING RENAMES A RUN still holds --
    the rename rewrites the run id's point name and the id stays the record's
    identity.

!!! requirement "FR-87 Flow-field samples go to probes and carry the fluid quantities, steady or unsteady <span class='srs-implemented'>implemented</span>"

    Read with PFS-2062, PFS-2062.01, PFS-2062.03, PFS-2062.04, PFS-2063, PFS-2063.01, PFS-2065, PFS-2065.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the fifth feedback item of 2026-09-10, the plot file is missing the fluid
    quantities; to keep it uniform between steady and unsteady, the unsteady
    fluid plots go in a `probes` folder. Carried by
    PFS-2036.05. Evidence: tests/tier1_offline/test_products_layout.py.*

    TWO CLAIMS AND THEY ARE SEPARABLE. First, the file is missing the fluid
    quantities: the unsteady plots emit forces AND fluid properties, and the
    file returned carried only the forces. That is a content defect and it
    is the expensive one, because the quantities are gone until the point is
    run again. Second, the directory is named `plots`, after the solver verb
    that produced the file, rather than after what the file holds.

    THE GENERICITY IS THE REQUIREMENT and not a side effect. A reader of a
    finished campaign should not have to know whether a row was steady or
    unsteady to know where the flow-field samples are. It lands with FR-81,
    under which a steady row creates the probe points it exports, so both run
    types produce the same directory with the same kind of content; the two
    are one capability seen from the writer's side and the reader's side.

    WHICH OF THE TWO SIDES THIS REQUIREMENT COVERS IS THE READER'S, and the
    distinction is written here rather than left to the badge. What this
    requirement implements is the POST STAGE: a point that HAS a flow-field
    export gets it tabled under `post/<matrix>/probes/` with its fluid columns,
    whatever run type produced it, and the test asserts that a steady row and
    an unsteady row citing the same artifact produce the same path.

    THE STEADY PRODUCER IS FR-81'S AND IT IS NOW BUILT (2026-09-11), which is
    what closes the other half: a steady row emits the probe creation verbs and
    then exports them, so a steady study that declares probes fills this
    directory from its own run. Until that landed, this paragraph said the
    opposite and said so deliberately.

    THE TEST'S STEADY SIDE IS STILL A COMMITTED FIXTURE, and that is stated
    rather than quietly upgraded now that the writer exists. It was written
    into the outputs folder by hand because a reader's test must not wait on a
    writer, and it stays a fixture because this requirement is about the
    reader; the evidence that the writer produces the same thing is FR-81's
    own, measured on the emitted script and not on this table.

    The flow-field samples of a point are written under
    `post/<matrix>/probes/` whatever the run type was, and the file carries
    every quantity the unsteady plots produce, forces and fluid properties
    alike. A test asserts the fluid columns are present on a row that
    requested fluid parameters, and asserts that a steady row and an unsteady
    row citing the same artifact produce the same path.

!!! requirement "FR-88 The polar tables live in a polars subfolder <span class='srs-implemented'>implemented</span>"

    *Origin: the reference sixth feedback item of 2026-09-10, "crie uma
    subpasta polars para os arquivos <>_M<>_g<>.csv e <>_M<>_g<>.dat atuais".
    Carried by PFS-2036.06. Evidence: tests/tier1_offline/test_products_layout.py.*

    WHAT IT IS FOR. Measured in the reference workspace, `post/matriz/`
    holds the polar tables loose at its top level beside `sections/`,
    `plots/`, `provenance/` and the campaign manifests. Every other family of
    file has a directory and the polar tables do not, so the top level reads
    as a directory and a drawer at once.

    The per-polar tables and their `.dat` companions are written under
    `post/<matrix>/polars/` and nothing per-polar is left loose at
    `post/<matrix>/`. THE CAMPAIGN-LEVEL FILES STAY WHERE THEY ARE: they are
    about the campaign rather than about one polar, and a move that swept them
    into a per-polar directory would satisfy a check that only looked for an
    empty top level. A test asserts both halves.

!!! requirement "FR-89 One derived file per polar and group carries everything the workspace knows <span class='srs-implemented'>implemented</span>"

    *Origin: the seventh feedback item of 2026-09-10, "crie um super
    arquivo derivado ... de forma que apenas com o arquivo se sabe tudo sobre
    aquela simulacao", and, asked again the same evening, "todas as variaveis
    que definem a condicao de voo precisam obrigatoriamente estar nesse super
    arquivo". Carried by PFS-2036.07. Evidence: tests/tier1_offline/test_post_superfile.py.*

    WHAT IT IS FOR. Knowing what one simulation was and what it produced
    currently takes the polar table, the campaign sweep table, the matrix row,
    the setup, the reference and the unsteady plots. Six files, five of them
    in different shapes.

    IT IS WRITTEN AFTER THE UNSTEADY POST-PROCESS, which settles its shape:
    every row is one CONVERGED point and there is no time series in it, so a
    reader cannot tell whether the run behind a row was steady or unsteady.
    That transparency is the point of it.

    THE NAME carries the prefix `SUPER-` instead of `POLAR-` so it is told
    apart from the other files at a glance, the swept variable written
    literally as `sweep`, and the group suffix at the end:

        post/matriz/polars/SUPER-0001_M15AL+000BE+000J+sweep_g01.csv

    IT IS COMPLETE BY CONSTRUCTION. Its column set is a SUPERSET of the union
    of what the workspace knows about that simulation: every column the polar
    table has, every parameter the unsteady plots produce with forces and
    fluids alike, RPM, the advance ratio, every variable that defines the
    flight condition, every input of the matrix row including `DESCRIPTION`,
    the flags, and everything the campaign sweep table holds.

    NO FIELD IS LEFT OUT BY JUDGEMENT, and the test is what enforces that: it
    BUILDS the union from the workspace rather than listing it, so a field
    added anywhere upstream fails the test until it reaches the file. The
    The acceptance is one sentence: if a reader has to
    open a second file to know something about that simulation, it failed.

    A ROW IS A RECORDED POINT, SO THE RECORD DECIDES WHERE THE TWO SPEAK.
    Several blocks name the same column, and from 0.17.0 the recorded flight
    condition is taken before the matrix row rather than after it. A matrix
    cell says what the workspace intends NEXT and is read from the file as it
    is today; a recorded point's conditions are what it actually ran at.
    Editing the matrix after a run therefore no longer relabels a result that
    has already happened. The matrix still supplies every key the record does
    not, which is every key of every row that has not run.

!!! requirement "FR-90 The post stage writes no file twice <span class='srs-implemented'>implemented</span>"

    Read with PFS-2058, PFS-2058.01 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: measured on 2026-09-10 while reading the reference workspace;
    it was not reported. Carried by PFS-2036.08. Evidence: tests/tier1_offline/test_run_cli.py.*

    WHAT IT IS FOR. Measured in the reference `post/matriz/`:

        sweep.csv           1012 bytes  sha256 d121faf0de4c9b7b...
        campaign_sweep.csv  1012 bytes  sha256 d121faf0de4c9b7b...

    Same length, same digest, same 27 columns. A reader who finds two files
    cannot know they are the same without hashing them, and a reader who edits
    one has silently disagreed with the other.

    `campaign_sweep.csv` is the name that survives: it says the table is about
    the campaign rather than about one polar's sweep, it is what FR-89 cites
    as one of its sources, and `sweep` is about to appear inside the name of
    every per-polar file. Both files are derived output that the post stage
    rebuilds, so removing one orphans nothing.

    The campaign sweep table is written once. A test asserts that the post
    stage produces no two files with identical bytes anywhere under
    `post/<matrix>/`, which catches this duplicate and any other, rather than
    asserting the absence of one file name.

!!! requirement "FR-91 A probe table carries where each point IS, beside what the flow did there <span class='srs-implemented'>implemented</span>"

    Read with PFS-2062, PFS-2062.02, PFS-2062.03, PFS-2062.04 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the instruction of 2026-09-11: a csv carrying the probe results, the
    xyz position of each probe and the reference frame, beside the fluid
    result (velocity, Mach and the rest); on the unsteady path the positions
    file matters particularly, because the unsteady plots never state where
    the probes are, and the decision on which quantities: every fluid property and everything a
    steady probe returns, boundary-layer information included. Evidence: tests/tier1_offline/test_probe_positions.py,
    17 cases, mutation score 7 of 7.*

    WHAT IT IS FOR. A probe result says what the flow did. It does not say
    WHERE. For a steady export the position travels with the sample; for an
    UNSTEADY one it does not, and the owning seat states the consequence directly:
    the unsteady plots do not write the position, so a reader holding an
    unsteady probe table cannot place a single one of its points. A survey
    whose coordinates live in a different file, or in no file, is a table of
    numbers about nowhere.

    THIS IS THE SAME TRANSPARENCY FR-87 AND FR-89 ARE ABOUT, applied to the
    probes: a reader of the table must not be able to tell whether the run
    behind it was steady or unsteady, and today the unsteady one is missing
    exactly the column that would let them place the data.

    A CSV under `post/<matrix>/probes/` carries, per probe point, its `X`, `Y`
    and `Z`, the NAME of the frame those coordinates are measured in, the
    solver step the sample came from, and the fluid quantities the export
    produced beside them. It is written for a steady row and for an unsteady
    row alike, under one name, `<point>_probes.csv`.

    THE SPINE IS WHAT IS IDENTICAL, and this paragraph replaces one that asked
    for identical COLUMNS. A steady probe export carries `X, Y, Z, Mach,
    Cp_ref, vx, vy, vz, vtot, Cp` and the boundary-layer columns `s_len,
    momentum_thickness, disp_thick, thickness, CF, Transition`, measured on
    `tests/tier1_offline/fixtures/probe_points_26.120.txt` line 30. An
    unsteady plots export carries ONE NUMBERED COLUMN PER PARAMETER THE ROW'S
    OWN PROBE ENTRY DECLARES, and no boundary layer at all. The two sets are
    not the same set, and the decision settles which way that resolves: take
    everything the steady probe returns, the boundary layer included. A writer
    that forced one column set would have to drop what was asked to be kept or
    invent what the solver did not measure. So `PROBE, X, Y, Z, FRAME, STEP` is
    identical on both paths and a test asserts it, and each table's fluid
    columns are its own export's, in its own names and units. `STEP` carries
    `NA` on a steady row, which has one step; since 0.23.0 EVERY spine cell
    the package cannot fill reads `NA` and none is blank, which is what a run
    recorded before 0.16.0 leaves in the position and frame columns. Until
    0.23.0 the step said `-` and those cells went empty: two spellings and a
    blank for one meaning, in one row. A value that does not apply is always `NA`.

    THE UNSTEADY GROUP IS THE ROW'S AND NOT THE FORMAT'S, and this paragraph
    once said otherwise under the word "measured". It named a six-column group
    `MACH<k>, VELOCITY<k>, VX<k>, VY<k>, VZ<k>, STATIC_PRESSURE_RATIO<k>`,
    which is what one artifact of the licensed suite DECLARES and not what any
    export in reach carries. The recorded rotor point of `pfs0160` reads
    `MACH<k>, VELOCITY<k>, STATIC_PRESSURE_RATIO<k>`, three names, because
    that row's entry asks for three. A declaration is not a measurement of an
    export, and the difference matters here because the writer composes the
    column names FORWARD from the declaration: a reader who took six for the
    format would think a three-parameter row had lost columns.

    WHERE EACH POINT IS COMES FROM THE LOOP THAT PLACED IT. The builder records
    the vertex number, the coordinates and the frame while it emits the point,
    the run stage writes them to `sims/<sim>/profiles/<sim>_probe_points.csv`,
    and the record names that file. The alternative was to re-derive the
    coordinates in the post stage through the same line, rectangle and circle
    layouts, which is a second author of one fact and disagrees with the first
    the week either is touched.

    THE NUMBERED GROUPS ARE COMPOSED FORWARD, from the parameters the artifact
    declares and the vertices the script recorded, never matched by a pattern
    against the header. Read backward, a force column of a mesh family named
    `Blade1` matches parameter `Blade` of vertex 1 and joins the survey; a test
    puts exactly that column in the table and asserts it stays out.

    THE FRAME IS NAMED AND NOT ASSUMED. A probe entry states the frame its
    points are given in, and a table that carried coordinates without saying
    which frame they are in would be as unplaceable as one carrying none.

    A STEADY EXPORT DOES NAME A FRAME, AND IT IS NOT THIS ONE. This paragraph
    said it "names no frame at all", and line 25 of the fixture it rests on
    reads `Coordinate frame for analysis: Reference`. That is the frame the
    ANALYSIS is reported in; the frame a probe entry laid its points out in is
    the entry's own, `PUSHER_SMRP` on the reference rotor row, and no export states it.
    So the column is needed for the reason given and the old sentence was
    still false. WHETHER THE EXPORT'S `X, Y, Z` ARE EXPRESSED IN THE ANALYSIS
    FRAME OR IN THE ENTRY'S is a solver-semantics question this requirement
    does not settle and must not assert: it is registered for the domain seat
    (the verification lens, 2026-09-11).

    A RUN RECORDED BEFORE 0.16.0 STILL PRODUCES ITS TABLE. It names no
    positions file, the frame cell reads `NA` (it was EMPTY until 0.23.0,
    like every other spine cell the package cannot fill), and the steady
    coordinates still come from the export as they always did. Refusing those runs would take a
    product away from a campaign that already happened.


!!! requirement "FR-92 Each datapoint collects its outputs into its own folder <span class='srs-implemented'>implemented</span>"

    Read with PFS-2058, PFS-2058.02, PFS-2064, PFS-2064.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: a swept row could not be judged past its first point, held in
    the tree as a strict expected failure since 0.16.0's sweep work and
    reported to the owning seat on 2026-09-11, whose instruction that day
    moved the fix from the assessor's SELECTION into the folder
    ARCHITECTURE. Carried by PFS-2036.10, which records the one fork taken
    without asking: which of the two point-name conventions the folder
    takes. Evidence:
    tests/tier1_offline/test_run_cli.py::test_a_swept_row_runs_end_to_end and
    tests/tier1_offline/test_sim_outputs_dir.py.*

    WHAT IT IS FOR. Every point of one case collected into a single
    `sims/<sim>/outputs/`, so from the SECOND point of a swept row onward that
    folder held two files that both read as loads tables. The standard
    assessor finds the loads spreadsheet BY CONTENT, deliberately, because a
    swept case names its outputs per point and no single literal could name
    them all; with two candidates it refused rather than guess which point ran.
    The remedy its refusal offered, naming the file, was the one its own
    documentation ruled out. A swept row therefore ran and then could not be
    judged, and this release's headline is sweeps.

    THE SELECTION WAS NOT THE DEFECT, THE LAYOUT WAS. A folder holding the
    evidence of several points cannot answer "which of these is this point's"
    from the filesystem alone, so every consumer downstream has to re-derive
    the answer from content, and each of them can get it wrong differently.
    One folder per datapoint makes the question unaskable.

    A run collects each point's declared outputs into
    `sims/<sim>/datapoints/DP-<point>/`, where `<point>` is the point tag that
    already ends the `run_id` and names the generated script, so the folder,
    the script and the run record carry one identity. This holds for every
    point of every row, steady or unsteady.

    ONE REFUSAL CHANGES ITS REASON AND NEITHER IS RELAXED. Two outputs of ONE
    point that collect to one name are still refused, at plan time and at
    collection, because they still land in one folder under one base name.

    TWO POINTS DECLARING THE SAME NAME ARE STILL REFUSED TOO, at plan time,
    AND THE REASON MOVED. They no longer collide where they are COLLECTED,
    which is each point's own folder now; they would collide where they are
    PUBLISHED, because `post/products.py` names every per-point product after
    the loads file's stem. Measured at this release's boundary, after a first
    version of this requirement had dropped that refusal on the argument that
    the points no longer meet: two points each in their own folder, both
    declaring `loads.txt` and `loads_plots.txt`, produced ONE
    `probes/loads_plots.csv` naming both runs while holding the last point's
    data, and a superfile whose runs list recorded one point twice, so the
    other was gone from the product record. They meet one layer down.

    A per-point output name remains the way to run a sweep, and nothing using
    one has to change. Making the per-point product names carry the point tag
    the folder now carries would let the refusal be lifted, and is deliberately
    NOT taken here: it moves file names a user's downstream scripts read.

    A WORKSPACE RECORDED BEFORE 0.16.0 IS STILL READ WHOLE. `outputs/` and
    `raw/` are read where a workspace holds them and neither is created. In
    those workspaces the points of a case do share a folder, so the assessor
    keeps the export whose printed operating conditions match the point it is
    judging (REV010-001), and refuses unchanged where that does not settle
    the matter. A test asserts each of the three layouts yields the same
    verdict for the same evidence.

    THE POINT'S OWN FOLDER IS THE SOLE CANDIDATE SET WHEN IT EXISTS, EMPTY
    INCLUDED, and the older folders are read ONLY where the point has none.
    That is the precedence rule and it is stated here because a test can
    otherwise only cite a code comment for it. The predicate is EXISTENCE and
    not contents, which is the difference between a refusal and a wrong
    answer: a collection that failed leaves an empty folder behind, and
    falling back from it lands on a shared folder that may hold another
    point's export. On an alpha sweep the operating-point binding above
    catches that; on an ADVANCE-RATIO sweep it cannot, because a loads export
    prints the alpha, the sideslip and the velocity it ran and never prints
    the ratio, so two points of a J sweep are indistinguishable to it.
    Measured: the point at J=1.7 was recorded CONVERGED on the export of
    J=1.3, in silence.

    A MIXED-LAYOUT SIMULATION IS THE CASE THAT DISCRIMINATES THIS, and it is
    the upgrade path rather than a curiosity: a `outputs/` left by 0.15.0
    with a point re-run under 0.16.0. Two mutants of the precedence survived
    the whole suite until a test covered it, and each refuses a correctly run
    point there.

    ONE SCRIPT PER POINT WAS THE RUN MODEL THIS RESTED ON, AND AT 0.17.0 IT
    IS NOT. This paragraph said that reusing a converged solution across the
    points of a steady sweep was a different run model and was deferred. It is
    deferred no longer: FR-95, "A steady row is ONE job and leaves ONE
    record", makes the sweep one script (FR-158 states whether its solver is
    cleared between points).

    WHAT THIS REQUIREMENT GUARANTEES IS UNTOUCHED, and the distinction is the
    reason the change is safe here. It is the FOLDER that separates a point's
    outputs, not the script: every point still collects into its own
    `datapoints/DP-<point>/`, still exports under its own names, and is still
    judged on its own evidence. What is shared is the process; what is never
    shared is the folder.


!!! requirement "FR-93 The run matrix carries nineteen columns <span class='srs-implemented'>implemented</span>"

    *Origin: the owning seat's format decision of 2026-09-12, taken after
    measuring what the free variables cell was being asked to carry. Evidence:
    tests/tier1_offline/test_matrix.py, test_matrix_upgrade.py and
    tests/tier1_offline/test_matrix_run.py.*

    SIX COLUMNS ARRIVE AND TWO MOVE. `CONFIGURATION`, `GEOMETRY`, `SYMMETRY`,
    `SYMMETRY_LOADS`, `NCPUS` and `WALLTIME` become columns of their own, and
    `HIDDEN | RUN` moves to sit directly after `POL`. Every one of the six was
    already expressible: four as keys inside the free `VAR_NAMES_VALUES` cell
    and two inside the setup artifact.

    THE RELEASE MOVES WHERE A FACT LIVES AND MAKES NO FACT REQUIRED. That is
    measured rather than promised: a row that states none of the six reads
    exactly as it did, because the committed fixtures include rows that state
    none, and one of them has never named a geometry at all.

    A COLUMN SAYS NOTHING WITH `-`, which is a single character rather than an
    empty cell so that a reader can tell "stated nothing" from "the line is
    truncated". Where a column says nothing, the older home still answers:
    `NCPUS` falls back to the cited setup's `max_parallel_threads` and
    `SYMMETRY_LOADS` to its `symmetry_loads`.

    A FACT MAY NOT BE STATED IN BOTH HOMES. A row that states one of the six
    as a column AND as a key in the free cell is refused naming both, because
    two homes for one fact is how the two come to disagree.

    `NCPUS` IS ONE NUMBER FOR EVERY PLATFORM and lives in the matrix alone. It
    reaches `SET_MAX_PARALLEL_THREADS` as the solver's thread count and, on a
    submitting run, the scheduler's processor request. While it lived in the
    setup and a cluster descriptor carried its own count, a job could reserve
    forty-eight processors and solve on eight with nothing noticing.

    THE UPGRADE IS A LADDER AND IT RENAMES NO RUN. A file in any older layout
    is converted on read, and not one cell that reaches a point tag is
    touched, so the tags that end every `run_id` in an existing manifest are
    the ones the converted file plans under and a resume still finds its
    records. A cell the conversion does not move is carried as its own bytes,
    spacing included.

!!! requirement "FR-94 A row may name its configuration, and the name configures nothing <span class='srs-implemented'>implemented</span>"

    *Origin: the owning seat's format decision of 2026-09-12. Evidence:
    tests/tier1_offline/test_matrix.py and test_workflows.py.*

    `CONFIGURATION` is the user's own name for what is in the wind, beside
    `AIRCRAFT`. It LABELS and it configures nothing, which is the whole of the
    requirement: no emitted solver command reads it, and no behaviour depends
    on it.

    IT REACHES TWO PLACES A READER OPENS: a comment at the top of the emitted
    script, written before the geometry is opened so it is the file's first
    line; and the TITLE LINE of the custom polar file, after ` - `. A label
    that reaches nothing a reader sees is a cell nobody would fill in.

    THE POLAR HEADER IS EXACTLY NINE LINES AND ITS READER COUNTS THEM, so the
    label joins line 1 rather than taking a line of its own: a tenth header
    line would make every file this release writes unreadable by the
    reference tooling. A row that states no configuration writes the title it
    always wrote, so no recorded file changes shape.

!!! requirement "FR-95 A steady row is ONE job and leaves ONE record <span class='srs-implemented'>implemented</span>"

    Read with PFS-2072, PFS-2072.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the owning seat's convention of 2026-09-12, taken with the
    predecessor toolchain's steady recipe in hand. Evidence:
    tests/tier1_offline/test_matrix_run.py and test_run_campaign.py.*

    EVERY POINT OF A STEADY MATRIX ROW RUNS IN ONE SCRIPT AND ONE PROCESS,
    and since 0.29.0 THE SOLUTION IS CLEARED BEFORE EACH POINT
    (`CLEAR_SOLUTION`, the first point of a reopened simulation included):
    COLD IS THE DEFAULT AND `COLD_START: false` IS THE OPT-IN to the warm
    start, as FR-158 states. A warm row does not clear between points, so each
    point begins from the previous point's converged solution, the panelling
    and the wake survive from one angle to the next, and the sweep costs one
    setup rather than one per point. A warm result depends on the order of
    the points, which the record states. A cold row is still ONE job; only the
    clear differs.

    AMENDED AT 0.29.0 BY FR-158. From 0.17.0 to 0.28.0 the default was warm and
    `COLD_START: True` was the opt-out, which followed the predecessor
    toolchain's steady recipe, that never cleared the solver between points.
    The 0.29.0 quality gate reversed it because a warm result depends on the
    order of the points; `build_steady_sweep` takes `cold=True` by default and
    the input glossary says the same. The one-job, one-record guarantee below
    is unchanged by the reversal.

    ONE JOB IS ONE RECORD. The record's `run_id` ends with the `sweep` token
    and never with a point tag, because the point tag is run IDENTITY and ends
    every `run_id` in every existing manifest; a record covering three points
    cannot borrow one of their tags. The record carries `job_id` and
    `points_ran`, which names every point IN THE ORDER IT RAN THEM, because a
    warm sweep's order is part of its result: the same three angles run in
    another order are not the same three numbers.

    THE JOB'S STATUS IS THE WORST OF ITS POINTS, by a stated severity order,
    so a reader triaging by status is pointed at the most serious thing that
    happened rather than the most recent.

    `RunRecord.as_points()` reads a job back one point at a time, so nothing
    downstream had to learn a new shape.

    SUPERSEDES the last paragraph of FR-92, which said that one script per
    point was the run model and that reusing a converged solution across a
    steady sweep was deferred. It is deferred no longer. FR-92's separability
    guarantee is untouched: each point still collects into its own datapoint
    folder, and it is the SCRIPT that is shared, never the folder.

!!! requirement "FR-96 A row may ask to continue a run the wall clock stopped <span class='srs-implemented'>implemented</span>"

    *Origin: the owning seat's decision of 2026-09-12, that the word RESTART
    is reused for continuity, and its measurement of 2026-09-13 that the
    solver resumes an unsteady march from a saved file. Evidence:
    tests/tier1_offline/test_workflows.py for the parser and
    tests/tier1_offline/test_restart_continuation.py for the continuation, the
    remainder arithmetic and the stamped archive.*

    `RESTART` states how to continue: `{FINISH_PENDING}`, which asks for what
    the row originally stated minus what the stopped run reached;
    `{ADDITIONAL_ITERS=<n>}`; or `{ADDITIONAL_REVS=<n>}`, which the row's own
    azimuthal step turns into time steps.

    THE WORD IS REUSED DELIBERATELY FOR A DIFFERENT THING. In the predecessor
    toolchain it named a phase-resolved march through one blade passage, which
    is an unsteady capability and not this one.

    SINCE 0.18.0 IT RUNS. A row stating `RESTART` resolves against the recorded
    run it continues, and the continuation opens that run's saved simulation
    with `OPEN <saved.fsm> ENABLE` rather than importing the mesh and building
    the case again. **The step count is a REMAINDER and not a total**, because
    the solver has already marched what it marched: a continuation that asked
    for the whole history would re-run the part already on disk and call the
    result a continuation. The time step is the row's own.

    SINCE 0.18.1 THE CONTINUATION OPENS THE ARCHIVED COPY BY ABSOLUTE PATH, and a
    `RESTART` row runs under the campaign that recorded the stopped run: a point
    of it is run when its MOST RECENT record stopped with more to do, is
    skipped when its most recent run finished or is still queued, so running
    the matrix again does not continue a continuation that already completed,
    and is REFUSED BY NAME when its most recent run failed, at plan and at the
    run's pre-flight, because a failed continuation is not retried and must
    never be passed over in silence.

    THE OUTPUTS A CONTINUATION REPLACES ARE ARCHIVED, not overwritten, into
    `archive/<day and hour>/` under that datapoint's own folder. The stamp is
    what makes a second continuation possible: a point may be continued more
    than once, and an unstamped archive would have the second continuation
    destroy the first one's evidence. A continuation's run id is
    `<campaign>/sim_<id>/r<stamp>/<tag>`, so the point tag still ENDS the run
    id, which is the invariant every existing manifest rests on.

    UNTIL 0.18.0 THE KEY WAS PARSED AND REFUSED, kept here in the past tense
    because a reader on an older release meets that behaviour and should find
    it described rather than absent: the three forms were read and the
    arithmetic existed, no builder shortened a march and nothing archived what
    a continuation would replace, so a row stating `RESTART` was refused BY
    NAME at plan, naming this release. A refusal at plan spends nothing;
    accepting the key and ignoring it spends a licensed seat re-running a
    point that was nearly done, which is what it did until 2026-09-13.

!!! requirement "FR-97 A run needs a plan, and the plan is pinned to the matrix it read <span class='srs-implemented'>implemented</span>"

    Read with PFS-2056, PFS-2056.06, PFS-2056.08, PFS-2056.12, PFS-2058, PFS-2058.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the owning seat's instruction of 2026-09-12, that the warning and
    the confirmation belong to `plan` and that without one `run` does not go.
    Evidence: tests/tier1_offline/test_run_cli.py and test_matrix_run.py.*

    `pyfs-matrix run` reads the plan receipt and refuses without one. The gate
    is on the COMMAND and not on the library entry: a caller who composes plan
    and run into one call would otherwise be made to write a file between them
    for no reason.

    THE RECEIPT CARRIES THE DIGEST OF THE MATRIX IT READ, so a matrix edited
    between planning and running is visible rather than silent. A mandatory
    plan that does not check freshness is satisfied by a stale plan, which is
    a receipt about a different study.

    `plan` SPENDS NO SOLVER TIME. It pre-flights every point, reports which
    are blocked and which are already recorded, and writes the receipt; the
    expected cost is behind `--cost`.

!!! requirement "FR-98 A row may state a wall clock, and the run watches it from inside <span class='srs-implemented'>implemented</span>"

    *Origin: the owning seat's decision of 2026-09-12, that WALLTIME is no
    longer HPC-only and drives a watchdog on the actions hook with the margin
    in the setup. Evidence: tests/tier1_offline/test_unsteady_actions.py.*

    AN UNSTEADY ROW THAT STATES `WALLTIME` REGISTERS A PAIR OF SOLVER-SIDE
    ACTIONS: a `COMMAND_LINE` python that keeps its own clock and fires once,
    and a `SCRIPT` action it rewrites, which does nothing until the clock and
    the margin meet. Where the row also exports on a counter, the clock pair
    takes positions (3) and (4) behind that pair, because the solver runs
    actions in creation order and cannot be told otherwise.

    THE MARGIN IS THE SETUP'S, twenty minutes by default: how much time to
    leave for the exports is the same question on every platform and does not
    vary with the row, while a wall clock does.

    WHAT THE RESCUE WRITES IS WHAT THE PER-STEP ACTION WRITES, from one
    implementation: the three update commands first wherever a sections,
    sectional-loads or probe export is among the outputs, then the export
    verbs, with the names claimed by the package's own output classifier. The
    outputs a stopped run leaves are the ONLY outputs it leaves, so an export
    of sections nobody updated is the whole evidence of that run being wrong.

    A RUN THE CLOCK STOPPED IS RECORDED `WALLTIME_REACHED`, WHICH IS NOT A
    FAILURE. It is the same shape as `COMPLETED_MAX_ITER`: the numbers up to
    that step are real and the user judges whether to continue. The record
    states where it stopped, without which FR-96's `{FINISH_PENDING}` has
    nothing to subtract from, and it carries the clock and the margin it was
    given, because neither can be recovered afterwards.

    WHAT IS NOT MEASURED, and it is stated here rather than left in one
    comment: whether `STOP` inside an action's script ends the RUN or only
    that script. The command database records `STOP` verified on 26.120 to
    26.123 with the manual's own note that it halts SCRIPT PROCESSING at that
    location, which is the ambiguity and not its resolution. Settling it needs
    a licensed probe that moves ONE thing, and the stop verb is kept to one
    substitutable line to make that probe cheap.

!!! requirement "FR-99 Linux is the cluster, and no cell says so <span class='srs-implemented'>implemented</span>"

    Read with PFS-2054, PFS-2054.04, PFS-2056, PFS-2056.07, PFS-2056.09 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: the owning seat's decision of 2026-09-12, that the code sees the
    environment and that a Linux run submits rather than calling the solver
    directly. Evidence: tests/tier1_offline/test_matrix_run.py.*

    THE PACKAGE READS THE PLATFORM. No matrix cell selects a cluster, so the
    same matrix, unchanged in every cell, runs locally on Windows and submits
    on Linux. A cell that must be remembered is a cell that gets forgotten,
    and a forgotten one on a cluster means a laptop-shaped run holding a login
    node for the night.

    THE SUBMISSION PROFILE LIVES IN `inputs/hpc/h<>.toml` AND THE SETUP STAYS
    MULTIPLATFORM. The profile states the scheduler's own name for the
    application, what the descriptor IS, the fields that cluster expects and
    what fills each, and the submit command argument by argument. A workspace
    carrying several profiles and nothing to say which is REFUSED rather than
    guessed, because guessing spends a queue.

    THE PROFILE TRANSLATES THE BUILD, AND THE CELL DOES NOT MOVE (0.18.1,
    PFS-2010.01.06). A row names one build, and a scheduler may know only an
    application family that covers several. The profile's `[builds]` table,
    keyed by canonical build, states what that scheduler calls each build,
    and a descriptor field writes it through `{fs_build_alias}`. A profile
    that writes the substitution and maps no alias for a build a row names is
    refused before any point is submitted, and a key that is not one
    registered build is refused when the profile is read. The table is a
    DECLARATION: it does not establish which build the scheduler starts, which
    only the build number in a collected log does, so a submitted point is not
    identity-checked before it runs.

    EACH SUBMITTED POINT RUNS IN ITS OWN DATAPOINT FOLDER (0.18.1,
    PFS-2010.01.02). The unsteady action program, its export script, the wall
    clock and its state and the descriptor are written there, so the points of
    one swept row are submitted together and none rewrites a file another's
    queued job reads; the record names the folder as `working_dir`, and the
    collect stage waits there and files the outputs in place. It holds because
    every input a point's script reads is named by absolute path. A steady row,
    one job over all its points, submits from the simulation folder, and a
    local point still runs there.

    THE FLAG THAT KEEPS A LINUX RUN LOCAL (0.27.0). `pyfs-matrix run --local`
    does not ask the cluster: a Linux machine carrying a profile runs the
    solver itself, the way Windows does, with the executable resolved as on
    Windows, and every point's executor entry says `forced_local`, so a
    profiled workspace that ran without a queue never has to be read against
    the platform. It changes nothing where nothing would have submitted.
    Evidence: tests/tier1_offline/test_matrix_run.py, the two `local` tests.

    A LINUX MACHINE WITH NO PROFILE RUNS LOCALLY. Not every Linux box is a
    cluster, and a study that never wrote a profile is saying it does not
    submit.

    A SUBMITTED POINT IS RECORDED `SUBMITTED` AND IS NOT ASSESSED. It has no
    outputs yet and no wall time of its own; the record names the descriptor
    the scheduler was handed, the profile that rendered it and whether the
    submit command ran, which is the only thing that says where the job went.
    The local solver-identity pre-flight is skipped, because a cluster's
    solver is on the cluster and asking would submit a probe job; the
    descriptor names the build the profile declares, which is not a check.

    SINCE 0.18.0 A COLLECT STAGE COMPLETES IT, and it watches the WORKSPACE
    rather than the scheduler. `pyfs-matrix collect` sweeps every `SUBMITTED`
    record, waits until each point's declared outputs are PRESENT AND
    SETTLED, then collects, assesses and rewrites that record with what the
    run did; `--watch` loops the sweep. Watching files rather than the queue
    is what keeps this free of a second scheduler vocabulary: no status
    command in the profile and no job-script template, so the same stage
    serves a cluster job, a local run somebody interrupted, and outputs a
    colleague dropped in by hand.

    SETTLED IS ASSERTED BY TWO SIGNALS THAT FAIL DIFFERENTLY, because a file
    EXISTS BEFORE IT IS FINISHED and a stage that fired on appearance alone
    would post-process a half-written table. Size and modification time
    stable across two observations catches a file still being written; the
    LAST declared output present is the stronger statement, since every
    emitted script ends with the log export and the close.

    THE DECLARED SET IS RECORDED AT SUBMISSION and is not re-read from the
    matrix at collection, so a matrix edited in between cannot change what
    the collector waits for. NO NINTH STATUS: a point whose collection
    refuses is `FAILED_INCOMPLETE_OUTPUT` with the reason, and the closed set
    stays eight.

    UNTIL 0.18.0 there was no collect stage and a `SUBMITTED` record was
    completed by hand. That sentence stood in this requirement rather than in
    a release note so a reader of the requirement learned it too, and it is
    kept here, in the past tense, for the same reason.

!!! requirement "FR-100 A row translates an alias the way it rotates one <span class='srs-implemented'>implemented</span>"

    *Origin: the 0.19.0 scope, a translation stated by the row with the
    architecture of the rotation. Evidence:
    `tests/tier1_offline/test_goal022_translate.py` (the cell grammar and its
    refusals, one surface line per boundary in the named frame, every
    owned and auxiliary frame at its new origin once, a frame whose axes are not
    the reference's, the kept hub shared with a rotation, a plot on a moved hub
    written in both frames, and the order on every run type that rotates).
    And `reports/RPT-048_what-a-per-surface-translation-does-to-shared-vertices_2026-09-14.md`
    (the split and the setup phase measured on 26.123, and a null test).
    AMENDS FR-35, whose variables cell gains the `TRANSLATE` list, and FR-71,
    whose kept frame a translation shares.*

    A row states `TRANSLATE` in its variables cell as a list of records with the
    grammar of `ROTATE`, applied in the order written:

        TRANSLATE: {DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, {...}

    `DISTANCE` is in METRES, as `ANGLE` is in degrees, and a record moves along
    ONE axis of the named frame, so a diagonal is two records. `AXIS` is
    `<frame>-<X|Y|Z>`, the frame being one the reference declares or one the
    package creates. `ALIAS` names exactly one word the reference declares, as a
    rotation's does, and `AUX_FRAMES` names frames the alias does not own that
    move with it. One row is one position: the translation is not swept.

    THE SURFACES MOVE IN THE NAMED FRAME, one `TRANSLATE_SURFACE_IN_FRAME` per
    boundary of the alias with `SPLIT_VERTICES ENABLE`, emitted after every frame
    exists and before every rotation, motion and post-processing command. The
    split is measured rather than chosen: two surfaces of one set share the
    vertices where they meet, and without it those vertices were moved once per
    surface and a set moved alone dragged the vertices of the surface it
    touched; with it every vertex of the set moves exactly once and every other
    surface stays where it was (RPT-048, on 26.123; the other registered
    builds have not been run this way).

    EVERY FRAME THE ALIAS OWNS MOVES WITH IT, plus each `AUX_FRAMES` entry and
    every frame the package placed from one of those, each once however many
    names it answers to, TO AN ABSOLUTE ORIGIN through
    `SET_COORDINATE_SYSTEM_ORIGIN`: its origin as the script placed it plus the
    distance along the named axis in reference axes. The script records where it
    placed each frame, and a frame whose placement it cannot state (one an opened
    project carries, or one turned into place about a pivot elsewhere) is
    refused by name rather than moved to a guess; so is an axis of a frame whose
    axes it cannot state. THE LEDGER READS A FRAME'S ORIGIN AS METRES, and
    `EDIT_COORDINATE_SYSTEM` carries no unit to check: a frame is placed in the
    simulation's length unit, so a translation is right only on a simulation
    whose length unit is metres.
    That a motion then spins about the moved hub follows from the frames the
    script moves and has not been run on the solver.

    `<ALIAS>_SMRP_ORIGINAL` is kept ONCE PER ALIAS before the first translation
    or rotation of it, one copy for both, and a post-processing entry naming a
    moved hub is emitted in both frames, as FR-71 states for a rotated one.

    A key a translation does not read, a missing `DISTANCE` or `AXIS`, no alias,
    a distance that is not a finite number, an axis token of another shape, an
    alias the reference does not declare or a list of them, a frame nothing
    defines, an axis of zero length, and the key on a `LEGACY` row are each
    refused at plan time naming the row.

!!! requirement "FR-101 One row on every build: the single march, the Euclidean rotor, and a refusal by name <span class='srs-implemented'>implemented</span>"

    *Origin: the 0.20.0 scope, every workflow on every registered build with the
    build as the only cell that changes. Evidence:
    `tests/tier1_offline/test_goal023_every_build.py` (every run type and case
    shape against every registered build, the cells that do not render named
    exactly, the single march on each build without actions, each feature only
    actions give refused at plan time by name, the strategy in the plan and the
    run record, one row planned under every build, and the 26.123 goldens
    unchanged). `tests/tier1_offline/test_workflows.py` (coverage derived with
    the substitute, and the Euclidean rotor's speed, axis and mark). And
    `reports/RPT-049_a-rotor-on-the-builds-before-the-rotary-motion_2026-09-15.md`
    (the unit and sense of the Euclidean angular velocity measured on 26.000
    against the rotary motion on 26.120, and the rotor mark removed on 26.100).
    `reports/RPT-051_a-rotor-on-26100-without-the-rotor-mark_2026-09-15.md`
    (the 26.100 rotor without the mark, in rev/min, recorded as a decision at
    0.20.1).
    AMENDS FR-98 and FR-96, whose wall clock and continuations are refused on a
    build without actions, and the coverage rule of the workflow table.*

    A matrix row names its build in `FS_BUILD` and nothing else about it. The
    package decides, per point and before the first emission, how the row runs
    on that build, from the command database and recorded evidence and never
    from a list of builds:

    - AN UNSTEADY ROW ON A BUILD THAT DOCUMENTS NO UNSTEADY SOLVER ACTION
      (`SET_NEW_UNSTEADY_SOLVER_ACTION`) RUNS AS A SINGLE MARCH: its plots
      declared before one solver start over every time step the row states,
      and every export after it. An unsteady row asking for no per-step
      feature renders the same script on 26.123 as it did before 0.20.0.
    - A ROW ASKING SUCH A BUILD FOR WHAT ONLY ACTIONS GIVE is refused with
      `BuildCapabilityError` at plan time: a snapshot threshold
      (`EXPORT_UNSTEADY_AFTER_ITER`, `EXPORT_UNSTEADY_AFTER_REV`), the in-run
      wall clock (`WALLTIME`), or a continuation that reads their records
      (`RESTART: {FINISH_PENDING}`, `RESTART: {ADDITIONAL_REVS=n}`). The
      sentence names the build, each feature, the builds that document the
      actions and the change to the row that runs on the build named. Nothing
      is emulated.
    - The plan's `PointPlan.march_strategy`, the run record's `march_strategy`
      and the superfile carry `"actions"` or `"single_march"` for every unsteady
      point, and None for a steady one.
    - A ROTOR ROW ON A BUILD WITHOUT THE ROTARY MOTION TYPE THAT DOCUMENTS THE
      EUCLIDEAN ROTOR (25.100 and 26.000) is written as a `EUCLIDEAN` motion
      whose `SET_MOTION_ANGULAR_VELOCITY` is the row's speed in rad/s along its
      axis, with `SET_MOTION_IS_ROTOR` along the same axis. The unit and the
      sense are measured on 26.000 (RPT-049); 25.100 was not run and rests on
      its manual's identical grammar and that measurement. A build carrying
      the rotor mark and not the angular velocity is refused naming both
      halves.
    - A ROTOR ROW ON 26.100, which documents the angular velocity and has no
      rotor mark (RPT-049), is written as a `EUCLIDEAN` motion whose
      `SET_MOTION_ANGULAR_VELOCITY` is the row's speed IN REV/MIN along its
      axis, with no rotor mark, and a comment line in the script saying both.
      The unit is a maintainer decision and not a measurement (RPT-051).

    The cells that still do not render remain unsupported and are named by the
    evidence test with their reasons: every run type on 25.000, whose
    `INITIALIZE_SOLVER` takes five settings no later edition exposes and none
    gives a default for. A solver preset or a
    post-processing artifact may still name a command a build lacks; that point
    is BLOCKED at plan time naming the command.
!!! requirement "FR-102 A point is named by its flight condition <span class='srs-implemented'>implemented</span>"

    *Origin: the cluster feedback of 2026-09-15, section 1, and the code table
    approved the same day. Evidence:
    `tests/tier1_offline/test_goal024_point_name.py` (the cell's variables in
    the cell's order, the same five reordered giving another name, the run_id,
    the folder and the files of a run, J 0.80 against J 0.84, two values that
    write one field refused at plan time, the seventeen keys of the table each
    against its written form, and the folder namer refusing anything but a
    checked name). SUPERSEDES the point tag of FR-10 and the file convention of
    FR-85 and FR-86. FR-88 is untouched: it says WHERE the polar tables live
    and names no convention.*

    A point has ONE name, and the row writes it: every variable the
    `FLIGHT_CONDITION` cell declares, in the order the cell declares them, each
    as a code and a fixed-width integer. That name ends the `run_id`, names the
    datapoint folder `DP-<name>`, and is the stem of every file of the point,
    `P<sim>-<name>`; the superfile is `SUPER-<sim>-<name>` with the swept field
    written `<code>+sweep`.

    - The codes and digits are the approved table: `M` (Mach x1000),
      `V` (m/s x10), `RE` (millions x100), `ALT` (feet), `DT` (K x10, signed),
      `RHO` (kg/m3 x1e4), `MU` (Pa s x1e9), `A` (m/s x10), `T` (K x10),
      `PS` (Pa), `AL` and `BE` (deg x10, signed), `J` (x100, signed),
      `RPM` (rev/min, signed), and `P`, `Q`, `R` (deg/s x10, signed).
    - A case authored in Python with no cell is named by its Mach number and
      then by the axes of its point, so there is ONE scheme and not two.
    - Two points of one case whose names are equal are refused AT PLAN TIME
      naming both points and what they write.
    - The run record carries `point_name` and `sweep_name`. A record written
      before 0.21.0 carries neither, and NEITHER STAGE RECOMPUTES ONE: the
      point's evidence would be filed where no record of it points. The
      products stage refuses such a record by name. AMENDED 0.21.1: `collect`
      resolves its folder from the record's own submission block, which is
      reading rather than recomputing, and refuses only a record that names no
      datapoint folder either -- a point submitted before 0.18.1, whose job ran
      in the simulation folder. Refusing it outright deadlocked a 0.20.x
      workspace with submitted points against FR-103, whose command refuses
      those same records and directs the user here. Evidence:
      `tests/tier1_offline/test_goal025_migration_deadlock.py`.

!!! requirement "FR-103 One command renames a workspace to the point names <span class='srs-implemented'>implemented</span>"

    *Origin: the same feedback, section 1: existing workspaces are renamed on
    upgrade rather than left behind. Evidence:
    `tests/tier1_offline/test_goal024_rename_command.py` (a workspace that ran
    under the 0.20 names, written back into that shape and then moved: the
    folders, the files, the scripts, the manifest, the plan, the archive, a
    second run that changes nothing, the products stage reading the renamed
    tree, the command line, and each of the four refusals).*

    `pyfs-matrix rename --workspace <root>` moves a workspace written under
    0.20.x to the names of FR-102. It reads the matrices beside `runs.json`,
    works out each record's new name from its row and its recorded point, and
    renames the datapoint folders, the scripts, the collected files, the
    manifest and the plan. The manifest it replaces is archived first, every
    change is printed, `--dry-run` rehearses it, and a second run changes
    nothing.

    BEFORE IT TOUCHES ANYTHING it refuses, by name: a record whose simulation
    has no row, a record whose recorded point the matrix no longer holds, two
    points that would share a name, and a SUBMITTED record whose folder would
    move, which is collected first. A half-renamed workspace is worse than an
    unrenamed one.

!!! requirement "FR-104 Every flight-condition variable sweeps, RPM included <span class='srs-implemented'>implemented</span>"

    *Origin: the same feedback, sections 2 and 3. Evidence:
    `tests/tier1_offline/test_goal024_sweep_any_variable.py` (a Mach sweep, a
    Reynolds sweep, an altitude sweep, a rate sweep, the state resolved per
    point, the emitted script of each point, and the refusals that remain) and
    `tests/tier1_offline/test_goal024_rpm.py` (RPM in the cell, swept, reaching
    the motion; MOTIONS winning; the three refusals and the computed velocity).
    IMPLEMENTS the rule of FR-69, which licensed any key of the cell while the
    code varied three.*

    ANY key of `FLIGHT_CONDITION` may carry the word `sweep`. A swept FLOW
    variable is resolved PER POINT, so each point carries its own density,
    velocity and Mach number, and such a row is ONE JOB PER POINT: the air
    state is a setup command the solver takes before it is initialised, so one
    process cannot hold two of them. A row that sweeps an attitude is the one
    warm job it has always been.

    `RPM` is a key of the cell, stated once for the row and reaching every
    motion that states no speed of its own, exactly as `ADVANCE_RATIO` does.

    - A `MOTIONS` record naming a speed wins over it.
    - `RPM` with `ADVANCE_RATIO` and a velocity is refused by name: the three
      are one relation, V = J x (RPM/60) x D.
    - `RPM` with `ADVANCE_RATIO` and no velocity COMPUTES the velocity, with D
      the diameter of the rotor `CLOCK_MOTION` names; a row naming no such
      rotor is refused by name.
    - The flat `RPM` of `VAR_NAMES_VALUES` is unchanged: it is one rotor's
      speed, it reaches no motion record, and a row whose records resolve to a
      speed still names its `CLOCK_MOTION`.

!!! requirement "FR-105 A body rate writes a free-stream rotation <span class='srs-implemented'>implemented</span>"

    *Origin: the same feedback, section 4. Evidence:
    `tests/tier1_offline/test_goal024_freestream_rotation.py` (one rate writing
    ROTATION about the moment point with the axis the reference declares and
    the rate in rev/min, each rate on its own axis, zero and absent writing
    CONSTANT, and the two refusals). THE SIGN the solver applies is measured on a seat,
    one axis at a time, on 26.124. Pitch in
    `reports/RPT-052_the-sense-of-a-rotating-free-stream_2026-09-15.md`, with
    its evidence at `reports/probes/RPT-052_2026-09-15_evidence.yaml`: three
    pitch rates on one wing-body, where a positive rate came back
    with the nose-down moment increment that opposes a nose-up rotation. Roll
    and yaw in the licensed probe T11,
    `reports/RPT-060_roll-and-yaw-rates-are-emitted-reversed_2026-09-23.md`,
    with its evidence at `reports/probes/RPT-060_2026-09-23_evidence.yaml`:
    seven converged solves showing that the rate emitted as written, the one
    sign of +1 of 0.21.0 to 0.26.0, solved the OPPOSITE roll and yaw rate.
    Since 0.27.0 (G13) each rate is emitted with the sign of its body axis in
    the geometry's frame, and the emitted line is scored against both probes
    by `tests/tier1_offline/test_ops2011_rate_sense_against_recorded_probes.py`.*

    A row states ONE body rate -- `roll_rate`, `pitch_rate` or `yaw_rate` -- in
    deg/s and in flight-mechanics signs, and the script writes
    `SET_FREESTREAM ROTATION` about the moment reference point of the row's
    `REF` instead of `CONSTANT`. The rate sweeps like any other variable of the
    cell.

    - Which model axis each rate turns about is the CONFIGURATION's to state:
      the reference artifact declares `[body_axes]`, and a row stating a rate
      against a reference that declares none is refused by name.
    - Two non-zero rates in one row are refused by name: the free stream turns
      about one axis at one speed.
    - Every rate zero, or no rate at all, writes `CONSTANT`.
    - The emitted rotation takes the sign of its body axis in the geometry's
      frame, x aft, y right, z up: roll and yaw are negated and pitch is not
      (0.27.0, G13). A row of 0.21.0 to 0.26.0 stating `roll_rate` or
      `yaw_rate` was solved at the opposite rate (RPT-060).

!!! requirement "FR-106 The wall clock carries its unit, and the cluster's own log is the log <span class='srs-implemented'>implemented</span>"

    *Origin: the same feedback, sections 5 and 6. Evidence:
    `tests/tier1_offline/test_goal024_walltime.py` (the units, the refusal of a
    bare number, the descriptor as written, the profile's arithmetic and the
    deadline it does not move) and
    `tests/tier1_offline/test_goal024_profile_log.py` (the command removed, the
    scheduler's own log copied to the declared name and judged, and the two
    refusals). AMENDS FR-93.*

    The `WALLTIME` cell carries its unit (`240m`, `4h`, `90s`, `1d`) and a bare
    number is refused by name: it read as seconds here and as minutes on the
    scheduler it was written for. What the descriptor's field carries is the
    HPC profile's `walltime_arithmetic` -- `wall`, the cell as written, or
    `seconds` -- and neither moves the watchdog's deadline.

    The HPC profile's `[log]` table says how that machine writes the solver
    log: `export_log = false` leaves `EXPORT_LOG` out of the script, and
    `native_log` names the file the scheduler writes, which `collect` copies to
    the name the row declared. `export_log = false` with no `native_log` is
    refused, and so are several files matching the pattern. The profile's key
    set is CLOSED, at the top level and inside `[log]`: a key outside it is
    refused by name rather than ignored, because a misplaced key is a job that
    reaches the cluster and aborts at `EXPORT_LOG`. A collected point's
    record carries what its log said: the iteration, the residual, the times
    and the file they were read from.
!!! requirement "FR-108 A point whose row was wrong is redone by naming it <span class='srs-implemented'>implemented</span>"

    *Origin: a matrix row can be wrong in a way the correction does not rename,
    and the package then had no way to run that point again: the recorded point
    is refused as a fork and resume skips it. Evidence:
    `tests/tier1_offline/test_goal026_force_rerun.py` (the named point running
    again, the points not named keeping their records, the manifest archived
    into `archive/`, the outputs archived per point, an unmatched name refused,
    the pair with resume refused before anything is read, and the per-point
    campaign that the one-job fixture cannot reach). AMENDS FR-34.*

    A point already in the manifest is REDONE when the run names it
    (`force_rerun`, CLI `--force-rerun`), by its point name, its `run_id`, or
    the job id of a swept row. Nothing is deleted: the manifest is copied whole
    under `archive/` before any record leaves it, and each named point's
    collected outputs move into that point's own `archive/<stamp>/`.

    IT NAMES POINTS. Redoing every recorded point of a matrix because one row
    was wrong spends a licensed seat per point, and a seat is the one thing
    archiving cannot return. A name no recorded point carries is refused rather
    than passed over, because a forced re-run that redid nothing reads exactly
    like one that worked. Recorded points the run does not name are skipped, so
    the flag is usable on a matrix of more than one row.

    It is refused together with resume, which SKIPS a recorded point; and a
    point of a row stating RESTART is continued rather than superseded, which
    the run says rather than passing over the flag.

    THIS AMENDS FR-34, which states resume semantics and was the only
    requirement about a manifest-recorded point. Resume skips such a point;
    this one redoes it; the refusal between them names both and says which does
    which.

!!! requirement "FR-107 A run may accept an unregistered build, on the user's word <span class='srs-implemented'>implemented</span>"

    *Origin: an installed build the package has no registration for must not
    stop a run, and registering every site's build would put site identifiers
    in a public package. Evidence:
    `tests/tier1_offline/test_goal024_unregistered_build_flag.py` (the refusal
    naming the flag, the run proceeding with it and warning, the record and the
    plan carrying it, and the library keyword). AMENDS FR-18.*

    `plan` and `run` take `--accept-unregistered-build`. Without it, a
    workstation whose installed build is not the one registered for the version
    a row names is refused, and the refusal NAMES the flag. With it the run
    proceeds, warns that compatibility is the user's to judge, and every record
    says the flag was used and carries the build the solver printed;
    `plan.json` records it too, so the rehearsal is the same command line the
    run executes. The library takes the same keyword.

!!! requirement "FR-109 A row names an actuator disc of its reference and its loading, and the run type emits it <span class='srs-implemented'>implemented</span>"

    *Origin: G06 of the 0.27.0 scope and the planning row PFS-2008.02.02, the
    actuator study through the workflow: the curated helper existed and no run
    type reached it, and a row stating the keys was refused as stating keys of
    no run type. Evidence: `tests/tier1_offline/test_g06_actuator_disc.py`
    (the disc emitted before the solver is initialised on every run type, the
    motions rotor path and the steady sweep included; the block read from the
    reference and each way it is refused; the hand; a profile resolved and
    checked at plan, the run's own copy of it written, named and hashed on every
    run type, and each form the solver would misread refused naming the line;
    each refusal of the row; the control of a row naming none; the profile
    route refused by build before any emission). On 26.124 the licensed runs of
    RPT-070 closed it: the disc by its net thrust moved the loads against a
    control row and its saved simulation names the disc, and the profile file is
    read in the form the probe measured (the rows joined by a newline, with no
    final newline).*

    A reference artifact declares an actuator disc as a top-level block of
    `kind = "actuator"`: its `frame`, `axis`, `offset_m`, `tip_radius_m`,
    `hub_radius_m`, `rpm_sign`, and optionally `blades`, `swirl` and
    `profile_units`. A row names ONE by `ACTUATOR`, states its speed by
    `ACTUATOR_RPM` (a magnitude; the block's `rpm_sign` is the hand) and
    exactly one loading, `ACTUATOR_THRUST` (net thrust in N) or `PROFILE` (the
    stem of a file of `inputs/profiles/`, rows `r,F`, resolved and checked at
    plan); every run type then emits the disc in the block's frame before the
    solver is initialised. The solver reads the run's own copy of the profile,
    written where the point runs in the form 26.124 reads (the rows joined by
    a newline, with no final newline) and hashed into the record's
    `inputs_sha256`; the user's file is never written.

    - A reference disc that no row names emits nothing.
    - A block the reference does not declare, a speed not above zero or
      missing, both loadings or neither, a profile on a block with no blade
      count, a loading key without `ACTUATOR`, and a frame the run did not
      create are each refused naming the key, before any line is written.
    - The profile route is refused on 25.000 and 25.100, whose grammar of
      `SET_PROP_ACTUATOR_PROFILE` takes no blade count.
    - A profile the solver would misread is refused at plan, naming the file
      and the line: a header or a count first, a row that is not two numbers
      separated by one comma, a number that is not finite, fewer than two rows.
    - Not measured: the disc on an unsteady or rotor row, where a motion that
      moves every frame moves the disc's; the disc under mirror symmetry;
      whether the thrust and enable commands take effect; the loads of a disc
      whose profile the solver read; and the profile command on any build but
      26.124.

!!! requirement "FR-110 The pproc declares a volume section, and each point samples it <span class='srs-implemented'>implemented</span>"

    Read with PFS-2072, PFS-2072.02 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    *Origin: G05 of the 0.27.0 scope, the basic GUI steps through the
    workflow: a volume section and its VTK or Tecplot export were reachable
    from no row. Evidence: `tests/tier1_offline/test_g05_volume_section.py`
    (the table and each shape's own keys, the section created after the solve
    and exported to the point's name, the delete before each later point of a
    warm sweep, the file never classified as a surface export, the refusal on
    both unsteady run types, and the file collected and hashed). The five
    commands it emits are verified one at a time on 26.120 to 26.124 by the
    compat probes, and a licensed row ran the whole path on 26.124, the
    rectangle exported to VTK (RPT-070, VERIFIED).*

    A pproc artifact declares at most ONE `[volume_section]`: a rectangle
    (`corners_m`) or a circle (`radii_m`, `points`) in a `plane` of a named
    `frame` at an `offset_m`, every length in metres, and a `format`, `vtk` or
    `tecplot`. SINCE 0.29.0 THE SECTION IS SAMPLED, NOT NATIVELY EXPORTED
    (FR-159): the package samples the declared plane through probes on a
    steady row, or through fluid plots on an unsteady or rotor row, and writes
    a vertex cloud to `post/<matrix>/fields/<point>_vsec.vtk` or `.dat`, with
    `_step_<STEP>` per unsteady step. No native volume section is cut or
    exported into `datapoints/DP-<point>/`.

    AMENDED AT 0.29.0 BY FR-159. In 0.27.0 and 0.28.0 each steady point cut the
    section after its solve and exported it natively to `{name}_vsec.vtk` or
    `{name}_vsec.dat` in its datapoint folder, an unsteady or rotor row that
    declared the table was refused, and a later point of a sweep deleted the
    previous section first. A historical 0.27.x or 0.28.x record keeps that
    native export. The licensed evidence cited above (RPT-070) measured the
    native path.

    - Each shape's keys are refused on the other, and a shape missing its own
      is refused naming them.
    - Not measured: any `refinement_layers` other than 1 on the native path.

!!! requirement "FR-111 A row names an additional pproc, and the post extracts it from each point's saved simulation with no solve <span class='srs-implemented'>implemented</span>"

    *Origin: G12 of the 0.27.0 scope: a finished point could not be asked for
    more without solving it again, although its final saved simulation is kept
    (FR-51) and RPT-062 measured on 26.124 what a reopened simulation gives
    back identically. Evidence: `tests/tier1_offline/test_additional_post.py`
    (the key planned READY and changing no byte of the run script on any run
    type; each plan refusal; the extraction script against one golden per
    pproc kind under `tests/tier1_offline/goldens/additional/`, never solving,
    saving, or creating a frame or a probe; the three skips of a row without
    the key, an absent saved simulation and one that does not hash as its
    record says, and the other skips; the run's record, manifest and files
    unchanged; the command line; the products marked with the pproc and a
    stale extraction skipped under its own key). The licensed end-to-end run
    of the extraction is RPT-072 (VERIFIED on 26.124).*

    A row states `ADDITIONAL_PPROC: <pproc id>` in its `VAR_NAMES_VALUES` cell;
    no builder reads it and the run record never carries it.
    `pyfs-matrix post <matrix> --additional-pproc` (library:
    `pyflightstream.run.matrix.run_additional_post`) then takes every
    recorded point of such a row whose final `.fsm` is on disk and hashes as
    its record says, copies it into `datapoints/DP-<point>/additional/<pid>/`,
    and runs one script there that opens the copy, creates the pproc's section
    distributions in the frames the run created, updates the sections, computes
    their sectional loads, exports the loads, the surface the pproc's
    `[exports]` selects, the sections, the sectional loads, the log and, on an
    unsteady point, the plots history, and closes, with no solve and no save.
    Each extraction is recorded in `additional.json` beside `runs.json`, which
    is never written; the post writes the products of every current extraction
    under `post/<matrix>/additional/<pid>/`, each entry marked with the pproc,
    `"additional": true` and the extractions it holds.

    - Refused at plan, naming the key or the table: an id the library lacks;
      an additional pproc declaring probes or a volume section (the field off
      the body does not come back, RPT-062), plots or time averaging, base
      regions, or an `[exports]` turning the sections or their loads off or a
      kind the extraction never writes on; the key on a `LEGACY` row; a row on
      a build other than 26.124.
    - Skipped by name per point: a row without the key; no saved simulation;
      one that does not hash as its record says; an extraction already made
      from the same bytes with the same artifact; a build that changed; a run
      that averaged its surface in time; a run script whose frames or
      boundaries the row no longer reproduces; a point queued, continued, or on
      an inactive row.
    - An unsteady point gives its last instant, warned at plan per row and per
      point at extraction, and recorded. The original saved simulation is
      opened only through a copy and is hashed again after the launch.
    - A workspace that submits from the machine is refused, naming `local`
      (CLI: `--local`): the submitting half is not built.
    - Not measured: any build but 26.124, a surface averaged in time reopened,
      and whether the reopened distributions the run created can be deleted.

## 0.25.0 to 0.32.0 additions

Requirements written after the specification was last reconciled with the package: the capabilities of the releases 0.25.0 to 0.31.0 that had none, and the ones 0.32.0 adds.

!!! requirement "FR-200 Every command opens with a titled block saying what it is <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066): the titled blocks of
    0.31.0 (P13) reached `pyfs-matrix plan` alone, and every other command
    printed as before. Evidence: `tests/tier1_offline/test_p0320_console.py`,
    `test_every_command_opens_with_a_titled_block_saying_what_it_is` (the
    test walks every command both parsers register, nested ones included),
    `test_the_opening_block_says_what_the_command_does_and_where_on_stderr_only`
    and `test_the_titled_block_rule_itself`.*

    Need: a user reading the console of any `pyfs-matrix` or `pyfs-workspace`
    command knows which command printed it, what it is for and which folder
    it works in, before the first line of its work.

    Requirement: the output of every `pyfs-matrix` and `pyfs-workspace`
    command opens with a titled block: the line `<program> <command>`, then,
    indented under it, `purpose:` (the command's own one-line help),
    `workspace:` (the folder, absolute, where the command has one) and, for a
    command that keeps one, `live log:`. The block goes to standard error, so
    standard output carries exactly what it carried before, byte for byte.
    `pyfs-matrix plan` keeps its own header block of 0.31.0 on standard
    output; its opening is said first only where another line would come
    before that header (a refusal).

    Solution (release 0.32.0): `pyflightstream._console` holds the shapes
    (`opening_lines`, `opens_with_titled_block`, `command_help`) and
    `pyflightstream._progress.command_console` prints the block, entered once
    by each program's `main`.

!!! requirement "FR-201 A command's warnings are held and printed together at the end <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066). Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_warnings_are_held_and_printed_together_at_the_end`,
    `test_a_refused_command_still_prints_its_held_warnings_at_the_end`,
    `test_an_interrupted_command_still_prints_its_held_warnings_at_the_end` and
    `test_a_python_caller_recording_warnings_still_receives_them`.*

    Need: a warning that arrives in the middle of a command's output is read
    as part of whatever it interrupted; together, under one title, they are
    read as what they are.

    Requirement: every command but `plan` holds the warnings it raises and
    prints them after its last line, on standard error, as one block titled
    `Warnings (<count>)`, a blank line before it, each warning in the short
    `[warning]` form of 0.31.0, in the order raised. A refusal (exit 2) and an
    interruption print the held warnings too. A warning is never swallowed:
    the filters in force decide as before, and a Python caller recording
    warnings receives each one. `plan` keeps the layout of 0.31.0, its
    `Warnings (<count>)` block right after its header block.

    Solution (release 0.32.0): `command_console(hold=True)` over
    `_console.held_warnings`, and `_progress.print_held_warnings`, the one
    printer of the block, which `plan` also calls.

!!! requirement "FR-202 A long command shows the progress of each stage <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066): `pyfs-matrix sync
    --apply` hashes, merges and copies with nothing printed until its final
    record. Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_a_stage_shows_files_and_bytes_over_the_total_the_file_elapsed_and_an_estimate`,
    `test_a_stage_with_nothing_to_do_prints_nothing_and_a_python_caller_sees_nothing`,
    `test_a_stage_that_raises_says_where_it_stopped_and_lets_the_error_through`,
    `test_tracked_counts_each_item_after_its_body_even_on_continue`,
    `test_a_tracked_loop_whose_body_raises_says_where_it_stopped_not_done`,
    `test_a_terminal_redraws_one_line_with_a_bar_and_ends_it`,
    `test_free_space_and_delete_sims_show_their_stages`,
    `test_delete_sims_removal_shows_bytes_over_the_total_it_measured` and
    `test_collect_and_post_show_their_stages`.*

    Need: a command that works for minutes says, while it works, how far each
    of its stages is, on which file, since when and for about how long more.

    Requirement: inside a console command, a stage announced through
    `stage_progress(name, total_files=..., total_bytes=...)` prints on
    standard error the line `[<name>] <files>/<total>, <bytes>/<total
    bytes>, <share>%, <MM:SS> elapsed, about <MM:SS> left, <current file>`,
    the share by bytes where the byte total is known and by files otherwise,
    the estimate the elapsed time scaled by what is left. It closes with
    `[<name>] done: ...`, or `[<name>] stopped at ...` when the stage raised
    or was interrupted, and the stage's own exception passes unchanged. A
    stage with nothing to do says nothing; a Python caller outside a console
    command sees nothing; the progress never changes a stage's result and
    never raises. The stages shown: `free-space` (one per recipe table, per
    simulation), `delete-sims` (measure, then remove, the removal also by
    the bytes the measure found), `collect` (per submitted point) and `post`
    (per simulation); the bytes appear where the stage knows them, and
    `sync` and `restore` call the same interface from their own packages of
    0.32.0.

    Solution (release 0.32.0): `pyflightstream._progress.StageProgress`
    (`advance`, `each`), `stage_progress` and `tracked`, the one-line hook of
    a loop (`size=` adds each item's known bytes); the line's shape is
    `_console.progress_text`.

!!! requirement "FR-203 A long command writes a live log while it runs <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066). Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_a_long_command_writes_its_live_log_while_it_runs` (the log is read
    from inside the running command),
    `test_only_the_long_commands_keep_a_live_log_and_only_in_a_workspace`,
    `test_a_second_live_log_of_the_same_second_gets_its_own_name` and
    `test_a_live_log_that_cannot_be_written_is_named_and_the_command_runs_on`.*

    Need: a command whose console is lost (a closed window, a cluster job)
    leaves what it said on disk as it said it, not only the record written at
    its end.

    Requirement: `sync`, `restore`, `free-space`, `delete-sims`, `collect` and
    `post`, run in a campaign workspace (a folder with `runs.json` or
    `inputs/`), write `logs/<command>-<UTC stamp>.log`, where the stamp is
    `YYYYMMDDTHHMMSSZ` and a name already taken gains `-2`, `-3`. It opens
    with `# <program> <command> started <time>`, receives every line the
    console shows (standard output included, the progress as plain lines)
    and is flushed at each line, and ends with `# finished <time> after
    <MM:SS>` (or `# ended with exit <code>`, `# ended by <exception>`). The
    opening block names it. A folder that is not a campaign workspace gets
    no file, a log that cannot be written is named in the opening block and
    the command runs on, and `post --diagnostics`, which changes no file of
    the workspace, writes none.

    Solution (release 0.32.0): `command_console(live_log=True)` wraps standard
    output and error for the length of the command; `LIVE_LOG_COMMANDS` names
    the six commands.

!!! requirement "FR-204 Without a terminal the progress is plain periodic lines <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066): a cluster job and a
    redirected output are not terminals. Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_without_a_terminal_the_progress_is_plain_periodic_lines` and
    `test_the_live_log_of_a_terminal_session_gets_plain_lines_not_redraws`.*

    Need: a redrawn bar written to a file or a scheduler's log is a wall of
    carriage returns; a job's log needs lines it can be read by.

    Requirement: where standard error is a terminal, a stage's line is
    redrawn in place, a bar of 20 cells after its name, at most every 0.2 s,
    and cleared before any other line. Where it is not, the stage prints a
    plain line at its first advance, then at most one every
    `PLAIN_PERIOD_S` (10 s), then its closing line, and never a carriage
    return. The live log always receives the plain lines, whatever the
    console is.

    Solution (release 0.32.0): `StageProgress._show` and the constants
    `PLAIN_PERIOD_S`, `REDRAW_PERIOD_S` and `BAR_CELLS` of
    `pyflightstream._progress`.

!!! requirement "FR-205 A returned failure of a stage kept off a terse console is said there <span class='srs-implemented'>implemented</span>"

    *Origin: ARCH2-B1 of the 0.31.0 review, registered for 0.32.0.
    Evidence: `tests/tier1_offline/test_p0320_console.py`,
    `test_a_returned_failure_of_a_verbose_only_stage_shows_on_a_terse_console`,
    `test_a_verbose_only_stage_that_finishes_stays_off_a_terse_console` and
    `test_a_caller_that_asked_quiet_keeps_it_for_a_returned_failure`;
    the first fails on the 0.31.0 condition.*

    Need: `workspace_activity(verbose_only=True)` keeps a stage that runs
    once per point off a console without `--verbose`; a stage that returned a
    failure without raising vanished from that console with it.

    Requirement: on a console without `--verbose`, a `verbose_only` stage
    whose result says it failed (`failed`, or an outcome starting with
    `FAILED`) prints its `[<stage>] failed` line; its `started` line, and
    both lines of a stage that finished, stay off that console, and the
    activity log records every one as before. A caller that passed `quiet`
    keeps it.

    Solution (release 0.32.0): the condition of the closing line in
    `pyflightstream._progress.workspace_activity`.

!!! requirement "FR-206 A warning-free plan has one blank line before its first block <span class='srs-implemented'>implemented</span>"

    *Origin: QA2-1 of the 0.31.0 review, a test gap registered for 0.32.0.
    Evidence: `tests/tier1_offline/test_p0320_console.py`,
    `test_a_warning_free_plan_has_one_blank_line_before_its_first_block`.*

    Need: the blank line that separates the header block of `pyfs-matrix
    plan` from its first block is written by a branch of its own when no
    warning is printed between them, and nothing tested that branch.

    Requirement: a plan that raises no warning prints its header block, one
    blank line, then its first block (`Cases`): never two blank lines and
    never none.

    Solution (release 0.32.0): the behavior of 0.31.0, now pinned by the
    test above.

!!! requirement "FR-210 A file of the records family is restored from the workspace's archive, exactly <span class='srs-implemented'>implemented</span>"

    *Need: `sync`, `--force-rerun`, `delete-sims` and `rename` archive
    `runs.json` before they rewrite it, and nothing brought a copy back.
    Requirement: `pyfs-matrix restore <kind>` (library:
    `pyflightstream.run.records.restore`) previews by default, writes with
    `--apply`, archives the current file first in the same form, and puts the
    archived bytes back unchanged, for `runs.json`, `storage_management.json`,
    `additional.json`, `post/<matrix>/products.json` and
    `post/<matrix>/plan.json`. Solution, release 0.32.0: the archive forms
    `archive/<stem>-<stamp>[.n][-label].json` and
    `post/<matrix>/archive/<stamp>/<name>`, the newest copy by default,
    `--stamp` (the copy of exactly that name) and `--matrix` (a folder
    name under `post/`) to choose, and every restore written under the
    `runs.json` lease a run, a collect and a sync hold, plus the storage or
    additional-post record's own lease (RST-6). Trace:
    `tests/tier1_offline/test_p0320_records.py`
    (`test_restore_previews_then_applies_each_kind_archiving_the_current_file`,
    `test_restore_takes_the_newest_stamp_and_a_named_one`,
    `test_restore_refuses_what_it_cannot_do_exactly`,
    `test_restore_of_the_manifest_refuses_while_a_run_holds_its_lock`,
    `test_rst6_every_restore_refuses_while_a_sync_holds_the_runs_lease`,
    `test_rst6_restore_writes_holding_the_runs_lease_and_the_records_own`,
    `test_restore_sorts_every_name_the_archive_pattern_accepts`,
    `test_restore_of_a_named_stamp_takes_the_copy_of_that_exact_name`,
    `test_restore_refuses_a_matrix_stem_that_leaves_post`,
    `test_the_archive_spellings_are_the_workspaces`,
    `test_the_cli_restores_and_rebuilds`).*

    - Refused, nothing changed: an unknown kind; no archived copy, naming
      where it was looked for; a stamp no copy carries, naming the stamps
      there are; archives of several matrices and none named; a copy that is
      not readable JSON, or a manifest copy that is not a list of records; a
      restore of any kind while `runs.json.lock` is held, as during a sync,
      or while the restored record's own lease is held.
    - The writers of the storage record, the products record, the plan
      receipt and the additional-post record do not archive their file yet, so
      for those kinds the copies found are the ones a restore made.

!!! requirement "FR-211 Run records are rebuilt from the simulation folders, proved by the script the version that ran renders <span class='srs-implemented'>implemented</span>"

    *Need: when no archive holds a record, a simulation whose outputs exist is
    invisible to the post. Requirement: `pyfs-matrix rebuild` (library:
    `pyflightstream.run.records.rebuild`) mints each record again by running
    its matrix row in a throwaway copy of the workspace with nothing submitted,
    rebuilds it only when the executed script equals the script this package
    version renders for that row (workspace root and interpreter set aside),
    and completes it through the collect stage run read-only
    (`collect_without_writing`); a truncated or missing output is
    `FAILED_INCOMPLETE_OUTPUT`, never `CONVERGED`; nothing in the workspace is
    written until `--apply`. Solution, release 0.32.0: the run layer's
    executor choice, build binding, per-row versions and manifest lease
    exposed publicly (`campaign_executor`, `bind_row_builds`,
    `row_versions`, `manifest_lock`), the workspace tree compared before and
    after, and a `REBUILT` warning on every rebuilt record. Trace:
    `tests/tier1_offline/test_p0320_records.py`
    (`test_rebuild_from_sims_gives_the_record_back_and_writes_nothing_until_asked`,
    `test_rebuild_refuses_an_edited_script_naming_the_version`,
    `test_rebuild_refuses_a_version_other_than_the_one_that_ran`,
    `test_rebuild_refuses_another_version_even_when_its_script_matches`,
    `test_rebuild_writes_nothing_when_the_workspace_changed_meanwhile`,
    `test_rebuild_of_a_truncated_output_is_failed_incomplete_never_converged`,
    `test_rebuild_of_a_missing_output_is_failed_incomplete_never_converged`).*

    - Refused per simulation, naming the reason: an executed script this
      version does not render (naming the version), a run a known record of
      another version wrote (naming both versions), a compressed simulation, a
      retired one, one with no declared output.
    - A collection that would move an output, copy the scheduler's log, write
      a translated surface export or expand a compressed simulation is not
      made; the record stays `SUBMITTED` for `pyfs-matrix collect`.
    - Without `--out`, `--apply` appends the run ids `runs.json` lacks after
      archiving it, or writes `runs.json` when there is none.

!!! requirement "FR-212 A rebuild written to another manifest never touches runs.json <span class='srs-implemented'>implemented</span>"

    *Need: a rebuilt record must be comparable with the original before it
    replaces anything. Requirement: `--out NAME` writes the rebuilt records to
    that file in the workspace root and never writes `runs.json`; the name
    `runs.json`, a file that exists, and a name that is not a file directly in
    the root are refused before any work. Solution, release 0.32.0: the
    refusals come before anything is read, the file is created
    exclusively, and it holds the rows of `runs.json` with each rebuilt
    record in the place of the row of its run id and the other rebuilt
    records after them. Trace: `tests/tier1_offline/test_p0320_records.py`
    (`test_rebuild_out_refuses_runs_json_and_an_existing_file_before_any_work`,
    `test_rebuild_out_never_touches_runs_json`,
    `test_rebuild_out_holds_the_rebuilt_record_of_a_named_recorded_sim`).*

!!! requirement "FR-213 Every simulation on disk is rebuilt for comparison, only into another manifest <span class='srs-implemented'>implemented</span>"

    *Need: comparing what the folders say with `runs.json` needs the recorded
    simulations rebuilt too. Requirement: `--all-sims` rebuilds every
    simulation folder under `sims/`, recorded or not, and is refused without
    `--out`. Solution, release 0.32.0: with `--all-sims` the written file holds
    the rebuilt records only. Trace: `tests/tier1_offline/test_p0320_records.py`
    (`test_rebuild_all_sims_requires_out_and_rebuilds_the_recorded_ones_too`).*

!!! requirement "FR-214 A row switched off after it ran still describes that run <span class='srs-implemented'>implemented</span>"

    *Need: a row set to `RUN 0` after it ran is still the row that ran.
    Requirement: the rebuild sets `RUN 1` on that row in the throwaway copy of
    the matrix only, leaves the matrix unchanged, and says so in the record.
    Solution, release 0.32.0 (RST-2). Trace:
    `tests/tier1_offline/test_p0320_records.py`
    (`test_rst2_a_row_switched_off_after_it_ran_still_describes_the_run`).*

!!! requirement "FR-215 A build the submission profile no longer maps takes the scheduler's name of its time <span class='srs-implemented'>implemented</span>"

    *Need: a run on a build the profile's `[builds]` table no longer maps is
    refused by the run layer before a descriptor is written. Requirement:
    `--build-alias BUILD=ALIAS` names the scheduler's word for that build,
    the build itself by default; it enters only the job descriptor of the
    throwaway run, never the solver script, and the record and the result say
    which alias was assumed. Solution, release 0.32.0 (RST-3): the profile is
    extended in memory only. Trace: `tests/tier1_offline/test_p0320_records.py`
    (`test_rst3_a_build_the_profile_no_longer_maps_takes_the_alias_in_the_descriptor_only`).*

!!! requirement "FR-216 A POL in no current matrix waits for the matrix revision that ran <span class='srs-implemented'>implemented</span>"

    *Need: a row deleted or renumbered after it ran leaves a folder no matrix
    names. Requirement: the rebuild names the simulations that wait for the
    revision that ran (`waiting_for_matrix`) and rebuilds them from
    `--matrix <file>`. Solution, release 0.32.0 (RST-4). Trace:
    `tests/tier1_offline/test_p0320_records.py`
    (`test_rst4_a_pol_in_no_current_matrix_waits_for_the_revision_that_ran`).*

!!! requirement "FR-217 A run on a cluster restored on Windows keeps its own root and style <span class='srs-implemented'>implemented</span>"

    *Need: a script executed on a cluster names a POSIX root with forward
    slashes, and a rebuild on Windows renders backslashes. Requirement: the
    identity check compares with the separators normalised and each side's
    own root replaced by one token, and the rebuilt record writes its paths
    in the run's root and style, never with the separators mixed. Solution,
    release 0.32.0 (RST-5). Trace: `tests/tier1_offline/test_p0320_records.py`
    (`test_rst5_a_cluster_run_restored_on_windows_keeps_the_runs_own_root`).*

!!! requirement "FR-218 A SUBMITTED record is pointed to collect, unless every simulation is judged from its outputs <span class='srs-implemented'>implemented</span>"

    *Need: a rebuild must not invent the end of a job, and a comparison of
    every folder must not keep a status the outputs contradict. Requirement:
    without `--all-sims` a `SUBMITTED` record is not rebuilt and is pointed to
    `pyfs-matrix collect`; with `--all-sims` that status is ignored and each
    simulation takes the status its outputs support, except a folder written
    within the last quiet window (`QUIET_WINDOW_S`, 30 minutes), which stays
    `SUBMITTED`. Solution, release 0.32.0 (RST-7). Trace:
    `tests/tier1_offline/test_p0320_records.py`
    (`test_rst7_submitted_records_point_to_collect_without_all_sims`,
    `test_rst7_all_sims_ignores_submitted_and_judges_the_outputs`).*

!!! requirement "FR-219 A drifted input is named, and inputs from another origin are accepted <span class='srs-implemented'>implemented</span>"

    *Need: an input changed after the run (a pproc group renamed, an export
    line switched, the loads frame line, a plot type) makes the executed script
    differ, and refusing or accepting that wholesale says nothing about which
    input changed. Requirement: the refusal names each changed line with its
    drift class and the input the package renders it from now; `--inputs-from
    <folder>` lays another origin's `inputs/` over the workspace's in the
    throwaway copy, and each rebuilt record names the inputs taken from there
    whose bytes differ; the workspace's inputs are never overwritten.
    Solution, release 0.32.0 (RST-8). Trace:
    `tests/tier1_offline/test_p0320_records.py`
    (`test_rst8_a_drifted_input_is_named_and_another_origin_is_accepted`,
    `test_rst8_each_drift_class_is_named_with_the_input_it_comes_from`).*

!!! requirement "FR-220 Sync compares every simulation folder of both workspaces, recorded or not <span class='srs-implemented'>implemented</span>"

    *Need: a workspace holds simulation folders that no record names,
    most copied by hand from a cluster, and `sync` said nothing about them:
    it merged the records and brought files without naming which folders
    each side holds and which no record carries. Requirement: every sync
    entry names the `sims/sim_*` folders of main and of the other workspace,
    compacted ones included, those only in main, only in the other and in
    both, and every folder main holds or will hold that no record of the
    merged manifest carries; `pyfs-matrix sync` prints the counts and the
    folders without a record. Solution, release 0.32.0: the entry's `sims`
    block (`main`, `other`, `only_main`, `only_other`, `both`,
    `without_record`) in `pyflightstream.workspace.storage.sync_workspaces`;
    a folder a `delete-sims` note names is accounted for by the note and
    left out of `without_record`, and so is a simulation of the other
    workspace that the sync's level does not bring. Trace:
    `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_sync_all_folders_names_every_sim_folder_of_both_sides`,
    `test_p0320_sync_all_folders_counts_a_compacted_sim_and_the_cli_prints_them`,
    `test_p0320_sync_all_folders_without_record_names_only_what_main_will_hold`,
    `test_p0320_sync_all_folders_leaves_out_a_folder_a_delete_sims_note_names`).*

!!! requirement "FR-221 Sync rebuilds the records of folders without one only when asked <span class='srs-implemented'>implemented</span>"

    *Need: the folders without a record stay invisible to `post` until a
    record exists, and rebuilding them is not what every sync should do.
    Requirement: `sync` never rebuilds a record by default; with `--restore`
    (library: `restore=True`) an applying sync rebuilds the records of the
    folders without one through `pyflightstream.run.records.rebuild`, after
    it released the `runs.json` lease, and the preview names the folders
    it would restore; a refused rebuild is written in the entry and the
    files the sync copied stand; `--restore` with `--runs` naming another
    manifest is refused, because the rebuild appends to `runs.json` only.
    Solution, release 0.32.0: the entry's `restore` block (`asked`, `sims`,
    `result` without the bulky records, `error`) and the storage record of
    the call. Trace: `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_sync_restore_is_off_by_default`,
    `test_p0320_sync_restore_rebuilds_the_orphans_after_the_lease_is_released`,
    `test_p0320_sync_restore_reports_a_refused_rebuild_and_keeps_the_sync`,
    `test_p0320_sync_restore_with_another_manifest_is_refused`,
    `test_p0320_sync_the_cli_passes_restore_and_include_archives`).*

!!! requirement "FR-222 A sync copy never leaves a partial file under the target's name <span class='srs-implemented'>implemented</span>"

    *Need: a sync over a network share can be interrupted, and a copy
    written in place left a truncated file where the whole one belonged,
    or had already moved main's own copy to the archive. Requirement: every
    file and matrix a sync brings is written to a temporary name in the
    target's folder, checked against the source's digest, and only then
    renamed over the target; an overwritten file stays in place, archived
    by a copy, until its replacement is whole; an interruption removes the
    temporary file and leaves the target as it was. Solution, release
    0.32.0: `_atomic_copy` in `workspace/storage.py`, the temporary name
    `.<name>.<pid>.pyfs-sync.tmp`, never brought by a later sync. Trace:
    `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_sync_atomic_an_interrupted_copy_leaves_no_partial_target`,
    `test_p0320_sync_atomic_an_interrupted_overwrite_keeps_mains_copy_in_place`,
    `test_p0320_sync_atomic_a_finished_copy_leaves_no_temporary_file`,
    `test_p0320_sync_atomic_a_temporary_file_a_killed_sync_left_is_never_brought`).*

!!! requirement "FR-223 Sync skips archive folders unless asked, and says how much it skipped <span class='srs-implemented'>implemented</span>"

    *Need: from the post level up the sync brought the whole `post/` tree,
    with every `post/<matrix>/**/archive/<stamp>/` earlier posts left,
    hundreds of files each read twice over the network. Requirement: a
    sync skips every file under a folder named `archive`, in `post/` and
    inside a simulation, unless `--include-archives` (library:
    `include_archives=True`); the entry and the preview state how many
    archive files and bytes were skipped. Solution, release 0.32.0:
    `files.archives_skipped` (`files`, `bytes`) in the sync entry and the
    line `archive: N file(s), X skipped` of `pyfs-matrix sync`. Trace:
    `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_sync_skip_archives_by_default_and_counts_what_was_skipped`,
    `test_p0320_sync_skip_archives_include_archives_brings_them`,
    `test_p0320_sync_the_cli_passes_restore_and_include_archives`).*

!!! requirement "FR-224 inputs/matrices/ is a matrix home equal to the workspace root <span class='srs-implemented'>implemented</span>"

    *Need: matrices are kept at the root or in `inputs/matrices/`, and a
    command that looked in one home only missed the matrix, or read one
    stem twice and refused every POL of it as stated by two matrices.
    Requirement: the sync, the plan's POL census and the post find a matrix
    in either home; one stem in both homes is read once when the two files
    hold the same bytes, and refused, naming both paths, when they differ;
    in the post the refusal is a warning naming both paths and the
    products fall back to the run records, never blocking. Solution,
    release 0.32.0: `pyflightstream.workspace.matrix_by_stem` and
    `find_matrix`, read by `workspace/storage.py`, `workspace/matrix.py`
    (the census), `post/superfile.matrix_rows` and the post stage's matrix
    warning; a sync that replaces a matrix main keeps in both homes
    replaces both. Trace: `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_matrices_home_one_stem_in_both_homes_is_read_once_or_refused`,
    `test_p0320_matrices_home_sync_reads_an_identical_pair_once_and_refuses_a_differing_one`,
    `test_p0320_matrices_home_sync_replaces_every_copy_main_keeps`,
    `test_p0320_matrices_home_the_census_reads_an_identical_copy_once`,
    `test_p0320_matrices_home_the_census_refuses_a_differing_copy_naming_both`,
    `test_p0320_matrices_home_the_census_refuses_in_the_words_of_the_one_rule`,
    `test_p0320_matrices_home_the_post_finds_the_matrix_in_inputs_matrices`,
    `test_p0320_matrices_home_the_post_refuses_a_differing_pair_naming_both`).*

!!! requirement "FR-225 A sync holds the runs.json lease for the whole of its merge and copy <span class='srs-implemented'>implemented</span>"

    *Need: a restore ran while a sync wrote into the same workspace, and
    the sync held the `runs.json` lease around its merge only. Requirement:
    an applying or previewing sync holds `runs.json.lock` from the merge of
    the records to the end of the copy, the input links and the matrices,
    so a restore, a run, a collect or a second sync refuses (or waits on
    the lease) while it writes; a sync started while the lease is held is
    refused naming it; a restore asked of the sync runs after the lease is
    released. Solution, release 0.32.0: one `_manifest_lock` block in
    `_sync_one`. Trace: `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_rst6_the_sync_holds_the_runs_lease_so_a_second_writer_is_refused`,
    `test_p0320_sync_restore_rebuilds_the_orphans_after_the_lease_is_released`).*

!!! requirement "FR-226 sync, free-space and delete-sims read the manifest --runs names <span class='srs-implemented'>implemented</span>"

    *Need: a rebuilt manifest beside `runs.json` must be usable by the
    storage commands without replacing `runs.json`. Requirement: `sync`,
    `free-space` and `delete-sims` take `--runs NAME` (library: `runs=`),
    resolved by `pyflightstream.run.records.resolve_manifest`, and a name
    that is not a JSON file directly in the root is refused before any
    work. `sync` merges the other workspace's `runs.json` into the named
    manifest of main and leaves main's `runs.json` untouched;
    `delete-sims` reads the records from the named manifest and removes
    them from it, archived first as `archive/<stem>-<stamp>.json`, and
    refuses `--matrix-products regenerate` with it; `free-space` reads the
    named manifest IN ADDITION to `runs.json`, so naming one never protects
    fewer files. Solution, release 0.32.0: `runs=` on `sync_workspaces`,
    `free_space` and `delete_sims`, and the command line passing the name
    through. Trace: `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_runs_name_sync_merges_into_the_named_manifest_only`,
    `test_p0320_runs_name_a_bad_name_is_refused_before_any_work`,
    `test_p0320_runs_name_delete_sims_edits_the_named_manifest_only`,
    `test_p0320_runs_name_delete_sims_regenerate_with_another_manifest_is_refused`,
    `test_p0320_runs_name_free_space_protects_what_the_named_manifest_names`,
    `test_p0320_runs_name_the_cli_passes_the_name_to_sync_and_storage`).*

!!! requirement "FR-227 Sync reports its hash, merge and copy stages to the progress <span class='srs-implemented'>implemented</span>"

    *Need: a long sync printed only its final summary. Requirement: the
    sync reports three stages, `sync hash` (the files compared, with their
    count), `sync merge` (the records) and `sync copy` (the files and bytes
    copied), to the stage progress of the package. Solution, release
    0.32.0: `pyflightstream._progress.stage_progress` called in `_sync_one`.
    Trace: `tests/tier1_offline/test_p0320_sync_matrices.py`
    (`test_p0320_sync_reports_its_three_stages_to_the_progress`).*

!!! requirement "FR-230 The post and the collect read the records of another manifest <span class='srs-implemented'>implemented</span>"

    *Need: a workspace can hold more than one set of run records for the same
    simulations, for example a manifest rebuilt from the simulation folders
    beside the one the runs wrote, and the post of each must be possible
    without renaming either file. Trace (P0320-RUNS-NAME):
    `tests/tier1_offline/test_p0320_b3_post_records.py`, the tests
    `test_p0320_runs_name_post_reads_another_manifest_into_its_own_folder`,
    `test_p0320_runs_name_resolves_the_workspace_of_a_manifest`,
    `test_p0320_runs_name_refuses_a_manifest_that_is_not_there`,
    `test_p0320_runs_name_collect_completes_the_named_manifest`,
    `test_p0320_runs_name_collect_once_writes_only_the_named_manifest` and
    `test_p0320_post_and_collect_report_their_stage_progress`.*

    `pyfs-matrix post --runs NAME` and `pyfs-matrix collect --runs NAME` shall
    read the run records of the manifest `NAME`, a JSON file directly in the
    workspace root, and `runs.json` shall be neither read nor written. The
    collect shall complete the submitted records of that manifest in place,
    under that manifest's own lock. A name that is not a file directly in the
    root, and a named manifest that is not there, shall be refused by name with
    exit status 2, never read as an empty manifest. `--runs runs.json` is the
    default workspace, unchanged. Both commands report their stage to the
    progress interface.

    Solution, release 0.32.0: `pyflightstream.run.records.manifest_workspace`
    resolves the name through `resolve_manifest` and returns a
    `ManifestWorkspace` whose `manifest_path` is the named file, so every
    reader and the three writers of the records follow it.

!!! requirement "FR-231 A post of other records writes its products apart and never over the default ones <span class='srs-implemented'>implemented</span>"

    *Need: the products of a post of another manifest are made to be compared
    with the default ones, so neither may overwrite the other. Trace
    (P0320-POST-RUNS-APART):
    `tests/tier1_offline/test_p0320_b3_post_records.py`, the tests
    `test_p0320_runs_name_post_reads_another_manifest_into_its_own_folder`,
    `test_p0320_post_runs_apart_twice_archives_inside_its_own_folder`,
    `test_p0320_runs_name_collect_posts_the_named_manifest_apart` and
    `test_p0320_runs_name_refuses_the_name_of_the_from_sims_folder`.*

    The products of `post --runs NAME` shall be written to
    `post/<matrix>@<stem>/`, `<stem>` the manifest's name without `.json`, and
    those of `post --from-sims` (FR-232) to `post/<matrix>@sims/`, each with its
    own `products.json`, `post.log`, `archive/` and measurement reports under
    its own `reports/`. Every byte under `post/<matrix>/` and under the
    workspace's `reports/` shall be left as the default post wrote it. A
    manifest named `sims.json` shall be refused, since its folder would be the
    one of `post --from-sims`. The columns inside the folder are those of the
    default post, and so are the file names of `post --runs NAME`; the file
    names of `post --from-sims` carry the names its records were assembled
    with (FR-232).

    Solution, release 0.32.0: `ManifestWorkspace.products_dir` and
    `ManifestWorkspace.reports_root` name the apart folder; the post stage asks
    the workspace for both (`CampaignWorkspace.reports_root` is the root, so a
    default post writes where it always did).

!!! requirement "FR-232 The post assembles the records from the simulation folders and refuses by name what it cannot recover <span class='srs-implemented'>implemented</span>"

    *Need: points run outside the package have no `runs.json` and no script to
    compare with, and their exports must still be posted with the package's
    products. Trace (P0320-POST-NO-MANIFEST):
    `tests/tier1_offline/test_p0320_b3_post_records.py`, the tests whose names
    begin `test_p0320_post_no_manifest_`, and
    `test_p0320_steps_per_revolution_is_refused_without_from_sims`.*

    `pyfs-matrix post MATRIX --from-sims` shall assemble the run records in
    memory, one per loads export found under `sims/sim_<POL>/` of a row of the
    matrix (outside its `archive`, `scripts` and `inputs` folders), and post
    them to `post/<matrix>@sims/` (FR-231). No manifest shall be written.

    - The point is the value of the row's sweep at the angles the export
      reports; the point's other exports are the files beside it named its
      stem plus the suffix of another export kind, never a file whose name
      only begins with the stem; its name is its `DP-<name>` folder's, else the export's
      stem; its status is the collect's assessment of its exports.
    - The flight condition is the row's, with the swept value in place,
      resolved with the setup's pins by the package's resolver; the reference
      block and the aliases are the row's reference.
    - The averaging window of a point with a time history is the row's
      `LAST_REVS_AVG` or `LAST_ITERS_AVG`, cut over the steps of its plots
      export; `--steps-per-revolution N` states the clock of a window in
      revolutions.
    - Refused by name, and that point or that row left out, never guessed: a
      reference that does not resolve (the aliases and the reference block); a
      condition the row and its setup do not resolve; an export whose angles
      are no value of the sweep, or a row sweeping anything but an angle over
      more than one value; two exports at one point; a time history with no
      window in the row; a window in revolutions with no
      `--steps-per-revolution`. Each refusal is printed and written into the
      post's log, and every assembled record says in the log that it was
      assembled.
    - A record assembled here carries no rotor block, so the rotor tables and
      the per-rotor reductions of its point are the post's named skips.
    - `--from-sims` is refused with no matrix, beside `--runs` and beside
      `--additional-pproc`; `--steps-per-revolution` is refused without
      `--from-sims`.

    Solution, release 0.32.0: `pyflightstream.run.records.assemble_records`
    and `from_sims_workspace`, whose records refuse every manifest writer.

!!! requirement "FR-240 A row names a CCS file and the solver lofts one of its components as a wing <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-1 of the 0.32.0 scope (GEO-066 section 2.4): no CCS command
    was reachable from a matrix row, 0 of 12 wing commands. Need: a wing mesh
    generated by the solver from the cross-sections of a CCS file, chosen by
    the row, with nothing meshed by hand. Solution, release 0.32.0: the
    `[import.ccs]` table of the geometry sidecar and the curve route of
    `pyflightstream.cases.ccs_wing`, reached from `_open_geometry` by one hook.
    Licensed round 1 on 26.124 accepted the route with the saved simulation
    listing the new boundary (probe C1) and `CCS_WING_MESH_SUBDIVISIONS CHORD
    30` changing the wing's faces from 4484 to 588 (C2 against C1). Trace:
    `tests/tier1_offline/test_p0320_ccs.py`, the tests named `test_p0320_ccs1_wing_*`
    and `test_p0320_ccs1_a_loft_*` (P0320-CCS1-WING).*

    A row whose `GEOMETRY` names a file with the `.csv` or `.ccs` suffix
    under `inputs/geometries/` is a CCS row. Its sidecar
    `<stem>.boundaries.toml` states `[import]` with the unit of the file's
    coordinates and `[import.ccs]` with `kind = "wing"` and `component`, the
    component counted from 1 in the order of the file's `Component` lines.
    Every run type then emits, before any other command, `CAD_CREATE_INITIALIZE`,
    `CAD_CREATE_IMPORT_CURVE_CCS <units> 1 <component>` with the file on the
    next line, `CAD_CREATE_CURVE_SELECT -1`, one `CCS_WING_MESH_SUBDIVISIONS`
    line per stated count (`subdivisions = { chord, span }`), and
    `CAD_CREATE_WING_MESH_FROM_CCS <name> <mark_trailing_edges>
    <trailing_edge> <close_ends> <loft_u> <loft_v>`, the name being the first
    entry of the sidecar's `boundaries`; then `SET_SIMULATION_LENGTH_UNITS
    METER` and the boundary inventory from the sidecar.

    - The loft defaults are `mark_trailing_edges = true`, `trailing_edge =
      "SHARP"`, `close_ends = "TRUE"`, `loft_u = "C2"` (chordwise) and
      `loft_v = "C0"` (spanwise).
    - Refused before any line is written, naming the row: a CCS file with no
      `[import.ccs]` table; a table beside a file that is not a CCS file; a
      component the file does not hold; a sidecar naming no boundary or more
      than the loft and its control surfaces make; a boundary name carrying
      whitespace; `units = "FILE"`, and `units = "OTHER"`, which names no
      length; mesh operations or `[import.cad]` beside
      the table; the raw-mesh tables `[trailing_edges]`, `[wake_termination]`
      and `[base_regions]`; a setup loading a saved solver initialization.
    - Refused when the row is planned: a table naming no component, and a key
      another kind reads.
    - Not measured: the route inside a whole campaign row with a solve
      (licensed round 2).

!!! requirement "FR-241 A row names a CCS file and the solver lofts one of its components as a fuselage <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-1 of the 0.32.0 scope, 0 of 10 fuselage commands reachable.
    Need: a fuselage mesh generated by the solver from a CCS component, chosen
    by the row. Solution, release 0.32.0: `kind = "fuselage"` in
    `[import.ccs]`, emitted by `pyflightstream.cases.ccs_fuselage`. Licensed
    round 1 on 26.124 accepted the route with the saved simulation listing the
    new boundary (probe C4). Trace: `tests/tier1_offline/test_p0320_ccs.py`,
    `test_p0320_ccs1_fuselage_is_lofted_from_its_component`,
    `test_p0320_ccs1_a_loft_refuses_the_file_unit` and
    `test_p0320_ccs1_the_three_emitters_are_the_route_each_kind_takes`
    (P0320-CCS1-FUSELAGE).*

    A CCS row whose `[import.ccs]` says `kind = "fuselage"` emits the curve
    route's prelude of FR-240 and `CAD_CREATE_FUSELAGE_MESH_FROM_CCS <name>
    <close_ends> <loft_u> <loft_v>`, where `loft_u` is the radial and
    `loft_v` the axial continuity, both `C2` by default.

    - The refusals of FR-240 apply; a wing key (`trailing_edge`,
      `mark_trailing_edges`, `subdivisions`, `control_surfaces`) or a
      revolution key on a fuselage is refused when the row is planned.

!!! requirement "FR-242 A row names a CCS file and the solver revolves one of its components into a body of revolution <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-1 of the 0.32.0 scope, 0 of 10 body-of-revolution commands
    reachable. Need: a body of revolution generated by the solver from a CCS
    profile, chosen by the row. Solution, release 0.32.0: `kind =
    "revolution"` in `[import.ccs]`, emitted by
    `pyflightstream.cases.ccs_revolution`. Licensed round 1 on 26.124
    accepted the route with the saved simulation listing the new boundary
    (probe C5). Trace: `tests/tier1_offline/test_p0320_ccs.py`,
    `test_p0320_ccs1_revolution_is_revolved_about_the_reference_axis_it_names`,
    `test_p0320_ccs1_revolution_default_is_a_full_turn` and
    `test_p0320_ccs1_a_key_the_kind_does_not_read_is_refused_at_binding`
    (P0320-CCS1-REVOLUTION).*

    A CCS row whose `[import.ccs]` says `kind = "revolution"` emits the curve
    route's prelude of FR-240 and `CAD_CREATE_REVOLVE_MESH_FROM_CCS <name> 1
    <axis> <start_angle_deg> <end_angle_deg> <close_ends> <loft_u> <loft_v>`:
    the profile turns about `axis` (`X` by default) through the origin of the
    reference frame, from 0 to 360 degrees by default.

    - The refusals of FR-240 apply; a wing key on a body of revolution is
      refused when the row is planned.
    - Not stated by the manual and not assumed: what a negative or a reversed
      pair of angles does.

!!! requirement "FR-243 A CCS wing declares its gapped control surfaces with all ten arguments <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-2 of the 0.32.0 scope, the helper PFS-2005.05. Need: the
    control surface of a CCS wing declared from the geometry's sidecar.
    Licensed round 1 on 26.124 refused the eight-token line the manual's own
    sample prints (`NEW_CCS_WING_CONTROL_SURFACE PYFS_AIL 0.5 0.9 0.25 0.25 0.5
    20.0 1.0`, "Review command syntax and arguments", probe C3), while SRC-752
    p.303 declares ten parameters. Solution, release 0.32.0: each
    `[[import.ccs.control_surfaces]]` table of a wing becomes one line with
    SPACE and AXIS always written. Trace: `tests/tier1_offline/test_p0320_ccs.py`,
    the tests named `test_p0320_ccs2_*` (P0320-CCS2-CONTROL-SURFACE).*

    A wing's `[[import.ccs.control_surfaces]]` states `name`, `v0`, `v1`,
    `u0`, `u1`, `hinge_height`, `angle_deg`, `slot_gap_pct`, and optionally
    `space` (`PARAMETRIC`, the default, or `REAL`) and `axis` (`Y` by
    default); each becomes `NEW_CCS_WING_CONTROL_SURFACE <name> <v0> <v1> <u0>
    <u1> <hinge_height> <angle_deg> <slot_gap_pct> <space> <axis>` after the
    curve selection and the subdivisions and before the loft, in the order
    written. The sidecar may name the boundaries the control surfaces add
    after the wing's own name.

    - Refused when the row is planned, naming the field: `u0` or `u1` not
      above 0 and below 0.5; `hinge_height` outside 0 to 1; `v1` not above
      `v0`; PARAMETRIC limits outside 0 to 1; a name carrying whitespace; a
      control surface on a kind other than a wing.
    - Not measured: the ten-argument line on a licensed run, and which
      boundaries the control surface adds (licensed round 2). Builds whose
      grammar has eight arguments (26.100, 26.101) refuse the line at the
      emitter.

!!! requirement "FR-244 A row chooses the shedding direction of a CCS file's relaxed trailing edges <span class='srs-implemented'>implemented</span>"

    *Origin: G35 (N87) of the 0.32.0 scope. Need: the row chooses the direction
    of a Relaxed_TE component's parametric shedding line. The direction exists
    only in the CCS file's line `Relaxed_TE;u;v1;v2;direction` (SRC-752 p.85);
    the script commands `NEW_CCS_FUSELAGE_RELAXED_TE` and
    `NEW_CCS_REVOLVE_RELAXED_TE` take no direction (SRC-752 pp.306, 309).
    Licensed round 1 on 26.124 imported one fuselage with the digit 0 and with
    1 by `CCS_IMPORT` (probes G35a, G35b): both accepted, and the two saved
    simulations differ in five per-face lines, the axial file marking a set of
    faces 79 apart and the azimuth file a run of 47 consecutive faces; `CCS_IMPORT`
    of a three-component file named one boundary per component (probe C0).
    The same reading found `script.helpers.RelaxedTrailingEdge` counting four
    leading values and a fifth for the direction, so the manual's
    `0.5;0.2;0.8;1` read as a line with no direction and was restated with
    five values. Solution, release 0.32.0: `kind = "file"` in `[import.ccs]`,
    the row key `CCS_SHEDDING`, and the helper counting the manual's three
    values. Trace: `tests/tier1_offline/test_p0320_ccs.py`, the tests named
    `test_p0320_g35_*` (P0320-G35-SHEDDING).*

    A CCS row whose `[import.ccs]` says `kind = "file"`, with `units =
    "FILE"`, emits `CCS_IMPORT` with `CLOSE_COMPONENT_ENDS DISABLE`,
    `UPDATE_PROPERTIES DISABLE`, `CLEAR_EXISTING ENABLE` and the file, and
    declares one boundary per component, in the file's order, named after its
    `Component` line. A row stating `CCS_SHEDDING` (`AXIAL` or `0`, `AZIMUTH`
    or `1`, registered on every run type) imports instead the run's own copy
    `<stem>.ccs_shedding.<ext>`, written where the point runs and hashed into
    the record, with every `Relaxed_TE` line restated in that direction; the
    user's file is never written. `parse_relaxed_trailing_edge` reads the
    line with or without the `Relaxed_TE` keyword, three values or four with
    the direction, and renders it as written.

    - Refused naming the row: `CCS_SHEDDING` on a loft; on a file with no
      `Relaxed_TE` line; a direction that is neither; a unit other than
      `FILE`; boundaries that are not the file's components in order.
    - A line stating no direction keeps stating none when the row asks for
      the axial direction, which it already means.
    - Not measured: the effect of the direction on a solution (licensed
      round 2).

!!! requirement "FR-250 A per-probe fluctuation report beside the time mean of per-step fields <span class='srs-implemented'>implemented</span>"

    *Origin: her answer Q19 ("Média + medir flutuação"), GEO-066 2.5.
    Evidence: `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-INFLOW-FLUCTUATION).*

    **Need.** A time mean of an unsteady run's per-step probe fields hides how
    much the inflow moves about it. Before a mean stands in for the field, the
    engineer must see the fluctuation per probe.

    **Requirement.** Given the last `K` per-step fields of one run, the
    package reports for each probe the population standard deviation (divided
    by `K`) of each velocity component and of the magnitude, in m/s. It refuses
    fewer than `K` steps on disk, steps that are not consecutive integers, any
    step whose probes differ from the first step's by more than 1e-6 m, and a
    single steady field. The report alone (`--fluctuation-only`) needs `--last`.
    For `K` steps of `v0 + a sin(2 pi k / K)` on one component, with `K` a
    multiple of 4, the standard deviation is `a / sqrt(2)`.

    **Solution (release 0.32.0).**
    `pyflightstream.workspace.fields.fluctuation_report`,
    `render_fluctuation` and `write_fluctuation`; `pyfs-workspace field
    time-mean --fluctuation` writes `<stem>.fluctuation.csv` beside the mean
    and names it, with its sha256, in the provenance record;
    `--fluctuation-only --last K` writes the report alone. The column and
    product definitions are on the post-processing definitions page.

    **Trace.** `test_p0320_inflow_fluctuation_population_std_of_a_sine`,
    `test_p0320_inflow_fluctuation_refuses_what_is_not_one_survey`,
    `test_p0320_inflow_fluctuation_folds_into_time_mean_with_provenance`,
    `test_p0320_inflow_fluctuation_only_refuses_without_last`,
    `test_p0320_inflow_fluctuation_only_refuses_more_steps_than_on_disk`.

!!! requirement "FR-251 A product table is copied into the installed frame <span class='srs-implemented'>implemented</span>"

    *Origin: her answer Q6a ("vamos ter os dois"), GEO-066 2.5. Evidence:
    `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-INSTALLED-FRAME).*

    **Need.** A table computed on the isolated (image) wheel is wanted in the
    installed frame too, and both must be kept.

    **Requirement.** The installed-frame copy is the isolated table mirrored
    through `y = 0`: the columns the definitions page lists change sign, the
    azimuths map `psi -> -psi mod 360`, all else is copied; blade and family
    names do not change; the copy is written beside the input, never
    overwrites, keeps the one comma-free alias line of a rotor table, and
    applying it twice returns the input. The sectional `Fx`, `Fz` and `Moment`
    are not negated unless named. The classification has one home, the
    definitions page, and the code reads one list held equal to it by a test.

    **Solution (release 0.32.0).**
    `pyflightstream.post.inflow_tools.to_installed_frame` and
    `installed_frame_columns`, with `FLIPPED_COLUMNS` and `AZIMUTH_COLUMNS`.

    **Trace.** `test_p0320_installed_frame_flips_the_classified_columns`,
    `test_p0320_installed_frame_is_an_involution_and_never_overwrites`,
    `test_p0320_installed_frame_keeps_the_alias_line_and_flips_named_columns`,
    `test_p0320_installed_frame_classification_has_one_home_the_definitions_page`.

!!! requirement "FR-252 The blade-view harmonics of a custom inflow, with their shares and reduced frequency <span class='srs-implemented'>implemented</span>"

    *Origin: GEO-066 2.5, beyond the plan's `--inflow-fft` (0.30.0). Evidence:
    `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-INFLOW-HARMONICS).*

    **Need.** The plan reports `n95` per radius; the engineer also needs how
    the perturbation's variance divides among harmonics, its size in degrees,
    the reduced frequency it implies and how all of it moves with the advance
    ratio of one fixed field.

    **Requirement.** For a field in a YZ plane and a rotor axis along X, per
    radius and advance ratio `J`: the variance share of harmonics 1 to 8 of the
    angle-of-attack perturbation, its rms and half peak-to-peak in degrees, the
    plan's own `n95`, `k_1P = Omega c / (2 mean V_rel)`, `k_eff = n95 k_1P`,
    and the suggested `PASSAGE_POSITIONS = ceil(n_max / N + 1)`. Another axis is
    refused. A uniform field at 5 degrees of angle of attack gives a first
    harmonic share of 1.

    **Solution (release 0.32.0).**
    `pyflightstream.post.inflow_tools.blade_view_harmonics`,
    `inflow_harmonics_map` and `write_inflow_harmonics`, over the plan's own
    reading `pyflightstream.cases.qsteady.blade_inflow_angles`; the tables
    `inflow_harmonics.csv` and `inflow_harmonics_J.csv`.

    **Trace.** `test_p0320_inflow_harmonics_uniform_field_at_aoa_is_first_harmonic`,
    `test_p0320_inflow_harmonics_n95_agrees_with_the_plan_inflow_fft`,
    `test_p0320_inflow_harmonics_refuses_an_axis_that_is_not_x`,
    `test_p0320_inflow_harmonics_j_map_writes_the_two_tables`.

!!! requirement "FR-253 The probes inside the body are filled from the ray outside it <span class='srs-implemented'>implemented</span>"

    *Origin: her answer of 2026-09-30 ("fill-interior (Recommended)"), step 5
    of the field chain 0.31.0 did not do. Evidence:
    `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-FILL-INTERIOR).*

    **Need.** A survey plane crosses the body; its probes inside carry no
    inflow and must not be read as one.

    **Requirement.** Every probe with `r < r_body` about the x axis (default
    0.38 m) takes the velocity of the probe at `r >= r_body` with the smallest
    radius on the same azimuth ray (within 1e-3 rad). Positions do not change,
    the count replaced is stated, a probe with no partner on its ray is
    refused, and, like every field operation, it previews by default, writes
    only with `--apply`, records its provenance and never overwrites unasked.

    **Solution (release 0.32.0).**
    `pyflightstream.workspace.fields.fill_interior`; `pyfs-workspace field
    fill-interior --r-body`.

    **Trace.** `test_p0320_fill_interior_takes_the_nearest_value_on_the_same_ray`,
    `test_p0320_fill_interior_refuses_a_ray_with_no_point_outside_the_body`,
    `test_p0320_fill_interior_cli_previews_then_applies_with_provenance`.

!!! requirement "FR-260 The post stage reads the solver's acoustic export <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-POST, section 2.6 part 4 of the 0.32.0 scope. Evidence: the export of the licensed round-1 probe on build 26.124 (`tests/tier1_offline/data/acoustic_signals_probe_a1.txt`), `tests/tier1_offline/test_p0320_noise_post.py::test_p0320_noise_post_reads_the_real_export_fr_260`, `::test_p0320_noise_post_refuses_a_bad_export_fr_260`.*

    Need: A user who exports the acoustic signals of an unsteady point holds a text file the package must read back.

    Requirement: `read_acoustic_signals(path)` returns one `AcousticSignal` per observer, in file order, with the position and the `PO` pressure against the observer time; a file that is unreadable, empty, lacks a position, a `PO` column or samples, or holds a non-numeric row is refused with a `ProductError` naming the line.

    Solution (release 0.32.0): `pyflightstream.post.acoustics.read_acoustic_signals`, the format of `docs/post-processing-definitions.md`, section The acoustic signals product.

!!! requirement "FR-261 Per observer, the pressure against time and its spectrum <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-POST, section 2.6 part 4 of the 0.32.0 scope. Evidence: the export of the licensed round-1 probe on build 26.124 (`tests/tier1_offline/data/acoustic_signals_probe_a1.txt`), `tests/tier1_offline/test_p0320_noise_post.py::test_p0320_noise_post_spectrum_of_a_cosine_fr_261`, `::test_p0320_noise_post_refuses_a_nonuniform_time_fr_261`.*

    Need: A reader wants each observer's record and its frequency content as tables.

    Requirement: For each observer the post writes the pressure table and the one-sided amplitude spectrum of the pressure over the observer time with the sampling stated; a record whose time step is not constant, or of fewer than two samples, gets no spectrum, is named in `post.log` and blocks nothing.

    Solution (release 0.32.0): `spectrum_of` and `write_acoustic_products`, files `<point>_<n>_<observer>_pressure.csv` and `_spectrum.csv` under `acoustics/`.

!!! requirement "FR-262 The overall sound pressure level of each observer <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-POST, section 2.6 part 4 of the 0.32.0 scope. Evidence: the export of the licensed round-1 probe on build 26.124 (`tests/tier1_offline/data/acoustic_signals_probe_a1.txt`), `tests/tier1_offline/test_p0320_noise_post.py::test_p0320_noise_post_oaspl_fr_262`.*

    Need: One number per observer to compare records.

    Requirement: OASPL is `20 log10(p_rms / 20e-6 Pa)`, `p_rms` about the mean of the record; a silent record is `NA`.

    Solution (release 0.32.0): `oaspl_db`, the `OASPL_DB` column of `<point>_acoustics_summary.csv`.

!!! requirement "FR-263 The blade-passage harmonics of each observer <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-POST, section 2.6 part 4 of the 0.32.0 scope. Evidence: the export of the licensed round-1 probe on build 26.124 (`tests/tier1_offline/data/acoustic_signals_probe_a1.txt`), `tests/tier1_offline/test_p0320_noise_post.py::test_p0320_noise_post_blade_passage_harmonics_fr_263`, `::test_p0320_noise_post_na_and_notes_when_the_record_lacks_blades_fr_263`.*

    Need: A rotor's noise concentrates at multiples of its blade-passage frequency.

    Requirement: From the rotor's blade count and speed in the point's record, harmonic `n` is at `n * blades * rpm / 60` hertz and is read at the nearest bin; without blades or speed, above the Nyquist frequency or below one bin the values are `NA`, with a line in `post.log`.

    Solution (release 0.32.0): `blade_passage_harmonics`, `<point>_acoustics_bpf.csv` (four harmonics per rotor and observer).

!!! requirement "FR-264 The directivity on an arc, and the post-stage hook <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-POST, section 2.6 part 4 of the 0.32.0 scope. Evidence: the export of the licensed round-1 probe on build 26.124 (`tests/tier1_offline/data/acoustic_signals_probe_a1.txt`), `tests/tier1_offline/test_p0320_noise_post.py::test_p0320_noise_post_arc_directivity_fr_264`, `::test_p0320_noise_post_writes_the_products_fr_261_to_fr_264`, `::test_p0320_noise_post_the_post_stage_hook_fr_264`, `::test_p0320_noise_post_the_hook_asks_nothing_of_a_plain_record_and_never_blocks_fr_264`.*

    Need: Observers placed on an arc give the directivity of the source.

    Requirement: When at least four observers are coplanar and on one circle (relative tolerance 1e-3) the post writes their angle about the centre and OASPL; a point whose record lists acoustic signals gets all the products above, and a record listing none is left alone.

    Solution (release 0.32.0): `arc_of`, `<point>_acoustics_directivity.csv`, and the post stage's `_acoustic_products` reading the export the record lists among its outputs, the entry ending `_acoustic_signals.txt` (FR-290).

!!! requirement "FR-265 A row key switches the acoustic sources on in an unsteady setup, before the solver initialises <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-SOURCES, section 2.6 part 1 of the 0.32.0 scope. Evidence: the licensed round-1 probes A0 and A1 on build 26.124 (`reports/compat/CMP-26124_2026-09-30_acoustics.yaml`, `ACOUSTIC_SOURCES` verified); `tests/tier1_offline/test_p0320_e2_noise_emission.py::test_p0320_noise_sources_row_key_switches_acoustic_sources_before_initialization`, `::test_p0320_noise_sources_reach_a_motions_row`, `::test_p0320_noise_sources_are_registered_on_the_unsteady_run_types_only`, `::test_p0320_noise_sources_value_outside_the_command_is_refused`.*

    Need: A user who wants the noise of an unsteady run has the solver record its acoustic sources during the march, which it does only when switched on before it initialises.

    Requirement: The row key `ACOUSTIC_SOURCES: ENABLE` (or `DISABLE`, the control) of an `unsteady` or `unsteady_rotor` row, a flat rotor row or a `MOTIONS` row alike, emits `ACOUSTIC_SOURCES <mode>` in the setup, before `INITIALIZE_SOLVER`; a row without it emits no acoustic command; any other value is refused naming the key; the steady run types do not register the key.

    Solution (release 0.32.0): `pyflightstream.cases.acoustics` (`ACOUSTIC_KEYS`, `emit_acoustic_setup`), registered on the two unsteady run types and called by each unsteady builder before its clock; the row's keys in `docs/acoustic-emission.md`.

!!! requirement "FR-266 Observers declared by the row as points, from a file of the library, or as an acoustic section, with their time window <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-OBSERVERS, section 2.6 part 2 of the 0.32.0 scope. Evidence: round-1 probe A1 on build 26.124 (`CREATE_NEW_ACOUSTIC_OBSERVER`, `ACOUSTIC_OBSERVERS_IMPORT`, `SET_ACOUSTIC_OBSERVER_TIME` and `CREATE_ACOUSTIC_SECTION` verified in `reports/compat/CMP-26124_2026-09-30_acoustics.yaml`); `tests/tier1_offline/test_p0320_e2_noise_emission.py::test_p0320_noise_observers_as_points_with_the_observer_time`, `::test_p0320_noise_observers_imported_from_the_point_s_copy_of_a_file`, `::test_p0320_noise_observers_as_an_acoustic_section_after_the_signals`, `::test_p0320_noise_observers_a_malformed_declaration_is_refused_naming_the_key`, `::test_p0320_noise_observers_without_sources_are_refused`, `::test_p0320_noise_observers_file_resolves_at_bind_and_refuses_a_malformed_file`, `::test_p0320_noise_observers_a_file_on_a_simulation_not_in_metres_is_refused`, `::test_p0320_noise_observers_a_section_is_placed_in_the_frame_it_names`.*

    Need: The signal is computed at observers, which a study places as points, as a list prepared in a file, or as a grid for a directivity pattern, each over a time window of its own.

    Requirement: `ACOUSTIC_OBSERVERS: NAME X Y Z, ...` creates each named observer in metres in the reference coordinate system, converted to the simulation's unit; `ACOUSTIC_OBSERVERS_FILE: <stem>` names `inputs/acoustics/<stem>.csv` (a count line, then that many `x,y,z` lines), resolved and checked when the row binds, whose copy the run writes in the point's folder and hashes, and which the solver imports; `ACOUSTIC_SECTION: {PLANE / OFFSET / RADIAL_OBSERVERS / AZIMUTH_OBSERVERS / INNER_RADIUS / OUTER_RADIUS, FRAME optional}` creates one annular grid after the signals are computed, into `<point>_acoustic_section/`; `ACOUSTIC_OBSERVER_TIME: T0 T1 N` sets the window. Refused, each naming the key: observers without `ACOUSTIC_SOURCES` or without the time window, the window without an observer, a declaration not in its form, two observers of one name, a frame the run does not create, a file that is missing or not in its form, the file key on a `LEGACY` row or on a simulation not in metres.

    Solution (release 0.32.0): `pyflightstream.cases.acoustics` (`acoustic_request`, `emit_acoustic_setup`, `emit_acoustic_signals`, `resolve_observers_file`, `read_observers_file`), `SimCase.acoustic_observers_file` bound by `workspace.matrix`.

!!! requirement "FR-267 The signals are computed and exported at the end of the run <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-COMPUTE-EXPORT, section 2.6 part 3 of the 0.32.0 scope. Evidence: round-1 probe A1 on build 26.124 (`EXPORT_ACOUSTIC_SIGNALS` verified, `COMPUTE_ACOUSTIC_SIGNALS` accepted with its effect not isolated, `reports/compat/CMP-26124_2026-09-30_acoustics.yaml`); `tests/tier1_offline/test_p0320_e2_noise_emission.py::test_p0320_noise_compute_export_at_the_end_of_the_run`, `::test_p0320_noise_compute_export_sources_alone_compute_nothing`, `::test_p0320_noise_compute_export_needs_its_declared_output`.*

    Need: The signals exist only once the solver computes them from the recorded sources, and a user holds them only once they are exported to a file.

    Requirement: A row declaring any observer emits `COMPUTE_ACOUSTIC_SIGNALS` after `START_SOLVER`, then, with point or file observers, `EXPORT_ACOUSTIC_SIGNALS` to the point's declared `<point>_acoustic_signals.txt`, then the section, all before the point's saved simulation and other exports; a row stating the sources and no observer computes nothing and declares no file; a case whose outputs lack the export is refused naming the helper that declares it.

    Solution (release 0.32.0): `emit_acoustic_signals`, called by the unsteady solve-and-export step; the export declared by `with_acoustic_signals` in the run layer's point names, for the plan and the run alike.

!!! requirement "FR-268 The exported signals and the section's files are collected and hashed in the record <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-COLLECT, section 2.6 part 3 of the 0.32.0 scope. Evidence: `tests/tier1_offline/test_p0320_e2_noise_emission.py::test_p0320_noise_collect_the_export_and_the_section_are_collected_and_hashed` (a matrix row through the real plan and run path with a stub solver), `::test_p0320_noise_collect_lists_the_section_files_beside_the_collected_outputs`, `::test_p0320_noise_collect_refuses_a_section_file_left_before_the_run`, `::test_p0320_noise_collect_a_submitted_point_names_its_section_files`.*

    Need: A signal is evidence only when the record names the file and binds it to its bytes, like every other output of the point.

    Requirement: The signals file is a declared output of the point, collected into its datapoint folder and hashed in `outputs_sha256`; every file of `<point>_acoustic_section/` but the run's own note is listed in the record's outputs, on a local run and on a submitted point `pyfs-matrix collect` completes, and hashed in `outputs_sha256` on a local run (a completed submitted point hashes none of its outputs, the section's files included); the observer file's copy is hashed among the inputs; none of these files is ever classified as a surface export or a loads table; a point whose section folder already holds a file other than the note before the solver runs is refused as a leftover, naming the file, and nothing runs.

    Solution (release 0.32.0): `cases.acoustics.acoustic_section_outputs`, called by the local point path of `run` and by `run/collect.py`; `cases.acoustics.acoustic_section_leftovers`, asked by the point path of `run` before the solver starts; `cases.classify_outputs` asks `is_acoustic_output` for records of 0.32.0 on.

!!! requirement "FR-269 The acoustic toolbox in the wrong order is refused <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-ORDER, section 2.6 parts 1 and 3 of the 0.32.0 scope, and the ordering rules of the command database (`commands/acoustics.yaml`). Evidence: `tests/tier1_offline/test_p0320_e2_noise_emission.py::test_p0320_noise_order_sources_after_initialization_are_refused`, `::test_p0320_noise_order_compute_and_export_on_a_steady_run_are_refused`, `::test_p0320_noise_order_a_steady_row_stating_the_keys_is_refused`, `::test_p0320_noise_order_a_continuation_with_acoustic_keys_is_refused`.*

    Need: Sources switched on after the solver initialises record nothing, and signals computed on a steady run or before a solve have no unsteady solution to read; either would spend a seat on a run whose signals mean nothing.

    Requirement: The acoustic setup emitted into a script that already holds `INITIALIZE_SOLVER` is refused; the computation and the exports on a steady run, or before `START_SOLVER`, are refused; a steady row stating an acoustic key is refused by the row-key guard naming the run types that read it; a continuation of a row stating acoustic keys is refused, since whether the recorded sources survive the saved simulation is not measured.

    Solution (release 0.32.0): the refusals of `emit_acoustic_setup`, `emit_acoustic_signals` and `refuse_acoustics_on_a_continuation`, each a `CampaignConfigError` naming the case.

!!! requirement "FR-290 The post reads the acoustic export the record lists among its outputs <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-POST and P0320-NOISE-COLLECT, integration defect found after wave 1: the post looked for an `acoustic_signals` field that `RunRecord` does not have, so the noise products were unreachable from a real record. Evidence: `tests/tier1_offline/test_p0320_noise_post.py::test_p0320_noise_post_the_record_lists_the_export_as_an_output_fr_290` (a synthetic `unsteady_rotor` record through `write_campaign_products`, with the trimmed real export), `::test_p0320_noise_post_the_post_stage_hook_fr_264`, `::test_p0320_noise_post_the_hook_asks_nothing_of_a_plain_record_and_never_blocks_fr_264`.*

    The post stage shall find the acoustic export of a point among the
    `outputs` of its run record, as the entry whose name ends with
    `ACOUSTIC_SIGNALS_SUFFIX` (`_acoustic_signals.txt`, defined once in
    `pyflightstream.cases.acoustics`), the way the run layer records it. A
    record whose outputs list none asks for no acoustics and nothing is said. An
    export that cannot be read is skipped by name with a warning and blocks
    nothing.

    Solution, release 0.32.0: `_acoustic_products` in `pyflightstream.post.products`
    reads the record's outputs and the suffix `pyflightstream.cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX`.

!!! requirement "FR-291 The storage record is archived before each write <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE, GEO-066 2.3 item 1. Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_the_storage_record`.*

    Before `storage_management.json` is rewritten, the previous file shall be
    copied to `archive/storage_management-<stamp>.json`, the form
    `pyfs-matrix restore storage` reads, so that a restore brings back the file
    as it stood before the last call.

    Solution, release 0.32.0: `record_storage_call` calls
    `pyflightstream.workspace.naming.archive_previous`.

!!! requirement "FR-292 The additional-post record is archived before each write <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE, GEO-066 2.3 item 1. Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_the_additional_record`.*

    Before `additional.json` is rewritten, the previous file shall be copied to
    `archive/additional-<stamp>.json`, so that `restore additional` brings it
    back.

    Solution, release 0.32.0: `CampaignWorkspace.append_additional` calls
    `archive_previous`.

!!! requirement "FR-293 The plan receipt and the products record are archived, not replaced or removed <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE, GEO-066 2.3 item 1; `products.json` used to be removed before a rebuild (ARCHITECTURE.md 5.9). Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_the_plan`, `::test_p0320_restore_archive_the_products_record_is_archived_not_removed`.*

    Before a matrix's `plan.json` is rewritten, by a plan or by a rename, and
    before a post rebuild removes and rewrites the matrix's `products.json`, the
    previous file shall be copied to `post/<matrix>/archive/<stamp>/<name>`, the
    form `restore plan` and `restore products` read. A plan of a campaign with no
    matrix, which keeps its plan at the workspace root, is not archived, since
    no restore kind reads it.

    Solution, release 0.32.0: the plan writer, the rename and the post rebuild
    call `archive_previous` with the matrix stem.

!!! requirement "FR-294 A copy for the archive that fails warns and never blocks the write <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE. Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_a_failed_copy_warns_and_never_raises`.*

    When the archive copy of a previous record cannot be made, the writer shall
    warn with a `PyflightstreamWarning` naming the file and shall write anyway;
    the archive names are spelled in one place,
    `pyflightstream.workspace.naming`, which `restore` also reads.

    Solution, release 0.32.0: `archive_previous`, `free_root_archive` and
    `free_matrix_archive` in `pyflightstream.workspace.naming`.

!!! requirement "FR-270 A wheel's sectional load is tabulated over its disc, by radius and azimuth <span class='srs-implemented'>implemented</span>"

    *Need.* The sectional loads of a quasi-steady wheel exist at every clocking
    with the azimuth of each blade (0.31.0), and the disc map was assembled by
    hand from them.

    *Requirement.* For each rotor and each sectional load quantity of a
    quasi-steady wheel point, the post shall write
    `sections/<point>_disc_<ROTOR>_<QUANTITY>.csv` with one row per blade
    station of every blade at every clocking of
    `sections/<point>_sections.csv`: `SAMPLE` (the clocking), `BLADE`,
    `AZIMUTH_DEG` (the table's own azimuth of that blade), `STATION_R_M`,
    `R_OVER_R` and `VALUE`, ordered by azimuth then radius, under the polar and
    condition columns of every table of the post. It shall register the file in
    `products.json` with `kind` `disc_map`.

    *Solution (release 0.32.0).* `pyflightstream.post.disc_maps.disc_map_rows`
    and `write_disc_maps` read the written table back and place each block at
    its own azimuth through `pyflightstream.post.axes`; the stage hooks
    `_write_disc_maps` in `pyflightstream.post.products` beside the harmonic
    product, which reads the same rows. A table is the product; no figure is
    drawn because matplotlib is not a dependency of the post.

    *Trace.* `tests/tier1_offline/test_p0320_g_qsteady_products.py`:
    `test_a_wheel_s_disc_map_gives_back_the_load_at_every_radius_and_azimuth`
    (P0320-G5-DISC-MAP).

!!! requirement "FR-271 An unsteady rotor's last revolution is tabulated over its disc <span class='srs-implemented'>implemented</span>"

    *Need.* An `unsteady_rotor` point writes its sections at every step, and
    the load over the disc of its last revolution was assembled by hand.

    *Requirement.* For each rotor of an `unsteady_rotor` point the post shall
    write the disc map of FR-270 from `series/<point>_sections_series.csv`,
    cut to the steps of the rotor's last complete revolution, with `SAMPLE`
    the step and `source` `unsteady last revolution` in the manifest.

    *Solution (release 0.32.0).* The same writer, called with the rows the
    harmonic product already cut to each rotor's revolution.

    *Trace.* `test_an_unsteady_rotor_s_disc_map_holds_its_last_revolution_only`
    (P0320-G5-DISC-MAP).

!!! requirement "FR-272 A disc map that cannot be made is refused by name <span class='srs-implemented'>implemented</span>"

    *Need.* A rotor with no blade in the table must not yield an empty file
    that reads as a map.

    *Requirement.* A rotor with no blade at a stated azimuth shall be named in
    the stage's skips under `sections/<point>_disc_#rotor=<ALIAS>` and warned,
    never blocking the other products; a point whose harmonics cannot be fitted
    for want of a readable table, a sections series, an export window or a
    complete revolution shall name its disc maps under
    `sections/<point>_disc_` (or `_disc_#rotor=<ALIAS>`) with the reason and a
    `post.log` line, so no map is silently absent; the standalone writer
    `pyflightstream.post.disc_maps.write_disc_map` shall refuse such a table
    with a `ProductError` and write nothing.

    *Solution (release 0.32.0).* `disc_map_rows` reports the rotor under
    `skipped`; `write_disc_map` raises where no map exists.

    *Trace.*
    `test_a_table_with_no_blade_of_the_rotor_refuses_to_map_and_names_why`
    (P0320-G5-DISC-MAP),
    `test_a_rotor_short_of_a_revolution_is_named_in_the_skips_of_the_disc_maps`
    and `test_the_disc_map_writer_maps_a_written_table_by_its_rotor`.

!!! requirement "FR-273 A saved simulation's faces are told to their boundaries <span class='srs-implemented'>implemented</span>"

    *Need.* The plan read a blade's chord from an OBJ only; a row that opens a
    saved simulation had no chord before the run.

    *Requirement.* The saved-simulation reader shall return each boundary's
    vertices by the boundary's name, from the block's per-face boundary row,
    and shall say None where the block carries no such row.

    *Solution (release 0.32.0).* `pyflightstream._fsm.boundary_vertices`. The
    boundary row is the seventh per-face row before the T/F rows, measured on
    every saved simulation of the tier-3 library (one to four boundaries); a
    row holding a value outside `1..boundaries` is not read.

    *Trace.* `test_the_saved_simulation_tells_each_face_to_its_boundary`
    (P0320-G7-CHORD-PLAN).

!!! requirement "FR-274 The plan warns before the run when the saved simulation's chord passes the reduced-frequency limit <span class='srs-implemented'>implemented</span>"

    *Need.* The reduced frequency `k` of a quasi-steady wheel was known before
    the run only for an OBJ mesh.

    *Requirement.* For a quasi-steady wheel row that opens a saved simulation
    (`.fsm`) unmoved before the solve, the plan shall read blade one's chord
    from the mesh, compute `k` at each station with
    `pyflightstream.cases.qsteady` (the one home of `k`) and warn before the
    run where `k` exceeds `REDUCED_FREQUENCY_LIMIT` (0.1). It shall never
    refuse: where the chord cannot be read the plan states why and gives `k`
    per metre of chord.

    *Solution (release 0.32.0).* `_blade_stations_from_the_mesh` reads a
    saved simulation through FR-273 in metres by the stored coordinate unit;
    the plan's existing warning then applies unchanged.

    *Trace.* `test_the_plan_reads_the_chord_of_the_fsm_as_it_reads_the_obj`,
    `test_the_plan_warns_before_the_run_when_the_fsm_chord_passes_the_limit`
    and `test_a_saved_simulation_that_cannot_tell_its_faces_says_why_and_never_refuses`
    (P0320-G7-CHORD-PLAN).

!!! requirement "FR-275 A setup removes surfaces by name <span class='srs-implemented'>implemented</span>"
    *Origin: G9 of the 0.32.0 scope (P0320-G9-DELETE-SURFACES). Evidence:
    licensed probe round 1 on 26.124, probe D1_delete_surfaces, which removed
    the third surface of a four-surface mesh and read the inventory back.*

    **Need.** A body without its blades was a mesh built by hand in the
    FlightStream window. A user never works with indices, so the surfaces to
    remove are named the way a row names any surface.

    **Requirement.** A setup key `delete_surfaces` lists boundary names,
    aliases or families of the opened geometry, and the point's script removes
    each with `DELETE_SURFACES` after the geometry opens and before any command
    cites a surface. A stated name that resolves to no surface, an empty list,
    a removal of every surface, and a row with no geometry or no boundary
    names are refused, naming the key. A setup that states no key emits
    nothing.

    **Solution (0.32.0).** `pyflightstream.cases.setup_surfaces.emit_setup_surfaces`,
    called from the geometry step of the workflow; a family is removed from its
    last member so no index shifts under the next command.

    **Trace.** `tests/tier1_offline/test_p0320_setup_surfaces.py`, the
    delete, family, refusal and control tests.

!!! requirement "FR-276 The surface inventory follows the solver's renumbering <span class='srs-implemented'>implemented</span>"
    *Origin: G9 of the 0.32.0 scope (P0320-G9-DELETE-SURFACES). Evidence: probe
    D1_delete_surfaces on 26.124, inventory Body, Base, Blade1, Blade2 before and
    Body, Base, Blade2 after, and the mesh export confirming only Blade2 moved.*

    **Need.** The solver renumbers the surfaces after a deleted one, so a
    command citing the old index would act on the wrong surface, silently.

    **Requirement.** After a removal, every later command of the point and the
    run record's inventory use the new indices: the surviving names in their
    original order, renumbered from 1, and the boundary total reduced by the
    number removed.

    **Solution (0.32.0).** The script's inventory and label table are rewritten
    by `EntityRegistry.renumber_boundaries` at the end of the removal.

    **Trace.** `test_delete_surfaces_by_name_emits_the_index_and_renumbers_the_inventory`
    and `test_a_command_after_the_removal_cites_the_new_index`.

!!! requirement "FR-277 A setup states the slipstream wake stabilization <span class='srs-implemented'>implemented</span>"
    *Origin: G4 of the 0.32.0 scope (P0320-G4-WAKE-DISABLE). Evidence: probe
    W1_wake_stab_disable on 26.124, DISABLE accepted after an ENABLE and the two
    saved simulations differing.*

    **Need.** The package recorded the option and never emitted it, so a setup
    could not switch the stabilization off.

    **Requirement.** A setup key `slipstream_wake_stabilization`, a toggle,
    emits `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` for each rotor motion the
    row creates, with the row's blade count where the build's command takes
    one. A DISABLE states 1 when the row states no count; an ENABLE without a
    count is refused where the command takes one. A setup that states no key emits nothing, and the key
    is no longer recorded-only.

    **Solution (0.32.0).** `emit_wake_stabilization`, called by the rotor
    motion step of the workflow.

    **Trace.** The wake stabilization tests of
    `tests/tier1_offline/test_p0320_setup_surfaces.py`.

!!! requirement "FR-278 A setup key that reaches nothing is refused <span class='srs-implemented'>implemented</span>"
    *Origin: the package's rule that a key is never silently dropped.
    Evidence: the refusal tests named below.*

    **Need.** A `delete_surfaces` on a row that opens no geometry, or a
    wake stabilization on a row with no rotor motion, would otherwise build a
    script that ignores the setup.

    **Requirement.** After the workflow builds the point, a stated
    `delete_surfaces` with no removal emitted, or a stated
    `slipstream_wake_stabilization` with no motion command emitted, is
    refused, naming the case and the key.

    **Solution (0.32.0).** `refuse_setup_keys_that_reached_nothing`, called
    after the workflow's builder.

    **Trace.** `test_a_removal_with_no_geometry_inventory_is_refused` and
    `test_the_wake_stabilization_on_a_row_with_no_rotor_is_refused`.

!!! requirement "FR-279 The two commands carry their 26.124 evidence <span class='srs-implemented'>implemented</span>"
    *Origin: the add-command convention. Evidence: probe round 1 on 26.124.*

    **Need.** A claim about the solver lives in the command database with its
    evidence, and nowhere else.

    **Requirement.** The 26.124 records of `DELETE_SURFACES` and
    `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` cite probe round 1, and their
    status stays documented: promotion to a measured status is done by a dated
    run report and no other route.

    **Solution (0.32.0).** The two records in the command database.

    **Trace.** `tests/tier1_offline/test_command_db.py` (no quoted manual
    text) and the two setup keys' tests.

!!! requirement "FR-280 A static rig row with MOTIONS is not refused for stating its speed twice <span class='srs-implemented'>implemented</span>"

    *Origin: D-RIG, moved from 0.33 by the owner's "pode entrar" (GEO-066,
    package J). Evidence: `tests/tier1_offline/test_p0320_rigor.py`
    (`test_p0320_d_rig_a_static_rig_with_motions_is_not_refused_for_a_double_speed`).*

    **Need.** A rotor rig turns at a fixed speed and sweeps the advance ratio,
    which then means the free stream, V = J x (RPM/60) x D.

    **Requirement.** A row that states `RPM` and a swept `ADVANCE_RATIO` and
    no velocity in its cell, with `MOTIONS`, is planned at every point and its
    rotor Mach numbers are resolved; the plan does not read the velocity it
    derived at the point as a stated one and refuse the row for stating its
    rotor speed twice.

    **Solution** (release 0.32.0). The static-rig test of `rotor_speed` asks
    what the cell declared (`condition_order`), not what the point resolved.
    Trace: `test_p0320_d_rig_a_static_rig_with_motions_is_not_refused_for_a_double_speed`.

!!! requirement "FR-281 One native match tolerance, with the printed-precision slack <span class='srs-implemented'>implemented</span>"

    *Origin: 0.29.1-tol, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_tol_0291_one_function_gives_the_printed_precision_slack`,
    `test_p0320_tol_0291_a_full_precision_native_adds_no_slack`.*

    **Need.** A native nodal export printed at limited digits and a VTK written
    at single precision differ, for a part far from the origin, by more than
    four single-precision epsilons of the coordinates.

    **Requirement.** One function, `native_match_tolerance`, beside
    `attach_native_strength`, gives the per-axis tolerance the match takes by
    default. Told the significant digits the native was printed at
    (`native_printed_digits`), it adds half a unit of the last digit and half
    a single-precision spacing of the coordinate magnitude. Told nothing, it is
    the rule it always was, and a native printed at full precision adds
    nothing.

    **Solution** (release 0.32.0). `results/native_surface.py`. Trace: the two
    tests above.

!!! requirement "FR-282 The time-averaged native strength uses that tolerance <span class='srs-implemented'>implemented</span>"

    *Origin: 0.29.1-avg, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_avg_0291_the_time_average_matches_a_far_native_with_that_tolerance`.*

    **Need.** The time average of a surface matched each step's native
    strength with a tolerance of its own.

    **Requirement.** `average_surface_exports` resolves the tolerance of each
    step's native from `native_match_tolerance` and the digits that native was
    printed at, and records it in the step's matching evidence.

    **Solution** (release 0.32.0). `post/surfaces.py`. Trace: the test above.

!!! requirement "FR-283 DEFAULT_DRIFT_LIMIT_PCT is public in cases <span class='srs-implemented'>implemented</span>"

    *Origin: ARCH2-S2, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_arch2_s2_the_default_drift_limit_is_public_in_cases`.*

    **Need.** The default drift limit is read by the post stage and belongs to
    the case model.

    **Requirement.** `DEFAULT_DRIFT_LIMIT_PCT` is in `pyflightstream.cases.__all__`
    and is the default of `PerRevolutionSpec.drift_limit_pct`.

    **Solution** (release 0.32.0). `cases/__init__.py`. Trace: the test above.

!!! requirement "FR-284 The clocking 0 filter of the NA shares is tested <span class='srs-implemented'>implemented</span>"

    *Origin: QA2-2, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_qa2_2_the_na_shares_read_clocking_zero_rows_only`.*

    **Need.** The thrust and torque shares above k = 0.1 read the point's own
    solve, clocking 0, of a table that holds every clocking; nothing pinned it.

    **Requirement.** With rows of another clocking that carry other forces and
    an unread force, the shares are those of clocking 0's rows alone and no
    note is written.

    **Solution** (release 0.32.0). A test of the 0.31.0 filter
    (`add_reduced_frequency_to_sections`); a mutant that removes the filter
    fails it. Trace: the test above.

!!! requirement "FR-285 A quasi-steady point's products state J <span class='srs-implemented'>implemented</span>"

    *Origin: QS-J, the owner's post-release defect class "ADVANCE_RATIO not
    NA", found by the X1 rehearsal: 17 rows of `_qs_avg.csv` and
    `_qs_positions.csv` of the recorded wheel workspace read `NA` in `J` and
    `J_CLOCK`. Evidence: `test_p0320_qs_j_a_wheel_point_states_its_j_from_its_own_speed_and_diameter`,
    `test_p0320_qs_j_a_requested_j_is_kept_and_a_missing_free_stream_stays_na`.*

    **Need.** A quasi-steady point turns its rotor at the speed of its record,
    and the rotor's block gives its diameter.

    **Requirement.** `J_CLOCK`, `RPM_CLOCK` and, where the row requested none,
    `J` state the rotor's own advance ratio `V / (n D)` in both quasi-steady
    tables, by the one formula of the rotor table (`rotor_advance_ratio`).
    What the row requested is kept, and a point without a free stream or a
    diameter stays `NA`. Re-posting a copy of the recorded workspace gives all
    17 rows a finite `J`.

    **Solution** (release 0.32.0). `post/_tables.py` (`rotor_advance_ratio`,
    shared with `J_CLOCK` of the other tables), `post/qsteady.py`. Trace: the
    two tests above.

!!! requirement "FR-112 The pproc declares a time-averaged surface, and the package averages the per-step exports <span class='srs-implemented'>implemented</span>"

    *Origin: F02 of the 0.25.0 scope and G25 of the 0.28.0 scope. The need, in
    the requester's words: "pyfs pode fazer a media com as exportações ja no
    esquema como sections". Evidence:
    `tests/tier1_offline/test_f02_time_averaging_refusal.py` (the refusal
    where the solver's own average is not recorded verified) and
    `tests/tier1_offline/test_g25_surface_time_average.py` (the window, the
    average of the per-step exports, every refusal and skip by name).*

    An unsteady row states the surface averaged over a window of its march in
    the pproc, and the products say that the surface is an average and over
    which window.

    - A `[time_averaging]` table states exactly one of `last_revs` (revolutions
      of the rotor clock, through the resolver of `LAST_REVS_AVG`) or
      `last_iters`; both, or neither, is refused.
    - The run exports the surface at every step of the window through the
      per-step exports, and the post averages those exports into
      `surfaces/<point>_time_average.dat`, and `.vtk` beside it where
      `[exports] vtk` asks. Every step weighs the same, each is written back in
      the reference frame first, and the nodes are those of the window's last
      step.
    - Steps that do not share one topology refuse the average by name, and a
      step of the window that was not exported skips it by name, never a
      partial average.
    - `SOLVER_TIME_AVERAGING` is never emitted, because it holds a script on
      26.124. The `products.json` entry carries `kind: average`, the window, the
      steps and each input's sha256, and the run records the window as
      `RunRecord.surface_average_window`.

    Solution: 0.25.0 added the table and its emission of the solver's command,
    refused on every build where that command is not verified; 0.28.0 replaced
    the route with the package's own average (`pyflightstream.post.surfaces`).
    Not measured: whether the command's bounds are time steps or inner
    iterations.

!!! requirement "FR-113 The surface flow leaves in VTK and CSV, and the Tecplot file is written from the VTK <span class='srs-implemented'>implemented</span>"

    *Origin: F03 of the 0.25.0 scope and G45 of the 0.28.0 scope. The need, in
    the requester's words: "tradutor vtk para tecplot (se vtk tiver mais
    outputs) - usar sempre essa rota para tecplot". Evidence:
    `tests/tier1_offline/test_surface_exports.py` (the two kinds, their
    default off, the variable list validated against the database) and
    `tests/tier1_offline/test_g45_tecplot_from_vtk.py` (the translation, the
    variable names, the images of a symmetric row).*

    A row can export the surface flow as VTK and as CSV, and every Tecplot
    surface of a campaign point comes from the VTK export.

    - `[exports]` accepts `vtk` and `csv`, both off by default. The VTK export
      lists the variables of the pproc's `vtk_variables`, each validated
      against the build's command database, or every variable when the list is
      absent. Both files join the per-step exports and the averaged surface.
    - `[exports] tecplot` exports the surface as VTK and the run writes the
      `.dat` from it, at the name the solver's own Tecplot had, before the
      point's outputs are collected and hashed. The script never emits
      `EXPORT_SOLVER_ANALYSIS_TECPLOT`.
    - The translated file is one cell-centered FEPolygon zone under the VTK's
      variable names. A row under mirror or periodic symmetry carries the
      images after the modeled surface, which the solver's file left out.

    Solution: 0.25.0 added the two kinds; 0.28.0 made the translation the only
    Tecplot route.

!!! requirement "FR-114 Every advanced solver setting has a setup key, so no `[[raw]]` is needed <span class='srs-implemented'>implemented</span>"

    *Origin: F04 of the 0.25.0 scope, and G09 and G14 of the 0.27.0 scope.
    Their requester's words are not kept verbatim in the scope tables.
    Evidence: `tests/tier1_offline/test_rel0250_f04_advanced_setup.py`,
    `tests/tier1_offline/test_g09_loads_selection.py` and
    `tests/tier1_offline/test_g14_lift_and_coupling_keys.py`.*

    A solver setting a study needs is a key of the setup, named for what it
    sets, and emits its solver command when stated and nothing when absent, so
    a setup that does not state it produces the same script as before.

    - Fourteen advanced settings: `laminar_separation`, `kutta_joukowski_lift`,
      `aeroelastic_rbf_type`, `print_rotor_induced_velocities`,
      `adaptive_field_grid_refinement`, `rotor_induced_velocity_blending`,
      `wake_numerical_relaxation`, `wake_relaxation`, `wake_decay_constant_per_m`,
      `wake_streamwise_agglomeration`, `jet_wake_decay_normalized_length`,
      `jet_wake_filaments_grid_induction`, `adverse_gradient_boundary_layer` and
      `vortex_ring_normalization`.
    - The loads analysis, on steady rows: `analysis_families`, `load_units` and
      `inviscid_loads`, stated after `START_SOLVER` on every point. A row of an
      unsteady run type stating one is refused at plan.
    - `vorticity_lift_model` (every run type) and
      `unsteady_viscous_coupling_iteration` (unsteady run types), stated before
      `INITIALIZE_SOLVER`.
    - A value or a command the run's build does not carry is refused naming the
      build, and on 26.124 a row stating either of the last two keys is refused
      naming the report that measured the command absent. `[[raw]]` still works.

    Solution: 0.25.0 (the fourteen) and 0.27.0 (the loads analysis and the two
    model keys).

!!! requirement "FR-115 Boundary-layer quantities are sampled where the build documents them, and the profile command is refused where it holds a script <span class='srs-implemented'>implemented</span>"

    *Origin: F05 of the 0.25.0 scope and G24 of the 0.28.0 scope. Their
    requester's words are not kept verbatim in the scope tables. Evidence:
    `tests/tier1_offline/test_rel0250_f05_fluid_parameters.py` and
    `tests/tier1_offline/test_g24_boundary_layer_profile.py`.*

    The six boundary-layer fluid-plot parameters (`BL_MOMENTUM_THICKNESS`,
    `BL_DISPLACEMENT_THICKNESS`, `BL_TOTAL_THICKNESS`, `BL_SHAPE_FACTOR`,
    `BL_SKIN_FRICTION`, `BL_TRANSITION_MARKER`) are accepted in a pproc probe's
    `parameters` on the builds whose manual lists them, and a build that does
    not document one refuses it naming the parameter and the build.
    `EXPORT_BL_VELOCITY_PROFILE` is recorded broken on 26.124, where it holds an
    unattended script, so a row writing it raw is refused at plan naming the
    report, and the package builds no route to the profile there.

    Solution: 0.25.0 (the parameters) and 0.28.0 (the refusal of the profile
    command on 26.124).

!!! requirement "FR-116 Each section distribution has its own sectional-loads file and Cp file, with optional integrated loads <span class='srs-implemented'>implemented</span>"

    *Origin: F07 of the 0.25.0 scope, and the integrated sectional loads of
    the 0.26.0 scope. The requester chose the strip rule: midpoint to
    midpoint, half a strip at the first and last station. Evidence:
    `tests/tier1_offline/test_f07_section_distributions.py` and
    `tests/tier1_offline/test_integrated_sectional_loads.py`.*

    The post writes, per point and per pproc `[[sections.distributions]]`
    entry, one sectional-loads file and one Cp file under `sections/`, named for
    the entry's alias or families.

    - The files are `<point>_sloads_<name>.csv` and `<point>_cp_<name>.csv`. With
      the per-step exports on, each holds every exported step in a `STEP`
      column; without them, the end-of-run export.
    - A record that does not identify its distributions is a named skip: the
      split is never guessed.
    - `integrate = true` on an entry, off by default, appends `Strip_length`,
      `Fx_int`, `Fz_int` and `My_int` to the same file, one instant at a time,
      over exported station midpoints and about the local quarter chord. An
      invalid distribution warns and keeps the original columns, and the default
      preserves the previous bytes. Where the recorded evidence cannot say what
      the builder would emit, the match refuses by name.

    Solution: 0.25.0 (the split, `pyflightstream.post.section_distributions`) and
    0.26.0 (the integrated columns).

!!! requirement "FR-117 On an unsteady row every probe is a fluid plot, and its table is the plots history <span class='srs-implemented'>implemented</span>"

    *Origin: F01 of the 0.25.0 scope. The scope row words the need: "A fonte da
    probe segue o tipo de corrida, SEMPRE." Evidence:
    `tests/tier1_offline/test_f01_probe_source.py` and
    `tests/tier1_offline/test_rel0250_f01_probe_skip.py`.*

    The source of a probe follows the run type. On an unsteady row every
    `[[probes]]` entry, drawn lines and cited `points_file` alike, becomes a
    fluid plot, and `post` builds the probes table from the plots history,
    never from a probe-points export. A steady row keeps the probe points.

    - A cited `points_file` is read at plan and each point, for each listed
      parameter, becomes a plot on the same vertex counter as the drawn lines.
      The row no longer imports the file nor exports probe points, and its
      default outputs lose `{name}_probes.txt`.
    - A pproc mixing drawn lines and a cited profile yields one history table.
    - A run recorded before 0.25.0 whose cited-profile probes were exported as a
      last-step instant has no history: those probes are left out with that
      reason in `products.json`, and posting again cannot create one.

    Solution: 0.25.0. This changed the probe source of every unsteady row, which
    is why the migration page carries it.

!!! requirement "FR-118 Every product's condition carries the speed and the advance ratio the clock rotor ran at <span class='srs-implemented'>implemented</span>"

    *Origin: the polar measured in 0.25.0 whose `J` read `NA` in every row while
    the record held the velocity and the speed. The requester's decision, in her
    words: "0.25.1 com as colunas mesmo assim." Evidence:
    `tests/tier1_offline/test_clock_rotor_columns.py` and
    `tests/tier1_offline/test_clock_columns_at_the_product.py`.*

    Beside `J`, the advance ratio the row requested, every product's condition
    carries `J_CLOCK` and `RPM_CLOCK`: what the clock rotor ran at, its speed
    with its hand, and `V / (n D)` from the point's own free stream, the
    recorded speed and the rotor's diameter.

    - The clock rotor is the one `CLOCK_MOTION` names, or the only rotor the row
      turns. A row turning several and naming none has no clock, and both columns
      are `NA`, because one rotor's ratio is not another's.
    - A flat single-rotor reference with a top-level `rotor_diameter_m` supplies
      the span of its one rotor; beside named blocks the flat diameter answers
      for nobody.
    - The rotor table keeps `J_<alias>` per rotor, unchanged.

    Solution: 0.25.1, as columns in a patch release by her decision, although
    semantic versioning would call them a minor change.

!!! requirement "FR-119 Nothing in the post refuses by default, and the freeze check is opt-in <span class='srs-implemented'>implemented</span>"

    *Origin: the owner decisions of 2026-09-22 for 0.25.1 and 0.26.0. First:
    "esse guard lendo o log vira um opcional, nao quero ele ligado por default
    ja na 0.25.1 e na 26 vamos rediscutir essa arquitetura, registra como
    pendencia." Then: "sobre arquitetura do post, eu nao quero que nada barre
    por default mas sempre seja escrito um log do proprio post com warnings se
    aplicavel." Evidence:
    `tests/tier1_offline/test_frozen_check_is_opt_in.py` and
    `tests/tier1_offline/test_b01_frozen_solve.py`.*

    `post` and `collect` refuse nothing from a point's native log unless asked,
    and the post writes every product it can compute.

    - `--check-frozen` turns the refusal of the averages of a frozen solve on.
      Without it the stage reads a log only to admit a point recorded
      `FAILED_DIVERGED` whose solver froze, so its histories, instants and
      pre-freeze averages are written, and a frozen solve's averages are
      published with a warning.
    - Frozen solves and unread blocks warn, malformed loads skip their point by
      name, an empty unsteady log warns and refuses averages only when asked,
      and a failed status alone no longer excludes usable exports.
    - The reducer states its exact plotted sample set from its resolved
      families, and every nonzero interpolation weight counts.
    - The provenance digest hashes every recorded output, the log included, in
      every mode.

    Solution: 0.25.1 (the option) and 0.26.0 (the rule for the whole post).

!!! requirement "FR-120 Every post writes a log of its own, human and machine readable <span class='srs-implemented'>implemented</span>"

    *Origin: the same decision as FR-119: "sempre seja escrito um log do proprio
    post com warnings se aplicavel." Evidence:
    `tests/tier1_offline/test_post_log.py` and
    `tests/tier1_offline/test_post_diagnostics.py`.*

    Every campaign post writes `post.log` beside `products.json`, even when
    clean, and `post.log.json` beside it.

    - The log carries the invocation header and one record for every named skip
      and stage warning, and is archived with the products on rebuild. The
      manifest names both files (`log_json` for the second).
    - `post.log.json` holds the header (`version`, `workspace`, `matrix`,
      `time`, `check_frozen`) and `records`, one per WARNING line in the same
      order, each with `point`, `product`, `message` and `remedy`. Both files
      are written from one list of records on a clean, a failed and an
      interrupted post, so they cannot disagree.
    - A WARNING line names the point and product its warning names
      (`WARNING point=<point> product=<product>: ...`); one that names none
      reads `point=campaign product=stage`.
    - A warning raised during a post by code outside the package is not written
      to the log; it reaches the caller's warning filters as before.

    Solution: 0.26.0 (`post.log`) and 0.27.0 (the JSON twin, the line form and
    the exclusion of foreign warnings). Not solved: warning capture is
    process-wide, so concurrent posts in threads can mix campaign warnings.

!!! requirement "FR-121 Every point of a row naming a run type leaves its final saved simulation <span class='srs-implemented'>implemented</span>"

    *Origin: G11 of the 0.27.0 scope. The need, in the requester's words: "isso
    não tá formalizado". Evidence:
    `tests/tier1_offline/test_saved_simulation.py` (a save in every workflow
    script of every run type and build, first among the point's exports, one for
    each point of a steady sweep, collected and hashed, a missing one recorded
    incomplete, the plan warning for a `LEGACY` row).*

    After a point's solve, first among its exports, the script saves the solver
    state as `<point file stem>.fsm`. The file is collected into the point's
    datapoint folder and listed in the run record's `outputs` with its sha256 in
    `outputs_sha256`.

    - This holds on every run type, on every build a run type renders on, and
      for each point of a steady sweep.
    - `[exports] simulation = false` is refused at plan, naming the row and the
      file, as `loads = false` is.
    - A point whose saved simulation is missing is recorded incomplete.
    - `pyfs-matrix plan` warns, naming the row, for each `LEGACY` row whose
      `OUTPUTS` declare no `.fsm`, because no final state of it is collected or
      hashed. The warning blocks nothing.

    Solution: 0.27.0.

!!! requirement "FR-122 A run record carries the boundary names of its geometry <span class='srs-implemented'>implemented</span>"

    *Origin: R03 of the 0.27.0 review round. Evidence:
    `tests/tier1_offline/test_r03_r04_recorded_inventory.py`.*

    Each run record carries its geometry's boundary names as `inventory`, in the
    solver's order as the script read them at `OPEN`, the name at position i
    being boundary i, on the point path and on the steady one-job path alike.

    - A run that opened no geometry declaring names (a `LEGACY` recipe, a file
      without a mesh block) writes no key.
    - `CampaignWorkspace.recorded_inventory(record)` returns the names, and for
      a record written before 0.27.0 reads them from the mesh block of the
      geometry file whose sha256 the record carries.
    - A manifest holding such a record needs 0.27.0 to be read: an older reader
      refuses the key.

    Solution: 0.27.0.

!!! requirement "FR-123 The input files describe themselves: a glossary of every key and a template of every file <span class='srs-implemented'>implemented</span>"

    *Origin: G08 of the 0.27.0 scope and G47 of the 0.28.0 scope. The need for
    the second, in the requester's words: "Criar um md input_template dentro de
    inputs". Evidence: `tests/tier1_offline/test_goal031_g08_input_glossary.py`
    (a key added with no row fails) and
    `tests/tier1_offline/test_g47_input_template.py` (every template read back
    with the package's own reader).*

    A workspace documents the input files a user writes, generated from the code
    where the format is the code's.

    - `inputs/pproc/INPUTS.md` holds one table per table of each input artifact
      (matrix, setup, pproc, reference, geometry sidecar), one row per key: what
      it sets, its unit or values, the run types or builds that accept it and
      the solver command it reaches. A key added without a row fails a test.
    - `inputs/input_template.md` holds one section per kind of input file (the
      matrix, the setup, the pproc, the reference and its blocks, the named
      points, the sidecars, the trailing-edge points file, the provenance
      record, the profiles, the custom free stream, the HPC profile and the build
      registry), each saying what the file is for and where it lives, with a
      commented complete example and the links to the page that covers it.
    - `pyfs-workspace init`, `pyfs-matrix plan` and `pyfs-matrix post` write both
      files, rewriting one only when its content changes.

    Solution: 0.27.0 (the glossary) and 0.28.0 (the template).

!!! requirement "FR-124 Every table the post writes opens with its header and the polar, and no cell needs quoting <span class='srs-implemented'>implemented</span>"

    *Origin: G16 of the 0.27.0 scope. The need, in the requester's words: "o
    numero da polar vai em todos os arquivos como um coluna", and of the rotor
    table's first line: "coloca isso como coluna tb". Evidence:
    `tests/tier1_offline/test_g16_polar_column.py` (every table written is read
    back, including by `numpy.genfromtxt`).*

    Every table the post writes under `post/<matrix>/`, the additional post's
    included, and `campaign_sweep.csv`, holds its header on the first line and
    the polar as its first column.

    - The column is `POL`, named as the run matrix names its polar column, and
      holds the polar of the point each row comes from. The steady polar and its
      super file carry `POL` in place of the `POLAR` of 0.26.0.
    - The rotor table's alias, alone on a line before the header since 0.23.0,
      is the `ROTOR` column right after `POL`.
    - Every text cell, header names included, writes a comma as `;`, a double
      quote as a single one and a line break as a space, through one rule, so no
      cell is quoted and a reader that splits on `,` reads every row as wide as
      its header.
    - Every other column keeps its name and its order after the new ones. The
      solver's own raw files do not change.

    Solution: 0.27.0. It moved every column of these tables one place to the
    right for a reader by position, which is why the migration page carries it.

!!! requirement "FR-125 A row states a custom free stream by an input file, and the plan checks the field against the body <span class='srs-implemented'>implemented</span>"

    *Origin: G15 of the 0.27.0 scope and G18 of the 0.28.0 scope. The need, in
    the requester's words: "quero ja incluir na 27" and "custom freestream (G18)
    por arquivo de input". Evidence:
    `tests/tier1_offline/test_g15_custom_freestream.py` (the script, both forms,
    every refusal, and the coverage warning of `test_g18_*`).*

    `FREESTREAM: <stem>` names a velocity field over the YZ plane of the global
    frame, in m and m/s, converted in no way, in a file of the workspace's
    `inputs/freestreams/`.

    - `<stem>.txt` is the STRUCTURED form of the manual (`Npts Mpts`, then
      `x y z vx vy vz` rows); `<stem>.dat` is the UNSTRUCTURED form (the rows
      alone). Every run type writes `SET_FREESTREAM CUSTOM <form>` and the file's
      absolute path in place of `SET_FREESTREAM CONSTANT`, once for a steady
      sweep, and nothing else of the script moves.
    - The file is resolved at plan, read where it lives and hashed into the
      record's `inputs_sha256`.
    - The plan refuses, by name, a stem the folder does not hold or holds in both
      forms, the key on a `LEGACY` row, and the key beside a body rate or a
      non-zero angle of attack or sideslip, since a run has one
      `SET_FREESTREAM`.
    - The plan warns, naming both extents, when the field's grid does not cover
      the body's y and z extent, and says the coverage was not checked on a row
      that moves the body.

    Solution: 0.27.0 (the key and the STRUCTURED form) and 0.28.0 (the
    UNSTRUCTURED form measured, and the coverage warning).

!!! requirement "FR-126 A raw OBJ's surface names are read from its groups <span class='srs-implemented'>implemented</span>"

    *Origin: G30 of the 0.28.0 scope: bringing an OBJ without writing its surface
    names by hand. Evidence:
    `tests/tier1_offline/test_g30_obj_surface_names.py`.*

    When an `.obj` a row names has no `<stem>.boundaries.toml`, `pyfs-matrix plan`
    and `run` write one beside it and say so on stderr, and `pyfs-matrix inventory
    <file>.obj` writes the same file through the same function.

    - The sidecar's `boundaries` are one per `o` or `g` group that holds a face,
      named by the group, in the order of the file, which is how 26.124 numbers an
      OBJ's surfaces on import. A group with no face makes none.
    - The file carries the list under a comment naming the OBJ's sha256, and the
      user adds `[import]` units and `[trailing_edges]` beneath it.
    - A sidecar that exists is never rewritten, `--overwrite` or not. When its
      `boundaries` differ from the groups a warning names both lists, and one
      stating none is refused naming the list the groups make.
    - What the measurement did not settle is refused naming the line, and an STL,
      which has no names, keeps its refusals.

    Solution: 0.28.0.

!!! requirement "FR-127 The FSI's blade properties come from its sections and a material <span class='srs-implemented'>implemented</span>"

    *Origin: G41 of the 0.28.0 scope, mandatory. The need, in the requester's
    words: "Geralmente blades de tunel de metal sao massiças, entao eu quero essa
    capacidade no fsi do pyflightstream pq ja destrava muita analise" and "Tudo
    precisa estar escriptado e reproduzivel". Evidence:
    `tests/tier1_offline/test_g41_section_properties.py` (closed forms for
    rectangles, plates, polygons standing for circles and ellipses, the torsion
    constant converging, the material database, the round trip and the
    provenance).*

    `pyflightstream.fsi.sections.blade_properties_from_sections` generates a
    `BladeProperties` from one closed section contour per station and a material,
    for a solid homogeneous section, instead of typed numbers.

    - The running mass is rho A, the mass moments of inertia per length are rho
      times the principal second moments, EI is E times the second moment about
      the chordwise centroidal axis, GJ is G J, and the elastic-axis offsets come
      with them.
    - Area, centroid, second moments and principal values of the polygon are
      exact and summed about the vertices' mean, so a section far from the origin
      keeps its digits. A contour that is no simple polygon is refused naming the
      vertices or edges.
    - The torsion constant J is computed from the Prandtl stress function and
      converges toward the closed form.
    - The material database carries a source for every entry, and an unknown
      material is refused naming the database.
    - The generation is scripted: the provenance records the material, the
      geometry and the method, and one of another blade is refused.

    - The elastic axis is taken at the centroid, a stated hypothesis; the shear
      centre is not computed, and hollow and spar sections are a future option,
      not built.

    Solution: 0.28.0 (`pyflightstream.fsi.sections` and
    `pyflightstream.fsi.materials`).

!!! requirement "FR-128 An actuator disc takes its speed from the advance ratio <span class='srs-implemented'>implemented</span>"

    *Origin: G20 of the 0.28.0 scope: a disc turning at a rate given by the
    advance ratio, as a rotor already does (FR-70). Evidence:
    `tests/tier1_offline/test_g06_actuator_disc.py`
    (`test_g20_a_disc_takes_its_speed_from_the_advance_ratio` and the swept
    case).*

    A row naming a disc and stating `ADVANCE_RATIO` (in its flight condition,
    swept or held) and no `ACTUATOR_RPM` turns the disc at n = V / (J D) by the
    rotors' rule.

    - D is the disc's own diameter, twice its `tip_radius_m`; V is the row's
      velocity; the hand stays the block's `rpm_sign`.
    - A row stating neither `ADVANCE_RATIO` nor `ACTUATOR_RPM` is refused naming
      both.
    - A steady row whose disc speed moves with a swept advance ratio runs one job
      per point, as a flow sweep does, so each point sets its own speed.

    Solution: 0.28.0.

!!! requirement "FR-129 A local run's log reads at a glance, and an unsteady point says how far it is <span class='srs-implemented'>implemented</span>"

    *Origin: G43 of the 0.28.0 scope. The need, in the requester's words: "vamos
    deixar o log de execução local mais bonitinho". Evidence:
    `tests/tier1_offline/test_g43_local_log.py` (the banner, the numbering, the
    summary table, the progress cadence and its refusal).*

    A local run opens with a banner naming the campaign and how many points it
    runs, numbers each point (`(3 of 17)`, a steady job its range,
    `(1-3 of 17)`), and closes with a table of how the points ended, a job's
    points counted one by one, and the time it took.

    - An unsteady point that carries its step counter prints a progress bar with
      its step, its share and the time so far every N completed time steps, read
      from the run's own counter while the solver runs, never from what the solver
      prints.
    - `pyfs-matrix run --progress-every N` sets N (10 by default, 0 for none); a
      negative N is refused. A row with no counter runs as before.

    Solution: 0.28.0.

!!! requirement "FR-130 A run that submits to a cluster does not post <span class='srs-implemented'>implemented</span>"

    *Origin: G43 of the 0.28.0 scope, from a submission of 25 points that printed
    270 lines. The need, in the requester's words: "ta muito poluido o log do run
    com submissao para o hpc" and "se for submissao para linux, o run nao deveria
    rodar post". Evidence:
    `tests/tier1_offline/test_goal021_swept_row.py`
    (`test_g43_a_run_that_submits_does_not_post`) and
    `tests/tier1_offline/test_g43_local_log.py`.*

    Points in a queue have no outputs yet, so a `run` that submits any point
    writes no product and no sweep table.

    - It ends with one line saying how many points it submitted and how many it
      ran here, and the command that collects and then posts
      (`pyfs-matrix collect --workspace <root>`, `--watch` to wait).
    - A run whose every point ran here posts as before.
    - `CampaignErrors.records` carries every record the failing call wrote,
      failed or not, beside `failures`, and the CLI reads it to tell a run that
      also submitted a point, which writes no table.

    Solution: 0.28.0.

!!! requirement "FR-131 The whole matrix is run again by one flag <span class='srs-implemented'>implemented</span>"

    *Origin: G44 of the 0.28.0 scope. The need, in the requester's words: "para
    28, eu quero um --force-rerun-all". Evidence:
    `tests/tier1_offline/test_g44_force_rerun_all.py`.*

    `pyfs-matrix run --force-rerun-all [--sims SIM ...]` archives every recorded
    point of the matrix, or of the simulations `--sims` names, with the archive
    of `--force-rerun`, and runs it again, a steady row recorded as one job as one
    job.

    - One line gives the count of points and jobs before anything runs.
    - It is refused beside `--resume` or `--force-rerun`, for an id the matrix
      does not carry, when `--sims` stands alone, and when nothing is recorded, in
      each case before anything runs.

    Solution: 0.28.0.

!!! requirement "FR-132 The plan warns when a plot group takes the rotor table's plot name <span class='srs-implemented'>implemented</span>"

    *Origin: G42 of the 0.28.0 scope, from a submission of 25 rows whose rotor
    tables were skipped. The decision, in the requester's words: "nao precisa
    fazer essa mudança, coloca no plan o aviso". Evidence:
    `tests/tier1_offline/test_goal028_rotor_plot_group.py`
    (`test_g42_the_plan_warns_when_a_group_takes_the_rotor_plot_name`).*

    A pproc plot group named like the automatic `ROTOR_<ALIAS>` group, such as
    `ROTOR_{family}` in a rotor's own frame, emits the names the rotor table
    reads, so the run keeps that group and writes no global-frame history for the
    rotor, and the post cannot write its table.

    - `pyfs-matrix plan` and `pyfs-matrix run` say so before a seat is spent,
      naming the pproc, the name and the rotor, and suggesting a rename
      (`SHAFT_{family}`).
    - Nothing is refused and nothing is renamed.

    Solution: 0.28.0.

!!! requirement "FR-133 An unsteady row saves the solver's residual and load plots <span class='srs-implemented'>implemented</span>"

    *Origin: G26 of the 0.28.0 scope, after the plots of a steady point (FR-51).
    Evidence: `tests/tier1_offline/test_g04_solver_plots.py`
    (`test_g26_an_unsteady_row_saves_its_residual_and_load_plots_once_after_the_march`).*

    An unsteady row saves `<point>_plot_residuals.txt` and `<point>_plot_loads.txt`
    by default, as a steady point does, once after the march and before the log
    (and in the wall clock's rescue), never per step.

    - Each file holds the whole march, one row per inner iteration.
    - `plot_residuals = false` or `plot_loads = false` under `[exports]` turns one
      off, and either stated true on an unsteady row is accepted, where 0.27.0
      refused it. This replaces the clause of FR-51 that an unsteady point saves
      none.

    Solution: 0.28.0.

!!! requirement "FR-134 An unsteady or rotor row refuses `COLD_START` at plan <span class='srs-implemented'>implemented</span>"

    *Origin: G36 of the 0.28.0 scope: a key that changed nothing on an unsteady
    row, which the plan did not say. Evidence:
    `tests/tier1_offline/test_workflows.py`
    (`test_g36_an_unsteady_row_refuses_cold_start`).*

    The key clears the solution between the points of a steady sweep over the
    attitude. Every point of an unsteady or rotor row is its own job and starts
    cold, so the key, true or false, changes nothing there, and the plan refuses
    it naming the key and saying why. A steady row that sweeps the flow keeps the
    key as the glossary states.

    Solution: 0.28.0.

!!! requirement "FR-150 A setup library and its physical guidance are written on request <span class='srs-implemented'>implemented</span>"

    *Origin: the setup standards of the 0.29.0 quality gate: a run needs a
    complete preset and a reason for each choice in it. Evidence:
    `tests/tier1_offline/test_setup_standards.py` and
    `tests/tier1_offline/test_setup_library_contract.py`.*

    `pyfs-matrix plan --setup-guidelines` writes
    `inputs/setups/SETUP_GUIDELINES.md` and `--setup-standards` writes the
    `s9XX` library of complete setup presets. The two options are independent.

    - The guidelines name the low-cost and the additional-fidelity starting
      point of each scenario, its assumptions and the supporting literature;
      a study that varies one setting names its baseline.
    - A command the build cannot emit stays a labeled comment; an existing
      file that differs is preserved; no matrix is silently reassigned to a
      new preset.

    **Solution (0.29.0).** The two options of `plan` and the `s9XX` library of
    `docs/setup-standards.md`. **Trace.** The two test files above.

!!! requirement "FR-151 The setups a plan resolved are inspected, with where each value came from <span class='srs-implemented'>implemented</span>"

    *Origin: the setup standards of the 0.29.0 quality gate: a user could not
    see what a setup would send to the solver. Evidence:
    `tests/tier1_offline/test_setup_standards.py` and
    `tests/tier1_offline/test_run_cli.py`.*

    `pyfs-matrix inspect-setups` reports each setup's values, the origin of
    each, its boundary selections and its raw commands, from the same records
    that planning stores, so the report and the run cannot differ.

    **Solution (0.29.0).** The command, the input glossary and the templates
    covering the structured fields it reads. **Trace.** The test files above.

!!! requirement "FR-152 Boundaries are edited by type, and each input has one owner <span class='srs-implemented'>implemented</span>"

    *Origin: the boundary handling of the 0.29.0 scope (G-series of the
    quality gate). Evidence: `tests/tier1_offline/test_approved_capabilities_029.py`
    and `tests/tier1_offline/test_goal034_setup_operational_commands.py`.*

    A geometry sidecar maps port identities to surfaces. A setup declares
    `[[ports]]` entries with the inlet or outlet role, optional remeshing and
    the MATRIX variable names; the MATRIX supplies velocities and profile file
    names. A setup selector applies a geometric trailing edge, wake or base
    declaration without implicitly clearing saved state, and a setup can
    remove initialization, delete transition trips and order base-region
    edits.

    - The unreleased physical sidecar forms are refused, with migration
      guidance.
    - A port to be created while its saved index is unknown is refused.
    - Native coverage stays build-specific and is not claimed beyond the
      builds measured.

    **Solution (0.29.0).** The typed boundary tables of the setup and the
    sidecar reader. **Trace.** The test files above.

!!! requirement "FR-153 Probes and volume sections write sampled velocity fields <span class='srs-implemented'>implemented</span>"

    *Origin: the sampled-field need of the 0.29.0 quality gate. Evidence:
    `tests/tier1_offline/test_f01_probe_source.py` and
    `tests/tier1_offline/test_approved_capabilities_029.py`.*

    Probes and volume sections write package-built VTK or Tecplot point
    fields whose provenance states the source, the position, the frame and the
    velocity components. Reusable inflow is offered only from an appropriate
    global YZ survey; a point sample never invents a volume-cell topology.

    **Solution (0.29.0).** `docs/sampled-fields.md` and the writers behind it.
    **Trace.** The test files above.

!!! requirement "FR-154 Boundary-layer products are separate: section integrals from the surface, profiles refused <span class='srs-implemented'>implemented</span>"

    *Origin: the boundary-layer products of the 0.29.0 scope. Evidence:
    `tests/tier1_offline/test_boundary_layer_products.py`.*

    A section-integral table reads the actual VTK cell quantities at the
    configured section cuts and keeps every incidence that shares an
    intersection. The velocity-profile request is a separate product, and it
    is refused by name wherever an unattended native profile export has no
    positive proof.

    **Solution (0.29.0).** `docs/boundary-layer-products.md`. **Trace.** The
    test above.

!!! requirement "FR-155 A named FSI input supplies the structure, and factors are applied once <span class='srs-implemented'>implemented</span>"

    *Origin: the FSI input need of the 0.29.0 scope. Evidence:
    `tests/tier1_offline/test_fsi_calibration_contract.py` and
    `tests/tier1_offline/test_workspace_fsi_setup.py`.*

    `inputs/fsi/f<id>.toml` supplies complete structural distributions, or
    calculates solid homogeneous sections from one sourced material. A MATRIX
    factor overrides a file factor exactly once, the base and effective values
    and each factor's origin are staged with their hashes, and a source and a
    derived factor along one dependency cannot compound silently. A supported
    fresh-mesh unsteady rotor row stages the existing driver's nodes,
    section-order maps and synchronous callbacks.

    - Unsupported inherited state, units, or an ambiguous blade or frame
      mapping is refused.
    - Staging is wiring; it does not establish native coupled accuracy, and
      the Euler beam and coupling model are unchanged.

    **Solution (0.29.0).** The named input and its staging in
    `pyflightstream.cases.fsi_workspace`. **Trace.** The test files above.

!!! requirement "FR-156 A macro-free workbook synchronizes with the run matrix through explicit steps <span class='srs-implemented'>implemented</span>"

    *Origin: the Excel need of the 0.29.0 scope. Evidence:
    `tests/tier1_offline/test_excel_sync.py`, `test_excel_file.py` and
    `test_excel_cli_refusals.py` under `tests/tier1_offline/`.*

    A macro-free `.xlsx` carries a Runs sheet and a Dictionary mapping. Python
    synchronizes saved files in both directions through explicit preview,
    apply and cancel commands.

    - Three-way conflicts, leading-zero identifiers, custom cells, formulas,
      legacy matrix schemas and recovery copies are kept within the supported
      workbook contract.
    - No Excel process and no trust-setting change is required, and an
      existing `.xlsm` workbook is never converted silently.

    **Solution (0.29.0).** `docs/excel-matrices.md` and the sync commands.
    **Trace.** The test files above.

!!! requirement "FR-157 A submitted additional-post extraction completes against a private copy <span class='srs-implemented'>implemented</span>"

    *Origin: the completion of FR-111 on a submitting workspace, 0.29.0.
    Evidence: `tests/tier1_offline/test_additional_post.py`.*

    On a submitting workspace each extraction is recorded `SUBMITTED` against
    a private copy of the saved simulation. `pyfs-matrix collect` waits for
    stable exports, checks the hashes of the original simulation, the script
    and the copy, translates the surface outputs and records `EXTRACTED`.
    Submission alone never means extracted, and a pending request is not
    resubmitted.

    **Solution (0.29.0).** The collect step of the additional post; it
    replaces the refusal FR-111 recorded for a submitting workspace.
    **Trace.** The test above.

!!! requirement "FR-158 A steady sweep starts every point cold unless the row says otherwise <span class='srs-implemented'>implemented</span>"

    *Origin: the geometry, units and steady-start review of the 0.29.0 quality
    gate: a warm result depends on the order of the points. It reverses the
    default FR-95 recorded at 0.16.0. Evidence:
    `tests/tier1_offline/test_approved_capabilities_029.py`.*

    A steady row's script clears the solution (`CLEAR_SOLUTION`) before each
    point, including the first point of a reopened simulation, and an absent
    `COLD_START` means cold. `COLD_START: false` in the row, or
    `build_steady_sweep(..., cold=False)`, keeps the warm behavior, and a warm
    sweep still records the order its points ran in.

    - An unsteady row refuses `COLD_START`, since every point of it is its own
      job and starts cold.
    - A value that is neither true nor false is refused at plan.

    **Solution (0.29.0).** The `cold` argument defaults to true in
    `pyflightstream.cases.workflows.build_steady_sweep`; see
    `docs/geometry-units-and-starts.md`. **Trace.** The test above.

!!! requirement "FR-159 A volume section is sampled through probes or fluid plots, not exported natively <span class='srs-implemented'>implemented</span>"

    *Origin: the volume-section review of the 0.29.0 quality gate, which
    supersedes the native export of FR-110. Evidence:
    `tests/tier1_offline/test_g05_volume_section.py`.*

    `[volume_section]` does not cut or export a native volume section into
    `datapoints/DP-<point>/`. It samples the declared plane through probes on
    a steady row, or through fluid plots on an unsteady or rotor row, which
    the section now accepts, and writes a vertex cloud to
    `post/<matrix>/fields/<point>_vsec.vtk` or `.dat`, with `_step_<STEP>` per
    unsteady step. A historical 0.27.x or 0.28.x record keeps its native
    export.

    **Solution (0.29.0).** `_pproc_sampled_volume` in
    `pyflightstream.cases.workflows`; see `docs/migrating-to-0.29.0.md`.
    **Trace.** The test above.

!!! requirement "FR-160 A Tecplot surface carries the nodal singularity strength when the pproc asks for it <span class='srs-implemented'>implemented</span>"

    *Origin: the Tecplot surface need of 0.29.0, and its reversal as an opt-in
    in 0.30.0 (SS1). Evidence: `tests/tier1_offline/test_g45_tecplot_from_vtk.py`
    and `tests/tier1_offline/test_g25_surface_time_average.py`.*

    A row whose pproc sets `singularity_strength = true` (a TOML boolean;
    `"true"` and `1` are refused) makes its Tecplot surface carry the nodal
    `Singularity_strength`, read from an auxiliary native Tecplot export beside
    the VTK, at the end of the run and at each exported step. Coordinate and
    polygon topology matching adds it beside the VTK cell quantities, without
    converting their associations or guessing a normalization, and each step
    uses its own source.

    - Without the key, the row exports the VTK alone: the `.dat` states the
      strength `NOT_CARRIED` (and `not_carried` in `products.json`), no native
      Tecplot file is written or hashed, and the point is not
      `FAILED_INCOMPLETE_OUTPUT` for lacking it. The time-averaged surface
      states it the same way.
    - `pyfs-matrix plan` states on each Tecplot row whether the strength is
      carried, and `plan.json` holds it under `singularity_strength`.

    **Solution (0.29.0 carries it always, 0.30.0 makes it a key).** See
    `docs/surface-translation.md`. **Trace.** The test files above.

!!! requirement "FR-161 Unsteady post-processing keeps an explicit time meaning <span class='srs-implemented'>implemented</span>"

    *Origin: the unsteady post review of the 0.29.0 quality gate. Evidence:
    `tests/tier1_offline/test_round1_surface_window.py` and
    `tests/tier1_offline/test_goal028_defaulted_window.py`.*

    Final Cp curves are exported once after the march. A surface mean uses the
    complete recorded window and keeps the final-step coordinates. A native
    field that contains only its final instant is distinguished from an actual
    time mean, and a wall-clock rescue whose native averaging or history
    semantics are unresolved never implies acceptance.

    **Solution (0.29.0).** The unsteady post paths of
    `docs/unsteady-postprocessing.md`. **Trace.** The test files above.

!!! requirement "FR-162 Execution and post logs report their stage and their outcome <span class='srs-implemented'>implemented</span>"

    *Origin: the log review of the 0.29.0 quality gate. Evidence:
    `tests/tier1_offline/test_cli_report_skips.py` and
    `tests/tier1_offline/test_post_diagnostics.py`.*

    Post warnings stay in the structured log and are shown with
    `--pproc-warnings`. `post --diagnostics` prints the recorded Markdown
    diagnostics to stdout without regenerating a product. A command's
    signature uses a result-aware message on stderr and leaves the structured
    stdout unchanged. A Windows callback uses a hidden runtime where that route
    is supported.

    **Solution (0.29.0).** The two options of `post` and the signature of
    `pyflightstream.run.cli`. **Trace.** The test files above.

!!! requirement "FR-163 Continuation checks its recorded inputs before it extracts <span class='srs-implemented'>implemented</span>"

    *Origin: the continuation review of the 0.29.0 quality gate, on the
    recovery of FR-96 and FR-111. Evidence:
    `tests/tier1_offline/test_additional_post.py` and
    `tests/tier1_offline/test_g58_frame_recovery.py`.*

    Recovery follows the saved script and the exact frame and source
    provenance. A historical command the package cannot read unambiguously is
    refused by name before a new extraction can invent state.

    **Solution (0.29.0).** The recovery readers of the additional post.
    **Trace.** The test files above.

!!! requirement "FR-164 A setting the package cannot apply honestly is refused by name <span class='srs-implemented'>implemented</span>"

    *Origin: the setup audit of the 0.29.0 quality gate: a key that runs with
    an effect it did not ask for is worse than a refusal. Evidence:
    `tests/tier1_offline/test_approved_capabilities_029.py` and
    `tests/tier1_offline/test_goal031_g08_glossary_claims.py`.*

    Three refusals, each on every build:

    - `ROTOR_SHEDDING` in a matrix row, whatever its value: the direction is a
      field of the relaxed trailing-edge component definition and no workflow
      command applies it. The key stays registered so the refusal names it;
      `rotor_relaxed_trailing_edges` still sets the direction from Python.
    - `legacy_solver_model` and `sonic_velocity_m_per_s` in a setup:
      `SET_SOLVER_MODEL` is documented by 25.000 alone, whose
      `INITIALIZE_SOLVER` no workflow writes, and no build from 26.101 records
      `SONIC_VELOCITY`. Use `solver_model`; the sound speed follows from the
      resolved temperature and specific-heat ratio.
    - `farfield_layers` above 5: the setup accepts 1 to 5, the documented
      range, and every standard setup states 5.

    **Solution (0.29.0).** The refusals at plan, and the input glossary that
    says so. **Trace.** The test files above.

!!! requirement "FR-165 A quasi-steady rotor is a run type: a sector or a wheel <span class='srs-implemented'>implemented</span>"

    *Origin: her decisions of 2026-09-29: "ai fica qsteady_rotor - se tiver
    simetria periodica, fica o caso setor"; "sobre os modos quasi steady,
    lembrando que eles podem ser chamados sem fsi. Eles se tornam workflows e
    o fsi continua como variavel opcional a direita da matriz". Evidence:
    `tests/tier1_offline/test_goal035_qsteady_rotor.py`,
    `test_goal035_qsteady_completion.py` and `test_goal035_l1_defects.py`
    under `tests/tier1_offline/`.*

    The `qsteady_rotor` run type solves an isolated axisymmetric rotor steady,
    its blades held still and the free stream turning about its shaft at its
    speed (`SET_FREESTREAM ROTATION` in the rotor's hub frame, signed by the
    rotor block's `rpm_sign`). The reference declares exactly one rotor block.

    - `SYMMETRY PERIODIC` is a SECTOR: one blade solved once, in an inflow that
      varies with the radius alone; an angle is refused and a custom inflow is
      checked for it (axisymmetric to 0.1 percent of its largest speed).
    - No symmetry is the WHEEL: every blade, and with an inflow that varies
      around the disc the row key `PASSAGE_POSITIONS: k` is required, the wheel
      solved at `theta_i = i (360 / N) / k` inside one blade passage and
      averaged by the post. A custom inflow on the wheel is the total velocity
      at the disc, and the package removes the rotation
      (`pyflightstream.cases.freestream.prepare_rotating_field`).
    - A second rotor, an actuator disc, a body rate or a boundary of the
      geometry that is none of the rotor's families is refused.

    **Solution (0.30.0).** The run type, `RotorShaftLoads` (`force_n`,
    `moment_hub_nm`) and `helpers.rotate_surfaces(after_initialization=True)`
    to clock surfaces between two solves. **Trace.** The test files above.

!!! requirement "FR-166 A wheel point states where its quasi-steady assumption holds <span class='srs-implemented'>implemented</span>"

    *Origin: her decision of 2026-09-29: "concordo do plan avisar", the plan
    warning when part of the span has k above 0.1. Evidence:
    `tests/tier1_offline/test_goal035_qsteady_completion.py` and
    `tests/tier1_offline/test_goal035_qsteady_rotor.py`.*

    The 1P reduced frequency `k = Omega c / (2 V_rel)` of a wheel point, the
    1P counted on the blade, is stated per station. `pyfs-matrix plan` shows
    the percent of the span with `k > 0.1` and the `k` minimum, maximum and
    mean, and warns naming the point when that percent is above zero. A point
    with no free-stream speed and no rotation states that `k` is not defined.

    After the post, each wheel point's `<point>_qsteady_validity.json` carries
    its validity, including the thrust and torque shares from the stations
    above `k = 0.1`, and its super-file row carries the validity columns
    (`K_1P_MIN` to `TORQUE_PCT_K_GT_0_1`). Two products,
    `polars/P<sim>-<ALIAS>_qs_positions.csv` (the loads at every clocking) and
    `_qs_avg.csv` (their mean per point), carry the same columns.

    **Solution (0.30.0).** `pyflightstream.cases.qsteady` and
    `pyflightstream.post.qsteady`; `PASSAGE_POSITIONS` is read as every count
    of a row. **Trace.** The test files above.

!!! requirement "FR-167 The plan reports the inflow's harmonic content as one blade meets it <span class='srs-implemented'>implemented</span>"

    *Origin: the wheel validity design of 0.30.0. Evidence:
    `tests/tier1_offline/test_goal035_qsteady_completion.py`.*

    `pyfs-matrix plan --inflow-fft` reports, for each wheel point in a custom
    inflow, the harmonics of that inflow as one blade meets it over a
    revolution: per station `n95` and `k_eff = n95 k_1P`, per point the `k_eff`
    minimum, maximum and mean, the percent of the span above 0.1, `n_max` and
    the suggested `PASSAGE_POSITIONS >= n_max / N + 1`, warned when the row
    states fewer. With the option the reduced-frequency warning reads `k_eff`.
    A harmonic below 0.001 degree of angle of attack is not counted.

    **Solution (0.30.0).** `blade_inflow_harmonics` and `qsteady_inflow_fft`.
    **Trace.** The test above.

!!! requirement "FR-168 FSI couples on a quasi-steady periodic sector and is refused on the wheel <span class='srs-implemented'>implemented</span>"

    *Origin: her decisions of 2026-09-29: "esse do quasi steady quero que entre
    na 30, e tanto o modo setor quanto o modo wheel" and, on the wheel with
    FSI, "esse wheel quasi estatico parece nao fazer sentido com fsi, vamos
    manter esse recusado por enquanto". Evidence:
    `tests/tier1_offline/test_fsi1_workspace_pieces.py`.*

    FSI on a `qsteady_rotor` periodic sector is the steady coupled route of
    the fixed wing with the ROTATING blade as the structure. Its
    `omega_rad_per_s` is taken from the row's `RPM`
    (`effective_fsi_config`), so the structural solve applies the centrifugal
    tension and stiffening and the in-plane centrifugal softening at the speed
    the free stream turns.

    - The route couples blade one at azimuth 0 on Z, shaft X through the
      origin, one XY section distribution in a frame coinciding with the
      reference, and refuses anything else by name.
    - The wheel with FSI stays refused.

    **Solution (0.30.0).** `cases.fsi_workspace.wire_quasi_steady_sector_fsi`
    and the run folder marker `fsi_quasi_steady_rotor`. **Trace.** The test
    above.

!!! requirement "FR-169 A fixed wing couples on a steady or an unsteady row without rotor motion <span class='srs-implemented'>implemented</span>"

    *Origin: FSI-G of the 0.30.0 scope, and the refusal FSI-GUARD that bounds
    it. Evidence: `tests/tier1_offline/test_fsig_fixed_wing.py` and
    `tests/tier1_offline/test_fsi1_workspace_pieces.py`.*

    An FSI input stating `[config.wing]` (with `omega_rad_per_s = 0` and
    `blade_count = 1`) is one wing clamped at its first station, its stiffness
    and mass distributions built as a blade's are. Its structural solve
    applies the aerodynamic sectional loads plus the wing's own weight, with no
    centrifugal term. Gravity is a vector of the reference frame, -z by
    default, which the angle of attack never turns; `self_weight = false`
    removes it. The wing is fed by one XZ section distribution in a frame with
    the reference axes at the wing's origin.

    - A steady coupled script ends at `EXECUTE_AEROELASTIC_ANALYSIS` with at
      most 50 coupling iterations, nothing follows it, and the run is waited
      for on the line `Aeroelastic solver run time`; a submitting executor,
      the probe points, the volume section and the loads selections are
      refused on that route.
    - FSI on `unsteady_rotor` is refused by the plan with the message "FSI on
      unsteady_rotor is still in debug on this release"; the table
      `FSI_WORKFLOW_STATE` states every workflow's FSI state, None meaning
      accepted.

    **Solution (0.30.0).** The pieces in `pyflightstream.cases.fsi_workspace`:
    `aeroelastic_surface_ids`, `structural_node_layout`,
    `patch_structural_node_frame`, `aeroelastic_rbf_type`,
    `aeroelastic_post_script`, `emit_steady_aeroelastic_analysis`,
    `refuse_lines_after_steady_analysis` and `steady_aeroelastic_finished`.
    **Trace.** The test files above.

!!! requirement "FR-170 The structural nodes sit inside the blade <span class='srs-implemented'>implemented</span>"

    *Origin: FSI-1 of the 0.30.0 scope. Evidence:
    `tests/tier1_offline/test_fsi1_nodes_inside.py`.*

    A configuration that carries the blade's sections
    (`BladeProperties.section_contours_m`) places the nodes on each section's
    camber line: the elastic-axis node at the configured chord fraction (30
    percent when that lies outside 20 to 50 percent), the leading-edge and
    trailing-edge nodes at 10 and 90 percent, at the local twist. Planning
    refuses a node set with any node outside its section, or inside it by less
    than max(1 mm, 10 percent of the local thickness), naming the node. A
    configuration without sections keeps the offset layout, unchecked.

    **Solution (0.30.0).** The layout; `fsi_node_map.json` gains the leading
    and trailing edge normal positions for such a layout, and a calculated
    configuration's `config_sha256` includes its sections. **Trace.** The
    test above.

!!! requirement "FR-171 The coupled blade route emits a kernel that transfers the bend <span class='srs-implemented'>implemented</span>"

    *Origin: FSI-1 of the 0.30.0 scope, measured on 26.124 (RPT-093 section
    7). Evidence: `tests/tier1_offline/test_fsi1_workspace_pieces.py` and
    `tests/tier1_offline/test_fsig_fixed_wing.py`.*

    The coupled blade route emits `AEROELASTIC_RBF_TYPE MULTI_QUADRATIC`
    unless the row's setup states a kernel. On one beam line `WENDLAND_C2`
    delivered 64 percent of an imposed bend at the leading edge and 1.4
    percent at the trailing edge, and the coupled run diverged;
    `MULTI_QUADRATIC` delivered it to 3 mm.

    **Solution (0.30.0).** `aeroelastic_rbf_type`; see `docs/fsi-workspace.md`.
    **Trace.** The test files above.

!!! requirement "FR-172 The rotating structural solve includes the in-plane centrifugal softening <span class='srs-implemented'>implemented</span>"

    *Origin: FSI-1 of the 0.30.0 scope. Evidence:
    `tests/tier1_offline/test_fsi1_in_plane_softening.py`.*

    The rotating structural solve includes the in-plane centrifugal softening
    `mu Omega^2 sin^2(beta) w` of the flap, iterated with the twist: a flap
    along the section normal at pitch `beta` moves the section in the rotor
    plane, where the centrifugal field pulls it outward. `RotatingSolution`
    states `flap_residual_m` and `flap_tolerance_m`, and `converged` requires
    both residuals.

    **Solution (0.30.0).** `fsi.centrifugal.in_plane_softening_coefficients`
    and `solve_rotating_static`. **Trace.** The test above, whose oracle checks
    the coefficient station by station and the tip-flap increase against an
    independent hand integration to 0.1 percentage point.

!!! requirement "FR-173 The workspace's disk is measured, freed and cleaned by named commands <span class='srs-implemented'>implemented</span>"

    *Origin: her decision of 2026-09-28 on the modes of the recipe,
    "compact_sims, delete_extensions, post_archives", and her request "quero
    no plan um check de memoria disponivel e um aviso se as rodadas da matriz
    vao caber ou nao, pra ver se ele recomenda um free-space". Evidence:
    `tests/tier1_offline/test_goal035_storage.py`.*

    `pyfs-matrix space-in-use` reports the sizes on disk by top level folder,
    by `sims/sim_*` and by extension. `free-space m<id>` runs the recipe of
    `inputs/management/m<id>.toml`: compact simulation folders into
    `sims/sim_<id>.zip`, delete files of named extensions under `sims/`, or
    compact or delete the post's `archive/<stamp>/` folders. `delete-sims`
    deletes named simulations, their own post products and their `runs.json`
    records. Each command previews by default and changes files only with
    `--apply`.

    - `delete-sims` refuses to apply against a matrix product shared with
      other points until `--matrix-products` says what happens to it.
    - Every call is recorded in `storage_management.json`; a `deleted_sim`
      note row may sit in `runs.json` and `read_manifest` skips it.
    - `pyfs-matrix plan` warns when the points still to run may not fit on the
      disk, from the mean size of a recorded datapoint, naming `free-space`.

    **Solution (0.30.0).** `pyflightstream.workspace.storage`; see
    `docs/storage-and-sync.md`. **Trace.** The test above.

!!! requirement "FR-174 A recipe prunes the per-step exports and a later post refuses what it removed <span class='srs-implemented'>implemented</span>"

    *Origin: the storage recipes of 0.30.0. Evidence:
    `tests/tier1_offline/test_goal035_prune_step_exports.py`.*

    The `free-space` table `[[prune_step_exports]]` keeps the last step of each
    per-step export (`<name>_iteration=<step>`) of each point of an unsteady
    row that exported at every step, and deletes the earlier steps, previewing
    by default. The recorded call lists the steps deleted per point and the
    deleted files leave `products.json`; a product made before stays, file and
    entry, marked `kept_after_pruning`.

    - A later `post` that needs a deleted step refuses the series, the
      time-averaged surface or the section distribution by name, naming the
      missing steps and the storage call, instead of writing it from the
      steps that remain.

    **Solution (0.30.0).** `docs/storage-and-sync.md`. **Trace.** The test
    above.

!!! requirement "FR-175 Sync brings runs, results and matrices from the other workspaces <span class='srs-implemented'>implemented</span>"

    *Origin: her instruction of 2026-09-28, "foca no storage-management e
    sync". Evidence: `tests/tier1_offline/test_goal035_storage.py` and
    `tests/tier1_offline/test_sync_plan_points_without_record.py`.*

    `pyfs-matrix sync` brings runs and results from the workspaces named in
    `inputs/sync-workspaces.toml` into the main one at a cumulative level
    (`runs`, `post`, `fsm`, `all`), previewing by default. Main wins a
    conflict unless `--prefer-other`, and `--overwrite` archives main's copy
    of a conflicting file before taking the other's.

    - A matrix is declared by the one workspace that owns it
      (`matrices = [...]`), every difference is reported as a merge conflict,
      and the owner's copy wins.
    - A synced simulation's `inputs` is linked into the main workspace's own
      geometry library, never copied; `delete-sims` and `free-space` undo
      every link in a simulation folder before removing it, so the mesh it
      points at survives.

    **Solution (0.30.0).** `pyflightstream.workspace.storage`. **Trace.** The
    test files above.

!!! requirement "FR-176 Tip and helical Mach numbers are stated for every rotor point <span class='srs-implemented'>implemented</span>"

    *Origin: her instruction of 2026-09-28: "para todos unsteady rotor a
    inclusao do calculo de mach tip (vindo da velocidade tangencial devido ao
    rpm) e o mach helicoidal (composicao tangencial e freestream)" and "no
    plan, eu quero que avise se tem pontos da polar que podem exceder mach
    helicodal = 1". Evidence:
    `tests/tier1_offline/test_goal035_rotor_mach.py`.*

    Every point of an `unsteady_rotor` row, of a `steady` row that states
    `RPM`, and of a row naming an actuator disc states
    `M_tip = Omega R / a` and `M_hel = sqrt(V^2 + (Omega R)^2) / a`, with
    `Omega = 2 pi RPM / 60`, `R` half the rotor diameter (a disc's
    `tip_radius_m`) and `V`, `a` the point's resolved free stream and speed of
    sound; at `V = 0`, `M_hel = M_tip`. They are computed in one place
    (`pyflightstream.cases.workflows.rotor_mach_numbers`).

    - `pyfs-matrix plan` prints both per rotor per point, `plan.json` carries
      them under `rotor_mach`, and the plan WARNS, naming the point, its rotor
      and its value, when `M_hel >= 1`. It never refuses for it.
    - A rotor of unknown radius is named with the row instead of a number.
    - The run record carries the block, and the rotor table gains two LAST
      columns, `MTIP_<alias>` and `MHEL_<alias>`, so every existing column
      keeps its position.

    **Solution (0.30.0).** `docs/post-processing-definitions.md`, "Tip and
    helical Mach numbers". **Trace.** The test above.

!!! requirement "FR-177 The user guides ship as numbered decks under guide/ <span class='srs-implemented'>implemented</span>"

    *Origin: her instruction of 2026-09-28, "vamos enumerar os guias tambem,
    fica na ordem: geral workspaces, gui to pyfs, references (novo, explicando
    arquivo refs), setup, pproc, fsi, python enviroment installation for
    offline machines". Evidence: `tests/tier1_offline/test_guide_decks.py`
    and `tests/tier1_offline/test_house_style.py`.*

    The guides are decks in `guide/` with their LaTeX sources
    (`guide/latex-sources/`), their build recipe and their compiled PDFs, each
    ending on numbered references, licensed CC BY 4.0
    (`guide/LICENSE-AND-AUTHORSHIP.md`). Since 0.31.0 they are eight, named
    `pyfts-guide-00` to `pyfts-guide-07`, guide 00 being the overview read
    first. A PDF may be tracked under `guide/` and nowhere else: the
    forbid-pdf hook, the CI guard job and the tier-1 walk of the tracked files
    carry the same exemption, and a test shows the hook and the job refuse
    exactly what the walk refuses.

    **Solution (0.30.0 seven decks, 0.31.0 eight and renamed).** **Trace.**
    The test files above.

!!! requirement "FR-178 Every console command ends with a signature and prints a readable log <span class='srs-implemented'>implemented</span>"

    *Origin: the console of 0.30.0. Evidence:
    `tests/tier1_offline/test_cli_signature.py` and
    `tests/tier1_offline/test_clean_log.py`.*

    Every console command ends with a box on stderr: an ASCII drawing 81
    columns wide with a phrase, a blank line before and after. A successful
    post is always the koala; another success, a failure and a cancellation
    each draw from their own drawings. `--help` and `--version` keep one short
    line, and the box never changes stdout or the exit code. The run banner
    draws one of two aircraft at random.

    A warning of the package's own categories prints as
    `[warning] <message>`, without the installed file's path, line number or
    echoed source line; Python callers keep Python's standard warnings. The
    stage lines print the workspace root once, absolute, and paths under it
    relative. `run --force-rerun` says one line per simulation with a count.
    `logs/activity.log` keeps every point and absolute paths, and `--verbose`
    of `run`, `collect` and `post` prints the full format again.

    **Solution (0.30.0).** The signature and the warning formatter of
    `pyflightstream.run.cli` and `pyflightstream._console`. **Trace.** The
    test files above.

!!! requirement "FR-179 The plan console is laid out in titled blocks <span class='srs-implemented'>implemented</span>"

    *Origin: her words of 2026-09-29: "claude, ainda to achando o log dificil
    de ler, talvez vale um espaco entre linhas" and "eu como usuaria nao sei o
    que eu to olhando sabe? o que cada bloco diz, etc"; she placed it inside
    0.31.0 (P13, "Dentro da 0.31.0"). Evidence:
    `tests/tier1_offline/test_goal036_console_blocks.py` (P0310-CONSOLE-BLOCKS).*

    The console of `pyfs-matrix plan` is laid out in blocks, each with a title
    line saying what it is and one blank line between two: the header, `Warnings
    (n)`, `Cases`, `Blocked points (n)`, `Rotor Mach numbers`, `Quasi-steady
    validity per point`, `Solver setup per case`, `Solver cost per point` and
    `Files written`. A block with nothing to say is not printed.

    - Every console warning of the package, under any command, is wrapped at
      90 columns under its text and followed by a blank line, its words
      unchanged.
    - The `[continuation] started` and `finished` lines print only with
      `--verbose`, which `plan` accepts; `logs/activity.log` records them as
      before.
    - Warnings stay on stderr and the blocks on stdout; the exit codes,
      `plan.json` and every product are unchanged.

    **Solution (0.31.0).** **Trace.** The test above.

!!! requirement "FR-180 An unsteady rotor point writes a per-revolution product with its drift <span class='srs-implemented'>implemented</span>"

    *Origin: G2 of the 0.31.0 scope (P0310-G2-PER-REV). Evidence:
    `tests/tier1_offline/test_goal036_per_revolution.py`.*

    An `unsteady_rotor` point writes
    `probes/<point>_per_revolution_<ALIAS>.csv` for each rotor its row turns:
    one row per COMPLETE revolution, read from the written plots table, with
    the mean of every plotted column and, from the second revolution on, each
    column's drift from the previous revolution in percent (`NA` where that
    mean is zero). A trailing partial revolution is excluded and said.

    - The pproc may declare `[per_revolution] drift_limit_pct` (positive,
      default 1); when the last revolution's drift of a force or moment column
      exceeds it, `post.log` carries a WARNING naming the point, rotor, column,
      drift and limit, and nothing is blocked.

    **Solution (0.31.0).** Defined in `docs/post-processing-definitions.md`.
    **Trace.** The test above.

!!! requirement "FR-181 A rotor point writes a per-station harmonic product <span class='srs-implemented'>implemented</span>"

    *Origin: the harmonic product of the 0.31.0 scope (P0310-HARMONICS).
    Evidence: `tests/tier1_offline/test_goal036_harmonics.py`.*

    A rotor point writes `sections/<point>_harmonics.csv`: per rotor, blade
    station and sectional load quantity (`Fx`, `Fz`, `Moment`), the
    least-squares `H0 + A1 cos(psi - PHI1) + A2 cos(2 psi - PHI2)` over every
    sample of the station, `psi` being the blade azimuth the written sections
    state. A wheel fits every blade at every clocking; an `unsteady_rotor`
    point every blade over its last complete revolution. `PHI` is in degrees in
    [0, 360).

    - A harmonic whose station has fewer distinct azimuths than it needs (1P
      3, 2P 5) is `NA`, said once in `post.log`.
    - A station that does not match across samples, and an `unsteady_rotor`
      point with no sections series, no export window or no rotor record, is
      a named skip with a WARNING.
    - The product is registered in `products.json` (`kind` `harmonics`).

    **Solution (0.31.0).** `pyflightstream.post.harmonics`. **Trace.** The test
    above.

!!! requirement "FR-182 Each blade and each clocking states its own azimuth <span class='srs-implemented'>implemented</span>"

    *Origin: the azimuth corrections of the 0.31.0 scope
    (P0310-H2-BLADE-AZIMUTH). Evidence:
    `tests/tier1_offline/test_goal036_blade_azimuth.py` and
    `tests/tier1_offline/test_goal036_positions_azimuth.py`.*

    A block of an `unsteady_rotor` sections table or series that cuts the
    families of one blade states THAT blade's azimuth: blade `n` of `N` at blade
    one's plus `(n - 1) 360 / N`, through
    `pyflightstream.post.axes.placed_blade_azimuth_deg`. A block over several
    blades or the general families keeps blade one's, and blade one's rows are
    unchanged. A wheel's blade `n` at clocking `i` is at
    `pyflightstream.post.axes.clocked_blade_azimuth_deg`, `datum + sign(rpm)
    theta_i`, and the clockings table `_qs_positions.csv` reads the same rule,
    so a left-hand wheel (`rpm_sign` -1) states `datum - theta_i`.

    **Solution (0.31.0).** The two public functions above. **Trace.** The test
    files above.

!!! requirement "FR-183 A clocked wheel cuts, exports and tabulates its sections at every clocking <span class='srs-implemented'>implemented</span>"

    *Origin: G1 of the 0.31.0 scope, confirmed on 26.124 (RPT-094). Evidence:
    `tests/tier1_offline/test_goal036_wheel_sections.py`.*

    A `qsteady_rotor` wheel of `PASSAGE_POSITIONS` 2 or more exports its
    sections, sectional loads and section Cp at every clocking: each clocking
    deletes the previous clocking's distributions, turns the wheel,
    initializes, creates them again in frames turned with the wheel and held
    there, updates and exports them as `<point>_qs<i>_cp.txt`,
    `<point>_qs<i>_sloads.txt` and `<point>_qs<i>_plot_cp_sections.txt`. Every
    clocking is cut at the same stations, and the point's quasi-steady record
    names each clocking's files (`section_exports`).

    - A wheel whose pproc cuts its sections in `LOCAL_AXIS` places one frame
      per blade, `<ALIAS>_RMRP<k>`, at the blade's azimuth.
    - `sections/<point>_sections.csv` and each distribution's loads and Cp file
      gain a `CLOCKING` column and a block of rows per clocking; a clocking not
      cut at clocking 0's stations is warned, and a missing export is named in
      `products.json`.

    **Solution (0.31.0).** **Trace.** The test above.

!!! requirement "FR-184 Custom free-stream files are built from other fields by named operations <span class='srs-implemented'>implemented</span>"

    *Origin: the field operations of the 0.31.0 scope (G6). Evidence:
    `tests/tier1_offline/test_goal036_field_operations.py`.*

    `pyfs-workspace field mirror|move|subtract|time-mean` builds a custom
    free-stream file of `inputs/freestreams/`: mirrored through the plane
    `x`, `y` or `z = 0` (`--plane`); moved so a source point lands on a target
    point; `total - (other - reference)` point by point on one grid, with the
    reference free stream REQUIRED (`--reference VX VY VZ`); or the time mean of
    an unsteady run's equally spaced per-step fields. Values are metres and
    metres per second in the global frame, nothing converted.

    - A different grid on `subtract` is refused, naming both files.
    - Each operation previews by default, writes only with `--apply` (the file
      and `<stem>.provenance.json` naming the operation, its parameters and the
      sha256 of every input), and never overwrites without `--overwrite`.

    **Solution (0.31.0).** `pyflightstream.workspace.fields`
    (`mirror_field`, `move_field`, `subtract_fields`); see
    `docs/field-operations.md`. **Trace.** The test above.

!!! requirement "FR-185 The wheel's correction machinery applies a fitted calibration beside the raw product <span class='srs-implemented'>implemented</span>"

    *Origin: her answer P9 of 2026-09-29, "Tudo, inclusive R1 (Recomendado)",
    which shipped routes 2 and 4 and only a diagnostic for route 1. Evidence:
    `tests/tier1_offline/test_goal036_qsteady_corrections.py`
    (P0310-CAL-SCHEMA, P0310-ROUTE2, P0310-ROUTE4, P0310-APPLY-*).*

    A pproc's `[qsteady_correction]` table names a `route` (`none`, the
    default; `table`, a calibration you fitted, route 4; `sector_offset`, a 0P
    offset from an axial unsteady sector run, route 2), the `file` of its
    calibration, `inputs/calibrations/<id>.toml` (an input kind created by
    `pyfs-workspace init`), and a `diagnostic`. It is off by default and NOT
    VALIDATED.

    - A calibration's rows name a component, its place on `J`, `ALPHA` and
      `K_1P`, and `OFFSET_0P`, `GAIN_0P`, `GAIN_1P`, `PHASE_1P_DEG`; the rows
      form a tensor grid interpolated multilinearly and never extrapolated (a
      point outside is `NA`, named and warned).
    - A file that cannot be read is refused whole naming the line
      (`CalibrationError`), at plan and at post.
    - The post writes `<name>_corrected.csv` BESIDE the raw rotor table,
      average table, harmonic product and sections, never over them. Each ends
      with `CORRECTION_ROUTE` and `CALIBRATION_SHA256`, and its `products.json`
      entry names the raw file, the route, the calibration, its sha256, the
      grid cells used and "not validated".
    - Everything runs at post; no route needs a new run.

    **Solution (0.31.0).** `pyflightstream.post.corrections`, including
    `sector_offset_calibration`; the input template names the
    `[per_revolution]` and `[qsteady_correction]` tables and the calibration
    file; see `docs/qsteady-corrections.md`. **Trace.** The test above.

!!! requirement "FR-186 The Theodorsen and Sears diagnostic corrects nothing, and the other routes are refused <span class='srs-implemented'>implemented</span>"

    *Origin: her answer P9 of 2026-09-29 (route 1 only as a diagnostic).
    Evidence: `tests/tier1_offline/test_goal036_qsteady_corrections.py`
    (P0310-ROUTE1-DIAGNOSTIC, P0310-ROUTE3-REFUSED).*

    `diagnostic = "theodorsen"` writes `sections/<point>_theodorsen.csv`: per
    station `K_1P`, `C(k)` and `S(k)` (modulus and phase), beside the measured
    1P amplitude and phase of the harmonic product. The Bessel functions of
    orders 0 and 1 are the package's own, held to 1e-10, since scipy is not a
    core dependency.

    - Route 1 asked as a correction, and route 3 (`dynamic_inflow`,
      `skewed_wake`, `pitt_peters`, `coleman`), are refused where the pproc or
      the calibration is read, each with its reason.

    **Solution (0.31.0).** `pyflightstream.post.corrections.bessel_j` and
    `bessel_y`. **Trace.** The test above.

!!! requirement "FR-187 A wheel point states its rotor state <span class='srs-implemented'>implemented</span>"

    *Origin: the rotor state the correction routes read, 0.31.0. Evidence:
    `tests/tier1_offline/test_goal036_rotor_state.py`.*

    A wheel point states `CT_ROTOR` (`T / (rho A (Omega R)^2)`), `CT_PROPELLER`
    (`T / (rho n^2 D^4)`), `MU_ROTOR` and `LAMBDA_C` (the free stream in and
    through the disc over the tip speed), the momentum-theory induced inflow
    `LAMBDA_I` (Glauert, solved by Newton to 1e-10) and the wake skew
    `CHI_DEG`, from the mean thrust over its clockings. They follow the validity
    columns in `_qs_avg.csv` and sit under `rotor_state` in
    `<point>_qsteady_validity.json`. An inflow that does not converge is `NA`
    with a WARNING in `post.log`.

    **Solution (0.31.0).** `pyflightstream.cases.qsteady.glauert_induced_inflow`
    and `pyflightstream.post.axes.free_stream_on_rotor_axis`. **Trace.** The
    test above.

!!! requirement "FR-188 The rotor table states the rotor's in-plane coefficients <span class='srs-implemented'>implemented</span>"

    *Origin: the in-plane loads of the 0.31.0 scope. Evidence:
    `tests/tier1_offline/test_goal036_rotor_in_plane.py`.*

    The rotor table states, as its last four columns after `MTIP_<alias>` and
    `MHEL_<alias>`, `CN_<alias>`, `CS_<alias>`, `CMN_<alias>` and `CMS_<alias>`:
    the force along the rotor's normal and side axes over `rho n^2 D^4` and the
    moment about them at the hub over `rho n^2 D^5`. The axes `(T, S, N)` are
    right-handed: `T` the rotor's axis, `N` the part of the reference frame's up
    (+z) square to it, `S = N x T`. A rotor whose axis lies along up reads `NA`
    in the four, said once in the post log.

    **Solution (0.31.0).** `post.axes.rotor_in_plane_axes` and
    `rotor_in_plane_loads`; defined in `docs/post-processing-definitions.md`.
    **Trace.** The test above.

!!! requirement "FR-189 The quasi-steady record has one type, one reader and one refusal <span class='srs-implemented'>implemented</span>"

    *Origin: the record consolidation of the 0.31.0 scope. Evidence:
    `tests/tier1_offline/test_goal036_qsteady_record.py`.*

    `<point>_qsteady.json` is read as a `QsteadyRecord` by
    `pyflightstream.cases.qsteady.read_qsteady_record`, which raises
    `QsteadyRecordError` for a record that is missing, unreadable or of another
    schema. The file the builder writes is byte for byte what 0.30.0 wrote.

    - The run never ignores an unreadable record in silence: it judges the
      point's log as one solve and records a warning on the point.
    - The post names each product such a point loses in `products.json` and
      `post.log`; a missing record is named as what it is.

    **Solution (0.31.0).** The two readers it replaces are removed.
    **Trace.** The test above.

!!! requirement "FR-190 The rotor table of a wheel is the mean of its clockings <span class='srs-implemented'>implemented</span>"

    *Origin: the wheel table of the 0.31.0 scope. Evidence:
    `tests/tier1_offline/test_goal036_rotor_mean.py`.*

    A wheel point's row of `polars/P<sim>-<ALIAS>_rotor.csv` is taken from the
    rotor's force and moment averaged over the point's `k` clockings, each
    clocking's own loads export, and `CT`, `CQ`, `CP`, `ETA`, `ETAW`, `CN`, `CS`,
    `CMN` and `CMS` are computed from those mean loads, never as a mean of
    per-clocking `ETA`. The table's `products.json` entry states `"source":
    "mean of k clockings"` and `"clockings": k`. A wheel point whose clocking
    export is missing is not a row and is named in `skipped`. A sector's row is
    unchanged.

    **Solution (0.31.0).** The 0.30.0 numbers remain a valid record of
    clocking 0. **Trace.** The test above.

!!! requirement "FR-191 A wheel's thrust and torque shares are taken along the rotor's axis <span class='srs-implemented'>implemented</span>"

    *Origin: the share defect of the 0.31.0 scope, confirmed on 26.124
    (RPT-094). Evidence: `tests/tier1_offline/test_goal036_thrust_axis.py`.*

    `THRUST_PCT_K_GT_0_1` and `TORQUE_PCT_K_GT_0_1` project each station's force
    on the record's `axis_vector`, stated in the frame the distribution was cut
    in, and take the torque as the moment of its in-plane component about the
    axis. A share reads `NA`, with a WARNING in `post.log`, where the frame's
    axes or the plane are not known, where a station states its `Fx`, `Fz` or
    `Offset` as `NA` (a gap is never read as a zero load), where the total is
    zero, or where stations of opposite sign put it outside 0 to 100 percent. A
    cut in the frame's XZ or XY plane is read; a YZ cut reads `NA`.

    **Solution (0.31.0).** `pyflightstream.post.axes.section_station_shaft_loads`.
    **Trace.** The test above.

!!! requirement "FR-192 A quasi-steady row resolves its advance ratio against the rotor block's own diameter <span class='srs-implemented'>implemented</span>"

    *Origin: the diameter rule of FR-63 for `unsteady_rotor` extended to
    the quasi-steady run type, 0.31.0. Evidence:
    `tests/tier1_offline/test_goal036_qsteady_own_diameter.py`.*

    A `qsteady_rotor` row that states `ADVANCE_RATIO` resolves `J`, and so the
    rotor speed `n = V / (J D)`, against the rotor block's own `diameter_m`, as
    an `unsteady_rotor` row does, instead of the reference's top-level
    `rotor_diameter_m`.

    **Solution (0.31.0).** **Trace.** The test above.

!!! requirement "FR-193 The repeated-POL census reads the matrices that sync reads <span class='srs-implemented'>implemented</span>"

    *Origin: her answer P12 of 2026-09-29, "Entra na 0.31 (Recomendado)".
    Evidence: `tests/tier1_offline/test_goal036_pol_census.py`
    (P0310-POL-CENSUS).*

    `pyfs-matrix plan` compares POLs across `<root>/*.fs` and
    `<root>/inputs/matrices/*.fs`, the two folders that sync and storage read,
    so a POL repeated between them, which would share one simulation folder, is
    seen. A matrix planned from any other folder plans with a warning naming
    it and saying that sync and the census do not see it.

    **Solution (0.31.0).** One function, `pyflightstream.workspace.matrix_files`,
    lists the matrices for the census, storage and sync. **Trace.** The test
    above.

!!! requirement "FR-194 The change log names the requirement of every capability it lists <span class='srs-implemented'>implemented</span>"

    *Origin: her request of 2026-09-29: "eu tambem quero que todas essas novas necessidades atendidas pelo pyflightstream nos ultimos releases sejam refletidas no src. Eu trouxe aqui as necessidade, debatemos requisito e solucao, mas nem tudo foi parar na documentacao do src". Evidence: `tests/tier1_offline/test_srs_changelog.py` (P0320-SRS-CHANGELOG).*

    Every top-level bullet of the Added and Changed sections of every release
    from 0.25.0 on, and of every `changelog.d` fragment, cites a requirement
    id that a page under `docs/srs/` defines, or says
    `(no requirement: <reason>)`. The sections headed as the type-checker debt
    are a measurement and are excluded.

    - A definition is an SRS admonition title, a heading or the first cell of a
      table row.
    - A bullet that cites nothing, or cites an id no page defines, fails the
      test naming the release and quoting the bullet.

    **Solution (0.32.0).** The tier-1 test, parametrised by release and by
    fragment, with a control that the parser reads the releases it claims to
    read and refuses an uncited bullet. **Trace.** The test above.
