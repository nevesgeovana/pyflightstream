# Grid and convert a named IGES

Two commands read IGES files whose components are named, as a CAD or meshing system writes
them: `geometry iges-grid` builds one surface grid for the solver, one family per component,
and `geometry iges-convert` rewrites the files as one IGES of B-spline faces that the solver's
CAD import reads. Both need the optional `gmsh` extra:

```text
pip install "pyflightstream[gmsh]"
```

Without it, either command stops with that install line and writes nothing.

## Component names

An IGES file names a component with a NAME property (entity 406, form 15) on a level: every
face on that level belongs to the component. The name is read up to its first `|`, so
`Fuselage|ANSA_Thick=1.` names the component `Fuselage`. A face whose level carries no NAME
belongs to `<file stem>_level<N>`. A NAME on level 0 names no level: it is a property another
entity points at, such as a feature name of the CAD system, and is never a component.

The file is read byte for byte, so its fixed 80-byte records and Hollerith counts hold for
any name. The bytes of a NAME are decoded with `--name-encoding` (default `latin-1`, one
character per byte); use `--name-encoding utf-8` for names written in UTF-8. The encoding is
never guessed, a name that is not valid in it is refused, and `iges-convert` writes names in
the same encoding, counting bytes in each Hollerith length.

The faces are every trimmed surface (144) and every untrimmed surface at the top level, in the
order of the file's directory. That is the order in which the geometry kernel imports them, and
the command compares the two counts: a file where they differ is refused with both counts.

## Grid a configuration

```text
pyfs-workspace geometry iges-grid airframe.igs rotor.igs --grid grid.toml --out model.obj
```

The faces of every file are healed and joined, so an edge two faces share becomes one curve
and its nodes are shared: the junction between two components is conformal. Each four-sided
patch of a component is meshed transfinite with the laws the grid control file gives and
recombined into quads; every other patch is meshed quad-dominant at the component's size. The
command writes:

| File | Content |
|---|---|
| `model.obj` | One family (`g`) per component, in the order of the grid control file, then the components the file does not name in the order of the IGES files; each family's faces turned to point outward |
| `model.obj.boundaries.toml` | The boundaries file `geometry mark-boundaries` reads: `fs_build`, the family list and face counts, `[import] units`, and one trailing-edge entry per component with a trailing edge, or `[trailing_edges] none = true` |
| `model.<Component>.te.txt` | The midpoints of a component's trailing-edge edges, under the unit line; a character of the name a file name cannot hold is written `_` |
| `model.obj.json` | The record: nodes and faces, per component the faces, nodes, quad share, least scaled Jacobian, largest aspect, smallest and largest corner angle, sliver faces and size, the conformal check, the joins, the transfinite patches, the counts one component imposed on another, and every warning |

The OBJ then enters `geometry mark-boundaries`, `repitch`, `collapse-te` and `morph` as any
other OBJ.

### The grid control file

```toml
fs_build = "26.127"

[defaults]
size = 150.0

[component.Wing]
size = 80.0
chord = {count = 40, law = "cosine"}
span = {count = 60, law = "geometric", ratio = 1.03}
trailing_edge = "auto"

[component.Fuselage]
size = 150.0
```

Lengths are in the unit of the first IGES file.

| Key | Meaning |
|---|---|
| `fs_build` | The solver build the boundaries file names; default the newest build this package knows |
| `[defaults] size` | The target edge of a component with no size; default a hundredth of the assembly's diagonal |
| `[defaults] tolerance` | The distance within which two faces are joined; default a millionth of the assembly's diagonal, widened to a measured gap the files leave (see checks below) |
| `[defaults] te_angle_deg` | The angle of `trailing_edge = "auto"`, default 60 |
| `[defaults] symmetry` | `"none"` (default), or `"x"`, `"y"`, `"z"`: the origin plane (normal to that axis) a half model is mirrored across when inner faces are removed. Never inferred; recorded as `symmetry` |
| `[defaults] remove_inner_faces` | `true` (default) removes the faces that lie inside the assembly where components cross (see below); `false` keeps every face |
| `[component.<Name>]` | One table per component, by the name the IGES gives it |
| `size` | The component's target edge; also the count of a side that `chord` or `span` does not set |
| `chord`, `span` | `{count, law, ratio}`: the cells along each direction of a four-sided patch and their law |
| `span_axis` | `x`, `y`, `z` or three numbers; default `y` or `z`, whichever the component extends along more |
| `le_cluster`, `te_cluster` | For a cosine chord: its `ratio`, the end cell over the middle cell as the count grows, 1 or less |
| `structured` | `false` meshes even the four-sided patches quad-dominant; default `true` |
| `trailing_edge` | `"auto"`, or a list of IGES curve names |
| `te_angle_deg` | The angle of `"auto"` for this component |

A patch is four-sided when it has four distinct curves and each of its four corners is below 160
degrees. A curve that continues the next nearly straight on is a point on a side, not a corner:
a side the join cut in two, or a three-cornered patch, is meshed quad-dominant, since a
transfinite map flattens the cell at such a point. 160 degrees leaves a margin above the real
corners of wing, tail and body panels.

The span pair of a four-sided patch is the pair of opposite sides closer to the span axis; the
other pair is the chord. A side shorter than the component's size is a strip, such as the base
of a blunt trailing edge, and takes one cell whatever its law; a count the grid control file
states for that direction is then warned with the component, the side and both counts.

A patch meshed quad-dominant grows its cells from its short curves: about a curve shorter than
the component's size, such as a piece the join cuts off, the size is that curve's length and
grows by 0.3 of the distance from it until it is the component's size again, so the curve
closes with cells of its own length rather than a sliver. These patches are meshed with gmsh's
MeshAdapt algorithm, which keeps the size on a strongly curved or narrow face, and two triangles
become a quad only when its every corner lies between 6 and 174 degrees.

| `law` | Spacing |
|---|---|
| `uniform` | Equal cells |
| `cosine` | Clustered at both ends by a symmetric bump law. `ratio` is the end cell over the middle cell as the count grows: at 6 cells a ratio of 0.2 gives an end cell about 0.33 of the middle one, at 40 cells about 0.21. Default: the end-to-middle ratio of cosine spacing for the count; the nodes are not at the cosine-spacing positions |
| `geometric` | Each cell `ratio` times the next one toward the clustered end (default 1.1) |
| `tanh` | A one-sided clustering of coefficient `ratio` (default 1.05; nearer 1 clusters harder) |

The clustered end of a one-sided law is the tip for a span side (the end farther from the plane
of symmetry along the span axis) and the downstream end, the larger x, for a chord side, on both
sides of a patch whichever way the join left each curve. When
`le_cluster` and `te_cluster` differ, the cosine law, which is symmetric, takes the smaller and
warns.

The opposite sides of a four-sided patch take one count, and a side two patches share takes
one count too. The curves that must agree form a group, and each group takes the count of the
first component in the grid control file that asks; every other request in the group is
recorded under `count_overrides`.

A component the IGES files hold and the grid control file does not name is warned and meshed
unstructured at the defaults size. A `[component.<Name>]` that names no component, and a key
that does not apply, are warned and skipped. A value that cannot be read is refused before
anything is imported.

### Trailing edges

With `trailing_edge = "auto"`, an edge two faces of the component share is a trailing edge when
their outward normals differ by more than `te_angle_deg` and their bisector points downstream
(+x) within 60 degrees. A leading edge faces upstream and a tip cap sideways, so neither is
taken. A sharp trailing edge gives one line. A blunt one with its base faces is found as two
rims, the lines on opposite sides of a base face, and one of them is marked: the longer, or on
a tie the one containing the lowest node number. This is a mesh-numbering tie-break,
not a choice of the geometrically lower rim. A line that joins the dropped rim to the kept one, such as
a tip's base edge, is dropped with it, and the record gives the count under
`dropped_rim_edges`. Both rims shed two wakes a base cell apart: on FlightStream 26.127 the
solve of the validation wing then diverged, and converged with either rim alone. A trailing edge read
from named IGES curves is marked as named. An open trailing edge, with no base face, is not
found this way. If more than one cell spans the blunt base thickness, the rims share no
base face and both remain marked.

With a list, each name is the NAME of a level holding curves at the top level of an IGES file
(lines, B-spline curves and composite curves); the edges of the component whose nodes lie on
those curves, within a hundredth of the component's size, are the trailing edge.

### Checks and warnings

Quality is warned with its numbers and never refused: a least scaled Jacobian below 0.1, a
largest aspect above 20, sliver faces (a corner under 5 or over 175 degrees, on which the
solver's surface vorticity can degenerate) with their count and the component's corner range,
and a component face that could not be meshed. The conformal check
counts the open edges of the grid. An open edge on a curve that bounds one face and lies on no
other is a boundary of the body, such as the open root of a wing; every other open edge is a
mismatch, warned and recorded as `conformal_mismatches`.

A free curve lies on another when five points of it are within a hundredth of the smaller size
of the two components and project inside the other curve's own span (a point that projects past
its end lies beside it, on the next piece of a curve the join cut). Such a pair is a join the
files missed: when `[defaults] tolerance` is not given, the gap is measured and every face is
joined again at one and a half times the widest gap, warned and recorded under `closed_gaps`
with the components and the gap. A wider opening, such as a blunt trailing edge left open, is a
boundary. A stated tolerance is kept, and a near miss under it stays a mismatch.

### Faces inside the assembly

Untrimmed components cross: a wing runs through the body to the plane of symmetry, a fillet lies
over the wing and the body, a fin root sinks into the body. The join splits them along each
crossing, where four faces then meet, and after the mesh the faces that lie inside the assembly
are removed so the OBJ holds the outer skin only. The faces of a component split into regions at
the crossings. The kept regions leave every edge to two faces or none and keep at least one
region of every component; each region left out lies inside what is kept, by the median
generalized winding number of the kept faces, oriented outward, at the centres of its nine
deepest faces (those farthest from its edge, so a fillet's tangent start on the skin it covers
does not decide). Of those selections the one keeping the largest area is written. A half model
is mirrored for the measure only across the plane `[defaults] symmetry` states; with none
stated nothing is mirrored and no plane is inferred from the geometry. Without a mirror, a region
near an open symmetry seam is measured against an open body, so check the removed areas the
warnings report. Each component that lost faces is warned with the count
and the area and recorded under `inner_faces_removed` and `inner_area_removed`; the record's
`inner_faces` says what was done. When no selection closes every crossing, as where a tailplane
with an open trailing edge crosses a fin and the crossing curve on the fin does not close, every
face is kept, a warning says so and `inner_faces` says why; so is an assembly whose crossings
leave more than 200000 selections to try. With `remove_inner_faces = false` and components that
cross, every face is kept and a warning says so. On FlightStream 26.127 the validation wing, body, tails and
fillet grid diverged with its inner faces kept, even with no wake, and converged without them.

## Convert to B-spline faces

```text
pyfs-workspace geometry iges-convert fuselage.igs --out fuselage-nurbs.igs
```

Every face, including a surface of revolution, is converted to a B-spline surface and written
to one IGES holding only B-spline surfaces and curves. Each component takes one level and one
NAME on it, so the solver and `iges-grid` read the same components back. The command reads the
written file back face by face before it keeps it and writes the record `<out>.json`: the faces
of each component, the digest of each source, the surface types before and after, and the
read-back.

The trimming curves carry the flags the solver's CAD import reads. Each curve on a parametric
surface (entity 142) with a parameter-space curve is flagged as geometry (entity use 00, columns
69 and 70 of its directory entry) with PREF 1, the parameter-space curve preferred; that curve
(its BPTR) and every member of it when it is a composite curve (102) are flagged as
parameter-space geometry (entity use 05). The geometry kernel writes these the other way round,
and the solver then refuses every patch as having non-parametric curves. Every record keeps its
80 columns and its sequence number.

## Units

The first file's length unit is kept. Every other file is scaled to it, and the record says
so. A file's unit is the one its global section's unit flag names, or its unit name when the
flag is 3. A file whose global section names a unit this package has no scale for is refused.

## Limits

- A crossing whose curve does not close on a component, such as a tailplane with an open
  trailing edge through a fin, keeps both parts: the faces inside are removed only where the
  crossings split the components into regions (see Faces inside the assembly).
- Two components that hold the same surface twice, such as two versions of one part in one
  file, are joined into faces the mesher may not finish: the faces of the second that lie on
  the first are given to the first and warned before meshing starts. Write each version to an
  IGES file of its own and grid one of them.
- A trailing edge with no base face is not found by `"auto"`.
- Entities the commands do not read: transformation matrices of named curves, and curve
  entities other than lines, B-spline curves and composite curves.

## License of the extra

gmsh is licensed under the GNU General Public License, version 2 or later. The base install
never installs or imports it, and the package does not redistribute it: it comes from its own
distribution when the `gmsh` extra is installed, and only these two commands call it. See
[install](../install.md#dependency-licenses).
