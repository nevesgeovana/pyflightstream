---
report: RPT-127
requirement: FR-342
tier2_rotate_surface: verified
tier2_set_new_unsteady_solver_action: verified
tier2_set_wake_termination_time_steps: verified
---

# RPT-127 - The T1 probe specifications re-measured by tier 2 on FlightStream 26.124 (2026-10-02)

The tier-2 native run **FR-342** owes (R3), run after the 0.34.0 release. One `pyfs-qa probe`
run on **FlightStream 26.124, build 8172026**, executable SHA-256 withheld from the public tree
per NFR-31, one solver instance at a time, hidden. The probe that solves states far field 5
layers (`SOLVER_SET_FARFIELD_LAYERS 5` immediately before `INITIALIZE_SOLVER`, added in the probe
run's own process: the released probe preludes state no far field; each script differs from the
package's by that line only, checked before the run). The probe scripts are the ones
pyflightstream 0.34.0 generates (package tree at `d09978f1`, no file changed). The run
window: 2026-10-02T17:18:39-03:00 to 2026-10-02T17:18:50-03:00.

The run's compatibility report is committed as
`reports/probes/RPT-127_2026-10-02_evidence.yaml`, byte for byte the report the run wrote
(`CMP-26124_2026-10-02_t1-probe.yaml`, SHA-256
`36e1fd12958cd30ae31e5b9d9dff80033adc10a9e5eae93d0ac01f64072273fc`). It is not under
`reports/compat/`: a report there obliges the command database to follow it, and that
promotion is owed to 0.35.0 (section 4).

Only outcomes are stated. The geometry is the synthetic blade of the tier-3 library
(`30_BLADE.fsm`, generated from public shape laws).

## 1. The question

FR-342, as the requirement states it: "every command the package emits that has no probe
specification carries one in the probe catalog, and a tier-2 native run on 26.124 re-measures
it." R3: "A tier-2 native run on 26.124, far field 5, re-measures them; RPT-127 carries the
verdicts and the command database follows them through the promotion tool, under the rule of
FR-333 R4."

## 2. The set

The four catalog entries of FR-342 R1 (the census of the work package, the workflow goldens):

| command | in the 26.124 view | instrument |
|---|---|---|
| `ROTATE_SURFACE` | yes | the saved simulation before and after: the mesh changes |
| `SURFACE_ROTATE` | no (26.121 and earlier) | not run: no 26.124 run can judge it |
| `SET_NEW_UNSTEADY_SOLVER_ACTION` | yes | the marker its registered script prints, in the log after a three-step unsteady solve; silence is unprobed |
| `SET_WAKE_TERMINATION_TIME_STEPS` | yes | the saved simulation before and after, under the unsteady mode |

`SET_MOTION_ANGULAR_VELOCITY` and `SET_MOTION_IS_ROTOR` carry no entry: no database view of
26.120 or later holds them, so no authorized run can judge them.

The control of each instrument is the probe's own: the saved state before the command against
the saved state after it in the same run, and, for the unsteady action, the absence of the
marker, which records `unprobed` rather than `verified`. The baseline probe and the `sim`
tier's baseline ran first, each in its own solver instance.

## 3. Measurements

The solver named build #8172026 (`FlightStream version 26.1, build #8172026`). Over the whole
26.124 view the report counts 3 verified, 0 broken, 0 removed and 367 unprobed; the 367 are
the commands this run did not probe.

| command | outcome | the evidence line, as the report records it |
|---|---|---|
| `ROTATE_SURFACE` | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: rotating every surface about the global frame changes the saved mesh |
| `SET_NEW_UNSTEADY_SOLVER_ACTION` | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the message the registered script prints appears in the log after the unsteady solve, so the solver ran the action; silence records unprobed |
| `SET_WAKE_TERMINATION_TIME_STEPS` | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the wake termination step count, set under the unsteady mode the rotor goldens render it in |

Each probe returned 0 with both sentinels seen and no log error between them; the wall times
were 0.85 s, 0.87 s and 0.75 s.

## 4. Verdict

- `ROTATE_SURFACE`: verified on 26.124, build 8172026.
- `SET_NEW_UNSTEADY_SOLVER_ACTION`: verified on 26.124, build 8172026.
- `SET_WAKE_TERMINATION_TIME_STEPS`: verified on 26.124, build 8172026.

What follows for the command database: the three statuses stay `documented` until 0.35.0
commits this run's report under `reports/compat/` and promotes from it with
`pyfs-qa apply-compat`; FR-342 R3's promotion is owed to 0.35.0, and the requirement stays
pending until then. The tier-1 test `tests/tier1_offline/test_rpt127_fr342_tier2.py` reads
this front matter against the outcomes the committed report records, with a planted mismatch
as its control.

## 5. What this does not show

- One build and one geometry; `SURFACE_ROTATE` and the two motion commands are not measured.
- An `unprobed` outcome means the instrument read nothing it could judge, not that the command
  failed.
- The command database does not yet carry these verdicts: the promotion is owed to 0.35.0.
