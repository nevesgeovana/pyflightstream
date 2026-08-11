# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

## [0.7.0] - 2026-08-10

**Eight builds, and every command every one of them documents.** A
FlightStream build is registered, 26.122, and every command any of the
eight registered editions documents now has an entry: `pyfs-manual
sweep` reports zero absent, which it has never done for more than the
newest four builds before.

READ THAT CLAIM AT THE LEVEL IT IS MEASURED AT, because the first
version of this paragraph did not. Zero absent is a statement about
ENTRY NAMES. Ten readings across four commands are deliberately
withheld, so `IMPORT_CAD` and `CAD_CREATE_IMPORT_CURVE_CCS` cannot be
emitted on three builds and `NEW_OFF_BODY_STREAMTUBE` and
`SET_SCENE_CONTOUR` cannot on two, even though those manuals document
them: each of those editions writes the command in a LAYOUT a version
row cannot express, and a row that ignored the difference would emit
the newer shape under the older edition's citation. The entries say so and
`PLN-20260810-1200` holds the schema decision. The sweep now reports
that second measure beside the first, so the gap is named by the tool
rather than by this sentence alone.

### API surface delta

New public names: `pyflightstream.utils.stale_citations`,
`pyflightstream.utils.StaleCitation`,
`pyflightstream.utils.unreachable_commands`,
`pyflightstream.utils.UnreachableCommand`, the three protocols
`pyflightstream.utils.RegistryLike`, `CommandEntryLike` and
`VersionRowLike`, `pyflightstream.utils.manual.citation_reach`, the
`pyflightstream.utils.manual.Reachability`, the `pyfs-manual
citations` subcommand, seven keyword arguments on
`pyflightstream.script.helpers.solver_settings`, one (`sonic_velocity`)
on `pyflightstream.script.helpers.atmosphere`, and the `source` field on
`pyflightstream.utils.Edition` with the matching `source:` key in the
edition manifest, which is what lets a citation be checked against the
document it names.

Behaviour changes a caller can see. `atmosphere` takes `sonic_velocity`
and reads its script's version to decide which five fluid properties
FLUID_PROPERTIES wants, so it serves the three pre-26.100 builds it had
stopped serving. Its `altitude_units` defaults to None instead of
`"METERS"`, so an omission can be told from an explicit pass: nothing
changes on the seven builds that take a units token, which still emit
METERS when nothing is given, but 25.000 takes no token and reads the
bare AIR_ALTITUDE value in FEET (SRC-749 p.286), so there the helper
REQUIRES `altitude_units='FEET'` and refuses silence. The same call is
metres on the other seven, a factor of 3.28, which is the one silence
worth refusing. `initialize_solver` refuses at entry on 25.000 rather
than dying inside the binder on a keyword the caller never typed: that
edition's grammar takes ten arguments and this helper's parameters do
not map onto it. The refusal for a command the refusal for a command
with no evidence lists builds by reachability and marks inherited ones,
so it no longer hides the newest build; and `pyfs-manual sweep` reports
a second finding, and `--fail-if-absent` gates on the row-level measure
alone: a name with no entry is unreachable too, so one term covers both
and the other could not have been falsified by any test.

Incompatible changes: none for a released signature. Deprecations:
none.

### Added

- **FlightStream 26.122 is registered**, vendor build 8092026, the day
  after it was issued. It is the second hotfix of the 26.12 release and
  says so from evidence rather than from its index: the vendor sells it
  as 26.12, its executable is named for 26.12, its solver prints 26.1
  like the other two, and the three build numbers are one release six
  weeks apart. Its manual documents the largest scripting surface of the
  eight editions, 372 commands. Read its `operational` level with its
  evidence: it reaches that level entirely on records inherited from
  26.120, because no command has been probed on this build.
- **Ten commands the 26.122 edition is the first to document**, among
  them `ROTATE_SURFACE`, `SOLVER_TIME_AVERAGING`,
  `SET_NEW_UNSTEADY_SOLVER_ACTION`, `EXPORT_BL_VELOCITY_PROFILE` and
  `SET_ACTUATOR_WAKE_TYPE`. Two of the ten stand where a command this
  edition stops printing stood, and neither pair is a plain rename:
  `ROTATE_SURFACE` takes six arguments, five on the command line and the
  surface indices on the next, where `SURFACE_ROTATE` is a keyword block
  of eight, and the two options
  `SPLIT_VERTICES` and `ADAPTIVE_MESH` have no equivalent in the newer
  form. Both superseded commands carry a `removed` row for 26.122 naming
  its successor.
- **Sixteen commands only the pre-26.100 editions document**, which
  closes the last gap in coverage. Three are version stories rather than
  disappearances: `SET_SOLVER_MODEL` becomes an argument of
  `INITIALIZE_SOLVER` in the edition that drops it,
  `SOLVER_UNINITIALIZE` and `REMOVE_INITIALIZATION` are exactly
  complementary across the eight editions, and the `PHYSICS` block
  becomes the two standalone autodetection commands at 26.000. That last
  one explains a gap this repository had already measured and misread:
  the two 25 builds are not missing trailing-edge autodetection, they
  spell it as one block.
- **Nineteen per-version argument grammars** for the three pre-26.100
  editions, read page against page. `FLUID_PROPERTIES` takes a sonic
  velocity and no specific heat ratio on all three; `INITIALIZE_SOLVER`
  has a different argument list on each of them.
- **`pyfs-manual citations`**, which re-reads every version row's cited
  page against the edition it names and exits non-zero when one does not
  hold. It exists because ten citations were found pointing at a
  document that had moved underneath them, each at a real page of a real
  manual, and nothing re-checked a citation once written.
- **Seven solver-setup flags** on `solver_settings`, for the
  settings-family commands only the older editions document:
  `solver_model`, `valarezo_criterion`, `crossflow_separation_cp`,
  `wake_relaxation`, `wake_streamwise_agglomeration`,
  `adverse_gradient_boundary_layer` and `vortex_ring_normalization`.

### Changed

- **A per-version argument override now states only its difference.**
  Unstated fields are filled from the base argument of the same name, so
  changing one field no longer means restating every other field of
  every argument. That restating is how a second field changes by
  accident: writing this release's overrides lost a list separator and
  an entity citation, which is the same defect this repository already
  had a test for. Writing `cites: null` still clears an inherited value,
  since inheritance reads the raw file where an unstated field and one
  stated at its default are distinguishable.
- **A `removed` row's citation no longer counts as manual coverage.** An
  absence is read across a whole chapter, so one such note marked every
  page of an edition as cited and the published coverage section went
  from a page-by-page gap listing to "every page is cited".
- The steady-polar example's version-awareness section now shows the two
  refusals that differ, a command a build does not carry and a command
  it carries with a different argument list, replacing a claim about
  26.0 having no recorded evidence that stopped being true.

### Fixed

- Ten version rows citing pages of the 25.000 manual were five or six
  pages off, from the conversion of that edition being corrected after
  the rows were written.
- **Three builds could not emit a command their own manuals document.**
  `EXPORT_ALL_SURFACE_STREAMLINES` had no row for 25.000, 25.100 or
  26.000 while its two family siblings on the same manual pages did, and
  the coverage sweep reported zero absent throughout, because it
  compares entry names and an entry missing one edition's row reads as
  covered.
- **26.122 would have emitted two commands the build before it has a
  negative record for.** Inheritance runs from the base release rather
  than from the sibling hotfix, so a `removed`-on-a-run record and a
  `broken` record on 26.121 were both overturned by 26.120's
  `documented` one.
- The README's opening example promised a refusal it no longer made and
  printed nothing, and CI could not see it: an example whose only claim
  is that something is refused goes green the day the refusal stops
  firing. It asserts now, and CONTRIBUTING states the limit.
- A note on `SET_SOLVER_MODEL` said the successor takes the same four
  tokens. It takes six, of which one is shared.
- **`atmosphere` serves the three pre-26.100 builds again.** Those
  editions take a sonic velocity and no specific heat ratio on
  `FLUID_PROPERTIES`, so entering their grammar closed both doors on
  them at once: passing the five newer properties was refused by the
  binder for a keyword the edition does not have, and omitting one was
  refused by the helper, which quoted a page of a different edition.
  The helper reads its script's version now and takes a new
  `sonic_velocity` keyword. The 25 series is the series registered so
  published work can be reproduced, so the curated path has to serve it.

### What the review changed

Reviewer passes over four rounds read this work, and the entries above
are what survived them. The count is deliberately not given: it was
written three times in this release at two different numbers and no
scope, and an unanchored count is worse than none. Four findings are
worth a reader's attention because they were wrong in ways nothing
mechanical could see.

The completeness claim was measured by a tool that cannot measure it.
`pyfs-manual sweep` compares entry NAMES, so an entry carrying no row
for one edition read as covered, and it reported zero absent while
three builds could not emit a command their own manuals document. The
sweep now reports both halves, and the completeness gate reads the
row-level one.

Four `removed` rows said the 26.122 edition does not print a command
while that edition's Script Index names it. The body does not, the
index does, and the body is what a script is written from, so the
conclusion stands and the citation did not. Each row states both
sources now. Measuring it inverted something worth knowing: the three
commands still emitted for that build are absent from the body AND the
index, while the four refused are absent from the body and present in
the index.

And two curated helpers stopped serving three builds the moment their
grammar was entered. `atmosphere` is fixed on both halves of its
signature; the second half was found only because a reviewer
parametrised over the builds instead of testing the one that changed.

The fourth is this release's own tag, and it is recorded here because
the fix ships inside the artifact. A tier 1 test imported the `[manual]`
extra with no guard, so the suite failed on every CI leg and the v0.7.0
tag was pushed anyway, fifteen seconds after the branch, while seven of
eight jobs were still running. Nothing was published: `release.yml`
binds publishing to its gates and they held. Release process only; no
runtime change. The account first written into the fixing commit was
wrong, and the correction is the useful part: the defect was NOT visible
only in a wheel environment, it was red in the ordinary matrix too, and
the real failure was a tag that did not wait for an answer CI was three
minutes from giving. Both causes now carry a guard rather than a
sentence, `tests/test_extras_isolation.py` for the import and
`.claude/hooks/ci_release_gate.py` for the tag
(INC-20260810-2140-shared).

### Known gaps

- **Three commands the 26.122 edition stops printing are still
  emitted for it.** That build inherits from its base release 26.120,
  and `CREATE_BULK_SEPARATION`, `SURFACE_DELETE` and `SURFACE_CLEARALL`
  have no record on the builds inheritance reaches past. Not that they
  have no successor and no measurement, which an earlier draft said and
  this repository's own files refute three times over: `DELETE_SURFACES`
  is recorded as replacing two of them and RPT-015 measured 26.121
  rejecting the third. The four that ARE refused
  are refused on stronger evidence, and the split is not a rule anyone
  chose: it is what the available evidence happens to look like. One
  probe run of seven names settles it (`PLN-20260810-1600`, and the
  licensed-evidence queue in `docs/srs/roadmap.md`).
- **Nothing has been probed on 26.122 at all.** It derives
  `operational` entirely on inherited records; the README row says so.
  The same is true of 25.000, 25.100 and 26.000, so four of the eight
  registered builds rest on manual evidence or on inheritance and no
  COMMAND has been measured on any of the four. Each has met a solver:
  an identity probe read its banner, which is where its build number
  comes from and is all it claims.
- **`initialize_solver` does not serve the three pre-26.100 builds.**
  Their INITIALIZE_SOLVER takes a different argument set, and this
  release fixes only `atmosphere`, the other helper the same gap hit.
  The refusal names the page and points at `script.emit`.

## [0.6.0] - 2026-08-09

**Seven builds, every one of them identified.** Three more FlightStream
builds are registered and every registered build now carries the vendor
build number its solver prints, read from a committed report. The three
that joined are the ones the author's published work was run on, so a
reader reproducing any of it has an identifier that resolves to a number
they can check against their own install.

Getting there meant finding out why three installs had looked broken.
They were not: the package was calling them with a command line they do
not accept, and a FlightStream build given a script argument it does not
recognise starts, checks out its licence, receives no script, and waits.
That reads as a hang with a clean licence and an empty log, which is why
two wrong diagnoses were written down before the right one. The fix is
one dash instead of two, measured across all seven builds.

The rest of the release follows from having seven readable builds. A
generated page maps what a solver prints onto the identifier to pass,
because a release name does not identify a build: the vendor ships two
builds as "26.1" and two more as "26.12". A new `pyfs-manual surface`
reports what each build documents and what changed between them, and
RPT-024 is its first output: the scripting surface grew from 272
commands to 364, unevenly, with 75 arriving in a single step.

### API surface delta

New public names: `pyflightstream.run.SCRIPT_ARGUMENT`,
`pyflightstream.run.describe_invocation`,
`pyflightstream.run.ExecutionResult.diagnosis`,
`pyflightstream.versions.FsVersion.prints`,
`pyflightstream.reference.markdown_build_table`,
`pyflightstream.utils.edition_surfaces`,
`pyflightstream.utils.surface_changes`,
`pyflightstream.utils.SurfaceChange`, and the `pyfs-manual surface`
subcommand. Incompatible changes: none for callers; the solver command
line changes, see below. Deprecations: none.

### Added

* **Three more FlightStream builds are registered, and every registered
  build now carries its vendor build number.** 25.000 (build 12162024,
  December 2024), 25.100 (build 5062025, May 2025) and 26.000 (build
  10202025, October 2025) join the registry at `registered` level. They
  are there for reproducibility rather than coverage: published work was
  run on the 25 series, and a reader of it needs the identifier to exist
  and to resolve to a build number they can check against their own
  install.

  Read their POSITION rather than assuming it. They precede every build
  the registry had, so they were inserted at the FRONT. The rule that
  versions are only added and never dropped is about dropping, not about
  the end of the list: the list is ordered by RELEASE order, so a build
  obtained later can belong earlier in it.

  The canonical scheme generalises from `26.XXX` to `YY.XXX` in the same
  change, which is what it always meant; the major was written as a
  literal while 26 was the only one registered. No identifier was
  reassigned. SRS FR-02a and BRF-19 carry the amendment.

* **`pyfs-manual surface` reports what each build documents and what
  changed between builds.** The sibling of `sweep`, off the same edition
  manifest: `sweep` asks what the database is missing, `surface` asks
  what each build documents so two builds can be compared. RPT-024 is
  its first output and is regenerated rather than maintained.

  The measurement, since it is the answer to "what changed between the
  builds I ran my research on": the scripting surface grew from 272
  commands to 364 across the seven builds, and 75 of that arrived in one
  step, 26.000 to 26.100, essentially the whole CAD and cross-section
  family at once. The step to watch is 26.100 to 26.101, which gained 35
  and lost 16 between two builds the vendor ships under the SAME release
  name.

  Lost means the newer manual stops printing the command, never that the
  solver stopped accepting it; those are different facts and only a
  probe separates them. The report says so rather than letting a reader
  infer a removal, and it lists names rather than only counts, because
  the counts cannot see that the four `CREATE_NEW_MOTION_*` commands of
  25.000 are one renamed `CREATE_NEW_MOTION` in 25.100 rather than four
  removals and one addition.

  The reading is cross-checked against the command database: for all
  four builds the database records, every command the manual documents
  has an entry, which is what makes the page ranges trustworthy.

* **A generated "Which build do I have" page.** The vendor ships two
  builds as "26.1" and two more as "26.12", so a paper recording
  "FlightStream 26.1" has not said which solver produced its numbers.
  The page maps the release name and build number a solver prints onto
  the canonical identifier to pass, and it is generated from the
  registry at docs build time so it cannot drift from it. It shows the
  two fields separately rather than the banner line, because that line
  is not byte-identical across builds: the 25.0 solver writes a NUL byte
  into it where the newer builds write a space.

  The registry gained a field for this and the reason is the sharper
  half of the release. `FsVersion.prints` records the release name the
  solver STATES ABOUT ITSELF, which is not the name the vendor sells the
  build under and may not be derived from it: 26.120 and 26.121 are sold
  as "26.12" and both binaries print "26.1". A first draft of the page
  keyed the column on the sold name, which would have sent the owner of
  either build to a row naming a different solver. It is recorded from a
  committed report's `solver_identity`, like the build number, and a
  tier 1 guard cross-checks it against the banners in those reports.

* **`pyfs-qa probe --identity-only`.** Judges no command: it runs the
  baseline, captures the solver's identity banner, and writes the report
  pair. That is how a newly registered build gets its build number into
  a committed report, which is the only place the registry accepts one
  from. Registering the three new builds is what it was built for, and
  it reads a build in about a second.

* **The probe baseline can run on a build that records no command.**
  Such a build has no grammar of its own for the three instruments, so
  the baseline borrows it from the newest build that records all three
  and reports the build unusable if the borrowed grammar does not work
  there. Without this the three builds registered in this release could
  not be probed at all, since a baseline needed a row and a row needed a
  probe. What the report does not yet say is that the borrowing
  happened, which is registered as PLN-20260809-2410.

### Fixed

* **The solver command line was version dependent and hardcoded as if it
  were not, which made three builds look broken.** The executor passed
  the script argument with two dashes, the spelling SRC-003 documents.
  The 25 series does not recognise it: the 25.0 manual documents the
  one-dash form. `pyflightstream.run.SCRIPT_ARGUMENT` is now the
  one-dash form, which RPT-023 measured working on all seven registered
  builds.

  The failure mode is the part worth publishing. A build given the
  spelling it does not know does not refuse it. It starts, prints its
  banner, checks out its licence successfully, receives no script, and
  waits for a user. Under `-hidden` with the standard streams redirected
  there is no console for it to report on, so the Fortran runtime raises
  `severe (30)` on `CONOUT$` and opens a modal dialog that no timeout can
  answer. What the harness sees is a clean licence checkout, an empty
  log, and a wall-clock time equal to its own timeout. Two diagnoses
  were written down before the right one, one of them naming a licence
  seat that was never held.

* **Every report derives its executor line instead of restating it.**
  That sentence sat as six literals across the three report writers, one
  machine-readable and one rendered each, and nothing would have noticed
  them disagreeing with the code: changing the argument would have left
  forty reports describing an invocation the package no longer made. It
  comes from `describe_invocation()` now, and a tier 1 guard compares
  the flags in the sentence with the flags the executor passes, as whole
  tokens. The first version of that guard asked whether each flag
  appeared in the sentence and a wrong sentence satisfied it, because
  `-script` is a substring of `--script`.

* **A failed solver run now says what the solver said.** Four sites
  composed `log_text or stderr or return code` by hand and all four
  omitted the same field: standard output, which the executor captures
  on every run and which nothing in the package read. A fifth, the
  timeout branch, discarded even those and recorded only "timed out and
  was killed".

  That is what made this release's own defect cost a day. Everything the
  harness reads is written by the solver AFTER it accepts a script, so
  every failure BEFORE that point looks identical; the baseline refusal
  told the operator the environment was unusable and offered the licence
  checkout as one of three candidate causes, while holding unprinted the
  line saying the checkout had succeeded. About a dozen licensed solver
  launches went into the licence hypothesis.

  `ExecutionResult.diagnosis()` is now the single composer, reporting
  the outcome and every non-empty channel, and the refusal quotes it
  instead of naming suspects it cannot rank. A tier 1 AST guard refuses
  any module outside the composer's home that reads two or more captured
  channels in one expression, which guards the shape rather than the
  five sites (INC-20260809-2230).

* **A stale editable install no longer stamps the wrong version into
  evidence.** Every compat, drift and physics report records
  `package_version` from the installed metadata, which for an editable
  install is whatever was recorded the last time the project was
  installed rather than what the source says today. That gap put
  `package_version: 0.5.0` into seven identity reports produced by the
  0.6.0 tree, one of them for a build the published 0.5.0 could not have
  driven at all. The reports were not rewritten, the writer refusing to
  overwrite evidence and rightly so; a tier 1 guard now fails when the
  installed metadata disagrees with the source tree, before a licensed
  run is spent, and names the one-line remedy.

* **The compatibility matrix and the offline `help()` page define their own
  cells.** Both carried a definition of the empty cell and of the
  inheritance mark and left the four status words to be inferred from
  their names. A legend now names all five, what each rests on, and what
  `Script.emit` does with it, which is the half no status name carries:
  three of the five are REFUSALS, each with a different exception class.
  Both layers render one tuple, so they cannot come to disagree, and the
  per-chapter reference pages stop restating the definitions and link to
  it instead.

  The reasoning worth keeping is about the guard rather than the text.
  The first version of it let eight of nine mutants through: every check
  was a search for a fragment ANYWHERE on the page, so the two columns
  could be swapped between `documented` and `verified`, the named
  exception class could be the wrong one, and the two non-refusing rows
  were proven by an `except Exception` that read an argument refusal as
  a successful emission. An emitter that could emit nothing at all left
  the file green. The guards now locate a row and assert inside it, tie
  each cell's opening clause to whether the model refuses that status
  without a committed report, and prove emission by emitting. Eleven of
  thirteen mutants die; the two that live are inversions of explanatory
  prose and are registered rather than papered over.

## [0.5.0] - 2026-08-09

**The command database is complete.** Every command that any of the four
registered FlightStream manual editions documents is in it, 388 entries,
and every entry carries a version row for each edition that documents the
command. Before this release the database held 147 commands and answered
for a curated subset of the solver; it answers for the whole scripting
surface now, and all four registered builds derive the `operational`
support level, which is checked by building a minimal end-to-end workflow
for each of them.

The rest of the release follows from that. Reading the command pages of
four editions found the ways a manual contradicts itself, and each
one is recorded on the entry it affects rather than smoothed over: a
sample copied from the neighbouring command, a heading and a table
disagreeing about an argument count, one command documented on two pages
where only one says anything, and a value set that gained a token between
builds. Where a page could not settle a question, the solver was asked on
a licensed machine and the answer is a committed report.

### API surface delta

* **Eighteen commands verified through the saved-state instrument, and
  four reverted to unobservable WITH their measurement.** 26.121 goes
  from 66 verified to 84: the full run of the same day recorded 66
  (`CMP-26121_2026-08-08_full`) and the saved-state run added 18
  (`CMP-26121_2026-08-08_savedstate2`). New public assertion `qa.fsm_changed`
  (`RPT-022`), for the
  commands whose effect is real and has no distinctive value to search
  for: a toggle writes T or F and a binding writes an index of 1, which
  match everywhere, so what it asserts is that the saved state MOVED.

  The four that came back broken were triaged rather than recorded, and
  none of them is broken: an actuator appears to be enabled at creation,
  the constant free-stream form is the documented solver default, every
  boundary appears pre-selected for analysis, and a clean synthetic wing
  has no wake termination nodes to detect. Each keeps an unobservable
  record whose note is now a measurement instead of a guess.

  BOTH SAVED-STATE ASSERTIONS COMPARED SETS OF LINES AND BOTH WERE WRONG
  FOR IT. The simulation file is positional and most of its lines are
  short tokens, so a line that genuinely changed from `0` to `1`
  contributes nothing to a set difference. Two commands that had really
  written to the state were recorded broken under that reading. They
  read a positional diff now.

* **Four chapter questions measured, and one was a command the emitter
  was building and the solver rejects** (`RPT-021`).

  `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` IS REMOVED ON 26.121. It is
  documented by the 26.101 and 26.120 editions and by neither
  neighbour; with no 26.121 row the registry handed it 26.120's
  evidence by hotfix inheritance, so a caller on that build got a
  validated script the solver refuses with an unrecognised command. The
  row is `removed` now, promoted from the run rather than read off the
  hotfix edition's silence, and a caller on 26.121 gets a refusal naming
  the build instead of a line the solver rejects. Second measured
  counter-example to that inheritance after `AIR_ALTITUDE`, and the
  first where the inherited evidence was optimistic.

  That row also needed a citation kind the database did not have.
  `ProbeOutcome` has no `removed` member, so the harness records a build
  that lacks a command as `broken`, which claims something else, and the
  guard that checks a status against its own compat yaml therefore had
  nothing to open. `VersionStatus` gains `probe_ref`, a committed
  narrative report of a run, admissible for `removed` and REFUSED for
  every other status: `verified` and `broken` stay checkable against
  harness output, because a guard whose population quietly shrinks
  reports green either way.
  `PLN-20260809-0300-the-harness-has-no-removed-outcome` carries the
  harness change that retires the field.

  `CREATE_NEW_BASE_REGION` GAINS `CUSTOM`: the solver accepts either
  that or `USER` there, while `SET_BASE_REGION_CP` accepts `CUSTOM`
  alone. The two pages disagreed and both are right about their own
  command; the manual is merely incomplete about the creator.

  DELETING A COORDINATE SYSTEM RENUMBERS the ones above it, so a frame
  index recorded before a delete means something else after it. Nothing
  in the library emits that delete and the entry states the safe
  pattern; what to do in `EntityRegistry` is a design decision left
  registered (`PLN-20260808-2100`).

  Two judgements this sweep took on reasoning were confirmed by
  measurement: `SURFACE_ROTATE` takes the sample's `SURFACES` and
  refuses the table's `SURFACE`, and `CAD_CREATE_MIRROR_CURVE`, the
  sample's spelling, is not a command.

* **26.100 IS OPERATIONAL, and it was the DATABASE holding it back, not
  the solver.** A per-edition sweep found 122 pairs of (command, manual
  edition) that an edition documents and this database had no version
  row for, so the emitter refused a command the caller's own manual
  prints and nothing distinguished that from the command not existing.
  Forty of them were on the February build, which is why its minimal
  end-to-end workflow could not be built. All four registered builds now
  derive `operational`.

  WHAT 122 COUNTS, since a reader comparing it against the diff will
  otherwise reach for the wrong number: pairs, not commands. One command
  documented by three editions and carrying a row for none of them is
  three pairs, and the backfill wrote 124 version rows, the two over
  being the per-version grammars written the same day. The count of
  distinct COMMANDS touched is smaller than 122 and is not the figure
  this stanza is about.

  EVERY PAIR WAS READ ON ITS PAGE, and four of the 122 turned out to
  differ, each now carrying its own per-version grammar rather than a
  copied row:

  - `NEW_SURFACE_SECTION_DISTRIBUTION` on 26.100 and 26.101 takes six
    keywords, not seven. The optional `INCLUDE_SYMMETRY` reached this
    database from a PROBE of a working 26.120 script and is first
    documented in 26.121, so a copied row would have offered older
    builds a keyword no evidence places in them.
  - `SET_TRAILING_EDGE_TYPE` on 26.100 closes its type set at three
    tokens; `VORTEX_SHEDDING` first appears in the May edition.
  - `SOLVER_PROXIMAL_BOUNDARIES` on 26.121 documents a second call form
    the older editions do not print, a count of -1 selecting every
    boundary and taking no index lines, so that row declares the
    sentinel and makes the list optional.
  - `NEW_CCS_WING_CONTROL_SURFACE` on 26.100 and 26.101 takes eight
    arguments and not ten: `SPACE` and `AXIS` arrive with 26.120, so
    spanwise placement is parametric only on the older builds.

* **The saved simulation is an instrument, and forty commands stop being
  unobservable** (`RPT-020`, `RPT-022`). The compat reports called their effects
  "stored in binary form"; the .fsm is sectioned TEXT and carries them.
  `ProbeSpec.save_state` brackets the target with SAVEAS and the new
  `qa.fsm_gained` asserts a distinctive value appears on a line the
  target added or changed. Eighteen commands verified on 26.121 with it across the two saved-state
  runs, eight of them through `fsm_gained`,
  among them the actuator axis, radius, rpm and swirl, and the frame
  origin and axes.

  It reads the DIFF rather than the whole file, because the first
  version did the latter and marked a working command BROKEN: the token
  it searched for also occurred somewhere innocent in the before-state.

  THE SOLVER NORMALISES A COORDINATE-SYSTEM AXIS WHATEVER THE FLAG SAYS.
  Found because the instrument reported `SET_COORDINATE_SYSTEM_AXIS`
  broken and the diff disagreed: a direction passed with the normalise
  flag FALSE is stored divided by its magnitude, to all seventeen
  digits. A direction cannot carry a scale.

* **MEASURED: a keyword block is read by NAME, not by position**
  (`RPT-019`, closing `PLN-20260808-2200`). Every `keyword_block` entry
  in the database fixes an order and nothing had ever asked whether the
  solver reads it. On the 26.121 build, the same five `FLUID_PROPERTIES`
  keyword lines in documented, transposed and fully REVERSED order leave
  the identical solver state, which a positional reader could not do.

  So the order an entry fixes is cosmetic, the
  `STABILITY_TOOLBOX_NEW_COEFFICIENT` table-versus-sample disagreement
  has no consequence, and the database-wide audit that a positional
  answer would have forced is not owed. The residual is in the report:
  one command, one build, and a parser being uniform over its own
  grammar is an inference.

  A GRAMMAR FACT FELL OUT OF BREAKING IT. A keyword block is terminated
  by a BLANK LINE; without one the solver reads the next command as a
  keyword line, and the error names that following command rather than
  the block. The emitter has always written the separator, which is why
  no script this library builds had ever hit it and why nothing asserted
  it. A tier-1 guard does now, proven by removing the separator.

* **The emitter has ONE way to know what an index cites, where it had
  two** (`PLN-20260807-1410`, the author's decision of 2026-08-08). An
  argument declares `cites` on its own entry, and the two global maps
  from argument NAME to entity kind are gone.

  They were already the fallback rather than the rule, and a fallback
  quietly covering 101 arguments is not a fallback. A name is a guess
  about an argument; a declaration is the argument saying so, which is
  why the maps could not carry `index`, a spelling that means a surface
  in one chapter and a section in three others. All 101 now declare it,
  including three that declare it on a per-version grammar rather than
  the default one.

  The visible gain is in the database rather than in the code: reading
  an entry now tells you whether its index is resolved and range
  checked, where before you had to know the map. The tier-1 closure
  guard lost one of its three ways to be satisfied, found the three
  per-version sites the bulk pass had missed, and was re-proven by
  mutation.

* **What the five reviewer passes changed, because two of it is
  user-visible.** `read_editions` is renamed `read_edition_manifest`
  before anyone depends on it, `Edition` is keyword-only (its two page
  ranges are the same type, so positionally they are interchangeable and
  a swap reads the Script Index as the scripting reference with nothing
  able to detect it), `sweep_editions` takes `recorded` by keyword and a
  `reader` for its one pdf dependency, and the manifest refuses an
  unknown key, a missing manual and a bad row before any manual is
  opened.

  THE SNAPSHOT NOW REPORTS THREE MORE SOLVER DEFAULTS.
  `rotor_induced_velocity_blending`, `wake_numerical_relaxation` and
  `jet_wake_decay_normalized_length` had their manual defaults written in
  prose; they are `default` and `default_ref` fields now, so a caller who
  leaves them unset gets the documented value and its page in
  `SolverSetup` rather than an `unknown`. A default the database records
  is a default the snapshot reports.

  `ArgSpec.on_command_line` gained a third refusal: an OPTIONAL argument
  cannot sit on the command line, where arguments are positional and
  unnamed, because omitting it would shift the ones after it into its
  place and the solver would read the line without complaint. Both
  current users are required, so the gap was latent, and it is the same
  failure class the field was added to prevent.

**INCOMPATIBLE CHANGES, first because they are what an upgrade can
break.** Five, all of them from earlier in this development cycle and
each explained in its own stanza below.

* `resolve("26.1")` RAISES `AmbiguousVersionAliasError` where it
  returned 26.100. The vendor shipped two releases under that one name,
  so the alias no longer identifies a build; pass a canonical
  identifier, `"26.100"` or `"26.101"`, and the refusal names both.
* `FsVersion(...)` refuses construction at a hotfix index, one whose
  last digit is not zero, unless the call states `inherits_base`.
  Whether a build carries its base release's command evidence is a fact
  about two vendor builds, and defaulting it let a hand-built version
  inherit a whole command set by omission. Registered builds are
  unaffected: `resolve` fills the field from the registry.
* `SWEEPER_SET_VELOCITY_SWEEP`'s file path moved from the second
  positional argument to the third. Pass it as `filename=`.
* `solver_settings(viscous_excluded=[])` now emits
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES` rather than a `SET` with a count
  of zero and an empty payload line, which the solver misread.
* A database entry with an inline list argument may no longer declare a
  separator other than `space`, and an `on_command_line` argument may no
  longer be optional or be preceded by a keyword line; the load refuses
  each. Both reach an entry author rather than a caller, and no shipped
  entry breaks.
* `Script.emit` refuses a payload count with no payload under it, on any
  command whose list argument is optional, unless the count is the
  documented all-entities `-1`. One grammar in the database allowed the
  refused shape (`SOLVER_PROXIMAL_BOUNDARIES` on 26.121) and it rendered
  a count line the solver would have followed by reading the NEXT
  commands as its data.

**Deprecations: none.**

**ONE THING THE v0.4.0 NOTES PROMISED FOR THIS RELEASE AND THIS RELEASE
DOES NOT DO.** Those notes announced the dry-run rename, breaking and
with no alias: `plan_matrix` to `dryrun_matrix`, `plan_campaign` to
`dryrun_campaign`, and `pyfs-matrix plan` to `pyfs-matrix dryrun`. It
has not landed. Nothing in the deprecation ledger held it, so no guard
noticed, and it surfaced in this release's own documentation review.

Said plainly rather than quietly carried forward, because an announced
break that does not arrive is a promise a reader planned around. The
three names are unchanged and keep working. The rename moves to the
next minor and is registered as `PLN-20260809-0200` with the ledger
entry it should have had.

**The public surface ADDED, in one place.** A new console script,
`pyfs-manual`, with the subcommands `coverage`, `draft` and `sweep`,
behind a new optional extra `[manual]` (pypdf). A new subpackage,
`pyflightstream.utils`, exporting `Edition`, `SweptCommand`,
`sweep_editions`, `read_edition_manifest`, `Coverage`, `ManualCommand`,
`ManualDraftError`, `TypeRule`, `TYPE_RULES`, `coverage_against`,
`parse_script_index`, `parse_signatures`, `propose_layout`,
`propose_type`, `read_pdf_pages`, `render_chapter`, `render_entry`,
`sample_contradiction` and `write_chapter`.

`helpers.solver_settings` gains TEN keyword parameters
(`kutta_joukowski_lift`, `print_rotor_induced_velocities`,
`adaptive_field_grid_refinement`, `jet_wake_filaments_grid_induction`,
`rotor_induced_velocity_blending`, `wake_numerical_relaxation`,
`jet_wake_decay_normalized_length`, `wake_decay_constant`,
`solver_stabilization`, `disable_ref_velocity`). `ArgSpec` gains the
fields `on_command_line`, `cites`, `all_sentinel` and `fixed_length`.
The database gains two evidence citations: `probe_ref` on an ENTRY, for
a command the solver accepts and no edition documents, and `probe_ref`
on a VERSION ROW, for a measured removal, admissible there for `removed`
alone. `qa` gains `fsm_gained`, `fsm_changed` and
`ProbeSpec.save_state`. `script.solver_setup` gains the four separation
models `AirfoilSeparation`, `AxialVortexSeparation`,
`CylindricalBulkSeparation` and `StratfordBulkSeparation`. The version
registry gains `inherits_base` and the registered version 26.101.

The stanzas below give the reasoning per chapter.

* **The tail entered: 28 commands across 21 sections, and THE SWEEP
  REACHES ZERO.** Every command that any of the four registered manual
  editions documents is now in the database: 388 entries, of which 387
  cite a manual page and one rests on a committed probe report
  (`DELETE_VALAREZO_SEPARATION_BOUNDARIES`, which the solver accepts and
  no edition names). Emittable per version at this release: 345 on
  26.100, 363 on 26.101, 363 on 26.120, 368 on 26.121.

  MEASURED ON 2026-08-08 against the four editions of the maintainer's
  own manifest: `pyfs-manual sweep` reports 0 absent. State it as a
  measurement of that date rather than as a property CI holds, because
  the manifest names licensed manual paths and cannot be committed, so
  no test in this repository can re-run it. What CI does hold is that
  every entry carries exactly one evidence citation. The sweep also now
  takes `--fail-if-absent` for a maintainer who wants the check to fail
  rather than to report.

  **Two more keyword parameters on `helpers.solver_settings`:**
  `solver_stabilization` and `disable_ref_velocity`, the latter on a new
  `bare_request` flag kind for a command that takes no argument at all,
  where False is the ABSENCE of the request rather than a way to ask for
  the opposite.

  Three commands exist in one edition only, which is the clearest
  evidence this sweep produced that the scripting surface is moving in
  both directions: `DISABLE_ACTUATOR` and `EXECUTE_SOLVER_SWEEPER` in
  the February edition alone, `DISABLE_SOLVER_REF_VELOCITY` in the
  26.121 hotfix alone. `EXECUTE_SOLVER_SWEEPER` does in one 21-parameter
  command what the later `SWEEPER_` family splits across ten, so that
  family was redesigned rather than extended.

  `CAD_CREATE_MIRROR_CURVES` HAS TWO SPELLINGS: the heading and the
  Script Index say CURVES and the sample beneath the heading says
  CURVE, in all four editions. The heading is recorded, and the
  reasoning is the reverse of this database's usual preference for
  samples: a sample is the stronger source for an ARGUMENT because the
  vendor ran the line, but a sample with the wrong NAME is a sample of
  nothing. `PLN-20260808-2300` carries the probe.

  Two chapters are worth naming for what they lack. Boundary Layer
  Transition Trips is ONE COMMAND AND IT IS A DELETE: no edition
  documents creating a trip, so a script can remove them and never add
  one. And `SET_PLOT_TYPE` prints `RESIDUALS` twice in its value list in
  every edition, so it takes 23 tokens rather than the 24 rows printed.

* **Coordinate Systems, both streamline families and the Stability and
  Control Toolbox entered: 19 commands, all four chapters complete.**
  Database 341 to 360; emittable per version 280, 307, 340, 345. Nine
  older entries across the frames and streamlines chapters get their
  missing edition rows in the same pass, the streamlines header having
  deferred the whole on-body family to the cases that would exercise it.

  `NORMALIZE_COORDINATE_SYSTEM` takes the index its sample passes,
  against a heading with no placeholder and a table reading N/A: the
  same shape as the February edition's `ENABLE_ACTUATOR` and read the
  same way. It is also the one command in its chapter that accepts frame
  1, every other requiring an index above the reference frame.

  `MIRROR_COORDINATE_SYSTEM` DUPLICATES AND THEN MIRRORS, which the
  manual states in a parameter row rather than in the command's
  description. Reading the name alone suggests the frame is mirrored in
  place, which is a different result for everything already pointing at
  it.

  `STABILITY_TOOLBOX_NEW_COEFFICIENT`'s keyword order follows its two
  printed samples, which agree with each other and not with the
  parameter table above them. That raised a question no chapter had
  asked: every keyword_block in the database fixes an order and nothing
  has tested whether the solver reads order at all
  (`PLN-20260808-2200`). `STABILITY_TOOLBOX_SETTINGS` carries a unit
  trap worth naming: its `UNITS` argument selects per-radian or
  per-degree OUTPUT, while `ANGULAR_RATE_INCREMENT` is an input the
  manual gives in rad/s regardless, so reading one as governing the
  other is a factor of about 57 in every dynamic derivative.

  Two further probes registered: what a deleted coordinate system does
  to the indices above it, which matters here because the builder TRACKS
  frames and would be wrong if the solver renumbers
  (`PLN-20260808-2100`).

* **The Advanced Settings and Inlets and Outlets chapters entered: 15
  commands, both complete.** Database 326 to 341; emittable per version
  253, 280, 321, 326.

  **Eight new keyword parameters on `helpers.solver_settings`:**
  `kutta_joukowski_lift`, `print_rotor_induced_velocities`,
  `adaptive_field_grid_refinement`, `jet_wake_filaments_grid_induction`,
  `rotor_induced_velocity_blending`, `wake_numerical_relaxation`,
  `jet_wake_decay_normalized_length` and `wake_decay_constant`, each with
  a snapshot flag. Not optional extra work: every command of a settings
  family is a snapshot flag, and the tier-1 guard refused the chapter
  until the model matched, so these arrived with the commands instead of
  a release later.

  ADVANCED SETTINGS IS THE CHAPTER WHERE THE EDITIONS DISAGREE ABOUT
  WHAT EXISTS, so its version rows differ per command. Four commands are
  absent from the February edition. `SET_WAKE_DECAY_CONSTANT` exists in
  the 26.121 hotfix alone, so it cites SRC-740 rather than the flagship,
  and its unit of 1/m is DERIVED from the manual's formula and printed
  nowhere: the constant is 19.1 over a characteristic length in metres,
  and a value computed with that length in other units gives a wake
  decaying orders of magnitude too fast or not at all, with nothing in
  the number to reveal which.

  `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` is documented by 26.101 and
  26.120 and dropped by the hotfix that follows, the only such command
  in the sweep. It entered with no 26.121 row and deliberately not a
  `removed` status, since a document going quiet is not a statement
  about a solver, and so it emitted on that build by inheritance from
  its base release. `PLN-20260808-2000` carried the probe that settled
  it, and the probe ran later the same day: the build does not have the
  command. What the row says now, and why a measured removal cites its
  run differently from a read one, is under the chapter-questions entry
  above.

  Inlets and Outlets is asymmetric and the asymmetry is the manual's: an
  inlet takes a custom velocity profile from a file and an outlet cannot,
  in any edition, so a case needing a non-uniform exhaust has no scripted
  way to ask for one. A test asserts the absence, the natural reading of
  a symmetric chapter being that the missing command was overlooked.

* **The Acoustics Toolbox and Base Regions chapters entered: 18
  commands, both complete.** Database 308 to 326; emittable per version
  243, 266, 307, 311.

  `ACOUSTIC_SOURCES` is a SETUP command in a post-processing toolbox,
  because the manual states it must be enabled before solver
  initialization; enabling it afterwards costs a whole unsteady run and
  produces no sources. `CREATE_ACOUSTIC_SECTION` creates and exports in
  one call, which is why its path names a folder: one VTK file per
  observer per time step, a count no edition warns about.

  `SET_BASE_REGION_BENDING_ANGLE` IS DOCUMENTED ON TWO PAGES AND ONLY
  ONE SAYS ANYTHING. The Base Regions chapter prints its heading with
  nothing beneath it; p.284 gives it a table, a range and a sample
  passing a value. Recorded from p.284. An empty heading is read as a
  bare command only where nothing in the manual argues with it, which is
  the rule the Scenes chapter rests on, and here the same manual argues
  with it 33 pages earlier.

  THE USER-SPECIFIED PRESSURE MODEL IS SPELLED TWO WAYS TWO COMMANDS
  APART: `USER` on `CREATE_NEW_BASE_REGION` and `CUSTOM` on
  `SET_BASE_REGION_CP`, in all four editions, both described as the
  model under which the caller's CP applies. Each entry records its own
  page and refuses the other's, because a keyword is emitted literally
  and accepting both would rest on a guess that one of the two pages is
  wrong. `PLN-20260808-1900` carries the probe.

  `SET_BASE_REGION_CP`'s CP is optional and its own page PROVES it, by
  printing a second sample that passes only the model. Its sibling makes
  the same claim about the empirical model in prose and prints no short
  sample, so there the argument stays required: a sample settling an
  arity question rather than contradicting one is rare enough in this
  manual to act on. And `REMESH_BASE_REGION` spells its growth scheme
  numerically, 1 and 2, where the three CCS chapters spell the same two
  schemes as words.

* **The Mesh Wrapper chapter entered: 11 commands, and NREQ-05 now
  excludes nothing.** The author's decision of 2026-08-08. This was the
  last family the scope excluded, so the non-requirement is narrowed to
  an empty set rather than retired, the two narrowings together being
  the record of a scope decision reversing itself. Database 297 to 308;
  emittable per version 225, 248, 289, 293.

  The wrapper builds one clean watertight surface over a set of input
  surfaces, which is what a dirty import needs before a panel method can
  run on it; `WRAPPER_EXECUTE` performs it and everything else
  configures it.

  **New public field: `ArgSpec.on_command_line`.** A keyword_block whose
  LEADING arguments sit on the command's own line, which the emitter
  could not express and which `WRAPPER_EDIT_LOCAL_CONTROL` needs. The
  attempt to spell it with `joins_previous` was refused by the schema,
  correctly: that flag appends to the line the PRECEDING ARGUMENT wrote,
  and in first position there is none. Two new refusals hold the shape,
  a list cannot take it and it must lead. An excluded family hiding a
  missing emitter capability is itself an argument against excluding
  families.

  `num_surfaces` is the FOURTH spelling in the database for a count of
  surfaces, after `surface_count`, `surfaces` and `boundaries`. All four
  are the manual's own on their own pages and the entries go on
  mirroring them; the tier-1 guard over the count-name set is what
  reported this one, before the entry could ship a count nothing
  compares against its list.

* **The Scenes and Scene Settings chapters entered: 18 commands, both
  complete.** Scenes had held ONE command, `CHANGE_SCENE_TO_PLOTS`,
  drafted under a rule that only entered commands with observed
  scripted use; that rule is gone with this sweep and the entry's three
  missing edition rows are backfilled in the same pass. Database 279 to
  297; emittable per version 214, 237, 278, 282, the 26.100 and 26.101
  figures gaining nineteen rather than eighteen because the backfill
  closes one older entry as well.

  Twelve of the thirteen Scenes commands take nothing at all, eleven of
  them printed as a signature heading with no table, no sample and no
  prose. That is the manual stating the command takes nothing, and it is
  read as such here because no edition contradicts it anywhere, which is
  precisely what distinguishes it from the February edition's
  `DISABLE_ACTUATOR`, where the same empty shape sits beside a sample
  passing an index.

  Scene Settings is six keyword blocks over the colour scale, every one
  selecting its target with the same first keyword. `CUT_OFF_MODE`'s
  `OFF` is quoted in the database because YAML 1.1 reads the bare word
  as the boolean false; the schema refuses a non-string enum value, so
  the mistake is loud, and a test now pins the token.
  `SET_SCENE_COLORMAP_CUSTOM_RANGE` HAS NO SAMPLE OF ITS OWN IN ANY
  EDITION: all four print one whose first line names the neighbouring
  command while its keyword lines are this one's, so the sample is not a
  runnable call of either.

* **The CCS Fuselage Mesh and CCS Body of Revolution Mesh chapters
  entered: 20 commands, both chapters complete.** The two remaining
  parametric component definitions beside the wing, each with its own
  grid controls (subdivisions, growth scheme and rate, periodicity, and
  the per-direction reset), axial refinement zones, relaxed
  trailing-edge boundaries, and the export that writes the lofted
  component to a file. Entered from all four editions in one pass, every
  signature identical across them. Database 259 to 279; emittable per
  version 195, 218, 260, 264.

  THE TWO COMPONENTS DO NOT SHARE A SECOND DIRECTION. A fuselage is
  AXIAL and RADIAL, a body of revolution AXIAL and AZIMUTH, and the two
  chapters are otherwise line for line the same commands. That makes a
  value carried across from one to the other the easy mistake and an
  invisible one, since both words are plausible for a body of
  revolution, so the enums are stated per chapter and a test emits each
  one against the other's token.

  `EXPORT_FUSELAGE_CCS_FILE` and `EXPORT_REVOLVE_CCS_FILE` ARE RECORDED
  FROM THEIR HEADING AGAINST TWO SOURCES THAT SAY OTHERWISE. The heading
  prints six placeholders, the parameter table documents four, and the
  sample is the neighbouring create command's with the name swapped.
  The revolve page proves the copy: its sample passes a frame index, an
  axis and two angles that appear nowhere in the export's own signature.
  The wing sibling prints the same six and documents all six, so these
  tables are missing rows rather than describing a shorter command. The
  solver has not been asked, and `PLN-20260808-1730` carries the probe.

* **`pyfs-manual sweep`, and the four-edition worklist becomes a
  committed tool rather than a session's scratch script.** New public
  names in `pyflightstream.utils`: `Edition`, `SweptCommand`,
  `sweep_editions` and `read_edition_manifest`, the last renamed from
  `read_editions` before release. `coverage` answers what ONE
  manual documents and the database does not; no sweep asks that
  question. A command absent from one edition may be recorded from
  another, and a command the database lacks must be entered for every
  edition documenting it at once, so both halves need the union of the
  registered builds and neither is obtainable by reading four
  single-edition reports side by side.

  The editions come from a YAML manifest, `--editions`, which is not
  committed and cannot be: it names the paths of licensed manuals
  (invariant 1). Registering a new build is adding a row to it. `index`
  is optional, because it supplies the section label only and skipping
  an edition for want of one would silently drop a whole build from the
  union; a sweep of NO editions raises instead of reporting the entire
  database absent, which is a configuration error wearing the costume of
  a catastrophic finding. `--by-section` groups by the chapter that
  documents each command, largest first, which is the order the
  remaining work is done in.

* **The CCS Wing Mesh chapter entered: 11 commands, the chapter
  complete.** The parametric wing definition that a mesh is lofted from,
  so everything here configures a definition rather than acting on an
  existing mesh: the per-direction grid (subdivisions, growth scheme and
  rate, periodicity, and the reset), the spanwise refinement zones, the
  morphing control surface and the flap cove, and the export that writes
  a lofted wing to a file instead of into the simulation. Entered from
  all four editions in one pass under the rule below. Database 248 to
  259; per version 118, 166, 238, 242.

  `NEW_CCS_WING_FLAP_COVE` REACHED THE DATABASE ONLY BECAUSE A PAGE WAS
  READ. It carries a signature heading in every edition and no Script
  Index row at all, and the coverage sweep was index-driven, so it
  reported the command as covered and would have gone on doing so
  indefinitely. A false absent is visible the moment someone looks for
  the command; a false covered is invisible by construction. The sweep
  now walks chapter bodies (`PLN-20260808-1200`), and the two
  measurements agreeing on a total of 140 turned out to be a
  coincidence, the index-driven set carrying one false positive and
  missing one command.

  `COVE_TYPE` is an index and not a word, 1 for a blended Bezier cove
  and 2 for a rectangular one, among a family whose every other shape
  argument is a token. `U00` and `U01` are upper- and lower-surface slot
  locations, which is a different pairing from the `U0` and `U1` of the
  two control-surface commands on the same page. And the -1 that deletes
  every refinement zone or control surface is recorded in the notes
  rather than declared as `all_sentinel`: those objects belong to the
  parametric definition and not to the loaded geometry, so the builder
  tracks neither and there is no inventory for a sentinel to be read
  against.

* **The author's decisions of 2026-08-08 on what this sweep owes the
  older builds, and what it does not.** A chapter now enters for every
  registered version in one pass, which is written into the
  chapter-entry guidance in `docs/srs/data-model.md`. The entries still
  documented in an edition they carry no row for, counted in the
  2026-08-07 stanza below, drain as the sweep reaches their chapters
  rather than as a task of their own, so the number falls without a
  separate push. Named rather than left to be discovered, because until
  it reaches zero a caller on 26.100 or 26.101 still meets a refusal for
  a command their own manual describes.

  Applying that rule to this commit closed ten of them at once. The
  whole Aeroelastic Coupling Toolbox carried a 26.120 row alone while
  its 26.101 and 26.121 pages had just been read here, so the rule was
  broken by the commit that introduced it; the rows are written with
  their own pages (SRC-725 pp.374-375, SRC-740 pp.378-379), the
  grammars being identical across the three editions that carry the
  chapter. 26.101 goes 145 to 155.

  Not changed, each deliberately: argument names go on mirroring each
  manual page rather than being harmonised; the count spelled
  `surfaces` stays, being the house spelling on eight commands and not a
  slip in one; the positivity bounds the manual states on the spring
  force stay unenforced; and the emitter's two argument-name maps were
  to stay beside the `cites` declaration rather than be replaced by it.
  THAT LAST DECISION WAS REVERSED THREE DAYS LATER and the maps are
  gone, which is the stanza at the top of this release; the reasoning
  that kept them, recorded here as it was taken, is what the reversal
  had to answer.

  One decision could not be carried out as taken.
  `ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS` was to have its lower bound
  enforced, and reading the page to do it showed the manual does not say
  WHICH value of 1 it forbids: the sentence sits on the count row and
  its gloss describes the reference index, the sample satisfies both
  readings, and the three editions that carry the chapter word it
  identically. Enforcing
  the wrong one would refuse a valid script, so nothing is enforced and
  `PLN-20260808-1100` carries the probe. The entry's note, which had
  stated one reading as fact, now states the ambiguity.

* **Fourth round, and the sweep itself verified clean.** An independent
  seat read all four editions page by page and confirmed the fifteen
  boundary indices: nine state an all-form, six state none, no edition
  disagrees with another. What the round found was around it.

  `Script.resolve_boundary(-1)` had started raising. It is a public
  method resolving a citation with no command attached, so the generic
  all-boundaries form is right there; it was passing through the
  per-kind default that the round before had deleted. The call site now
  states -1 explicitly, and the docstring says why that differs from
  `emit`, where six commands refuse it.

  `SURFACE_ROTATE`'s own all-form was unreachable. Its page states -1 in
  the COUNT row and the index line then has nothing to list, but the
  list was required, so the documented call was refused outright and an
  empty list emitted a stray blank line into the keyword block.

  Three of the nine declared sentinels were pinned only by a literal in
  the test inventory, which is not a guard: editing the declaration and
  the literal together left the suite green with the documented all-form
  refused. All nine are asserted behaviourally now. The
  undeclared-inventory branch was untested the same way, and every
  negative count, not only -1, was bypassing the count-versus-list
  check.

  Two claims corrected: the `all_sentinel` docstrings still taught the
  per-kind default in both homes, and the closure guard's docstring
  called the vocabulary closed when it is a heuristic over name stems,
  which a QA pass demonstrated by getting seventeen invented spellings
  past it. The stems were widened with all seventeen and the claim now
  matches what it measures. The goldens are compared for carriage
  returns directly, since `read_text` had been hiding exactly what the
  LF pin was added to prevent.

* **The same inversion, found a THIRD time, and now fixed at its root.**
  `-1` was still the all-boundaries default for every entity of that
  kind, so the six surface commands whose page states no all-form
  accepted it anyway: `SURFACE_RENAME` renamed all surfaces to one name,
  `SURFACE_MIRROR` mirrored them, and the refusal text OFFERED `-1` on
  pages that never mention it. The two earlier rounds each moved this
  rule somewhere better without asking whether the default itself was a
  claim, and it is one.

  There is no per-kind default now. Absent means the page states no
  all-form and every non-positive index is refused. SRC-003 pp.307 and
  309-313, SRC-741 p.305 and SRC-740 p.315 were read command by command:
  nine boundary indices state one and declare it, six state none and
  declare nothing. Both halves are asserted, so a rule that simply says
  yes or simply says no fails.

  The refusal wording moved with it. A command with no all-form says so
  rather than naming a value the solver was never told to accept, which
  is where the original defect did its damage.

* **The three declarations below, reviewed in turn, and the round found
  the repair less finished than it looked.** Three of its four new
  guards were untested, and the QA pass measured all three mutations
  surviving a green suite: deleting every `cites:` declaration, deleting
  the whole `fixed_length` refusal, and deleting the backfilled version
  rows. Each is now asserted as behaviour and each mutation is caught.

  `all_sentinel` was not self-sufficient. It reached the emitter only
  because a name map happened to resolve the spelling beside it, so
  renaming that map row would have made the sentinel inert and silent,
  which is the class of defect the field was added to end. It now
  requires `cites:`, and the database is refused at load without it.

  The list path still hardcoded `-1` for every entity kind, which is the
  per-family rule the change below removed from the scalar path and left
  standing next to it. A list of frames or motions has no documented
  all-form at all. Both paths now read the argument.

  The sentinel was also swallowed whenever no boundary inventory had
  been declared. An inventory bounds an index from above; being 1-based
  bounds it from below, and that half needs no inventory, so `-1` on a
  zero-sentinel command emitted silently on any script that had not
  called `declare_existing`.

  The precedence rule was written out four times, once per
  scalar-or-list branch in each of two paths; it is now
  `_reference_kind`, consulted by both.

* **A guard now closes the argument vocabulary, and it found five gaps
  the review did not.** An index argument whose name says it cites
  something must declare what it cites, be a spelling the emitter
  already resolves, be a count, or be listed as an index of an object
  the entity tracker does not model (CAD bodies, curves, sections,
  trailing edges). Running it first reported `DELETE_SURFACES`, both
  surface-section distributions, `ROTATE_COORDINATE_SYSTEM`'s second
  frame and the aeroelastic structural frame: all confirmed against the
  manual and now declared. The Mesh Operations chapter header states the
  rule, since mirroring the manual's own argument spellings is what
  makes the declaration necessary.

* **Three facts an argument used to only describe, it now declares, after
  the review of the four chapters above found each one wrong in the
  emitter.** `ArgSpec` gained `all_sentinel`, `cites` and `fixed_length`.

  The all-surfaces sentinel was fixed per ENTITY KIND at `-1`, and the
  two `TRANSLATE_SURFACE` commands document zero. So the emitter refused
  the documented `0` and accepted the meaningless `-1`, exactly
  inverted, and its refusal message steered the caller to `-1`. The
  notes said so in prose, and the test asserted the prose on the
  reasoning that "nothing can refuse it, since both are valid
  integers". That reasoning was the defect: the sentinel is a
  per-command fact, so the argument carries it.

  Which entity an index cites was inferred from the ARGUMENT NAME, and
  the Mesh Operations chapter mirrors each manual page's own spellings.
  Five of them reached neither map, so `SURFACE_DELETE` accepted a
  declared label and `SURFACE_INVERT` did not, and `SURFACE_COMBINE`'s
  index list and `TRANSLATE_SURFACE_BY_FRAME`'s two frames were range
  checked against nothing. The name map stayed at this point for a
  spelling that means one thing database-wide, and could not be extended
  to `index`, which is a surface here and a section or separation index
  in three other chapters. An argument that needs it now says what it
  cites, and the map itself was deleted later in this release.

  `SET_MOTION_6DOF_ACTIVE_VARIABLES` writes six toggle lines with no
  count before them, and a short payload made the solver read the next
  command as data. The length is declared and a short or long one is
  refused, naming the corruption rather than the arity.

  The count-spelling guard was blind in the same way and the QA pass
  proved it: renaming a real count to `surface` left the whole suite
  green while the emitter stopped comparing the count to its list. The
  exemption now reads the argument's declaration, not its name.

* **Corrected: `solver_settings(thin_boundaries="all")` was refused, and
  the refusal recommended a call that failed again.** `SET_THIN_BOUNDARIES
  -1` marks every mesh boundary thin and takes no index line; the helper
  rejected the bare label and suggested `["all"]`, which then failed as
  an unknown boundary label. The keyword now has three distinct states,
  documented together: absent leaves the solver's list alone, `"all"`
  emits the `-1` form, and the empty sequence erases.

* **Corrected: nine commands the manual documents in the February and
  May 2026 builds carried no row for them,** so the emitter refused them
  on builds whose manual describes them. Six in Motion Definitions
  (boundaries, moving frames, coordinate system, start time and the two
  rotor commands), the two FSI seam commands, and four in Solver
  Settings. This was a pre-existing gap rather than one the sweep
  introduced, and it is not the whole of it: **117 entries are still
  documented in an edition they carry no row for**, all of them 26.100
  and 26.101. Registered as `PLN-20260807-1400`; whether early-build
  parity is a v0.5.0 goal is the author's call.

  Database 248 entries, unchanged by this pass; per version 26.100 106,
  26.101 145, 26.120 227, 26.121 231. The figures previously recorded
  here for 26.120 and 26.121 were wrong before the gap was closed, not
  because of it.

* **Solver Settings is complete.** Three commands remained:
  `SET_SURFACE_ROUGHNESS`, whose height is in NANOMETRES and not the
  metres every other length in this helper takes, and the
  `SET_THIN_BOUNDARIES` and `DELETE_THIN_BOUNDARIES` pair, absent from
  the February 2026 build. Both reach `solver_settings()` as new
  keywords, which the snapshot guard required rather than suggested:
  every command of the settings families must carry a FlagSpec or the
  provenance record silently lags the database.

  A fourth name looks absent and is not. Every edition's Script Index
  spells `CREATE_STRATFORD_BULK_SEPARATION` as
  `CREATE_STARTFORD_BULK_SEPARATION`, and the command is recorded under
  the spelling its chapter body and sample use, which RPT-015 measured
  the solver accepting. A coverage sweep driven from the index will keep
  reporting the misspelling as a gap, and a test now says so.

* **Motion Definitions is complete: 17 commands entered.** The 6DOF
  family (mass and inertia, gravity, initial conditions, active
  variables, the external, custom and spring forces, the trajectory
  export), the custom motion table, and the five kinematic commands
  that exist in the February 2026 build alone. Database 228 to 245.

  THREE COORDINATE SYSTEMS APPEAR IN THAT CHAPTER and no argument name
  distinguishes them: `SET_MOTION_GRAVITY` reads the REFERENCE system,
  the 6DOF initial conditions and forces read the BODY frame, and the
  February kinematic family reads the MOTION DEFINITION system. A
  script setting gravity and an initial velocity writes two vectors
  into two different frames, and the notes are the only place that is
  said.

  `SET_MOTION_CUSTOM_TABLE` takes its TYPE before the motion id, the
  only command in the chapter that does not open with the id.
  `CREATE_NEW_6DOF_SPRING_FORCE` is the third of the five wrapped
  signatures and declares eleven arguments, three of them lengths that
  are not interchangeable. `SET_6DOF_MOTION_SYMMETRY_LOADS` prints a
  shorter name in its sample than in its heading; the heading is
  recorded, on the measured record that a heading has won every case a
  solver has settled. The chapter header, which said the 6DOF family was
  pending, now records the chapter complete and carries the
  three-coordinate-system warning; chapter headers render live in the
  overview, so the stale text was public.

* **Corrected: `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` had one
  grammar and the manual has two.** The February 2026 edition takes two
  arguments and later editions three, the blade count arriving with the
  rotary motion, and the entry carried the three-argument form with a
  26.120 row alone. The February grammar was neither recorded nor
  reachable.

* **The Mesh Operations chapter entered: 22 commands, the whole chapter
  bar one already present.** Everything that moves, copies, cuts,
  selects or deletes a mesh surface between import and solver
  initialization. Database 206 to 228.

  Two things in that chapter are not uniform and both are recorded
  because nothing else would carry them. The all-surfaces sentinel is
  `-1` on most commands and **zero** on `TRANSLATE_SURFACE_IN_FRAME` and
  `TRANSLATE_SURFACE_BY_FRAME`, which the manual states per command and
  never contrasts, so a script reaching for `-1` out of habit translates
  surface `-1` rather than every surface. And `SURFACE_MIRROR`'s
  `MIRROR_PLANE` is an INDEX, 1 for YZ, 2 for XZ and 3 for XY, the only
  plane argument in the database that refuses the two-letter token every
  neighbouring command takes.

  Two version stories the manual tells by omission rather than
  statement. `SELECT_GEOMETRY_BY_ID` is the February spelling of
  `SURFACE_SELECT_BY_ID`, and each carries only the editions that
  document it, so emitting the wrong one for a build is refused.
  `SURFACE_DELETE` and `SURFACE_CLEARALL` are documented in three
  editions and replaced by `DELETE_SURFACES` in the fourth; neither is
  `removed`, because a removal here means a manual stating one. The
  emitter still accepts both for 26.121 through hotfix inheritance,
  which is per version and cannot be denied per command
  (PLN-20260807-1010), and a test pins that permissive behaviour so the
  fix cannot land quietly.

  `SURFACE_ROTATE`'s surface keyword is spelled `SURFACE` in its table
  and `SURFACES` in its sample. A keyword is emitted rather than
  matched, so unlike a value set this cannot accept both. Both spellings
  are printed, the table's and the sample's; the SAMPLE's is used,
  because the sample is the only runnable line on the page, and
  PLN-20260807-1000 carries the probe.

* **The CAD chapters entered the database: 42 commands across all four
  registered builds, and CAD Create is COMPLETE.** Six CAD body commands
  in `cad.yaml`, and 36 in `cad_create.yaml`: the pane settings and the
  basic shapes, the virtual curve constructors with their index and
  delete commands, the three file importers, the three cross-section
  commands that cut curves out of an existing mesh body, the curve
  transforms, and the three loft commands that turn curves into a mesh
  boundary. With `SWEEPER_SET_MACH_SWEEP` and the flow-separation
  family, the database went from 147 entries at v0.4.0 to 206. Every
  entry carries its own page per edition rather than one citation
  reused, and every command emits on all four builds.

  One command was held back at this point in the cycle: the CAD Create
  mirror, whose name the manual spells one way in its heading and
  another in the sample beneath it. IT ENTERED LATER IN THIS SAME
  RELEASE, under the heading's spelling `CAD_CREATE_MIRROR_CURVES`,
  which the Script Index agrees with; the sample's singular was then
  measured not to be a command at all (RPT-021). The stanza on the tail
  of the sweep carries it.

  Facts the argument names do not carry, which is why these were read
  one at a time rather than pattern-matched:
  `CAD_CREATE_CURVE_ARC` takes NINE coordinates whose FIRST triple is
  the arc's ORIGIN and not a vertex on it; the three curve index
  commands take -1 for every curve; `CAD_CREATE_PROJECT_CURVE` reads its
  PLANE in the frame it names and its projection VECTOR in the global
  reference frame, so a script using a local frame projects along the
  wrong direction with nothing to object;
  `CAD_CREATE_PROJECT_MULTI_CURVE`'s two indices are not
  interchangeable, the first being projected and the second a guide; and
  `CAD_CREATE_REORDER_CURVES` takes a SIGNED axis, six tokens rather
  than three, where every other axis argument in the family takes a bare
  letter. `CAD_CREATE_AUTO_CROSS_SECTIONS` and
  `CAD_CREATE_REVOLVE_MESH_FROM_CCS` each declare EIGHT arguments and a
  signature parser reports seven, because their manual headings wrap and
  the eighth placeholder sits alone on the second line; both samples pass
  eight tokens, which is what settles it. `LOFT_TYPE_U` and
  `LOFT_TYPE_V` mean chordwise and spanwise on the wing loft and radial
  and axial on the other two, so a value carried across means something
  else. And `CLOSE_ENDS` is documented as OPEN or CLOSED on all three
  lofts while all three of their printed samples pass `TRUE`: the table's
  pair and the printed token are all accepted, because refusing either
  side would refuse something the manual states. `FALSE` is NOT among
  them, and was until the review caught it: it is the value set of the
  neighbouring `MARK_TRAILING_EDGES` argument, pasted across.

  `CAD_CREATE_CURVE_EXPORT_CCS` carries phase `geometry` despite its
  name, following `EXPORT_SURFACE_MESH`: a phase is the position the
  ordering rule assigns, and filing a curve export under `export` would
  let a script emit it once and then refuse every remaining CAD Create
  command.

  Not entered at this point: the CAD Create mirror, whose name the
  manual spells two ways, the heading and the Script Index together
  against the sample. It entered later in the same release under the
  heading's spelling, and the sample's spelling was measured not to be a
  command (RPT-021).

* **The Sweeper Toolbox chapter was drafted from a worked example and
  has been redrafted from the reference pages, which changes what the
  emitter accepts.** The example at SRC-003 p.406 exercises two of the
  three sweep modes and three of the four sweep axes, so every gap
  followed from it: `UNIFORM` was missing from all three enumerations,
  `SWEEPER_SET_MACH_SWEEP` was missing entirely, and the velocity axis
  could take a file where the angle axes could take a list, an asymmetry
  the manual does not have. The reference pages give all four axes one
  parameter table, word for word.

  New command: `SWEEPER_SET_MACH_SWEEP`. New accepted mode on all four:
  `UNIFORM`, which takes start, stop and INCREMENT (the parameter table
  labels the triple STEPS, and the Mach sample passes 0.05 there, which
  no count can be). Every axis now takes the value list inline or a file
  path, whichever the caller has.

  Consequence for the caller: `script.emit("SWEEPER_SET_AOA_SWEEP",
  "UNIFORM", [-10.0, 20.0, 1.0])` used to be refused as an unknown mode
  and now emits. No script the emitter accepted before renders
  differently, but the velocity axis gained the inline value list its
  three siblings already had, so its `filename` moved from the second
  positional to the third: a positional `emit("SWEEPER_SET_VELOCITY_SWEEP",
  "CUSTOM", path)` now binds the path to `values` and is refused. Pass
  it as `filename=`. The
  curated `sweep()` helper still covers the CUSTOM subset and says so
  in its docstring, with the extension registered.

* **Eight commands became available on 26.101, and two on 26.121, that
  the database was silent about.** The whole Sweeper family gains a
  26.101 row, `AEROELASTIC_RBF_TYPE` gains 26.101 and 26.121, and
  `CREATE_NEW_MOTION` gains 26.100 and 26.101. Emitting any of them for
  those builds raised `CommandNotInVersionError` before; the manual
  documents them and now the database does.

* **`CREATE_NEW_MOTION` carries a per-version vocabulary.** The February
  2026 build names the first motion type `EUCLIDEAN` and every later
  edition names it `ROTARY`, and the two are not one capability
  relabelled: four commands that configure the February form exist in no
  later edition and two that configure the later one exist in no earlier
  edition. Emitting `ROTARY` on 26.100 is now refused with the February
  token list.

* **A refusal about a per-version grammar cites that version's page.**
  It used to cite the entry-level one, so the refusal above would have
  listed February's tokens beside a page number from the current manual.
  An error message naming the wrong page is worse than one naming none,
  because the reader goes and reads it.

* **`CAD_BODY_ROTATE` accepts the axis index as well as the letter.**
  Its parameter table names only X, Y or Z, in every edition, and the
  sample printed beneath that same table passes `2`, also in every
  edition, so the declared set refused the manual's own call. Pass the
  index as the string `"2"`.

* **`parse_signatures` reads a signature heading that WRAPS.** Five
  commands continue their placeholders onto a second line, identically
  in all four registered editions, and the parser reported every one of
  them short: `CREATE_NEW_RECTANGLE_VOLUME_SECTION` by three arguments,
  the other four by one. A short signature is the worst output this
  module has, because the draft it feeds LOADS: the schema accepts an
  entry with fewer arguments, the emitter then accepts a call with fewer
  tokens, and the solver reads the line differently with nothing between
  them to object. The rule is strict about what continues a heading, a
  line of placeholders and nothing else, so a following heading cannot
  donate its arguments to the command above it.

  No committed entry was wrong: the two affected commands already in the
  database were hand-authored from the page rather than from the parser,
  which is the argument for reading the page that this session has now
  made twice.

* **New public function `pyflightstream.utils.sample_contradiction`**,
  and `render_entry` now writes `???` for a type the manual's own sample
  refuses instead of writing the type. Drafts of commands whose
  parameter table and sample disagree no longer load.

* **New public property `CommandEntry.citation`**, the entry's evidence
  citation whichever kind it carries. A message built from `manual_ref`
  alone printed an empty pair of brackets for an entry resting on a
  probe report.

* **An inline list argument may no longer declare a separator other than
  `space`.** The inline renderer joins with a space and never consulted
  the field, so the two SWEEPER sweep commands spent a release declaring
  `comma` and rendering spaces: right by accident, and unreadable as a
  statement of the grammar. The database now refuses the declaration at
  load time rather than ignoring it. Other layouts honour the field and
  are unchanged.

* **Corrected: the registered scripting-reference page range of two
  manual editions.** SRC-003 was recorded as pp.286-371 against a
  measured pp.281-376, and SRC-740 was short by the same five pages at
  each end. The published manual-coverage page listed ten real reference
  pages as uncited and described 22 in-chapter citations as material
  beyond the reference chapter. A tier-1 guard now fails when an
  evidence citation falls outside its edition's registered range, which
  needs no pdf: both facts are committed.

* Deprecations: none.

* **New database field `probe_ref`, and the first command recorded on
  one.** Until now every entry needed a manual page, which refused a fact
  this repository holds evidence for: RPT-018 measured
  `DELETE_VALAREZO_SEPARATION_BOUNDARIES` accepted on 26.100 while the
  name SRC-741 p.339 prints for the same erase is unrecognised, and
  RPT-015 measured `CREATE_STRATFORD_BULK_SEPARATION` accepted on a build
  whose manual does not mention it. Such a command could not be recorded,
  so the user was pushed to `Script.raw()`, the one emission path with no
  validation at all.

  A committed probe report may now stand where the page would, and the
  entry says which report. Exactly one citation per entry, enforced by
  the model and by a walk over the files: neither is an assertion, both
  leaves a reader unable to say which the entry rests on. A tier-1 guard
  checks that a cited report exists AND names the command, the same rule
  the status citations carry, because a citation pasted from a sibling is
  the defect this database has already produced once.

  It does not relax the status rules. `verified` and `broken` still come
  only from a compat report applied by `pyfs-qa apply-compat` (invariant
  3); `probe_ref` records that a command EXISTS, which is a different
  claim from how it behaves.

  Consequence for the caller:
  `solver_settings(valarezo_separation_boundaries=[])` emits the erase
  again. It was REFUSED between 2026-08-05 and 2026-08-06, which was the
  right answer to a database that could not hold the working name and the
  wrong one once it could.


* **The flow-separation family is in the database, across all four
  registered builds, and `solver_settings()` emits every command of
  it.** That includes the Valarezo erase, whose working spelling is the
  one RPT-018 measured rather than the one SRC-741 prints; the helper
  refused that keyword for one day, between the probe and the
  `probe_ref` field that let the working name be recorded at all, and
  the entry above is the same change seen from the database side.
  Sixteen commands entered, the sixteenth being the probe-backed erase
  named below: the per-mechanism boundary lists of
  26.100 (axial, Valarezo criterion, cross-flow, each a SET and a
  DELETE, plus the cross-flow diameter and its axisymmetric toggle), the
  named assignment models of 26.101 and later
  (`CREATE_AIRFOIL_SEPARATION`, `CREATE_AXIAL_VORTEX_SEPARATION`,
  `DELETE_SEPARATION`), the 26.121 split of the bulk model
  (`CREATE_CYLINDRICAL_BULK_SEPARATION`,
  `CREATE_STRATFORD_BULK_SEPARATION`), and the two members documented in
  every edition and recorded in none of them,
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES` and `LAMINAR_SEPARATION`.

  Four new public models, one per assignment command:
  `AirfoilSeparation`, `AxialVortexSeparation`,
  `CylindricalBulkSeparation`, `StratfordBulkSeparation`, exported from
  `pyflightstream.script.solver_setup` beside the existing
  `BulkSeparation`. Eleven new `solver_settings()` keywords carry them
  and the 26.100 lists. Every keyword whose command belongs to ONE
  generation is version-gated: a 26.100 keyword on a 26.101, 26.120 or
  26.121 script refuses naming the command, and the reverse too.
  `laminar_separation` is the exception and is not a gap, its command
  being documented in all four editions. The database records the two
  generations on disjoint builds; RPT-018 measured part of that
  disjointness, five of the eight February commands on 26.101 and three
  on 26.121, and none of them on 26.120, which sits between two measured
  builds by inference.

  **A probe decided the names rather than a reading, and it had to.**
  The February manual documents the Valarezo pair under two spellings,
  one in a function header and one in a sample, so the RPT-012 rule
  (the header wins) had nothing to decide between. On the licensed
  February build the solver accepts `SET_VALAREZO_SEPARATION_BOUNDARIES`
  and does not recognise `SET_VALAREZO_CRITERION_BOUNDARIES`, and the
  delete is the reverse of what the manual says: the documented
  `DELETE_VALAREZO_CRITERION_BOUNDARIES` is unrecognised while an
  undocumented `DELETE_VALAREZO_SEPARATION_BOUNDARIES` works. The
  database records the documented name with the contradiction on it, and
  the working name has an entry of its own, resting on that report
  through `probe_ref`: it was unrecordable for one day, which is the
  entry above.
  Full method and results in
  `reports/RPT-018_separation-family-across-builds_2026-08-05.md`.

* **Behaviour change: `solver_settings(viscous_excluded=[])` now emits
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES`.** It used to emit
  `SET_VISCOUS_EXCLUDED_BOUNDARIES 0` followed by an empty index line,
  which asks the parser to read a line carrying nothing. The empty
  sequence is the erase for the viscous exclusion list and for two of
  the three 26.100 separation lists; omitting the keyword, or passing
  None, still leaves the list as the script found it. A caller who
  wanted the old emission was writing a malformed script.

  Three empty sequences are REFUSED rather than acted on, and the
  message says why in each case. `valarezo_separation_boundaries=[]` would emit
  the one name in this family the solver does not recognise, so it
  names `Script.raw()` and the spelling that works. An empty sequence of
  assignment models (`airfoil_separation=[]` and its three siblings)
  emits nothing, which would be a third meaning for `[]` in one
  signature and the only silent one; it names `delete_separations`,
  which is how the solver erases. And an assignment model whose own
  `boundaries` is empty would emit the count 0 followed by an empty
  index line, the malformed shape the viscous-exclusion refusal was
  written for, reached through a different keyword. That refusal covers
  `bulk_separation` too, which routed onto the shared renderer in this
  release: it had its own emission block predating the renderer and was
  the one assignment keyword the refusal did not reach.

  A single assignment model may be passed where a sequence is expected,
  since `bulk_separation` takes one and the habit crosses over; it used
  to die on `object of type CylindricalBulkSeparation has no len()`.
  `delete_separations` reads its `"all"` sentinel case-insensitively and
  refuses any other string didactically, where `"ALL"` reached a `<`
  comparison and raised a bare `TypeError`. `AxialVortexSeparation.frame`
  accepts a declared coordinate-system LABEL as well as an index, like
  every other frame citation in the library.

* **New registry field `inherits_base`, and a build that stopped
  inheriting.** A hotfix build falls back to its base release's command
  evidence, which is right for a real hotfix and was applied on the
  strength of the identifier alone: last digit not zero meant hotfix.
  The 2026-08-04 renumbering put the February 2026 build at 26.100 and
  appended the May build as 26.101, so that rule made the May release a
  hotfix of the February one. It inherited eight February-only commands,
  and `Script(version="26.101")` emitted lines that solver reports as
  deprecated and refuses.

  Inheritance is now stated per build in `commands/_meta.yaml` with the
  reason beside it, and the silent default is gone from four places
  rather than one, each closed after the previous close was measured
  incomplete by the next review round. The registry refuses to load a hotfix index that states
  nothing. **`FsVersion` refuses to be BUILT as one**, which is a
  breaking change to a public constructor: `FsVersion(canonical="26.121",
  alias="26.12", index=4)` raised nothing before and raises
  `UnknownVersionError` now, because `Script` accepts an `FsVersion` and
  the field default made the original defect reachable through the
  documented public surface. And **`resolve()` reconciles an `FsVersion`
  argument against the registry** instead of handing it back, so a
  hand-built object cannot state a wrong descent for a REGISTERED build
  either. And **the REGISTRY answers, in the layer that reads the
  fact**: `CommandEntry.evidence_in` asks the ordering authority rather
  than the object it is handed, so a caller cannot assert a descent in
  either direction, and a canonical the registry has never heard of
  inherits nothing. An unregistered `26.122` used to receive the whole
  26.120 command view while the string `"26.122"` raised for not being
  registered, so the two documented input types of one parameter
  disagreed about whether a build exists. A synthetic version still
  resolves and still sees its own direct records, which is what this
  package's own fixture registries need.

  `bulk_separation` refuses on a build whose grammar drops
  SEPARATION_TYPE, naming that build, both manual editions and the
  `Script.emit` escape. The binder's generic message named an argument
  the caller never typed and cited the 26.120 page to somebody whose
  grammar is documented at SRC-725 p.341.

  26.121 still inherits from 26.120, which is a genuine hotfix pair.

* **New subpackage `pyflightstream.utils`, and its first member
  `utils.manual`**: read a FlightStream manual and report what the
  command database does not record. Point it at a new build's manual and
  it returns the vendor's own Script Index, each command's page,
  signature and sample, and the three-way difference against the
  database (absent, recorded, recorded-but-undocumented).

  ```python
  from pyflightstream.utils import read_pdf_pages, parse_signatures, coverage_against
  ```

  **It proposes and does not write, and the reason is measured rather
  than cautious.** Checked against the 147 entries this database held
  when the tool was written, authored by hand from these same manuals
  (162 since the flow-separation family landed), it reproduces 77
  percent of their argument lists. The remaining quarter are not parser
  bugs: a variable-length list is one `int_list` argument in the database
  and N lines in the manual's sample, a keyword block has no inline
  signature at all, some commands document alternative forms in one
  sample, and the manual names arguments `value` where the database names
  them `layers`. Every layout proposal carries the sentence saying what
  it was read from, so a reviewer can disagree cheaply.

  New optional extra `[manual]` (pypdf, BSD-3-Clause, license card in
  `reports/RPT-017`). Maintainer tooling: no run path imports it, and the
  parsing half needs nothing, because it takes text. Only the pdf reader
  needs the extra.

  **New console script `pyfs-manual`**, the fifth, with two subcommands
  at this point in the cycle; `sweep` joined later and the shipped CLI
  has three.
  `coverage` reports what a build's manual documents and the database
  does not. `draft` renders entries for those commands, and **writes
  nothing unless `--write` is passed with `--out`**; without a
  destination it refuses rather than guessing where to put a draft.

  A drafted entry writes `???` wherever no rule reads a value: every
  phase whose section is unmapped, and every argument type the parameter
  table does not decide (see the entry below, which added that reading;
  before it, every type was unanswered). That
  is deliberate and it is the safety property: the database schema
  refuses `???`, so an unreviewed draft turns the suite red instead of
  quietly becoming grammar the emitter validates other people's scripts
  against. Each also carries a `drafted:` line naming the tool, the
  manual and the page, so one grep finds every machine-drafted entry.

  New public exception `utils.ManualDraftError`, in the catalog and
  keeping `ValueError` as its second base. It refuses a request to draft
  a `verified` or `broken` status: those are promoted from a committed
  probe report by `pyfs-qa apply-compat`, never from a page citation
  (invariant 3).

  **`utils.manual` now reads the manual's parameter table, which is
  where argument types live**, and proposes them: new public
  `propose_type`, and a new `ManualCommand.parameters` field carrying
  the table. Every argument used to draft as `???`, because the
  signature line and the sample block say nothing about a type.

  The rules are public DATA rather than control flow: `TYPE_RULES` and
  its element type `TypeRule`, both exported from
  `pyflightstream.utils`. The ORDER of that table is the specification,
  each row carrying a docstring and the four whose position has been
  wrong once saying why they sit where they do, and the tests pin every
  adjacent pair. Three review rounds each found one rule in
  the wrong place while the order lived in a chain of ifs, and each fix
  was invisible on a revert.

  `Coverage` and `ManualDraftError` are exported from
  `pyflightstream.utils`, which the entry above announced and the
  subpackage did not do: `Coverage` is the return type of a public
  function and could not be named to annotate a variable, and
  `ManualDraftError` was importable only from its own module.

  `read_pdf_pages` takes its page range keyword-only and refuses a range
  it cannot honour. A reversed pair read no pages and `coverage_against`
  reports an empty manual as one that documents nothing, which is a
  confident answer produced by a typo; a first page of zero indexed the
  pdf at -1 and keyed the manual's LAST page as page 0, so a drafted
  entry cited `p.0`. Reaching past the end now refuses too, naming the
  page count, which is also the cheapest sign of the wrong edition.

  `pyfs-manual draft` spells the version flag `--fs-version`, as every
  other CLI of this package does; `--version` is what a reader expects
  to print the package's own version. Every argument is checked before
  the manual is opened, so `--write` without `--out` refuses in a second
  rather than after two full pdf reads on a 400-page document, and a
  malformed page range exits 2 with the flag named instead of raising a
  raw `ValueError`.

  Measured against 148 arguments this repository typed by hand: **57
  percent agreed, 43 percent proposed nothing, none disagreed.** The
  third number is the one to hold. A rule that cannot read a type
  returns None and the draft still writes `???`, so a tranche is still a
  person's work; the failure that matters is a wrong type, because that
  one loads and then validates other people's scripts. The one
  disagreement found while measuring is pinned as a test: matching the
  toggle tokens case-insensitively read the ordinary words "enabled" and
  "disabled" out of a sentence about boundaries and proposed an enum for
  a count.

* **Breaking, and it can affect a script you already wrote:
  `resolve("26.1")` now raises `AmbiguousVersionAliasError` where it
  returned 26.100.** Two registered builds carry that vendor name since
  the February 2026 install was registered, exactly as 26.120 and 26.121
  have shared "26.12" all along. The refusal names both candidates; pass
  the canonical identifier. No deprecation cycle is possible for this:
  the name stopped being unique because the vendor shipped another build
  under it, not because this package renamed anything.

  Read the general lesson rather than only the instance: a vendor
  release name is unique only until the vendor reuses it, so a script
  that passes one is correct until it silently is not. Canonical
  identifiers are the stable input.
* **New registered version: 26.101**, the May 2026 build (vendor build
  5012026). Purely additive, and no version was dropped (CLAUDE.md
  invariant 4).
* **26.100 now names the FEBRUARY 2026 build** (vendor build 2122026,
  read from the solver's own identity line). Its 38 records did not
  disappear: they describe the May build, which was appended as 26.101,
  and they moved there with it. It began this release with no command
  evidence of its own and holds 11 entries since the flow-separation
  family landed, so its derived support level is `documented` rather
  than `registered`. It reaches `operational` later in this same
  release, at 345 emittable commands, which is the per-edition residual
  stanza above.

### Changed

* **Every committed report of a 26.1x run had its version LABEL
  corrected, and nothing else.** Eleven reports recorded runs of vendor
  build 5012026 under the name 26.100, which this repository reassigned
  on 2026-08-04 when the earlier February build took that index under
  the append-only ordering rule. The build number, the executable name,
  the date, the measurements and the outcomes are byte-identical; each
  report carries a note saying so, and each keeps its original id
  because ids are cited elsewhere. The `fs_exes` field of the drift
  reports confirms the reattribution independently: they ran
  `FlightStream.exe`, which is the executable of the install now named
  26.101.
* The `26.100` manual edition is now SRC-741 (Altair FlightStream User
  Guide, February 2026, 396 pages). SRC-725 moves to 26.101, which is
  the edition every existing SRC-725 citation was read from, so no page
  citation changed meaning.

## [0.4.0] - 2026-08-04

### API surface delta

* **Incompatible change, numerical: `farfield.plane_integral` returns
  NaN where it used to return a finite number.** This is the one entry
  in this release that changes an EXISTING result rather than refusing a
  new input, so it is stated here rather than only among the fixes.

  It inherited xarray's `skipna=True`, so an absent sample left the sum
  while its ring weight stayed in the geometry. Flux, force, torque and
  energy shrank in exact proportion to how much data was missing, with
  no warning, no flag and no non-zero status. A 0.3.0 result computed
  over a complete lattice is unaffected; one computed over an incomplete
  lattice was wrong and now says so.

  **How to tell whether your existing evidence is affected**, because
  "recompute everything" is not a triage:

  ```python
  from pyflightstream.farfield import sample_coverage

  # Same integrand you would pass to plane_integral. Returns the finite
  # fraction of the (r, psi) samples, per remaining dimension, so a
  # sweep answers per plane rather than once for the whole array.
  coverage = sample_coverage(integrand)
  bool((coverage == 1.0).all())   # True: nothing changed for this data
  ```

  Where the coverage is 1.0 the old number and the new number agree and
  no action is needed, and that half is exact. Anywhere below 1.0 the old
  number was low by the AREA-WEIGHTED share of the missing samples, which
  the coverage number bounds but does not quantify: `plane_integral`
  weights each sample by its annulus area, so a sample missing at the tip
  costs far more of the integral than one missing at the hub. Coverage
  tells you WHICH planes are affected; recompute to learn by how much.
  The NaN is not a regression, it is the first time the gap was visible. `sample_coverage` is new in this
  release for exactly this question, and it reports per plane rather
  than one number for the sweep, so one dead probe is distinguishable
  from a half-empty lattice.
* **New public names: `script.ScriptLineBreakError`,
  `farfield.sample_coverage` and `fsi.state.check_state_matches_config`,
  and `Script.comment()` renders differently.** All three names and the
  rendering change come from the blocker fixes, and they are listed here
  because this section is where a reader scans for what the surface did.

  `ScriptLineBreakError` subclasses `CommandArgumentError` and is raised
  when a text or path argument contains a line terminator, which used to
  become a line boundary and turn the text after it into the next
  command with `raw_flag` still False. `Script.comment()` now prefixes
  EVERY physical line of a multi-line comment, so a comment can no
  longer end and a command begin inside what was written as prose. If
  you passed multi-line text through a text argument and relied on it
  splitting, `Script.raw()` is the sanctioned route and still sets the
  flag.

  Seven refusals are new in the blocker fixes below, and they are not
  every refusal this release adds; the entries above carry more. A line
  terminator in a text
  argument, a non-finite scalar or list value in an FSI configuration, a
  probe lattice outside its documented domain, an out-of-domain Omega in
  a Campbell sweep, a duplicate column in a parsed table, trailing
  content after an export block, and a solver mode the package has not
  been taught. Each replaces a path that previously produced a result.
* **FR-37 closes as covered and the terminal-status set stays closed at
  six** (SRS 1.13.0). The requirement collided with FR-46, which closes
  the set at the six values `RunStatus` carries: FR-37 asked for a status
  distinct from a COMPLETED one, and a run reaching its iteration cap
  lands in `COMPLETED_MAX_ITER`. The author resolved it in FR-46's favour
  and the requirement is RESTATED rather than merely declared satisfied:
  it now asks for a status distinct from the CONVERGED one, which is what
  this library guarantees. Two of the six give it, `COMPLETED_MAX_ITER`
  for a run that reached its cap and `FAILED_INCOMPLETE_OUTPUT` for one
  whose loop did not complete. Requirement text and docstrings only; no
  runtime change, and no status value was added, removed or renamed.
* **New public names: `commands.Evidence` and
  `CommandEntry.evidence_in`.** The compatibility matrix showed 76 of
  147 cells for 26.121 as though that build had been probed, and it had
  not.

  A hotfix build inherits its base release's evidence until a probe on
  the hotfix overrides it. That default is right and it is not what
  changed. What changed is that the inheritance was INVISIBLE:
  `status_in` returned the base record with nothing saying it had, so an
  inherited cell and a directly probed cell were indistinguishable, and
  each inherited cell carried a citation to a report run on the OTHER
  build.

  It mattered because a hotfix had already been measured changing a
  command: `AIR_ALTITUDE` is broken on 26.120 and verified on 26.121. So
  the inherited answer was known to be falsifiable at the moment it was
  being published as fact.

  ```python
  evidence = entry.evidence_in(resolve("26.121"))
  evidence.record      # the VersionStatus, as status_in returns
  evidence.source      # "26.120" when it came from the base release
  evidence.inherited   # True: an assumption, not a measurement
  ```

  `status_in` is unchanged in behaviour and is now implemented on top of
  `evidence_in`, so the two cannot drift. Prefer `evidence_in` wherever
  the answer reaches a person or a report.

  The published matrix marks every inherited cell and its per-version
  summary gains an **Of which inherited** column, which reads 76 for
  26.121 and 0 everywhere else. A tier-1 guard asserts that the marked
  set and the inherited set are the same set, in both directions:
  showing an assumption as a measurement and showing a measurement as
  an assumption are the same defect pointing opposite ways.

  Not changed, and measured rather than assumed: `version_support`
  counts 69 probed commands for 26.121 of which 68 were probed on that
  build, so its overstatement is one command and its level is unaffected.
* **New public name: `workspace.collection_name`.** It answers one
  question, "what name does this declared output take once collected",
  and it exists because two layers were answering it differently.

  **Behaviour change, and it moves a refusal earlier.** Three campaigns
  used to plan as `READY` and fail at collection, which is after the
  solver has run:

  ```python
  case.outputs = ["loads.txt", "loads.txt"]      # one point
  case.outputs = ["a/loads.txt", "b/loads.txt"]  # one point
  case.outputs = ["a/loads.txt", "b/loads.txt"]  # two points of one case
  ```

  Collection moves every declared output into `raw/` under its BASE
  name, so all three collide there. The plan-time check keyed on the
  declared string, where `a/loads.txt` and `b/loads.txt` differ, and it
  skipped a repeated name carrying the same point tag as itself, which
  is what let the first case through. So the cheap boundary passed what
  the expensive one refused, and the difference was paid in licensed
  solver time.

  This contradicted two statements this project publishes: the case
  model says a case whose points would render the same output name is
  blocked before it runs, and the entry below says every collision is
  refused before anything moves. Both are now true.

  A declared name with a directory part is still legitimate; it simply
  does not make two outputs differ, and the refusal says so.

* **The run matrix collects its outputs, honours its HIDDEN column, and
  says when an override overrules a row.** **Breaking**: a matrix row
  that declares no outputs is now refused. Found by running the
  author's own research campaign, not by a review.

  Three defects, one theme: *the matrix states a fact, a function
  parameter states the same fact, and the parameter wins silently.*

  **Outputs, the one that lost work.** `to_campaign` never set
  `outputs`, so every matrix-driven case carried the empty default and
  the collection step had nothing to look for. With the standard
  `LoadsAssessor`, which the README and the guides tell you to pass, a
  point lands `FAILED_INCOMPLETE_OUTPUT` *after* the solver has run.
  Measured: a thirty-minute unsteady run completed, the solver wrote
  all eight expected files into the run folder, and the point was
  recorded as a failure with the files sitting beside it.

  A row declares them in `VAR_NAMES_VALUES` as
  `OUTPUTS: loads.txt, loads_cp.txt`, **comma**-separated, because the
  slash already separates the `KEY:VALUE` pairs. A row that declares
  none is refused before the solver starts, since a refusal costs
  nothing and the silent empty list cost half an hour.
  `convert_matrix` carries them into `campaign.toml`, so FR-11 stays
  lossless.

  **HIDDEN.** The column existed and was read into the `matrix_hidden`
  variable and never acted on, so a row saying `0` (show the window)
  ran headless because `run_matrix(hidden=...)` defaulted to `True`.
  The parameter now defaults to `None`, meaning the row decides; an
  explicit `True` or `False` still wins.

  **The override.** The explicit `fs_exe` override is the only way to
  run a `MANUAL` row, so it has to win, and it used to win silently
  over a row naming a real build: a row saying `FS_BUILD 26.121` ran on
  the 26.120 executable and was recorded as having requested 26.120.
  It warns now, naming the builds it overruled.

  **Why tier 1 never saw any of it.** The one end-to-end matrix test
  passed a stub assessor that returns `CONVERGED` without reading a
  file, the fixture recipe exported a literal instead of
  `case.outputs[0]`, and the stub solver wrote a fixed name regardless
  of what the script asked for. All three are corrected, and the test
  now asserts the collected files and their hashes.
* **Announced for v0.5.0, breaking, with no alias: the dry-run pair is
  renamed.** No change in this release; this notice is what makes the
  direct break available, the same way the v0.3.0 notes made this
  release's tabular renames available.

  ```python
  dryrun_matrix(...)     # was plan_matrix
  dryrun_campaign(...)   # was plan_campaign
  ```

  `plan_matrix` reads as "plan what is in the matrix" and the function
  dry-runs it: it resolves, validates, builds every script and checks
  the geometry, executing nothing. The prose has called that a
  pre-flight all along, so the divergence was already here.

  `preflight_*` was considered and rejected, because *pre-flight* is
  already the name of a different thing: the solver-identity check
  runs the solver once, lazily, to read which build is installed.
  Collapsing the two under one public name would erase exactly the
  distinction "executes or does not execute" that the rename exists
  to carry.

  `dryrun` is the verb; **`plan` stays the noun**. `CampaignPlan`,
  `PointPlan`, `PlanStatus`, `plan.json` and `write_plan` are
  unchanged, because what the action returns and writes *is* a plan.
  The old names used the noun as a verb.

  Both are renamed rather than only the matrix one: the matrix
  delegates to the campaign, so renaming one would move the asymmetry
  somewhere deeper and less visible.

  **The CLI follows**: `pyfs-matrix plan` becomes
  `pyfs-matrix dryrun`. A library function and the console subcommand
  that fronts it carrying different verbs would put one fact in two
  homes on the surface a user types.
* **Every public refusal the guard reaches now carries the package's
  base exception** (SRS FR-39, whose first clause was false in 70
  places; 24 named sites remain, see the end of this entry).
  **Widening only**: every new class keeps its standard-library base,
  so an existing `except ValueError` or `except RuntimeError` catches
  exactly what it caught before, and `except PyflightstreamError` now
  catches these too.

  FR-39 has read *implemented* since 2026-07-27 and its two guards
  inspect exception CLASSES, never a `raise` statement. An independent
  review found three public functions raising a bare `ValueError`;
  walking the tree found **70 sites across 11 modules**; widening the
  walk to the modules that declare no `__all__` found 46 more; and
  widening it again to reachability, because a bare raise inside a
  module-private helper that a public function calls reaches the caller
  exactly as an exported one does, found 21 more. Nine
  catalogued classes are added for the conditions that had no home:

  * `results.MalformedOutputError`, the sibling of
    `IncompleteOutputError` for a file that is whole and still cannot
    be read as itself (a duplicated column, a second concatenated
    export, an impossible count).
  * `results.FieldNotInExportError`, for a field name absent from an
    export's columns; `KeyError` stays as its second base.
  * `probes.ProbeGeometryError`, shared by the cylindrical lattice, the
    planar grids and the geometry gate.
  * `cases.CampaignConfigError`, for a campaign or recipe that cannot
    be used as written.
  * `farfield.FarfieldInputError`, for fields a reduction cannot
    integrate.
  * `qa.QaEvidenceError`, for a committed QA artifact that cannot be
    read as the evidence it claims.
  * `extras.UnknownExtraError`, for a name used as an extra that this
    package does not have.
  * `commands.CommandDatabaseError`, for a command database that cannot
    be read as the evidence record it claims to be.
  * `fsi.errors.FsiInputError`, for a coupling input a run cannot use.
    Written with the submodule because that is where it is reachable:
    the `fsi` package root re-exports no exception at all, and making
    this one the first is a convention decision left to v0.5 rather
    than taken here by a one-line paste. Both classes are also
    re-exported from `pyflightstream.exceptions`, as every catalogued
    class is.

  New `pyflightstream.probes.errors`, `pyflightstream.qa.errors` and
  `pyflightstream.fsi.errors` hold one shared class each, because the
  package `__init__` imports the submodules that raise them.

  A third guard walks every exported public name, and every
  module-private helper an exported one calls, for bare
  standard-library raises. It is the one that measured 70 when the
  review had reported three. **It does not make the headline
  universally true, and this note says so rather than leaving the SRS
  to say it alone**: 24 sites are exempt by name in a ratchet, three
  `TypeError` raises needing a base this catalogue does not have
  (`PLN-20260803-2340`) and the 21-site reachability tranche deferred
  to v0.5 (`PLN-20260804-0130`). The list is the debt, it is countable,
  and any site the walk reaches that is not on it fails today. SRS
  FR-39 carries the residual and the two measured limits of the walk's
  own reach.
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
  six (SRS FR-46), and the author resolved on 2026-08-03 that it stays
  closed. FR-37 is restated
  to ask for a status distinct from the CONVERGED one, which is what the
  library guarantees, and closes as covered (SRS 1.13.0).
* **"Supported" was one word covering four states, and is now four
  named values** (SRS FR-49, new). New public names at the top of the
  package: `SupportLevel`, `support_table()`, `version_support()`,
  `support_level()`, plus the `pyflightstream.support` module with
  `minimal_workflow()`, the `VersionSupport` record those functions
  return, and the two data members a caller reads rather than
  reconstructs, `SUPPORT_LADDER` and `MINIMAL_WORKFLOW_COMMANDS`.
  Purely additive.

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

  The waiver emits the command and records it through the new exported
  type `script.BrokenCommandUse`, one instance per waived command:
  `script.broken_commands`
  and the new `broken_commands` field of `RunRecord` carry the command,
  TWO versions, the committed report, the recorded observation, the
  justification and the script line the first waived emission rendered.
  The two versions are `version`, the build the script targeted, and
  `source_version`, the build whose record is broken and therefore the
  build the cited report was run on; they differ exactly when a hotfix
  inherits its base release's record, and reading either as the other is
  the defect this release is named for.

  The same promise `raw_flag` makes for unvalidated
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
  CATALOGUED exception descends from it** (SRS FR-39, which was pending
  on exactly this clause). Read that word before relying on the
  sentence: a residual of bare standard-library raises survives. Every
  site the guard's walk reaches is named in the ratchet in
  `tests/test_exceptions_catalog.py`, which is the single home of that
  list; SRS FR-39 states the walk's reach and the count, and at least
  one site sits outside the walk. One except clause
  catches the catalog:

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

* **The user guide is refreshed for 26.121, and a guard now keeps it
  current.** Six claims went stale when the 26.121 onboarding landed
  and nothing caught any of them: the guide is neither built nor
  executed by CI, so every claim in it was true only until the next
  licensed session moved the evidence underneath it.

  Corrected: the version diagram, which drew three nodes ending at
  26.120 beside a listing that printed four; the pinned refusal
  transcript, which listed two recorded versions where the library
  prints three; AIR_ALTITUDE, which the guide called broken without
  saying on which build, when in fact the vendor hotfix fixes it and the
  probe on 26.121 promoted it to verified; SET_MOTION_START_TIME, which
  said "await re-probe" after the re-probe had run and found the same
  abort; and the pitfall table, which now names the builds each finding
  applies to and gained the SWEEPER_REF_VELOCITY_SAME row it was
  missing.

  The AIR_ALTITUDE entry is the one with user consequence, so it now
  carries the number: on 26.120, 5000 METERS produced 1.056 kg/m^3, the
  5000 ft standard state, where 0.736 is correct. A density 43 percent
  high with no error, and the hotfix digit in the version identifier is
  what lets the database say the two builds disagree.

  The counts are gone rather than corrected (author's decision,
  2026-08-03). "144 commands" was wrong by three, and the plan item
  recording that it was wrong was itself wrong by two the day after it
  was written. The compatibility matrix generates the current numbers on
  every docs build, and the guide points at it.

  `tests/test_guide_currency.py` is the guard, and it is a different
  failure class from `test_guide_api_names.py`: that one checks the
  names the guide teaches, this one the facts it states. No
  hand-written command count, the curated-helper count equal to what the
  module defines, every registered version mentioned, every pinned
  transcript equal to what the library prints, every pitfall row naming
  the builds the database calls broken, and every broken command having
  a row at all. That last one closes the hole the others leave: a
  missing row is invisible to a check that reads the rows present, and a
  missing row is what happened. Six mutants, one per original stale
  claim, all caught.
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

  **The push-gate half of this promotion is superseded within the same
  release.** The entry above re-vendors the gate alone to 0.2.16 to
  close a fail-open the 0.2.4 body carried, so the gate this release
  ships is 0.2.16 and not the 0.2.4 described here. The other three
  artifacts of this bullet, the analyst charter, the snapshot tool and
  the skill wording, are still at 0.2.4. Both entries stay: this one
  records why the privacy promotion happened, the other why the gate
  moved again, and a reader arriving at either needs the pointer.
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
    contain as written. Resolved on 2026-08-03: the set stays closed at
    six and FR-37 is restated to ask for a status distinct from CONVERGED,
    which two of the six give.

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

[Unreleased]: https://github.com/nevesgeovana/pyflightstream/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.7.0
[0.6.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.6.0
[0.5.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.5.0
[0.4.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.4.0
[0.3.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.3.0
[0.2.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.2.0
[0.1.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.1.0
