"""NFR-47: ProbeLattice(tip_radius=float('nan'), ...) names its domain field."""

import json

import pytest

from pyflightstream.probes import ProbeGeometryError, ProbeLattice
from pyflightstream.probes.planar import (
    AxisSpec,
    FrameDefinition,
    GeometryGateReport,
    PlanarProbeGrid,
    RefinementBand,
)


@pytest.mark.requirement("NFR-47")
@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), -float("inf")],
    ids=["P0410-nan", "P0410-inf", "P0410-negative-inf"],
)
@pytest.mark.parametrize("route", ["constructor", "mapping", "json"])
@pytest.mark.parametrize(
    "model,data,field,sequence",
    [
        (
            ProbeLattice,
            dict(tip_radius=1.0, stations=(0.0, 1.0), ring_edges=(0.1, 1.0), n_psi=8),
            field,
            sequence,
        )
        for field, sequence in [
            ("tip_radius", False),
            ("stations", True),
            ("ring_edges", True),
            ("lateral_radius", False),
            ("lateral_stations", True),
        ]
    ]
    + [
        (AxisSpec, dict(start=0.0, stop=1.0, spacing=0.1), field, False)
        for field in ("start", "stop", "spacing")
    ]
    + [
        (
            AxisSpec,
            dict(start=0.0, stop=1.0, count=4, distribution="geometric", ratio=2.0),
            "ratio",
            False,
        ),
        (RefinementBand, dict(distance=0.1, factor=2), "distance", False),
    ]
    + [
        (FrameDefinition, dict(x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)), field, True)
        for field in ("origin", "x_axis", "y_axis")
    ]
    + [
        (
            GeometryGateReport,
            dict(base_total=4, base_culled=0, refined_added=0, refined_culled=0),
            field,
            False,
        )
        for field in ("band_distance", "standoff")
    ],
)
def test_p0410_fx4_nonfinite_geometry_names_field(model, data, field, sequence, value, route):
    assert model(**data)
    data = dict(data, **{field: (value, 0.0, 1.0) if sequence else value})
    with pytest.raises(ProbeGeometryError, match=field):
        if route == "constructor":
            model(**data)
        elif route == "mapping":
            model.model_validate(data)
        else:
            model.model_validate_json(json.dumps(data))


@pytest.mark.requirement("NFR-47")
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"], ids=lambda v: f"P0410-{v}")
def test_p0410_fx4_string_validation_names_field(value):
    with pytest.raises(ProbeGeometryError, match="spacing"):
        AxisSpec.model_validate_strings(dict(start="0", stop="1", spacing=value))


@pytest.mark.parametrize("route", ["mapping", "json"])
@pytest.mark.parametrize("nested", [False, True], ids=["P0410-RV3-axis", "P0410-RV3-grid"])
def test_p0410_rv3_probe_validation_preserves_explicit_strictness(route, nested):
    axis = dict(start="0", stop=1.0, count=3)
    model = PlanarProbeGrid if nested else AxisSpec
    data = (
        dict(
            frame=dict(x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
            u=axis,
            v=dict(start=0.0, stop=1.0, count=3),
        )
        if nested
        else axis
    )
    # Default coercion still works; only an explicit strict request refuses strings.
    assert model(**data)
    with pytest.raises(ProbeGeometryError, match="start"):
        if route == "mapping":
            model.model_validate(data, strict=True)
        else:
            model.model_validate_json(json.dumps(data), strict=True)
    axis["start"] = 0.0
    if route == "mapping":
        assert model.model_validate(data, strict=True)
    else:
        assert model.model_validate_json(json.dumps(data), strict=True)


@pytest.mark.requirement("NFR-47")
@pytest.mark.parametrize("field", ["frame", "u", "v", "refinement"], ids=lambda v: f"P0410-{v}")
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("route", ["constructor", "mapping", "json"])
def test_p0410_fx4_nested_grid_nonfinite_names_field(field, value, route):
    data = dict(
        frame=dict(x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
        u=dict(start=0.0, stop=1.0, count=3),
        v=dict(start=0.0, stop=1.0, count=3),
        refinement=dict(distance=0.1, factor=2),
    )
    valid = PlanarProbeGrid(**data)
    assert PlanarProbeGrid.from_json(valid.to_json()) == valid
    leaf = {"frame": "origin", "u": "start", "v": "stop", "refinement": "distance"}[field]
    data[field][leaf] = (value, 0.0, 0.0) if field == "frame" else value
    with pytest.raises(ProbeGeometryError, match=leaf):
        if route == "constructor":
            PlanarProbeGrid(**data)
        elif route == "mapping":
            PlanarProbeGrid.model_validate(data)
        else:
            PlanarProbeGrid.model_validate_json(json.dumps(data))
