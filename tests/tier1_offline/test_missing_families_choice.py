"""Tier 1: the run chooses whether a missing family skips or refuses (PFS-2035.13).

The author's design of 2026-09-10, asked one question at a time and answered in the author's
own words: "a minha ideia era ter uma flag na chamada da linha de comando
--ignore_missing_families e ali o usuario poder passar false, sendo que o
default e true".

WHAT MAKES IT A FLAG AND NOT A CELL. A post-processing artifact names
families, and the same artifact is meant to serve a wing-body and an
isolated rotor: a family the opened mesh does not carry is left out, which
is the artifact's own rule (PFS-2035.01) and the reason one file covers
several geometries. That skip and a MISSPELLED family read exactly alike
from the script. So whether the skip is right is a property of THIS
INVOCATION's intent rather than of the row or of the artifact, and the
choice travels on the command line.

Three layers, one per section below: the word the shell passes, the case
variable the resolution writes, and the reader that honours it.
"""

from __future__ import annotations

import argparse

import pytest

from pyflightstream.cases import (
    AliasCycleError,
    CampaignConfigError,
    SimCase,
    SweepAxis,
    alias_members_missing,
)
from pyflightstream.cases.workflows import (
    IGNORE_MISSING_FAMILIES_VARIABLE,
    _ignore_missing_families,
    _selected_families,
    read_a_choice,
)
from pyflightstream.run.cli import (
    _a_word_that_means_false,
    _build_parser,
    _the_missing_family_choice,
)

#: The boundaries the synthetic mesh carries. It has a wing and no rotor,
#: which is the shape the skip exists for: an artifact naming both serves
#: it and the rotor-only geometry beside it.
INVENTORY = ["WING", "FUSELAGE"]


def case(**overrides) -> SimCase:
    fields = {
        "sim_id": "9401",
        "aircraft": "WORK",
        "recipe": "steady",
        "sweep": SweepAxis(type="alpha", values=[0.0]),
        "aliases": {"airframe": ["WING", "FUSELAGE"]},
    }
    fields.update(overrides)
    return SimCase(**fields)


def expand(subject: SimCase):
    """Expand one entry naming a family this geometry does not carry."""
    return _selected_families(
        subject, "BLADE_1", INVENTORY, lambda name: "BLADE" in name, "a plot group"
    )


# --- the word the shell passes ---------------------------------------------


@pytest.mark.requirement("FR-73")
@pytest.mark.parametrize("word", ["false", "FALSE", " False ", "no", "0"])
def test_the_words_that_mean_false_are_read_as_false(word):
    """The author asked to be able to pass false, and argparse's store_true cannot."""
    assert _a_word_that_means_false(word) is False


@pytest.mark.requirement("FR-73")
@pytest.mark.parametrize("word", ["true", "TRUE", " Yes ", "1"])
def test_the_words_that_mean_true_are_read_as_true(word):
    assert _a_word_that_means_false(word) is True


@pytest.mark.requirement("FR-73")
@pytest.mark.parametrize("word", ["off", "flase", "False.", "anything", "", "disable"])
def test_a_word_outside_the_vocabulary_is_refused_and_never_read_as_the_default(word):
    """THE FLAG MUST NOT FAIL SILENT, which is the whole reason it exists.

    The first version read every word but three as TRUE, so
    `--ignore-missing-families off` gave the user the SKIP: the silence
    they passed the flag to escape, on a run that planned green with
    nothing anywhere saying the word was not understood. Two review lenses
    raised it at severity 1 on 2026-09-10, and the estate had already
    written the rule down: `pyflightstream.script.toggles` refuses anything
    outside its two words, and its module docstring carries the incident
    that taught it. Truthiness has no failure mode; this reader does.

    The refusal names BOTH halves of the vocabulary, because a user who
    wrote the wrong word for NO needs to see the right words for NO.
    """
    with pytest.raises(argparse.ArgumentTypeError) as refused:
        _a_word_that_means_false(word)
    message = str(refused.value)
    assert "--ignore-missing-families" in message
    assert "true, yes, 1" in message
    assert "false, no, 0" in message


@pytest.mark.requirement("FR-73")
def test_plan_and_run_take_the_flag_and_default_to_true():
    """The default is the skip, which is what every row written so far means.

    Read through `_the_missing_family_choice`, which is the ONE reader of the
    pair, and never off the namespace. The parser's own default is `None`
    rather than `True` so that a command stating both spellings can be told
    from silence and refused; `None` is an intermediate nothing outside that
    function sees, and asserting on it would tie this test to a spelling
    instead of to the behaviour.
    """
    parser = _build_parser()
    for command in ("plan", "run"):
        bare = parser.parse_args([command, "m.fs", "--workspace", "."])
        assert _the_missing_family_choice(bare) is True, command
        stated = parser.parse_args(
            [command, "m.fs", "--workspace", ".", "--ignore-missing-families", "false"]
        )
        assert _the_missing_family_choice(stated) is False, command
        # BARE IS TRUE, which is the ordinary shape of a flag and is what
        # `nargs="?"` with `const=True` buys: writing the flag alone asks
        # for the behaviour the flag is named after.
        alone = parser.parse_args(
            [command, "m.fs", "--workspace", ".", "--ignore-missing-families"]
        )
        assert _the_missing_family_choice(alone) is True, command
        # THE FLAG SPELLING OF THE SAME CHOICE.
        negated = parser.parse_args(
            [command, "m.fs", "--workspace", ".", "--no-ignore-missing-families"]
        )
        assert _the_missing_family_choice(negated) is False, command


@pytest.mark.requirement("FR-73")
def test_stating_both_spellings_is_refused_rather_than_resolved():
    """Two statements of one choice cannot both be the one obeyed.

    This is the case the `None` default exists for: with `True` as the
    default the reader could not tell a stated `true` from silence, so a
    command writing the flag AND the word would have been resolved by
    precedence instead of refused.
    """
    parser = _build_parser()
    for word in ("true", "false"):
        both = parser.parse_args(
            [
                "plan",
                "m.fs",
                "--workspace",
                ".",
                "--no-ignore-missing-families",
                "--ignore-missing-families",
                word,
            ]
        )
        with pytest.raises(SystemExit):
            _the_missing_family_choice(both)


@pytest.mark.requirement("FR-73")
def test_convert_does_not_take_it_because_it_writes_a_file_that_outlives_the_call():
    """A per-invocation choice frozen into an artifact stops being one.

    `convert` emits a campaign.toml that is read later by something that
    never saw this command line, so the flag would become a property of
    the file. `plan` and `run` act now, and the choice dies with them.
    """
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["convert", "m.fs", "--fs-exe", "C:/fs/FlightStream.exe", "--ignore-missing-families"]
        )


# --- the case variable the resolution writes -------------------------------


@pytest.mark.requirement("FR-73")
def test_a_row_that_states_nothing_skips_because_that_is_what_every_row_means():
    """Absent, it is TRUE: PFS-2035.01 unchanged, and no row is rewritten."""
    assert _ignore_missing_families(case()) is True


@pytest.mark.requirement("FR-73")
@pytest.mark.parametrize("stated", ["false", "FALSE", "no", "0"])
def test_the_variable_turns_the_skip_into_a_refusal(stated):
    """Ignoring is what the reader answers, so the four spellings turn it OFF."""
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: stated})
    assert _ignore_missing_families(subject) is False


@pytest.mark.requirement("FR-73")
def test_the_variable_refuses_a_word_outside_the_vocabulary_too():
    """ONE VOCABULARY, ONE READER, both ends.

    The tuple of no-words was written twice, in two layers, with nothing
    asserting the two agreed (the architecture lens of 2026-09-10). They
    are one function now, so a word the command line refuses is a word the
    row variable refuses, and this case is what keeps that true.
    """
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "off"})
    with pytest.raises(CampaignConfigError) as refused:
        _ignore_missing_families(subject)
    assert "'off' is not a yes or a no" in str(refused.value)
    assert IGNORE_MISSING_FAMILIES_VARIABLE in str(refused.value)


@pytest.mark.requirement("FR-73")
def test_a_python_caller_may_pass_the_value_it_means():
    """A bool passes through, so the reader is not a string-only door."""
    assert read_a_choice(True, context="x") is True
    assert read_a_choice(False, context="x") is False


@pytest.mark.requirement("FR-73")
def test_the_default_writes_nothing_onto_the_case(tmp_path):
    """MEASURED, and it is the promise the upgrade rests on.

    A variable written on BOTH sides would put a new key into every
    campaign of the 0.14.0 comparison and rename nothing while changing
    what the record carries. At the default the resolved case must be the
    case it was before this argument existed.
    """
    resolved = resolve_one(tmp_path)
    assert IGNORE_MISSING_FAMILIES_VARIABLE not in resolved.variables


@pytest.mark.requirement("FR-73")
def test_false_reaches_the_case_as_a_variable(tmp_path):
    """The command line writes it; the cases layer never learns one exists."""
    resolved = resolve_one(tmp_path, ignore_missing_families=False)
    assert resolved.variables[IGNORE_MISSING_FAMILIES_VARIABLE] == "false"
    assert _ignore_missing_families(resolved) is False


ROW = (
    "9401 | TestWing | MISSING_FAMILIES | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 |          | 0 | 1 | OUTPUTS: loads_{point}.txt"
)


def workflow_matrix(tmp_path, name, row=ROW):
    """Write ROW as a matrix and turn it into a RUN TYPE row.

    NOT LEGACY, AND THE MUTANT IS WHY. `write_matrix` upgrades a pre-0.8.0
    row, whose WORKFLOW becomes LEGACY, and a LEGACY row keeps its own
    variable keys because its RECIPE is their reader. On such a row the
    key guard never runs, so a fixture left LEGACY let the mutant that
    unregisters this key pass with every case green.
    """
    from tests.tier1_offline.test_matrix_run import write_matrix

    path = write_matrix(tmp_path / name, [row])
    text = path.read_text(encoding="utf-8")
    path.write_text(
        # RECIPE GOES WITH THE WORKFLOW WORD. The upgrade moves a LEGACY
        # row's code into its variables, because a LEGACY row's recipe is
        # what reads them; a run-type row registers no such key and is
        # blocked for it, which is the key guard doing its job on a
        # fixture that half-converted.
        text.replace("| LEGACY ", "| steady ")
        .replace("OUTPUTS: loads_{point}.txt / ", "")
        .replace("OUTPUTS: loads_{point}.txt", "")
        .replace(" / RECIPE: 003", "")
        .replace("RECIPE: 003", ""),
        encoding="utf-8",
    )
    return path


def resolve_one(tmp_path, **kwargs) -> SimCase:
    """Resolve one row against a synthetic library and return its case."""
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, make_library

    workspace = make_library(tmp_path)
    path = workflow_matrix(tmp_path, "families.fs")
    resolved = resolve_matrix(
        path,
        workspace,
        name="families",
        fs_version="26.120",
        recipes=RECIPES,
        fs_exe="C:/fs/FlightStream.exe",
        **kwargs,
    )
    return next(sim for sim in resolved.campaign.sims if sim.sim_id == "9401")


@pytest.mark.requirement("FR-73")
def test_a_point_still_plans_ready_when_the_run_asked_for_the_refusal(tmp_path):
    """MEASURED END TO END, and it is the case a unit test could not reach.

    The variable the flag writes is a case variable, and every case
    variable is checked against the keys its run type registers: a key
    nothing reads is refused rather than ignored. So writing the variable
    without registering it BLOCKED EVERY POINT of the author's own matrix,
    23 of 23, with a refusal about a key of no run type and not a word
    about a family. A refusal test alone would never have seen it, because
    the refusal it asserts is the one that fired.
    """
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run import PlanStatus
    from pyflightstream.run.matrix import plan_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, make_library

    workspace = make_library(tmp_path)
    path = workflow_matrix(tmp_path, "families.fs")
    plan = plan_matrix(
        path,
        workspace,
        name="families",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        fs_exe="C:/fs/FlightStream.exe",
        write_plan=False,
        ignore_missing_families=False,
    )
    assert [point.status for point in plan.points] == [PlanStatus.READY] * len(plan.points)
    assert plan.points, "the fixture planned no point at all, so this asserted nothing"


@pytest.mark.requirement("FR-73")
def test_a_cell_may_not_state_the_key_because_the_row_is_not_where_it_belongs(tmp_path):
    """Registered means typable, and typed in a cell it stops being a choice.

    The key had to be registered on every run type so the flag's own write
    is not refused. That makes it a word a user can put in a cell, and a
    cell says what the ROW is; the same row is planned across a wing and a
    rotor, which is the whole reason the skip exists. So the reader
    refuses it there and names the flag, the way it has refused
    `LOG_OUTPUT` on a workflow row since 0.11.0.
    """
    from pyflightstream.cases.matrix import MatrixError, read_matrix

    stated = ROW.replace(
        "OUTPUTS: loads_{point}.txt",
        "OUTPUTS: loads_{point}.txt / IGNORE_MISSING_FAMILIES: false",
    )
    path = workflow_matrix(tmp_path, "in_the_cell.fs", row=stated)
    with pytest.raises(MatrixError) as refused:
        read_matrix(path)
    message = str(refused.value)
    assert "9401" in message
    assert IGNORE_MISSING_FAMILIES_VARIABLE in message
    assert "ignore_missing_families (CLI: --ignore-missing-families)" in message


@pytest.mark.requirement("FR-73")
def test_a_list_member_that_names_nothing_is_refused_even_beside_one_that_resolves():
    """THE ARM A SURVIVING MUTANT FOUND, and the most common spelling.

    `select_families` aggregates a LIST into one set that is non-empty as
    soon as ONE member resolves, so `["WING", "BLADE_1"]` over a mesh with
    no blade selected the wing and passed in silence with the refusal asked
    for. Every case in this module reached the reader with a STRING, so a
    mutant returning early for a non-string selection left all 28 green.
    The QA lens measured it on 2026-09-10.
    """
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    with pytest.raises(CampaignConfigError) as refused:
        _selected_families(
            subject, ["WING", "BLADE_1"], INVENTORY, lambda name: "BLADE" in name, "a plot group"
        )
    message = str(refused.value)
    assert "'BLADE_1' names nothing this geometry carries" in message
    assert "'WING'" in message, "the geometry's own boundaries are what to compare against"


@pytest.mark.requirement("FR-73")
def test_a_misspelled_alias_beside_a_good_member_is_refused_too():
    """The misspelling FR-73 says the flag exists to surface."""
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    with pytest.raises(CampaignConfigError) as refused:
        _selected_families(
            subject, ["airfrmae", "WING"], INVENTORY, lambda name: "BLADE" in name, "a plot group"
        )
    assert "'airfrmae' names nothing this geometry carries" in str(refused.value)


@pytest.mark.requirement("FR-73")
def test_a_list_every_member_of_which_resolves_is_not_refused():
    """Without this the refusal above could be a constant on any list."""
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    assert _selected_families(
        subject, ["WING", "FUSELAGE"], INVENTORY, lambda name: "BLADE" in name, "a plot group"
    ) == [["WING", "FUSELAGE"]]


@pytest.mark.requirement("FR-73")
# `each_blade` is deliberately not here: on this bladeless mesh it selects
# nothing and the refusal is RIGHT, and it is the second kind (an entry
# that selects nothing) rather than a member reported absent. The two
# words the author's retirement keeps are the two this case is about.
@pytest.mark.parametrize("word", ["all", "each"])
def test_a_word_that_names_no_set_of_its_own_is_never_reported_absent(word):
    """`all` and the two `each` words expand; they do not name a set.

    Asking "does this name anything the geometry carries" of `all` is
    asking the wrong question, and answering it wrongly would refuse every
    artifact in the estate the moment a user passed false.

    BARE, WHICH IS WHERE THOSE WORDS MEAN WHAT THEY MEAN. Inside a LIST
    they have never expanded: `select_families` reads a list member as an
    alias or a family, so `["each"]` selected nothing at 0.14.0 too and
    still does. That is the pre-0.15.0 reading and this release does not
    move it; what would have been new is refusing the BARE word, and this
    case is what stops that.
    """
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    assert _selected_families(
        subject, word, INVENTORY, lambda name: "BLADE" in name, "a plot group"
    )


@pytest.mark.requirement("FR-73")
def test_the_reporter_refuses_a_ring_the_way_the_resolver_does():
    """MEASURED DIVERGENCE, closed. Two readings of one file is one too many.

    On a ring the resolver raises and the reporter used to answer
    confidently, so the two disagreed about a file the package refuses.
    The QA lens measured it on 2026-09-10.
    """
    ring = {"top": ["mid", "TAIL"], "mid": ["top"]}
    with pytest.raises(AliasCycleError) as refused:
        alias_members_missing("top", INVENTORY, ring)
    assert "'top'" in str(refused.value) and "'mid'" in str(refused.value)


# --- the reader that honours it --------------------------------------------


@pytest.mark.requirement("FR-73")
def test_by_default_the_entry_is_left_out_and_the_warning_says_so():
    """The artifact's own rule, unchanged: one file serves both geometries."""
    with pytest.warns(UserWarning, match="carries no family of it, so the entry is"):
        assert expand(case()) == []


@pytest.mark.requirement("FR-73")
def test_asked_for_the_refusal_the_point_is_refused_and_names_both_sides():
    """The refusal has to name what to compare, or it cannot be acted on.

    A user who passed false believes this geometry carries every family
    the artifact names. What they need back is the two lists that
    disagree: the aliases the row's setup defines, and the boundaries the
    geometry declares.
    """
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    with pytest.raises(CampaignConfigError) as refused:
        expand(subject)
    message = str(refused.value)
    assert "9401" in message
    assert "'BLADE_1'" in message
    assert "airframe" in message
    assert "'WING'" in message and "'FUSELAGE'" in message
    assert "ignore_missing_families (CLI: --ignore-missing-families)" in message


# --- the alias member no boundary answers -----------------------------------


@pytest.mark.requirement("FR-73")
def test_an_alias_member_the_mesh_lacks_is_dropped_in_silence_by_default():
    """The rule PFS-2035.01 states, and the one the flag exists to question.

    THIS IS THE SILENCE A PASSING ENTRY HIDES. The alias names three
    boundaries and the mesh carries two, so the entry expands, the plot is
    written, and nothing anywhere says the third was left out.
    """
    subject = case(aliases={"airframe": ["WING", "FUSELAGE", "TAIL"]})
    assert _selected_families(
        subject, "airframe", INVENTORY, lambda name: "BLADE" in name, "a plot group"
    ) == [["WING", "FUSELAGE"]]


@pytest.mark.requirement("FR-73")
def test_the_dropped_member_is_named_when_the_run_asked_to_hear_it():
    """The acceptance sentence of PFS-2035.13: the alias, the member, the inventory."""
    subject = case(
        aliases={"airframe": ["WING", "FUSELAGE", "TAIL"]},
        variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"},
    )
    with pytest.raises(CampaignConfigError) as refused:
        _selected_families(
            subject, "airframe", INVENTORY, lambda name: "BLADE" in name, "a plot group"
        )
    message = str(refused.value)
    assert "'airframe'" in message
    assert "'TAIL'" in message
    assert "'WING'" in message and "'FUSELAGE'" in message


@pytest.mark.requirement("FR-73")
def test_a_member_that_is_another_alias_is_followed_to_the_end():
    """The reporter walks the way the resolver walks, nesting included.

    A reporter that read a nested member as a family name would call
    `airframe` itself absent and never reach TAIL, which is the finding
    that would be worse than silence.
    """
    subject = case(
        aliases={"airframe": ["WING", "FUSELAGE", "TAIL"], "outside": ["airframe"]},
        variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"},
    )
    with pytest.raises(CampaignConfigError) as refused:
        _selected_families(
            subject, "outside", INVENTORY, lambda name: "BLADE" in name, "a plot group"
        )
    message = str(refused.value)
    # THE DECLARING ALIAS, NOT THE CITED ONE. `outside` does not name TAIL;
    # `airframe` does, and `airframe` is the table row the user must edit.
    # The first version of this message sent a reader to the wrong line
    # (the interface lens of 2026-09-10).
    assert "'airframe' names 'TAIL'" in message


@pytest.mark.requirement("FR-73")
def test_an_alias_every_member_of_which_resolves_is_not_reported():
    """A refusal that fires on a complete alias is a constant, not a check."""
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    assert alias_members_missing("airframe", INVENTORY, subject.aliases) == []
    assert _selected_families(
        subject, "airframe", INVENTORY, lambda name: "BLADE" in name, "a plot group"
    ) == [["WING", "FUSELAGE"]]


@pytest.mark.requirement("FR-73")
def test_a_family_reading_still_answers_so_a_bare_family_name_is_not_absent():
    """A member is a boundary name OR a family, and the family must count.

    `WING` names a boundary here; on a mesh whose wings are `WING1` and
    `WING2` the same member names the family and answers two boundaries.
    A reporter that only asked the inventory would refuse that file.
    """
    numbered = ["WING1", "WING2"]
    assert alias_members_missing("airframe", numbered, {"airframe": ["WING"]}) == []
    assert alias_members_missing("airframe", numbered, {"airframe": ["TAIL"]}) == [
        ("airframe", "TAIL")
    ]


@pytest.mark.requirement("FR-73")
def test_the_refusal_is_about_the_missing_family_and_not_about_every_entry():
    """A family the geometry DOES carry is expanded, false or not.

    The flag turns an empty expansion into an error; it does not make the
    reader stricter about anything else. Without this case the refusal
    could be a constant that fires on the second entry too.
    """
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    assert _selected_families(
        subject, "WING", INVENTORY, lambda name: "BLADE" in name, "a plot group"
    ) == [["WING"]]
