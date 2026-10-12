"""P0400-ROTORMESH (PFS-2135.045): compare_rotor_meshes.py reads the mesh block through the package.

The script carried a second positional reader that trusted the element count
the block states first, which the package documents as wrong on a campaign
geometry. With that count off, its per-face loop read no array and the load
ended in an IndexError. It now reads through ``pyflightstream._fsm``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pyflightstream._fsm import MESH_MARKER, surface_mesh

REPO = Path(__file__).resolve().parents[2]
WING = REPO / "tests" / "tier3_licensed" / "inputs" / "geometries" / "10_WING.fsm"


def _load():
    spec = importlib.util.spec_from_file_location(
        "compare_rotor_meshes_p0400", REPO / "scripts" / "compare_rotor_meshes.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0400_rotormesh_a_wrong_stated_count_is_not_trusted(tmp_path: Path) -> None:
    """P0400-ROTORMESH: the stated count off by 64 still reads every face of every surface."""
    lines = WING.read_bytes().split(b"\n")
    at = next(i for i, line in enumerate(lines) if line.strip() == MESH_MARKER.encode())
    stated = lines[at + 1].strip()
    lines[at + 1] = lines[at + 1].replace(stated, str(int(stated) + 64).encode())
    wrong = tmp_path / "wing_wrong_count.fsm"
    wrong.write_bytes(b"\n".join(lines))
    vertices, faces = surface_mesh(WING)

    names, triangle, of_face, xyz = _load().load(wrong)
    assert len(of_face) == len(faces) == len(triangle[0])
    assert len(xyz[0]) == len(vertices)
    assert set(of_face) <= set(range(1, len(names) + 1))
    assert [tuple(t - 1 for t in corner) for corner in zip(*triangle, strict=True)] == list(faces)
