"""P0400-DECLINED125 (PFS-2085.021): a declined surface on 26.125 prints CDp 0 and is warned.

RPT-166 (D-01, D-01c): on 26.125 a surface with no trailing edge on the vorticity
induced-drag list prints CDp exactly 0, as earlier builds print CDi 0. The rule
reads CDi, which a 26.125 export does not print, so such a surface got numbers
in its axis drag columns and nothing said the solver had not computed them.
"""

from __future__ import annotations

import copy
import warnings

import pytest

from tests.tier1_offline.test_pfs2006_declined_induced_drag import _EVERY_BOUNDARY

_B_CDP = "+0.0000333"


def _log_of(tmp_path, monkeypatch, *, b_printed_at_zero: bool) -> list[str]:
    import tests.tier1_offline.test_post_superfile as sf

    setup = copy.deepcopy(sf._SOLVER_SETUP)
    setup["flags"]["SET_VORTICITY_DRAG_BOUNDARIES"] = dict(_EVERY_BOUNDARY)
    assert sf._LOADS.count("CL, CDi, CDo,") == 1
    loads = sf._LOADS.replace("CL, CDi, CDo,", "CL, CDp, CDv,")
    if b_printed_at_zero:
        assert loads.count(_B_CDP) == 1
        loads = loads.replace(_B_CDP, "+0.0000000")
    monkeypatch.setattr(sf, "_LOADS", loads)
    monkeypatch.setattr(sf, "_SOLVER_SETUP", setup)
    workspace = sf._workspace(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sf._post(workspace)
    log = (workspace.products_dir("matriz") / "post.log").read_text(encoding="utf-8")
    return [line for line in log.splitlines() if "CDp exactly 0" in line]


@pytest.mark.parametrize((), [pytest.param(id="P0400-DECLINED125")])
def test_p0400_declined125_a_listed_surface_at_cdp_zero_is_warned(tmp_path, monkeypatch):
    """P0400-DECLINED125: every point warns, naming the surface and the build 26.125."""
    said = _log_of(tmp_path, monkeypatch, b_printed_at_zero=True)
    assert len(said) >= 2, said
    assert all("build 26.125" in line and "exactly 0 for B, on the" in line for line in said), said


@pytest.mark.parametrize((), [pytest.param(id="P0400-DECLINED125")])
def test_p0400_declined125_a_listed_surface_with_a_cdp_is_not_warned(tmp_path, monkeypatch):
    """P0400-DECLINED125: a listed surface printing a real CDp was computed, so no warning."""
    assert _log_of(tmp_path, monkeypatch, b_printed_at_zero=False) == []
