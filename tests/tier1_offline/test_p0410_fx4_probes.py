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


def test_f7_0203_lattice_cylinder_must_enclose_the_annular_planes():
    """F-218: a closure cylinder inside the outer ring edge is refused; outside it is allowed."""
    from pyflightstream.probes.lattice import build_lattice

    with pytest.raises(ProbeGeometryError, match="lateral_radius"):
        build_lattice(tip_radius=1.0, r_outer=3.0, lateral_radius=2.5)
    assert build_lattice(tip_radius=1.0, r_outer=2.0, lateral_radius=2.5).lateral_radius == 2.5


@pytest.mark.parametrize("shape", [(2, 2, 3), (4, 2), (6,)])
def test_f7_0203_points_csv_refuses_anything_but_coordinate_triples(shape):
    """F-1418: a higher-dimensional or wrong-width array is not written as bracketed text."""
    import io

    import numpy as np

    from pyflightstream.probes.layouts import write_points_csv

    sink = io.StringIO()
    with pytest.raises(ProbeGeometryError, match=r"\(n, 3\)"):
        write_points_csv(np.zeros(shape), sink)
    assert sink.getvalue() == ""


def test_f7_0203_geometric_axis_neither_overflows_nor_coincides():
    """F-219 F-220: a large ratio gives finite increasing points or a refusal, never NaN."""
    import numpy as np

    wide = AxisSpec(start=0.0, stop=1.0, count=200, distribution="geometric", ratio=1.0001)
    points = wide.points()
    assert np.all(np.isfinite(points)) and np.all(np.diff(points) > 0.0)
    steep = AxisSpec(start=0.0, stop=1.0, count=3000, distribution="geometric", ratio=1.5)
    with pytest.raises(ProbeGeometryError, match="coincident"):
        steep.points()


def test_f7_0203_a_nan_in_the_planned_positions_is_not_a_match():
    """F-221: a NaN planned row cannot be compared, so the export is refused."""
    import numpy as np

    from pyflightstream.probes.planar import PlannedProbes

    planned = np.array([[0.0, 0.0, 0.0], [np.nan, 1.0, 1.0]])
    plan = PlannedProbes(grid=None, points=planned, report=None)  # type: ignore[arg-type]
    with pytest.raises(ProbeGeometryError, match="non-finite"):
        plan.verify_positions(np.array([[0.0, 0.0, 0.0], [5.0, 1.0, 1.0]]))


class TestF7ProbeGeometry:
    """F7-1617: layouts and frames refuse what they cannot define."""

    @staticmethod
    def test_x_f_1203_an_infinite_extent_is_a_probe_geometry_error():
        from pyflightstream.probes.layouts import farfield_plane

        with pytest.raises(ProbeGeometryError, match="finite plane|positive extent"):
            farfield_plane(
                (0.0, 0.0, 0.0),
                direction=(1.0, 0.0, 0.0),
                distance=2.0,
                half_width=float("inf"),
                half_height=1.0,
                spacing=0.1,
            )

    @staticmethod
    def test_x_f_1204_a_non_triple_array_is_a_probe_geometry_error(tmp_path):
        import numpy as np

        from pyflightstream.probes.layouts import write_points_csv

        with pytest.raises(ProbeGeometryError, match="n, 3"):
            write_points_csv(np.zeros((4, 2)), tmp_path / "p.csv")

    @staticmethod
    @pytest.mark.parametrize("big", [1e200, 1e300])
    def test_f_224_f_225_a_huge_axis_keeps_its_direction(big):
        frame = FrameDefinition(x_axis=(big, 0.0, 0.0), y_axis=(0.0, big, 0.0))
        assert frame.x_axis == (1.0, 0.0, 0.0)
        assert frame.y_axis == (0.0, 1.0, 0.0)

    @staticmethod
    def test_x_f_1067_a_stored_frame_survives_the_json_round_trip_exactly():
        frame = FrameDefinition(x_axis=(1.0, 2.0, 3.0), y_axis=(-2.0, 1.0, 0.5))
        again = FrameDefinition.model_validate_json(frame.model_dump_json())
        assert again.x_axis == frame.x_axis
        assert again.y_axis == frame.y_axis

    @staticmethod
    def test_f_222_the_documented_reference_lattice_order_is_the_largest_unaliased_one():
        import numpy as np

        from pyflightstream.farfield import FarfieldInputError, azimuthal_harmonics
        from pyflightstream.probes import lattice as lattice_module

        doc = " ".join(lattice_module.build_lattice.__doc__.split())
        assert "order 35 without aliasing" in doc
        psi = np.arange(72) * 2.0 * np.pi / 72
        field = np.cos(3 * psi)
        assert azimuthal_harmonics(field, psi=psi, m_max=35).shape[-1] == 36
        with pytest.raises(FarfieldInputError):
            azimuthal_harmonics(field, psi=psi, m_max=36)
