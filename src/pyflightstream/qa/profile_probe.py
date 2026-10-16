"""Preparation of an explicitly located, unattended profile probe.

Pipeline role: maintainer receipt preparation. This factory is deliberately
outside the automatic probe catalog and does not enable the product.
"""

from __future__ import annotations

import math
from pathlib import Path

from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.probes import ProbeArtifacts, ProbeSpec, Requires, file_effect
from pyflightstream.script import Script

__all__ = ["unattended_profile_spec"]


def unattended_profile_spec(point: tuple[float, float, float]) -> ProbeSpec:
    """Prepare G52's receipt against an explicitly supplied solved surface point.

    Use only with build 26.125 and a saved, solved control state. The session
    selects the upper-wing point from its control export, as RPT-075 describes.
    This spec is deliberately absent from the generic probe catalog: its
    geometry-dependent input must never be guessed. A nonempty file proves
    export completion only; inspection of its format and product acceptance
    remain separate, and the product stays disabled.
    """
    if len(point) != 3 or not all(math.isfinite(value) for value in point):
        raise QaEvidenceError("profile probe point requires three finite reference coordinates")

    def target(script: Script, workdir: Path) -> None:
        if script.version.canonical != "26.125":
            raise QaEvidenceError("the G52 unattended-profile receipt is scoped to build 26.125")
        script.emit("EXPORT_BL_VELOCITY_PROFILE", 1, *point, workdir / "profile.txt")

    def observe(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / "profile.txt"
        size = path.stat().st_size if path.is_file() else 0
        return f"profile.txt: {size} bytes; format and physical interpretation not yet accepted"

    return ProbeSpec(
        command="EXPORT_BL_VELOCITY_PROFILE",
        build_target=target,
        requires=Requires.SIM,
        assert_effect=file_effect("profile.txt"),
        observe=observe,
        timeout_s=120.0,
        effect_note="a nonempty profile file and the after-target sentinel complete unattended",
    )
