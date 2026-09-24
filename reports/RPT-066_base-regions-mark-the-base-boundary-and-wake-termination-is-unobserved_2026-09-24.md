# RPT-066: base regions mark the base boundary, and wake termination is unobserved (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed probe T04 of the 0.27.0 work
**Status:** CLOSED in 0.27.0 (G02: the base-region route names the base boundary; wake termination stays unverified)
**Affects:** every workflow row carrying `BASE_REGIONS`, which emits `DETECT_BASE_REGIONS_BY_SURFACE` with the index of the boundary the row names; the tier-3 rows 1005, 1021, 4003 and 9001 to 9003 name the body

## What this settles

A body with a flat base needs that base marked as a base region before a solve.
The workflow's `BASE_REGIONS` key emits `DETECT_BASE_REGIONS_BY_SURFACE <index>`
with the index of the boundary the row names, and the manual describes the
argument only as the mesh boundary "to use for marking base regions". **The
argument is the boundary that BECOMES the base region. Given the base boundary's
index, the command marks the base, exactly as automatic detection does. Given the
body's index, which is what a row writing `BASE_REGIONS: Body` emits, it marks
nothing and says nothing.** Wake-termination detection moved nothing on the one
geometry tried, so this run cannot say what it marks.

## What was run

FlightStream 26.124, nine short runs with no solve, launched one at a time,
detached, with no solver alive before each. Every run opens a copy of a saved
geometry, saves it, applies ONE block, and saves again. A script that initialises
states `SOLVER_SET_FARFIELD_LAYERS 5` first.

    geometries  a half wing-body, boundaries [W, B] (RPT-052's mesh)
                the tier-3 20_BODY, boundaries [Body, Base]
    instrument  which lines of the saved file move between the two saves, setting
                aside the header value of order 1e-309 that differs between saves
                (RPT-061); flag rows are counted by their 1s or Ts
    build       FlightStream 26.124 (build 8172026, executable sha256 68e64e66...)

## What came back

| geometry | the one block | what moved |
|---|---|---|
| wing-body | nothing (control) | nothing |
| wing-body | `AUTO_DETECT_WAKE_TERMINATION_NODES` | nothing, and nothing in the log |
| wing-body | `DETECT_WAKE_TERMINATION_NODES_BY_SURFACE 2` | nothing, and nothing in the log |
| wing-body | `INITIALIZE_SOLVER` alone | the initialisation data only |
| body | nothing (control) | nothing |
| body | `AUTO_DETECT_BASE_REGIONS` | one 0/1 row, 0 to 24 faces, and a base-region block named `Base` |
| body | `DETECT_BASE_REGIONS_BY_SURFACE 1` (the Body boundary) | **nothing** |
| body | `DETECT_BASE_REGIONS_BY_SURFACE 2` (the Base boundary) | the same 24 faces and block as automatic detection |
| body | `INITIALIZE_SOLVER` alone | the initialisation data only, no base region |

The by-surface and the automatic states differ in one line of four flags, which
records how the region was made. The faces are the same.

## What it means for the package

- The `BASE_REGIONS` key has to name the boundary that is the base (`Base` on
  20_BODY), and the page that documents the key has to say so. A row naming the
  body gets no base region and no error, and has solved without one since the key
  existed. The tier-3 rows that name the body are wrong under this reading, and the
  fix changes their goldens.
- `AUTO_DETECT_BASE_REGIONS` marks the same faces on this geometry, so it is a
  valid second route for a simple case.
- Initialisation marks no base region by itself.

## What this does NOT establish

- **Wake termination.** On the wing-body, neither detection command moved the
  saved state or printed a line. Either the geometry has no termination nodes to
  find, or it already carries them. A geometry that visibly needs them is owed
  before the command can be verified.
- **One build, one body.** The base-region reading rests on 20_BODY on 26.124.
- **What a solve does** with a body that has no base region. That is physics, and
  this run measured the setup only.

## Evidence

`reports/probes/RPT-066_2026-09-24_evidence.yaml`: per run, the block, how many
lines moved and which flag rows, the solver's lines, and the script's digest; the
seven checks as booleans. The solver outputs stayed on the measuring machine
(invariant 5).

## CLOSED in 0.27.0, 2026-09-24

Nothing above is changed. Both consequences the section "What it means for the package"
drew are now in the package.

- **The `BASE_REGIONS` key names the base.** Its page
  (`docs/workspace-and-workflows.md`, "BASE_REGIONS NAMES THE BASE, NOT THE BODY") says
  the key names the boundary that becomes the base region, never the body that carries
  it, and that a row naming the body gets no base region and no error. The pproc
  artifact's `base_regions`, the builder's docstring and FR-55 say the same. The six
  tier-3 rows that named the body, 1005, 1021, 4003 and 9001 to 9003, now name `Base`.
  Their six goldens were regenerated with `python -m tests.tier3_licensed.offline
  --write`, and each moved by one line, `DETECT_BASE_REGIONS_BY_SURFACE 1` to `2`, the
  index of `Base` in 20_BODY's `[Body, Base]` and 40_PUSHER's `[Body, Base, Blade1]`.
  `tests/tier1_offline/test_tier3_offline.py::test_every_tier3_row_marking_base_regions_names_the_boundary_that_becomes_the_base`
  holds every such row and its golden to it. Nothing offline can tell a base from a
  body, so no row is refused for naming the body; the page says which to name.
- **`AUTO_DETECT_BASE_REGIONS` as a second route** is offered where a raw mesh declares
  its boundary conditions: `[base_regions] detect = "auto"` in its sidecar (the G02
  routing, commit 4caface of this branch).

**Wake termination stays unverified, as this report left it.** The same routing offers
`[wake_termination]` (automatic, or by surface) and emits its command, and the page
states that what the command marks was not observable on the geometry tried. A geometry
that visibly needs termination nodes is still owed before the option can be called
measured.
