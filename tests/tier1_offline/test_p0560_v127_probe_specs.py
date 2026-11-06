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
    saved = json.loads(FIXTURE.read_text(encoding="utf-8"))
    empty = saved["SURFACE_RENAME"]["before"]
    two_edges = saved["IMPORT_WAKE_EDGES_FROM_FILE"]["after"]
    before, after = tmp_path / "state_before.fsm", tmp_path / "state_after.fsm"

    assert effect(artifacts_in(tmp_path)) is None
    before.write_text(empty)
    after.write_text(_shifted(two_edges, 2.0, 1.0))
    assert effect(artifacts_in(tmp_path)) is True
    after.write_text(two_edges)
    assert effect(artifacts_in(tmp_path)) is False
    after.write_text(empty)
    assert effect(artifacts_in(tmp_path)) is False
    before.write_text(saved["IMPORT_WAKE_EDGES_FROM_FILE"]["before"])
    after.write_text(_shifted(two_edges, 2.0, 1.0))
    assert effect(artifacts_in(tmp_path)) is None
    after.write_text("not a saved simulation")
    before.write_text(empty)
    assert effect(artifacts_in(tmp_path)) is None
