"""G24 of 0.28.0: the boundary-layer velocity profile, refused on 26.124 by name.

The licensed probe T20 (RPT-075) ran ``EXPORT_BL_VELOCITY_PROFILE`` on FlightStream
26.124 after a steady solve: the script stopped at it and the run was lost at its
timeout, as on 26.122, where the command opens a modal window that waits for a
person (RPT-027). The approved decision built the pproc route only if 26.124 ran it
unattended; it does not, so the command is recorded broken on 26.124 from the
probe's compat transcription, and a row that writes it raw is refused at plan,
naming the report, before a seat is spent.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import RawCommand
from pyflightstream.cases.workflows import build_script
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import BrokenCommandError, CommandArgumentError, Script
from tests.tier1_offline.test_workflows import steady_case

#: The line a user would write in a row's raw entries: frame 1, a point, the file.
LINE = "EXPORT_BL_VELOCITY_PROFILE 1 0.5 0.0 0.1 bl_profile.txt"
REPORT = "reports/compat/CMP-26124_2026-09-25_bl-profile.yaml"
REPORT_26125 = "reports/compat/CMP-26125_2026-10-16_bl-profile.yaml"


def _case():
    return steady_case().model_copy(
        update={"raw_commands": [RawCommand(command=LINE, before="export")]}
    )


def test_g24_the_command_is_recorded_broken_on_26124_from_the_probe():
    """Promoted by pyfs-qa apply-compat from the transcription, never by hand."""
    row = CommandRegistry.load().commands["EXPORT_BL_VELOCITY_PROFILE"].versions["26.124"]
    assert row.status is Status.BROKEN, row.status
    assert row.report == REPORT, row.report


@pytest.mark.requirement("FR-115")
def test_g24_a_row_writing_it_raw_is_refused_on_26124_naming_the_report():
    with pytest.raises(BrokenCommandError) as raised:
        build_script(_case(), Script("26.124"))
    text = str(raised.value)
    assert "EXPORT_BL_VELOCITY_PROFILE" in text and REPORT in text, text
    assert "allow_broken" in text, text


def test_g24_on_a_build_where_it_is_documented_the_line_is_still_written():
    """The record is by build: 26.123 documents the command and was not probed."""
    script = Script("26.123")
    build_script(_case(), script)
    assert any(
        line.startswith("EXPORT_BL_VELOCITY_PROFILE 1") for line in script.render().splitlines()
    )


@pytest.mark.requirement("FR-3216")
@pytest.mark.parametrize("waived", [False, True], ids=["P0450-G52-default", "P0450-G52-waived"])
def test_p0450_g52_26125_refuses_modal_profile_before_emission(waived):
    """Even allow_broken cannot make a measured modal export unattended."""
    script = Script("26.125")
    if waived:
        script.allow_broken("EXPORT_BL_VELOCITY_PROFILE", reason="test the modal restriction")
    before = script.render()
    error = CommandArgumentError if waived else BrokenCommandError
    with pytest.raises(error) as raised:
        script.emit("EXPORT_BL_VELOCITY_PROFILE", 1, 0.5, 0.0, 0.1, "bl_profile.txt")
    message = str(raised.value)
    for expected in ("26.125", REPORT_26125, "raw()", "supervised", "integrated viscous drag"):
        assert expected in message
    assert script.render() == before


@pytest.mark.requirement("FR-3216")
def test_p0450_g52_26125_plan_refuses_profile_with_its_report():
    with pytest.raises(BrokenCommandError, match="CMP-26125_2026-10-16_bl-profile"):
        build_script(_case(), Script("26.125"))


@pytest.mark.requirement("FR-3216")
def test_p0450_g52_supervised_raw_escape_remains_explicit():
    script = Script("26.125")
    script.raw(LINE)
    assert LINE in script.render()
