# RPT-039: the 1-based position in a saved simulation's mesh block is the solver's boundary index (2026-09-02)

**PFS-2028.00.** The evidence behind the one claim every rotor run of
0.10.1 rests on, written down because a verification lens found it resting on a
module docstring instead.

## Why this report exists

`src/pyflightstream/_fsm.py` reads boundary NAMES out of a saved simulation and
maps each to its 1-based POSITION in the mesh block, and the whole release
depends on that position being what the solver calls boundary *i*. The claim was
stated in the module's docstring and cited nothing. A verification review said
plainly that a claim resting on gitignored evidence is not acceptable at the
standard this repository already holds itself to, and it is right: every other
solver-behaviour claim here is promoted through a committed dated report.

The geometries themselves stay outside the repository. They run to 9 MB each and
some are derivatives that may not be distributed. **What needed committing was
never the files; it was the measurement**, and it is small.

## What is measured, and by whom

Every figure below was taken by the session that wrote this file, on
2026-09-02, against the eight geometries in the author's campaign workspace at
`GeoverseResearch/tools/fts_workspace/pfs0100/inputs/geometries/` and the run
outputs beside them. Where a figure was reported by a review agent and this
session could not reproduce it, it is EXCLUDED and named as excluded rather than
carried.

## Measurement 1: the number printed on each boundary's first line is NOT the index

Each boundary record begins with an integer and three flags. That integer is the
obvious candidate for the index and it is not the index.

| geometry | boundaries | head numbers run | first name |
|---|---|---|---|
| `09_NX_B45_NTUD_CTE.fsm` | 3 | 2 to 4 | `Blade1` |
| `14_NX_B45_NMIN.fsm` | 3 | 2 to 4 | `Blade1` |
| `18_NX_B45_NMIN_FW.fsm` | 8 | 2 to 9 | `Blade1` |
| `21_NX_B45_NTUD_BTE.fsm` | 3 | 2 to 4 | `Blade1` |
| `30_WB.fsm` | 2 | 2 to 3 | `W` |
| `35_BPN_PYL0.fsm` | 4 | 2 to 5 | `S` |
| `63_BPNX_PYL0_B45.fsm` | 10 | 2 to 11 | `Blade1` |
| `WING_ONLY.fsm` | 1 | 1 to 1 | `W` |

**Seven of the eight start their head numbers at 2 and one starts at 1.** A map
built from the head number is therefore off by one in seven files out of eight,
and correct in the eighth, which is the worst possible distribution: it would
work on the simplest geometry a reader tests with.

## Measurement 2: the solver's own run log lists the boundaries in mesh-block order

This is the solver answering the question directly, and it is the strongest of
the three.

The initialisation block of `sims/sim_9001/raw/unsteady_9001_a+00.0_b+00.0_log.txt`,
from the licensed 26.123 run of 2026-09-01, lists under `Poly / Boundary`:

    Blade1
    S
    N

The mesh block of the geometry that run opened, `14_NX_B45_NMIN.fsm`, read by
`pyflightstream._fsm.boundary_names`, gives:

    ('Blade1', 'S', 'N')

**Identical, and in the same order.** Compared as sequences rather than as sets,
so an agreeing multiset in a different order would fail.

## Measurement 3: every cell of the campaign resolves correctly under position ordering, and incoherently under head numbers

The campaign matrix carries ten cells citing boundaries by position, across five
rotor geometries. Under POSITION ordering every one resolves to the surfaces the
study intended, and one cell naming the family reproduces all ten:

| row | geometry | the cell as written | `Blade,S` resolves to | agree |
|---|---|---|---|---|
| 1004 | `09_NX_B45_NTUD_CTE` | `1,2` | `1,2` | yes |
| 1005 | `09_NX_B45_NTUD_CTE` | `1,2` | `1,2` | yes |
| 1006 | `09_NX_B45_NTUD_CTE` | `1,2` | `1,2` | yes |
| 1007 | `14_NX_B45_NMIN` | `1,2` | `1,2` | yes |
| 1008 | `18_NX_B45_NMIN_FW` | `1,2,4,5,6,7,8` | `1,2,4,5,6,7,8` | yes |
| 1009 | `21_NX_B45_NTUD_BTE` | `1,2` | `1,2` | yes |
| 1012 | `63_BPNX_PYL0_B45` | `1,2,4,5,6,7,8` | `1,2,4,5,6,7,8` | yes |
| 9001 | `14_NX_B45_NMIN` | `1,2` | `1,2` | yes |
| 9002 | `09_NX_B45_NTUD_CTE` | `1,2` | `1,2` | yes |
| 9003 | `63_BPNX_PYL0_B45` | `1,2,4,5,6,7,8` | `1,2,4,5,6,7,8` | yes |

**Ten of ten.** And the head-number reading is not merely different, it is
incoherent: every one of those ten cells cites index 1, and **no rotor geometry
in this campaign carries a boundary whose head number is 1**. Under that reading
the author's whole campaign cites a boundary that does not exist.

Two controls were run beside it, because a cell that agrees everywhere might
agree degenerately:

- A different family gives a different answer. On `18_NX_B45_NMIN_FW`: `Blade`
  alone gives `1,4,5,6,7,8`; `S` alone gives `2`; `Blade,S,N` gives
  `1,2,3,4,5,6,7,8`.
- The same cell on a permuted file MOVES. With the same three names reordered to
  `N, Blade1, S`, the cell `Blade,S` emits `2,3` where it emitted `1,2`. The
  positional cell `1,2` emits `1,2` in both, which is the defect.

## Byte identity, which is the compatibility claim

Driven through `pyflightstream.cases.workflows.build_script`, which is what the
campaign loop calls, with the real geometries and the row's own values:

| geometry | cell as written | cell naming the family | rendered script |
|---|---|---|---|
| `14_NX_B45_NMIN` | `1,2` | `Blade,S` | byte identical |
| `09_NX_B45_NTUD_CTE` | `1,2` | `Blade,S` | byte identical |
| `21_NX_B45_NTUD_BTE` | `1,2` | `Blade,S` | byte identical |
| `18_NX_B45_NMIN_FW` | `1,2,4,5,6,7,8` | `Blade,S` | byte identical |
| `63_BPNX_PYL0_B45` | `1,2,4,5,6,7,8` | `Blade,S` | byte identical |

Whole scripts compared, not the motion lines alone.

## EXCLUDED: a fourth measurement this session could not reproduce

A review agent reported that each geometry's own per-element surface array takes
values exactly 1 to N and never 2 to N+1, which would be a fourth independent
confirmation. **This session could not reproduce it.** Reading the array at the
offset it guessed returned distinct values in the range 0 to 3 on files with 8
and 10 boundaries, which is plainly the wrong array rather than a refutation.

It is recorded here as EXCLUDED rather than carried, because a measurement one
session states and the next cannot reproduce is not evidence, whoever was right.
The three above stand without it, and the second of them is the solver's own
answer.

## What this report does not establish

- **That a mesh block always has this shape.** Eight geometries from one study,
  all exported by the same toolchain. The reader refuses a block that does not
  hold the shape rather than guessing, which is the design answer to that bound.
- **That the solver reports its boundaries in mesh order on every build.** One
  run, on 26.123. The claim is corroboration, not a guarantee, and the package
  makes no promise resting on it beyond this release's own campaign.
- **Anything about a geometry with two boundaries sharing a name.** None of the
  eight has one. The reader leaves such a name out of the inventory and warns,
  which is a decision recorded in the code rather than a measurement here.

## Reproduction

The geometries and run outputs are in the author's campaign workspace, which is
gitignored, so a reader outside this machine cannot re-run these figures. That is
the residual and it is why the numbers are quoted rather than described: every
table above can be checked against the files by anyone who has them, and the
head-number column in particular can be checked by eye against any mesh block.

Measured on: python 3.12.0, `pyflightstream` at the commit carrying this file,
against the campaign's eight geometries and the 26.123 run of 2026-09-01.
