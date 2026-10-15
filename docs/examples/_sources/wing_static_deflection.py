# %% [markdown]
# # Static deflection of the generic wing under its polar design load
#
# The FSI subpackage is blade oriented, but at Omega = 0 its beam
# machinery reduces to a classic clamped cantilever: no centrifugal
# tension, no propeller moment. This example applies it to the
# project's generic wing, the synthetic NACA 0012 of
# `pyflightstream.qa.geometry` (chord 1 m, span 8 m, AR 8) that flies
# the steady polar example, and prescribes structural inputs sized for
# reasonable numbers:
#
# 1. flight point and elliptical lift from the measured polar slope;
# 2. structural prescription: EI from a 3 percent tip deflection
#    target, GJ from a half degree twist target, plausible mass;
# 3. static solve: bending and torsion along the span;
# 4. modal sanity: first bending and torsion frequencies.
#
# Everything is synthetic and self-contained: no solver run, no real
# aircraft data. The load is prescribed, not iterated: this is the
# static response to a frozen load, not a divergence analysis.

# %%
"""Wing static deflection example: generic NACA 0012 wing, prescribed elliptical load."""

import math

from pyflightstream.fsi import beam
from pyflightstream.fsi.config import BladeProperties, FsiConfig
from pyflightstream.qa.geometry import WingSpec

# %% [markdown]
# ## 1. The wing and its design point
#
# Same wing and flight point as the steady polar example: 30 m/s at
# sea level. The lift slope 4.83/rad was measured on FlightStream
# 26.120 (HND-016); at 6 degrees the wing carries about 2230 N. Each
# clamped half wing takes half of that, distributed elliptically,
# which is both the classic ideal and consistent with an AR 8
# rectangular wing.

# %%
wing = WingSpec(naca="0012", chord_m=1.0, span_m=8.0)
HALF_SPAN_M = wing.span_m / 2.0
RHO_KG_M3 = 1.225
VELOCITY_M_S = 30.0
ALPHA_DEG = 6.0
CL_SLOPE_PER_RAD = 4.83

q_pa = 0.5 * RHO_KG_M3 * VELOCITY_M_S**2
cl = CL_SLOPE_PER_RAD * math.radians(ALPHA_DEG)
half_lift_n = 0.5 * q_pa * wing.area_m2 * cl
peak_n_per_m = 4.0 * half_lift_n / (math.pi * HALF_SPAN_M)
print(f"design point: q {q_pa:.0f} Pa, CL {cl:.3f}, half-wing lift {half_lift_n:.0f} N")

# %% [markdown]
# ## 2. Structural prescription
#
# Sized backwards from the response we want, the numbers a real
# preliminary design would iterate on:
#
# * EI = 6.0e4 N m^2: an elliptical load of this magnitude on a 4 m
#   uniform cantilever gives a tip deflection near 12 cm, 3 percent
#   of the half span, typical of a semi-rigid light aircraft wing.
# * GJ = 3.0e4 N m^2: with the elastic axis at 40 percent chord and
#   the aerodynamic center at 25 percent, the nose-up torque arm of
#   0.15 c twists the tip about half a degree.
# * mu = 8 kg/m: 64 kg of wing structure for a 227 kg design lift,
#   putting the first bending mode near 3 Hz; the sectional inertias
#   I1 + I2 = 0.5 kg m (radius of gyration about a quarter chord)
#   put first torsion near 15 Hz, an order above bending, as it
#   should be.
#
# The CG offsets stay zero: they only enter the centrifugal terms,
# inert at Omega = 0. blade_count 2 stands for the two half wings.

# %%
N_STATIONS = 21
EI_N_M2 = 6.0e4
GJ_N_M2 = 3.0e4
MU_KG_PER_M = 8.0
I1_KG_M = 0.45
I2_KG_M = 0.05
EA_ARM_M = 0.15 * wing.chord_m

n = N_STATIONS
radii = [i * HALF_SPAN_M / (n - 1) for i in range(n)]
config = FsiConfig(
    blade_count=2,
    omega_rad_per_s=0.0,
    blade=BladeProperties(
        station_radii_m=radii,
        chord_m=[wing.chord_m] * n,
        mass_per_length_kg_per_m=[MU_KG_PER_M] * n,
        inertia_major_kg_m=[I1_KG_M] * n,
        inertia_minor_kg_m=[I2_KG_M] * n,
        bending_stiffness_n_m2=[EI_N_M2] * n,
        torsion_stiffness_n_m2=[GJ_N_M2] * n,
        elastic_axis_offset_chordwise_m=[0.0] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[0.0] * n,
    ),
)

# %% [markdown]
# ## 3. Static solve
#
# The elliptical lift bends the wing up; the same lift acting at the
# aerodynamic center, ahead of the elastic axis, twists it nose up
# (the wash-in direction that drives divergence on swept-forward
# wings; here it stays half a degree).

# %%
lift_n_per_m = [peak_n_per_m * math.sqrt(max(0.0, 1.0 - (r / HALF_SPAN_M) ** 2)) for r in radii]
torsion_n_m_per_m = [EA_ARM_M * value for value in lift_n_per_m]

model = beam.build_beam_model(config)
beam.apply_station_loads(
    model, config, flap_load_n_per_m=lift_n_per_m, torsion_moment_n_m_per_m=torsion_n_m_per_m
)
beam.solve_static(model)
solution = beam.extract_solution(model, config)

tip_w = solution.flap_deflection_m[-1]
tip_theta_deg = math.degrees(solution.elastic_twist_rad[-1])
print(f"tip deflection: {tip_w * 100:.1f} cm ({tip_w / HALF_SPAN_M:.1%} of the half span)")
print(f"tip twist: {tip_theta_deg:+.2f} deg (nose up)")
print(f"{'y [m]':>6} {'w [cm]':>8} {'theta [deg]':>12}")
for r, w, theta in zip(
    solution.station_radii_m,
    solution.flap_deflection_m,
    solution.elastic_twist_rad,
    strict=True,
):
    if r in (radii[0], radii[5], radii[10], radii[15], radii[20]):
        print(f"{r:6.1f} {w * 100:8.2f} {math.degrees(theta):12.3f}")

# %% [markdown]
# ## 4. Modal sanity
#
# The same model gives the natural frequencies. For this prescription
# the closed forms of the uniform cantilever put first bending at
# 3.0 Hz and first torsion at 15.3 Hz; the model reproduces them
# within a percent (that is the WP3 benchmark).

# %%
modal = beam.modal_frequencies(model, config, n_modes=4)
for f, kind in zip(modal.frequencies_rad_per_s, modal.kinds, strict=True):
    print(f"{kind:8s} {f / (2.0 * math.pi):6.2f} Hz")

# %% [markdown]
# ## 5. Spanwise plot (optional, extra [plot])

# %%
try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    print("matplotlib not installed (extra [plot]); skipping the figure")
else:
    fig, (ax_w, ax_t) = plt.subplots(2, 1, sharex=True, figsize=(7.0, 6.0))
    y = solution.station_radii_m
    ax_w.plot(y, [w * 100 for w in solution.flap_deflection_m], "o-")
    ax_w.set_ylabel("deflection w [cm]")
    ax_w.set_title("Generic wing at the polar design point, prescribed elliptical load")
    ax_t.plot(y, [math.degrees(t) for t in solution.elastic_twist_rad], "s-", color="tab:red")
    ax_t.set_ylabel("elastic twist [deg]")
    ax_t.set_xlabel("span position y [m]")
    fig.tight_layout()
    out = "wing_static_deflection.png"
    fig.savefig(out, dpi=150)
    print(f"figure written to {out}")
