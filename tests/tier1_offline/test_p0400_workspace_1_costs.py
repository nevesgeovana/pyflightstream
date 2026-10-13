"""P0400-WSCOST: the per-machine cost file (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run.cli import main as matrix_cli
from pyflightstream.workspace.costs import (
    priced_rows,
    read_cost_file,
    resolve_cost_file,
    select_cost_file,
)
from pyflightstream.workspace.hpc import resolve_hpc_profile, select_hpc_profile
from tests.tier1_offline.test_p0350_cost_file import _FILE, _inputs, _row

pytestmark = pytest.mark.requirement("P0400-WSCOST")


@pytest.fixture(autouse=True)
def _clear_selection():
    select_cost_file(None)
    select_hpc_profile(None)
    yield
    select_cost_file(None)
    select_hpc_profile(None)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "c001.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_p0400_wscost_the_cost_file_selection_ends_with_its_command(tmp_path):
    """P0400-WSCOST (PFS-2094.045): a pyfs-matrix call leaves no --cost-file behind it."""
    inputs = _inputs(tmp_path, "c001", "c002")
    for argv in (
        ["plan", "--cost-file", "c002", "--workspace", str(tmp_path)],
        ["plan", "--workspace", str(tmp_path)],
    ):
        try:
            matrix_cli(argv)
        except SystemExit:
            pass
        with pytest.raises(InputArtifactError, match="nothing says which machine"):
            resolve_cost_file(inputs)


def test_p0400_wscost_the_hpc_selection_ends_with_its_command(tmp_path):
    """P0400-WSCOST (PFS-2094.045): a second invocation inherits no --hpc."""
    try:
        matrix_cli(["plan", "--hpc", "h002", "--workspace", str(tmp_path)])
    except SystemExit:
        pass
    assert resolve_hpc_profile(tmp_path / "inputs") is None


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("DISABLE", 100.0),
        ("disable", 100.0),
        ("OFF", 100.0),
        ("false", 100.0),
        ("0.0", 100.0),
        ("ENABLE", 300.0),
        (" enable ", 300.0),
        (True, 300.0),
    ],
)
def test_p0400_wscost_only_an_enabled_row_flag_is_priced(tmp_path, value, seconds):
    """P0400-WSCOST (PFS-2094.046): DISABLE, OFF, false or 0.0 applies no flag multiplier."""
    inputs = _inputs(tmp_path, "c001")
    case = SimpleNamespace(solver=None, variables={"VISCOUS_COUPLING": value})
    (priced,) = priced_rows([_row()], {"r1": case}, inputs)
    assert priced.seconds == seconds


@pytest.mark.parametrize(
    ("old", "new", "named"),
    [
        ("mesh_faces = 1000", "mesh_faces = 0", "[reference] mesh_faces"),
        ("steps = 10", "steps = 0", "[reference] steps"),
        ("steps = 10", 'steps = "10"', "[reference] steps"),
        ("wall_time_s = 100.0", "wall_time_s = -1.0", "[reference] wall_time_s"),
        ("ncpus = 4\n", "ncpus = 0\n", "[reference] ncpus"),
        ("speedup = [1.0, 2.0, 6.0]", 'speedup = ["1", "2", "6"]', "[parallel] speedup"),
        ("ncpus = [2, 4, 8]", 'ncpus = ["a", 4, 8]', "[parallel] ncpus"),
        ("speedup = [1.0, 2.0, 6.0]", "speedup = [1.0, 2.0, nan]", "[parallel] speedup"),
        ("ncpus = [2, 4, 8]", "ncpus = [true, 4, 8]", "[parallel] ncpus"),
    ],
)
def test_p0400_wscost_a_malformed_reference_or_curve_is_refused_by_name(tmp_path, old, new, named):
    """P0400-WSCOST (PFS-2097.019): a zero, text or nan figure is refused naming [table] key."""
    assert old in _FILE
    path = _write(tmp_path, _FILE.replace(old, new, 1))
    with pytest.raises(InputArtifactError, match=re.escape(named)):
        read_cost_file(path)
