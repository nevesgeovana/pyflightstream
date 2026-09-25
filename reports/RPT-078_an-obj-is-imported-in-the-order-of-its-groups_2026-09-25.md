# RPT-078: an OBJ is imported one boundary per group, in the order of the file (2026-09-25)

**Date:** 2026-09-25
**Found by:** the licensed probe T27 of the 0.28.0 work
**Status:** OPEN until G30 (0.28.0: an OBJ brought in without its surface names written by hand)
**Affects:** `IMPORT` with `FILE_TYPE OBJ` on 26.124

## What this settles

A raw mesh's surfaces are named in `<geometry>.boundaries.toml`, written by hand,
and the package emits every per-surface command by the POSITION the solver gives a
surface. For the package to write that list itself from an OBJ, it had to be known
how the solver numbers the surfaces of an OBJ with several groups. **One boundary
per group that holds a face, named by the group, numbered in the order the groups
appear in the file, for `o` and `g` alike.**

## What was run

FlightStream 26.124 (build 8172026), no solve: each variant imports one OBJ the way
row 4102 of the tier-3 matrix does (`NEW_SIMULATION`, `IMPORT` with `UNITS METER`,
`FILE_TYPE OBJ`, the file, `CLEAR`), saves the simulation and closes; the saved
file's boundary list is read back with the package's own reader. The OBJ is row
4102's wing, 816 faces under one `o Wing` group; each variant rewrites its groups
and nothing else, in one detached batch with no solver alive before it:

| variant | groups, in file order |
|---|---|
| O_ONE | `o Wing` (the control) |
| O_THREE | the faces cut into three contiguous thirds: `o ZETA`, `o ALPHA`, `o MID` |
| O_G | the same three written with `g` |
| O_EMPTY | `o ZETA`, then `o EMPTY` holding no face, then `o ALPHA`, `o MID` |

The names are not in alphabetical order, so an order by name and an order by file
differ.

## What came back

| variant | boundaries, by index |
|---|---|
| O_ONE | Wing |
| O_THREE | ZETA, ALPHA, MID |
| O_G | ZETA, ALPHA, MID |
| O_EMPTY | ZETA, ALPHA, MID |

Every import returned 0 in about one second and saved its simulation.

## What it means for the package

- **The boundary list of an OBJ can be read from the file**: its groups that hold
  a face, in file order, `o` or `g`, each named by its group. The package can write
  `<geometry>.boundaries.toml` for an OBJ instead of asking for it by hand; an STL,
  which names no group, stays by hand.
- **An empty group makes no boundary**, so it takes no position; a reader that
  counted it would shift every later surface by one.

## What this does not settle

- A file mixing `o` and `g`, or a group split in two places of the file.
- Faces before the first group.

## Evidence

The OBJ files, the scripts and the result records are kept machine-local with the
probe driver `p28o_driver.py`; the GOAL-032 ledger's T27 receipt names every path,
the executable's sha256 and the batch's preflight.

**Verdict: VERIFIED**, for what was run: `IMPORT` of an OBJ on 26.124 makes one
boundary per group holding a face, named by the group, in the order of the file,
for `o` and `g`, and none for an empty group.
