# FSI workspace inputs

The [workspace calibration example](examples/workspace_fsi_calibration.md) creates
complete calculated and supplied inputs for the same synthetic solid blade, then
checks their equivalence with one explicit matrix factor.

Place one structural configuration in `inputs/fsi/f001.toml`. A matrix row selects
it in `VAR_NAMES_VALUES`:

```text
FSI: f001 / FSI_BENDING_STIFFNESS_N_M2_FACTOR: 1.15
```

The resolver attaches the effective `FsiConfig` and provenance to the case. The
existing run writer places `config.json` and `fsi-provenance.json` in the point's
working directory and records both hashes. The source artifact is also hashed;
changing it after resolution requires planning again. The geometry library is
never used as a destination for these generated files.

This configuration uses the existing solid homogeneous Euler beam. It adds no
shell, spar, hollow-section, shear-center or second structural model.

## Which workflows accept FSI in 0.30.0

| Workflow | FSI in this release |
| --- | --- |
| `unsteady_rotor` | Refused by the plan: FSI on unsteady_rotor is still in debug on this release (the morph is applied to the un-rotated blade, reported to the vendor). |
| `steady`, `unsteady` without rotor motion | Accepted: the fixed-wing route (FSI-G), [below](#fixed-wing-fsi). |
| `qsteady_rotor` | Accepted on a periodic SECTOR: the rotating blade at the row's speed, [below](#quasi-steady-sector-fsi), through the structural nodes or, on 26.125, by [direct mesh morphing](#direct-mesh-morphing-0370). Refused on a whole wheel. |

On 26.124 a mapped rotating blade is morphed at its imported azimuth: after
each structural call the surface is the un-rotated blade carrying the
displacement, and the next time step restores the rigid rotated blade. The
morph replaces the rotation instead of composing with it, so no coupled rotor
number of that route is a rotor result. RPT-025 carries the dated correction
of the earlier reading. The rotor wiring below is kept, tested, and closed by
the plan until the route is released.

## Quasi-steady sector FSI

A `qsteady_rotor` row with `SYMMETRY PERIODIC` (one blade meshed, its free
stream turning about the shaft at the rotor's speed) couples that blade on the
steady route. The blade is held still; the STRUCTURE turns: the configuration
the run stages as the point's `config.json` takes `omega_rad_per_s` from the
row, `|RPM| pi / 30`, the speed its free stream turns at, whatever the FSI
input wrote (an input stating another non-zero speed is warned, the row's
wins; `fsi-provenance.json` records the move), so an RPM sweep couples each
point at its own speed. Each coupling call solves the rotating blade under
the loads of the solve before it: the centrifugal tension and its
stiffening, the propeller moment and the in-plane centrifugal softening, with
the configured `coupling_relaxation` on every call. The run folder is marked
`fsi_quasi_steady_rotor`, which routes the structural program to that steady
rotating solve; a steady export on a rotating configuration is refused without
it.

What the route fixes, as the fixed-wing route does: the blade's boundary ID,
the structural nodes placed inside its sections, the `MULTI_QUADRATIC`
kernel, at most 50 coupling iterations, the row's whole export block in the
aeroelastic post-processing script, `EXECUTE_AEROELASTIC_ANALYSIS` last and
the process stopped after the solver prints that the analysis ended.

Because the blade does not move, its frame is the one it was meshed in, and
the scripted import stores the structural nodes in the reference frame. So
the route couples blade one at azimuth 0 with its datum on Z, on a shaft
along X through the origin (where the rotor blade frame, x the shaft and z
the span, is the reference frame), with `blade_count = 1` and one section
distribution over blade one cut on XY in a frame the run created that
coincides with the reference (the rotor's hub frame, `SMRP`, at the origin).
Anything else is refused, named, rather than converted. A sector turning at
0 rev/min is refused: the route exists to apply the centrifugal loads.

### Direct mesh morphing (0.37.0)

On a build that runs it (26.125), the sector can be coupled by the solver's
direct mesh morphing instead of the structural-node import. The FSI input
states it in its `[config]` table:

```toml
[config]
blade_count = 1
omega_rad_per_s = 0.0
morphing = "direct"
```

The script then emits `SET_DIRECT_AEROELASTIC_MESH_MORPHING <frame> RIGID`, in
the frame the blade's sections are cut in, in place of
`IMPORT_AEROELASTIC_STRUCTURAL_NODES` and its node file; every other line, and
every staged file, is the mapped route's, and the staged `config.json` carries
`"morphing": "direct"`. Before each structural call the solver writes
`FSInodes.txt`, the blade's surface vertices at their undeformed positions
(RIGID), one row each with its normal and force. The structural program writes
one displacement per row back to `FSIDisp.txt`, in that order: the beam
solution at the vertex by the rigid-section kinematics the mapped route encodes
at its three nodes per station (the flap along the section normal, plus the
twist times the vertex's chordwise distance from the elastic axis), blended
linearly between two stations and held at the end station beyond the first and
the last, relaxed as on the mapped route. The displacements are totals from the
undeformed surface: on 26.125 two coupling cycles moved the surface by exactly
what was written (RPT-155). A call with no `FSInodes.txt`, or whose node list
changed length since the previous call, is refused. Its declared node count
must match the complete table, and every node row must contain nine finite
numbers. A truncated or malformed row refuses the call rather than shifting
the displacement rows onto different vertices.

Refused by the plan, each naming the remedy: `morphing = "direct_deflected"`
(DEFLECTED nodes: from the second coupling cycle the solver applied the written
displacements to the surface already deflected, RPT-155); `"direct"` on
`unsteady_rotor` (the morph of the rotating blade lands at the azimuth it was
imported at), on `steady` and `unsteady` (a fixed wing couples through its
structural nodes), on a wheel, and on a build that does not run the command
(26.124 does not recognise it, RPT-154). Leaving `morphing` out, or stating
`"mapped"`, is the route of 0.36.0, byte for byte.

## Fixed-wing FSI

A `steady` row, or an `unsteady` row with nothing turning, couples a fixed
wing. The FSI input states `[config.wing]`, and the structure is then one wing
clamped at its first station:

```toml
mode = "calculated"
material = "ti-6al-4v-grade5-annealed"

[config]
blade_count = 1
omega_rad_per_s = 0.0

[config.wing]
self_weight = true
gravity_m_per_s2 = [0.0, 0.0, -9.80665]
span_axis = "+Y"
origin_m = [0.25, 0.0, 0.0]

[sections]
station_radii_m = [0.0, 2.0, 4.0]
chord_m = [1.0, 1.0, 1.0]
geometric_pitch_deg = [0.0, 0.0, 0.0]
geometry_source = "Synthetic lens sections about the quarter chord, in metres"
sections_m = [
  [[0.25, 0.0], [0.0, 0.06], [-0.25, 0.08], [-0.75, 0.0], [-0.25, -0.08], [0.0, -0.06]],
  [[0.25, 0.0], [0.0, 0.06], [-0.25, 0.08], [-0.75, 0.0], [-0.25, -0.08], [0.0, -0.06]],
  [[0.25, 0.0], [0.0, 0.06], [-0.25, 0.08], [-0.75, 0.0], [-0.25, -0.08], [0.0, -0.06]]
]
```

- **The stiffness and mass along the span** come from the same section and
  material tooling a calculated blade uses: `[sections]` gives one closed
  contour per station, in metres, chordwise toward the leading edge and normal
  toward the suction side, about the wing's pitch axis. A supplied
  configuration states the distributions under `[config.blade]` instead. The
  stations are distances along the span from `origin_m`, the reference-frame
  point on the pitch axis; `span_axis` is `+Y` for a right wing and `-Y` for a
  left one. The package's frame is x aft, y right, z up, so a station's
  section axes are -x and +z, turned nose up by its `geometric_pitch_deg`.
- **The loads** are the aerodynamic sectional loads the solver exports, plus
  the wing's own weight: the running mass under `gravity_m_per_s2`, a vector of
  the reference frame, -z at standard gravity by default. The angle of attack
  and the sideslip turn the free stream, never the body, so they never turn
  gravity; a model mounted in another orientation states its own vector. With
  its centre of gravity off the elastic axis (`cg_offset_chordwise_m`,
  `cg_offset_normal_m`), the weight twists the section too. A wing at rest has
  no centrifugal load, and none is applied: a `[config.wing]` configuration
  stating a speed, or more than one structure, is refused.
- **`self_weight = false`** removes the weight, for a wind-tunnel model whose
  weight the balance and the support carry. It is on by default.
- **The sections the loads come from** are one distribution of the row's
  pproc, over the wing's one family, on the XZ plane, in a frame with the
  reference axes whose origin sits on the wing's `origin_m` along the span.
  The MRP frame of a reference whose moment point is on that plane is one:

  ```toml
  [sections]
  count = 40
  include_symmetry = false

  [[sections.distributions]]
  families = ["Wing"]
  frame = "MRP"
  planes = ["XZ"]
  ```

  Another distribution, another plane or a frame elsewhere is refused rather
  than converted. The surface list holds the family's boundary ID, the nodes
  are placed inside the wing's sections and stored in the reference frame,
  and the kernel is `MULTI_QUADRATIC`, as below.
- **A steady row** ends its script at `EXECUTE_AEROELASTIC_ANALYSIS`, with at
  most 50 coupling iterations; the solver stops the loop itself once its
  displacement residual converges. The row's exports all run in the
  aeroelastic post-processing script, after the loads the structural call
  reads, so the files left after the run are those of the last coupling
  iteration. Each point is its own process, and a local run stops the solver
  once it prints `Aeroelastic solver run time`; a submitting executor refuses
  such a script, because the process never exits by itself. The probe points,
  the pproc's volume section and the loads selections are refused on this
  route.
- **An unsteady row** couples once per time step inside the march
  (`SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE`, one coupling iteration per
  step) and writes the deformed surface, `fsi_surface.vtk`, after every
  structural call; the row's own exports stay at the end of the march.
- Each structural call solves the clamped beam once and relaxes the written
  displacement by `phases.coupling_relaxation` (0.4 unless the configuration
  states it). Its row in `fsi_convergence_log.csv` states the phase
  `fixed_wing`.

The convergence log `fsi_convergence_log.csv` of every route keeps the
columns it had in 0.33.0 and ends with `tip_flap_signed_m` (0.34.0): the tip
flap deflection in metres with its sign, the sign the displacement file
`FSIDisp.txt` carries, positive along the section's normal toward the
suction side, so a wing bending down under its own weight reads negative.
`tip_flap_m` stays its magnitude; on a rotor both name the blade of largest
magnitude. A frozen replay leaves both empty.

`CDo`, the profile drag coefficient of the loads export, reads zero in a
coupled run because the solver prints it so. On 26.124 (reports/RPT-128, the
fixed-wing route) the spreadsheet exported at the head of a coupled point's
one pass of the aeroelastic post, before the post updates anything and
before the structural call, already reads zero, where the rigid solve of the
same wing reads 0.0098384. The package's order of operations does not cause
it, and nothing the package emits changes for it.

The export's moment column of an XZ cut is read as positive about +y, which
is nose up on either wing, by analogy with the blade's XY cut. On 26.124
(reports/RPT-092) the route converged and mapped 1052 of 1052 vertices, and
on that symmetric NACA 0012 wing the reading agrees in sign at the integral
(+7.49 against +17.13 N m) and not in magnitude (44 percent), which a symmetric
section cannot decide. On the cambered NACA 4412 wing of reports/RPT-128 the
magnitude is confirmed: the summed cut moments are 1.00825 of the solver's
moment about the same line, at least as close to 1 as the summed cut forces
are to the lift (0.99033), and the coupled point gives the same verdict
(1.00791 and 0.99045). The
offline tests hold the emitted script, the weight against the cantilever's closed form
q L^4 / (8 E I) and the absence of any centrifugal term.

## Automatic workspace coupling

Selecting `FSI: f001` on an `unsteady_rotor` row prepares the existing
driver's complete input interface (refused in this release, above). Planning derives the node CSV and
ordering map from the effective configuration, resolves blade boundaries and
rotating frames, and records the emitted section-load order in
`fsi_family_map.json`. The run writer stages and hashes these files, the native
loads-export callback and the Python callback beside `config.json`.

The native script imports one identical blade-local node file per blade, in
blade order, assigns those boundaries/frames, keeps
`SET_AEROELASTIC_ITERATIONS 1` and enables coupling before ordinary
`START_SOLVER`. Each synchronous callback refreshes the sectional loads in
Newtons and invokes the existing `pyfs-fsi` step. The interpreter is the one
preparing the run, with its existing `pythonw.exe` sibling on Windows. The
package must remain available to that interpreter on the execution host.

The initial automatic route is deliberately bounded:

- A fresh OBJ/STL mesh import creates `NEW_SIMULATION`; the selected native
  length unit must be `METER`. Saved-FSM section inheritance and other node-file
  units are not yet established for this adapter.
- Exactly one moving rotor resolves to all of its explicit blades. Periodic or
  mirror symmetry, missing blades and ambiguous rotor selection are refused.
- The existing structural `rotor_frame` convention requires shaft X and blade
  datum Z. The declared geometry and structural pitch must describe that same
  physical blade; this adapter does not infer a new basis or re-pitch the mesh.
- Exactly one XY section distribution per blade must be emitted in blade order,
  each in that blade's own rotating frame. Duplicate cuts, aggregated families,
  other planes or additional distributions are refused instead of attributed
  to the first matching blade.
- Positive structural angular velocity must match the resolved row's speed;
  a declared structural time increment must match the solver clock. Raw
  commands/custom flags that could alter the mapping are not accepted on this
  initial automatic route.
- Zero-speed coupling and continuation are named refusals. Continuation
  needs compatible structural state and inherited section-order evidence;
  creating fresh maps beside a stopped run would not establish that evidence.

For example, the corresponding pproc entry for a one-blade rotor whose family
is `Blade1` is:

```toml
[sections]
count = 50
include_symmetry = false

[[sections.distributions]]
families = ["Blade1"]
frame = "LOCAL_AXIS"
planes = ["XY"]
```

For multiple blades, select the rotor's blades so LOCAL_AXIS expands them in
the declared blade order. The structural `blade_count` must include every
explicit blade. A separate `[settings.aeroelastic]` table is not required.

The existing [FSI tutorial](fsi-tutorial.md) remains the manual interface for
other carefully configured native cases. `pyfs-fsi step --dir /absolute/path`
executes one driver call when current loads and maps already exist. Outputs
`FSIDisp.txt`, structural state, convergence logs and per-call archives remain
in that point directory. Stale solver iterations are refused. Changing a
calibration requires a new resolved point and regenerated nodes.

### What the coupled route fixes itself

These pieces are shared by every coupled route
(`pyflightstream.cases.fsi_workspace`):

- **The surface list holds the boundary ID.** The solver stores
  `ASSIGN_AEROELASTIC_SURFACES` as written and maps the boundaries whose ID
  matches, while a script cites a boundary by its position in the geometry
  tree. An OBJ import numbers its boundaries from 2, an STL import from 1, so
  an OBJ blade at position 1 is surface 2, the ID its motion holds. Any other
  geometry is refused rather than guessed: a wrong ID maps no vertex, in
  silence.
- **The structural nodes sit inside the blade.** When the configuration
  carries the blade's sections (a calculated blade does; a supplied blade may
  state `section_contours_m` under `[config.blade]`, one closed polygon of
  chordwise and normal metres per station), the nodes are placed on each
  section's camber line: the elastic-axis node at the configured elastic
  axis's chord fraction (30 % when that lies outside 20 to 50 %), the
  leading-edge and trailing-edge nodes at 10 % and 90 %. The plan refuses a
  node set with any node outside its section, or inside it by less than
  max(1 mm, 10 % of the local thickness), naming the node. Node order, roles
  and row count do not change, so the FSIDisp rows keep their meaning. A
  supplied blade without sections keeps the offset layout, which is not
  checked: there is no geometry to check it against.
- **The morphing kernel is `MULTI_QUADRATIC`** unless the row's setup states
  `aeroelastic_rbf_type`. The package's structural nodes are a beam line, and
  on one beam line `WENDLAND_C2` delivered 64 % of an imposed bend at the
  leading edge and 1.4 % at the trailing edge, a nose-up shear of up to
  14 deg, and the coupled run diverged; `MULTI_QUADRATIC` delivered the bend
  to 3 mm.
- **The node frame.** On 26.124 `IMPORT_AEROELASTIC_STRUCTURAL_NODES` does
  not store its frame argument: the saved node block always states the
  reference frame. A route whose nodes must turn with the blade saves the
  built simulation, patches that one field to the rotating frame's index
  (`patch_structural_node_frame`, which changes that field and nothing else)
  and opens the patched file. One node block holds one frame, so a rotor with
  one rotating frame per blade cannot be stated this way.
- **Exports that must show the deformation run in the aeroelastic
  post-processing script.** In unsteady the solver runs it twice per step,
  before the structural call and after the morph, writing the same file
  names, so the file left after a step is the deformed one. A Tecplot or VTK
  surface export carries the morphed vertices; a triangulation export and
  `SAVEAS` keep the reference ones.
- **A steady coupled script ends at `EXECUTE_AEROELASTIC_ANALYSIS`.** In a
  script the analysis returns at once: an export after it runs before the
  analysis iterates, and a `CLOSE_FLIGHTSTREAM` after it ends the analysis.
  The exports go in the post-processing script, which the solver runs after
  every coupling iteration, the last one included, and the run is complete
  when the solver prints `Aeroelastic solver run time`, after which its
  process is stopped.

The rotating structural solve includes the in-plane centrifugal softening
of the flap, mu Omega^2 sin^2(beta) w: a flap along the section normal at
pitch beta moves the section in the rotor plane, where the centrifugal field
pulls it outward. It iterates with the twist in the same inner loop.

These wiring checks do not establish native two-way rotor deformation,
convergence or aerodynamic validity. The native interface evidence includes
callbacks with unsteady coupling enabled, but an undeformed final saved node
state; the older rotary-boundary morphing limitation is also retained in the
[FSI tutorial](fsi-tutorial.md). Saved-FSM/continuation usability and native
coupled validation remain open release acceptance work, not an implied success
from staging or command acceptance. The supplied zero-omega examples below are
valid structural inputs for offline checks, not runnable coupled rotor rows.

## Supplied distributions

Use `mode = "supplied"`, put existing `FsiConfig` scalars under `[config]`, and
put the complete existing `BladeProperties` arrays under `[config.blade]`.
Station radii are metres, strictly increasing, and all arrays have the same
length. Mass per length is kg/m; EI and GJ are N m²; principal mass inertias per
length are kg m. The existing config validators check finite values, station
counts, positive mass/stiffness/chord and nonnegative principal inertia.

```toml
mode = "supplied"

[calibration]
bending_stiffness_n_m2 = 1.05

[config]
blade_count = 2
omega_rad_per_s = 0.0

[config.blade]
station_radii_m = [0.1, 0.5]
chord_m = [0.04, 0.04]
mass_per_length_kg_per_m = [1.0, 2.0]
inertia_major_kg_m = [0.001, 0.002]
inertia_minor_kg_m = [0.0001, 0.0002]
bending_stiffness_n_m2 = [10.0, 20.0]
torsion_stiffness_n_m2 = [5.0, 10.0]
elastic_axis_offset_chordwise_m = [0.0, 0.0]
elastic_axis_offset_normal_m = [0.0, 0.0]
cg_offset_chordwise_m = [0.0, 0.0]
cg_offset_normal_m = [0.0, 0.0]
geometric_pitch_deg = [0.0, 0.0]
```

The example distributions are synthetic, not a material or airframe dataset.
With the row factor `1.15` above, effective EI is `[11.5, 23.0]`; it is not the
product of the file's `1.05` and the row's `1.15`.

## Calculated solid sections

`mode = "calculated"` reads section contours and the established material
dataset. The section coordinates are chordwise/normal metres about the pitch
axis; `sections_m` contains one closed polygon per station. The existing section
integrator computes area, centroid, principal inertias and the Prandtl torsion
constant. Do not also provide `[config.blade]` in this mode.

```toml
mode = "calculated"
material = "ti-6al-4v-grade5-annealed"

[config]
blade_count = 2
omega_rad_per_s = 0.0

[sections]
station_radii_m = [0.1, 0.5]
chord_m = [0.04, 0.04]
geometric_pitch_deg = [0.0, 0.0]
geometry_source = "Synthetic rectangular sections in SI units"
torsion_grid_cells = 16
sections_m = [
  [[-0.02, -0.002], [0.02, -0.002], [0.02, 0.002], [-0.02, 0.002]],
  [[-0.02, -0.002], [0.02, -0.002], [0.02, 0.002], [-0.02, 0.002]]
]
```

The existing Grade 5 dataset retains its source, annealed condition and tabulated
shear modulus. Calibration never rewrites the source material database. A custom
`[material]` table instead states every `Material` field and a `[material.source]`
table with `document`, `table`, `condition`, `url` and `consulted`. The material
checks require finite positive density/E/G and `-1 < poisson_ratio < 0.5`.

## Calibration and provenance

Every factor is dimensionless, finite and positive. Omission selects the file
factor or unity. An explicit matrix value, including `1.0`, replaces the file
factor exactly once. The accepted property names are:

| Level | Names |
| --- | --- |
| Supplied or calculated distributions | `mass_per_length_kg_per_m`, `inertia_major_kg_m`, `inertia_minor_kg_m`, `bending_stiffness_n_m2`, `torsion_stiffness_n_m2` |
| Structural orientation | `geometric_pitch_deg` |
| Existing offsets | `elastic_axis_offset_chordwise_m`, `elastic_axis_offset_normal_m`, `cg_offset_chordwise_m`, `cg_offset_normal_m` |
| Calculated material only | `density_kg_per_m3`, `youngs_modulus_pa`, `shear_modulus_pa`, `poisson_ratio` |

The pitch factor scales each signed structural angle in degrees once; zero stays
zero. For example, file factor `2.0` replaced by
`FSI_GEOMETRIC_PITCH_DEG_FACTOR: 1.5` maps `[-60, 20]` to `[-90, 30]`,
not `[-180, 60]`. It changes the spinning beam section orientation used to
generate structural nodes and project loads, while retaining the section
properties, radii and node order. It is not an angular offset and does not
rotate the section contours again or re-pitch the aerodynamic mesh. Keep the
aerodynamic geometry consistent with the intended structural orientation and
regenerate the node file and ordering map from the effective configuration.
This parameter alone does not establish coupled aerodynamic validation.

A matrix key is `FSI_` + the uppercase property name + `_FACTOR`. Source and
derived calibration on the same dependency is refused: density plus mass or
mass inertia, E plus EI, or G plus GJ. For isotropically derived G, E/Poisson
calibration also cannot be combined with a separate G or GJ calibration. The
legacy `config.stiffness_scale_factor` must be unity in workspace artifacts.

When the source tabulates G, changing E or Poisson ratio preserves that tabulated
G. Only a material declaring isotropically derived G follows E / (2 (1 + nu)).
The two contracts remain distinct even with unity calibration.

`fsi-provenance.json` contains the source path/hash, unscaled config, effective
config, every factor and whether it came from unity, file or matrix. Calculated
inputs also retain base/effective material properties and the section algorithm
provenance. Effective properties are validated again, including the ordering of
major and minor principal inertia. No solver executes while loading or planning
these inputs.
