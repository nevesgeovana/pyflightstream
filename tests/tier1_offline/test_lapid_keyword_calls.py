"""New numerical calls name every input after their primary positional argument.

For example, trace_coefficients(120, side_force=3, induced_drag=4, ...) must
accept the named forces and reject trace_coefficients(120, 3, 4, ...).
"""

from inspect import Parameter, signature

import pytest

from pyflightstream import farfield, probes


@pytest.mark.parametrize(
    "function",
    [
        farfield.lattice_fields,
        farfield.plane_fields,
        farfield.hub_frame_velocities,
        farfield.grid_weights,
        farfield.grid_integral,
        farfield.azimuthal_harmonics,
        farfield.symmetry_floor,
        farfield.lateral_flux,
        farfield.crossflow_integrand,
        farfield.trace_forces,
        farfield.trace_coefficients,
        farfield.wake_crossings,
        farfield.rotor_channels,
        probes.line_points,
        probes.rectangle_points,
        probes.circle_points,
        probes.farfield_plane,
    ],
)
def test_new_secondary_inputs_are_keyword_only(function):
    parameters = list(signature(function).parameters.values())
    assert all(p.kind is Parameter.KEYWORD_ONLY for p in parameters[1:]), function.__name__


def test_force_components_cannot_be_silently_exchanged_by_position():
    named = farfield.trace_coefficients(
        120.0, side_force=3.0, induced_drag=4.0, q=540.0, s_ref=4.0, b_ref=8.0
    )
    assert named["CL_T"] == pytest.approx(120.0 / 2160.0)
    with pytest.raises(TypeError):
        farfield.trace_coefficients(120.0, 3.0, 4.0, q=540.0, s_ref=4.0, b_ref=8.0)
