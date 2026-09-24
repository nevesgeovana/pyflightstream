# RPT-061: where the wake-edge import reads its nodes (2026-09-23)

**Date:** 2026-09-23
**Found by:** the licensed probe T02 of the 0.27.0 work
**Status:** REGISTERED for 0.27.0 (G02 emits the grammar and writes the file measured here)
**Affects:** `IMPORT_WAKE_EDGES_FROM_FILE` on 26.124; `helpers.mark_wake_edges` and
`workspace.wake_edges.write_node_file` as shipped since 0.8.0, which emit a form this
build refuses

## What this settles

`IMPORT_WAKE_EDGES_FROM_FILE` marks trailing edges from a list of points, and every
edition that documents it (26.122 to 26.124) prints a signature and a sample with
two values, `<TYPE> <TOLERANCE>`, and says nothing about where the list comes from.
The command database recorded that silence rather than inventing a path argument.
This run answers it for 26.124. **The command reads the list from the path on the
line after it, and only when its own line carries a third token. The file is a
count, one coordinate line the solver consumes, then the edge mid-points in the
simulation's length unit.** Neither the grammar nor the file layout the manual
prints is accepted. Given the whole span, the import marks exactly the edges that
angle detection marks.

## What was run

One probe workspace on FlightStream 26.124, 46 short runs with no solve, launched
one at a time, detached, with no solver alive before each. Every run opens the
same saved simulation, a clean wing with no trailing edge marked, saves it, emits
the variant, and saves it again.

    geometry    the tier-3 10_WING mesh: 816 faces, a straight trailing edge at
                x = 1, z = 0, 16 mesh edges on it every 0.5 m of span
    build       FlightStream 26.124 (build 8172026, executable sha256 68e64e66...)
    package     0.27.0.dev0 at 2f3c10e
    instrument  the saved simulation's per-face trailing-edge rows (two 0/1 rows
                and two T/F rows), counted before and after, the edge-type row,
                and what the solver logged between two sentinels
    reference   AUTO_DETECT_TRAILING_EDGES on the same state marks 16 edges (32
                faces), edge type 1
    control     the state saved before the variant, in the same run: 0 edges

Each variant moved one thing from the one before it. The points were computed from
the mesh file and match its 16 trailing-edge mid-points exactly.

## What came back

**The grammar.**

| form | what the solver did |
|---|---|
| `IMPORT_WAKE_EDGES_FROM_FILE VORTEX_SHEDDING 0.0001` (the manual's) | syntax error, script stopped |
| the same, the path on the next line | syntax error, script stopped |
| a third token: the path | `Invalid file format`, the same for a present file and an ABSENT one |
| a third token AND the path on the next line | the file is read |
| `0.0001 VORTEX_SHEDDING ...` (the parameter table's order) | syntax error |

The third form looked like success at first: the solver says it read a file. The
absent-file mutant gives the same words, so what it read was the line after the
command, the probe's own `PRINT` line. That is why nine file layouts tried in
that form all came back `Invalid file format`: none of them was opened. They
measure nothing about the layout and are kept in the evidence as that lesson.

The third token is required and, on everything measured, ignored: `METER`,
`MILLIMETER`, `1`, `0` and a path give the same result. It is **not** the
coordinates' unit. With `MILLIMETER` as the token, a file in metres marks all 16
edges, and the same points written in millimetres mark none.

**The file**, read from the next line.

| file | edges marked |
|---|---|
| count / `METER` / id,x,y,z (the manual's layout) | 0 |
| count / id,x,y,z | 0 |
| count / `METER` / x,y,z | 0 |
| count / `MILLIMETER` or `INCH` / x,y,z in that unit | 0 |
| count / x,y,z, the 8 mid-points of one half | **7**, the first point's edge missing |
| count / x,y,z with the first mid-point written twice | **8** |
| count / an empty line or a bare `0` / the 8 mid-points | 7 |
| count / the 9 end vertices of those 8 edges | 0 |
| count / a placeholder triple / the 16 mid-points | **16**, the same edges as detection |

So the first line holding three numbers after the count is consumed and not used,
empty and one-number lines are skipped, and any line holding a word, the manual's
unit names included, makes the import mark nothing. The points are edge
MID-POINTS, as the command's tolerance parameter says, and not the end vertices
the GUI's import page describes.

**The tolerance and the type.**

| variant | edges marked |
|---|---|
| 8 mid-points moved 0.05 mm aft, tolerance 0.0001 | 8 |
| moved 0.2 mm aft | 0 |
| the whole span with TYPE `STANDARD` / `RELAXED` / `VORTEX_SHEDDING` | 16, edge type 1 / 2 / 4 |

The tolerance is a distance in the simulation's length unit, and TYPE is applied:
the saved edge-type row carries the type's position in the signature's list, and
detection's edges carry 1, `STANDARD`. `JET_OUTFLOW`, 3 by that rule, was not run.

**`TRAILING_EDGES_IMPORT` is removed.** The manual body dropped its page at 26.123
while the Script Index still lists it. 26.124 answers `Unrecognized command`, with
a file present, with a file absent, and with either kind of point.

**A wrong file is silent.** When a file marks nothing, the solver logs nothing:
no error, no count. It logs `N trailing edges imported for boundary <name>` only
when it marks something.

## What it means for the package

- `mark_wake_edges` emits the manual's two-argument line, which 26.124 refuses as
  a syntax error that stops the script. It needs the third token and the path on
  the next line.
- `write_node_file` writes the manual's layout (count, unit, id,x,y,z), which marks
  nothing. It needs count, a consumed coordinate line, and bare mid-points in the
  simulation's unit, converted when the points are given in another unit, since
  the file's unit is not read.
- Because a wrong file is silent, a run that imports trailing edges has to compare
  the solver's `N trailing edges imported` with the number of points it wrote and
  refuse when they differ. An exit code cannot tell.

## What this does NOT establish

- **One build.** 26.124. 26.122 and 26.123 document the same two-argument line and
  are not measured, so the file route is claimed on 26.124 only and refused before
  26.122.
- **What the third token is.** It is required and nothing measured here depends on
  its value.
- **Whether the count is read.** Given N points and N + 1 coordinate lines, the
  import marked all N, and given N lines it marked N - 1. Reading N + 1 lines and
  reading to the end of the file both fit. The writer emits N + 1 lines, which is
  right under either.
- **One geometry.** A straight trailing edge on a wing. A twisted blade, the case
  the route exists for, is T07's run.
- The manual's grammar and layout disagreeing with the build goes to the vendor
  as a question (OPS-2003.05).

## Evidence

`reports/probes/RPT-061_2026-09-23_evidence.yaml`: for each of the 46 runs, what it
moved, the harness outcome, the edges marked, the edge type, the solver's first
line after the begin sentinel with local paths removed, and the digest of the
script it ran. The solver outputs stayed on the measuring machine (invariant 5).
