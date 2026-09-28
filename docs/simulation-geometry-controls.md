# Simulation units and geometry thresholds

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
simulation unit. [The CAD example](../examples/cad_import.py) exercises the typed
route without launching a solver. [RPT-082](../reports/RPT-082_cad-units-and-custom-inflow-coverage_2026-09-27.md)
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
