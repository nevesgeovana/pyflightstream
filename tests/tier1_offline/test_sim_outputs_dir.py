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
    assert workspace.collect_outputs("9001", [produced], datapoint={"alpha": 2.0}) == [
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


def test_a_mixed_layout_judges_the_point_from_its_own_folder_and_not_the_legacy_one(tmp_path):
    """The upgrade path: a 0.15.0 `outputs/` still on disk, a point re-run at 0.16.0.

    THIS IS THE CASE THE THREE-LAYOUT TEST CANNOT SEE, because that one
    gives each layout its own directory so the two never sit in one
    simulation. A mutant that puts the LEGACY folders first survived the
    whole suite for want of it, and refuses a correctly run point here:

        folders = [outputs, raw] + own   ->  "several of them parse"

    IT DOES NOT KILL THE MERGE MUTANT, and this docstring claimed it did
    until the quality lens scored it (2026-09-11): a merge of ONE folder
    is that folder, and this simulation holds one legacy folder beside
    the point's own. The case below,
    `test_the_older_of_the_two_legacy_folders_does_not_join_the_newer`,
    is the layout that discriminates a merge, and it holds BOTH.

    The property is PRECEDENCE, stated by the code and by FR-92 and
    measured by nothing until now: a point that has a folder is judged
    from that folder, and the legacy files are not among its candidates.
    """
    sim = tmp_path / "sim_9001"
    # The legacy shared folder, holding two OTHER points of the same row.
    (sim / "outputs").mkdir(parents=True)
    for name, alpha in (("a+00.0.txt", "0.000"), ("a+02.0.txt", "2.000")):
        (sim / "outputs" / name).write_text(
            _loads_text().replace(
                "Angle of attack (Deg)                       2.000",
                f"Angle of attack (Deg)                       {alpha}",
            ),
            encoding="utf-8",
        )
    # This point, re-run under 0.16.0 into its own folder.
    own = sim / "datapoints" / "DP-a+04.0"
    own.mkdir(parents=True)
    (own / "loads.txt").write_text(
        _loads_text().replace(
            "Angle of attack (Deg)                       2.000",
            "Angle of attack (Deg)                       4.000",
        ),
        encoding="utf-8",
    )

    from pyflightstream.cases import SimCase, SweepAxis

    case = SimCase(
        sim_id="9001",
        aircraft="WB",
        velocity=30.0,
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0, 2.0, 4.0]),
    )
    case.point = {"alpha": 4.0}
    verdict = LoadsAssessor()(case, None, sim)
    assert verdict.status is RunStatus.CONVERGED, verdict.error
    printed = {entry.get("axis"): entry.get("reported") for entry in (verdict.conditions or [])}
    assert printed.get("alpha") == 4.0, (
        f"the point was judged on an export printing {printed.get('alpha')}, so the "
        "legacy shared folder reached the candidates"
    )


def test_an_empty_datapoint_folder_is_this_points_refusal_and_not_a_fall_through(tmp_path):
    """A point that HAS a folder is judged from it, empty or not (FR-92).

    The fallback took "the first folder that holds anything", so a
    datapoint folder that EXISTS and is EMPTY -- which is what a refused
    collection leaves behind -- fell through to the shared pre-0.16.0
    folder and judged the point on somebody else's export.

    MEASURED ON AN ADVANCE-RATIO SWEEP, DELIBERATELY. A loads export
    prints the alpha, the sideslip and the velocity it ran and NEVER
    prints the advance ratio, so REV010-001's binding cannot tell two
    points of a J sweep apart: on an alpha sweep the binding rescues the
    verdict and hides the defect, and here the point at J=1.7 was
    recorded CONVERGED on the export of J=1.3, in silence.
    """
    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.workspace import datapoint_dir_name

    sim = tmp_path / "sim_9001"
    point = {"alpha": 2.0, "advance_ratio": 1.7}
    (sim / "datapoints" / datapoint_dir_name(point)).mkdir(parents=True)
    (sim / "outputs").mkdir(parents=True)
    (sim / "outputs" / "J+01.3.txt").write_text(_loads_text(), encoding="utf-8")

    case = SimCase(
        sim_id="9001",
        aircraft="WB",
        velocity=30.0,
        recipe="steady",
        sweep=SweepAxis(type="advance_ratio", values=[1.3, 1.7]),
    )
    case.point = point
    verdict = LoadsAssessor()(case, None, sim)
    assert verdict.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, (
        "the point was judged on another point's export: its own folder is empty, and "
        "the loads export prints no advance ratio, so nothing downstream could tell"
    )


def test_a_point_with_no_axis_is_refused_before_anything_is_moved(tmp_path):
    """The collector takes the POINT, so this is the refusal it can earn.

    A datapoint with no coordinates has no stable folder, and a fallback
    name would give two different points one folder, which is the
    collision this layout exists to remove. The refusal is asserted on
    the operative content of its message rather than on its type alone.
    """
    import pytest

    from pyflightstream.cases import CampaignConfigError

    workspace = CampaignWorkspace(tmp_path / "camp")
    produced = tmp_path / "loads.txt"
    produced.write_text("data", encoding="utf-8")
    with pytest.raises(CampaignConfigError, match="no known axis"):
        workspace.collect_outputs("9001", [produced], datapoint={})
    assert produced.is_file(), "a refusal must leave the source exactly where it was"


def test_the_older_of_the_two_legacy_folders_does_not_join_the_newer(tmp_path):
    """`outputs/` is read and `raw/` is not, on a workspace holding both.

    THE `break` IN THE FOLDER LOOP CARRIES THIS and nothing measured it: a
    mutant that drops it and MERGES every folder's files survived the whole
    suite (the quality lens, 2026-09-11). Restored against this case it dies,
    with the refusal the merge earns:

        collected: outputs_loads.txt, raw_loads.txt
        several of them parse The mixed-layout test above kills the
    mutant that REORDERS the folders and not the one that merges them, because
    a merge of one folder is that folder.

    THE LAYOUT THAT DISCRIMINATES is a simulation holding BOTH pre-0.16.0
    folders and no datapoint folder, which is what a workspace that lived
    through the 0.16.0 rename looks like. FR-84 promises `outputs/` is the one
    read there; merged, the two parse as two loads tables and the point is
    refused.

    WRITTEN ON AN ADVANCE-RATIO SWEEP, deliberately, as the empty-folder case
    is: a loads export never prints the ratio, so REV010-001's binding cannot
    tell the two files apart and cannot rescue a merge. An alpha-sweep version
    of this test is inert and reports the mutant as equivalent.
    """
    from pyflightstream.cases import SimCase, SweepAxis

    sim = tmp_path / "sim_9001"
    for folder in ("outputs", "raw"):
        (sim / folder).mkdir(parents=True)
        (sim / folder / f"{folder}_loads.txt").write_text(_loads_text(), encoding="utf-8")

    case = SimCase(
        sim_id="9001",
        aircraft="WB",
        velocity=30.0,
        recipe="steady",
        sweep=SweepAxis(type="advance_ratio", values=[1.3, 1.7]),
    )
    case.point = {"alpha": 2.0, "advance_ratio": 1.7}
    verdict = LoadsAssessor()(case, None, sim)
    assert verdict.status is RunStatus.CONVERGED, (
        "the two legacy folders were read together, so two files parsed as loads "
        f"tables and the point was refused: {verdict.error}"
    )
