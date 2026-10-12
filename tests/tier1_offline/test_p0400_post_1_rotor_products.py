"""P0400 rotor-products defects (post-1 lane).

P0400-ACOUSTICSKIP (PFS-2105.007): an unreadable acoustic export is a skip of
its own point, so two points' reasons both survive in products.json.
P0400-WALLTIMEREV (PFS-2105.008): the unsteady harmonics of a run a wall clock
stopped are fitted over the last revolution the series holds, not one counted
to the planned last step.
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pyflightstream.post._rotor_products import _acoustic_products
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_goal036_harmonics import _post, _unsteady


@pytest.mark.parametrize((), [pytest.param(id="P0400-ACOUSTICSKIP")])
def test_p0400_acousticskip_each_point_keeps_its_own_reason(tmp_path):
    """P0400-ACOUSTICSKIP: two unreadable exports leave two named skips."""
    skipped: dict[str, str] = {}
    for stem in ("P1", "P2"):
        record = SimpleNamespace(run_id=f"run-{stem}", outputs=[f"{stem}_acoustic_signals.txt"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _acoustic_products(
                cast(Any, record),
                sim_dir=tmp_path,
                stem=stem,
                out=tmp_path / "post",
                rotors={},
                clocks={},
                target=lambda path: path,
                skipped=skipped,
            )
    assert set(skipped) == {
        "acoustics/P1_acoustics_summary.csv",
        "acoustics/P2_acoustics_summary.csv",
    }, skipped
    assert "P1_acoustic_signals" in skipped["acoustics/P1_acoustics_summary.csv"]
    assert "P2_acoustic_signals" in skipped["acoustics/P2_acoustics_summary.csv"]


@pytest.mark.parametrize((), [pytest.param(id="P0400-WALLTIMEREV")])
def test_p0400_walltimerev_the_fit_ends_where_the_series_ends(tmp_path, monkeypatch):
    """P0400-WALLTIMEREV: planned 20 steps, stopped at 14: the fit reads 7 to 12, not 13 to 18."""
    workspace = _unsteady(tmp_path, monkeypatch, blades=3, rpm=1200.0)
    (record,) = workspace.read_manifest()
    plan = dict(record.reductions or {})
    plan["time_iterations"] = 20
    stopped = record.model_copy(
        update={
            "status": RunStatus.WALLTIME_REACHED,
            "stopped_at": {"step": 14},
            "export_window": {**(record.export_window or {}), "time_iterations": 20},
            "reductions": plan,
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [stopped])
    _out, manifest, _log = _post(workspace)
    entry = manifest["products"]["sections/AL-020_harmonics.csv"]  # type: ignore[index]
    assert entry["revolution"] == {"PROP": [7, 12]}, entry
    assert entry["samples"] == 18, entry
