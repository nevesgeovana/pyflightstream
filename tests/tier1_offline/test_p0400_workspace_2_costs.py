"""P0400-COSTFILE: a cost file's reference values and curve entries are checked when it is read."""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace.costs import read_cost_file
from tests.tier1_offline.test_p0350_cost_file import _FILE


@pytest.mark.parametrize(
    ("old", "new", "named"),
    [
        ("mesh_faces = 1000", "mesh_faces = 0", "mesh_faces to be a positive number"),
        ("wall_time_s = 100.0", "wall_time_s = -1.0", "wall_time_s to be a positive number"),
        ("ncpus = 4\n", "ncpus = 0\n", "ncpus to be a positive number"),
        ("steps = 10", "steps = 0", "steps to be a positive number"),
        ("steps = 10", 'steps = "10"', "steps to be a positive number"),
        ("ncpus = [2, 4, 8]", 'ncpus = [2, "4", 8]', "entry to be a number"),
        ("speedup = [1.0, 2.0, 6.0]", 'speedup = [1.0, "2", 6.0]', "entry to be a number"),
    ],
)
def test_p0400_costfile_a_bad_reference_or_curve_entry_is_refused_by_name(
    tmp_path, old, new, named
):
    """P0400-COSTFILE (PFS-2097.012): a zero or negative reference value, a string steps and a
    non-number curve entry are InputArtifactError naming the key, never a ZeroDivisionError,
    ValueError or TypeError later in estimate_seconds."""
    assert old in _FILE
    path = tmp_path / "c001.toml"
    path.write_text(_FILE.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(InputArtifactError, match=named):
        read_cost_file(path)
