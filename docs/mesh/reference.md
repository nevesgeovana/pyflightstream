# Mesh input reference

The inventory command writes `<mesh>.obj.boundaries.toml` or
`<mesh>.fsm.boundaries.toml`, according to its input. An existing OBJ inventory
is never rewritten, including with `--overwrite`. The marking declaration
locator accepts `<mesh>.boundaries.toml` when the `.obj.` filename is absent.

## Named boundary declarations

The marking loader reads an ordered table per trailing-edge entry and per base
family. The family must occur in `boundaries`; trailing-edge labels are free.

```toml
fs_build = "26.125"
boundaries = ["wing", "rim"]

[trailing_edges.tip]
file = "tip.te.txt"
type = "RELAXED"
wake_termination_nodes = "auto"

[base_regions.rim]
trailing_edges = "auto"
merge_into = "wing"
```

A trailing-edge entry requires `type`: `STANDARD`, `RELAXED`, `JET_OUTFLOW` or
`VORTEX_SHEDDING`. Replace `file` with `detect = "auto"` or
`detect = { surfaces = ["wing"], sweep_angle = 30.0 }` for detection, which
accepts only `STANDARD`. File matching defaults to `tolerance = 0.0001` metres.
Termination nodes may name a points file instead of `"auto"`.

Base regions default to `model = "EMPIRICAL"` and `cp = -0.2`. Their rim is
`"auto"` or `{ file = "rim.te.txt", type = "STANDARD" }`. A merge destination
must be another existing family and cannot itself be merged.

Migration: each old unnamed trailing-edge file becomes a named entry (use its
file stem as the label). Move `[wake_termination]` to `wake_termination_nodes`
on the entry it serves, or the first entry if it served all. Replace base-region
autodetection with one named base table per family. The marking loader refuses
these old table forms with their translation. Matrix planning refuses all
marking declaration tables; only mark-boundaries consumes them.
`[trailing_edges] none = true` remains supported for a mesh with no trailing
edge, alone without named entries. State `fs_build` when declaring boundaries.

### The surface names

Inventory reads OBJ groups holding faces in file order. The marking pass
uses those names and publishes the saved FSM inventory after renames and
base merges. Matrix rows refer to those saved names. Existing OBJ sidecars
are never overwritten by inventory.

### The unit

The OBJ sidecar states its source units; no unit is assumed:

```toml
fs_build = "26.124"
boundaries = ["Wing"]
[import]
units = "METER"
[trailing_edges.wing]
file = "wing.te.txt"
type = "STANDARD"
tolerance = 0.0001
```

The file matching tolerance is in metres. Points files declare their own
length unit. The saved simulation carries its coordinate scale into the run.

### Explicit CAD conversion is a separate route

CAD and CCS inputs belong to [geometry build](../geometry.md). The matrix
opens the resulting FSM. Geometry build retains its own solver pass and its
instruction format; the named OBJ declarations here belong to mark-boundaries.

### A CCS file is another route

Use the [CCS geometry](../ccs-geometry.md) build stage, then run its saved FSM.

### The mesh operations of an import

Import operations belong to preparation. Move geometry construction to a
geometry instruction. Row `TRANSLATE` and `ROTATE` still act on the saved body
after the run's frames have been defined.

### The boundary conditions of a raw mesh

Use the named declarations above with `geometry mark-boundaries`. Each
trailing-edge entry has its own label and type. The marking pass checks the
saved result before publishing it; runs perform no per-point wake-edge
import-count verdict. An intentional absence of trailing edges is written:

```toml
fs_build = "26.124"
[trailing_edges]
none = true
```

Explicit termination points are named by `wake_termination_nodes = "tips.wt.txt"`
inside the trailing-edge entry. Use `"auto"` only where the build's recorded
evidence permits the automatic command. Preview does not establish support.

### The points file

The wake-edge import matches a mesh edge by its MID-POINT: an edge is marked
when a point in the file lies within the import's tolerance of the edge's
mid-point, and a point farther than that from every mid-point marks nothing
and reports nothing. So a points file names edges by their mid-points, never
by their end vertices. Its first line names the length unit of its points (a
token of `SET_SIMULATION_LENGTH_UNITS`, `OTHER` excepted), and every later
line is one `x,y,z` mid-point:

```text
METER
0.216872113,-0.002159825,0.223199974
0.250942335,-0.004761036,0.219139256
```

The points file is the package's, not the solver's: its unit is stated once,
on the first line, since a mesh file does not carry one, and the run converts
its points to the simulation's length unit and writes the file the solver
imports.

**It is checked before any seat is spent.** When the row is bound, the file is
read and every point is checked against the mesh (`read_trailing_edge_points`
and `matched_trailing_edge_points`, in `pyflightstream.workspace.wake_edges`),
compared in the simulation's length unit. The first point farther than
`tolerance` from every mesh-edge mid-point is refused by its position, its
file line, its coordinates and its distance, and two points nearest one edge
are refused as well, since the solver would mark that edge once. A file of the
edges' end vertices fails this check at its first point. The checked points
come back in metres.

The marking pass writes any solver node files in its work folder and checks
the saved result before publication. Matrix runs open that result and do not
write marking files or apply per-run trailing-edge count verdicts.

### Which build runs what, and what is measured

Marking checks the command evidence on the sidecar's declared `fs_build`
before applying. Unverified commands are refused by name. The saved-state
checks cover surfaces, trailing edges, termination counts and base regions;
see [marking and publication](../geometry.md#mark-boundaries-once-into-a-saved-simulation).
The matrix does not repeat marking or certify a GUI-authored FSM.

### What that content hash is, and what it leaves out

Stated here because this page is where a user is told to trust it, and a
checksum whose rule is unstated cannot settle the question it exists for: two
people holding what they believe is the same input file must be able to tell
whether they really do.

**The algorithm is sha256, and there is no other.** Every digest this library
writes into a manifest comes from `pyflightstream._digest`, which holds the
algorithm as a value rather than as a sentence, so a tier 1 test spends it and
a second algorithm cannot arrive quietly.

**The canonical form is the raw bytes of the staged file**, read in blocks and
never decoded. One manifest field is not a file digest and is named here so
the rule is not over-read: `recipe_sha256` records the recipe function's
SOURCE, and a source text is hashed as its UTF-8 encoding, which is the second
canonical form `pyflightstream._digest` states.

**Nothing around the file enters the digest.** Not the path it was staged
from, not the file name, not its modification time, not the machine or the
user that staged it, and not the order the inputs were staged in. Those are
exactly the fields that differ between two runs which are otherwise the same
run, so admitting one would make the manifest report two identical runs as
different. They are absent by construction rather than by filtering: the
digest reads bytes and reads nothing else.

**Metadata embedded in those bytes is included.** A timestamp, path or user
name saved inside a mesh or other input changes the digest when it changes.
Hashing does not parse, filter or normalize that content. The exclusions
above concern external filesystem and process metadata only.

Read the consequence for a text mesh, because it is the one that surprises. An
OBJ is bytes like anything else, so the same mesh checked out with CRLF line
endings on one machine and LF on another is two different files carrying two
different digests. That is the digest being correct about the file rather than
wrong about the content: the solver reads the file, not an idea of it. A
`.fsm` artifact is binary and has no such ambiguity, which is a further reason
the [supported pattern](how-to.md#the-supported-pattern) treats it as immutable. Where a comparison has to survive a
line-ending change, compare the parsed geometry rather than the manifest
digest.

### The boundary inventory sidecar

A saved simulation carries its boundary names in the solver's own order, and a
workflow row cites boundaries by those names (`MOVING_BOUNDARIES:
Blade1,Blade2`). The order is a property of the file, so it is never stated
by hand: a setup artifact that carries `mesh_order_list` is
refused, and the order is written from the file itself:

```text
pyfs-matrix inventory inputs/geometries/30_WB.fsm
```

writes `inputs/geometries/30_WB.fsm.boundaries.toml`, a `boundaries` list in the
file's order, and refuses to overwrite one that exists without `--overwrite`.
The sidecar sits beside the file, so a geometry kept in its own folder,
`inputs/geometries/30_WB/30_WB.fsm`, has it inside that folder, and the run reads it
from there. `pyfs-matrix inventory` reads an `.obj`'s order from its groups
instead ([above](#the-surface-names)), and refuses any other file without a
mesh block (an `.stl`, or a file the solver never saved) by name, because it
has no block to read the order from.

A row whose `.fsm` has a sidecar is checked when the script opens the file: a
sidecar that disagrees with the file's own block is refused before any seat is
spent, naming both lists, and an agreeing one is recorded in the run record as
the inventory source (`inventory_source: sidecar`; `mesh_block` when the file
alone declared the names). The record also carries the names
themselves, `inventory`, in the file's order; the post reads a section
distribution's selection over them. The sidecar is what lets a name resolve
for a file whose mesh block a reader cannot open, and it is otherwise a
statement the run verifies rather than trusts.

<a id="actions-saved-in-the-geometry-since-0330"></a>

### Actions saved in the geometry

A saved simulation keeps the unsteady solver actions it was saved with. When
the script creates an action with the name of a saved one, the saved one
stays and the solver runs ITS command, so a geometry saved on a workstation
after an unsteady run carries that workstation's walltime clock, interpreter
path included, and every unsteady run of it on a cluster aborts when the
clock fires. `pyfs-matrix inventory` names each saved action, on every call,
with the command that removes them:

```text
pyfs-matrix inventory inputs/geometries/30_WB/30_WB.fsm --clean
```

`--clean` reduces the file to its meshes and the boundary conditions
already applied. It sets the action count to 0 and removes
the action records, and it puts every other block back to the content a
freshly imported file holds, where that content is measured for the file's
build and length unit; everything else comes from the script. The blocks and
their fresh-import content were measured on the ten tier-3 geometries, fresh
imports saved by 26.120 (build 7012026) in metres, which hold the same
`GLOBAL`, `MOTION`, `POST`, `WAKE`, `SOLVER`, `ACOUSTIC`, `STABILITY` and
`AEROELASTIC` whatever the shape: those are the blocks reset, and each one
reset is named on standard error. Anything set by hand in them is discarded,
the reference point and frame of `GLOBAL` and the solver and wake settings of
`SOLVER` and `WAKE` included, since the script sets them again; the ten
geometries were all made by one preparation recipe, so the content is the one
common to those saves. Never reset:
`MESH` (the meshes, the boundaries, the trailing edges and the wake
termination marks), `PHYSICS` (the surface lists the boundary conditions are
set in), `WRAPPER` and `GRAPHICS` (which differ between fresh imports), and
`CAD`, `CADCREATE` and `CADMESHING` (measured on STL imports only). A file of
another build or unit, 26.124 included, has no measured fresh import: only its
saved actions are removed, every other block is kept, and the command says
so. That the solver opens and runs a cleaned file is owed by the licensed
validation round.

The file as it was is copied to `30_WB.fsm.bak-<stamp>` beside it first, and
it is read again after the change: its boundary names and every block kept
must be as before and its action records must read as none, or the copy is
put back and the call refused. A file whose build is measured but which lacks
one of the blocks to reset is refused before anything is written, and a file
already clean is not written. An existing sidecar is kept, since the
boundaries it lists did not change, unless `--overwrite` is given too. To
clean every geometry of a workspace kept one per folder:

```text
for d in inputs/geometries/*/; do n=$(basename "$d"); f="$d$n.fsm"; [ -f "$f" ] && pyfs-matrix inventory "$f" --clean; done
```

**The plan warns too.** `pyfs-matrix plan` reads the geometry of
every row whose run type is `unsteady` or `unsteady_rotor`, a continuation
included, with the same reader, and for each file carrying saved actions
prints a warning naming the rows that open it, the file, each action (name,
type, command) and the `--clean` command; a file whose action records cannot
be read is named as unreadable. The plan never refuses on that account: its
rows, its files and its exit status are those of the same plan without the
warnings.

## The refinement file and the audit

This section is the reference of `pyfs-matrix refine` and `pyfs-matrix
audit-mesh`; the walk-through is
[Refining or coarsening a mesh](how-to.md#refining-or-coarsening-a-mesh).

### The two commands

```text
pyfs-matrix refine MESH [FACTOR] [--families A,B] [--parallel F] [--normal F]
                   [--accept-remesh] [--accept-unknown] [--force-factors] [--config FILE]
                   [--out DIR] [--overwrite]
pyfs-matrix audit-mesh OBJ [--against SOURCE] [--out FILE]
```

| argument | of | meaning |
|---|---|---|
| `MESH` | `refine` | the source OBJ; it and its folder are never modified |
| `FACTOR` | `refine` | the factor of every selected family, a finite number above zero |
| `--families A,B` | `refine` | the families to change, comma separated (default: every family) |
| `--parallel F`, `--normal F` | `refine` | the factor of one direction of every selected grid family: `--parallel` along the family's reference perimeter, `--normal` across it (on a multiblock family, of the patch sides running that way against the perimeter); refused for a remeshed family unless `--accept-remesh` is given. `--spanwise F` and `--chordwise F` are read as `--parallel` and `--normal`, with a warning |
| `--accept-remesh` | `refine` | remesh with FACTOR a family given `--parallel` or `--normal`, or stated `method = "grid"`, whose grid is not recovered, and a later grid whose layout the blocks refuse (a shared curve counted apart), with a warning, in place of refusing it; the `accept_remesh` keyword of `refine_mesh` in Python |
| `--accept-unknown` | `refine` | warn and skip, in place of refusing, an unknown table or key of the refinement file, a value it cannot read (the key takes its default, a table left with no factor is skipped, a bad tag gives the built one), an implicit refinement file that cannot be read, a family table or `[components]` member the mesh does not hold, and a `--families` name it does not hold; the `accept_unknown` keyword of `refine_mesh` in Python |
| `--force-factors` | `refine` | raise a grid factor below the least its grid allows (one interval per side, or what a tube's caps carry) to that least, with a warning, in place of refusing it; the `force_factors` keyword of `refine_mesh` in Python |
| `--config FILE` | `refine` | the refinement file (default: `<stem>.refine.toml` beside the mesh) |
| `--out DIR` | `refine` | where the level folder goes (default: the parent of the folder holding the source); the `out_dir` keyword of `refine_mesh` in Python; `--out-dir DIR` is a deprecated alias |
| `--overwrite` | `refine` | replace an existing level folder |
| `OBJ` | `audit-mesh` | the OBJ to audit |
| `--against SOURCE` | `audit-mesh` | the OBJ it was made from; without it only G1, G2 and G4 are judged |
| `--out FILE` | `audit-mesh` | write the figures as CSV, one row per family and figure (the audit JSON is always written beside the OBJ, whatever `--out` says); `--csv FILE` is a deprecated alias. Refused when it names a file the command reads or writes: the OBJ, its boundaries file, its `<stem>.te.txt` or the points file the boundaries file names (`MeshAudit.files_read`), the OBJ's `<stem>.refine.json`, the `<stem>.audit.json` the command writes, and every one of these files of the `--against` source |

`refine` exits 0 when the level is written, whatever the audit says, and 2 when
the request is refused. `audit-mesh` exits 0 when every gate and check passes,
1 when one fails (the audit is still written) and 2 when its input is refused.
A refusal is printed on standard error, names the object, what was refused and
what to do, and ends with `Nothing was written.`: every refusal of the
arguments, the refinement file, the family names and the installed extras comes
before any family is resampled and before any file is written.
A level is written into a staging folder, audited there, and renamed
once complete, so an error leaves no level folder behind; with `--overwrite`
the existing level is replaced only then, and kept when an error comes first.

`--out-dir` and `--csv` are deprecated aliases of `--out` on their command: each
gives the identical result and warns once that it is deprecated, and an alias
given together with `--out` is refused, naming both.

An option the refinement no longer offers is warned and skipped, never
refused: the `[trailing_edge]` and `[periodic]` tables of the refinement file,
`keep_first_row` (the family key, the command flag and the `refine_mesh`
keyword), `trailing_edge_direction`, and the keys `axial`, `circumferential`,
`axis` and `origin` of a family table. A family table that states `factor`
beside the last four is refined by `factor`; one that states only them is
skipped.

### Where the factors come from

1. FACTOR applies to every family `--families` selects (default: every family).
   `--parallel` and `--normal` replace it in that direction of each selected
   grid family; given alone, the factor of the other direction is 1.
2. When the command gives none of FACTOR, `--parallel` and `--normal`, the
   factors are the `[families.<name>]` tables of the refinement file:
   `--config FILE`, or else `<stem>.refine.toml` beside the mesh. A family the
   file does not name is not changed. `--families` then selects among the
   file's tables: an unselected family is not changed, and a selected name the
   mesh does not hold is refused, as on the FACTOR route.
3. With no factor on the command and no file, a file that states no family,
   or a selection the file states no factor for, the command is refused.
4. A `[families.<name>]` table whose factors are not read (every one when the
   command gives the factors, an unselected one under `--families`) is a
   warning naming it, and `refine.json` lists it under
   `ignored_families_tables`; an `elements` key in it still applies.

The `[refine]`, `[components]` and `[[perimeter]]` tables of the refinement file
are read whenever the file exists, whatever gives the factors.

### The keys of the refinement file

The block below names every key at once; a real file holds the tables its
own mesh needs, and every family it names must be a family of that mesh.

```toml title="every-key.refine.toml"
[refine]
tag = "fine"
elements = "triangles"

[families.Wing]
factor = 2
parallel_factor = 2
normal_factor = 1.5
method = "grid"

[families.Tip]
factor = 2
method = "remesh"
elements = "quad-dominant"

[components]
Blade1 = ["Blade1_side", "Blade1_tip"]

[[perimeter]]
file = "wing.nodes.txt"
export_te_per_family = true
te_families = ["Wing"]
aft = [1.0, 0.0, 0.0]
```

| table | key | value | meaning |
|---|---|---|---|
| `[refine]` | `tag` | text | the level's name, `<stem>_<tag>`, in place of the factors |
| `[refine]` | `filename` | text, with or without `.obj` | the name of the level's folder and OBJ, in place of `<stem>_<tag>`; when both are stated the filename names the level and the tag is warned and skipped; a text that is not one file name is warned and skipped |
| `[refine]` | `elements` | `"triangles"` (default) or `"quad-dominant"` | the elements of every remeshed family that does not state its own |
| `[families.<name>]` | `elements` | `"triangles"` or `"quad-dominant"` | the elements of a remeshed family: quad-dominant pairs the remeshed triangles into convex quadrilaterals (angles 30 to 150 degrees, warp at most 10 degrees), never across an open boundary, the trailing edge or a ridge; refused with `method = "grid"`, ignored (and said so in `refine.json`) on a family that `"auto"` resolves to a grid |
| `[families.<name>]` | `factor` | number above zero | multiplies the intervals of each index direction of a grid; divides the target edge length of a remeshed family |
| `[families.<name>]` | `parallel_factor`, `normal_factor` | number above zero | the factor of one direction of a grid, replacing `factor` there: along the family's reference perimeter and across it. They need no trailing edge. `spanwise` and `chordwise` are read as `parallel_factor` and `normal_factor`, with a warning |
| `[families.<name>]` | `method` | `"auto"` (default), `"grid"` or `"remesh"` | `"auto"` takes the grid when it is recovered and remeshes otherwise; `"grid"` refuses a family whose grid is not recovered, naming why; `"remesh"` remeshes it |
| `[components]` | `NAME = [...]` | a non-empty list of family names | the members written as one family `NAME` of the output, their faces in the source's family order |
| `[[perimeter]]` | `file` | non-empty path | a node list saved from an ANSA SET node window (`Id, Name, X, Y, Z`), relative to this refine file; any number of `[[perimeter]]` tables may be stated, and one list may hold the perimeters of every component, in any node order |
| `[[perimeter]]` | `export_te_per_family` | boolean, default false | the list holds trailing edges: the level writes `<level>.te.txt` and `<level>.<family>.te.txt` from it, after component grouping |
| `[[perimeter]]` | `te_families` | list of family or component names | the trailing edge of each named family is its rearmost line, the listed edges its surface lies forward of, on the one listed perimeter of each piece that reaches furthest aft; the level writes `<level>.<family>.te.txt` for it by output family. A name that matches no family is warned and skipped |
| `[[perimeter]]` | `aft` | three numbers, not all zero; default `[1, 0, 0]` | the direction from the nose to the tail, which tells the rearmost line of a family |

Each of these is refused naming the file, the table and the key, and listing
the known keys: a table or key the list above does not hold, a family the mesh
does not hold, a family table with neither `factor` nor `parallel_factor` nor
`normal_factor`, and `parallel_factor` or `normal_factor` on a family whose
method is `"remesh"` (unless `--accept-remesh` is given, which remeshes a family
whose grid is not recovered, with a warning). Under `--accept-unknown` a table
or key the list above does not hold, a family table and a `[components]` member
the mesh does not hold are warned and skipped instead. In `[components]`, a member the
mesh does not hold, a family listed in two components, and a component named
after a family that is not one of its members are refused naming the component
and the family. A `[[perimeter]]` table that states no file, a `file` that is
missing, a node that matches no vertex of the mesh and a list that joins no
edge are warned and skipped.

### The tag of a level

The level is named `<stem>_<tag>` unless `[refine] filename` names it. The tag
is `[refine] tag` when the file states one, used as given. Otherwise it is
built from the factors, `p` standing for the decimal point:

| refinement | tag |
|---|---|
| factor 2 on every family | `R2` |
| factor 0.5 on every family | `R0p5` |
| normal 1.5 and parallel 0.7 on every family | `R1c1p5s0p7` |
| factor 2 on `Wing` only | `R-Wing2` |
| `Wing` at 2 and `Tip` at 1.5 | `R-Wing2-Tip1p5` |
| a selection whose built tag is longer than 32 characters | `R-<n>fam-<hash>` |

The letters of a built tag are `c` for the normal factor and `s` for the
parallel factor, the letters their earlier names gave, so a level keeps its
name across the rename of the keys.

A factor in a built tag shows at most 6 significant digits (`2.0000001` and
`2` both read `2`, `0.0000123456` reads `1p23456e-05`); `refine.json` holds
the exact factor under `specs`. For a short tag without a hash, two otherwise
identical selections whose factors agree to 6 significant digits build the
same tag, and the second level is refused as an existing one unless
`--overwrite` (`overwrite=True`) replaces it; give a `[refine] tag` to keep both.
Summary tags hash the exact factors, so matching rounded spellings do not
imply matching summary tags.

A built tag of at most 32 characters is the tag above. A longer one is
`R-<n>fam-<hash>`, at most 20 characters for any selection: `<n>` is the number
of selected families and `<hash>` the first 8 hexadecimal characters of the
SHA-256 of the canonical selection, encoded as UTF-8. The canonical selection
holds one line per selected family, in the source's family order, joined by a
newline: the family's name, then every option its table states that changes
the level (`factor`, `chordwise` for the normal factor, `spanwise` for the
parallel factor, `method`, `elements`) as `key=value` pairs sorted by key and
separated by single spaces, for example `Wing chordwise=1.5 factor=2
spanwise=2`. The same selection gives the same tag on every run and machine,
and two selections that differ in a family or an option give different
canonical selections; the 8-character digest tells them apart and is not a
guarantee against collision. For such a tag `refine.json` lists the selected
families under `tag_selection`, in the source's order. A short tag tells
apart a family's factors only: two selections that differ only
in `method` or `elements` share it. A family name that cannot be part of a
folder name is refused when the tag is built from the names, and not when
the tag is the summary and the hash.

### The files of a level

The level folder is `<out>/<stem>_<tag>/` (`--out`, or `out_dir` in Python;
`[refine] filename` replaces `<stem>_<tag>`), and every file in it is written
through the package's one text route, without a carriage return.

| file | written when | content |
|---|---|---|
| `<stem>_<tag>.obj` | always | the level, its families in the source's order (a component in place of its members) |
| `<stem>_<tag>.te.txt` | a `[[perimeter]]` list exports trailing edges | one mid-point per trailing-edge edge of the new mesh |
| `<stem>_<tag>.<family>.te.txt` | a `[[perimeter]]` list exports trailing edges or names `te_families` | the same points for one output family |
| `<stem>_<tag>.obj.boundaries.toml` | the source has a sidecar, or a perimeter list exports trailing edges | updated inventory and preserved declarations, with component renames only |
| `<stem>_<tag>.refine.json` | always | what was done to each family |
| `<stem>_<tag>.audit.json` | always | the audit of the level against its source |

The trailing edges the level writes come from the `[[perimeter]]` lists of the
refine file; there is no fallback to marking declarations or to a
`<stem>.te.txt` beside the mesh. Relative paths resolve beside the refine
file, and the mid-points are written in the unit of the mesh (`[import] units`
of the OBJ sidecar, else metres).

The source sidecar is `<mesh>.obj.boundaries.toml`, falling back to the legacy
`<mesh>.boundaries.toml`. Refinement preserves its declarations, comments and
formatting, except component renames. It never selects the new points file for
marking: edit the level's `[trailing_edges.<label>] file` yourself. When a
perimeter list exports the trailing edges and the source declares none, the
level's boundaries file declares one `[trailing_edges.<component>]` table per
component, with `file = "<level>.<component>.te.txt"` and `type = "STANDARD"`,
for you to edit before `mark-boundaries`; a source file that declares its own
trailing edges keeps them. With `export_te_per_family`, each
`<level>.<family>.te.txt` can be named by one such entry, with your chosen type
and `fs_build`.

`refine.json` states `schema_version` (2), `source`, `level`, `config` (the
refinement file read, or null), `trailing_edge_files` (the level points path,
or null), `specs` (the factors of each family), `tag_selection` (the selected
families, for a tag shortened to the summary and the hash),
`components`, `ignored_families_tables` (the families whose file table was not
read for its factors) and `faces` (the face count of each family of the output).
Its `families` entry holds, per family:

- a grid: `method` (`"grid"`), `reason` (the layout recovered), `layout`,
  `ends`, `split`, `grid` (the node counts before and after), `intervals`
  (`chordwise` for the normal direction and `spanwise` for the parallel one, before and after), `faces` (before and after),
  `order` (`"sweep"` when the source's sweep was kept, `"nearest"` otherwise)
  and `interfaces` (the nodes of each curve it shares); a grid whose reference
  perimeter came from a node list or from the mesh adds `trailing_edge`
  (`"perimeter"` or `"detected"`, where its trailing edge came from) and
  `trailing_edge_points`, the mid-point `[x, y, z]` of each edge of that line
  on the source, which the audit of the level reads to count the source's
  trailing-edge chains;
- a smooth tube is a grid whose circumferential direction is a periodic cubic
  spline, with the seam at the lowest source node index of its first end
  station and no trailing-edge points; a multiblock family reports `layout`
  `"multiblock"`, `patches` (their number), `blocks` (each patch's `rows` and
  `columns` before and after), `arcs` (the patch sides), `order`
  (`"nearest"`) and `kept_sides` (each patch side a factor below 1/m kept:
  `patch`, `side`, `source_intervals`, `intervals`, `centroid`, `bbox_min`,
  `bbox_max`; empty when none); `--parallel` and `--normal` apply to each
  patch side by its direction against the family's reference perimeter
  (parallel within 45 degrees of it, measured as the length-weighted mean of
  the absolute cosine against the nearest perimeter segment), refused for a
  patch whose two directions cannot be told apart, and across a patch side the level is continuous, not smooth;
- a grid resampled with the grids it shares nodes with (one layout) reports
  `grouped_with` (those families), its own `layout` (`"sheet"` or
  `"multiblock"`), and the `patches`, `blocks`, `arcs`, `kept_sides` and
  `faces` of its own part of the layout, with `order` `"nearest"`;
- a remeshed family: `method` (`"remesh"`), `reason` (why no grid was taken),
  `elements`, `quads`, `triangles` and `quad_share` (the element mode and its
  counts; `elements` on a grid says the key was ignored),
  the families remeshed together, the curve edges kept, the median ratio of
  edge length to target, the interfaces rebuilt on a grid's nodes, and the
  face counts before and after; a family remeshed at factor 1 that shares a
  curve with a refined side adds `shared_edge_target_m`, the minimum, mean and
  maximum of its target length at its nodes on that curve, in metres, for
  example `{"min": 0.0021, "mean": 0.0034, "max": 0.0052}`. The mesh's
  `[import] units` supplies the conversion. If no convertible mesh unit is
  stated, the record uses `shared_edge_target_mesh_units` instead, with
  lengths in the source coordinates;
- a neighbour the two-layer band would cover whole: `method`
  `"rebuilt_whole"`, `reason` `"band_covers_family"`, `band` and `faces` (both
  the family's face count in the source), remeshed whole at factor 1 as if its
  table stated `factor = 1` and `method = "remesh"`, with one warning naming it;
- a family the refinement does not change: `method` `"copied"`, or
  `"unchanged"` with the face count of its two-layer `band` when a grid's
  nodes on a shared curve changed, and `shared_edge_target_m` as above.

A key may be added to `refine.json` or `audit.json` without changing
`schema_version`; a key is removed or changes type only with a new one.
`refine.json` uses schema version 2, which carries the conditional target
unit keys above; the audit schema remains version 1.

### Reference perimeters and trailing edges

A grid family has a reference perimeter: the grid line its two directions are
measured from. `--parallel` runs along it and `--normal` across it. The line
is found, in this order, from the `[[perimeter]]` node lists of the refine
file, then from the mesh. A node list is saved from an ANSA SET node window
(`Id, Name, X, Y, Z`); each listed node is matched to the mesh vertex within a
quarter of that vertex's shortest edge, so rounded coordinates match. A family
takes the first line that recovers its grid, the exported lists first: the
whole of a list on the family, then each connected piece of it, then each
piece cut at its corners, so a trailing edge and a root listed together are
told apart. An incomplete list on a sheet is completed from the grid line
every listed edge lies on, with a warning naming the edges added.

- **Trailing edge.** A list with `export_te_per_family = true` is a trailing
  edge: the level writes its mid-points as `<level>.te.txt` and
  `<level>.<family>.te.txt`. A list with `te_families` takes, for each named
  family or component, its rearmost line: the listed edges its surface lies
  forward of, forward being against `aft` (default +x). That line is also the
  first tried to orient the family's grid.
- **No trailing edge.** `--parallel` and `--normal` need none. A grid family
  with none takes the side of its boundary that holds a neighbouring family's
  trailing edge, else its longest side, and warns which.
- **Warnings.** A node that matches no vertex, a list that is missing or
  joins no edge, and a `te_families` name that matches no family are warned
  and skipped; the refinement goes on.
- **Record.** The family's entry of `refine.json` holds `trailing_edge`
  (`"perimeter"` or `"detected"`) and `trailing_edge_points`.

### The geometry commands for trailing edges

Three commands of `pyfs-workspace geometry` prepare the lists and files above.
None needs a solver.

```text
pyfs-workspace geometry convert2midnodes NODES OUTPUT [--unit U] [--per-family MESH] [--accept-empty] [--overwrite]
pyfs-workspace geometry identify-te OBJ [NODES] [--families A,B] [--max-angle DEG] [--aft X Y Z]
                                    [--unit U] [--simulation-unit U] [--overwrite]
pyfs-workspace geometry prepare-to-refine OBJ [--max-angle DEG] [--aft X Y Z] [--overwrite]
```

| command | what it writes |
|---|---|
| `convert2midnodes NODES OUTPUT` | a `.te.txt` from an ANSA SET node list in any node order: the nodes are ordered along their lines, a long jump starts a new line, and each neighbouring pair gives one mid-point. `--unit` states the coordinates' unit (default `METER`). No mesh is needed. With `--per-family MESH` it writes `<OUTPUT stem>.<family>.te.txt` for each family of the OBJ instead, from the mesh edges joining two listed nodes |
| `identify-te OBJ [NODES]` | the trailing edges of the OBJ in the format the solver imports: `<obj stem>.nodes.te.txt` for every family, or `<obj stem>.<family>.fs.te.txt` for each family named by `--families`, each beside the package's points file (`<obj stem>.te.txt` or `<obj stem>.<family>.te.txt`) that a boundaries file's `[trailing_edges.<label>] file` reads. Without NODES they are found from the mesh: each family is cut at its sharp edges into pieces, a piece's perimeter is its boundary and its sharp edges, and on the one perimeter of each piece that reaches furthest aft the rearmost edges that lie within `--max-angle` (default 45 degrees) of the plane across `--aft` (the yz plane by default) are kept; the nodes are also written as `<obj stem>.nodes.txt`, the node list a refine file reads. With NODES, an ANSA SET node list, they are taken among its lines, on a refined level with merged families too. `--aft` is the nose-to-tail direction (default +x); `--unit` is the coordinates' unit (default the mesh's, else `METER`) and `--simulation-unit` the unit the solver reads the file in (default `--unit`) |
| `prepare-to-refine OBJ` | an optional first step of a refinement, from any OBJ: `<stem>_patches.obj` with every family cut at its sharp edges into `<family>_<NNN>_grid` patches (the quadrilaterals the refinement recovers as a grid) and `<family>_<NNN>_mixed` ones, numbered within the family from the largest extent along y; `<stem>_patches.refine.toml` with every patch at factor 1 (`method = "grid"` or `"remesh"`), `[components]` putting each family back together and a `[[perimeter]]` with `te_families`; and `<stem>_patches.nodes.txt`, the rearmost line of each grid patch, its edges within `--max-angle` of the plane across `--aft` (the yz plane by default), as an ANSA SET node list. The source is not modified; an earlier run is kept unless `--overwrite` is given |

In Python, `prepare_to_refine` of `pyflightstream.workspace` is the function
behind `prepare-to-refine` ([The Python API](#the-python-api)).

### What the audit judges

The audit reads the mesh, and the source when there is one, with numpy alone.
A GATE is judged on its own terms, a RELATIVE CHECK compares a 95th percentile
(linear interpolation between ranks) of the mesh with the source's, and a
FIGURE is reported and never judged.

| gate | fails when |
|---|---|
| G1 | an edge is shared by more than two faces, two nodes sit at one position (within 1e-9 of the size, the diagonal of the bounding box), or a face has zero area |
| G2 | two neighbouring faces have opposite orientation, or a closed shell, including one spread across families, does not enclose a positive volume |
| G3 | the open boundary loops of the mesh are not the source's in number and in the opening each closes: a level loop matches one source loop, one to one, when every node of each lies within a quarter of the source loop's extent (its bounding-box diagonal) from the other's polyline |
| G4 | a trailing-edge point lies on no mesh edge, two points lie on one mesh edge (`points_sharing_an_edge`), the trailing-edge chains are not the source's in number, or a chain of the source ends where no chain of the level ends (a shortened line); the lines' total lengths are reported, not judged |
| G5 | two families that shared nodes in the source share none |
| G6 | a grid family written at factor 1 no longer has the source's faces in coordinates and order |

| relative check | fails when the 95th percentile exceeds |
|---|---|
| equiangle skewness | the source's plus 0.05 |
| quadrilateral warp | the larger of the source's and 10 degrees |
| size growth (the area ratio of two neighbours, across edges whose dihedral is below 30 degrees) | the larger of the source's and 2 |

Each check is made per family and on the whole mesh. A check is relative
because the source is the accepted mesh: where a source already exceeds a
practice, the limit is the source's own value (the larger of the source's and
the practice's, as the table says), so the level is judged not to be worse than
its source, and the audit still reports that the source is beyond the practice.
Reported and never judged, per family and on the whole
mesh: the face, triangle and quadrilateral counts, the aspect ratio (95th
percentile and largest), the faces beyond the pre-processor's quality
thresholds (aspect ratio above 8 and above 20, skewness above 0.5, warp above
10 and above 45 degrees, a quadrilateral angle under 45 degrees, a triangle
angle under 30 degrees), a face quality ratio (a face's inscribed radius
against its neighbours', the solver's user's manual calling below 2 good; the
manual gives no formula, so the package's is its own reading), the faces whose
aspect ratio exceeds 50, the trailing-edge triangles whose aspect ratio exceeds
50, and the faces lying on the plane y = 0.

Without `--against` only G1, G2 and G4 are judged and the rest is reported.
G6 is judged only for a level `refine` wrote, which names its grid families at
factor 1 (and each component whose every member is one) in its `refine.json`
under `unchanged_grids`; `audit-mesh` reads them from the level's
`refine.json` when it names that level and the source given with `--against`,
so a saved level is re-audited as `refine` audited it. The record's
`trailing_edge_files` selects its level and source points independently of
marking declarations. G4 reads the same
record for a family whose trailing edge `refine` detected: the source's chains
are the connected chains of its listed edges and the detected edges the record
lists under `trailing_edge_points`, together, so a detected line that a listed
edge continues is one chain.

`audit.json` holds `schema_version`, `mesh`, `source`, `passed`, `gates` and
`checks` (each with its `name`, `family`, `verdict` (`pass`, `fail` or
`not judged`) and `values`) and `figures` (per family and `(whole mesh)`). A
failed gate or check is also a warning: `audit gate G3 failed on (whole mesh):
open_loops 2, source_open_loops 1, unmatched_loops 1`.

### The Python API

Each of these is imported from `pyflightstream.workspace`.

| name | what it is |
|---|---|
| `refine_mesh(mesh, factor=None, *, families=None, parallel=None, normal=None, config=None, out_dir=None, overwrite=False, accept_remesh=False, accept_unknown=False, force_factors=False, progress=None)` | writes a level; `parallel` and `normal` are the two directional factors (`chordwise` and `spanwise` are still read as `normal` and `parallel`, with a warning); `accept_remesh` remeshes with `factor` a family given a directional factor whose grid is not recovered, with a warning; `accept_unknown` warns and skips the entries `--accept-unknown` names; `progress` is called with one line per stage and family (the command prints them to stderr); returns a `RefinedMesh`; raises `InputArtifactError` on every refusal and `MissingExtraError` when a family must be remeshed and the geometry extra is missing |
| `RefinedMesh` | frozen: `folder` (the level folder), `obj` (its OBJ), `files` (every file written, the OBJ first), `report` (the `families` entry of `refine.json`) and `audit` (the `MeshAudit` of the level) |
| `prepare_to_refine(mesh, *, max_angle=45.0, aft=(1.0, 0.0, 0.0), overwrite=False)` | the function behind `geometry prepare-to-refine`: writes the patches OBJ, the refine file and the node list beside the source and returns a `PreparedMesh` |
| `wake_edges.write_trailing_edge_midnodes(source, path, *, unit="METER", overwrite=False)` | the function behind `geometry convert2midnodes`: writes one mid-point per neighbouring pair of the node list's lines, under a line naming `unit`, and returns the path |
| `wake_edges.write_trailing_edge_midnodes_per_family(source, mesh, path, *, unit="METER", overwrite=False)` | the function behind `convert2midnodes --per-family`: one points file per family of `mesh`, the edges whose two ends are listed |
| `wake_edges.write_trailing_edges_identified(mesh, source=None, families=None, *, aft=(1.0, 0.0, 0.0), max_angle=45.0, unit=None, simulation_unit=None, overwrite=False, accept_empty=False)` | the function behind `geometry identify-te`: writes the solver node files, the package points files and, without `source`, the ANSA node list, and returns their paths |
| `PreparedMesh` | frozen: `obj`, `config` (the refine file) and `nodes` (the node list) written, and `patches`, the patch names of each original family in order |
| `audit_mesh(mesh, *, against=None, unchanged_grids=())` | audits an OBJ, writes `<stem>.audit.json` beside it and returns a `MeshAudit`; `unchanged_grids` names the grid families G6 compares (default: those the level's `refine.json` lists) |
| `MeshAudit` | frozen: `mesh`, `source`, `gates` and `checks` (each item with `name`, `family`, `values`, `verdict`, `passed` and `line()`), `figures`, `path`, `passed`, `failures`, `as_json()`, `summary()` and `write_csv(path)`; the static method `MeshAudit.files_read(mesh)` returns the files an audit of `mesh` reads, each with what it is (the OBJ, its boundaries file, its trailing-edge points files), a file that does not exist included |
| `derive_thin_blade(geometry, *, root_offset, overwrite=False, boundary=None)` | the function behind `pyfs-matrix degenerate`: derives the thin blade of a blade mesh (an `.fsm` or an OBJ), writes it beside the source and returns a `ThinBlade`; `thin_blade_path` gives the name it writes |

### Limits of the refinement

- **A grid that mixes cells is remeshed.** A lateral grid that mixes
 quadrilateral and triangulated cells is remeshed under `method = "auto"` and
 refused under `method = "grid"` naming the reason; a family of quadrilaterals
 only is recovered as one grid, a smooth tube or a multiblock.
- **Quad-dominant levels can warn.** The audit's growth and skewness checks
 read a quadrilateral beside a triangle as a size jump and a paired rhombus
 as skewed, so pairing can raise both figures; the tested two-family plate
 at factor 2 warned on both. A warning comes only from a figure above its
 limit; read the reported values.
- **A multiblock patch side is continuous, not smooth.** No spline crosses it.
- **Factor 1.** Under `method = "auto"` a family at factor 1 is copied; a
 family that states `method = "remesh"` is remeshed at any factor.
- **A component is audited against its members.** A level written with
 `[components]` is compared with the union of the members in the source,
 read from the level's `refine.json`.
- **A triangulated tip cap is not part of a grid.** A cap is part of a grid only
 when it is a fan of triangles around one pole node or a zipper. Give any other
 cap a family of its own in the pre-processor and merge it back with
 `[components]`, as in
 [A solid blade kept structured by dummy families](how-to.md#a-solid-blade-kept-structured-by-dummy-families).
- **Grids that share nodes are resampled as one layout.** Grid families of
 quadrilaterals that touch, sheets and multiblock families, are cut together
 into four-sided patches, the curves where two families meet among the patch
 sides, so each shared curve is resampled once and both families hold its
 nodes. Its interval count is `max(1, round(f m))` from each family holding
 it, `f` the family's factor in the curve's direction; two counts that differ
 are refused naming both families, the curve's end nodes and both counts.
 A tube, a family with triangles, and touching
 grids whose union has no layout of four-sided patches join none: of grids
 that share nodes the first in the source's family order is then a grid and a
 later one is remeshed, or refused naming both under `method = "grid"`.
- **A level's boundaries file states the level's inventory.** When the source's
 boundaries file states `mesh_faces`, `boundary_faces` or `mesh_sha256`, the
 level's states each of them counted in the level's OBJ as written (per
 boundary in the level's `boundaries` order, after `[components]`) and its
 sha256, and its header comment names that sha256; a source file without them
 gives a level file without them.
- **Offline verification, not validation.** The tests verify the geometry of a
 level offline. Whether a level gives the solver the result of a mesh made at
 that size in the pre-processor is a licensed comparison, reported for one
 rotor case.

## Mesh format policy

The library's mesh seam is deliberately narrow: OBJ in and out. READING a
mesh is a runtime capability through trimesh, because the
trailing-edge extraction sits on the default path of a rotor campaign and a
capability behind an extra makes the library promise what a default install
cannot do. What stays in the
`[geom]` extra is the SPATIAL INDEX the geometry gate queries through:
rtree's bounds tree and scipy's kd-tree. Reading vertices and faces needs
neither. Two standing decisions bound any widening:

* More formats never enter through raw third-party APIs. If a
 workflow needs formats beyond OBJ, meshio joins the `[geom]` extra
 as a conversion backend behind a project-owned adapter (decision D8): the adapter exposes only what the workflow needs,
 a license evidence card is committed at adoption time like every
 dependency, and validity checks stay with trimesh. The dependency assessment
 refused meshio on the committed weight budget, at five new
 distributions and 12.26 MiB against limits of one and five, one of them
 a syntax highlighter. Its route into this package is still through the
 adapter and still only if a workflow needs it.
* Until that need materializes, converting external formats to OBJ
 with your own tooling is the supported route.

## The four rotor facts a reference artifact once carried

The reference artifact refuses the retired fields `rotation`, `blade_travel`,
`rpm_sign_installed` and `rpm_sign_isolated`. The speed a row states is a
MAGNITUDE and the hand is `rpm_sign` on that rotor's own block, beside its
`axis`. The [upgrading page](../upgrading.md#older-layouts)
explains the historical row-sign convention. The argument that
related them is kept here, because it is what a reader setting up a new
rotor has to work out once. For the isolated-rotor reference case:

* The frame is x aft, y starboard, z up. On a port propeller, +y is
 inboard.
* `blade_travel = "inboard_down"` is the datasheet's side-independent
 vocabulary: the blade at its inboard azimuth (the +y side of the disc)
 travels towards -z. That needs an angular velocity of negative sign about
 +x, which is the "positive rpm is inboard-up" sentence the datasheet
 states the other way round.
* `rotation` is the viewed-from-behind sense. An observer behind the
 aircraft looking forward has screen-right +y and screen-up +z; a point at
 screen-right moving down reads clockwise. So inboard-down on a port
 propeller is clockwise from behind; if the meshes' port and starboard
 assignment is the other way, it is counterclockwise, a one-word edit.
* `rpm_sign_installed = -1` was that sign about +x for the installed
 meshes, and `rpm_sign_isolated = 1` the sign for the isolated meshes,
 which were built the other way round; which of the two applies is a
 property of the mesh a row opens, which is why the row states it.

None of this was ever read by an emitter, and the sense of rotation does
not determine the sign of the rotor speed on its own: the sign is the
mesh's, the sense is the propeller's, and the row is where the two meet.

## Applying named boundary declarations

Run `pyfs-workspace geometry mark-boundaries <mesh>.obj` to preview the
declarations, then add `--apply` on a licensed machine. The verb requires a
current OBJ inventory, explicit `[import] units`, and `fs_build`. Each named
file entry becomes one import; detection remains STANDARD only. Source points
are matched before import operations and carried through their scale, rotation,
translation and mirror transformations in metres. Explicit termination nodes
use the written OBJ vertex indices and are refused after vertex-changing
operations. Termination nodes combined with merging remain conservatively
refused until their saved-state persistence is measured.

The output `.fsm.boundaries.toml` contains only inventory fields and
`marked_by`; it carries no import or marking declarations. The original
`.obj.boundaries.toml` remains the authoring source. The matrix refuses
declaration tables; the marking verb refuses unnamed forms with their
named-table translation.

## What this policy is not

It is not a promise to wrap the GUI. Steps stay GUI-only until the
solver's scripting interface documents a command for them; when that
happens, the command enters the database with its citation and the
step graduates from this page to the reference.

## Matrix geometry

A matrix row names the saved simulation that marking produces. The order in
which planning reads its inventory, the stale-input refusals and the raw OBJ
imports kept by FSI rows are in [matrix geometry](../geometry.md#matrix-geometry).
