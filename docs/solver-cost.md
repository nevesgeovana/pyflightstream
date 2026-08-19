# What a run cost, and which build got slower

Every campaign this package runs already records how long each point
took. The manifest, `runs.json`, has carried `wall_time_s` per run since
the v0.3 line, next to the vendor build string the solver reported and
the sha256 of the executable that actually ran. What was missing was a
way to ask the question those three fields exist to answer: **did the
new build get slower on the same points?**

That is what the cost view is for. It reads the manifest and nothing
else. No solver starts, no report is opened, and no licensed machine is
needed, so you can run it on a laptop over a campaign someone else
measured.

## Three things it will not do

These are worth reading before the example, because each one is a number
the view refuses to invent.

**A run with no recorded time is absent, not zero.** A manifest written
before the field existed, or by a run that died before the timer
stopped, carries no wall time. The cost view reports `None` there and
the command line prints `absent`. It is not `0.0`, which would make the
build look infinitely fast, and it is not a floating-point NaN, which is
a number that quietly survives a `sum()`.

`results.tables.run_table` does use NaN for the same field, and is right
to: its rows are a numeric frame in which every cell must be a number.
This view is evidence rather than arithmetic, and the two answers are
different on purpose.

**A column is a build AND an executable.** `fs_build` is what the vendor
prints; `fs_exe_sha256` is what ran. A hotfix rebuilt from the same
source tag prints the same build number and is a different program, so
the two together are one column key and appear separately.

**A comparison only counts work both builds did.** Points timed on one
build alone are listed as unpaired and left out of both totals. The
error this prevents is the dangerous direction: the build that ran more
points would otherwise look slower for having done more.

## From Python

```python
from pyflightstream.qa.cost import cost_view
from pyflightstream.workspace import RunRecord, RunStatus


def run(run_id, alpha_deg, build, sha, seconds):
    """One manifest record, as a campaign would have written it."""
    return RunRecord(
        run_id=run_id,
        sim_id="SIM-01",
        point={"alpha_deg": alpha_deg},
        fs_version_requested="26.120",
        fs_build=build,
        fs_exe_sha256=sha,
        package_version="0.8.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
        wall_time_s=seconds,
    )


old, new = "a" * 64, "b" * 64
view = cost_view(
    [
        run("r1", 0.0, "2122026", old, 41.2),
        run("r2", 4.0, "2122026", old, 58.9),
        run("r3", 8.0, "2122026", old, None),   # ran, never timed
        run("r4", 0.0, "2900000", new, 63.5),
        run("r5", 4.0, "2900000", new, 88.1),
    ]
)

baseline, candidate = view.builds

# The untimed run is absent, and absent is not a number.
assert view.wall_time_s(view.points[2], baseline) is None

comparison = view.compare(baseline, candidate)
assert round(comparison.ratio, 2) == 1.51        # the candidate is ~51% slower
assert [point.label for point in comparison.unpaired] == ["alpha_deg=8.0"]
```

In real use the argument is a campaign root or a `CampaignWorkspace`
rather than a list of records:

<!-- skip: next -->

```python
view = cost_view("runs/my-campaign")
```

`view.rows()` gives the pivot as plain dictionaries, one per point, keyed
by `"sim_id"`, `"point"` and one label per build. They are plain dicts on
purpose: this layer holds no opinion about a substrate, and
`pandas.DataFrame(view.rows())` is one call away if you want one.
`cost_rows()` gives the long form instead, one row per run, with the full
executable hash rather than the twelve-character label prefix.

## From the command line

```text
$ pyfs-qa cost runs/my-campaign --compare 2122026@aaaaaaaaaaaa,2900000@bbbbbbbbbbbb
SIM     POINT          2122026@aaaaaaaaaaaa  2900000@bbbbbbbbbbbb
SIM-01  alpha_deg=0.0  41.20                 63.50
SIM-01  alpha_deg=4.0  58.90                 88.10
SIM-01  alpha_deg=8.0  absent                not-run

column 2122026@aaaaaaaaaaaa: fs_build=2122026 fs_exe_sha256=aaaa...
column 2900000@bbbbbbbbbbbb: fs_build=2900000 fs_exe_sha256=bbbb...
seconds of wall-clock time around the solver process; absent = the run is
recorded and carries no wall time, not-run = that point never ran on that
build. Both are read as absent, never as zero.

SIM-01  alpha_deg=0.0  41.20 -> 63.50  x1.54
SIM-01  alpha_deg=4.0  58.90 -> 88.10  x1.50
SIM-01  alpha_deg=8.0  not timed on both builds, left out
2 point(s) compared, 1 unpaired: 100.10 s -> 151.60 s, overall x1.51
(above 1 means the candidate build is slower)
```

The two empty cells say different things and are printed differently.
`absent` means a run is recorded at that point on that build and carries
no wall time. `not-run` means that point was never run on that build at
all. Neither is a number.

The column labels accepted by `--compare` are the ones the table prints.
A typo is answered with the labels that do exist.

## What the number is, and what it is not

It is wall-clock time in seconds around the solver process, taken with a
monotonic performance counter. It includes process start-up and file IO,
it is not CPU time, and it is only meaningful between runs taken on the
same machine under a comparable load. Two builds compared across two
machines are not compared at all.

Repeated runs of one point on one build are averaged, and the individual
readings stay available as `view.cell(point, build).samples`. Runs that
ended in a FAILED status are kept and counted rather than dropped, and
the command line says how many there were: time to a failure is time,
and it is not the time to an answer.
