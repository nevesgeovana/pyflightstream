# Setup standards and guidance

Generate the guide and standard setup library while planning:

```console
pyfs-matrix plan matrix.fs --workspace . --fs-version 26.123 --setup-guidelines --setup-standards
```

Both flags work independently. Generation requires an explicit `--fs-version` so
each availability statement names its target build. The files go to the plural
`inputs/setups` directory. The guide is `SETUP_GUIDELINES.md`; `s900` through `s908`
are scenario starting points and explicit study baselines. `s910` through `s956`
vary one setting relative to the baseline named in that file: `s900` for steady
attached flow, `s904` for unsteady controls, `s905` for transonic refinement, or
`s906` for laminar-separation sensitivity. The matrix's `SET` column selects the
setup identifier as usual.

The low-cost baseline assumes low-Mach attached flow and a fully turbulent boundary
layer. The coupled, rotor and transonic examples require the corresponding physics
and workflow. They are starting points for comparisons, not calibrated predictions
or a promise that enabling more controls improves accuracy. Single-setting values
are illustrative study choices. Boundary examples carry `Wing` and `Body` labels;
replace those labels and illustrative diameters with your actual geometry before
planning. Fields ending in `_families` use family selectors; the other boundary
lists use declared boundary labels or one-based indices.

Each preset comments every typed setup key, the chosen override or omitted state,
documented defaults and command evidence. The guide also inventories command
arguments. A control unavailable in the target command database is commented
`UNAVAILABLE` rather than emitted. Such a file is not a test of that control.
Select an evidenced build or a supported model-assignment route. For example,
newer builds select Valarezo within an airfoil separation assignment rather than
through the legacy global toggle:

```toml
airfoil_separation = [{name = "Wing", boundaries = ["Wing"], valarezo_criterion = true}]
```

The existing command database still refuses unsupported or broken emissions.
Documented syntax, successful parsing, usable native operation and validated
aerodynamics are different evidence claims. The generator executes no solver.
The bibliography explains physical assumptions; it does not establish native
command compatibility. Roughness is not simply an early transition trip, and a
pressure-difference threshold calibrated at one Reynolds number, Mach number and
geometry is not a universal stall model.

Generation reports `created`, `unchanged`, or `preserved` for each destination.
Existing differing files, including user-owned s9XX collisions, are never
overwritten. To compare a new package's definitions without disturbing edits,
generate into a separate workspace and review the differences. Generation happens
before normal matrix planning, so created files remain if a subsequent matrix
check fails. Review the printed statuses and the normal plan result.

`s907` combines viscous coupling and an airfoil-separation assignment. `s908`
combines laminar and airfoil separation as an explicit interaction hypothesis,
not an established recommendation. Compare their separate effects first.

## Inspect the resolved setup

`pyfs-matrix inspect-setups MATRIX.fs --workspace CAMPAIGN --fs-version 26.124`
prints complete per-row JSON: typed settings, whether each value came from the
setup or a package default, row NCPUS overrides, command evidence, reference
aliases and frames, custom flags, raw commands, and raw-mesh boundary conditions.
The ordinary `plan` command prints a concise view from those same records and
stores them under `setup_inspections` in `post/<matrix>/plan.json`. Point-dependent
quantities and native defaults not established by evidence are not guessed.

## Velocity, Mach and coefficient normalization

`freestream_input = "velocity"` preserves the normal velocity setter. Selecting
`freestream_input = "mach"` instead emits `SOLVER_SET_MACH_NUMBER` using the Mach
already resolved from the row's flight condition. It introduces no second Mach
value in the setup. The inspection record includes this choice.

Mach mode requires the resolved velocity, Mach and sound speed to agree. On
builds whose fluid command takes the heat-capacity ratio, the sound speed must
also agree with `sqrt(gamma * pressure / density)` and the emitted temperature
using the package's canonical dry-air gas constant. The native manual states that
modern sonic velocity follows temperature and specific-heat ratio (26.120 User
Guide, p.328). Missing fluid data, an
inconsistent independent sound-speed pin, or a conflicting sonic override is
refused before settings emission. Use velocity mode to preserve such independently
specified states; switching the native setter must not change the physics.

Coefficient normalization is a separate choice: `reference_velocity_m_per_s`,
`reference_mach`, or the explicit `disable_reference_velocity = true` reset.
Only one may be stated. With none present, the existing freestream reference
velocity remains explicit. On 26.124/build 8172026, the measured reset changed
a held 47.513 m/s reference to the 30 m/s freestream and then followed a subsequent
40 m/s freestream change. The saved override flag changed from true to false.

The same build, at Mach 0.13, temperature 288.15 K and gamma 1.4, saved
44.2381515552 m/s through the Mach setter versus 44.2382184434 m/s through the
velocity setter. The 1.51 ppm difference falls inside the 2 ppm acceptance bound
for this control only. Mach and fluid inputs are not adjusted to hide native
rounding, and this single measurement is no general precision guarantee.

## Multiple actuator discs

Keep the existing flat ACTUATOR keys for one disc, or use ordered brace records
in the existing free-variable cell:

```text
ACTUATOR: {ACTUATOR: Left / ACTUATOR_RPM: 2000 / ACTUATOR_THRUST: 100}, {ACTUATOR: Right / ADVANCE_RATIO: 0.5 / ACTUATOR_THRUST: 200}
```

Each name selects its own reference actuator block. An advance ratio uses that
block's diameter and the point velocity; RPM and loading belong to that record.
`PROFILE: <stem>` selects a separate radial profile instead of net thrust, and
requires the reference block's blade count. Every converted native profile is
written and hashed. Do not mix brace records with flat actuator loading keys.
Duplicate disc names and unknown record keys are refused. This syntax and its
emission are checked offline; native multi-disc operation requires its own test.


The reference block may additionally choose `wake_type = "RIGID"` or
`"RELAXED"`. Omission preserves the native default. `thrust_units` selects
`NEWTONS` (the existing default), `POUNDS`, or `COEFFICIENT` for that block's
`ACTUATOR_THRUST` value; profile-file force units remain `profile_units`.
The coefficient convention is native and must match the intended formulation;
dimensional thrust avoids that ambiguity (FlightStream User Guide, p.187).
These newly exposed variants require the separate native controls recorded by
this release; their typed acceptance alone is not proof of a wake or load effect.

A setup can request explicit lifecycle actions after the row creates its discs:

```toml
[[actuator_operations]]
op = "rename"
actuator = "Left"
name = "LeftCruise"
[[actuator_operations]]
op = "enable"
actuator = "LeftCruise"
```

These tables belong at the root of an s<> setup. `delete` removes one named disc. Each action uses the
name at that step, and deletion updates subsequent numbering. Unknown or
ambiguous names and duplicate rename destinations are refused. A missing action
never deletes or disables anything. `disable` is retained only on builds that
document that command; current builds refuse it through the command registry.
Saved actuators can be edited by these actions, but mixing new discs with a saved
actuator inventory retains its existing explicit refusal.

## Uniform inlet and outlet boundaries

Geometry, setup and conditions have separate owners. The geometry sidecar
identifies the physical surfaces:

```toml
# inputs/geometries/duct/duct.boundaries.toml
boundaries = ["Inlet", "Outlet", "Wall"]
[import]
units = "METER"
[trailing_edges]
none = true
[ports]
feed = "Inlet"
exit = "Outlet"
```

The setup selects which geometric ports act as inlet or outlet:

```toml
# inputs/setups/s020.toml
apply_trailing_edges = true
apply_wake_termination = false
apply_base_regions = false
[[ports]]
port = "feed"
kind = "inlet"
velocity_variable = "FEED_VELOCITY"
# profile_variable = "FEED_PROFILE" # optional file selected by MATRIX
[[ports]]
port = "exit"
kind = "outlet"
velocity_variable = "EXIT_VELOCITY"
```

The row's MATRIX free cell supplies `FEED_VELOCITY: -10 / EXIT_VELOCITY: 10`.
An omitted `velocity_variable` selects `<PORT>_VELOCITY` with the identity
uppercased. An omitted `profile_variable` requests no profile. Selecting one
requires that MATRIX variable to name a file under `inputs/profiles/`.
No numeric condition or profile filename is copied into the geometry or setup.
The workspace example and emitted commands are tested in
`test_boundary_artifact_separation.py`.

The surface names are exact after import renames. Velocity values are passed
unchanged in simulation velocity units. The current manual is inconsistent:
the command text describes signed normal velocity, but the GUI note on p.189
says direction follows the boundary type and signs are unnecessary. The negative
inlet above is an explicit test input; the native control compares it with a
positive inlet. Neither direction is claimed verified from parser acceptance.
Setup array order is preserved across both port kinds. `none = true` excludes marking
or detection and produces a no-wake warning; it cannot request wake termination
nodes. The generator `tests/tier3_licensed/duct.py` reproduces the synthetic duct
locally; its boundary controls remain in `tests/tier3_licensed/inputs/duct`.
These are controlled test inputs, not a validated duct-flow result.

An inlet may select `profile_variable = "FEED_PROFILE"` in its setup and
`FEED_PROFILE: inlet-profile.txt` in MATRIX.
The reader hashes the file, building refuses later changes, and the run stages
and hashes its exact bytes. FlightStream User Guide supplied with 26.123/26.124,
printed/PDF p.190, defines comma-separated `x,y,z,Vmag` rows mapped to the inlet.
No actuator-profile conversion is applied. The command uses the inlet sequence
index, independently of the mesh boundary index. Native profile mapping and the
velocity-sign discrepancy remain explicit acceptance checks.

The GUI discusses outlet profiles, but the scripting reference supplies no
outlet-profile setter; a setup requesting one is refused by name. Port
remeshing is explicit through `[ports.remesh]`; it runs
after port creation and before profile assignment. On the measured 26.124 build, remeshing an outlet after an inlet requires
its position in the combined created-port sequence. The paired native control
increased the target cap from two to 28 triangles while retaining its area and
the other boundaries. This establishes mesh editing, not a solved port flow.
The GUI exhaust-outflow perimeter feature also lacks a proven scripted counterpart;
`SET_OUTLET_TRAILING_EDGES` addresses base regions and is not substituted for it.
See [Boundary conditions and initialization actions](boundary-conditions.md)
for the available actions, ordering and current evidence limits.

`ROTOR_SHEDDING` is refused in matrix workflows because it has no effective
native route there. CCS Relaxed_TE direction control remains deferred; the
standalone Python component helper remains available.

### Applying existing boundary declarations

The setup choices `apply_trailing_edges`, `apply_wake_termination` and
`apply_base_regions` select application of the corresponding geometric declarations.
`false` means do not redefine them; it never emits a delete or clears saved FSM state.
`true` requires the corresponding declaration. Omitting a choice adapts the
published TE/wake/base sidecar behavior, preserving existing workspaces. Explicit
base-region editing actions conflict with `apply_base_regions = false`.

The unreleased sidecar `[[inlets]]` and `[[outlets]]` forms are rejected with a
setup/MATRIX migration message. Use `[ports]` for identity only. Creating ports on
a saved FSM remains refused while its existing port indices are unknown; use a
fresh mesh for the measured creation sequence. No saved state is implicitly cleared.
