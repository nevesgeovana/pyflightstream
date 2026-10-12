"""P0400-TABLEDSTEPS (PFS-2105.038): the sections series lists only the steps it tabled.

A step whose export declares zero sections has a file and no row; the
manifest's ``steps_tabled`` listed it all the same.
"""

from __future__ import annotations

import re
import warnings

import pytest

from tests.tier1_offline.test_f07_section_distributions import _post, _workspace


@pytest.mark.parametrize((), [pytest.param(id="P0400-TABLEDSTEPS")])
def test_p0400_tableddsteps_a_step_of_no_section_is_not_listed(tmp_path, monkeypatch):
    """P0400-TABLEDSTEPS: step 4 declares no section; steps_tabled is [3, 5]."""
    workspace, _record = _workspace(tmp_path, monkeypatch, stamped=True)
    step = workspace.sim_dir("7001") / "AL-020_sloads_iteration=4.txt"
    text = step.read_text(encoding="utf-8")
    emptied = re.sub(r"(Number of Surface Sections:\s*)\d+", r"\g<1>0", text)
    assert emptied != text
    step.write_text(emptied, encoding="utf-8", newline="\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _out, manifest = _post(workspace)
    (entry,) = [
        value for key, value in manifest["products"].items() if key.endswith("_sections_series.csv")
    ]
    assert entry["steps_tabled"] == [3, 5], entry
