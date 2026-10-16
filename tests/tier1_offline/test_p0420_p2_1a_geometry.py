"""A non-finite wall margin must fail before mesh inspection or point generation."""

import pytest

from pyflightstream.probes import (
    AxisSpec,
    FrameDefinition,
    PlanarProbeGrid,
    ProbeGeometryError,
    RefinementBand,
)
from pyflightstream.probes.geometry import apply_geometry_gate


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_p0420_p2_1a_standoff_is_finite(value):
    grid = PlanarProbeGrid(
        frame=FrameDefinition(x_axis=(1, 0, 0), y_axis=(0, 1, 0)),
        u=AxisSpec(start=0, stop=1, count=2),
        v=AxisSpec(start=0, stop=1, count=2),
    )
    with pytest.raises(ProbeGeometryError, match="standoff.*finite"):
        apply_geometry_gate(grid, cull=False, standoff=value)
    assert len(apply_geometry_gate(grid, cull=False, standoff=0).points) == 4


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", ["start", "stop", "spacing", "ratio", "distance"])
def test_p0420_p2_1a_models_already_refuse_nonfinite_fields(field, value):
    if field == "distance":
        factory, values = RefinementBand, {"distance": value, "factor": 2}
    else:
        factory = AxisSpec
        values = {"start": 0, "stop": 1, "spacing": 0.5, field: value}
    with pytest.raises(ProbeGeometryError, match=field) as caught:
        factory(**values)
    assert caught.value.__cause__ is not None
