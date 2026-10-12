"""P0400-CMDREMOVED and P0400-CMDPROBEREF: two refusals of the per-version command view.

P0400-CMDREMOVED (PFS-2135.020): the removal refusal named the newest
non-removed row over every registered build as "Last documented", so a
command removed on 26.124 and first documented on 26.125 read "Last documented
in 26.125". Only an earlier build is now "last documented"; a later one is
named as a later build.

P0400-CMDPROBEREF (PFS-2102.024): a per-version grammar override on a
probe-cited entry wrote "<report>, the <ver> grammar" into ``probe_ref``
through ``model_copy``, which runs no validator, so the copy carried a
``probe_ref`` its own path rule refuses.
"""

from __future__ import annotations

import pytest

from pyflightstream.commands import (
    _PROBE_REF_PATTERN,
    ArgSpec,
    ArgType,
    CommandEntry,
    CommandNotInVersionError,
    CommandRegistry,
    Layout,
    Phase,
    Status,
    VersionStatus,
)

REPORT = "reports/RPT-018_separation-family-across-builds_2026-08-05.md"


def _entry(versions: dict[str, VersionStatus], **citation: str) -> CommandEntry:
    return CommandEntry(
        name="X_CMD",
        layout=Layout.INLINE,
        phase=Phase.GEOMETRY,
        args=(ArgSpec(name="mode", type=ArgType.ENUM, values=("A", "B")),),
        versions=versions,
        **citation,
    )


def test_p0400_cmdremoved_a_later_build_is_not_last_documented() -> None:
    """P0400-CMDREMOVED: removed on 26.124, documented on 26.125 only."""
    entry = _entry(
        {
            "26.124": VersionStatus(status=Status.REMOVED, probe_ref=REPORT, note="Probed."),
            "26.125": VersionStatus(status=Status.DOCUMENTED),
        },
        manual_ref="SRC-753 p.388",
    )
    registry = CommandRegistry(commands={"X_CMD": entry})
    with pytest.raises(CommandNotInVersionError) as refused:
        registry.for_version("26.124")["X_CMD"]
    message = str(refused.value)
    assert "Last documented in 26.125" not in message
    assert "Documented in the later build(s) 26.125." in message


def test_p0400_cmdremoved_an_earlier_build_is_still_last_documented() -> None:
    """P0400-CMDREMOVED: an earlier documented build is still the last one before removal."""
    entry = _entry(
        {
            "26.100": VersionStatus(status=Status.DOCUMENTED),
            "26.124": VersionStatus(status=Status.REMOVED, probe_ref=REPORT, note="Probed."),
            "26.125": VersionStatus(status=Status.DOCUMENTED),
        },
        manual_ref="SRC-753 p.388",
    )
    registry = CommandRegistry(commands={"X_CMD": entry})
    with pytest.raises(CommandNotInVersionError, match=r"Last documented in 26\.100\. "):
        registry.for_version("26.124")["X_CMD"]


def test_p0400_cmdprobref_override_keeps_a_valid_probe_ref() -> None:
    """P0400-CMDPROBEREF: a probe-cited entry with an args override keeps its probe_ref."""
    entry = _entry(
        {
            "26.100": VersionStatus(
                status=Status.DOCUMENTED,
                note="SRC-747 p.301, this edition's own grammar",
                args=(ArgSpec(name="mode", type=ArgType.ENUM, values=("A",)),),
            ),
            "26.120": VersionStatus(status=Status.DOCUMENTED),
        },
        probe_ref=REPORT,
    )
    resolved = CommandRegistry(commands={"X_CMD": entry}).for_version("26.100")["X_CMD"]
    assert resolved.args[0].values == ("A",)
    assert resolved.manual_ref == ""
    assert resolved.probe_ref == REPORT
    assert _PROBE_REF_PATTERN.match(resolved.probe_ref)
