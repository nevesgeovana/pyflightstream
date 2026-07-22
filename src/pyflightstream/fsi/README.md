# pyflightstream.fsi: structural coupling for rotating blades

Tutorial companion of the FSI subpackage (milestone M6). Each module
gets its section here, written together with the module (FSI-R16).
The coupled tool closes with a user guide; until then this README and
the percent-format examples under `examples/` are the entry points.

## The loop in one paragraph

FlightStream orchestrates the coupling: its Aeroelastic Toolbox calls
an external executable between coupling iterations. Per call the
executable reads the sectional loads FlightStream exported, the run
configuration (`config.json`), and its own persisted state
(`state.json`); solves one beam per blade; converts the solution to
nodal translations; and writes `FSIDisp.txt` for the solver to deform
the mesh. The executable is stateless per call: kill it, restart it,
nothing is lost beyond `state.json`. Everything happens in the
rotating blade frames, so this package never sees azimuth.

Validity boundary, stated up front: the structure is solved
quasi-statically at every step. The mean deformation is exact within
the beam idealization; the azimuthal (1P) content is trustworthy only
where the excitation stays well below resonance, roughly
n Omega / omega_n at or below 0.3. This is a documented property of
the tool, printed in the convergence log header.

## config: one JSON, one hash (`config.py`)

`FsiConfig` is the complete per-run configuration: blade count, Omega,
the per-station structural distributions of the blade, the twist-node
offsets, and the driver phase parameters. It is a pydantic model with
`extra="forbid"`, so a typo in `config.json` fails loudly at load
time, and every validation error names the physical cause (a zero EI
reports that the static solve would be singular, not a bare "value
must be > 0").

```python
from pyflightstream.fsi import FsiConfig, config_hash, load_config
from pyflightstream.fsi.config import dump_config

cfg = load_config("config.json")   # validates on load
print(config_hash(cfg))            # sha256, formatting independent
dump_config(cfg, "config.json")    # canonical pretty print
```

The hash is computed over the sorted, whitespace-free JSON dump, so it
identifies the physics, not the file layout. Every convergence-log row
carries it (FSI-R15): any point of a later parametric map is traceable
to its exact configuration, the same discipline as the run manifest.

Units are SI throughout and encoded in the field names
(`bending_stiffness_n_m2`, `mass_per_length_kg_per_m`). Frames: the
blade frame is right handed with spanwise from root to tip along the
pitch axis and chordwise toward the leading edge. Offsets chain as
pitch axis -> elastic axis (`elastic_axis_offset_*`, used by the load
transfer) and elastic axis -> CG (`cg_offset_*`, source of the
centrifugal bend-twist coupling).

Only synthetic blades appear in tests and examples; real blade
property sets are research data and never enter the repository.

## beam: the blade as a PyNite beam (`beam.py`)

One node per radial station on the elastic axis, one member per bay
with bay-averaged EI and GJ, root clamped. The trick to keep the model
didactic: unit elastic moduli (E = G = 1), so the section constants
fed to PyNite are numerically the stiffnesses of the config, with no
invented cross sections. The structural model is (w, theta), flap plus
torsion; only those degrees of freedom carry mass (lumped tributary
masses, mu l for flap and (I1 + I2) l for twist), and every other DOF
is condensed out of the eigenproblem exactly (Guyan condensation is
exact for massless DOFs). Static solves run linear, or with P-Delta
whenever axial tension is present.

```python
from pyflightstream.fsi import beam

model = beam.build_beam_model(cfg)
beam.apply_station_loads(model, cfg, flap_load_n_per_m=[3.0] * 21)
beam.solve_static(model)
solution = beam.extract_solution(model, cfg)   # (w, theta) per station
modal = beam.modal_frequencies(model, cfg)     # flap/torsion classified
```

WP3 verification (tier 1, `tests/test_fsi_beam.py`): tip deflection,
tip rotation, and the first flap and torsion frequencies of a clamped
uniform beam match the closed forms within 1 percent.

## centrifugal: what rotation adds (`centrifugal.py`)

Two loads on top of the aerodynamic ones, recomputed analytically at
every coupling call:

* Tension: the distributed axial force mu Omega^2 r makes N(r) emerge
  inside the solver, and P-Delta turns it into bending stiffness with
  no manual correction terms.
* Propeller moment: minus Omega^2 (I1 - I2) sin(theta) cos(theta)
  drives every section toward flat pitch. It depends on the total
  pitch, geometric plus elastic, so each call re-solves the beam a few
  times (`solve_rotating_static`) until the twist distribution
  stabilizes; the structural nonlinearity converges implicitly at
  millisecond cost, decoupled from the expensive aerodynamic loop.

The trapeze effect is not modeled, a declared limitation: omitting it
overpredicts elastic twist, which is conservative for relevance
conclusions.

`campbell_sweep` plus `southwell_fit` deliver Gate 1: frequencies
versus rotor speed, straight in the (Omega^2, omega_n^2) plane, with
Southwell coefficients about 1.1 to 1.3 for the first flap mode and
near (I1 - I2) / (I1 + I2) for torsion. Run
`examples/fsi_campbell_diagram.py` for the worked example and the
figure.

Every physics formula lives in a small function whose docstring cites
its source, and a schema test enforces the discipline: the primary
sources of the model are still being verified research side (TSR-014),
so any future correction must stay a localized change.

## loads: what FlightStream hands the structure (`loads.py`)

Per coupling call the post-processing script exports
`FS_SurfaceSection_Loads.txt`; `parse_sectional_loads` turns it into a
typed report using the anchor primitives of `results/` (labels and
header rows, never line offsets). The parser is strict where errors
would be silent:

* SI assertion (FSI-R03): the unit-carrying header labels must be
  present and the footer must read Newtons and Newton-Meter. Anything
  else raises `UnitsError` naming the fix (the post-processing script
  computes with `COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS`), because a
  wrong unit here would silently rescale the structural response.
* Completeness (FR-17): the declared section count, the table
  terminator, and the units footer are structural; a truncated file
  raises instead of returning fewer sections.

```python
from pyflightstream.fsi import loads

report = loads.parse_sectional_loads(text)
blocks = report.split(family_map)            # per-blade attribution
ea = loads.to_elastic_axis(blocks["blade_1"], cfg)
ea.flap_load_n_per_m                          # line densities for the beam
```

Attribution follows the family-per-blade convention (RPT-005 finding
6): the flat export concatenates the section distributions in creation
order, so the code that creates them owns the bookkeeping and emits a
`SectionFamilyMap`. `split` partitions the rows by that map and
cross-checks the geometry: inside a family the offsets march
monotonically along the span, and at a true boundary the offset
restarts or the chord jumps; a map that disagrees with the creation
order fails loudly instead of loading the wrong blade.

Units, settled by the WP7 pilot (RPT-006): the data rows are line
densities along the span ([N/m], [N m/m]) despite the footer naming
the computation unit, so the fields are named `*_per_m`, the beam
consumes them directly, and `cross_check_totals` integrates them over
the tributary widths against the integrated loads of the same run
(the pilot closed to a few percent on the axial component). Moments
arrive about the quarter chord, the pitch axis reference;
`to_elastic_axis` transfers them with the configured e(r)
(M_EA = M_PA + e x F, FSI-R04), so refining the elastic axis estimate
never touches the FlightStream setup. Axes: the export columns are
the cut-plane axes (axial and in-plane on a rotating blade, RPT-006
finding 3); on a spinning configuration `to_elastic_axis` projects
them onto the section chordwise/normal axes with the local blade
angle from the geometric pitch distribution
(`project_rotor_frame_loads`; the export moment is positive
nose-down and flips sign into the nose-up convention). The embedding
rule (`config.frame_embedding`) is shared with the node generator, so
loads and displacements always live in the same triad; at Omega zero
everything passes through unchanged (the wing case).

## kinematics: twist as differential translations (`kinematics.py`)

`FSIDisp.txt` carries translations only, so the elastic twist is
encoded geometrically (DLV-007 Section 4.4): three nodes per station,
one on the elastic axis and one toward each edge at a quarter chord,
and the beam solution maps to their normal translations by rigid
section kinematics, dy = w + theta d. The encoding is linear by
design, so the inverse is exact: w reads back from the elastic-axis
node and theta from the offset-node difference, and the round trip
closes at machine precision (the WP5 acceptance test).

## nodes: one generator, one ordering (`nodes.py`)

FlightStream applies displacements to the imported nodes strictly in
import order, which makes any bookkeeping drift a silent geometry
corruption. `generate_node_layout` is therefore the single source of
truth (FSI-R14): the imported node CSV, the serialized
`NodeOrderingMap`, the flat `FSIDisp.txt` writer, and the reader that
reconstructs (w, theta) for the replay harness all derive from it.

```python
from pyflightstream.fsi import kinematics, nodes

layout = nodes.generate_node_layout(cfg)
nodes.write_node_file(layout, "structural_nodes.csv")   # imported per blade
nodes.write_node_map(layout, cfg.node_map_file)
flat = nodes.flatten_blade_translations(layout, per_blade_translations)
nodes.write_fsidisp("FSIDisp.txt", flat)
```

Every blade shares the same local coordinates in its own rotating
frame, so one node file serves all blades: it is imported once per
blade frame, in blade order, and the FSIDisp rows follow that same
blade-major order. Formats are the dry-run evidence exactly: comma
separated three-column files, no header (RPT-005 finding 5).

On a spinning blade the sections embed at the local blade angle
(`station_triads`: nodes on the actual twisted chord, displacements
along the local suction direction), so the scalar twist encoding
survives untouched while positions and FSIDisp rows live in the rotor
import frame; at Omega zero the embedding is the identity and nothing
changes for the wing case. The map records the embedding and the
blade angles, keeping the round trip exact either way.

## driver and state: the four-phase machine (`driver.py`, `state.py`)

`coupling_step(run_dir)` is one complete coupling call, file-driven:
parse the fresh loads export, assemble per-blade elastic-axis loads,
solve the rotating beam per blade, relax the displacements against the
previous call, write `FSIDisp.txt`, append the convergence log, and
persist `state.json` atomically (temporary file plus rename, FSI-R13,
so a killed call resumes cleanly, which the crash-recovery test
holds it to).

The phase machine is keyed on the step counter, with steps converted
to revolutions from the configured Omega and the time increment. The
loads header prints dt with three decimals only (RPT-006: 0.003525
prints as .004), so a configured `time_increment_s` takes precedence
and the printed value is cross-checked at print precision:

| Phase | Behavior |
|---|---|
| 1, wake development | zero displacements on the rigid blade |
| 2, averaged coupling | loads averaged over the window, relaxed updates (FSI-R07) |
| 3, convergence watch | as 2; tip response logged per revolution, convergence when the tip twist change per revolution drops below tolerance (FSI-R09) |
| 4, recording | instantaneous loads, lambda = 1 by design, twist recorded per step |

Freshness is asserted, not assumed: every call must see an advancing
solver iteration in the loads header; a repeated iteration means
FlightStream is running more than one FSI iteration per time step and
the driver refuses to continue (`SET_AEROELASTIC_ITERATIONS` must stay
1, FSI-R12). The node layout is regenerated from `config.json` on
every call and any staged map must agree with it (FSI-R14).

Frozen mode (FSI-R10) is first class: drop a
`fsi_frozen_displacements.txt` into the run folder and every call
replays it verbatim, no loads, no solve, for sensitivity runs and
Gate 2.

The convergence log (`fsi_convergence_log.csv`) states the
quasi-steady validity boundary in its header and carries the config
hash on every row (FSI-R15), so any point of a later parametric map is
traceable to its exact configuration. The whole machine runs offline
in the tier 1 replay harness (`tests/test_fsi_driver.py`), fed by the
archived WP1 fixtures, no FlightStream in the loop.

## cli: the executable FlightStream calls (`cli.py`)

`pyfs-fsi` is the console entry point; pip installs it as an `.exe`
shim under the environment's `Scripts/` folder, and that path is what
the FlightStream script sets as the FSI executable
(`SET_MOTION_FSI_EXECUTABLE` family, SRC-003 pp.335-336). Today it
implements the WP1 dummy: called bare, it executes one coupling step
that writes zero displacements (the blade stays rigid) and archives
every interface file it sees under `fsi_archive/call_NNNN/`, plus a
directory listing and a call log. The dry run therefore collects the
real fixtures the loads parser (WP2) will be written against.

### WP1 dry run: findings and the working recipe

Executed 2026-07-21 on 26.120 build 7012026 with the generic blade
case over half a revolution; full evidence in
`reports/RPT-005_fsi-dry-run_2026-07-21.md`, fixtures in
`tests/fixtures/fsi/`. What the run established:

* The implemented scripting interface is the Aeroelastic Coupling
  Toolbox family (SRC-003 pp.375-376; `aeroelastic_coupling.yaml` in
  the command database). The `SET_MOTION_FSI` pair of the motion
  chapter is rejected as unrecognized by the build: stale manual
  section, tracked as candidate broken (PLN-019).
* The executable is called bare, no arguments, once per time step,
  with its working directory equal to
  `SET_AEROELASTIC_WORKING_DIRECTORY`; its console output lands in
  `FSI_output.txt` there.
* `FS_SurfaceSection_Loads.txt` is produced by the post-processing
  script FlightStream runs between FSI iterations, before the
  executable: `UPDATE_ALL_SURFACE_SECTIONS`,
  `COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS`,
  `EXPORT_SURFACE_SECTIONAL_LOADS` with the path on its own line.
  Fresh content each step (advancing solver iteration counter in the
  header); standard header with units in the labels, so the WP2 SI
  assertion anchors on labeled values; data rows carry per-section
  offset, chord, quarter-chord position, Fx, Fz, and the moment
  about the quarter chord (the pitch axis reference).
* File formats: structural node import and `FSIDisp.txt` are both
  comma separated three-column files, displacement order equal to
  node import order (SRC-003 pp.273-274).
* Blade attribution, by the author's standing convention: every
  blade is meshed as its own geometry family, and each blade gets
  its own section distribution targeting that boundary in the
  blade's rotating frame. The export concatenates the families as
  one flat table in creation order (block sizes equal to each
  family's section count), so attribution is bookkeeping owned by
  the code that creates the distributions; offset and chord jumps
  at the block boundaries are the cross-check.

Working setup, in script form: assign the blade boundaries and the
rotating blade frames to the toolbox, import the node list in the
blade frame, set the working directory, the post-processing script,
the execution command (the `pyfs-fsi` shim path), iterations 1
(FSI-R12), coupling in unsteady ENABLE, then start the unsteady
solver. Seed the dummy first with
`pyfs-fsi init-dummy --node-count <N> --dir <working directory>`.

The loads parser (WP2) and the twist-encoding node machinery (WP5)
are built against these fixtures; see their sections above. The
coupled driver (WP6) will replace the dummy step behind this same
entry point.
