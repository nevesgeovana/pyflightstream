"""SWEEP-CSV-SECOND-COPY: ``--sweep-csv`` names THE table, never a second one.

The help of the option promises that the run writes one sweep table and never a
second copy under another name. The run layer wrote the default table on its
own and the command then wrote the chosen path, so a chosen path meant two.
"""

from __future__ import annotations

import warnings

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run import SWEEP_TABLE_NAME
from pyflightstream.run import cli as cli_mod
from pyflightstream.run.matrix import run_matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    _steady_sweep_matrix,
    converged,
)


def test_the_command_hands_the_chosen_path_to_the_run(tmp_path, monkeypatch):
    received: dict[str, object] = {}

    def spy(matrix, workspace, **keywords):
        received.update(keywords)
        return []

    monkeypatch.setattr(cli_mod, "run_matrix", spy)
    monkeypatch.setattr(cli_mod, "plan_receipt_error", lambda *args, **kwargs: None)
    chosen = tmp_path / "elsewhere" / "my_table.csv"
    matrix = tmp_path / "warm.fs"
    matrix.write_text("", encoding="utf-8")
    cli_mod.main(
        [
            "run",
            str(matrix),
            "--workspace",
            str(tmp_path / "ws"),
            "--name",
            "warm",
            "--fs-version",
            "26.120",
            "--sweep-csv",
            str(chosen),
        ]
    )
    assert "sweep_csv" in received, sorted(received)
    assert str(received["sweep_csv"]) == str(chosen)


def _run(tmp_path, **extra):
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(
            matrix,
            workspace,
            name="warm",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=CountingStub(WRITES_EVERY_EXPORT),
            default_fs_version="26.120",
            **extra,
        )
    return workspace


def test_a_chosen_path_is_the_only_sweep_table_the_run_leaves(tmp_path):
    chosen = tmp_path / "elsewhere" / "my_table.csv"
    workspace = _run(tmp_path, sweep_csv=chosen)
    assert chosen.is_file()
    default = workspace.sweep_dir("warm") / SWEEP_TABLE_NAME
    assert not default.exists(), "the run left a second copy under the default name"
    assert list(workspace.root.rglob(SWEEP_TABLE_NAME)) == []


def test_without_a_chosen_path_the_default_table_is_still_left(tmp_path):
    workspace = _run(tmp_path)
    assert (workspace.sweep_dir("warm") / SWEEP_TABLE_NAME).is_file()
