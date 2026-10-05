# Restore and rebuild the run records

## Archive and restore

A campaign workspace keeps its run records in `runs.json`, and a few files of
the same nature beside it: the storage record `storage_management.json`, the
additional-post record `additional.json`, and per matrix the products record
`post/<matrix>/products.json` and the plan receipt `post/<matrix>/plan.json`.
When one of them is lost or overwritten, two commands bring the records back,
and they carry two names on purpose:

- `pyfs-matrix restore` brings a file back from the workspace's archive,
  byte for byte. It is exact and always safe.
- `pyfs-matrix rebuild` makes run records AGAIN from the simulation folders
  under `sims/`, when no archive holds them. Every record it makes says so,
  so a rebuilt record is never taken for the one written when the point ran.

Both preview by default and change nothing; `--apply` writes.

## Restore a file from the archive

```text
pyfs-matrix restore runs --workspace .              # which copy, and what it holds
pyfs-matrix restore runs --workspace . --apply      # put it back
pyfs-matrix restore runs --workspace . --stamp 20260929-120000 --apply
pyfs-matrix restore products --workspace . --matrix matrix-lnx --apply
```

The kinds are `runs`, `storage`, `additional`, `products` and `plan`. The
archive forms read are:

| kind | the file | its archived copies |
|---|---|---|
| `runs` | `runs.json` | `archive/runs-<stamp>.json` |
| `storage` | `storage_management.json` | `archive/storage_management-<stamp>.json` |
| `additional` | `additional.json` | `archive/additional-<stamp>.json` |
| `products` | `post/<matrix>/products.json` | `post/<matrix>/archive/<stamp>/products.json` |
| `plan` | `post/<matrix>/plan.json` | `post/<matrix>/archive/<stamp>/plan.json` |

`sync`, `--force-rerun`, `delete-sims` and `rename` copy `runs.json` to
`archive/runs-<stamp>.json` before they rewrite it. A copy numbered within one
stamp (`runs-<stamp>.2.json`) or labelled after it
(`runs-<stamp>-before-doctor.json`) is found too. Without `--stamp` the newest
copy is taken. `--matrix STEM` names the matrix for `products` and `plan` when
several matrices have archives.

With `--apply` the current file, when there is one, is first archived in the
same form, so a restore can itself be undone by restoring that copy. A copy
that is not readable JSON, or a manifest copy that is not a list of records,
is refused. A restore writes holding the lease on `runs.json` that a run, a
collect and a sync hold while they write, and for the storage and
additional-post records their own lease too; while one of those leases is held
(`runs.json.lock` is there, for example during a sync), the restore is refused
and nothing changes.

The writers of the storage record, the products record, the plan receipt and
the additional-post record do not archive their file before rewriting it, so
for those kinds the copies a restore finds are the ones an earlier restore
made or copies you put there yourself.

## Rebuild records from the simulation folders

```text
pyfs-matrix rebuild --workspace .                   # which records, and why not the others
pyfs-matrix rebuild --workspace . --apply           # add them to runs.json
pyfs-matrix rebuild --workspace . --out runs-rebuilt.json --apply
pyfs-matrix rebuild --workspace . --all-sims --out runs-compare.json --apply
```

For each simulation folder the package runs its matrix row again in a
throwaway copy of the workspace, with nothing submitted, and compares the
script it renders with the script that ran, in `sims/sim_<id>/scripts/`. The
record is rebuilt only when they are the same, once the workspace root and the
interpreter path are set aside. The record is then completed by the package's
own collect stage over the files already on disk, and that collection writes
nothing: a collection that would move an output, copy the scheduler's log,
write a surface export translated from the VTK or expand a compressed
simulation is not made, and the record stays `SUBMITTED` for
`pyfs-matrix collect`. The whole workspace is compared before and after the
rebuild, and nothing is written when it changed.

What a rebuild decides, and how:

- **Only the version that ran rebuilds a record.** The proof is the script
  this version renders, so a record a known run of another version wrote (in
  an archived `runs.json` or in a matrix's `campaign_sweep.csv`) is refused,
  naming both versions.
- **An edited or drifted script is refused, and the refusal says which
  input.** Each changed line is named with what it is (a VTK export line, the
  loads frame line, a plot type line, a renamed pproc group) and the input the
  package renders it from now, for example `inputs/pproc/p001.toml`.
- **Inputs from another origin.** When an input changed after the run (a pproc
  group renamed from `ROTOR_*` to `SHAFT_*`, an export switched off),
  `--inputs-from <folder>` lays another workspace's `inputs/` folder over this
  one in the throwaway copy. Each rebuilt record names the inputs it took from
  there whose bytes differ from the workspace's. The workspace's own inputs are
  never changed.
- **Outputs decide the status.** A truncated or missing output is
  `FAILED_INCOMPLETE_OUTPUT`, never `CONVERGED`. A point whose outputs are all
  there and whose solver log was deleted is `RAN_MISSING_LOG` (FR-413), never
  refused for the log alone; its record leaves the solver clock and the
  iteration count unstated.
- **Grouped runs (`--batch`, `--polar-sweep`)** are rebuilt like points run
  alone (FR-412). A batch point's script names its batch folder
  (`sims/batch/<matrix>_b<ID>/sim_<id>/`), and the rendering is compared there.
  A point whose outputs are in its datapoint folder is completed and names its
  batch and its job, as `collect` records it; the job entry comes from the plan
  receipt `post/<matrix>/plan.json`, and what only the submission carried (the
  scheduler's fields) is left empty, never invented. A simulation still in its
  batch folder, its batch not yet moved home, is rebuilt from there and left
  `SUBMITTED` with its job entry: `pyfs-matrix collect` moves it home and
  completes it, since a rebuild writes nothing in the workspace. Without a plan
  receipt naming its job such a simulation is refused, with the remedy (restore
  the plan receipt, `pyfs-matrix restore plan`).
- **A row switched off after it ran** (`RUN 0`) still describes that run: the
  row is set to `RUN 1` in the throwaway copy only, and the record says so.
  The throwaway copy holds the matrix once, in the home the workspace keeps
  it in, so a matrix kept in `inputs/matrices/` with a `RUN 0` row is never
  read as being "in both homes" (FR-411).
- **The matrix is the workspace's.** `--matrix NAME` with a bare name or stem
  reads the matrix in the workspace's root or `inputs/matrices/`, from any
  working directory; a file of that name in the working directory is not read,
  and a WARNING says so when its bytes differ (FR-411).
- **A build the submission profile no longer maps** (a run on 26.123 after the
  profile's `[builds]` table moved to 26.124): `--build-alias 26.123=26.12`
  names the scheduler's word at the time; the default is the build itself. The
  alias enters only the job descriptor, never the solver script, and the record
  says which alias was assumed.
- **A POL no current matrix holds** (the row was deleted or renumbered after
  it ran): the command names the simulations that wait for the revision that
  ran; pass it with `--matrix <file>`, named as the matrix was named then.
- **A run on a cluster restored on Windows.** The executed script names a
  POSIX root with forward slashes; the comparison normalises the separators
  and sets each side's root aside, and the rebuilt record writes its paths in
  the run's own root and style, never with the two separators mixed.
- **`SUBMITTED` records.** Without `--all-sims` a rebuild gives them no end and
  points to `pyfs-matrix collect`. With `--all-sims` the status in `runs.json`
  is ignored and each simulation takes the status its outputs support, except
  a folder written in the last 30 minutes, which stays `SUBMITTED` because its
  job may still be writing.

Where the rebuilt records go:

- Without `--out`, `--apply` appends to `runs.json` the rebuilt records whose
  run ids it does not hold, after copying it to `archive/runs-<stamp>.json`,
  or writes `runs.json` when there is none.
- `--out NAME` writes them to that file in the workspace root and never
  touches `runs.json`: the file holds the rows of `runs.json`, each rebuilt
  record in the place of the row with its run id, and the other rebuilt
  records after them. A name that is `runs.json`, or a file that exists, is
  refused before any work.
- `--all-sims` rebuilds every simulation folder on disk, recorded or not, to
  compare with `runs.json`, and requires `--out`.

Comparing a rebuilt manifest with the original, some fields differ by nature
and say nothing about the run: `package_version`, `package_commit`,
`package_dirty`, `wall_time_s`, `warnings` (the `REBUILT` line), `staged_as`,
and sometimes `started_at` and `finished_at`, which are read from the dates of
the files. A local run's `argv`, `executor` and `cwd` are reconstructed.

Not rebuilt, each named with the reason and what to do: a simulation stored
compressed (`sims/sim_<id>.zip`), one retired by `delete-sims`, one whose
folder holds no declared output, and the cases above that are refused. The
summary ends with the count rebuilt and the count refused
(`rebuild: 2 rebuilt, 1 refused`), and `--apply` with nothing to write prints
every refusal before it stops (FR-412).

!!! warning
    Never run `pyfs-matrix run --resume` on a simulation a rebuild refused:
    with no record, the resume takes it as never run and runs it again.
    Settle the reason first and rebuild again.

<a id="mark-a-run-failed-after-the-fact-since-0330"></a>

## Mark a run failed after the fact

A run can end `CONVERGED` and still be wrong, which you find only later,
reading its products. `mark-failed` records that verdict:

```text
pyfs-matrix mark-failed --sims 2006,2007 --reason "wrong mesh"           # preview
pyfs-matrix mark-failed --sims 2006,2007 --reason "wrong mesh" --apply   # write
```

Every record of each named simulation becomes `FAILED_MARKED`, whatever it
ended in, `SUBMITTED` included. Nothing is deleted: each record keeps, under
`marked`, the status it had (`from`), when it was marked (`at`) and the
reason (`reason`), and `runs.json` is copied to `archive/runs-<stamp>.json`
first, so `pyfs-matrix restore runs` undoes it. `FAILED_MARKED` is a failure
to every reader: the post treats the run as any failed one (it names the status
in a warning, and the coefficient tables do not expect coefficients from it),
the cost estimate leaves its wall time out, and `delete-sims` deletes the simulation
without `--force`. A simulation id with no record is refused by name before
anything is written, and a record already `FAILED_MARKED` is left as it is.

## Mark a run converged after reading it

The other verdict a person gives. You can know, from your own reading of a
point's products and history, that it converged where the package could not
say so: its log was deleted (`RAN_MISSING_LOG`), or its march reached its last
step (`COMPLETED_MAX_ITER`). `mark-converged` records that verdict, instead of
an edit of `runs.json` by hand (FR-414):

```text
pyfs-matrix mark-converged --sims 2006 2007 --reason "residuals flat over the last revolution"
pyfs-matrix mark-converged --sims 2006 --points AL+020 --reason "..." --apply
```

Without `--apply` it previews and writes nothing; `--reason` is required, and
`--points` narrows the mark to the named points of the simulations.
`--sims` takes whole simulations, as words, comma separated or in brackets
(`2006 2007`, `2006,2007`, `[2006,2007]`), and `--points` the point names.
Unlike `mark-failed`, it does not mark a run id alias (`2006_3`): the alias is
read as `mark-failed` reads it and refused, and the refusal names the
`--sims` and `--points` that select its point (`--sims 2006 --points AL+020`). Each marked record becomes `CONVERGED` and keeps under `marked` the status it had
(`from`), when (`at`), your reason (`reason`) and the verdict (`verdict`);
`runs.json` is copied to `archive/runs-<stamp>.json` first, so
`pyfs-matrix restore runs` undoes it. A point of a steady job is marked alone,
and the job takes its worst point's status.

Refused by name, with the reason and what to do, and nothing written while
any is named: a point still `SUBMITTED` (collect it first), a point whose loads
export is not on disk (restore its folder or collect it again), a simulation
`delete-sims` deleted, and a point marked failed (restore `runs.json` from
before that mark first). A point already `CONVERGED` is listed and left alone.

The verdict stays the person's everywhere: `show` prints it under `marked`,
`status --points` prints the status the point had (`was`), `post.log` names
each marked point once, and every entry of `products.json` built from a marked
point carries its `marked` field, by run id. A later writer keeps it: a
rebuild keeps the person's status and says which status the files support, and
a `sync` that prefers the other workspace names a marked record as a conflict
and leaves it.

## From Python

`pyflightstream.run.records.restore`, `pyflightstream.run.records.rebuild`,
`pyflightstream.run.records.mark_failed` and
`pyflightstream.run.records.mark_converged` take the same options as the commands and return what they did, or would do,
as a dictionary; `summary_lines` gives the lines the commands print.
`collect_without_writing` is the read-only collection on its own, and
`manifest_lock` holds the lease the workspace's writers hold around a
manifest.
