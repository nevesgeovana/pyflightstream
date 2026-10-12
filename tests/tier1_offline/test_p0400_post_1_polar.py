"""P0400-UNJUDGEDDRAG (PFS-2085.021): on a 26.125 table the declined-drag rule is said to be off.

The rule reads CDi, which a 26.125 export does not print, so a surface on the
vorticity induced-drag list got numbers in its axis drag columns and nothing
said the rule could not be applied.
"""

from __future__ import annotations

import copy
import warnings

import pytest

from tests.tier1_offline.test_pfs2006_declined_induced_drag import _EVERY_BOUNDARY


@pytest.mark.parametrize((), [pytest.param(id="P0400-UNJUDGEDDRAG")])
def test_p0400_unjudgeddrag_is_said_in_the_post_log(tmp_path, monkeypatch):
    """P0400-UNJUDGEDDRAG: every point of a 26.125 polar with listed surfaces is warned."""
    import tests.tier1_offline.test_post_superfile as sf

    setup = copy.deepcopy(sf._SOLVER_SETUP)
    setup["flags"]["SET_VORTICITY_DRAG_BOUNDARIES"] = dict(_EVERY_BOUNDARY)
    assert sf._LOADS.count("CL, CDi, CDo,") == 1
    monkeypatch.setattr(sf, "_LOADS", sf._LOADS.replace("CL, CDi, CDo,", "CL, CDp, CDv,"))
    monkeypatch.setattr(sf, "_SOLVER_SETUP", setup)
    workspace = sf._workspace(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sf._post(workspace)
    log = (workspace.products_dir("matriz") / "post.log").read_text(encoding="utf-8")
    said = [line for line in log.splitlines() if "26.125 split" in line]
    assert len(said) >= 2, log
    assert all("W, B are on the vorticity induced-drag list" in line for line in said), said
