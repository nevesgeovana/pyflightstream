"""P0400-WSSIDECAR: a saved simulation's boundary inventory is valid TOML (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import tomllib

import pytest

from pyflightstream.workspace.sidecars import write_inventory
from tests.support_helpers import saved_mesh_fixture

pytestmark = pytest.mark.requirement("P0400-WSSIDECAR")

NAMES = ["Wing\\tip", 'Say "hi"', "Plain"]


def test_p0400_wssidecar_names_with_a_backslash_or_a_quote_read_back_unchanged(tmp_path):
    """P0400-WSSIDECAR (PFS-2095.034): each name and the file value is a quoted TOML string."""
    geometry = saved_mesh_fixture(tmp_path / "wing.fsm", NAMES)
    written = write_inventory(geometry)
    data = tomllib.loads(written.read_text(encoding="utf-8"))
    assert data["boundaries"] == NAMES
    assert data["file"] == geometry.name
