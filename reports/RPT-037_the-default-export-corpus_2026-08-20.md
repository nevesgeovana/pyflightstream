# RPT-037: the default export corpus, captured small enough to commit (2026-08-20)

Four licensed runs on a synthetic wing produced one committable example of
every export in `PFS-2014.02`'s default set except one, and measured why that
one cannot be captured at all.

It exists because the blocking artefact for `PFS-2014.02` was never code. Six
of the seven `EXPORT_OWED` rows of `results.EXPORT_CONVERSIONS` gave the same
reason, "no observed export captured", and a parser for a format nobody has
observed is a guess.

## THE FIRST FINDING IS THAT A CAPTURE ALREADY EXISTED AND WAS UNUSABLE

A run of 2026-08-17 had already captured twelve formats on 26.123, and its
outputs sat under `_private/exe/exports/captured/`. Nothing was wrong with it;
it simply could not become a fixture, for two reasons that are worth separating
because only one of them is obvious.

The obvious one is size. Its wing carries 25 chordwise and 40 spanwise panels,
which is the mesh a physics reference wants, and its force distribution is
508 KiB and its CSV 215 KiB. A fixture tree does not take half a megabyte per
format.

The one that is not obvious is that `_private/` is where it lived, and tier 1
cannot reach it. So the debt in the classification was real and its stated
reason was stale at the same time: the note said no export had been captured,
and one had. A reader of the classification would have concluded nobody had
tried.

## The runs

All four on the NACA 0012 wing this package generates for its own physics
cases (`qa.geometry.generate_wing_stl`), at **6 chordwise by 6 spanwise
panels**. Synthetic deliberately: a capture on research geometry could never be
committed (invariant 5), which would leave every parser written against it
untestable in tier 1. Coarse deliberately: a parser is pinned by the shape of a
table, its header, its terminator and its column names, and none of those vary
with panel count. **No coefficient in any of these files is evidence of
anything**; the QA references answer for accuracy and run their own converged
meshes.

Script: `scripts/capture_export_corpus.py`, committed, with `--sweeper` and
`--version` for the runs that need them.

| # | Build | Timeout | Solver | Outcome |
|---|---|---|---|---|
| 1 | 26.123 | 1800 s | TIMED OUT | seven exports written in the first 2 s, then 1798 s of nothing |
| 2 | 26.123 | 240 s | TIMED OUT | same seven, one of them repaired (below), same hang |
| 3 | 26.123 | 300 s | exit 0, 0.8 s | the sweeper spreadsheet |
| 4 | 26.122 | 180 s | TIMED OUT | the same seven and the same hang on a second build |

## What was captured

| Command | Fixture | Bytes |
|---|---|---|
| `EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS` | `force_distributions_26.123.txt` | 24969 |
| `EXPORT_ALL_OFF_BODY_STREAMLINES` | `off_body_streamlines_26.123.txt` | 16106 |
| `EXPORT_ALL_SURFACE_SECTIONS` | `all_surface_sections_26.123.txt` | 5682 |
| `EXPORT_SOLVER_ANALYSIS_CSV` | `solver_analysis_26.123.csv` | 9030 |
| `SWEEPER_EXPORT_SPREADSHEET` | `sweeper_spreadsheet_26.123.txt` | 2049 |
| `EXPORT_SURFACE_SECTIONS` | `surface_sections_26.120.txt` | 1984 |

The last is from the 2026-08-20 run recorded in `RPT-036b` and was already
committed.

Against the 2026-08-17 run, the force distribution went from 508 KiB to 24 KiB
and the CSV from 215 KiB to 9 KiB, with the same header, the same column list
and the same terminator.

## SECOND FINDING: THE FIRST RUN PRODUCED A DEGENERATE FIXTURE AND IT LOOKED FINE

Run 1's `EXPORT_ALL_SURFACE_SECTIONS` came back at 1997 bytes carrying
`Edges=0`. Correct title, correct preamble, correct 20-column header, correct
software footer, **zero rows**.

The cause is arithmetic and it is the coarse mesh's own doing: six spanwise
panels over an 8 m span put the panel boundaries at multiples of 1.333 m, so
the section plane at `y = 0` lay exactly on one and cut no edges. Run 2 moved
it to `y = 0.5` and the same command returned 5682 bytes with `Edges=12`.

This is worth a section of its own rather than a line in a table, because a
parser tested against the first file would have PASSED while never having read
a row, and nothing about the file announces that. The script now names the
offset as a constant with the arithmetic in its comment, so the next mesh
change cannot quietly put the plane back on a boundary.

## THIRD FINDING: `EXPORT_BL_VELOCITY_PROFILE` HANGS THE SOLVER

The one format still unobserved, and it is not for want of trying.

The solver accepts the command, prints nothing further, and does not return.
Measured three times, on both builds that document the command, on a mesh that
solves in two seconds:

* run 1, 26.123, 1800 s, probe at `y = 0`;
* run 2, 26.123, 240 s, probe at `y = 0.5`, which rules out the panel-boundary
  explanation that the degenerate section above would otherwise suggest;
* run 4, 26.122, 180 s, which rules out the build.

The viscous solution exists and is reachable by another command in the same
run: `SET_BOUNDARY_LAYER_TYPE TURBULENT` and `SET_SOLVER_VISCOUS_COUPLING
ENABLE` are emitted before `START_SOLVER`, the run converges at iteration 65,
and the surface-section export in the same script carries populated `CF`,
`Delta*`, `Delta` and `H` columns, which are boundary-layer quantities.

The log is what makes this a measurement rather than an inference. `EXPORT_LOG`
is emitted BEFORE this command in run 2 onward, precisely so a hang leaves one,
and it shows the run reaching the command and writing nothing after it. In run
1 the log came last and was therefore never written, which is the whole reason
the order was changed.

**No status was moved.** Invariant 3: `broken` moves only through the
sanctioned probe path with a committed compat report, and three runs of a
capture script are evidence FOR a probe rather than a substitute for one. The
reading this supports is recorded in the local plan ledger, together with what
the probe should test and why a hang is worse for a campaign than an abort: an
aborting command leaves a nonzero status, and this one leaves a run that looks
busy.

## FOURTH FINDING: 26.122 AND 26.123 DO NOT AGREE, AT THE FIFTH DECIMAL

Run 4 was made to answer a question about one export and answered a different
one on the way. It ran the SAME script on the SAME generated geometry against
26.122, so the two output sets are directly comparable, and they are not
identical.

Compared line by line with the software stamp, the date and every absolute
path removed, three of the seven differ in their NUMBERS and four are identical:

| Export | 26.122 versus 26.123 |
|---|---|
| `EXPORT_SOLVER_ANALYSIS_CSV` | byte-identical |
| `EXPORT_ALL_OFF_BODY_STREAMLINES` | identical |
| `EXPORT_PROBE_POINTS` | identical |
| `EXPORT_SURFACE_SECTIONAL_LOADS` | identical |
| `EXPORT_SOLVER_ANALYSIS_SPREADSHEET` | **differs** |
| `EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS` | **differs** |
| `EXPORT_ALL_SURFACE_SECTIONS` | **differs** |

The spreadsheet is the one small enough to quote whole, and it localises the
difference:

    26.123   Cx -0.0037803   CDo +0.0089664   CMy -0.1066443
    26.122   Cx -0.0037889   CDo +0.0089578   CMy -0.1066442

`CL`, `CDi`, `Cz` and the reference quantities agree to every printed digit.
What moves is `Cx` and `CDo`, by about 9e-6 absolute, and `CMy` in the last
digit. Those are the VISCOUS terms, and this case runs with the boundary layer
turned on.

Three things this is and is not. It **is** a measurement: same script, same
geometry, same units, one variable changed. It is **not** a drift verdict, not
a reference update, and not evidence that either build is wrong; a difference
of 9e-6 in a viscous coefficient on a six-panel wing is well inside any band
this repository sets, and the QA references answer for accuracy on meshes this
one has no business speaking for. And it **is not new evidence about the
FORMAT**, which is the question this report was written to answer: every
column, header, terminator and count is the same on both builds, so the
committed fixtures pin a format that both builds write.

It is recorded because the two builds are registered as separate versions and a
reader is entitled to know that the separation is visible in the output rather
than only in the manual. A local plan row carries it to the Tier 3 drift
path, which is where a comparison like this is made properly, on a converged
mesh and against a stored reference.

## What the emitter refused, across all four runs

Recorded because each refusal is a file that would never have appeared and a
seat that would have been spent finding that out:

* `SWEEPER_SET_AOA_SWEEP` with `ENABLE`, which is not one of the three values
  the entry declares (`UNIFORM`, `CUSTOM`, `DISABLE`). Refused with the page
  citation.
* `EXPORT_SURFACE_SECTIONS` is NOT emitted in this script at all, and that is a
  finding carried over rather than an omission: `RPT-036b` observed the solver
  consuming the FOLLOWING LINE as its filename, because the entry declares
  `index: int` alone where the real layout carries a path on its own line.
  Emitting it mid-script destroys the next command.
* The three `RPT-036b` records from the earlier run stand unchanged.

## What this report does NOT do

It promotes no status and edits no command database row. An observed export is
evidence for a PARSER; a status moves only through the probe path. The
classification note for `EXPORT_BL_VELOCITY_PROFILE` is rewritten to carry the
measured reason above in place of "no observed export captured", which is a
correction to a stale sentence rather than a status change.
