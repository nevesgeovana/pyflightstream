# Geometry units and steady starts

A steady attitude sweep starts every point cold, including the
first point. The script clears the solution before each solve. To retain the
previous warm behavior, set `COLD_START: false` in the matrix row. The Python
builder uses `build_steady_sweep` for the same opt-in.

Warm results can depend on the order of the points. The run continues to record
that order. Geometry and setup are emitted once in either mode. This change
applies to steady sweeps; it does not clear an unsteady time march or its
continuation. Unsteady rows continue to refuse `COLD_START`.

Physical coordinates in reference `moment_point_m`, `rotor_position_m`, rotor
`x_m/y_m/z_m`, reference `[[frames]].origin`, and probe specifications are
metres. Probe coordinates scaled by rotor radius first become physical metres.
The builder converts them once through the common length-unit table before
emitting a command that takes simulation units. Directions and angles are not
lengths and are not multiplied by this factor.

For example, a moment point at `0.25 m` is emitted as `250` in a simulation
whose length unit is millimetres. A probe `0.1 m` from that point is `100`
millimetres locally and `350` millimetres in the reference frame. Commands that
explicitly take `METER`, such as frame-origin translation, retain that explicit
unit; the placement ledger converts their result back to native coordinates.

The legacy matrix variable `ROTOR_ORIGIN` explicitly uses simulation units and
retains that contract. It is distinct from metre-valued rotor reference fields.
Imported raw meshes retain their existing import-unit conversion. No field of
custom inflow velocities or coordinates is automatically rotated.

Saved FSM units are decoded only for measured paired global-block headers:
`` is metres and `` is millimetres. The latter reuses the
 Paired static controls on build
8172026 imported the same meter-valued square, used frame origins differing
by a factor of 1,000, and saved identical meter-valued mesh/frame coordinates
after a positive 90-degree X rotation (maximum discrepancy below 1e-10).
`_fsm.saved_mesh_coordinate_unit` therefore separates the measured stored
coordinate unit from the display unit. Coverage checks do not apply the
millimeter factor to an already meter-valued saved mesh. This millimeter
storage interpretation is restricted to the measured build.

Unknown or inconsistent pairs are refused when a physical conversion is
needed. An explicit supported simulation-unit setting after opening the file
remains available when the user knows its unit.

Offline tests verify conversion and emitted ordering. Equivalent native loads,
moments and field behavior still require the release's licensed comparisons;
script serialization alone does not establish that equivalence.

## Measured OBJ boundary names

Native controls on 26.124, build 8172026, confirmed an `o` group followed by
a `g` group, repeated `g` groups, faces before the first `g`, and a `g`
statement naming several groups. Repeated groups remain separate boundaries,
even when their names match. Such duplicate names are selectable by position;
a name that matches several boundaries does not choose one arbitrarily.

Faces before the first `g` form `Boundary-1`. For `g Main Wing`, the measured
importer retains `Main`; the reader warns about this choice. It does not treat
the whole statement as a multiword name. Reverse `g`-to-`o` transitions,
reopened `o` names, empty group statements and multiword `o` names retain
the explicit-sidecar route until their native behavior is measured.

## Prescribed-frame evidence

`Script.frame_motions` records final emitted frame placement, explicit motion
attachments, centers, axes, RPM and time-step inputs. Read it after setup has
finished because a probe can be emitted before its frame is attached to a
motion. Unknown placement or timing carries a reason. Raw commands and
ambiguous attachments do not silently become fixed frames.

A saved record can be passed to
`pyflightstream.script.motion.resolve_frame_motion(record, solver_identity=...)`.
The resolver returns a copy and requires a measured proof matching the actual
executable SHA-256, build, version and length unit. A nominal version alone
does not activate a transform. The bundled METER proof for 26.124 build
8172026 follows the emitted RPM sign and maps STEP to elapsed time as
`STEP * dt`. It is bound to the measured executable digest. The control used
six steps, a 0.00625-second increment and -800 RPM; it established coordinate
and timing conventions, not aerodynamic accuracy. Delayed starts and other
length units remain unproved. Velocity component bases require their own
export-specific proof.

## Simulation geometry controls

A setup preset can declare these optional solver settings:

```toml
[solver]
simulation_length_unit = "MILLIMETER"
vertex_merge_tolerance_m = 0.0002
geometric_edge_bluntness_angle_deg = 90.0
```

The workflow applies the simulation unit after the complete saved-simulation
OPEN or raw-mesh/CAD import, before dimensional frames and edge detection.
METER and MILLIMETER are the measured workflow choices. The source mesh import
unit or CAD metadata still declares its physical size. Changing this setting
does not authorize reinterpreting those input coordinates.

The merge tolerance is a physical distance in metres. The example emits
SET_VERTEX_MERGE_TOLERANCE 0.2 in a millimetre simulation and 0.0002 in a metre
simulation. Its typed bounds require a finite nonnegative distance. The current
workflow emits the setter after geometry, following the command phase contract.
This demonstrates configuration and conversion; it does not establish that the
setter repairs an already imported mesh or that its effect is identical before
and after import. Mesh-repair acceptance remains a separate native measurement.

The geometric-edge threshold accepts 45 through 179 degrees and is emitted
before trailing-edge detection. Its command is documented from 26.122 onward;
the workflow does not silently substitute the older trailing-edge command.
Detection quality and resulting topology must be checked for the particular mesh.

Unstated settings preserve existing behavior: raw mesh/CAD imports default to
METER, and a saved simulation retains its unit. Metre-valued reference origins,
rotor positions and other dimensional inputs are converted once to the selected
simulation unit. [The CAD example](examples/cad_import.md) exercises the typed
route without launching a solver.
records the measured unit domain and negative controls.

## Reference compatibility

Python-authored `ReferenceData` keeps `normalization_units="NATIVE"` by default:
its area and length retain their existing native-unit contract. Set
`normalization_units="SI"` to provide square metres and metres explicitly.
Workspace REF files already name `area_m2` and `chord_m`; their loader now
records SI and the workflow converts once at emission, using the effective
simulation unit at that moment. Raw unit settings therefore do not cause a
second conversion of stored values. Runtime velocity and
`reference_velocity_m_per_s` remain physical m/s in the case and are emitted
in native length units per second. Mach stays dimensionless.
