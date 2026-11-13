"""The matrix split preserves results captured from 42cf219a before the cut."""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from pyflightstream.cases.matrix import read_matrix

FIXTURES = Path(__file__).parent / "fixtures"
GOLDENS = json.loads((FIXTURES / "p0360_w9d_goldens.json").read_text(encoding="utf-8"))
MESH_ROUTE_CELL = 9  # the column 0.57.0 added after GEOMETRY


def _without_mesh_route(data: bytes) -> bytes:
    """Return ``data`` with the MESH_ROUTE cell taken out of every 20-cell line."""
    lines = []
    for line in data.split(b"\n"):
        cells = line.split(b"|")
        if len(cells) == 20:
            del cells[MESH_ROUTE_CELL]
        lines.append(b"|".join(cells))
    return b"\n".join(lines)


@pytest.mark.parametrize("fixture", GOLDENS["fixtures"])
@pytest.mark.parametrize("active_only", [True, False])
def test_read_matrix_matches_pre_cut_rows(fixture: str, active_only: bool) -> None:
    path = FIXTURES / fixture
    golden = GOLDENS["fixtures"][fixture]
    # The goldens hash the 0.56.0 bytes. 0.57.0 migrated the fixtures by adding the
    # MESH_ROUTE column (PFS-2214) and nothing else, which this pins: the fixture with
    # that one cell taken out of every 20-cell line is the captured file, byte for byte.
    assert hashlib.sha256(_without_mesh_route(path.read_bytes())).hexdigest() == golden["sha256"]
    actual = []
    for row in read_matrix(path, active_only=active_only):
        data = dataclasses.asdict(row)
        # The goldens predate the field, and no fixture states any.
        assert data.pop("identifiers") == {}
        data["sweep"] = row.sweep.model_dump(mode="json")
        actual.append(data)
    assert actual == golden["active_rows" if active_only else "all_rows"]
