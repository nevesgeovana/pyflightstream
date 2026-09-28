# Boundary-layer products

Choose the products independently in the pproc library file, such as
`inputs/pproc/p001.toml`:

```toml
[products]
boundary_layer_integrals = true
boundary_layer_velocity_profile = false

[[sections.distributions]]
families = "Wing"
frame = "MRP"
planes = ["XZ"]
count = 20
```

The integral request adds its VTK surface and surface-section coordinate exports
to the point's required outputs, including when an export was otherwise disabled.
Planning checks these dependencies before launching a solver. Post writes
`sections/<point>_boundary_layer.csv` and its provenance in `products.json`.
This is the final exported state of that point, with its recorded STEP when
available; it is not an unsteady average or a wall-normal profile.

## What each row means

The product reads the actual cut points exported for the configured sections.
Native section XYZ columns are already in the reference frame. The product restores
the VTK mesh from its recorded loads frame and orients the cut plane using the
recorded section frame and frame-motion evidence. It does not invent the
spacing of a section distribution. Every row identifies a section, a cut point,
and an incident original VTK polygon. `CELL_ID` is zero-based. A cut on a shared
edge produces a row for each incident cell, with `INCIDENT_CELLS` stating the
multiplicity. Overlapping cells are also retained explicitly. No nearest-cell
replacement or cell-to-node interpolation is performed.

The available fields include displacement thickness, momentum thickness, shape
factor, boundary-layer thickness and streamline length, transition/separation
markers, skin friction, normalized vorticity, free-stream Cp, static pressure
ratio and raw Boundary_Index. These are the solver's existing integral/scalar
quantities. The package does not integrate a new velocity profile to derive them.

Scalars preserve the VTK cell values with round-trip floating-point precision.
Missing selected fields are `NA` and are listed in the product manifest. At least
one native thickness or shape-factor field must exist. Coordinates use the simulation length
unit recorded with the frames; the metadata names that unit. Thickness values
are carried unchanged, without an assumed millimetre/metre conversion.
Boundary_Index is carried unchanged and is not converted to a component name or
an assumed one-based inventory index.

## Evidence and unavailable inputs

[The measured VTK report](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-074_the-vtk-export-is-written-in-the-loads-frame-per-cell_2026-09-25.md)
identifies the per-cell variables and the loads-frame coordinate convention on
26.124. That measurement does not by itself establish section-coordinate mapping
for every geometry, moving frame or build. The new product records source hashes,
section layout, actual available fields, coordinate unit and matching tolerance.
A moving frame additionally requires executable-bound timing evidence and the
actual exported STEP.

Missing cut coordinates, a changed recorded output hash, missing placement or
motion proof, incompatible units, or a cut point with no incident VTK cell is a
named skip in post diagnostics. Other products remain available. Historical
records that lack the required frame identities/evidence are not silently
reinterpreted; a new run records them. A small matching tolerance, recorded in
native coordinate units, accounts for export precision. For a warped polygon,
the recorded section plane intersects its original edges and defines the cut
chord. The point must lie on that chord within tolerance; no triangulation or
nearest-cell projection supplies a substitute. Ambiguous multiple chords are refused.

Reused solved 26.124 exports include a translated loads frame and a loads frame
rotated by 90 degrees. They establish the reference XYZ convention and the
cut-plane chord rule for these fixed-frame cases. The acceptance comparison
checks each output scalar against its original VTK cell and checks all four
thickness/shape-factor quantities against the native section table at its
seven-significant-digit precision. It does not extend this evidence to another
build or a moving frame.

## The separate velocity-profile request

Setting `boundary_layer_velocity_profile = true` raises a named configuration
refusal before execution. On 26.122 the command opens a modal dialog requiring a
person to press Done
([RPT-027](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-027_boundary-layer-across-a-proximity-gap_2026-08-17.md));
on 26.124 it prevents an unattended script from completing
([RPT-075](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-075_the-boundary-layer-profile-still-holds-the-script-on-26124_2026-09-25.md)).
No supported build currently has positive unattended-profile evidence. A new
build needs that evidence before the route is enabled. Requesting a profile never
silently produces integrals in its place, including when both flags are true.

## Executable example

[boundary_layer_sections.py](examples/boundary_layer_sections.md) creates a
small synthetic cell/section example and writes the table. It demonstrates raw
value preservation and shared-edge association; its geometry is a mathematical
fixture, not native solver validation. The offline test executes its `main`
function and checks the written values. Workspace users normally select the two
flags in pproc and use the usual plan/run/post flow.
