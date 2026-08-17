# Scope

## In scope

The package owns the full pipeline from case definition to
engineering results:

- The per-version command database with evidence-backed statuses.
- Validating script construction (builder plus curated helpers).
- Campaign and case modeling, including the pipe-delimited run-matrix
  format as a first-class interface.
- Headless execution with a manifest recording every outcome.
- Output parsing and tabular post-processing.
- The managed workspace: input-artifact library, run layout, naming,
  archiving.
- Far-field probe surveys and their conservation ledgers.
- Aeroelastic coupling (the `fsi` subpackage, optional extra).
- The QA ladder: CI tests, licensed command-validity probes, licensed
  physics regression and cross-version drift.

## Non-requirements

Explicit exclusions. Like requirements, they carry stable identifiers
and are never silently dropped.

!!! nonrequirement "NREQ-01 No GUI"
    The package is a library and a set of command-line tools. No
    graphical interface is planned or accepted.

!!! nonrequirement "NREQ-02 No geometry generation or meshing"
    The predecessor imported pre-built meshes; so does pyflightstream.
    Synthetic QA geometry generators exist for testing, not as a
    meshing product. Open-source meshers are reachable only as
    external tools through file exchange (see the integrations
    research card, RPT-008).

!!! nonrequirement "NREQ-03 No solver-accuracy claims"
    The physics regression matrix guards regressions of the pipeline
    and of solver behavior across versions. It does not validate
    FlightStream physics against nature, and the package makes no
    accuracy claims on the solver's behalf.

!!! nonrequirement "NREQ-04 No FlightStream versions older than 26.0"
    The registry starts at 26.000. Supported versions are only ever
    added going forward, never dropped (NFR-04).

!!! nonrequirement "NREQ-05 No command family is excluded from the database (narrowed to nothing 2026-08-08)"
    Every command any registered manual edition documents enters the
    database, chapter by chapter. This non-requirement now excludes
    NOTHING, and it is kept rather than deleted because identifiers here
    are never reused and because the two narrowings are the record of a
    scope decision reversing itself.

    NARROWED TO NOTHING on 2026-08-08, the author's decision, when the
    mesh-wrapper chapter entered: eleven commands read from all four
    registered editions in one pass. That was the last family the
    exclusion still named, so what remains here is a heading over an
    empty set.

    Read the reversal as a whole rather than as two edits. The original
    exclusion was a reasonable bet that a family nobody had asked for
    was not worth the reading, and the bet was wrong in a way that is
    invisible from outside the package: a caller meets a refusal for a
    command their own manual documents, and nothing tells them the
    command was excluded rather than missing. Entering the families
    whole is also what surfaced two defect classes, the
    parameter-table-versus-sample disagreement and the copied sample,
    neither of which reading one command at a time would have shown.

    **PROPOSED CORRECTION, PENDING THE AUTHOR, NOT APPLIED (2026-08-17).**
    The heading and the first sentence say this excludes NOTHING, and
    that stopped being true on 2026-08-17 when FlightStream 26.123 was
    registered with its edition SRC-751. That edition documents
    `SET_OUTLET_TRAILING_EDGES`, a rename of `SET_OUTFLOW_TRAILING_EDGES`
    made in place, and the database does not carry it. So a registered
    edition documents a command the database lacks, which is the exact
    state this non-requirement's reversal was written about: a caller
    meets a refusal for a command their own manual documents.

    The distinction that matters is between an EXCLUSION and a DEBT. No
    family is excluded by decision any more, and that is what the
    reversal settled. What exists now is one command owed an entry, from
    an edition registered nine days after the sweep closed. The
    difference is worth a sentence because "excludes nothing" reads as a
    standing promise and the sweep was a dated measurement.

    The sentence this lane believes it should have, offered rather than
    applied:

    > Every command a registered manual edition documents enters the
    > database, chapter by chapter, and no family is excluded by
    > decision. A newly registered edition may document a command not yet
    > entered; that is a dated debt in the evidence queue and never an
    > exclusion, and the emitter refuses such a command rather than
    > guessing at it.

    Why it is not taken here: the change alters what the non-requirement
    PROMISES rather than correcting a fact inside it, and the heading
    carries a dated parenthesis that would have to move with it. That is
    hers. Until she rules, the debt is listed in the evidence queue on
    the roadmap page, where a reader looking for what is owed will find
    it.

    The wrapper chapter also cost the emitter one new capability, which
    is the kind of thing an excluded family hides: a keyword block whose
    leading argument sits on the command's own line. That is
    `on_command_line`, added with the chapter, and
    `WRAPPER_EDIT_LOCAL_CONTROL` is still the only command in the
    database that needs it.

    The 2026-08-06 narrowing, kept for the record: the identifier is
    kept rather than deleted because
    identifiers here are never reused. As written until 2026-08-06 this
    also excluded the CAD and CCS families and said individual commands
    would enter only when a workflow needed one. The CAD and CAD Create
    chapters then entered WHOLESALE, read chapter by chapter from all
    four registered manual editions rather than pulled in one at a time
    (the count is the database's own fact and its home is the CHANGELOG
    entry, not this sentence), so the sentence had become false in both halves: the
    families are in, and they did not arrive the way this said they
    would.

    The reason for the change is worth recording, since a non-requirement
    is a scope decision and not an oversight. The database's own coverage
    measurement showed the manuals describing 386 commands against 162
    recorded, and the author's decision of 2026-08-06 was that everything
    the manual documents enters, chapter by chapter, rather than on
    demand. Entering a family whole is also what surfaced the
    parameter-table-versus-sample defect class, which reading one command
    at a time would not have shown.

    The page range this used to cite (SRC-003 pp.286-317) rested on a
    scripting-reference span that was itself wrong by five pages at each
    end; the corrected span is recorded in `commands/_meta.yaml`.

!!! nonrequirement "NREQ-06 No GPL or AGPL dependencies"
    Not as runtime dependencies, not as extras, not vendored. GPL
    tools are reachable only as user-run external executables through
    file exchange (NFR-02; RPT-008 records the per-candidate
    evidence).

## Boundary notes

- The FSI structural solver was out of scope at v0.1 (seam only) and
  entered in-package at M6 as the optional `[fsi]` extra; the
  requirement history (FR-23, FR-23a) records the amendment rather
  than rewriting it.
- HPC execution remains deferred (FR-15): the executor interface must
  allow it without changes to the campaign model, but no cluster
  submission ships today.
