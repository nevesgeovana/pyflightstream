# One row: a body free to move (6DOF)

The row key `SIXDOF: d<id>` of an `unsteady` row names a file of
`inputs/sixdof/` that frees a body to move under its own aerodynamic loads,
instead of a prescribed motion. The reference case is a free-to-pitch model: a
wing-body on a pitch pivot, free in pitch only, released from a short force
pulse, whose oscillation gives the pitch damping and the short-period frequency.

```text
POL  | ... | WORKFLOW | VAR_NAMES_VALUES
9401 | ... | unsteady | VELOCITY: 25.0 / DELTA_TIME: 0.0005 / TIME_ITERATIONS: 2000 / LAST_ITERS_AVG: 1000 / SIXDOF: d001
```

## The input

Every vector key names its frame and its unit: the solver reads gravity in the
reference system and velocities and forces in the body system.

```toml
# inputs/sixdof/d001.toml
families = ["Wing", "Fuselage"]    # the moving surfaces
frame = "PIVOT"                    # the body frame at the pivot, a frame the run creates

[mass]
mass_kg = 4.2
# IXX, IYY, IZZ, IXY, IYZ, IZX (the last pairs Z with X), the solver's order
inertia_kg_m2 = [0.05, 0.31, 0.33, 0.0, 0.0, 0.0]

[gravity]
vector_reference_m_per_s2 = [0.0, 0.0, -9.80665]

[initial]
velocity_body_m_per_s = [0.0, 0.0, 0.0]
angular_velocity_body_deg_per_s = [0.0, 0.0, 0.0]

[free]                             # every freedom is locked unless stated true
q = true

[[forces]]                         # a 10 ms pulse 0.25 m ahead of the pivot
kind = "external"
point_body_m = [0.25, 0.0, 0.0]
force_body_n = [0.0, 0.0, -40.0]
start_s = 0.0
duration_s = 0.01                  # a duration, not an end time

[export]
trajectory = true
```

The pivot frame is declared in the reference's or the setup's `[[frames]]`
table, like any named frame.

Two more force kinds:

```toml
[[forces]]
kind = "spring"                    # a spring on the body
point_body_m = [0.0, 0.0, 0.0]
axis_body = [0.0, 0.0, 1.0]
free_length_m = 0.40               # where it stops pushing
solid_length_m = 0.05              # fully compressed
initial_length_m = 0.30            # where it starts
rate_n_per_m = 800.0

[[forces]]
kind = "custom"                    # a force profile from a file beside the input
type = "FORCE_VS_TIME"             # or FORCE_VS_DISTANCE
file = "pulse_force.txt"
```

`symmetry_loads = true` includes the loads on the symmetry boundary of a
mirrored half model.

## What the script does

After the frames and before the solver is initialised, the script creates one
6DOF motion of the families about the body frame, states the mass and inertia,
gravity, the initial velocities, the six freedoms (in the order U V W P Q R),
each force in the order written, the symmetry loads, and the trajectory export
to `<point>_trajectory_6dof.txt`, which joins the row's outputs. The initial
angular velocity is written in radians per second, the unit measured for the
solver's other angular velocity.

The point folder also receives `sixdof-provenance.json` (the input's path, its
digest and its parsed content) and any custom force file, hashed.

## What is refused

- `SIXDOF` on `steady`, `qsteady_rotor` or `unsteady_rotor`: a free body needs
  the time march, and a free body with a rotor turning is outside this route.
- `SIXDOF` together with `FSI`.
- A mass not above zero; an inertia tensor that is not positive definite; every
  freedom locked; an external force with a duration not above zero; spring
  lengths not above zero or a solid length above the free length; a custom force
  file that is not a file of `inputs/sixdof/`; a key the input does not define.
- A free lateral freedom (`v`, `p` or `r`) on a row whose `SYMMETRY` is
  `MIRROR`: a half model carries no lateral loads.
- A frame or a family the run does not create or the geometry does not carry; a
  simulation in another length unit than metres; continuing a stopped march.
- A build on which a 6DOF command is still recorded from the manual only, with
  no licensed run behind it: the plan names the command.

## What is not here yet

The trajectory file is kept as the solver writes it; a package table of the
trajectory waits for its grammar to be read from a licensed run. A prescribed
motion read from a table (the solver's CUSTOM motion) is a later capability.
