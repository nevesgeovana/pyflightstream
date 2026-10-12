"""Tier 1, 0.40.0 lane run-1: the grouped run gate reads the plan's grouping block.

The grouped workspace of the 0.35.0 tests, its receipt then spoiled by hand; no solver runs.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.run._grouped import read_receipt
from tests.tier1_offline import test_p0350_batch_run as p0350


@pytest.mark.parametrize(
    "block",
    [{"schema": "pyfs-grouping/9"}, {"schema": "pyfs-grouping/1"}, "a sentence"],
    ids=["foreign-schema", "missing-keys", "not-a-table"],
)
def test_p0400_a_malformed_grouping_block_is_a_refusal_not_a_traceback(tmp_path, block):
    """P0400-GROUPING-UNREADABLE (PFS-2095.049): a spoiled ``grouping`` block in plan.json.

    The gate caught only OSError, ValueError and AttributeError around the JSON and read the
    block outside the try, so another schema, a missing key or a non-table block crashed the
    run with ValueError, KeyError or TypeError. It is now refused: plan it again.
    """
    workspace, profile, _ = p0350._workspace(tmp_path)
    matrix = p0350._matrix(tmp_path)
    p0350._plan(workspace, matrix, mode="batch", batch=1)
    plan_file = workspace.plan_dir(p0350.MATRIX) / "plan.json"
    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    payload["grouping"] = block
    plan_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert read_receipt(workspace, p0350.MATRIX) is None
    with pytest.raises(MatrixError, match="no readable grouping"):
        p0350._run(workspace, matrix, executor=p0350._submitting(profile))
