"""The fixed wing's structural solve: aerodynamic loads plus its own weight (FSI-G).

Pipeline role: the structural half of a coupled steady run and of a
coupled unsteady run with nothing turning (0.30.0). The wing is one
cantilever beam on its elastic axis, built by :mod:`pyflightstream.fsi.beam`
from the same per-station distributions a blade uses
(:class:`~pyflightstream.fsi.config.BladeProperties`, generated from the
wing's sections and a material by
:func:`pyflightstream.fsi.sections.blade_properties_from_sections`), and
clamped at its first station.

The loads it solves under are the aerodynamic loads the solver exports,
projected on the section axes (:func:`pyflightstream.fsi.loads.to_elastic_axis`),
plus the wing's own weight: the running mass under gravity, applied as a
distributed load (:func:`weight_loads`). The owner's rule of 2026-09-28:
a wing at rest has no centrifugal load, it has its weight. So nothing of
:mod:`pyflightstream.fsi.centrifugal` is reached from here: no tension, no
propeller moment, no in-plane softening, and the solve is linear.

Frame: the package's geometry frame, x aft, y right, z up. Gravity is a
vector of that frame (:attr:`~pyflightstream.fsi.config.FixedWing.gravity_m_per_s2`,
-z by default): the angle of attack and the sideslip turn the free
stream, never the body, so they never turn gravity.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from pyflightstream.fsi import beam
from pyflightstream.fsi.config import FsiConfig
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import transfer_moment_to_elastic_axis
from pyflightstream.fsi.nodes import config_triads


def _require_a_wing(cfg: FsiConfig) -> None:
    if cfg.wing is None:
        raise FsiInputError(
            "this configuration is not a fixed wing (it states no [wing] table), so its "
            "structural solve is the rotating blade's, not the wing's"
        )


def weight_loads(cfg: FsiConfig) -> tuple[list[float], list[float]]:
    """Return the wing's own weight as flap and torsion load densities per station.

    The weight of a strip is mu(s) g per unit span, a force at the
    section's centre of gravity. Its component along the section's
    toward-suction axis is the flap load q_n = mu (g . n); its component
    along the toward-leading-edge axis, q_c = mu (g . c), has no bending
    degree of freedom in this beam and enters only the torsion. Carried
    from the centre of gravity to the elastic axis, the pair twists the
    section by m = e_c q_n - e_n q_c, with (e_c, e_n) the offset from the
    elastic axis to the centre of gravity
    (``cg_offset_chordwise_m``, ``cg_offset_normal_m``), the identity of
    :func:`pyflightstream.fsi.loads.transfer_moment_to_elastic_axis`. The
    spanwise component would load the beam axially, which this beam
    holds rigid, so it is not applied.

    Source: elementary statics of a distributed weight, mu g per unit span
    acting at the section's centre of gravity; the moment transfer of
    DLV-007 Section 4.3 (FSI-R04) carries it to the elastic axis.

    Parameters
    ----------
    cfg : FsiConfig
        A fixed-wing configuration.

    Returns
    -------
    tuple of (list of float, list of float)
        Flap load [N/m] and torsion moment [N m / m] at every station; all
        zero when ``wing.self_weight`` is False.

    Raises
    ------
    FsiInputError
        If the configuration is not a fixed wing.
    """
    _require_a_wing(cfg)
    assert cfg.wing is not None
    n = len(cfg.blade.station_radii_m)
    if not cfg.wing.self_weight:
        return [0.0] * n, [0.0] * n
    gravity = np.asarray(cfg.wing.gravity_m_per_s2, dtype=float)
    triads = config_triads(cfg)
    mu = np.asarray(cfg.blade.mass_per_length_kg_per_m, dtype=float)
    q_c = mu * (triads[:, 0, :] @ gravity)
    q_n = mu * (triads[:, 1, :] @ gravity)
    torsion = transfer_moment_to_elastic_axis(
        np.zeros(n),
        q_c,
        q_n,
        np.asarray(cfg.blade.cg_offset_chordwise_m, dtype=float),
        np.asarray(cfg.blade.cg_offset_normal_m, dtype=float),
    )
    return q_n.tolist(), torsion.tolist()


def solve_wing_static(
    cfg: FsiConfig,
    flap_load_n_per_m: Sequence[float] | None = None,
    torsion_moment_n_m_per_m: Sequence[float] | None = None,
) -> beam.StaticBeamSolution:
    """Solve the clamped wing under its aerodynamic loads and its own weight.

    One linear static solve of the beam of :func:`pyflightstream.fsi.beam.build_beam_model`:
    the aerodynamic densities given, plus :func:`weight_loads`. No axial
    load, no P-Delta, no inner iteration: nothing turns.

    Parameters
    ----------
    cfg : FsiConfig
        A fixed-wing configuration.
    flap_load_n_per_m : sequence of float, optional
        Aerodynamic flap load at the stations [N/m], toward the suction side.
    torsion_moment_n_m_per_m : sequence of float, optional
        Aerodynamic moment about the elastic axis at the stations [N m / m],
        nose up.

    Returns
    -------
    beam.StaticBeamSolution
        Flap deflection and elastic twist at the stations.
    """
    weight_flap, weight_torsion = weight_loads(cfg)
    n = len(weight_flap)
    aero_flap = list(flap_load_n_per_m) if flap_load_n_per_m is not None else [0.0] * n
    aero_torsion = (
        list(torsion_moment_n_m_per_m) if torsion_moment_n_m_per_m is not None else [0.0] * n
    )
    for name, values in (("flap", aero_flap), ("torsion", aero_torsion)):
        if len(values) != n:
            raise FsiInputError(
                f"the aerodynamic {name} load has {len(values)} entries for {n} stations; "
                "sectional loads must be sampled at the configuration stations"
            )
    model = beam.build_beam_model(cfg)
    beam.apply_station_loads(
        model,
        cfg,
        flap_load_n_per_m=[a + w for a, w in zip(aero_flap, weight_flap, strict=True)],
        torsion_moment_n_m_per_m=[a + w for a, w in zip(aero_torsion, weight_torsion, strict=True)],
    )
    beam.solve_static(model, p_delta=False)
    return beam.extract_solution(model, cfg)
