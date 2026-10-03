## The quasi-steady rotor

A `qsteady_rotor` point is steady, and every product a steady point writes
(the polar, the rotor table, the sections, the probes) is written for it as
for any steady point: the instant of its own solve, which on a wheel is
clocking 0, except that a wheel's sections hold every clocking and a wheel's
row of the rotor table is the mean of its clockings (both below). The rotor table's speed, `RPM_<alias>`, is the row's, the speed
the free stream turns at, read from the point's quasi-steady record
(`<point>_qsteady.json`), as an unsteady rotor's is read from its plan. Where the row states `ADVANCE_RATIO`, the speed is n = V / (J D) with D the rotor block's own `diameter_m`, never the reference's top-level `rotor_diameter_m`. A
sector's table is its one solve's export as it stands, with no factor for
the periodic copies (the export carries the whole rotor where the row enables
symmetry loads and the sector alone where it does not).

**The rotor table of a wheel is the mean of its clockings**. The rotor's force and its moment about
the hub are averaged over the `k` clockings, each clocking's own loads export
as the point's record names it: every surface's six components, each taken
from its export's reference velocity to the point's, averaged over the
clockings by the same average the average table takes, and then the rotor's
statics as for any steady point. Because the sum over the rotor's surfaces
and the transfer of the moment to the hub are linear, that is the mean of the
rotor's force and moment, and `CT`, `CQ`, `CP`, `ETA`, `ETAW`, `CN`, `CS`,
`CMN` and `CMS` are then computed from those mean loads:

```text
F_mean = (1/k) sum_i F_i        M_hub,mean = (1/k) sum_i M_hub,i
ETA    = J CT(F_mean) / CP(M_hub,mean)     never (1/k) sum_i ETA_i
```

The table's `products.json` entry says `"source": "mean of k clockings"`
with `k` written out, and `"clockings": k` (a mapping of run to `k` where the
points of one table differ). A wheel point one of whose clocking exports is
missing, unreadable, without a reference velocity, in another analysis frame
or listing other surfaces is not a row of the table and is named under its
key in `products.json` `skipped`; the mean of the other clockings is never
written in its place. A sector is one solve and its row is that solve, as
before.

Two products are the run type's own, and a wheel point's sections
gain its clockings and its validity.

- **The clockings table**, `polars/P<sim>-<ALIAS>_qs_positions.csv`: one row
  per point and clocking, the shape of the unsteady rotor's phase-locked table
  (one row per azimuth). `REDUCTION` is `qsteady_position`; `AZIMUTH` is where
  blade one is at that clocking, `(blade1.azimuth_deg + sense * theta_i) mod 360`
  with `sense` the sign of the rotor's speed, by the one rule the sections
  table's `AZIMUTH` follows (`pyflightstream.post.axes.clocked_blade_azimuth_deg`),
  so the two agree for either hand; `POSITION` is `i`
  and `POSITIONS` is `k`. Each value is an
  INSTANT, the steady solve at that clocking.
- **The average table**, `polars/P<sim>-<ALIAS>_qs_avg.csv`: one row per
  point, `REDUCTION` `qsteady_average`, the mean over its clockings of every
  loads column. It is the quasi-steady counterpart of the unsteady time
  average, and it is an AVERAGE over clockings, never over time.

In both tables `J_CLOCK` and `RPM_CLOCK` state what the rotor ran at, from the
speed of the point's own record, the diameter of the rotor's block and the
point's free stream (`V / (n D)`, the one formula of the rotor table), and `J`
states the same number where the row requested no advance ratio. A point with
a speed and a free stream is never `NA` in them; what the row requested is kept
as written, and a point whose free stream or diameter is not stated stays `NA`.

Both carry `CONTEXT_COLUMNS`, the moment point, the validity columns below
(the average table then the rotor state of a wheel point, below)
and then, for the rotor (`_<ALIAS>`) and for each blade (`_<family>`),
`FX FY FZ` (N) and `MX MY MZ` (N m, about the rotor's HUB), in the loads
frame's axes, and `THRUST` and `TORQUE`, the components along the shaft, each
taken from the loads export of that clocking at its reference velocity and
the point's density, by the rotor table's own statics. A point whose record
or one of whose clocking exports is missing is not a row, and
`products.json` names it under the file.

**The validity columns**, on both tables and on the sections of a wheel
point: `K_1P_MIN`, `K_1P_MAX`, `K_1P_MEAN` (span weighted),
`SPAN_PCT_K_GT_0_05`, `SPAN_PCT_K_GT_0_1`, `THRUST_PCT_K_GT_0_1`,
`TORQUE_PCT_K_GT_0_1` and `K_1P_SOURCE`, with
`k = Omega c / (2 sqrt(V^2 + (Omega r)^2))` per station. The `1P` is counted
on the blade, once per revolution of that blade: the frequency at which one
blade meets an inflow that varies once around the disc, never the
blade-passing frequency a fixed surface near the rotor feels, nor what a
balance summing every blade reads. Where the point has
a sectional loads export (`K_1P_SOURCE` `sections`), `c` is the export's
`Chord` and `r` the absolute `Offset` of the rows the record's layout gives to
the rotor, read as the radius of a distribution cut along the blade from the
hub; the summary is taken over the rotor's first blade present, so a wheel's
blades do not count one station several times. Each station stands for a
strip, half-way to its neighbours. The two shares are the strips above 0.1
over all strips, of the thrust and of the torque per unit span, both taken
along the rotor's axis. The export states `Fx` and `Fz` in the
axes of the frame the distribution was cut in, which the run's sections layout
names for each block; for a cut in that frame's XZ plane the station's force
is `F = Fx e_x + Fz e_z` and the station sits at `r = Offset e_y`, for a cut
in its XY plane `F = Fx e_x + Fz e_y` and `r = Offset e_z`, and with
`a` the rotor's axis (the record's `axis_vector`, in the sense its thrust is
counted positive) stated in the same frame's axes:

```text
thrust per unit span  t = F . a
torque per unit span  q = (r x F) . a
THRUST_PCT_K_GT_0_1 = 100 sum_{k > 0.1} t w / sum t w
TORQUE_PCT_K_GT_0_1 = 100 sum_{k > 0.1} q w / sum q w
```

with `w` each station's strip, so the torque comes from the in-plane
(tangential) component of the force only. In a frame of the rotor
(`<ALIAS>_SMRP`, `<ALIAS>_RMRP`, a blade's `<ALIAS>_RMRP<k>`, and each
clocking's copy of one) `a` is the frame's shaft axis, the rotor's letter or
`z` for a shaft stated as a vector, because every such frame is the hub frame
turned about the shaft; in `MRP`, whose axes are the geometry's, `a` is
`axis_vector` itself. See [the wheel migration](../migrating-to-0.31.0.md) for the historical thrust and torque correction. The reading of an XZ cut rests on the FSI pilot records (RPT-005,
RPT-006); the reading of an XY cut was measured on the 0.31.0 short licensed
confirmation of a clocked wheel, where the strip integrals of `Fx`, `Fz` and
`Fz Offset` over blade one matched the blade's force along the shaft, its
in-plane force and its moment about the shaft to about 2 per cent. **A share
is `NA`**, and the post says why in a WARNING line of `post.log` naming the
point, where a block was cut in a frame whose axes the post does not know (one
a setup creates), in the YZ plane (not measured), or in a block the layout does
not name; where a station of the blade the shares are taken over states its
`Fx`, `Fz` or `Offset` as `NA` or as nothing readable (the line names the
station; a gap is never read as a zero load); where the total is zero; and where
stations of opposite sign put the share outside 0 to 100 per cent, the total
then having no sign a share of it could be read against. Where the point has
no such export the values are the plan's, the chord read off the mesh
(`K_1P_SOURCE` `mesh`), and the two shares are `NA`.

**The rotor state of a wheel point**, the quantities the
wheel's correction routes read: six columns after the validity columns in
`_qs_avg.csv`, and the same six under `rotor_state` in the point's validity
file (`null` where not known). With `T` the rotor's thrust along its axis,
the mean over the clockings of `THRUST_<ALIAS>` (the thrust of the rotor
table's mean loads), `rho` the point's density, `V` its free-stream speed,
`n = |rpm| / 60` and `Omega = 2 pi n` the rotor's speed, `D` its diameter,
`R = D / 2`, `A = pi R^2`, and `alpha_p` the angle between the rotor's axis
(in the sense its thrust is counted positive) and the direction of flight,
the direction the free stream comes from (`alpha_p = 0` in axial flight along
the thrust, 90 degrees edgewise):

| column | definition |
|---|---|
| `CT_ROTOR` | `T / (rho A (Omega R)^2)`, the rotor convention |
| `CT_PROPELLER` | `T / (rho n^2 D^4)`, the propeller convention, `pi^3 / 4` times `CT_ROTOR` |
| `MU_ROTOR` | `V sin(alpha_p) / (Omega R)`, the advance ratio in the disc plane |
| `LAMBDA_C` | `V cos(alpha_p) / (Omega R)`, the free stream through the disc against the thrust |
| `LAMBDA_I` | the momentum-theory induced inflow, the root of Glauert's relation below |
| `CHI_DEG` | `atan2(MU_ROTOR, LAMBDA_C + LAMBDA_I)` in degrees, the wake skew angle |

```text
LAMBDA_I = CT_ROTOR / (2 sqrt(MU_ROTOR^2 + (LAMBDA_C + LAMBDA_I)^2))
```

`LAMBDA_I` is solved by Newton's method from the hover value
`sign(CT_ROTOR) sqrt(|CT_ROTOR| / 2)` until a step is no larger than 1e-10, in
at most 100 steps (`pyflightstream.cases.qsteady.glauert_induced_inflow`). A
relation that does not converge (momentum theory does not describe a rotor
descending into its own wake) leaves `LAMBDA_I` and `CHI_DEG` `NA`, and the
post says so in a WARNING line of `post.log` naming the point and the average
table; `NA` everywhere a thrust is not known at every clocking, or the point
states no density or speed. `MU_ROTOR`, not `MU`: `MU` is the air's viscosity
in every table's condition block. A sector's row reads `NA` in all six.

**The sections of a wheel point** (0.31.0) hold EVERY clocking: the wheel
exports its section distributions at each clocking, created again in that
clocking's pose in frames turned with the wheel (see the workspace page), and
`sections/<point>_sections.csv` holds clocking 0's rows, then clocking 1's,
up to clocking `k - 1`'s, each block in the order the run recorded it. After
the export's own columns come:

| column | what it is |
|---|---|
| `CLOCKING` | `i`, the clocking the row was cut at; 0 is the point's own solve |
| `K_1P` | the reduced frequency of the row's station (`NA` on a row no rotor owns) |
| the validity columns | the point's, one value down the table |

and on every row `ROTOR` is the wheel's rotor for a block of its families,
and `AZIMUTH` states where the block's blade is at that clocking,

`AZIMUTH = (blade1.azimuth_deg + (n - 1) * 360 / N + sense * i * (360 / N) / k) mod 360`

for a block of ONE blade, blade `n` of the rotor's `N` (its place in
`families_blades`), with `sense` the sign of the rotor's speed: blade `n`
sits `(n - 1) / N` of a turn from blade one, as the blade frames are placed,
and clocking `i` turns the wheel by `theta_i` in the sense of rotation, as the
surfaces are turned. A block of several families of the rotor states blade
one's, which is what `AZIMUTH` means in every other sections table; a block
no rotor owns reads `NA`. The rule has one home,
`pyflightstream.post.axes.clocked_blade_azimuth_deg`.

Every clocking is cut at the same stations (each distribution is created in
its frame turned with the blades, so the blade spans one interval along every
clocking's normal): the post compares each clocking's blocks, planes and
`Offset` with clocking 0's, to a thousandth of the largest offset, and a
clocking that differs is tabled as exported and warned in `post.log`. A
clocking whose export the point's record does not name (a historical wheel record may name sections at clocking 0 only), or which is not on disk, is
not in the table, and `products.json` names it under the table's key with
`#clocking=<i>`; the other clockings are written.

The validity summary is taken over clocking 0's rows, the point's own solve,
so a clocking's stations are not counted `k` times; `K_1P` is stated on every
row.

**The super file** row of a wheel point carries the validity columns after
every other key of the row, the sections' values where the point has them,
else the plan's; `NA` in the rows of every other point.

**The per-point validity file**, `<point>_qsteady_validity.json`, is written by
the post into the wheel point's datapoint folder, beside the run's
`<point>_qsteady.json`: every value of the validity columns (the thrust and
torque shares included, `null` where not known), `K_1P_SOURCE`, the rotor state (`rotor_state`), and the
plan's record as the run kept it. The run's record is a hashed input of the
run and is never rewritten; this file is the post's and every post rewrites
it. `products.json` names each point's file under the clockings and average
tables' entries (`validity_files`, relative to the products folder).

The steady polar table and the rotor table of a quasi-steady point do not
carry the validity columns: their columns are a fixed contract a reader's
scripts index, and no line precedes a CSV header, so a reader of those two
finds the point's values in its super-file row and in its validity file.

**A point whose quasi-steady record cannot be read** (missing, not JSON, of a
schema other than the one the package writes, or holding a key it does not
write) keeps every product that does not need the record, and loses, each by
name in `products.json` `skipped` and as a WARNING line in `post.log`, the ones
that do: its row of the rotor table (the speed is the record's), its rows of the
clockings and average tables, and, where it has a sections table, that
table's `K_1P` column and validity columns. The reason given is the record's
own refusal, naming the file. The post never stops on it.

---
