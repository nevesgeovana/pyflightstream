## Added

- `native_match_tolerance` and `native_printed_digits` in `results/native_surface.py`: the one tolerance function of the native strength match, with the slack a native printed at limited digits carries far from the origin (FR-281).
- `DEFAULT_DRIFT_LIMIT_PCT` is in `pyflightstream.cases.__all__` (FR-283).

## Changed

- The time-averaged native strength matches each step's native with that tolerance and the digits the native was printed at (FR-282).
- The two quasi-steady tables state `J_CLOCK`, `RPM_CLOCK` and, where the row requested none, `J` from the rotor's own speed, its block's diameter and the point's free stream (FR-285).

## Fixed

- A static rig row (fixed `RPM`, `ADVANCE_RATIO` swept, with `MOTIONS`) is no longer refused by the plan for stating the rotor speed twice (FR-280).
- The thrust and torque shares of a wheel's sections table are pinned to clocking 0's rows by a test (FR-284).

## Migration

- `J` of `_qs_avg.csv` and `_qs_positions.csv` was `NA` and now holds the rotor's advance ratio where the row requested none; a reader that took `NA` there for "no advance ratio" reads the number (FR-285).
- A native strength matched at a point far from the origin, printed at limited digits, may now match where it was refused as ambiguous or missing (FR-281, FR-282).
