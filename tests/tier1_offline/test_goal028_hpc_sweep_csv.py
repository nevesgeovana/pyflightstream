"""FR-3777 (D30): the campaign sweep table is retired, and so is the option that named it.

0.58.0 writes no ``campaign_sweep.csv``: each polar's TOTAL group file is complete. The
``--sweep-csv`` flag, the ``sweep_csv`` keyword of ``run_matrix`` and ``run_campaign`` and the
``run.SWEEP_TABLE_NAME`` constant are refused by name with the page's successor sentence.
"""

from __future__ import annotations

import warnings

import pytest

import pyflightstream.run as run
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import InputArtifactError, PyflightstreamWarning
from pyflightstream.run import cli as cli_mod
from pyflightstream.run.matrix import run_matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    _steady_sweep_matrix,
    converged,
)

SUCCESSOR = (
    "campaign_sweep.csv is retired: each polar's TOTAL group file is complete, and the guide "
    "(docs/pproc/index.md#joining-polars) joins several."
)


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


@pytest.mark.requirement("FR-3777")
@pytest.mark.parametrize("form", ["--sweep-csv", "--sweep-csv=table.csv"])
def test_the_command_refuses_the_retired_flag_by_name(tmp_path, capsys, form):
    argv = ["run", str(tmp_path / "warm.fs"), "--workspace", str(tmp_path / "ws"), form]
    if form == "--sweep-csv":
        argv.append("table.csv")
    assert cli_mod.main(argv) == 2
    err = capsys.readouterr().err
    assert "--sweep-csv" in err and "no longer accepted since v0.58.0" in err
    assert SUCCESSOR in err


@pytest.mark.requirement("FR-3777")
def test_run_matrix_refuses_the_retired_keyword_by_name(tmp_path):
    with pytest.raises(MatrixError, match="sweep_csv of run_matrix") as refused:
        _run(tmp_path, sweep_csv=tmp_path / "my_table.csv")
    assert SUCCESSOR in str(refused.value)


@pytest.mark.requirement("FR-3777")
def test_run_campaign_refuses_the_retired_keyword_by_name():
    with pytest.raises(InputArtifactError, match="sweep_csv of run_campaign") as refused:
        run.run_campaign(None, None, None, assess=converged, sweep_csv="t.csv")  # type: ignore[arg-type]
    assert SUCCESSOR in str(refused.value)


@pytest.mark.requirement("FR-3777")
def test_the_retired_constant_is_refused_by_name():
    with pytest.raises(AttributeError, match="SWEEP_TABLE_NAME of pyflightstream.run") as refused:
        run.SWEEP_TABLE_NAME  # noqa: B018 - the access is the behaviour under test
    assert SUCCESSOR in str(refused.value)
    assert not hasattr(run, "SWEEP_TABLE_NAME")


@pytest.mark.requirement("FR-3777")
def test_the_run_leaves_no_campaign_sweep_table(tmp_path):
    workspace = _run(tmp_path)
    assert list(workspace.root.rglob("campaign_sweep.csv")) == []
    assert workspace.read_manifest(), "the run recorded nothing, so the absence proves nothing"
