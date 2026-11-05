"""A rotor section entry selects a blade-local load decomposition.

Usage: [[farfields]] variant = "rotor_sections", rotor = "ROTOR".
"""

import numpy as np
import pytest

from pyflightstream.cases import PprocSpec


@pytest.mark.requirement("FR-3620")
def test_p0551_rotor_sections_entry():
    value = {"farfields": [{"variant": "rotor_sections", "rotor": "ROTOR"}]}
    try:
        spec = PprocSpec.model_validate(value)
    except ValueError as error:
        pytest.fail(f"the rotor section analysis must accept its declared entry: {error}")
    entry = spec.farfields[0]
    assert entry.chord_fraction == 0.25
    assert entry.trefftz.variant == ["rotor_sections"]


def _sections():
    from pyflightstream.farfield.rotor_sections import SectionLoads

    return SectionLoads(
        radius=np.array([1.0, 2.0]),
        width=np.ones(2),
        chord=np.ones(2),
        radial=np.array([0.0, 0.0, 1.0]),
        points=np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 2.0]]),
        force=np.array([[20.0, -10.0, 0.0], [40.0, -10.0, 0.0]]) + [1.0, 2.0, 0.0],
        friction=np.tile([1.0, 2.0, 0.0], (2, 1)),
        moment=np.array([3.0, 4.0]),
    )


def _project(sections, induced=None, moment=None):
    from pyflightstream.farfield.rotor_sections import project_sections

    return project_sections(
        sections,
        np.zeros((2, 3)) if induced is None else induced,
        axis=np.array([1.0, 0.0, 0.0]),
        wind=np.array([10.0, 0.0, 0.0]),
        hub=np.array([7.0, 8.0, 9.0]),
        moment_point=np.array([7.0, 8.0, 9.0]) if moment is None else moment,
        omega=20.0,
        rho=1.0,
    )


@pytest.mark.requirement("FR-3621")
def test_p0551_pressure_projection_removes_friction_and_transfers_moments():
    totals, strips = _project(_sections())
    assert totals["T"] == pytest.approx(60.0)
    assert totals["Q"] == pytest.approx(30.0)
    assert totals["T_NEAR_INVISCID"] == pytest.approx(60.0)
    assert totals["Q_NEAR_INVISCID"] == pytest.approx(30.0)
    assert totals["T_FRICTION"] == pytest.approx(2.0)
    assert totals["Q_FRICTION"] == pytest.approx(-6.0)
    assert totals["MY"] == pytest.approx(100.0)
    assert totals["MZ"] == pytest.approx(7.0)
    np.testing.assert_allclose(strips["GAMMA"], 1.0)
    np.testing.assert_allclose(strips["ALPHAI_DEG"], 0.0, atol=1e-12)
    moved, _ = _project(_sections(), moment=np.zeros(3))
    assert moved["Q"] == pytest.approx(totals["Q"])
    assert moved["MY"] == pytest.approx(100.0 + 9.0 * 60.0)
    assert moved["MZ"] == pytest.approx(7.0 - 7.0 * 20.0 - 8.0 * 60.0)


@pytest.mark.requirement("FR-3621")
def test_p0551_induction_changes_direction_not_the_near_reference():
    original, _ = _project(_sections())
    perturbed, strips = _project(_sections(), induced=np.tile([5.0, 0.0, 0.0], (2, 1)))
    assert perturbed["T_NEAR_INVISCID"] == original["T_NEAR_INVISCID"]
    assert perturbed["Q_NEAR_INVISCID"] == original["Q_NEAR_INVISCID"]
    assert abs(perturbed["Q"] / original["Q"] - 1.0) > 0.1
    assert np.all(strips["ALPHAI_DEG"] > 0.0)


@pytest.mark.requirement("FR-3622")
def test_p0551_helix_scale_and_derangement():
    from pyflightstream.farfield.rotor_sections import wake_velocity

    # Exact on-axis Biot-Savart integral for a finite helix, radius R and
    # pitch p metres/radian: u_x = G theta/(4 pi sqrt(R^2+(p theta)^2)).
    # The 0.1 percent bound covers discretization at 720 segments per turn.
    theta = np.linspace(0.0, 40.0 * np.pi, 14401)
    radius, pitch, gamma = 1.0, 0.3, 2.0
    line = np.column_stack((pitch * theta, radius * np.cos(theta), radius * np.sin(theta)))
    expected = gamma * theta[-1] / (4.0 * np.pi * np.hypot(radius, pitch * theta[-1]))
    velocity = wake_velocity(np.zeros((1, 3)), [line], np.array([-gamma]), line[:1])
    assert velocity[0, 0] == pytest.approx(expected, rel=0.001)
    wrong = wake_velocity(np.zeros((1, 3)), [line], np.array([gamma]), line[:1])
    assert abs(wrong[0, 0] - expected) > expected


@pytest.mark.requirement("FR-3622")
def test_p0551_wrench_helical_induction_factor():
    from pyflightstream.farfield.rotor_sections import wake_velocity

    # Wrench two-term factor, as written in Wood (2024), equations 8, 11, 13.
    # https://doi.org/10.3389/fenrg.2024.1350551
    # Equation 1 has half its doubly infinite value at the lifting line.
    # A 0.5 percent bound includes the finite 12-turn tail and polygonal helix.
    n, r, t, p = 3, 0.99, 1.0, 0.1
    cr, ct = np.hypot(1.0, r / p), np.hypot(1.0, t / p)
    a = p / (2 * t) * np.sqrt(ct / cr)
    b = ((9 * (t / p) ** 2 + 2) / ct**3 + (3 * (r / p) ** 2 - 2) / cr**3) / 24
    u = (t * (cr - 1) / (r * (ct - 1)) * np.exp(cr - ct)) ** n
    s = -a * (n * u / (1 - u) - b * np.log1p(-u))
    expected = np.array(
        [n / (4 * np.pi * p) - t * s / (2 * np.pi * p**2), t * s / (2 * np.pi * p * r)]
    )
    theta = np.linspace(0.0, 24 * np.pi, 48001)
    lines = [
        np.column_stack((p * theta, t * np.cos(theta + phase), t * np.sin(theta + phase)))
        for phase in np.arange(n) * 2 * np.pi / n
    ]
    measured = wake_velocity(
        np.array([[0.0, r, 0.0]]), lines, -np.ones(n), np.array([line[0] for line in lines])
    )
    np.testing.assert_allclose(measured[0, [0, 2]], expected, rtol=0.005)
    deranged = wake_velocity(
        np.array([[0.0, r, 0.0]]),
        lines,
        np.array([1.0, -1.0, -1.0]),
        np.array([line[0] for line in lines]),
    )
    assert abs(deranged[0, 0] / expected[0] - 1) > 0.5


@pytest.mark.requirement("FR-3623")
def test_p0551_frame_off_span_is_measured():
    from pyflightstream.post.rotor_section_frames import section_span_angle

    ring = np.array([[0.0, 0.0, 2.0], [1.0, 0.0, 2.0], [1.0, 1.0, 2.0], [0.0, 1.0, 2.0]])
    assert section_span_angle(ring, np.array([0.0, 0.0, 1.0])) == pytest.approx(0.0)
    assert section_span_angle(ring, np.array([0.0, np.sqrt(3) / 2, 0.5])) == pytest.approx(60.0)


@pytest.mark.requirement("FR-3624")
@pytest.mark.parametrize("companion", [False, True], ids=["alone", "with-wake"])
@pytest.mark.parametrize(
    "mirror,periodic,wing,cut",
    [
        (False, 1, False, "missing"),
        (True, 1, True, "offspan"),
        (False, 3, False, "aligned"),
        (False, 1, False, "integer-tags"),
    ],
    ids=[
        "P0551-full-missing",
        "P0551-mirror-wing-offspan",
        "P0551-periodic-aligned",
        "P0551-integer-tags",
    ],
)
def test_p0551_rotor_sections_through_product(tmp_path, mirror, periodic, wing, cut, companion):
    import csv
    from dataclasses import replace

    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_helical_wake
    from tests.tier1_offline.test_regression_farfield_products import _p0470_post_rotor_wake

    omega = 1000.0 * 2 * np.pi / 60
    lines, values = _p0470_helical_wake(
        2,
        gamma=np.zeros(4),
        radii=np.array([0.3, 0.5, 0.7, 0.9, 1.0]),
        v=30.0,
        omega=omega,
        turns=1.0,
    )
    lines = [line + [3.1, 0.0, 2.0] for line in lines]
    expected = {}

    def prepare(ctx):
        _blade_exports(tmp_path, integer_tags=cut == "integer-tags")
        ctx.pproc = PprocSpec.model_validate(
            {"farfields": [{"variant": "rotor_sections", "rotor": "ROTOR"}]}
        )
        ctx.record_of["point"].inventory = ["Blade1", "Blade2"] + (["Wing"] if wing else [])
        if mirror:
            ctx.matrix_row.variables.update(SYMMETRY="MIRROR", SYMMETRY_LOADS="true")
        ctx.reference = replace(ctx.reference, xmom_m=1.0, ymom_m=2.0, zmom_m=3.0)
        ctx.points[0] = replace(
            ctx.points[0],
            loads=replace(
                ctx.points[0].loads, surfaces={"Blade1": {"Cx": 1.0}, "Blade2": {"Cx": 1.0}}
            ),
        )

        q = 0.5 * 1.225 * ctx.points[0].loads.reference_velocity_m_s ** 2
        if cut in ("aligned", "offspan"):
            _cut_exports(tmp_path, ctx, q, offspan=cut == "offspan")
        r, dr = np.array([0.25, 0.4, 0.6, 0.8, 0.95]), np.array([0.1, 0.2, 0.2, 0.2, 0.1])
        denominator = 30.0**2 + (omega * r) ** 2
        expected["T"] = 2 * periodic * np.sum(q * 0.2 * 30.0 * omega * r / denominator * dr)
        expected["Q"] = 2 * periodic * np.sum(q * 0.2 * 30.0**2 * r / denominator * dr)

    with pytest.warns(UserWarning) as caught:
        _, _, ctx = _p0470_post_rotor_wake(
            tmp_path, lines, values, rotor=True, sector_copies=periodic, prepare=prepare
        )
    if companion:
        from dataclasses import make_dataclass

        from pyflightstream.post.farfield_products import farfield_products

        # The real context is a dataclass, allowing per-entry copies in the stage.
        ctx = make_dataclass("Context", [(key, object) for key in vars(ctx)])(**vars(ctx))
        ctx.pproc = PprocSpec.model_validate(
            {
                "farfields": [
                    {"variant": "rotor_sections", "rotor": "ROTOR"},
                    {"variant": "wake"},
                ]
            }
        )
        ctx.farfield_super.clear()
        farfield_products(ctx)
        assert "T_WAKE_N_FF_W_ROTOR" in ctx.farfield_super["point"]
    paths = list((tmp_path / "post/farfield").glob("*_rotor_sections_ROTOR.csv"))
    assert paths, [str(w.message) for w in caught]
    path = paths[0]
    with path.open() as stream:
        row = next(csv.DictReader(stream))
    assert float(row["T_FF_RS_ROTOR"]) == pytest.approx(expected["T"], rel=1e-5)
    assert float(row["Q_FF_RS_ROTOR"]) == pytest.approx(expected["Q"], rel=1e-5)
    assert float(row["MY_FF_RS_ROTOR"]) == pytest.approx(-expected["T"], rel=1e-5)
    assert float(row["MZ_FF_RS_ROTOR"]) == pytest.approx(2 * expected["T"], rel=1e-5)
    assert row["LOCAL_VALIDATED"].lower() == str(not wing).lower()
    assert "T_FF_RS_ROTOR" in ctx.farfield_super["point"]
    messages = " ".join(str(w.message) for w in caught)
    if cut == "offspan":
        assert "60 degrees off blade span" in messages
    if cut == "aligned":
        assert "surface re-cut used" not in messages


def _cut_exports(root, ctx, q, *, offspan):
    import re
    from pathlib import Path

    from tests.tier1_offline.test_regression_farfield_products import _farfield_products___sloads

    head = _farfield_products___sloads().split("     Offset,")[0].replace("160", "4")
    force = 1e6 if offspan else q * 0.2
    source = root / "point_sloads.txt"
    source.write_text(
        head
        + "     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n"
        + "".join(f"{r}, .2, 0, 0, 0, {-force}, 0\n" for r in [0.3, 0.8] * 2)
        + " "
        + "-" * 100
        + "\n     Force Units: Newtons\n"
        "     Moment Units: Newton-Meter\n     Software : Flightstream\n",
        encoding="utf-8",
    )
    fixture = (Path(__file__).parent / "fixtures/all_surface_sections_26.123.txt").read_text()
    prefix = re.sub(r"(Number of Surface Sections:\s*)1", r"\g<1>4", fixture.split("Edges=")[0])
    footer = fixture[fixture.rfind("     " + "-" * 100) :]
    sections = []
    for i, r in enumerate([0.3, 0.8] * 2):
        normal = np.array([0.0, -0.866025403784 if offspan else 0.0, 0.5 if offspan else 1.0])
        center = np.array([3.0, r if i < 2 else -r, 2.0])
        ring = [
            center + x * np.array([1.0, 0.0, 0.0]) + z * normal
            for x, z in [(-0.1, -0.01), (0.1, -0.01), (0.1, 0.01), (-0.1, 0.01)]
        ]
        sections.extend(["Edges=4", f"Surface cross-section {i + 1}"])
        for xyz in ring:
            values = np.zeros(20)
            values[1:4] = xyz
            values[10] = 30.0
            sections.append(",".join(str(x) for x in values))
    (root / "point_cp.txt").write_text(
        prefix + "\n".join(sections) + "\n" + footer, encoding="utf-8"
    )
    ctx.exports = {"point": (source, None, None)}
    ctx.record_of["point"].sections_layout = [
        dict(
            distribution=i,
            distribution_families=[f"Blade{i}"],
            families=[f"Blade{i}"],
            plane="XY",
            frame=f"ROTOR_RMRP{i}",
            count=2,
        )
        for i in (1, 2)
    ]


def _blade_exports(root, *, integer_tags=False):
    """Two flat labelled blades; uniform Cp gives a known tangential load."""
    vertices, faces, owners = [], [], []
    for blade in range(2):
        sign = 1 if blade == 0 else -1
        first = len(vertices)
        for r in np.linspace(0.2, 1.0, 9):
            vertices.extend([(2.9, sign * r, 2.0), (3.1, sign * r, 2.0)])
        for i in range(8):
            a = first + 2 * i
            faces.extend([(a, a + 1, a + 3), (a, a + 3, a + 2)])
            owners.extend([blade + 1] * 2)

    def row(values):
        return ",".join(str(x) for x in values) + ","

    n = len(faces)
    saved = [
        "26,1",
        "8172026",
        "$GLOBAL_START$",
        "1",
        "5",
        "$GLOBAL_END$",
        "$MESH_START$",
        "header one",
        "header two",
        "2",
    ]
    for blade in range(2):
        saved.extend([f"{blade + 1}, T, F, F", f"Blade{blade + 1}", ".494,.573,.576"])
    saved.extend([str(n), row(range(1, n + 1)), row([3] * n)])
    saved.extend(row(face[k] + 1 for face in faces) for k in range(3))
    saved.extend(row(owners if k == 6 else [0] * n) for k in range(15))
    edge_rows = [" 6," * n] * 3 if integer_tags else [" F," * n] * 3
    saved.extend([" F," * n, *edge_rows, " F," * n, "0", str(len(vertices))])
    saved.extend(row(v[k] for v in vertices) for k in range(3))
    (root / "point.fsm").write_text("\n".join(saved) + "\n", encoding="utf-8")
    vtk = [
        "# vtk DataFile Version 3.0",
        "synthetic blade loads",
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {len(vertices)} double",
    ]
    vtk.extend(" ".join(str(x) for x in v) for v in vertices)
    vtk.append(f"POLYGONS {n} {4 * n}")
    vtk.extend("3 " + " ".join(str(x) for x in face) for face in faces)
    vtk.append(f"CELL_DATA {n}")
    for name, value in (
        ("Cp_reference", -1.0),
        ("skin_friction_coeff.", 0.0),
        ("Vx", 30.0),
        ("Vy", 0.0),
        ("Vz", 0.0),
    ):
        vtk.extend([f"SCALARS {name} double 1", "LOOKUP_TABLE default", *[str(value)] * n])
    (root / "point.vtk").write_text("\n".join(vtk) + "\n", encoding="utf-8")


@pytest.mark.requirement("FR-3625")
def test_p0551_w_anchor_restores_a_constant_without_scaling_values():
    from pyflightstream.farfield.rotor_sections import anchored_wake_loads

    lines = [np.array([[0.0, 0.0, r], [5.0, 0.0, r]]) for r in (0.5, 1.5, 2.5)]
    values = np.zeros(3)
    t, q, anchor = anchored_wake_loads(
        _sections(),
        np.ones(2),
        lines,
        values,
        np.arange(3),
        hub=np.zeros(3),
        axis=np.array([1.0, 0.0, 0.0]),
        wind=np.array([10.0, 0.0, 0.0]),
        omega=20.0,
        rho=1.0,
    )
    assert (t, q, anchor) == pytest.approx((60.0, 30.0, 1.0))
    np.testing.assert_array_equal(values, np.zeros(3))


@pytest.mark.requirement("FR-3625")
def test_p0551_w_product_retains_raw_and_adds_the_anchor(tmp_path):
    from dataclasses import replace

    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_helical_wake
    from tests.tier1_offline.test_regression_farfield_products import _p0470_post_rotor_wake

    lines, values = _p0470_helical_wake(
        2,
        gamma=np.zeros(4),
        radii=np.array([0.3, 0.5, 0.7, 0.9, 1.0]),
        v=30.0,
        omega=100.0,
        turns=1.0,
    )
    lines = [line + [3.1, 0.0, 2.0] for line in lines]
    expected = {}

    def prepare(ctx):
        _blade_exports(tmp_path)
        ctx.record_of["point"].inventory = ["Blade1", "Blade2"]
        ctx.matrix_row.variables.update(SYMMETRY="MIRROR", SYMMETRY_LOADS="true")
        ctx.points[0] = replace(
            ctx.points[0],
            loads=replace(
                ctx.points[0].loads, surfaces={"Blade1": {"Cx": 1.0}, "Blade2": {"Cx": 1.0}}
            ),
        )
        expected["Q"] = (
            0.5 * 1.225 * ctx.points[0].loads.reference_velocity_m_s ** 2 * 0.2 * (1.0 - 0.2**2)
        )

    with pytest.warns(UserWarning):
        _, rows, _ = _p0470_post_rotor_wake(tmp_path, lines, values, rotor=True, prepare=prepare)
    row = next(row for row in rows if row["VARIANT"] == "W")
    assert "T_WAKE_REPAIRED_N" in row, "W must expose its anchored companion beside raw W"
    assert float(row["T_WAKE_N"]) == pytest.approx(0.0)
    assert float(row["Q_WAKE_NM"]) == pytest.approx(0.0)
    assert abs(float(row["T_WAKE_REPAIRED_N"])) > 0.0
    assert abs(float(row["Q_WAKE_REPAIRED_NM"])) > 0.0
    assert float(row["Q_NEAR_NM"]) == pytest.approx(expected["Q"], rel=1e-5)


@pytest.mark.requirement("FR-3620")
@pytest.mark.parametrize(
    "entry",
    [
        {"variant": "rotor_sections"},
        {"variant": "rotor_sections", "rotor": "../ROTOR"},
        {"variant": "rotor_sections", "rotor": "ROTOR", "chord_fraction": 1.1},
    ],
    ids=["P0551-missing-alias", "P0551-path-alias", "P0551-outside-chord"],
)
def test_p0551_rotor_section_keys_refuse_wrong_numbers(entry):
    with pytest.raises(ValueError):
        PprocSpec.model_validate({"farfields": [entry]})


@pytest.mark.requirement("FR-3632")
@pytest.mark.parametrize("fraction", [0.0, 0.25, 1.0], ids=["P0551-LE", "P0551-QC", "P0551-TE"])
def test_p0551_chord_line_keeps_the_requested_span_at_endpoints(tmp_path, fraction):
    from pyflightstream.post.rotor_sections_surface import blade_surface_strips

    _blade_exports(tmp_path)
    radii = np.array([0.3, 0.5, 0.7, 0.9, 1.0])
    lines = [
        np.array([[3.1, sign * r, 2.0], [4.1, sign * r, 2.0]]) for sign in (1, -1) for r in radii
    ]
    blades, groups, attachments = blade_surface_strips(
        tmp_path / "point.vtk",
        tmp_path / "point.fsm",
        ["Blade1", "Blade2"],
        lines,
        hub=np.array([3.0, 0.0, 2.0]),
        axis=np.array([1.0, 0.0, 0.0]),
        moment_point=np.zeros(3),
        per_m=1.0,
        rho=1.0,
        reference_speed=30.0,
        thrust_sign=1.0,
        chord_fraction=fraction,
    )
    for name, sign in (("Blade1", 1), ("Blade2", -1)):
        expected = np.column_stack(
            [np.full(5, 2.9 + 0.2 * fraction), sign * radii, np.full(5, 2.0)]
        )
        np.testing.assert_allclose(attachments[groups[name]], expected, atol=1e-12)
        np.testing.assert_allclose(blades[name].radial, [0.0, sign, 0.0], atol=1e-12)
