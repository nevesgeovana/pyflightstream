"""P0520-NOREFUSAL (FR-3404): the commands of the 26.126 rotor study are planned, not refused.

Each test is written from the requirement: a row the package refused before is
now planned and built, the command reaches the script in the position that
makes it act (before ``START_SOLVER`` where the march must see it), and where
the build has no measurement of the command the plan warns, naming the
command and the build. This module holds the shared helpers and the coupled
``unsteady_rotor`` row; ``test_p0520_norefusal_*.py`` hold the other lifts.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_aeroelastic_typed_setup import (
    verified_marking_registry as verified_marking_registry,
)

#: The vendor-recommended coupling block of a rotating blade, in order, each
#: command opening its own line (FR-3404): every line of it precedes START_SOLVER.
ROTOR_COUPLING = [
    "AEROELASTIC_RBF_TYPE",
    "DELETE_AEROELASTIC_STRUCTURAL_NODES",
    "ASSIGN_AEROELASTIC_SURFACES",
    "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS",
    "IMPORT_AEROELASTIC_STRUCTURAL_NODES",
    "SET_AEROELASTIC_WORKING_DIRECTORY",
    "SET_AEROELASTIC_POST_PROCESSING_SCRIPT",
    "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
    "SET_AEROELASTIC_ITERATIONS",
    "SET_AEROELASTIC_COUPLING_IN_UNSTEADY",
]


def first_words(text: str) -> list[str]:
    """The command word of every non-blank line, in order."""
    return [line.split()[0] for line in text.splitlines() if line.strip()]


def build(case, version: str = "26.124") -> tuple[Script, list[warnings.WarningMessage]]:
    """Build ``case`` on ``version``, recording every warning."""
    script = Script(version)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build_script(case, script)
    return script, list(caught)


def messages(caught) -> list[str]:
    """The text of every recorded warning."""
    return [str(item.message) for item in caught]


@pytest.mark.requirement("FR-3404")
def test_p0520_a_coupled_unsteady_rotor_row_is_built_with_the_block_before_the_solve(tmp_path):
    # P0520-NOREFUSAL-FSI-ROTOR
    script, caught = build(coupled_case(tmp_path))
    words = first_words(script.render())
    start = words.index("START_SOLVER")
    at = [words.index(command) for command in ROTOR_COUPLING]
    assert at == sorted(at), "the coupling block is emitted in the vendor's order"
    assert at[-1] < start, "every coupling line precedes START_SOLVER"
    lines = script.render().splitlines()
    assert "SET_AEROELASTIC_ITERATIONS 1" in lines
    assert "SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE" in lines
    assert "fsi_callback.py" in script.pending_input_files
    warned = [m for m in messages(caught) if "unsteady_rotor" in m]
    assert warned and "imported azimuth" in warned[0], warned
