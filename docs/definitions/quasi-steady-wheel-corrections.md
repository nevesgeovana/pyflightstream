## Quasi-steady wheel corrections

!!! note "NOT VALIDATED"
    The machine that applies a correction to a `qsteady_rotor` wheel's
    products at post, beside the raw ones. Every route is off by default and
    none is validated; the choice of a route and of its numbers is research's.
    The user's page is [Quasi-steady wheel corrections](../qsteady-corrections.md).

**What asks for it.** The pproc's `[qsteady_correction]` table: `route`
(`none`, the default; `table`, route 4; `sector_offset`, route 2), `file` (the
id of `inputs/calibrations/<id>.toml`, required by a route) and `diagnostic`
(`none`, the default, or `theodorsen`). Route 1 (the Theodorsen and Sears lift
deficiency) is refused as a route and offered as the diagnostic only; route 3
(`dynamic_inflow`, `skewed_wake`, `pitt_peters`, `coleman`) is refused, its
double counting with the solver's own wake being unmeasured. It applies to the
WHEEL points of a simulation and to nothing else; a simulation of quasi-steady
points none of which is a wheel is named under `skipped`
(`qsteady_correction#sim=<sim>`).

**It is read from the WRITTEN products**, after the post has written them, and
never writes over one: each corrected product is a new file,
`<name>_corrected.csv`, beside its raw file, and the raw file is byte for byte
what a post with no route writes.

**The calibration and its grid.** Each row of the file names a component, its
place on the axes `J` (the rotor table's `J_<ALIAS>` of the point), `ALPHA`
(the point's, deg) and `K_1P` (the station's for a sectional component, the
point's `K_1P_MEAN` for a rotor component), and the coefficients `OFFSET_0P`,
`GAIN_0P`, `GAIN_1P` and `PHASE_1P_DEG`. The rows of one component form a
tensor grid over the axes whose values vary; an axis with one value is
constant and constrains nothing. The coefficients are interpolated
multilinearly inside the grid; a point outside it on a varying axis, or stating
no value on one, is NEVER extrapolated: its corrected cells are `NA`, named in
`skipped` (`<corrected file>#point=<point>#component=<C>` for a rotor table or
an average table, `<corrected harmonics>#component=<C>` for a station) and in a
WARNING line of `post.log`. A file the post cannot read corrects nothing,
named under `calibrations/<id>.toml#sim=<sim>`.

**The corrected products**, for a component the calibration names:

| file | the change |
|---|---|
| `polars/P<sim>-<ALIAS>_rotor_corrected.csv` | `CT_<ALIAS>`, `CQ_<ALIAS>`, `CN_<ALIAS>`, `CS_<ALIAS>`, `CMN_<ALIAS>`, `CMS_<ALIAS>`: `q' = GAIN_0P q + OFFSET_0P`; `CP`, `ETA` and `ETAW` `NA` where `CT` or `CQ` is corrected |
| `polars/P<sim>-<ALIAS>_qs_avg_corrected.csv` | `THRUST_<ALIAS>`, `TORQUE_<ALIAS>`, `FX_<ALIAS>` .. `MZ_<ALIAS>`, `CT_PROPELLER` (by `CT`), `CT_ROTOR`: the same; `CT_ROTOR`, `CT_PROPELLER`, `LAMBDA_I` and `CHI_DEG` `NA` where the thrust is corrected and they are not |
| `sections/<point>_harmonics_corrected.csv` | per station: `H0' = GAIN_0P H0 + OFFSET_0P`, `H1_AMP' = GAIN_1P H1_AMP`, `H1_PHASE_DEG' = H1_PHASE_DEG + PHASE_1P_DEG` in `[0, 360)`; `H2_AMP`, `H2_PHASE_DEG` and `RESIDUAL_RMS` unchanged |
| `sections/<point>_sections_corrected.csv` | each row, blade `n` at clocking `i` at its `AZIMUTH` `psi`: `load' = load + (H0' - H0) + [A1' cos(psi - PHI1') - A1 cos(psi - PHI1)]` with the station's fit as the harmonic product wrote it; `Fx_int`, `Fz_int`, `My_int` `NA` where their load is corrected |

A station whose 1P harmonic is `NA` is corrected in its 0P term only, and the
entry says how many cells. A column no component names is carried raw.

**Every corrected file** ends with `CORRECTION_ROUTE` and `CALIBRATION_SHA256`
on every row. Its `products.json` entry: `kind` `corrected`, `raw`, `route`,
`calibration` (the file, relative to the workspace), `calibration_sha256`,
`cells` (each point, component and, for a section component, station, with the
grid values bracketing it on each varying axis and the one value of each
constant axis), `derived_na`, `validation` `not validated`, a `note`, and
`source_run_id` (and `wheel_run_id`) for route 2. A route 2 file's
`source_run_id` that is not a run of `runs.json` is a WARNING line and the file
is applied as it stands.

**The diagnostic**, `sections/<point>_theodorsen.csv`, for a wheel point with a
harmonic product: `POL`, the condition (the harmonic product's), then `ROTOR`,
`QUANTITY`, `STATION_R_M`, `R_OVER_R`, `K_1P` (the station's, from the
sections), `C_ABS` and `C_PHASE_DEG` of `C(k) = H1(k) / (H1(k) + i H0(k))`,
`Hn = Jn - i Yn`, `S_ABS` and `S_PHASE_DEG` of
`S(k) = (J0(k) - i J1(k)) C(k) + i J1(k)` (the gust referred to mid-chord),
phases in degrees in `[-180, 180]`, `C(0) = S(0) = 1`, then the measured
`H1_AMP` and `H1_PHASE_DEG`. Entry: `kind` `theodorsen`, `source` (the harmonic
product), `diagnostic`, `validation`. It corrects nothing.
