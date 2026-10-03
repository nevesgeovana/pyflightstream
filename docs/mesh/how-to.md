# Mesh inputs and GUI-only operations

This page is for a user who brings a mesh to a run. Two inputs are canonical,
and a workflow row takes both:

* a raw surface mesh, an `.obj` or an `.stl`, which the script IMPORTS through
  the mesh-import family, with OBJ as the reference format; and
* a saved simulation, a `.fsm`, which the script OPENS, made once in the
  FlightStream GUI when a step has no scripting command.

This page walks through preparing a raw mesh or a saved simulation. The
[reference](reference.md) defines their sidecars, build support and measured
limits; [the complete example](example.md#a-complete-example-a-wing-obj-with-its-trailing-edge-by-file)
provides a wing OBJ setup to copy.

A workflow row imports `.obj` and `.stl` and opens `.fsm`. Explicit IGES
conversion is a separate route described in the [reference](reference.md); STEP remains refused. A
recipe of your own reaches every format the mesh-import family documents;
the other formats `IMPORT` documents stay there, because what the solver
makes of their surfaces' names and order is unmeasured.

## Starting from an OBJ or STL

A mesh file carries surfaces and nothing else: no length unit, no name this
package reads, no trailing edge. So everything a run needs to know about it is
written in one file beside it, `<stem>.boundaries.toml` (`wing.boundaries.toml`
beside `wing.obj`), and every row that names the mesh shares it. The row names
the mesh as it names any geometry, `wing.obj` in its `GEOMETRY` column.

The sidecar says, in this order:

1. `boundaries`: the names of the mesh's surfaces, in the order the solver
   numbers them, which the plan writes for an `.obj` from its groups when it
   has no sidecar;
2. `[import]`: `units`, the length unit the file is written in;
3. `[[import.operations]]`: the operations that make the file into the body,
   when it is not the body yet;
4. `[trailing_edges]`: how the trailing edge is marked, by a points file (the
   default), by detection, or explicitly absent with `none = true`;
5. `[wake_termination]` and `[base_regions]`: two detections, each applied
   only when written.

The [reference](reference.md) describes each sidecar field, build support and
measured limits. The next section shows how to write the points file.

### Writing a points file from a blade's mesh

`pyflightstream.workspace.trailing_edge_midpoints` reads a blade surface and
returns the mid-point of every mesh edge on its trailing edge, in order along
the span, and `write_trailing_edge_node_file` writes them as the blade's
points file. The points come back in the MESH's own reference frame and length
units, because they are mid-points of mesh edges and nothing transforms them.
The rotor axis and hub you pass in are what the CRITERION is computed in, not
what the output is expressed in. The file it writes is the file a
`[trailing_edges]` table names, `file = "blade.te.txt"`, and a row naming the
blade then marks exactly these edges.

<!-- skip: next -->
```python
from pyflightstream.workspace import write_trailing_edge_node_file

write_trailing_edge_node_file(
    "blade.obj", "blade.te.txt", axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), unit="METER"
)
```

That block is skipped by the executable-examples run, because it names a
blade mesh and this repository commits no blade. The name it imports is
checked all the same: `tests/tier1_offline/test_mesh_inputs_page.py` resolves
every name a python block on this page imports, so a rename fails the suite
rather than leaving the block stale.

The vertices and the faces are read. The mesh need not be watertight and no
proximity query is made, so this runs on a base install with no extra.
`extract_trailing_edge` still returns one aftmost vertex per section, and
`TrailingEdge.write_node_file` refuses: a list of vertices marks nothing.

**THE CRITERION IS NOT A CREASE, and that is the whole point.** The obvious
implementation is a dihedral-angle threshold over face adjacency, which every
mesh library offers. This package refuses it, because marking wake edges from a
file exists precisely BECAUSE the solver's own auto-detection is an angle
criterion, and a strongly twisted blade has a trailing edge that is not a
crease. Building the extraction on adjacency angles would reimplement in Python
the criterion the capability was created to escape, and a campaign would gain a
different threshold rather than a different capability.

What is computed instead: a vertex's spanwise coordinate is its radial distance
from the rotor axis, the vertices are binned into chordwise sections by that
coordinate, and each section contributes its AFTMOST point, with the chordwise
direction taken from the section's own extent. The trailing edge between two
sections is the shortest chain of mesh edges joining their aftmost points,
along edges that are the aft ridge of both their faces: the far vertex of each
face lies forward of the edge, forward meaning against the section's aft chord.
The chain continues past the first and last section while exactly one such edge
leads outward, and each edge of it gives one mid-point. No angle is compared
with a threshold. A blunt trailing edge, two aft corners at each station, is
refused rather than guessed. The reasoning, and the alternatives that were
rejected, are in the design note `DD-27`.

An OBJ file's named group for the trailing edge would have been the preferred
route and was measured and dropped: the mesh library this package reads the
mesh through does not surface OBJ group names, so a blade exported with its
trailing edge already named as a group offers nothing that library can see.
The groups ARE read for the SURFACE NAMES from the file's own text
(G30, RPT-078: `IMPORT` makes one boundary per group holding a face, in file
order).

## The saved simulation: GUI once, script everything after

### The gap this route closes

See [Saved simulation](../continuation-recovery.md#saved-simulation) for the reason this route exists.

### The supported pattern

When a step is GUI-only, the supported workflow is:

1. Perform the GUI-only procedure interactively, once: import the geometry,
   run the manual meshing or repair step, configure what has no command.
2. Save the result as a `.fsm` simulation file. That file is now an input
   artifact: store it in the campaign workspace input library under
   `inputs/`, selected by id like any other artifact, and treat it as
   immutable (redo the GUI step, save a new artifact, never edit in place).
3. Everything downstream stays scripted: scripts `OPEN` the saved `.fsm`,
   `declare_existing` tells the builder which entities (boundaries, frames,
   actuators, motions) the file already contains so index and label checks
   keep working, and solver setup, sweeps, and exports run reproducibly on
   top.

The GUI step itself is the one part the library cannot replay; the saved
`.fsm` is its record. The workspace stages inputs with content hashes following
[`pyflightstream._digest`'s sha256 rule](reference.md#what-that-content-hash-is-and-what-it-leaves-out)
in the run manifest (`inputs_sha256`), so every run names exactly which saved file it
consumed. This policy dates from 2026-07-23.

When a mesh exists only inside a `.fsm`, the pre-processing export
(`run.export_surface_mesh`) produces the OBJ counterpart through a solver run,
which is how the geometry gate of the probe planner gets its watertight
surface.
