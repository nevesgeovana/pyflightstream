## The far-field family

!!! note "Current behavior"
    Far-field lift, induced drag and span efficiency from three independent
    traces of the wake (the section loads, the solver's wake lines, a plane of
    probes), and the conservation balances of a probe survey, selected in the
    `[farfield]` table of the pproc artifact and written to `farfield/`.

**The far field is an instrument, not a second solver.** It integrates what the
solver already exported, downstream of the body, and states a number the solver
does not compute: the solver reports no force in a Trefftz plane (its log's
"Trefftz plane location" is where it clips the wake). The polar and
`campaign_sweep.csv` are never changed by it.

The analyses and where they are written:

| analysis | `[farfield]` selection | reads | writes |
|---|---|---|---|
| Trefftz A, section loads | `[farfield.trefftz] variant = "sections"` | the sectional loads export | `farfield/<group>_trefftz.csv`, `sections/<point>_trefftz_<family>.csv` |
| Trefftz B, wake trace | `variant = "wake"` | the wake lines, `<name>_wakes.vtk` | the same two files, family `TOTAL` |
| Trefftz C, velocity plane | `variant = "plane"` | the probe-points export on the far-field plane or lattice | `farfield/<group>_trefftz.csv` |
| Balances | `[farfield.ledgers]` | the probe-points export on the survey lattice | `farfield/<group>_ledgers.csv` |

`<group>` is the stem of the simulation's polar table. On an unsteady row each
file is written twice, `<group>_<analysis>_instant.csv` (the last time step)
and `<group>_<analysis>_average.csv` (the average over the row's averaging
window), and each manifest entry states `reduction` as `instant` or `average`.

What each analysis needs and is not declared, the plan adds and says so; see
[What the plan adds](#what-the-plan-adds).

### Notation and axes

- `V` the free-stream speed, `rho` the point's density, `q = rho V^2 / 2`.
- Wind axes: `x` along the free stream, downstream; `y` to the right; `z` up.
  Every component below is in these axes, turned from the export's frame in the
  post step before any integral (the far-field core never turns a vector).
- `SREF` and `BREF` from the reference artifact; `AR = BREF^2 / SREF`.
- Coefficients: `CL_T = L / (q SREF)`, `CDI_T = D_i / (q SREF)`,
  `CY_T = Y / (q SREF)`, and

        E_T = CL_T^2 / (pi AR CDI_T)

  `NA` where `CDI_T` is zero or not finite.
- A value the analysis cannot compute is `NA`
  ([The token for a value that does not exist](the-token-for-a-value-that-does-not-exist.md)).

<a id="the-discrete-trace"></a>

### The discrete trace (shared by A and B)

A trace is an ordered list of points `(y_i, z_i)`, `i = 0 .. N-1`, along one
wake sheet in the Trefftz plane, each carrying the circulation `Gamma_i` of the
strip around it.

**Strip edges, the extended rule.** Between two points the edge is their
midpoint; beyond each end point the edge lies half the adjacent spacing further
out:

    e_0     = p_0 - (p_1 - p_0) / 2
    e_j     = (p_{j-1} + p_j) / 2              j = 1 .. N-1
    e_N     = p_{N-1} + (p_{N-1} - p_{N-2}) / 2

with `p` the point position along the trace (the edges of a trace in `(y, z)`
are built on both coordinates by the same rule). For `N` uniform stations at
the centers of `N` equal strips, which is how the solver lays a section
distribution, the edges tile exactly the extent the solver divided, and the tip
filament stands at the tip.

**Trailing filaments.** A filament leaves every edge with the circulation shed
there, `dGamma_j = Gamma_j - Gamma_{j-1}`, with `Gamma_{-1} = Gamma_N = 0`; its
circulation about `+x` is `-dGamma_j`.

**Normalwash.** At the point `c_i = (y_i, z_i)` of strip `i` (its station, or
its crossing), the crossflow induced by the filaments in the plane, a filament
`k` at `(y_k, z_k)` contributing

    (v, w) = -dGamma_k / (2 pi r^2) * (-(z - z_k), (y - y_k)),    r^2 = (y - y_k)^2 + (z - z_k)^2

and `v_n,i` the component along the strip's upward normal
`n_i = (-dz, dy) / ds`.

**Forces.** With `ds_i`, `dy_i`, `dz_i` the strip's length and its projections:

    L   =  rho V  sum_i Gamma_i dy_i
    Y   = -rho V  sum_i Gamma_i dz_i
    D_i = -(rho / 2) sum_i Gamma_i v_n,i ds_i

On a flat trace (`z` constant) the normalwash is the Trefftz-plane downwash,
twice the downwash at the lifting line, and the drag reduces to

    w_LL(c_i) = (1 / (4 pi)) sum_j dGamma_j / (c_i - e_j)          (positive down)
    D_i       = rho sum_i Gamma_i w_LL(c_i) dy_i

**Families, two values.** Each family row carries two induced drags:

- `CDI_T`, the family's share of the total: the sum over its own strips with
  the normalwash induced by every selected family's filaments. The family
  shares add up to the total.
- `CDI_T_ISOLATED`, the family alone: the sum over its own strips with the
  normalwash induced by its own filaments only. The `TOTAL` row's value is `NA`
  (does not apply); the total minus the sum of the families' isolated values is
  the interference drag between them.

**Symmetry.** On a half model (`SYMMETRY = MIRROR`) whose points all lie on one
side of the reference XZ plane, the trace is mirrored, and the inner edge of the
innermost strip is set on the plane, so no filament is shed at the root by the
mirror. A half model with points on both sides is not traced. A half model whose
`SYMMETRY_LOADS` is false reports the coefficients of the meshed half, as its
polar does.

**Spanwise quantities** (written per strip):

    w(y)        = w_LL                          downwash at the lifting line, m/s, positive down
    alpha_i(y)  = atan(w_LL / V)                induced angle, deg
    d_i'(y)     = rho Gamma w_LL                induced drag per unit span, N/m
    cdi(y)      = d_i' / (q c)                  on the local chord c (A only)

**The discretization bias.** On an elliptic loading the span efficiency of the
discrete trace exceeds the exact `e = 1` by 1.05 percent at 40 stations per side,
0.52 percent at 80 and 0.26 percent at 160: the bias halves when the stations
double. Where the absolute `CDI_T` matters, use 80 stations per side or more;
the plan lays 80 when it adds a distribution, and warns, naming this bias, when
a reused distribution has fewer.

<a id="trefftz-a"></a>

### Trefftz A, from the section loads

**Input.** The sectional loads export of each selected family: stations
(`Offset`), chord, quarter-chord position (`X_QC`, `Z_QC`) and the force line
densities `Fx`, `Fz` (N/m) in the section axes.

**Circulation.** For a distribution cut in planes XZ of a frame whose axes are
the reference axes,

    l'    = Fz cos(alpha) - Fx sin(alpha)          lift per unit span, N/m
    Gamma = l' / (rho V)                           m^2/s

**Trace.** The stations along the span at the height of their quarter-chord
points (`Z_QC`): a straight wake leaving the lifting line, no roll-up. It
follows dihedral and separates two lifting surfaces at different heights; for a
flat wing it is the planar trace. Then [The discrete trace](#the-discrete-trace).

**Assumptions and validity.**

- The wake leaves the lifting line straight downstream and does not roll up or
  deform; the result is the induced drag of that frozen sheet. A wing whose wake
  rolls up strongly before it leaves the near field is better served by B.
- Steady flow, zero sideslip: a point with sideslip is not traced by A.
- A distribution cut in other planes, or in a frame whose axes turn, is not a
  spanwise trace and is not used.
- The loading between the outermost station and the strip edge beyond it is the
  outermost station's; nothing is extrapolated to a tip value of zero.
- On a coupled FSI row the section cut is fixed in space, so the trace is the
  projected span of the deformed surface.
- Rotors are not traced: a helical wake is not a streamwise sheet.

<a id="trefftz-b"></a>

### Trefftz B, from the solver's wake

**Input.** The wake export `<name>_wakes.vtk`: the solver's wake lines, one per
trailing-edge node, as chains of segments, each line carrying one value,
the circulation each line sheds, constant along the line. Empty polygon blocks
and redundant point-coordinate scalars are accepted. Connected node indices
preserve both exported mirror halves. For a mirror model, post selects one
half by its upstream nodes and reflects its strips once; coincident root lines
are omitted. Zero-strength collapsed lines are omitted with a warning that
their missing shed circulation can bias the result.
Its coordinates are in the simulation's length unit, which post reads from the
point's saved simulation; a point whose unit cannot be read is a named skip.

**Trace.** The plane normal to the free stream at `distance_bref BREF` behind
the most downstream point of the selected families. Each wake line is cut at its
first crossing of the plane (linear interpolation on the straddling segment).
The crossings are ordered along each sheet by where their lines start on the
trailing edge, so a rolled-up sheet keeps its order. Each crossing is a trace
edge of a strip. On a mirror half, ordered from root to tip, the raw strip
circulation between lines `j` and `j+1` is the negative sum of exported values
from line `j+1` through the tip. It is placed at the midpoint of those crossings.
On a full sheet with signed filament strengths, sum the negative values from
the first edge through line `j`. Mirror halves include the central strip
between their innermost crossings with the accumulated root circulation.
Apply the force equations of [The discrete trace](#the-discrete-trace) at
these midpoints, using the actual wake crossings as filament positions,
with `Gamma = k Gamma_raw`. Signed edge projections preserve folded topology;
crossings are never re-sorted after roll-up.

**The scale, calibrated from the near field.** The scale of the exported value
is not documented by the solver. `k` is the factor that makes the trace's lift
equal the solver's own `CL` of the point:

    k = CL_near q SREF / (rho V sum_i Gamma_raw_i dy_i)

so `CL_T` of variant B equals the solver's `CL` by construction and carries no
information of its own; `CDI_T`, which scales with `k^2`, and `E_T`, which does
not depend on `k`, are what B adds. The factor is written as `GAMMA_SCALE`. A
point without a near-field `CL`, or with a zero one, writes `E_T` only.

**Agreement with A.** On a flat wake whose lines bound A's strips and whose
shed values reconstruct A's circulation, B returns A's numbers. Reading the
line value itself as strip circulation is incorrect: it changes the lift scale
and span efficiency with refinement. The recorded fine-mesh comparison gives
raw lift within 3 percent of the near field and efficiency within 0.03 of A.

**Assumptions and validity.**

- The trace is the solver's relaxed wake at the plane, roll-up included; it is
  as converged as the wake the solver relaxed.
- The plane must lie inside the wake: a line that ends before it makes the
  point's B value `NA`.
- One `TOTAL` row per point: the export does not say which family a line
  belongs to.
- Rotors are not traced.

<a id="trefftz-c"></a>

### Trefftz C, from a plane of probes

**Input.** The probe values on the far-field plane: for a wing, a uniform
rectangular grid normal to the free stream of each point (it turns with the
angle of attack and the sideslip), centered on the free-stream line through the
moment reference point, at `distance_bref BREF` behind the selected families;
for a rotor, one station of its survey lattice. Velocities are turned to wind
axes (wing) or lattice axes (rotor); the static pressure is `p - p_inf = Cp_ref q_ref`,
the export's coefficient on the reference velocity, which a rotor at rest still has
(on a wing at speed with the reference velocity the free stream, `Cp q`). The
probe positions are in the simulation's length unit, read as for Trefftz B.

**Induced drag, the crossflow energy (Munk).**

    D_i = (rho / 2) integral_P (v^2 + w^2) dS

The integrand is the crossflow-energy integrand of the balances
([The balances](#the-balances)) with the advecting velocity set to `V`; the
balance advects with the sampled `u`, which differs at second order in the
perturbation. Written as `CDI_T`.

**Induced drag, the vorticity (Maskell).** From the streamwise vorticity
`xi = dw/dy - dv/dz` (central differences on the grid) and its stream function
in the plane,

    psi(P)    = -(1 / (2 pi)) sum_Q xi_Q ln|P - Q| dS_Q
    D_i,vort  = (rho / 2) sum_P psi_P xi_P dS_P

written as `CDI_T_VORT`; it does not depend on the plane's extent once the plane
holds all the vorticity, so a difference between `CDI_T` and `CDI_T_VORT` flags
a plane too small for the wake.

**The Bernoulli residual, Betz's artificial velocity.** With the total-pressure
deficit

    p0_inf - p0 = (p_inf - p) - (rho / 2) (u^2 + v^2 + w^2 - V^2)

and the artificial axial velocity `u* = sqrt(u^2 + 2 (p0_inf - p0) / rho)`,

    D_p = integral_W [ (p0_inf - p0) + (rho / 2) (u* - u) (u* + u - 2 V) ] dS

over the part `W` of the plane where `p0 < p0_inf`, written as the coefficient
`BERNOULLI_RESIDUAL = D_p / (q SREF)`. Where the sampled field satisfies
Bernoulli's relation exactly, as a field induced by surface and wake
singularities does, `p0 = p0_inf` everywhere, `u* = u`, and the term is zero by
construction: its value then measures how far the exported pressure and velocity
depart from that relation. In a field that carries total-pressure loss the same
integral is the profile drag (Betz, Maskell); no column of 0.40.0 names it a
drag.

**Rotor channels** at a lattice station, `u' = u - V`, `v_theta_0` the azimuthal
mean of the swirl:

    P_AXIAL     = (rho / 2) integral u'^2 u dS
    P_SWIRL     = (rho / 2) integral v_theta_0^2 u dS
    P_CROSSFLOW = (rho / 2) integral (v_r^2 + v_theta^2 - v_theta_0^2) u dS
    P_TOTAL     = integral (p0 - p0_inf) u dS
    ETA_FF      = T V / (T V + P_AXIAL + P_SWIRL + P_CROSSFLOW)

with `T` the axial force of the balance between the inlet and that station;
`ETA_FF` is `NA` at `V = 0`.

**The quasi-steady rotor.** A `qsteady_rotor` point holds the blades still and
carries the rotation in the free stream, so its probe velocities are those of
the frame that turns with the blades. Before any integral they are converted to
the hub frame by adding back the frame velocity of the rotor the lattice names,

    v_hub = v_probe + Omega x (x - x_hub)

with `Omega` along the rotor's axis and the sense of its speed, so the channels
and the balances are those of the rotor turning in still air. The speed is the
one every product of the point reads: the run's plan where it states one, and
otherwise the row's own speed in the quasi-steady record beside the loads export,
which a `qsteady_rotor` run always writes. It is signed by the rotor's hand
(`rpm_sign` times the row's `RPM`), and that sign alone gives the sense of `Omega`.

**Quadrature.** The trapezoid rule on the grid (corners a quarter, edges a half
of a cell); a missing sample makes the integral `NA` and `COVERAGE` states the
finite fraction. The same samples integrated on every other grid point give a
second value; `CDI_T_QERR` is the difference.

**Assumptions and validity.**

- Incompressible relations. Above Mach 0.3 the row is written with a WARNING.
- The crossflow energy is truncated at the plane's edges; the energy outside a
  plane of half-width `a` falls as `1/a^2` for a wing's far wake. The vorticity
  path is not truncated this way.
- Probes close to a wake line sample a velocity that grows as the inverse of the
  distance; the grid spacing and `CDI_T_QERR` say how much the plane resolves it.
- Static rotor (`V = 0`): the channels are written; `ETA_FF` is `NA`.

<a id="the-balances"></a>

### The balances on the survey lattice

**The lattice.** Annular planes at stations `x/R`, rings with explicit edges
`r_{j-1/2}`, `r_{j+1/2}` (`r/R`) and `N_psi` uniform azimuths, optionally rings
on a lateral cylinder; cylindrical axes on the rotor shaft, `y = r sin(psi)`,
`z = r cos(psi)`, `x` downstream ([The survey lattice](#the-survey-lattice)).

**Quadrature, once for every balance.**

    w_j   = (1/2) (r_{j+1/2}^2 - r_{j-1/2}^2) dpsi R^2,     dpsi = 2 pi / N_psi
    I[f]  = sum_j sum_k f_jk w_j

A non-uniform azimuth grid is refused: uniform periodic sampling is what makes the
azimuthal rectangle rule spectrally accurate. A missing sample makes `I[f]` `NA`;
`COVERAGE` states the finite fraction.

**Harmonics.** `c_m = (1 / N_psi) sum_k f_k exp(-i m psi_k)`, `m = 0 .. m_max`,
`m_max < N_psi / 2`.

**The balances**, with `u' = u - V`, `p' = p - p_inf`,
`v_r = v sin(psi) + w cos(psi)`, `v_theta = v cos(psi) - w sin(psi)`:

    mass               mdot(x)   = I[rho u]                                     kg/s
    axial              G(x)      = I[rho u u' + p'],   F_X(x) = G(x) - G(x_in)   N
    transverse         T_z(x)    = I[rho u w],         F_Z = T_z(x) - T_z(x_in) + D_lat     N
    torque             Q(x)      = I[rho (r R) v_theta u]                       N m
    in-plane moment    M_Y       = [I[z g] - x I[rho u w]] (x) - [same] (x_in),  g = rho u u' + p'
    crossflow energy   E(x)      = I[(rho / 2) (v_r^2 + v_theta^2) u],
                       E_swirl   = I[(rho / 2) v_theta_0^2 u],   E_induced = E - E_swirl     W

`F_Y` and `M_Z` follow with `v` and `y = r sin(psi)`. The transverse flux and the
in-plane moment are also written from the harmonics (Parseval, every order the
grid carries); the two paths are independent and their difference is a check.
The lateral term `D_lat` is the momentum and pressure flux through the lateral
cylinder, from the lateral rings where the lattice has them.

**Diagnostics, written and not judged.**

    MASS_SPREAD     = max_x |mdot(x) - mean(mdot)| / |mean(mdot)|
    SYMMETRY_FLOOR  = max_{m >= 1} |c_m|                    of the axial velocity
    SPURIOUS_COUNTS = 2 (F_near - F_far) / (rho V^2 SREF) 1e4

**Unsteady rows, instant and average.** The instant is the balance of the
lattice at the last time step. The average is the average, over the row's
averaging window (`LAST_REVS_AVG` or `LAST_ITERS_AVG`, the window the unsteady
products use), of the balance of each step: every flux is computed on each
step's field and then averaged, never computed on an averaged field, because
the fluxes are not linear in the velocity.

**Assumptions and validity.** The lateral cylinder is at free stream unless its
rings say otherwise; the swirl and induced channels are the transverse components
only (no axial-deficit term); the density is the free-stream value; a station cut
by the body is `NA`.

<a id="the-survey-lattice"></a>

### The survey lattice and the far-field plane are probes

The lattice and the plane are probe shapes
([The probes table](the-probes-table.md#the-probes-table)): a `[[probes]]` entry
declares a lattice under `lattices`, beside `lines`, `rectangles` and
`circles`; a declared one is reused by the far field, and one the far field
needs and the artifact does not declare is added by the plan. They are fixed in
space, also on a coupled row: they sample the flow, not the structure.

On a steady row the added plane and lattice are written to one staged
`X,Y,Z,TYPE` CSV in the simulation length unit and appended by one
`PROBE_POINTS_IMPORT`. The file starts with its point count, uses volume
type 1 and preserves the recorded order, plane before lattice. Distinct
point sets have distinct content-derived filenames. Unsteady rows keep
their per-step fluid plots.

<a id="what-the-plan-adds"></a>

### What the plan adds

| analysis | needs | when declared | when not declared |
|---|---|---|---|
| A | a section distribution over each family, planes XZ, reference axes; the sectional loads export | reused | added: frame `MRP`, plane XZ, 80 stations per side |
| B | the VTK export with the wake | reused | the wake switched on in the VTK export, the export added if the row has none |
| C | the plane (wing) or the lattice (rotor); the probe-points export | reused when identical after layout, or when it is the one that qualifies | added as probe points |
| balances | the lattice; the probe-points export | reused when identical after layout, or when it is the one that qualifies | added as probe points |

**Which declaration is reused.** A declared plane or lattice is the far field's when
its points after layout are the far field's own (same frame, every coordinate equal
at the precision a probe position is written in), so a key stated at its default
is the same geometry as the key left out. Where `[farfield]` states no geometry, the
one declaration that qualifies is reused: a lattice on the same rotor, or in the
same frame with the same tip radius, whose azimuths carry `m_max`; a rectangle of
the reference frame that is a Trefftz C plane of the point (one spacing both ways,
an odd count each way, its first edge horizontal and its second upward in the plane
normal to the point's free stream, behind the body). With several that qualify,
only an identical one is reused.

**Post reads the probes the run laid.** The plane and the lattice each point reads,
reused or added, are stated in `plan.json` and carried by the run record
(`farfield_layout`); post lays their points again from it and matches every exported
position to them, each set exactly once, before it integrates, with the grid and
the areas they were laid with. A set it cannot match, or matches twice, is a named
skip, never the points that happen to be last or to number as many. A record
without `farfield_layout` (written before 0.40.0 recorded it) is matched to the
table as it stands: a rotor's lattice where its hub places it, the plane and a
frame's lattice by their shape.

Every addition is stated in `plan.json` (the row's `farfield` object) and on the
console. An `[exports]` entry set to false that the far field needs is turned on
for that row, with a WARNING. The plan refuses only what cannot be produced: an
export the selected build does not have, probes on a row type that takes none, a
family the geometry does not have, on a coupled row a far-field section
distribution beyond the one the coupling uses, and a probe point the plan adds
inside the body. A probe point the user declared inside the body is kept, with a
WARNING.

On an unsteady row the plane or lattice the plan adds is sampled at every time
step (one fluid plot per point and parameter); the plan states that count.

### Where each analysis applies

| row | A | B | C | balances |
|---|---|---|---|---|
| steady, fixed wing | yes | yes | yes | yes |
| steady rotor | no | no | rotor channels | yes |
| `unsteady_rotor` | no | no | rotor channels, instant and average | instant and average |
| `qsteady_rotor` | no | no | rotor channels, in the hub frame | yes, in the hub frame |
| unsteady, fixed wing | no | no | instant and average | instant and average |
| coupled FSI, steady | the coupled distribution | yes | refused (no probes) | refused (no probes) |

A "no" is a named skip: the point appears in `products.json` `skipped` with the
reason, and in `post.log`.
