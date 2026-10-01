# RPT-113 - pyflightstream 0.33 licensed round L1: the parity campaign against 0.32 on FlightStream 26.124 (2026-10-01)

The report of the parity campaign of licensed round L1 of pyflightstream
0.33.0 (GOAL-038, arm L1): a short recorded campaign that exercises a steady
and an unsteady run type, run again by 0.33.0 and compared with its record.
It is the licensed counterpart of the offline parity receipt of arm R1
(`scripts/check_parity.py`, which posts the same recorded workspace with
v0.32.0 and with the release and compares the products). The rows ran
through the package route (`pyfs-matrix plan`, then `pyfs-matrix run
--local`) on **FlightStream 26.124, build 8172026**, executable SHA-256
withheld from the public tree per NFR-31, one solver instance at a time,
hidden, far field 5 layers. The package is the tree at `6e046291`. No solver
was run to write this report.

Only nondimensional values are stated: Mach and Reynolds numbers, the advance
ratio, r/R, coefficients, ratios, counts and times. The run id's last token,
which states the rotor speed, is written `RPM<n>`.

## 1. The campaign and why it is the reference

The recorded campaign is the one of RPT-094: three rows on one rotor, all on
26.124 (build 8172026):

| row | run type | what it moves |
|---|---|---|
| 9311 | qsteady_rotor (steady solves, three passage positions) | the wheel at an angle of attack of 5 degrees, sections |
| 9321 | unsteady_rotor, one revolution in 36 steps | a uniform custom free stream |
| 9322 | unsteady_rotor, one revolution in 36 steps | the constant control |

It was chosen because it is the smallest recorded campaign on 26.124 that
holds a steady and an unsteady run type, its record is complete, and it is
the workspace the offline parity receipt already posts. It was recorded by
the 0.31 tree; before the round, the scripts v0.32.0 renders for its rows
were compared with the scripts the record ran, after normalising only the
staged paths, the line ends and the action interpreter: **0 differing lines
in all three**, so the record is what v0.32.0 runs. The reference was
therefore recorded by the 0.31 tree and bridged offline by v0.32.0 rendering
byte-identical scripts; it was not recorded by v0.32.0 itself. The scripts
0.33.0 renders differ from v0.32.0's only by the step counter's three lines
on 9321 and 9322 (FR-314) and not at all on 9311.

## 2. How the comparison is read

The recorded workspace was copied (no junction followed) and posted again by
0.33.0, so the two post trees come from one post code and a difference is the
solver's. Every CSV file present in both trees is compared cell by cell with
the csv module: **identical**, **within** (every numeric cell within a
relative 1e-6) or **differs**. The records are compared on status,
iterations and time steps. The comparison script reported identical, differs
or missing; no table fell in the intermediate class of within.

## 3. Results

| row | record status, then and now | iterations or steps, then and now | tables identical | tables within | tables differing |
|---|---|---|---|---|---|
| 9311 | CONVERGED, CONVERGED | 61 iterations, 61 | 12 | 0 | 2 (timing only) |
| 9321 | CONVERGED, CONVERGED | 36 steps, 36; 1048 iterations, 1048 | 8 | 0 | 1 (timing only) |
| 9322 | CONVERGED, CONVERGED | 36 steps, 36; 1048 iterations, 1048 | 8 | 0 | 1 (timing only) |

The campaign-level `campaign_sweep.csv` of each of the two workspaces is
present only on the 0.33 side (it is new in 0.33, not a changed result): 34
files compared, 28 identical, 4 differing, 2 new.

Every coefficient table (rotor totals, quasi-steady averages and passage
positions, the harmonics, the per-revolution, phase-locked and time-average
probe tables, the section, pressure-coefficient and sectional-load tables) is
identical in every cell. The four differing tables are the two `SUPER` polars
of 9311 (largest relative difference 0.406, in the column `wall_time_s`) and
the unsteady average of 9321 and of 9322 (0.382 and 0.483, in the column
`solver_run_time_s`): run timing, which is not a result. The solver time of
the two unsteady rows was longer than recorded (78.6 s and 90.6 s against 48.6
s and 46.8 s); this round did not separate the counter's cost from the load of
the machine, and does not claim a cause.

## 4. Verdict

Parity on 26.124 (build 8172026): 0.33.0 reproduces the recorded results of
the steady and the unsteady run types: every status, iteration count and step
count is equal, and every coefficient, section, probe and reduction table is
identical in every cell; the only differing cells are run timings.

What this report does not cover: the confirmations of FR-318 and FR-96 are
not part of this round and stay owed. One rotor, one build, three rows: this
is parity of the recorded campaign, not of every run type.
