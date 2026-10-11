# RPT-164 - Zero-area faces at the shared curve of a refined level, 0.38.0 against 0.39.0 (2026-10-11)

The measurement behind FR-432 R1 to R5 (PFS-2079, GOAL-049 item S4): how many faces of a refined level fall under `ZERO_AREA_FRACTION * size**2` in the level audit (gate G1, `faces_of_zero_area`) on a private multi-component rotor panel mesh, with pyflightstream 0.38.0 and with 0.39.0. No solver run is involved; the quantity is read from the written level. The mesh stays private and only counts are published here.

## Purpose

Show, on a real multi-component mesh, that a family rebuilt at factor 1 beside a refined grid, and a family refined alone beside an unselected grid, no longer write faces of zero area at the curve the two share, and that the whole release sweep of selections keeps it so.

## Method

The mesh is a quad-dominant panel mesh of a rotor with several blades, each blade a grid family with a closing tip cap. It is not named and not shipped. Every level was written by `refine_mesh` and then audited, and the count is the `faces_of_zero_area` of the level audit (G1).

Builds measured:

| Build | Identity |
|---|---|
| 0.38.0 | the PyPI wheel |
| 0.39.0, case (a) | development tree of lane A (FR-431 and FR-432), uncommitted at the run |
| 0.39.0, case (b) | development tree before R5 (the six caps), and the release tree for the release sweep |
| 0.39.0, sweep (c) | commit `25c7b472d07f32dc4876bdc35af28e0181bdfbcb`, version 0.39.0 |

Measured on 2026-10-11.

## Results

(a) The rotor blades refined at factor 2, their tip caps rebuilt at factor 1 by remesh (FR-432 R1 to R3):

| Build | Faces under the threshold |
|---|---:|
| 0.38.0 (PyPI wheel) | 11 |
| 0.39.0 | 0 |

(b) Each tip cap refined alone at factor 2 beside its unselected blade grid (FR-432 R5):

| Build | Faces under the threshold per cap |
|---|---|
| 0.38.0 (PyPI wheel) | 5 and 9, measured on two caps |
| 0.39.0 development tree before R5 | 4 to 9, over the six caps |
| 0.39.0 | 0 on each cap |

(c) The release sweep: 56 selections, namely every family alone at factors 0.5 and 2, every grid with its neighbours unselected, and all grids together at both factors, on commit `25c7b472d07f32dc4876bdc35af28e0181bdfbcb`:

| Quantity | Value |
|---|---:|
| selections | 56 |
| levels written | 56 |
| faces of zero area in total | 0 |
| longest path written | 87 characters |

## Limits

One mesh, one element mix (quad-dominant), the area threshold of gate G1 as the only criterion; the faces' shape quality and the solver's response are not measured here. The 0.38.0 counts of case (b) come from two caps only; the range of 4 to 9 comes from the development tree. The case (a) and (b) runs of 0.39.0 were made on development trees before the release commit; the sweep (c) is the one made on the release tree.
