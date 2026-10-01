# Migrating to 0.33.1

0.33.1 is a patch of [0.33.0](migrating-to-0.33.0.md). Its dependencies and
extras are the ones 0.33.0 declared, except that the `dev` extra gains
`pytest-xdist`. No public name, console command, option, setup key or
product byte changed, and no matrix or pproc artifact needs an edit. Keep a
copy of the workspace and install the release in a separate Python
environment before running existing matrices, as for any release.

What a user meets is two false failures that stop being recorded: points that
read `FAILED_INCOMPLETE_OUTPUT` although they had converged and written
everything they were asked to write now read `CONVERGED`.

## A steady sweep's points 2 to n are no longer recorded failed

The points of a steady row run as one job in one solver session, and the
solver log each point exports holds every solve of the session so far. From
the second point on, a steady row that imports its trailing edges from a file
was recorded `FAILED_INCOMPLETE_OUTPUT` with "no solver log was read" while
its log was on disk, because the package did not read that file as the log of
one solve (FR-55). Where no collected output reads as the log of one solve,
the point's one collected `_log.txt` is now its log, so its trailing-edge
count is read and the point keeps its verdict. Two such files still name no
log, and the residual of points 2 onward is unchanged.

## A body row whose artifact plots wing sections is no longer recorded failed

A row whose geometry carries none of the families its pproc artifact's section
distributions cut, for example a body row citing an artifact that cuts the
wing, declared the section Cp plot `{name}_plot_cp_sections.txt` and exported
it with `SECTIONS_CP`. The solver cannot write that plot with no section to
plot, so every point of such a row was recorded `FAILED_INCOMPLETE_OUTPUT`
for a file that could not exist (FR-51). The declaration now follows the family
selection the builder makes over the row's geometry: the builder still warns
that the distribution is left out, and a row whose geometry carries a cut
family, or whose inventory is not known, declares and exports the plot as
before.

The one change of an emitted script is that the section Cp plot export is
left out of such a row.

## What to do with an old `runs.json`

A record written before 0.33.1 keeps the status it was written with: the
release does not rewrite a `runs.json`, and no command of 0.33.1 judges such a
record again. What each command does with one was measured on a record of each
cause written as 0.33.0 writes it, by the two tests of an old record in
`tests/tier1_offline/test_p0331_false_failures.py`
(`test_an_old_sweep_record_keeps_its_status_until_its_job_is_run_again` for
the steady sweep, `test_an_old_body_row_record_keeps_its_status_until_it_is_run_again`
for the body row). The answer is the same for both causes.

- **Its products need nothing.** `pyfs-matrix post` writes a point recorded
  `FAILED_INCOMPLETE_OUTPUT` into the products from its outputs on disk, its
  polar row included, and says so once for each such point in `post.log`:
  "the recorded status is FAILED_INCOMPLETE_OUTPUT". 0.33.1 changes no post
  code, so a post already run on the workspace wrote those rows too.
- **Its status stays until the point runs again.** `pyfs-matrix post` and
  `pyfs-matrix collect` leave every status as recorded, since collect
  completes only `SUBMITTED` records. `pyfs-matrix rebuild` refuses a
  simulation whose record another version wrote ("a record is rebuilt only by
  the version that ran") and writes nothing. The one way to a `CONVERGED`
  record is to run the point again with 0.33.1:
  `pyfs-matrix run <matrix> --force-rerun <run_id>`, with the `run_id` that
  `runs.json` records (for a steady row, the job's, which names every point of
  it). It archives the record and the collected outputs before it runs, and it
  spends a licensed seat per job. `--resume` skips a recorded point and so
  leaves its status.
- Re-run only where the status in `runs.json` is what you need: the products
  do not wait on it. A point that truly lacks an output still reads
  `FAILED_INCOMPLETE_OUTPUT` after the re-run.

## The tier 1 suite runs in parallel

For contributors only. `pytest-xdist` joins the `dev` extra, and the CI and
release workflows run tier 1 and the coverage floor with `-n auto`, so a
serial run of about 36 minutes, the 0.33.0 release gate's serial run, is no
longer the wall time of a gate. To run
the suite the same way, install the extra and add `-n auto` (or a worker
count, `-n 4`) to the `pytest` command. A user of the package, with no `dev`
extra, sees no change.

## FSI on `unsteady_rotor` is still refused

Unchanged in 0.33.1: the plan refuses a fluid-structure row on
`unsteady_rotor`, which is still in debug on this release. Nothing in 0.33.1
touches that refusal.
