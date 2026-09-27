# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.1
# artifact_id: test-workspace-fsi-driver
# last_modified_at: 2026-09-27T20:26:41.337Z
# last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
# dependencies: [pyflightstream.workspace.fsi_setup, pyflightstream.fsi.cli]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Preserve literal newline escapes in the actual driver replay fixture.
# revision_source: git
# GEOVERSE_HEADER_END
"""Offline usability of the existing FSI driver with a workspace f-prefixed input."""

import json

import numpy as np
import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.fsi import cli, driver, nodes
from pyflightstream.fsi.config import config_sha256, load_config
from pyflightstream.fsi.state import load_state
from pyflightstream.run import _write_pending_files
from pyflightstream.script import Script
from pyflightstream.workspace.fsi_setup import resolve_row_fsi
from tests.tier1_offline.test_fsi_driver import FAMILY_MAP, driver_config, write_loads


@pytest.mark.parametrize("factor", [1.0, 2.0])
def test_workspace_config_reaches_real_driver_and_displacement_archive(tmp_path, factor):
    """GOAL033:fsi:checks:workspace_integration.

    Replay the existing public synthetic rotor load fixture. This checks the
    actual structural driver, not native FlightStream convergence or validity.
    """
    base = driver_config()
    folder = tmp_path / "inputs" / "fsi"
    folder.mkdir(parents=True)
    source = folder / "f001.toml"
    lines = [
        'mode = "supplied"',
        "[calibration]",
        "bending_stiffness_n_m2 = 1.5",
        "[config]",
        f"blade_count = {base.blade_count}",
        f"omega_rad_per_s = {base.omega_rad_per_s}",
        "[config.phases]",
        *(f"{key} = {json.dumps(value)}" for key, value in base.phases.model_dump().items()),
        "[config.blade]",
        *(
            f"{key} = {json.dumps(value)}"
            for key, value in base.blade.model_dump(exclude={"provenance"}).items()
        ),
    ]
    text = "\n".join(lines) + "\n"
    source.write_text(text, encoding="utf-8")
    resolved = resolve_row_fsi(
        tmp_path / "inputs",
        {"FSI": "f001", "FSI_BENDING_STIFFNESS_N_M2_FACTOR": str(factor)},
    )
    assert resolved is not None
    case = SimCase(
        sim_id="001",
        aircraft="Synthetic",
        recipe="unsteady",
        sweep=SweepAxis(type="alpha", values=[0]),
        fsi=resolved.effective,
        fsi_provenance=resolved.provenance(),
    )
    run_dir = tmp_path / "run" / "001" / "point"
    hashes = _write_pending_files(Script("26.120"), run_dir, case=case, recorded={})
    staged = load_config(run_dir / "config.json")
    assert staged.blade.bending_stiffness_n_m2 == pytest.approx(
        [x * factor for x in base.blade.bending_stiffness_n_m2]
    )
    assert hashes["config.json"] == file_sha256(run_dir / "config.json")
    (run_dir / driver.FAMILY_MAP_FILE).write_text(
        FAMILY_MAP.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    layout = nodes.generate_node_layout(staged)
    nodes.write_node_map(layout, run_dir / staged.node_map_file)
    nodes.write_node_file(layout, run_dir / "structural_nodes.csv")
    for iteration in (100, 140):
        write_loads(run_dir, iteration)
        assert cli.main(["step", "--dir", str(run_dir)]) == 0
    state = load_state(run_dir / driver.STATE_FILE)
    assert state.call_count == state.step_count == 2
    assert state.phase == 2 and state.config_sha256 == config_sha256(staged)
    displacements = nodes.read_fsidisp(run_dir / driver.DISPLACEMENT_FILE)
    assert displacements.shape == (layout.total_nodes, 3)
    assert np.all(np.isfinite(displacements)) and np.any(displacements != 0)
    archive = run_dir / cli.ARCHIVE_DIR / "call_0002"
    assert (archive / driver.DISPLACEMENT_FILE).read_bytes() == (
        run_dir / driver.DISPLACEMENT_FILE
    ).read_bytes()
    assert config_sha256(staged) in (run_dir / driver.LOG_FILE).read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == text
    assert not (run_dir / cli.ERROR_LOG).exists()
