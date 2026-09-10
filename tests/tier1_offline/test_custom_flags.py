"""Tier 1: the setup declares custom flags and a row sets them (PFS-2035.20).

The author's design of 2026-09-10, in her own words: "no setup, quero
adicionar a declaracao de custom flags, o usuario pode passar o nome do
comando do flightstream e a flag se torna acessivel via matriz. Assim o uso do
raw realmente vai ficar para casos particulares", and then the condition that
shapes the whole feature: "o custom flags tambem passa pelo check de emit".

WHAT THIS IS FOR, and why it is not the [[raw]] table that already exists. A
raw entry is a whole command LINE with its arguments, fixed in the preset, so
every row citing that preset emits the same one. A flag names the command and
the ROW states the value, so one preset serves a SWEEP over that value. That
is what leaves RAW to the particular case its name promises rather than making
it the ordinary way to reach any setting the package does not curate.

THE EMIT CHECK IS THE POINT. The line goes out through `Script.emit_line`, so
a flag naming a command this build cannot emit, or given a value of the wrong
type, is refused when the row is PLANNED and never at the licensed machine.
The cases below measure that on both sides: the good line reaches the script,
and each of the three ways to get it wrong is refused with the flag named.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CustomFlag, SimCase, SweepAxis
from pyflightstream.cases.workflows import WORKFLOW_KEY, build_script
from pyflightstream.script import Script

#: A COMMAND OF THE SETUP PHASE, chosen because a flag may only reach the
#: three seams the builders open and this one has a database entry on every
#: build the suite covers. Its argument is an integer, which is what lets the
#: wrong-type case below be a real refusal rather than a spelling.
SETUP_COMMAND = "SET_SIGNIFICANT_DIGITS"


def case(**overrides) -> SimCase:
    """A steady row, with whatever flags and variables the case under test wants."""
    fields = {
        "sim_id": "9501",
        "aircraft": "WORK",
        "recipe": "steady",
        "sweep": SweepAxis(type="alpha", values=[0.0]),
        "point": {"alpha": 0.0},
        "outputs": ["loads_a+00.0.txt"],
        # `matrix_workflow` AND NOT `recipe`: the key guard leaves a case
        # whose RECIPE names the type alone, because a recipe is the reader
        # of its own keys, so a fixture built the other way would exercise
        # the guard nowhere and the flag's registration would prove nothing.
        "variables": {WORKFLOW_KEY: "steady", "VELOCITY": "30.0"},
    }
    variables = dict(fields["variables"])
    variables.update(overrides.pop("variables", {}))
    fields["variables"] = variables
    fields.update(overrides)
    return SimCase(**fields)


def rendered(sim: SimCase) -> list[str]:
    script = Script("26.123")
    build_script(sim, script)
    return script.render().splitlines()


def flag(**overrides) -> CustomFlag:
    fields = {"name": "digits", "command": SETUP_COMMAND, "setup": "s500"}
    fields.update(overrides)
    return CustomFlag(**fields)


# --- the flag reaches the script --------------------------------------------


@pytest.mark.requirement("FR-74")
def test_a_row_stating_a_declared_flag_emits_the_command_with_the_rows_value():
    """The whole feature in one case: the preset names the command, the row the value."""
    lines = rendered(case(flags=[flag()], variables={"digits": "6"}))
    assert f"{SETUP_COMMAND} 6" in lines, (
        f"the flag did not reach the script; the setup-phase lines are "
        f"{[line for line in lines if line.startswith('SET_')]}"
    )


def test_the_word_is_read_case_folded_as_every_other_row_key_is():
    """A cell writing DIGITS reaches a flag declared `digits`.

    Without this the feature has a rule of its own: every other key of a
    row is matched case folded, and one that is not would be a trap
    whose only symptom is a command that quietly does not appear.
    """
    lines = rendered(case(flags=[flag()], variables={"DIGITS": "6"}))
    assert f"{SETUP_COMMAND} 6" in lines, lines


def test_a_row_that_states_no_flag_emits_nothing_for_it():
    """The discriminator. Without it every case above is satisfied by a
    builder that emits the command whatever the row says."""
    lines = rendered(case(flags=[flag()]))
    assert not any(line.startswith(SETUP_COMMAND) for line in lines), (
        "the command was emitted for a row that states no value for the flag"
    )


def test_a_cell_written_with_an_empty_value_states_nothing():
    """`digits:` is a half-finished edit, not a request to emit with no argument.

    Read as a value it would reach the emitter as a bare command and be
    refused there for its arity, which is a true sentence about the
    command and says nothing about the row the user is holding.
    """
    lines = rendered(case(flags=[flag()], variables={"digits": "  "}))
    assert not any(line.startswith(SETUP_COMMAND) for line in lines), lines


#: A COMMAND OF THE CONTROL PHASE, whose phase the database leaves open. It is
#: the case a flag reaches at every seam, so it is the one that proves the
#: line goes out ONCE rather than once per seam.
CONTROL_COMMAND = "PRINT"


def test_a_control_phase_flag_is_emitted_exactly_once():
    """THE MUTANT THAT SURVIVED TWELVE CASES, written down as a case.

    `_custom_flags` runs at all three seams. The derived phase of a CONTROL
    command was read from the CURRENT phase, so it equalled whatever seam
    was asking and the skip never fired: the line went out three times. The
    QA lens measured three emissions of `PRINT`, and `SAVEAS` and
    `RUN_SCRIPT` are in the same set and are not idempotent.

    COUNTING IS THE POINT. Every other case here asserts the line is IN the
    script, and membership is satisfied by one emission or by three.
    """
    lines = rendered(case(flags=[flag(command=CONTROL_COMMAND)], variables={"digits": "hello"}))
    emitted = [line for line in lines if line.startswith(f"{CONTROL_COMMAND} ")]
    assert len(emitted) == 1, (
        f"a control-phase flag was emitted {len(emitted)} times, once per seam the "
        f"builder opens: {emitted}"
    )


def test_a_setup_phase_flag_is_emitted_exactly_once_too():
    """The control for the case above: the counting is not about CONTROL."""
    lines = rendered(case(flags=[flag()], variables={"digits": "6"}))
    emitted = [line for line in lines if line.startswith(f"{SETUP_COMMAND} ")]
    assert len(emitted) == 1, f"emitted {len(emitted)} times: {emitted}"


def test_the_declaration_folds_the_word_it_stores():
    """The declaration side of the fold, which no case reached.

    A mutant that stopped folding the DECLARED name survived, and it was a
    no-op: the fixture's flag name is already lower case, so the mutation
    changed nothing and the survival was evidence of nothing. This states
    the name in capitals, so the fold has somewhere to happen.
    """
    lines = rendered(case(flags=[flag(name="DIGITS")], variables={"digits": "6"}))
    assert f"{SETUP_COMMAND} 6" in lines, lines


# --- the emit check, which is the author's own condition ---------------------


@pytest.mark.requirement("FR-74")
def test_a_flag_naming_a_command_the_build_cannot_emit_is_refused_naming_the_flag():
    """The condition the author set on the feature, measured.

    A flag is a declaration rather than a string substitution precisely
    so that this can happen at plan time: the command database is asked
    the same question it is asked for every curated emission.
    """
    from pyflightstream._errors import PyflightstreamError

    with pytest.raises(PyflightstreamError) as refused:
        rendered(case(flags=[flag(command="NO_SUCH_COMMAND")], variables={"digits": "6"}))
    message = str(refused.value)
    assert "digits" in message and "s500" in message, (
        f"the refusal does not name the flag and the setup that declared it: {message}"
    )
    assert "NO_SUCH_COMMAND" in message, message


@pytest.mark.requirement("FR-74")
def test_a_value_of_the_wrong_type_is_refused_with_the_value_named():
    """The second half of the same check: the ARGUMENT is judged too.

    A flag that reached the script as text would put `SET_SIGNIFICANT_DIGITS
    six` in front of the solver and the run would fail at the machine, on a
    seat, for a typo a reader could have been shown at plan time.
    """
    from pyflightstream._errors import PyflightstreamError

    with pytest.raises(PyflightstreamError) as refused:
        rendered(case(flags=[flag()], variables={"digits": "six"}))
    message = str(refused.value)
    assert "digits" in message and "'six'" in message, message


def test_a_flag_naming_a_command_of_a_later_phase_is_refused_rather_than_dropped():
    """A flag has three seams to reach, and a command outside them has none.

    Emitting an `init` command before `setup` would advance the script
    past its init phase and the order guard would then refuse the phase's
    own commands, so the flag cannot simply be moved; and a flag that
    quietly did not appear is the silence this package refuses everywhere
    else. The refusal names the phase and points at the table that IS the
    escape.
    """
    from pyflightstream.cases import CampaignConfigError

    with pytest.raises(CampaignConfigError, match="init"):
        rendered(case(flags=[flag(command="SOLVER_SET_ITERATIONS")], variables={"digits": "600"}))


# --- the declaration itself --------------------------------------------------


def test_a_flag_whose_command_carries_arguments_is_refused():
    """The value would then be stated twice, and the two could disagree."""
    with pytest.raises(ValueError, match="arguments"):
        CustomFlag(name="digits", command=f"{SETUP_COMMAND} 6")


def test_a_flag_naming_no_command_is_refused_naming_the_flag():
    with pytest.raises(ValueError, match="digits"):
        CustomFlag(name="digits", command="")


def test_a_flag_declared_before_a_word_that_names_no_phase_is_refused():
    with pytest.raises(ValueError, match="whenever"):
        CustomFlag(name="digits", command=SETUP_COMMAND, before="whenever")


# --- the key guard ------------------------------------------------------------


@pytest.mark.requirement("FR-74")
def test_the_flags_word_is_a_key_the_row_may_state():
    """A row states a key no run type registers and is refused; a DECLARED
    flag is registered by the declaration, and refusing it would refuse
    the one key the preset just said the row could write.

    The control is the next case: an undeclared word is still refused, so
    this is not the guard being switched off.
    """
    lines = rendered(case(flags=[flag()], variables={"digits": "6"}))
    assert f"{SETUP_COMMAND} 6" in lines


def test_a_word_no_flag_declares_is_still_refused():
    """The control for the case above."""
    from pyflightstream.cases import CampaignConfigError

    with pytest.raises(CampaignConfigError, match="FOO_BAR"):
        rendered(case(flags=[flag()], variables={"FOO_BAR": "1"}))
