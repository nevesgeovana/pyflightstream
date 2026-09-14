# RPT-048: what a per-surface translation does to shared vertices, on 26.123 (2026-09-14)

**WHAT THIS SETTLES.** FR-100 moves the boundaries of an alias with one
`TRANSLATE_SURFACE_IN_FRAME` per boundary, because the command moves one
surface or all of them and nothing in between. Two surfaces of one set share
the vertices where they meet. Whether a per-surface move carries those vertices
once or once per surface is a property of the solver, not of the script, and
this round measured it.

**THE VERDICT.** Without `SPLIT_VERTICES` the shared vertices are moved once per
surface that owns them, so a two-surface set moved by `d` puts its junction at
`2d`. With `SPLIT_VERTICES ENABLE` on each surface every vertex of the set moves
exactly once, the set stays joined to itself, and a surface outside the set is
not touched. FR-100 emits `ENABLE`.

## The mesh and the build

A saved simulation of two boundaries, a wing and a body, 7252 vertices and
14266 faces, 84 vertices shared by the two boundaries (counted from the face
connectivity of its mesh block). FlightStream 26.1, build #8112026 (26.123).

The comparison reads the mesh block of the input file and of each saved file:
the vertex count line, then the X, Y and Z rows, then per face its vertex
indices and its boundary index. A face's vertices are compared with the same
face's vertices in the input, so a split vertex (a new index) is still compared
with the vertex it came from.

## Four probes: open, translate by 0.5 m along X in the reference frame, save

Each probe is a script of four or five lines (open, one or two translation
lines, save as, close), under a second of solver time.

| probe | lines | what moved | shared vertices after |
|---|---|---|---|
| all surfaces | one line, surface `0` | every face vertex of both boundaries by 0.5 | 84 |
| each surface, split | wing then body, `ENABLE` | every face vertex of both boundaries by 0.5 | 84 |
| wing alone, split | wing, `ENABLE` | the wing by 0.5; the body not at all | 0 (7336 vertices: the wing came away) |
| wing alone, no split | wing, `DISABLE` | the wing by 0.5, and 253 face vertices of the body by 0.5 | 84 |

## The first build, which emitted `DISABLE`

Four steady rows moved both boundaries, one line per boundary without the split.
The two that only translated (by 0.5 m along X, one with the moment frame
carried and one without) diverged with non-finite coefficients; their saved
meshes had 7168 vertices moved 0.5 m and the 84 shared vertices moved 1.0 m, and
the solver log reported three faces remediated, its initial face count 14263
against the control's 14266. The two that translated and then turned the set
ran to their iteration limit.

## The rerun with `ENABLE`, as a null test

The same rows with the split, against a control that moves nothing, at Mach 0.2
with mirror symmetry. Moving the whole aircraft through a uniform flow does not
change the problem, and turning it by +2 degrees about the moment point's Y axis
with the flow at the angle of attack less 2 degrees is the control again (the
sign measured by RPT-047).

| row | against the control | worst gap |
|---|---|---|
| moved 0.5 m along X, the moment frame carried | all nine coefficients | 0, to every printed digit; same iterations and residual |
| moved 0.5 m along X and -0.2 m along Z, then turned 2 degrees, flow turned back | CL, CDi, CDo | 3.3e-06 |
| the same geometry with the flow 2 degrees the other way | CL, CDi, CDo | differs, by 0.35 in CL (the control that must differ) |
| moved 0.5 m along X, the moment frame LEFT behind | the six force coefficients | 0 |
| the same row | the change in CMy against -(dx/c) Cz | 1.6e-05 (the wrong direction would be off by 0.22, a double move by 0.11) |

All five rows converged. The last row is the one that has the translation's
DIRECTION in it: the other rows are invariant under a move in the wrong
direction too.

## What this does NOT say

- A rotor alias moved on an unsteady row was not run. That its motion then spins
  about the moved hub follows from the frames the script moves, and is not
  measured here.
- The wing moved alone was a geometry probe with no solve. Whether a part that
  has come away from what it touched is an acceptable model is the study's call.
- Only build 26.123 was run. The command has the same grammar on every
  registered build and the split has not been measured on the others.
- The scripts and the comparison are not in this tree; the procedure above is
  complete enough to repeat on any two-boundary mesh.
