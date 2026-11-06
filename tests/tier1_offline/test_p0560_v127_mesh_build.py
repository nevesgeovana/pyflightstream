"""P0560-MESHBUILD: a [mesh] build with no operation previews no refusal (FR-3741, PFS-2187.04).

EXPORT_SURFACE_MESH is the one evidence-gated command such a build emits. It is verified on
26.100 and 26.124 to 26.127 by the export probe (reports/compat/CMP-<build>_2026-11-05_export-
surface.yaml), so the plan awaits nothing on those builds and the preview prints no refusal,
while a build the probe never ran keeps the refusal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.tier1_offline.test_regression_geometry_build_sweep import (
    _geometry_build__geometry,
)

PROBED = ["26.100", "26.124", "26.125", "26.126", "26.127"]


def _workspace(tmp_path: Path, build: str) -> Path:
    root = tmp_path / "ws"
    (root / "inputs" / "geometries").mkdir(parents=True)
    exe = Path(sys.executable).as_posix()
    (root / "inputs" / "executables.toml").write_text(
        f'"{build}" = {{ path = "{exe}", version = "{build}" }}\n', encoding="utf-8"
    )
    instruction = (
        f'fs_build = "{build}"\nboundaries = ["Wing"]\noutputs = ["fsm", "obj"]\n'
        '[mesh]\nfile = "src.obj"\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n'
    )
    return _geometry_build__geometry(root, "wing", instruction)


@pytest.mark.requirement("FR-3741")
@pytest.mark.parametrize("build", PROBED)
def test_p0560_v127_a_mesh_build_with_no_operation_awaits_nothing(tmp_path, build):
    """P0560-MESHBUILD: the plan on the real command database awaits no evidence."""
    from pyflightstream.workspace._geometry_build import plan_geometry_build

    plan = plan_geometry_build(_workspace(tmp_path, build))
    assert "EXPORT_SURFACE_MESH OBJ -1" in plan.variants[0].script.text
    assert plan.awaiting_evidence == ()


@pytest.mark.requirement("FR-3741")
@pytest.mark.parametrize("build", PROBED)
def test_p0560_v127_the_mesh_build_preview_prints_no_refusal(tmp_path, capsys, monkeypatch, build):
    """P0560-MESHBUILD: the preview names no command awaiting a licensed probe."""
    from pyflightstream.workspace.cli import main

    monkeypatch.chdir(_workspace(tmp_path, build))
    assert main(["geometry", "build"]) == 0
    out = capsys.readouterr().out
    assert "EXPORT_SURFACE_MESH OBJ -1" in out
    assert "refused with --apply" not in out


@pytest.mark.requirement("FR-3741")
def test_p0560_v127_an_unprobed_build_keeps_the_refusal(tmp_path):
    """P0560-MESHBUILD: 26.123 has no export probe, so its build still awaits one."""
    from pyflightstream.workspace._geometry_build import plan_geometry_build

    plan = plan_geometry_build(_workspace(tmp_path, "26.123"))
    assert plan.awaiting_evidence == ("EXPORT_SURFACE_MESH",)
