# Mesh inputs and GUI-only operations

Policy page: what the library supports when a workflow step exists in
the FlightStream GUI but has no scripting command, and which mesh
inputs are canonical. Adopted 2026-07-23 (PLN-028).

## The gap this page closes

The FlightStream scripting interface covers a subset of what the GUI
can do. The command database only ever contains commands the manual
documents, or that a committed probe report measured the solver accepting
(each entry carries one citation or the other), so a workflow step
with no script command cannot be emitted by the script builder, and
no amount of library code changes that. Geometry preparation and
meshing are the common case, and the picture there changed on
2026-08-06 through 2026-08-08, when the sweep finished: every command
the eight editions registered at that date documented entered the
database, so the CAD, CAD Create and Mesh Operations chapters are
emittable in full, and the last of those is this page's own subject,
everything that translates, rotates, scales, mirrors, copies, cuts,
selects or deletes a surface between import and solver initialization.
The mesh-wrapper chapter is in too, as of 2026-08-08.

**Read the scope of that claim, because a ninth edition has arrived
since.** It is a statement about the eight editions swept in August 2026
and it is not a standing promise about every edition the vendor will
ever publish. SRS non-requirement NREQ-05 excluded nothing at the close
of that sweep; registering 26.123 on 2026-08-17 opened exactly one
exception, `SET_OUTLET_TRAILING_EDGES`, which the SRC-751 edition
documents and this database does not yet carry. That command belongs to
the boundary conditions rather than to meshing, so this page's own subject is
unaffected, and the debt is listed in the SRS evidence queue. What has
NOT changed is the reason this page
exists. A command being in the database means the script builder will
emit and validate it; it does not mean the GUI-driven parts of geometry
preparation have a scripted equivalent, and the pattern below is still
the supported one.

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
hashes in the run manifest (`inputs_sha256`), so every run names
exactly which saved file it consumed.

### What that content hash is, and what it leaves out

Stated here because this page is where a user is told to trust it, and
a checksum whose rule is unstated cannot settle the question it exists
for: two people holding what they believe is the same input file must
be able to tell whether they really do.

**The algorithm is sha256, and there is no other.** Every digest this
library writes into a manifest comes from `pyflightstream._digest`,
which holds the algorithm as a value rather than as a sentence, so a
tier 1 test spends it and a second algorithm cannot arrive quietly.

**The canonical form is the raw bytes of the staged file**, read in
blocks and never decoded. One manifest field is not a file digest and
is named here so the rule is not over-read: `recipe_sha256` records the
recipe function's SOURCE, and a source text is hashed as its UTF-8
encoding, which is the second canonical form `pyflightstream._digest`
states.

**Nothing around the file enters the digest.** Not the path it was
staged from, not the file name, not its modification time, not the
machine or the user that staged it, and not the order the inputs were
staged in. Those are exactly the fields that differ between two runs
which are otherwise the same run, so admitting one would make the
manifest report two identical runs as different. They are absent by
construction rather than by filtering: the digest reads bytes and
reads nothing else.

Read the consequence for a text mesh, because it is the one that
surprises. An OBJ is bytes like anything else, so the same mesh
checked out with CRLF line endings on one machine and LF on another is
two different files carrying two different digests. That is the digest
being correct about the file rather than wrong about the content: the
solver reads the file, not an idea of it. A `.fsm` artifact is binary
and has no such ambiguity, which is a further reason the pattern above
treats it as immutable. Where a comparison has to survive a
line-ending change, compare the parsed geometry rather than the
manifest digest.

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
