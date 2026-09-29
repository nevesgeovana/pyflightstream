# Storage and sync

A campaign workspace grows: simulation folders, post products, archived
copies of a superseded product. This page covers the four `pyfs-matrix`
commands that manage that growth, the recipe file that drives two of them,
the record they all write, and the workspace sync that brings runs and
results together from several machines.

Every command below previews by default and changes files only when you
pass `--apply`. Run the preview first, read it, then apply.

## The four commands

### space-in-use

```bash
pyfs-matrix space-in-use --workspace .
```

Prints the sizes on disk in three groupings, in this order: by top level
folder (`sims/`, `post/`, `inputs/`, and so on), by simulation
(`sims/sim_*`, a compacted simulation included), and by extension. It
changes nothing. `--top N` limits how many rows print per grouping; the
default is 15.

You can also write it as a flag on the main command line:

```bash
pyfs-matrix --workspace . --space-in-use
```

### free-space

```bash
pyfs-matrix free-space m001 --workspace . --apply
```

Runs a recipe named `m<id>`, read from
`inputs/management/m<id>.toml`. Without `--apply` it only reports what it
would do. A recipe holds up to four tables, run in this order: pruning an
unsteady point's per-step exports to its last step, compacting simulation
folders, deleting files of named extensions, and compacting or deleting the
post's archived folders. See "The recipe file" below for the
format of each.

The owner's flag form works here too:

```bash
pyfs-matrix --workspace . --free-space m001
```

### delete-sims

```bash
pyfs-matrix delete-sims 4001,2009 --workspace . --apply
```

Deletes the named simulations outright: the `sims/sim_<id>` folder (or its
compacted zip), the post products that belong only to that simulation, and
its rows in `runs.json`. The ids are comma separated; the owner's bracketed
form, `[4001,2009]`, is also accepted.

If a post product mixes the deleted simulation's points with points from
other simulations, applying the command needs `--matrix-products`:

- `points-only` leaves that product on disk, recorded as stale (it still
  holds the deleted points, and nothing rebuilds it for you);
- `regenerate` reruns that matrix's post without the deleted points, so the
  product on disk agrees with what remains.

Without one of the two, `--apply` refuses and names the product it cannot
decide about. Preview (no `--apply`) never needs the flag: it only reports
what would be shared.

See "What a deleted simulation leaves behind" below for what happens to its
row in `runs.json` and whether its id can be used again.

### sync

```bash
pyfs-matrix sync post --workspace . --apply
```

Brings runs and results from the other workspaces named in
`inputs/sync-workspaces.toml` into the main workspace. See "Sync" below for
the configuration file, the levels, and how a conflict is settled.

## The recipe file

A recipe lives at `inputs/management/m<id>.toml`, where `<id>` is anything
after the leading `m` (so the file for `pyfs-matrix free-space m001` is
`inputs/management/m001.toml`). It holds four tables, each a list of
steps, run in the order the sections below list them. A table you leave
out simply runs no steps of that kind.

### `[[prune_step_exports]]`: keep only the last step of each per-step export

```toml
[[prune_step_exports]]
sims = "all"
status = ["CONVERGED", "COMPLETED_MAX_ITER"]
```

For an unsteady row that exports at every step
(`EXPORT_UNSTEADY_AFTER_ITER` or `EXPORT_UNSTEADY_AFTER_REV`), the solver
writes one file per step and export where the point ran, stamped
`<name>_iteration=<step>` before the extension (`.txt`, `.dat`, `.vtk` or
`.csv`): the loads, the sectional loads (`_sloads`), the Cp sections
(`_cp`), the probes (`_probes`) and each surface. This table keeps the LAST
step of each of those exports, point by point, and deletes the earlier
steps.

- `sims` and `status` select simulations exactly as for `compact_sims`.
- Each export keeps its own last step: a probe export that stopped one step
  before the loads keeps that step, it is not deleted for want of the later
  one.
- A simulation with any run still `SUBMITTED` is refused and keeps every
  step.
- The declared outputs, the scripts, the logs and every file a run record
  names are never deleted (see "What is protected, and why" below), and
  nothing under a simulation's `inputs` is read, whether it is a link into
  the geometry library or a staged copy.

The recorded call lists, for each point folder, the runs it belongs to, the
steps deleted (`deleted_steps`), every file deleted with its step and size,
and the files kept. Once applied, the listings of the deleted files leave
the matrix's `products.json`, with a `pruned_by_storage` note saying which
and when, because that manifest never names a file that is not on disk.

What happens to the post afterwards:

- A product made before the call stays as it was: the series table, the
  time-averaged surface or the section distribution built from every step
  keeps its file and its entry in `products.json`. A later `post` does not
  rebuild it, marks the entry `kept_after_pruning` with the reason, and does
  not archive it.
- A product a later `post` would build from a window that includes a
  deleted step is refused, never written from the steps that remain. The
  refusal is recorded in `products.json` under `skipped`, under the
  product's name, and names the missing steps, the first missing file and
  the call of `storage_management.json` that deleted them.
- A step that was never exported, which no storage call deleted, keeps the
  rule it had before: the series is written from the steps that exist, and
  the time-averaged surface is skipped naming the step.

Run the post you need over the full window before pruning, and prune only
the simulations whose per-step history you will not need again.

### `[[compact_sims]]`: zip a simulation folder

```toml
[[compact_sims]]
sims = "all"
status = ["CONVERGED", "COMPLETED_MAX_ITER"]
older_than_days = 30
```

- `sims` is `"all"` or a list of simulation ids, for example
  `["4001", "4002"]`.
- `status` is optional: only simulations whose every recorded run carries
  one of the named statuses are eligible. Leave it out to consider every
  simulation regardless of status.
- `older_than_days` is optional: only a folder whose modification time is
  at least this many days in the past is eligible. Leave it out to
  consider every eligible folder regardless of age.

A simulation with any run still `SUBMITTED` is refused, never compacted,
because collecting that run still needs the folder.

The result is `sims/sim_<id>.zip`. The folder is gone from disk, but
nothing that reads a simulation has to know that: `post`, `collect` and a
continuation restore the folder automatically, in place, the moment they
need it, and check every restored file's hash against what was recorded at
compaction time.

### `[[delete_extensions]]`: delete files of named extensions

```toml
[[delete_extensions]]
extensions = [".vtk"]
sims = "all"
```

- `extensions` names the file extensions to delete under `sims/`, for
  example `[".vtk", ".png"]`. Every entry must start with a dot.
- `sims` is `"all"` or a list of ids, exactly as for `compact_sims`.

An extension a run record needs to reopen its post processing can never be
named here: `.fsm`, the saved simulation, is refused outright, and the
recipe is rejected before it touches a single file. See "What is protected,
and why" below for the rest of what a recipe never deletes even when its
extension matches.

### `[[post_archives]]`: compact or delete the post's archived folders

```toml
[[post_archives]]
action = "compact"
keep_latest = 2
older_than_days = 14
```

- `action` is `"compact"` (zip the archived folder, then remove it) or
  `"delete"` (remove it outright).
- `keep_latest` is how many of the newest archived folders, per matrix, are
  left alone regardless of age. The default is 0.
- `older_than_days` is optional, exactly as above.

When a matrix's post writes a new copy of a product over an old one, the
old copy moves to `post/<matrix>/archive/<stamp>/` rather than being lost.
This table is how you reclaim the space those superseded copies hold once
you no longer need them.

## What is protected, and why

A recipe touches `sims/` and the post's archived folders only. It never
touches `inputs/`, a matrix file, or `storage_management.json` itself.

Within a simulation folder, the following are never deleted by a recipe,
even when their extension is named in `delete_extensions`:

- the saved simulation, `.fsm`;
- everything under a `scripts/` folder;
- every log file (anything ending `_log.txt` or `.log`, and the solver's
  own runtime log by name);
- every file a run record names or hashes: a declared output, a staged
  input, the executed script.

These are what a later `post` needs to extract the post processing again,
or what a person needs to see why a run ended the way it did. Deleting them
would make a workspace's remaining records unusable rather than merely
smaller.

## storage_management.json

Every call to any of the four commands, including `space-in-use`, is
recorded as one entry in `storage_management.json` at the workspace root.
The file's schema is `pyfs-storage/1`. It is the same schema the older
standalone `fts_sync.py` script wrote, and a file that script started is
continued rather than replaced: if you have been using that script, this
package picks up its record where it left off.

Each entry carries when the call ran, which tool and version made it,
whether it changed files, and the full detail of what it did or would do.
An automatic restore of a compacted simulation (by `post`, `collect` or a
continuation) is recorded too, with the reason it happened.

## What a deleted simulation leaves behind

`delete-sims` never leaves a workspace unable to say that a simulation
existed. When it deletes simulation `4001`, its rows leave `runs.json` (the
manifest is archived first, so nothing is lost) and one short note row
takes their place:

```json
{
  "run_id": "deleted/sim_4001/20260928-101500",
  "deleted_sim": "4001",
  "deleted_at": "2026-09-28T10:15:00+00:00",
  "deleted_run_ids": ["camp/sim_4001/AL+000"],
  "note": "this simulation id belonged to a simulation deleted by pyfs-matrix delete-sims; the full entry is call 7 of storage_management.json",
  "storage_entry": 7
}
```

That row is a note, not a run record, and every reader of the manifest
knows it: it is skipped when the manifest is read as run records, so it
never appears as a phantom run in a table or a report. It stays in
`runs.json` only so that a later sync from another workspace, or a person
reading the file directly, can see that the id was used and deliberately
retired rather than simply missing.

Because the id is retired rather than reserved, it can be reused: nothing
stops a later run from being recorded under simulation id `4001` again.

THE MESH IS NEVER DELETED WITH A SIMULATION. A simulation's `inputs` folder
is usually a link (a junction on Windows) into `inputs/geometries/`. Before
anything is removed, `delete-sims` undoes every link inside the simulation
folder, and it refuses to remove the folder while one is still there; the
links undone are recorded. The same holds when `free-space` compacts a
simulation.

## Sync

`sync` reads `inputs/sync-workspaces.toml`, which names the main workspace
and every workspace it can pull from:

```toml
main = "central"

[workspaces.central]
path = "."
matrices = ["matriz", "matriz_rotor"]

[workspaces.station-b]
path = "//shared/station-b/campaign"
matrices = ["matriz_hpc"]
```

`main` names which entry is the workspace you are standing in; `sync` is
run there. Every other named workspace is a source `sync` can pull from,
by name, with `--from station-b`, or all of them at once when `--from` is
left out.

`matrices` names the matrices each workspace OWNS, by stem (the file is
`<stem>.fs` at the workspace root or in `inputs/matrices/`). A matrix
belongs to one workspace and one only; a workspace may own several. A stem
declared by two workspaces refuses the sync, and so does a matrix file, in
the main workspace or in a source, that no workspace declares.

### Levels

The level you pass is cumulative, each one bringing everything the level
before it brings, plus more:

- `runs`: the run records in `runs.json`, and the provenance every record
  needs to be believed, each simulation's `scripts/` folder and its
  datapoint logs.
- `post`: the above, plus the `post/` folder, the products and the
  provenance that explains them.
- `fsm`: the above, plus the saved simulation of every datapoint.
- `all`: the above, plus everything else under `sims/`, except an `inputs`
  folder that is a junction into the input library, which is never
  followed or copied.

At every level, each simulation folder the sync brings gets its `inputs`
LINKED into the main workspace's own `inputs/geometries/`, to the same
geometry folder the source's simulation was linked to, so no copy of a
mesh is ever made. A geometry the main library does not have is not linked,
and the sync says so for that simulation. A source that staged a copy of
its inputs instead of a link is not copied either.

At every level, the matrices are compared too (next section).

### How a conflict is settled

A record present only in the other workspace is added. A record present in
both, identical in both, is left alone. When they differ: if the main
workspace's own record is still `SUBMITTED`, the other one's record wins,
because a submitted job with no result yet is not a record worth keeping
over a finished one. Otherwise main wins unless you pass `--prefer-other`,
in which case the other workspace's record replaces main's.

A simulation still `SUBMITTED` in the other workspace has its record
brought over, but none of its files: there is nothing finished yet worth
copying, and copying a job's files while it may still be writing them
would be copying a result mid write.

A file present in both workspaces, with different content, is a conflict:
main's copy is kept unless you pass `--overwrite`, which archives main's
copy to `archive/sync-<stamp>/` first and then takes the other workspace's
copy. Nothing is ever silently discarded.

A MATRIX is different: any difference between main's copy and the source's
is reported as a MERGE CONFLICT, every time, and the workspace that owns the
matrix wins. When the source owns it, main's copy is archived to
`archive/sync-<stamp>/` and replaced by the owner's; when main (or a third
workspace) owns it, main's copy stays. A matrix that only the source has is
copied when the source owns it and left out, with the reason, when it does
not. `--prefer-other` and `--overwrite` do not apply to matrices: ownership
decides.

Before rewriting `runs.json`, the previous copy is archived to
`archive/runs-<stamp>.json`. A `runs.json.lock` in the main workspace (a
run in progress here) refuses the sync; one in a source workspace skips
that source, recorded with the reason, rather than reading a manifest mid
write.

A run id that a note row says `delete-sims` deleted in the main workspace
is never brought back by a sync: the note row records exactly which ids
were retired, and a sync that saw only "this id is not in `runs.json`"
would happily reintroduce something the workspace deliberately let go.

Every sync call, one entry per source workspace, is recorded in
`storage_management.json`, exactly like the other three commands.

## The plan disk warning

`pyfs-matrix plan` estimates whether the points it is about to run will fit
on the workspace's disk. The estimate is the mean size of a datapoint
folder already recorded in this workspace, times the number of points
still to run, checked against the disk's free space with a margin. When it
looks like the run will not fit, the plan prints a warning naming
`free-space` as the command that makes room, after `space-in-use` has shown
where the space is going. A workspace with nothing recorded yet, or a disk
that cannot be measured, prints nothing: there is no basis for an estimate.
