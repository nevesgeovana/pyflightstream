# pyfs-workspace

Generated from the argument parser at build time, so this page and `pyfs-workspace --help` cannot disagree. The entry point is `pyflightstream.workspace.cli:main`.

## `pyfs-workspace`

Managed campaign workspace tooling; the tree it creates is owned by pyflightstream and never hand-built.

```text
usage: pyfs-workspace [-h] {init,archive,migrate-geometries,field,profile,geometry}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `pyfs-workspace init`: create the full campaign tree (inputs library, sims, post, archive)
- `pyfs-workspace archive`: zip one recorded simulation under archive/ and remove its folder
- `pyfs-workspace migrate-geometries`: move a flat inputs/geometries library into one folder per geometry
- `pyfs-workspace field`: build a custom free-stream file of inputs/freestreams/ from other fields
- `pyfs-workspace profile`: build an actuator-disc radial thrust profile of inputs/profiles/
- `pyfs-workspace geometry`: build a geometry from its instruction file, and inspect or refine a mesh

### `pyfs-workspace init`

```text
usage: pyfs-workspace init [-h] [--workspace WORKSPACE] [root]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<root>` |  | `.` | campaign root to create or complete (default: the current directory) |
| `--workspace` | `WORKSPACE` |  | campaign workspace (default: the current directory); the positional root names the same folder |

### `pyfs-workspace archive`

Zips sims/sim_&lt;sim_id>/ of a recorded simulation into archive/ and removes the folder, so the simulation can be re-run into a clean folder while its evidence stays. Refuses a simulation the manifest (runs.json) does not record, and an archive name already taken: file management never destroys an unrecorded run or an earlier archive. It does not read the status of the simulation's runs, so a failed or stale run is archived like a finished one; do not archive a simulation whose run is still going.

```text
usage: pyfs-workspace archive [-h] [--workspace WORKSPACE] [root] sim_id
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<root>` |  |  | deprecated positional alias of --workspace; still accepted with a warning |
| `<sim_id>` |  |  | the simulation to archive, as the manifest records it (the folder is sims/sim_&lt;sim_id>/) |
| `--workspace` | `WORKSPACE` |  | campaign workspace (default: the current directory); the positional root names the same folder |

### `pyfs-workspace migrate-geometries`

Moves every inputs/geometries/&lt;stem>.&lt;ext> into inputs/geometries/&lt;stem>/ with its &lt;stem>.boundaries.toml and &lt;stem>.provenance.toml, so what belongs to one geometry sits in one place and a point stages that geometry's files only. A folder that already exists is left alone, a second run moves nothing, and the GEOMETRY cells of a matrix do not change: the package reads both layouts, the folder first. Refuses a root with no inputs/geometries.

```text
usage: pyfs-workspace migrate-geometries [-h] [--workspace WORKSPACE] [root]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<root>` |  | `.` | campaign root carrying inputs/geometries/ (default: the current directory) |
| `--workspace` | `WORKSPACE` |  | campaign workspace (default: the current directory); the positional root names the same folder |

### `pyfs-workspace field`

Builds a custom free-stream field (the file a row's FREESTREAM names) from other fields: mirror, move, subtract, time-mean. Metres and m/s in the global frame, nothing converted. Previews by default; --apply writes inputs/freestreams/&lt;stem>.txt or.dat and &lt;stem>.provenance.json (operation, parameters, inputs with sha256), and an existing file is replaced only with --overwrite.

```text
usage: pyfs-workspace field [-h] {mirror,move,subtract,time-mean,fill-interior}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `pyfs-workspace field mirror`: mirror a field through the plane x = 0, y = 0 or z = 0
- `pyfs-workspace field move`: translate a field so a source point lands on a target point
- `pyfs-workspace field subtract`: total - (other - reference), point by point on one grid
- `pyfs-workspace field time-mean`: the time mean of an unsteady run's per-step fields
- `pyfs-workspace field fill-interior`: fill the probes inside the body from the ray outside it

#### `pyfs-workspace field mirror`

Mirrors a field through a coordinate plane: through y = 0 each row x y z vx vy vz becomes x -y z vx -vy vz. The row order and a STRUCTURED header are kept.

```text
usage: pyfs-workspace field mirror [-h] --plane {x,y,z} --out STEM [--workspace WORKSPACE] [--apply] [--overwrite] field
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<field>` |  |  | the field file (.txt STRUCTURED or.dat UNSTRUCTURED) |
| `--plane` | one of `x`, `y`, `z` |  | the coordinate whose sign changes: y mirrors through the plane y = 0 Required. |
| `--out` | `STEM` |  | the stem of the file written in inputs/freestreams/ (no extension: the form gives it,.txt STRUCTURED,.dat UNSTRUCTURED) Required. |
| `--workspace` | `WORKSPACE` | `.` | campaign workspace whose inputs/freestreams/ receives the field (default: the current directory) |
| `--apply` |  |  | write the files (default: preview) |
| `--overwrite` |  |  | replace an existing &lt;stem> file and its provenance record |

#### `pyfs-workspace field move`

Translates every position by (target - source), so the source point (a hub) lands on the target point; the velocities are unchanged.

```text
usage: pyfs-workspace field move [-h] --source-point X Y Z --target-point X Y Z --out STEM [--workspace WORKSPACE] [--apply] [--overwrite] field
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<field>` |  |  | the field file (.txt STRUCTURED or.dat UNSTRUCTURED) |
| `--source-point` | `SOURCE_POINT` |  | the source point (a hub) in m, global frame Required. |
| `--target-point` | `TARGET_POINT` |  | the point the source point lands on in m, global frame Required. |
| `--out` | `STEM` |  | the stem of the file written in inputs/freestreams/ (no extension: the form gives it,.txt STRUCTURED,.dat UNSTRUCTURED) Required. |
| `--workspace` | `WORKSPACE` | `.` | campaign workspace whose inputs/freestreams/ receives the field (default: the current directory) |
| `--apply` |  |  | write the files (default: preview) |
| `--overwrite` |  |  | replace an existing &lt;stem> file and its provenance record |

#### `pyfs-workspace field subtract`

Subtracts OTHER from TOTAL point by point, matched by position: the result is total - (other - reference), with --reference the uniform free stream OTHER was solved in, so only the velocity OTHER's body induces is removed. --reference is required: state 0 0 0 only where OTHER is already induced-only (its free stream taken out), and the result is then total - other. Two grids that are not one point set are refused.

```text
usage: pyfs-workspace field subtract [-h] --reference VX VY VZ [--tolerance M] --out STEM [--workspace WORKSPACE] [--apply] [--overwrite] total other
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<total>` |  |  | the field subtracted from (its positions are kept) |
| `<other>` |  |  | the field subtracted, on the same grid |
| `--reference` | `REFERENCE` |  | the free stream OTHER was solved in, m/s, global frame (required; 0 0 0 only where OTHER is already induced-only) Required. |
| `--tolerance` | `M` | `1e-06` | two positions closer than this, in m along each axis, are one point (default: 1e-06) |
| `--out` | `STEM` |  | the stem of the file written in inputs/freestreams/ (no extension: the form gives it,.txt STRUCTURED,.dat UNSTRUCTURED) Required. |
| `--workspace` | `WORKSPACE` | `.` | campaign workspace whose inputs/freestreams/ receives the field (default: the current directory) |
| `--apply` |  |  | write the files (default: preview) |
| `--overwrite` |  |  | replace an existing &lt;stem> file and its provenance record |

#### `pyfs-workspace field time-mean`

Averages the per-step fields of an unsteady run (&lt;point>_field_NN_step_&lt;N>.inflow.dat, written by the post from a [[probes]] entry with reusable_inflow) into one field. The steps must be equally spaced and hold the same points.

```text
usage: pyfs-workspace field time-mean [-h] [--last K] [--fluctuation] [--fluctuation-only] [--vinf M_S] [--tolerance M] --out STEM [--workspace WORKSPACE] [--apply] [--overwrite] files [files...]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<files>` |  |  | the per-step field files, or glob patterns |
| `--last` | `K` |  | average only the last K steps given (default: every step given) |
| `--fluctuation` |  |  | also write &lt;stem>.fluctuation.csv: the per-probe population standard deviation of the averaged steps (needs at least two steps) |
| `--fluctuation-only` |  |  | report the fluctuation only, with no field (needs --last) |
| `--vinf` | `M_S` |  | the free-stream speed, in m/s, the fluctuation summary is also stated against |
| `--tolerance` | `M` | `1e-06` | two positions closer than this, in m along each axis, are one point (default: 1e-06) |
| `--out` | `STEM` |  | the stem of the file written in inputs/freestreams/ (no extension: the form gives it,.txt STRUCTURED,.dat UNSTRUCTURED) Required. |
| `--workspace` | `WORKSPACE` | `.` | campaign workspace whose inputs/freestreams/ receives the field (default: the current directory) |
| `--apply` |  |  | write the files (default: preview) |
| `--overwrite` |  |  | replace an existing &lt;stem> file and its provenance record |

#### `pyfs-workspace field fill-interior`

Every probe with r &lt; --r-body about the x axis takes the velocity of the probe at r >= --r-body with the smallest radius on the same azimuth ray (within 1e-3 rad). A probe with no such partner is refused.

```text
usage: pyfs-workspace field fill-interior [-h] [--r-body M] --out STEM [--workspace WORKSPACE] [--apply] [--overwrite] field
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<field>` |  |  | the field file (.txt STRUCTURED or.dat UNSTRUCTURED) |
| `--r-body` | `M` | `0.38` | the body radius about the x axis, in m (default: 0.38) |
| `--out` | `STEM` |  | the stem of the file written in inputs/freestreams/ (no extension: the form gives it,.txt STRUCTURED,.dat UNSTRUCTURED) Required. |
| `--workspace` | `WORKSPACE` | `.` | campaign workspace whose inputs/freestreams/ receives the field (default: the current directory) |
| `--apply` |  |  | write the files (default: preview) |
| `--overwrite` |  |  | replace an existing &lt;stem> file and its provenance record |

### `pyfs-workspace profile`

Builds the radial thrust profile a row's PROFILE names (the CUSTOM disc): rows r,F with r in m and F in N/m per blade, no header and no final newline, scaled so that B * integral(F dr) is the target thrust (--thrust in N, or --ct with --rho and --rpm, CT = T / (rho n^2 D^4)). The shape is 'sections' (a POL's written sections: the sectional loads table, or --pol; -Fx at the stations, a zero from the axis to the hub and a zero at the tip; --last K averages a table of several steps), 'uni' (F = c r) or 'bp' (Betz-Prandtl, --advance-ratio J). The disc is a reference's block (--ref, --disc) or stated (--tip-radius, --hub-radius, --blades). The ELLIPTICAL disc is native in the solver and needs no file: its row states ACTUATOR_THRUST. A RELAXED disc ignores a custom profile. Previews by default; --apply writes inputs/profiles/&lt;stem>.csv and &lt;stem>.provenance.json, and an existing file is replaced only with --overwrite.

```text
usage: pyfs-workspace profile [-h] [--pol POL] [--family FAMILY] [--component {Fx,Fz}] [--sign {-1,1}] [--last K] [--advance-ratio J] [--stations N] [--ref RID] [--disc NAME] [--tip-radius M] [--hub-radius M] [--blades B] [--thrust N] [--ct CT] [--rho KG_M3] [--rpm RPM] --out STEM [--workspace WORKSPACE] [--apply] [--overwrite] {sections,uni,bp} [table]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<shape>` | one of `sections`, `uni`, `bp` |  | the shape of the profile |
| `<table>` |  |  | sections: the sectional loads table (or --pol to find it) |
| `--pol` | `POL` |  | sections: the POL whose table the post recorded |
| `--family` | `FAMILY` |  | sections: the family of --pol (default: Blade1) |
| `--component` | one of `Fx`, `Fz` |  | sections: the force read (default: Fx) |
| `--sign` | one of `-1`, `1` |  | sections: its sign (default: -1, so -Fx) |
| `--last` | `K` |  | sections: average the last K steps of a table |
| `--advance-ratio` | `J` |  | bp: J = V / (n D), required |
| `--stations` | `N` |  | uni, bp: radii from the hub to the tip (default: 61) |
| `--ref` | `RID` |  | the reference id that declares the disc |
| `--disc` | `NAME` |  | the disc's block name in --ref |
| `--tip-radius` | `M` |  | the tip radius, in m |
| `--hub-radius` | `M` |  | the hub radius, in m |
| `--blades` | `B` |  | the blade count |
| `--thrust` | `N` |  | the target thrust, in N |
| `--ct` | `CT` |  | the target CT = T / (rho n^2 D^4) |
| `--rho` | `KG_M3` |  | the density of --ct |
| `--rpm` | `RPM` |  | the speed of --ct, in rev/min |
| `--out` | `STEM` |  | the stem of the file written in inputs/profiles/ (the row's PROFILE) Required. |
| `--workspace` | `WORKSPACE` | `.` | campaign workspace whose inputs/profiles/ receives the profile (default: the current directory) |
| `--apply` |  |  | write the files (default: preview) |
| `--overwrite` |  |  | replace an existing &lt;stem> file and its provenance record |

### `pyfs-workspace geometry`

Builds a body outside the run matrix from &lt;name>.geometry.toml, previewing by default and running the solver once with --apply; accepts a built body after inspection; writes the instruction of a geometry a matrix builds in the row; and refines, audits, inventories and derives meshes (docs/geometry.md).

```text
usage: pyfs-workspace geometry [-h] {build,accept,from-sidecar,refine,audit,inventory,degenerate}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `pyfs-workspace geometry build`: preview a geometry's build, or run it with --apply
- `pyfs-workspace geometry accept`: record that a built geometry was inspected
- `pyfs-workspace geometry from-sidecar`: write the instruction of a geometry a matrix builds in the row
- `pyfs-workspace geometry refine`: as pyfs-matrix refine, whose home this group is
- `pyfs-workspace geometry audit`: as pyfs-matrix audit-mesh, whose home this group is
- `pyfs-workspace geometry inventory`: as pyfs-matrix inventory, whose home this group is
- `pyfs-workspace geometry degenerate`: as pyfs-matrix degenerate, whose home this group is

#### `pyfs-workspace geometry build`

Reads &lt;name>.geometry.toml (the one of the current folder, or of the folder or file TARGET names) and prints the script, the boundaries after each step and what would be written. With --apply it runs the solver once with no solve, saves the body, reads it back, audits it, and writes the preview and the record. Exit 0 built, 1 built with a failed audit gate, 2 refused, 3 the solver or the read-back failed.

```text
usage: pyfs-workspace geometry build [-h] [--apply] [--build ID] [--fs-exe PATH] [--png] [--overwrite] [--only TAG[,TAG...]] [--parallel N] [--rows POL] [--matrix FILE] [TARGET]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<TARGET>` |  |  | an instruction file or a geometry folder |
| `--apply` |  |  | run the solver and write the geometry |
| `--build` | `ID` |  | the build id, over the instruction's fs_build |
| `--fs-exe` | `PATH` |  | the executable, over the registry |
| `--png` |  |  | also draw &lt;name>.preview.png (the plot extra) |
| `--overwrite` |  |  | replace the outputs of an earlier build |
| `--only` | `TAG[,TAG...]` |  | build only these variants of a [sweep], such as AIL+100 |
| `--parallel` | `N` | `1` | run up to N variants of a [sweep] at once, 1 or 2 (default: 1); a variant that fails beside another is run again alone |
| `--rows` | `POL` |  | print, per built geometry, the row POL of --matrix with its CONFIGURATION, GEOMETRY and POL cells set for it; nothing is written into the matrix |
| `--matrix` | `FILE` |  | the run matrix --rows copies from |

#### `pyfs-workspace geometry accept`

Writes who and when into each named geometry's &lt;name>.build.json.

```text
usage: pyfs-workspace geometry accept [-h] [--workspace WORKSPACE] NAME[,NAME...]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<NAME[,NAME...]>` |  |  | geometry folders of inputs/geometries |
| `--workspace` | `WORKSPACE` | `.` | the workspace root (default: the current directory) |

#### `pyfs-workspace geometry from-sidecar`

Reads the sidecar of a CCS, IGES or raw-mesh geometry of inputs/geometries and prints the instruction file that builds the same body; --apply writes it. The sidecar and the matrices are never edited.

```text
usage: pyfs-workspace geometry from-sidecar [-h] [--apply] [--build ID] [--workspace WORKSPACE] GEOMETRY
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<GEOMETRY>` |  |  | the file a GEOMETRY cell names |
| `--apply` |  |  | write &lt;stem>.geometry.toml |
| `--build` | `ID` |  | the build id; else the rows' newest |
| `--workspace` | `WORKSPACE` | `.` | the workspace root (default: the current directory) |

#### `pyfs-workspace geometry refine`

Refines or coarsens a panel mesh from its OBJ into a new geometry folder &lt;out>/&lt;stem>_&lt;tag>/ holding the OBJ, the trailing-edge points file, the boundaries file, &lt;stem>_&lt;tag>.refine.json and the audit against the source. FACTOR multiplies the intervals of each index direction of a grid family and divides the target edge length of a remeshed family; --chordwise and --spanwise replace it in one direction of the grid families. Without FACTOR, --chordwise or --spanwise, the factors come from the refinement file (--config, or &lt;stem>.refine.toml beside the mesh), whose [components], [periodic], [refine] tag and elements (triangles or quad-dominant) are read whenever it exists. --keep-first-row names grid families with a trailing edge whose row of panels at each end meeting another component keeps its spanwise width and is refined chordwise only. Faces are written in the source's order. The source and its folder are never modified. Remeshing a family needs the geom extra. Needs no executable. Exits 0 when the level is written, even when its audit fails: each failed gate or check is a warning and the audit is written beside the level, while audit-mesh exits 1 on the same audit. Exits 2 when the request is refused, and then writes nothing.

```text
usage: pyfs-workspace geometry refine [-h] [--families FAMILIES] [--chordwise CHORDWISE] [--spanwise SPANWISE] [--config FILE] [--keep-first-row FAMILY[,FAMILY...]] [--out DIR] [--out-dir DIR] [--overwrite] MESH [FACTOR]
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

#### `pyfs-workspace geometry audit`

Audits an OBJ and writes &lt;stem>.audit.json beside it. The gates G1 to G6 judge the topology, the orientation, the open boundary, the trailing edge and the nodes families share; the relative checks compare the 95th percentiles of the skewness, the warp and the size growth with the source's; the other figures are reported and never judged. Without --against only G1, G2 and G4 are judged. The trailing-edge points file is the one &lt;stem>.boundaries.toml names, or else &lt;stem>.te.txt. A gate or check that fails is a warning, and the audit is still written. Exits 0 when every gate and check passes, 1 when one fails, 2 when the input is refused or when the --out CSV cannot be written after the audit was (the error names the audit written). Needs no executable.

```text
usage: pyfs-workspace geometry audit [-h] [--against SOURCE] [--out FILE] [--csv FILE] OBJ
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<OBJ>` |  |  | the OBJ to audit |
| `--against` | `SOURCE` |  | the OBJ the mesh was refined or coarsened from; the gates and checks that compare with a source are judged against it |
| `--out` | `FILE` |  | write the figures as CSV, one row per family and figure; the audit JSON is always written beside the OBJ |
| `--csv` | `FILE` |  | deprecated alias of --out, with the identical result |

#### `pyfs-workspace geometry inventory`

Reads the mesh block of a saved simulation and writes its boundary order as a sidecar beside it; a run whose sidecar disagrees with the file is refused before the solver starts. Needs no executable. For an OBJ the order is its groups that hold a face, in the order of the file, which is what a plan writes when the OBJ has no sidecar; an OBJ's existing sidecar is never rewritten.

```text
usage: pyfs-workspace geometry inventory [-h] [--overwrite] [--clean] geometry
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<geometry>` |  |  | a saved simulation or an OBJ under inputs/geometries/ |
| `--overwrite` |  |  | rewrite a saved simulation's sidecar that already exists; without it an existing one is refused |
| `--clean` |  |  | remove the unsteady solver actions saved in the simulation, which inventory otherwise names as a warning, keeping a copy &lt;file>.bak-&lt;stamp> beside it; an existing sidecar is then kept unless --overwrite  |

#### `pyfs-workspace geometry degenerate`

Derives the thin blade of a blade mesh, the sheet midway between its two sides from the root to the tip, with the root moved outward along the span by --root-offset so it does not cross the spinner, and writes it beside the source as &lt;stem>_thin_blade.obj with its boundary inventory &lt;stem>_thin_blade.boundaries.toml. The root is the end of the blade nearer the origin of the mesh's own coordinates. The source is read only; a file holding more than one boundary needs --boundary. The derived geometry is a modelling choice: a run confirms what the solver makes of it. Needs no executable.

```text
usage: pyfs-workspace geometry degenerate [-h] [--kind {thin-blade}] --root-offset LENGTH [--boundary NAME] [--overwrite] geometry
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<geometry>` |  |  | a blade mesh: a saved simulation or an OBJ |
| `--kind` | one of `thin-blade` | `thin-blade` | the degenerate geometry to derive; thin-blade is the one kind of 0.34.0 (default: thin-blade) |
| `--root-offset` | `LENGTH` |  | how far the root of the thin blade is moved outward along the span, a positive length in the mesh's own unit, shorter than the blade Required. |
| `--boundary` | `NAME` |  | the boundary (an OBJ's group) that is the blade, for a file that also holds a spinner, a nacelle or other bodies; only its faces are read and the output is named &lt;stem>_&lt;NAME>_thin_blade; without it a file holding more than one boundary is refused |
| `--overwrite` |  |  | rewrite a thin blade and its inventory that already exist; without it an existing one is refused |
