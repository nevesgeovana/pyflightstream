"""P0540-MARK: the marking preview says what it is doing at each stage (FR-3478)."""

from __future__ import annotations

import pytest

OBJ = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\ng wing\nf 1 2 3 4\n"


def _mesh(tmp_path, build="26.125"):
    from pyflightstream.workspace.sidecars import write_inventory

    mesh = tmp_path / "wing.obj"
    mesh.write_text(OBJ)
    (tmp_path / "edge.te.txt").write_text("METER\n0.5,0.0,0.0\n")
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write(
            f'\nfs_build = "{build}"\n[import]\nunits = "METER"\n'
            '[trailing_edges.te]\nfile = "edge.te.txt"\ntype = "STANDARD"\n'
        )
    return mesh


@pytest.mark.requirement("FR-3478")
@pytest.mark.parametrize("build", ["26.100", "26.125"])
def test_p0540_the_preview_reports_each_stage_in_order(tmp_path, build):
    from pyflightstream.workspace import plan_mark_boundaries

    lines: list[str] = []
    mesh = _mesh(tmp_path, build)
    plan = plan_mark_boundaries(mesh, progress=lines.append)
    stages = [
        "reading wing.obj and its sidecar",
        "te: matching the points file to mesh edges",
        "te: placing 1 points through the import operations",
        "base regions",
        "wake-termination nodes and merges",
        "rendering the marking script",
    ]
    positions = [lines.index(stage) for stage in stages]
    assert positions == sorted(positions)
    # The progress route changes nothing about the plan itself.
    assert plan.script == plan_mark_boundaries(mesh).script


@pytest.mark.requirement("FR-3478")
def test_p0540_the_command_prints_the_stages_through_the_console_route(tmp_path, capsys):
    from pyflightstream.workspace.cli import main

    mesh = _mesh(tmp_path)
    assert main(["geometry", "mark-boundaries", str(mesh)]) == 0
    captured = capsys.readouterr()
    assert "[mark-boundaries " in captured.err
    assert "rendering the marking script" in captured.err
    assert "[mark-boundaries " not in captured.out


def _reference_placed_points(points, mesh, spec, tolerance):
    """The loop the preview used before it was indexed: every point against every edge."""
    import numpy as np

    from pyflightstream.workspace import _mark_rims as marking

    edges = marking._obj_edges(mesh, spec.units)
    placed: list[tuple[float, ...]] = []
    for point in points:
        families = {
            name for name, xyz in edges if np.linalg.norm(np.asarray(xyz) - point) <= tolerance
        }
        for family in sorted(families):
            copies = [np.asarray(point, dtype=float)]
            for operation in spec.operations:
                if operation.surface not in ("all", family):
                    continue
                if operation.op == "rename":
                    family = operation.to
                else:
                    copies = marking._move_copies(copies, operation, spec.units)
            placed.extend(tuple(float(v) for v in xyz) for xyz in copies)
    return tuple(dict.fromkeys(placed))


@pytest.mark.requirement("FR-3478")
def test_p0540_the_indexed_placement_equals_the_every_point_against_every_edge_loop(tmp_path):
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace import _mark_rims as marking
    from pyflightstream.workspace.sidecars import read_mesh_import, write_inventory

    n = 6
    vertices = [f"v {i / n!r} {j / n!r} 0.0" for j in range(n + 1) for i in range(n + 1)]
    faces = [
        "f " + " ".join(str(k) for k in (a, a + 1, a + n + 2, a + n + 1))
        for j in range(n)
        for a in [j * (n + 1) + i + 1 for i in range(n)]
    ]
    mesh = tmp_path / "wing.obj"
    mesh.write_text("\n".join([*vertices, "g wing", *faces[:18], "g flap", *faces[18:]]) + "\n")
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write(
            '\nfs_build = "26.125"\n[import]\nunits = "METER"\n'
            '[[import.operations]]\nop = "scale"\nsurface = "wing"\nfactors = [2, 1, 1]\n'
            '[[import.operations]]\nop = "mirror"\nsurface = "flap"\nplane = "XZ"\n'
            '[[import.operations]]\nop = "translate"\nvector = [0.5, 0, 0]\nsurface = "flap"\n'
            "[trailing_edges]\nnone = true\n"
        )
    spec = read_mesh_import(sidecar)
    # Mid-points on the boundary between the two groups and on the outer edge.
    points = [((i + 0.5) / n, 3 / n, 0.0) for i in range(n)] + [(1.0, 0.5 / n, 0.0)]
    with pytest.raises(InputArtifactError, match="not on an OBJ polygon edge"):
        marking._placed_points([(0.123, 0.456, 0.7)], mesh, spec, 1e-4)
    placed = marking._placed_points(points, mesh, spec, 1e-4)
    assert placed == _reference_placed_points(points, mesh, spec, 1e-4)
    assert len(placed) > len(points)
