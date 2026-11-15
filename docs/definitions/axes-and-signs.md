## Axes and signs

<a id="axes-and-signs"></a>

Every coefficient of the polar files is stated in one of four kinds of frame,
named by a letter appended to the column with no underscore: `W` (wind), `S`
(stability), `B` (body) and `R<id>` (the frame of rotor `<id>`), so `CDW`,
`CDS`, `CDB` and `CDR0`. The frames are written in that order, W, S, B, then
every declared rotor with its id ascending. The rotations below are the ones
`pyflightstream.post.axes` applies; the per-column formulas are in
[airframe coefficients](airframe-coefficients.md#airframe-coefficients) and
[rotor coefficients](rotor-coefficients.md#rotor-coefficients).

Direction-cosine matrices are passive and right-handed: `C @ v` gives the
components of the same vector in the turned coordinate system. `C1`, `C2` and
`C3` are that matrix about x, y and z.

<a id="the-export-frame"></a>

### The export frame E

The mesh, the moment reference point, the rotor hubs and axes, and the loads
export are all in the geometry's frame: **x aft, y right, z up**. A geometry
built in another axis-aligned frame is declared in its `boundaries.toml` and
converted before the run, so the loads the post reads are always in this frame.

<a id="the-body-frame"></a>

### The body frame B

Forward, right, down: half a turn about y from the export frame,
`C_B/E = C2(pi) = diag(-1, 1, -1)`.

<a id="the-stability-and-wind-frames"></a>

### The stability frame S and the wind frame W

`C_S/B = C2(-alpha_s)` and `C_W/B = C3(beta_w) C2(-alpha_s)`. The angles are
read off the velocity the solver flies, `V (cos a cos b, cos a sin b, sin a)`
in body axes: `alpha_s = atan2(w, u)` and `beta_w = asin(v / V)`. They equal
the written `ALPHA` and `BETA` when either is zero; at `ALPHA 4, BETA 2` they
are 4.0024 and 1.9951 degrees (see
[the axes of a steady polar](the-axes-of-a-steady-polar.md#the-axes-of-a-steady-polar)).

<a id="the-rotor-frame"></a>

### The rotor frame `R<id>`

Each rotor of the reference carries an integer `id` (0 when it writes none;
two rotors of one reference may not share an id). Its frame `R<id>` is the
body frame turned by the rotor's toe and pitch, taken from the declared shaft
`axis`:

1. The shaft in body axes is `a = C_B/E axis`, a unit vector.
2. **The sense rule**, so thrust is positive forward: if `a_x < 0`, `a = -a`;
   if `a_x = 0` and `a_z > 0`, `a = -a`, so a lift rotor's thrust is positive
   up; if both are 0, `a_y >= 0`.
3. Toe `psi = atan2(a_y, a_x)` and pitch `theta = asin(-a_z)`; pitch is
   positive nose up and toe positive toward +y. A vertical shaft
   (`a_x = a_y = 0`) has toe 0.
4. `C_R/B = C2(theta) C3(psi)`, so `x_R = a`. The roll is zero, so `y_R` is
   horizontal.

The run block states each rotor's angles as `PITCH<id>` and `TOE<id>` in
degrees. No input key states them: they are derived from the shaft.

The rotor's speed `RPM<id>` is signed about its declared axis. Its rate about
`x_R` is `n_R = s RPM<id> / 60` with `s = +1` when `x_R` has the declared
axis's sense and `-1` when the sense rule turned it. Power is invariant under
that turn: the torque and the rate change sign together.

A rotor whose declared axis points aft (a pusher declared with its axis along
+x of the export frame) is turned by the sense rule, so its thrust, its
torque and its in-plane signs are opposite to those of the rotor table it replaces,
which counted thrust along the declared axis. The post warns once per such
rotor.

With zero roll, `y_R` equals `-S` and `z_R` equals `-N` of the in-plane axes
`(T, S, N)` the rotor table it replaces built on a shaft declared in the sense of
`x_R` (see
[the in-plane coefficients](rotor-coefficients.md#the-in-plane-coefficients)),
so `CFZ = CN`, `CFY = -CS`, `CMZ = -CMN` and `CMY = -CMS`.

<a id="signs"></a>

### Signs in every frame

- **Airframe coefficients** (the ACOEF files): `CD` positive aft, `CL`
  positive up, `CY` positive right, in W, S, B and R<id> alike. The moments
  keep the right-hand rule about each frame's forward-right-down axes:
  positive roll is right wing down, positive pitch nose up, positive yaw nose
  right.
- **Rotor coefficients** (the RCOEF files): thrust positive forward along
  `x_R`, so `CT`, `TC` and `TCA` have the opposite sign of the drag-direction
  force in the same frame; the side force positive right and the normal force
  positive up; the moments right-hand about the R axes.
- **Dimensional loads** (the DIM files) keep the solver's components and signs
  in the frame the export states them in.
