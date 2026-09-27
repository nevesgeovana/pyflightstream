<!--
GEOVERSE_HEADER
file_version: 1.0.4
file_role: sampled-field-user-guide
last_modified_at: 2026-09-27T20:42:05.231Z
last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
dependencies: [pyflightstream.post.probe_fields, pyflightstream.post.field_frames]
authority: pyflightstream
status: draft
confidentiality: public
change_summary: Explain separate typed native surface-property histories.
revision_source: git
-->
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
simulations. Fluid-plot command vertices use metres in both cases; the saved
layout retains native coordinates for frame placement. The measured velocity
components are already absolute REFERENCE components in m/s, even when the sampling
frame rotates. Applying the sampling-frame rotation to those components again
would be incorrect. Another export family, build, executable or unit needs its
own evidence; the diagnostic identifies a missing convention.

Steady probe exports have a separate control on that exact build. Their XYZ and
velocity components are REFERENCE values regardless of the analysis frame.
METER exports use metres and m/s; MILLIMETER exports use millimetres and mm/s.
The field exporter converts both to SI once. These steady values need not equal
the last fluid-plot sample: the exports can sample different solution states.
The original probe CSV keeps its native values for compatibility.

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
surface-probe frame. See [RPT-083](../reports/RPT-083_probe-frames-and-temporal-export-limits_2026-09-27.md)
for the measured domain and the retained BL failure.
