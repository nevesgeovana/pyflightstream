# RPT-081 - Typed boundary and base-region operations (2026-09-27, editorial amendment 2026-09-28)

These controls distinguish emitted commands, saved configuration, mesh changes and solver execution. They used FlightStream 26.124 build 8172026, executable SHA-256 withheld from the public tree per NFR-31. No control in this report initialized or started a solve. A stored boundary value establishes configuration, not its effect on a velocity field or aerodynamic loads. Other builds and untested argument combinations remain outside these observations.

## Inlets, outlets and profiles

A synthetic closed duct has separate inlet, outlet and wall mesh boundaries. Paired saves retained the selected inlet/outlet boundaries and requested signed normal values at magnitudes 10 and 20. A four-row inlet profile retained its supplied X, Y, Z and velocity-magnitude values. This establishes ingestion and stored values; interpolation and physical flow direction were not measured. The manual's signed-normal explanation and its type-directed example comment are not treated as a resolved sign convention.

An explicit combined deletion returned the saved port state to the unmarked control. That result does not isolate each deletion command's effect. Profile bytes are hashed when read, staged unchanged, and refused if changed before generation. An outlet-profile request is refused because the inspected scripting vocabulary provides an inlet-profile setter, without an equivalent outlet setter.

## The remesh index is the created-port sequence

The outlet occupies mesh boundary 2 in all four diagnostics. Each uses inner radius 0, four radial faces per side, successive growth and growth factor 1.2.

| Created ports | REMESH_OUTLET argument | Measured result |
| --- | --- | --- |
| Inlet, then outlet | OUTLET 1 | Modal: no valid edges found; no saved FSM |
| Inlet, then outlet | OUTLET 2 | Outlet remeshed; inlet and wall retained |
| Outlet alone | OUTLET 1 | Outlet remeshed; inlet and wall retained |
| Outlet alone | OUTLET 2 | Native index error; exit 0 but no saved FSM |

Both successful outlet controls changed its two triangles to 28 and preserved its area of 1. The other cap retained two triangles and the wall retained eight. The separate inlet-remesh control likewise changed only its target cap from two triangles to 28. These are geometric effects, not parser acceptance.

The workflow previously restarted its remesh counter for outlets. It now increments one created-port index across inlet and outlet creation. The mesh-boundary index still identifies the boundary to create; the shared port index identifies the object to remesh. The regression reproduced incorrect OUTLET 1 before the fix and passed with OUTLET 2 afterward.

The native modal stated: “No valid edges were found. Please check selected boundary perimeter.” The guard recorded it and ended only the launched process, without clicking through. The other negative control retained an exit code of zero with a scripting error and missing outputs. Neither counts as successful operation.

## Explicit base-region operations

The public synthetic body fixture has Body and Base mesh boundaries. Creation uses mesh boundary 2; the resulting base-region object is index 1. These are different index domains.

| Command and tested arguments | Saved-state or geometric observation |
| --- | --- |
| CREATE_NEW_BASE_REGION 2 USER -0.2 | Base entry stores Cp -0.2; 24 faces at X=4 marked |
| SET_BASE_REGION_CP 1 CUSTOM -0.3 | Stored Cp changes to -0.3; mesh retained |
| DELETE_BASE_REGION 1 | Entire saved FSM equals unmodified control |
| REMESH_BASE_REGION 1; radius 0; elements 4; growth 1/1.2 | Base changes 24→168 triangles; Body's 1,032 coordinate triangles unchanged |
| SET_BASE_REGION_TRAILING_EDGES 1 | Log reports 24 trailing edges on Base; saved markers change |
| SET_OUTLET_TRAILING_EDGES 2 | Entire saved FSM equals created control; effect unobserved |
| SELECT_BASE_REGION_FACES 1 | Graphics state changes; selected face identities unproved |

Base remeshing changed the total mesh from 1,056 triangles/530 vertices to 1,200 triangles/602 vertices. Base area remained 0.776457135287988 within roundoff, and every base vertex remained at X=4. This identifies the affected region rather than treating any saved-state change as proof. Additional index-1 and all-regions (-1) controls also produced saves identical to the created control. None establishes an outflow-edge effect. A further pair first marks the base trailing edges and then requests outlet conversion; those controls are prepared and remain unmeasured. The presence of pre-existing trailing edges is a hypothesis to test, not a documented prerequisite inferred from silence.

Actions are optional and ordered. Omission performs no destructive clear. The implementation preserves command-specific USER/CUSTOM vocabulary; [RPT-021](RPT-021_chapter-questions-measured_2026-08-08.md) measured the creator/setter distinction on 26.121. This report measures USER creation and CUSTOM update on the stated 26.124 executable only.

## Reference normalization routes

The setup accepts reference_mach or the explicit action disable_reference_velocity=true, in addition to reference_velocity_m_per_s. Only one may be stated. With none, the workflow still sets reference velocity to resolved freestream. Either new route suppresses that competing default setter.

The earlier exact-build compatibility report measured reference Mach 0.157 in the initialized settings dump after SOLVER_SET_REF_MACH_NUMBER; that evidence is reused. Three no-solve DISABLE_SOLVER_REF_VELOCITY controls now measure its effect. The held control stores reference velocity 47.513 with freestream 30 and an enabled override marker. Reset stores both velocities 30 and clears the marker. Changing freestream to 40 afterward stores both velocities 40 while the marker remains cleared. This establishes saved reference normalization behavior for this condition.

## Physical Mach input and native output precision

The typed freestream_input choice selects velocity or Mach emission from the same resolved physical condition. Mach mode checks consistency among velocity, sound speed, temperature, density, pressure and heat-capacity ratio; it does not introduce a second Mach value in the setup. Dimensioned model values remain SI.

For Mach 0.13, temperature 288.15 K and heat-capacity ratio 1.4, the velocity route saved 44.23821844339157 m/s and the Mach route saved 44.23815155523207 m/s. The difference is approximately 0.00006688816 m/s, or 1.512 ppm. The human-readable settings exports are identical at their displayed precision, but the saved values are not exactly identical. The replay asserts a 2 ppm bound for this executable and this condition only. Reference velocity remains unchanged between the two routes. No gas constant or physical Mach value was altered to hide the discrepancy. This single observation is not a universal precision bound.

## Saved wake and separation settings

Each pair changes one requested setting in the same unsolved body fixture. The listed field is the sole change within its relevant saved WAKE or SOLVER block. Other opaque native metadata is not assigned a physical interpretation.

| Command | Tested contrast | Observed saved value |
| --- | --- | --- |
| LAMINAR_SEPARATION | DISABLE / ENABLE | F / T |
| ADDITIONAL_WAKE_RELAXATION_ITERATION | DISABLE / ENABLE | F / T |
| SET_WAKE_ON_WAKE_INDUCTION | DISABLE / ENABLE | F / T |
| SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY | DISABLE / ENABLE | F / T |
| SOLVER_UNSTEADY_PRESSURE_AND_KUTTA | DISABLE / ENABLE | F / T |
| SET_WAKE_NUMERICAL_RELAXATION | 0.25 / 0.75 | 0.250 / 0.750 |
| SET_WAKE_DECAY_CONSTANT | 0.15 / 0.45 | 0.150 / 0.450 |

These observations establish setter persistence, not aerodynamic effects, convergence improvements or model interactions. A rotor-induced-velocity blending 0.25/0.75 pair produced identical complete saved FSMs on the unsolved body fixture, so that command's operational effect remains unproved by this experiment. A rotor-specific solved comparison is a separate obligation.

## Regressions and limits

The outlet defect produced one failing and one passing diagnostic before correction, then all 15 boundary tests passed. Reference normalization produced five expected failures before implementation. The combined reference, boundary, base-region, glossary and complete-template run passed 82 tests; Ruff and mypy on the two edited source modules passed.

- [Boundary and port tests](../tests/tier1_offline/test_boundary_setup_coverage.py)
- [Base-region tests](../tests/tier1_offline/test_base_region_setup.py)
- [Reference-normalization tests](../tests/tier1_offline/test_reference_normalization_setup.py)
- [Native saved-state replays](../tests/tier1_offline/test_setup_native_state_evidence.py)
- [Typed actuator controls](../tests/tier1_offline/test_actuator_typed_controls.py)

Native outlet/base analysis verified all 45 retained output hashes; receipt digest 249893611e39f2a3fb897597ed37c215845072a3f99a264b5342a829d5ce0ecb. The subsequent 24-control analysis verified 101 output hashes, analysis digest 3542d951d89c77187fae3a75dc379d82f67de6ce1233d389975a7c4539975b40. Eleven opt-in replay cases inspect the actual hash-bound artifacts, including the negative blending comparison; the latest combined actuator/replay/glossary run passed 37 tests. Original scripts and negatives remain intact; resource-limited execution copies add one parallel thread without changing target commands.

This bounded evidence does not close the complete setup inventory, prove profile interpolation, validate every radial scheme, establish flow/load effects, or make deprecated commands supported. Outstanding operational coverage remains explicit in the release audit.
