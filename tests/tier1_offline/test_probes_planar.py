"""Tier 1: planar probe grids, frames, distributions, serialization, emission."""

import numpy as np
import pytest
from pydantic import ValidationError

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.probes import (
    AxisSpec,
    FrameDefinition,
    PlanarProbeGrid,
    emit_probe_import,
    write_points_csv,
)
from pyflightstream.script import Script
from pyflightstream.script.helpers import coordinate_frame
from tests.tier1_offline._no_evidence import registry_without


def yz_frame() -> FrameDefinition:
    # A plane at x = 1 spanned by the reference y and z axes.
    return FrameDefinition(origin=(1.0, 0.0, 0.0), x_axis=(0.0, 1.0, 0.0), y_axis=(0.0, 0.0, 1.0))


def test_frame_orthonormalizes_its_axes():
    frame = FrameDefinition(x_axis=(2.0, 0.0, 0.0), y_axis=(1.0, 1.0, 0.0))
    assert frame.x_axis == pytest.approx((1.0, 0.0, 0.0))
    assert frame.y_axis == pytest.approx((0.0, 1.0, 0.0))
    assert frame.z_axis == pytest.approx((0.0, 0.0, 1.0))


def test_frame_refuses_degenerate_axes_with_the_physical_cause():
    with pytest.raises(ValidationError, match="zero vector"):
        FrameDefinition(x_axis=(0.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0))
    with pytest.raises(ValidationError, match="parallel"):
        FrameDefinition(x_axis=(1.0, 0.0, 0.0), y_axis=(2.0, 0.0, 0.0))


def test_frame_transform_round_trip_on_a_custom_plane():
    frame = yz_frame()
    local = np.array([[0.25, -0.5, 0.0], [1.0, 2.0, 0.0]])
    reference = frame.to_reference(local)
    assert reference == pytest.approx(np.array([[1.0, 0.25, -0.5], [1.0, 1.0, 2.0]]))
    assert frame.from_reference(reference) == pytest.approx(local)


def test_uniform_axis_prescribes_the_element_size():
    axis = AxisSpec(start=0.0, stop=1.0, spacing=0.25)
    assert axis.points() == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])
    snapped = AxisSpec(start=0.0, stop=1.0, spacing=0.3)
    assert len(snapped.points()) == 4  # 3 elements of 1/3, snapped to fill
    assert snapped.points()[-1] == 1.0


def test_cosine_axis_clusters_the_requested_ends():
    both = AxisSpec(start=0.0, stop=1.0, count=11, distribution="cosine").points()
    sizes = np.diff(both)
    assert sizes[0] < sizes[len(sizes) // 2]
    assert sizes[-1] < sizes[len(sizes) // 2]
    start = AxisSpec(start=0.0, stop=1.0, count=11, distribution="cosine", cluster="start").points()
    assert np.all(np.diff(np.diff(start)) > -1e-12)  # sizes grow away from start


def test_geometric_axis_grows_by_the_ratio():
    axis = AxisSpec(
        start=0.0, stop=1.0, count=5, distribution="geometric", ratio=2.0, cluster="start"
    )
    sizes = np.diff(axis.points())
    assert sizes[1:] / sizes[:-1] == pytest.approx([2.0, 2.0, 2.0])
    assert axis.points()[-1] == 1.0


def test_axis_validation_names_the_didactic_cause():
    with pytest.raises(ValidationError, match="positive extent"):
        AxisSpec(start=1.0, stop=0.0, spacing=0.1)
    with pytest.raises(ValidationError, match="exactly one of spacing"):
        AxisSpec(start=0.0, stop=1.0)
    with pytest.raises(ValidationError, match="count, never spacing"):
        AxisSpec(start=0.0, stop=1.0, spacing=0.1, distribution="cosine")
    with pytest.raises(ValidationError, match="ratio > 1"):
        AxisSpec(start=0.0, stop=1.0, count=5, distribution="geometric")


def test_grid_orders_base_points_row_major_in_u_then_v():
    grid = PlanarProbeGrid(
        frame=yz_frame(),
        u=AxisSpec(start=0.0, stop=1.0, count=2),
        v=AxisSpec(start=0.0, stop=2.0, count=3),
    )
    points = grid.base_points()
    assert grid.shape == (2, 3)
    assert grid.point_count == 6
    # u index major: all v values of u=0 first, at x=1 (the plane).
    assert points[:3, 1] == pytest.approx([0.0, 0.0, 0.0])
    assert points[:3, 2] == pytest.approx([0.0, 1.0, 2.0])
    assert points[3:, 1] == pytest.approx([1.0, 1.0, 1.0])
    assert np.all(points[:, 0] == 1.0)


def test_grid_serialization_round_trip():
    grid = PlanarProbeGrid(
        frame=yz_frame(),
        u=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        v=AxisSpec(start=0.0, stop=1.0, count=9, distribution="cosine"),
    )
    clone = PlanarProbeGrid.from_json(grid.to_json())
    assert clone == grid
    assert np.array_equal(clone.base_points(), grid.base_points())


def test_grid_emission_goes_through_the_documented_import(tmp_path):
    grid = PlanarProbeGrid(
        frame=yz_frame(),
        u=AxisSpec(start=0.0, stop=1.0, count=2),
        v=AxisSpec(start=0.0, stop=1.0, count=2),
    )
    csv = tmp_path / "plane.csv"
    count = write_points_csv(grid.base_points(), csv)
    lines = csv.read_text(encoding="utf-8").strip().splitlines()
    assert count == 4
    assert lines[0] == "4"
    assert lines[1] == "1.0,0.0,0.0,1"
    script = Script(version="26.120")
    emit_probe_import(script, csv, units="METER", frame=1)
    assert "PROBE_POINTS_IMPORT\nUNITS METER\nFRAME 1\n" in script.render()
    # Silenced rather than aimed at a build that lacks it: every
    # registered build documents this command since 2026-08-10.
    silent = registry_without("PROBE_POINTS_IMPORT")
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        emit_probe_import(Script(version="26.120", registry=silent), csv)


def test_coordinate_frame_helper_mirrors_the_frame_definition():
    frame = yz_frame()
    script = Script(version="26.120")
    index = coordinate_frame(
        script,
        name="probe_plane",
        origin=frame.origin,
        x_axis=frame.x_axis,
        y_axis=frame.y_axis,
    )
    text = script.render()
    assert index == 2
    assert "CREATE_NEW_COORDINATE_SYSTEM" in text
    assert "NAME probe_plane" in text
    assert "ORIGIN_X 1.0" in text
    # z axis computed right-handed from the plane axes: y cross z = x.
    assert "VECTOR_Z_X 1.0" in text


# --- PFS-2038.07, GEO-039-F08: a non-finite coordinate reaches no file --------


def test_goal019_bandd_a_nan_axis_is_refused_and_not_normalized():
    """The review's own reproduction: `FrameDefinition(x_axis=(nan, 0, 0))`.

    A NAN NEVER FAILS A COMPARISON. Every guard in the frame asks whether
    something is smaller than a tolerance and `nan < 1e-10` is False, so
    the NaN walked past the degeneracy check and past the parallelism
    check and came out the other side as a frame.
    """
    with pytest.raises(ValidationError, match="not finite"):
        FrameDefinition(x_axis=(float("nan"), 0.0, 0.0), y_axis=(0.0, 1.0, 0.0))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("where", ["x_axis", "y_axis", "origin"])
def test_goal019_bandd_no_non_finite_component_makes_a_frame(where, bad):
    """Both infinities as well as NaN, in either axis and in the origin."""
    kwargs = {
        "origin": (0.0, 0.0, 0.0),
        "x_axis": (1.0, 0.0, 0.0),
        "y_axis": (0.0, 1.0, 0.0),
    }
    kwargs[where] = (bad, 0.0, 0.0) if where != "y_axis" else (0.0, bad, 0.0)
    with pytest.raises(ValidationError, match="not finite"):
        FrameDefinition(**kwargs)


def test_goal019_bandd_a_finite_frame_is_untouched():
    """The control. The refusal is of input that is already invalid.

    A check that refuses everything measures nothing, so the same
    construction with finite numbers must still produce the frame it
    always did.
    """
    frame = FrameDefinition(origin=(1.0, 0.0, 0.0), x_axis=(0.0, 2.0, 0.0), y_axis=(0.0, 0.0, 3.0))
    assert frame.x_axis == (0.0, 1.0, 0.0)
    assert frame.y_axis == (0.0, 0.0, 1.0)


def test_goal019_bandd_write_points_csv_refuses_nan_and_writes_nothing(tmp_path):
    """The writer boundary, checked as well as the frame.

    `write_points_csv` reported two points written and emitted two
    `nan,nan,nan,1` rows into a file the solver opens. A point array
    reaches this function from callers that never built a frame, which is
    why the check is here too and not only there.
    """
    from pyflightstream.probes.errors import ProbeGeometryError

    target = tmp_path / "points.csv"
    points = np.asarray([[0.0, 0.0, 0.0], [float("nan"), 1.0, 2.0]])
    with pytest.raises(ProbeGeometryError, match="not finite"):
        write_points_csv(points, target)
    assert not target.exists(), "a refusal wrote the file anyway"
    # The control, in the same place: finite positions still write.
    assert write_points_csv(np.asarray([[0.0, 1.0, 2.0]]), target) == 1
    assert target.read_text(encoding="utf-8").splitlines() == ["1", "0.0,1.0,2.0,1"]
