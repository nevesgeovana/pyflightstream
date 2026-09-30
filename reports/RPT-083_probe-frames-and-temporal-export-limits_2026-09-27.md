# RPT-083 - Probe frames and temporal export limits (2026-09-27, editorial amendment 2026-09-28)

This report records GOAL-033 controls for sampled velocity fields, final
unsteady plots and surface averages. The conclusions apply to the exact native
builds below. A nominal version number alone is not sufficient evidence.
Private geometry, executable payloads and workspace paths are not reproduced.

| Native version | Reported build | Executable SHA-256 |
| --- | --- | --- |
| 26.124 | 8172026 | withheld; build 8172026 |
| 26.122 | 8092026 | 75668a514d1887db2f94a97e3d57662888029e3e9e0b5e8f5611ac7082b15690 |

## Sample positions, vector meaning and units

The 26.124 unsteady control retained the existing rotor setup and added
nineteen diagnostic sample positions with VX, VY, VZ and speed: 76 scalar
histories over six actual STEPs. Coincident fixed and moving samples, an
axis sample, a twelve-point off-axis ring, a fixed frame rotated 90 degrees
and a moving frame with that initial rotation distinguish position motion
from velocity-component rotation. Explicit motion attachments identify the
moving frames; frame names alone are not used as evidence.

For the METER case, exported velocity components are absolute velocities in
REFERENCE axes. They do not receive an affine origin shift, a local-basis
rotation, or subtraction of angular velocity crossed with radius. The matched
ring positions progress through 330, 300, 270, 240, 210 and 180 degrees for the
emitted -800 RPM, with delta-time 0.00625 s. The sampled time is
(STEP - 0) × delta-time. This does not prove a delayed-start convention or an
arbitrary composed motion.

Steady EXPORT_PROBE_POINTS was measured separately by reopening the saved
state without another solve. Four points under three analysis-frame settings
retained the same REFERENCE positions and absolute REFERENCE velocity
components. METER outputs use m and m/s; MILLIMETER outputs use mm and mm/s.
After conversion, differences were at most 1.776e-15. A final steady export
and the last unsteady fluid-plot sample differ (for example VX 11.012 versus
11.022); the export families are not asserted to sample the same instant.

The moving MILLIMETER investigation deliberately preserved four controls:

| Control | Changed boundary relative to its parent | Observation |
| --- | --- | --- |
| Initial MM | Coordinate/reference dimensions scaled; velocity commands and custom field retained | Reynolds number became 2,300 instead of 2,300,000; not physically equivalent |
| Native-input MM | Velocity commands and custom-field XYZ/VXYZ also scaled ×1,000 | All 71 load-history columns matched the METER run, but the diagnostic samples did not |
| CUSTOM-SI isolation | Only the custom field returned to the exact METER bytes | Reynolds number was restored, but loads and sample fields disagreed |
| Fluid-vertex-SI isolation | Only UNSTEADY_SOLVER_NEW_FLUID_PLOT VERTEX values divided by 1,000 | All 76 diagnostic columns at all six STEPs and all 71 load-history columns matched METER exactly |

These controls distinguish command interfaces: on this executable, the
runtime velocity inputs and custom-field coordinates/velocities follow the
simulation units, whereas unsteady fluid-plot VERTEX arguments and their
exported velocity values are SI. This finding is specific to those commands;
it does not change the separately measured steady-probe output units.
The independent MM hypothesis comparison admitted only absolute REFERENCE
components, no origin shift, the measured signed rotation and STEP origin 0.
The registry binds that evidence to the exact executable hash and build.
No unmeasured build is admitted.

Field products retain the original sample identities, actual STEP values,
source hashes, solver identity, declared frame, resolved integer frame,
trajectory proof and export convention. Output coordinates and velocities
are REFERENCE m and m/s. Vertex-cloud topology is explicit: no surface cells
or interpolated values are invented. A reusable inflow file additionally
requires a nondegenerate global YZ-plane survey with no duplicate positions.

## Final section Cp, residual and load plots

T40 measured final SECTIONS_CP after the established unsteady control on
26.124: thirty nonempty curves with 15-18 sample pairs were written once
after the march. Nine final load coefficients matched the baseline exactly.
This supports the final section-Cp export; it is not a claim of per-STEP Cp
section histories. The callback control used the reviewed Windows pythonw
variant. Its executed bytes are distinguished from the original console
interpreter variant.

Walltime rescue was measured separately on 26.122. CLOSE_FLIGHTSTREAM after
the declared exports ended the native process at STEP 16 without an external
kill. The residual and load plots each contain 1,128 finite samples with
inner-iteration abscissae 1-1,128. The separate aggregate unsteady history
contains only STEPs 1-15. A rescue filename carrying 16 therefore identifies
the export event; it does not imply every history contains sample 16.
No missing sample is reconstructed or appended.

## Native nodal strength and cell-field association

T39 matched nine native Tecplot/VTK pairs on 26.124: a REFERENCE reopen,
a fixed 30-degree Y-tilted analysis frame, six actual STEPs and the final
state. Each pair matched 1,054 nodes and verified the topology of 1,138 cells
using unique coordinates plus polygon-edge incidence at 1e-6 coordinate
tolerance, without interpolation. Both source hashes remain in provenance.
Original VTK cell values retain their cell association; native nodal
Singularity_strength retains its nodal association.

After the measured frame correction, tilted and REFERENCE coordinates agreed
to 1.916e-15; velocity-component differences were at most 9.948e-14, and
matched nodal strength agreed exactly. Strength changed between every pair
of successive STEPs (maximum absolute changes 53.6515, 4.52304, 6.01261,
6.86747 and 6.07439), ruling out reuse of the final array for earlier states.

The distinct Cp_reference and Cp_freestream fields were preserved under an
unequal reference-velocity control. Their native values do not support an
assumed universal factor-of-four conversion. The translator does not invent
that conversion, interpolate nodal Cp from cell Cp or relabel Cp as strength.
These instantaneous T39 observations do not make nodal strength or native
boundary-layer exports averaged statistics; the temporal distinction below
still applies.

## Temporal averages and the permitted discrepancy branch

The rotor T41 control on 26.122 exported twelve STEPs, with its first retained
instantaneous surface at 6 and averaging window 7-12. The original RPT-079
observables (native nodal Cp, Vx and speed) were compared node by node after
applying the same uniform reducer to the native instantaneous arrays.
Maximum scaled errors were 8.128e-16, 1.222e-15 and 7.240e-16 respectively,
within the 1e-13 band. This diagnostic does not convert the product's cell Cp
into nodal Cp. A separate cell-to-cell comparison preserves its association.

Native Singularity_strength, CF and boundary-layer fields retained their last
instantaneous values in this control. The package instead computes their
actual means from matching per-STEP native/VTK pairs. These are different
statistics, so native equivalence is not claimed for them. An independent
sum/count calculation checked every selected scalar in the rotor 7-12 and
walltime 2-3 windows to 1e-13, with changing nodal strength proving that final
values were not borrowed. X, Y and Z remain coordinates of the last selected
STEP; coordinates are not treated as averaged physical scalar fields.

The walltime CLOSE control's native Cp, Vx and speed were exactly the STEP 16
instantaneous values rather than the requested mean 2-3. Their scaled
comparison errors were 10.219, 7.147 and 14.599. The package therefore refuses
WALLTIME surface-average products by name. This follows the approved G55
criterion: if solver and package disagree for a run type, the package average
for that type is refused until corrected. It is not an equivalence claim or
a waiver of the comparison.

Two negative stop controls are retained. STOP inside the action fired at 13
but the solver continued to 93 before the 90 s guard ended its own process.
Changing TIME_ITERATIONS from the callback did not return normally and
reached the separate 30 s guard. Neither behavior is used to claim successful
walltime termination. CLOSE proves termination and instantaneous rescue;
it does not prove finalization of aggregate histories or native averages.
G38 modal-window monitoring and its licensed T30 control are separate gates.

## Evidence and limits

All native source and executed-script hashes are retained in the control
receipts. Principal comparison digests are:

| Evidence | SHA-256 |
| --- | --- |
| METER fixed/moving velocity comparison | af4cc684043546188b4de86320c00b8a45041d7da40b6b2cd62b0172cf55130b |
| Independent moving MILLIMETER comparison | 4193840726b01d12b9cfd81c854636ed5b9328a431d315020f5cde8b505c62b6 |
| T39 geometry/topology and association comparisons | 31bb749f3a68232277378e7f3591b3404655975125608c10e3e7cf79b38b91cb |
| Separate steady METER/MM frame comparison | 58b314eaf3aa7ce2cb7823255b8b8031e99bc6b67664cae000b17c321316e9cb |
| Rotor comparison in the original RPT-079 domain | 671033004a3966d4d7b7bc7d3e58adbffd0a14feaf363295d0125f39221c68cc |
| Independent selected-field sum/count checks | 8ef8761449af3a2765107da34c1451ad36fcf1eeebeec9eae1102ca3eb949a1e |
| Walltime native-average discrepancy and history coverage | 65445ac6921a2ad38e398b2c654f57d981a2abe0ccac0f27a77bc9b1a9cfef29 |

The controls do not establish arbitrary native versions, arbitrary motion
composition, delayed motion starts, interpolation accuracy or a universal
benefit from ingesting a sampled inflow. Unchanged native files remain the
authority for the samples actually produced.

The focused implementation regression run passed 70 tests, Ruff and mypy for
the four field/averaging/continuation source modules. A reviewed continuation
defect was corrected: reopening a saved state now retains the recorded field
layout, solver setup and sample-position file after verifying its coordinates
and identities against the predecessor. Changed evidence is refused by name.
These checks do not replace the separate whole-release review and native gates.

## Native surface-property histories

A separate 26.124 build 8172026 control exercised
`NEW_UNSTEADY_SOLVER_SURFACE_PROBE` on the same synthetic public geometry.
Its SHA-256 is `c6e719b921fe4396c89870b513c0e84f714a089699ee5562775d465d376ad599`;
the public provenance describes construction from shape laws. Two stationary
surface-cell centroids, two fixed frames (REFERENCE and a translated Z90 frame),
14 parameter tokens and six STEPs produced 56 histories per unit. METER and
MILLIMETER controls used corresponding local native-length coordinates.
All 336 compared values matched exactly. A MILLIMETER control using metre-valued
probe arguments differed by as much as 16.689 in the recorded scalar values.
This command therefore has a different coordinate contract from fluid-plot
vertices. No moving-frame surface-probe claim follows from these fixed-frame tests.

Eight parameters produced distinct supported observables: CP_FREE, CP_REF, MACH,
VELOCITY, VX, VY, VZ and STATIC_PRESSURE_RATIO. At the first point and STEP,
CP_FREE was -0.093918, CP_REF -0.021108, speed 16.609, and velocity components
(15.401, -2.0064, 5.8871). Components remained REFERENCE components in m/s
in the fixed-frame and unit comparisons. Raw columns are preserved without
force-coefficient scaling.

All six BL tokens returned exactly CP_FREE at every tested point, frame and
STEP: BL_MOMENTUM_THICKNESS, BL_DISPLACEMENT_THICKNESS, BL_TOTAL_THICKNESS,
BL_SHAPE_FACTOR, BL_SKIN_FRICTION and BL_TRANSITION_MARKER. Saved native plot
records also retained the same internal property tuple as CP_FREE. Negative
Cp values must not be published as boundary-layer thicknesses. The typed
workspace route now refuses these requests by name before emitting probes.
Section-based boundary-layer products remain separate observables; they do not
replace the requested histories. This native defect leaves that part of the
command inventory open; the refusal is not a claim of complete G67 support.

The public numerical fixture is
`tests/tier1_offline/data/native_surface_probe_samples.json`. It retains all
56 six-step series in both units and their source hashes. Original METER
plot SHA-256: `bac53d7ad88bb5a8a4b7d0d27272a537acc82cca4eb355e8c0ff50d2a07ef11c`;
MILLIMETER plot SHA-256: `70ab2bf95d61c5d472b02d468c88a6694c67ab7abcba0be4893dd95f32637fd5`.
The fixture includes negative BL results explicitly, without redistributing
private paths or licensed solver payloads.
