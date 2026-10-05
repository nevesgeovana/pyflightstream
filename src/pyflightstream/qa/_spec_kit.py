"""Shared instruments of the probe specification catalog.

Pipeline role: the build callables, effect assertions and the registry
every catalog module (``qa.specs`` and the modules it imports) draws on,
so the catalog can be written in several modules none of which holds the
whole of it. ``PROBE_SPECS`` is created here and filled by the catalog
modules; ``pyflightstream.qa.specs`` re-exports it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyflightstream.qa.probes import (
    ProbeArtifacts,
    ProbeSpec,
    printed_line,
)
from pyflightstream.script import Script

#: The catalog exports its catalog and nothing else. Without this, every
#: non-underscore definition here is public the moment the wheel ships,
#: which would make three effect-assertion helpers of this module part
#: of the supported surface by accident (the rule is stated in
#: tests/tier1_offline/test_exceptions_catalog.py: an absent __all__ means the module

__all__ = ["PROBE_SPECS"]

_NESTED_NAME = "nested_probe.txt"
_SHEET = "sheet.txt"


# --- shared instruments -------------------------------------------------


def _sheet(script: Script, workdir: Path) -> None:
    """Export the settings sheet, the universal state instrument."""
    script.emit("EXPORT_PROBE_POINTS", workdir / _SHEET)


def _saveas(script: Script, workdir: Path) -> None:
    """Save the simulation for the name-greppability instrument."""
    script.emit("SAVEAS", workdir / "saved.fsm")


def _seq(*parts: Callable[[Script, Path], None]) -> Callable[[Script, Path], None]:
    """Chain build callables into one."""

    def build(script: Script, workdir: Path) -> None:
        for part in parts:
            part(script, workdir)

    return build


def _read(workdir: Path, name: str) -> str | None:
    path = workdir / name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")


def sheet_matches(pattern: str, strict: bool = True) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: the settings sheet matches ``pattern`` (regex).

    Strict only for labels the recon proved the sheet exposes; a
    missing sheet always returns None (the instrument, not the target,
    failed).
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        sheet = _read(artifacts.workdir, _SHEET)
        if sheet is None:
            return None
        if re.search(pattern, sheet):
            return True
        return False if strict else None

    return check


def fsm_grep(token: str, expect: bool = True) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: a readable name is present (or absent) in the saved file.

    Object names survive as text in a SAVEAS file (recon-proven);
    numeric fields do not. A missing saved file returns None.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / "saved.fsm"
        if not path.is_file():
            return None
        present = token.encode("ascii") in path.read_bytes()
        return present is expect

    return check


def _unobservable(artifacts: ProbeArtifacts) -> None:
    """Effect placeholder: the state is not observable yet (unprobed)."""
    return None


def region_printed_lax(marker: str) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: a log message in the target region, None when silent."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        return True if printed_line(artifacts.target_region(), marker) else None

    return check


def _log_printed(marker: str) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: a message in the log exported after the epilogue.

    None when that log never appeared (the epilogue aborted, so the
    instrument, not the target, failed).
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        final = artifacts.log_final()
        if final is None:
            return None
        return printed_line(final, marker)

    return check


def _file_lax(name: str, minimum_bytes: int = 1) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: an epilogue-produced file has content, None when absent.

    Lax because the file is written by a support command, not by the
    target: absence may mean the instrument broke, never proof of a
    target no-op.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        if path.is_file() and path.stat().st_size >= minimum_bytes:
            return True
        return None

    return check


def _emit(command: str, *args: object, **kwargs: Any) -> Callable[[Script, Path], None]:
    """Make a build callable that emits one fixed command."""

    def build(script: Script, workdir: Path) -> None:
        script.emit(command, *args, **kwargs)

    return build


def _emit_full(
    command: str, *args: object, tail: tuple[tuple[str, object], ...]
) -> Callable[[Script, Path], None]:
    """Emit a command with the trailing arguments its build's grammar names (FR-423).

    ``tail`` pairs an argument name with the value passed for it. Each is
    appended only on a build whose grammar of ``command`` names it, so one
    specification writes the form each edition prints: the 26.125 manual adds
    DIRECTION, SPACE and AXIS to commands that earlier builds print without.
    """

    def build(script: Script, workdir: Path) -> None:
        names = {arg.name for arg in script.registry.for_version(script.version)[command].args}
        extra = [value for name, value in tail if name in names]
        script.emit(command, *args, *extra)

    return build


def _named_frame(name: str) -> Callable[[Script, Path], None]:
    """Create local frame 2 and give it a greppable name."""

    def build(script: Script, workdir: Path) -> None:
        script.emit("CREATE_NEW_COORDINATE_SYSTEM")
        script.emit(
            "EDIT_COORDINATE_SYSTEM",
            frame=2,
            name=name,
            origin_x=0.1,
            origin_y=0.0,
            origin_z=0.0,
            vector_x_x=1.0,
            vector_x_y=0.0,
            vector_x_z=0.0,
            vector_y_x=0.0,
            vector_y_y=1.0,
            vector_y_z=0.0,
            vector_z_x=0.0,
            vector_z_y=0.0,
            vector_z_z=1.0,
        )

    return build


PROBE_SPECS: dict[str, ProbeSpec] = {}


def _spec(**kwargs: Any) -> None:
    spec = ProbeSpec(**kwargs)
    PROBE_SPECS[spec.command] = spec
