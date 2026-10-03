"""AD-20: matrix binding preserves the results captured from 42cf219a."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from pyflightstream.workspace.matrix import ResolvedMatrix, resolve_matrix
from tests.tier1_offline.test_matrix_run import RECIPES, make_library

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("fixture", ["matrix.fs", "matrix_registry.fs"])
def test_resolve_matrix_matches_before_the_cut(tmp_path, fixture):
    """P0360-W9c, AD-20: both committed matrices retain their complete binding."""
    workspace = make_library(tmp_path, register_build=("26.120", "FlightStream.exe"))
    resolved = resolve_matrix(
        FIXTURES / fixture,
        workspace,
        name="matrix",
        fs_version="26.120",
        recipes=RECIPES,
        fs_exe="FlightStream.exe" if fixture == "matrix.fs" else None,
    )
    actual = json.loads(TypeAdapter(ResolvedMatrix).dump_json(resolved))
    expected = json.loads((FIXTURES / "p0360_w9c.json").read_text(encoding="utf-8"))
    assert actual == expected[fixture]
