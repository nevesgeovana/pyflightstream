"""P0310-POL-CENSUS: the repeated-POL census reads the matrices `sync` reads.

`sync` and storage find a workspace's matrices in `<root>/*.fs` and in
`<root>/inputs/matrices/*.fs`; the census of the plan read the root only, so a
POL repeated between the two folders shared one simulation folder in silence.
Both now call `pyflightstream.workspace.matrix_files`.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-193.

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import matrix_files
from pyflightstream.workspace.storage import _matrix_files
from tests.tier1_offline.test_goal021_matrix_ids import _matrix, _workspace, row


def _plan_recording(workspace, matrix):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan_matrix(
            matrix, workspace, name="p", default_fs_version="26.120", recipes={"003": "steady"}
        )
    return [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]


def test_goal036_pol_census_a_repeat_between_root_and_inputs_matrices_is_refused(tmp_path):
    # P0310-POL-CENSUS
    workspace = _workspace(tmp_path)
    planned = _matrix(workspace.root, "a.fs", [row(8001)])
    _matrix(workspace.inputs_dir / "matrices", "b.fs", [row(8001)])
    with pytest.raises(MatrixError) as raised:
        _plan_recording(workspace, planned)
    assert "POL 8001 in a.fs row 1, b.fs row 1" in str(raised.value)


def test_goal036_pol_census_the_same_repeat_seen_from_the_inputs_folder(tmp_path):
    # P0310-POL-CENSUS
    workspace = _workspace(tmp_path)
    _matrix(workspace.root, "a.fs", [row(8001)])
    planned = _matrix(workspace.inputs_dir / "matrices", "b.fs", [row(8001)])
    with pytest.raises(MatrixError, match="8001"):
        _plan_recording(workspace, planned)


def test_goal036_pol_census_a_matrix_in_another_folder_plans_with_the_warning(tmp_path):
    # P0310-POL-CENSUS
    workspace = _workspace(tmp_path)
    planned = _matrix(workspace.root / "elsewhere", "c.fs", [row(8001)])
    messages = _plan_recording(workspace, planned)
    outside = [m for m in messages if "c.fs lies outside" in m]
    assert len(outside) == 1, messages
    assert "`sync` and the repeated-POL census do not see it" in outside[0]


@pytest.mark.parametrize("where", ["root", "inputs"])
def test_goal036_pol_census_a_matrix_inside_a_folder_is_not_warned(tmp_path, where):
    # P0310-POL-CENSUS
    workspace = _workspace(tmp_path)
    folder = workspace.root if where == "root" else workspace.inputs_dir / "matrices"
    planned = _matrix(folder, "d.fs", [row(8001)])
    assert [m for m in _plan_recording(workspace, planned) if "lies outside" in m] == []


def test_goal036_pol_census_storage_and_census_return_the_same_list(tmp_path):
    # P0310-POL-CENSUS
    workspace = _workspace(tmp_path)
    _matrix(workspace.root, "a.fs", [row(8001)])
    _matrix(workspace.inputs_dir / "matrices", "b.fs", [row(8002)])
    _matrix(workspace.root / "elsewhere", "c.fs", [row(8003)])
    shared = matrix_files(workspace.root)
    assert [p.name for p in shared] == ["a.fs", "b.fs"]
    assert [workspace.root / rel for rel in _matrix_files(workspace.root).values()] == shared
