# Propeller definitions

A propeller component accepts `type = "propeller"` and a `definition` table
containing schema 1 data. Lengths in this table use mm, chord and station
positions use fractions of radius, and angles use degrees. The definition is
strict: an unknown key, invalid unit, missing profile or invalid station names
the offending input and refuses the design.

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

The disk solidity is `B/pi * integral(c/R d(r/R))`. The per-blade activity
factor is `100000/32 * integral((c/R)(r/R)^3 d(r/R))`. These integrals cover
the supplied aerodynamic stations, excluding the optional root extension.
The report also gives local solidity and beta at 0.7 R.
