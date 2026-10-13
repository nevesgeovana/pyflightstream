"""Shared support of the P0400 command-gap tests: a command database with chosen statuses.

The streamline and 6DOF commands were recorded ``documented`` and unprobed on
26.124 when their routes were written, and the evidence gate refuses them
at plan. The emission tests build their scripts against
a copy of the committed database in which the commands they name carry the
status the test needs on one build, so a golden runs the real emission path
before the licensed probes record the evidence and after it, and the refusal
test sees an unverified record whatever the committed one says. Nothing is
patched: the script is given the registry, as any caller may give one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from pyflightstream.commands import CommandRegistry, Status, VersionStatus
from pyflightstream.versions import resolve

#: The report a test-only verified record cites; never a committed file.
TEST_REPORT = "reports/compat/TEST-ONLY_p0400_gaps_rt.yaml"


def registry_with(
    commands: Iterable[str],
    build: str,
    status: Status,
    base: CommandRegistry | None = None,
) -> CommandRegistry:
    """Return ``base`` (the committed database) with ``commands`` given ``status`` on ``build``."""
    registry = base if base is not None else CommandRegistry.load()
    canonical = resolve(build).canonical
    changed = {}
    for name in commands:
        entry = registry.commands[name]
        record = VersionStatus.model_construct(
            status=status,
            report=TEST_REPORT if status in (Status.VERIFIED, Status.BROKEN) else None,
        )
        versions = {**entry.versions, canonical: record}
        changed[name] = entry.model_copy(update={"versions": versions})
    return replace(registry, commands={**registry.commands, **changed})
