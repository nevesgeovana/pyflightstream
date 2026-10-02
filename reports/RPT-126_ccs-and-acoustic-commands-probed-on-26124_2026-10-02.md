---
report: RPT-126
requirements: FR-333, FR-334, FR-335, FR-336
ccs2_real_verdict: refusal_stays
ccs2_real_cause: "The REAL token is not the cause: REAL with the limits 0.5 and 0.9 is lofted without error, as PARAMETRIC is, while the limits 2.0 and 3.6 end the solver process after the command line and before any loft is written in both spaces and along either axis, so the REAL row of RPT-097 neither solved nor saved."
---

# RPT-126 - The acoustic and CCS commands probed on FlightStream 26.124, the arity of two CCS exports, and the REAL control-surface form (2026-10-02)

This report records the licensed tier-2 run that **FR-333** to **FR-336** require, made after the
0.34.0 release, and one re-probe of the CCS meshing commands that this run left unjudged.
Everything ran on
**FlightStream 26.124, build 8172026**, executable SHA-256 withheld from the public tree per
NFR-31, one solver instance at a time, hidden.

- **The run** (three launches, 2026-10-02T17:46:06-03:00 to 2026-10-02T17:47:59-03:00): the
  `pyfs-qa probe` run of the command set (17:46:20 to 17:47:20), the arity arms (17:46:06 to
  17:46:17) and the control-surface arms (17:47:23 to 17:47:59). Package tree at `b8d84191`.
- **The re-probe** (one launch, 2026-10-02T19:01:52-03:00 to 2026-10-02T19:02:26-03:00), named
  LQ2B in the evidence lines of the report. Package tree at `907391af`.

At both trees no file under `src/` differs from v0.34.0: the probe scripts are the ones
pyflightstream 0.34.0 generates. Far field: every probe that solves states far field 5 layers
(`SOLVER_SET_FARFIELD_LAYERS 5` immediately before each `INITIALIZE_SOLVER`, added in the run's
own process, because the released probe preludes state no far field; each script differs from
the package's by that line only, checked before the run). In the run, the nine acoustic probes
and the two control-surface arms that solve (P_s and RL_s) carry that line. No other probe of the
run solves, and no probe of the re-probe does.

The committed compatibility report is `reports/compat/CMP-26124_2026-10-02_qa-promote.yaml`,
with its Markdown rendering: the run's report with the one line the re-probe judged replaced
(section 6), both written by the package's report writer. Every status of the command database
named below moved by `pyfs-qa apply-compat` from it, and from nothing else.

Only outcomes, counts and line counts are stated. The geometries are synthetic: the
three-component CCS file the probe catalog builds from public shape laws, and the pusher of the
tier-3 library (a body, its base and one blade, saved by 26.120) for the probes that open a
simulation.

## 1. The questions

FR-333: "the seven acoustic commands ..., the CCS commands, `DELETE_SURFACES` and the wake
commands that ran in RPT-096 to RPT-098 carry probe specifications, are run by `pyfs-qa probe` on
26.124, and the command database records each verdict." R4: "a command the run did not judge
keeps its status and RPT-126 says why."

FR-334: "the surface-sections, CCS-wing and boundary-layer commands carry probe specifications,
are run on 26.124 by `pyfs-qa probe` in the run of FR-333, and their verdicts are committed in the
command database and in a report."

FR-335: "a licensed probe on 26.124 measures whether `EXPORT_FUSELAGE_CCS_FILE` and
`EXPORT_REVOLVE_CCS_FILE` take six arguments or four, and the command database states the
measured arity for that build." R1: "RPT-126 states, per command, the arity measured and how (the
file written and its content)."

FR-336: "a licensed probe on 26.124 separates why the REAL form of the control-surface limits
fails, and RPT-126 states the cause." R1: "Each probe changes one thing against the PARAMETRIC
form that runs, so the cause is separated rather than guessed."

## 2. The set, and what this run did not judge

The run judged 43 commands: every command of the acoustics, CCS-wing, CCS-fuselage and
CCS-revolution chapters of the command database, `DELETE_SURFACES` and `CCS_IMPORT`, each with
its probe specification: 9 of the acoustic chain and 33 CCS commands (`CCS_IMPORT` and the 32
meshing commands of the three CCS chapters, the control surface of FR-334 among them), with
`DELETE_SURFACES`.

Not judged by this run, each keeping its 26.124 status (FR-333 R4): `EXPORT_SURFACE_SECTIONS`
(FR-334), `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` and the six `CAD_CREATE_*` lofting commands
(FR-333 R1). A verdict would move a status in a chapter that the commits after the 0.34.0 tag do
not change; they are owed to 0.35.0. `VOLUME_SECTION_BOUNDARY_LAYER` (FR-334) is in no database
view of 26.120 or later, so no 26.124 run can judge it.

## 3. The command verdicts (FR-333, FR-334)

| outcome | the run | after the re-probe |
|---|---|---|
| verified | 25 | 26 |
| broken | 7 | 7 |
| unprobed | 11 | 10 |

Verified (26):

- the nine acoustic commands: `ACOUSTIC_SOURCES`, `CREATE_NEW_ACOUSTIC_OBSERVER`,
  `ACOUSTIC_OBSERVERS_IMPORT`, `SET_ACOUSTIC_OBSERVER_TIME`, `COMPUTE_ACOUSTIC_SIGNALS`,
  `EXPORT_ACOUSTIC_SIGNALS`, `CREATE_ACOUSTIC_SECTION`, `DELETE_ACOUSTIC_OBSERVER` and
  `DELETE_ALL_ACOUSTIC_OBSERVERS`;
- `CCS_IMPORT`, and `DELETE_SURFACES` (the saved boundary inventory after the command is the one
  before it without its first boundary, the rest renumbered: three boundaries before, two after);
- the control surface of FR-334, `NEW_CCS_WING_CONTROL_SURFACE`, in its ten-argument PARAMETRIC
  form (the wing lofted after it has 743 vertices against 1302 before it);
- the settings of the three CCS chapters: `CCS_WING_MESH_SUBDIVISIONS`,
  `CCS_WING_MESH_GROWTH_RATE`, `CCS_WING_MESH_GROWTH_SCHEME`, `CCS_WING_MESH_PERIODICITY`,
  `CCS_FUSELAGE_MESH_SUBDIVISIONS`, `CCS_FUSELAGE_MESH_GROWTH_RATE`,
  `CCS_FUSELAGE_MESH_PERIODICITY`, `CCS_REVOLVE_MESH_SUBDIVISIONS`,
  `CCS_REVOLVE_MESH_GROWTH_RATE`, `CCS_REVOLVE_MESH_GROWTH_SCHEME` and
  `CCS_REVOLVE_MESH_PERIODICITY`, and `CCS_FUSELAGE_MESH_GROWTH_SCHEME`, the one command the
  re-probe judged (section 6);
- the refinement zone of the fuselage and of the revolution: `NEW_CCS_FUSELAGE_REFINEMENT_ZONE`
  and `NEW_CCS_REVOLVE_REFINEMENT_ZONE`.

Broken, each with the reason its database row now carries (FR-334 R3 for any of FR-334's
three; none of the three is broken):

| command | the probe's reason |
|---|---|
| `EXPORT_WING_CCS_FILE` | ran past the command; the CCS file it names was not written |
| `EXPORT_FUSELAGE_CCS_FILE` | ran past the command; the CCS file it names was not written |
| `EXPORT_REVOLVE_CCS_FILE` | script processing aborted at the command (END sentinel missing) |
| `NEW_CCS_WING_FLAP_COVE` | script processing aborted at the command (END sentinel missing) |
| `NEW_CCS_WING_MORPHING_SURFACE` | script processing aborted at the command (END sentinel missing) |
| `NEW_CCS_FUSELAGE_RELAXED_TE` | script processing aborted at the command (END sentinel missing) |
| `NEW_CCS_REVOLVE_RELAXED_TE` | script processing aborted at the command (END sentinel missing) |

Each broken row keeps the form the database states, with the probe's reason in its note; a
refusal of any of them by the package at plan is a change in `src/`, owed to 0.35.0.

The ten commands that stay unprobed are in section 7, grouped by the cause measured.

## 4. The arity of the two CCS exports (FR-335)

Five forms of each command, the catalog's probe script with its target line alone edited
(criterion fixed before the run):

| form | the line's tokens after the command | fuselage | revolution |
|---|---|---|---|
| A6, the package's | NAME TRUE SHARP TRUE C2 C2 | ran past it, no file | aborted at it, no file |
| A6m | NAME FALSE BLUNT TRUE C2 C2 (the two the table has no row for, changed) | ran past it, no file | aborted at it, no file |
| A6c | NAME TRUE SHARP OPEN C2 C2 (informative) | ran past it, no file | aborted at it, no file |
| A4 | NAME TRUE C2 C2 (the table's four) | ran past it, no file | aborted at it, no file |
| A4c | NAME OPEN C2 C2 (the control: a token the solver reads moves the file) | ran past it, no file | aborted at it, no file |

Six when A6m's file differs from A6's; four when A6m's equals A6's, A4 writes A6's file and A4c's
differs from A4's; undetermined otherwise. No form of either command wrote a file, so there is
no file and no content to compare. Measured: fuselage undetermined, revolution undetermined. The
evidence line of each command in the compatibility report says that the written file did not
separate the two readings on this build and claims no count of arguments; the database keeps
six, and nothing emitted changes. Both commands are broken on 26.124 (section 3). The arity of
FR-335 stays unmeasured, and a probe that makes either command write its file is owed to 0.35.0.

## 5. The REAL form of the control-surface limits (FR-336)

| arm | the line (after the name) | what moved against its pair | stopped where | lofts written | solved save |
|---|---|---|---|---|---|
| P | 0.5 0.9 ... PARAMETRIC Y | the control | ran to the end, exit code 0 | both | |
| R | 0.5 0.9 ... REAL Y | the space, against P | ran to the end, exit code 0 | both | |
| RL | 2.0 3.6 ... REAL Y | the limits, against R (RPT-097's row) | past the command, then the process ended, exit code 3221225477 | none | |
| PL | 2.0 3.6 ... PARAMETRIC Y | the limits, against P | past the command, then the process ended, exit code 3221225477 | none | |
| RX | 2.0 3.6 ... REAL X | the axis, against RL | past the command, then the process ended, exit code 3221225477 | none | |
| P_s | P, then one loft, the steady solve and a save | the row, against P | ran to the end, exit code 0 | | written |
| RL_s | RL, then the same | the row, against RL | past the command, then the process ended, exit code 3221225477 | | not written |

"Past the command" means the log exported after the command line exists: the solver read the
line without a script error. Exit code 3221225477 is 0xC0000005, an abnormal end of the solver
process; no loft and no saved simulation followed it.

RPT-097's REAL row ended FAILED_EXECUTION with no saved simulation and no log line naming a
cause; the package's window log of that row recorded one empty dialog. The arms separate it:
the REAL token is not the cause, because REAL with the limits 0.5 and 0.9 is lofted without error, as PARAMETRIC
is (R against P); the limits 2.0 and 3.6 end the solver process in both spaces (RL against R,
PL against P) and along either axis (RX against RL). RPT-097's row, RL_s, neither solved nor
saved, so by the rule fixed before the run (`form_works` only when RL_s solves and saves)
`ccs2_real_verdict: refusal_stays`.

What follows: the plan's refusal of the REAL form (FR-295 to FR-297) stays. Its message cites
RPT-097; citing this report is a change of the message, which is in `src/`, owed to 0.35.0.

## 6. The re-probe of the CCS meshing commands

**Why it ran.** The run left eleven commands unprobed. Nine of them are CCS meshing commands
whose probe lofts two or three surfaces in one solver session and exports them all at the end,
by index. On 26.124 a surface lofted earlier in the session does not keep its mesh when a
refinement zone, a control surface, a default reset or the fuselage growth scheme follows it:
the reference loft exported 0 vertices where the same loft, with nothing structural after it,
exports 1975 (fuselage), 4484 (wing) and 4584 (revolution). The released judges read an empty
export as not observable, so the lines said unprobed. The re-probe changes when each loft is
exported, and only that.

**The five arms.** Each spec is the released catalog entry with its prelude and epilogue rebuilt
from the released builders; the target line, the judge, the instrument reading and the effect
note are the released ones. Each arm's script differs from the released script only by moved or
added mesh exports, `DELETE_SURFACES 1`, the control loft of arm D and the one precondition line
of DP, DR or DS (checked before the run).

| arm | what it changes |
|---|---|
| I | every loft exported as it is made; the first surface re-exported at the end shows whether a later command changed it |
| D | every loft exported as it is made and then deleted, so each loft is alone in the session; an undo spec adds a control loft after the modified one, without the probed command, which must equal the modified loft |
| DP | D, with the probed default reset also stated before the first loft (the three default resets) |
| DR | D, with the fuselage axial growth rate 1.2 before the first loft (the fuselage growth scheme): both lofts share the rate and differ by the scheme alone |
| DS | D, with the wing span subdivisions 40 before the first loft (the two wing zone commands) |

Arm I confirmed the cause: in eight of the nine specs the first surface, re-exported at the end,
had 0 vertices; in the ninth (`DELETE_CCS_WING_REFINEMENT_ZONES`) index 1 at the end was another
surface (the first export slot held a different surface, so the comparison was not
possible).

**The merge rule, fixed before the run.** An arm's line counts when its outcome is verified or
broken, every judged mesh export names exactly the surface the spec lofted into it, and, in a
D-based undo arm, the control loft holds the same vertices and faces as the modified loft. When
the counting arms of a command agree, the first of them in the order I, D, DP, DR, DS replaces
the run's unprobed line; when they disagree, the run's line stays; when none counts, the run's
line stays. Only the package's own verdict on an arm counts: nothing outside the package's
judge decides a line.

**The control of the merge.** The merged report was written by the package's report writer from
the run's lines and the re-probe's counting line. The run's 370 lines rebuilt through the writer
equal the run's lines exactly, and the solver identity, the executable name, the package
version and the invocation of the re-probe are the run's.

**Result.** One command judged, verified: `CCS_FUSELAGE_MESH_GROWTH_SCHEME`, from arm DR. With the
default growth rate (arm D) the two lofts are equal, so the scheme had nothing to act on; with
the rate 1.2 the loft after the successive scheme has the same counts (1975 vertices, 1896
faces) and a different mesh. Its line in the report states the re-probe and the arm.

## 7. The ten commands that stay unprobed on 26.124, each owed to 0.35.0

None of these ten is verified on 26.124; the counts below are observations, not verdicts.

Each keeps its 26.124 status (FR-333 R4). Judging any of them needs a change of a probe
specification or of a judge, which is in `src/`.

**The effect is in the raw counts, and the released judge does not classify it (six).**
`DEFAULT_CCS_FUSELAGE_MESH_SETTINGS`, `DEFAULT_CCS_REVOLVE_MESH_SETTINGS`,
`DEFAULT_CCS_WING_MESH_SETTINGS`, `DELETE_CCS_FUSELAGE_REFINEMENT_ZONES`,
`DELETE_CCS_REVOLVE_REFINEMENT_ZONES` and `DELETE_CCS_WING_CONTROL_SURFACE`.

| command | reference loft | modified loft | control, without the command | restored loft |
|---|---|---|---|---|
| `DEFAULT_CCS_FUSELAGE_MESH_SETTINGS` | 1975 v, 1896 f | 2449 v, 2370 f | 2449 v, 2370 f | 1975 v, 1896 f |
| `DEFAULT_CCS_REVOLVE_MESH_SETTINGS` | 4584 v, 4661 f | 2293 v, 2370 f | 2293 v, 2370 f | 4584 v, 4661 f |
| `DEFAULT_CCS_WING_MESH_SETTINGS` | 4484 v, 4366 f | 588 v, 560 f | 588 v, 560 f | 4484 v, 4366 f |
| `DELETE_CCS_FUSELAGE_REFINEMENT_ZONES` | 1975 v, 1896 f | 2844 v, 2765 f | 2844 v, 2765 f | 1975 v, 1896 f |
| `DELETE_CCS_REVOLVE_REFINEMENT_ZONES` | 4584 v, 4661 f | 5058 v, 5135 f | 5058 v, 5135 f | 4584 v, 4661 f |
| `DELETE_CCS_WING_CONTROL_SURFACE` | 4484 v, 4366 f | 3925 v, 3750 f | 3925 v, 3750 f | 4484 v, 4366 f |

(arm D; v vertices, f faces.) In plain words: in each of these six, arm D's raw counts show the
effect. The loft made after the command returns to the reference counts, and the control loft
made without the command stays at the modified counts. The released judge does not classify
it: it gives a verdict only when the restored loft equals the first loft line for line, and here
the counts match while the exported lines do not, so it returns no verdict and the line reads
unprobed. By the rule fixed before the run only the package's verdict counts, so these six are
owed to 0.35.0 (a judge that reads the restore against its control), not verified.

**The zone does not change this wing's mesh (two).** `NEW_CCS_WING_REFINEMENT_ZONE` and
`DELETE_CCS_WING_REFINEMENT_ZONES`. In arms D and DS, where each loft is alone in the session,
the wing lofted after the released spec's refinement zone equals the reference loft (4484
vertices and 4366 faces in D, 4838 and 4720 in DS, the same mesh), and in arm I the zone loft
exported empty. The zone the spec defines does not change this wing's mesh, so no verdict is
possible; a spec whose zone changes the wing loft is owed to 0.35.0.

**The precondition is refused, and the effect is not in the mesh (two).**
`DELETE_CCS_FUSELAGE_RELAXED_TE` and `DELETE_CCS_REVOLVE_RELAXED_TE`, not re-probed. Their only
scripted precondition, `NEW_CCS_FUSELAGE_RELAXED_TE` or `NEW_CCS_REVOLVE_RELAXED_TE`, aborts the
script on 26.124 with a script error at its own line (both are broken, section 3), so the probe
of the delete never reached its sentinels. A relaxed trailing edge also marks faces in the saved
simulation rather than changing the lofted mesh, which the released mesh judge cannot see. Now
that the precondition is recorded broken on 26.124, the released probe script of each delete no
longer builds on that build: the probe waives its target command only. A spec and a judge that
read the saved state are owed to 0.35.0.

## 8. What this does not show

- One build. The acoustic chain on one geometry at one rotation rate; the verdicts are of the
  commands' effects, not of any acoustic level.
- The REAL arms run one wing, two sets of limits and two axes. No arm solved a REAL
  row with the limits 0.5 and 0.9, so whether such a row solves is not shown.
- The arity of FR-335: neither export wrote a file in any form.
- The commands of section 2 that this run did not judge, and the ten of section 7.
