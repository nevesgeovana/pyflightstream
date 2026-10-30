"""P0520-NOREFUSAL-FSI-MARKING (FR-3404): FSI marking on a build without its evidence.

A coupled row marks its boundaries at import. Where a marking command is
documented and not verified on the row's build (every 26.125 verified row is
documented on 26.126 until a run judges it), the plan warns, naming the
commands and the build, and emits them.
"""

from __future__ import annotations

import pytest

from pyflightstream.commands import CommandRegistry, Status
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_aeroelastic_typed_setup import (
    verified_marking_registry as verified_marking_registry,
)
from tests.tier1_offline.test_p0520_norefusal import build, first_words, messages


@pytest.mark.requirement("FR-3404")
def test_p0520_fsi_marking_of_an_unverified_build_warns_and_emits(tmp_path, monkeypatch):
    # P0520-NOREFUSAL-FSI-MARKING
    registry = CommandRegistry.load()
    entry = registry.commands["AUTO_DETECT_TRAILING_EDGES"]
    registry.commands["AUTO_DETECT_TRAILING_EDGES"] = entry.model_copy(
        update={
            "versions": {
                key: value.model_copy(update={"status": Status.DOCUMENTED})
                for key, value in entry.versions.items()
            }
        }
    )
    monkeypatch.setattr(CommandRegistry, "load", classmethod(lambda cls: registry))
    script, caught = build(coupled_case(tmp_path))
    assert "AUTO_DETECT_TRAILING_EDGES" in first_words(script.render())
    named = [m for m in messages(caught) if "AUTO_DETECT_TRAILING_EDGES" in m]
    assert named and "26.124" in named[0] and "not verified" in named[0], messages(caught)
