# Sampled velocity fields

A probe survey can produce VTK or Tecplot files containing its sampled positions
and three velocity components. Add the formats to an existing pproc artifact:

```toml
[[probes]]
frame = "REFERENCE"
field_formats = ["vtk", "tecplot"]
reusable_inflow = true
rectangles = [{origin=[0,-1,-2], along_u=[0,1,-2], along_v=[0,-1,2], points_u=2, points_v=2}]
```

The request includes VX, VY and VZ automatically. General plot generation can be
turned off while the requested field histories remain enabled. A volume section
uses the same sampling route; its grid is specified by its own plane, dimensions
and point counts. The exported topology is a **vertex cloud**. It contains no
invented surface panels or interpolated volume cells.

The workspace `[volume_section]` route samples through probes and does not
address native volume-section indices. It can therefore sample a saved FSM that
already contains native sections without using those sections as its new grid.
The direct native/custom API remains different: it does not discover existing
section indices from a saved FSM. A caller using that low-level route must
establish the actual native indices; this limitation is not repaired by the
probe adapter. New locations or histories require recorded samples or a supported
extraction; post-processing cannot reconstruct an unrecorded flow field.

Each unsteady STEP produces a separate file. Positions in the resulting field
are in REFERENCE coordinates and metres; velocity is absolute, in REFERENCE
components and metres per second. The provenance names the original frame,
its recorded motion, the actual STEP, coordinate conversion, source-file hash
and native velocity evidence. The source results remain unchanged.

Named fixed and rotating frames are resolved when the script is built. Their
original local sample coordinates are retained; post-processing uses the final
motion record, including attachments emitted later in the script. A resumed
run inherits its validated sampling layout, solver setup, point-position evidence
and unchanged recorded trajectories. Changed or unproved motion facts
produce a named diagnostic instead of a guessed placement.

Native fluid-plot conventions are verified for FlightStream 26.124 build 8172026
with the recorded executable digest, independently in METER and MILLIMETER
simulations. Build 8242026 of 26.124 is registered with the same conventions by
decision of 2026-10-01, not by measurement ([RPT-136](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-136_fr153-build-8242026_2026-10-01.md)):
its fields are written with no warning, and its rows say "not measured". Fluid-plot command vertices use metres in both cases; the saved
layout retains native coordinates for frame placement. The measured velocity
components are already absolute REFERENCE components in m/s, even when the sampling
frame rotates. Applying the sampling-frame rotation to those components again
would be incorrect. Another export family, solver version or unit needs its
own evidence; the diagnostic identifies a missing convention. Another build of
26.124 in a measured unit is written with a warning, as
[A run on another build](#a-run-on-another-build) describes.

Steady probe exports have a separate control on that exact build. Their XYZ and
velocity components are REFERENCE values regardless of the analysis frame.
METER exports use metres and m/s; MILLIMETER exports use millimetres and mm/s.
The field exporter converts both to SI once. These steady values need not equal
the last fluid-plot sample: the exports can sample different solution states.
The original probe CSV keeps its native values for compatibility.

**A quasi-steady rotor run is the exception.** A `qsteady_rotor` point holds
the blades still and turns the free stream about the shaft, so the probe
velocities of a quasi-steady run are expressed in the rotating frame of the
blade, not in a fixed frame: the swept velocity of the blade is in them, with
the other sign. Measured on 26.124 (build 8172026) by the research study
[RPT-137](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-137_actuator-disc-measured-behaviour-on-26124_2026-10-01.md)
summarises: outside the slipstream, at 1.5 rotor radii and an advance ratio of
1.8, a probe read a tangential velocity of -2.618 times the free-stream speed,
which is the blade's rotation times that radius over the free-stream speed.
Add the rotation times the radius back before comparing the field with a
fixed-frame one, such as an `unsteady_rotor` probe or a wind-tunnel survey.

A reusable inflow file contains X, Y, Z, VX, VY and VZ in the native custom-inflow
UNSTRUCTURED form, with SI units. That form requires a two-dimensional global
YZ survey at constant X, without repeated positions. A field may be suitable for
visualization while its orientation or sampling does not define such an inflow.
Choose and validate the STEP and spatial coverage appropriate to the next case;
writing the file does not install it as a new boundary condition. State `FREESTREAM_UNITS:SI`
in matrix variables, or `freestream_units="SI"` in the case API, when reusing
this SI file. The input staging records any conversion to the simulation units
and preserves the original file.

The [worked example](examples/sampled_field_export.md) uses explicitly
synthetic data and needs no solver:

```console
python examples/sampled_field_export.py --output /absolute/path/to/new-output
```

It writes one VTK field, one Tecplot field and one reusable inflow with matching
provenance. The numerical source is saved beside them so the file hashes and
values can be inspected independently.

## A run on another build

The velocity conventions above were measured on FlightStream 26.124 build
8172026 and, by the decision above, 8242026. A run of 26.124 in METER or
MILLIMETER on any other build, for example a cluster build run with
`--accept-unregistered-build`, still gets its fields.
The post writes them with the convention measured on build 8172026 and adds one
warning per point to `post.log` and to the warnings the console prints, naming
the build the convention was measured on and the build the run reports. Each
field's entry in `products.json` records the same:

```json
"velocity_convention": {"measured_on_build": "8172026", "run_build": "<the run's build>", "proven": false}
```

A field sampled in a frame that turns needs one more measurement: the frame's
rotation timing, the rotation sense and the time origin of the STEP count. It
was measured on the same build, in METER and MILLIMETER. On another build of
26.124 such a field is written with that timing too, and the same one warning
per point says the timing is also unproven on the run's build. The entry then
records both:

```json
"velocity_convention": {"measured_on_build": "8172026", "run_build": "<the run's build>", "proven": false},
"rotation_timing": {"measured_on_build": "8172026", "run_build": "<the run's build>", "proven": false}
```

A delayed motion start has no measured timing on any build and is still
refused. A run of another solver version, another unit or another export family
has no evidence at all, and its fields are still refused with "native velocity
convention has no evidence for this export/build/unit", or, for a rotating
frame, as an unknown sampling frame (FR-153).

**How the convention was established.** One unsteady rotor run sampled VX, VY
and VZ at nineteen positions over six actual STEPs: an axis sample, and
coincident samples in a fixed frame and in a frame that turns with the rotor,
among them a twelve-point off-axis ring. The rotor turned 30 degrees per STEP
(-800 rev/min, 0.00625 s), so each moving ring sample lay on a fixed ring
sample at every STEP. The exported components of every coinciding pair were
equal: the components are absolute velocities in REFERENCE axes, in m/s, with
no origin shift, no rotation into the local basis and no subtraction of the
angular velocity crossed with the radius. A MILLIMETER twin of the run matched
the METER run in all 76 columns. [RPT-083](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-083_probe-frames-and-temporal-export-limits_2026-09-27.md)
records the comparison and its receipts.

**Measuring it on your build.** Run, on that build, an unsteady rotor row whose
rotor turns one ring spacing per STEP, 30 degrees for a ring of twelve:

```text
VELOCITY: 30.0 / RPM: 800 / ROTOR_AXIS: X / BLADES: 4 / DELTA_THETA: 30 / REVOLUTIONS: 1
```

Its pproc samples the same ring twice: once in the rotor's hub frame
`ROTOR_SMRP`, which stays fixed, and once in its turning frame `ROTOR_RMRP1`,
which starts on it and turns with the motion. The frame names are
`<ALIAS>_SMRP` and `<ALIAS>_RMRP<k>` (here the alias is `ROTOR` and the
blade is `1`); the bare names `SMRP` and `RMRP` are refused by the plan.
Write the ring about the rotor axis, clear of the blades, in the hub frame's coordinates; the numbers below assume the hub
frame's x axis is the rotor axis and are to be adapted to your rotor:

```toml
[groups]
"1" = "all"

[[probes]]
frame = "ROTOR_SMRP"
parameters = ["VX", "VY", "VZ"]
circles = [{center = [-0.5, 0, 0], normal = [1, 0, 0], radius = 0.3, points_radial = 2, points_azimuth = 12}]

[[probes]]
frame = "ROTOR_RMRP1"
parameters = ["VX", "VY", "VZ"]
circles = [{center = [-0.5, 0, 0], normal = [1, 0, 0], radius = 0.3, points_radial = 2, points_azimuth = 12}]
```

A rotor of four blades (`BLADES: 4`) makes the sampled field repeat every 90
degrees, so a ring of twelve stations identifies the rotation shift only modulo
three stations: the sense and the time origin can still be told apart over six
STEPs, but one blade pins the whole shift. Measure on a single blade when the
full shift matters.

At every STEP, compare in the point's plots export the VX, VY and VZ of each
moving sample with those of the fixed sample it lies on. The convention above
holds on your build when every coinciding pair is equal; repeat the row on a
MILLIMETER geometry for that unit. The same run measures the rotation timing:
the moving ring samples land on the fixed ones at the STEPs the emitted speed
and time step predict, which fixes the rotation sense and the time origin of
the STEP count.

**Registering the build.** The package reads the measured conventions from one
table, `VELOCITY_EVIDENCE` in `pyflightstream.post.field_frames`: one row per
solver version, build, export family and unit, holding the factor to m/s and
the comparison that established it. The rotation timing is the same kind of
table in `pyflightstream.script.motion`, one row per solver version, unit and
build. Registering your build is one row in each, citing your comparison, in a
change to the package. A run of a registered build is proven, and its fields
carry no warning. A row registered by decision and not by a comparison, as
8242026 is (RPT-136), says "not measured" in its evidence.

## Surface-property histories

An unsteady pproc artifact can request a native property at a surface point:

```toml
[[surface_probes]]
name = "upper_cp"
parameter = "CP_FREE"
frame = "REFERENCE"
point_m = [0.25, 0.1, 0.02]

[[surface_probes]]
name = "upper_speed"
parameter = "VELOCITY"
frame = "REFERENCE"
point_m = [0.25, 0.1, 0.02]
```

Place these points on your actual surface. The script emits
`NEW_UNSTEADY_SOLVER_SURFACE_PROBE` before initialization and records the
resolved frame, native command coordinates, parameter and plot identity.
Names use letters, digits and underscores, starting with a letter, and must
be unique. The resulting columns are `SURFACE_upper_cp` and
`SURFACE_upper_speed`; this prefix keeps their identity distinct from force
and off-body fluid plots. The native plots export is retained even when
`exports.plots = false`, because this request needs its history.

Supported surface-history parameters are `CP_FREE`, `CP_REF`, `MACH`,
`VELOCITY`, `VX`, `VY`, `VZ` and `STATIC_PRESSURE_RATIO`. The standard plots
CSV retains their native values and identities; it does not apply force-coefficient
scaling to these columns.

The six documented `BL_*` parameters are retained by the schema but refused
before probe emission. On FlightStream 26.124 build 8172026, all six returned
`CP_FREE` at both tested surface points and in both tested frames. Negative
values therefore cannot be interpreted as boundary-layer thicknesses.
There is no verified replacement surface-history route for these parameters.
The separate section-based boundary-layer products do not satisfy this request.

These histories are separate from sampled velocity fields and from the
section-based boundary-layer products. A steady row or a new additional-post
request cannot produce an unsteady surface history and is refused by name.
A validated continuation retains the original recorded declarations.

Surface-probe coordinates were independently measured in METER and MILLIMETER
simulations on that exact build and executable. The builder converts `point_m`
to local native length units once. All 56 histories across six STEPs matched
exactly between units; using metre-valued arguments in the MILLIMETER case did
not match. REFERENCE and a translated fixed frame rotated 90 degrees about Z
returned matching values. The measured velocity components were REFERENCE
components in m/s. This control does not establish behavior for a moving
surface-probe frame. See [RPT-083](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-083_probe-frames-and-temporal-export-limits_2026-09-27.md)
for the measured domain and the retained BL failure.
