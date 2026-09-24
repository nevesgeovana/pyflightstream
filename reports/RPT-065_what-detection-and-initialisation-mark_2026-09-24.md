# RPT-065: what detection and initialisation mark (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed probe T03 of the 0.27.0 work
**Status:** REGISTERED for 0.27.0 (G02 relies on it: the trailing-edge file is the default route, and a run checks the solver's import count)
**Affects:** how a raw mesh gets its trailing edges through pyfs; the probe specification of `AUTO_DETECT_TRAILING_EDGES`, whose note assumed initialisation detects edges by itself

## What this settles

A raw mesh needs its trailing edges marked before a solve. The 0.27.0 default is a
file of edge mid-points (`IMPORT_WAKE_EDGES_FROM_FILE`, RPT-061); automatic
detection is the second route. Two things were unknown and each decides the
design: whether `INITIALIZE_SOLVER` marks trailing edges on its own, and whether it
re-detects on top of an import. **It does neither. Initialisation alone marks
nothing, keeps a half-span import at exactly its half, and leaves a file that marked
nothing at nothing. So the file route marks exactly what the file names, and a
wrong file reaches the solve with no trailing edge, silently.** Detection marks the
same edges whole or by surface, and the stored blade's twelve.

## What was run

FlightStream 26.124, eleven short runs with no solve, launched one at a time,
detached, with no solver alive before each. Every run opens a clean saved state,
saves it, applies ONE block, and saves again. Any script that initialises states
`SOLVER_SET_FARFIELD_LAYERS 5` first.

    states      W: the tier-3 wing STL (816 faces, 16 trailing-edge edges at x = 1)
                B: the tier-3 blade STL, the same mesh the stored 30_BLADE.fsm was made from
                both imported and saved with no detection
    instrument  the saved mesh block's edge-slot rows turned into edge mid-points;
                offline, the reader gives 16 on the stored 10_WING.fsm and 12 on 30_BLADE.fsm
    build       FlightStream 26.124 (build 8172026, executable sha256 68e64e66...)

## What came back

| run | the one block | edges after |
|---|---|---|
| wing, control | nothing | 0 |
| wing | `AUTO_DETECT_TRAILING_EDGES` | 16, the analytic set |
| wing | `DETECT_TRAILING_EDGES_BY_SURFACE` on surface 1 | 16, the same set |
| wing | `INITIALIZE_SOLVER` alone | **0** |
| wing | import of the 8 mid-points of one half | 8 |
| wing | the same import, then `INITIALIZE_SOLVER` | **8**, the same set |
| wing | a file of that half 0.2 mm aft (marks nothing), then `INITIALIZE_SOLVER` | **0** |
| blade, control | nothing | 0 |
| blade | `AUTO_DETECT_TRAILING_EDGES` | 12, the set 30_BLADE stores |
| blade | sweep angle 10, then detection | 3, a subset of the 12 |
| blade | sweep angle 80, then detection | 12, the same set |

The solver says so in its log: detection prints `N trailing edges marked on surface
<name>`, the import prints `N trailing edges imported for boundary <name>`, and
initialisation prints neither.

## What it means for the package

- The file route can restrict what is marked: initialisation does not add the
  edges detection would find. That is what makes the file the default worth having
  for a twisted blade, where detection by angle picks a different set (3 of 12 at
  10 degrees).
- Initialisation does not rescue a wrong file. A run that imports trailing edges
  must compare the solver's `N trailing edges imported` with the number of points
  it wrote and refuse when they differ, because nothing else will tell.
- The probe specification of `AUTO_DETECT_TRAILING_EDGES` can assert on the saved
  trailing-edge rows instead of the log, since initialisation does not mark them.

## What this does NOT establish

- **One build, two geometries**, both single-boundary. A multi-boundary file
  shares the global face arrays; T04 measures one.
- **What a solve marks.** No run started the solver; whether a solve adds wake
  edges of its own is outside these runs.
- **The default sweep angle's value.** Only that 80 and the default gave the same
  twelve here.

## Evidence

`reports/probes/RPT-065_2026-09-24_evidence.yaml`: per run, the block, the edges
before and after, the solver's lines, and the script's digest; the eight checks
above as booleans; the three blade mid-points kept at 10 degrees. The solver outputs
stayed on the measuring machine (invariant 5).

## Amended 2026-09-24: the probe's note

Nothing above is changed. The note of the `AUTO_DETECT_TRAILING_EDGES` probe
specification (`src/pyflightstream/qa/specs.py`), which every compat report quotes, said
`INITIALIZE_SOLVER` detects edges on its own and that no instrument separates the two.
It now states what this report measured on 26.124, and that the saved-state reader used
here is not yet that probe's assertion: the probe still asserts a line of the log, and a
silent region is still unprobed.
