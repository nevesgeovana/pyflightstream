## The averaging window

The window is stated in iterations or in last revolutions, ON THE MATRIX ROW,
and a row of an unsteady run type must state it.

| column | run type | required | unit |
|---|---|---|---|
| `LAST_REVS_AVG` | `unsteady_rotor` | **yes** | last revolutions, **accepts a float** |
| `LAST_ITERS_AVG` | `unsteady` | yes | last iterations |

**The key is written in UPPER CASE, exactly as the table spells it**, like every
other key of a matrix row. `VAR_NAMES_VALUES` keys are matched on the exact
spelling: a lower-case `last_revs_avg` on a workflow row is refused as a key of
no run type, and where that check does not run it is not read at all, so the
window it meant to state is not applied.

**It lives in the MATRIX, not in the pproc**, because it converses directly with
the temporal setup: `DELTA_TIME`, `TIME_ITERATIONS` and `RPM` are all on the same
row. Putting it in the pproc would separate the window from the quantities that
define it.

`WINDOW_STEPS` and `WINDOW_REVOLUTIONS` are **retired** -- they were the same idea
under another name in another place, and two spellings of one idea are how two
published numbers come to disagree.

`WINDOW_STEPS`, `WINDOW_REVOLUTIONS` and `WINDOW_DEGREES`
are refused at plan time. Write `LAST_ITERS_AVG` for steps or `LAST_REVS_AVG`
for revolutions; divide degrees by 360. A new unsteady plan requires one of
these current keys. Older records retain the window the run was given, with
a warning naming the steps when no current averaging key was recorded.

**A continued point is averaged over the last steps of its WHOLE march**
(FR-96). A continuation (`RESTART`) records the row's clock, so
its window as recorded ends at the last step of the run it continues; the post
moves every window of the point, keeping its length, to end at the last step
of the march, so `LAST_REVS_AVG: 1` averages the last revolution the solver
turned, in the continuation. The plots table of such a point is the history of
the whole march: the post reads the plots export of each run of the chain from
the archive the next run moved it into (`datapoints/DP-<point>/archive/<stamp>/`)
and joins them by step number. An export whose first step follows the
history's last is appended; one that starts inside the history and repeats its
rows there restates the march and is taken from where it starts; one that
starts again at step 1 with rows of its own is numbered on from the history's
last step, its time with it. No step is repeated or missing at a seam, and
`post.log` says how the history was joined and the step the window ends at. A
history that cannot be found or joined is said there, naming the file, and the
table then holds the continuation's own export, as it states its steps. Which
of these the solver writes is not yet read on a licensed run, so each is read.
A point that continues nothing is averaged exactly as before.

---
