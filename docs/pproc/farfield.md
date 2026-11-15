## The far-field tables

<a id="farfield"></a>

`farfield/<group>_trefftz.csv`, `farfield/<group>_ledgers.csv` and
`farfield/<group>_rotor_sections_<rotor>.csv`, written for a simulation whose pproc declares
`[[farfields]]` entries; without one nothing is written. `<group>` is the stem of the simulation's
polar tables, so the file stands beside its polars by name. On an unsteady row the Trefftz and
ledger tables are written once more with the suffixes `_instant` (the step the export states) and
`_average` (the window average); the rotor-section table has a `_strips` companion. The spanwise
files of Trefftz A and B are in `sections/`, as `<point>_trefftz_<family>.csv` and
`<point>_trefftz_TOTAL_<entry>.csv`. The definitions are on
[the far-field family](../definitions/the-far-field-family.md), and
[`products.json`](products-json.md) states the unit and the frame of every column.

All vectors are in the far-field axes: x along the free stream downstream, y to the right, z up.
Every table opens with `POL`, `ENTRY`, `STEP`, then the run block
([the run block](../definitions/the-run-block.md#the-run-block)), then the columns below. A cell an
analysis cannot serve is empty and the point is named as a skip in `products.json` and warned in
`post.log`. A rotor column is written only in a table where a rotor row holds a value.

### The Trefftz table

| Columns | Content |
| --- | --- |
| `FAMILY`, `VARIANT` | what the row is of (`TOTAL` for A and B, lowercase `net` for C and D) and the variant letter, `A`, `B`, `C` or `D` |
| `CL_T`, `CDI_T`, `CDI_T_ISOLATED`, `CY_T` | far-field lift, induced drag and side force coefficients, dimensionless; `CDI_T_ISOLATED` the induced drag of the traced family alone |
| `E_T`, `AR` | the span efficiency and the aspect ratio, dimensionless |
| `N_TRACE` | the number of trace stations |
| `X_T_M`, `GAMMA_SCALE`, `COVERAGE` | the plane position in m, the circulation scale and the share of the wake the plane covers |
| `CDI_T_QERR`, `CDI_T_VORT`, `BERNOULLI_RESIDUAL`, `CDI_NEAR_PRESSURE`, `CDI_NEAR_VORTICITY` | the cross-checks of the induced drag |
| `P_AXIAL_W`, `P_SWIRL_W`, `P_CROSSFLOW_W`, `P_TOTAL_W`, `ETA_FF` | the power of the wake in W, and the far-field efficiency |
| `P_TOTAL_CORRECTED_W`, `ETA_FF_CORRECTED`, `T_WAKE_N`, `Q_WAKE_NM`, `T_WAKE_REPAIRED_N`, `Q_WAKE_REPAIRED_NM`, `T_NEAR_N`, `Q_NEAR_NM`, `DT_WAKE_COUNTS`, `DQ_WAKE_COUNTS` | the rotor columns: the disk total-pressure correction and the wake loads, thrust in N and torque in N m |
| `STATUS` | the point's solver termination status, last |

### The ledger table

| Columns | Content |
| --- | --- |
| `LATTICE`, `STATION_X_R` | the survey lattice and the station of the row, in rotor radii |
| `MDOT_KG_S`, `AXIAL_FLUX_N` | the mass flow in kg/s and the axial momentum flux in N |
| `FX_N`, `FY_PLANE_N`, `FY_PLANE_HARMONIC_N`, `FZ_PLANE_N`, `FZ_PLANE_HARMONIC_N`, `FY_LATERAL_N`, `FZ_LATERAL_N` | forces from the balances, in N |
| `TORQUE_NM`, `MY_LOADING_NM`, `MY_ARM_NM`, `MZ_LOADING_NM`, `MZ_ARM_NM` | torque and moments, in N m |
| `E_TOTAL_W`, `E_SWIRL_W`, `E_INDUCED_W` | the energy fluxes, in W |
| `COVERAGE`, `MASS_SPREAD`, `SYMMETRY_FLOOR`, `SPURIOUS_COUNTS` | the quality of the lattice survey |
| `F_NEAR_N`, `F_NEAR_VISCOUS_N` | the near-field force and its viscous part, in N |
| `P_PRIME_CORRECTION_N`, `AXIAL_FLUX_CORRECTED_N`, `FX_CORRECTED_N` | the rotor columns, in N |
| `STATUS` | last |

### The rotor-section table

`farfield/<group>_rotor_sections_<rotor>.csv` and its `_strips` companion hold, with `POL` and
`POINT`, the run block and the columns the rotor-section analysis states for the declared rotor,
and `STATUS` last.

The far-field targets of a polar are also written as trailing columns of the group ACOEF files, see
[the far-field family](../definitions/the-far-field-family.md).
