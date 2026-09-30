# Sync every folder, and the two matrix homes

This page covers what `pyfs-matrix sync` and the matrix lookup do since
0.32.0. The sync itself, its levels, its conflicts and the matrix owners
are described in [Storage and sync](storage-and-sync.md).

## Every simulation folder, recorded or not

A sync compares every `sims/sim_*` folder of main and of the other
workspace, compacted ones (`sims/sim_<id>.zip`) included, and not only the
simulations a record names. The preview prints:

```text
  sims/: 4 in main, 6 in other, 3 in both
    without a record: 2002, 2003, 3000
    run again with --restore --apply to rebuild their records
```

"Without a record" names every folder main holds, or will hold once the
sync is applied, that no record of the merged manifest carries: typically
folders copied by hand from a cluster. A folder whose simulation was
deleted with `pyfs-matrix delete-sims` is accounted for by its note and is
not listed, and neither is a simulation of the other workspace that the
level does not bring (a compacted one below `all`, or a folder holding
nothing the level copies): it is counted in the other workspace only.

## Restoring their records, only when asked

The sync never writes a record it did not merge unless asked:

```text
pyfs-matrix sync runs --workspace .                     # preview: lists the folders
pyfs-matrix sync runs --workspace . --restore           # preview: says they would be restored
pyfs-matrix sync runs --workspace . --restore --apply   # copies, then rebuilds their records
```

With `--restore --apply`, once the files are copied and the `runs.json`
lease is released, the sync rebuilds the records of those folders through
`pyfs-matrix rebuild`, which proves each record and marks it `REBUILT`.
A refusal of the rebuild is printed and recorded in `storage_management.json`; the files the sync
copied stand. `--restore` is refused with `--runs` naming another
manifest, because the rebuild appends to `runs.json` only.

## Archive folders are skipped

Every file under a folder named `archive` is skipped by default: the
`post/<matrix>/**/archive/<stamp>/` folders earlier posts left, and any
`archive/` inside a simulation. The preview says how much was skipped:

```text
  archive: 120 file(s), 18.4 MB skipped (--include-archives brings them)
```

`--include-archives` brings them.

## A copy is never partial

Each file is copied to a temporary name in the target's folder
(`.<name>.<pid>.pyfs-sync.tmp`), checked against the source's digest, and
only then renamed over the target. An interrupted sync leaves the target
as it was: absent, or main's own copy. With `--overwrite`, main's copy is
archived under `archive/sync-<stamp>/` by a copy and stays in place until
its replacement is whole.

## One writer at a time

The sync holds the `runs.json` lease (`runs.json.lock`) from the merge of
the records to the end of the copy. A `pyfs-matrix restore` refuses while
the lease is held, and a run, a collect or another sync waits for it or is
refused. A sync started while the lease is held is refused.

## Another manifest: `--runs NAME`

`sync`, `free-space` and `delete-sims` take `--runs NAME`, a JSON file
directly in the workspace root, such as one `pyfs-matrix rebuild --out`
wrote:

| command | what `--runs NAME` does |
|---|---|
| `sync` | merges the other workspace's `runs.json` into `NAME` in main; main's `runs.json` is not touched |
| `delete-sims` | reads the records from `NAME` and removes them from it, archiving it first as `archive/<stem>-<stamp>.json`; `--matrix-products regenerate` is refused with it |
| `free-space` | reads `NAME` in addition to `runs.json`: a file either names is kept, a simulation `SUBMITTED` in either is left alone |

## The two matrix homes

A workspace keeps its matrices at its root or in `inputs/matrices/`, and
both are equal homes for every command that takes a matrix or looks one up
(since 0.33.0, FR-310): `upgrade`, `convert`, `plan`, `inspect-setups`,
`run`, `post` (its matrix and `--additional-pproc`), `rebuild --matrix` and
the rebuild's own scan, `rename`, `sync`, the Excel synchronization with and
without `--matrix`, and the physics check of `pyfs-qa`. `space-in-use` and
`free-space` read no matrix, and `delete-sims --matrix-products regenerate`
reads it through the post. All of them ask one lookup:

- a value that names its folder (`inputs/matrices/wing.fs`, an absolute
  path) is read from that folder, as before;
- a bare file name or a stem (`wing.fs`, `wing`) is looked up in both
  homes of the command's `--workspace`, the working directory for `upgrade`
  and `convert`, which take none; a name in neither home is read as given;
- one stem in both homes is read once when the two files hold the same
  bytes;
- with different bytes it is refused before any work, naming both paths:
  every command stops, except `post`, which warns naming both and falls
  back to the run records.

`restore --matrix` names the folder under `post/` by the matrix's stem and
reads no matrix file. Keep one copy, or make the two identical.
