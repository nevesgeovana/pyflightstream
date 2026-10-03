"""Tier 1, 0.35.0: every datapoint has the run id alias ``<sim>_<index>`` (FR-395).

Pipeline role: quality gate of P0350-RUN-ID-ALIAS, through ``pyflightstream.run.cli.main``.

The alias is derived and never stored: the 1-based position of the point in its polar, the
recorded points first and the planned ones without a record after them. It is accepted by
``--points``, ``mark-failed`` and (refused, whole simulations only) ``delete-sims``, and
printed beside the point by ``plan``. Where a verb destroys, an alias whose record reading and
plan reading disagree is refused naming both.

What it does NOT check: a solver. A stub stands in for the executor.
"""
# The evidence line of this requirement cites this module (docs/srs/functional-requirements.md):

from __future__ import annotations

import json
import re

from pyflightstream.run import cli
from pyflightstream.workspace import RunRecord, RunStatus
from tests.tier1_offline.test_p0340_run_usability import (
    _argv,
    _names,
    _plan_file,
    _two_simulations,
)

_ALIAS_LINE = re.compile(r"^\s+(\d+_\d+)  POL (\d+) (\S+)\s*$", re.MULTILINE)


def _record(sim, run_id, *, status=RunStatus.CONVERGED, points_ran=None):
    return RunRecord(
        run_id=run_id,
        sim_id=sim,
        matrix_stem="warm",
        fs_version_requested="26.120",
        package_version="0.35.0",
        script_sha256="c" * 64,
        raw_flag=False,
        status=status,
        outputs=[],
        script_path=None,
        inputs_sha256={},
        points_ran=points_ran or [],
    )


def _aliases(capsys, workspace, matrix):
    """Plan through main and return {alias: point name} the plan prints."""
    capsys.readouterr()
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    return {alias: name for alias, _sim, name in _ALIAS_LINE.findall(capsys.readouterr().out)}


def _record_points(workspace, sim, names):
    for name in names:
        workspace.append_record(_record(sim, f"warm/sim_{sim}/{name}"))


def test_fr395_each_point_of_a_three_point_polar_has_its_alias(tmp_path, monkeypatch, capsys):
    """P0350-RUN-ID-ALIAS (FR-395): the plan prints ``<sim>_<index>`` beside each point, from 1."""
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    assert len(names) == 3
    found = _aliases(capsys, workspace, matrix)
    assert {key: found[key] for key in ("5002_1", "5002_2", "5002_3")} == {
        "5002_1": names[0],
        "5002_2": names[1],
        "5002_3": names[2],
    }
    assert "5002_0" not in found and "5002_4" not in found


def test_fr395_the_alias_is_stable_when_a_point_is_rerun_or_continued(
    tmp_path, monkeypatch, capsys
):
    """P0350-RUN-ID-ALIAS (FR-395 R1): a re-run and a continuation add records, move no alias."""
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    before = _aliases(capsys, workspace, matrix)
    _record_points(workspace, "5002", names)
    recorded = _aliases(capsys, workspace, matrix)
    workspace.append_record(_record("5002", f"warm/sim_5002/r20261002T010203/{names[1]}"))
    workspace.append_record(_record("5002", f"warm/sim_5002/r20261003T010203/{names[0]}"))
    continued = _aliases(capsys, workspace, matrix)
    assert before == recorded == continued
    assert continued["5002_2"] == names[1]
    # A point added at the front of the sweep takes the next index; the recorded ones keep theirs.
    text = matrix.read_text(encoding="utf-8")
    matrix.write_text(text.replace("-2.0,0.0,2.0", "-4.0,-2.0,0.0,2.0"), encoding="utf-8")
    grown = _aliases(capsys, workspace, matrix)
    assert [grown[f"5002_{index}"] for index in (1, 2, 3)] == names
    assert grown["5002_4"] not in names


def test_fr395_a_steady_jobs_points_have_aliases(tmp_path, monkeypatch, capsys):
    """P0350-RUN-ID-ALIAS (FR-395 R4): a job record stands for its points, in the order it ran."""
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5001")
    ran = [{"tag": name, "status": "CONVERGED"} for name in names]
    workspace.append_record(_record("5001", "warm/sim_5001/sweep", points_ran=ran))
    found = _aliases(capsys, workspace, matrix)
    assert [found[f"5001_{index}"] for index in (1, 2, 3)] == names
    capsys.readouterr()
    assert cli.main(["mark-failed", "--sims", "5001_3", "--workspace", str(workspace.root)]) == 0
    assert "warm/sim_5001/sweep" in capsys.readouterr().out


def test_fr395_points_takes_an_alias_and_a_name_alike(tmp_path, monkeypatch, capsys):
    """P0350-RUN-ID-ALIAS (FR-395 R2): ``--points 5002_2`` plans that point alone, no ``--sims``."""
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    assert cli.main(_argv("plan", workspace, matrix, "--points", "5002_2")) == 0
    planned = json.dumps(json.loads(_plan_file(workspace, matrix).read_text(encoding="utf-8")))
    assert names[1] in planned and names[0] not in planned and "5001" not in planned, planned
    capsys.readouterr()
    assert cli.main(_argv("plan", workspace, matrix, "--sims", "5001", "--points", "5002_2")) == 2
    assert "5002" in capsys.readouterr().err


def test_fr395_an_alias_that_names_no_point_is_named_on_standard_error(
    tmp_path, monkeypatch, capsys
):
    """P0350-RUN-ID-ALIAS (FR-395 R5): index 9 of a three-point polar is refused by name."""
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    capsys.readouterr()
    assert cli.main(_argv("plan", workspace, matrix, "--points", "5002_9")) == 2
    assert "5002_9" in capsys.readouterr().err
    _record_points(workspace, "5002", _names(workspace, matrix, "5002"))
    assert cli.main(["mark-failed", "--sims", "5002_9", "--workspace", str(workspace.root)]) == 2
    assert "5002_9" in capsys.readouterr().err


def test_fr395_mark_failed_marks_the_point_of_the_alias_alone(tmp_path, monkeypatch, capsys):
    """P0350-RUN-ID-ALIAS (FR-395 R2): the control is an alias both readings agree on."""
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    _record_points(workspace, "5002", names)
    capsys.readouterr()
    argv = ["mark-failed", "--sims", "5002_2", "--workspace", str(workspace.root), "--apply"]
    assert cli.main(argv) == 0
    status = {
        row["run_id"]: row["status"] for row in json.loads(workspace.manifest_path.read_text())
    }
    assert status[f"warm/sim_5002/{names[1]}"] == "FAILED_MARKED"
    assert status[f"warm/sim_5002/{names[0]}"] == "CONVERGED"
    assert status[f"warm/sim_5002/{names[2]}"] == "CONVERGED"


def test_fr395_a_destructive_verb_refuses_an_alias_the_two_readings_disagree_on(
    tmp_path, monkeypatch, capsys
):
    """P0350-RUN-ID-ALIAS (FR-395): only the second point is recorded, so ``5002_1`` is ambiguous.

    The records read it as the second point (the one recorded), the plan as the first; the
    refusal names both and nothing is written. The control is the test above, where they agree.
    """
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    _record_points(workspace, "5002", [names[1]])
    before = workspace.manifest_path.read_bytes()
    capsys.readouterr()
    argv = ["mark-failed", "--sims", "5002_1", "--workspace", str(workspace.root), "--apply"]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert names[0] in err and names[1] in err and "5002_1" in err, err
    assert workspace.manifest_path.read_bytes() == before


def test_fr395_delete_sims_refuses_an_alias_and_names_the_simulation(tmp_path, monkeypatch, capsys):
    """P0350-RUN-ID-ALIAS (FR-395 R2): delete-sims removes whole simulations, never one point."""
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    _record_points(workspace, "5002", names)
    capsys.readouterr()
    assert cli.main(["delete-sims", "5002_2", "--workspace", str(workspace.root)]) == 2
    assert "5002" in capsys.readouterr().err
    assert cli.main(["delete-sims", "5002", "--workspace", str(workspace.root)]) == 0
