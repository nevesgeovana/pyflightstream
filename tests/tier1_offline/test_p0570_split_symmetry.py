"""0.57.0 C8: ``split-symmetry`` cuts a full model at its symmetry plane and writes the half.

Written first, from requirement C8 of the geometry release: the faces crossing the plane are
trimmed exactly on it by the kernel, the plane edges are left open, the names are kept, and a
model the plane misses is refused. The model is synthetic, built here from closed boxes of
bilinear patches: a body and a wing that cross y = 0, and a tail pair that does not.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.exceptions import InputValueError
from tests.tier1_offline._kernel_support import kernel_or_skip


@pytest.fixture
def kernel():
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    instance = open_kernel("split symmetry test")
    try:
        yield instance
    finally:
        instance.close()


def _box(kernel, lo, hi):
    """The six faces of an axis-aligned closed box, as bilinear patches."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    corners = (
        ((x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)),
        ((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)),
        ((x0, y0, z0), (x0, y0, z1), (x1, y0, z1), (x1, y0, z0)),
        ((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)),
        ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)),
        ((x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)),
    )
    return [
        kernel.add_bspline_surface(
            [[a, d], [b, c]],
            knots_u=[0.0, 1.0],
            knots_v=[0.0, 1.0],
            mult_u=[2, 2],
            mult_v=[2, 2],
            deg_u=1,
            deg_v=1,
        )
        for a, b, c, d in corners
    ]


def _model(kernel, path, *, wing_y=(-3.0, 3.0)):
    """Write the wing-body: BODY and WING cross y = 0, the TAIL pair does not."""
    groups = {
        "BODY": _box(kernel, (0.0, -1.0, -1.0), (4.0, 1.0, 1.0)),
        "WING": _box(kernel, (1.5, wing_y[0], 1.2), (2.5, wing_y[1], 1.4)),
        "TAIL": [
            *_box(kernel, (3.5, 1.5, -0.05), (4.0, 2.5, 0.05)),
            *_box(kernel, (3.5, -2.5, -0.05), (4.0, -1.5, 0.05)),
        ],
    }
    kernel.export_iges(groups, path)
    return path


def _split(*args, **kwargs):
    from pyflightstream.workspace.geometry_pipeline import split_symmetry

    return split_symmetry(*args, **kwargs)


def test_p0570_c8_split_keeps_the_positive_half_trimmed_on_the_plane(kernel, tmp_path):
    source = _model(kernel, tmp_path / "full.igs")
    full = kernel.inspect_file(source, 1e-6)
    assert all(len(owners) == 2 for _, owners in full.edges)  # closed boxes, no free edge
    record = _split(source, tmp_path / "half.igs")
    assert record["status"] == "passed", record
    assert record["plane"] == "y" and record["kept_side"] == "+"
    assert record["faces"] == {"before": 24, "after": 16, "cut": 8, "removed": 16}
    assert record["components"]["BODY"]["faces_after"] == 5
    assert record["components"]["WING"]["faces_after"] == 5
    assert record["components"]["TAIL"]["faces_after"] == 6
    assert record["components"]["BODY"]["cut_length"] == pytest.approx(12.0, rel=1e-9)
    assert record["components"]["WING"]["cut_length"] == pytest.approx(2.4, rel=1e-9)
    assert record["cut_length"] == pytest.approx(14.4, rel=1e-9)
    assert record["warnings"] == []
    half = kernel.inspect_file(tmp_path / "half.igs", 1e-6)
    assert sorted(set(half.names)) == ["BODY", "TAIL", "WING"]
    assert sum(half.areas) == pytest.approx(sum(full.areas) / 2, rel=1e-6)
    free = [samples for samples, owners in half.edges if len(owners) == 1]
    assert free, "the plane edges must be left open"
    assert all(abs(float(y)) < 1e-9 for samples in free for y in samples[:, 1])
    assert sum(len(owners) == 2 for _, owners in half.edges) > 0
    json.dumps(record)


def test_p0570_c8_split_from_the_command_line(kernel, tmp_path, capsys):
    from pyflightstream.run.geom_cli import main

    source = _model(kernel, tmp_path / "full.igs")
    code = main(["split-symmetry", str(source), "--out", str(tmp_path / "half.igs")])
    assert code == 0
    assert (tmp_path / "half.igs").is_file()
    assert '"cut_length"' in capsys.readouterr().out


def test_p0570_c8_a_half_model_is_refused_as_the_plane_misses_it(kernel, tmp_path):
    source = _model(kernel, tmp_path / "full.igs")
    _split(source, tmp_path / "half.igs")
    with pytest.raises(InputValueError, match="nothing of the model lies on the negative side"):
        _split(tmp_path / "half.igs", tmp_path / "again.igs")
    assert not (tmp_path / "again.igs").exists()


def test_p0570_c8_an_unknown_component_is_refused_with_the_names_found(kernel, tmp_path):
    source = _model(kernel, tmp_path / "full.igs")
    with pytest.raises(InputValueError, match=r"'FIN'.*BODY, TAIL, WING"):
        _split(source, tmp_path / "half.igs", component="FIN")
    assert not (tmp_path / "half.igs").exists()


def test_p0570_c8_a_component_left_whole_that_crosses_the_plane_is_refused(kernel, tmp_path):
    source = _model(kernel, tmp_path / "full.igs")
    with pytest.raises(InputValueError, match="'BODY' crosses the plane y = 0"):
        _split(source, tmp_path / "half.igs", component="WING")
    assert not (tmp_path / "half.igs").exists()


def test_p0570_c8_a_named_component_that_does_not_reach_the_plane_is_refused(kernel, tmp_path):
    source = _model(kernel, tmp_path / "full.igs")
    with pytest.raises(InputValueError, match="'TAIL' does not cross the plane y = 0"):
        _split(source, tmp_path / "half.igs", component="TAIL")


def test_p0570_c8_an_asymmetric_component_is_warned_by_name(kernel, tmp_path):
    source = _model(kernel, tmp_path / "full.igs", wing_y=(-3.0, 2.0))
    record = _split(source, tmp_path / "half.igs")
    assert record["status"] == "passed"
    assert [w for w in record["warnings"] if "'WING'" in w and "not symmetric" in w]
    assert not [w for w in record["warnings"] if "'BODY'" in w]


def test_p0570_c8_source_and_destination_must_differ(tmp_path):
    source = tmp_path / "a.igs"
    source.write_text("", encoding="utf-8")
    with pytest.raises(InputValueError, match="source and destination must differ"):
        _split(source, source)


def test_p0570_c8_a_missing_source_is_refused(tmp_path):
    with pytest.raises(InputValueError, match="file does not exist"):
        _split(tmp_path / "a.igs", tmp_path / "h.igs")
