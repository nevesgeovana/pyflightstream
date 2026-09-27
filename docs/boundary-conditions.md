<!--
GEOVERSE_HEADER
file_version: "1.0.0"
last_modified_at: "2026-09-27T19:37:02.602Z"
last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementation-agent}
dependencies: [../src/pyflightstream/cases/__init__.py, ../src/pyflightstream/workspace/inputs.py]
authority: pyflightstream
status: draft
confidentiality: public
change_summary: Document inlet profiles, radial meshes and ordered base-region setup actions.
revision_source: git
-->

# Boundary conditions and initialization actions

A raw mesh declares ports in its geometry sidecar. Each port names the exact boundary after import renames. The velocity value is passed unchanged in the simulation velocity units. The current manual is inconsistent about direction: its command description specifies a signed normal velocity, while the GUI note on p.189 says direction now follows the inlet/outlet type and signs are unnecessary. The negative inlet below is an explicit signed-input control, pending comparison with a positive-input control on the target executable.

```toml
[trailing_edges]
none = true

[[inlets]]
boundary = "Inlet"
velocity = -10.0

[[outlets]]
boundary = "Outlet"
velocity = 10.0
```

The no-trailing-edge choice warns and creates no wake. It does not prove that an inlet/outlet configuration needs no exhaust wake.

## A native inlet profile

An inlet may add `profile = "inlet-profile.txt"`, relative to the sidecar. The reader binds exact bytes by SHA-256; building refuses a changed file. The run stages a uniquely named copy in the point's working directory and records its digest. Neither newline style nor columns are rewritten. `profile_sha256` is package metadata, not an authored input.

The profile command addresses the inlet sequence, separately from boundary indices. Inlets created on boundaries 3 and 7 receive inlet indices 1 and 2.

The GUI manual gives comma-separated `x,y,z,Vmag` rows on p.190 and says the vertices are mapped onto the inlet to form a continuous field. This resolves the copied motion-data description in the scripting parameter table. Coordinate units and sign behavior still require build-specific confirmation; the fixture uses a simulation explicitly set to metres. An actuator radial-thrust file is not an inlet-profile specification. Operational acceptance of the new route is still pending.

An outlet profile is refused because no counterpart is documented. The GUI's exhaust-outflow perimeter marking also has no established script route. The base-region command `SET_OUTLET_TRAILING_EDGES` is not substituted for it. These are unresolved operational capabilities, not completeness claims. Sources: FlightStream User Guide supplied with 26.123/26.124, pp.190–191 and 330–331; `inlets_outlets.yaml` retains the source discrepancies.

## Explicit setup actions

These optional keys belong under `[solver]`. Omission preserves existing behavior; action requests use `true`, not a guessed native default.

| Key | Meaning and order |
| --- | --- |
| `proximal_boundaries = ["Wing"]` | Resolve labels or indices before initialization. `"all"` expands a known inventory and refuses an unknown one. |
| `remove_initialization = true` | Remove saved initialization before the workflow initializes again. This is distinct from clearing a solution. |
| `delete_inlets = [2, 1]` / `delete_outlets = [1]` | Unmark existing port indices in the written order before initialization. The native port sequence is separate from mesh boundary indices. |
| `delete_transition_trips = [3, 1]` | Delete saved trip indices in precisely this order. No saved inventory or renumbering is invented. |
| `clear_vorticity_drag_boundaries = true` | Clear the induced-drag selection after a steady solve and before export. It conflicts with an explicit family selection and is refused on an unsteady march, where it would not affect earlier step products. |

Typed input, inspection and emission establish the requested script. Native acceptance additionally requires executable identity, input and script hashes, logs, and measured state or output changes. Parser acceptance and exit code zero alone are insufficient.

## Radial inlet and outlet meshes

A port can request an explicit radial mesh after it is marked and before its custom profile is assigned:

```toml
[[inlets]]
boundary = "Inlet"
velocity = 10.0
[inlets.remesh]
inner_radius_m = 0.0
radial_faces = 4
growth_scheme = "successive"
growth_rate = 1.2
```

Use `[outlets.remesh]` under an outlet for the same controls. The radius is in metres and is converted using the simulation's known length unit. Zero requests a disk; a positive inner radius requests an annulus and must remain below the outer radius of the actual geometry. `radial_faces` counts faces generated from each wall boundary edge. Growth scheme `successive` maps to native 1 and `dual_sided` to 2; growth rate 1 is uniform and a value above 1 refines the outer perimeter. These meanings come from the supplied 26.124 manual, printed/PDF pp.190–192.

The command registry places remeshing in the setup phase because it needs an already-created port. It remains forbidden after initialization settings. Offline tests exercise that prerequisite order; native remesh state and mesh suitability remain pending. Repeating the same boundary in inlet/outlet tables is refused: the manual says reassignment removes the old association and may delete its port, making later port indices ambiguous.

## Ordered base-region actions

A setup may declare `base_region_bending_angle_deg` and an ordered array of `[[base_region_operations]]`. Detection happens first, then these operations, then initialization. The angle is applied before automatic or named-boundary detection. The package does not invent a base-region inventory: `boundary` identifies a mesh boundary when creating a region; `index` identifies the current base-region sequence. After deletion, state and numbering may change, so subsequent indices are the user's explicit responsibility.

```toml
base_region_bending_angle_deg = 25.0

[[base_region_operations]]
operation = "create"
boundary = "Base"
model = "USER"
cp = -0.2

[[base_region_operations]]
operation = "set_pressure"
index = 1
model = "CUSTOM"
cp = -0.3

[[base_region_operations]]
operation = "remesh"
index = 1
[base_region_operations.mesh]
inner_radius_m = 0.0
radial_faces = 4
growth_scheme = "successive"
growth_rate = 1.2
```

Creation requires `boundary`, `model` and `cp`, including the ignored Cp argument for EMPIRICAL. A pressure update requires `index` and `model`; CUSTOM also requires `cp`. USER is refused for a pressure update: RPT-021 measured different creator/setter vocabularies on 26.121. That report does not establish current-build operation.

The operations `delete`, `mark_trailing_edges` and `select_faces` require `index`. Trailing-edge marking and face selection accept `index = "all"`; deletion does not. Face selection changes application selection state. `mark_outflow_edges` instead requires `boundary` (mesh name, index or `"all"`), following the command registry's boundary argument. The manual calls it a base-region boundary, not an outlet perimeter; native association remains to be measured. Its documented command is SET_OUTFLOW_TRAILING_EDGES on 26.122 and SET_OUTLET_TRAILING_EDGES on 26.123/26.124. Build routing follows those records; it does not establish native operation.

RPT-066 already measured automatic detection and detection by the actual base boundary on the supplied body in 26.124. New pressure, deletion, radial remesh and edge-marking routes require their own saved-state checks. In particular, a syntactically accepted remesh is not proof that the intended faces changed.

The [executable base-region setup example](examples/base_region_setup.md) generates a script from the repository's public body fixture without launching a solver. It demonstrates explicit indices and ordering; inspect the starting geometry's actual base regions before applying it to another saved simulation.
