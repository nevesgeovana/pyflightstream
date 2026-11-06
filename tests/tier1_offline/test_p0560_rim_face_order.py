"""R1-MARK-S4: on 26.127 a base region's rim is written last face first.

Licensed probes of a six-blade wheel on 2026-11-06 (the 0.56.0 wheel-routes receipt): FlightStream
26.127 kept 742 of the 768 rim edges the wheel's files named when each rim was written in the
file's order, and 768 of 768 when written in descending order of the face outside the base; the
same files in the file's order kept 768 on 26.125. An edge was dropped only where it met an edge
already marked whose face outside the base came earlier in the mesh.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.workspace import plan_mark_boundaries

CELLS = 4


def _wing_with_cap(folder: Path, build: str) -> Path:
    """A strip ``wing`` whose rim at x = 0 is shared with a base ``cap``; the wing face of
    rim edge i is the 2i-th face, so the faces outside the base rise along the rim. The rim
    file lists the edges in that rising order."""
    from pyflightstream.workspace.sidecars import write_inventory

    rim = [(0.0, float(i), 0.0) for i in range(CELLS + 1)]
    upstream = [(-1.0, float(i), 0.0) for i in range(CELLS + 1)]
    cap = [(0.0, float(i), -0.1) for i in range(CELLS + 1)]
    vertices = rim + upstream + cap
    r = lambda i: i + 1  # noqa: E731
    u = lambda i: CELLS + 1 + i + 1  # noqa: E731
    c = lambda i: 2 * (CELLS + 1) + i + 1  # noqa: E731
    wing = []
    for i in range(CELLS):
        wing += [f"f {u(i)} {r(i)} {r(i + 1)}", f"f {u(i)} {r(i + 1)} {u(i + 1)}"]
    base = []
    for i in range(CELLS):
        base += [f"f {r(i + 1)} {r(i)} {c(i)}", f"f {r(i + 1)} {c(i)} {c(i + 1)}"]
    mesh = folder / "capped.obj"
    mesh.write_text(
        "\n".join([*(f"v {x} {y} {z}" for x, y, z in vertices), "g wing", *wing, "g cap", *base])
        + "\n",
        encoding="utf-8",
    )
    rows = [f"0.0,{i + 0.5},0.0" for i in range(CELLS)]
    (folder / "cap.te.txt").write_text("\n".join(["METER", *rows]) + "\n", encoding="utf-8")
    sidecar = write_inventory(mesh)
    with sidecar.open("a", encoding="utf-8") as stream:
        stream.write(
            f'\nfs_build = "{build}"\n[import]\nunits = "METER"\n'
            '[base_regions.cap]\ntrailing_edges = {file = "cap.te.txt", type = "STANDARD"}\n'
        )
    return mesh


def _written_rim(plan) -> list[float]:
    """The y of every mid-point the rim's node files list, in the order written."""
    names = [name for name in plan.pending if Path(name).stem.startswith("edges-")]
    assert names, plan.pending.keys()
    return [
        float(row.split(",")[1])
        for name in sorted(names)
        for row in plan.pending[name].decode("utf-8").splitlines()[2:]
        if row.strip()
    ]


@pytest.mark.requirement("FR-3766")
@pytest.mark.parametrize(
    ("build", "expected"),
    [("26.127", [3.5, 2.5, 1.5, 0.5]), ("26.125", [0.5, 1.5, 2.5, 3.5])],
)
def test_p0560_r1_mark_s4_a_base_rim_is_written_last_face_first_on_26127(
    tmp_path: Path, build: str, expected: list[float]
) -> None:
    """R1-MARK-S4: on 26.127 the rim file of a base region is written in descending order of
    the face outside the base that holds each edge, the order that build keeps every edge of;
    26.125 keeps the file's order."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_mark_boundaries(_wing_with_cap(tmp_path, build))
    assert _written_rim(plan) == expected


@pytest.mark.requirement("FR-3766")
def test_p0560_r2_001_a_renamed_base_rim_is_written_last_face_first_on_26127(
    tmp_path: Path,
) -> None:
    """R2-001: a base family renamed by an import operation keeps 26.127's rim order, read
    from the OBJ by the family's name there; with the renamed name the rim matched no OBJ
    family and was written in the file's order, the order 26.127 drops edges of."""
    mesh = _wing_with_cap(tmp_path, "26.127")
    sidecar = Path(str(mesh) + ".boundaries.toml")
    text = sidecar.read_text(encoding="utf-8").replace(
        '[import]\nunits = "METER"\n',
        '[import]\nunits = "METER"\n[[import.operations]]\nop = "rename"\nsurface = "cap"\n'
        'to = "Base"\n',
    )
    sidecar.write_text(text, encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_mark_boundaries(mesh)
    assert _written_rim(plan) == [3.5, 2.5, 1.5, 0.5]
