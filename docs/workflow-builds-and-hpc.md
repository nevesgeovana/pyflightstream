# Builds, local runs and clusters

The build as an input, where a point runs, what the record's digests guard, and naming a build to a cluster's scheduler.

## Keeping a Linux run local

Linux is the cluster: a workspace that carries a submission profile submits
from Linux and runs locally on Windows, and no cell says so. When the Linux
machine is a workstation, or the point is a smoke test on the machine itself,
`pyfs-matrix run --local` keeps the run on that machine: the cluster is not
asked, the executable resolves as on Windows (the `FS_BUILD` column through
`inputs/executables.toml`, or `--fs-exe`), each point runs and writes its
outputs in its own `datapoints/DP-<point>/` as any point does, and every
record's `executor` entry says
`forced_local`. The flag changes nothing on a machine that would not have
submitted, and `collect` is not needed afterwards: a local point runs to its
end before its record is written.

**The profile's log decision still holds under `--local`.** A profile stating
`[log] export_log = false` says the solver build on that cluster aborts at
`EXPORT_LOG`, and it aborts there whether the job is submitted or run on the
machine, so a run `--local` keeps there leaves `EXPORT_LOG` out of the script
as a submitted job does. No scheduler writes the log of a local run, so the
run writes the declared `_log.txt` from what it captured of the solver, its
standard output then its standard error, as a scheduler's job log holds them,
and the point is judged by it when it reads as a residual history. When the
solver printed nothing, the log is not counted as a missing output: the point
is judged from its loads export, as any point that exports no log is, and the
record's `residual_note` says why it has no log. The same note says so when
the log is the captured output. A steady row of several points runs as one job
and one process, so what it printed is no single point's log: no point's log
is written from it, each point is judged from its loads export, and the job's
`residual_note` says why. A row that imports its trailing edges from a file is
held to the count the solver logs, read from the captured output; with nothing
captured the point is recorded `FAILED_INCOMPLETE_OUTPUT` naming the machine,
and such a row is run submitted, where the scheduler's log is collected. Every
profile of the workspace is read for this, and profiles that disagree about
the log are refused under `--local`. The build-identity pre-flight, which
runs once per installation before the first point, exports no log on such a
machine either: it reads the build from what the solver printed, refuses a
build other than the registered one as it always does, and when the solver
printed none it warns, naming the profile, and never refuses.

## The build is an input

A workflow declares the commands it always emits, and the builds it
covers are DERIVED from the command database rather than written down.
Asked for a build outside its range, the workflow refuses before it
emits its first line, and the refusal names the build you gave, the
builds it covers, and the commands that decided it.

Because the range is derived, a build registered tomorrow joins it the
moment its evidence lands, and nobody has to remember to widen a list.

**The row is the same on every build: only `FS_BUILD` changes.** Where a
build spells the same thing in its own vocabulary, the package writes
that vocabulary, and the plan and the run record say what was chosen.
What each run type does on each registered build:

| run type | 25.000 | 25.100, 26.000 | 26.100 | 26.101, 26.120, 26.121 | 26.122, 26.123, 26.124 |
|---|---|---|---|---|---|
| `steady` | refused | runs | runs | runs | runs |
| `unsteady` | refused | single march | single march | single march | actions where the row asks for them |
| `unsteady_rotor` | refused | single march, Euclidean rotor (run on 26.000; 25.100 from its manual) | single march, Euclidean rotor without the rotor mark, speed in rev/min (not run) | single march | actions where the row asks for them |

**A single march** is how an unsteady row runs on a build whose manual
documents no unsteady solver action (`SET_NEW_UNSTEADY_SOLVER_ACTION`,
first documented in 26.122): the plots are declared before one solver
start that runs every time step the row states, and every export is
taken after it. It is also how a row asking for none of the features
below runs on every build. Such a row (FR-314), on a build
that documents the actions, also registers the step counter alone, which
counts the time steps and writes nothing else, so the progress bar of a
local run (FR-129) appears on every unsteady row; its script differs from
the one 0.32.0 wrote by those three lines only, and its `march_strategy`
stays `single_march`. That the counter leaves the results unchanged is owed
by the licensed round of 0.33.0. The per-step history of
the products stage comes from the plots table the solver writes, so the
reductions and the series are built on every build.

Three things only the actions give, and a row asking a build without
them for one is BLOCKED at plan time, before any solver time is spent,
with a sentence naming the build, the feature, the builds that document
the actions and the change to the row that runs where you asked:

- snapshots from a threshold (`EXPORT_UNSTEADY_AFTER_ITER`,
  `EXPORT_UNSTEADY_AFTER_REV`), because the step counter is an action;
- the wall clock inside the run (`WALLTIME`), because the clock and its
  stop are actions; size `TIME_ITERATIONS` to the queue instead and
  continue a capped run with `RESTART: {ADDITIONAL_ITERS=n}`;
- a continuation that reads their records, `RESTART: {FINISH_PENDING}` and
  `RESTART: {ADDITIONAL_REVS=n}`.

Nothing is emulated. The plan's `march_strategy` and the run record's
`march_strategy` carry `actions` or `single_march` for every unsteady
point, and the superfile carries it as a column, so two runs of one row
on two builds are told apart by what they were given.

**A Euclidean rotor** is how a rotor row runs on 25.100 and 26.000, whose
manuals name the motion type `EUCLIDEAN` and have no rotor axis or speed
command. The package writes a Euclidean motion whose angular velocity is
the row's speed converted to rad/s along its axis, marked as a rotor
with `SET_MOTION_IS_ROTOR`. On 26.000 a blade driven this way turned
exactly as the rotary motion at the same speed turns it on 26.120, in
the same sense (RPT-049); 25.100 prints the same grammar and was not
run.

**On 26.100 the Euclidean rotor carries no rotor mark.** Its manual prints
the mark and its solver answers it as an unrecognized command (RPT-049).
The package writes the Euclidean motion without it, with the angular
velocity in REV/MIN along the axis, and a comment in the script says so.
None of this is measured (RPT-051):

- the unit is a maintainer decision, while that build's manual tutorial
  gives rad/s for the field and 26.000 measured rad/s;
- the sense of rotation is not measured on that build;
- the solver is never told the motion is a rotor.

Before trusting the loads of a 26.100 rotor, check on one short run that
the blade turned the angle the row states, and in the direction it states.

**25.000 is refused for every run type.** Its `INITIALIZE_SOLVER` takes
five settings no later edition exposes and no edition gives a default
for, and choosing them for you is not this package's decision.

**The table is about the run types, and a row's inputs can still ask a
build for more.** A solver preset or a post-processing artifact names
settings too. For example, a preset's stabilization is a command from
26.101, its wake-on-wake induction and additional wake relaxation from
26.100, and its Reynolds-averaged drag from 25.100; and on the builds
before 26.120 a section distribution takes no `INCLUDE_SYMMETRY`. Such a
point is BLOCKED at plan time naming the command, and the plan lists
every blocked point before any solver time is spent. Run `pyfs-matrix
plan` with the `FS_BUILD` you mean first.

## Where a submitted point runs

On a cluster each point of a row is submitted as its own job and runs in its
own datapoint folder, `sims/sim_<id>/datapoints/DP-<tag>/`, which is where
its outputs are filed. The scheduler's descriptor (`submit.yaml` or the name
the profile gives it), the unsteady action program with its export script,
and the wall clock with its state are written there, so every point of a
swept row is submitted in one invocation and no queued job shares a file with
another. The run record names the folder as `working_dir`, and
`pyfs-matrix collect` waits for the declared outputs there and records them
where they were written. A point run on this machine runs in the same
folder, so its exports, the per-step ones included, are written
where they are filed, and a point whose run fails leaves them there rather
than in the folder every point of the row shares; the script is the same
either way, since its exports are named relative to the working directory and
its inputs by absolute path. A steady row, which is ONE job over all its
points and one script, submits from and runs in the simulation folder, and
collection files each point's outputs in its own folder. FR-99 states the
requirement.

**A steady job's log on a machine that exports none.** Where the profile
states `[log] export_log = false`, the job's script exports no log for any of
its points, and its scheduler writes one log of the whole job. `collect`
therefore waits for each point's other outputs and for that one log, and files
the log once, under the job's script name with `_log.txt`
(`P<POL>-<sweep name>_log.txt`), in the simulation folder where the job ran; no
point waits for a log of its own, so `collect --watch` does not wait for files no scheduler writes. Each point is judged from its loads
export, and each point's `residual_note`, and the job's, names the job's log. A
row that imports its trailing edges from a file holds every point to the count
in that one log
(`test_collect_files_a_steady_job_whose_scheduler_logs_the_job_once`,
`test_a_steady_job_that_imported_trailing_edges_is_held_to_the_job_s_log`).

**A job that ended without its log (FR-311).** `collect` waits
for the solver log (`native_log`, or the declared `_log.txt`), and a job that
died before writing it used to stay `SUBMITTED` for ever, looking like a job
still running. The profile can name the files its scheduler writes when a job
ends, under `[log]`, as globs with the placeholders of `native_log`
(`{sim}`, `{point}`); the scheduler's job id, which the package never learns,
is matched by the glob:

```toml
[log]
export_log = false
native_log = "FTS{sim}.l*"
job_end_files = ["FTS{sim}.o*", "FTS{sim}.e*"]
```

When every listed pattern matches a file in the point's folder and the solver
log does not exist, `collect` records the point `FAILED_EXECUTION`; the
record's `error` names the files it read and the log that is missing, and
carries the last 20 lines of each end-of-job file, read as bytes and decoded
with replacement. When only some of them exist, or the log exists, or the
profile has no `job_end_files`, `collect` waits as before. Nothing of one
scheduler is written in the package: the names above are the ones reported
for one cluster, not yet confirmed from a real cluster folder, so write your
scheduler's own. The rule is a heuristic: a log delayed on a shared file
system, or a job the scheduler requeued, can be misjudged.

## What the record's digests guard, and where that stops

A run record names the bytes of every file its solver read, `inputs_sha256`
beside `script_sha256`, and 0.27.0 holds the files the run writes to that. Before
a single one is written, the run refuses: two files it would write on one path
(names equal but for case, a path through a parent folder, a name Windows reads
as another's alias such as a trailing dot, an 8.3 short name or a stream); a
file parked on a path the run writes itself (the point's script, its probe
points file, the scheduler's descriptor, the unsteady counter and wall-clock
programs); a parked file that would change an input the record already hashed;
and a data file it hashes (a trailing-edge node file, a disc's profile copy)
outside the folder the point runs in, a link or a junction resolved. The lines
the solver logs when it cannot use a disc's profile are read in the solver's own
log where the job ran and in every collected output that is not a binary kind,
whatever its name.

What this does NOT defend against is a file system arranged to deceive it: a
hard link, a link or a junction made or changed between the check and the
write, a recipe's own Python writing files directly, or another process writing
into a point's folder while its job is queued. A digest says which bytes were
there when the run wrote them; keep a workspace's simulation folders to the
runs that own them.

## Choosing a profile and the longest walltime

When a workspace holds more than one profile in `inputs/hpc/`, `--hpc NAME` on
`plan`, `run` and `collect` selects `inputs/hpc/<NAME>.toml`; a workspace with
one profile needs no option. The top-level key `max_walltime`, written
`HH:MM:SS` (hours may exceed 24), states the longest walltime the queue
accepts. A grouped plan caps the walltime of every job at it, with a warning
that suggests a larger number of batches, and refuses a row whose own
`WALLTIME` cell is above it (FR-364, FR-377). A value that does not parse is
refused naming the key, and a profile without the key states no limit. The
sum rule for the walltime of a job, and the value `BEST`, are in
[Planning a campaign and what it costs](workflow-plan-and-cost.md).

## Naming the build to a cluster's scheduler

A row's `FS_BUILD` names ONE build, `26.123`. A scheduler often knows only an
application family, such as `26.1`, which covers more than one registered
build. The two vocabularies refuse each other: the scheduler does not know
`26.123`, and this package refuses `26.1` because it cannot tell which build
it means. So the cell keeps the build, and the cluster's profile translates it:

```toml
# inputs/hpc/h001.toml
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
ApplicationId = "{application_id}"
version       = "{fs_build_alias}"
master_file   = "{script_path}"

[submit]
command = ["esub", "{descriptor_path}"]

# What this scheduler calls each build a row may name. Keyed by the BUILD,
# because several builds can share one scheduler name. This is a DECLARATION,
# not a verification: nothing checks that the scheduler starts this build.
# Which build a point ran on is known only from the build number in its
# collected log.
[builds]
"26.123" = "26.1"
```

The matrix cell stays the same on every machine, so one study opens on a
workstation or on the cluster with no cell changed. A profile that writes
`{fs_build_alias}` and has no line for a build a row names is refused before
any point is submitted, naming the build and the table. A key that is not one
registered build, `26.1` for instance, is refused when the profile is read. A
profile that does not write the substitution is unaffected by the table.
