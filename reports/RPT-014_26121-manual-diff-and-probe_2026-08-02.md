# RPT-014: FlightStream 26.121 onboarding, manual diff and probe evidence

Date: 2026-08-02. Licensed machine, FlightStream 26.121
(`Flightstream_2612.exe`, solver build **#7262026**), compared against
26.120 (same executable name, solver build **#7012026**). Synthetic
geometry only: a generated NACA 0012 rectangular half-wing from the
package's own `qa.geometry` generator. No research geometry is involved.

Produced by the `fts-version-update` skill, steps 2 to 8. Every manual
fact below is a paraphrase with a page citation; no manual text is
reproduced.

## 1. The hotfix carries its own manual edition

This is the finding that reshaped the work, because the onboarding plan
assumed a hotfix might carry none.

The 26.121 install ships `Altair FlightStream User Manual.pdf`, a
different document from the 26.120 edition by content hash. Measured:

| | 26.120 | 26.121 |
|---|---|---|
| manual pages | 410 | 413 |
| scripting reference | pp. 286-371 | pp. 289-374 |
| compiled help (.chm) | differs | differs |
| release notes PDF | identical | identical |

The 26.120 copy is byte-identical to the manual already registered as
SRC-003, so SRC-003 is the 26.120 edition and the new file is a
different one. **Every page citation shifts by exactly +3**, so an
SRC-003 page number does not address the same page in the new edition.

The vendor release-notes PDF is **byte-identical between the two
installs**. It documents none of the changes below. That is the skill's
"vendor release notes are incomplete" rule holding in the strongest
possible form: they are not merely incomplete, they were not reissued.

The new edition has **no source id yet**, so the six commands documented
only in it are not registered. Registered as
`PLN-20260803-0942-the-26121-manual-edition-has-no-source-id`, which
carries the full transcription so the work is a copy, not a re-reading.

## 2. Command surface diff, 26.120 manual to 26.121 manual

Derived mechanically: per-page text extraction of both PDFs, then a set
difference of command-shaped tokens with their page numbers.

### 2.1 New in the 26.121 edition (6)

| command | p. | grammar |
|---|---|---|
| `DELETE_SURFACES` | 315 | inline, one INDEX |
| `DISABLE_SOLVER_REF_VELOCITY` | 342 | bare |
| `CREATE_CYLINDRICAL_BULK_SEPARATION` | 345 | NAME, NUM_BOUNDARIES, DIAMETER |
| `CREATE_STRATFORD_BULK_SEPARATION` | 345 | NAME, NUM_BOUNDARIES |
| `SET_WAKE_DECAY_CONSTANT` | 346 | VALUE, documented as 19.1/L with L in metres |
| `NEW_UNSTEADY_SOLVER_SURFACE_PROBE` | 350 | NAME, PARAMETER, CSYS, X, Y, Z |

### 2.2 Gone from the 26.121 edition (3)

`SURFACE_DELETE` and `SURFACE_CLEARALL` (26.120 pp. 312-313), and
`CREATE_BULK_SEPARATION` (26.120 p. 342). The enum values `FLAT_PLATE`
and `CYLINDRICAL` of the latter's `SEPARATION_TYPE` argument go with it.

### 2.3 Signatures changed on commands already in the database (2)

* `UNSTEADY_SOLVER_NEW_FLUID_PLOT` (26.120 p. 347, 26.121 p. 350) gains
  six boundary-layer values in its PARAMETER enum:
  `BL_MOMENTUM_THICKNESS`, `BL_DISPLACEMENT_THICKNESS`,
  `BL_TOTAL_THICKNESS`, `BL_SHAPE_FACTOR`, `BL_SKIN_FRICTION`,
  `BL_TRANSITION_MARKER`.
* `NEW_SURFACE_SECTION_DISTRIBUTION` (26.120 p. 364, 26.121 p. 367)
  gains an `INCLUDE_SYMMETRY` keyword between `PLOT_DIRECTION` and
  `SURFACES`, documented as extending the sections across mirror and
  periodic representations.

### 2.4 Documented in BOTH manuals and never registered (2)

Found by diffing the new manual against the database rather than against
the old manual, so these are ingestion gaps, not version changes.

* `UNSTEADY_SOLVER_DELETE_ALL_PLOTS` (SRC-003 p. 347). **Registered in
  this change.**
* `UNSTEADY_SOLVER_ANIMATION` (SRC-003 pp. 347-348). **Not registered**,
  because its grammar maps onto none of the five layouts: an inline
  toggle plus a keyword block whose presence depends on that toggle.
  Registered as
  `PLN-20260803-0940-unsteady-animation-needs-a-layout-the-emitter-lacks`.

  This one matters beyond its own row. It takes FOLDER, FILETYPE
  (`SOLVER_BITMAP`, `PLOTS_BITMAP`, `TECPLOT_DATA`, `PARAVIEW_VTK`),
  FREQUENCY in solver time steps, and VOLUME_SECTIONS, which makes it
  **the only documented per-timestep field export in the whole command
  set**. A survey of the 144 registered commands concluded that such an
  export is unreachable from a single script; that conclusion is true of
  the database and false of the solver.

## 3. Manual defects found, in both directions

These are errors in the vendor's document, recorded because the database
is drafted from it and a reader of the citation will meet them.

1. **26.121 p. 346**: the sample under the heading for the Stratford
   bulk separation "all boundary list" invokes
   `CREATE_CYLINDRICAL_BULK_SEPARATION` instead, and with two arguments
   where the cylindrical form takes three. Two defects in one four-line
   sample.
2. **26.121 p. 386** (the function index) spells the same command
   `CREATE_STARTFORD_BULK_SEPARATION`, against `STRATFORD` on pp.
   345-346. This family has now produced three spellings across two
   editions: RPT-012 established that the 26.1 manual's sample blocks
   said `CREARE_BULK_SEPARATION` where the header said `CREATE_`, and
   that the solver accepted only the header spelling. The index is not
   a reliable source for this database.
3. **26.121 pp. 315-316**: `DELETE_SURFACES` declares one parameter,
   `INDEX`, but its samples show `DELETE_SURFACES 2 4 7` under a
   "delete multiple existing surfaces" heading. Whether that is three
   indices or a count of 2 followed by indices 4 and 7 is not
   determinable from the page, and the two readings delete different
   surfaces. A probe question, flagged in the plan item.
4. **26.121 p. 315** names the parameter `iNDEX` in the table and
   `INDEX` in the signature. Cosmetic, recorded for completeness.

## 4. Probe evidence: what the hotfix actually changed

Tier 2 run, 109 probe specifications, `--fsm` a synthetic wing session.

| | 26.120 (`CMP-26120_2026-07-21_full`) | 26.121 (`CMP-26121_2026-08-02_full`) |
|---|---|---|
| verified | 64 | 65 |
| broken | 4 | 3 |
| unprobed | 44 | 75 |

The unprobed count is not comparable between the two runs: this run used
a different, deliberately minimal session file, so more specifications
found no session state to act on. Coverage of the judged set is what the
comparison below rests on.

### 4.1 Working on 26.121, broken on 26.120 (2)

**`AIR_ALTITUDE` is fixed by the hotfix, and it was a units defect.**
On 26.120 the command ran and its `METERS` argument read as ignored: an
altitude of 5000 m produced a density of 1.056 kg/m^3, which is the
5000 **foot** standard state, not the 5000 m one. On 26.121 the same
probe observes 0.736 kg/m^3, the 5000 m standard-atmosphere density.
Anyone who set altitude in metres on 26.120 was flying at the wrong
density, silently.

**`NEW_SURFACE_SECTION_DISTRIBUTION` is fixed by the hotfix.** On 26.120
script processing aborted at the command (the log exported before it
exists, the one after it never appeared). On 26.121 the command
completes and the effect is observed: the all-sections export written
afterwards carries the distribution. Note this is the same command whose
signature gained `INCLUDE_SYMMETRY` in the new manual (2.3): a documented
change and a behavioural fix landing together.

### 4.2 Still broken on 26.121 (2)

`NEW_OFF_BODY_STREAMLINE` and `SET_MOTION_START_TIME`, both with the same
signature as on 26.120: script processing aborts at the command. The
hotfix did not touch either. `SET_MOTION_START_TIME` is load-bearing for
any blade-passage average, since it sets the transient offset that
decides which leading time steps to discard.

### 4.3 Newly measured broken on 26.121 (1)

`SWEEPER_REF_VELOCITY_SAME` aborts script processing. It was unprobed in
the 26.120 full run, so this is a first measurement rather than a
regression; whether 26.120 shares the fault is not established here.

### 4.4 Coverage lost, and why it is not a version finding

`SET_INVISCID_LOADS` was verified on 26.120 and is unprobed here. Its
effect assertion requires the run's viscous default drag to be nonzero
so that enabling inviscid-only can be seen to zero it, and on this
session file it is not. An artifact of the session file, not of the
build.

## 5. Rename checklist for the human (skill step 7)

A rename is engineering judgment and is never decided automatically.
Three suspected renames, none of them applied.

1. `SURFACE_DELETE` + `SURFACE_CLEARALL` -> `DELETE_SURFACES`.
   The evidence for a merge is strong: the new command's samples cover
   both jobs (`DELETE_SURFACES 1` and `DELETE_SURFACES -1`), and both
   old commands vanish in the same edition. The grammar changes as well
   as the name: `SURFACE_DELETE` was a keyword block taking `SURFACE 5`
   on the following line, `DELETE_SURFACES` takes the index inline.
   **Question for the human:** record as one `removed` pair with
   `successor: DELETE_SURFACES`, or as two independent removals?

2. `CREATE_BULK_SEPARATION` -> `CREATE_CYLINDRICAL_BULK_SEPARATION`.
   The cylindrical form is the old command minus its `SEPARATION_TYPE`
   argument, with the type moved into the name. Argument-for-argument
   identical otherwise (NAME, NUM_BOUNDARIES, DIAMETER).
   **Question for the human:** confirm this is a rename rather than a
   coincidence of shape, given item 3 below shares its lineage.

3. `CREATE_BULK_SEPARATION SEPARATION_TYPE=FLAT_PLATE` ->
   `CREATE_STRATFORD_BULK_SEPARATION`. **This is the one that is not a
   naming question, and it needs the domain-expert seat.** The old
   flat-plate variant took a DIAMETER; the Stratford form takes none.
   A Stratford criterion is a turbulent boundary-layer separation
   criterion, which is not obviously the same model as a flat-plate bulk
   separation, and the dropped argument is evidence that the
   parameterisation changed rather than the label. Treating it as a
   rename would silently reinterpret an existing user's model.
   **Question for the author:** is Stratford the flat-plate model
   renamed, or a new separation model that replaces it?

Until these are answered, `CREATE_BULK_SEPARATION` keeps its 26.120
evidence and gains no 26.121 record, which is the honest state: the
database says nothing about it on the new build rather than guessing.

## 6. What this run does not establish

* No 26.121 status is recorded for any command the run left `unprobed`;
  those keep their 26.120 evidence and inherit it through the hotfix
  fallback. The compatibility matrix does not currently distinguish an
  inherited cell from a directly measured one.
* The six commands new in the 26.121 manual were not probed, because
  they are not in the database, because the edition has no source id.
* The unsteady chapter has no probe specifications at all, so none of
  its commands can be promoted past `documented` by any run
  (`PLN-20260803-0941-unsteady-chapter-has-no-probe-specs`).
* The `DELETE_SURFACES` arity question of section 3.3 is answerable by
  probe and was not answered.
