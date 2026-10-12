"""P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): RelaxedTrailingEdge resolves and refuses."""

from __future__ import annotations

import pytest

from pyflightstream.script import CommandArgumentError, helpers

# --- P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018) ----------------------------


@pytest.mark.parametrize(
    ("direction", "token"),
    [(0, "AXIAL"), (1, "AZIMUTH"), ("azimuth", "AZIMUTH"), ("1", "AZIMUTH")],
)
def test_p0400_relaxedte_the_constructor_takes_the_directions_its_refusal_names(direction, token):
    """P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): the helper preserves its declared contract."""
    edge = helpers.RelaxedTrailingEdge(fields=("0.5", "0.1", "0.9"), direction=direction)
    assert edge.direction == token
    assert helpers.parse_relaxed_trailing_edge(edge.render()) == edge


@pytest.mark.parametrize("direction", [2, -1, True, "SIDEWAYS"])
def test_p0400_relaxedte_a_third_direction_is_still_refused(direction):
    """P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): the helper preserves its declared contract."""
    with pytest.raises(CommandArgumentError, match="neither"):
        helpers.RelaxedTrailingEdge(fields=("0.5", "0.1", "0.9"), direction=direction)


@pytest.mark.parametrize(
    "fields", [("0.5", "", "0.9"), ("0.5", "  ", "0.9"), ("0.5", "0.1;0.9", "1")]
)
def test_p0400_relaxedte_a_field_that_cannot_render_is_refused(fields):
    """P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): the helper preserves its declared contract."""
    with pytest.raises(CommandArgumentError, match="blank or hold"):
        helpers.RelaxedTrailingEdge(fields=fields)
