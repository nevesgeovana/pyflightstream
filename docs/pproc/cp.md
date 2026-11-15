## Cp: the pressure coefficient along the sections

<a id="cp"></a>

`sections/<point>_cp.csv` (the default, `[sections] split = "point"`), or
`sections/<point>_FAM-<FAMILY>_cp.csv` per family (`"family"`), or both (`"both"`). One
row per cut point of every section of every distribution, from the solver's all-sections
export. The same key governs the sections table; a Cp file is never one per polar.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block) |
| `FAMILY`, `FAMILY_ID` | the family the section cuts and its 1-based index in the boundary inventory |
| `STEP`, `PLANE` | the solver step and the cutting plane of the distribution |
| `ROTOR_ID`, `AZIMUTH` | the declared id of the rotor whose blades the family is and the azimuth of the block's blade, in degrees; `NA` off a rotor |
| `SECTION` | the index of the cut within its distribution, from 1 |
| <a id="section_direction_value"></a>`Section_direction_value` | the station along the section's own direction, in the simulation's length unit |
| `X`, `Y`, `Z` | the cut point, in the simulation's length unit and in the reference coordinates |
| `nx`, `ny`, `nz` | the unit surface normal at the point |
| `L` | the normalized position along the cut |
| <a id="cp-column"></a>`Cp` | the pressure coefficient against the free stream |
| `Mach` | the local Mach number |
| `vx`, `vy`, `vz`, `vtot` | the velocity at the point, in m/s |
| `Cp_ref` | the pressure coefficient against the reference velocity |
| `Theta`, `CF`, `Delta*`, `Delta`, `H` | the boundary-layer quantities: momentum thickness, skin-friction coefficient, displacement thickness, thickness (the three in the simulation's length unit) and shape factor |

The columns are the export's, in its order; nothing is rescaled. The solver's own
export stays in the run record.
