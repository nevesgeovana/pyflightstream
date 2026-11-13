# Parametric aircraft geometry

A parametric configuration describes an aircraft by a few parameters per component: a body of
revolution or a superellipse body, a lifting surface with its sections, and the fairing between
a wing and its body. Five `pyfs-workspace geometry` verbs generate an IGES from it, check a
rebuilt surface against an original, mesh it into quads, identify a lifting surface of an
original IGES and print the schema of the parameter record. Everything that needs the geometry
kernel uses gmsh, which installs with the package; where the library cannot load, each verb stops
with a message naming it and writes nothing. The schema verb needs no kernel.

## The configuration

A TOML file with one table per component under `[components]`. Every value is resolved with
its source (`given` or `default`), so a result can say which numbers you stated; the quantities
computed from them (area, mean chord) are kept apart under `derived`.
A parameter this release does not know warns and is skipped: it appears under `warnings` in what
`generate` and `mesh-generated` print and in the resolved configuration. Python reads the file with
`pyflightstream.geometry.load_config` and `resolve_config`.

```toml
[components.WING]
type = "lifting_surface"
[[components.WING.stations]]
eta = 0.0
section = { kind = "naca", code = "0012" }
[components.WING.planform]
sref_m2 = 0.24
aspect_ratio = 6.0
taper = 0.5
le_sweep_deg = 15.0
```

A lifting surface is given by one complete planform set: `sref_m2`, `aspect_ratio` and `taper`
(the span, semispan and chords follow), or `semispan_mm`, `root_chord_mm` and `tip_chord_mm`. The
semispan includes the tip cap. A file that mixes the two sets is refused with the redundant keys
named. A file may also be written as `[surface]`, `[planform]`, `[[stations]]`, `[cap]`,
`[[control]]` and `[[engine]]` tables with no `type` and no `components` table; `[surface]`
makes it a lifting surface. Control `eta` values are fractions of the planform semispan,
including the tip cap; control limits must remain inside the skin before the cap.
Flat tip and root caps use three quadrilateral faces sharing an interior point.
Their outer edges preserve the skin's exact section curve. The default wing
above exports six faces; use `--until S11.P` to include the reader-profile check.
A body is written with `length_mm`, `nose = {kind}`, `tail = {kind}`, `parts` and
`sections` whose shapes carry `half_width_mm`, `half_height_mm` and `centre_z_mm`. A section may be
given as a `bspline` (inline `degree`, `knots`, `poles`, or `file` naming a JSON file with those
three), a `naca` (`code`), a `cst` or a `coords` file. A key that the verb reads but whose feature
is not generated yet
(a `[[bay]]` list, a cap template, a tabulated flap cove) warns by name and is skipped.

## Generate

```text
pyfs-geom run wing.toml --out out --until S11
```

The exposed skin of every component is generated as B-spline patches, assembled by surface
fragment (a component inside another leaves its hidden part out, with a transition ring where a
wing meets a body), audited for free and non-manifold edges and written as one IGES with one
NAME per component on its own level, in metres, so `iges-grid` and the solver's CAD import read
the components back. `--configuration NAME` generates only the components of an entry of the
`[configurations]` table. A wing and body assembly takes about a minute. Python:
`pyflightstream.workspace.geometry_pipeline.run_geometry` with `until="S11"`.

`run` executes the stages S0 to S13 in order (`--until` ends earlier; a run to S9 needs no
kernel), writes one record per stage and `report.json`, and stops at the first failed check: the
report names that stage and check with the value measured and the limit, and the exit code is 1.
An input the pipeline refuses exits 2 with the reason. A run where no check failed but a check
of the stage table was not measured (a stage this version does not build yet) is `incomplete`,
exit 3, and its report lists each such check under `not_run`; only a run that measured every
check is `accepted`, exit 0. `--set component.key=value` overrides one
value (an unknown name is refused). `pyfs-geom doe wing.toml sets.toml --out out` runs one report
per `[[sets]]` table of the second file and continues after a failed set, each in a worker
process of its own. `pyfs-geom stages` lists the stages and their checks, `validate` prints every
resolved value with its source and `configurations` lists the registry.

## Plain controls

Plain flaps and ailerons cut stationary and moving pieces from the same lifting
skin. Span gaps shorten the moving piece at both ends; the chord gap translates
it aft, and each deflection produces a separately named piece. This numerical
example creates two deflections without loading the CAD kernel:

```python
from pyflightstream.geometry import resolve_config, stages

config = resolve_config({"components": {"wing": {
    "type": "lifting_surface",
    "planform": {"sref_m2": 4.0, "aspect_ratio": 4.0, "taper": 1.0},
    "root": "flat",
    "cap": {"type": "flat"},
    "control": [{
        "name": "flap", "kind": "plain", "eta": [0.2, 0.7],
        "chord_ratio": 0.25, "gap_span": 0.01, "gap_chord": 0.002,
        "deflection_deg": [0, 15],
    }],
}}})
wing = stages.unpack(config)["components"]["wing"]
pieces = stages.controls.build(wing)
assert set(pieces.pieces) == {"main", "flap-d0", "flap-d15"}
```

Use these component tables in a TOML file and run `pyfs-geom run wing.toml
--out out --until S10.F4` to write and check the control pieces. F0 compares
written and read face counts; F1 and F2 check sewn closure; F3 measures clearance
to configured body hosts; F4 checks the combined angle choices. F5 and F6 use
the trimmed body and engine cuts and compare their free edges and junction
lengths with an independently assembled clean reference. A failed reference
stops the applied cut.
An applied variant exports each selected combination of control positions
separately, with its own manifest and source identity. The export checks run
for every position. S13.R regenerates the stored B-spline sections without a
fit; reverse identification of an applied assembly is reported as unsupported.
Sewn control check IDs include their sub-step, for example
`control.f1.free_edges` for the main piece and `control.f2.free_edges` for the
control alone, so records and run logs identify the failing operation.

To edit an existing normalized polynomial lifting skin, put the same control
entry in a `[[control]]` table in `controls.toml` and run:

```text
pyfs-geom add-control-surface source.igs WING controls.toml --out edited.igs
```

The Python equivalent is `add_control_surfaces(source, "WING", entries, target)`
from `pyflightstream.workspace.geometry_pipeline`. The source skin uses u=0 and
u=1 at the trailing edges, u=0.5 at the leading edge and v along the span.
Native cuts preserve existing trims and unrelated faces. Entries need disjoint
span intervals strictly inside (0, 1), and rigid deflection needs a straight
hinge. The destination must differ from the source. Read the returned `status`
and `checks`: writing a file alone does not establish sewn closure at 0.01 mm.

## Check against an original

```text
pyfs-geom check rebuilt.igs original.igs --chord-m 0.27
```

The distance is measured in two directions on sampled points: forward, from the original to the
rebuilt surface everywhere, and reverse, from the rebuilt surface to the original inside the
original's trimmed boundary (samples whose nearest point lies on a trim edge are left out and
counted). The limit is the named profile `study_default`: the larger of 0.5 mm and 0.1 percent
of the local chord. The numbers are sampled upper bounds, not continuous Hausdorff distances,
and the record says so under `method`. Exit 0 means accepted, 1 rejected, 2 refused.
Python: `check_against_original`.

## Mesh

```text
pyfs-workspace geometry mesh-generated wing.toml --obj wing.obj --component WING
```

Each patch is meshed from its role: constant width across the span with a refined tip, growth
along the chord from the leading edge, a constant azimuth and axial step on a body, a planar
all-quad flat tip cap (one planar face bounded by the tip section outline: both sides and, for a
blunt trailing edge, the base segment; every tip cap is this face unless `cap.type` names
`rounded`, `ridged` or `exact_loft`) and, for a wing on a body, the fairing as one quad-dominant transition
ring (the only triangles). The orientation is outward and the record carries the acceptance
checks: inverted and degenerate cells, non-manifold edges, free edges off the symmetry plane and
the spacing rules measured on the realized nodes. The OBJ has one group per component. The OBJ
is written and the exit is 0 even when a check fails, so read `accepted` and
`spacing_rules.passed` in the record. Python:
`mesh_generated`.

## Mesh from per-component controls (strategy 1)

```text
pyfs-workspace geometry mesh wing-body.toml --controls mesh.toml --dry-run
pyfs-workspace geometry mesh wing-body.toml --controls mesh.toml --out meshes --fsm-template fresh.fsm
```

The mesh controls hold a `[mesh]` table (`strategy = 1`, `configuration`, `variant` clean, cs or
csf, `iges`, `output.descriptor`), a `[defaults]` table (`lifting_surface`, `body`, `quality`,
`transition`) and one `[components.<name>]` table per member. A primary or flexible lifting
surface states `chordwise` and `spanwise`, each with at least `cells` and `law` (error E15);
the other keys come from `defaults.lifting_surface`. A body takes `x_cells` or `x_step_m`, and
`azimuth_cells`, `azimuth_step_deg` or `azimuth_rule` (the count from the largest half
perimeter over `target_aspect` times the axial step, raised to a multiple of the body's half
sectors; the realized band quads are then measured against `aspect_band`). The body's station
lines at the wing root (and at a fairing end, when it is a station) must fall on the axial
step for the spacing rows to pass. A fairing or fillet with no table follows its hosts.
Membership comes from `mesh.configuration` and the component names from the 406 names of
`mesh.iges` (the generated names when it is absent): a table naming a component outside the
configuration is warned (W01) and ignored, one naming no IGES component is refused (E04).
`chordwise.hinge_rows` pins node rows at those chord fractions without changing the cell
count. `trailing_edge = "collapsed"` with `collapse_tolerance_m` closes the blunt base to one
line of nodes in the mesh only; the default blunt base is left one quad across, whatever the
number of faces it was generated as.

A body carrying a wing is cut at the root leading and trailing edges. A fairing end is a cut
too only when its footprint leaves the end at an angle to the ring there (`start_exponent` or
`end_exponent` of 1 or more): the default rounded nose and tail (0.5) are tangent to the ring,
and a cut through them would leave two fuselage faces with a cusp.

Next to the fairing, each wing and fuselage face is one block of the layout crossed or bounded
by the junction curve. A block that keeps four corners (none sharper than 20 degrees), with the
junction as one curved side, is meshed structured like the rest of its component; any other
(five corners, a cusp, a junction that is not single valued) is meshed with the fairing,
quad-dominant, so the wing and fuselage stay full grid and the fairing adapts. The record lists
each such face with its decision and reason (`junction_faces`). A face of the fairing zone
whose mesh holds an inverted cell or a corner sine under 0.02 is meshed again with the next
quad-dominant algorithm (frontal-Delaunay for quads, frontal-Delaunay, Delaunay, MeshAdapt);
the record keeps each pass's defective faces (`ring_algorithm_history`). A tip cap may be
quad-dominant: its triangles and nodes are left out of the triangle and irregular-node rows and
reported apart.

`--dry-run` validates, prints each component's counts and the warnings, and writes nothing. A
run measures the acceptance table on the realized mesh: inverted and degenerate cells, edges
used by more than two cells, free edges off the symmetry plane, quad aspect (the cell across a blunt trailing-edge base is exempt from the limit and reported with
its count and largest aspect) and skew outside
the transition components (`defaults.quality`), triangles only in transition components under
their `max_triangle_fraction`, irregular nodes inside a structured surface, the spacing laws,
the distance to the source, each follower sharing a curve with every neighbour it follows,
surfaces only, and the cells across each trailing-edge base. A limit that is not given is
recorded as skipped with its measured value. `--out` writes `<descriptor>.obj`,
`<descriptor>.mesh.json` (controls hash, plan, counts, every check, `accepted`, the hashes of
the files) and, with `--fsm-template`, `<descriptor>.fsm`: the template's blocks with its mesh
block replaced, one boundary per component, quads as partner triangle pairs, and the trailing
edges marked. The template must be a fresh saved simulation with no base region,
trailing-edge group or termination. Exit 0 planned or accepted, 1 not accepted, 2 refused.
Python: `mesh_configuration`.

## Mesh as one structured grid (strategy 2)

A matrix row with `MESH_ROUTE` `full_grid` meshes its generated configuration by strategy 2
from controls with `strategy = 2`. Every face of the fragmented configuration becomes a block:
its four sharpest corners make four sides, and a face trimmed by a junction keeps the junction
curve as one side even when the curve is cut in several pieces, which builds the collar around a
wing root and the topology around a footprint from the faces themselves. One cell count per
edge is solved for the whole configuration: opposite sides of every block equal (E09), the
lifting root ring holding `2 chordwise.cells` plus the base cells on every side (E08, or
`[[junctions]] ring_count` when given), the body azimuth ring holding its count (`azimuth_cells`,
or `azimuth_rule`, which derives it from the measured half perimeter and `x_step_m` and splits
it over the body's sectors by arc length), and the cell width carried across every junction
under `defaults.junction.max_growth`, 1.2 when not given (E10). A component's `blocks` table
names its topology (`O` for a body, `C` for a lifting surface, `collar` for a fairing or
fillet, `H`, `cap`) and its poles (`valence3` or `open`; any other is refused, E11). Any
triangle allowance in the controls is refused (E07).

Each block is meshed transfinite and recombined. A face with fewer than four corners is
meshed with quads from an even boundary and listed by name as not full grid. The record
measures triangles (E07), opposite sides (E09), carry growth (E10), the ring count on each side
of every lifting root junction (E08), the valence 3 poles at the body closures (E11), the other
irregular nodes, the not-full-grid faces, inverted and degenerate cells, edges used by more
than two cells (each with the faces holding them), the distance to the source (a planar face,
such as the one-face tip cap, against its plane) and surfaces only. A collapsed edge of a face
(the cap's leading-edge side) bounds no cells and takes no count. The one-face tip cap is meshed
apart from the blocks on its rim nodes, quad-dominant as in strategy 1: its triangles are
reported under E07 (`tip_cap`) and left out of the triangle and irregular-node rows. The matrix
route calls it.

## Identify a lifting surface

```text
pyfs-geom identify original.igs WING --config-out wing-found.toml
```

The trimmed faces of the component are cut by planes normal to the span axis. The clean
stations are classified (one closed airfoil contour, smooth chord and thickness trends), the
planform is built between the root and the outermost clean cut, and a CST section is fitted at
the root, the middle and the tip. The root is the symmetry plane (`--root plane`), the point
where the extended leading edge meets a host (`--host`) or the span extent of the original's own
boundary curves (`--root boundary`). A coarse and a fine pass must agree within stated
tolerances for the result to be `accepted`, and each section states whether its residual met its
tolerance; a station that is not one airfoil is recorded with its reason and left out, never
repaired. The exit is 0 whether or not the result is accepted, so read `accepted` in the record;
2 is a refusal. `--config-out` writes a configuration that `generate` reads back, with the seed's
section, not the fitted one. This release
identifies lifting surfaces only; bodies, rings and propellers are not identified. Python:
`identify_lifting_surface`.

## The component record

`pyflightstream.geometry.ComponentRecord` is the contract between a reconstruction and this
library: stations, the split points of each section curve (IGES type 126 curves pinned by file,
SHA-256 and entry number), the construction method, the trailing-edge base and the measured
deviation. `pyfs-geom schema` prints its JSON Schema, and
`pyfs-geom schema --validate RECORD --asset-root DIR` checks a record and re-reads every file it
pins against its SHA-256 (exit 1 when a pin fails).

## From a matrix row, through the solver's CAD import (`native`)

A row with `GEOMETRY` naming a `.geom.toml` and `MESH_ROUTE` `native` generates the configuration
to the IGES and its conversion check (`--until S12.C`; the library's own gridding of the reader,
S12.G, is not asked, because the solver meshes the IGES itself) and writes a geometry
instruction beside it: a `[cad]` source over the IGES in `FILE` units. `pyfs-matrix run` builds
the `.fsm` with the solver before it binds the rows, once, for every native row whose `.fsm`
is missing; `plan` spends no licence. The solver is told `IMPORT_CAD` and `CONVERT_CAD_TO_MESH -1`
and reads the IGES directly, with no `iges-convert` pass.

The solver names the one body it converts `Model 0`, whatever the components of the IGES are:
the component names are not boundaries of the saved simulation. A boundary name cannot carry a
space, so the instruction renames `Model 0` to the file's stem (`[[operations]]` `rename`), and
that is the boundary the row's references use.

The solver's own tessellation leaves triangles of zero area along the seams of the source faces
(a fan at the vertex where the leading-edge end of a tip cap collapses, slivers along a patch
edge) and a pair of slivers folded on an edge two patches share. Gate G1 of the build audit
would refuse them, so for a `[cad]` source the build reads the IGES and passes G1 only when every
such face lies, every point of its sides, on one edge of a source face (or has two nodes on one
source vertex) and every such edge lies on a source edge; the build record names them by the
source faces. "On" means within 1e-3 of the mesh size (the diagonal of its bounding box) of the
CAD curve itself, measured exactly, so a chord across a curved edge is not taken for the edge.
A zero-area face with a point off every source edge, or any other failed gate, still fails:
nothing is
promoted, the row is recorded as `GEOMETRY_FAILED` with the gate named, and the other rows run.
The measured behaviour of build 26.127 is in `tests/tier3_licensed/data/g13-native-import.json`.
`run_matrix` and the grouped run build the missing native geometry; `pyfs-matrix plan` binds
nothing for such a row until it is built, so build once with `pyfs-workspace geometry build NAME
--apply` (and `geometry accept NAME` after looking at its preview), then plan and run.
