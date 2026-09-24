# RPT-062: what a reopened simulation gives back (2026-09-23)

**Date:** 2026-09-23
**Found by:** the licensed probe T09 of the 0.27.0 work
**Status:** REGISTERED for 0.27.0 (G12 extracts from a saved simulation exactly what this run
reproduced, and the plan refuses the rest)
**Affects:** the additional post-processing of 0.27.0; nothing shipped before it opens a
solved simulation to extract from it

## What this settles

Every workflow point saves its simulation after the solve and before its exports. The
additional post of 0.27.0 opens that file again, with no solve, and extracts what a
pproc asks for. This run measures what comes back. **Loads, the surface solution, every
surface section and the sectional loads computed on it come back identical, including
a new distribution defined after reopening. Off-body probe points do not: updated or
created after reopening, they differ from the run's.** On an unsteady point, the file
holds the last instant, and the force-plot history too.

## What was run

Two saved points on FlightStream 26.124, reopened from a copy (the run's own file is
never opened), eight variants with no solve, launched one at a time, detached, with no
solver alive and at least 4 GB free before each.

    steady      30_WB, RPT-060's control point (row 4201, CONVERGED): its script saves after
                the solve, the section update, the sectional loads and the probe update
    unsteady    40_PUSHER, tier-3 row 9001 run again on 26.124 with farfield layers 5:
                30 degrees per step, one revolution, step exports from half a revolution;
                COMPLETED_MAX_ITER, 857 iterations
    build       FlightStream 26.124 (build 8172026, executable sha256 68e64e66...)
    package     0.27.0.dev0 at 709bbd1

Each variant moved one thing:

| variant | what it does after opening |
|---|---|
| S1, U1 | export at once, the unsteady force-plot history included |
| S2, U2 | re-run the extractions the run made after its solve (update the sections, compute the sectional loads, update the probes), then export |
| S3, U3 | create a NEW distribution, and on the steady point NEW probe lines, identical to the run's, compute, export |
| S4, S5 | S2 and S3 with `LOAD_SOLVER_INITIALIZATION ENABLE` on the open |

Each export is compared with the run's own export of the same kind, the file-name and
date lines set aside. For S3, S5 and U3 the rows the variant ADDED are compared with the
run's rows. The control is the run's own export. The derangement compares S1 with a
different point (row 4202, the +4 deg/s roll of RPT-060) and must not come back
identical. It does not: every file differs.

## What came back

**Steady.**

| export | S1 open, export | S2 recompute | S3 new block |
|---|---|---|---|
| total loads | identical | identical | identical |
| surface solution | identical bytes | identical bytes | identical bytes |
| surface sections | identical | identical | the new 12 sections: identical |
| sectional loads | **zero**: not stored | identical | the new 12 rows: identical |
| probes | identical, as stored | **differ** | the new 99 points: **differ** |

**Unsteady.**

| export | U1 open, export | U2 recompute | U3 new block |
|---|---|---|---|
| total loads | identical | identical | identical |
| surface solution | identical bytes | identical bytes | identical bytes |
| surface sections | identical | identical | the new 20 sections: identical |
| sectional loads | **zero**: not stored | identical | the new 20 rows: identical |
| force-plot history | identical | identical | identical |

Against the run's own export of its last step, the reopened state gives the same
surface solution, sections and sectional loads. So the saved file is the last instant.

**The probes.** Updated on the reopened steady point, the 99 probe points keep their
positions and change their values: up to 0.0936 in Cp, 3.0 m/s in speed on 71 m/s
(4 percent), and 5.7 m/s and 4.1 m/s in the two cross components, against largest values
of 13.5 m/s and 5.7 m/s. New probe lines identical to the run's give the same changed
values, and loading the solver initialization on the open (S4, S5) changes nothing. The
file keeps the probe values the run computed, and a probe computed after reopening is a
different number. The surface solution comes back exactly, and the field off the body
does not.

## What it means for the package

- The additional post can promise the total loads, the surface solution, surface
  sections, the sectional loads and new distributions, all identical to what the run
  would have produced. It has to compute the sectional loads after opening, because the
  file stores the sections and not their loads.
- It cannot promise off-body probes. A pproc that asks for probe points on a saved point
  is refused by the plan, with this report as the reason. The probes the run already
  exported stay what they are.
- On an unsteady point it gives the last instant, with a warning that it is one instant
  and not the run's per-step history. The force-plot history comes back as the run wrote
  it.

## Seen on the way, and registered separately

- **The steady probe lines are emitted N squared times.** A pproc that declares 3 probe
  lines produces 9 `NEW_PROBE_LINE` commands on a steady row, each line three times, so
  the export carries 99 points where 33 were asked for. The emitting block sits inside
  the loop over the lines.
- **The unsteady step exports are in the reference frame, not the moment point's.** The
  unsteady script sets the loads frame after `START_SOLVER`, so every step export prints
  `Coordinate frame for analysis: Reference`, while the final export prints the row's
  frame. The forces agree and the moment coefficients about y and z do not.

## What this does NOT establish

- **One build.** 26.124.
- **Two geometries.** A half wing-body, steady, and a pusher rotor, unsteady.
- **Why the probes differ.** Off-body velocity depends on the wake, and the measurement
  is consistent with the wake not coming back as the run left it. That reading is not
  measured here.
- **The per-step history of an unsteady point** (the surface solution at each step, the
  step exports) is not in the file. Only the plots history is, as measured.

## Evidence

`reports/probes/RPT-062_2026-09-23_evidence.yaml`: the two points, each variant's script
digest and per-export result, the new-block comparisons, the derangement against row
4202, the probe differences column by column, and the last-step comparison. The solver
outputs stayed on the measuring machine (invariant 5).
