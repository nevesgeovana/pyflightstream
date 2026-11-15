## Airframe coefficients

<a id="airframe-coefficients"></a>

The columns of the `DIM` and `ACOEF` polar files, for a family (one row per
point and family) or for a group (one row per point). Every file opens with
[the run block](the-run-block.md#the-run-block); its identity columns follow,
then the values, and `MESH_FACES` closes the row. The frames and the sign
rules are those of [axes and signs](axes-and-signs.md#axes-and-signs).

<a id="family"></a>

### `FAMILY` and `FAMILY_ID`

`FAMILY` is the family's name in the OBJ or FSM. `FAMILY_ID` is its 1-based
position in the geometry's boundary inventory, the `boundaries` list in file
order that `pyfs-matrix inventory` writes and the run record keeps as
`inventory`.

<a id="group"></a>

### `GROUP` and `GROUP_ID`

A group file carries `GROUP` and `GROUP_ID` in place of `FAMILY` and
`FAMILY_ID`. `GROUP_ID` is stable for a given reference and pproc: `0` for
`TOTAL` (every family), `1` for `AIRFRAME` (every family not inside a rotor),
`10 + <id>` for the group of rotor `<id>`, and `100 + k` for the k-th group of
`[groups]`, 1-based in the order written. A group's values are formed from the
sum of its members' dimensional loads, never by summing coefficients.

<a id="dim"></a>

### Dimensional loads (`DIM`)

`FX_<F>`, `FY_<F>`, `FZ_<F>` in N and `MX_<F>`, `MY_<F>`, `MZ_<F>` in N m:
the force, and the moment about the frame's origin (the moment reference
point for `MRP`), in the frame `<F>` the loads are stated in, named as the
export names it, upper case (`FX_MRP`). No sign is changed: the components are
the solver's. On a steady point they are the export's coefficients times
`q_ref SREF` for the force and `q_ref SREF CREF` for the moment (the export
normalises all three moments by the chord), with `q_ref = 0.5 RHO VREF^2`, the
export's own normalisation, finite at a static point.

<a id="acoef"></a>

### The six coefficients of a frame (`ACOEF`)

For each frame f, in the order W, S, B, R0, R1, ..., six columns, with `F_f`
and `M_f` the force and the moment about the moment reference point in the
forward-right-down axes of f and `q_ref = 0.5 RHO VREF^2`:

<a id="drag-coefficient"></a>

- `CD<f> = -F_f,x / (q_ref SREF)`, the drag coefficient, positive aft;

<a id="side-force-coefficient"></a>

- `CY<f> = F_f,y / (q_ref SREF)`, the side force coefficient, positive right;

<a id="lift-coefficient"></a>

- `CL<f> = -F_f,z / (q_ref SREF)`, the lift coefficient, positive up;

<a id="rolling-moment-coefficient"></a>

- `Cl<f> = M_f,x / (q_ref SREF BREF)`, the rolling moment coefficient;

<a id="pitching-moment-coefficient"></a>

- `Cm<f> = M_f,y / (q_ref SREF CREF)`, the pitching moment coefficient;

<a id="yawing-moment-coefficient"></a>

- `Cn<f> = M_f,z / (q_ref SREF BREF)`, the yawing moment coefficient.

The moments keep the right-hand rule about the frame's axes. The moment turns
as one vector in one length before the span or the chord is applied. A load
that is not a number, or a divisor that is not positive, gives `NA`.

`CLW` and `ClW` differ only in case; a reader that folds case cannot tell
them apart, and `products.json` names the quantity of every column.

<a id="drag-split"></a>

### The drag split

`CD0, CDI` (or `CDV, CDP` on 26.125) follow the frame blocks of `ACOEF`:
the export's drag split, in wind axes, as defined in
[the drag split of 26.125](the-axes-of-a-steady-polar.md#the-drag-split-of-26125).

<a id="mesh-faces"></a>

### `MESH_FACES`

The face count of the geometry the point's run opened, as its boundary
inventory states it, `NA` where it states none (see
[the mesh face count](the-mesh-face-count.md)). It is the last column so that
positional readers keep their places.

<a id="unsteady"></a>

### An unsteady row

An unsteady row averages each dimensional component arithmetically over the
averaging window, then forms its coefficients from the averaged loads: the
rotations are linear and the condition is fixed over the window.
