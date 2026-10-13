"""P0400-RFIXF2-DISTRIBUTIONS: plan and post share one rule for a declared distribution.

PFS-2081.100 (REL2-004): the sectional-loads export holds one block per
distribution and plane, summed over its families, so Trefftz A traces a block
of exactly one family. A declared ``families = "all"`` distribution on a
geometry of one family is that family's block, and post now traces it as the
plan reused it; a declared aggregate of several families covers none of them,
so the plan adds their own blocks rather than reusing what post cannot read.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF2.

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from pyflightstream.cases.farfield_inputs import traced_family
from pyflightstream.cases.workflows._farfield import _covered, plan_record
from pyflightstream.workspace import RunRecord
from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline.test_p0400_farfield_plan import _case, _script

pytestmark = pytest.mark.requirement("FR-455")

_TREFFTZ_A = {"families": "all", "trefftz": {"variant": "sections", "stations": 80}}


def _sections(families: object) -> dict:
    return {
        "sections": {
            "count": wing.STATIONS,
            "distributions": [{"families": families, "frame": "MRP", "planes": ["XZ"]}],
        }
    }


def _states(record: dict) -> set[str]:
    return {
        item["state"]
        for item in record["inputs"]
        if item["analysis"] == "trefftz:sections" and item["input"] == "section_distribution"
    }


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_an_all_distribution_of_one_family_is_traced(tmp_path, monkeypatch):
    """P0400-RFIXF2-DISTRIBUTIONS (FR-455 R2, R4): plan reuses it, post traces it (row A)."""
    (tmp_path / "plan").mkdir()
    case = _case(tmp_path / "plan", _TREFFTZ_A, **_sections("all"))
    script = _script(case)
    assert _states(plan_record(case, "26.124", script)) == {"reused"}
    (block,) = script.section_blocks
    assert block["families"] == [], "the every-boundary form, as the script records it"

    def record(**fields: Any) -> RunRecord:
        return RunRecord(**{**fields, "sections_layout": [block], "inventory": ["W"]})

    monkeypatch.setattr(wing, "RunRecord", record)
    workspace = wing._workspace(tmp_path / "post", farfield=True)
    wing._post(workspace)
    root = Path(workspace.root)
    with wing._one(root, "farfield/*_trefftz.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["VARIANT"]: row for row in csv.DictReader(handle)}
    assert "A" in rows and float(rows["A"]["CL_T"]) == pytest.approx(wing.CL, rel=2e-3)
    skipped = json.loads(wing._one(root, "products.json").read_text(encoding="utf-8"))
    assert not [why for why in skipped.get("skipped", {}).values() if "distribution" in why]


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_multi_family_aggregate_covers_none(tmp_path):
    """P0400-RFIXF2-DISTRIBUTIONS (FR-455 R2, R3): a block over W and T is no family's block.

    The plan's coverage, the rule post reads by, leaves both families
    uncovered, so the plan adds a block of each instead of reusing the
    aggregate.
    """
    case = _case(tmp_path, _TREFFTZ_A, **_sections(["W", "T"]))
    assert _covered(case, ["W", "T"]) == set()
    assert traced_family(["W", "T"], ["W", "T"]) is None
    assert traced_family([], ["W"]) == "W"
    assert traced_family([], ["W", "T"]) is None
