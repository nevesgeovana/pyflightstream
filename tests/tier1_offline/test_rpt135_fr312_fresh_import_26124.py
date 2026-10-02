"""FR-312 on recorded 26.124 saves: the fresh import measured, and the reset against it (RPT-135).

The fixture holds the blocks (MESH left out, machine paths replaced) of the ten tier-3 shapes
freshly imported on FlightStream 26.124 (build 8172026) by the tier-3 preparation recipe,
and of D, the blade saved by 26.124 after a 12-step unsteady_rotor solve (far field 5). The
26.124 table is NOT in the released package (FR-312 R2: a 26.124 file keeps its blocks); the
tests give it to the package's own reset in-process, which is what registering it in 0.35.0
would do, and they pin the released behaviour beside it.

D's WAKE (268 lines) and SOLVER (720 lines) are recorded as one placeholder line each,
carrying the block's sha256; the fixture carries the blade's fresh-import hashes of the same
two blocks under the same convention (``block_sha256``), so those two are compared by
content, as the other four blocks the reset puts back are compared by their lines.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from pyflightstream._fsm_fresh import (
    FRESH_IMPORT,
    KEPT_BLOCKS,
    block_lines,
    common_blocks,
    reset_to_fresh_import,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "rpt135" / "fsm_blocks_26124.json"
BUILD124, BUILD120, UNIT = "8172026", "7012026", "METER"
#: The blocks RPT-135 measured the reset to put back on D.
RESET_PUT_BACK: tuple[str, ...] | None = ("GLOBAL", "MOTION", "POST", "WAKE", "SOLVER", "ACOUSTIC")
MESH = ["$MESH_START$", "<the mesh block is not recorded>", "$MESH_END$"]
#: A block of D recorded by its line count and hash rather than by its lines.
HASHED = re.compile(r"<recorded block: (\d+) lines, sha256 ([0-9a-f]{64})>")


def _sha256(lines) -> str:
    """The fixture's convention: the block's lines, markers left out, joined by '|', latin-1."""
    return hashlib.sha256("|".join(lines).encode("latin-1")).hexdigest()


def _content(body) -> str:
    """A recorded block's content hash, read from its placeholder when it carries one."""
    match = HASHED.fullmatch(body[0]) if len(body) == 1 else None
    return match[2] if match else _sha256(body)


def _data() -> dict:
    return json.loads(FIX.read_text(encoding="utf-8"))


def _text(saved: dict) -> str:
    """A saved simulation's text from its recorded head and blocks, MESH a placeholder."""
    lines = list(saved["head"])
    for name, body in saved["blocks"].items():
        if name == "GLOBAL":
            lines += MESH
        lines += [f"${name}_START$", *body, f"${name}_END$"]
    return "\r\n".join(lines) + "\r\n"


def _table() -> dict[str, tuple[str, ...]]:
    return {n: tuple(v) for n, v in _data()["table_26124"].items()}


def test_the_26124_table_is_the_measurement_of_the_ten_fresh_imports_fr_312():
    """common_blocks over the recorded fresh imports gives RPT-135's table, kept blocks left out."""
    # Verifies FR-312.
    fresh = [_text(s) for s in _data()["fresh"].values()]
    assert len(fresh) == 10 and all(s["head"][1] == BUILD124 for s in _data()["fresh"].values())
    measured = {
        n: v for n, v in common_blocks(fresh).items() if n not in KEPT_BLOCKS and n != "MESH"
    }
    assert measured == _table()


def test_the_builds_compared_the_26124_table_is_not_the_26120_one_fr_312():
    """The builds named: a table of one build is not the other's, block by block (R2)."""
    # Verifies FR-312.
    released = FRESH_IMPORT[(BUILD120, UNIT)]
    differing = [n for n in released if _table().get(n) != released[n]]
    assert differing, "the 26.124 fresh import holds the 26.120 content in every block"


def test_the_dirty_save_differs_and_the_reset_puts_back_what_rpt_135_measured_fr_312(monkeypatch):
    """D against the blade's fresh import: different before the reset (the control), equal after."""
    # Verifies FR-312.
    if RESET_PUT_BACK is None:
        pytest.fail("RESET_PUT_BACK is not filled from RPT-135")
    data = _data()
    dirty, fresh = _text(data["dirty"]), _text(data["fresh"]["blade"])
    before = [n for n in _table() if block_lines(dirty)[n] != block_lines(fresh)[n]]
    assert sorted(before) == sorted(RESET_PUT_BACK), before
    # By content, not by the placeholder: the two blocks of D recorded by hash are compared
    # with the fresh blade's hashes of the same convention, which are re-measured first.
    recorded = data["block_sha256"]["fresh_blade"]
    fresh_blocks, dirty_blocks = data["fresh"]["blade"]["blocks"], data["dirty"]["blocks"]
    hashed = [n for n in dirty_blocks if HASHED.fullmatch(dirty_blocks[n][0])]
    assert sorted(hashed) == sorted(recorded) == ["SOLVER", "WAKE"], hashed
    assert all(recorded[n] == _sha256(fresh_blocks[n]) for n in recorded), recorded
    differ = [n for n in _table() if _content(dirty_blocks[n]) != _content(fresh_blocks[n])]
    assert sorted(differ) == sorted(RESET_PUT_BACK), differ
    # The table is registered for this test only, as an entry of the released registry,
    # which is what registering it in 0.35.0 would do; the registry is restored after.
    monkeypatch.setitem(FRESH_IMPORT, (BUILD124, UNIT), _table())
    result = reset_to_fresh_import(dirty, UNIT, "D")
    assert sorted(result.blocks) == sorted(RESET_PUT_BACK) and result.note is None
    after = block_lines(result.text)
    assert all(after[n] == block_lines(fresh)[n] for n in _table())
    assert all(after[n] == block_lines(dirty)[n] for n in after if n not in _table())


def test_the_released_package_keeps_every_block_of_the_recorded_26124_save_fr_312():
    """As released (R2): no 26.124 table, so the recorded save keeps every block and says so."""
    # Verifies FR-312.
    dirty = _text(_data()["dirty"])
    result = reset_to_fresh_import(dirty, UNIT, "D")
    assert result.text == dirty and result.blocks == () and "8172026" in (result.note or "")
