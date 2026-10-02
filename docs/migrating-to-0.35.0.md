# Migrating to 0.35.0

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices.

## The post writes no archive by default

Until 0.34.0 every rebuild by `pyfs-matrix post` moved the products it replaced
into `post/<matrix>/archive/<day and hour>/` before writing the new ones, so
a workspace that was posted often collected one archive folder per rebuild.
From 0.35.0 a post with no option overwrites the products, `products.json`,
`post.log`, `post.log.json` and the provenance files in place and writes no
`archive/` folder. The products themselves are byte for byte the ones 0.34.0
wrote.

To keep the old behaviour, pass `--archive`:
`pyfs-matrix post --workspace <root> --archive`. In Python the same is
`write_campaign_products(workspace, archive=True)`. `--force-overwrite` still
exists, and it cannot be combined with `--archive`, since one keeps a copy and
the other keeps none. The archives of the planning, the storage commands, the
additional post, `--force-rerun` and `rename` are unchanged.

## A continuation keeps the reopened state

A `RESTART` continuation reopens the saved simulation of the run it continues
and marches on from the step that run reached (FR-396). Until 0.34.0 the
script emitted `INITIALIZE_SOLVER` after reopening it, which cleared the
reopened solution, and registered the unsteady actions the saved file already
carries a second time. From 0.35.0 the script no longer re-initializes a
reopened state and does not register those actions again. The run still
stages the files the actions run (the step counter, the per-step exports
script and the wall clock), and the run record names the same actions.

The change is verified offline: the emitted script is compared with the hand
edited script that marched on in RPT-134, the resume arm of that
measurement. Licensed confirmation of the continuation the package itself
emits is owed. The continuation of a run the wall clock stopped shares the
emission path and has not been measured.

The post now warns, once per continuation, when its plots export ends where
the march it continues had already ended, so a continuation that added no time
step is no longer joined to its run without a word. The warning names the
continuation and the run it continues, and the table is posted as the march
stands. Nothing needs to change in a matrix.

## A rotor march lists its vorticity drag boundaries before the solve

A row that turns a rotor in time (`unsteady_rotor`, or an unsteady row that
states a rotor speed) and states `vorticity_drag_families` now has its
`SET_VORTICITY_DRAG_BOUNDARIES` line written between the moments model and
`START_SOLVER` (FR-318 R6). Until 0.34.0 the line came right after
`START_SOLVER`. Measured on 26.124 (RPT-133): in the old order no per-step
export carries the list and only the final loads export does; in the new order
every per-step export carries it. A steady row, the quasi-steady rotor and an
unsteady row that turns no rotor keep the line after `START_SOLVER`. The
scripts of a rotor row that states the families therefore differ from 0.34.0,
and `check_parity.py` names the difference by its requirement.

## Running a polar or a batch as one job

`pyfs-matrix run --polar-sweep` submits one cluster job per simulation, and the
job runs every pending unsteady point of that polar in order, in one solver
instance (FR-350). `pyfs-matrix run --batch N` submits the N jobs the plan
receipt lists, each running its polars in order (FR-351). Both apply to
unsteady rows only, combine with `--local` (one local instance, one licence,
one batch at a time, FR-375), and run the solver only: `run` does not post
(FR-376), the products come from `collect` and then `post`.

`plan --batch N` decides the split (FR-362). It groups the polars by processor
count and build, cuts them into contiguous batches of whole polars so that the
longest batch is as short as it can be, prints the split as a table, and
records every batch in the plan receipt `post/<matrix>/plan.json`. `run --batch`
refuses a receipt that has no batches, was made for another N or for another
matrix (FR-365). A polar the grouped plan cannot take, such as a steady row,
is named, with the reason, in the table and in the receipt, and no grouped job runs it.

The walltime of a job follows the `WALLTIME` cell of its rows. The cell is the
budget of one datapoint of the row, and a job asks for the sum of the cells of
its points, capped at the profile's `max_walltime` with a warning that suggests
a larger N; one row whose own cell exceeds `max_walltime` is refused (FR-364).
The value `BEST` asks the package to price the job: its estimate times 1.25
plus the walltime margin, rounded up to the minute (FR-364). `BEST` is a
value of the grouped plan and is refused by a plan that uses neither option.

The job scripts are `FULL-POLAR.txt` at the root of the simulation's folder and
`BATCH-<first sim>-<last sim>.txt` inside the batch's folder
`sims/batch/<matrix>_b<ID>/` (FR-357). The per-point scripts are still written
beside their records (FR-356). While a batch runs its simulations live in that
folder (FR-374) and every save and export in the job names an absolute path
(FR-359). A geometry that already carries saved unsteady actions is refused by
`plan --batch` (FR-378).

## Collecting batched points

`pyfs-matrix collect` reads a job's descriptor, native log and end files from
the job's folder and completes each point as soon as its files settle, while
the job still runs. While the batch has not ended it copies finished
simulations to `sims/` and never touches the batch folder; once the batch has
ended it moves them (FR-367). It cuts the job's cumulative log into one log per
point (FR-368). A point that failed without stopping the instance does not stop
the job, and the points a stopped job never started are named (FR-369,
FR-370).

`collect --discard-walltime` marks each point whose latest record is
`WALLTIME_REACHED` as `FAILED_MARKED`, so the next grouped plan runs it again
from the start; it is off by default (FR-400).

## Choosing the HPC profile

`--hpc NAME` on `plan`, `run` and `collect` selects the profile
`inputs/hpc/<NAME>.toml` when the workspace holds more than one. A workspace
with a single profile needs no option. The profile's `max_walltime`, in the
form `HH:MM:SS`, is the longest walltime the queue accepts (FR-377).

## The run id alias

Every datapoint has the alias `<sim>_<index>`, where the index is the 1-based
position of the point in its polar's sweep order as the plan lists it (FR-395).
It is derived, never stored, and does not change when the point is re-run or
continued. Every place that takes a run id accepts it: the query verbs,
`--points`, `mark-failed` and `delete-sims`. A query prints it beside the run
id, and an alias that names no point is named on standard error.

## The cost file

A workspace may carry a cost file `inputs/costs/c<NNN>.toml` that `plan --cost`
and the `plan --batch` estimate read (FR-398). It states an efficiency curve
against the processor count, an exponent on the mesh size and the multiplier of
each solver flag. A value between two stated points is interpolated and a
processor count outside the stated range is never extrapolated silently.
`--cost-file NAME` names the file when there are several. Without a cost file
`plan --cost` behaves as in 0.34.0. The package ships only a synthetic example,
`examples/costs/c000.toml`; the values of a machine belong to its user.

## The query verbs

`pyfs-matrix status` prints one row per polar with its recorded statuses and
the planned points no record carries, shown as `planned` (FR-379 to FR-385).
`show` prints the record of one datapoint, outcome first (FR-386); `log` prints
the activity log and, with `--post`, the grouped post log (FR-387); `trace`
follows a product to the runs that made it (FR-389); `history` and `diff` read
every record a point had and compare two runs (FR-390, FR-391). `log --storage`
and `status --additional` read the storage and additional registers
(FR-392, FR-393). All of them write nothing and take no lock (FR-383), print
recorded words as recorded (FR-384), and have `--json` and `--csv` forms
(FR-385). The same rows are functions of `pyflightstream.workspace.ledger`
(FR-388). See [Workspace queries](workspace-queries.md).

## Other commands read a batched point as a point run alone

After `collect` has brought a batch's simulations to `sims/`, `post`,
`mark-failed`, `RESTART`, `rename`, `rebuild`, `delete-sims`, `sync`,
`post --from-sims`, `free-space` and `run --force-rerun` read a batched point
as they read a point run alone (FR-372). While a batch runs, the query verbs,
`delete-sims` and `mark-failed` find its simulations in the batch folder, and
`delete-sims` refuses one of a running batch unless forced.

## Nested pytest runs

The nested pytest runs of the examples test use their own root and their own
base temporary folder, so they can no longer list or collect from the system
temporary folder (FR-399). This changes the test suite only.
