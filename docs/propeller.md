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
