"""Malformed wake headers stay within the reader and post refusal contract."""
# ruff: noqa: N999 - the assigned lane name is rfixA.

from pathlib import Path

import pytest

from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError
from pyflightstream.results.wake import parse_wake_export
from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline import test_p0400_ffproof_post as post

pytestmark = pytest.mark.requirement("P0400-RFIXA-WAKE")
HEADER = "# vtk DataFile Version 3.0\nwake\nASCII\nDATASET POLYDATA\n"


@pytest.mark.parametrize("block", ["POINTS", "LINES", "CELL_DATA", "POINT_DATA"])
@pytest.mark.parametrize("count", ["", " bad", " -1"])
def test_p0400_rfixa_wake_count_headers_are_named_refusals(block, count):
    """FR-16, FR-17: missing counts are incomplete; invalid counts are malformed."""
    error = IncompleteOutputError if not count else MalformedOutputError
    if block == "LINES" and count:
        count += " 0"
    with pytest.raises(error, match=block):
        parse_wake_export(HEADER + block + count + "\n")


@pytest.mark.parametrize("header", ["LINES 2", "LINES 2 bad", "LINES 2 -6"])
def test_p0400_rfixa_wake_lines_size_is_checked(header):
    error = IncompleteOutputError if header == "LINES 2" else MalformedOutputError
    with pytest.raises(error, match="LINES"):
        parse_wake_export(HEADER + header + "\n")


def test_p0400_rfixa_truncated_header_is_a_post_skip(tmp_path):
    workspace = wing._workspace(tmp_path, farfield=True)
    wake = next((workspace.sim_dir("3207") / "outputs").glob("*_wakes.vtk"))
    wake.write_text(HEADER + "POINTS\n")
    post._post(workspace)
    root = Path(workspace.root)
    skipped = post._manifest(root)["skipped"]
    assert any("POINTS" in reason and "truncated" in reason for reason in skipped.values())
    assert any("POINTS" in line for line in post._warnings_of(root))
