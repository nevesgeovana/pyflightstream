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

The same restriction applies to ordinary Python `SimCase` construction.

## A matrix sweep

State `ALPHA:sweep, BETA:0.0` in `FLIGHT_CONDITION` and
`-4.0,0.0,4.0` in `SWEEP_VALUES`. The matrix declares three points with a
fixed sideslip; the Python case represents this with
`SweepAxis(type="alpha", values=[-4.0, 0.0, 4.0], held={"beta": 0.0})`.
The held angle is part of each point and its identity.

See the [steady wing polar](https://github.com/nevesgeovana/pyflightstream/tree/main/examples/using-CLI/steady-wing-polar)
for runnable workspace inputs and the matching
[Python script](https://github.com/nevesgeovana/pyflightstream/blob/main/examples/using-API/steady_wing_polar.py).

Write it one of two ways.

- **One rotation, held fixed across the aerodynamic sweep.** Put
  `angle_deg: 5.0` in `VAR_NAMES_VALUES`. One value. The row keeps its alpha sweep and stays
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
