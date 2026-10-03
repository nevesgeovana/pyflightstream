## The installed-frame copy of a product table

`pyflightstream.post.inflow_tools.to_installed_frame(table)` writes `<table>_installed.csv` beside a product table stated in the ISOLATED frame, the same numbers in the INSTALLED frame, which is the isolated one mirrored through `y = 0`. It never overwrites; the isolated table is the record and this is a second table beside it, unless `out=` names another place for it, and `flip=` names further columns to negate. Applying it to its own output returns the input. A rotor table may open with one alias line that holds no comma; it is kept as it stands.

Blade and family names do not change. Blade `k` of the image wheel, at `+(k - 1) 60` degrees on a six-blade wheel, is blade `k` of the installed wheel, at `-(k - 1) 60`, so a table keeps its row order and its names. The mirror changes sign or maps a column as this table says (a column name is matched case-insensitively at its start, then `_`, a digit or the end of the name; the code reads the same list, `FLIPPED_COLUMNS` and `AZIMUTH_COLUMNS`, and a test holds the two equal):

| column | treatment | why |
|---|---|---|
| `FY` | flip | the force along the mirrored axis |
| `MX` | flip | a moment about an axis in the mirror plane |
| `MZ` | flip | a moment about an axis in the mirror plane |
| `CY[A-Z]*` | flip | the side-force coefficients |
| `CR[A-Z]*` | flip | the roll coefficients, a moment about x |
| `CN[BSW]\d*` | flip | the yaw coefficients of the body, stability and wind axes |
| `CMX` | flip | the coefficient of `MX` |
| `CMZ` | flip | the coefficient of `MZ` |
| `TORQUE` | flip | the sense of rotation reverses in the mirror |
| `RPM` | flip | the signed speed follows the sense of rotation |
| `BETA` | flip | the sideslip angle |
| `CS` | flip | the side-force coefficient |
| `CMN` | flip | the yawing-moment coefficient |
| `AZIMUTH` | azimuth | `psi -> -psi mod 360` |
| `AZIMUTH_START` | azimuth | `psi -> -psi mod 360` |
| `AZIMUTH_END` | azimuth | `psi -> -psi mod 360` |
| `azimuth_deg` | azimuth | `psi -> -psi mod 360` |
| `FX` | keep | along the axis the mirror leaves |
| `MY` | keep | a moment about the normal of the mirror plane |
| `CT` | keep | the thrust coefficient |

The sectional `Fx`, `Fz` and `Moment` are NOT negated by default: the orientation of the section axes is not settled, and negating them on a guess would write a wrong number that looks like a right one. The `flip=` argument names them once it is. Any other column is copied as written.
