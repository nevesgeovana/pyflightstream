# The quasi-steady rotor: `qsteady_rotor`

`qsteady_rotor` solves an ISOLATED, AXISYMMETRIC rotor steady: the blades are
held still and the free stream turns about the rotor's shaft at the rotor's
speed (`SET_FREESTREAM ROTATION`, in the rotor's hub frame, about its shaft,
at its `RPM` signed by the rotor block's `rpm_sign`). The reference declares
exactly one rotor block, and the rotor is that block: its hub, its shaft, its
hand and its blades. The row states the speed as `RPM` (or `ADVANCE_RATIO`)
in its `FLIGHT_CONDITION` cell. It runs without FSI; a sector may couple its
blade (FSI, below).

It is valid only where nothing but the rotor is in the flow and every blade
is alike, and the builder refuses what it can detect is not: a reference
declaring no rotor or several, a row turning a second rotor (`MOTIONS`),
loading an actuator disc, or turning the free stream by a body rate, and an
opened geometry holding a boundary that is none of the rotor's families.
Whether the blades are alike is the user's to know: the mesh is not compared
blade by blade. A rotor on an airframe runs as `unsteady_rotor`.

The row's `SYMMETRY` decides which of two cases it is:

| case | the row states | what is solved |
|---|---|---|
| SECTOR | `SYMMETRY PERIODIC` and `PERIODIC_COPIES` | the meshed blade, once, steady |
| WHEEL | no symmetry | every blade, once per clocking, each clocking steady |

A `MIRROR` symmetry is refused: a turning rotor is not its own mirror image.

**The sector** stands for the wheel only in an inflow that is the same at
every azimuth. An angle of attack or of sideslip is refused on it, and a
custom inflow (`FREESTREAM`) is accepted only where it varies with the
radius alone: rows at the same distance from the shaft (to 1e-4 of the
field's largest radius) must state the same axial, radial and swirl
velocity to 0.1 % of the field's largest speed, a tolerance a field extracted
from another solution and interpolated onto rings meets
(`pyflightstream.cases.qsteady.azimuthal_variation`, whose `relative` and
`radius_relative` a caller states otherwise), and a file with no two rows at
one radius is refused, since nothing in it shows that it is axisymmetric.

**The wheel** meshes every blade the rotor block lists (a mesh of one blade is
a sector); a blade is present by its own label or by the alias the row's
reference gives it. In an axial, uniform inflow it is steady in the rotating frame and
solved once. In an inflow that varies around the disc (an angle of attack or
of sideslip, or a custom inflow) each blade meets a different flow, and the
row MUST state `PASSAGE_POSITIONS: k`, a count, one or more (`2` or `2.0`,
read as every count of a row is): the wheel is solved at
`k` clockings uniform inside ONE blade passage,
`theta_i = i * (360 / N) / k` for `i` from 0 to `k - 1` with `N` the blade
count, and the post averages them. The clockings are rotations of the
rotor's surfaces about its shaft in the sense of its rotation, each followed
by a new initialisation of the solver; clocking 0 is solved last, with the
point's full set of exports, so its loads export is of that one solve. Each
further clocking exports its loads as `<point>_qs<i>.txt` beside the
point's own and the section exports the row declares (the
sections' Cp, their sectional loads, the section Cp plot), each with
`_qs<i>` before its suffix: `<point>_qs01_sloads.txt`. The solver fixes a
distribution's cuts when it creates it, over the blade's extent in the pose
it then holds, and a frame does not turn with the blades on a steady run, so
the pproc's distributions are created at EVERY clocking: each clocking
deletes the previous clocking's (`DELETE_ALL_SURFACE_SECTIONS`, so none
accumulates), turns the wheel, initialises, and creates them again in frames
placed in the setup turned with the wheel to that clocking and held there
(`<frame>_QS<i>`). Every clocking is then cut at the same stations over the
blade's span. A distribution in `LOCAL_AXIS` is cut in each blade's own frame,
`<ALIAS>_RMRP<k>`, which a wheel places for that purpose; a frame whose
placement the script does not know cannot be turned with the wheel and is
refused naming it. The point's quasi-steady record names each clocking's
section exports (`section_exports`). The solver log the point exports holds EVERY clocking's solve,
in the order they ran (clockings 1 to `k - 1`, then 0), each residual table
counting its iterations from 1 again. The run reads it solve by solve: each
clocking's convergence is judged from its own solve, and its last iteration
is held to that clocking's loads export. The run record carries one verdict
per clocking in `clocking_verdicts` (`index`, `clocking_deg`, `status`,
`iterations`, `residual`), and the point's status and residual are the worst
of them.

How many clockings, measured on a six-blade research propeller at 5 deg on
26.124 (RPT-089): **`PASSAGE_POSITIONS: 2` converges thrust and torque to
about 0.2 %; state 6 or more for the in-plane loads** (the side forces and
the pitching and yawing moments, small resultants of large blade loads,
within 1.6 % of 24 clockings at 6). The cost is one steady solve per
clocking, about ten times less than three unsteady revolutions at 6.

**A custom inflow on the wheel is the TOTAL velocity of the air at the disc**,
in the global frame, and the package composes from it the RELATIVE free
stream the fixed blades see, which removes the rotational velocity of each
point: it writes a new field file, `v - Omega x (p - hub)` at every row, with
`Omega` along the rotor's shaft (a letter or a vector) and `p - hub` measured
from the rotor's hub, the air as the blade held still meets it, and states
`SET_FREESTREAM CUSTOM` of that file (a run has one
`SET_FREESTREAM`). The field lies in the YZ plane, so the rotor's shaft must
be the global X axis; the file's units are declared by `FREESTREAM_UNITS`
(an undeclared file is read in metres and metres per second, and refused on
a simulation in another unit). The source file is never written; the new
one carries a provenance file naming what was added.

**FSI.** A SECTOR couples its blade: the steady coupled route, the blade held
still and the free stream turning, and the structural solve is the ROTATING
blade at the speed the row turns the free stream (its `omega_rad_per_s` is
taken from the row's `RPM`, whatever the FSI input states), so the
centrifugal tension and its stiffening and the in-plane centrifugal softening
are applied ([FSI in the workspace](fsi-workspace.md#quasi-steady-sector-fsi)).
A WHEEL with FSI is refused: a quasi-steady wheel is several steady clockings
averaged, and a blade deformed once per clocking is not the state of one
structure.

**The validity parameter.** The quasi-steady solution holds where the blade's
load changes slowly against the time the flow takes to cross it. Its measure
is the 1P reduced frequency of each blade station,

```text
Omega = 2 pi RPM / 60
V_rel = sqrt(V^2 + (Omega r)^2)
k     = Omega c / (2 V_rel)
```

with `r` the station's radius, `c` its chord and `V` the point's free-stream
speed. The `1P` is counted ON THE BLADE: how many times one blade meets the
inflow's non-uniformity in one of its own revolutions, once for an inflow
that varies once around the disc. It is not the excitation a fixed surface
near the rotor feels as the blades pass it (the blade count times the
rotation rate), nor what a balance under the whole rotor reads summing every
blade. Below about 0.05 the flow follows a once-per-revolution load as it
changes; above about 0.1 the lag of the unsteady wake is no longer small and
the load there is an estimate. `pyfs-matrix plan` shows, for every wheel
point, the per cent of the span with `k > 0.1`, the minimum, the maximum and
the span-weighted mean of `k`, and WARNS, naming the point, when that per
cent is above zero; nothing is refused. The plan reads the chord off the
blade's mesh where the geometry is an OBJ the row does not move (the largest
width of each radial band of the first blade's surface); where it cannot, it
says why and states what it knows, `k` per metre of chord at the root and at
the tip; a point with no free-stream speed and no rotation says that `k` is
not defined there, since the blade sees no relative flow. Each wheel point
leaves `<point>_qsteady.json` in its datapoint folder: the case, the rotor,
each clocking and its loads export, and the plan's `k` (minimum, maximum,
mean and the span above 0.05 and above 0.1). After the run the post reads the
chord from the sectional loads export and adds the share of thrust and of
torque from the stations above 0.1, and writes the point's values into
`<point>_qsteady_validity.json` beside that record (the run's record is a
hashed input of the run and is not rewritten); the sections, the clockings
and average tables and the point's super-file row carry the same values
([the definitions](post-processing-definitions.md#the-quasi-steady-rotor)).
The record has one reader, `pyflightstream.cases.qsteady.read_qsteady_record`,
which returns it as a `QsteadyRecord` and refuses a record that is missing,
unreadable or of another schema with one error, `QsteadyRecordError`. The run
then judges the point's solver log as one solve and says so in the point's
record `warnings`; the post names every product the point loses.

**The harmonics of a custom inflow: `pyfs-matrix plan --inflow-fft`.** The 1P
`k` measures the slowest change a blade meets; a custom inflow can make it
meet faster ones. With `--inflow-fft` the plan reads, for every wheel point
in a custom inflow, the angle-of-attack perturbation ONE BLADE meets as it
turns once through the field, at each station of blade one (the field
sampled at 360 azimuths by a quadratic fitted to its twelve nearest rows,
the rotation composed, `w = v - Omega x (p - hub)`, the inflow angle
`atan2(w_axial, w_tangential)`), its Fourier spectrum, and `n95`, the
smallest harmonic order whose harmonics hold 95 % of its variance. A
harmonic below 0.001 deg of angle of attack is not counted, and a station
with none above it meets a constant inflow: `n95` 0, one clocking. The
sampling leaves at most about 1e-4 deg on a field the blade meets as a
constant (a radial profile on rings or on a grid), and a 1 deg crossflow
reaches a blade tip as a few hundredths of a degree, so the floor sits
between the two. Then, per
point: `k_eff = n95 k_1P` per station, its minimum, maximum, span-weighted
mean and the per cent of the span with `k_eff > 0.1`; `n_max`, the highest
`n95`; and the suggested `PASSAGE_POSITIONS >= n_max / N + 1`, rounded up,
with a WARNING naming the point when the row states fewer. With the option
the reduced-frequency warning reads `k_eff`. Without a chord at plan time
the harmonics are read at equal bands between 0.2 R and the tip and `k_eff` is
not computed, and the plan says so.

**nP is counted on the BLADE.** The harmonic order `n` is how many times ONE
blade meets the perturbation in one revolution, seen in the blade's own
frame as it turns through the field. It is NOT the blade-passing excitation
`N P` a fixed surface near the rotor feels as the `N` blades go by, and it is
NOT what a balance carrying the whole rotor measures: summed over `N`
identical blades `360 / N` apart, every harmonic of one blade cancels in the
rotor's total except the multiples of `N` (`m N P`). That is why the count of
clockings is read against `n_max / N`: the clockings sample one blade
passage, in which the rotor's total repeats.

**The limits.** Axisymmetric, isolated rotors only. At an angle, the
in-plane loads are quasi-steady ESTIMATES: on the measured propeller the
side force and the yawing moment came out with the opposite sign to the
unsteady rotor's and the normal force 20 % lower, whatever the clocking
count. At 0 deg of angle and 10 deg per step, the quasi-steady thrust was
9.2 % above the unsteady rotor's after three revolutions and 7.5 % after
six, and the torque 7.1 % and 5.75 % above (RPT-089 section 3). A finer unsteady step
closes part of that: at 5 deg per step and six revolutions the thrust gap was
3.6 % at 5 deg of angle and 3.9 % at 0 deg, the normal force was 11.7 % and
`Mz` 8.2 % away, and the side force and the yawing moment kept their
opposite sign. That measurement is of hand-built scripts of the same
commands, which clocked the wheel from a new simulation per clocking rather
than by rotating its surfaces between solves. The scripts this run type
builds have since run on 26.124: a sector coupled with FSI (RPT-090) and a
wheel at 5 deg clocked by rotating its surfaces inside one launch
(RPT-091).

From the terminal, that whole study is one command:

```text
pyfs-matrix run workflow_rotor_matrix.fs \
    --name rotor --workspace . \
    --sweep-csv sweep.csv
```

No Python is written, no notebook is opened, and nothing sits between
the file and the result. The sweep table lands as `campaign_sweep.csv`
under `post/<matrix stem>/` in the workspace when you do not say where, so a
second matrix of the same workspace keeps its own.

**Each point keeps its outputs in its own folder**, and that is what lets
a swept row be judged point by point. `run` judges each finished point
with the standard assessor, which reads the loads spreadsheet that point
exported, and finds it by CONTENT rather than by name, because a swept
case names its outputs per point and no single literal could name them
all. Each point collects into `sims/<sim>/datapoints/DP-<point>/`, so
what the assessor reads is that point's evidence and nothing else. The
matrix printed on [the workflows page](workspace-and-workflows.md) runs as printed, row 7002's two alphas included,
and that is what the acceptance case in the suite does with the
committed fixture unmodified.

**A missing output strands nothing** (0.27.0). A point one of whose
declared outputs was not written is recorded `FAILED_INCOMPLETE_OUTPUT`, and
every declared output it did write is still filed in its
`datapoints/DP-<point>/`, listed in the record's `outputs` with its sha256 in
`outputs_sha256`; the error names the missing files and nothing else
(`test_a_missing_log_strands_no_other_output_of_a_local_point`,
`test_collection_files_every_output_that_exists_and_names_only_the_missing`). A missing file does not prevent collection of the outputs that exist. The collection method raises `MissingOutputsError`, a
`WorkspaceError` whose `collected` lists what it filed.

**Every point of a row that names a run type leaves its final saved
simulation** (G11). After the point's
solve, first among its exports, the script saves the solver's state with
`SAVEAS` under the point's file stem
(`test_g11_every_workflow_script_saves_its_final_simulation`,
`test_g11_the_save_comes_first_among_the_points_exports`), and the file is
collected into `sims/sim_<POL>/datapoints/DP-<point>/P<POL>-<point>.fsm`
(the stem as `pyfs-matrix` names it). It is listed in the run record's
`outputs` and hashed in its `outputs_sha256`
(`test_g11_the_saved_simulation_is_collected_and_hashed`), and a point whose
file is not there is recorded `FAILED_INCOMPLETE_OUTPUT`, like any declared
export that is missing
(`test_g11_a_point_whose_saved_simulation_is_missing_is_recorded_incomplete`).
It holds for `steady`, where each point of a steady sweep saves its own
(`test_g11_every_point_of_a_steady_sweep_saves_its_own`), for `unsteady` and
for `unsteady_rotor`, on every registered build a run type renders on
(`test_g11_every_workflow_script_saves_its_final_simulation`,
`test_g11_the_saved_simulation_is_collected_and_hashed`); 25.000 renders
no script for any run type, so it has no point to save. A pproc cannot
turn it off: `[exports] simulation = false` is refused, as `loads = false`
is (`test_g11_a_pproc_cannot_switch_the_saved_simulation_off`). A `LEGACY`
row saves one only if its recipe writes `SAVEAS` to a name its `OUTPUTS`
declare, and `pyfs-matrix plan` warns naming every `LEGACY` row whose
`OUTPUTS` declare no `.fsm`; the warning blocks nothing
(`test_g11_a_legacy_row_without_a_saved_simulation_is_warned_at_plan`). A
case written in Python that declares its own `outputs` exports exactly
those, with no saved simulation unless one of them ends in `.fsm`
(`test_a_row_declaring_a_loads_table_and_a_log_gets_exactly_those`). This
file is what [the additional post](workflow-additional-post.md#extracting-more-from-a-finished-point-the-additional-post)
reopens.

**A point that imports its trailing edges from a file is held to the
solver's own count** (G02). A point that matches no mesh edge
marks nothing, and the solver says nothing about it, so after the run the
number of trailing edges the solver logs as imported is compared with the
points the script wrote, and the point is recorded `FAILED_SCRIPT` when they
differ, whatever its convergence; with no solver log to read it is recorded
`FAILED_INCOMPLETE_OUTPUT`. The count is read from the exported log, so a
raw-mesh row on the file route declares one among its outputs (a run type's
default outputs do), and a row that declares none is refused when its script
is built ([mesh inputs](mesh-inputs.md#the-boundary-conditions-of-a-raw-mesh)).

**Name your outputs per point.** The folders no longer collide, but the
PRODUCTS do: a point's polar, plots and probe tables are named after the
stem of its loads file, so two points sharing a name produce one table
claiming both runs. That is refused at plan time, before anything runs,
as it was before this release; what changed is the reason, not the rule.
Two outputs of ONE point may not share a name either, and there the old
reason still holds: they land in one folder under one base name.

**The probe velocities are in the blade's frame.** The run holds the blades
still and turns the free stream, so the probe velocities of a quasi-steady run
are expressed in the rotating frame of the blade: the velocity a probe reports
carries minus the rotation times its radius, and a fixed-frame field is that
velocity with the rotation times the radius added back. Measured on 26.124
(build 8172026) by the research study
[RPT-137](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-137_actuator-disc-measured-behaviour-on-26124_2026-10-01.md)
summarises, where a probe at 1.5 rotor radii read a tangential velocity of
-2.618 times the free-stream speed at an advance ratio of 1.8. The probe frame
is described with the other probe conventions in
[sampled velocity fields](sampled-fields.md).
