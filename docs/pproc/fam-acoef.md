## FAM-ACOEF: the airframe coefficients of every family

<a id="fam-acoef"></a>

`polars/FAM-ACOEF-P<POL>.csv`, one file per polar, beside
[FAM-DIM](fam-dim.md#fam-dim). One row per point and family.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block), in its order |
| `FAMILY`, `FAMILY_ID` | as in FAM-DIM |
| `CD<f>`, `CY<f>`, `CL<f>`, `Cl<f>`, `Cm<f>`, `Cn<f>` | for each frame `f` in the order `W`, `S`, `B`, then `R<id>` for every rotor the reference declares, id ascending |
| `CD0`, `CDI` (or `CDV`, `CDP`) | the export's drag split, as it prints it |
| `MESH_FACES` | last |

CD is positive aft and CL positive up in every frame; the moments are about
the moment reference point, right-hand about the frame's forward, right and
down axes ([airframe coefficients](../definitions/airframe-coefficients.md#airframe-coefficients),
[axes and signs](../definitions/axes-and-signs.md#axes-and-signs)). The
coefficients are taken against `q_ref = 0.5 RHO VREF^2`, the export's own
normalisation, so they are finite at a static point.

A family whose induced drag the solver did not compute writes `NA` in `CDI`
and in every coefficient the x force reaches at that point's angles; the
others keep their numbers.

The pproc's `[equations]` of an unsteady row are written as trailing columns
of the TOTAL group's ACOEF file ([group files](group-files.md#group-files)),
before `MESH_FACES`.
