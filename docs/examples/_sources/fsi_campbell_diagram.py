# %% [markdown]
# # Campbell diagram of a synthetic rotating blade (Gate 1)
#
# This example closes Gate 1 of the FSI work plan on the structural
# branch alone: no FlightStream involved, only the beam model and the
# centrifugal loads of `pyflightstream.fsi`.
#
# 1. define a synthetic uniform blade in the `FsiConfig` schema;
# 2. sweep rotor speed and extract flap and torsion frequencies;
# 3. fit the Southwell lines omega_n^2 = omega_0^2 + S Omega^2;
# 4. draw the Campbell diagram with the 1P to 4P excitation rays
#    (needs the `[plot]` extra; the numbers print without it).
#
# The blade is synthetic by policy: no real blade property set ever
# enters the repository. Its numbers are chosen for didactic clarity,
# not for any specific rotor.

# %%
"""Campbell diagram example: synthetic blade, rotor speed sweep, Southwell fits."""

import math

from pyflightstream.fsi import centrifugal
from pyflightstream.fsi.config import BladeProperties, FsiConfig

N_STATIONS = 15
ROOT_M, TIP_M = 0.0, 1.0
OMEGAS_RAD_S = [0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0]

# %% [markdown]
# ## 1. The synthetic blade
#
# A uniform clamped blade: constant chord, mass, and stiffness, thin
# section (I2 << I1), zero pitch, zero offsets. Every field name
# carries its SI unit; the frame is the rotating blade frame (spanwise
# root to tip, chordwise toward the leading edge).

# %%
n = N_STATIONS
radii = [ROOT_M + i * (TIP_M - ROOT_M) / (n - 1) for i in range(n)]
blade = BladeProperties(
    station_radii_m=radii,
    chord_m=[0.1] * n,
    mass_per_length_kg_per_m=[2.0] * n,
    inertia_major_kg_m=[1.0e-3] * n,
    inertia_minor_kg_m=[2.0e-5] * n,
    bending_stiffness_n_m2=[120.0] * n,
    torsion_stiffness_n_m2=[40.0] * n,
    elastic_axis_offset_chordwise_m=[0.0] * n,
    elastic_axis_offset_normal_m=[0.0] * n,
    cg_offset_chordwise_m=[0.0] * n,
    cg_offset_normal_m=[0.0] * n,
    geometric_pitch_deg=[0.0] * n,
)
cfg = FsiConfig(blade_count=2, omega_rad_per_s=0.0, blade=blade)

# %% [markdown]
# ## 2. Rotor speed sweep
#
# At every speed the blade is first solved statically under its own
# centrifugal loads (P-Delta, inner twist iteration), then the modal
# problem adds the geometric stiffness of that tension state and the
# propeller moment stiffening. Frequencies rise with Omega: the
# Southwell effect.

# %%
campbell = centrifugal.campbell_sweep(cfg, OMEGAS_RAD_S, n_modes=6)
flap_track = campbell.family_track("flap")
torsion_track = campbell.family_track("torsion")

print(f"{'Omega [rad/s]':>14} {'flap 1 [rad/s]':>15} {'torsion 1 [rad/s]':>18}")
for omega, flap, torsion in zip(OMEGAS_RAD_S, flap_track, torsion_track, strict=True):
    print(f"{omega:14.1f} {flap:15.2f} {torsion:18.2f}")

# %% [markdown]
# ## 3. Southwell fits
#
# The WP4 verification: the tracks must be straight lines in the
# (Omega^2, omega_n^2) plane. The slope S is the Southwell
# coefficient; for the first flap mode of a uniform blade it sits
# around 1.1 to 1.3, and for the torsion mode of a thin blade the
# propeller moment gives S near (I1 - I2) / (I1 + I2), close to 1.

# %%
for name, track in (("first flap", flap_track), ("first torsion", torsion_track)):
    omega_0, coefficient, r_squared = centrifugal.southwell_fit(OMEGAS_RAD_S, track)
    print(
        f"{name}: omega_0 {omega_0:7.2f} rad/s, Southwell S {coefficient:5.3f}, r^2 {r_squared:.6f}"
    )

# %% [markdown]
# ## 4. The diagram
#
# Natural frequencies versus rotor speed, with the nP excitation rays
# (n blades excite at integer multiples of Omega). Crossings between a
# frequency track and a ray flag potential resonances; the coupled
# tool's quasi-steady validity boundary (n Omega / omega_n at or below
# about 0.3) lives far below the first crossing.

# %%
try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    print("matplotlib not installed (extra [plot]); skipping the figure")
else:
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.plot(OMEGAS_RAD_S, flap_track, "o-", label="first flap")
    ax.plot(OMEGAS_RAD_S, torsion_track, "s-", label="first torsion")
    omega_max = max(OMEGAS_RAD_S)
    for harmonic in range(1, 5):
        ax.plot(
            [0.0, omega_max],
            [0.0, harmonic * omega_max],
            linestyle=":",
            color="gray",
            linewidth=1.0,
        )
        ax.annotate(f"{harmonic}P", (omega_max, harmonic * omega_max))
    ax.set_xlabel("rotor speed Omega [rad/s]")
    ax.set_ylabel("natural frequency omega_n [rad/s]")
    ax.set_ylim(0.0, math.ceil(1.1 * max(torsion_track)))
    ax.set_title("Campbell diagram, synthetic uniform blade (Gate 1)")
    ax.legend()
    fig.tight_layout()
    out = "fsi_campbell_diagram.png"
    fig.savefig(out, dpi=150)
    print(f"figure written to {out}")
