## The installed-frame copy of a product table

`pyflightstream.post.inflow_tools.to_installed_frame(table)` writes `<table>_installed.csv` beside a product table stated in the ISOLATED frame, the same numbers in the INSTALLED frame, which is the isolated one mirrored through `y = 0`. It never overwrites; the isolated table is the record and this is a second table beside it, unless `out=` names another place for it, and `flip=` names further columns to negate. Applying it to its own output returns the input. A rotor table may open with one alias line that holds no comma; it is kept as it stands.

Blade and family names do not change. Blade `k` of the image wheel, at `+(k - 1) 60` degrees on a six-blade wheel, is blade `k` of the installed wheel, at `-(k - 1) 60`, so a table keeps its row order and its names. The mirror changes sign or maps a column as this table says (a column name is matched case-insensitively at its start, then `_`, a digit or the end of the name; the code reads the same list, `FLIPPED_COLUMNS` and `AZIMUTH_COLUMNS`, and a test holds the two equal):

| column | treatment | why |
|---|---|---|
| `FY` | flip | the force along the mirrored axis |
| `MX` | flip | a moment about an axis in the mirror plane |
| `MZ` | flip | a moment about an axis in the mirror plane |
| `CY[A-Z]*` | flip | the side-force coefficients |
| `CR(?!EF)[A-Z]*` | flip | the roll coefficients, a moment about x (never `CREF`, the reference chord) |
| `CN[BSW]\d*` | flip | the yaw coefficients of the body, stability and wind axes |
| `CMX` | flip | the coefficient of `MX` |
| `CMZ` | flip | the coefficient of `MZ` |
| `TORQUE` | flip | the sense of rotation reverses in the mirror |
| `RPM` | flip | the signed speed follows the sense of rotation |
| `BETA` | flip | the sideslip angle |
| `CS` | flip | the side-force coefficient |
| `CMN` | flip | the yawing-moment coefficient |
| `Y` | flip | a position along the mirrored axis: a point at +y appears at -y (class: position) |
| `VY` | flip | the y component of a velocity (class: polar vector) |
| `VORTICITY_[XZ]` | flip | the x and z components of a vorticity (class: axial vector) |
| `AZIMUTH` | azimuth | `psi -> -psi mod 360` |
| `AZIMUTH_START` | azimuth | `psi -> -psi mod 360` |
| `AZIMUTH_END` | azimuth | `psi -> -psi mod 360` |
| `azimuth_deg` | azimuth | `psi -> -psi mod 360` |
| `FX` | keep | along the axis the mirror leaves |
| `MY` | keep | a moment about the normal of the mirror plane |
| `CT` | keep | the thrust coefficient |

The sectional `Fx`, `Fz` and `Moment` are NOT negated by default: the orientation of the section axes is not settled, and negating them on a guess would write a wrong number that looks like a right one. The `flip=` argument names them once it is. Any other column is copied as written.

**The post writes the copies of the inflow tables.** `[products] installed_frame` in the pproc is a list of families from `probes` and `inflow` (default empty; any other name is refused when the pproc is read, naming these two). For `probes` the post writes `probes/<point>_probes_installed.csv` beside each probes table; for `inflow` it writes `<stem>.inflow_installed.dat` beside each reusable inflow profile (`fields/<stem>.inflow.dat`), the six columns `x y z vx vy vz` read as `X Y Z VX VY VZ`. Each copy is the mirror through `y = 0` by the one classification above, so a probe at +y appears at -y, its `VY` changes sign and its vorticity's x and z components change sign, while every other column is copied as written. Mirroring a copy again returns the source.

The classes are three: a POSITION (`Y`) and a POLAR vector (a velocity `VY`, a force `FY`) change the sign of the y component; an AXIAL vector (a moment, a vorticity) changes the sign of its x and z components; an azimuth maps `psi -> -psi mod 360`. A column the classification cannot place is copied unchanged and named once per simulation in `post.log`; the columns the probes table carries by construction (its spine, the condition and reference columns, the fluid parameters and the solver's own probe export) are placed and never named.

Each copy is listed in `products.json` with `"kind": "installed_frame"` and its source table in the entry's `source` field.

The copy is the isolated-frame table mirrored, blade `k` staying blade `k`. It holds where the installed configuration is the mirror image of the simulated one, and it asserts nothing about a flow that is not (a wake, a body or a rotor that is not mirror-symmetric).
