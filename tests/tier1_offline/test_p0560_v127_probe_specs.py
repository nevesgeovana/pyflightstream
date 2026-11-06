"""P0560-EXPORTPROBE: the surface-export probe of FR-3741.

EXPORT_SURFACE_MESH is judged by the OBJ it writes (twelve faces over the eight vertices of the
imported box). It may not verify on a log line, and an absent file is broken, not guessed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tier1_offline._p0340_probe_support import artifacts_in

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
