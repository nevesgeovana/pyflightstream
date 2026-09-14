"""GOAL-020 item 7: PFS-2018.06, the living physics report, begins at 26.123.

WHAT MAKES IT LIVING is not that a file exists. It is that a build which
arrives shows up in it WITHOUT anyone remembering to edit it, and that a
committed copy which no longer matches the evidence FAILS rather than sitting
there being read. Both are held here; the first by generating a report over a
tree with an extra build in it, the second by the generator's own check mode.

AND IT DOES NOT BACK-FILL, which is the owner's decision of 2026-09-13. A
report that quietly re-derived a verdict for every build ever registered is
exactly the work that decision exists to avoid, so the floor is asserted from
both sides: a build below it is left out even when its evidence is present.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "build_living_physics.py"
REPORT = REPO / "reports" / "physics" / "LIVING-PHYSICS-ACROSS-BUILDS.md"

sys.path.insert(0, str(REPO / "scripts"))


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_living_physics", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_goal020_physics_report_exists_and_names_its_floor():
    assert REPORT.is_file(), f"{REPORT} does not exist"
    text = REPORT.read_text(encoding="utf-8")
    assert "oldest_build: 26.123" in text


def test_goal020_physics_report_compares_no_build_older_than_the_floor():
    """HER DECISION: it begins at 26.123 and grows forward.

    Asserted over the table's own header rather than over prose, because the
    prose can say anything and the header is what a reader compares by.
    """
    text = REPORT.read_text(encoding="utf-8")
    header = next(line for line in text.splitlines() if line.startswith("| case |"))
    builds = [cell.strip() for cell in header.strip("|").split("|")[2:]]
    assert builds, "the report compares no build at all"
    for build in builds:
        assert build >= "26.123", f"the report compares {build}, which is older than the floor"


def test_goal020_physics_report_is_current():
    """A committed copy that no longer matches the evidence FAILS rather than being read."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        # EXPLICIT, and a copy rather than the object: an inherited
        # environment carries whatever the runner injected, and the
        # repository's spawn ratchet counts a call without this keyword.
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_goal020_physics_report_leaves_an_older_build_out(tmp_path, monkeypatch):
    """The floor is held from BOTH sides: evidence below it is present and not folded in."""
    module = _module()
    physics = tmp_path / "physics"
    physics.mkdir()
    for build, verdict in (("26100", "fail"), ("26123", "pass")):
        (physics / f"PHY-{build}_2026-01-01_full.yaml").write_text(
            yaml.safe_dump(
                {
                    "date": "2026-01-01",
                    "summary": {"pass": 1, "warn": 0, "fail": 0, "no_reference": 0},
                    "cases": {"PHY-01": {"title": "a case", "verdicts": {"CL": verdict}}},
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(module, "PHYSICS", physics)
    admitted = module.builds_at_or_after(module.OLDEST_BUILD)
    assert "26.100" not in admitted, "a build below the floor was folded in"
    assert "26.123" in admitted


def test_goal020_physics_report_takes_a_new_build_with_no_hand_edit(tmp_path, monkeypatch):
    """THE WHOLE OF LIVING: a build arrives and the page carries it, unedited."""
    module = _module()
    physics = tmp_path / "physics"
    physics.mkdir()
    (physics / "PHY-26123_2026-01-01_full.yaml").write_text(
        yaml.safe_dump(
            {
                "date": "2026-01-01",
                "summary": {"pass": 1, "warn": 0, "fail": 0, "no_reference": 0},
                "cases": {"PHY-01": {"title": "a case", "verdicts": {"CL": "pass"}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PHYSICS", physics)
    before = module.build_report()
    assert "26.130" not in before

    (physics / "PHY-26130_2026-02-02_full.yaml").write_text(
        yaml.safe_dump(
            {
                "date": "2026-02-02",
                "summary": {"pass": 0, "warn": 1, "fail": 0, "no_reference": 0},
                "cases": {"PHY-01": {"title": "a case", "verdicts": {"CL": "warn"}}},
            }
        ),
        encoding="utf-8",
    )
    after = module.build_report()
    assert "26.130" in after, "a build that arrived did not reach the page"
    assert "1 warn" in after, "the new build's verdict did not reach the page"


def test_goal020_physics_report_says_not_run_rather_than_nothing(tmp_path, monkeypatch):
    """A case that never ran on a build is EMPTY and says so; empty is not a pass."""
    module = _module()
    physics = tmp_path / "physics"
    physics.mkdir()
    (physics / "PHY-26123_2026-01-01_full.yaml").write_text(
        yaml.safe_dump(
            {
                "date": "2026-01-01",
                "summary": {},
                "cases": {"PHY-01": {"title": "a", "verdicts": {"CL": "pass"}}},
            }
        ),
        encoding="utf-8",
    )
    (physics / "PHY-26130_2026-02-02_full.yaml").write_text(
        yaml.safe_dump(
            {
                "date": "2026-02-02",
                "summary": {},
                "cases": {"PHY-99": {"title": "b", "verdicts": {"CL": "pass"}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PHYSICS", physics)
    rendered = module.build_report()
    assert "not run" in rendered
