# Quasi-steady wheel corrections

!!! warning "Not validated"
    Every route on this page is an OPTION, OFF by default, and NOT VALIDATED.
    0.31.0 ships the machine that applies a correction; which route is
    recommended, and with which numbers, is a research question the package
    does not answer. A corrected product says so in its `products.json` entry
    (`"validation": "not validated"`).

A `qsteady_rotor` WHEEL point solves every blade once per clocking, holds the
blades still and turns the free stream (see
[the quasi-steady rotor](post-processing-definitions.md#the-quasi-steady-rotor)).
Its loads carry no lag of the unsteady wake, so its 0P and 1P content may
differ from an unsteady solve. The correction machinery lets you apply a
correction of your own AT POST, beside the raw products and never over them,
and lets you look at the classical lift deficiency as a diagnostic.

Everything here runs at post. Choosing a route, changing it or editing its
calibration never needs a new solver run: `pyfs-matrix post` reads the pproc
and the calibration again every time.

## Choosing a route

The pproc's `[qsteady_correction]` table:

```toml
[qsteady_correction]
route = "table"        # "none" (the default), "table" or "sector_offset"
file = "c001"          # inputs/calibrations/c001.toml ("c001.toml" also names it); required by a route
diagnostic = "none"    # "none" (the default) or "theodorsen"
```

| route | what it is | status |
|---|---|---|
| `none` | nothing is corrected, and no corrected file is written | the default |
| `table` | route 4: a calibration table, a discrepancy surface you fitted over `J`, `ALPHA` and `K_1P` | applied, not validated |
| `sector_offset` | route 2: a 0P offset calibrated from an axial unsteady SECTOR run at the same `J` | applied, not validated |
| `theodorsen`, `sears`, or any spelling asking the lift deficiency | route 1 | REFUSED as a route: offered as a diagnostic only (below), because it is not validated against the unsteady solver |
| `dynamic_inflow`, `skewed_wake`, `pitt_peters`, `coleman` | route 3 | REFUSED: not offered as a correction, because its double counting with the solver's own wake is unmeasured |

A refused route is refused where the pproc is read, with the reason, and the
same words refuse it in a calibration file.

## The calibration file

`inputs/calibrations/<id>.toml`; `pyfs-workspace init` creates the folder. The
file states its `route` (`table` or `sector_offset`), optionally a
`description`, and one `[[rows]]` table per node of its grid:

```toml
route = "table"
description = "a discrepancy surface over J"

[[rows]]
COMPONENT = "THRUST"
J = 0.5
ALPHA = 0.0
K_1P = 0.05
OFFSET_0P = 0.0
GAIN_0P = 1.0
GAIN_1P = 1.0
PHASE_1P_DEG = 0.0

[[rows]]
COMPONENT = "THRUST"
J = 0.7
ALPHA = 0.0
K_1P = 0.05
OFFSET_0P = 0.0
GAIN_0P = 1.0
GAIN_1P = 1.0
PHASE_1P_DEG = 0.0
```

The numbers above are placeholders. A `sector_offset` file must also state
`source_run_id`, the run id of the axial unsteady sector run its offsets were
taken from (and may state `wheel_run_id`); the post warns when that run is not
in the workspace's `runs.json`, and applies the file as it stands.

**The axes.** `J` is the rotor's advance ratio as its rotor table states it,
`J_<ALIAS>`; `ALPHA` is the point's angle of attack in degrees; `K_1P` is the
1P reduced frequency: each station's own `K_1P` for a sectional component, and
the point's `K_1P_MEAN` for a rotor component.

**The components.**

| component | corrects | in |
|---|---|---|
| `THRUST`, `TORQUE` | `THRUST_<ALIAS>`, `TORQUE_<ALIAS>` (N, N m) | the average table |
| `FX`, `FY`, `FZ`, `MX`, `MY`, `MZ` | `FX_<ALIAS>` .. `MZ_<ALIAS>`, the rotor's force and hub moment | the average table |
| `CT` | `CT_<ALIAS>`, and `CT_PROPELLER`, the same quantity | the rotor table, the average table |
| `CQ` | `CQ_<ALIAS>` | the rotor table |
| `CT_ROTOR` | `CT_ROTOR` | the average table |
| `CN`, `CS`, `CMN`, `CMS` | the in-plane coefficients `CN_<ALIAS>` .. `CMS_<ALIAS>` | the rotor table |
| `Fx`, `Fz`, `Moment` | the sectional loads, by the names the export prints | the harmonic product and the sections |

**The grid.** The rows of one component form a TENSOR GRID over the axes whose
values vary: every combination of the values each varying axis takes is one
row. An axis on which a component's rows state one value is CONSTANT and
constrains nothing: the file above applies at any `ALPHA` and any `K_1P`.
Inside the grid the four coefficients are interpolated multilinearly. A point
OUTSIDE the grid on any varying axis is NEVER extrapolated: its corrected cells
are `NA`, and the point and component are named under `skipped` in
`products.json` and in a WARNING line of `post.log`. A point that states no
value on a varying axis (no rotor table row for its `J`, say) is named the same
way. Nothing blocks.

**Refused whole, naming the line.** An unknown route, an unknown component, an
unknown or missing column, a number that is not finite, two rows at one node,
or rows that are not a grid are refused when the file is read
(`pyflightstream.exceptions.CalibrationError`, with the line). The plan reads
the file a row's pproc names and refuses a broken one before a solver runs; the
post reads it again and, where it is refused there, corrects nothing and says
why.

## What a route does

For a component the calibration names, at the point's place in its grid:

- a 0P quantity `q` of the rotor table and of the average table becomes
  `GAIN_0P q + OFFSET_0P`;
- per station, the harmonic product `load(psi) = H0 + A1 cos(psi - PHI1) +
  A2 cos(2 psi - PHI2)` becomes `H0' = GAIN_0P H0 + OFFSET_0P`,
  `A1' = GAIN_1P A1`, `PHI1' = PHI1 + PHASE_1P_DEG` (in `[0, 360)`), and `A2`,
  `PHI2` and `RESIDUAL_RMS` are unchanged;
- each row of the sections (each blade at each clocking, at its own azimuth
  `psi`, its `AZIMUTH`) becomes

      load' = load + (H0' - H0) + [A1' cos(psi - PHI1') - A1 cos(psi - PHI1)]

  the raw row plus the change of its 0P and 1P terms, so the part of the load
  the fit does not explain is kept.

A column derived from a corrected one that the correction does not derive
again is `NA` in the corrected file, never the raw value beside a corrected
neighbour: `CP`, `ETA` and `ETAW` when `CT` or `CQ` is corrected; `CT_ROTOR`,
`CT_PROPELLER`, `LAMBDA_I` and `CHI_DEG` when the thrust is (unless the file
corrects them itself); a strip's `Fx_int`, `Fz_int` or `My_int` when its load
is. The entry lists them under `derived_na`. The per-blade columns of the
average table and the validity columns are the raw ones.

**Route 2 from recorded runs.** `pyflightstream.post.corrections.sector_offset_calibration`
writes a `sector_offset` file from a wheel point and an axial sector point
the post has tabled, both at zero angle of attack and sideslip and at the same
`J_<ALIAS>`:

<!-- skip: next -->
```python
from pyflightstream.post.corrections import sector_offset_calibration

sector_offset_calibration(
    "campaign", wheel_run_id="<wheel run id>", sector_run_id="<sector run id>",
    calibration_id="c002", matrix_stem="campaign",
)
```

It reads both rows of the rotor tables (the sector's row is its window
average, the wheel's the mean of its clockings) and writes, for `THRUST`,
`TORQUE`, `CT` and `CQ`, `OFFSET_0P` = sector less wheel with
`THRUST = CT rho n^2 D^4` and `TORQUE = CQ rho n^2 D^5` of each row, gains 1, a
1P gain of 1 and a phase of 0, at the wheel's `J`, with both run ids recorded.

## The diagnostic

`diagnostic = "theodorsen"` writes `sections/<point>_theodorsen.csv` for each
wheel point that has a harmonic product: per rotor, quantity and station, the
station's `K_1P`, Theodorsen's function `C(k)` (`C_ABS` and `C_PHASE_DEG`) and
Sears's function `S(k)` (`S_ABS` and `S_PHASE_DEG`), next to the measured 1P
amplitude and phase of the harmonic product (`H1_AMP`, `H1_PHASE_DEG`). It is
never applied to any product, with or without a route.

    C(k) = H1(k) / (H1(k) + i H0(k)),        Hn = Jn - i Yn
    S(k) = (J0(k) - i J1(k)) C(k) + i J1(k)   (the gust referred to mid-chord)

with `C(0) = S(0) = 1`. The Bessel functions of orders 0 and 1 are the
package's own (`pyflightstream.post.corrections.bessel_j` and `bessel_y`), a
power series summed in decimal arithmetic below an argument of 30 and Hankel's
asymptotic expansion above it, held to 1e-10 against a reference
implementation in the test suite; scipy is not a core dependency.

## The files written

| file | beside | what |
|---|---|---|
| `polars/P<sim>-<ALIAS>_rotor_corrected.csv` | the rotor table | the rotor table with its components corrected |
| `polars/P<sim>-<ALIAS>_qs_avg_corrected.csv` | the average table | the average table with its components corrected |
| `sections/<point>_harmonics_corrected.csv` | the harmonic product | `H0`, `H1_AMP`, `H1_PHASE_DEG` corrected |
| `sections/<point>_sections_corrected.csv` | the sections | each row corrected by the change of its 0P and 1P terms |
| `sections/<point>_theodorsen.csv` | the harmonic product | the diagnostic |

A corrected file is written only for a table that holds a component the
calibration names. The raw files are byte for byte what the post writes with no
route. Every corrected file ends with two columns, `CORRECTION_ROUTE` and
`CALIBRATION_SHA256`, on every row. Its `products.json` entry has `kind`
`corrected` and names `raw` (the raw file), `route`, `calibration` (the file),
`calibration_sha256`, the grid `cells` used (per point and component, and per
station for the sectional components), `derived_na`, `validation`
(`"not validated"`) and a `note` saying the same; a route 2 entry adds
`source_run_id`. The definitions are in
[the post-processing definitions](post-processing-definitions.md#quasi-steady-wheel-corrections).
