## The far-field family

!!! note "Current behavior"
    Far-field lift, induced drag and span efficiency from three independent
    traces of the wake (the section loads, the solver's wake lines, a plane of
    probes), and the conservation balances of a probe survey, selected in the
    `[[farfields]]` entries of the pproc artifact and written to `farfield/`.

**The far field is an instrument, not a second solver.** It integrates what the
solver already exported, downstream of the body, and states a number the solver
does not compute: the solver reports no force in a Trefftz plane (its log's
"Trefftz plane location" is where it clips the wake). The polar and
`campaign_sweep.csv` are never changed by it.

The analyses and where they are written:

| analysis | `[[farfields]]` selection | reads | writes |
|---|---|---|---|
| Trefftz A, section loads | `variant = "sections"` | the sectional loads export | `farfield/<group>_trefftz.csv`, `sections/<point>_trefftz_<family>.csv` |
| Trefftz B, wake trace | `variant = "wake"` | the wake lines, `<name>_wakes.vtk` | `farfield/<group>_trefftz.csv`, `sections/<point>_trefftz_net_<entry>.csv` |
| Trefftz C, velocity plane | `variant = "plane"` | the probe-points export on the far-field plane | `farfield/<group>_trefftz.csv` |
| Trefftz D, power | `variant = "power"` | the survey lattice | `farfield/<group>_trefftz.csv` |
| Balances | `variant = "power"` with `balances` | the probe-points export on the survey lattice | `farfield/<group>_ledgers.csv` |

B, C and D identify the whole flow with lowercase `net` in `FAMILY`.
A retains its selected family rows and their `TOTAL` row. B's spanwise file
and its product-manifest key use `_trefftz_net_<entry>.csv`, with `wake` as the
default entry name; entries `near` and `far` retain separate spanwise files.
The super file reads A's `TOTAL` and B/C/D's `net` rows into
`CL_T_<VARIANT>_<ENTRY>`, `CDI_T_<VARIANT>_<ENTRY>` and
`E_T_<VARIANT>_<ENTRY>` columns, one set per entry. For example, A entries
named `wing` and `tail` write `CL_T_A_wing` and `CDI_T_A_tail`; C named `net`
writes `CDI_T_C_net`. An unnamed C entry uses `CDI_T_C_plane`.

### Selecting analyses

Each `[[farfields]]` entry selects one variant. Its optional `name` defaults to
the variant word and must be unique. Name both entries when selecting a variant
twice, for example separate section traces for a wing and tail. Both far-field
tables carry `ENTRY` immediately after `POL`, including every total and ledger row.
Names must also remain distinct as filenames: characters other than ASCII
letters, digits, `_`, `.`, `+` and `-` become `_`, and the resulting spellings
are compared ignoring case for portability across case-insensitive filesystems.
Thus `a/b` and `a_b`, or `near` and `NEAR`, are refused together, naming both
entries and their shared case-folded file spelling (`a_b` or `near`). Accepted
filenames keep the entry's own case.

```toml
[[farfields]]
name = "wing"
variant = "sections"
families = ["Wing"]
stations = 80

[[farfields]]
name = "tail"
variant = "sections"
families = ["HTail"]

[[farfields]]
variant = "plane"
distance_bref = 0.25
half_width_bref = 0.75
half_height_bref = 0.5
spacing_bref = 0.01
```

Keys belong to the analysis that reads them; a key on another variant is refused
with the variants that accept it. `families` is required on `sections` and refused
on `wake`, `plane` and `power`: these read the whole field, respectively every wake
line, the plane and the lattice. `stations` is a count per side on `sections` and
a list of x/R positions on `power`. `distance_bref` belongs to `wake` and `plane`;
the half extents and spacing belong to `plane` alone. `station`, `rotor`, `frame`,
`tip_radius_m`, `n_r`, `r_inner`, `r_outer`, `n_psi`, `lateral_radius`,
`lateral_stations`, `hub_width`, `tip_width`, `m_max` and `balances` belong to `power`.
Its placement requires `rotor`, or `frame` together with `tip_radius_m`.
An unstated `lateral_radius` uses `max(2.5, r_outer)`; a stated radius below
`r_outer` is refused, so increase it or reduce `r_outer`.

Every entry accepts `export_type = "default"`, `"last_step"` or `"avg_window"`.
Unstated means `"default"`. Other values, including `"all_steps"`, are refused.
On steady rows all three values produce the same single-step products.
On unsteady rows `"default"` and `"last_step"` read only the last step,
regardless of the row's `EXPORT_UNSTEADY_*` keys. They write `_instant` only;
the manifest names the absent average. A needs no explicit window to plan.

`"avg_window"` exports A's sectional loads and C/D's conventional probe points
at exactly the steps in the final averaging window. Each entry may specify
`last_revs` (positive turns of the row's rotor clock) or `last_steps` (positive
integer), exclusively; otherwise it uses `LAST_REVS_AVG` or `LAST_ITERS_AVG`.
The window ends at the last recorded step and clips to the run if longer.
Multiple entries export the union of their windows. Other per-step products
retain the row's export threshold. The average is the mean of the per-step
analysis results, and is skipped if any window snapshot is missing.
B retains its steady-only applicability.

`last_revs` and `last_steps` are refused on steady rows and with `export_type`
other than `"avg_window"`. `last_revs` without a rotor clock is refused naming
`last_steps`. Normal declared probes do not restrict the far-field window.
The manifest records each entry's `export_type`; each average also records
its window, sample count and source under `reduced_from`.

The retired `[farfield]` spelling is refused at load with equivalent array entries.
Its families move to A alone. Its ledgers become a `power` entry. A retired rotor
`plane` analysis with ledgers means the power analysis; request a separate `plane`
entry only when a velocity plane is also wanted.

`<group>` is the stem of the simulation's polar table. Every row of these files, and
of the spanwise files, ends with `STATUS`, the point's solver termination status as
`campaign_sweep.csv` writes it, so a point that is not converged says so on its rows. On an unsteady row each
file has `<group>_<analysis>_instant.csv` (the last time step), and under
`"avg_window"`, `<group>_<analysis>_average.csv` (the entry's window average).
Each manifest entry states `reduction` as `instant` or `average`.

What each analysis needs and is not declared, the plan adds and says so; see
[What the plan adds](#what-the-plan-adds).

### Notation and axes

- `V` the free-stream speed, `rho` the point's density, `q = rho V^2 / 2`.
- Wind axes: `x` along the free stream, downstream; `y` to the right; `z` up.
  Every component below is in these axes, turned from the export's frame in the
  post step before any integral (the far-field core never turns a vector).
- `SREF` and `BREF` from the reference artifact; `AR = BREF^2 / SREF`.
- `CL_near` the solver's `CL` of the point restated on `q`: the export divides by
  the dynamic pressure of its reference velocity `VREF`, so
  `CL_near = CL (VREF / V)^2`, the solver's `CL` itself where `VREF` is `V`.
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
- The trace holds the lift of the selected families only. Where it departs from the
  solver's `CL` by more than 5 percent (a wing selected without its body), post
  writes a WARNING with both lifts: the drag and the span efficiency are then those
  of the traced families, not the configuration's.

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
equal the solver's own lift of the point:

    k = CL_near q SREF / (rho V sum_i Gamma_raw_i dy_i)

so `CL_T` of variant B equals `CL_near` by construction and carries no
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
- One `net` row per point: the export does not say which family a line
  belongs to.
- Rotors are not traced.

<a id="trefftz-c"></a>

### Trefftz C, from a plane of probes

**Input.** The probe values on the far-field plane: a uniform
rectangular grid normal to the free stream of each point (it turns with the
angle of attack and the sideslip), centered on the free-stream line through the
moment reference point, at `distance_bref BREF` behind the whole geometry.
This includes steady RPM, `unsteady_rotor` and `qsteady_rotor` rows. On a
`qsteady_rotor` row the probes read the frame that turns with the blades, so
their velocities are first converted to the hub frame exactly as the lattice's
are ([The quasi-steady rotor](#trefftz-d-power-on-the-survey-lattice)),
`v_hub = v_probe + Omega x (x - x_hub)`, about the row's one rotor with its signed
speed; the static pressure is frame independent and kept. A sector is one
solve and writes one C row. A wheel solved at several clockings exports the
plane with its full export set, at clocking 0 alone: its C row is clocking 0's,
post names that limitation as a skip, and no clocking average is written.
Velocities are turned to wind axes; the static pressure is `p - p_inf = Cp_ref q_ref`,
the export's coefficient on the reference velocity, which a rotor at rest still has
(on a wing at speed with the reference velocity the free stream, `Cp q`). The
probe positions are in the simulation's length unit, read as for Trefftz B.

**Induced drag, the crossflow energy (Munk).**

    D_i = (rho / 2) integral_P (v^2 + w^2) dS

The integrand is the crossflow-energy integrand of the balances
([The balances](#the-balances)) with the advecting velocity set to `V`; the
balance advects with the sampled `u`, which differs at second order in the
perturbation. Written as `CDI_T`. On rotor configurations this is the net
configuration induced drag, including swirl; efficiency uses configuration
`CL`, and the Bernoulli residual remains an informative field check.
The propeller slipstream's total-pressure gain can make that residual depart
from zero; this is information about the powered field, not an error.

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
integral is the profile drag (Betz, Maskell); no output column names it a
drag.

**The plane's own lift, a check of the field.** From the same vorticity,

    L_plane = rho V sum_P y_P xi_P dS_P

the Kutta-Joukowski lift of the trailing vorticity the plane holds (for a flat sheet
of strip circulation `Gamma` it is `rho V integral Gamma dy`, and roll-up does not
change it), written as `CL_T` of the C row. A plane that holds the wake the loads
shed carries the solver's lift; where `CL_T` departs from `CL_near` by more
than 10 percent (or by an absolute difference greater than 1e-3 when
`|CL_near| < 1e-3`), the probe field does not hold that circulation and its crossflow
energy is not the loads' induced drag: the row is written and post writes a
WARNING with both values. `E_T` of the C row is formed with `CL_near`.

**Quadrature and validity.** The plane uses the trapezoid rule (corners a
quarter, edges a half of a cell). Missing samples make the integral `NA`;
Plane-normal offsets allow each coordinate's printed precision, including the
first point's precision, projected onto the normal, plus 0.001 of the spacing.
`COVERAGE` is the finite sampled area fraction. Every other grid point gives
the second value used for `CDI_T_QERR`. Relations are incompressible; Mach
above 0.3 warns. Crossflow energy outside the finite plane is omitted, and
probes close to wake lines need spacing refinement.

### Trefftz D, power on the survey lattice

`variant = "power"` reads `station` in x/R, defaulting to the last lattice
station, on every row type, including power-off rows. Placement requires
`rotor` or `frame` plus `tip_radius_m`. The row has `VARIANT = D` and
`FAMILY = net`; `balances` additionally requests the ledger rows.

An explicit `station` must select one declared lattice station. Loading refuses
an absent or ambiguous station and names the entry and available stations.
An exact match wins; otherwise relative and absolute roundoff tolerances of
`1e-12` apply, as when reading the sampled field.

**Power channels** at a lattice station, `u' = u - V`, `v_theta_0` the azimuthal
mean of the swirl:

    P_AXIAL     = (rho / 2) integral u'^2 u dS
    P_SWIRL     = (rho / 2) integral v_theta_0^2 u dS
    P_CROSSFLOW = (rho / 2) integral (v_r^2 + v_theta^2 - v_theta_0^2) u dS
    P_TOTAL     = integral (p0 - p0_inf) u dS
    ETA_FF      = T V / (T V + P_AXIAL + P_SWIRL + P_CROSSFLOW)

with `T` the axial force of the balance between the inlet and that station;
`ETA_FF` is `NA` where `T V <= 0`, including static and power-off conditions.
On a rotor row with blade loads, `P_TOTAL_CORRECTED_W` and `ETA_FF_CORRECTED`
are the same channels on the pressure corrected by the disk total-pressure rise
([The balances](#the-balances)).

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

The annular quadrature and coverage are those of the balances below.

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
`COVERAGE` states the fraction of the plane's area that was sampled, a missing sample weighted by the annular cell it stands for (`pyflightstream.farfield.sample_area_coverage`).

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
cylinder, from the lateral rings where the lattice has them. The plane term and
`D_lat` are written apart (`FZ_PLANE_N`, `FZ_LATERAL_N`), `D_lat` as the
lateral term of `pyflightstream.farfield.transverse_force`, which never folds it
into the plane term.

**Diagnostics, written and not judged.**

    MASS_SPREAD     = max_x |mdot(x) - mean(mdot)| / |mean(mdot)|
    SYMMETRY_FLOOR  = max_{m >= 1} |c_m|                    of the axial velocity
    SPURIOUS_COUNTS = 2 (F_near - F_far) / (rho V^2 SREF) 1e4

For a lattice serving a rotor of B blades, G3 (`SYMMETRY_FLOOR`) omits the
blade-passage orders B, 2B, ... through `m_max`. B comes from the row's recorded
blade count (including periodic copies), or the rotor's declared blade families.
A non-rotor lattice retains every order from 1 through `m_max`. The product
manifest's `symmetry_excluded_orders` maps each point and entry to the excluded
orders. If no order remains, G3 is `NA`: no symmetry floor was measured.
A six-blade signal with `|c_6| = 0.4828 m/s` and `|c_1| = 3.47e-5 m/s`
therefore reports `3.47e-5 m/s` at `m_max = 6`, the same as at `m_max = 5`.

**The rotor's disk total-pressure rise.** On a rotor row (a power entry naming
`rotor = ...`, or any `unsteady_rotor` or `qsteady_rotor` row, including an entry
naming a frame) the exported probe pressure is the Bernoulli pressure of the probe
velocity with the free-stream total pressure: inside the slipstream it lacks the
total-pressure rise the blades add, so the lattice axial balance alone cannot
balance the rotor thrust. The PFS-2165 measurement (G4SPLIT, 2026-10-26,
FlightStream 26.124) found a pressure/Bernoulli integral ratio of approximately
1.01053, pointwise residual at most 3.32605 Pa, and at 2 R a window momentum flux
of 680.83791 N with a pressure contribution of -993.97923 N, giving -313.14132 N
versus 646.7 N near-field thrust.

Post reconstructs the rise from the rotor's own blade sectional loads, never from
the probe swirl:

1. The loads of each blade distribution cut in a blade frame (`LOCAL_AXIS`) or the
   rotor frame (`<ALIAS>_RMRP`), in planes containing the shaft: the force density
   along the shaft is the blade's axial force, the other in-plane density its
   tangential force, `Offset` the radius. The blades are averaged, the result is
   summed over the rotor's blade count (periodic copies included) and turned to
   the loading on the fluid, `dT/dr` and `dQ/dr`. On an unsteady row the per-step
   exports of the averaging window are averaged when they cover it; otherwise the
   final export is read.
2. Per annulus,

        dp0(r_d) = (dT/dr) / (2 pi r_d) + rho v_theta^2 / 2
        v_theta  = (dQ/dr) / (rho v_a 2 pi r_d^2)

   with `v_a` the azimuthal mean axial velocity of the mapping station at `r_d`
   (for an ideal rotor the swirl term equals the Euler form
   `Omega (dQ/dr) / (2 pi r v_a)` written as a static jump plus swirl), the loading
   interpolated linearly between strip centres and zero outside the strip edges.
3. The mapping station is the first lattice station behind the blades' axial
   reach (the largest axial quarter-chord coordinate plus the chord). Each ring
   of that station and of every station behind it is mapped to its disk radius
   `r_d` by equal mass flow (the azimuthal mean of `rho u` integrated from the
   innermost ring edge), the mapping station's radius standing for the disk's.
4. The corrected pressure is `p' + dp0(r_d)`. Upstream of the blades `dp0 = 0`; a
   station cut by the blades (`|x/R|` within their reach) is `NA`, never
   extrapolated.

The corrected columns are written beside the uncorrected ones, which stay:
`P_PRIME_CORRECTION_N` (the integral of `dp0` over the station),
`AXIAL_FLUX_CORRECTED_N` and `FX_CORRECTED_N` in the ledgers, and
`P_TOTAL_CORRECTED_W` and `ETA_FF_CORRECTED` on the D row (the same channels on
the corrected pressure, `T` the corrected axial force). G4 (`SPURIOUS_COUNTS`) and
`F_NEAR_N` on a rotor row compare the near field with the corrected axial balance.
These columns appear only in a table where a rotor row carries them, before
`STATUS`; a table of rows without a rotor keeps its columns and bytes.

Where the row exported no usable blade loads, `SPURIOUS_COUNTS` and `F_NEAR_N` are
`NA` in the instant and averaged ledgers with a named skip saying why, and the
corrected columns are absent. Flux and other ledger columns stay;
`F_NEAR_VISCOUS_N` remains available when the loads supply it. In the ideal
actuator disk (uniform or smooth loading, exported pressure the Bernoulli
pressure) the corrected axial balance returns the thrust at every far-wake
station; at a station close behind the disk the one-dimensional model the
correction assumes leaves the static pressure outside the slipstream out.

A wing with no rotor keeps G4. It compares like with like: `F_near` is the inviscid near-field axial force,
written as `F_NEAR_N`. The total projection minus `F_NEAR_VISCOUS_N` gives
`F_NEAR_N`; adding those two columns reconstructs the old total.
The viscous force is assumed to act along the free-stream direction with
magnitude `CDo q S` (`CDv` in newer loads exports), using the loads reference
dynamic pressure. It is projected on the lattice axis with exactly the same
sign as the total force. For example, a total of -29.106 N, a viscous projection
of -29.106 N and a far-field force of 7.938 N at `q S = 4410 N` give
`F_NEAR_N = 0` and G4 = -18 counts.

For an averaged ledger, G4 compares the window mean axial flux difference with
the mean inviscid near-field axial force over exactly the same steps. The latter comes
from the point's whole-configuration global force plots history, the series read
by its unsteady polar, subtracting the projected viscous scalar from the same
history (`CDO_<group>` on 26.125). The written history coefficients are already
on free-stream dynamic pressure. Missing history, viscous drag (including the
26.124 control plots), or a missing window step gives `NA` for G4 and
`F_NEAR_N` and a named `SPURIOUS_COUNTS` skip; the instant still uses the final
loads export. A drag group must cover the whole configuration.

**Unsteady rows, instant and average.** The instant is the balance of the
lattice at the last time step. The average is the average, over the row's
averaging window (`LAST_REVS_AVG` or `LAST_ITERS_AVG`, the window the unsteady
products use), of the balance of each step: every flux is computed on each
step's field and then averaged, never computed on an averaged field, because
the fluxes are not linear in the velocity.

**What the balances measure.** They integrate the probe field the solver exported,
and close against the near-field thrust and torque only where that field holds the
circulation of the solver's own wake. A field whose swirl does not follow its own
wake lines (Stokes' theorem) gives balances that move from station to station while
the mass flow stays constant; they are then a check of the probe field, not a
far-field thrust.

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
A steady entry in the reference frame emits its declared lattices with
`pyflightstream.probes.emit_probe_points`, placed on the rotor's hub or the
reference axes, in the simulation length unit and rounded to five decimals.
The minimum lattice spacing must be at least twice the coordinate tolerance at
its reach divided by 0.25; a refusal states that spacing in native units and
names `r_inner`, `n_psi`, `n_r`, `r_outer` and `stations` as the controls to adjust.

On a steady row the added plane and lattice are written to one staged
`X,Y,Z,TYPE` CSV in the simulation length unit (by
`pyflightstream.probes.write_points_csv`, or `write_probe_csv` with the same
placement for a lattice added alone) and appended by one
`PROBE_POINTS_IMPORT`. The file starts with its point count, uses volume
type 1 and preserves the recorded order, plane before lattice. Distinct
point sets have distinct content-derived filenames. On every row type the
far field uses conventional probe points, never fluid plots. Its own export is
`<point>_farfield_survey.txt`, with
`<point>_farfield_survey_iteration=<step>.txt` at each `"avg_window"` step.
The FR-1052 warning states points per exported step and the exported step count.
On unsteady rows, sets used by any `avg_window` entry are imported at the
window-start action. Sets needed only by `last_step` or `default` entries
are appended after the march. Each phase parks its own counted CSV and emits
one import. A shared set is imported once, at window start, and remains in
the final export. Window snapshots exclude final-only sets. Each recorded
shape names its import phase and the exports carrying it; warnings state each
set's point count, window steps and final export.
Declared `instantaneous` probes keep their fluid plots and history table
(`probes/<point>_probes_history.csv` when mixed with default entries).
With `default` declared probes, the final far-field export also contains those points;
the far field selects its own by the offsets recorded during construction.
Each set has an identity, a zero-based offset within its phase's import,
a count, and a final-export offset. A reused declaration keeps its identity;
two exports reading the same far-field shape share one imported set. Equal
coordinates in distinct declared entries do not merge their identities.
When a declaration contains several shapes, `sample_offset` locates the
far-field shape within that declaration and `count` retains its shape count;
`set_count` records the entire imported declaration's size.

<a id="what-the-plan-adds"></a>

### What the plan adds

| analysis | needs | when declared | when not declared |
|---|---|---|---|
| A | a section distribution over each family, planes XZ, reference axes; the sectional loads export | reused | added: frame `MRP`, plane XZ, 80 stations per side |
| B | the VTK export with the wake | reused | the wake switched on in the VTK export, the export added if the row has none |
| C | the configuration plane; the probe-points export | reused when identical after layout, or when it is the one that qualifies | added as probe points |
| D | the entry's survey lattice; the probe-points export | reused when identical after layout, or when it is the one that qualifies | the stated lattice is laid as probe points |
| balances | the lattice; the probe-points export | reused when identical after layout, or when it is the one that qualifies | added as probe points |
| D and balances on a rotor row | the blade sectional loads for the disk total-pressure rise | reused (a distribution in a blade or rotor frame) | `unsteady_rotor`: one distribution per blade in its own frame, 50 stations, and the sectional loads export (per step over the window under `"avg_window"`); other rotor rows: `not_applicable` with a WARNING, G4 stays `NA` |

**Which declaration is reused.** A declared plane or lattice is the far field's when
its points after layout are the far field's own (same frame, every coordinate equal
at the precision a probe position is written in), so a key stated at its default
is the same geometry as the key left out. Where an entry states no geometry, the
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
without `farfield_layout` (written before far-field layouts were recorded) is matched to the
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

On an unsteady row the plane or lattice uses conventional probe points.
`"default"` and `"last_step"` export only after the march; `"avg_window"`
requests snapshots only over the final averaging window. The plan states
the point count per exported step and the number of exported steps.
Post selects each entry's recorded sets for its own export: for example, C
`last_step` reads its plane from the final survey while D `avg_window` reads
its lattice from the window snapshots. A missing or duplicated set remains a
named skip. Steady and quasi-steady rotor scripts retain their analysis route.

### Where each analysis applies

| row | A | B | C | balances |
|---|---|---|---|---|
| steady, fixed wing | yes | yes | yes | yes |
| steady rotor | nonrotor families | no | configuration plane | yes |
| `unsteady_rotor` | nonrotor families | no | configuration plane, instant and average | instant and average |
| `qsteady_rotor` | no | no | configuration plane, in the hub frame | yes, in the hub frame |
| unsteady, fixed wing | yes | no | instant and average | instant and average |
| coupled FSI, steady | the coupled distribution | yes | refused (no probes) | refused (no probes) |

A refuses any selection, including selector words, that resolves to a rotor
block's blade or general families. The refusal names the rotor and families
and points to the reference aliases for lifting surfaces. A and B on a
`qsteady_rotor` row are not applicable, never refused: that row holds an
isolated rotor, with no lifting surface outside it, so the plan states each
entry `not_applicable` with a WARNING naming the entry and stays ready, and
post names the skip. One pproc thus serves the `unsteady_rotor` row that
carries the lifting surfaces and the `qsteady_rotor` row of its rotor. On unsteady rows A writes the end-of-run sectional trace as instant;
its average computes each step's trace before averaging. Missing per-step
sectional exports produce a named average skip in the manifest and `post.log`.
For A, `export_type = "avg_window"` requests the stamped sectional-load
exports automatically over its final window, independently of the row's
`EXPORT_UNSTEADY_*` threshold. Average products in the table above require
`"avg_window"`; `"default"` and `"last_step"` produce only the instant.

A "no" for B is a named skip: the point appears in `products.json` `skipped` with the
reason, and in `post.log`.


### Python entry points

`pyflightstream.farfield.plane_lift` integrates the streamwise vorticity
on a Trefftz C plane to obtain its Kutta-Joukowski lift. The same function is
available from `pyflightstream.farfield.trefftz`.

`pyflightstream.post.farfield_fields.FarLayout` describes the plane and lattice
positions and grid used to match the exported samples. `recorded_layout`
rebuilds it from a run record's `farfield_layout` shapes; `derived_layout`
constructs the layout from the pproc table for a historical record that has no
layout. These names are public and appear in the generated API reference.
They keep the maturity of their modules: Trefftz is provisional, and the post
layout reader is provisional. A public name does not establish licensed
validation on an unmeasured solver build.
