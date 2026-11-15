## Sections: sectional loads

<a id="sections"></a>

`sections/<point>_sections.csv` (the default, `[sections] split = "point"`), or one file
per family, `sections/<point>_FAM-<FAMILY>_sections.csv` (`"family"`), or both
(`"both"`). Written for every point that cuts sections. Any other value of `split` is
refused, naming the three; a sections file is never one per polar.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block) |
| `FAMILY`, `FAMILY_ID` | the family the distribution cuts, as the OBJ or FSM names it, and its 1-based index in the boundary inventory |
| `STEP` | the solver step the distribution was sampled at |
| `PLANE` | the cutting plane of the distribution |
| `ROTOR_ID` | the declared id of the rotor whose blades the family is (0 for a rotor that declares none); `NA` off a rotor |
| `AZIMUTH` | where the block's blade is at `STEP`, in degrees; `NA` off a rotor |
| `Offset`, `Chord`, `X_QC`, `Z_QC` | the station's offset, chord and quarter-chord point, in m |
| `Fx`, `Fz` | the sectional forces, in N/m |
| `Moment` | the sectional moment, in N m/m |
| `Strip_length`, `Fx_int`, `Fz_int`, `My_int` | optional: the strip length in m and the strip integrals in N and N m |

The loads are in the section frame of the distribution, stated in
[`products.json`](products-json.md). The definition of record, with how each row is
told from its neighbours, is
[the sections table](../definitions/the-sections-table-and-which-row-is-which.md#the-sections-table-and-which-row-is-which).
