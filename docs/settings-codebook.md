# The numeric settings codebook

This page is the CONTRACT for the optional all-numeric settings table
that `pyflightstream.post.settings_table` writes. It is not a
description of the code: `tests/test_settings_codebook.py` reads this
page and fails when the library disagrees with it, so the two cannot
drift. That direction matters. If the only thing holding the encoding
still were a page describing the code, they would part the first time a
flag gained a state, and every file written in between would be misread
from then on.

The current codebook version is 1. Every file names it, in a column of
its own, and a reader meeting another version refuses the file rather
than reinterpreting it: an id that moved makes every row describe a
different flag.

## What this file is for, and what it is not

The settings record beside every post-processing file (PFS-2012.11)
holds strings, citations and mixed types, because it is the RECORD. A
plotting script or a spreadsheet cannot treat that as data, so this
second form carries nothing but numbers.

It is LOSSY by construction and therefore optional. It never replaces
the full record: a boundary selection contributes its length and
nothing else, and a mapping contributes its entry count. The kinds that
lose information are named in the file's own legend, written beside it
as `<name>.codebook.json`, so the pair is readable without this page.

## Why unknown is a code and not a number

Across the sixty-five flags of a bare snapshot on 26.120 the value
field holds five Python types: fifty-seven absent, two integers, four
floats, one token and one list. One column cannot carry that and stay
numeric.

A sentinel may only appear in a column whose domain we control. The
code columns below are assigned here, densely from 1, so 999 is free in
them by construction. The value columns are not ours: they carry
iteration counts, angles and boundary indices, any of which can
legitimately be 999, and read back a filled cell and a real setting
equal to the fill are the same bytes. So an unknown flag is written as
the provenance code `3` with the value columns EMPTY, and a caller may
ask for empty CODE cells to be filled; asking to fill a value column is
refused, naming the flags whose legal range contains the fill.

## Columns

The tidy form, one row per run and flag:

`codebook_version`, `run_index`, `flag_id`, `provenance_code`, `emitted`, `value_kind`, `value_num`, `value_code`, `value_count`

The wide form gives one row per run, and each flag contributes
`f<id>_value` and `f<id>_prov`. Two columns are enough there and three
are needed in the tidy form for a structural reason: a per-flag column
is monomorphic, so `f15_value` always holds an enumeration code and
`f11_value` always holds an iteration count, whereas one shared value
column would hold both.

Column ORDER is documented and not guaranteed. A reader resolves a
column by its label (the author's convention of 2026-08-17, NFR-19).

## Provenance codes

| code | provenance |
| --- | --- |
| 1 | explicit |
| 2 | default |
| 3 | unknown |

## Value kind codes

| code | kind |
| --- | --- |
| 1 | bool |
| 2 | int |
| 3 | float |
| 4 | enumerated |
| 5 | list |
| 6 | mapping |

The kinds that lose information in this form are `list` and `mapping`.

## Per-flag enumerations

Coded per flag rather than globally, which is what lets a reader tell
that 999 is the sentinel here and a value there. A token this table
does not carry is REFUSED at write time rather than given a code.

| flag | code | token |
| --- | --- | --- |
| AEROELASTIC_RBF_TYPE | 1 | WENDLAND_C2 |
| AEROELASTIC_RBF_TYPE | 2 | GAUSSIAN |
| AEROELASTIC_RBF_TYPE | 3 | THIN_PLATE_SPLINE |
| AEROELASTIC_RBF_TYPE | 4 | MULTI_QUADRATIC |
| AEROELASTIC_RBF_TYPE | 5 | INV_MULTI_QUADRATIC |
| DELETE_SEPARATION | 1 | all |
| SET_AXIAL_SEPARATION_BOUNDARIES | 1 | all |
| SET_BOUNDARY_LAYER_TYPE | 1 | LAMINAR |
| SET_BOUNDARY_LAYER_TYPE | 2 | TRANSITIONAL |
| SET_BOUNDARY_LAYER_TYPE | 3 | TURBULENT |
| SET_CROSSFLOW_SEPARATION_BOUNDARIES | 1 | all |
| SET_SOLVER_MODEL | 1 | INCOMPRESSIBLE |
| SET_SOLVER_MODEL | 2 | SUBSONIC |
| SET_SOLVER_MODEL | 3 | TRANSONIC |
| SET_SOLVER_MODEL | 4 | LOW_ORDER_SUPERSONIC |
| SET_THIN_BOUNDARIES | 1 | all |
| SET_VALAREZO_SEPARATION_BOUNDARIES | 1 | all |
| SET_VISCOUS_EXCLUDED_BOUNDARIES | 1 | all |
| SET_VORTICITY_DRAG_BOUNDARIES | 1 | all |

## Flag ids

Appended, never derived. `FLAG_SPECS` grows whenever a registered build
adds a settings command, and it grows in the middle, because its order
is the emission order of the curated helper rather than an arrival
order. An id read off a position there would renumber half this table
on the next build, so the order is frozen and a new flag takes the next
unused id in the same commit that moves this page.

| id | flag |
| --- | --- |
| 1 | SET_SOLVER_STEADY |
| 2 | SET_SOLVER_UNSTEADY |
| 3 | SOLVER_SET_AOA |
| 4 | SOLVER_SET_SIDESLIP |
| 5 | SOLVER_SET_VELOCITY |
| 6 | SOLVER_SET_MACH_NUMBER |
| 7 | SOLVER_SET_REF_VELOCITY |
| 8 | SOLVER_SET_REF_MACH_NUMBER |
| 9 | SOLVER_SET_REF_AREA |
| 10 | SOLVER_SET_REF_LENGTH |
| 11 | SOLVER_SET_ITERATIONS |
| 12 | SOLVER_SET_CONVERGENCE |
| 13 | SET_MAX_PARALLEL_THREADS |
| 14 | SOLVER_SET_FORCED_ITERATIONS |
| 15 | SET_BOUNDARY_LAYER_TYPE |
| 16 | SET_SOLVER_VISCOUS_COUPLING |
| 17 | SET_VISCOUS_EXCLUDED_BOUNDARIES |
| 18 | DELETE_VISCOUS_EXCLUDED_BOUNDARIES |
| 19 | SET_SURFACE_ROUGHNESS |
| 20 | SET_THIN_BOUNDARIES |
| 21 | DELETE_THIN_BOUNDARIES |
| 22 | CREATE_BULK_SEPARATION |
| 23 | KUTTA_JOUKOWSKI_LIFT_FORCES |
| 24 | PRINT_ROTOR_INDUCED_VELOCITIES |
| 25 | SET_ADAPTIVE_FIELD_GRID_REFINEMENT |
| 26 | SET_JET_WAKE_FILAMENTS_GRID_INDUCTION |
| 27 | ROTOR_INDUCED_VELOCITY_BLENDING |
| 28 | SET_WAKE_NUMERICAL_RELAXATION |
| 29 | SET_JET_WAKE_DECAY_NORMALIZED_LENGTH |
| 30 | SET_WAKE_DECAY_CONSTANT |
| 31 | SOLVER_STABILIZATION |
| 32 | DISABLE_SOLVER_REF_VELOCITY |
| 33 | SET_SOLVER_MODEL |
| 34 | VALAREZO_CRITERION |
| 35 | SET_CROSSFLOW_SEPARATION_CP |
| 36 | SET_WAKE_RELAXATION |
| 37 | SET_WAKE_STREAMWISE_AGGLOMERATION |
| 38 | SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER |
| 39 | SOLVER_VORTEX_RING_NORMALIZATION |
| 40 | DELETE_SEPARATION |
| 41 | CREATE_AIRFOIL_SEPARATION |
| 42 | CREATE_AXIAL_VORTEX_SEPARATION |
| 43 | CREATE_CYLINDRICAL_BULK_SEPARATION |
| 44 | CREATE_STRATFORD_BULK_SEPARATION |
| 45 | SET_AXIAL_SEPARATION_BOUNDARIES |
| 46 | DELETE_AXIAL_SEPARATION_BOUNDARIES |
| 47 | SET_VALAREZO_SEPARATION_BOUNDARIES |
| 48 | DELETE_VALAREZO_SEPARATION_BOUNDARIES |
| 49 | DELETE_VALAREZO_CRITERION_BOUNDARIES |
| 50 | SET_CROSSFLOW_SEPARATION_BOUNDARIES |
| 51 | DELETE_CROSSFLOW_SEPARATION_BOUNDARIES |
| 52 | SET_CROSSFLOW_SEPARATION_DIAMETER |
| 53 | SET_CROSSFLOW_SEPARATION_AXISYMMETRIC |
| 54 | LAMINAR_SEPARATION |
| 55 | SET_SOLVER_CONVERGENCE_ITERATIONS |
| 56 | SOLVER_MINIMUM_CP |
| 57 | REYNOLDS_AVERAGED_DRAG_FORCES |
| 58 | SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY |
| 59 | SOLVER_SET_FARFIELD_LAYERS |
| 60 | SOLVER_UNSTEADY_PRESSURE_AND_KUTTA |
| 61 | SET_WAKE_TERMINATION_TIME_STEPS |
| 62 | SET_WAKE_ON_WAKE_INDUCTION |
| 63 | ADDITIONAL_WAKE_RELAXATION_ITERATION |
| 64 | AEROELASTIC_RBF_TYPE |
| 65 | SET_VORTICITY_DRAG_BOUNDARIES |
