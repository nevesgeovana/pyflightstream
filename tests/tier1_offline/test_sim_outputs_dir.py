"""Tier 1: where a simulation's collected outputs live, and what is still read.

Pipeline role: quality gate over the managed workspace layout and over
the one reading of the word ``raw`` that FR-84 renamed.

THE FOLDER HAS MOVED TWICE AND EVERY EARLIER SHAPE IS STILL READ, which
is the property this module exists for: ``raw/`` until 0.16.0, then
``outputs/`` (FR-84), and one folder per datapoint under ``datapoints/``
since 0.16.0 (FR-92). A workspace recorded under any of them keeps every
one of its points.

THE WORD ``raw`` MEANS THREE THINGS and only the SUBDIRECTORY was
renamed, so this module asserts the others are untouched in the same
file: a result row still carries ``data_origin = raw``.
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


def _case_at_two():
    """A one-point case at alpha 2, so the assessor can name its folder."""
    from pyflightstream.cases import SimCase, SweepAxis

    case = SimCase(
        sim_id="9001",
        aircraft="WB",
        velocity=30.0,
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[2.0]),
    )
    case.point = {"alpha": 2.0}
    return case


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


def test_a_simulation_collects_into_its_datapoint_and_creates_neither_older_folder(tmp_path):
    """FR-92: a point's evidence is alone in that point's own folder.

    ``outputs`` named what the files are and ``raw`` named how they
    arrived; neither named WHOSE they are, and one simulation holds the
    evidence of every point of its sweep. Neither older folder is
    created, for the reason ``raw`` stopped being created at 0.16.0: a
    folder this release does not write to is an empty promise in every
    new simulation.
    """
    workspace = CampaignWorkspace(tmp_path / "camp")
    sim = workspace.create_sim("9001")
    assert (sim / "datapoints").is_dir()
    assert not (sim / "outputs").exists()
    assert not (sim / "raw").exists()
    produced = tmp_path / "loads.txt"
    produced.write_text("data", encoding="utf-8")
    assert workspace.collect_outputs("9001", [produced], datapoint="DP-a+02.0") == [
        "datapoints/DP-a+02.0/loads.txt"
    ]
    assert (sim / "datapoints" / "DP-a+02.0" / "loads.txt").is_file()
    assert not (sim / "outputs").exists()
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


def test_the_assessor_judges_a_point_collected_under_any_of_the_three_folders(tmp_path):
    """FR-84 and FR-92: a recorded point's outcome does not change with the layout.

    All three are asserted together, so a release that adds a fourth
    folder and forgets one of the older ones fails here rather than in a
    user's re-judged workspace.
    """
    verdicts = []
    for folder in ("raw", "outputs", "datapoints/DP-a+02.0"):
        sim = tmp_path / folder.replace("/", "_")
        (sim / folder).mkdir(parents=True)
        (sim / folder / "loads.txt").write_text(_loads_text(), encoding="utf-8")
        verdicts.append(LoadsAssessor("loads.txt")(_case_at_two(), None, sim).status)
    assert verdicts == [RunStatus.CONVERGED] * 3


def test_a_result_row_still_carries_the_raw_data_origin():
    """FR-84: the ``data_origin`` value is NOT renamed, and this is the guard.

    A sweep that renamed every ``raw`` would change the meaning of every
    recorded result: this column says the numbers came off the run rather
    than out of a reduction, and its companion is ``reduced``.
    """
    frame = to_table(parse_loads(_loads_text()))
    assert set(frame["data_origin"]) == {"raw"}
