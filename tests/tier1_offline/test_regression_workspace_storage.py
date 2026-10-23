"""Regression coverage grouped by subject."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tomllib
import zipfile
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run._batch_collect import job_ended
from pyflightstream.run.records import restore
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError, _make_dir_link
from pyflightstream.workspace import RunStatus as _IntegfixStorageRunStatus
from pyflightstream.workspace import RunStatus as _Workspace3StorageRunStatus
from pyflightstream.workspace import _batch_life as batch_life
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.ledger import activity_rows, additional_rows, diff, post_log_groups
from pyflightstream.workspace.manifest import RunRecord
from pyflightstream.workspace.manifest import RunStatus as _Workspace2ManifestRunStatus
from pyflightstream.workspace.naming import ARCHIVE_DIR
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from pyflightstream.workspace.sidecars import (
    load_toml,
    read_inventory,
    write_inventory,
)
from tests.support_helpers import saved_mesh_fixture as _workspace_1_sidecars__saved_mesh_fixture
from tests.tier1_offline.test_free_space_list import _record as _integfix_storage___record
from tests.tier1_offline.test_free_space_list import _write as _integfix_storage___write
from tests.tier1_offline.test_goal024_profile_log import (
    LOG_TABLE as _WORKSPACE_1_BATCH_LIFE__LOG_TABLE,
)
from tests.tier1_offline.test_goal024_profile_log import (
    _write_profile as _workspace_1_batch_life___write_profile,
)
from tests.tier1_offline.test_goal035_storage import (
    _copied_paths as _workspace_1_batch_life___copied_paths,
)
from tests.tier1_offline.test_goal035_storage import (
    _linked_sim as _workspace_3_storage___linked_sim,
)
from tests.tier1_offline.test_goal035_storage import _record as _workspace_1_batch_life___record
from tests.tier1_offline.test_goal035_storage import _record as _workspace_1_storage___record
from tests.tier1_offline.test_goal035_storage import _record as _workspace_3_storage___record
from tests.tier1_offline.test_goal035_storage import (
    _shared_product_workspace as _workspace_3_storage___shared_product_workspace,
)
from tests.tier1_offline.test_goal035_storage import _sync_pair as _workspace_1_storage___sync_pair
from tests.tier1_offline.test_goal035_storage import _sync_pair as _workspace_3_storage___sync_pair
from tests.tier1_offline.test_goal035_storage import _write as _workspace_1_storage___write
from tests.tier1_offline.test_goal035_storage import _write as _workspace_3_storage___write
from tests.tier1_offline.test_goal035_storage import (
    _write_recipe as _workspace_1_storage___write_recipe,
)
from tests.tier1_offline.test_goal035_storage import (
    _write_recipe as _workspace_3_storage___write_recipe,
)
from tests.tier1_offline.test_goal035_storage import _ws as _workspace_1_storage___ws
from tests.tier1_offline.test_goal035_storage import _ws as _workspace_3_storage___ws
from tests.tier1_offline.test_p0350_query_history import NEXT as _WORKSPACE_1_LEDGER__NEXT
from tests.tier1_offline.test_p0350_query_history import RUN as _WORKSPACE_1_LEDGER__RUN
from tests.tier1_offline.test_p0350_query_history import _record as _workspace_1_ledger___record
from tests.tier1_offline.test_p0350_query_history import _script as _workspace_1_ledger___script
from tests.tier1_offline.test_p0350_query_history import _write as _workspace_1_ledger___write
from tests.tier1_offline.test_workspace import make_record as _workspace_1_manifest__make_record


class TestIntegfixStorage:
    """Tier 1, 0.40.0 integration fixes: storage's free-space through the command line.

    A synthetic workspace and recipe; no solver runs.
    """

    @staticmethod
    def test_p0400_free_space_prints_a_delete_extensions_refusal(tmp_path, capsys):
        """P0400-EXT-SUBMITTED-PRINT (PFS-2093.006): the refused simulation is printed.

        delete_extensions records a simulation with a SUBMITTED run as refused, as the
        other two modes do, and the command line printed the other two modes' refusals
        only, so the preview said nothing of the simulation it left alone.
        """
        workspace = CampaignWorkspace(tmp_path / "camp")
        workspace.init(workspace.root)
        _integfix_storage___write(
            workspace.sim_dir("4601") / "datapoints" / "DP-1" / "a.vtk", "v" * 10
        )
        workspace.append_record(
            _integfix_storage___record("4601").model_copy(
                update={"status": _IntegfixStorageRunStatus.SUBMITTED}
            )
        )
        recipe = workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml"
        _integfix_storage___write(recipe, '[[delete_extensions]]\nextensions = [".vtk"]\n')
        capsys.readouterr()
        code = matrix_cli.main(["free-space", "m001", "--workspace", str(workspace.root)])
        out = capsys.readouterr().out
        assert code == 0, out
        assert "refused sim 4601: a run is still SUBMITTED" in out, out


_WORKSPACE_1_BATCH_LIFE__LABEL = "matriz_b1"


def _workspace_1_batch_life___job(**values):
    return {
        "kind": "batch",
        "name": _WORKSPACE_1_BATCH_LIFE__LABEL,
        "batch_id": 1,
        "label": _WORKSPACE_1_BATCH_LIFE__LABEL,
        "dir": f"sims/batch/{_WORKSPACE_1_BATCH_LIFE__LABEL}",
        "script": f"sims/batch/{_WORKSPACE_1_BATCH_LIFE__LABEL}/BATCH-1-1.txt",
        "root": ".",
        "executor": "submitting",
        "values": dict(values),
        "order": 1,
        "points": 1,
        "receipt_sha256": "0" * 64,
    }


def _workspace_1_batch_life___batch(tmp_path, *, fired: bool):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    point = (
        workspace.root
        / "sims"
        / "batch"
        / _WORKSPACE_1_BATCH_LIFE__LABEL
        / "sim_1"
        / "datapoints"
        / "DP-A"
    )
    (point / "actions").mkdir(parents=True)
    state = {"fired": fired, "steps": 40, "stopped_at": {"step": 40}}
    (point / "actions" / "pfs_walltime_clock.json").write_text(json.dumps(state), "utf-8")
    rows = [{"sim_id": "1", "submission": {"job": _workspace_1_batch_life___job()}}]
    return workspace, rows


def _workspace_1_batch_life___collect_says(workspace, job):
    return job_ended(
        workspace,
        job,
        profile=None,
        observer=lambda paths: {str(p): 1 for p in paths},
        settled=lambda first, second: first == second,
        sleep=lambda seconds: None,
        interval=0.0,
    ).ended


class TestWorkspace1BatchLife:
    """P0400-WSBATCH: the workspace's batch end verdict and sync rule (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSBATCH")

    @staticmethod
    @pytest.mark.parametrize("fired", [True, False], ids=["clock-fired", "no-evidence"])
    def test_p0400_wsbatch_the_workspace_and_collect_agree_on_a_fired_clock(tmp_path, fired):
        """P0400-WSBATCH (PFS-2094.041, PFS-2094.044): a fired clock ends the batch for both layers."""  # noqa: E501
        workspace, rows = _workspace_1_batch_life___batch(tmp_path, fired=fired)
        assert (
            _workspace_1_batch_life___collect_says(workspace, _workspace_1_batch_life___job())
            is fired
        )
        running = batch_life.running_batches(workspace.root, rows)
        assert (_WORKSPACE_1_BATCH_LIFE__LABEL not in running) is fired, running

    @staticmethod
    @pytest.mark.parametrize(
        ("pattern", "values"),
        [
            ("FTS{sim}.o*", {}),
            ("FTS{ncpus:.2f}.o*", {"ncpus": []}),
            ("FTS{sim.missing}.o*", {"sim": "1"}),
        ],
    )
    def test_p0400_wsbatch_an_unformattable_end_glob_is_said(
        tmp_path, monkeypatch, pattern, values
    ):
        """P0400-WSBATCH (PFS-2094.050): a glob naming a value the job did not record warns."""
        workspace, rows = _workspace_1_batch_life___batch(tmp_path, fired=False)
        rows[0]["submission"]["job"] = _workspace_1_batch_life___job(**values)
        if values:
            # Exercise the formatter independently of the file reader's stricter grammar.
            monkeypatch.setattr(batch_life, "_end_globs", lambda root: (pattern,))
        else:
            _workspace_1_batch_life___write_profile(
                workspace,
                _WORKSPACE_1_BATCH_LIFE__LOG_TABLE + f"job_end_files = [{json.dumps(pattern)}]\n",
            )
        with pytest.warns(PyflightstreamWarning, match="cannot be formatted") as seen:
            running = batch_life.running_batches(workspace.root, rows)
        assert _WORKSPACE_1_BATCH_LIFE__LABEL in running
        assert pattern in str(seen[0].message)

    @staticmethod
    def test_p0400_wsbatch_sync_takes_every_log_by_one_rule(tmp_path):
        """P0400-WSBATCH (PFS-2087.002): a sim and a batch sim bring the same logs, any case."""
        other = CampaignWorkspace.init(tmp_path / "other")
        names = ("FlightStreamLog.txt", "fs_runtime_output.txt", "P1-A_log.txt", "solver.log")
        home, batch = (
            other.sim_dir("1"),
            other.root / "sims" / "batch" / _WORKSPACE_1_BATCH_LIFE__LABEL / "sim_2",
        )
        for sim in (home, batch):
            for name in (*names, "loads.vtk"):
                target = sim / "datapoints" / "DP-A" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
        other.append_record(_workspace_1_batch_life___record("1", "camp/sim_1/AL+000"))
        copied = _workspace_1_batch_life___copied_paths(tmp_path, other.root, "runs", "logs")
        for sim in ("sims/sim_1", f"sims/batch/{_WORKSPACE_1_BATCH_LIFE__LABEL}/sim_2"):
            for name in names:
                assert f"{sim}/datapoints/DP-A/{name}" in copied, (sim, name, sorted(copied))
            assert f"{sim}/datapoints/DP-A/loads.vtk" not in copied


_WORKSPACE_1_LEDGER__CLUSTER = "/scratch/user/sample"


def _workspace_1_ledger___two_runs(
    tmp_path, *, script_a: str, script_b: str, cwd_a: str, cwd_b: str, folder="scripts"
):
    path_a, sha_a = _workspace_1_ledger___script(
        tmp_path, f"sims/sim_2006/{folder}/a.txt", script_a
    )
    path_b, sha_b = _workspace_1_ledger___script(
        tmp_path, f"sims/sim_2006/{folder}/b.txt", script_b
    )
    rows = [
        _workspace_1_ledger___record(script_path=f"{folder}/a.txt", script_sha256=sha_a, cwd=cwd_a),
        _workspace_1_ledger___record(
            _WORKSPACE_1_LEDGER__NEXT, script_path=f"{folder}/b.txt", script_sha256=sha_b, cwd=cwd_b
        ),
    ]
    _workspace_1_ledger___write(tmp_path / "runs.json", rows)
    return tmp_path


def _workspace_1_ledger___scripts(root: str) -> str:
    return f'LOAD_FILE\n"{root}/inputs/geometries/wing.fsm"\nSOLVER_SET_AOA\n2\n'


def _workspace_1_ledger___activity_log(tmp_path, *lines: str):
    _workspace_1_ledger___write(tmp_path / "runs.json", [_workspace_1_ledger___record()])
    log = tmp_path / "logs" / "activity.log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


_WORKSPACE_1_LEDGER__GOOD = (
    '{"timestamp": "2026-10-01T12:00:00Z", "event": "started", "stage": "run"}'
)


class TestWorkspace1Ledger:
    """P0400-WSLEDGER: ledger diff, the activity log reader and the query API's refusals.

    0.40.0 lane workspace-1. Each test is the regression of one planning node and
    fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSLEDGER")

    @staticmethod
    def test_p0400_wsledger_a_local_and_a_cluster_run_of_one_script_do_not_differ(tmp_path):
        """P0400-WSLEDGER (PFS-2103.013): each side is normalised by its own root, either order."""
        local = tmp_path.as_posix()
        root = _workspace_1_ledger___two_runs(
            tmp_path,
            script_a=_workspace_1_ledger___scripts(local),
            script_b=_workspace_1_ledger___scripts(_WORKSPACE_1_LEDGER__CLUSTER),
            cwd_a=f"{local}/sims/sim_2006/datapoints/DP-A0",
            cwd_b=f"{_WORKSPACE_1_LEDGER__CLUSTER}/sims/sim_2006/datapoints/DP-A0",
        )
        for first, second in (
            (_WORKSPACE_1_LEDGER__RUN, _WORKSPACE_1_LEDGER__NEXT),
            (_WORKSPACE_1_LEDGER__NEXT, _WORKSPACE_1_LEDGER__RUN),
        ):
            fields = [row["field"] for row in diff(root, first, second)]
            assert "script_comparison" not in fields, (first, fields)

    @staticmethod
    def test_p0400_wsledger_a_real_change_between_two_runs_is_still_named(tmp_path):
        """P0400-WSLEDGER (PFS-2103.013): the control, a changed command is reported."""
        local = tmp_path.as_posix()
        root = _workspace_1_ledger___two_runs(
            tmp_path,
            script_a=_workspace_1_ledger___scripts(local),
            script_b=_workspace_1_ledger___scripts(_WORKSPACE_1_LEDGER__CLUSTER).replace(
                "\n2\n", "\n4\n"
            ),
            cwd_a=f"{local}/sims/sim_2006/datapoints/DP-A0",
            cwd_b=f"{_WORKSPACE_1_LEDGER__CLUSTER}/sims/sim_2006/datapoints/DP-A0",
        )
        rows = {
            row["field"]: row
            for row in diff(root, _WORKSPACE_1_LEDGER__RUN, _WORKSPACE_1_LEDGER__NEXT)
        }
        assert "SOLVER_SET_AOA | 2" in rows["script_comparison"]["detail"]
        assert "geometries" not in rows["script_comparison"]["detail"]
        assert ": a " in rows["script_comparison"]["detail"]
        assert ", b " in rows["script_comparison"]["detail"]
        assert "renders" not in rows["script_comparison"]["detail"]

    @staticmethod
    def test_p0400_wsledger_the_recorded_script_path_is_read_in_the_simulation_folder(tmp_path):
        """P0400-WSLEDGER (PFS-2103.039): script_path is relative to the simulation folder."""
        shared = tmp_path / "shared"
        shared.mkdir()
        (tmp_path / "sims" / "sim_2006").mkdir(parents=True)
        _make_dir_link(shared, tmp_path / "sims" / "sim_2006" / "linked")
        text = _workspace_1_ledger___scripts(tmp_path.as_posix())
        root = _workspace_1_ledger___two_runs(
            tmp_path, script_a=text, script_b=text, cwd_a="", cwd_b="", folder="linked"
        )
        rows = {
            row["field"]: row
            for row in diff(root, _WORKSPACE_1_LEDGER__RUN, _WORKSPACE_1_LEDGER__NEXT)
        }
        assert "script_comparison" not in rows, rows.get("script_comparison")

    @staticmethod
    def test_p0400_wsledger_a_malformed_additional_register_is_a_workspace_error(tmp_path):
        """P0400-WSLEDGER (PFS-2095.028): additional_rows raises the class it documents."""
        _workspace_1_ledger___write(tmp_path / "runs.json", [_workspace_1_ledger___record()])
        _workspace_1_ledger___write(tmp_path / "additional.json", {"not": "a list"})
        with pytest.raises(WorkspaceError, match="additional"):
            additional_rows(tmp_path)

    @staticmethod
    def test_p0400_wsledger_a_malformed_post_log_is_a_workspace_error(tmp_path):
        """P0400-WSLEDGER (PFS-2095.028): post_log_groups raises the class it documents."""
        _workspace_1_ledger___write(tmp_path / "runs.json", [_workspace_1_ledger___record()])
        _workspace_1_ledger___write(
            tmp_path / "post" / "sample" / "post.log.json", {"records": "none"}
        )
        with pytest.raises(WorkspaceError, match="post"):
            post_log_groups(tmp_path, "sample")

    @staticmethod
    def test_p0400_wsledger_an_invalid_since_filter_is_a_workspace_error(tmp_path):
        """P0400-WSLEDGER (PFS-2095.028): an invalid filter raises the documented class."""
        with pytest.raises(WorkspaceError, match="since"):
            activity_rows(
                _workspace_1_ledger___activity_log(tmp_path, _WORKSPACE_1_LEDGER__GOOD),
                since="yesterday",
            )

    @staticmethod
    @pytest.mark.parametrize(
        "bad",
        [
            '{"timestamp": "2026-10-01T12:05:00Z", "event": "fini',
            '["not", "an", "object"]',
            '{"timestamp": "yesterday", "event": "finished", "stage": "run"}',
        ],
        ids=["torn", "not-an-object", "non-iso-time"],
    )
    def test_p0400_wsledger_one_bad_activity_line_is_named_and_the_rest_is_read(tmp_path, bad):
        """P0400-WSLEDGER (PFS-2081.25): a torn or malformed line warns; the query still answers."""
        root = _workspace_1_ledger___activity_log(tmp_path, _WORKSPACE_1_LEDGER__GOOD, bad)
        with pytest.warns(PyflightstreamWarning, match="line 2"):
            rows = activity_rows(root)
        assert [row["event"] for row in rows] == ["started"]

    @staticmethod
    def test_p0400_wsledger_a_sim_id_is_not_read_inside_a_longer_one(tmp_path):
        """P0400-WSLEDGER (PFS-2094.043): sims 20 does not select the events of sim 20-b."""
        root = _workspace_1_ledger___activity_log(
            tmp_path,
            '{"timestamp": "2026-10-01T12:00:00Z", "event": "started", "detail": "sims/sim_20/x"}',
            '{"timestamp": "2026-10-01T12:01:00Z", "event": "failed", "detail": "sims/sim_20-b/x"}',
            '{"event": "suffix", "detail": "sims/sim_prefix-sim_20/x"}',
        )
        assert [row["event"] for row in activity_rows(root, sims=["20"])] == ["started"]
        assert [row["event"] for row in activity_rows(root, sims=["20-b"])] == ["failed"]

    @staticmethod
    def test_p0400_wsledger_explicit_sim_ids_win_over_mentions_in_details(tmp_path):
        """P0400-WSLEDGER (PFS-2094.043): structured simulation identity wins over text."""
        root = _workspace_1_ledger___activity_log(
            tmp_path,
            '{"sim_id": "20-b", "event": "other", "detail": "copied from sim_20/x"}',
            '{"sims": ["20-b"], "event": "batch", "detail": "copied from sim_20/x"}',
        )
        assert activity_rows(root, sims=["20"]) == []


class TestWorkspace1Manifest:
    """P0400-WSMANIFEST: reading the manifest's per-point entries (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSMANIFEST")

    @staticmethod
    @pytest.mark.parametrize(
        ("entry", "named"),
        [
            ({"tag": "AL+000", "status": "EXPLODED"}, "status 'EXPLODED'"),
            ({"tag": 7, "status": "CONVERGED"}, "tag 7"),
        ],
        ids=["unknown-status", "tag-not-text"],
    )
    def test_p0400_wsmanifest_an_unreadable_points_ran_entry_is_refused_when_read(
        tmp_path, entry, named
    ):
        """P0400-WSMANIFEST (PFS-2093.005): the row is unreadable at read, not later in as_points."""  # noqa: E501
        workspace = CampaignWorkspace(tmp_path)
        workspace.append_record(
            _workspace_1_manifest__make_record(
                points_ran=[{"tag": "AL+000", "status": "CONVERGED"}]
            )
        )
        rows = _read_record_rows(workspace.manifest_path)
        rows[0]["points_ran"] = [entry]
        workspace._replace_manifest(rows)
        with pytest.raises(WorkspaceError, match=named) as caught:
            workspace.read_manifest()
        assert "row 1" in str(caught.value) and "points_ran" in str(caught.value)

    @staticmethod
    def test_p0400_wsmanifest_a_known_points_ran_entry_still_reads():
        """P0400-WSMANIFEST (PFS-2093.005): the guard refuses nothing a release writes."""
        record = _workspace_1_manifest__make_record(
            points_ran=[{"tag": "AL+000", "status": "CONVERGED"}, {"tag": None}]
        )
        assert [point.point_name for point in record.as_points()] == ["AL+000", None]


_WORKSPACE_1_SIDECARS__NAMES = ["Wing\\tip", 'Say "hi"', "Plain"]


class TestWorkspace1Sidecars:
    """P0400-WSSIDECAR: a saved simulation's boundary inventory is valid TOML (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """  # noqa: E501

    pytestmark = pytest.mark.requirement("P0400-WSSIDECAR")

    @staticmethod
    def test_p0400_wssidecar_names_with_a_backslash_or_a_quote_read_back_unchanged(tmp_path):
        """P0400-WSSIDECAR (PFS-2095.034): each name and the file value is a quoted TOML string."""
        geometry = _workspace_1_sidecars__saved_mesh_fixture(
            tmp_path / "wing.fsm", _WORKSPACE_1_SIDECARS__NAMES
        )
        written = write_inventory(geometry)
        data = tomllib.loads(written.read_text(encoding="utf-8"))
        assert data["boundaries"] == _WORKSPACE_1_SIDECARS__NAMES
        assert data["file"] == geometry.name


_WORKSPACE_1_STORAGE___COMPACT = '[[compact_sims]]\nsims = "all"\n'


def _workspace_1_storage___one_sim(tmp_path):
    workspace = _workspace_1_storage___ws(tmp_path)
    sim = workspace.sim_dir("1201")
    _workspace_1_storage___write(sim / "datapoints" / "DP-1" / "loads.vtk", "payload")
    workspace.append_record(_workspace_1_storage___record("1201", "camp/sim_1201/AL+000"))
    return workspace, sim


class TestWorkspace1Storage:
    """P0400-WSSTORAGE: storage recipes are judged whole before any file moves.

    0.40.0 lane workspace-1.

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSSTORAGE")

    @staticmethod
    @pytest.mark.parametrize(
        ("later", "named"),
        [
            ('[[delete_extensions]]\nextensions = [".fsm"]\n', "never deleted by a recipe"),
            ('[[post_archives]]\nkeep_latest = "two"\n', "keep_latest is a whole number"),
            ('[[post_archives]]\naction = "shred"\n', 'action is "compact" or "delete"'),
            ('[[delete_extensions]]\nextensions = [".vtk"]\nsims = ["9999"]\n', "9999"),
        ],
        ids=["fsm", "keep-latest-text", "action", "sims-without-folder"],
    )
    def test_p0400_wsstorage_a_later_bad_table_stops_the_recipe_before_the_first_step(
        tmp_path, later, named
    ):
        """P0400-WSSTORAGE (PFS-2096.028): a valid compaction is not run before a refused table."""
        workspace, sim = _workspace_1_storage___one_sim(tmp_path)
        _workspace_1_storage___write_recipe(
            workspace, "m001", _WORKSPACE_1_STORAGE___COMPACT + later
        )
        with pytest.raises(storage_module.StorageError, match=re.escape(named)):
            storage_module.free_space(workspace.root, "m001", apply=True)
        assert sim.is_dir() and (sim / "datapoints" / "DP-1" / "loads.vtk").is_file()
        assert not sim.with_name(sim.name + storage_module.COMPACTED_SUFFIX).exists()

    @staticmethod
    @pytest.mark.parametrize(
        ("table", "named"),
        [
            ("[[post_archives]]\nkeep_last = 2\n", "keep_last is spelled keep_latest here"),
            ("[[compact_sims]]\nolder_than = 3\n", "[[compact_sims]] does not read ['older_than']"),
            ('[[delete_extensions]]\nextensions = [".vtk"]\nstatuses = ["FAILED"]\n', "statuses"),
            ("[[post_archives]]\nkeep_latest = -1\n", "keep_latest is a whole number"),
        ],
        ids=["keep-last", "older-than", "statuses", "negative-keep"],
    )
    def test_p0400_wsstorage_a_key_no_table_reads_is_refused_by_name(tmp_path, table, named):
        """P0400-WSSTORAGE (PFS-2093.007): a misspelt key is no silent widest default."""
        workspace, sim = _workspace_1_storage___one_sim(tmp_path)
        _workspace_1_storage___write_recipe(workspace, "m001", table)
        with pytest.raises(storage_module.StorageError, match=re.escape(named)):
            storage_module.free_space(workspace.root, "m001", apply=True)

    @staticmethod
    def test_p0400_wsstorage_a_status_string_is_refused_as_a_list(tmp_path):
        """P0400-WSSTORAGE (PFS-2097.020): status = "CONVERGED" names the list form and the recipe."""  # noqa: E501
        workspace, _ = _workspace_1_storage___one_sim(tmp_path)
        _workspace_1_storage___write_recipe(
            workspace, "m001", '[[compact_sims]]\nstatus = "CONVERGED"\n'
        )
        with pytest.raises(storage_module.StorageError) as refused:
            storage_module.free_space(workspace.root, "m001")
        assert 'status = ["CONVERGED"]' in str(refused.value)
        assert "m001.toml" in str(refused.value)

    @staticmethod
    def test_p0400_wsstorage_an_unknown_status_lists_the_statuses_and_the_recipe(tmp_path):
        """P0400-WSSTORAGE (PFS-2097.020): an unknown name lists every RunStatus and the recipe."""
        workspace, _ = _workspace_1_storage___one_sim(tmp_path)
        _workspace_1_storage___write_recipe(
            workspace, "m001", '[[compact_sims]]\nstatus = ["CONVERGD"]\n'
        )
        with pytest.raises(storage_module.StorageError) as refused:
            storage_module.free_space(workspace.root, "m001")
        assert "m001.toml" in str(refused.value) and "CONVERGED" in str(refused.value)

    @staticmethod
    @pytest.mark.parametrize("source", ["absent", "main"])
    def test_p0400_wsstorage_sync_refusals_name_the_python_keyword(tmp_path, source):
        """P0400-WSSTORAGE (PFS-2100.018): the refusal names source and --from."""
        main, _ = _workspace_1_storage___sync_pair(tmp_path, "source")
        with pytest.raises(storage_module.StorageError, match=r"source \(CLI: --from\)"):
            storage_module.sync_workspaces(main.root, "runs", source=source)


_WORKSPACE_2_MANIFEST___MARK = {
    "from": "CONVERGED",
    "at": "2026-10-12T12:00:00",
    "reason": "wrong mesh",
}


def _workspace_2_manifest___job(**fields) -> RunRecord:
    row = {
        "run_id": "campaign/sim_7002/sweep",
        "sim_id": "7002",
        "fs_version_requested": "26.120",
        "package_version": "0.40.0",
        "script_sha256": "0" * 64,
        "raw_flag": False,
        "status": "CONVERGED",
        "points_ran": [
            {"tag": "A0", "status": "CONVERGED", "point": {"ALPHA": 0.0}},
            {"tag": "A4", "status": "CONVERGED", "point": {"ALPHA": 4.0}},
        ],
    }
    row.update(fields)
    return RunRecord.model_validate(row)


class TestWorkspace2Manifest:
    """P0400-JOBPOINTS: a steady job's per-point records keep the job's verdict and their own limit."""  # noqa: E501

    @staticmethod
    def test_p0400_jobpoints_a_job_marked_failed_fails_every_unmarked_point():
        """P0400-JOBPOINTS (PFS-2103.014): mark-failed writes FAILED_MARKED and the mark on the job
        row only; every point of it comes back FAILED_MARKED, not its entry's CONVERGED."""
        job = _workspace_2_manifest___job(
            status="FAILED_MARKED", marked=_WORKSPACE_2_MANIFEST___MARK
        )
        points = job.as_points()
        assert [p.status for p in points] == [
            _Workspace2ManifestRunStatus.FAILED_MARKED,
            _Workspace2ManifestRunStatus.FAILED_MARKED,
        ]
        assert all(p.marked == _WORKSPACE_2_MANIFEST___MARK for p in points)

    @staticmethod
    def test_p0400_jobpoints_a_point_verdict_of_its_own_stands_under_a_failed_job():
        """P0400-JOBPOINTS (PFS-2103.014): a point a person marked on its own keeps that verdict."""
        own = {"from": "FAILED_MARKED", "at": "2026-10-12T13:00:00", "reason": "checked"}
        job = _workspace_2_manifest___job(
            status="FAILED_MARKED", marked=_WORKSPACE_2_MANIFEST___MARK
        )
        job.points_ran[1].update(status="CONVERGED", marked=own)
        assert [p.status for p in job.as_points()] == [
            _Workspace2ManifestRunStatus.FAILED_MARKED,
            _Workspace2ManifestRunStatus.CONVERGED,
        ]

    @staticmethod
    def test_p0400_jobpoints_each_point_keeps_its_own_limit_and_note():
        """P0400-JOBPOINTS (PFS-2103.015): the job row carries what _record_sweep_outcome writes (no
        note, no limit) and the MAX_ITER_REACHED entry carries its own; the per-point record keeps
        the entry's, so the post's warning names the limit."""
        job = _workspace_2_manifest___job(status="MAX_ITER_REACHED")
        job.points_ran[0].update(
            status="MAX_ITER_REACHED",
            iterations_requested=500,
            residual_note="unsettled at the iteration limit (500)",
        )
        first, second = job.as_points()
        assert first.iterations_requested == 500
        assert first.residual_note == "unsettled at the iteration limit (500)"
        assert second.iterations_requested is None and second.residual_note is None

    @staticmethod
    def test_p0400_jobpoints_mark_failed_withholds_job_points_from_post(tmp_path):
        """Exercise the writer, expansion and post admission together."""
        from pyflightstream.post._products_campaign import _admit_campaign_records
        from pyflightstream.run.records import mark_failed
        from pyflightstream.workspace import CampaignWorkspace

        workspace = CampaignWorkspace(tmp_path)
        workspace.append_record(_workspace_2_manifest___job())
        mark_failed(tmp_path, ["7002"], reason="wrong mesh", apply=True)
        records = workspace.read_manifest()
        assert all(
            p.status == _Workspace2ManifestRunStatus.FAILED_MARKED
            for r in records
            for p in r.as_points()
        )
        admitted, skipped = {}, {}
        _admit_campaign_records(
            workspace,
            records,
            sims=None,
            superseded={},
            check_frozen=True,
            by_sim=admitted,
            skipped=skipped,
        )
        assert admitted == {}
        assert len(skipped) == 2
        assert all("FAILED_MARKED" in reason for reason in skipped.values())


_WORKSPACE_3_SIDECARS__CP1252_TOML = 'name = "référence"\n'.encode("cp1252")


class TestWorkspace3Sidecars:
    """P0400-WS3-SIDECARS: geometry sidecar readers and the geometry layout migration."""

    @staticmethod
    def test_p0400_load_toml_names_a_file_that_is_not_utf8(tmp_path: Path):
        """P0400-TOML-UTF8 (PFS-2095.035): a cp1252 artifact is refused by name, not by codec."""
        path = tmp_path / "setup.toml"
        path.write_bytes(_WORKSPACE_3_SIDECARS__CP1252_TOML)
        with pytest.raises(InputArtifactError) as raised:
            load_toml(path, "setup")
        message = str(raised.value)
        assert str(path) in message and "UTF-8" in message, message

    @staticmethod
    def test_p0400_load_toml_accepts_a_byte_order_mark(tmp_path: Path):
        """P0400-TOML-BOM (PFS-2095.035): a UTF-8 file with a BOM, as PowerShell 5.1 writes, reads."""  # noqa: E501
        path = tmp_path / "setup.toml"
        path.write_bytes(b"\xef\xbb\xbf" + b'name = "x"\n')
        assert load_toml(path, "setup") == {"name": "x"}

    @staticmethod
    def test_p0400_a_sidecar_that_is_not_utf8_is_refused_by_name(tmp_path: Path):
        """P0400-SIDECAR-UTF8 (PFS-2095.035): the sidecar reader names a cp1252 sidecar."""
        sidecar = tmp_path / "wing.boundaries.toml"
        sidecar.write_bytes('boundaries = ["Étage"]\n'.encode("cp1252"))
        with pytest.raises(InputArtifactError) as raised:
            read_inventory(sidecar)
        message = str(raised.value)
        assert str(sidecar) in message and "UTF-8" in message, message


_Workspace3StorageStorageError = storage_module.StorageError


_WORKSPACE_3_STORAGE__DELETED = storage_module.DELETED_SIM_KEY


def _workspace_3_storage___recorded_sim(
    workspace, sim_id: str, files: dict[str, str], **record
) -> None:
    for name, text in files.items():
        _workspace_3_storage___write(workspace.sim_dir(sim_id) / name, text)
    workspace.append_record(
        _workspace_3_storage___record(sim_id, f"camp/sim_{sim_id}/AL+000", **record)
    )


def _workspace_3_storage___zip(workspace, sim_id: str) -> Path:
    """The archive a compacted simulation is stored as, ``sims/sim_<id>.zip``."""
    folder = workspace.sim_dir(sim_id)
    return folder.with_name(folder.name + storage_module.COMPACTED_SUFFIX)


def _workspace_3_storage___compacted(workspace, sim_id: str, files: dict[str, str]) -> Path:
    """Write, record and compact one simulation; return its archive."""
    _workspace_3_storage___recorded_sim(workspace, sim_id, files)
    _workspace_3_storage___write_recipe(
        workspace, "m901", f'[[compact_sims]]\nsims = ["{sim_id}"]\n'
    )
    storage_module.free_space(workspace.root, "m901", apply=True)
    archive = _workspace_3_storage___zip(workspace, sim_id)
    assert archive.is_file()
    return archive


def _workspace_3_storage___members(archive: Path) -> set[str]:
    with zipfile.ZipFile(archive) as zf:
        return set(zf.namelist())


def _workspace_3_storage___rows(workspace) -> list[dict]:
    return _read_record_rows(workspace.manifest_path)


_WORKSPACE_3_STORAGE__FULL = {"scripts/point.fs": "s", "datapoints/DP-1/loads.txt": "full"}


# --------------------------------------------------------------------------- PFS-2096.015, .011
def _workspace_3_storage___synced_linked_archive(tmp_path: Path, tag: str, *, main_has_wing: bool):
    main, other = _workspace_3_storage___sync_pair(tmp_path, tag)
    _workspace_3_storage___linked_sim(other, "4201")
    other.append_record(_workspace_3_storage___record("4201", "camp/sim_4201/AL+000"))
    _workspace_3_storage___write_recipe(other, "m901", '[[compact_sims]]\nsims = ["4201"]\n')
    storage_module.free_space(other.root, "m901", apply=True)
    if main_has_wing:
        _workspace_3_storage___write(
            main.inputs_dir / "geometries" / "wing" / "wing.obj", "o wing\n"
        )
    storage_module.sync_workspaces(main.root, "all", apply=True)
    assert _workspace_3_storage___zip(main, "4201").is_file()
    return main, other


# --------------------------------------------------------------------------- PFS-2096.026
class _Workspace3StorageClock(dt.datetime):
    """Local 09:00, and UTC three hours later, as on a machine at UTC-3."""

    @classmethod
    def now(cls, tz=None):
        local = dt.datetime(2026, 10, 12, 9, 0, 0)
        return local if tz is None else (local + dt.timedelta(hours=3)).replace(tzinfo=tz)


# --------------------------------------------------------------------------- PFS-2094.047
def _workspace_3_storage___exited_pid() -> int:
    done = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    return int(done.stdout)


class TestWorkspace3Storage:
    """P0400-WS3-STORAGE: storage commands keep every copy, lease and record they owe."""

    @staticmethod
    # --------------------------------------------------------------------------- PFS-2096.014
    def test_p0400_compacting_a_folder_beside_an_archive_is_refused_and_the_archive_kept(tmp_path):
        """P0400-COMPACT-OVER-ZIP (PFS-2096.014): a second compaction never replaces the zip."""
        workspace = _workspace_3_storage___ws(tmp_path, "overzip")
        archive = _workspace_3_storage___compacted(workspace, "4101", _WORKSPACE_3_STORAGE__FULL)
        members = _workspace_3_storage___members(archive)
        _workspace_3_storage___write(workspace.sim_dir("4101") / "scripts" / "point.fs", "partial")
        entry = storage_module.free_space(workspace.root, "m901", apply=True)
        assert "4101" in entry["steps"][0]["refused"], entry["steps"]
        assert _workspace_3_storage___members(archive) == members

    @staticmethod
    def test_p0400_a_restore_refuses_a_folder_beside_the_archive_naming_both(tmp_path):
        """P0400-RESTORE-BOTH (PFS-2096.014): the folder and the zip together are refused."""
        workspace = _workspace_3_storage___ws(tmp_path, "both")
        archive = _workspace_3_storage___compacted(workspace, "4102", _WORKSPACE_3_STORAGE__FULL)
        _workspace_3_storage___write(workspace.sim_dir("4102") / "scripts" / "point.fs", "partial")
        with pytest.raises(_Workspace3StorageStorageError) as raised:
            storage_module.ensure_sim_expanded(workspace, "4102", reason="test")
        message = str(raised.value)
        assert str(archive) in message and str(workspace.sim_dir("4102")) in message

    @staticmethod
    def test_p0400_sync_restores_a_compacted_simulation_before_copying_into_it(tmp_path):
        """P0400-SYNC-INTO-ZIP (PFS-2096.014): sync expands main's archive, then copies."""
        main, other = _workspace_3_storage___sync_pair(tmp_path, "zipsync")
        archive = _workspace_3_storage___compacted(main, "4103", _WORKSPACE_3_STORAGE__FULL)
        _workspace_3_storage___write(other.sim_dir("4103") / "scripts" / "point.fs", "s")
        _workspace_3_storage___write(
            other.sim_dir("4103") / "datapoints" / "DP-1" / "run_log.txt", "log"
        )
        (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
        assert entry["expanded"] == ["4103"]
        assert not archive.exists()
        folder = main.sim_dir("4103") / "datapoints" / "DP-1"
        assert (folder / "loads.txt").read_text(encoding="utf-8") == "full"
        assert (folder / "run_log.txt").is_file()

    @staticmethod
    def test_p0400_a_synced_archive_restores_its_inputs_link_into_mains_library(tmp_path):
        """P0400-RESTORE-RELINK (PFS-2096.015): the link goes to main's library, not the other's."""
        main, _ = _workspace_3_storage___synced_linked_archive(
            tmp_path, "relinkzip", main_has_wing=True
        )
        assert storage_module.ensure_sim_expanded(main, "4201", reason="test")
        inputs = main.sim_dir("4201") / "inputs"
        assert (inputs / "wing.obj").is_file(), "inputs/ is not the link into main's library"
        assert Path(os.path.realpath(inputs)) == (main.inputs_dir / "geometries" / "wing").resolve()

    @staticmethod
    def test_p0400_a_restore_that_cannot_link_inputs_records_it_and_warns(tmp_path):
        """P0400-RESTORE-NOLINK (PFS-2085.011): an empty inputs folder is recorded and warned."""
        main, other = _workspace_3_storage___synced_linked_archive(
            tmp_path, "nolink", main_has_wing=False
        )
        with pytest.warns(PyflightstreamWarning, match="empty folder"):
            assert storage_module.ensure_sim_expanded(main, "4201", reason="test")
        entry = storage_module.read_storage_calls(main.root)[-1]
        assert entry["action"] == "restore"
        assert entry["inputs_link_restored"] is False
        recorded = Path(entry["inputs_link_target"])
        assert recorded == (other.inputs_dir / "geometries" / "wing").resolve()

    @staticmethod
    # --------------------------------------------------------------------------- PFS-2096.016
    def test_p0400_two_readers_of_one_compacted_simulation_restore_it_once(tmp_path, monkeypatch):
        """P0400-RESTORE-RACE (PFS-2096.016): the second reader waits and finds it restored."""
        workspace = _workspace_3_storage___ws(tmp_path, "tworeaders")
        archive = _workspace_3_storage___compacted(
            workspace,
            "4301",
            {
                **_WORKSPACE_3_STORAGE__FULL,
                "datapoints/DP-1/a.txt": "a",
                "datapoints/DP-1/b.txt": "b",
            },
        )
        results: dict[str, bool] = {}
        errors: list[BaseException] = []

        def reader(name: str) -> None:
            try:
                results[name] = storage_module.ensure_sim_expanded(workspace, "4301", reason=name)
            except BaseException as error:  # noqa: BLE001 - every failure is asserted on
                errors.append(error)

        second = threading.Thread(target=reader, args=("second",))
        real_extract = zipfile.ZipFile.extract

        def extract(self, member, path=None, pwd=None):
            if threading.current_thread() is threading.main_thread() and second.ident is None:
                second.start()
                second.join(timeout=3)
            return real_extract(self, member, path, pwd)

        monkeypatch.setattr(zipfile.ZipFile, "extract", extract)
        reader("first")
        second.join(timeout=120)
        assert not errors, errors
        assert sorted(results.values()) == [False, True], results
        assert not list((workspace.root / "sims").glob("*.restoring"))
        assert not archive.exists()
        assert (workspace.sim_dir("4301") / "datapoints" / "DP-1" / "b.txt").is_file()

    @staticmethod
    def test_p0440_rb5_26_same_clock_deletes_have_distinct_record_ids(tmp_path, monkeypatch):
        """P0400-ARCHIVE-CLOCK (PFS-2096.026): restore takes the newest copy, and none is lost."""
        monkeypatch.setattr(dt, "datetime", _Workspace3StorageClock)
        workspace = _workspace_3_storage___ws(tmp_path, "clock")
        for sim in ("4401", "4402", "4403"):
            _workspace_3_storage___recorded_sim(workspace, sim, {"scripts/point.fs": "s"})
        first = storage_module.delete_sims(workspace.root, ["4401"], apply=True)
        second = storage_module.delete_sims(workspace.root, ["4402"], apply=True)
        assert first["delete_stamp"] != second["delete_stamp"]
        workspace.supersede_records(["camp/sim_4403/AL+000"], stamp=dt.datetime(2026, 10, 12, 9))
        archives = sorted((workspace.root / ARCHIVE_DIR).glob("runs-*.json"))
        assert len(archives) == 3, [path.name for path in archives]
        chosen = restore(workspace.root, "runs")
        newest = _read_record_rows(workspace.root / chosen["source"])
        assert any(row.get(_WORKSPACE_3_STORAGE__DELETED) == "4402" for row in newest), chosen[
            "source"
        ]
        assert any(row.get("sim_id") == "4403" for row in newest), chosen["source"]

    @staticmethod
    # --------------------------------------------------------------------------- delete-sims
    def test_p0400_a_repeated_id_writes_one_tombstone(tmp_path):
        """P0400-DELETE-DEDUP (PFS-2103.041): one note row per simulation, run ids unique."""
        workspace = _workspace_3_storage___ws(tmp_path, "dedup")
        _workspace_3_storage___recorded_sim(workspace, "4501", {"scripts/point.fs": "s"})
        entry = storage_module.delete_sims(workspace.root, ["4501", "4501"], apply=True)
        rows = _workspace_3_storage___rows(workspace)
        assert len([row for row in rows if row.get(_WORKSPACE_3_STORAGE__DELETED) == "4501"]) == 1
        run_ids = [row["run_id"] for row in rows]
        assert len(run_ids) == len(set(run_ids))
        assert [item["sim_id"] for item in entry["sims"]] == ["4501"]

    @staticmethod
    def test_p0400_an_interrupted_delete_is_recorded_and_a_rerun_finishes_it(tmp_path, monkeypatch):
        """P0400-DELETE-INTENT (PFS-2086.005): the stop is recorded; the same delete finishes it."""
        workspace = _workspace_3_storage___shared_product_workspace(tmp_path, "interrupted")
        real = Path.replace

        def killed(self, target):
            if Path(target).name == "products.json":
                raise RuntimeError("killed while rewriting products.json")
            return real(self, target)

        monkeypatch.setattr(Path, "replace", killed)
        with pytest.raises(RuntimeError):
            storage_module.delete_sims(
                workspace.root, ["3001"], matrix_products="points-only", apply=True
            )
        assert not workspace.sim_dir("3001").exists()
        assert any(row.get("sim_id") == "3001" for row in _workspace_3_storage___rows(workspace))
        calls = [
            call
            for call in storage_module.read_storage_calls(workspace.root)
            if call["action"] == "delete-sims"
        ]
        assert any("intent" in call for call in calls), calls
        assert "killed while rewriting" in calls[-1]["interrupted"]
        monkeypatch.setattr(Path, "replace", real)
        storage_module.delete_sims(
            workspace.root, ["3001"], matrix_products="points-only", apply=True
        )
        rows = _workspace_3_storage___rows(workspace)
        assert not any(
            row.get("sim_id") == "3001" and _WORKSPACE_3_STORAGE__DELETED not in row for row in rows
        )
        assert [row for row in rows if row.get(_WORKSPACE_3_STORAGE__DELETED) == "3001"]

    @staticmethod
    @pytest.mark.parametrize("content", ['{"products": {"polar.csv": {', "[]", "null", "7"])
    def test_p0440_rb5_43_delete_refuses_unreadable_products(tmp_path, content):
        """P0400-DELETE-PRODUCTS (PFS-2086.006): a truncated products.json refuses, deleting nothing."""  # noqa: E501
        workspace = _workspace_3_storage___shared_product_workspace(tmp_path, "truncated")
        manifest = workspace.root / "post" / "matriz" / "products.json"
        manifest.write_text(content, encoding="utf-8")
        with pytest.raises(Exception) as raised:
            storage_module.delete_sims(workspace.root, ["3001"], apply=True)
        assert isinstance(raised.value, _Workspace3StorageStorageError)
        assert str(manifest) in str(raised.value)
        assert workspace.sim_dir("3001").is_dir()

    @staticmethod
    # --------------------------------------------------------------------------- free-space
    def test_p0400_delete_extensions_records_a_submitted_simulation_it_skips(tmp_path):
        """P0400-EXT-SUBMITTED (PFS-2093.006): the skipped simulation is recorded as refused."""
        workspace = _workspace_3_storage___ws(tmp_path, "extsubmitted")
        _workspace_3_storage___recorded_sim(
            workspace,
            "4601",
            {"datapoints/DP-1/a.vtk": "v"},
            status=_Workspace3StorageRunStatus.SUBMITTED,
        )
        _workspace_3_storage___write_recipe(
            workspace, "m902", '[[delete_extensions]]\nextensions = [".vtk"]\n'
        )
        entry = storage_module.free_space(workspace.root, "m902")
        assert "SUBMITTED" in entry["steps"][0]["refused"]["4601"]

    @staticmethod
    @pytest.mark.parametrize("value", ["-1", '"two"', "1.5", "true"])
    def test_p0400_post_archives_keep_latest_is_a_whole_number(tmp_path, value):
        """P0400-KEEP-LATEST (PFS-2096.017): keep_latest is refused unless an integer 0 or more."""
        workspace = _workspace_3_storage___ws(tmp_path, "keeplatest")
        stamp = workspace.root / "post" / "matriz" / ARCHIVE_DIR / "20260101-000000"
        _workspace_3_storage___write(stamp / "polar.csv", "old")
        _workspace_3_storage___write_recipe(
            workspace, "m904", f"[[post_archives]]\nkeep_latest = {value}\n"
        )
        with pytest.raises(_Workspace3StorageStorageError, match="keep_latest"):
            storage_module.free_space(workspace.root, "m904", apply=True)
        assert (stamp / "polar.csv").is_file()

    @staticmethod
    def test_p0400_a_later_step_naming_a_compacted_sim_is_refused_before_any_step(tmp_path):
        """P0400-RECIPE-CHECKED (PFS-2096.027): the preview refuses what the apply would."""
        workspace = _workspace_3_storage___ws(tmp_path, "checked")
        _workspace_3_storage___recorded_sim(
            workspace, "4901", {**_WORKSPACE_3_STORAGE__FULL, "datapoints/DP-1/a.vtk": "v"}
        )
        _workspace_3_storage___write_recipe(
            workspace,
            "m905",
            '[[compact_sims]]\nsims = ["4901"]\n\n'
            '[[delete_extensions]]\nsims = ["4901"]\nextensions = [".vtk"]\n',
        )
        with pytest.raises(_Workspace3StorageStorageError, match="4901"):
            storage_module.free_space(workspace.root, "m905")
        with pytest.raises(_Workspace3StorageStorageError, match="4901"):
            storage_module.free_space(workspace.root, "m905", apply=True)
        assert workspace.sim_dir("4901").is_dir()
        assert not _workspace_3_storage___zip(workspace, "4901").exists()

    @staticmethod
    def test_p0400_an_applied_recipe_that_stops_part_way_is_recorded(tmp_path, monkeypatch):
        """P0400-RECIPE-PARTIAL (PFS-2096.027): the steps done and the error are recorded."""
        workspace = _workspace_3_storage___ws(tmp_path, "partial")
        _workspace_3_storage___recorded_sim(workspace, "4911", _WORKSPACE_3_STORAGE__FULL)
        _workspace_3_storage___recorded_sim(workspace, "4912", _WORKSPACE_3_STORAGE__FULL)
        real = zipfile.ZipFile.write

        def second_fails(self, filename, *args, **kwargs):
            if "sim_4912" in str(filename):
                raise OSError("held open by another process")
            return real(self, filename, *args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "write", second_fails)
        _workspace_3_storage___write_recipe(workspace, "m906", '[[compact_sims]]\nsims = "all"\n')
        with pytest.raises(OSError, match="held open"):
            storage_module.free_space(workspace.root, "m906", apply=True)
        last = storage_module.read_storage_calls(workspace.root)[-1]
        assert last["action"] == "free-space" and last["applied"] is True
        assert "held open" in last["interrupted"]
        assert [item["sim_id"] for item in last["steps"][0]["sims"]] == ["4911"]

    @staticmethod
    def test_p0400_a_compaction_that_fails_while_zipping_leaves_no_partial_zip(
        tmp_path, monkeypatch
    ):
        """P0400-COMPACT-TMP (PFS-2096.029): the temporary zip is removed on a failed write."""
        workspace = _workspace_3_storage___ws(tmp_path, "ziptmp")
        _workspace_3_storage___recorded_sim(workspace, "4921", _WORKSPACE_3_STORAGE__FULL)

        def held_open(self, filename, arcname=None, *args, **kwargs):
            raise PermissionError(f"{filename} is held open")

        monkeypatch.setattr(zipfile.ZipFile, "write", held_open)
        _workspace_3_storage___write_recipe(workspace, "m907", '[[compact_sims]]\nsims = "all"\n')
        with pytest.raises(PermissionError):
            storage_module.free_space(workspace.root, "m907", apply=True)
        assert not list((workspace.root / "sims").glob("*.tmp"))
        assert workspace.sim_dir("4921").is_dir()

    @staticmethod
    def test_p0400_compaction_verifies_each_member_by_streaming_it(tmp_path, monkeypatch):
        """P0400-COMPACT-STREAM (PFS-2101.001): no member is read whole into memory."""
        workspace = _workspace_3_storage___ws(tmp_path, "stream")
        _workspace_3_storage___recorded_sim(workspace, "4931", _WORKSPACE_3_STORAGE__FULL)

        def whole(self, name, pwd=None):
            raise AssertionError(f"{name} was read whole into memory")

        monkeypatch.setattr(zipfile.ZipFile, "read", whole)
        _workspace_3_storage___write_recipe(workspace, "m908", '[[compact_sims]]\nsims = "all"\n')
        entry = storage_module.free_space(workspace.root, "m908", apply=True)
        assert [item["sim_id"] for item in entry["steps"][0]["sims"]] == ["4931"]

    @staticmethod
    def test_p0400_a_lock_left_by_a_dead_process_does_not_stop_free_space_which_holds_the_lease(
        tmp_path, monkeypatch
    ):
        """P0400-LEASE-DEAD (PFS-2094.047): the lease's rules recover it; free-space holds the lease."""  # noqa: E501
        workspace = _workspace_3_storage___ws(tmp_path, "deadlock")
        _workspace_3_storage___recorded_sim(workspace, "4701", _WORKSPACE_3_STORAGE__FULL)
        lock = workspace.root / "runs.json.lock"
        owner = {
            "pid": _workspace_3_storage___exited_pid(),
            "host": socket.gethostname(),
            "token": "gone",
        }
        lock.write_text(json.dumps(owner) + "\n", encoding="utf-8")
        held: list[bool] = []
        real = zipfile.ZipFile.write

        def watching(self, filename, *args, **kwargs):
            held.append(lock.exists())
            return real(self, filename, *args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "write", watching)
        _workspace_3_storage___write_recipe(workspace, "m903", '[[compact_sims]]\nsims = "all"\n')
        entry = storage_module.free_space(workspace.root, "m903", apply=True)
        assert [item["sim_id"] for item in entry["steps"][0]["sims"]] == ["4701"]
        assert held and all(held), held
        assert not lock.exists()

    @staticmethod
    def test_p0400_sync_reads_another_workspace_whose_lock_no_heartbeat_touched(tmp_path):
        """P0400-LEASE-STALE (PFS-2094.047): a stale lock there is not a run in progress."""
        main, other = _workspace_3_storage___sync_pair(tmp_path, "stalelock")
        _workspace_3_storage___recorded_sim(other, "4702", {"scripts/point.fs": "s"})
        lock = other.root / "runs.json.lock"
        lock.write_text("{}\n", encoding="utf-8")
        old = time.time() - 3600
        os.utime(lock, (old, old))
        (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
        assert "skipped" not in entry, entry.get("skipped")
        assert entry["runs"]["added"]

    @staticmethod
    # --------------------------------------------------------------------------- PFS-2094.049
    def test_p0400_a_relative_sync_path_is_the_workspace_roots(tmp_path, monkeypatch):
        """P0400-SYNC-RELATIVE (PFS-2094.049): path = "." names main from any working directory."""
        main, other = _workspace_3_storage___sync_pair(tmp_path, "relpath")
        config = main.root / storage_module.SYNC_CONFIG
        config.write_text(
            'main = "main"\n\n[workspaces.main]\npath = "."\n\n'
            '[workspaces.other]\npath = "../relpath_other"\n',
            encoding="utf-8",
        )
        _workspace_3_storage___recorded_sim(other, "4801", {"scripts/point.fs": "s"})
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
        assert Path(entry["source"]) == other.root.resolve()
        assert entry["runs"]["added"]


def test_p0440_rb4_13_free_space_documents_partial_apply():
    text = storage_module.free_space.__doc__
    assert "WorkspaceError" in text
    assert "earlier steps" in text
    assert "interrupted" in text
