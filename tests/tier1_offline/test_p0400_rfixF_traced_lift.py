"""P0400-RFIXF-TRACEDLIFT: Trefftz A says so when its families do not carry the lift (PFS-2081.96).

A trace over a subset of the lifting surfaces (a wing selected without its
body) holds those surfaces' lift alone, and its span efficiency is theirs: a
wing-body traced over the wing gave e = 0.25 with no warning. Post now writes a
WARNING naming the families, both lifts and their ratio where the traced lift
departs from the solver's CL by more than 5 percent (FR-451 R13).
"""
# ruff: noqa: N999 - the assigned lane name is rfixF.

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline import test_p0400_ffproof_post as ffpost
from tests.tier1_offline.test_p0400_rfixF_layout import _rows

_STEM = "POLAR-3207_M20AL-020BE+000"


def _post(tmp_path: Path, total_cl: str | None) -> tuple[list[dict[str, str]], list[str]]:
    """Post the wing fixture; ``total_cl`` replaces the loads export's total CL."""
    workspace = wing._workspace(tmp_path, farfield=True)
    if total_cl is not None:
        loads = workspace.sim_dir("3207") / "outputs" / f"{_STEM}.txt"
        text = loads.read_text(encoding="utf-8")
        assert text.count("+0.1882829") == 1
        loads.write_text(text.replace("+0.1882829", total_cl), encoding="utf-8")
    ffpost._post(workspace)
    root = Path(workspace.root)
    rows = [r for r in _rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "A"]
    said = [line for line in ffpost._warnings_of(root) if "Trefftz A traces" in line]
    return rows, said


@pytest.mark.requirement("FR-451")
def test_p0400_rfixf_a_trace_short_of_the_configurations_lift_is_warned(tmp_path):
    """P0400-RFIXF-TRACEDLIFT (FR-451 R13): the traced wing carries 0.75 of the solver's CL.

    The configuration's CL is raised to 0.2510 (a body lifting the rest); the
    traced wing still lifts 0.1883. The A rows are written and post.log names
    the family, both values and the ratio. Before the fix nothing was said.
    """
    rows, said = _post(tmp_path, "+0.2510439")
    assert rows and float(rows[-1]["CL_T"]) == pytest.approx(0.1883, rel=3e-3)
    (line,) = said
    assert "W" in line and "0.75" in line and "0.251" in line and "FR-451 R13" in line


@pytest.mark.requirement("FR-451")
def test_p0400_rfixf_a_trace_carrying_the_lift_is_not_warned(tmp_path):
    """P0400-RFIXF-TRACEDLIFT (FR-451 R13): the wing traced alone, at its own CL, is silent."""
    rows, said = _post(tmp_path, None)
    assert rows and not said
