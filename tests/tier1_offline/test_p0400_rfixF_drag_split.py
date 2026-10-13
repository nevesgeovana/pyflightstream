"""P0400-RFIXF-DRAGSPLIT: the far field reads the solver's induced drag on 26.125 (PFS-2081.98).

26.125 prints its loads split as ``CDp, CDv`` where earlier builds print
``CDi, CDo`` (FR-423). The far-field rows read the solver's induced drag for
direct comparison (``CDI_NEAR_PRESSURE``, ``CDI_NEAR_VORTICITY``) and read
``CDi`` only, so on 26.125 they wrote ``NA``. They now read the first column of
whichever split the table prints. The 26.125 header is the recorded one of
``fixtures/s10_26125/loads_26.125.txt``.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF.

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline import test_p0400_ffproof_post as ffpost
from tests.tier1_offline.test_p0400_rfixF_layout import _rows

_STEM = "POLAR-3207_M20AL-020BE+000"
_RECORDED = Path(__file__).parent / "fixtures" / "s10_26125" / "loads_26.125.txt"


def _header(text: str) -> str:
    (line,) = [line for line in text.splitlines() if line.strip().startswith("Surface,")]
    return line


@pytest.mark.requirement("FR-456")
@pytest.mark.parametrize("build", ["26.124", "26.125"])
def test_p0400_rfixf_the_near_field_induced_drag_is_read_on_both_builds(tmp_path, build):
    """P0400-RFIXF-DRAGSPLIT (FR-456 R2, FR-423): ``CDI_NEAR_PRESSURE`` is the split's first column.

    The same loads table with the 26.124 header and with the recorded 26.125
    header (``CDp, CDv`` in the same places): both rows state 0.0012418, the
    total's induced or pressure drag. Before the fix the 26.125 rows read NA.
    """
    workspace = wing._workspace(tmp_path, farfield=True)
    if build == "26.125":
        loads = workspace.sim_dir("3207") / "outputs" / f"{_STEM}.txt"
        text = loads.read_text(encoding="utf-8")
        recorded = _header(_RECORDED.read_text(encoding="utf-8"))
        assert "CDp, CDv" in recorded
        loads.write_text(text.replace(_header(text), recorded), encoding="utf-8")
    ffpost._post(workspace)
    rows = _rows(Path(workspace.root), "farfield/*_trefftz.csv")
    assert rows
    assert {row["CDI_NEAR_PRESSURE"] for row in rows} == {"0.0012418"}
    assert {row["CDI_NEAR_VORTICITY"] for row in rows} == {"NA"}
