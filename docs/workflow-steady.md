# The steady workflow

The `steady` run type, and how one row sweeps the angle of attack or the sideslip.

`steady` is one point of a polar: a uniform free stream, the solver
settings the row's `SET` identifier resolved to, one solve, one loads
export.

## One sweep per row, and the geometry variant that is its own row

A row sweeps ONE thing. The swept key of `FLIGHT_CONDITION` and
`SWEEP_VALUES` sweep the
aerodynamic condition, and a geometric variation of the same
configuration, a rotated blade or a trailing-edge variant, does **not**
multiply with it. A row that asks for both is refused when the file is
read, before a workspace is opened and before a solver is started, and
the refusal names the row, both sweeps and the count of runs they would
have produced.

The rule is the same in a hand-written `campaign.toml`: a `[[sim]]`
declaring a multi-angle `angle_sweep_deg` beside a multi-point `sweep`
is refused when the file loads, which is the moment the case is
declared. Neither door lets in what the other refuses.

## What a row's sweep looks like in `campaign.toml`

`pyfs-matrix convert` writes the row's sweep as one inline table, and a
hand-written file may write the same thing:

```toml
[[sim]]
sim_id = "9001"
sweep = {type = "alpha", values = [-4.0, 0.0, 4.0], held = {beta = 0.0}}
```

`type` is the ONE variable that varies, `values` are its values in
degrees, and **`held` is what the row keeps constant at every point of
the sweep**, in degrees, under the same axis names. `held` is what makes
`ALPHA:sweep, BETA:0.0` in a matrix row and the paired `AL/BE` cell it
replaced plan the same three runs under the same three names: the point's
NAME ends the `run_id`, so a held angle has to reach the point or the
upgrade would rename every run that has one. That was the tag
`a-04.0_b+00.0` until 0.20.x and is `AL-040BE+000` in a cell that declares
those two variables since 0.21.0; what matters here is unchanged, which is
that the held value is part of the point and not only of the row.

It holds the two ANGLES and nothing else. A key that is not a point axis
is refused naming the axes, and so is a `held` entry for the variable the
sweep already varies. An advance ratio the case holds goes in its
variables, where it went before this release.

`held` is omitted when the row holds nothing, so a file written before
0.15.0 loads unchanged. The paired `type = "alpha_beta"` still loads and
is deprecated: write `type = "alpha"` with the sideslip in `held`, which
plans the identical runs.

Write it one of two ways.

- **One rotation, held fixed across the aerodynamic sweep.** Put
  `angle_deg: 5.0` in `VAR_NAMES_VALUES` (or `angle_deg = 5.0` under
  `[sim.variables]`). One value. The row keeps its alpha sweep and stays
  one row.
- **A sweep of the geometry.** One row per angle, each with its own
  `POL` and a single-valued `angle_deg`. Three angles across an eleven
  point alpha sweep are three rows of eleven runs, not one row of
  thirty three.

The limit is about IDENTITY before it is about cost. A run is named by its
FLIGHT CONDITION: a cell declaring `MACH`, `REmi`, `ALPHA` and `BETA` names
two points of an alpha sweep `DP-M200RE230AL-040BE+000` and
`DP-M200RE230AL+000BE+000`, and nothing in either name is geometric.
Crossing three angles into an eleven point sweep would give thirty three
runs eleven names, so each group of three would share one `run_id` and one
set of output file names, and the cost view would average the three into a
single cell. Three rows cost the same thirty three runs and keep thirty
three identities.
