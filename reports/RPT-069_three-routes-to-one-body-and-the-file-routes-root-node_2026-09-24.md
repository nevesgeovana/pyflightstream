# RPT-069: three routes to one body, and the node the file route lost at the blade's root (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed test T07 of the 0.27.0 work
**Status:** CLOSED in 0.27.0 (G01, G02: a raw mesh runs through the workflow; the trailing-edge file route initialises the solver, detects its wake-termination nodes and initialises again)
**Affects:** `EXPORT_SURFACE_MESH`, `IMPORT_WAKE_EDGES_FROM_FILE`, `AUTO_DETECT_WAKE_TERMINATION_NODES`, `DETECT_WAKE_TERMINATION_NODES_BY_SURFACE`, on 26.124

## What this settles

0.27.0 lets a matrix row run a raw mesh (an OBJ or STL) through the workflow,
with its unit stated, its trailing edge marked from a points file by default
or by automatic detection when written. The question T07 answers: does the
same body give the same coefficients whichever route brings it to the solver,
the saved simulation it came from, its OBJ with the trailing edge from a
points file, or its OBJ with the trailing edge detected? **It does, to the
print, on a wing and on a twisted blade, once the file route detects its
wake-termination nodes after the solver has initialised.** Before that fix the
blade's file route lost the one termination node at its root, the node that
models the hub, and its loads sat 1.8% (CDi) away.

## What was run

FlightStream 26.124 (build 8172026, executable sha256 68e64e66...), one
detached run at a time, no solver alive before each, every solving script
stating `SOLVER_SET_FARFIELD_LAYERS 5`. The band was committed before the
first solve: 1e-4 relative to each coefficient, or to a floor of 1e-3 where
the coefficient prints smaller (one unit of the loads table's last printed
decimal over that floor).

1. **The OBJ files, exported by the package** (`EXPORT_SURFACE_MESH`, its first
   run on 26.124), one per source, the wing and the blade. Each round trip
   gave the saved simulation's counts (wing 410 vertices and 816 faces, blade
   262 and 520), the same faces in the same order, and every vertex within
   4.6e-9 m (wing) and 6.9e-9 m (blade): the OBJ carries eight decimals.
2. **The eight rows of `matriz_mesh.fs`**, steady but one:

| row | body | route |
|---|---|---|
| 4101 | wing | the saved simulation (control) |
| 4102 | wing | the OBJ, trailing edge from a points file |
| 4103 | wing | the OBJ, trailing edge detected |
| 4104 | wing | the OBJ written in millimetres, detected |
| 4105 | wing | the saved simulation, unsteady (the additional post's point) |
| 4111 | blade | the saved simulation (control) |
| 4112 | blade | the OBJ, trailing edge from a points file |
| 4113 | blade | the OBJ, trailing edge detected |

## What came back

The first run: every route of the wing equalled its control to the print
(CL 0.3293351, CDi 0.0288962, CMy -0.0070039); the millimetre OBJ equalled the
metre one (the import converts); the blade's detection route equalled its
control (CL 0.0001315, CDi 0.023631, CMy 0.0139297); **the blade's file route
did not**: CL 8.94e-5, CDi 0.0232103, CMy 0.0137619, outside the band. All
three blade routes logged 12 trailing edges, the same wake grid (1338 cells,
13 strands) and saved the same 24 trailing-edge flags.

Four one-thing probes, each on a copy of the file route's script with its
outputs redirected:

| probe | the one change | termination nodes saved | loads |
|---|---|---|---|
| convergence | both routes forced to 300 iterations | | the same gap |
| order | the points file's rows reversed | | identical to the file route |
| by surface | `DETECT_WAKE_TERMINATION_NODES_BY_SURFACE 1` in place of the automatic form | none | identical to the file route |
| after initialisation | `AUTO_DETECT_WAKE_TERMINATION_NODES` moved after `INITIALIZE_SOLVER` | one (the root) | identical to the file route |
| initialise again | the same, with `INITIALIZE_SOLVER` repeated after the detection | one (the root) | **equal to the control**, 205 iterations |

The saved simulations of the control and of the detection route carry one
wake-termination node, at the blade's root; the file route's carried none.
After `IMPORT_WAKE_EDGES_FROM_FILE` the solver forms its trailing-edge groups
only when it initialises ("1 trailing edge groups created."), so a detection
run before the initialisation finds no end to mark; one run after it marks
the node but the solver was already initialised without it; a second
`INITIALIZE_SOLVER` clears the first ("Solution cleared. Initialization
removed.") and solves with it.

## What it means for the package

- A raw mesh through the workflow is the saved simulation it came from, on
  both bodies and both trailing-edge routes, and in either unit.
- **The file route now initialises, detects its wake-termination nodes and
  initialises again**; the detection route and a saved simulation are
  unchanged. With that order the blade's file route was run again and
  equalled its control to the print: CL 0.0001315, CDi 0.023631, CMy
  0.0139297. A wing-body marked by file would have lost its junction nodes the
  same way.
- The order is measured on a steady point; unsteady and rotor rows use it
  without a licensed measurement of their own.

## Evidence

The scripts the solver received are `sims/sim_4101` to `sims/sim_4113` of the
tier-3 workspace of this run (4102 and 4112 as re-run on the fixed order; their
first scripts are in the workspace's archive), each stating
`SOLVER_SET_FARFIELD_LAYERS 5`. The checks are `tests/tier3_licensed/test_mesh.py`
and `tests/tier3_licensed/mesh_routes.py` (the band read from its commit);
the order is held offline by `tests/tier1_offline/test_raw_mesh_conditions.py`.

**Verdict: VERIFIED.** Every route of each body gives its control's
coefficients within the committed band, the blade's file route after the
order fix this run found.
