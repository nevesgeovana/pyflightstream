"""P0540-MARK: the marking pass on 26.100, by one vertex file per rim (FR-3470, FR-3471)."""

from __future__ import annotations

import pytest

from pyflightstream._errors import NotApplicableWarning

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


def _capped_strip(tmp_path, tables):
    """The same panel with its one-cell base as a family of its own: groups wing and cap."""
    from pyflightstream.workspace.sidecars import write_inventory

    mesh = _blunt_strip(tmp_path, "")
    lines = mesh.read_text().splitlines()
    faces = [line for line in lines if line.startswith("f ")]
    head = [line for line in lines if line.startswith("v ")]
    mesh.write_text(
        "\n".join([*head, "g wing", *faces[: 2 * NY], "g cap", *faces[2 * NY :]]) + "\n"
    )
    sidecar = mesh.with_name(mesh.name + ".boundaries.toml")
    sidecar.unlink()
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write('\nfs_build = "26.100"\n[import]\nunits = "METER"\n' + tables)
    return mesh


def _vertex_rows(text):
    count, unit, *rows = text.split()
    assert unit == "METER" and int(count) == len(rows)
    return [tuple(float(v) for v in row.split(",")[1:]) for row in rows]


AUTO_AND_FILE = (
    '[base_regions.wing]\ntrailing_edges = {file = "top.te.txt", type = "STANDARD"}\n'
    '[base_regions.cap]\ntrailing_edges = "auto"\n'
)


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_an_auto_rim_follows_the_base_it_names(tmp_path):
    """REL-K-001: SET_BASE_REGION_TRAILING_EDGES <n> names base n, so base n exists first."""
    from pyflightstream.workspace import plan_mark_boundaries

    lines = plan_mark_boundaries(_capped_strip(tmp_path, AUTO_AND_FILE)).script.splitlines()
    creates = [i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_BASE_REGION")]
    autos = [i for i, line in enumerate(lines) if line.startswith("SET_BASE_REGION_TRAILING_EDGES")]
    imports = [i for i, line in enumerate(lines) if line == "TRAILING_EDGES_IMPORT"]
    assert lines[autos[0]] == "SET_BASE_REGION_TRAILING_EDGES 2"
    assert len(creates) == 2 and len(autos) == 1 and imports
    # Nothing that marks an edge stands between two creates, the order measured on this build.
    assert max(imports) < min(creates) and max(creates) < min(autos)


def _read_back_of(plan, monkeypatch, groups):
    """The read-back of ``plan`` on a save that states ``groups`` and the declared bases."""
    from pyflightstream.workspace import _mark_boundaries as marking

    bases = tuple(
        (region.family, region.cp, {"USER": 0, "EMPIRICAL": 1, "AXISYMMETRIC": 2}[region.model])
        for region in plan.declarations.base_regions
    )
    monkeypatch.setattr(marking, "boundary_names", lambda _: plan.names)
    monkeypatch.setattr(marking, "saved_wake_edge_verdict", lambda *_: None)
    monkeypatch.setattr(marking, "saved_trailing_edge_groups", lambda _: groups)
    monkeypatch.setattr(marking, "saved_termination_count", lambda _: 0)
    monkeypatch.setattr(marking, "saved_base_regions", lambda _: bases)
    monkeypatch.setattr(marking, "saved_cross_edges", lambda *_: {})
    return marking._read_back(plan, plan.work / "x.fsm")


def _wedge(tmp_path):
    """A blunt base strip closing to a point: its two rims share the vertex at the tip."""
    from pyflightstream.workspace.sidecars import write_inventory

    top = [(1.0, j / NY, THICK) for j in range(NY)]
    bottom = [(1.0, j / NY, -THICK) for j in range(NY)]
    tip = (1.0, 1.0, 0.0)
    vertices = [*top, *bottom, tip]
    faces = [[j + 1, NY + j + 1, NY + j + 2, j + 2] for j in range(NY - 1)]
    faces.append([NY, 2 * NY, 2 * NY + 1])
    mesh = tmp_path / "wedge.obj"
    mesh.write_text(
        "".join(f"v {x} {y} {z}\n" for x, y, z in vertices)
        + "g wing\n"
        + "".join("f " + " ".join(map(str, face)) + "\n" for face in faces)
    )
    rows = []
    for side in (top, bottom):
        for a, b in zip([*side, tip], [*side, tip][1:], strict=False):
            rows.append(",".join(repr((p + q) / 2) for p, q in zip(a, b, strict=True)))
    (tmp_path / "rim.te.txt").write_text("METER\n" + "\n".join(rows) + "\n")
    with write_inventory(mesh).open("a") as stream:
        stream.write('\nfs_build = "26.100"\n[import]\nunits = "METER"\n')
        stream.write('[trailing_edges.te]\nfile = "rim.te.txt"\ntype = "STANDARD"\n')
    return mesh, top, bottom, tip


def _loop(tmp_path):
    """One rim closed in a loop round a square cap of two triangles, with its diagonal inside."""
    from pyflightstream.workspace.sidecars import write_inventory

    corners = [(1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (1.0, 1.0, 1.0), (1.0, 0.0, 1.0)]
    mesh = tmp_path / "cap.obj"
    mesh.write_text(
        "".join(f"v {x} {y} {z}\n" for x, y, z in corners) + "g cap\nf 1 2 3\nf 1 3 4\n"
    )
    rows = [
        ",".join(repr((p + q) / 2) for p, q in zip(a, b, strict=True))
        for a, b in zip(corners, [*corners[1:], corners[0]], strict=True)
    ]
    (tmp_path / "rim.te.txt").write_text("METER\n" + "\n".join(rows) + "\n")
    with write_inventory(mesh).open("a") as stream:
        stream.write('\nfs_build = "26.100"\n[import]\nunits = "METER"\n')
        stream.write('[trailing_edges.te]\nfile = "rim.te.txt"\ntype = "STANDARD"\n')
    return mesh, corners


def _vertex_sets(plan):
    return [set(_vertex_rows(body.decode())) for body in plan.pending.values()]


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_rims_that_touch_at_a_vertex_do_not_share_a_file_across_a_rung(tmp_path):
    """REL-K-003: the solver marks every mesh edge a file names both ends of (the joint trial)."""
    from pyflightstream.workspace import plan_mark_boundaries

    mesh, top, bottom, tip = _wedge(tmp_path)
    plan = plan_mark_boundaries(mesh)
    files = _vertex_sets(plan)
    for upper, lower in zip(top, bottom, strict=True):
        assert not [names for names in files if {upper, lower} <= names], (upper, lower)
    for side in (top, bottom):
        for a, b in zip([*side, tip], [*side, tip][1:], strict=False):
            assert [names for names in files if {a, b} <= names], (a, b)
    # The rungs stay known to the read-back, which proves that none was marked.
    (entry,) = plan.sets
    assert entry["rim_vertices"] == tuple(len(names) for names in files)
    rungs = {(1.0, j / NY, 0.0) for j in range(NY)}
    assert rungs <= {tuple(point) for point in entry["cross_m"]}


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_a_rim_closed_in_a_loop_names_no_chord_in_one_file(tmp_path):
    """REL-K-003: a closed rim's file would mark the diagonal between two of its own vertices."""
    from pyflightstream.workspace import plan_mark_boundaries

    mesh, corners = _loop(tmp_path)
    plan = plan_mark_boundaries(mesh)
    files = _vertex_sets(plan)
    assert not [names for names in files if {corners[0], corners[2]} <= names]
    for a, b in zip(corners, [*corners[1:], corners[0]], strict=True):
        assert [names for names in files if {a, b} <= names], (a, b)
    assert plan.sets[0]["cross_m"] == ((1.0, 0.5, 0.5),)


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_an_open_rim_stays_one_file(tmp_path):
    """REL-K-003 control: a rim with no edge between its own vertices is not split."""
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _blunt_strip(tmp_path, '[trailing_edges.te]\nfile = "top.te.txt"\ntype = "STANDARD"\n')
    plan = plan_mark_boundaries(mesh)
    assert plan.sets[0]["rim_vertices"] == (NY + 1,) and len(plan.pending) == 1


TWO_ENTRIES = (
    '[trailing_edges.blunt]\nfile = "rim.te.txt"\ntype = "STANDARD"\n'
    '[trailing_edges.sharp]\nfile = "top.te.txt"\ntype = "STANDARD"\n'
)


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_a_skipped_file_is_no_group_of_the_read_back(tmp_path, monkeypatch):
    """REL-K-002: an entry warned and skipped marks nothing, so its pass still reads back."""
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _blunt_strip(
        tmp_path, '[trailing_edges.te]\nfile = "top.te.txt"\ntype = "VORTEX_SHEDDING"\n'
    )
    with pytest.warns(NotApplicableWarning):
        plan = plan_mark_boundaries(mesh)
    record = _read_back_of(plan, monkeypatch, ())
    assert [entry["group"] for entry in record["entries"]] == [None]


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_each_entry_reads_its_own_group_after_a_two_rim_entry(tmp_path, monkeypatch):
    """REL-K-002: an entry of two rims leaves two groups, so the next entry is the third."""
    from pyflightstream.workspace import plan_mark_boundaries

    plan = plan_mark_boundaries(_blunt_strip(tmp_path, TWO_ENTRIES))
    record = _read_back_of(plan, monkeypatch, ("blunt_a", "blunt_b", "sharp"))
    assert {entry["label"]: entry["group"] for entry in record["entries"]} == {
        "blunt": "blunt_a",
        "sharp": "sharp",
    }


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_the_console_names_each_base_rim_group(tmp_path, monkeypatch, capsys):
    """REL-K-002: the groups follow the script's order, so the console names the right one."""
    from pyflightstream.run._cli_geometry import _print_marking_readback
    from pyflightstream.workspace import plan_mark_boundaries

    tables = (
        '[trailing_edges.te]\nfile = "top.te.txt"\ntype = "VORTEX_SHEDDING"\n'
        '[base_regions.cap]\ntrailing_edges = "auto"\n'
        '[base_regions.wing]\ntrailing_edges = {file = "rim.te.txt", type = "STANDARD"}\n'
    )
    with pytest.warns(NotApplicableWarning):
        plan = plan_mark_boundaries(_capped_strip(tmp_path, tables))
    # The script imports the two rims of wing, then marks the auto rim of cap.
    record = _read_back_of(plan, monkeypatch, ("wing", "wing", "cap"))
    _print_marking_readback(plan, record)
    printed = capsys.readouterr().out
    assert "base region cap: model EMPIRICAL, Cp -0.2, rim group cap" in printed
    assert "base region wing: model EMPIRICAL, Cp -0.2, rim group wing" in printed
    assert "entry te: type VORTEX_SHEDDING, group none" in printed


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
    assert plan.awaiting_evidence == ()


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_the_vertex_import_is_gated_on_evidence_and_the_probes_opened_it(tmp_path):
    from pyflightstream.commands import CommandRegistry, Status
    from pyflightstream.versions import resolve
    from pyflightstream.workspace._mark_boundaries import EVIDENCE_GATED

    assert "TRAILING_EDGES_IMPORT" in EVIDENCE_GATED
    command = CommandRegistry.load().commands["TRAILING_EDGES_IMPORT"]
    assert command.status_in(resolve("26.100")).status is Status.VERIFIED


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_an_empirical_base_is_stated_once_by_its_create(tmp_path):
    """26.100 stops the script at SET_BASE_REGION_CP <n> EMPIRICAL <cp>, measured on a wheel."""
    from pyflightstream.workspace import plan_mark_boundaries

    empirical = BLUNT.replace("USER", "EMPIRICAL")
    script = plan_mark_boundaries(_blunt_strip(tmp_path, tables=empirical)).script
    assert "CREATE_NEW_BASE_REGION" in script
    assert "SET_BASE_REGION_CP" not in script
    # A custom model still takes the form the probe verified on 26.100.
    (tmp_path / "user").mkdir()
    custom = plan_mark_boundaries(_blunt_strip(tmp_path / "user")).script
    assert "SET_BASE_REGION_CP 1 CUSTOM -0.2" in custom
    (tmp_path / "custom").mkdir()
    stated = plan_mark_boundaries(
        _blunt_strip(tmp_path / "custom", tables=BLUNT.replace("USER", "CUSTOM"))
    ).script
    assert "SET_BASE_REGION_CP 1 CUSTOM -0.2" in stated


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_an_axisymmetric_base_is_stated_once_by_its_create(tmp_path):
    """REL-K-004: only <n> CUSTOM <cp> ran on 26.100; <n> <model> <cp> of EMPIRICAL stopped it."""
    from pyflightstream.workspace import plan_mark_boundaries

    tables = BLUNT.replace("USER", "AXISYMMETRIC")
    script = plan_mark_boundaries(_blunt_strip(tmp_path, tables=tables)).script
    assert "CREATE_NEW_BASE_REGION 1 AXISYMMETRIC -0.2" in script
    assert "SET_BASE_REGION_CP" not in script


@pytest.mark.requirement("FR-3470")
def test_p0540_26100_every_rim_is_imported_before_the_first_base(tmp_path):
    """A rim import between two bases leaves only the last base saved, measured on 26.100."""
    from pyflightstream.workspace import plan_mark_boundaries

    lines = plan_mark_boundaries(_blunt_strip(tmp_path)).script.splitlines()
    imports = [i for i, line in enumerate(lines) if line == "TRAILING_EDGES_IMPORT"]
    bases = [i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_BASE_REGION")]
    assert imports and bases and max(imports) < min(bases)


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
def test_p0540_26100_a_rim_edge_within_tolerance_of_a_cross_edge_is_no_cross_edge(
    tmp_path, monkeypatch
):
    """REL-K-007: a tolerance wider than half a cell must not read a rim edge as a cross edge."""
    import pyflightstream._fsm as fsm
    from pyflightstream.workspace import plan_mark_boundaries
    from pyflightstream.workspace._mark_boundaries import BoundaryMarkingError, _cross_edges

    plan = plan_mark_boundaries(_blunt_strip(tmp_path))
    plan.sets[0]["tolerance"] = 0.2  # the mid-point of a rung is 0.174 from a rim edge's
    marked = list(plan.sets[0]["points_m"])
    monkeypatch.setattr(fsm, "saved_mesh_coordinate_unit", lambda _: "METER")
    monkeypatch.setattr(fsm, "trailing_edge_midpoints", lambda _: tuple(marked))
    assert _cross_edges(plan, tmp_path / "x.fsm") == {"wing": 0}
    # A cross edge really marked is still found, and only that one counts.
    marked.append(plan.sets[0]["cross_m"][0])
    with pytest.raises(BoundaryMarkingError, match="wing: 1"):
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
