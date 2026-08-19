# RPT-031: the search for the command that sets the coupling tolerance (2026-08-19)

The 26.123 edition documents something no earlier edition did: the
coupling loop has a stopping test of its own. It monitors how far the
structural nodes moved between one coupling pass and the next, reduced
to a single root-mean-square figure, and it stops when that figure
reaches a tolerance the page attributes to the runtime settings
(SRC-751 p.277).

The page names the tolerance and names no command that sets it. That gap
is recorded in the chapter header of
`src/pyflightstream/commands/aeroelastic_coupling.yaml`, which says a
search of this edition's scripting reference and its Script Index is what
would close it. This report is that search.

**The answer is NOT FOUND, and no command entry was added.** Nothing in
this repository claims a command sets this tolerance.

## What was read

Two page ranges of SRC-751, the 26.123 edition, as its own registry entry
in `commands/_meta.yaml` declares them:

* pp.283-383, the scripting reference chapter;
* pp.384-390, its Script Index.

Read with `pyflightstream.utils.manual.read_pdf_pages`. This is a
READING and not a run: no solver was started and no licensed seat was
spent. The manual is licensed vendor material, lives in `_private/` and
never enters Git (CLAUDE.md invariant 1); everything below is paraphrase
with a page citation.

Every page of both ranges was scanned for nine tokens: COUPLING,
AEROELASTIC, RMS, TOLERANCE, CONVERGENCE, DISPLACEMENT, STRUCTURAL,
MODAL and FSI. The pages that carry any of them are pp.283, 288, 293,
311, 323, 326, 340, 341, 344, 346, 349, 352, 355, 382, 383, 384, 385,
387, 388, 389 and 390. Every command name on those pages was read; the
candidates are below with the reason each was rejected.

## The Aeroelastic Coupling Toolbox in this edition

The chapter documents eleven commands, at pp.382-383: run the analysis,
assign the boundaries, assign the coordinate systems, import and delete
the structural nodes, set the working directory, set the post-processing
script, set the structural execution command, set the number of
iterations, enable coupling inside an unsteady run, and choose the RBF
mesh-morphing kernel.

**Not one of them takes a tolerance, a threshold or a residual.** Every
argument in the family is a count, an index, a path, a file name, an
enable-or-disable, or a kernel name.

All eleven are carried by this database. Ten sit in
`commands/aeroelastic_coupling.yaml` and `AEROELASTIC_RBF_TYPE` sits in
`commands/advanced_settings.yaml`, which is worth one sentence so a
reader counting one file does not report a missing command.

## Candidates rejected, with the reason for each

**SOLVER_SET_CONVERGENCE** (body p.344, index p.388). The nearest
candidate and the one the chapter header already names. It takes a
threshold, and the block that documents it carries no parameter table at
all: the page that names the command says nothing about which residual
the threshold governs. The page that describes the setting does say, and
it is not this one. In THIS edition, p.200 defines the convergence
threshold as the level the surface pressure and velocity residuals must
fall below, names those two as the criteria used, and adds that the
supersonic solver uses pressure residuals and the hypersonic solver
needs no residual check. The FSI nodal-displacement RMS residual of
p.277 is a different quantity. The database's own note on the entry
scopes it the same way against SRC-003 p.200, so this reading confirms
that note on the newer edition rather than resting on it. Mapping this
command to the coupling tolerance would be an inference, and an
inference recorded as evidence is what invariant 3 exists to prevent.

**SET_SOLVER_CONVERGENCE_ITERATIONS** (body p.349, index p.384). Sets how
many iterations the solver must run AFTER crossing the convergence
threshold before it declares convergence. A count, and it qualifies the
flow-solver threshold above rather than the coupling loop.

**SET_AEROELASTIC_ITERATIONS** (body p.383, index p.384). A number of
coupling iterations: an upper bound on how many passes may run, not the
tolerance that ends them early. The p.277 text describes exactly this
pair working together, iterations bounded from above and terminated from
below by a residual, and only the upper bound has a command.

**SET_AEROELASTIC_COUPLING_IN_UNSTEADY** (body p.383, index p.384).
Enable or disable. It decides whether the loop runs inside an unsteady
simulation, not when it stops.

**AEROELASTIC_RBF_TYPE** (body p.383, index p.384). Chooses the radial
basis function used to morph the surface grid from the node
displacements. It shapes how a displacement is applied, not how small a
displacement has to become.

**SET_SOLVER_VISCOUS_COUPLING** (body p.346, index p.390). Matched the
COUPLING token and is a different mechanism entirely: the coupling
between the potential-flow solution and the boundary-layer model. It
takes enable or disable.

**SET_MOTION_FSI_EXECUTABLE** and **SET_MOTION_FSI_STRUCTURAL_NODES**
(body pp.340-341, index p.387). The motion chapter's FSI pair, which name
an external executable and the structural node set for a motion
definition. Neither takes a tolerance. They are also the pair the WP1 dry
run found unrecognised by build 7012026, recorded in the chapter header of
`commands/aeroelastic_coupling.yaml`.

**SET_VERTEX_MERGE_TOLERANCE** (body p.288, index p.389),
**SET_CAD_CREATE_MERGE_TOLERANCE** (body p.293, index p.385) and the
TOLERANCE argument of **IMPORT_WAKE_EDGES_FROM_FILE** (body p.323).
Matched the TOLERANCE token and are geometric: a distance below which two
vertices, two CAD entities or a mesh edge and a wake edge are treated as
one. A length, not a residual.

## The Script Index adds nothing here

The registry note for this edition records that its Script Index
OVER-reports, listing at least one command the chapter body no longer
documents, so the body is the authority. For this question the two agree:
the index at p.384 lists the same eleven aeroelastic names the body
documents at pp.382-383 and no twelfth, so nothing was found in the index
that the body does not carry.

## The modal-representation claim is uncorroborated by any edition

The chapter header names a second claim, that the internal loop can drive
a modal structural representation with no external structural solver, and
records it as coming from delivery correspondence rather than from a
document. This report measures that rather than repeating it.

The words `modal` and `mode shape` were searched for in every page of
every manual edition this repository holds locally, plus the two vendor
release-notes pdfs: SRC-003 (410 pages), SRC-725 (409), SRC-740 (413),
SRC-741 (396), SRC-747 (360), SRC-748 (361), SRC-749 (342), SRC-750 (417),
SRC-751 (417), SRC-172 (5) and SRC-215 (7).

**Zero occurrences, in all eleven documents.** The only related word
anywhere is `Eigen-vector` on p.247 of both 26.12 editions, describing how
attachment-line faces are detected from the local velocity field, which is
a flow-feature detector and has nothing to do with structural dynamics.

So the claim is not merely unstated in the 26.123 edition; no edition this
repository can read states it, and nothing here should be written as
though a primary document supported it.

## What follows from this report

* No command entry is added, and no version note is written, because
  nothing on a page inside pp.283-383 names a command that sets this
  tolerance. NOT FOUND adds no entry.
* The chapter header's sentence saying that a search is what would close
  the gap is now answered and should cite this report instead of asking
  for the search again. That edit belongs to the file that holds the
  header.
* The gap itself stands and is a fact about the document rather than
  about the solver: the tolerance exists, the solver applies it, and this
  edition does not say how a script sets it. A probe on a licensed
  machine is what could turn that into a measurement, and this reading
  cost no seat, so nothing here consumes the budget such a probe would
  need.
