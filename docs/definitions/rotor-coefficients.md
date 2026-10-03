## Rotor coefficients

`J`, `CT`, `CQ`, `CP`, `ETA`, `ETAW`, and the in-plane `CN`, `CS`,
`CMN`, `CMS`, one table per rotor, every column suffixed with the rotor's alias. They make physical sense for **one** rotor and not for
several summed: the diameters and speeds that normalise them are different
numbers.

The table is `polars/P<sim>-<alias>_rotor.csv`. It opens with `POL` and
`ROTOR`, the rotor's alias, on every row, then the condition block,
`RPM_<alias>`, `DIAMETER_<alias>` and the six, `J_<alias>` to `ETAW_<alias>`,
then `MTIP_<alias>` and `MHEL_<alias>`
([Tip and helical Mach numbers](tip-and-helical-mach-numbers.md#tip-and-helical-mach-numbers)), and then, last
`CN_<alias>`, `CS_<alias>`, `CMN_<alias>` and `CMS_<alias>`
([The in-plane coefficients](#the-in-plane-coefficients)). The column contract
grows at its end only, so every earlier column keeps its position.
Its first line is its header; the `ROTOR` column identifies the rotor on every row. See [the CSV migration](../migrating-to-0.27.0.md) for older files with an alias line.

### Where an unsteady point's numbers come from

A steady point's row is built from the loads export. **An unsteady point's row
is the average of the PLOTS history over the row's window**, the same window the
unsteady polar and the reductions use, because the loads export of an unsteady
run states the last time step, one instant of a cycle.

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
  table's manifest entry states `source` and `window`.

See [the rotor-table migration](../migrating-to-0.24.0.md) for the correction to historical unsteady tables.

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

**It reduces to `ETA` when the shaft lies along the stream**, which is what makes
the column readable beside `ETA`. A caller that states no wind-axis force gets
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
  They also read `NA` wherever `CT` does (a static point, a loads frame that
  is not the geometry's), because they come from the same force.
- On an unsteady point they are the window's average, as every other column
  of the row is. On a quasi-steady wheel they are of the mean loads over its
  clockings, as every other column of the row is, and on a
  sector solved without symmetry loads they are the modelled sector's, not
  the whole rotor's.

### A static point

Every rotor coefficient reads `NA` on a static point except `J`, which is a real
`0.00000`. The export states coefficients normalised by the run's own dynamic
pressure; at `V = 0` that pressure is zero and the rotor's real thrust has been
divided away before the package sees it. **No rotor coefficient is recoverable
from a static point whatever the package does**, which is also why a hover figure
of merit cannot be offered: it needs a force the run does not state.
