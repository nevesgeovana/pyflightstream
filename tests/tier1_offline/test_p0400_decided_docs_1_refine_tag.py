"""Tier 1: the short refine tag and two factors it cannot tell apart (P0400-REFINE-TAG).

Pipeline role: quality gate on the level tag of ``refine`` (FR-433, planning
node PFS-2081.01). A factor in a built tag shows 6 significant digits, so two
factors that agree to 6 digits build one tag: the second level is refused as
an existing one unless overwritten, and ``refine.json`` keeps the exact factor.
The page docs/mesh/reference.md states all three facts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine import _config
from tests.tier1_offline.test_p0380_s1_refine import _source

PAGE = Path(__file__).resolve().parents[2] / "docs" / "mesh" / "reference.md"


def _numbers(node: object) -> list[float]:
    """Return every number of a parsed JSON tree."""
    if isinstance(node, dict):
        return [n for value in node.values() for n in _numbers(value)]
    if isinstance(node, list):
        return [n for value in node for n in _numbers(value)]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return [float(node)]
    return []


def test_p0400_refine_tag_close_factors_collide_and_refine_json_keeps_the_exact_one(tmp_path):
    # Verifies FR-433.
    """P0400-REFINE-TAG: 2.0000001 and 2.0000002 share R2; the second is refused, then replaced."""
    src = _source(tmp_path)
    first = refine_mesh(src, 2.0000001)
    assert first.folder.name.endswith("_R2"), first.folder
    record = json.loads((first.folder / f"{first.folder.name}.refine.json").read_text("utf-8"))
    assert 2.0000001 in _numbers(record["specs"]), record["specs"]
    with pytest.raises(InputArtifactError, match=r"the level exists; give overwrite=True"):
        refine_mesh(src, 2.0000002)
    second = refine_mesh(src, 2.0000002, overwrite=True)
    assert second.folder == first.folder


def test_p0400_refine_tag_page_states_digits_exact_factor_and_collision():
    """P0400-REFINE-TAG: the page gives the 6 digits, the exact factor and the refusal."""
    text = " ".join(PAGE.read_text(encoding="utf-8").split())
    assert "at most 6 significant digits" in text
    assert "`refine.json` holds the exact factor under `specs`" in text
    assert "refused as an existing one unless `--overwrite`" in text


def test_p0400_refine_tag_rounding_collision_excludes_summary_hashes():
    """P0400-REFINE-TAG: summary hashes retain digits hidden by the short spelling."""
    names = ["LongFamilyNameAlpha", "LongFamilyNameBeta"]
    requests = [
        _config.RefineRequest(
            specs={
                names[0]: _config.FamilySpec(factor=factor),
                names[1]: _config.FamilySpec(factor=5.0),
            }
        )
        for factor in (2.0000001, 2.0000002)
    ]
    assert [_config.spec_tag(request.specs[names[0]]) for request in requests] == ["2", "2"]
    tags = [_config.level_tag(request, names) for request in requests]
    assert all(tag.startswith("R-2fam-") for tag in tags)
    assert tags[0] != tags[1]
    text = " ".join(PAGE.read_text(encoding="utf-8").split())
    assert "For a short tag without a hash" in text
    assert "Summary tags hash the exact factors" in text
