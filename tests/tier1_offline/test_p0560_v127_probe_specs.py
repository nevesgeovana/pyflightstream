"""P0560-EXPORTPROBE and P0560-DETECTPROBE: the two probes of FR-3741 and FR-3742.

EXPORT_SURFACE_MESH is judged by the OBJ it writes (twelve faces over the eight vertices of the
imported box); AUTO_DETECT_TRAILING_EDGES by the saved edges before and after it, read with the
measured mesh-block reader, where the wing stub's sharp trailing edge has mid-point (2, 2, 0).
Neither may verify on a log line, and neither may guess when its instrument read nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.tier1_offline._p0340_probe_support import artifacts_in

FIXTURE = Path(__file__).parent / "fixtures" / "p0460_marking_sections.json"
BOX = (
    (0.0, -1.0, -1.0),
    (0.0, 1.0, -1.0),
    (0.0, 1.0, 1.0),
    (0.0, -1.0, 1.0),
    (2.0, -1.0, -1.0),
    (2.0, 1.0, -1.0),
    (2.0, 1.0, 1.0),
    (2.0, -1.0, 1.0),
)


def _obj(path: Path, faces: int = 12, points=BOX) -> None:
    rows = [f"v {x} {y} {z}" for x, y, z in points] + ["g Body"]
    rows += [f"f 1 2 {3 + i % 6}" for i in range(faces)]
    path.write_text("\n".join(rows) + "\n", encoding="ascii")


def _shifted(text: str, dy: float, dz: float) -> str:
    """The saved excerpt with every vertex moved by (0, dy, dz): rows two and three of the block."""
    lines = text.splitlines()
    rows = [i for i, line in enumerate(lines) if "E+00" in line][:3]
    for index, offset in ((rows[1], dy), (rows[2], dz)):
        values = [float(v) + offset for v in lines[index].split(",") if v.strip()]
        lines[index] = ",".join(f"{v: .17E}" for v in values) + ","
    return "\n".join(lines) + "\n"


@pytest.mark.requirement("FR-3741")
@pytest.mark.parametrize("build", ["26.100", "26.124", "26.125", "26.126", "26.127"])
def test_p0560_v127_the_export_probe_renders_on_every_build_it_serves(tmp_path, build):
    """P0560-EXPORTPROBE: a synthetic box import, then the export of every boundary to OBJ."""
    from pyflightstream.qa.probes import Requires, generate_probe_script
    from pyflightstream.qa.specs import PROBE_SPECS

    assert "EXPORT_SURFACE_MESH" in PROBE_SPECS
    spec = PROBE_SPECS["EXPORT_SURFACE_MESH"]
    assert spec.requires is Requires.NONE
    lines = generate_probe_script(spec, build, tmp_path).render().splitlines()
    begin = lines.index("PRINT PYFS_PROBE_BEGIN_EXPORT_SURFACE_MESH")
    target = next(line for line in lines[begin:] if line.startswith("EXPORT_SURFACE_MESH"))
    assert target == "EXPORT_SURFACE_MESH OBJ -1"
    assert "FILE_TYPE OBJ" in lines[:begin]


@pytest.mark.requirement("FR-3741")
def test_p0560_v127_the_export_probe_judges_the_written_obj(tmp_path):
    """P0560-EXPORTPROBE: the file decides; absent or another mesh is broken, never verified."""
    from pyflightstream.qa.specs import PROBE_SPECS

    assert "EXPORT_SURFACE_MESH" in PROBE_SPECS
    effect = PROBE_SPECS["EXPORT_SURFACE_MESH"].assert_effect
    assert effect(artifacts_in(tmp_path)) is False
    _obj(tmp_path / "export.obj")
    assert effect(artifacts_in(tmp_path)) is True
    _obj(tmp_path / "export.obj", faces=11)
    assert effect(artifacts_in(tmp_path)) is False
    _obj(tmp_path / "export.obj", points=[(x * 1000, y, z) for x, y, z in BOX])
    assert effect(artifacts_in(tmp_path)) is False


@pytest.mark.requirement("FR-3742")
def test_p0560_v127_the_detection_probe_reads_the_saved_edges(tmp_path):
    """P0560-DETECTPROBE: the wing trailing edge saved after and nothing before verifies."""
    from pyflightstream.qa.probes import Requires
    from pyflightstream.qa.specs import PROBE_SPECS

    spec = PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"]
    assert spec.requires is Requires.NONE and spec.save_state
    effect = spec.assert_effect
    before, after = tmp_path / "state_before.fsm", tmp_path / "state_after.fsm"
    assert effect(artifacts_in(tmp_path)) is None
    before.write_text(_detection_save("empty"))
    after.write_text(_detection_save("extra"))
    assert effect(artifacts_in(tmp_path)) is True
    after.write_text(_detection_save("wrong"))
    assert effect(artifacts_in(tmp_path)) is False
    after.write_text(_detection_save("empty"))
    assert effect(artifacts_in(tmp_path)) is False
    before.write_text(_detection_save("target"))
    after.write_text(_detection_save("target"))
    assert effect(artifacts_in(tmp_path)) is None
    after.write_text("not a saved simulation")
    before.write_text(_detection_save("empty"))
    assert effect(artifacts_in(tmp_path)) is None


def _detection_save(mark, dz=0.0):
    """Controlled marks on measured 26.124 box rows, shifted to the fixed probe target.

    This is a reader control, not a new licensed rounded-output observation.
    """
    saved = json.loads(FIXTURE.read_text(encoding="utf-8"))
    text = _shifted(saved["IMPORT_WAKE_EDGES_FROM_FILE"]["after"], 2.0, 1.0)
    lines = text.splitlines()
    start = 1 + 3 + 3 * 2
    faces = list(
        zip(
            *[[int(v) - 1 for v in lines[start + i].split(",") if v.strip()] for i in (3, 4, 5)],
            strict=True,
        )
    )
    coords = [i for i, line in enumerate(lines) if "E+00" in line][:3]
    points = list(
        zip(*[[float(v) for v in lines[i].split(",") if v.strip()] for i in coords], strict=True)
    )
    for j, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))):
        flags = []
        for face in faces:
            midpoint = tuple((points[face[a]][i] + points[face[b]][i]) / 2 for i in range(3))
            active = (mark in ("target", "extra") and midpoint == (2.0, 2.0, 0.0)) or (
                mark in ("wrong", "extra") and midpoint == (2.0, 2.0, 2.0)
            )
            flags.append("T" if active else "F")
        lines[start + 22 + j] = ",".join(flags) + ","
    values = [float(v) + dz for v in lines[coords[2]].split(",") if v.strip()]
    lines[coords[2]] = ",".join(f"{v:.17E}" for v in values) + ","
    return "$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n" + "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    "delta, expected",
    [
        (0, True),
        (0.999e-6, True),
        (1e-6, True),
        (1.001e-6, False),
        (1.0001e-6, False),
        (-1e-6, True),
        (-1.001e-6, False),
    ],
)
def test_p0570_detection_coordinate_bound(tmp_path, delta, expected):
    from pyflightstream.qa.specs import PROBE_SPECS

    effect = PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"].assert_effect

    (tmp_path / "state_before.fsm").write_text(_detection_save("empty"))
    (tmp_path / "state_after.fsm").write_text(_detection_save("target", delta))
    assert effect(artifacts_in(tmp_path)) is expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_p0570_detection_nonfinite_is_unknown(tmp_path, value):
    from pyflightstream.qa.specs import PROBE_SPECS

    effect = PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"].assert_effect

    (tmp_path / "state_before.fsm").write_text(_detection_save("empty"))
    (tmp_path / "state_after.fsm").write_text(_detection_save("target", value))
    assert effect(artifacts_in(tmp_path)) is None


@pytest.mark.parametrize(
    "head", ["", "$GLOBAL_START$\n0.001\n2\n$GLOBAL_END$\n", "$GLOBAL_START$\n2\n5\n$GLOBAL_END$\n"]
)
def test_p0570_detection_unresolved_units(tmp_path, head):
    from pyflightstream.qa.specs import PROBE_SPECS

    effect = PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"].assert_effect

    (tmp_path / "state_before.fsm").write_text(_detection_save("empty"))
    text = _detection_save("target").split("$GLOBAL_END$\n", 1)[1]
    (tmp_path / "state_after.fsm").write_text(head + text)
    assert effect(artifacts_in(tmp_path)) is None


def test_p0570_detection_tolerance_override(tmp_path):
    from pyflightstream.qa.specs import PROBE_SPECS

    effect = PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"].assert_effect

    (tmp_path / "state_before.fsm").write_text(_detection_save("empty"))
    (tmp_path / "state_after.fsm").write_text(_detection_save("target", 2e-6))
    assert effect(artifacts_in(tmp_path)) is False
    assert effect(artifacts_in(tmp_path), coordinate_tolerance_m=3e-6) is True
    with pytest.raises(ValueError, match="finite and nonnegative"):
        effect(artifacts_in(tmp_path), coordinate_tolerance_m=-1)


def test_p0570_recorded_26124_exact_outcome_is_preserved(tmp_path):
    from pyflightstream.qa.specs import PROBE_SPECS

    report = Path(__file__).parents[2] / "reports/compat/CMP-26124_2026-11-05_autodetect-te.md"
    assert '{"before": [], "after": [[2.0, 2.0, 0.0]]}' in report.read_text()
    (tmp_path / "state_before.fsm").write_text(_detection_save("empty"))
    (tmp_path / "state_after.fsm").write_text(_detection_save("target"))
    spec = PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"]
    assert spec.assert_effect(artifacts_in(tmp_path)) is True
    assert json.loads(spec.observe(artifacts_in(tmp_path))) == {
        "before": [],
        "after": [[2.0, 2.0, 0.0]],
    }


@pytest.mark.parametrize("change", ["topology", "identity", "geometry", "names"])
def test_p0570_detection_incomparable_save(tmp_path, change):
    from pyflightstream.qa.specs import PROBE_SPECS

    (tmp_path / "state_before.fsm").write_text(_detection_save("empty"))
    after = _detection_save("target")
    if change == "topology":
        after = after.replace("3,4,2,6,3,7,4,8,1,5,6,7,", "4,3,2,6,3,7,4,8,1,5,6,7,")
    elif change == "geometry":
        after = _detection_save("target", 1.0)
    elif change == "names":
        after = after.replace("Body", "Unknown")
    else:
        # Collapse an edge onto another: its midpoint no longer identifies one edge.
        after = after.replace("2.00000000000000000E+00", "0.00000000000000000E+00")
    (tmp_path / "state_after.fsm").write_text(after)
    assert PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"].assert_effect(artifacts_in(tmp_path)) is None


def test_p0570_actual_probe_target_is_separated_from_competing_edges(tmp_path):
    import math

    from pyflightstream.qa.probes import generate_probe_script
    from pyflightstream.qa.specs import PROBE_SPECS

    generate_probe_script(PROBE_SPECS["AUTO_DETECT_TRAILING_EDGES"], "26.124", tmp_path)
    vertices, faces = [], []
    for row in (tmp_path / "marking.obj").read_text().splitlines():
        fields = row.split()
        if fields[0] == "v":
            vertices.append(tuple(map(float, fields[1:])))
        elif fields[0] == "f":
            faces.append([int(i) - 1 for i in fields[1:]])
    edges = {
        tuple(sorted((a, b)))
        for face in faces
        for a, b in zip(face, face[1:] + face[:1], strict=True)
    }
    distances = sorted(
        math.dist(tuple((vertices[a][i] + vertices[b][i]) / 2 for i in range(3)), (2.0, 2.0, 0.0))
        for a, b in edges
    )
    assert distances[0] == 0
    assert distances[1] > 2 * math.sqrt(3) * 1e-6
