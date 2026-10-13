## Tip and helical Mach numbers

Every point of three row types states how fast the blade tip
moves against the speed of sound: an `unsteady_rotor` row, for each rotor it
turns; a `steady` row that states `RPM`, for its rotor; and a row of any run
type that names an actuator disc (`ACTUATOR`), for each disc:

```text
Omega = 2 pi RPM / 60                  rad/s
M_tip = Omega R / a
M_hel = sqrt(V^2 + (Omega R)^2) / a
M_adv = sqrt((Omega R + V_ip)^2 + V_ax^2) / a
```

- `RPM` is the speed the run turns, in rev/min, the unit of every rotor speed
  the package resolves: a rotor's `RPM` stated, or derived from
  `ADVANCE_RATIO`; a disc's `ACTUATOR_RPM`, or the speed its advance ratio
  works out to against the disc's own diameter, as its script emits it.
  Its sign is the rotor's hand and is not read: both numbers are of a speed.
  Rotor motions on 26.100 are refused until a rotation null test settles its
  angular-velocity unit (RPT-051). The earlier rev/min decision disagrees with
  the manual's rad/s, so the package cannot interpret that motion safely.
- `R` is a rotor's half diameter: the `diameter_m` of its rotor block in the
  reference, else the reference's `rotor_diameter_m`. A rotor with neither has
  no known radius, and its two numbers are not computed: the plan and the run
  record say so naming the row, and nothing is guessed. A disc's `R` is its
  block's `tip_radius_m`, which a disc block cannot omit; a row naming a disc
  its reference does not declare gets the same named note.
- `V` is the free-stream speed and `a` the speed of sound of the point's own
  resolved flight condition, the same resolution that sets the Mach number the
  run flies (a pinned `ASMPS` included). On a static rig, a row stating `RPM`
  and `ADVANCE_RATIO` and no velocity, `V` is the velocity the package derives,
  `J (RPM / 60) D` of the clock rotor. At `V = 0`, `M_hel = M_tip`.
- `M_tip` is the tangential speed of the tip alone; `M_hel` composes it with
  the free stream, the speed at which the tip meets the air in a helix. Both
  are dimensionless and geometric: `V` is the free-stream speed alone, not
  corrected for the rotor's own induced velocity, which near hover and at low
  advance ratio adds to the speed the tip actually sees.
- `M_adv` is the Mach number of the advancing blade tip. `V_ax` is the
  component of the free-stream velocity along the rotor axis and
  `V_ip = |V - V_ax axis|` the component in the rotor plane; the velocity
  comes from the point's resolved speed, angle of attack and sideslip in the
  body frame, and the axis from the rotor block's `axis` (a disc's, from its
  block's `axis` in its frame, where that frame is `MRP` or a declared
  `[[frames]]` entry). **`M_hel` bounds the tip only in axial flow**: there
  `M_adv = M_hel`, and in edgewise flow `M_adv = (Omega R + V) / a`, which is
  larger. Where a row's rotor axis cannot be resolved, `M_adv` is that
  edgewise bound and the plan line says so. `M_hel` is unchanged.

Where they appear:

- `pyfs-matrix plan` prints both per rotor and per disc per point, and
  `plan.json` carries them per point under `rotor_mach`, keyed by the rotor's
  alias or the disc's name, with `kind` (`rotor` or `actuator`) and the speed,
  the diameter, `V` and `a` they were taken at, and `mach_advancing`
  (`M_adv`) beside `mach_helical`, with `mach_advancing_bound` saying `axis`
  or `edgewise`. **The plan warns when `M_adv >= 1`** on any point, naming
  each point, its rotor or disc and its `M_adv`: at 1 or more the advancing
  tip is sonic or supersonic. It is a warning and never a refusal.
- The run record (`runs.json`) carries the same block under `rotor_mach`;
  the key is absent on a record with no such point. A steady row runs its
  points as one job, so its job record keys the blocks one level up by the
  point's name, and each point read out of the job carries its own.
- The rotor table carries `MTIP_<alias>` and `MHEL_<alias>` after its six
  coefficients (and before the four in-plane ones of 0.31.0), and
  `MADV_<alias>` as its last column (0.40.0), taken at that
  row's speed and `DIAMETER_<alias>` and at the point's resolved condition. A
  point whose condition does not resolve reads `NA` in both and keeps its row.
  A disc has no rotor table, and a steady row's record states no rotor speed
  for the table to read, so for those two the numbers are in the plan,
  `plan.json` and the run record. A `qsteady_rotor` point is the exception
  among steady rows: its rotor table reads the row's speed from the point's
  quasi-steady record (below).

---
