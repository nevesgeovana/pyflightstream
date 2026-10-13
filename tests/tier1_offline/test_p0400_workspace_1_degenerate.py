"""P0400-WSTHIN: the thin blade's rows, its blunt trailing edge and its operations.

0.40.0 lane workspace-1. Each test is the regression of one planning node and
fails on the code before its fix. The blade is the built oracle of
``test_p0340_thin_blade``: a cambered section whose mean surface is known.
"""

from __future__ import annotations

import numpy
import pytest

from pyflightstream.cases import RawMeshConditions, TrailingEdgeMarking
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._geometry import _plan_import_operations
from pyflightstream.script import Script
from pyflightstream.workspace._degenerate import CHORD_PANELS, derive_thin_blade
from pyflightstream.workspace.sidecars import inventory_sidecar, read_inventory, read_mesh_import
from tests.tier1_offline.test_p0340_thin_blade import (
    CHORD,
    RINGS,
    ROOT,
    SIDE_POINTS,
    TIP,
    _blade,
    _camber,
    _half_thickness,
    _read_obj,
    _stations,
    _write_obj,
)
from tests.tier1_offline.test_workflows import steady_case

pytestmark = pytest.mark.requirement("P0400-WSTHIN")


def _rows(result):
    return _read_obj(result.mesh).reshape(result.stations, CHORD_PANELS + 1, 3)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_p0400_wsthin_every_row_runs_from_the_leading_edge_whatever_the_face_order(tmp_path, seed):
    """P0400-WSTHIN (PFS-2099.001): shuffled faces leave rows[k, 0] at the leading edge."""
    vertices, faces = _blade()
    shuffled = [faces[i] for i in numpy.random.default_rng(seed).permutation(len(faces))]
    result = derive_thin_blade(
        _write_obj(tmp_path / "blade.obj", vertices, shuffled), root_offset=0.05
    )
    xi = _rows(result)[:, :, 0] / CHORD + 0.25
    assert numpy.abs(xi[:, 0]).max() <= 1e-9, xi[:, 0]
    assert numpy.abs(xi[:, -1] - 1.0).max() <= 1e-9, xi[:, -1]


#: The half thickness of the blunt trailing edge's base, a fraction of the chord.
BASE = 0.01


def _blunt_blade():
    """The oracle blade with an open trailing edge closed by a straight base."""
    x = _stations()
    inner = x[1:]
    half = _half_thickness(inner) + BASE * inner
    upper = numpy.column_stack([inner, _camber(inner) + half])
    lower = numpy.column_stack([inner, _camber(inner) - half])
    section = numpy.vstack([[0.0, 0.0], upper, lower[::-1]])
    n = len(section)
    vertices = [
        [(px - 0.25) * CHORD, py * CHORD, z]
        for z in numpy.linspace(ROOT, TIP, RINGS)
        for px, py in section
    ]
    faces = []
    for k in range(RINGS - 1):
        for j in range(n):
            a, b = k * n + j, k * n + (j + 1) % n
            faces += [[a, b, b + n], [a, b + n, a + n]]
    for k, z in ((0, ROOT), (RINGS - 1, TIP)):
        centre = len(vertices)
        vertices.append([*(section.mean(axis=0) - [0.25, 0.0]) * CHORD, z])
        faces += [[centre, k * n + (j + 1) % n, k * n + j] for j in range(n)]
    return numpy.asarray(vertices), faces


def test_p0400_wsthin_a_blunt_trailing_edge_ends_at_its_base_midpoint(tmp_path):
    """P0400-WSTHIN (PFS-2099.002): the sheet's trailing edge is the base's midpoint."""
    assert len(_stations()) == SIDE_POINTS + 1
    vertices, faces = _blunt_blade()
    result = derive_thin_blade(
        _write_obj(tmp_path / "blunt.obj", vertices, faces), root_offset=0.05
    )
    rows = _rows(result)
    trailing = rows[:, -1]
    assert numpy.abs(trailing[:, 0] - 0.75 * CHORD).max() <= 1e-9
    assert numpy.abs(trailing[:, 1] - CHORD * _camber(numpy.array(1.0))).max() <= 1e-9
    leading = rows[:, 0]
    assert numpy.abs(leading[:, 0] + 0.25 * CHORD).max() <= 1e-9


def test_p0400_wsthin_a_sharp_trailing_edge_is_not_read_as_a_base(tmp_path):
    """P0400-WSTHIN (PFS-2099.002): the control, the closed oracle keeps its own edges."""
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "sharp.obj", vertices, faces)
    rows = _rows(derive_thin_blade(source, root_offset=0.05))
    xi = rows[:, :, 0] / CHORD + 0.25
    assert numpy.abs(xi[:, 0]).max() <= 1e-9 and numpy.abs(xi[:, -1] - 1.0).max() <= 1e-9


def _two_bodies(tmp_path):
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "rotor.obj", vertices, faces, group="Blade")
    spinner = [[0.0, 0.0, 0.0], [0.05, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 0.05]]
    first = len(vertices) + 1
    lines = ["o Spinner", *(f"v {x!r} {y!r} {z!r}" for x, y, z in spinner)]
    lines += [
        f"f {first + a} {first + b} {first + c}"
        for a, b, c in ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))
    ]
    with source.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    inventory_sidecar(source).write_text(
        'boundaries = ["Blade", "Spinner"]\n\n[import]\nunits = "meter"\n\n'
        '[[import.operations]]\nop = "rename"\nsurface = "Spinner"\nto = "Hub"\n\n'
        '[[import.operations]]\nop = "mirror"\nsurface = "Hub"\nplane = "XZ"\n\n'
        '[[import.operations]]\nop = "rename"\nsurface = "Blade"\nto = "Blade1"\n\n'
        '[[import.operations]]\nop = "mirror"\nsurface = "Blade1"\nplane = "XZ"\n\n'
        '[[import.operations]]\nop = "translate"\nvector = [0, 0, 1]\n',
        encoding="utf-8",
    )
    return source


def test_p0400_wsthin_a_thin_blade_keeps_only_the_operations_on_itself(tmp_path):
    """P0400-WSTHIN (PFS-2099.003, PFS-2099.013): every carried operation names a surface
    the thin blade holds at its step, as the plan resolves them, and the rest are named."""
    result = derive_thin_blade(_two_bodies(tmp_path), root_offset=0.05, boundary="Blade")
    carried = read_mesh_import(result.sidecar)
    assert carried is not None
    names = list(read_inventory(result.sidecar))
    for operation in carried.operations:
        assert operation.surface == "all" or operation.surface in names, (operation, names)
        if operation.op == "rename":
            names = [operation.to if name == operation.surface else name for name in names]
    assert [(op.op, op.surface) for op in carried.operations] == [
        ("rename", "Blade"),
        ("mirror", "Blade1"),
        ("translate", "all"),
    ]
    case = steady_case().model_copy(
        update={
            "geometry": str(result.mesh),
            "mesh_import": carried,
            "inventory": tuple(read_inventory(result.sidecar)),
            "inventory_source": "sidecar",
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect")
            ),
        }
    )
    steps, final_names = _plan_import_operations(case, Script("26.124"), str(result.sidecar))
    assert len(steps) == 3 and final_names == ("Blade1",)
    script = Script("26.124")
    build_script(case, script)
    assert "START_SOLVER" in script.render() and "Spinner" not in script.render()
    text = result.sidecar.read_text(encoding="utf-8")
    assert "operation 1 (rename of 'Spinner')" in text
    assert "operation 2 (mirror of 'Hub')" in text
