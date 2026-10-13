# pyfs-matrix

Generated from the argument parser at build time, so this page and `pyfs-matrix --help` cannot disagree. The entry point is `pyflightstream.run.cli:main`.

## `pyfs-matrix`

Run-matrix tooling: the matrix is a first-class interface of the file-managed modality, with campaign.toml as the canonical internal form.

```text
usage: pyfs-matrix [-h] {upgrade,rename,inventory,space-in-use,free-space,delete-sims,sync,restore,rebuild,mark-failed,convert,plan,inspect-setups,run,collect,post,degenerate,status,show,log,trace,history,diff,mark-converged,refine,audit-mesh}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `pyfs-matrix upgrade`: convert a matrix written under an older layout to the current one (what moves depends on the layout it entered at, see --help)
- `pyfs-matrix rename`: rename a workspace written under 0.20.x to the 0.21.0 point names
- `pyfs-matrix inventory`: write &lt;stem>.boundaries.toml beside a saved simulation, from its mesh block, or beside an OBJ, from its groups
- `pyfs-matrix space-in-use`: report the sizes on disk: by top-level folder, by sims/sim_*, by extension
- `pyfs-matrix free-space`: run a storage recipe inputs/management/m&lt;id>.toml (preview unless --apply)
- `pyfs-matrix delete-sims`: delete simulations, their post products and their records (preview unless --apply)
- `pyfs-matrix sync`: bring runs and results from the workspaces in inputs/sync-workspaces.toml
- `pyfs-matrix restore`: restore runs.json or another records file from archive/ (preview unless --apply)
- `pyfs-matrix rebuild`: rebuild run records from the folders under sims/ (preview unless --apply)
- `pyfs-matrix mark-failed`: mark every run record of the named simulations FAILED_MARKED, whatever it ended in (preview unless --apply)
- `pyfs-matrix convert`: emit the native campaign.toml equivalent of a matrix
- `pyfs-matrix plan`: bind the matrix to the workspace input library and pre-flight every point, executing nothing. REQUIRED BEFORE `run` since v0.17.0: it writes the receipt that command asks for, pinned to the digest of the matrix it read
- `pyfs-matrix inspect-setups`:
- `pyfs-matrix run`: run every active point of the matrix and write the sweep table
- `pyfs-matrix collect`: collect a submitted job's outputs when they land, then post
- `pyfs-matrix post`: rebuild the post-processed CSV products from the manifest, with no solver
- `pyfs-matrix degenerate`: derive a degenerate geometry, the thin blade first, from a blade mesh and write it beside the source
- `pyfs-matrix status`: one row per polar: simulation, polar, sweep, datapoints, matrix and status (reads only)
- `pyfs-matrix show`: print an outcome-first datapoint card (reads only)
- `pyfs-matrix log`: read recorded activity, post or storage calls
- `pyfs-matrix trace`: follow an indexed product to its runs (reads only)
- `pyfs-matrix history`: every record of a simulation or point, including archives (reads only)
- `pyfs-matrix diff`: compare two runs' recorded identities and scripts (reads only)
- `pyfs-matrix mark-converged`: record your verdict that the named points CONVERGED, with its reason (preview unless --apply)
- `pyfs-matrix refine`: refine or coarsen a panel mesh from its OBJ into a new geometry folder
- `pyfs-matrix audit-mesh`: audit a panel mesh's topology, trailing edge and panel quality, alone or against the source it was made from

### `pyfs-matrix upgrade`

What an upgrade moves depends on the layout the file entered at. A file at the v0.8.x layout crosses the REmi boundary and its numbers will differ; a file whose SWEEP_TYPE column is folded keeps every run identity, so a resume still finds its records. The command says which applied to the file you named.

```text
usage: pyfs-matrix upgrade [-h] [--in-place] [--inputs DIR] matrix
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<matrix>` |  |  | path of the run matrix to upgrade |
| `--in-place` |  |  | rewrite the file; without it the upgraded matrix goes to standard output |
| `--inputs` | `DIR` |  | the workspace inputs/ directory whose groups library moves to pproc (inputs/groups/e001.toml becomes inputs/pproc/p001.toml under [groups]); needs --in-place, because the matrix cells that name the files are rewritten with them |

### `pyfs-matrix rename`

A point is named by its flight condition since 0.21.0, and a workspace written before it carries the earlier tag in every run_id, folder and file. This reads the matrices beside runs.json, works out the new name of every record from its row and its recorded point, and moves ALL of it: the datapoint folders, the scripts, the collected files, the manifest and the plan. It prints every change and a second run makes none. It refuses, before touching anything, a record whose row is gone, a record whose point the matrix no longer holds, two records that would share a name, and a SUBMITTED record whose folder would move: collect those first. See docs/migrating-to-0.21.0.md.

```text
usage: pyfs-matrix rename [-h] [--workspace WORKSPACE] [--dry-run]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--workspace` | `WORKSPACE` | `.` | managed campaign root carrying runs.json (default: the current directory) |
| `--dry-run` |  |  | print what would move and change nothing, which is the rehearsal to read before the workspace is rewritten |

### `pyfs-matrix inventory`

Reads the mesh block of a saved simulation and writes its boundary order as a sidecar beside it; a run whose sidecar disagrees with the file is refused before the solver starts. Needs no executable. For an OBJ the order is its groups that hold a face, in the order of the file, which is what a plan writes when the OBJ has no sidecar; an OBJ's existing sidecar is never rewritten.

```text
usage: pyfs-matrix inventory [-h] [--overwrite] [--clean] geometry
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<geometry>` |  |  | a saved simulation or an OBJ under inputs/geometries/ |
| `--overwrite` |  |  | rewrite a saved simulation's sidecar that already exists; without it an existing one is refused |
| `--clean` |  |  | remove the unsteady solver actions saved in the simulation, which inventory otherwise names as a warning, keeping a copy &lt;file>.bak-&lt;stamp> beside it; an existing sidecar is then kept unless --overwrite  |

### `pyfs-matrix space-in-use`

Prints the workspace's sizes in three groupings, in this order: by top-level folder, by simulation (sims/sim_*, compacted ones included) and by extension. Changes no file; the call is recorded in storage_management.json.

```text
usage: pyfs-matrix space-in-use [-h] [--workspace WORKSPACE] [--top TOP]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--top` | `TOP` | `15` | rows shown per grouping (default: 15) |

### `pyfs-matrix free-space`

Runs the recipe's steps in order: [[prune_step_exports]] deletes an unsteady point's per-step exports (the *_iteration=&lt;step> files) except the last step of each export (keep_last = K keeps the last K steps, delete_steps = [A, B] deletes the steps A to B and keeps the rest), and a later post refuses a product that needs a deleted step, naming it; [[compact_sims]] zips a simulation folder into sims/sim_&lt;id>.zip (post, collect and a continuation restore it automatically), [[delete_extensions]] deletes files of the named extensions under sims/ except what a later post needs (saved simulations, scripts, logs, and every file a run record names or hashes), [[post_archives]] compacts or deletes the archive/&lt;stamp>/ folders the post wrote. Nothing outside sims/ and the post archives is touched. Every call is recorded in storage_management.json.

```text
usage: pyfs-matrix free-space [-h] [--workspace WORKSPACE] [--apply] [--list] [--runs NAME] recipe
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<recipe>` |  |  | the recipe id, m&lt;id> (inputs/management/m&lt;id>.toml) |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--apply` |  |  | change files; without it the command previews and changes nothing |
| `--list` |  |  | after each step, print every path it would touch (preview) or touched (--apply) with its size and what happens to it |
| `--runs` | `NAME` |  | the manifest file to read, directly in the workspace root (default: runs.json) |

### `pyfs-matrix delete-sims`

Deletes each named simulation: its sims/sim_&lt;id> folder (or zip), its own post products and its records in runs.json, which keeps one note row per simulation saying its id belonged to a deleted one. The full mention (id, matrix, run ids, statuses, dates, sizes and hashes, caller) is recorded in storage_management.json. The id may be reused afterwards. A product that mixes the deleted points with others needs --matrix-products: points-only leaves it, recorded stale; regenerate reruns that matrix's post without them.

```text
usage: pyfs-matrix delete-sims [-h] [--workspace WORKSPACE] [--matrix-products {points-only,regenerate}] [--force] [--apply] [--runs NAME] sims
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<sims>` |  |  | simulation ids, comma separated: 2006,2007 or [2006,2007]; one quoted value of words, '2006 2007', reads as two ids |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--matrix-products` | one of `points-only`, `regenerate` |  | what happens to a matrix product that also holds the deleted points |
| `--force` |  |  | delete a simulation whatever the status of its records; without it a simulation with a run still SUBMITTED is refused |
| `--apply` |  |  | change files; without it the command previews and changes nothing |
| `--runs` | `NAME` |  | the manifest file to read, directly in the workspace root (default: runs.json) |

### `pyfs-matrix sync`

Levels are cumulative: runs (runs.json and run provenance: scripts/ and the datapoint logs), post (+ post/), fsm (+ the datapoints' saved simulations), all (+ everything else under sims/). Run on the main workspace. A record only in the other workspace is added; a main record still SUBMITTED takes the other's; any other difference is a conflict where main wins unless --prefer-other. A simulation still SUBMITTED there syncs its record only. A file conflict keeps main's copy unless --overwrite, which archives it first. Nothing in main is deleted and inputs/ is never touched, except a declared matrix. MATRICES: each is declared in sync-workspaces.toml by the one workspace that owns it (matrices = ["&lt;stem>",...]); a difference is always reported as a MERGE CONFLICT and the owning workspace's copy wins. A synced simulation's inputs/ is linked into main's own geometry library, never copied. Every call is recorded in storage_management.json.

```text
usage: pyfs-matrix sync [-h] [--workspace WORKSPACE] [--from SOURCE] [--apply] [--prefer-other] [--overwrite] [--restore] [--include-archives] [--runs NAME] {runs,post,fsm,all}
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<level>` | one of `runs`, `post`, `fsm`, `all` |  | what to bring |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--from` | `SOURCE` |  | one workspace name from sync-workspaces.toml (default: every non-main one) |
| `--apply` |  |  | change files; without it the command previews and changes nothing |
| `--prefer-other` |  |  | on a runs.json conflict, take the other workspace's record |
| `--overwrite` |  |  | on a file conflict, archive main's copy and take the other's |
| `--restore` |  |  | with --apply, rebuild the records of the sims/ folders no record carries |
| `--include-archives` |  |  | also bring the files under folders named archive (skipped by default) |
| `--runs` | `NAME` |  | the manifest file to read, directly in the workspace root (default: runs.json) |

### `pyfs-matrix restore`

```text
usage: pyfs-matrix restore [-h] [--workspace WORKSPACE] [--stamp STAMP] [--matrix MATRIX] [--apply] {runs,storage,products,plan,additional}
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<kind>` | one of `runs`, `storage`, `products`, `plan`, `additional` |  | the file to restore |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--stamp` | `STAMP` |  | the archive stamp to restore from |
| `--matrix` | `MATRIX` |  | for products and plan: the matrix whose file to restore, when several have archives; its file path or its stem, as rebuild and post read it |
| `--apply` |  |  | change files; without it the command previews and changes nothing |

### `pyfs-matrix rebuild`

```text
usage: pyfs-matrix rebuild [-h] [--workspace WORKSPACE] [--out NAME] [--all-sims] [--sims SIMS] [--build-alias BUILD=ALIAS] [--matrix MATRIX] [--inputs-from FOLDER] [--apply]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--out` | `NAME` |  | the manifest file the rebuilt records go to, directly in the workspace root |
| `--all-sims` |  |  | rebuild every simulation folder on disk, recorded or not |
| `--sims` | `SIMS` |  | simulation ids, comma separated: 2006,2007 or [2006,2007]; one quoted value of words, '2006 2007', reads as two ids |
| `--build-alias` | `BUILD=ALIAS` | `[]` | the scheduler name of a solver build (repeatable) |
| `--matrix` | `MATRIX` |  | the matrix the simulations ran from |
| `--inputs-from` | `FOLDER` |  | another origin's inputs/ folder, laid over this workspace's for inputs that changed after the run; each record names the inputs taken from it |
| `--apply` |  |  | change files; without it the command previews and changes nothing |

### `pyfs-matrix mark-failed`

A run can end CONVERGED and be found wrong later. Its records become FAILED_MARKED, which the post, the re-run and delete-sims treat as any failure, and each keeps the status it had, when and why under 'marked'; runs.json is copied to archive/ first.

```text
usage: pyfs-matrix mark-failed [-h] --sims SIMS [SIMS...] [--reason REASON] [--points POINTS [POINTS...]] [--workspace WORKSPACE] [--apply]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--sims` | `SIMS` |  | simulation ids, comma separated: 2006,2007 or [2006,2007]; one quoted value of words, '2006 2007', reads as two ids; a run id alias (2006_3) marks that point's record alone Required. |
| `--reason` | `REASON` |  | why, recorded as given |
| `--points` | `POINTS` |  | point names to mark within the selected simulations |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--apply` |  |  | change files; without it the command previews and changes nothing |

### `pyfs-matrix convert`

```text
usage: pyfs-matrix convert [-h] [--name NAME] [--fs-version FS_VERSION] [--recipe CODE=MODULE:FUNCTION] --fs-exe FS_EXE [--out OUT] [-o OUTPUT] matrix
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<matrix>` |  |  | the pipe-delimited run matrix file |
| `--name` | `NAME` |  | campaign name; without it the workspace directory's name is the campaign's, and `convert`, which has no workspace, still needs it |
| `--fs-version` | `FS_VERSION` |  | the FlightStream version rows whose FS_BUILD cell is empty fall back to: canonical identifier (for example 26.120); a vendor release name works only where it names exactly one registered build. A matrix whose every active row fills FS_BUILD needs none  |
| `--recipe` | `CODE=MODULE:FUNCTION` | `[]` | FS_SCRIPT code to recipe reference (repeatable); replaces the import-by-number system |
| `--fs-exe` | `FS_EXE` |  | explicit path of the FlightStream executable (never guessed) Required. |
| `--out` | `OUT` |  | write the campaign.toml here instead of standard output |
| `-o`, `--output` | `OUTPUT` |  | deprecated alias of --out, with the identical result |

### `pyfs-matrix plan`

```text
usage: pyfs-matrix plan [-h] [--hpc NAME] [--name NAME] [--fs-version FS_VERSION] [--recipe CODE=MODULE:FUNCTION] [--setup-guidelines] [--setup-standards] [--ignore-missing-families [true|false]] [--no-ignore-missing-families] [--workflow CODE=NAME] [--workspace WORKSPACE] [--point-name POINT_NAME] [--fs-exe FS_EXE] [--cost] [--cost-file NAME] [--inflow-fft] [--update-ids] [--accept-unregistered-build | --no-accept-unregistered-build] [--sims SIM [SIM...]] [--points POINT [POINT...]] [--polar-sweep | --batch N] [--verbose | --log-level {quiet,normal,verbose}] matrix
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--hpc` | `NAME` |  | the HPC profile inputs/hpc/&lt;NAME>.toml to use when the workspace holds several (0.35) |
| `<matrix>` |  |  | the pipe-delimited run matrix file |
| `--name` | `NAME` |  | campaign name; without it the workspace directory's name is the campaign's, and `convert`, which has no workspace, still needs it |
| `--fs-version` | `FS_VERSION` |  | the FlightStream version rows whose FS_BUILD cell is empty fall back to: canonical identifier (for example 26.120); a vendor release name works only where it names exactly one registered build. A matrix whose every active row fills FS_BUILD needs none  |
| `--recipe` | `CODE=MODULE:FUNCTION` | `[]` | FS_SCRIPT code to recipe reference (repeatable); replaces the import-by-number system |
| `--setup-guidelines` |  |  | write inputs/setups/SETUP_GUIDELINES.md, preserving existing edits |
| `--setup-standards` |  |  | write commented s9XX setup standards, preserving existing edits |
| `--ignore-missing-families` | `true|false` |  | whether a family the opened mesh does not carry is left out (the default, true) or REFUSES the point (false). One artifact serves a wing-body and an isolated rotor because a family the geometry lacks is skipped; pass false when you believe this geometry carries every family the artifact names and want to hear about it if it does not  |
| `--no-ignore-missing-families` |  |  | the same choice as --ignore-missing-families false, written as a flag: a family the opened mesh does not carry REFUSES the point instead of being left out. Stating both is refused |
| `--workflow` | `CODE=NAME` | `[]` | FS_SCRIPT code to WORKFLOW type (repeatable); the same mapping `run` takes, so a workflow matrix can be pre-flighted before a seat is spent |
| `--workspace` | `WORKSPACE` | `.` | managed campaign root carrying the inputs/ library (default: the current directory) |
| `--point-name` | `POINT_NAME` | `{polar}` | the template that names each point's script and exports; the default is P&lt;sim>-&lt;point name>, the point name writing every variable the row's flight condition declares, in its order (0.21.0); {point}, {alpha}, {beta}, {mach}, {advance_ratio}, {sim} and {campaign} are the other placeholders  |
| `--fs-exe` | `FS_EXE` |  | explicit executable override; mandatory for MANUAL rows, otherwise the FS_BUILD column resolves through inputs/executables.toml |
| `--cost` |  |  | also table what each polar is expected to cost: mesh size, marked trailing edges, farfield layers, viscous coupling, steady or unsteady, time iterations, processors set, and an EXPECTED wall time fitted from this workspace's own recorded runs. The time is an extrapolation and the table says so, carrying the number of samples behind it; a point with no comparable recorded run reads 'unknown' rather than a number with no basis |
| `--cost-file` | `NAME` |  | the cost file inputs/costs/&lt;NAME>.toml that prices the points when the workspace holds several; a single file needs no name (0.35) |
| `--inflow-fft` |  |  | for every qsteady_rotor WHEEL point in a custom inflow, read the inflow's harmonic content as ONE BLADE meets it over a revolution (nP counts how many times one blade meets the perturbation per turn, in the blade's frame; not the N P a fixed surface or a balance under the whole rotor sees, where only multiples of N P survive): per point k_eff = n95 k_1P (min, max, mean, per cent of the span above 0.1), n_max and the suggested PASSAGE_POSITIONS >= n_max / N + 1, WARNED when the row states fewer; the reduced-frequency warning then reads k_eff |
| `--update-ids`, `--updateIDs` |  |  | before planning, REWRITE THIS MATRIX so that none of its POLs repeats one stated elsewhere in the workspace or earlier in this file: each repeated row takes the next free POL above every POL, run record and sims/ folder of the workspace, and every other matrix is left as it is. Each change is printed. A row whose POL already has runs of this matrix is refused rather than moved. THE RENUMBERING IS WRITTEN BEFORE THE PLAN RUNS and stays written if the plan then refuses |
| `--accept-unregistered-build` |  |  | run on an installed FlightStream build other than the one registered for the version a row names, instead of refusing it: its compatibility is then YOUR responsibility, the run warns, and every record says the flag was used and carries the build the solver printed. `plan` launches no solver and records the flag in plan.json, so it rehearses the same command line `run` executes |
| `--no-accept-unregistered-build` |  |  | refuse an installed build other than the registered one for this command, whatever pyfs.toml, pyfs.local.toml or a build entry of inputs/executables.local.toml states |
| `--sims` | `SIM` |  | plan or run only these simulations, by their ids as the matrix spells them (for example --sims 2031 2032 2033); every other simulation is left untouched. With `run --force-rerun-all`, the simulations to redo. An id the matrix does not carry is refused before anything runs |
| `--points` | `POINT` |  | with --sims, plan or run only these points of those simulations, by the point name the plan prints for each, or by its run id alias &lt;sim>_&lt;index> (2006_3, which names its simulation; the plan prints each); the matrix file is not edited and no other point is planned, staged or run. A point the matrix does not carry is refused before anything runs |
| `--polar-sweep` |  |  | run each simulation's points as ONE solver job (one polar per job). Combines with --local; a job holds steady or unsteady polars, never both. Each row left out is named by the plan: LEGACY rows, RESTART rows, steady rows stating COLD_START false, coupled rows on steady or qsteady_rotor, unsteady rows on a build without the unsteady action command, polars whose points do not splice into one job (a steady point that initialises the solver twice among them) and rows whose points are all recorded. Run those rows point by point, without this flag. |
| `--batch` | `N` |  | run the simulations' points as N solver jobs, polars split across them. Combines with --local; a job holds steady or unsteady polars, never both. Each row left out is named by the plan: LEGACY rows, RESTART rows, steady rows stating COLD_START false, coupled rows on steady or qsteady_rotor, unsteady rows on a build without the unsteady action command, polars whose points do not splice into one job (a steady point that initialises the solver twice among them) and rows whose points are all recorded. Run those rows point by point, without this flag. |
| `--verbose` |  |  | print every warning in Python's full format (file, line and source) and the started and finished lines of the stages printed only on request, such as [continuation]; logs/activity.log holds them either way (0.31.0) |
| `--log-level` | one of `quiet`, `normal`, `verbose` |  | how much the console says: quiet (the errors, the final summary line and the signature), normal (the default) or verbose (as --verbose); logs/activity.log keeps the full detail at every level. Default: [log] console of pyfs.local.toml or pyfs.toml, else normal |

### `pyfs-matrix inspect-setups`

```text
usage: pyfs-matrix plan [-h] [--hpc NAME] [--name NAME] [--fs-version FS_VERSION] [--recipe CODE=MODULE:FUNCTION] [--setup-guidelines] [--setup-standards] [--ignore-missing-families [true|false]] [--no-ignore-missing-families] [--workflow CODE=NAME] [--workspace WORKSPACE] [--point-name POINT_NAME] [--fs-exe FS_EXE] [--cost] [--cost-file NAME] [--inflow-fft] [--update-ids] [--accept-unregistered-build | --no-accept-unregistered-build] [--sims SIM [SIM...]] [--points POINT [POINT...]] [--polar-sweep | --batch N] [--verbose | --log-level {quiet,normal,verbose}] matrix
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--hpc` | `NAME` |  | the HPC profile inputs/hpc/&lt;NAME>.toml to use when the workspace holds several (0.35) |
| `<matrix>` |  |  | the pipe-delimited run matrix file |
| `--name` | `NAME` |  | campaign name; without it the workspace directory's name is the campaign's, and `convert`, which has no workspace, still needs it |
| `--fs-version` | `FS_VERSION` |  | the FlightStream version rows whose FS_BUILD cell is empty fall back to: canonical identifier (for example 26.120); a vendor release name works only where it names exactly one registered build. A matrix whose every active row fills FS_BUILD needs none  |
| `--recipe` | `CODE=MODULE:FUNCTION` | `[]` | FS_SCRIPT code to recipe reference (repeatable); replaces the import-by-number system |
| `--setup-guidelines` |  |  | write inputs/setups/SETUP_GUIDELINES.md, preserving existing edits |
| `--setup-standards` |  |  | write commented s9XX setup standards, preserving existing edits |
| `--ignore-missing-families` | `true|false` |  | whether a family the opened mesh does not carry is left out (the default, true) or REFUSES the point (false). One artifact serves a wing-body and an isolated rotor because a family the geometry lacks is skipped; pass false when you believe this geometry carries every family the artifact names and want to hear about it if it does not  |
| `--no-ignore-missing-families` |  |  | the same choice as --ignore-missing-families false, written as a flag: a family the opened mesh does not carry REFUSES the point instead of being left out. Stating both is refused |
| `--workflow` | `CODE=NAME` | `[]` | FS_SCRIPT code to WORKFLOW type (repeatable); the same mapping `run` takes, so a workflow matrix can be pre-flighted before a seat is spent |
| `--workspace` | `WORKSPACE` | `.` | managed campaign root carrying the inputs/ library (default: the current directory) |
| `--point-name` | `POINT_NAME` | `{polar}` | the template that names each point's script and exports; the default is P&lt;sim>-&lt;point name>, the point name writing every variable the row's flight condition declares, in its order (0.21.0); {point}, {alpha}, {beta}, {mach}, {advance_ratio}, {sim} and {campaign} are the other placeholders  |
| `--fs-exe` | `FS_EXE` |  | explicit executable override; mandatory for MANUAL rows, otherwise the FS_BUILD column resolves through inputs/executables.toml |
| `--cost` |  |  | also table what each polar is expected to cost: mesh size, marked trailing edges, farfield layers, viscous coupling, steady or unsteady, time iterations, processors set, and an EXPECTED wall time fitted from this workspace's own recorded runs. The time is an extrapolation and the table says so, carrying the number of samples behind it; a point with no comparable recorded run reads 'unknown' rather than a number with no basis |
| `--cost-file` | `NAME` |  | the cost file inputs/costs/&lt;NAME>.toml that prices the points when the workspace holds several; a single file needs no name (0.35) |
| `--inflow-fft` |  |  | for every qsteady_rotor WHEEL point in a custom inflow, read the inflow's harmonic content as ONE BLADE meets it over a revolution (nP counts how many times one blade meets the perturbation per turn, in the blade's frame; not the N P a fixed surface or a balance under the whole rotor sees, where only multiples of N P survive): per point k_eff = n95 k_1P (min, max, mean, per cent of the span above 0.1), n_max and the suggested PASSAGE_POSITIONS >= n_max / N + 1, WARNED when the row states fewer; the reduced-frequency warning then reads k_eff |
| `--update-ids`, `--updateIDs` |  |  | before planning, REWRITE THIS MATRIX so that none of its POLs repeats one stated elsewhere in the workspace or earlier in this file: each repeated row takes the next free POL above every POL, run record and sims/ folder of the workspace, and every other matrix is left as it is. Each change is printed. A row whose POL already has runs of this matrix is refused rather than moved. THE RENUMBERING IS WRITTEN BEFORE THE PLAN RUNS and stays written if the plan then refuses |
| `--accept-unregistered-build` |  |  | run on an installed FlightStream build other than the one registered for the version a row names, instead of refusing it: its compatibility is then YOUR responsibility, the run warns, and every record says the flag was used and carries the build the solver printed. `plan` launches no solver and records the flag in plan.json, so it rehearses the same command line `run` executes |
| `--no-accept-unregistered-build` |  |  | refuse an installed build other than the registered one for this command, whatever pyfs.toml, pyfs.local.toml or a build entry of inputs/executables.local.toml states |
| `--sims` | `SIM` |  | plan or run only these simulations, by their ids as the matrix spells them (for example --sims 2031 2032 2033); every other simulation is left untouched. With `run --force-rerun-all`, the simulations to redo. An id the matrix does not carry is refused before anything runs |
| `--points` | `POINT` |  | with --sims, plan or run only these points of those simulations, by the point name the plan prints for each, or by its run id alias &lt;sim>_&lt;index> (2006_3, which names its simulation; the plan prints each); the matrix file is not edited and no other point is planned, staged or run. A point the matrix does not carry is refused before anything runs |
| `--polar-sweep` |  |  | run each simulation's points as ONE solver job (one polar per job). Combines with --local; a job holds steady or unsteady polars, never both. Each row left out is named by the plan: LEGACY rows, RESTART rows, steady rows stating COLD_START false, coupled rows on steady or qsteady_rotor, unsteady rows on a build without the unsteady action command, polars whose points do not splice into one job (a steady point that initialises the solver twice among them) and rows whose points are all recorded. Run those rows point by point, without this flag. |
| `--batch` | `N` |  | run the simulations' points as N solver jobs, polars split across them. Combines with --local; a job holds steady or unsteady polars, never both. Each row left out is named by the plan: LEGACY rows, RESTART rows, steady rows stating COLD_START false, coupled rows on steady or qsteady_rotor, unsteady rows on a build without the unsteady action command, polars whose points do not splice into one job (a steady point that initialises the solver twice among them) and rows whose points are all recorded. Run those rows point by point, without this flag. |
| `--verbose` |  |  | print every warning in Python's full format (file, line and source) and the started and finished lines of the stages printed only on request, such as [continuation]; logs/activity.log holds them either way (0.31.0) |
| `--log-level` | one of `quiet`, `normal`, `verbose` |  | how much the console says: quiet (the errors, the final summary line and the signature), normal (the default) or verbose (as --verbose); logs/activity.log keeps the full detail at every level. Default: [log] console of pyfs.local.toml or pyfs.toml, else normal |

### `pyfs-matrix run`

Runs every active point of the matrix and writes the sweep table. SINCE v0.17.0 THIS NEEDS A PLAN: run `pyfs-matrix plan <matrix>` first and this command will not release without it. The plan is where the warning is, and it is pinned to the matrix it read, so a matrix edited after it was planned is planned again rather than run against a receipt about a different study. The plan spends no solver time.

```text
usage: pyfs-matrix run [-h] [--hpc NAME] [--name NAME] [--fs-version FS_VERSION] [--recipe CODE=MODULE:FUNCTION] [--ignore-missing-families [true|false]] [--no-ignore-missing-families] [--workflow CODE=NAME] [--workspace WORKSPACE] [--point-name POINT_NAME] [--fs-exe FS_EXE] [--resume] [--force-rerun POINT] [--force-rerun-all] [--progress-every N] [--sims SIM [SIM...]] [--points POINT [POINT...]] [--polar-sweep | --batch N] [--sweep-csv SWEEP_CSV] [--local | --no-local] [--accept-unregistered-build | --no-accept-unregistered-build] [--pproc-warnings | --no-pproc-warnings] [--verbose | --log-level {quiet,normal,verbose}] matrix
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--hpc` | `NAME` |  | the HPC profile inputs/hpc/&lt;NAME>.toml to use when the workspace holds several (0.35) |
| `<matrix>` |  |  | the pipe-delimited run matrix file |
| `--name` | `NAME` |  | campaign name; without it the workspace directory's name is the campaign's, and `convert`, which has no workspace, still needs it |
| `--fs-version` | `FS_VERSION` |  | the FlightStream version rows whose FS_BUILD cell is empty fall back to: canonical identifier (for example 26.120); a vendor release name works only where it names exactly one registered build. A matrix whose every active row fills FS_BUILD needs none  |
| `--recipe` | `CODE=MODULE:FUNCTION` | `[]` | FS_SCRIPT code to recipe reference (repeatable); replaces the import-by-number system |
| `--ignore-missing-families` | `true|false` |  | whether a family the opened mesh does not carry is left out (the default, true) or REFUSES the point (false). One artifact serves a wing-body and an isolated rotor because a family the geometry lacks is skipped; pass false when you believe this geometry carries every family the artifact names and want to hear about it if it does not  |
| `--no-ignore-missing-families` |  |  | the same choice as --ignore-missing-families false, written as a flag: a family the opened mesh does not carry REFUSES the point instead of being left out. Stating both is refused |
| `--workflow` | `CODE=NAME` | `[]` | FS_SCRIPT code to WORKFLOW type (repeatable); a run type this package builds itself, so no Python is written. Registered: qsteady_rotor, steady, unsteady, unsteady_rotor |
| `--workspace` | `WORKSPACE` | `.` | managed campaign root carrying the inputs/ library (default: the current directory) |
| `--point-name` | `POINT_NAME` | `{polar}` | the template that names each point's script and exports; the default is P&lt;sim>-&lt;point name>, the point name writing every variable the row's flight condition declares, in its order (0.21.0); {point}, {alpha}, {beta}, {mach}, {advance_ratio}, {sim} and {campaign} are the other placeholders  |
| `--fs-exe` | `FS_EXE` |  | explicit executable override; mandatory for MANUAL rows, otherwise the FS_BUILD column resolves through inputs/executables.toml |
| `--resume` |  |  | skip points already in the manifest, so a grown matrix runs only its new points; without it an already-recorded point refuses before anything executes |
| `--force-rerun` | `POINT` | `[]` | REDO this point, which is already in the manifest, for a row that was wrong. Name it by its point name, by the full run_id the refusal printed, or by the JOB id of a swept steady row, which is what that refusal prints for one and which names every point of it, because a job is indivisible; repeat the flag for several. The manifest is copied to archive/runs-&lt;stamp>.json, the named records leave it, and each point's collected outputs move into that point's own archive/&lt;stamp>/ before it runs; NOTHING IS DELETED. It names points rather than being a switch because redoing a whole matrix over one wrong row spends a licensed seat per point, and a seat is what archiving cannot give back. A name no recorded point carries is refused. This is NOT --resume, which SKIPS such a point instead of redoing it, and the two together are refused |
| `--force-rerun-all` |  |  | REDO every recorded point of the matrix, or of the simulations --sims names: each is archived as --force-rerun archives it and runs again, a recorded steady job as one job. The count of points and jobs, which is the licences it spends, is printed before anything runs. Refused with --resume and with --force-rerun |
| `--progress-every` | `N` | `10` | on a local unsteady point, say how far the run is every N completed time steps, read from the run's own step counter (default 10; 0 says nothing) |
| `--sims` | `SIM` |  | plan or run only these simulations, by their ids as the matrix spells them (for example --sims 2031 2032 2033); every other simulation is left untouched. With `run --force-rerun-all`, the simulations to redo. An id the matrix does not carry is refused before anything runs |
| `--points` | `POINT` |  | with --sims, plan or run only these points of those simulations, by the point name the plan prints for each, or by its run id alias &lt;sim>_&lt;index> (2006_3, which names its simulation; the plan prints each); the matrix file is not edited and no other point is planned, staged or run. A point the matrix does not carry is refused before anything runs |
| `--polar-sweep` |  |  | run each simulation's points as ONE solver job (one polar per job). Combines with --local; a job holds steady or unsteady polars, never both. Each row left out is named by the plan: LEGACY rows, RESTART rows, steady rows stating COLD_START false, coupled rows on steady or qsteady_rotor, unsteady rows on a build without the unsteady action command, polars whose points do not splice into one job (a steady point that initialises the solver twice among them) and rows whose points are all recorded. Run those rows point by point, without this flag. |
| `--batch` | `N` |  | run the simulations' points as N solver jobs, polars split across them. Combines with --local; a job holds steady or unsteady polars, never both. Each row left out is named by the plan: LEGACY rows, RESTART rows, steady rows stating COLD_START false, coupled rows on steady or qsteady_rotor, unsteady rows on a build without the unsteady action command, polars whose points do not splice into one job (a steady point that initialises the solver twice among them) and rows whose points are all recorded. Run those rows point by point, without this flag. |
| `--sweep-csv` | `SWEEP_CSV` |  | write the campaign sweep table here (default: post/&lt;matrix stem>/campaign_sweep.csv in the workspace, so each matrix of a workspace keeps its own; the run writes that one file and never a second copy of it under another name) |
| `--local` |  |  | run every point on THIS machine instead of submitting it. Linux is the cluster: a workspace carrying a submission profile submits from Linux and runs locally on Windows, with no cell to remember. This flag keeps a Linux run local, for a workstation or a smoke test on the machine itself; the executable resolves as on Windows (the FS_BUILD column through inputs/executables.toml, or --fs-exe) and every record's executor entry says forced_local. It changes nothing on a machine that would not have submitted |
| `--no-local` |  |  | the opposite of --local for this command, whatever pyfs.toml or pyfs.local.toml states |
| `--accept-unregistered-build` |  |  | run on an installed FlightStream build other than the one registered for the version a row names, instead of refusing it: its compatibility is then YOUR responsibility, the run warns, and every record says the flag was used and carries the build the solver printed. `plan` launches no solver and records the flag in plan.json, so it rehearses the same command line `run` executes |
| `--no-accept-unregistered-build` |  |  | refuse an installed build other than the registered one for this command, whatever pyfs.toml, pyfs.local.toml or a build entry of inputs/executables.local.toml states |
| `--pproc-warnings` |  |  | print grouped post-processing warnings |
| `--no-pproc-warnings` |  |  | the opposite of --pproc-warnings for this command, whatever pyfs.toml or pyfs.local.toml states |
| `--verbose` |  |  | print every warning in Python's full format (file, line and source) and one line per item where a repeated warning is otherwise counted in one line, and the [continuation] started and finished lines (0.31.0); logs/activity.log holds the full detail either way |
| `--log-level` | one of `quiet`, `normal`, `verbose` |  | how much the console says: quiet (the errors, the final summary line and the signature), normal (the default) or verbose (as --verbose); logs/activity.log keeps the full detail at every level. Default: [log] console of pyfs.local.toml or pyfs.toml, else normal |

### `pyfs-matrix collect`

Sweeps every SUBMITTED record of runs.json and, for each, waits until the outputs that point declared are PRESENT AND SETTLED, then collects them, assesses the run and rewrites the record with what it did. It watches the WORKSPACE and not the scheduler, so it needs no status command in the submission profile and serves a cluster job, a local run somebody interrupted, and outputs dropped in by hand alike. A file EXISTS BEFORE IT IS FINISHED, so settled means size and modification time stable across two observations AND every declared output present, the last of which is the log. One sweep by default; --watch loops until nothing is outstanding.

```text
usage: pyfs-matrix collect [-h] [--hpc NAME] [--workspace WORKSPACE] [--check-frozen | --no-check-frozen] [--watch] [--discard-walltime] [--interval INTERVAL] [--watch-interval WATCH_INTERVAL] [--rounds ROUNDS] [--no-post] [--sims IDS] [--pproc-warnings | --no-pproc-warnings] [--verbose | --log-level {quiet,normal,verbose}] [--runs NAME]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--hpc` | `NAME` |  | the HPC profile inputs/hpc/&lt;NAME>.toml to use when the workspace holds several (0.35) |
| `--workspace` | `WORKSPACE` | `.` | managed campaign root carrying runs.json (default: the current directory) |
| `--check-frozen` |  |  | REFUSE instead of WARN for averages touched by a frozen solve or an unread native-log block. By default computable products are written and post.log warns. Both modes write post.log and post.log.json with the point, product, step and remedy; refusals are also named in products.json |
| `--no-check-frozen` |  |  | the opposite of --check-frozen for this command, whatever pyfs.toml or pyfs.local.toml states |
| `--watch` |  |  | keep sweeping until no submitted point is outstanding, instead of once |
| `--discard-walltime` |  |  | mark each WALLTIME_REACHED point FAILED_MARKED, outputs kept. A grouped plan takes it again from the start automatically; a default-mode plan needs --force-rerun |
| `--interval` | `INTERVAL` |  | seconds between the two observations that decide settled (default: 2) |
| `--watch-interval` | `WATCH_INTERVAL` |  | seconds between sweeps under --watch (default: 60) |
| `--rounds` | `ROUNDS` |  | stop a watch after this many sweeps, whatever is still outstanding |
| `--no-post` |  |  | collect and do NOT rebuild the products, which is the half a reader wants when the products are built somewhere else |
| `--sims` | `IDS` |  | sweep only the SUBMITTED records of these simulations, comma separated as delete-sims takes them (2006,2007 or [2006,2007]); every other record is left untouched and is not counted as outstanding, and the post that follows is limited to the same simulations. An id no record carries is refused before anything is swept |
| `--pproc-warnings` |  |  | print grouped post-processing warnings |
| `--no-pproc-warnings` |  |  | the opposite of --pproc-warnings for this command, whatever pyfs.toml or pyfs.local.toml states |
| `--verbose` |  |  | print every warning in Python's full format (file, line and source) and one line per item where a repeated warning is otherwise counted in one line, and the [continuation] started and finished lines (0.31.0); logs/activity.log holds the full detail either way |
| `--log-level` | one of `quiet`, `normal`, `verbose` |  | how much the console says: quiet (the errors, the final summary line and the signature), normal (the default) or verbose (as --verbose); logs/activity.log keeps the full detail at every level. Default: [log] console of pyfs.local.toml or pyfs.toml, else normal |
| `--runs` | `NAME` |  | the manifest file to read, directly in the workspace root (default: runs.json) |

### `pyfs-matrix post`

Reads runs.json and the collected exports of every successful point and writes the polar, section and plot tables under post/&lt;matrix stem>/, exactly as `run` left them; needs no executable and spends no seat. Given a matrix, rebuilds that matrix's products; given none, every matrix the manifest names, and the records naming none under post/products. EXCEPT with --additional-pproc, which first reopens the final saved simulation of every recorded point whose row states ADDITIONAL_PPROC, one solver launch per point and no solve, extracts that pproc into datapoints/DP-&lt;point>/additional/&lt;pid>/ and records it in additional.json; runs.json is never written.

```text
usage: pyfs-matrix post [-h] [--additional-pproc] [--fs-version FS_VERSION] [--fs-exe FS_EXE] [--local | --no-local] [--recipe CODE=MODULE:FUNCTION] [--check-frozen | --no-check-frozen] [--workspace WORKSPACE] [--archive | --force-overwrite] [--yes] [--strict] [--pproc-warnings | --no-pproc-warnings] [--verbose | --log-level {quiet,normal,verbose}] [--diagnostics] [--sims IDS] [--runs NAME] [--from-sims] [--steps-per-revolution N] [matrix]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--additional-pproc` |  |  | before the products, reopen the final.fsm of every recorded point whose row states ADDITIONAL_PPROC: p&lt;id>, with no solve, and extract that pproc: its section distributions, the sections and their sectional loads, the loads, the surface exports it selects, the log, and on an unsteady point the plots history (one instant, the last). A point without the key, without its.fsm, or whose.fsm does not hash as its record says is skipped by name. Needs the matrix and the executable its rows name; one solver launch per point. 26.124 only  |
| `--fs-version` | `FS_VERSION` |  | with --additional-pproc: the version rows whose FS_BUILD cell is empty fall back to, as for `run` |
| `--fs-exe` | `FS_EXE` |  | with --additional-pproc: the explicit executable override, as for `run` |
| `--local` |  |  | with --additional-pproc: reopen the saved simulations on THIS machine, as `run --local` runs there; the submitting half of the additional post is not built, so a workspace that submits from here is refused without it |
| `--no-local` |  |  | the opposite of --local for this command, whatever pyfs.toml or pyfs.local.toml states |
| `--recipe` | `CODE=MODULE:FUNCTION` | `[]` | with --additional-pproc: a LEGACY row's recipe code (repeatable), so a matrix mixing LEGACY rows with rows naming a run type binds as it did for `run` |
| `--check-frozen` |  |  | REFUSE instead of WARN for averages touched by a frozen solve or an unread native-log block. By default computable products are written and post.log warns. Both modes write post.log and post.log.json with the point, product, step and remedy; refusals are also named in products.json |
| `--no-check-frozen` |  |  | the opposite of --check-frozen for this command, whatever pyfs.toml or pyfs.local.toml states |
| `<matrix>` |  |  | the run matrix whose products to rebuild, matched by its file stem against the records of runs.json (default: every matrix the manifest names) |
| `--workspace` | `WORKSPACE` | `.` | managed campaign root carrying runs.json and the inputs/ library (default: the current directory) |
| `--archive` |  |  | keep the files a rebuild replaces: MOVE them into post/&lt;matrix>/archive/&lt;day and hour>/ before writing, as 0.34.0 always did. Without it  a rebuild overwrites the products in place and writes no archive folder |
| `--force-overwrite` |  |  | Deprecated confirmation control. Rebuilds overwrite in place without an archive by default; use --archive to keep a copy. This option adds an explicit confirmation before rebuilding and does not change the archive policy. Pass --yes to confirm in a script. |
| `--yes` |  |  | Deprecated confirmation control for --force-overwrite. It confirms a rebuild, whose default still writes no archive; --archive keeps a copy. |
| `--strict` |  |  | exit 3 when any simulation's product was skipped by design (a polar under sideslip, for one), after every product is written in full; without it a recorded skip is named on stderr with a count, its reasons printed by --diagnostics, and the exit is 0, since everything producible was produced. 2 stays the code of a refusal that wrote nothing |
| `--pproc-warnings` |  |  | print grouped post-processing warnings |
| `--no-pproc-warnings` |  |  | the opposite of --pproc-warnings for this command, whatever pyfs.toml or pyfs.local.toml states |
| `--verbose` |  |  | print every warning in Python's full format (file, line and source) and one line per item where a repeated warning is otherwise counted in one line, and the [continuation] started and finished lines (0.31.0); logs/activity.log holds the full detail either way |
| `--log-level` | one of `quiet`, `normal`, `verbose` |  | how much the console says: quiet (the errors, the final summary line and the signature), normal (the default) or verbose (as --verbose); logs/activity.log keeps the full detail at every level. Default: [log] console of pyfs.local.toml or pyfs.toml, else normal |
| `--diagnostics` |  |  | print recorded post diagnostics as Markdown without changing products |
| `--sims` | `IDS` |  | rebuild only these simulations' products of the matrix, comma separated as delete-sims takes them (2006,2007 or [2006,2007]), in place: their files are rewritten (archived only with --archive), every other simulation's files and products.json entries stay as they were, and the super files, whose columns are the union over every simulation, are left as the last whole post wrote them and named under partial.not_rebuilt in products.json and in post.log. An id with no record of the matrix is refused before anything is written |
| `--runs` | `NAME` |  | the manifest file to read, directly in the workspace root (default: runs.json) |
| `--from-sims` |  |  | ignore runs.json and assemble the records in memory from sims/, for points run outside the package; the products go to post/&lt;matrix>@sims/ |
| `--steps-per-revolution` | `N` |  | with --from-sims: the solver steps of one revolution, for a LAST_REVS_AVG window |

### `pyfs-matrix degenerate`

Derives the thin blade of a blade mesh, the sheet midway between its two sides from the root to the tip, with the root moved outward along the span by --root-offset so it does not cross the spinner, and writes it beside the source as &lt;stem>_thin_blade.obj with its boundary inventory &lt;stem>_thin_blade.boundaries.toml. The root is the end of the blade nearer the origin of the mesh's own coordinates. The source is read only; a file holding more than one boundary needs --boundary. The derived geometry is a modelling choice: a run confirms what the solver makes of it. Needs no executable.

```text
usage: pyfs-matrix degenerate [-h] [--kind {thin-blade}] --root-offset LENGTH [--boundary NAME] [--overwrite] geometry
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<geometry>` |  |  | a blade mesh: a saved simulation or an OBJ |
| `--kind` | one of `thin-blade` | `thin-blade` | the degenerate geometry to derive; thin-blade is the one kind of 0.34.0 (default: thin-blade) |
| `--root-offset` | `LENGTH` |  | how far the root of the thin blade is moved outward along the span, a positive length in the mesh's own unit, shorter than the blade Required. |
| `--boundary` | `NAME` |  | the boundary (an OBJ's group) that is the blade, for a file that also holds a spinner, a nacelle or other bodies; only its faces are read and the output is named &lt;stem>_&lt;NAME>_thin_blade; without it a file holding more than one boundary is refused |
| `--overwrite` |  |  | rewrite a thin blade and its inventory that already exist; without it an existing one is refused |

### `pyfs-matrix status`

Reads the run records, the plans and the posts, and changes no file: no record, log or lock is written. A polar whose datapoints share one status shows that word; a mixed polar shows the count of each. A point a plan names and no record carries is shown as `planned`, in lower case because no recorded status is written so.

```text
usage: pyfs-matrix status [-h] [--additional] [--sims SIMS] [--matrix STEM] [--status WORD] [--failed] [--points] [--json | --csv] [--workspace WORKSPACE] [--runs NAME]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--additional` |  |  | list the additional register as recorded |
| `--sims` | `SIMS` |  | only these simulations, comma separated, with or without brackets: 2006,2007 or [2006,2007] |
| `--matrix` | `STEM` |  | only the polars of this matrix, by its stem (found in the workspace root or inputs/matrices/) |
| `--status` | `WORD` | `[]` | only the polars with a datapoint in this status, as recorded (repeatable; a trailing * matches every word it begins, for example FAILED_*) |
| `--failed` |  |  | only the polars with at least one failed datapoint |
| `--points` |  |  | one row per datapoint instead of one per polar |
| `--json` |  |  | print the rows as one JSON document on stdout |
| `--csv` |  |  | print the rows as CSV on stdout, LF line ends |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--runs` | `NAME` |  | another manifest in the workspace root, read in place of runs.json |

### `pyfs-matrix show`

```text
usage: pyfs-matrix show [-h] [--point POINT] [--workspace WORKSPACE] [--runs RUNS] [--json | --csv] target
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<target>` |  |  | run id, alias, or simulation id |
| `--point` | `POINT` |  | point name or 1-based alias index within the simulation |
| `--workspace` | `WORKSPACE` | `.` | workspace root (default: current directory) |
| `--runs` | `RUNS` |  | another run manifest in the workspace root |
| `--json` |  |  | print a JSON document of the rows |
| `--csv` |  |  | print CSV; nested cells are JSON |

### `pyfs-matrix log`

```text
usage: pyfs-matrix log [-h] [--post MATRIX | --storage] [--sims SIMS] [--run RUN] [--stage STAGE] [--since SINCE] [--problems] [--open] [--workspace WORKSPACE] [--runs RUNS] [--json | --csv]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--post` | `MATRIX` |  | group a matrix's saved post warnings |
| `--storage` |  |  | list the recorded storage calls |
| `--sims` | `SIMS` |  | only these simulation ids, comma or blank separated |
| `--run` | `RUN` |  | only events naming this run id or alias |
| `--stage` | `STAGE` |  | only this recorded stage (storage: command) |
| `--since` | `SINCE` |  | events since an ISO time or duration, e.g. 2h, 7d |
| `--problems` |  |  | only problems and failed outcomes |
| `--open` |  |  | stages started without a finish in the records; never asks a scheduler |
| `--workspace` | `WORKSPACE` | `.` | workspace root (default: current directory) |
| `--runs` | `RUNS` |  | another run manifest in the workspace root |
| `--json` |  |  | print a JSON document of the rows |
| `--csv` |  |  | print CSV; nested cells are JSON |

### `pyfs-matrix trace`

```text
usage: pyfs-matrix trace [-h] [--run RUN] [--workspace WORKSPACE] [--runs RUNS] [--json | --csv] [product]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<product>` |  |  | product path relative to the workspace or absolute |
| `--run` | `RUN` |  | print the provenance tree of this run id or alias |
| `--workspace` | `WORKSPACE` | `.` | workspace root (default: current directory) |
| `--runs` | `RUNS` |  | another run manifest in the workspace root |
| `--json` |  |  | print a JSON document of the rows |
| `--csv` |  |  | print CSV; nested cells are JSON |

### `pyfs-matrix history`

Read present and archived records with continuation links and archive stamps. No log, lock, record or extracted file is written.

```text
usage: pyfs-matrix history [-h] [--workspace WORKSPACE] [--runs NAME] [--json | --csv] target
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<target>` |  |  | simulation id, point name or run id |
| `--workspace` | `WORKSPACE` | `.` | workspace root (default: current directory) |
| `--runs` | `NAME` |  | another root manifest and its archives |
| `--json` |  |  | print one JSON document on stdout |
| `--csv` |  |  | print the same rows as CSV, with LF line ends |

### `pyfs-matrix diff`

Compare versions, digests, solver flags, flight condition and outcome. Use run_id@&lt;archive stamp> for an archived copy. Script changes name line numbers and candidate inputs using rebuild's comparison.

```text
usage: pyfs-matrix diff [-h] [--workspace WORKSPACE] [--runs NAME] [--json | --csv] run_a run_b
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<run_a>` |  |  | first run id, optionally @&lt;archive stamp> |
| `<run_b>` |  |  | second run id, optionally @&lt;archive stamp> |
| `--workspace` | `WORKSPACE` | `.` | workspace root (default: current directory) |
| `--runs` | `NAME` |  | another root manifest and its archives |
| `--json` |  |  | print one JSON document on stdout |
| `--csv` |  |  | print the same rows as CSV, with LF line ends |

### `pyfs-matrix mark-converged`

You know from your own reading that points converged where the package could not say so. Their records become CONVERGED, each keeping under 'marked' the status it had, when, your reason and the verdict; runs.json is copied to archive/ first. A point SUBMITTED, without its loads export, deleted, or marked failed is refused by name and nothing is written.

```text
usage: pyfs-matrix mark-converged [-h] --sims ID [ID...] [--points NAME [NAME...]] --reason REASON [--workspace WORKSPACE] [--apply]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--sims` | `ID` |  | simulation ids, comma separated: 2006,2007 or [2006,2007]; one quoted value of words, '2006 2007', reads as two ids; also as separate words (2006 2007) or a mix (2006 2007,2008); to mark some of their points, name them with --points (a run id alias such as 2006_3 is refused, naming the --sims and --points that select its point) Required. |
| `--points` | `NAME` |  | the point names to mark; every point of the simulations without it |
| `--reason` | `REASON` |  | why, recorded as given Required. |
| `--workspace` | `WORKSPACE` | `.` | the workspace root carrying runs.json (default: the current directory) |
| `--apply` |  |  | change files; without it the command previews and changes nothing |

### `pyfs-matrix refine`

Refines or coarsens a panel mesh from its OBJ into a new geometry folder &lt;out>/&lt;stem>_&lt;tag>/ holding the OBJ, the trailing-edge points file, the boundaries file, &lt;stem>_&lt;tag>.refine.json and the audit against the source. FACTOR multiplies the intervals of each index direction of a grid family and divides the target edge length of a remeshed family; --chordwise and --spanwise replace it in one direction of the grid families. Without FACTOR, --chordwise or --spanwise, the factors come from the refinement file (--config, or &lt;stem>.refine.toml beside the mesh), whose [components], [periodic], [refine] tag and elements (triangles or quad-dominant) are read whenever it exists. --keep-first-row names grid families with a trailing edge whose row of panels at each end meeting another component keeps its spanwise width and is refined chordwise only. Faces are written in the source's order. The source and its folder are never modified. Remeshing a family needs the geom extra. Needs no executable. Exits 0 when the level is written, even when its audit fails: each failed gate or check is a warning and the audit is written beside the level, while audit-mesh exits 1 on the same audit. Exits 2 when the request is refused, and then writes nothing.

```text
usage: pyfs-matrix refine [-h] [--families FAMILIES] [--chordwise CHORDWISE] [--spanwise SPANWISE] [--config FILE] [--keep-first-row FAMILY[,FAMILY...]] [--out DIR] [--out-dir DIR] [--overwrite] MESH [FACTOR]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<MESH>` |  |  | the source OBJ |
| `<FACTOR>` |  |  | the factor of every selected family |
| `--families` | `FAMILIES` |  | the families to change, comma separated (default: all) |
| `--chordwise` | `CHORDWISE` |  | the chordwise factor of the grid families |
| `--spanwise` | `SPANWISE` |  | the spanwise factor of the grid families |
| `--config` | `FILE` |  | the refinement file (default: &lt;stem>.refine.toml) |
| `--keep-first-row` | `FAMILY[,FAMILY...]` |  | grid families with a trailing edge that keep the spanwise width of their row of panels at another component, comma separated |
| `--out` | `DIR` |  | where the level folder goes (Python: out_dir; default: the parent of the source's folder) |
| `--out-dir` | `DIR` |  | deprecated alias of --out, with the identical result |
| `--overwrite` |  |  | replace an existing level folder |

### `pyfs-matrix audit-mesh`

Audits an OBJ and writes &lt;stem>.audit.json beside it. The gates G1 to G6 judge the topology, the orientation, the open boundary, the trailing edge and the nodes families share; the relative checks compare the 95th percentiles of the skewness, the warp and the size growth with the source's; the other figures are reported and never judged. Without --against only G1, G2 and G4 are judged. The trailing-edge points file is the one &lt;stem>.boundaries.toml names, or else &lt;stem>.te.txt. A gate or check that fails is a warning, and the audit is still written. Exits 0 when every gate and check passes, 1 when one fails, 2 when the input is refused or when the --out CSV cannot be written after the audit was (the error names the audit written). Needs no executable.

```text
usage: pyfs-matrix audit-mesh [-h] [--against SOURCE] [--out FILE] [--csv FILE] OBJ
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<OBJ>` |  |  | the OBJ to audit |
| `--against` | `SOURCE` |  | the OBJ the mesh was refined or coarsened from; the gates and checks that compare with a source are judged against it |
| `--out` | `FILE` |  | write the figures as CSV, one row per family and figure; the audit JSON is always written beside the OBJ |
| `--csv` | `FILE` |  | deprecated alias of --out, with the identical result |
