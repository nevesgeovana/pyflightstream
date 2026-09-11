"""Tier 1: FR-84, a simulation's collected outputs live under ``outputs/``.

Pipeline role: quality gate over the managed workspace layout and over
the one reading of the word ``raw`` that FR-84 renames.

THE WORD MEANS THREE THINGS and only the SUBDIRECTORY is renamed, so
this module asserts the other two are untouched in the same file the
rename is asserted in: a result row still carries ``data_origin = raw``,
and a workspace written before the rename is still read whole.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyflightstream
from pyflightstream.results import parse_loads, to_table
from pyflightstream.results.tables import sweep_table
from pyflightstream.run import LoadsAssessor
from pyflightstream.workspace import CampaignWorkspace, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"


def _loads_text() -> str:
    return (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")


def _record(collected: str) -> dict[str, object]:
    """One manifest record naming ``collected`` as its only output."""
    return {
        "run_id": "camp/sim_9001/a+02.0",
        "sim_id": "9001",
        "point": {"alpha": 2.0},
        "fs_version_requested": "26.120",
        "package_version": pyflightstream.__version__,
        "script_sha256": "0" * 64,
        "raw_flag": False,
        "status": RunStatus.CONVERGED.value,
        "outputs": [collected],
    }


def _workspace_holding(tmp_path: Path, folder: str) -> CampaignWorkspace:
    """A recorded one-point workspace whose output sits in ``folder``."""
    root = tmp_path / folder
    sim = root / "sims" / "sim_9001"
    (sim / folder).mkdir(parents=True)
    (sim / folder / "loads.txt").write_text(_loads_text(), encoding="utf-8")
    (root / "runs.json").write_text(
        json.dumps([_record(f"{folder}/loads.txt")], indent=2), encoding="utf-8"
    )
    return CampaignWorkspace(root)


def test_a_simulation_collects_into_outputs_and_creates_no_raw(tmp_path):
    """FR-84: ``outputs`` names what the files are; ``raw`` named how they arrived."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    sim = workspace.create_sim("9001")
    assert (sim / "outputs").is_dir()
    assert not (sim / "raw").exists()
    produced = tmp_path / "loads.txt"
    produced.write_text("data", encoding="utf-8")
    assert workspace.collect_outputs("9001", [produced]) == ["outputs/loads.txt"]
    assert (sim / "outputs" / "loads.txt").is_file()
    assert not (sim / "raw").exists()


def test_a_workspace_that_already_holds_raw_is_still_read(tmp_path):
    """FR-84: no recorded point is orphaned by the rename.

    Scored against a CONTROL: the same campaign written under the new
    folder. The two tables must carry the same points with the same
    coefficients, which is what "returns the points it returned before"
    means and what an assertion on the legacy workspace alone cannot say.
    """
    legacy = sweep_table(_workspace_holding(tmp_path, "raw"))
    control = sweep_table(_workspace_holding(tmp_path, "outputs"))
    assert list(legacy["run_id"]) == list(control["run_id"])
    assert list(legacy["CL"]) == list(control["CL"])
    assert len(legacy) == 1


def test_the_assessor_judges_a_point_collected_under_either_folder(tmp_path):
    """FR-84: the outcome of a recorded point does not change with the rename."""
    verdicts = []
    for folder in ("raw", "outputs"):
        sim = tmp_path / folder
        (sim / folder).mkdir(parents=True)
        (sim / folder / "loads.txt").write_text(_loads_text(), encoding="utf-8")
        verdicts.append(LoadsAssessor("loads.txt")(None, None, sim).status)
    assert verdicts == [RunStatus.CONVERGED, RunStatus.CONVERGED]


def test_a_result_row_still_carries_the_raw_data_origin():
    """FR-84: the ``data_origin`` value is NOT renamed, and this is the guard.

    A sweep that renamed every ``raw`` would change the meaning of every
    recorded result: this column says the numbers came off the run rather
    than out of a reduction, and its companion is ``reduced``.
    """
    frame = to_table(parse_loads(_loads_text()))
    assert set(frame["data_origin"]) == {"raw"}
