# RPT-111 - pyflightstream 0.33 licensed round L1: a geometry cleaned by `inventory --clean` opened and run on FlightStream 26.124 (2026-10-01)

The report of the clean-geometry row of licensed round L1 of pyflightstream
0.33.0 (GOAL-038, arm L1), for **FR-312** (item INVENTORY-CLEAN of the 0.33.0
scope) and the plan warning of **FR-313**. One row ran through the package
route (`pyfs-matrix plan`, then `pyfs-matrix run --local`) on **FlightStream
26.124, build 8172026**, executable SHA-256 withheld from the public tree per
NFR-31. One solver instance, hidden, far field 5 layers. The package is the
tree at `6e046291` (`package_commit` in `runs.json`, `package_dirty: false`).
No solver was run to write this report: it reads the round's records, logs and
saved simulations.

Only nondimensional values are stated. The geometry is a private saved
simulation; this report states none of its dimensions, names nor origin, and
the file, its sidecar and the scripts stay in the round's folder.

## 1. What was cleaned

The input is a saved simulation written by 26.124 (build 8172026, saved in
metres) whose `SOLVER` block ends with **two saved unsteady solver actions**:
a `COMMAND_LINE` action naming an interpreter of another machine, and a
`SCRIPT` action. Before the clean, `pyfs-matrix plan` warned once, naming the
row, the file, both actions and the command `pyfs-matrix inventory <file>
--clean`, and still wrote the plan with exit status 0 (FR-313 R2, R4).

`pyfs-matrix inventory <file> --clean` then:

- removed both saved actions (the action count set to 0, the action records
  removed), and kept a copy of the file as it was beside it (FR-308 R3);
- kept every other block unchanged, and said so on standard error: no fresh
  import of build 8172026 saved in metres is measured, so the FR-312 table,
  measured on 26.120 (build 7012026), is not applied to a file of another
  build (FR-312 R2);
- left the boundary names and boundary-condition marks equal before and after
  (FR-312 R4). The cleaned file differs from the original only in the
  `SOLVER` block's action list (seven lines replaced by the action count 0).

After the clean the plan printed no warning (FR-313 R5).

## 2. What the solver did with the cleaned file

| row | run type | steps | record status | the solver opened the cleaned file | error lines in the log | the removed interpreter in the log |
|---|---|---|---|---|---|---|
| 3311 | unsteady, periodic sector | 8 | `CONVERGED` | yes, the staged geometry hashes as the cleaned file | 0 | 0 |

What the row shows:

- The solver opened the cleaned file and marched the 8 steps (137 iterations,
  `CONVERGED`, build 8172026), and the simulation was saved. `plan` and `run`
  both ended with exit status 0.
- The step counter of FR-314 was registered on this row too: count 8 of 8,
  and the log shows the counter executed on every one of the 8 steps (RPT-112).
- The saved action that the clean removed did not run: the log holds 0
  mentions of the removed interpreter, 0 error or unrecognized lines and 0
  actions that failed to execute.

## 3. What this does not show

- The block reset of FR-312 R1 was not exercised by this row: the file is a
  26.124 save, for which no fresh import is measured, and the block-reset
  table covers 26.120 saves only, so only the saved actions were removed. The
  run proves that the cleaned file was **opened** and run, not the block
  reset. For a 26.120 save in metres the cleaned file is the fresh import
  byte for byte (`tests/tier1_offline/test_fr312_inventory_clean.py`), and
  that content is the committed tier-3 geometries', which 26.124 opens in
  every licensed round since 0.27.0; no separate licensed row was spent on it.
- One file, one build. A fresh import of 26.124 is not measured; until it is,
  a 26.124 save keeps its other blocks.
- The fallback row without symmetry, prepared in case the solver refused the
  periodic sector, was not needed and did not run.

## 4. Verdict

FR-312 licensed confirmation, limited as section 3 says: the solver **opened**
and ran a file cleaned by 0.33.0 on 26.124 (build 8172026): 8 steps,
`CONVERGED`, no error line, the removed interpreter never invoked. The block
reset of FR-312 R1 stays covered by the offline test alone.
