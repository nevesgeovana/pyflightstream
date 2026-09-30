# CCS geometry

A matrix row can name a CCS file (Component Cross-Section, the solver's
parametric geometry format) in its `GEOMETRY` cell. The solver then makes the
mesh itself, from the cross-sections of the file, with its CCS commands: a
wing, a fuselage or a body of revolution lofted from one component, or every
component of the file imported whole. Nothing is meshed by hand and no saved
simulation is needed.

The file carries the `.csv` or the `.ccs` extension; the manual states both,
and the extension only routes the file.

## The sidecar table

Beside the CCS file, in the same folder of `inputs/geometries/`, the sidecar
`<stem>.boundaries.toml` states the boundary names and an `[import.ccs]` table
under `[import]`, the table every imported geometry uses:

```toml
boundaries = ["WING"]

[import]
units = "METER"

[import.ccs]
kind = "wing"
component = 1
```

and the row names the file:

```text
... | VAR_NAMES_VALUES: GEOMETRY: wing.csv
```

`kind` chooses the route:

| `kind` | what the solver does | `units` |
|---|---|---|
| `wing` | lofts one component as a wing | the unit of the file's coordinates, such as `METER` |
| `fuselage` | lofts one component as a fuselage | the same |
| `revolution` | revolves one component's profile about an axis | the same |
| `file` | imports every component whole (`CCS_IMPORT`) | `FILE`: the file states its own `Units` line |

A loft names the component by `component`, counted from 1 in the order of the
file's `Component` lines, and the boundary it makes takes the first name of
`boundaries`. The file route makes one boundary per component, named after its
`Component` line, so `boundaries` lists those names in the file's order.

## The keys of each kind

| key | kinds | values | default |
|---|---|---|---|
| `component` | wing, fuselage, revolution | an integer from 1 | none: required |
| `mark_trailing_edges` | wing | `true` or `false` | `true` |
| `trailing_edge` | wing | `SHARP`, `BLUNT`, `BLEND`, `OPEN` | `SHARP` |
| `close_ends` | wing, fuselage, revolution | `TRUE`, `OPEN`, `CLOSED` | `TRUE` |
| `loft_u` | wing, fuselage, revolution | `C2` or `C0` | `C2` |
| `loft_v` | wing, fuselage, revolution | `C2` or `C0` | `C0` on a wing, `C2` otherwise |
| `subdivisions` | wing | `{ chord = <n>, span = <n> }` | the solver's own |
| `control_surfaces` | wing | an array of tables, below | none |
| `axis` | revolution | `X`, `Y` or `Z` of the reference frame | `X` |
| `start_angle_deg`, `end_angle_deg` | revolution | degrees | `0.0` and `360.0` |

On a wing `loft_u` is the chordwise continuity and `loft_v` the spanwise one; on
a fuselage and a body of revolution they are the radial and the axial ones. A
key written under a kind that does not read it is refused when the row is
planned, never ignored.

The body of revolution turns about `axis` through the origin of the reference
frame: the route runs before any frame of the run exists.

## Control surfaces of a CCS wing

A wing declares its gapped control surfaces as
`[[import.ccs.control_surfaces]]`, one table each, and each becomes one
`NEW_CCS_WING_CONTROL_SURFACE` line before the loft:

```toml
[[import.ccs.control_surfaces]]
name = "AIL"
v0 = 0.5
v1 = 0.9
u0 = 0.25
u1 = 0.25
hinge_height = 0.5
angle_deg = 20.0
slot_gap_pct = 1.0
space = "PARAMETRIC"
axis = "Y"
```

`v0` and `v1` are the inner and outer spanwise limits, parametric between 0 and
1 (or, with `space = "REAL"`, coordinates along `axis` of the reference frame);
`u0` and `u1` the chordwise depths from the trailing edge, above 0 and below
0.5; `hinge_height` runs from the upper surface (0) to the lower one (1);
`slot_gap_pct` is a percentage of span. The line always carries all ten
arguments, `space` and `axis` included. A value outside these ranges is refused
when the row is planned.

If the control surfaces add boundaries of their own, list them after the wing's
name in `boundaries`; the wing is always the first name.

## The shedding direction of a relaxed trailing edge

A component of a CCS file can declare relaxed-Kutta trailing edges with a line
`Relaxed_TE;u;v1;v2;direction`, whose last value is the direction of the relaxed
wake's parametric shedding line: `0` axial (the default) or `1` azimuth. The
direction exists only in the file, so a row chooses it on the file route:

```text
... | VAR_NAMES_VALUES: GEOMETRY: body.csv / CCS_SHEDDING: AZIMUTH
```

with `kind = "file"` and `units = "FILE"` in the sidecar. `CCS_SHEDDING` takes
`AXIAL` or `0`, `AZIMUTH` or `1`. The run imports its own copy of the file,
`<stem>.ccs_shedding.<ext>` in the folder the point runs in, with every
`Relaxed_TE` line restated in the row's direction; your file is never edited.
A line stating no direction keeps stating none when the row asks for the axial
direction, which it already means.

`CCS_SHEDDING` is refused on a loft, whose relaxed trailing-edge commands take
no direction, and on a file with no `Relaxed_TE` line.

From Python, `pyflightstream.script.helpers.parse_relaxed_trailing_edge` reads
such a line, with or without the `Relaxed_TE` keyword: three values, or four
with the direction.

## What is refused

Each refusal names the row and what to write instead:

- a CCS file whose sidecar has no `[import.ccs]` table;
- an `[import.ccs]` table beside a file that is not a CCS file;
- a loft whose component the file does not hold, whose sidecar names no
  boundary or more than the loft and its control surfaces make, or whose
  boundary name carries a space;
- `units = "FILE"` on a loft, and `units = "OTHER"`, which names no length;
  any unit but `FILE` on the file route;
- boundaries on the file route that are not the file's components in order;
- mesh operations or an `[import.cad]` table beside `[import.ccs]`;
- the raw-mesh tables `[trailing_edges]`, `[wake_termination]` and
  `[base_regions]` beside a CCS file: a wing loft marks its own trailing edges
  with `mark_trailing_edges`, and a file states `Mark_trailing_edges` itself;
- a setup that loads a saved solver initialization, since the route creates a
  new mesh.

## What has been measured

On FlightStream 26.124 a licensed probe round accepted each route in isolation:
the wing, the fuselage and the body of revolution lofted by the curve route
each saved a simulation listing the new boundary, the chordwise subdivisions
changed the wing's face count, and `CCS_IMPORT` imported a three-component file
with one boundary per component. The two shedding directions of the same
fuselage saved simulations that differ in the per-face marks of the relaxed
trailing edge. The eight-argument control-surface line was refused there, which
is why the package writes all ten arguments. A run through a whole campaign row,
the control surface in its ten-argument form and the effect of the shedding
direction on a solution are still to be confirmed on a licensed run; the change
log of the release says which of them were.
