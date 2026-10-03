## Fixed

- **Steady and quasi-steady polars join the grouped jobs** (FR-403). `plan --batch N`
  and `plan --polar-sweep` no longer leave every `steady` and `qsteady_rotor` row out:
  they are grouped in jobs of their own, never with an unsteady polar, each later
  point of a polar restated from `SOLVER_SET_AOA` after `REMOVE_INITIALIZATION` (or,
  where it differs before that line, reopened after `NEW_SIMULATION`), and each point
  recorded and collected as the point run alone. A steady row stating
  `COLD_START` false, and a steady point that initialises the solver more than once,
  are left out and named. The licensed confirmation is owed.
- **`run --batch` and `run --polar-sweep` refuse a receipt that holds no job**
  (FR-365, FR-403). When the plan had left every polar out, the run read the empty
  receipt as no selection and ran every one of those polars in the default mode.
