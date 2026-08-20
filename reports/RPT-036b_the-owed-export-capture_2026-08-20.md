# RPT-036b: what one licensed run observed of the owed exports (2026-08-20)

One run on 26.120, synthetic geometry, 0.9 s of solver time. It exists
because `PFS-2014.02` was blocked on FILES rather than on code: six of
the seven `EXPORT_OWED` entries in `results.EXPORT_CONVERSIONS` say "no
observed export captured", and a parser for a format nobody has observed
is a guess.

**AMENDED THE SAME DAY, and the amendment is the sentence above.** Those
notes were STALE: a run of 2026-08-17 had already captured twelve formats
on 26.123, under `_private/`, where tier 1 cannot reach them and where
nothing in the classification pointed at them. This report's own premise
was therefore correct about the notes and wrong about the world, and it
is corrected here rather than quietly. `RPT-037` records the full
picture, including why that earlier capture could not become a fixture
(size, and the tree it lived in) and the corpus that replaces it. What
this report contributes stands unchanged: two formats observed on 26.120,
and the two database findings below, neither of which the earlier run
had surfaced.

## The run

* Build 26.120, chosen over the newest because 26.123 is registered
  `inherits_base: false`, so a command with no 26.123 row is REFUSED
  rather than resolved from the base, and two of the owed seven have no
  such row.
* Geometry: the NACA 0012 wing this package generates for its own
  physics cases (`qa.geometry.generate_wing_stl`, 1.2 MB STL). Synthetic
  deliberately: a capture on research geometry could never be committed
  as a fixture (invariant 5), which would leave every parser written
  against it untestable in tier 1.
* Script: `scripts/capture_owed_exports.py`, 44 lines, one solve and
  five exports.
* Solver exit 0.

## THE EMITTER REFUSED THREE COMMANDS BEFORE THE SEAT WAS SPENT

This is the result worth reporting first, because each refusal was a
file that would never have appeared:

1. `EXPORT_SOLVER_ANALYSIS_CSV` was emitted with one argument. The
   database names five. Refused with the page citation, so the solver
   never got to decide what a one-argument call meant.
2. `EXPORT_BL_VELOCITY_PROFILE` has no recorded evidence on 26.120 at
   all: its only rows are 26.122 and 26.123. Refused by version, and it
   cannot ride this build's run.
3. `NEW_OFF_BODY_STREAMLINE`, the precondition of the streamline export,
   is recorded BROKEN on 26.120 by a committed probe report: script
   processing aborts at the command, and the solver accepts the line, so
   the run would have returned numbers nothing marks as wrong. Refused.

Two more were caught by the phase guard and by argument typing: a
surface section cannot be created after the first export, and
`EXPORT_SURFACE_SECTIONS` takes an INDEX where a path was passed.

## What was observed

| command | result |
|---|---|
| `EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS` | **1724 bytes**, header "Aerodynamic Force Distribution" |
| `EXPORT_SURFACE_SECTIONS` | **1984 bytes**, header "FlightStream Surface Sections" |
| `EXPORT_SOLVER_ANALYSIS_CSV` | file written, **0 bytes** |
| `EXPORT_ALL_SURFACE_SECTIONS` | syntax error, no file |
| `SWEEPER_EXPORT_SPREADSHEET` | no file |

Both observed files are committed as fixtures:
`tests/fixtures/force_distributions_26.120.txt` and
`tests/fixtures/surface_sections_26.120.txt`.

## FINDING 1: `EXPORT_SURFACE_SECTIONS` consumes the NEXT LINE as its filename

The database records one argument, `index: int`. The solver wrote the
section file to a path named `EXPORT_ALL_SURFACE_SECTIONS`, which is the
NEXT COMMAND IN THE SCRIPT, and then failed at line 39 with
"Unrecognized command" naming the path that followed it.

So the command's real layout is an index inline and a filename on the
following line, in the shape `IMPORT_CAD` and `TRAILING_EDGES_IMPORT`
use. The entry is missing an `own_line: true` path argument.

This is why the capture arrived under the wrong name and why the next
export failed: one missing argument in the entry consumed the next
command. It is a database defect with observed evidence behind it, and
correcting it needs the manual page rather than this run alone.

## FINDING 2: the CSV export writes an EMPTY file rather than refusing

`EXPORT_SOLVER_ANALYSIS_CSV` accepted five arguments, reported "Data
written to external text file" in the solver's own log, and produced
zero bytes. A reader of the log alone would record a successful export.

The likely cause is the surface selection: the call passed `-1` for
boundaries, and an empty selection may produce an empty file rather than
an error. Not settled by this run, and stated as unsettled.

## FINDING 3: `SWEEPER_EXPORT_SPREADSHEET` needs a sweeper that this run
never configured

No file and no error. The command belongs to the sweeper family, which
has its own setup sequence; emitting the export without it is a call
with nothing to write. A capture for it needs a sweeper case, which is a
different run rather than another export appended to this one.

## What is still owed, and what each needs

* `EXPORT_BL_VELOCITY_PROFILE`: a run on 26.122 or 26.123.
* `EXPORT_ALL_OFF_BODY_STREAMLINES`: a build where the streamline seed
  is not recorded broken, plus the seed and generate steps.
* `EXPORT_ALL_SURFACE_SECTIONS`: blocked by finding 1 until the entry
  carries the missing argument.
* `EXPORT_SOLVER_ANALYSIS_CSV`: a run with an explicit boundary
  selection, to settle finding 2.
* `SWEEPER_EXPORT_SPREADSHEET`: a sweeper case.

## What this report does NOT do

It promotes no status and edits no command database row. An observed
export is evidence for a PARSER; a status moves only through the
sanctioned probe path (invariant 3). Findings 1 and 2 are candidates for
a probe report, not for a hand edit.
