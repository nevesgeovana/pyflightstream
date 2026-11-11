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
`options.trailing_edge` is `blunt` or `sharp`; `te_thickness` specifies the
blunt gap as a chord fraction. `root_cap` and `tip` are `planar` or `none`.
`root_extension_r_R` copies the first section farther inboard.
If every source section has a zero trailing gap, its naturally sharp edge
closes directly and no zero-area trailing face is written.

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

Export uses the library IGES writer, with both spatial and parameter-space
trim curves and PREF 1. The runner checks written pcurves against the spatial
trim at `1e-4 mm`, face counts and areas after reimport, and free and triple
edges after sewing at `0.01 mm`. Open ends are permitted only when requested
with `root_cap = "none"` or `tip = "none"`. Numerical closure uses exact
shared patch edges at `1e-6 mm`.

Optional tip laws are `skew_tip_deg` or `skew_tip_s_R`, and `rake_tip_x_R` or
`rake_tip_deg`, with powers defaulting to 2. The law is
`tip * ((r/R - first_station)/(1 - first_station))**power`. A column and a tip
law for the same displacement cannot be combined. Optional `[frame]` vectors
are `blade_dir`, `thrust_dir`, `rotation_dir_at_blade`, and
`pitch_axis_point_mm`; directions must be orthogonal.
