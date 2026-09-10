# RPT-041: her three master's cases against the 0.15.0 wheel

Date: 2026-09-10. Arm 4 of GOAL-014. Build 26.120, the build her recorded
campaign ran on. Wheel `pyflightstream-0.15.0.dev0-py3-none-any.whl`, built
from `eae10ec`, which is the reviewed tree before the tag.

The machine-readable comparison is `reports/master-cases-0150.json`, which
the goal's `hercases` arm reads and RE-MEASURES; it reads no verdict this
report or that file states about itself.

## The question this seat run answered

Do her three cases produce the same coefficients under 0.15.0 as under the
recorded campaign, given that this release rewrites the emitted script in
five places at once: the matrix layout (thirteen columns, `SWEEP_TYPE`
folded into the condition, her row 9001's paired `AL/BE` converted), the
reference vocabulary (`[aliases]`, `[[frames]]` and engine blocks moving
from the setup preset to the reference), the rotor identity (a motion names
its rotor by alias), the post-processing artifact (the frame decides how an
entry expands) and the reductions (per rotor, each over its own passage)?

Nothing cheaper answers it. Each of those changes rewrites the script the
solver reads. A fixture proves the package emits what the package intends
and a golden proves the bytes have not moved; neither says whether a script
this release now writes produces the same NUMBERS.

## What it cost

Four points on 26.120: rows 5207 (two incidences), 5224 and 5901 of
`pfs0150-repro`, which are her 3207, 3224 and 9001 upgraded. No point was
spent on 26.123, because the question is about the PACKAGE and the solver
must be held constant; the cross-build comparison is `pfs0140`'s rows 5307,
5324 and 5903, which already ran.

## The run identities are unchanged, and that was checked BEFORE the run

The point tag ends every `run_id`, so an upgrade that renamed a run would
cost her every recorded seat. Planned against `pfs0140/runs.json` for the
same three rows, before anything was spent:

| identity | 0.14.0 | 0.15.0 |
|---|---|---|
| `sim_5207/a-02.0` | yes | yes |
| `sim_5207/a+00.0` | yes | yes |
| `sim_5224/a+00.0` | yes | yes |
| `sim_5901/a+00.0_b+00.0` | yes | yes |

Identical in both, the paired row included: `a+00.0_b+00.0` keeps the held
sideslip in the tag after `SWEEP_TYPE` was folded away, which is what
`SweepAxis.held` was built for and what FR-69 promises.

## The result

**0.15.0 reproduces the 0.14.0 run EXACTLY.** Every coefficient of every
point and every residual, to the last printed digit, on all four points. The
emitted script for the rotor case is byte for byte the 0.14.0 script, the
staged geometry path apart. This release moved no number.

Against her 0.11.0 record, measured over nine coefficients per point:

| case | max delta from her record | at | status |
|---|---|---|---|
| 3207 steady wing-body, both points | 0.000e+00 | every coefficient | CONVERGED, COMPLETED_MAX_ITER |
| 3224 unsteady wing-body | 2.000e-07 | `a+00.0.CMx` | COMPLETED_MAX_ITER |
| 9001 isolated propeller B45 | 5.640e-05 | `a+00.0_b+00.0.Cz` | CONVERGED |

Every status matches her record's, point for point, and the residual pair
for 9001 is the one already recorded: 7.5929024e-06 against 7.5929667e-06.

## The band, and why it is not a new one

Her instruction is that every coefficient match the pfs0110 record "within
the band that workspace already records", and that a difference "is a
finding and not a new band".

That band is recorded per case in `pfs0131/README.md`, from the
reproduction that ran on the published 0.13.1: 3207 identical to every
printed decimal; 3224 max delta 2e-7, the last printed digit; 9001 max
delta 5.6e-5 at Cz and CL, with that same residual pair. Her sentence
beside it: "the steady row to the digit, the unsteady wing to the last
digit, and the rotor within the solver's own run-to-run band (the residual
differs in the fifth digit; the 0.11.0 repeatability control of GOAL-011
measured the same class)".

The three deltas measured here are that table, case for case, including
which coefficient carries the maximum.

**ONE DECISION IN THIS REPORT IS MINE AND IS THE ONE TO CHECK.** Her table
is written to two significant figures: it says 5.6e-5 where the delta it
describes is 5.640e-5, on the very coefficient it names. Read as a literal
threshold it fails the measurement it was written from, and rounding it up
to 5.65e-5 or 5.7e-5 would be me choosing a number, which is the widening
she forbids. So the band of each coefficient in the JSON is that
coefficient's OWN recorded delta, `abs(0.14.0 - 0.11.0)`, at full printed
precision from the 0.14.0 reproduction of the same three rows.

The criterion that makes is exactly what arm 4 is for: **this release moves
no coefficient further from her record than the last release already
stood.** A coefficient the two releases agree on carries a band of zero and
must match her record exactly, which is what all eighteen of the steady
row's do. It is measured rather than chosen, and a regression of any size
fails it.

## Two things this report does NOT claim

It does not claim the 0.11.0 to 0.14.0 deltas are acceptable. They are hers,
they were characterized at 0.13.1, and nothing here revisits them; what is
shown is that 0.15.0 adds nothing to them.

It does not claim the solver is deterministic for the rotor case. Her own
note says the residual differs in the fifth digit and that the 0.11.0
repeatability control measured the same class, so the rotor's run-to-run
behaviour is a property of the solver on this build and not of this package.

## Where it ran

`GeoverseResearch/tools/fts_workspace/pfs0150-repro`, a sibling workspace,
and NOT in `pfs0150` as item 8 of the goal says. `pfs0150` is her live use
case with an uncommitted README, and mixing four reproduction sims into it
seemed worse than the deviation. The workspace, its matrix and its
comparison script are outside git, with her geometries; only this report and
the JSON are committed. If she wants it inside `pfs0150`, the run moves and
nothing else changes.

`pfs0110` was read and not written.
