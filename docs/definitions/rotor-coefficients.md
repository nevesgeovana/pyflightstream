## Rotor coefficients

`J`, `CT`, `CQ`, `CP`, `ETA`, `ETAW`, and the in-plane `CN`, `CS`,
`CMN`, `CMS`, one table per rotor, every column suffixed with the rotor's alias. They make physical sense for **one** rotor and not for
several summed: the diameters and speeds that normalise them are different
numbers.

The table is `polars/P<sim>-<alias>_rotor.csv`. It opens with `POL` and
`ROTOR`, the rotor's alias, on every row, then the condition block,
`RPM_<alias>`, `DIAMETER_<alias>` and the six, `J_<alias>` to `ETAW_<alias>`,
then `MTIP_<alias>` and `MHEL_<alias>`
([Tip and helical Mach numbers](tip-and-helical-mach-numbers.md#tip-and-helical-mach-numbers)), and then
`CN_<alias>`, `CS_<alias>`, `CMN_<alias>` and `CMS_<alias>`
([The in-plane coefficients](#the-in-plane-coefficients)), and, last,
`MADV_<alias>`, the advancing-tip Mach number. The column contract
grows at its end only, so every earlier column keeps its position.
Missing recorded ALPHA or BETA leaves the shaft angle and ETAW as `NA`, with
a warning naming the rows; unsteady axis coefficients refuse missing attitude.
MADV's documented zero-angle default is the one exception for these products.
Its first line is its header; the `ROTOR` column identifies the rotor on every row. See [the CSV migration](../upgrading.md#older-layouts) for older files with an alias line.

### Where an unsteady point's numbers come from

A steady point's row is built from the loads export. **An unsteady point's row
is the average of the PLOTS history over the row's window**, because the loads
export of an unsteady run states the last time step, one instant of a cycle.
**Each rotor's table follows its own rotor's clock**, as each blade does
([`per_blade`](per_blade.md#per_blade)): `LAST_REVS_AVG` counts that rotor's
own revolutions, so on a row with several rotors turning at different rates
each table averages over the stated number of its own revolutions, and its
window in steps can differ from the clock rotor's, which the unsteady polar
uses. `LAST_ITERS_AVG` is the stated step count for every rotor.

- **The history is the rotor's own six components in the global `MRP` frame**,
  `FX, FY, FZ, MX, MY, MZ` in Newtons, over the rotor's own families, general
  and blades. It is found through the pproc: a `[[plots.groups]]` entry with
  `frame = "MRP"` whose families are exactly the rotor's, whatever it is
  called. Where the pproc plots none, the run adds one itself, `ROTOR_<ALIAS>`.
- **A group in a rotor's own frame is never the source.** Its force is stated in
  axes that turn with the rotor and its moment is already about the hub. A
  group that merely shares the alias's name over other families is not one either.
- **A row that states a window never holds an instant.** A point whose history
  does not cover the window, or holds no such columns, is LEFT OUT of the table
  and named in `products.json`, as the unsteady polar beside it does. The
  table's manifest entry states `source`, `window`, the row's window on its
  clock rotor, and `windows`, each point's window of THIS rotor in steps.
- **A rotor's revolution is its own `steps_per_revolution`** in the run's
  plan, and its window ends at the row's last step. A row whose matrix states
  no window key, or a record that states no clock of the rotor, averages every
  rotor over the row's window.

See [the rotor-table migration](../upgrading.md#older-layouts) for the correction to historical unsteady tables.

### `ETAW`

It is an efficiency, with the rotor's force vector turned to wind axes in
place of the thrust.

1. Take the full force vector in the rotor frame, `[Fx, Fy, Fz]_rotor`.
2. Carry it to the airframe body frame by the **transpose** of the
   rotor-to-body rotation.
3. Carry it to wind axes by the **AIAA** rotation, with **alpha and beta**.
4. Take the **X** component: `Fx_W`.
5. `ETAW = J * CTW / CP`, where `CTW = Fx_W / (rho n^2 D^4)` -- the wind-axis
   force nondimensionalised exactly as the thrust is, entering the same
   efficiency where `CT` enters. It stays **dimensionless**.

**It reduces to `ETA` when the shaft lies along the stream**, whichever way the
reference points the rotor's axis, which is what makes the column readable
beside `ETA`. The sense `Fx_W` is counted in is fixed once per rotor, from its
frame `R<id>` against the body's `+x`: a shaft with a forward component counts
`Fx_W` forward, as `CTW` does, and a shaft square to the body's `+x` (a lift
rotor) counts it along the stream, so its `ETAW` is `J (-CTW) / CP`. The sense
does not follow the incidence, so a lift rotor's `ETAW` changes sign with
`Fx_W`, as its thrust tilts through the stream, never because the sense rule
turned. A caller that states no wind-axis force gets
`NA`, never the old cosine: publishing the superseded number under the corrected
name would leave a reader unable to tell which of the two they hold.

**It is two rotations on a vector, never the cosine of a scalar angle.** A cosine
discards the components that are not along the axis, which is exactly what the
rotation chain preserves.

### The in-plane coefficients

The table states the rotor's force and moment square to its
axis, in the rotor's own axes `(T, S, N)`:

- `T` is the rotor's axis as the reference declares it, the direction in
  which its thrust is counted positive (the same axis `CT` projects on).
- `N`, the normal, is the part of the reference frame's up direction (`+z`
  of the loads frame: x aft, y right, z up) square to `T`, normalised.
- `S`, the side axis, completes the right-handed set: `S = N x T`, so
  `T x S = N`.

For a level rotor whose axis points forward (`-x`), `N` is `+z` and `S` is
`-y`, the right of a viewer upstream of the rotor looking downstream at it;
the force components are then `N = +FZ` and `S = -FY`, and the moments
`MN = +MZ` and `MS = -MY`. `N`, `S`, `MN` and `MS` are taken from the same
rotor force and the same moment about the HUB that `CT` and `CQ` are taken
from (`M_hub = M_mrp + (r_mrp - r_hub) x F`), and normalised as they are,
with that row's density, the magnitude of its rotor speed and the rotor's
diameter:

```text
CN  = N  / (rho n^2 D^4)
CS  = S  / (rho n^2 D^4)
CMN = MN / (rho n^2 D^5)
CMS = MS / (rho n^2 D^5)
```

- The axes turn with the rotor: a tilted axis tilts `N` with it, and `N`
  stays in the vertical plane that holds the axis.
- The sense of rotation does not enter them: none is a power.
- **An axis along the up direction has no normal and no side axis.** The four
  read `NA` on every row, and the post says so once for the table, in its log.
  They also read `NA` wherever `CT` does (a zero or unstated reference speed,
  a loads frame that is not the geometry's), because they come from the same
  force.
- On an unsteady point they are the window's average, as every other column
  of the row is. On a quasi-steady wheel they are of the mean loads over its
  clockings, as every other column of the row is, and on a
  sector solved without symmetry loads they are the modelled sector's, not
  the whole rotor's.

### The normal-force slope against incidence

`[products] rotor_cn_slope = true` (off by default) writes, beside each rotor
table, `polars/P<sim>-<ALIAS>_cn_slope.csv`: the slope of the rotor's normal
force coefficient `CN_<ALIAS>` against the incidence `ALPHA`, at each advance
ratio the table holds. It is computed from the rotor table the post has just
written, whatever the table states (steady, unsteady window average, or
quasi-steady mean over clockings); no solver run is added.

- **One row per distinct `J_<ALIAS>` of the table**, in ascending `J`. Rows of
  the table with the same `J` (rounded to six decimals) form one
  group. The columns are `POL`, the context columns of the rotor table
  (`ALPHA` and `J` excluded: both are columns of the row), `ROTOR`, `J`, `ALPHA_LOW`, `ALPHA_HIGH`, `CN_LOW`,
  `CN_HIGH` and `CN_SLOPE_PER_DEG`. A context column holds its value when every
  row of the group states the same one and `NA` otherwise.
- **The slope is the secant between the two rows of lowest distinct `|ALPHA|`
  at that `J`.** `ALPHA_LOW` and `CN_LOW` are the row of smaller `|ALPHA|`,
  `ALPHA_HIGH` and `CN_HIGH` the other, and
  `CN_SLOPE_PER_DEG = (CN_HIGH - CN_LOW) / (ALPHA_HIGH - ALPHA_LOW)` with
  `ALPHA` in degrees as the table states it and `CN` as the table states it,
  unchanged. Two rows with the same `|ALPHA|` (for example `+2` and `-2`)
  count as one value of `|ALPHA|`, the positive one being taken. A row whose
  `ALPHA` or `CN_<ALIAS>` is `NA` is not a candidate.
- **A row of the table that states no `J` belongs to no group.** It gives no slope row and
  the products manifest names it under `skipped` for the table.
- **A `J` with one usable `|ALPHA|` only is not an error**, and that includes a
  `J` sampled at `+2` and `-2` alone. Its row is written with `NA` in the two
  `ALPHA`/`CN` pairs and in the slope, and the products manifest names it under
  `skipped` for the table, with the `J` and the reason. A table with no usable
  group still writes its file, every slope `NA`.
- The manifest entry states `kind: cn_slope`, `rotor` and the `runs` the
  table was read from. The slope is a secant of two sampled rows, not a fit and
  not the derivative at zero incidence: its value depends on which two
  incidences the sweep sampled, which is why both are in the row.

### A static point

**A zero free stream and a zero reference speed are two different things.** A
static point has a zero free stream: `J` is a real `0.00000`, and `ETA` and
`ETAW` read `NA`. They are the useful propulsive power over the shaft power,
`J CT / CP` and `J CTW / CP`, and at zero free stream the useful power is nil:
the rotor produces thrust and absorbs torque and no propulsive work, so any
number there would be an artifact of the algebra and not a measurement. The
package states `NA` whenever the free-stream speed or `CP` is zero; `CT` and
`CQ` stay real. The export states its
coefficients normalised by the reference dynamic pressure

```text
qref = rho VREF^2 / 2
```

where `VREF` is the run's reference velocity, and the rotor table takes them
back to newtons and newton-metres with that `qref`. So a static point with a
positive `VREF` has its forces and moments, and `CT`, `CQ`, `CP` and the
in-plane coefficients are written from them. A point whose `VREF` is zero or
not stated has a zero `qref`: no load is recoverable from coefficients divided
by it, and every rotor coefficient reads `NA` except `J`.

`VREF` is not a pure scale factor in hover. The reference speed also sets the
Reynolds number of the solve, so two hover runs that differ only in `VREF` can
differ in their solution and not only in their normalisation; the measured
hover arms behind this definition are in the hover normalisation report under
`reports/`. A hover figure of merit is not a column of the table.

<a id="the-rotor-frame-set"></a>

### The rotor frame set (`RCOEF`)

The `RCOEF` polar files hold the coefficients of every family inside a rotor
(one row per point and family) and of every group whose members all sit inside
one rotor (one row per point). After the run block and the identity columns
comes `ROTOR_ID`, then the columns below, then `MESH_FACES`. Every value is in
the frame `R<id>` of the row's own rotor
([the rotor frame](axes-and-signs.md#the-rotor-frame)) except the per-frame
set, which repeats three of them in every frame.

The symbols: `F_R` and `M_R` are the force and the moment about the rotor's
hub (`x_m, y_m, z_m`, transferred from the moment reference point by
`M_hub = M_mrp + (r_mrp - r_hub) x F`), in the axes of `R<id>`; `n` is the
rate in rev/s, signed about `x_R` (`n = s RPM<id> / 60`, see the sense rule);
`D = D<id>`; `A = ADISC<id> = pi D^2 / 4`; `q = 0.5 RHO VINF^2`, the free
stream's dynamic pressure, which is zero at a static point; and
`J = J<id> = VINF / (|n| D)`.

<a id="rotor-id"></a>

`ROTOR_ID` is the rotor's declared `id`, 0 when the rotor block writes none.

<a id="thrust-torque-and-power"></a>

**Thrust, torque and power.** `T = F_R,x` in N, the thrust, positive forward;
`Q = M_R,x` in N m, the torque about the hub, right-hand about `x_R`; and
`P = 2 pi n Q / 1000` in kW, the shaft power, by the sign rule
`CP = 2 pi CQ sign(n)`. The thrust and the torque are stated in the rotor frame
only.

<a id="rotor-frame-coefficients"></a>

**The rotor coefficients.**

```text
CT  = T / (RHO n^2 D^4)
CQ  = Q / (RHO n^2 D^5)
CP  = 2 pi CQ sign(n)
ETA = J CT / CP
```

<a id="in-plane-coefficients-in-r"></a>

**The in-plane coefficients**, with `Z = -F_R,z` (positive up),
`Y = F_R,y` (positive right), `N = M_R,z` and `M = M_R,y`:

```text
CFZ = Z / (RHO n^2 D^4)      CFY = Y / (RHO n^2 D^4)
CMZ = N / (RHO n^2 D^5)      CMY = M / (RHO n^2 D^5)
```

They replace the rotor table's `CN, CS, CMN, CMS` of the rotor's `(T, S, N)` axes:
`CFZ = CN`, `CFY = -CS`, `CMZ = -CMN`, `CMY = -CMS`.

<a id="disc-loadings"></a>

**The loadings over the disc.**

```text
TC = T / (q A)      YC = Y / (q A)      ZC = Z / (q A)
QC = Q / (q A D)    NC = N / (q A D)    MC = M / (q A D)
```

<a id="airframe-loadings"></a>

**The loadings over the airframe reference.**

```text
TCA = T / (q SREF)      YCA = Y / (q SREF)      ZCA = Z / (q SREF)
QCA = Q / (q SREF BREF) NCA = N / (q SREF BREF) MCA = M / (q SREF CREF)
```

<a id="per-frame"></a>

**The per-frame set.** For every frame f of the file, W, S, B, R0, R1, ...:

```text
CT<f>  = F_f,x / (RHO n^2 D^4)
CQ<f>  = M_hub,f,x / (RHO n^2 D^5)
ETA<f> = J CT<f> / CP
```

with `x_f` the frame's forward axis. In the row's own rotor frame they repeat
the bare values: `CTR<id> = CT`, `CQR<id> = CQ`, `ETAR<id> = ETA`. In another
rotor's frame (`CTR1` of a blade of rotor 0) the value is the same force along
that rotor's axis, still normalised by the row's own rotor's `n` and `D`.
`ETAW`, the efficiency in wind axes (see [`ETAW`](#etaw)), is the `ETA<f>` of
`f = W`. Every other column of the set is in the rotor frame only.

<a id="na-rules-of-the-rotor-frame-set"></a>

**When a value does not exist (`NA`).**

- A static point, `VINF = 0` (so `q = 0` and `J = 0`): `ETA`, every
  `ETA<f>`, and `TC` to `MCA` are `NA`; `T`, `Q`, `P`, `CT`, `CQ`, `CP`,
  `CFZ`, `CFY`, `CMZ`, `CMY` and every `CT<f>` and `CQ<f>` are written.
- A rotor not turning, or of unknown speed (`RPM<id>` is 0 or `NA`): every
  coefficient over `n^2` and `ETA` are `NA`; `T` and `Q` are written; `P` is 0
  at `RPM<id> = 0` and `NA` when the speed is unknown; `TC` to `MCA` are
  written when `q > 0`.
- Loads the export states in a frame that is not a translation of the
  geometry's give `NA` loads, and every value formed from them is `NA`.
