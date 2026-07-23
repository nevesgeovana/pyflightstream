# Mesh inputs and GUI-only operations

Policy page: what the library supports when a workflow step exists in
the FlightStream GUI but has no scripting command, and which mesh
inputs are canonical. Adopted 2026-07-23 (PLN-028).

## The gap this page closes

The FlightStream scripting interface covers a subset of what the GUI
can do. The command database only ever contains commands the manual
documents (each entry carries its page citation), so a workflow step
with no script command cannot be emitted by the script builder, and
no amount of library code changes that. Geometry preparation and
meshing are the common case: the CAD and mesh-wrapper chapters are
currently outside the database scope (SRS non-requirement NREQ-05).

## The supported pattern: GUI once, script everything after

When a step is GUI-only, the supported workflow is:

1. Perform the GUI-only procedure interactively, once: import the
   geometry, run the manual meshing or repair step, configure what
   has no command.
2. Save the result as a `.fsm` simulation file. That file is now an
   input artifact: store it in the campaign workspace input library
   under `inputs/`, selected by id like any other artifact, and treat
   it as immutable (redo the GUI step, save a new artifact, never
   edit in place).
3. Everything downstream stays scripted: scripts `OPEN` the saved
   `.fsm`, `declare_existing` tells the builder which entities
   (boundaries, frames, actuators, motions) the file already
   contains so index and label checks keep working, and solver
   setup, sweeps, and exports run reproducibly on top.

The GUI step itself is the one part the library cannot replay; the
saved `.fsm` is its record. The workspace stages inputs with content
hashes in the run manifest, so every run names exactly which saved
file it consumed.

## Canonical mesh inputs

Two input routes are canonical:

* Geometry meshed inside FlightStream, carried as a saved `.fsm`
  artifact (the pattern above).
* A direct surface mesh imported by script through the mesh-import
  family, with OBJ as the reference format.

When a mesh exists only inside a `.fsm`, the pre-processing export
(`run.export_surface_mesh`) produces the OBJ counterpart through a
solver run, which is how the geometry gate of the probe planner gets
its watertight surface.

## Mesh format policy

The library's mesh seam is deliberately narrow: OBJ in and out, with
geometric validity (watertightness, containment queries) owned by the
`[geom]` extra on trimesh. Two standing decisions bound any widening:

* More formats never enter through raw third-party APIs. If a
  workflow needs formats beyond OBJ, meshio joins the `[geom]` extra
  as a conversion backend behind a project-owned adapter (decision
  D8, 2026-07-23): the adapter exposes only what the workflow needs,
  a license evidence card is committed at adoption time like every
  dependency, and validity checks stay with trimesh.
* Until that need materializes, converting external formats to OBJ
  with your own tooling is the supported route.

## What this policy is not

It is not a promise to wrap the GUI. Steps stay GUI-only until the
solver's scripting interface documents a command for them; when that
happens, the command enters the database with its citation and the
step graduates from this page to the reference.
