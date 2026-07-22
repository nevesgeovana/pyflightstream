"""Tier 1: twist-encoding kinematics and node bookkeeping (WP5).

The WP5 verification of DLV-007 Section 7: impose analytic flap and
twist distributions, encode them as three-node translations, write and
read the interface files, and reconstruct the solution at machine
precision. The node file and the FSIDisp ordering map come from the
same generator (FSI-R14), which these tests hold to its contract.
"""

from pathlib import Path

import numpy as np
import pytest
from conftest import make_uniform_blade_config

from pyflightstream.fsi import kinematics, nodes

FIXTURES = Path(__file__).parent / "fixtures" / "fsi"


def analytic_solution(radii: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Smooth cantilever-like flap and twist distributions for tests."""
    span = radii[-1] - radii[0]
    xi = (radii - radii[0]) / span
    return 0.05 * xi**2, np.deg2rad(2.0) * xi


def test_encode_touches_only_the_normal_component():
    radii = np.linspace(0.2, 1.2, 11)
    w, theta = analytic_solution(radii)
    le, te = np.full(11, 0.025), np.full(11, -0.025)
    translations = kinematics.encode_station_translations(w, theta, le, te)
    assert translations.shape == (11, 3, 3)
    assert np.all(translations[:, :, 0] == 0.0)
    assert np.all(translations[:, :, 2] == 0.0)
    # EA node carries w; the LE node adds theta * d on top.
    assert np.array_equal(translations[:, 0, 1], w)
    assert np.allclose(translations[:, 1, 1] - w, theta * 0.025, rtol=1e-12)


def test_in_memory_round_trip_is_machine_precision():
    radii = np.linspace(0.2, 1.2, 11)
    w, theta = analytic_solution(radii)
    chord = np.linspace(0.12, 0.08, 11)
    le, te = 0.25 * chord, -0.25 * chord
    translations = kinematics.encode_station_translations(w, theta, le, te)
    w_back, theta_back = kinematics.decode_station_translations(translations, le, te)
    assert np.allclose(w_back, w, rtol=1e-13, atol=1e-16)
    assert np.allclose(theta_back, theta, rtol=1e-12, atol=1e-16)


def test_decode_rejects_wrong_shape():
    with pytest.raises(ValueError, match="n_stations"):
        kinematics.decode_station_translations(np.zeros((5, 3)), 0.02, -0.02)


def test_node_layout_positions_follow_the_map():
    cfg = make_uniform_blade_config()
    layout = nodes.generate_node_layout(cfg)
    positions = nodes.node_positions(layout)
    assert positions.shape == (layout.nodes_per_blade, 3)
    for s, radius in enumerate(layout.station_radii_m):
        for role, offset in (
            ("elastic_axis", 0.0),
            ("leading_edge", layout.le_offset_m[s]),
            ("trailing_edge", layout.te_offset_m[s]),
        ):
            row = layout.row_index(0, s, role) % layout.nodes_per_blade
            assert positions[row, 0] == pytest.approx(layout.ea_offset_chordwise_m[s] + offset)
            assert positions[row, 1] == pytest.approx(layout.ea_offset_normal_m[s])
            assert positions[row, 2] == pytest.approx(radius)
    # Offsets encode a quarter-chord arm on each side (default fraction).
    assert layout.le_offset_m[0] == pytest.approx(0.25 * cfg.blade.chord_m[0])
    assert layout.te_offset_m[0] == pytest.approx(-0.25 * cfg.blade.chord_m[0])


def test_node_file_and_map_round_trip(tmp_path):
    cfg = make_uniform_blade_config()
    layout = nodes.generate_node_layout(cfg)
    nodes.write_node_file(layout, tmp_path / "structural_nodes.csv")
    nodes.write_node_map(layout, tmp_path / cfg.node_map_file)
    reloaded = nodes.load_node_map(tmp_path / cfg.node_map_file)
    assert reloaded == layout
    parsed = nodes.read_fsidisp(tmp_path / "structural_nodes.csv")
    assert parsed.shape == (layout.nodes_per_blade, 3)
    assert np.allclose(parsed, nodes.node_positions(layout), atol=5e-7)


def test_full_file_round_trip_is_machine_precision(tmp_path):
    """WP5 acceptance: impose, write, read, reconstruct, exactly."""
    cfg = make_uniform_blade_config(blade_count=2)
    layout = nodes.generate_node_layout(cfg)
    radii = np.asarray(layout.station_radii_m)
    le, te = np.asarray(layout.le_offset_m), np.asarray(layout.te_offset_m)
    per_blade_in = []
    for blade in range(layout.blade_count):
        w, theta = analytic_solution(radii)
        per_blade_in.append((w * (1.0 + blade), theta * (1.0 - 0.5 * blade)))
    flat = nodes.flatten_blade_translations(
        layout,
        [kinematics.encode_station_translations(w, theta, le, te) for w, theta in per_blade_in],
    )
    nodes.write_fsidisp(tmp_path / "FSIDisp.txt", flat)
    flat_back = nodes.read_fsidisp(tmp_path / "FSIDisp.txt", expected_rows=layout.total_nodes)
    # 17 significant digits: the file round trip is bit exact.
    assert np.array_equal(flat_back, flat)
    for (w_in, theta_in), translations in zip(
        per_blade_in, nodes.unflatten_translations(layout, flat_back), strict=True
    ):
        w_out, theta_out = kinematics.decode_station_translations(translations, le, te)
        assert np.allclose(w_out, w_in, rtol=1e-13, atol=1e-16)
        assert np.allclose(theta_out, theta_in, rtol=1e-12, atol=1e-16)


def test_row_order_is_blade_major():
    layout = nodes.generate_node_layout(make_uniform_blade_config(blade_count=3))
    assert layout.row_index(0, 0, "elastic_axis") == 0
    assert layout.row_index(0, 0, "trailing_edge") == 2
    assert layout.row_index(0, 1, "elastic_axis") == 3
    assert layout.row_index(1, 0, "elastic_axis") == layout.nodes_per_blade
    assert layout.total_nodes == 3 * layout.nodes_per_blade


def test_fsidisp_row_count_guard(tmp_path):
    layout = nodes.generate_node_layout(make_uniform_blade_config())
    nodes.write_fsidisp(tmp_path / "FSIDisp.txt", np.zeros((5, 3)))
    with pytest.raises(ValueError, match="node map orders"):
        nodes.read_fsidisp(tmp_path / "FSIDisp.txt", expected_rows=layout.total_nodes)


def test_flatten_rejects_wrong_blade_count():
    layout = nodes.generate_node_layout(make_uniform_blade_config(blade_count=2))
    one_blade = np.zeros((layout.station_count, 3, 3))
    with pytest.raises(ValueError, match="every blade"):
        nodes.flatten_blade_translations(layout, [one_blade])


def test_wp1_fixture_formats_are_readable():
    """The dry-run interface files parse with the same readers (RPT-005)."""
    disp = nodes.read_fsidisp(FIXTURES / "FSIDisp.txt", expected_rows=11)
    assert np.all(disp == 0.0)
    imported = nodes.read_fsidisp(FIXTURES / "structural_nodes.csv")
    assert imported.shape == (11, 3)
    # The dry-run nodes sit on the pitch axis, span along the third column.
    assert np.all(imported[:, :2] == 0.0)
    assert np.all(np.diff(imported[:, 2]) > 0.0)
