"""The far-field family: Trefftz-plane drag and survey balances, on numpy.

Pipeline role: the one home of every far-field analysis (FR-450). A facade over
a numpy core with no input or output: :mod:`.fields` (the survey and plane
containers and the one refusal), :mod:`.quadrature` (the plane, ring and strip
rules and the harmonic layer, each once), :mod:`.balances` (the conservation
balances of a survey lattice, FR-38) and :mod:`.trefftz` (the discrete trace of
variants A and B and the probe plane of variant C, FR-451 to FR-453). A user
reaches them through the ``[farfield]`` table of the pproc artifact; the post
step reads the exports, turns the vectors and calls this core.

The equations are those of the definitions page, The far-field family. The
names ``lattice_dataset``, ``rothalpy`` and ``irreversible_deficit`` were
removed in 0.40.0 and refuse, naming what replaced them (FR-457, FR-458).
"""

from __future__ import annotations

from pyflightstream._retired_names import RetiredAttributeError, retired_attribute
from pyflightstream.farfield.balances import (
    CrossflowEnergy,
    InPlaneMoment,
    MassClosure,
    TransverseForce,
    axial_flux,
    axial_force,
    crossflow_integrand,
    crossflow_kinetic_energy,
    in_plane_moment,
    lateral_flux,
    mass_closure,
    mass_flux,
    shaft_torque,
    spurious_diagnostic,
    to_counts,
    transverse_flux,
    transverse_force,
)
from pyflightstream.farfield.fields import (
    FarfieldInputError,
    LatticeFields,
    PlaneFields,
    cylindrical_components,
    hub_frame_velocities,
    lattice_fields,
    plane_fields,
)
from pyflightstream.farfield.quadrature import (
    azimuthal_harmonics,
    grid_coverage,
    grid_integral,
    grid_weights,
    plane_integral,
    ring_sample_weights,
    sample_coverage,
    strip_edges,
    symmetry_floor,
)
from pyflightstream.farfield.trefftz import (
    RUN_GAP_FACTOR,
    PlaneDrag,
    RotorChannels,
    TraceResult,
    WakeTrace,
    bernoulli_residual,
    calibration_scale,
    plane_induced_drag,
    plane_lift,
    plane_vorticity_drag,
    rotor_channels,
    trace_coefficients,
    trace_forces,
    wake_crossings,
)

__all__ = [
    "CrossflowEnergy",
    "FarfieldInputError",
    "InPlaneMoment",
    "LatticeFields",
    "MassClosure",
    "PlaneDrag",
    "PlaneFields",
    "RUN_GAP_FACTOR",
    "RotorChannels",
    "TraceResult",
    "TransverseForce",
    "WakeTrace",
    "axial_flux",
    "axial_force",
    "azimuthal_harmonics",
    "bernoulli_residual",
    "calibration_scale",
    "crossflow_integrand",
    "crossflow_kinetic_energy",
    "cylindrical_components",
    "grid_coverage",
    "grid_integral",
    "grid_weights",
    "hub_frame_velocities",
    "in_plane_moment",
    "lateral_flux",
    "lattice_fields",
    "mass_closure",
    "mass_flux",
    "plane_fields",
    "plane_induced_drag",
    "plane_integral",
    "plane_lift",
    "plane_vorticity_drag",
    "ring_sample_weights",
    "rotor_channels",
    "sample_coverage",
    "shaft_torque",
    "spurious_diagnostic",
    "strip_edges",
    "symmetry_floor",
    "to_counts",
    "trace_coefficients",
    "trace_forces",
    "transverse_flux",
    "transverse_force",
    "wake_crossings",
]


def __getattr__(name: str) -> object:
    """Refuse the names retired in 0.40.0, naming what replaced them."""
    entry = retired_attribute(__name__, name)
    if entry is not None:
        raise RetiredAttributeError(entry.message())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
