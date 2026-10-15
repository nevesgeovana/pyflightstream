"""The matrix split preserves results captured from 42cf219a before the cut."""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from pyflightstream.cases.matrix import read_matrix

FIXTURES = Path(__file__).parent / "fixtures"
GOLDENS = json.loads((FIXTURES / "p0360_w9d_goldens.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture", GOLDENS["fixtures"])
@pytest.mark.parametrize("active_only", [True, False])
def test_read_matrix_matches_pre_cut_rows(fixture: str, active_only: bool) -> None:
    path = FIXTURES / fixture
    golden = GOLDENS["fixtures"][fixture]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == golden["sha256"]
    actual = []
    for row in read_matrix(path, active_only=active_only):
        data = dataclasses.asdict(row)
        data["sweep"] = row.sweep.model_dump(mode="json")
        actual.append(data)
    assert actual == golden["active_rows" if active_only else "all_rows"]
