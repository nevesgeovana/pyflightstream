# Migrating to 0.35.1

This patch corrects grouped runs and extends the rows accepted by
`plan --batch` and `plan --polar-sweep`. Generate a new plan before using
either grouped run mode.

## Repeated sweep values (FR-408)

A matrix with repeated `SWEEP_VALUES`, or values that produce the same point
name, is refused before planning. The error names the POL, both values and
their positions, and the shared point name. Remove the repeated value or use
values with distinct point names, then plan again.

## Grouped rows and their limits

Steady and quasi-steady polars now join jobs of their own (FR-403). A steady
row with `COLD_START` false or a point requiring multiple initializations
stays excluded. An empty grouped receipt is refused; it no longer runs the
excluded rows in the default mode (FR-365).

Polars requesting `[time_averaging]` join grouped jobs, with each point's
surface exports in its own folder (FR-402). Rows with `unsteady_solver_actions`
are grouped by their action set, registered once per job (FR-405). Place a
relative `SCRIPT` file in the job folder named by the plan's warning; relative
paths inside `COMMAND_LINE` actions also resolve there. A geometry carrying
saved solver actions remains refused; inspect it with `pyfs-matrix inventory`
and use `--clean` to remove those actions (FR-378).

Each acoustic polar runs in its own job (FR-406). Coupled `unsteady` points
join grouped jobs and reopen the geometry for each point; coupled `steady`
and `qsteady_rotor` rows remain excluded because their scripts must end at
`EXECUTE_AEROELASTIC_ANALYSIS` (FR-407).

Job budgets combine priced `BEST` estimates with explicit cell budgets;
an unknown `BEST` point requires `max_walltime` (FR-364). Collected points
retain their solver identity (FR-366), sections persist across a point reset
(FR-362), and coupled logs keep resets within the point's own segment.

See [Planning and cost](workflow-plan-and-cost.md) for grouped-run options
and limits. The bounded licensed comparisons are recorded in RPT-148;
the time-average repeat includes a difference of at most 1.1e-19 on one
point's last step, and relative `SCRIPT` grouping has offline evidence only.
