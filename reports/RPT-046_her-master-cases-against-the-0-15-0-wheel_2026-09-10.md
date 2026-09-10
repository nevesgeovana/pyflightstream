# RPT-046: her three master's cases against the 0.15.0 wheel

Date: 2026-09-10. Arm 4 of GOAL-014. Build 26.120, the build her recorded
campaign ran on. Wheel `pyflightstream-0.15.0.dev0-py3-none-any.whl`, built
from `eae10ec`, the reviewed tree before the tag.

The machine-readable comparison is `reports/master-cases-0150.json`, which
the goal's `hercases` arm reads and re-measures from its numbers.

**This report was reviewed by the verification lens before it was pushed, and
six of its findings changed it.** What that pass corrected is recorded in the
last section, because a report whose first version claimed more than its data
supported should say so rather than quietly read as though it had not.

## Three tables, and which two this compares

The distinction below is the one the first version of this report blurred,
and it is worth the space because every number here depends on it.

1. **Her master's campaign.** Her own scripts, before this package existed.
   Its numbers survive in `RPT-040`'s `recorded` column and nowhere else in
   this repository.
2. **The pfs0110 table**, `pfs0110/post/campaign_sweep.csv`, stamped
   `package_version 0.11.0` in every row. This is pyflightstream 0.11.0
   driving the same build through the workflow. It is `RPT-040`'s
   `reproduced` column, and it is what "the pfs0110 record" names.
3. **This run**, pyflightstream 0.15.0 on the same build.

**This report compares 3 against 2.** It does not compare against 1, and
where it says "the record" it means the pfs0110 table.

`RPT-040` already measured 1 against 2 and found them identical on every
selected point EXCEPT 3207 at zero incidence, where it reports a difference
of up to 0.0025969 at `Total.Cz` and states plainly that the difference is
"reported, not bound by the band", because her point was warm-started from
the previous angle and the workflow runs it cold. **That difference is still
there and this report does not revisit it.** A reader who wants her
campaign's own numbers for that point must read `RPT-040`.

## The question this seat run answered

Do her three cases produce the same coefficients under 0.15.0 as under the
pfs0110 table, given that this release rewrites the emitted script in five
places at once: the matrix layout (thirteen columns, `SWEEP_TYPE` folded into
the condition, her row 9001's paired `AL/BE` converted), the reference
vocabulary (`[aliases]`, `[[frames]]` and engine blocks moving from the setup
preset to the reference), the rotor identity (a motion names its rotor by
alias), the post-processing artifact (the frame decides how an entry expands)
and the reductions (per rotor, each over its own passage)?

Nothing cheaper answers it. Each of those changes rewrites the script the
solver reads. A fixture proves the package emits what the package intends and
a golden proves the bytes have not moved; neither says whether a script this
release now writes produces the same NUMBERS.

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

**0.15.0 reproduces the 0.14.0 run exactly.** Every coefficient of every
point and every residual, to the last printed digit, on all four points. The
emitted script for the rotor case is byte for byte the 0.14.0 script, the
staged geometry path apart. This release moved no number.

Against the pfs0110 table, over nine coefficients per point:

| case | max delta | at | status, both sides |
|---|---|---|---|
| 3207 steady wing-body, both points | 0.000e+00 | every coefficient | CONVERGED, COMPLETED_MAX_ITER |
| 3224 unsteady wing-body | 2.000e-07 | a three-way tie, `CL`, `CMx` and `Cz` | COMPLETED_MAX_ITER |
| 9001 isolated propeller B45 | 5.640e-05 | `a+00.0_b+00.0.Cz` | CONVERGED |

The residual pair for 9001 is the one already recorded: 7.5929024e-06 against
7.5929667e-06.

**PER SURFACE, NOT ONLY THE TOTAL.** The table above is the `Total` surface,
and a per-rotor reduction change is exactly what a Total can hide: shifts
across the blade and the hub that cancel leave it unmoved. So every surface
of every polar group was compared as well, 1080 values:

| case | per-surface values | max delta |
|---|---|---|
| 3207 | 540 | 0.000e+00 |
| 3224 | 270 | 0.000e+00 |
| 9001 | 270 | 6.000e-05, at `g05.CLB` |

Nothing compensating: the rotor case's per-surface maximum is the same order
as its Total, and the two steady and unsteady wing-body cases are identical
on every surface. 3224's per-surface zero against its Total's 2e-7 is the
polar tables' five decimals against the sweep table's seven.

## The band

Her instruction is that every coefficient match "within the band that
workspace already records", and that a difference "is a finding and not a new
band". There are two recorded answers and the report names both.

**In this repository**, `RPT-040` line 12 defines the band by PFS-2030.06 as
the repeatability control, "her recorded script for the unsteady point run
again unchanged, whose largest difference from the recorded table is the band
a reproduction may differ by without being a regression", and measures it at
**0.0000000**, "so the criterion the selected points meet below is identity,
not a tolerance".

**Out of tree**, `pfs0131/README.md` records a band per case from the
reproduction on the published 0.13.1: 3207 identical to every printed
decimal; 3224 max delta 2e-7; 9001 max delta 5.6e-5 with the same residual
pair. Her sentence beside it: "the steady row to the digit, the unsteady wing
to the last digit, and the rotor within the solver's own run-to-run band (the
residual differs in the fifth digit; the 0.11.0 repeatability control of
GOAL-011 measured the same class)".

The band in the JSON is neither of those read as a literal threshold. It is
each coefficient's OWN recorded delta, `abs(0.14.0 - 0.11.0)`, at full
printed precision from the 0.14.0 reproduction of the same three rows, which
makes the criterion **this release moves no coefficient further from the
pfs0110 table than the last release already stood**. A coefficient the two
releases agree on carries a band of zero and must match exactly, which every
one of 3207's eighteen does.

**WHICH BAND SHOULD GOVERN A RELEASE CHECK IS HERS TO SETTLE**, and it is
routed rather than decided. Under `RPT-040`'s 0.0000000 the 2e-7 of 3224 and
the 5.64e-5 of 9001 are findings, not a band. Under the per-coefficient band
above they are the position the previous release already occupied and this
one did not move from. The numbers she needs for that call are all in the
table above and in the JSON.

## The judgements in this report

Four, and the first version of this report disclosed only the last.

1. **Which table is "the pfs0110 record".** The workspace's own
   `campaign_sweep.csv`, stamped 0.11.0, rather than her master's campaign.
   Corrected after review; the first version's prose said "her record" while
   the data said the table, and the two differ at 3207 zero incidence by up
   to 2.6e-3.
2. **Which recorded band governs.** Routed to her, above.
3. **Comparing per surface as well as Total.** Added after review. The first
   version compared the Total only and did not say so.
4. **Reading her two-significant-figure band at full precision.** Her table
   says 5.6e-5 where the delta it describes is 5.640e-5, on the very
   coefficient it names. Read as a literal threshold it fails the measurement
   it was written from, and rounding it up to 5.65e-5 or 5.7e-5 would be
   choosing a number, which is the widening she forbids. So each
   coefficient's band is its own recorded delta: measured, not chosen.

## What a reader of THIS repository cannot check

The run happened outside the tree, in a workspace holding her geometry. These
claims rest on artifacts no clone carries, and the digests are given so a
later reader can tell whether the file they hold is the file that was read:

| artifact | sha256 (first 32) | bytes |
|---|---|---|
| `pfs0110/post/campaign_sweep.csv` | `fe7556b21f2455c8fa184d2a2f377ae5` | 1254 |
| `pfs0140/post/matriz_repro/sweep.csv` | `1d37fd968d1414f7de4b5146bf9e704d` | 2587 |
| `pfs0150-repro/post/matriz_repro/sweep.csv` | `c18dfd1e69d20077868b0eb7d4db104b` | 1295 |

Not checkable from here: that 0.15.0 reproduces 0.14.0 exactly; that the
rotor script is byte for byte the 0.14.0 script; the four statuses; the
residual pair; the run-identity table; the per-surface comparison; and her
`pfs0131/README.md` band. Twenty-seven of the thirty-six `recorded` values in
the JSON ARE independently confirmed against `RPT-040`'s committed tables;
the other nine are 3207's zero-incidence point, which `RPT-040` tabulates
against her campaign rather than against the pfs0110 table.

**The JSON's check is an equality by construction**, and that is stated
rather than left to be discovered: `band` is `abs(at_0_14_0 - recorded)` and
`measured` equals `at_0_14_0` in all thirty-six, so `abs(measured -
recorded) <= band` holds with equality everywhere. That is what an exact
reproduction looks like, and it is also what a file with one column copied
twice would look like. The digests above are what separates the two.

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
seemed worse than the deviation. The workspace, its matrix and its comparison
script are outside git, with her geometries; only this report and the JSON
are committed. If she wants it inside `pfs0150`, the run moves and nothing
else changes.

`pfs0110` was read and not written.

## What the review pass corrected

The verification lens read the first version and found six things. Five are
folded above and one is this file's name.

1. **Nine of 3207's eighteen `recorded` values were the pfs0110 table where
   the prose said her record**, so a 2.6e-3 warm-start difference documented
   in `RPT-040` was reported as 0.000e+00. The values are correct for what
   they are; the prose was not. The three-table section at the top exists
   because of this finding.
2. **The band this repository records, `RPT-040`'s 0.0000000 under
   PFS-2030.06, was not mentioned at all.** It is now, and the choice is
   routed to her rather than asserted.
3. **The check is an equality by construction and the report did not say
   so**, nor carry anything letting a reader tell an exact reproduction from
   a copied column. The digests are that.
4. **The comparison was Total-only and did not say so.** The per-surface
   comparison, 1080 values, was run in answer and is above.
5. **Only one judgement was disclosed, under a heading inviting a reviewer to
   check that one.** Four are listed now.
6. **The identifier collided**: `RPT-041` was already taken by
   `RPT-041_script-action-reread-on-26123_2026-09-08.md`. This is RPT-046.

Two questions the lens raised are hers and are not answered here: that
9001's `CMz` moves 84 per cent of its own value while the absolute maximum
reads 5.6e-5, so the largest RELATIVE disagreement is invisible in the
headline; and that her README names "Cz and CL" as carrying the 5.6e-5
maximum where Cz alone carries it, CL being 5.540e-5.
