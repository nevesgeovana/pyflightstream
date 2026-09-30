# Restore and rebuild the run records

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
is refused, and so is a restore of `runs.json` while a run holds
`runs.json.lock`.

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
  `FAILED_INCOMPLETE_OUTPUT`, never `CONVERGED`.
- **A row switched off after it ran** (`RUN 0`) still describes that run: the
  row is set to `RUN 1` in the throwaway copy only, and the record says so.
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
  touches `runs.json`. A name that is `runs.json`, or a file that exists, is
  refused before any work.
- `--all-sims` rebuilds every simulation folder on disk, recorded or not, to
  compare with `runs.json`, and requires `--out`.

Comparing a rebuilt manifest with the original, some fields differ by nature
and say nothing about the run: `package_version`, `package_commit`,
`package_dirty`, `wall_time_s`, `warnings` (the `REBUILT` line), `staged_as`,
and sometimes `started_at` and `finished_at`, which are read from the dates of
the files. A local run's `argv`, `executor` and `cwd` are reconstructed.

Not rebuilt, each named with the reason: a simulation stored compressed
(`sims/sim_<id>.zip`), one retired by `delete-sims`, one whose folder holds no
declared output, and the cases above that are refused.

!!! warning
    Never run `pyfs-matrix run --resume` on a simulation a rebuild refused:
    with no record, the resume takes it as never run and runs it again.
    Settle the reason first and rebuild again.

## From Python

`pyflightstream.run.records.restore` and `pyflightstream.run.records.rebuild`
take the same options as the commands and return what they did, or would do,
as a dictionary; `summary_lines` gives the lines the commands print.
`collect_without_writing` is the read-only collection on its own, and
`manifest_lock` holds the lease the workspace's writers hold around a
manifest.
