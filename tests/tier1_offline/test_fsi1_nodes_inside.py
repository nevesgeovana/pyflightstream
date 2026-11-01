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
from tests.tier1_offline.test_aeroelastic_typed_setup import (
    verified_marking_registry as verified_marking_registry,
)

RADII = [0.3, 0.6, 0.9]
CHORDS = [0.20, 0.15, 0.10]
PITCH = [30.0, 20.0, 10.0]
PITCH_AXIS = 0.25


def _blade(sections=None):
    sections = sections or [
        airfoil_section_contour(
            naca4_contour("4412", 80), chord_m=c, pitch_axis_chord_fraction=PITCH_AXIS
        )
        for c in CHORDS
    ]
    return blade_properties_from_sections(
        RADII,
        sections_m=sections,
        chord_m=CHORDS,
        geometric_pitch_deg=PITCH,
        material="ti-6al-4v-grade5-annealed",
        geometry_source="NACA 4412",
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


def test_p0430_f6_04_clearance_checks_the_serialized_nodes():
    # Sub-micrometre thickness is lost by the six-decimal import format.
    contour = [[-0.75e-4, 0.1e-6], [0.25e-4, 0.1e-6], [0.25e-4, 0.4e-6], [-0.75e-4, 0.4e-6]]
    layout = nodes.NodeOrderingMap(
        blade_count=1,
        station_radii_m=[0.3, 0.6, 0.9],
        roles=list(NODE_ROLES),
        ea_offset_chordwise_m=[0.0] * 3,
        ea_offset_normal_m=[0.25e-6] * 3,
        le_offset_m=[0.15e-4] * 3,
        te_offset_m=[-0.65e-4] * 3,
    )
    with pytest.raises(FsiInputError, match="clearance"):
        nodes.refuse_nodes_outside_sections(layout, [contour] * 3)


@pytest.mark.requirement("FR-1382")
@pytest.mark.parametrize("chord", [0.05, 0.5])
def test_p0420_p1_1d_clearance_scales_with_section(chord):
    """A 50 mm NACA 0012 and its scaled copy both admit the trailing node."""
    contours = [
        airfoil_section_contour(
            naca4_contour("0012", 100), chord_m=chord, pitch_axis_chord_fraction=0.25
        )
    ] * 3
    blade = blade_properties_from_sections(
        RADII,
        sections_m=contours,
        chord_m=[chord] * 3,
        geometric_pitch_deg=[0.0] * 3,
        material="ti-6al-4v-grade5-annealed",
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


# ------------------------------- P0530 contours placed on the mesh cut (FR-3417) --


def _prism_mesh(sections, offsets):
    """A blade mesh built synthetically: at each station a short prism of the station's real
    section, 0.02 m either side of its radius, the real section being the stated contour
    moved by ``offsets`` (toward the leading edge, toward the suction side) in its frame.

    The rotor-frame section axes are written here from their definition (the span along Z,
    the section turned by the pitch beta about Z): toward the leading edge
    (-sin beta, -cos beta, 0), toward the suction side (-cos beta, sin beta, 0).
    """
    vertices, faces = [], []
    for radius, beta_deg, contour, (d_le, d_suction) in zip(
        RADII, PITCH, sections, offsets, strict=True
    ):
        beta = math.radians(beta_deg)
        e_le = np.array([-math.sin(beta), -math.cos(beta), 0.0])
        e_suction = np.array([-math.cos(beta), math.sin(beta), 0.0])
        real = np.asarray(contour) + (d_le, d_suction)
        n = len(real)
        base = len(vertices)
        for z in (radius - 0.02, radius + 0.02):
            vertices.extend(c * e_le + s * e_suction + (0.0, 0.0, z) for c, s in real)
        for i in range(n):
            j = (i + 1) % n
            faces.append((base + i, base + j, base + n + j))
            faces.append((base + i, base + n + j, base + n + i))
    return np.asarray(vertices), np.asarray(faces)


def _quarter_chord_sections():
    return [
        airfoil_section_contour(
            naca4_contour("4412", 80), chord_m=c, pitch_axis_chord_fraction=PITCH_AXIS
        )
        for c in CHORDS
    ]


#: Like the study's first contours: written about the quarter chord with the origin placed
#: on the pitch axis, so the beam sits 26 to 50 mm aft of the blade's real section.
AFT_OFFSETS = [(0.026, 0.0035), (0.038, 0.007), (0.050, 0.011)]


@pytest.mark.requirement("FR-3417")
def test_p0530_a_contour_off_the_mesh_cut_warns_and_a_placed_one_is_silent():
    # P0530-CONTOUR-PLACEMENT: an f201-like blade warns, naming each station and its
    # offset; an f204-like one (the contour IS the mesh's section) says nothing.
    import warnings

    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.fsi.sections import (
        CONTOUR_PLACEMENT_TOLERANCE_M,
        warn_of_contours_off_the_mesh_cut,
    )

    sections = _quarter_chord_sections()
    cfg = _config(_blade(sections))
    aft = _prism_mesh(sections, AFT_OFFSETS)
    with pytest.warns(PyflightstreamWarning) as caught:
        warned = warn_of_contours_off_the_mesh_cut(cfg, *aft, where="blade Blade1")
    assert warned == [1, 2, 3]
    message = str(caught[0].message)
    for station, (d_le, d_suction) in enumerate(AFT_OFFSETS, start=1):
        assert f"station {station} (r = {RADII[station - 1]:.4g} m)" in message
        assert f"{1e3 * d_le:+.1f} mm toward the leading edge" in message
        assert f"{1e3 * d_suction:+.1f} mm toward the suction side" in message
    placed = _prism_mesh(sections, [(0.0, 0.0)] * 3)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert warn_of_contours_off_the_mesh_cut(cfg, *placed, where="blade Blade1") == []
    assert CONTOUR_PLACEMENT_TOLERANCE_M < 0.026


#: A calculated FSI input over the module's stations: NACA 4412 about the quarter chord.
CALCULATED_INPUT = f"""mode = "calculated"
material = "ti-6al-4v-grade5-annealed"

[config]
blade_count = 2
omega_rad_per_s = 100.0

[sections]
station_radii_m = {RADII}
chord_m = {CHORDS}
geometric_pitch_deg = {PITCH}
naca = "4412"
chord_panels = 80
pitch_axis_chord_fraction = {PITCH_AXIS}
geometry_source = "NACA 4412 about the quarter chord"
torsion_grid_cells = 16
"""


@pytest.mark.requirement("FR-3417")
def test_p0530_the_helper_writes_the_contours_placed_on_the_mesh_cut(tmp_path):
    # P0530-CONTOUR-PLACEMENT: the helper WRITES the input with the contours moved, to the
    # path given, and the written input loads back through the FSI input reader with them.
    from pyflightstream.fsi.sections import contour_mesh_offsets, place_on_mesh_cut
    from pyflightstream.workspace.fsi_setup import resolve_fsi_setup

    source, target = tmp_path / "f001.toml", tmp_path / "f002.toml"
    source.write_text(CALCULATED_INPUT, encoding="utf-8")
    cfg = resolve_fsi_setup(source).effective
    stated = cfg.blade.section_contours_m
    aft = _prism_mesh(stated, AFT_OFFSETS)
    written = place_on_mesh_cut(cfg, *aft, source=source, target=target)
    assert source.read_text(encoding="utf-8") == CALCULATED_INPUT, "the input is never rewritten"
    for contour, before, offset in zip(written, stated, AFT_OFFSETS, strict=True):
        np.testing.assert_allclose(np.asarray(contour), np.asarray(before) + offset, atol=1e-9)
    loaded = resolve_fsi_setup(target).effective
    np.testing.assert_allclose(
        np.asarray(loaded.blade.section_contours_m), np.asarray(written), atol=1e-12
    )
    assert "placed on the mesh cut" in loaded.blade.provenance.geometry_source
    for offset in contour_mesh_offsets(loaded, *aft):
        assert offset is not None and math.hypot(*offset) < 1e-9


@pytest.mark.requirement("FR-3417")
def test_p0530_the_helper_keeps_every_other_table_and_writes_a_file_that_loads(tmp_path):
    # REL-001: an airfoil written one point a line, a [sections] header with a comment and an
    # indented table after [sections] are valid TOML; the rewrite must neither corrupt the input
    # in place nor drop a table, and the file it writes loads back with the placed contours.
    import tomllib

    from pyflightstream.fsi.sections import place_on_mesh_cut
    from pyflightstream.workspace.fsi_setup import resolve_fsi_setup

    unit = naca4_contour("4412", 20).tolist()
    points = ",\n".join(f"[{x!r}, {y!r}]" for x, y in unit)
    text = (
        'mode = "calculated"\nmaterial = "ti-6al-4v-grade5-annealed"\n\n'
        "[config]\nblade_count = 2\nomega_rad_per_s = 100.0\n\n"
        "[sections]  # the blade's stations\n"
        f"station_radii_m = {RADII}\nchord_m = {CHORDS}\ngeometric_pitch_deg = {PITCH}\n"
        f"pitch_axis_chord_fraction = {PITCH_AXIS}\n"
        'geometry_source = "unit airfoil, one point a line"\ntorsion_grid_cells = 16\n'
        f"airfoil = [\n{points}\n]\n\n"
        "  [calibration]\n  bending_stiffness_n_m2 = 2.0\n"
    )
    source = tmp_path / "f001.toml"
    source.write_text(text, encoding="utf-8")
    before = tomllib.loads(text)
    cfg = resolve_fsi_setup(source).effective
    aft = _prism_mesh(cfg.blade.section_contours_m, AFT_OFFSETS)
    written = place_on_mesh_cut(cfg, *aft, source=source, target=source)
    after = tomllib.loads(source.read_text(encoding="utf-8"))
    assert {k: v for k, v in after.items() if k != "sections"} == {
        k: v for k, v in before.items() if k != "sections"
    }
    assert after["sections"]["sections_m"] == written and "airfoil" not in after["sections"]
    loaded = resolve_fsi_setup(source).effective
    np.testing.assert_allclose(
        np.asarray(loaded.blade.section_contours_m), np.asarray(written), atol=1e-12
    )


@pytest.mark.requirement("FR-3417")
def test_p0530_the_written_file_names_what_the_placed_contours_replaced(tmp_path):
    # REL-006: a comment line in [sections] names the key replaced (naca here, then the
    # earlier sections_m on a second placement) and that the contours were placed.
    from pyflightstream.fsi.sections import place_on_mesh_cut
    from pyflightstream.workspace.fsi_setup import resolve_fsi_setup

    source, target, again = (tmp_path / f"f00{n}.toml" for n in (1, 2, 3))
    source.write_text(CALCULATED_INPUT, encoding="utf-8")
    cfg = resolve_fsi_setup(source).effective
    aft = _prism_mesh(cfg.blade.section_contours_m, AFT_OFFSETS)
    place_on_mesh_cut(cfg, *aft, source=source, target=target)
    lines = target.read_text(encoding="utf-8").splitlines()
    opened = lines[lines.index("[sections]") + 1]
    assert opened == (
        "# sections_m: the contours placed on the mesh cut (place_on_mesh_cut), "
        'replacing naca = "4412"'
    )
    place_on_mesh_cut(resolve_fsi_setup(target).effective, *aft, source=target, target=again)
    lines = again.read_text(encoding="utf-8").splitlines()
    assert lines[lines.index("[sections]") + 1].endswith("replacing the earlier sections_m")


def _contour_warnings_of_a_row(tmp_path, units: str, metres_per_unit: float) -> list[str]:
    """Build a coupled rotor row whose OBJ is the aft-placed blade written in ``units``.

    The blade sits on the fixture rotor's hub, off the origin, where the script places the
    blade's frame; the contours are placed in that frame.
    """
    from pyflightstream.cases.mesh import MeshImport
    from tests.tier1_offline.test_aeroelastic_typed_setup import _named_fsi_case, coupled_case
    from tests.tier1_offline.test_p0520_norefusal import build, messages

    sections = _quarter_chord_sections()
    cfg = FsiConfig(
        blade_count=1,
        omega_rad_per_s=40 * math.pi,
        time_increment_s=0.0001,
        blade=_blade(sections),
    )
    vertices, faces = _prism_mesh(sections, AFT_OFFSETS)
    case = coupled_case(tmp_path)
    hub = np.asarray(case.rotors["ROTOR"].origin)
    assert np.abs(hub).max() > 0.05, "the fixture's hub must sit off the origin"
    mesh = tmp_path / "blade.obj"
    lines = ["o Blade1"]
    lines += [
        "v " + " ".join(repr(float(value) / metres_per_unit) for value in vertex + hub)
        for vertex in vertices
    ]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    mesh.write_text("\n".join(lines) + "\n", encoding="utf-8")
    case = _named_fsi_case(case.model_copy(update={"geometry": str(mesh), "fsi": cfg}))
    case = case.model_copy(update={"mesh_import": MeshImport(units=units)})
    _, caught = build(case, "26.124")
    return [m for m in messages(caught) if "cut of the imported mesh" in m]


@pytest.mark.requirement("FR-3417")
@pytest.mark.parametrize(("units", "metres_per_unit"), [("METER", 1.0), ("MILLIMETER", 0.001)])
def test_p0530_the_plan_reads_the_blade_in_the_unit_its_import_states(
    tmp_path, units, metres_per_unit
):
    # REL-002: an OBJ written in millimetres is the same blade as one written in metres, and a
    # blade on a hub off the origin is placed in the frame on that hub; the plan's contour
    # check reads the mesh in the unit the import states about the hub, so both rows warn
    # alike, with the offsets the blade has.
    said = _contour_warnings_of_a_row(tmp_path, units, metres_per_unit)
    assert len(said) == 1, said
    for station, (d_le, d_suction) in enumerate(AFT_OFFSETS, start=1):
        assert f"station {station} (r = {RADII[station - 1]:.4g} m)" in said[0]
        assert f"{1e3 * d_le:+.1f} mm toward the leading edge" in said[0]
        assert f"{1e3 * d_suction:+.1f} mm toward the suction side" in said[0]


# --------------------------------- P0530 sections cut from the mesh (PFS-2185.11) --

#: The synthetic blade, written from its definition: NACA 4412 about its quarter chord on the
#: z axis, chord 0.2 m at r = 0.2 m tapering to 0.1 m at r = 1.0 m, twisted from 40 deg to
#: 15 deg, placed with the rotor-frame axes (toward the leading edge (-sin b, -cos b, 0),
#: toward the suction side (-cos b, sin b, 0)).
ROOT_M, TIP_M = 0.2, 1.0


def _chord_at(radius):
    return 0.2 - 0.1 * (radius - ROOT_M) / (TIP_M - ROOT_M)


def _twist_at(radius):
    return 40.0 - 25.0 * (radius - ROOT_M) / (TIP_M - ROOT_M)


def _naca_blade(rings=41, panels=80, *, open_band=None, open_te=False, flare=0.0):
    """Vertices [m] and 0-based triangles of the blade, ring by ring, flat end caps.

    ``open_band`` (r0, r1) leaves out the lower-surface faces between those radii, so no cut
    there closes; ``open_te`` drops the points aft of 99 % chord and the faces across the gap,
    leaving the trailing edge open; ``flare`` widens the rings below 0.26 m as a root fillet.
    """
    unit = naca4_contour("4412", panels)[:-1]
    lower = np.arange(len(unit)) <= panels  # the contour runs the lower surface first
    if open_te:
        keep = unit[:, 0] < 0.99
        unit, lower = unit[keep], lower[keep]
    count = len(unit)
    vertices, faces = [], []
    radii = np.linspace(ROOT_M, TIP_M, rings)
    for radius in radii:
        beta = math.radians(_twist_at(radius))
        lead = np.array([-math.sin(beta), -math.cos(beta), 0.0])
        suction = np.array([-math.cos(beta), math.sin(beta), 0.0])
        grow = 1.0 + flare * max(0.0, (0.26 - radius) / 0.06) ** 2
        section = airfoil_section_contour(unit, chord_m=_chord_at(radius)) * grow
        vertices += [c * lead + s * suction + (0.0, 0.0, radius) for c, s in section]
    for k in range(rings - 1):
        band = open_band and open_band[0] - 1e-9 <= radii[k] and radii[k + 1] <= open_band[1] + 1e-9
        for i in range(count - 1 if open_te else count):
            j = (i + 1) % count
            if band and lower[i] and lower[j]:
                continue
            a, b, c, d = k * count + i, k * count + j, (k + 1) * count + j, (k + 1) * count + i
            faces += [(a, b, c), (a, c, d)]
    if not open_te:
        for k in (0, rings - 1):
            centre = len(vertices)
            vertices.append(np.mean(vertices[k * count : (k + 1) * count], axis=0))
            faces += [(centre, k * count + i, k * count + (i + 1) % count) for i in range(count)]
    return np.asarray(vertices), np.asarray(faces)


def _write_obj(path, vertices, faces, metres_per_unit=1.0, units="METER"):
    lines = ["o Blade1"]
    lines += [
        "v " + " ".join(repr(float(v) / metres_per_unit) for v in point) for point in vertices
    ]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.with_suffix(".obj.boundaries.toml").write_text(
        f'boundaries = ["Blade1"]\n[import]\nunits = "{units}"\n', encoding="utf-8"
    )
    return path


def _write_fsm(path, vertices, faces):
    """The blade as a saved simulation in metres with one boundary, Blade1 (the layout of
    test_post_products' placement .fsm: the boundary row is the seventh per-face row)."""

    def row(values):
        return ",".join(str(value) for value in values) + ","

    count = len(faces)
    lines = ["26,1", "2122026", "$GLOBAL_START$", "1", "5", "$GLOBAL_END$", "$MESH_START$"]
    lines += ["header one", "header two", "1", "1, T, F, F", "Blade1", ".494,.573,.576"]
    lines += [str(count), row(range(1, count + 1)), row([3] * count)]
    lines += [row(int(t[slot]) + 1 for t in faces) for slot in range(3)]
    lines += [row([1] * count if index == 6 else [0] * count) for index in range(15)]
    lines += [" " + ",".join([" F"] * count) + ","] * 5
    lines += ["0", str(len(vertices))]
    lines += [row(f"{v[axis]:.12f}" for v in vertices) for axis in range(3)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _reference_naca(points=4000):
    """The NACA 4412 curve finely, the angle its longest chord makes with the chord line
    (the leading edge being the point farthest from the trailing edge), and that chord."""
    dense = naca4_contour("4412", points)
    far = dense[int(np.argmax(np.hypot(dense[:, 0] - 1.0, dense[:, 1])))]
    return dense, math.degrees(math.atan2(far[1], 1.0 - far[0])), math.hypot(1.0 - far[0], far[1])


def _off_the_curve(contour, radius, pitch, dense):
    """Largest distance [chord] of a derived contour from the NACA curve of its radius."""
    beta, twist = math.radians(pitch), math.radians(_twist_at(radius))
    points = np.asarray(contour)
    xy = points[:, :1] * [-math.sin(beta), -math.cos(beta)]
    xy = xy + points[:, 1:] * [-math.cos(beta), math.sin(beta)]
    along = xy @ [-math.sin(twist), -math.cos(twist)]
    across = xy @ [-math.cos(twist), math.sin(twist)]
    unit = np.column_stack([0.25 - along / _chord_at(radius), across / _chord_at(radius)])
    start, step = dense[:-1], np.diff(dense, axis=0)
    share = np.einsum("pkj,kj->pk", unit[:, None, :] - start[None], step) / np.sum(step**2, axis=1)
    nearest = start[None] + np.clip(share, 0.0, 1.0)[..., None] * step[None]
    return float(np.linalg.norm(unit[:, None, :] - nearest, axis=2).min(axis=1).max())


def _properties(table, sections_key="sections_m"):
    return blade_properties_from_sections(
        table["station_radii_m"],
        sections_m=table[sections_key],
        chord_m=table["chord_m"],
        geometric_pitch_deg=table["geometric_pitch_deg"],
        material="ti-6al-4v-grade5-annealed",
        geometry_source="the synthetic blade",
        torsion_grid_cells=32,
    )


@pytest.mark.requirement("FR-3440")
@pytest.mark.parametrize(("units", "metres_per_unit"), [("METER", 1.0), ("MILLIMETER", 0.001)])
def test_p0530_mesh_sections_recover_a_twisted_naca_blade(tmp_path, units, metres_per_unit):
    # P0530-MESH-SECTIONS A1: the blade written in metres and in millimetres; each section's
    # contour within 0.1 % chord of the NACA curve, its pitch within 0.05 deg of the twist plus
    # the angle of the airfoil's own longest chord, and EI, GJ within 1 % of the analytic ones.
    from pyflightstream.workspace.fsi_setup import beam_sections

    obj = _write_obj(tmp_path / "blade.obj", *_naca_blade(), metres_per_unit, units)
    table = beam_sections(obj, "Blade1", 5).sections
    dense, angle, longest = _reference_naca()
    radii = table["station_radii_m"]
    np.testing.assert_allclose(radii, np.linspace(ROOT_M, TIP_M, 5), atol=1e-5)
    for radius, chord, pitch, contour in zip(
        radii, table["chord_m"], table["geometric_pitch_deg"], table["sections_m"], strict=True
    ):
        assert abs(pitch - (_twist_at(radius) + angle)) < 0.05, (radius, pitch)
        assert abs(chord / (_chord_at(radius) * longest) - 1.0) < 1e-3, (radius, chord)
        assert _off_the_curve(contour, radius, pitch, dense) < 1e-3, radius
    analytic = {
        "sections_m": [
            airfoil_section_contour(naca4_contour("4412", 300), chord_m=_chord_at(r)).tolist()
            for r in radii
        ]
    }
    derived, expected = _properties(table), _properties({**table, **analytic})
    for name in ("bending_stiffness_n_m2", "torsion_stiffness_n_m2"):
        np.testing.assert_allclose(getattr(derived, name), getattr(expected, name), rtol=0.01)


@pytest.mark.requirement("FR-3440")
def test_p0530_the_same_blade_saved_as_fsm_gives_the_sections_of_the_obj(tmp_path):
    # P0530-MESH-SECTIONS A2: the saved simulation of the same blade, read in the unit it
    # stores, gives the sections of the OBJ.
    from pyflightstream.workspace.fsi_setup import beam_sections

    vertices, faces = _naca_blade()
    (tmp_path / "obj").mkdir()
    (tmp_path / "fsm").mkdir()
    obj = beam_sections(_write_obj(tmp_path / "obj" / "blade.obj", vertices, faces), "Blade1", 5)
    fsm = beam_sections(_write_fsm(tmp_path / "fsm" / "blade.fsm", vertices, faces), "Blade1", 5)
    assert fsm.path.name == "blade.Blade1.beam.toml"
    for key in ("station_radii_m", "chord_m", "geometric_pitch_deg"):
        np.testing.assert_allclose(fsm.sections[key], obj.sections[key], rtol=1e-9, atol=1e-9)
    for ours, theirs in zip(fsm.sections["sections_m"], obj.sections["sections_m"], strict=True):
        np.testing.assert_allclose(ours, theirs, atol=1e-9)


@pytest.mark.requirement("FR-3441")
def test_p0530_an_open_trailing_edge_is_closed_by_its_segment(tmp_path):
    # P0530-MESH-SECTIONS A3: the trailing edge left open (points aft of 99 % chord dropped,
    # no face across the gap) still gives every station, each closed by the gap's segment.
    import warnings

    from pyflightstream.fsi.sections import polygon_area_moments, sections_from_mesh

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        cut = sections_from_mesh(*_naca_blade(21, 40, open_te=True), 5)
    assert cut.trailing_edge_closed == [True] * 5 and cut.left_out_radii_m == []
    for radius, contour in zip(cut.station_radii_m, cut.sections_m, strict=True):
        area = polygon_area_moments(contour).area_m2
        closed = polygon_area_moments(
            airfoil_section_contour(naca4_contour("4412", 40), chord_m=_chord_at(radius))
        ).area_m2
        assert abs(area / closed - 1.0) < 0.01, radius


@pytest.mark.requirement("FR-3441")
def test_p0530_the_root_station_is_the_first_closed_cut_above_a_fillet(tmp_path):
    # P0530-MESH-SECTIONS A3: a flared root whose lower surface stops short of 0.26 m (the cut
    # crosses the fillet's open edge there): the first station is the first closed cut, at
    # 0.26 m, and the file records that radius.
    import tomllib

    from pyflightstream.workspace.fsi_setup import beam_sections

    blade = _naca_blade(41, 40, open_band=(ROOT_M, 0.26), flare=0.5)
    written = beam_sections(_write_obj(tmp_path / "blade.obj", *blade), "Blade1", 5)
    stated = tomllib.loads(written.path.read_text(encoding="utf-8"))
    assert abs(stated["requested_radii_m"][0] - 0.26) < 1e-5
    assert stated["sections"]["station_radii_m"][0] == stated["requested_radii_m"][0]
    assert abs(stated["sections"]["station_radii_m"][-1] - TIP_M) < 1e-5


@pytest.mark.requirement("FR-3441")
def test_p0530_a_station_that_does_not_close_moves_to_the_nearest_closed_cut(tmp_path):
    # P0530-MESH-SECTIONS A3: stations at 0.2, 0.4, 0.6, 0.8, 1.0 m; the lower surface is open
    # from 0.76 to 0.86 m, so the 0.8 m station is cut at 0.76 m, the nearest closed radius
    # within its window (0.7 to 0.9 m); the file states the radius used and it is warned.
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.fsi.sections import sections_from_mesh

    with pytest.warns(PyflightstreamWarning, match=r"does not close at 0\.8 m to 0\.75999"):
        cut = sections_from_mesh(*_naca_blade(51, 40, open_band=(0.76, 0.86)), 5, where="b")
    assert cut.requested_radii_m[3] == pytest.approx(0.8, abs=1e-5)
    assert cut.station_radii_m[3] == pytest.approx(0.76, abs=1e-4)
    assert len(cut.station_radii_m) == 5 and cut.left_out_radii_m == []


@pytest.mark.requirement("FR-3441")
def test_p0530_a_station_with_no_closed_cut_in_its_window_is_left_out(tmp_path):
    # P0530-MESH-SECTIONS A3: open from 0.66 to 0.94 m, no cut closes in the 0.8 m station's
    # window (0.7 to 0.9 m), next to the tip: that station is warned and left out.
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.fsi.sections import sections_from_mesh

    with pytest.warns(PyflightstreamWarning, match=r"0\.8 m, so those stations are left out"):
        cut = sections_from_mesh(*_naca_blade(51, 40, open_band=(0.66, 0.94)), 5, where="b")
    assert cut.left_out_radii_m == [pytest.approx(0.8, abs=1e-5)]
    np.testing.assert_allclose(cut.station_radii_m, [0.2, 0.4, 0.6, 1.0], atol=1e-5)


@pytest.mark.requirement("FR-3440")
def test_p0530_the_derived_contours_lie_on_the_mesh_cut(tmp_path):
    # P0530-MESH-SECTIONS A4: the beam built from the derived sections places every contour
    # on the blade's cut of the mesh to below 0.01 mm (contour_mesh_offsets), and the plan's
    # placement check says nothing.
    import warnings

    from pyflightstream.fsi.sections import contour_mesh_offsets, warn_of_contours_off_the_mesh_cut
    from pyflightstream.workspace.fsi_setup import beam_sections

    vertices, faces = _naca_blade()
    table = beam_sections(_write_obj(tmp_path / "blade.obj", vertices, faces), "Blade1", 7)
    cfg = FsiConfig(blade_count=1, omega_rad_per_s=100.0, blade=_properties(table.sections))
    offsets = contour_mesh_offsets(cfg, vertices, faces)
    assert all(offset is not None and math.hypot(*offset) < 1e-5 for offset in offsets), offsets
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert warn_of_contours_off_the_mesh_cut(cfg, vertices, faces, where="b") == []


@pytest.mark.requirement("FR-3442")
def test_p0530_a_kept_beam_file_is_used_as_it_is_and_recut_on_a_changed_mesh_or_count(
    tmp_path,
):
    # P0530-MESH-SECTIONS A5: same sha256 and count, the file is untouched and its hand edit
    # used; a changed mesh, then a changed count, is warned, the old file kept as .bak and the
    # sections cut again.
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.workspace.fsi_setup import beam_sections

    obj = _write_obj(tmp_path / "blade.obj", *_naca_blade(21, 40))
    first = beam_sections(obj, "Blade1", 4)
    text = first.path.read_text(encoding="utf-8")
    chord = repr(first.sections["chord_m"][1])
    edited = text.replace(
        f"chord_m = [{repr(first.sections['chord_m'][0])}, {chord}",
        f"chord_m = [{repr(first.sections['chord_m'][0])}, 0.123",
        1,
    )
    assert edited != text
    first.path.write_text(edited, encoding="utf-8")
    again = beam_sections(obj, "Blade1", 4)
    assert again.path.read_text(encoding="utf-8") == edited
    assert again.sections["chord_m"][1] == 0.123
    backup = first.path.with_name("blade.Blade1.beam.toml.bak")
    obj.write_text(obj.read_text(encoding="utf-8") + "# moved\n", encoding="utf-8")
    with pytest.warns(PyflightstreamWarning, match="cut from a mesh of sha256"):
        recut = beam_sections(obj, "Blade1", 4)
    assert backup.read_text(encoding="utf-8") == edited
    assert recut.sections["chord_m"][1] == first.sections["chord_m"][1]
    with pytest.warns(PyflightstreamWarning, match="holds 4 stations and 6 are asked for"):
        six = beam_sections(obj, "Blade1", 6)
    assert len(six.sections["station_radii_m"]) == 6
    assert "stations = 4" in backup.read_text(encoding="utf-8")


#: An FSI input whose sections come from the row's mesh.
MESH_INPUT = """mode = "calculated"
material = "ti-6al-4v-grade5-annealed"
[config]
blade_count = 1
omega_rad_per_s = 100.0
[sections]
source = "mesh"
{stations}torsion_grid_cells = 16
"""


@pytest.mark.requirement("FR-3443")
def test_p0530_an_input_from_the_mesh_without_stations_stops_the_plan(tmp_path):
    # P0530-MESH-SECTIONS A6: source = "mesh" and no stations states no usable sections; the
    # plan stops on the input, asking for stations = <n>.
    import sys
    from pathlib import Path

    from tests.support_helpers import make_library
    from tests.tier1_offline.test_raw_mesh_conditions import _case as bind_row

    workspace = make_library(tmp_path, register_build=("26.124", Path(sys.executable).as_posix()))
    _write_obj(workspace.inputs_dir / "geometries" / "blade.obj", *_naca_blade(21, 40))
    (workspace.inputs_dir / "fsi" / "f001.toml").write_text(MESH_INPUT.format(stations=""))
    with pytest.raises(
        ValueError,
        match=r'f001\.toml: \[sections\] source = "mesh" states no'
        r" stations.*add stations = <n>",
    ):
        bind_row(tmp_path, workspace, geometry="blade.obj", tail=" / FSI: f001")


@pytest.mark.requirement("FR-3443")
def test_p0530_fewer_than_two_usable_stations_stop_the_input_naming_the_radii(tmp_path):
    # P0530-MESH-SECTIONS A6: one station, or a blade whose cuts never close, is no beam; the
    # input is refused naming the radii tried.
    from pyflightstream.workspace.fsi_setup import FsiSetupError, beam_sections, resolve_row_fsi

    obj = _write_obj(tmp_path / "blade.obj", *_naca_blade(21, 40))
    inputs = tmp_path / "inputs"
    (inputs / "fsi").mkdir(parents=True)
    (inputs / "fsi" / "f001.toml").write_text(MESH_INPUT.format(stations="stations = 1\n"))
    with pytest.raises(
        FsiSetupError,
        match=r"f001\.toml: .*fewer than two usable stations.*"
        r"the radii tried were 0\.2 m",
    ):
        resolve_row_fsi(
            inputs, {"FSI": "f001"}, mesh_sections=lambda n: beam_sections(obj, "Blade1", n)
        )
    open_blade = _write_obj(tmp_path / "open.obj", *_naca_blade(21, 40, open_band=(0.0, 2.0)))
    with pytest.raises(FsiSetupError, match="fewer than two usable stations.*no cut of the mesh"):
        beam_sections(open_blade, "Blade1", 5)


def _rotor_workspace(tmp_path, stations=5):
    """A workspace whose reference r003 holds one rotor on the origin, blade one Blade1 on
    Z, a mesh blade.obj of that blade, and f001 cutting its sections from the mesh."""
    import hashlib
    import sys
    from pathlib import Path

    from tests.support_helpers import make_library
    from tests.tier1_offline.test_raw_mesh_conditions import _case as bind_row

    workspace = make_library(tmp_path, register_build=("26.124", Path(sys.executable).as_posix()))
    vertices, faces = _naca_blade(21, 40)
    obj = _write_obj(workspace.inputs_dir / "geometries" / "blade.obj", vertices, faces)
    obj.with_suffix(".obj.boundaries.toml").write_text(
        'fs_build = "26.124"\nboundaries = ["Blade1"]\n'
        f"boundary_faces = [{len(faces)}]\nmesh_faces = {len(faces)}\n"
        f'mesh_sha256 = "{hashlib.sha256(obj.read_bytes()).hexdigest()}"\n'
        '[import]\nunits = "METER"\n'
        '[trailing_edges.main]\ndetect = "auto"\ntype = "STANDARD"\n',
        encoding="utf-8",
    )
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(
        "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n"
        '[rotors.ROTOR]\nalias = "ROTOR"\nx_m = 0.0\ny_m = 0.0\nz_m = 0.0\naxis = "X"\n'
        'rpm_sign = 1\ndiameter_m = 2.0\nfamilies_blades = ["Blade1"]\n'
        'blade1 = { azimuth_deg = 0.0, zero = "Z" }\n',
        encoding="utf-8",
    )
    (workspace.inputs_dir / "fsi" / "f001.toml").write_text(
        MESH_INPUT.format(stations=f"stations = {stations}\n")
    )
    tail = " / FSI: f001 / RPM: 955"
    return workspace, bind_row(tmp_path, workspace, geometry="blade.obj", tail=tail)


@pytest.mark.requirement("FR-3442")
def test_p0530_the_plan_cuts_the_rows_mesh_into_the_geometrys_beam_file(tmp_path):
    # P0530-MESH-SECTIONS: the plan of a row whose input states source = "mesh" writes
    # blade.Blade1.beam.toml beside the mesh and builds the beam from it, and the provenance
    # names the file and its sha256.
    import tomllib

    from pyflightstream._digest import file_sha256

    workspace, case = _rotor_workspace(tmp_path)
    written = workspace.inputs_dir / "geometries" / "blade.Blade1.beam.toml"
    stated = tomllib.loads(written.read_text(encoding="utf-8"))["sections"]
    assert case.fsi.blade.station_radii_m == stated["station_radii_m"]
    assert case.fsi.blade.geometric_pitch_deg == stated["geometric_pitch_deg"]
    record = {"file": written.name, "sha256": file_sha256(written)}
    assert case.fsi_provenance["beam_sections"] == record
    assert case.fsi.blade.provenance.geometry_file_name == written.name


@pytest.mark.requirement("FR-3442")
def test_p0530_the_run_names_the_beam_file_in_its_blade_mesh_record(tmp_path):
    # P0530-MESH-SECTIONS: blade_mesh, the run's record of how the mesh holds the blade,
    # names the .beam.toml the sections were read from and its sha256.
    from pyflightstream.cases.workflows import blade_mesh_record
    from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case

    beam = {"file": "blade.Blade1.beam.toml", "sha256": "ab" * 32}
    case = coupled_case(tmp_path).model_copy(update={"fsi_provenance": {"beam_sections": beam}})
    record = blade_mesh_record(case)
    assert record["beam_toml"] == beam["file"] and record["beam_toml_sha256"] == beam["sha256"]


@pytest.mark.requirement("FR-3444")
def test_p0530_the_beam_command_writes_the_plans_file_and_its_drawing(tmp_path):
    # P0530-MESH-SECTIONS A7: pyfs-workspace geometry beam writes, for the same mesh, the file
    # the plan wrote, byte for byte; --visual-inspection draws blade.Blade1.beam.pdf.
    import shutil

    from pyflightstream.workspace.cli import main as workspace_main

    workspace, _ = _rotor_workspace(tmp_path / "plan")
    planned = workspace.inputs_dir / "geometries" / "blade.Blade1.beam.toml"
    alone = tmp_path / "alone"
    alone.mkdir()
    for name in ("blade.obj", "blade.obj.boundaries.toml"):
        shutil.copy2(workspace.inputs_dir / "geometries" / name, alone / name)
    argv = ["geometry", "beam", str(alone / "blade.obj"), "--families", "Blade1"]
    assert workspace_main([*argv, "--stations", "5", "--visual-inspection"]) == 0
    assert (alone / "blade.Blade1.beam.toml").read_bytes() == planned.read_bytes()
    pdf = alone / "blade.Blade1.beam.pdf"
    assert pdf.read_bytes().startswith(b"%PDF") and pdf.read_bytes().count(b"/Type /Page") >= 2
