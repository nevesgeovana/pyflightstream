## FAM-DIM: the dimensional loads of every family

<a id="fam-dim"></a>

`polars/FAM-DIM-P<POL>.csv`, one file per polar, written for every polar of a
steady, unsteady or unsteady-rotor row when `[products] polars` is on (the
default). One row per point and family.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block), in its order |
| `FAMILY`, `FAMILY_ID` | the family's name in the OBJ or FSM and its 1-based position in the boundary inventory ([definition](../definitions/airframe-coefficients.md#family)) |
| `FX_<F>`, `FY_<F>`, `FZ_<F>` | the family's force in N, in the frame `<F>` the loads are stated in (`FX_MRP`) |
| `MX_<F>`, `MY_<F>`, `MZ_<F>` | the moment about the frame's origin in N m |
| `MESH_FACES` | the face count of the geometry, last |

The components are the solver's, with no sign changed
([dimensional loads](../definitions/airframe-coefficients.md#dim)). A steady
row is the loads export of the point: its coefficients times `q_ref SREF`
(forces) and `q_ref SREF CREF` (moments), `q_ref = 0.5 RHO VREF^2`. An
unsteady row is the window average of the run's plots: each family's six
components of the plot group `MRP_<family>`, averaged over the row's window
([the averaging window](../definitions/the-averaging-window.md)).

A family whose loads do not exist on a point (no dynamic pressure, a frame
that is not the geometry's, a record written without the family plots) is a
row of `NA`, never of zeros; the last case is said once, naming the plots the
record lacks.

The polar's number `<POL>` is the matrix row's, as the matrix writes it. The
file holds every point of the polar: the point's condition is in its run
block, so no Mach or sweep token is in the name.
