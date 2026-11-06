"""P0560-HUBQ: quality warned with its numbers and the mesh written, not refused.

Usage:
    pyfs-workspace geometry repitch sector.obj --morphing morphing.toml --out pitched.obj
    pyfs-workspace geometry hub-rings sector.obj --morphing morphing.toml --out rings.obj

Mesh quality (folded, reversed or turned cells, a node off the hub) is warned with its numbers
and the mesh is written; only broken input and broken invariants are refused.
"""

import re
import tomllib
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace._refine._obj import ObjMesh, obj_text, read_obj
from tests.tier1_offline.test_p0560_morph import (
    build,
    control,
    invoke,
    record,
)

# PFS-2197: quality is warned with its numbers and the mesh is written.


def _thin_ring_sector(folder: Path) -> Path:
    """An O-grid hub of two thin rings hugging the root, so a 5 degree turn folds its cells."""
    theta = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    root = np.c_[0.3 * np.cos(theta), 0.12 * np.sin(theta), np.ones(16)]
    nodes = [root, root + [0, 0, 1], root + [0, 0, 2]]
    for scale in (1.02, 1.04):
        nodes.append(root * [scale, scale, 1])
    blade = [
        [k * 16 + j, k * 16 + (j + 1) % 16, (k + 1) * 16 + (j + 1) % 16, (k + 1) * 16 + j]
        for k in range(2)
        for j in range(16)
    ]
    rings = [0, 3, 4]
    hub = [
        [a * 16 + j, b * 16 + j, b * 16 + (j + 1) % 16, a * 16 + (j + 1) % 16]
        for a, b in zip(rings[:-1], rings[1:], strict=True)
        for j in range(16)
    ]
    path = folder / "thin.obj"
    path.write_text(obj_text(ObjMesh(np.vstack(nodes), {"Blade1": blade, "Spinner": hub})))
    (folder / "thin.toml").write_text(
        '[repitch]\nangle_deg = 5.0\nblades = ["Blade1"]\nhub = ["Spinner"]\n'
        "axis = { origin = [0.0, 0.0, 0.0], direction = [0.0, 0.0, 1.0] }\n"
    )
    return path


@pytest.mark.requirement("FR-3681")
def test_p0560_hubq_folded_and_reversed_ring_cells_are_warned_with_their_numbers_and_written(
    tmp_path,
):
    source = _thin_ring_sector(tmp_path)
    out = tmp_path / "folded.obj"
    with pytest.warns(PyflightstreamWarning) as caught:
        assert invoke("repitch", source, tmp_path / "thin.toml", out) == 0
    said = [str(w.message) for w in caught]
    folded = r"hub 'Spinner' has \d+ folded cell\(s\); the least scaled Jacobian is -?\d"
    assert any(re.search(folded, s) for s in said), said
    assert any(re.search(r"hub 'Spinner' has \d+ reversed cell", s) for s in said), said
    assert out.exists()
    report = record(out, "repitch")
    checks = report["checks"]
    assert checks["passed"] is False
    assert any("folded" in w for w in checks["warnings"])
    assert any("reversed" in w for w in checks["warnings"])
    assert report["hub"]["Spinner"]["reversed_cells"] >= 1
    assert report["hub"]["Spinner"]["output_quality"]["folded_cells"] >= 1


@pytest.mark.requirement("FR-3681")
def test_p0560_hubq_hub_rings_warns_a_folded_new_cell(tmp_path):
    """A node only new faces hold, reflected through a neighbour: its cells fold over. The arm
    refused; it now warns with the count and the least scaled Jacobian and lists the warning."""
    from pyflightstream.workspace import hub_rings

    source = build(tmp_path)
    mesh = read_obj(source)
    cfg = hub_rings.read_config(
        tomllib.loads(control(tmp_path, "[hub_rings]\nrings = 4\n").read_text()), mesh
    )
    result, surface = hub_rings.build_rings(mesh, cfg)
    added = {tuple(f) for f in result.added["Blade1"]}
    others = {
        v for fs in result.mesh.families.values() for f in fs if tuple(f) not in added for v in f
    }
    face = next(f for f in reversed(result.added["Blade1"]) if any(v not in others for v in f))
    k = next(k for k, v in enumerate(face) if v not in others)
    node, across = face[k], face[(k + 2) % len(face)]
    result.mesh.verts[node] = 2.0 * result.mesh.verts[across] - result.mesh.verts[node]
    with pytest.warns(PyflightstreamWarning, match=r"new hub cell\(s\) fold; the least scaled"):
        checks = hub_rings.verify_rings(result, surface, ["Spinner"])
    assert checks["new_cell_quality"]["folded_cells"] >= 1
    assert any("fold" in w for w in checks["warnings"])
