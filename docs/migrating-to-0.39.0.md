# Migrating to 0.39.0

> Frozen record: not edited after its release.

Nothing is removed, and a matrix, setup or pproc of 0.38.0 renders the same
scripts. Four readings change, and each is below with what to do: a steady
point stopped at its requested iteration limit without settling gets a new
status, `MAX_ITER_REACHED`, which a 0.38.0 reader refuses; a quoted `--sims`
of several ids reads as several ids; the automatic tag of a long refinement
selection becomes a summary and a short hash; and `--ignore-missing-families
false` reaches every key that cites a surface. Two options of the mesh verbs
are renamed, the old names kept as deprecated aliases. The release adds a
`[study]` table to the reference artifact (FR-435) and two workspace files,
`pyfs.toml` and `pyfs.local.toml` (FR-436), each read only where it exists.

## A new terminal status: `MAX_ITER_REACHED` (FR-434)

A steady point, alone or in a steady job, is recorded `MAX_ITER_REACHED` when
the iteration counter of its evidence (the solver log, else the loads
footer) equals the iteration limit the run requested and the residual
history of its solver log shows that it did not settle: the final residual
is above the convergence limit. On 0.38.0 such a point read
`COMPLETED_MAX_ITER`, as an unsteady run that ended its time loop does. The
closed set of terminal statuses of FR-46 gains this one value.

It is not a failure, and every reader treats it as `COMPLETED_MAX_ITER` is
treated: the post writes every product of the point, with one WARNING in
`post.log` naming the point and the limit; `run --resume` does not run it
again; `status` counts it apart from the converged points; the cost
estimate, `delete-sims` and the grouped collect read it as an ended run. The
record keeps `iterations` for the counter reached and gains
`iterations_requested`, the requested limit, written only for this status:

```json
{"status": "MAX_ITER_REACHED", "iterations": 500, "iterations_requested": 500}
```

A point whose evidence does not show the counter at the limit, or whose log
gives no readable residual (no log, or iterations forced with no residual
threshold), keeps `COMPLETED_MAX_ITER`; an unsteady point keeps it too.

What to do:

- **Do not open a workspace collected by 0.39.0 with 0.38.0.** A manifest
  holding `MAX_ITER_REACHED` is refused by the 0.38.0 reader. A record written
  by an earlier release is never rewritten and reads as it was.
- **A list of statuses you wrote names the new one only if you add it.** A
  status filter in a script, a storage rule (`status = ["CONVERGED",
  "COMPLETED_MAX_ITER"]`) or a `status --status WORD` meant for every ended
  steady point adds `MAX_ITER_REACHED`.

## A quoted `--sims` of several ids is several ids (NFR-45 R2)

The commands that read `--sims` as one value, `mark-failed`, `rebuild`,
`delete-sims`, `post`, `collect`, `status` and `log`, read a blank or a tab
between ids as a comma. `--sims "2006 2007"` is the two ids 2006 and 2007;
on 0.38.0 it was the single id `20062007`, which matched nothing or the
wrong simulation. Every form accepted before (`2006,2007`, `[2006,2007]`,
`2006, 2007`) reads the same ids. The forms each command takes are in
[Restore and rebuild the run records](restore-and-rebuild.md).

## Renamed options of the mesh verbs (NFR-45 R2, R6)

The mesh verbs take `--out`, as their sibling commands do (`rebuild --out`,
`pyfs-workspace ... --out`). The old names stay as deprecated aliases: each
gives the identical result and warns once that it is deprecated, and an
alias given together with `--out` is refused, naming both.

| 0.38.0 command line | 0.39.0 command line |
|---|---|
| `pyfs-matrix refine MESH ... --out-dir DIR` | `pyfs-matrix refine MESH ... --out DIR` |
| `pyfs-matrix audit-mesh OBJ ... --csv FILE` | `pyfs-matrix audit-mesh OBJ ... --out FILE` |

Replace the old names in scripts and notes now; nothing else of either
command changes.

## The level folder of a long selection (FR-433)

A tag `refine` builds from the selection stays the 0.38.0 tag while it is at
most 32 characters (`R2`, `R-Wing2-Tip1p5`). A longer one, from a selection
of many families or long family names, becomes `R-<n>fam-<hash>`: the number
of selected families and the first 8 hexadecimal characters of the SHA-256
of the canonical selection, a folder such as `W1_R-12fam-<hash>`. On 0.38.0
such a selection could write a folder name past the Windows path limit and
fail after all its work. The level's `refine.json` records the selected
families, in the source's order, under `tag_selection`.

What to do: a script that built a level's folder name from its selection
reads it from `RefinedMesh.folder` (or from the folder `refine` prints), or
names the level itself with `[refine] tag` in the refinement file, which is
used as given.

A family that keeps its first row (below) writes `k` in its part of the tag,
so a level with kept rows and one without never share a folder.

## `--ignore-missing-families false` reaches every key that cites a surface (FR-435 R10)

Under `--ignore-missing-families false`, a name that selects nothing on the
row's model refuses the row on every key that cites a surface: the setup's
`delete_surfaces`, `analysis_families`, `vorticity_drag_families`,
`axial_separation_families` and the `boundary` of each
`base_region_operations` entry, and the pproc's `base_regions` and the
members of each `[groups]` entry. On 0.38.0 the flag left the `*_families`
keys and the `[groups]` members silent. A row planned with the flag that
cites, in one of those, a name its model does not carry is now refused,
naming the key, the name and the flag. At the default value of the flag
nothing changes for a reference without `[study]`.

## New: the study's surfaces in the reference (FR-435)

A reference artifact may declare the surfaces of a study in a top-level
`[study]` table, so that one setup, one pproc and one reference serve every
model of the study (a wing-body and a wing-body-tail, say):

```toml title="inputs/references/r010.toml"
[study]
surfaces = ["Wing", "Body", "Base", "HTail", "VTail", "TailBase", "Sting"]
```

On a row citing such a reference, a name the vocabulary holds and the row's
model does not carry is skipped where it is cited, said once per artifact,
key and name as a plan WARNING naming every row that lacks it, and listed in
each point's run record under `skipped_names`. A name the vocabulary does
not hold and the model does not carry is a misspelling, and the row is
BLOCKED at plan. The reading is described in
[The reference artifact](workflow-reference-artifact.md#one-setup-for-every-model-of-a-study).

A reference without `[study]` plans, emits, records and refuses as on
0.38.0, and a top-level table named `study` that states a `kind` stays the
block it was.

## New: the workspace settings files (FR-436)

`pyfs.toml` at the workspace root and `pyfs.local.toml` beside it state the
defaults of the `pyfs-matrix` options: the version, the HPC profile, the
cost file, the acceptance of an unregistered build, how much the console
says, and the other keys listed in
[The workspace settings files](workspace-settings.md). A workspace without
either file runs as before.

What to do:

- **A file already named `pyfs.toml` or `pyfs.local.toml` at a workspace
  root is now read.** Rename it if it is not a settings file: a key the
  package does not know is refused, naming the key and the file, before any
  work.
- **Keep `pyfs.local.toml` out of version control**, as
  `inputs/executables.local.toml` is: it is this machine's overlay.
- `accept_unregistered_build = true` may be stated on a table entry of
  `inputs/executables.local.toml`, accepting that entry's build only; in
  `inputs/executables.toml` the key is refused.
- `plan.json` and every run record carry `settings_sources`, naming each
  value taken from a file and the file it came from; the field is absent
  when nothing came from a file.
- `--log-level quiet|normal|verbose` sits beside `--verbose`, which is kept
  as `--log-level verbose`. `--no-accept-unregistered-build`,
  `--no-check-frozen`, `--no-local` and `--no-pproc-warnings` turn an option
  off for one command whatever the files state.

## New in the refinement

- **Keeping the first row at another component** (FR-430). A grid family with
  a trailing edge can keep the spanwise width of its row of panels at each
  end station that meets another component: `keep_first_row = true` in its
  `[families.<name>]` table, `pyfs-matrix refine --keep-first-row
  FAMILY[,FAMILY...]`, or `refine_mesh(..., keep_first_row=["Wing"])`. See
  [Keeping the row at an interface](mesh/how-to.md#keeping-the-row-at-an-interface).
- **A neighbour the band covers whole** (FR-431). A selection whose unchanged
  neighbour is two face layers deep or less stopped on 0.38.0 with an
  internal error. The neighbour is now rebuilt whole at factor 1, with one
  warning naming it, and `refine.json` records it as `"method":
  "rebuilt_whole"`, `"reason": "band_covers_family"`.
- **A family rebuilt at factor 1 beside a refined side** (FR-432) takes the
  spacing of the edge it shares with that side, so its faces near the shared
  curve differ from the 0.38.0 level of the same selection. Refine such a
  level again before comparing it with a level refined by 0.39.0; a family
  that shares no curve with a refined side is unchanged. `refine.json`
  records `shared_edge_target_m` under each such family.

## A point submitted without a list of its logs (FR-413 R8)

A record that carries no `submission["declared_logs"]`, as a point submitted
by an older release does not, now takes the names of its solver logs from
the job's own script on disk. A collect or a rebuild of such a point whose
outputs are all present and whose log is gone records `RAN_MISSING_LOG`
where 0.38.0 kept waiting on it. A recorded list, an empty one included,
stays authoritative.

## A sweeper export with an unknown header (NFR-45 R2)

`mark-converged` still refuses a sweeper export with an unknown header, and the
refusal now names the column that differs: for each known layout, the first
differing column with its position, the expected name and the name found, or
the counts when the header is a prefix. Nothing to change in a file it
accepted before.

## `refine` and `audit-mesh` read `[trailing_edges] detect` like the workflow (NFR-45 R3)

A `[trailing_edges] detect` shape the workflow refuses (a word other than
`"auto"`, a key it does not read, an empty surface list, `file` and `detect`
together) is now refused by `refine` and `audit-mesh` too, before any work and
in the same words, ending `Nothing was written.`. 0.38.0 ignored such a shape
in the mesh verbs, so a refinement file that carried one ran there and is
refused here: correct the table as the message says.

## The guides are built from the release sources (NFR-46)

The user guide and cheatsheet are available from [PDF guides](guides.md); each PDF names the release
it was built from and has its build log beside it. Nothing changes for a
workflow; take the guides of the release you installed.

## New fields

| field | where | written when | requirement |
|---|---|---|---|
| `iterations_requested` | run record | the status is `MAX_ITER_REACHED` | FR-434 |
| `skipped_names` | run record | the point's row skipped a name its study declares | FR-435 |
| `settings_sources` | `plan.json`, run record | a value or the acceptance came from a file | FR-436 |
| `kept_rows`, `trailing_edge` | `refine.json`, family entry | the family keeps its first row | FR-430 |
| `"method": "rebuilt_whole"`, `reason`, `band`, `faces` | `refine.json`, family entry | the band covered the family | FR-431 |
| `shared_edge_target_m` | `refine.json`, family entry | a family rebuilt at factor 1 shares a curve with a refined side | FR-432 |
| `tag_selection` | `refine.json` | the tag is the summary and the hash | FR-433 |

A key added to `refine.json` does not change its `schema_version`. A record
without these fields reads as before.
