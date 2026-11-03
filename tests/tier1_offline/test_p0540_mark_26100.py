"""P0540-MARK: the marking pass on 26.100, by one vertex file per rim (FR-3470, FR-3471)."""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError, NotApplicableWarning

NY = 3
THICK = 0.05
BLUNT = (
    '[base_regions.wing]\nmodel = "USER"\ncp = -0.2\n'
    'trailing_edges = {file = "rim.te.txt", type = "STANDARD"}\n'
)


def _points(*heights):
    rows = "".join(f"1.0,{(j + 0.5) / NY},{z}\n" for z in heights for j in range(NY))
    return "METER\n" + rows


def _blunt_strip(tmp_path, tables=BLUNT):
    """A wing panel with a blunt trailing edge: a top skin, a bottom skin and a one-cell base."""
    from pyflightstream.workspace.sidecars import write_inventory

    vertices = []
    for z in (THICK, -THICK):
        for x in (0.0, 1.0):
            vertices += [(x, j / NY, z) for j in range(NY + 1)]
    index = {}
    for number, (x, y, z) in enumerate(vertices, start=1):
        index[(x, round(y * NY), z)] = number
    faces = []
    for z, flip in ((THICK, False), (-THICK, True)):
        for j in range(NY):
            quad = [(0.0, j, z), (1.0, j, z), (1.0, j + 1, z), (0.0, j + 1, z)]
            faces.append([index[key] for key in (quad[::-1] if flip else quad)])
    for j in range(NY):
        quad = [(1.0, j, THICK), (1.0, j, -THICK), (1.0, j + 1, -THICK), (1.0, j + 1, THICK)]
        faces.append([index[key] for key in quad])
    mesh = tmp_path / "panel.obj"
    mesh.write_text(
        "".join(f"v {x} {y} {z}\n" for x, y, z in vertices)
        + "g wing\n"
        + "".join("f " + " ".join(map(str, face)) + "\n" for face in faces)
    )
    (tmp_path / "rim.te.txt").write_text(_points(THICK, -THICK))
    (tmp_path / "top.te.txt").write_text(_points(THICK))
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write('\nfs_build = "26.100"\n[import]\nunits = "METER"\n' + tables)
    return mesh


def _vertex_rows(text):
    count, unit, *rows = text.split()
    assert unit == "METER" and int(count) == len(rows)
    return [tuple(float(v) for v in row.split(",")[1:]) for row in rows]


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_marks_each_rim_from_its_own_vertex_file(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    plan = plan_mark_boundaries(_blunt_strip(tmp_path))
    imports = [line for line in plan.script.splitlines() if line.startswith("TRAILING_EDGES")]
    assert len(imports) == 2 and all(line == "TRAILING_EDGES_IMPORT" for line in imports)
    assert "IMPORT_WAKE_EDGES_FROM_FILE" not in plan.script
    assert len(plan.pending) == 2
    rims = [_vertex_rows(body.decode()) for body in plan.pending.values()]
    heights = sorted({z for rows in rims for _, _, z in rows})
    assert heights == [-THICK, THICK]
    for rows in rims:
        assert len(rows) == NY + 1 and len({z for _, _, z in rows}) == 1
    # The edges between the rims are known at plan time, and no file names one.
    (entry,) = plan.sets
    assert len(entry["cross_m"]) >= NY + 1
    assert all(point[0] == 1.0 and abs(point[2]) < THICK for point in entry["cross_m"])
    assert entry["rim_vertices"] == (NY + 1, NY + 1)
    assert "TRAILING_EDGES_IMPORT" in plan.awaiting_evidence


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_apply_is_refused_by_the_evidence_gate_until_probed(tmp_path):
    from pyflightstream.workspace import apply_mark_boundaries, plan_mark_boundaries

    plan = plan_mark_boundaries(_blunt_strip(tmp_path))
    with pytest.raises(InputArtifactError, match="awaiting_evidence: .*TRAILING_EDGES_IMPORT"):
        apply_mark_boundaries(plan, runner=lambda *_: pytest.fail("the gate ran the solver"))
    assert not plan.work.exists()


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_readback_records_and_refuses_cross_edges(tmp_path, monkeypatch):
    import pyflightstream._fsm as fsm
    from pyflightstream.workspace import plan_mark_boundaries
    from pyflightstream.workspace._mark_boundaries import BoundaryMarkingError, _cross_edges

    plan = plan_mark_boundaries(_blunt_strip(tmp_path))
    marked = list(plan.sets[0]["points_m"])
    monkeypatch.setattr(fsm, "saved_mesh_coordinate_unit", lambda _: "METER")
    monkeypatch.setattr(fsm, "trailing_edge_midpoints", lambda _: tuple(marked))
    assert _cross_edges(plan, tmp_path / "x.fsm") == {"wing": 0}
    marked.append(plan.sets[0]["cross_m"][0])
    with pytest.raises(BoundaryMarkingError, match="join two rims of one entry"):
        _cross_edges(plan, tmp_path / "x.fsm")


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_skips_a_file_of_another_edge_type_with_a_warning(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _blunt_strip(
        tmp_path, '[trailing_edges.te]\nfile = "top.te.txt"\ntype = "VORTEX_SHEDDING"\n'
    )
    with pytest.warns(NotApplicableWarning, match="top.te.txt.*takes no edge type"):
        plan = plan_mark_boundaries(mesh)
    assert "TRAILING_EDGES_IMPORT" not in plan.script
    assert plan.sets == []


@pytest.mark.requirement("FR-3471")
def test_p0540_26100_direct_route_warns_names_the_saved_route_and_writes_nothing(
    tmp_path, monkeypatch, capsys
):
    from pyflightstream.script import ScriptOrderError, _marking
    from pyflightstream.workspace import plan_mark_boundaries
    from pyflightstream.workspace.cli import main

    mesh = _blunt_strip(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(_marking, "MARKING_ROUTE_26100", "direct")
    with (
        pytest.warns(NotApplicableWarning, match="geometry sector-to-wheel"),
        pytest.raises(ScriptOrderError, match="nothing was written"),
    ):
        plan_mark_boundaries(mesh)
    with pytest.warns(NotApplicableWarning):
        code = main(["geometry", "mark-boundaries", str(mesh), "--apply"])
    assert code != 0
    assert "sector-to-wheel" in capsys.readouterr().err
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.requirement("FR-3471")
def test_p0540_26100_solver_route_is_the_default_constant():
    from pyflightstream.script import _marking

    assert _marking.MARKING_ROUTE_26100 == "solver"


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_explicit_termination_nodes_are_warned_and_skipped(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    (tmp_path / "nodes.txt").write_text("METER\n1.0,0.0,0.05\n")
    mesh = _blunt_strip(
        tmp_path,
        '[trailing_edges.te]\nfile = "top.te.txt"\ntype = "STANDARD"\n'
        'wake_termination_nodes = "nodes.txt"\n',
    )
    with pytest.warns(NotApplicableWarning, match="MARK_WAKE_TERMINATION_NODES"):
        plan = plan_mark_boundaries(mesh)
    assert "SELECT_MESH_NODE" not in plan.script
    assert plan.script.count("TRAILING_EDGES_IMPORT") == 1


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_probe_specification_imports_one_rim_per_file_and_has_its_controls(tmp_path):
    from pyflightstream.qa.specs import PROBE_SPECS
    from pyflightstream.script import Script

    spec = PROBE_SPECS["TRAILING_EDGES_IMPORT"]
    script = Script("26.100")
    spec.prelude(script, tmp_path)
    spec.build_target(script, tmp_path)
    spec.epilogue(script, tmp_path)
    lines = script.render().splitlines()
    assert lines.count("TRAILING_EDGES_IMPORT") == 2
    assert [name for name in ("before.fsm", "control.fsm", "split.fsm") if name in script.render()]
    for key, rows in (("a", 2), ("b", 2), ("joint", 4)):
        text = (tmp_path / f"rim_{key}.txt").read_text().split()
        assert text[:2] == [str(rows), "METER"] and len(text) == 2 + rows
    for name in ("single", "joint", "split_ws"):
        assert (tmp_path / f"trial_{name}.txt").is_file()
    assert spec.assert_effect is not None
    # No saved state was produced here, so the instrument reports nothing rather than a verdict.
    assert spec.assert_effect(_Bare(tmp_path)) is None


class _Bare:
    def __init__(self, workdir):
        self.workdir = workdir


@pytest.mark.requirement("FR-3470")
@pytest.mark.parametrize(
    "command",
    [
        "TRAILING_EDGES_IMPORT",
        "CREATE_NEW_BASE_REGION",
        "SET_BASE_REGION_CP",
        "SET_BASE_REGION_TRAILING_EDGES",
        "SURFACE_COMBINE",
        "SURFACE_RENAME",
    ],
)
def test_p0540_26100_marking_probes_build_a_validated_script(tmp_path, command):
    from pyflightstream.qa.probes import generate_probe_script
    from pyflightstream.qa.specs import PROBE_SPECS

    script = generate_probe_script(
        PROBE_SPECS[command], "26.100", tmp_path, fsm=tmp_path / "dummy.fsm"
    )
    assert f"PYFS_PROBE_BEGIN_{command}" in script.render()
