"""Regressions found in the adversarial review of the FSI release lane."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.fsi import cli, driver, nodes
from tests.tier1_offline.test_fsi_driver import driver_config, stage_run


def test_p0400_failed_archive_preserves_the_original_failure(tmp_path, capsys):
    """P0400-FAILARCHIVE: archival failure cannot mask the coupling failure."""
    stage_run(tmp_path)
    (tmp_path / cli.ARCHIVE_DIR).write_text("occupied", encoding="utf-8")

    assert cli.coupled_step(tmp_path, echo_failure=True) == 1

    error = capsys.readouterr().err
    assert "pyfs-fsi step failed: FileNotFoundError" in error
    assert str(tmp_path / cli.ERROR_LOG) in error
    log = (tmp_path / cli.ERROR_LOG).read_text(encoding="utf-8")
    assert "FS_SurfaceSection_Loads.txt" in log
    assert "could not archive the failed call" in log


@pytest.mark.parametrize("configured", [[], [0.0], [0.0] * 100])
def test_p0400_configured_axis_requires_one_value_per_station(configured):
    """P0400-EANODE: the new axis distribution obeys the map's shape contract."""
    layout = nodes.generate_node_layout(driver_config())
    payload = {**layout.model_dump(), "ea_configured_chordwise_m": configured}
    with pytest.raises(ValidationError, match="ea_configured_chordwise_m.*entries"):
        nodes.NodeOrderingMap.model_validate(payload)


def test_p0400_all_routes_share_the_section_load_reduction():
    """P0400-SHAREDLOADS: one reduction serves both rotors and the fixed wing."""
    tree = ast.parse(Path(driver.__file__).read_text(encoding="utf-8"))
    reductions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "to_elastic_axis"
    ]
    assert len(reductions) == 1, "all three routes must use the same per-family load reduction"
