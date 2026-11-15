## FAM-RCOEF: the rotor coefficients of every rotor family

<a id="fam-rcoef"></a>

`polars/FAM-RCOEF-P<POL>.csv`, one file per polar whose reference declares a
rotor. One row per point and family INSIDE a rotor (a family of the rotor's
`families_blades` or `families_general`); an airframe family has no row.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block), in its order |
| `FAMILY`, `FAMILY_ID`, `ROTOR_ID` | the family, and the declared id of the rotor it sits in |
| `T`, `Q`, `P` | thrust (N), torque about the hub (N m) and shaft power (kW), in the rotor's frame `R<id>` |
| `CT`, `CQ`, `CP`, `CFZ`, `CFY`, `CMZ`, `CMY`, `ETA` | the rotor coefficients in `R<id>` |
| `TC`, `YC`, `ZC`, `QC`, `NC`, `MC` | the loads over the disc loading |
| `TCA`, `YCA`, `ZCA`, `QCA`, `NCA`, `MCA` | the loads over the airframe loading |
| `CT<f>`, `CQ<f>`, `ETA<f>` | per frame `f` in `W`, `S`, `B`, `R<id>`; `CTR<own id>` repeats `CT` |
| `MESH_FACES` | last |

Thrust is positive forward along the rotor's shaft, whatever sense the
reference declares it in; a rotor declared pointing aft is said once per post.
Every formula, and which values are `NA` at a static point or on a rotor that
does not turn, is on the
[rotor coefficients](../definitions/rotor-coefficients.md#the-rotor-frame-set) page.

The rotor's speed, advance ratio, tip and helical Mach numbers, diameter, disc
area, pitch and toe are in the run block as `RPM<id>`, `J<id>`, `MTIP<id>`,
`MHEL<id>`, `D<id>`, `ADISC<id>`, `PITCH<id>` and `TOE<id>`.
