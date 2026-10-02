"""The five solver-settings toggles that ignored their value (FR-349, WP9a finding).

``solver_settings`` resolved eight of its toggle keywords through the shared
reader before emitting and left five out: ``valarezo_criterion``,
``wake_relaxation``, ``wake_streamwise_agglomeration``,
``adverse_gradient_boundary_layer`` and ``vortex_ring_normalization``. A string
reached the emitter as written, so ``"DISABLE"`` (a non-empty string) wrote
ENABLE and the snapshot stored the string. 0.34.0 reads all five: each keyword
emits what was asked, in either vocabulary, and the record holds a boolean.

Marker for the evidence line of FR-349: P0340-TOGGLES.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

from pyflightstream.script import CommandArgumentError, Script, helpers

VERSION = "26.000"

#: keyword -> the command the solver reads it through (SRC-003 pp.344-346, SRC-740).
FIVE = {
    "valarezo_criterion": "VALAREZO_CRITERION",
    "wake_relaxation": "SET_WAKE_RELAXATION",
    "wake_streamwise_agglomeration": "SET_WAKE_STREAMWISE_AGGLOMERATION",
    "adverse_gradient_boundary_layer": "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
    "vortex_ring_normalization": "SOLVER_VORTEX_RING_NORMALIZATION",
}

#: What the caller may write for a state, in both vocabularies of the toggle.
SPELLINGS = {
    "ENABLE": (True, "ENABLE", "enable"),
    "DISABLE": (False, "DISABLE", "disable"),
}


def _render(keyword: str, value: object) -> tuple[str, object]:
    """The emitted script and the snapshot record of one call asking one toggle."""
    script = Script(version=VERSION)
    script.declare_existing(boundaries={"wing": 1})
    kwargs: dict[str, Any] = {keyword: value}
    setup = helpers.solver_settings(script, **kwargs)
    return script.render(), setup.flags[FIVE[keyword]].value


@pytest.mark.parametrize("keyword", sorted(FIVE))
@pytest.mark.parametrize("state", ["ENABLE", "DISABLE"])
def test_p0340_toggles_fr349_each_keyword_emits_what_was_asked(keyword, state):
    """FR-349 P0340-TOGGLES: ENABLE writes ENABLE and DISABLE writes DISABLE, per keyword.

    Every spelling of the state (the boolean, the upper-case word and the
    lower-case word) emits the one command line with the state asked, and the
    snapshot records the boolean, not the string the caller wrote. On 0.33.0
    every DISABLE spelled as a word emitted ENABLE and recorded the word.
    """
    command = FIVE[keyword]
    expected = state == "ENABLE"
    for spelling in SPELLINGS[state]:
        text, recorded = _render(keyword, spelling)
        lines = [line for line in text.splitlines() if line.startswith(command)]
        assert lines == [f"{command} {state}"], (keyword, spelling, lines)
        assert recorded is expected, (keyword, spelling, recorded)


@pytest.mark.parametrize("keyword", sorted(FIVE))
def test_p0340_toggles_fr349_a_value_in_neither_vocabulary_refuses_before_emitting(keyword):
    """FR-349 P0340-TOGGLES: a value that is no toggle refuses on an untouched script.

    The five keywords now share the refusal of the other eight: a stray word
    raises the script layer's error naming the helper and the keyword, and
    nothing was emitted by the call.
    """
    script = Script(version=VERSION)
    script.declare_existing(boundaries={"wing": 1})
    before = script.render()
    kwargs: dict[str, Any] = {keyword: "MAYBE"}
    with pytest.raises(CommandArgumentError, match=rf"solver_settings: {keyword}"):
        helpers.solver_settings(script, aoa=2.0, **kwargs)
    assert script.render() == before


def test_p0340_toggles_fr349_the_difference_is_named_in_the_parity_checker():
    """FR-349 P0340-TOGGLES: check_parity.py names the flip and holds it to its five lines.

    The only bytes FR-349 changes are a toggle line of these five commands going
    from the state the 0.33.0 defect wrote to the state asked. The entry admits
    changed lines of those five commands with a state, and nothing else, so a
    changed line of any other command is not named by it.
    """
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_parity.py"
    spec = importlib.util.spec_from_file_location("check_parity_fr349", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = [e for e in module.NAMED_DIFFERENCES if e["requirement"] == "FR-349"]
    assert len(entries) == 1
    pattern = entries[0]["lines"]
    for command in FIVE.values():
        for state in ("ENABLE", "DISABLE"):
            assert re.search(pattern, f"{command} {state}"), (command, state)
    for other in (
        "SET_WAKE_ON_WAKE_INDUCTION DISABLE",
        "SET_WAKE_RELAXATION MAYBE",
        "SET_PROP_ACTUATOR_RPM 1 -300",
        "VALAREZO_CRITERION",
    ):
        assert not re.search(pattern, other), other
    assert re.fullmatch(
        entries[0]["block"], "SET_WAKE_RELAXATION ENABLE\nSET_WAKE_RELAXATION DISABLE"
    )
    assert not re.fullmatch(entries[0]["block"], "SET_WAKE_ON_WAKE_INDUCTION ENABLE")
