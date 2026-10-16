"""Tier 1: the structural nodes sit inside the blade (FSI-1 of 0.30.0).

The owner's rule of 2026-09-28: the structural nodes are inside the
component. With the blade's sections known, the nodes are placed on each
section's camber line (elastic axis at its chord fraction, leading-edge and
trailing-edge nodes at 10 % and 90 %), and a node set with any node outside
its section, or inside it by less than max(0.1 % chord, 10 % of the local
thickness), is refused naming the node. Order, roles and row count do not
change, so the FSIDisp rows keep their meaning.

The camber line is checked against the NACA four-digit mean line in closed
form, not against the package's own crossing construction.
"""

import json
import math

import numpy as np
import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.fsi import nodes
from pyflightstream.fsi.config import FsiConfig
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.kinematics import NODE_ROLES
from pyflightstream.fsi.sections import airfoil_section_contour, blade_properties_from_sections
from pyflightstream.qa.geometry import naca4_contour
from pyflightstream.script import Script

RADII = [0.3, 0.6, 0.9]
CHORDS = [0.20, 0.15, 0.10]
PITCH = [30.0, 20.0, 10.0]
PITCH_AXIS = 0.25


def _blade(sections=None):
    sections = sections or [
        airfoil_section_contour(naca4_contour("4412", 80), c, PITCH_AXIS) for c in CHORDS
    ]
    return blade_properties_from_sections(
        RADII, sections, CHORDS, PITCH, "ti-6al-4v-grade5-annealed", geometry_source="NACA 4412"
    )


def _config(blade=None, omega=100.0):
    return FsiConfig(blade_count=2, omega_rad_per_s=omega, blade=blade or _blade())


def _naca_mean_line(x, m=0.04, p=0.4):
    if x < p:
        return m / p**2 * (2 * p * x - x * x)
    return m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x * x)


def _section_points(layout):
    """(chordwise, normal) per station and role, from the map's own fields."""
    out = []
    for i in range(layout.station_count):
        e_c, e_n = layout.ea_offset_chordwise_m[i], layout.ea_offset_normal_m[i]
        out.append(
            [
                (e_c, e_n),
                (e_c + layout.le_offset_m[i], layout.le_offset_normal_m[i]),
                (e_c + layout.te_offset_m[i], layout.te_offset_normal_m[i]),
            ]
        )
    return out


@pytest.mark.requirement("FR-170")
def test_nodes_sit_on_the_camber_line_at_their_chord_fractions():
    layout = nodes.generate_node_layout(_config())
    assert layout.roles == list(NODE_ROLES)
    for station, points in enumerate(_section_points(layout)):
        chord = CHORDS[station]
        # 2e-3 chord: the midpoint of the chord-normal crossings departs from
        # the NACA mean line by 1.2e-3 chord at 10 %, where the thickness is
        # laid perpendicular to a mean line of slope 0.15. The mean line itself
        # is 1.75e-2 chord above the chord there.
        for (chordwise, normal), fraction in zip(points[1:], (0.10, 0.90), strict=True):
            # chordwise axis toward the leading edge, origin on the pitch axis
            assert (PITCH_AXIS - chordwise / chord) == pytest.approx(fraction, abs=2e-3)
            assert normal / chord == pytest.approx(_naca_mean_line(fraction), abs=2e-3)
        ea_fraction = PITCH_AXIS - points[0][0] / chord
        assert 0.20 <= ea_fraction <= 0.50
        assert points[0][1] / chord == pytest.approx(_naca_mean_line(ea_fraction), abs=2e-3)


def test_every_generated_node_clears_its_skin():
    # P0300-FSI1-NODES-INSIDE
    blade = _blade()
    layout = nodes.generate_node_layout(_config(blade))
    report = nodes.node_clearances(layout, blade.section_contours_m)
    assert len(report) == 3 * len(RADII)
    assert all(item.inside and item.ok for item in report)
    assert [item.role for item in report] == list(NODE_ROLES) * len(RADII)


@pytest.mark.requirement("FR-1382")
@pytest.mark.parametrize("chord", [0.05, 0.5])
def test_p0420_p1_1d_clearance_scales_with_section(chord):
    """A 50 mm NACA 0012 and its scaled copy both admit the trailing node."""
    contours = [airfoil_section_contour(naca4_contour("0012", 100), chord, 0.25)] * 3
    blade = blade_properties_from_sections(
        RADII,
        contours,
        [chord] * 3,
        [0.0] * 3,
        "ti-6al-4v-grade5-annealed",
        geometry_source="synthetic NACA 0012",
    )
    try:
        layout = nodes.generate_node_layout(_config(blade))
    except FsiInputError as error:
        pytest.fail(f"a geometrically similar section must admit its camber nodes: {error}")
    checks = nodes.node_clearances(layout, contours)
    assert all(item.ok for item in checks)
    for item in checks:
        assert item.required_m == pytest.approx(max(0.001 * chord, 0.1 * item.thickness_m))
    # A node still inside, but almost touching the upper skin, must be refused.
    altered = layout.model_copy(deep=True)
    altered.le_offset_normal_m[0] += checks[1].thickness_m * 0.499
    with pytest.raises(FsiInputError, match="clearance"):
        nodes.refuse_nodes_outside_sections(altered, contours)


@pytest.mark.requirement("FR-39")
def test_p0420_p1_1d_unknown_node_role_is_an_fsi_error(tmp_path):
    """Keyword FSIDisp writing keeps path-first compatibility; unknown roles refuse."""
    layout = nodes.generate_node_layout(_config())
    translations = np.zeros((layout.total_nodes, 3))
    path = tmp_path / "FSIDisp.txt"
    nodes.write_fsidisp(path=path, translations=translations)
    assert nodes.read_fsidisp(path).shape == translations.shape
    with pytest.raises(FsiInputError, match="role.*unknown"):
        layout.row_index(0, 0, "unknown")


def test_an_elastic_axis_outside_the_window_falls_back_to_thirty_percent():
    blade = _blade()
    aft = blade.model_copy(
        update={"elastic_axis_offset_chordwise_m": [-(0.8 - PITCH_AXIS) * c for c in CHORDS]}
    )
    layout = nodes.generate_node_layout(_config(aft))
    for station, chord in enumerate(CHORDS):
        fraction = PITCH_AXIS - layout.ea_offset_chordwise_m[station] / chord
        assert fraction == pytest.approx(nodes.ELASTIC_AXIS_FALLBACK_CHORD_FRACTION, abs=2e-3)


def test_order_roles_and_rows_are_unchanged_and_fsidisp_round_trips():
    cfg = _config()
    layout = nodes.generate_node_layout(cfg)
    assert layout.nodes_per_blade == 3 * len(RADII)
    assert layout.total_nodes == cfg.blade_count * 3 * len(RADII)
    rows = nodes.render_node_file(layout).splitlines()
    assert len(rows) == layout.nodes_per_blade
    radii = [float(row.split(",")[2]) for row in rows]
    assert radii == [r for r in RADII for _ in NODE_ROLES]
    rng = np.random.default_rng(3)
    per_blade = [rng.normal(size=(len(RADII), 3, 3)) for _ in range(cfg.blade_count)]
    flat = nodes.flatten_blade_translations(layout, per_blade)
    for got, want in zip(nodes.unflatten_translations(layout, flat), per_blade, strict=True):
        assert np.allclose(got, want, atol=1e-14)
    assert nodes.NodeOrderingMap.model_validate_json(layout.model_dump_json()) == layout


def test_nodes_embed_at_the_local_twist():
    layout = nodes.generate_node_layout(_config())
    positions = nodes.node_positions(layout)
    for station, beta in enumerate(PITCH):
        chordwise, normal = _section_points(layout)[station][1]
        b = math.radians(beta)
        expected = (
            chordwise * np.array([-math.sin(b), -math.cos(b), 0.0])
            + normal * np.array([-math.cos(b), math.sin(b), 0.0])
            + np.array([0.0, 0.0, RADII[station]])
        )
        assert positions[3 * station + 1] == pytest.approx(expected, abs=1e-12)


def _plate(chord, thickness):
    half, t = chord / 2, thickness / 2
    return [(half, t), (-half, t), (-half, -t), (half, -t)]


def test_a_node_too_near_its_skin_is_refused_naming_it():
    thin = _blade([_plate(c, 0.15e-3) for c in CHORDS])
    with pytest.raises(FsiInputError) as refused:
        nodes.generate_node_layout(_config(thin))
    message = str(refused.value)
    assert "row 0 (station 0, r = 0.3000 m, elastic_axis): inside by 0.07 mm, needs 0.20 mm" in (
        message
    )
    assert "9 structural node(s)" in message


def test_an_offset_layout_outside_its_section_is_refused_naming_the_node():
    blade = _blade()
    typed = blade.model_copy(update={"section_contours_m": None})
    lifted = typed.model_copy(update={"elastic_axis_offset_normal_m": [0.2 * c for c in CHORDS]})
    layout = nodes.generate_node_layout(_config(lifted))
    with pytest.raises(FsiInputError, match=r"row 0 \(station 0, .*OUTSIDE the section"):
        nodes.refuse_nodes_outside_sections(layout, blade.section_contours_m)


def test_the_plan_refuses_a_blade_whose_nodes_are_not_inside(tmp_path, monkeypatch):
    # P0300-FSI1-NODES-INSIDE
    from pyflightstream.cases.workflows import build_script
    from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case

    guard = ws.fsi_workflow_refusal
    monkeypatch.setattr(
        ws,
        "fsi_workflow_refusal",
        lambda workflow: None if workflow == "unsteady_rotor" else guard(workflow),
    )
    case = coupled_case(tmp_path)
    blade = case.fsi.blade
    thin = blade.model_copy(
        update={"section_contours_m": [_plate(c, 0.15e-3) for c in blade.chord_m]}
    )
    case = case.model_copy(update={"fsi": case.fsi.model_copy(update={"blade": thin})})
    script = Script("26.124")
    with pytest.raises(CampaignConfigError, match="FSI structural nodes: .*row 0 \\(station 0"):
        build_script(case, script)
    with pytest.raises(CampaignConfigError, match="FSI structural nodes: .*row 0 \\(station 0"):
        ws.structural_node_layout(case.fsi)
    assert "AEROELASTIC" not in script.render()


def test_a_map_without_camber_offsets_serialises_as_before():
    cfg = _config(_blade().model_copy(update={"section_contours_m": None}))
    layout = nodes.generate_node_layout(cfg)
    dumped = json.loads(layout.model_dump_json())
    assert "le_offset_normal_m" not in dumped
    assert "te_offset_normal_m" not in dumped
    assert "section_contours_m" not in json.loads(cfg.model_dump_json())["blade"]
