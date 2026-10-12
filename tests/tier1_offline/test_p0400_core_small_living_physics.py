"""P0400-LIVINGPICK (PFS-2135.041): the living physics page reads the newest report, never a label.

builds_at_or_after kept the alphabetically last report of a build, so a
targeted rerun named ``_targeted`` replaced the ``_full`` run of the same date. The
latest date now wins, and two reports of one build on that date are refused.
"""

from __future__ import annotations

import pytest
import yaml

from tests.tier1_offline.test_living_physics import _module


def _write(physics, name):
    (physics / name).write_text(
        yaml.safe_dump({"date": "2026-01-01", "cases": {}}), encoding="utf-8"
    )


def test_p0400_livingpick_same_date_reports_are_refused(tmp_path, monkeypatch):
    """P0400-LIVINGPICK: a full run and a rerun on one date name both and stop."""
    module = _module()
    physics = tmp_path / "physics"
    physics.mkdir()
    _write(physics, "PHY-26124_2026-09-01_full.yaml")
    _write(physics, "PHY-26124_2026-09-01_targeted.yaml")
    monkeypatch.setattr(module, "PHYSICS", physics)
    with pytest.raises(ValueError, match=r"26\.124 has 2 physics reports dated 2026-09-01"):
        module.builds_at_or_after(module.OLDEST_BUILD)


def test_p0400_livingpick_the_latest_date_wins_over_the_label(tmp_path, monkeypatch):
    """P0400-LIVINGPICK: a later full run wins over an earlier rerun whose label sorts last."""
    module = _module()
    physics = tmp_path / "physics"
    physics.mkdir()
    _write(physics, "PHY-26124_2026-09-01_zz-rerun.yaml")
    _write(physics, "PHY-26124_2026-09-02_full.yaml")
    monkeypatch.setattr(module, "PHYSICS", physics)
    found = module.builds_at_or_after(module.OLDEST_BUILD)
    assert found["26.124"].name == "PHY-26124_2026-09-02_full.yaml"
