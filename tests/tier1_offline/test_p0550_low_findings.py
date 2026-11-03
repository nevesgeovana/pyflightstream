"""P0550-LOW: the small defects of the 0.54.0 review that carry no decision.

Pipeline role: tier-1 oracle of PFS-2187.07. Each test runs the verb or the command line a user
runs and reads what the user reads: the message, the exit code and the files.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from tests.tier1_offline.test_p0540_sector_remesh import ARGS, build_blunt_sector


def _messages(call: Callable[[], object]) -> list[str]:
    """Return the text of every warning the call raised."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    return [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]


@pytest.mark.requirement("FR-3520")
def test_p0550_the_sector_angle_warning_states_the_angle_the_copies_need(tmp_path: Path) -> None:
    from pyflightstream.workspace import power_off_body

    source = build_blunt_sector(tmp_path)
    text = " ".join(
        _messages(
            lambda: power_off_body(source, blades=["Blade1"], copies=2, out=tmp_path / "a.fsm")
        )
    )
    assert "2 copies (N = 2 was asked) need 360/2 = 180.0000 deg each" in text
    assert "rotation check below" not in text
    assert "for a whole number N" not in text


def test_p0550_the_body_verb_does_not_speak_of_the_rows_of_a_remesh(tmp_path: Path) -> None:
    from pyflightstream.workspace import power_off_body, sector_remesh

    source = build_blunt_sector(tmp_path)
    body = " ".join(
        _messages(
            lambda: power_off_body(
                source, blades=["Blade1"], copies=5, tip_radius=5.0, out=tmp_path / "b.fsm"
            )
        )
    )
    assert "tip-radius" in body and "largest radius about the axis" in body
    assert "rows of a remesh" not in body
    assert "span rows" not in " ".join(
        _messages(
            lambda: power_off_body(source, blades=["Blade1"], copies=5, out=tmp_path / "c.fsm")
        )
    )
    remesh = " ".join(
        _messages(
            lambda: sector_remesh(
                source, blades=["Blade1"], tip_radius=5.0, out=tmp_path / "r.fsm", **ARGS
            )
        )
    )
    assert "the rows of a remesh stop short" in remesh
