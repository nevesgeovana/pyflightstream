"""Tier 1: the run chooses whether a missing family skips or refuses (PFS-2035.13).

Her design of 2026-09-10, asked one question at a time and answered in her
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

import pytest

from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
    SweepAxis,
    alias_members_the_geometry_lacks,
)
from pyflightstream.cases.workflows import (
    IGNORE_MISSING_FAMILIES_VARIABLE,
    _ignore_missing_families,
    _selected_families,
)
from pyflightstream.run.cli import _a_word_that_means_false, _build_parser

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
    """She asked to be able to pass false, and argparse's store_true cannot."""
    assert _a_word_that_means_false(word) is False


@pytest.mark.requirement("FR-73")
@pytest.mark.parametrize("word", ["true", "yes", "1", "anything"])
def test_every_other_word_leaves_the_default_standing(word):
    """Only the four spellings of no turn it off; nothing else is a trap."""
    assert _a_word_that_means_false(word) is True


@pytest.mark.requirement("FR-73")
def test_plan_and_run_take_the_flag_and_default_to_true():
    """The default is the skip, which is what every row written so far means."""
    parser = _build_parser()
    for command in ("plan", "run"):
        bare = parser.parse_args([command, "m.fs", "--workspace", "."])
        assert bare.ignore_missing_families is True, command
        stated = parser.parse_args(
            [command, "m.fs", "--workspace", ".", "--ignore-missing-families", "false"]
        )
        assert stated.ignore_missing_families is False, command
        # BARE IS TRUE, which is the ordinary shape of a flag and is what
        # `nargs="?"` with `const=True` buys: writing the flag alone asks
        # for the behaviour the flag is named after.
        alone = parser.parse_args(
            [command, "m.fs", "--workspace", ".", "--ignore-missing-families"]
        )
        assert alone.ignore_missing_families is True, command


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
    assert "'TAIL'" in message
    assert "'airframe'" not in message.split("names")[0]


@pytest.mark.requirement("FR-73")
def test_an_alias_every_member_of_which_resolves_is_not_reported():
    """A refusal that fires on a complete alias is a constant, not a check."""
    subject = case(variables={IGNORE_MISSING_FAMILIES_VARIABLE: "false"})
    assert alias_members_the_geometry_lacks("airframe", INVENTORY, subject.aliases) == []
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
    assert alias_members_the_geometry_lacks("airframe", numbered, {"airframe": ["WING"]}) == []
    assert alias_members_the_geometry_lacks("airframe", numbered, {"airframe": ["TAIL"]}) == [
        "TAIL"
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
