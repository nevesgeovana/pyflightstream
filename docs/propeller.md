# Propeller definitions

A propeller component accepts `type = "propeller"` and a `definition` table
containing schema 1 data. Lengths in this table use mm, chord and station
positions use fractions of radius, and angles use degrees. The definition is
strict: an unknown key, invalid unit, missing profile or invalid station names
the offending input and refuses the design.
Resolved records label embedded radii in mm, pitch in degrees and skew and
rake in their declared column units. Supplied and default values retain
distinct provenance.

The definition contains `propeller`, `stations`, `airfoils`, `options` and
`output` tables. Supply at least four increasing `r_R` stations with equal
length `c_R`, `beta_deg`, `t_c` and `airfoil` arrays. A profile is identified by
one of `naca` (four digits), `file` (coordinates), or `cst` (upper and lower
coefficient arrays). File paths are relative to the input TOML.

The Python facade exposes `Propeller`. `Propeller.from_toml(path)` reads a
standalone schema 1 definition. `Propeller(config)` takes the same mapping;
the keyword constructor accepts station rows or columns. `blade()` and
`rotor()` return numerical B-spline patches in mm. `report()` measures the
numerical checks with their thresholds. `to_toml(path)` writes the design.

`with_pitch(degrees)`, `with_skew(values, units="deg")`, and
`with_rake(values, units="x/R")` return independent designs. A displacement
can be a scalar, an array with one value per station, or a callable of r/R.
Skew also accepts `s/R`; rake also accepts `deg`.

Beta is measured from the propeller plane. A constant pitch offset makes the
cubic not-a-knot beta law equal `pitch_setting` at `pitch_reference_r_R`.
The default blade points along +z, thrust is -x, and `positive_x` rotation
moves the blade along -y. Positive skew moves opposite rotation; positive
rake moves aft. Skew rigidly rotates each planar section around the shaft.
Rake translates it axially after scale and pitch. The stacking point defaults
to the section area centroid, with optional `x_ref` and `y_ref` chord fractions.

Sections use degree-five B-splines on a common vector. Their pole rows are
interpolated with a cubic not-a-knot spline in r/R, yielding C2 continuity.
The loft includes the pitch reference and 0.7 R as actual planar sections
when they lie within the supplied radial range. Their profiles and parameter
columns use cubic interpolation. Beta checks measure the resulting chord.
`options.trailing_edge` is `blunt` or `sharp`; `te_thickness` specifies the
blunt gap as a chord fraction. `root_cap` and `tip` are `planar` or `none`.
`root_extension_r_R` copies the first section farther inboard.
If every source section has a zero trailing gap, its naturally sharp edge
closes directly and no zero-area trailing face is written.
Mixed profile tables may have different trailing gaps. An uncapped rim is
checked against the actual sharp or blunt section at that end.

The disk solidity is `B/pi * integral(c/R d(r/R))`. The per-blade activity
factor is `100000/32 * integral((c/R)(r/R)^3 d(r/R))`. These integrals cover
the supplied aerodynamic stations, excluding the optional root extension.
The report also gives local solidity and beta at 0.7 R.

To write and check the full rotor through the standard geometry runner:

```python
from pyflightstream.geometry import Propeller
from pyflightstream.workspace.geometry_pipeline import run_geometry

p = Propeller.from_toml("docs/examples/propeller/simple_naca.toml")
p = p.with_pitch(31).with_skew(lambda r: 20 * r**2).with_rake(0.03)
report = run_geometry(p.component(), out="build/propeller")
print(report["status"], report["outputs"].get("iges"))
```

Use `p.component(blades="one")` for one blade. `output.blades` in TOML also
selects `one` or `all`. The runner's `out` folder selects the destination;
the definition's `output.iges` is a suggested standalone filename, not a path
that can override the runner's destination. Geometry in the API uses mm;
component placement and workspace surfaces use metres.

The same workflow from the CLI is:

```console
pyfs-geom run docs/examples/propeller/simple_naca.toml --out build/propeller
pyfs-geom run docs/examples/propeller/skewed_naca.toml --out build/skewed
```

`--until S8` runs the numerical checks without loading the kernel. A
propeller-only run selects the applicable propeller and export sub-steps;
it does not run the lifting-surface mesh workflow. Each sub-step writes its
inputs, measured checks, thresholds and timing to a stage JSON record and
`geom-run.log`. The first failed check stops the run and is named in the
returned report.
Handedness and section planarity are checked at every defining station;
the reference station cannot mask a reversed inboard or outboard section.

Propeller groups are exported in mm. The live kernel model remains in metres.
Export uses the library IGES writer, with both spatial and parameter-space
trim curves and PREF 1. The runner checks written pcurves against the spatial
trim at `1e-4 mm` for an iso trim (`propeller.pcurve_3d`) and at the `0.01 mm`
sewing tolerance of the assembly junctions for a curved junction edge
(`propeller.pcurve_3d_junction`): the blade-root cut of a spinner and the root
hole of a hub face. A trim declares its junction edges when it is built, so no
edge is classified by its measured value. The runner also checks face counts
and areas after reimport, and free and triple edges after sewing at `0.01 mm`.
Open ends are permitted only when requested
with `root_cap = "none"` or `tip = "none"`. Numerical closure uses exact
shared patch edges at `1e-6 mm`.

Optional tip laws are `skew_tip_deg` or `skew_tip_s_R`, and `rake_tip_x_R` or
`rake_tip_deg`, with powers defaulting to 2. The law is
`tip * ((r/R - first_station)/(1 - first_station))**power`. A column and a tip
law for the same displacement cannot be combined. Optional `[frame]` vectors
are `blade_dir`, `thrust_dir`, `rotation_dir_at_blade`, and
`pitch_axis_point_mm`; directions must be orthogonal.

## Spinner

An optional `[spinner]` table in the same definition builds the spinner with
the blades. Without it the definition builds as before. Lengths are in mm and
axial positions are measured aft along the shaft from
`frame.pitch_axis_point_mm`.

| key | unit | default | meaning |
|---|---|---|---|
| `shape` | | `"ellipse"` | `ellipse` (semi-ellipse), `ogive` (tangent ogive, when stated) or `points` (meridian file) |
| `radius` | mm | required, not with `points` | radius of the cylinder and of the rim |
| `nose_length` | mm | required, not with `points` | axial length from the nose pole to the end of the nose |
| `cylinder_length` | mm | 0 | constant-radius length aft of the nose |
| `nose_x` | mm | required | axial position of the nose pole |
| `points` | file | | meridian `x r` rows in mm, x aft from the pole, first row `0 0`; relative to the TOML |
| `scale` | | 1.0 | homothetic factor of the whole spinner about its rim centre |
| `aft` | | `"base"` | `base` (planar disk at the rim, a closed shell) or `open` (rim left free for a nacelle) |
| `hub_band` | mm | derived | `[front, aft]` axial positions of the two cuts bounding the hub region |
| `hub_margin_R` | R | 0.038 | without `hub_band`: the blade root footprint widened by this fraction of R on each side |
| `circle_tol` | mm | 1e-3 | largest radial deviation of the azimuth from the true circle |

The meridian runs from a blunt pole to the rim: the nose law, tangent to the
cylinder at the shoulder, then the cylinder. A `points` meridian is
interpolated by a cubic spline in arc length. The spinner is one bicubic
B-spline surface skinned once: u along the meridian, v a periodic azimuth
whose poles are one sector's poles rotated, so the closed surface is N-fold
symmetric. The azimuth is non-rational; the fewest poles per sector that keep
the circle within `circle_tol` are used and the deviation is recorded.

Knot insertion to full multiplicity cuts the surface at the two hub band
stations (faces `nose`, `hub`, `aft`, plus `base` with `aft = "base"`) and
at N seams midway between blades, N the blade count: seam k lies at
`phi_0 + 180/N + 360 k/N`, with `phi_0` the azimuth of blade 1's root
stacking point, so every blade is centred in its sector. Sector 1 is computed
and sectors 2 to N are its control nets rotated by `360 k/N`, as the rotor
copies its blades. One blade gives two halves with seams at 90 and 270 deg.
Faces are `spinner_<i>_nose`, `spinner_<i>_hub`, `spinner_<i>_aft` and
`spinner_<i>_base`, sector i holding blade i.

The spinner dominates the blades. Each blade is cut along its exact
intersection with its hub face, the blunt trailing edge included, and loses
its root cap; the hub face loses the inside of the blade root as an inner
loop. The cut is made once, on blade 1 and hub face 1, and rotated with the
sectors. The root section must lie inside the spinner and the junction must
clear the band cuts and the seams by more than `0.01 mm`; otherwise the input
is refused with the value it needs.

`Propeller.spinner()` returns the spinner patches of every sector in mm, its
record (`info`) and the junction trims. `output.blades = "all"` writes the N
blades and every spinner face; `"one"` writes blade 1 and spinner sector 1
with its seams free, the piece `pyfs-mesh sector-to-wheel` copies. The runner
writes `<component>.spinner.json` beside the IGES: the resolved inputs with
their provenance, the band, the seam azimuths, the circle deviation, the
continuity measures and the checks.

The checks, in S8.P and S11.PS:

| check | measure | limit |
|---|---|---|
| `spinner.periodic_net` | sector k's control net turned by 360/N against sector k+1's | 1e-6 mm |
| `spinner.periodic_surface` | the same on a 41 by 41 grid per face | 1e-6 mm |
| `spinner.seam_shared` | sector k's end seam edge against sector k+1's start seam edge | 1e-6 mm |
| `spinner.split_exact` | split faces against the global surface | 1e-9 mm |
| `spinner.circle` | radial deviation from the circle | `circle_tol` |
| `spinner.continuity` | normal jump on band cuts and seams; pole and shoulder tangency | 1 deg |
| `spinner.junction_in_band` | junction clearance to band cuts and seams | more than 0.01 mm |
| `spinner.junction_gap` | blade-side and hub-side images of the junction | 0.01 mm |
| `propeller.pcurve_3d_junction` | written pcurve image against the spatial trim, junction edges only | 0.01 mm |
| `spinner.periodic_reimport` | written faces turned by 360/N against the neighbour sector | 0.01 mm |

A definition without a spinner records them skipped; with one blade the two
periodic checks are not applicable. The tangent ogive reaches the axis at a
finite angle, so its pole passes the 1 deg tangency only when it is nearly
hemispherical; `ellipse` always gives a blunt pole.

```console
pyfs-geom run docs/examples/propeller/spinner_naca.toml --out build/spinner
```

## Slicing an existing propeller

`pyfs-mesh prop-slice` reads a propeller OBJ or IGES and writes the definition above
that rebuilds it:

```console
pyfs-mesh prop-slice --geometry rotor.igs --blades 3 --out sliced_igs
pyfs-mesh prop-slice --geometry rotor.obj --blades 5 --stations 0.25 0.4 0.55 0.7 0.85 1.0 --out sliced_obj
```

The folder holds `propeller.toml` (schema 1, read by `Propeller.from_toml`),
one normalized profile per station in `sections/sNN.dat` (leading edge at
0, trailing-edge midpoint at 1, upper surface from the trailing edge to the
leading edge, then the lower), `table.csv` and the record `prop-slice.json`.
A folder that already holds any of these is refused and nothing is written;
`--overwrite` (`overwrite=True`) replaces them.
The table gives, over r/R, `c_R`, `beta_deg`, `t_c`, `camber` (the largest
mean-line ordinate in chords), `te_gap_c`, `skew_deg` and `rake_x_R`. From
Python, `pyflightstream.workspace.prop_slice.slice_propeller` does the same
and returns the record.

The measures use this page's definitions, so the output rebuilds the
geometry it was cut from:

- The axis is the thrust direction `--axis` (default `-1 0 0`) through
  `--origin` (mm, default 0). Blade 0 is the blade nearest `--blade-dir`
  (default `0 0 1`), and skew is measured from that direction. A frame other
  than the default is written as `[frame]`. The rotation sense is measured:
  the leading edge faces the motion.
- Each station is cut by a plane, not a cylinder: the plane at distance `r`
  from the shaft whose normal is the blade direction rotated by the station's
  skew, which is where the builder places a planar section. The skew is found
  by iteration until the section's area centroid, the default stacking
  point, lies on that plane's radial line; a cylinder would bend the section
  and bias its chord and pitch.
- The chord runs from the trailing-edge midpoint to the leading edge, the
  point farthest from it. The ends come from the extreme pair of the
  section, the rounder end being the leading edge. When the widths of the
  two ends at 5 percent of the chord differ by less than 5 percent of the
  wider (two equally sharp or round ends), the end ahead in the blade's
  motion sense is the leading edge, so `beta_deg` stays continuous along the
  span; the motion sense is the one measured from the reference section, as
  the inputs carry no rotation. A section whose pitch then comes out beyond 90
  degrees in magnitude (the end behind in the motion was taken for the leading
  edge, as when the two end widths miss the tie by a few percent) is turned about
  its mid-chord, so the end ahead leads. A propeller section's pitch is taken in
  (-90, 90] in the rotor frame: a feathered or reversed blade beyond 90 degrees
  is not supported by prop-slice, which reports it folded into that range. A blunt base is the run
  of section steps at more than 45 degrees to the chord next to the far end.
  `beta_deg` is the chord line's angle from the propeller plane, `t_c` the
  largest thickness at equal x, rake the centroid's aft distance over R.
- The blades are counted between 0.55 and 0.75 of the tip radius and must
  equal `--blades`. The radius is the largest distance of the blade from the
  shaft along its tip direction, so a planar tip cap gives it exactly. The
  root is the innermost such distance of the blade surface; a hub or a
  spinner, whose normals have no azimuthal part, is excluded. The default
  stations are 21 equal steps from the root to the tip, and 0.7.
- The root and tip cuts stay 0.2 percent of the radius inside the blade, so
  they cut no cap; the table at a station beyond them is extrapolated from
  the cuts by a cubic in r/R, and the row records the cut it came from.
- An OBJ is cut as its polygons (unit `--unit`, default mm). An IGES is
  imported by the gmsh kernel in a worker process, triangulated with
  curvature refinement, and every section point is projected alternately
  onto the nearest face and back onto the plane, so its sections lie on the
  exact surfaces.

A round trip on a three-blade built propeller with chord, twist, thickness,
skew and rake all varying along the span (tested) recovers, at every station:
chord, thickness and camber within 0.5 percent of the tip chord, beta within
0.1 deg, skew arc and rake within 0.5 percent of the radius from an OBJ of
161 by 121 points per surface, and five times closer from the IGES. The
rebuilt blade lies within 0.5 percent of the tip chord of the original (0.1
percent from the IGES). Measured on that propeller, both inputs recover chord
and thickness within 0.03 percent of the tip chord, beta within 0.01 deg and
skew and rake within 0.005 percent of the radius; the dense OBJ is as close as
the IGES, whose sections lie on the exact faces whatever their triangulation.

Missing files, other suffixes, a blade count that is not a positive integer
or that differs from the blades found, and a surface where no closed blade
section is found are refused by name and nothing is written.
