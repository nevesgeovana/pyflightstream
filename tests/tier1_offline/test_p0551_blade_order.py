"""P0551-BLADEORDER: plan a wheel, repair the refused list, and plan again.

Reproduction: plan_matrix(matrix, workspace, write_plan=False) with clockwise
blade families listed in mesh order must block before any solver is run.
"""

import json
import math
import warnings

import numpy as np
import pytest

from tests.tier1_offline.test_goal024_point_name import _matrix, _plan


def wheel(path, count, sense, axis="X", hub=(0, 0, 0), angles=None, weighted=False):
    """Write independent triangular blades in the documented saved mesh layout."""
    vertices = []
    for k in range(count):
        a = math.radians(angles[k] if angles else sense * k * 360 / count)
        for x, r in ((-0.1, 1), (0.1, 1), (0, 2)):
            p = np.array([x, r * math.cos(a), r * math.sin(a)])
            if axis == "Z":
                p = p[[1, 2, 0]]
            vertices.append(p + hub)
        if weighted:
            # Tiny equal-vertex-count patches far to +Y would dominate an
            # unweighted vertex/face centroid, collapsing all blade azimuths.
            vertices.extend(
                np.array([0, 20, 0]) + np.array(v) * 1e-4 for v in ((0, 0, 0), (1, 0, 0), (0, 1, 0))
            )
    xyz = np.array(vertices)
    nf = len(vertices) // 3
    ints = [[0] * nf for _ in range(20)]
    ints[0], ints[1] = list(range(1, nf + 1)), [3] * nf
    for j in range(3):
        ints[2 + j] = list(range(j + 1, nf * 3 + 1, 3))
    ints[11] = [k for k in range(1, count + 1) for _ in range(2 if weighted else 1)]
    lines = [
        "26,1",
        "7012026",
        "$GLOBAL_START$",
        "1.0",
        "5",
        "$GLOBAL_END$",
        "$MESH_START$",
        str(nf),
        str(count + 1),
        str(count),
    ]
    for k in range(count):
        lines += [f"{k + 2}, T, F, F", f"Blade{k + 1}", ".5,.5,.5"]
    lines += [str(nf), *[",".join(map(str, row)) + "," for row in ints]]
    lines += [" F," * nf] * 5
    lines += [
        "0",
        str(len(xyz)),
        *[",".join(map(str, xyz[:, j])) + "," for j in range(3)],
        "0",
        "$MESH_END$",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fixture(
    tmp_path,
    count=6,
    sense=-1,
    axis="X",
    rpm=1200,
    hub=(0, 0, 0),
    sector=False,
    mirror=False,
    angles=None,
):
    workspace, matrix = _matrix(
        tmp_path,
        condition="TASmps:30, ALPHA:0, RPM:sweep",
        values=str(abs(rpm)),
        stem="wheel.fsm",
        workflow="unsteady_rotor",
        cell=f"ROTOR_AXIS:{axis} / DELTA_TIME:0.01 / TIME_ITERATIONS:8 / LAST_REVS_AVG:0.5"
        + (" / PERIODIC_COPIES:6" if sector else ""),
    )
    mesh = workspace.inputs_dir / "geometries" / "wheel.fsm"
    wheel(mesh, 1 if sector else count, sense, axis, hub, angles)
    reference = workspace.inputs_dir / "references" / "r003.toml"
    names = [f"Blade{k + 1}" for k in range(count)]
    mesh.with_name(mesh.name + ".boundaries.toml").write_text(
        "boundaries = " + json.dumps(names[:1] if sector else names) + "\n"
    )
    reference.write_text(
        f'''area_m2 = 1.0
chord_m = 1.0
span_m = 2.0
moment_point = {{ x_m = 31.0, y_m = 22.0, z_m = -14.0 }}
[PROP]
kind = "rotor"
axis = "{axis}"
diameter_m = 4.0
x_m = {float(hub[0])}
y_m = {float(hub[1])}
z_m = {float(hub[2])}
rpm_sign = {-1 if rpm < 0 else 1}
families_blades = {json.dumps(names)}
blade1 = {{ zero = "{"X" if axis == "Z" else "Y"}", azimuth_deg = 0.0 }}
''',
        encoding="utf-8",
    )
    if mirror:
        matrix.write_text(matrix.read_text().replace("NONE", "MIRROR"))
    if sector:
        matrix.write_text(matrix.read_text().replace("NONE", "PERIODIC"))
    return workspace, matrix, reference, mesh, names


@pytest.mark.requirement("FR-3616")
@pytest.mark.parametrize("count", [4, 6], ids=lambda n: f"P0551-{n}")
@pytest.mark.parametrize("sense", [-1, 1])
@pytest.mark.parametrize(
    "axis,rpm,hub,mirror",
    [
        ("X", 1200, (0, 0, 0), False),
        ("Z", -1200, (7, -4, 2), False),
        ("X", -1200, (0, -4, 0), True),
    ],
)
def test_p0551_plan_refuses_wrong_order_and_computed_repair_passes(
    tmp_path, count, sense, axis, rpm, hub, mirror
):
    workspace, matrix, ref, mesh, names = fixture(
        tmp_path, count, sense, axis, rpm, hub, mirror=mirror
    )
    plan = _plan(workspace, matrix)
    if sense == 1:
        assert all(p.status.value == "READY" for p in plan.points), plan.summary()
        assert plan.points[0].rotor_mach["PROP"]["rpm"] == rpm
        return
    assert all(p.status.value == "BLOCKED" for p in plan.points), plan.summary()
    message = plan.summary()
    correct = [names[0], *names[:0:-1]]
    remedy = "families_blades = " + json.dumps(correct)
    assert remedy in message
    assert "PROP" in message and mesh.name in message and json.dumps(names) in message
    ref.write_text(ref.read_text().replace(json.dumps(names), json.dumps(correct)))
    repaired = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in repaired.points), repaired.summary()
    assert repaired.points[0].rotor_mach["PROP"]["rpm"] == rpm


@pytest.mark.requirement("FR-3617")
@pytest.mark.parametrize("count,sector", [(1, False), (6, True)])
def test_p0551_single_blade_and_sector_are_not_refused(tmp_path, count, sector):
    workspace, matrix, *_ = fixture(tmp_path, count=count, sector=sector)
    plan = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in plan.points), plan.summary()


@pytest.mark.requirement("FR-3617")
def test_p0551_uneven_spacing_warns(tmp_path):
    workspace, matrix, *_ = fixture(tmp_path, count=4, sense=1, angles=[0, 80, 180, 270])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in plan.points), plan.summary()
    assert any("blade order has uneven blade spacing" in str(w.message) for w in caught)


@pytest.mark.requirement("FR-3617")
def test_p0551_unreadable_mesh_warns_once_across_points(tmp_path):
    workspace, matrix, _, mesh, _ = fixture(tmp_path)
    mesh.write_text("26,1\n7012026\n")
    matrix.write_text(matrix.read_text().replace("| 1200 |", "| 1200,1300 |"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = _plan(workspace, matrix)
    assert len(plan.points) == 2
    assert all(p.status.value == "READY" for p in plan.points), plan.summary()
    said = [str(w.message) for w in caught if "blade order was not checked" in str(w.message)]
    assert len(said) == 1
    assert "wheel.fsm" in said[0] and "PROP" in said[0]


@pytest.mark.requirement("FR-3616")
@pytest.mark.parametrize("offset,blocked", [(22.4, False), (22.6, True)])
def test_p0551_quarter_pitch_boundary(tmp_path, offset, blocked):
    workspace, matrix, *_ = fixture(tmp_path, count=4, sense=1, angles=[0, 90 + offset, 180, 270])
    plan = _plan(workspace, matrix)
    assert all((p.status.value == "BLOCKED") == blocked for p in plan.points), plan.summary()


@pytest.mark.requirement("FR-3616")
def test_p0551_sector_to_wheel_output_plans(tmp_path):
    from pyflightstream.workspace import sector_to_wheel
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector

    workspace, matrix, _, mesh, _ = fixture(tmp_path, sense=1)
    sector = build_blunt_sector(tmp_path)
    output = tmp_path / "expanded.fsm"
    assert sector_to_wheel(sector, copies=6, blades=["Blade1"], out=output).written
    mesh.write_bytes(output.read_bytes())
    mesh.with_name(mesh.name + ".boundaries.toml").write_text(
        'boundaries = ["Blade1", "S", "N", "Blade2", "Blade3", "Blade4", "Blade5", "Blade6"]\n'
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in plan.points), plan.summary()
    assert not any("blade order was not checked" in str(w.message) for w in caught)


@pytest.mark.requirement("FR-3616")
def test_p0551_area_weighting_ignores_tiny_distant_faces(tmp_path):
    workspace, matrix, _, mesh, _ = fixture(tmp_path, sense=1)
    wheel(mesh, 6, 1, weighted=True)
    plan = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in plan.points), plan.summary()


@pytest.mark.requirement("FR-3616")
def test_p0551_installed_shaft_preserves_geometric_order(tmp_path):
    workspace, matrix, reference, mesh, names = fixture(tmp_path)
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    lines = mesh.read_text().splitlines()
    xyz = np.array([[float(v) for v in line.split(",") if v] for line in lines[-5:-2]]).T
    xyz = xyz @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]).T
    lines[-5:-2] = [",".join(map(str, xyz[:, k])) + "," for k in range(3)]
    mesh.write_text("\n".join(lines) + "\n")
    reference.write_text(
        reference.read_text().replace(
            'axis = "X"', f'axis = {{ shaft = "X", vector_wrt_global = [{c}, {s}, 0] }}'
        )
    )
    refused = _plan(workspace, matrix)
    correct = [names[0], *names[:0:-1]]
    assert "families_blades = " + json.dumps(correct) in refused.summary()
    reference.write_text(reference.read_text().replace(json.dumps(names), json.dumps(correct)))
    accepted = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in accepted.points), accepted.summary()


@pytest.mark.requirement("FR-3616")
@pytest.mark.parametrize("suffix", [".fsm", ".obj"])
@pytest.mark.parametrize("selection", ["family", "casefold"])
@pytest.mark.parametrize("sense", [-1, 1])
def test_rel551_r1_blade_order_resolves_surface_families(tmp_path, suffix, selection, sense):
    from pyflightstream._fsm import boundary_surface
    from pyflightstream.cases.blade_order import validate_blade_order
    from pyflightstream.cases.reference_blocks import CampaignConfigError, RotorBlock

    source = tmp_path / "source.fsm"
    wheel(source, 4, sense)
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    data = source.read_text()
    for i, name in enumerate(names, 1):
        data = data.replace(f"Blade{i}\n", f"{name}1\n")
    source.write_text(data)
    if suffix == ".obj":
        mesh = tmp_path / "wheel.obj"
        rows = []
        for i, name in enumerate(names):
            vertices, _ = boundary_surface(source, name + "1")
            # Two separately named surfaces of each blade, sharing its area.
            rows.extend("v " + " ".join(map(str, p)) for p in vertices)
            for part in (1, 2) if selection == "family" else (1,):
                rows += [f"g {name}{part}", f"f {3 * i + 1} {3 * i + 2} {3 * i + 3}"]
    else:
        mesh = source
    if suffix == ".obj":
        mesh.write_text("\n".join(rows) + "\n")
    selected = names if selection == "family" else [name.lower() + "1" for name in names]
    rotor = RotorBlock(
        alias="R",
        axis="X",
        diameter_m=4,
        families_blades=selected,
        blade1={"zero": "Y", "azimuth_deg": 0.0},
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if sense < 0:
            with pytest.raises(CampaignConfigError, match="blade order disagrees"):
                validate_blade_order(mesh, rotor, units="METER")
        else:
            validate_blade_order(mesh, rotor, units="METER")
    assert not any("was not checked" in str(w.message) for w in caught)


@pytest.mark.requirement("FR-3616")
@pytest.mark.parametrize("sense", [-1, 1])
def test_rel551_r1_integer_edge_tags_do_not_disable_geometry_check(tmp_path, sense):
    from pyflightstream._fsm import MeshReadError, trailing_edge_midpoints

    workspace, matrix, _, mesh, _ = fixture(tmp_path, count=4, sense=sense)
    lines = mesh.read_text().splitlines()
    first = lines.index(" F," * 4)
    lines[first + 1 : first + 4] = [" 6," * 4] * 3
    mesh.write_text("\n".join(lines) + "\n")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = _plan(workspace, matrix)
    assert all((p.status.value == "BLOCKED") == (sense < 0) for p in plan.points)
    assert not any("blade order was not checked" in str(w.message) for w in caught)
    # PFS-2200: 26.127 writes the edge-slot rows as integers, 0 or the trailing-edge group's
    # number (CMP-26127_2026-11-06_marking.yaml), so a nonzero tag reads as a flagged edge.
    del MeshReadError
    assert trailing_edge_midpoints(mesh)
