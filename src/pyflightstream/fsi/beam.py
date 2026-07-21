"""PyNite beam model of one blade: static solve and modal frequencies.

Pipeline role: WP3 of DLV-007. Builds the finite element beam of one
blade on the elastic axis from :class:`~pyflightstream.fsi.config.FsiConfig`,
solves it statically under sectional loads (with P-Delta when axial
tension is present, FSI-R05), and extracts flap and torsion natural
frequencies for the Campbell diagram (Gate 1).

Model and frame: the beam lies along the global X axis (spanwise, root
to tip), flap deflection w is global Y, and elastic twist theta is the
rotation about X. The structural model is (w, theta) per the coupling
plan: only flap translation and torsion carry mass; the remaining
degrees of freedom are exactly condensed out of the eigenproblem.
Stiffness is encoded with unit elastic moduli (E = G = 1) so the
section constants are numerically EI and GJ; the blade root station is
clamped.

PyNite (PyPI ``PyNiteFEA``, import name ``Pynite``) is required; it is
installed by the ``[fsi]`` extra only.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

import numpy as np

from pyflightstream.fsi.config import FsiConfig

try:
    from Pynite import FEModel3D
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "pyflightstream.fsi.beam needs the PyNite structural backend, which is "
        "not installed; install the optional extra with: pip install pyflightstream[fsi]"
    ) from exc

logger = logging.getLogger(__name__)

_COMBO = "structural"
_MATERIAL = "blade_unit_moduli"
# Fake axial area: with E = 1 this is the axial stiffness EA [N]. It only
# has to dwarf the bending stiffness so the spanwise DOF is quasi rigid;
# the axial DOF carries no mass and is condensed out of the eigenproblem.
_AXIAL_AREA = 1.0e9

# Per-node degree of freedom order in PyNite's global matrices.
_DOF_ORDER = ("DX", "DY", "DZ", "RX", "RY", "RZ")
_FLAP_DOF = _DOF_ORDER.index("DY")
_TWIST_DOF = _DOF_ORDER.index("RX")


def station_name(i: int) -> str:
    """Return the model node name of radial station ``i`` (root is 0)."""
    return f"S{i:03d}"


@dataclass(frozen=True)
class StaticBeamSolution:
    """Beam solution sampled at the radial stations.

    Attributes
    ----------
    station_radii_m : tuple of float
        Radial stations [m], as in the configuration.
    flap_deflection_m : tuple of float
        Flap deflection w at each station [m], positive along +Y of
        the rotating blade frame.
    elastic_twist_rad : tuple of float
        Elastic twist theta at each station [rad], positive nose up
        about the spanwise axis.
    """

    station_radii_m: tuple[float, ...]
    flap_deflection_m: tuple[float, ...]
    elastic_twist_rad: tuple[float, ...]


@dataclass(frozen=True)
class ModalResult:
    """Natural frequencies of the (w, theta) beam.

    Attributes
    ----------
    frequencies_rad_per_s : tuple of float
        Undamped natural frequencies omega_n [rad/s], ascending.
    kinds : tuple of str
        Per mode, ``"flap"`` or ``"torsion"``: the family holding the
        larger share of the mode's generalized mass.
    flap_mass_fractions : tuple of float
        Per mode, fraction of generalized mass in the flap DOFs; near
        1 for pure flap, near 0 for pure torsion, intermediate when
        offsets couple the families.
    """

    frequencies_rad_per_s: tuple[float, ...]
    kinds: tuple[str, ...]
    flap_mass_fractions: tuple[float, ...]


def build_beam_model(cfg: FsiConfig) -> "FEModel3D":
    """Build the PyNite model of one blade on the elastic axis.

    One node per radial station along global X, one member per bay
    with bay-averaged EI and GJ (times the stiffness scale factor),
    root station clamped.

    Parameters
    ----------
    cfg : FsiConfig
        Validated configuration; only the blade distributions and the
        stiffness scale factor are used here.

    Returns
    -------
    FEModel3D
        Model ready for loading and analysis; the load combination
        ``"structural"`` is registered.
    """
    blade = cfg.blade
    model = FEModel3D()
    model.add_material(_MATERIAL, E=1.0, G=1.0, nu=0.3, rho=0.0)
    for i, r in enumerate(blade.station_radii_m):
        model.add_node(station_name(i), r, 0.0, 0.0)
    scale = cfg.stiffness_scale_factor
    for i in range(len(blade.station_radii_m) - 1):
        ei = 0.5 * (blade.bending_stiffness_n_m2[i] + blade.bending_stiffness_n_m2[i + 1])
        gj = 0.5 * (blade.torsion_stiffness_n_m2[i] + blade.torsion_stiffness_n_m2[i + 1])
        section = f"bay{i:03d}"
        model.add_section(section, A=_AXIAL_AREA, Iy=ei * scale, Iz=ei * scale, J=gj * scale)
        model.add_member(f"B{i:03d}", station_name(i), station_name(i + 1), _MATERIAL, section)
    model.def_support(
        station_name(0),
        support_DX=True,
        support_DY=True,
        support_DZ=True,
        support_RX=True,
        support_RY=True,
        support_RZ=True,
    )
    model.add_load_combo(_COMBO, {"Case 1": 1.0})
    return model


def apply_station_loads(
    model: "FEModel3D",
    cfg: FsiConfig,
    flap_load_n_per_m: Sequence[float] | None = None,
    torsion_moment_n_m_per_m: Sequence[float] | None = None,
    axial_load_n_per_m: Sequence[float] | None = None,
) -> None:
    """Apply per-station distributed loads to a built model.

    Distributed flap and axial loads become trapezoidal member loads
    between stations. The distributed torsion moment is lumped to
    nodal torques over tributary lengths, which reproduces the exact
    tip twist of a uniform distributed torque on a uniform beam.

    Parameters
    ----------
    model : FEModel3D
        Model from :func:`build_beam_model`.
    cfg : FsiConfig
        Configuration providing the station radii.
    flap_load_n_per_m : sequence of float, optional
        Distributed flap force per unit span at each station [N/m],
        positive +Y.
    torsion_moment_n_m_per_m : sequence of float, optional
        Distributed torque about the elastic axis at each station
        [N m / m], positive nose up.
    axial_load_n_per_m : sequence of float, optional
        Distributed axial (spanwise) force at each station [N/m],
        positive toward the tip; the centrifugal tension enters here
        and stiffens the beam through P-Delta (FSI-R05).
    """
    radii = cfg.blade.station_radii_m
    n = len(radii)
    for name, values, direction in (
        ("flap_load_n_per_m", flap_load_n_per_m, "FY"),
        ("axial_load_n_per_m", axial_load_n_per_m, "FX"),
    ):
        if values is None:
            continue
        if len(values) != n:
            raise ValueError(
                f"{name} has {len(values)} entries for {n} stations; sectional "
                "loads must be sampled at the configuration stations"
            )
        for i in range(n - 1):
            model.add_member_dist_load(f"B{i:03d}", direction, values[i], values[i + 1])
    if torsion_moment_n_m_per_m is not None:
        if len(torsion_moment_n_m_per_m) != n:
            raise ValueError(
                f"torsion_moment_n_m_per_m has {len(torsion_moment_n_m_per_m)} "
                f"entries for {n} stations; sectional loads must be sampled at "
                "the configuration stations"
            )
        for i, torque in enumerate(tributary_lengths(radii)):
            lumped = torsion_moment_n_m_per_m[i] * torque
            if lumped != 0.0:
                model.add_node_load(station_name(i), "MX", lumped)


def solve_static(model: "FEModel3D", p_delta: bool = False) -> None:
    """Run the static analysis on the ``"structural"`` combination.

    Parameters
    ----------
    model : FEModel3D
        Loaded model.
    p_delta : bool
        Use the geometrically nonlinear P-Delta analysis so axial
        tension stiffens bending with no manual correction terms
        (FSI-R05). The linear analysis is the right choice only when
        no axial load is present.
    """
    if p_delta:
        model.analyze_PDelta(log=False, sparse=True)
    else:
        model.analyze_linear(log=False, sparse=True)


def extract_solution(model: "FEModel3D", cfg: FsiConfig) -> StaticBeamSolution:
    """Read (w, theta) at every station from an analyzed model."""
    radii = cfg.blade.station_radii_m
    w = []
    theta = []
    for i in range(len(radii)):
        node = model.nodes[station_name(i)]
        w.append(node.DY[_COMBO])
        theta.append(node.RX[_COMBO])
    return StaticBeamSolution(
        station_radii_m=tuple(radii),
        flap_deflection_m=tuple(w),
        elastic_twist_rad=tuple(theta),
    )


def modal_frequencies(
    model: "FEModel3D",
    cfg: FsiConfig,
    n_modes: int = 6,
    include_geometric_stiffness: bool = False,
    twist_stiffness_n_m_per_rad: Sequence[float] | None = None,
) -> ModalResult:
    """Extract flap and torsion natural frequencies of the blade.

    The stiffness matrix comes from PyNite (elastic, plus the
    geometric stiffness of the analyzed axial state when requested);
    the mass matrix is the lumped (w, theta) matrix of
    :func:`lumped_station_masses`. Massless degrees of freedom are
    condensed out exactly, so the eigenproblem is small and free of
    artifacts from the fake axial and chordwise stiffness.

    Parameters
    ----------
    model : FEModel3D
        Analyzed model (run :func:`solve_static` first; the analysis
        assigns the global degree of freedom numbering and, for the
        rotating case, the axial force state behind the geometric
        stiffness).
    cfg : FsiConfig
        Configuration providing mass and inertia distributions.
    n_modes : int
        Number of lowest modes to return.
    include_geometric_stiffness : bool
        Add PyNite's geometric stiffness of the ``"structural"``
        combination, so centrifugal tension raises the flap
        frequencies (the Southwell effect probed by WP4).
    twist_stiffness_n_m_per_rad : sequence of float, optional
        Additional lumped torsional stiffness per station
        [N m / rad], added on the twist degrees of freedom. The
        centrifugal (propeller moment) torsional stiffening of
        :mod:`pyflightstream.fsi.centrifugal` enters here; PyNite's
        geometric stiffness covers bending only.

    Returns
    -------
    ModalResult
        Ascending frequencies with flap or torsion classification.
    """
    stiffness = np.array(model.Ke(_COMBO, log=False, check_stability=False, sparse=True).todense())
    if include_geometric_stiffness:
        stiffness = stiffness + np.array(
            model.Kg(_COMBO, log=False, sparse=True, first_step=False).todense()
        )
    node_ids = {name: node.ID for name, node in model.nodes.items()}
    n_stations = len(cfg.blade.station_radii_m)
    flap_mass, twist_inertia = lumped_station_masses(cfg)

    if twist_stiffness_n_m_per_rad is not None and len(twist_stiffness_n_m_per_rad) != n_stations:
        raise ValueError(
            f"twist_stiffness_n_m_per_rad has {len(twist_stiffness_n_m_per_rad)} "
            f"entries for {n_stations} stations; the lumped torsional stiffening "
            "must be sampled at the configuration stations"
        )

    free_rows: list[int] = []
    masses: list[float] = []
    is_flap: list[bool] = []
    twist_master_station: dict[int, int] = {}
    slave_rows: list[int] = []
    root_id = node_ids[station_name(0)]
    for i in range(n_stations):
        node_id = node_ids[station_name(i)]
        if node_id == root_id:
            continue  # clamped: all six DOFs are supported
        for dof in range(6):
            row = node_id * 6 + dof
            if dof == _FLAP_DOF:
                free_rows.append(row)
                masses.append(flap_mass[i])
                is_flap.append(True)
            elif dof == _TWIST_DOF:
                twist_master_station[len(free_rows)] = i
                free_rows.append(row)
                masses.append(twist_inertia[i])
                is_flap.append(False)
            else:
                slave_rows.append(row)
    condensed = _condense_massless(stiffness, free_rows, slave_rows)
    if twist_stiffness_n_m_per_rad is not None:
        for master_index, i in twist_master_station.items():
            condensed[master_index, master_index] += twist_stiffness_n_m_per_rad[i]

    mass_vector = np.array(masses)
    # Symmetric standard form: L^-1 K L^-T with L = sqrt(M) (M is diagonal).
    inv_sqrt_m = 1.0 / np.sqrt(mass_vector)
    sym = condensed * inv_sqrt_m[:, None] * inv_sqrt_m[None, :]
    eigenvalues, eigenvectors = np.linalg.eigh(sym)

    frequencies = []
    kinds = []
    fractions = []
    flap_mask = np.array(is_flap)
    for k in range(min(n_modes, len(eigenvalues))):
        lam = eigenvalues[k]
        if lam < 0.0:
            raise ValueError(
                "negative eigenvalue in the modal problem: the axial state is "
                "beyond buckling of this blade, or the model is not analyzed"
            )
        shape = eigenvectors[:, k]
        flap_fraction = float(np.sum(shape[flap_mask] ** 2) / np.sum(shape**2))
        frequencies.append(sqrt(lam))
        kinds.append("flap" if flap_fraction >= 0.5 else "torsion")
        fractions.append(flap_fraction)
    return ModalResult(
        frequencies_rad_per_s=tuple(frequencies),
        kinds=tuple(kinds),
        flap_mass_fractions=tuple(fractions),
    )


def lumped_station_masses(cfg: FsiConfig) -> tuple[list[float], list[float]]:
    """Lump running mass and torsional inertia to the stations.

    Each station receives the tributary half lengths of its adjacent
    bays: translational mass mu(r_i) l_i [kg] for the flap DOF and
    polar inertia (I1(r_i) + I2(r_i)) l_i [kg m^2] for the twist DOF.

    Source: standard tributary (lumped) mass matrix for beam finite
    elements, Cook, Malkus, Plesha, Witt, "Concepts and Applications
    of Finite Element Analysis", 4th ed., Section 11.4.

    Parameters
    ----------
    cfg : FsiConfig
        Configuration providing mu(r), I1(r), I2(r) and the stations.

    Returns
    -------
    tuple of (list of float, list of float)
        Per-station flap masses [kg] and twist inertias [kg m^2].
    """
    blade = cfg.blade
    tributary = tributary_lengths(blade.station_radii_m)
    flap_mass = [
        mu * length for mu, length in zip(blade.mass_per_length_kg_per_m, tributary, strict=True)
    ]
    twist_inertia = [
        (i1 + i2) * length
        for i1, i2, length in zip(
            blade.inertia_major_kg_m, blade.inertia_minor_kg_m, tributary, strict=True
        )
    ]
    return flap_mass, twist_inertia


def tributary_lengths(radii: Sequence[float]) -> list[float]:
    """Return the half-bay tributary length of every station [m]."""
    n = len(radii)
    lengths = []
    for i in range(n):
        left = radii[i] - radii[i - 1] if i > 0 else 0.0
        right = radii[i + 1] - radii[i] if i < n - 1 else 0.0
        lengths.append(0.5 * (left + right))
    return lengths


def _condense_massless(
    stiffness: np.ndarray, master_rows: list[int], slave_rows: list[int]
) -> np.ndarray:
    """Condense massless degrees of freedom out of a stiffness matrix.

    Static (Guyan) condensation is exact, not approximate, when the
    condensed degrees of freedom carry no mass, which is the case here
    by construction of the lumped (w, theta) mass matrix.

    Source: R. J. Guyan, "Reduction of stiffness and mass matrices",
    AIAA Journal 3(2), 1965, p.380.
    """
    kmm = stiffness[np.ix_(master_rows, master_rows)]
    kms = stiffness[np.ix_(master_rows, slave_rows)]
    kss = stiffness[np.ix_(slave_rows, slave_rows)]
    return kmm - kms @ np.linalg.solve(kss, kms.T)
