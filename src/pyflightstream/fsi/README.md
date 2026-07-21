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

### WP1 dry run instructions (licensed machine)

Goal: close the open interface questions with evidence, on half a
revolution of an unsteady propeller case with the Aeroelastic Toolbox
enabled: export cadence and layout of `FS_SurfaceSection_Loads.txt`,
how blades are identified, whether the Toolbox passes arguments or a
specific working directory to the executable, the units setting, and
the exact loads file header (for the parser's SI assertion, FSI-R03).

1. Install with the extra on the licensed machine:
   `pip install -e .[fsi]`, and note the shim path
   (`<venv>\Scripts\pyfs-fsi.exe`).
2. Prepare the unsteady propeller case: surface sections on every
   blade, a structural node list imported, SI units in the Toolbox
   export settings, FSI iterations per time step left at 1
   (FSI-R12), and the FSI executable pointed at the shim path.
3. Seed the dummy in the simulation folder:
   `pyfs-fsi init-dummy --node-count <N> --dir <sim folder>`, with
   `<N>` the imported node count.
4. Run about half a revolution with FSI enabled, then stop.
5. Collect everything: `fsi_archive/`, `pyfs_fsi_calls.log`,
   `FSIDisp.txt`, the FlightStream script and log. If
   `pyfs_fsi_error.log` appears instead, the Toolbox called the
   executable in an unexpected working directory, and that file
   records where; rerun after seeding the dummy config there.

The archived files become committed tier 1 fixtures, and their
sanitized facts (cadence, header, blade labels) close WP1; only then
is the parser (WP2) finalized.
