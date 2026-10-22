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
beside `ETA`. `Fx_W` is counted in the sense of the shaft, as the thrust is:
an axis whose x component is negative counts it against the stream's X, and
any other axis, one square to the body's `+x` included, counts it along it. The
sense is fixed once per rotor, against the body's `+x`, so a lift rotor's `ETAW`
does not change sign between two incidences where its thrust and `CP` do not. A caller that states no wind-axis force gets
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

### A static point

**A zero free stream and a zero reference speed are two different things.** A
static point has a zero free stream: `J` is a real `0.00000`, and `ETA` and
`ETAW`, which divide by the free-stream speed, read `NA`. The export states its
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
