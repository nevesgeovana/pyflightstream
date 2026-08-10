"""Tier 1: the manual reader, and the limits it states about itself.

Every fixture here is SYNTHETIC. It imitates the shape of the vendor
manual's scripting reference (a signature line, a parameter table, a
sample block) and carries none of its text, because that manual is
licensed material which never enters Git (CLAUDE.md invariant 1). The
command names are this database's own, which are public already.

The point of the file is not only that the parser works on a well-formed
page. It is that the four shapes the parser CANNOT resolve are pinned as
tests, so nobody reads a proposal as an answer. Those four are why
``utils.manual`` produces a draft and not a database entry.
"""

from __future__ import annotations

import pathlib

import pytest

from pyflightstream.utils import (
    TYPE_RULES,
    Edition,
    ManualCommand,
    coverage_against,
    edition_surfaces,
    parse_script_index,
    parse_signatures,
    propose_layout,
    propose_type,
    read_edition_manifest,
    read_pdf_pages,
    render_entry,
    sample_contradiction,
    stale_citations,
    surface_changes,
    sweep_editions,
    unreachable_commands,
)
from pyflightstream.utils.cli import main as cli_main
from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.utils.manual import citation_reach

INDEX_PAGE = """376
Script Index
Function Name Location
ACOUSTIC_SOURCES Acoustics Toolbox
SET_BASE_REGION_CP Base Regions
SET_PROP_ACTUATOR_PROFILE Actuators
EDIT_COORDINATE_SYSTEM Coordinate Systems
METER
"""

INLINE_PAGE = """Function name: SET_BASE_REGION_CP <BASE INDEX> <MODEL> <CP>
Function parameters:
Parameter Value
BASE INDEX index of the base region boundary
MODEL one of three named models
CP pressure value for the custom form
Sample:
#*********************
SET_BASE_REGION_CP 1 CUSTOM -0.2
"""

CONTINUATION_PAGE = """Function name: SET_PROP_ACTUATOR_PROFILE <INDEX> <UNITS> <BLADES>
Function parameters:
Parameter Value
INDEX actuator index
UNITS force unit
BLADES blade count
Sample:
SET_PROP_ACTUATOR_PROFILE 2 NEWTONS 4
C:/props/thrust.txt
"""

KEYWORD_PAGE = """Function name: EDIT_COORDINATE_SYSTEM
Function parameters:
Parameter Value
FRAME frame index
Sample:
EDIT_COORDINATE_SYSTEM
FRAME 2
ORIGIN_X 0.0
ORIGIN_Y 1.0
"""

BARE_PAGE = """Function name: START_SOLVER
Function parameters:
Parameter Value
Sample:
START_SOLVER
"""


def test_the_index_reads_commands_and_their_sections():
    found = parse_script_index({376: INDEX_PAGE})
    assert found["SET_BASE_REGION_CP"] == "Base Regions"
    assert found["SET_PROP_ACTUATOR_PROFILE"] == "Actuators"
    assert len(found) == 4


def test_the_index_refuses_an_argument_value_that_sits_alone_on_a_line():
    """``METER`` is a unit, not a command, and the fixture ends with one.

    The index is a two-column list, so a bare token with no section is
    not an entry. Without this the parser reports units, colour maps and
    threshold modes as commands, which is measurably what a heading
    heuristic does on the real chapter.
    """
    assert "METER" not in parse_script_index({376: INDEX_PAGE})


def test_a_signature_gives_the_inline_arguments_in_order():
    found = parse_signatures({316: INLINE_PAGE})
    command = found["SET_BASE_REGION_CP"]
    assert command.page == 316
    assert command.inline_args == ("BASE INDEX", "MODEL", "CP")
    assert command.sample == ("SET_BASE_REGION_CP 1 CUSTOM -0.2",)
    assert command.continuation_lines == ()


def test_the_section_is_carried_across_when_an_index_is_given():
    index = parse_script_index({376: INDEX_PAGE})
    found = parse_signatures({316: INLINE_PAGE}, sections=index)
    assert found["SET_BASE_REGION_CP"].section == "Base Regions"


def test_the_first_definition_wins_so_a_cross_reference_cannot_move_the_page():
    later = "Function name: SET_BASE_REGION_CP <BASE INDEX> <MODEL> <CP>\nSample:\nX\n"
    found = parse_signatures({316: INLINE_PAGE, 350: later})
    assert found["SET_BASE_REGION_CP"].page == 316


@pytest.mark.parametrize(
    ("page", "name", "layout"),
    [
        (BARE_PAGE, "START_SOLVER", "bare"),
        (INLINE_PAGE, "SET_BASE_REGION_CP", "inline"),
        (CONTINUATION_PAGE, "SET_PROP_ACTUATOR_PROFILE", "param_lines"),
        (KEYWORD_PAGE, "EDIT_COORDINATE_SYSTEM", "keyword_block"),
    ],
)
def test_the_layout_proposal_reads_the_sample(page, name, layout):
    command = parse_signatures({1: page})[name]
    proposed, why = propose_layout(command)
    assert proposed == layout
    assert why, "a proposal without a reason cannot be argued with"


def test_the_signature_alone_understates_the_arity():
    """The finding that decides what this module is allowed to do.

    ``SET_PROP_ACTUATOR_PROFILE`` takes four arguments and its signature
    line shows three, because the file path is written on the next line.
    Measured across the whole database, the signature alone reproduces
    46 percent of recorded argument counts and the sample raises that to
    77. That is why the module proposes and does not write.
    """
    command = parse_signatures({330: CONTINUATION_PAGE})["SET_PROP_ACTUATOR_PROFILE"]
    assert len(command.inline_args) == 3
    assert command.continuation_lines == ("C:/props/thrust.txt",)
    assert len(command.inline_args) + len(command.continuation_lines) == 4


def test_a_keyword_block_has_no_inline_signature_at_all():
    command = parse_signatures({307: KEYWORD_PAGE})["EDIT_COORDINATE_SYSTEM"]
    assert command.inline_args == ()
    assert len(command.continuation_lines) == 3
    assert propose_layout(command)[0] == "keyword_block"


def test_a_multi_line_payload_is_flagged_rather_than_counted():
    """A variable-length list is ONE database argument and N sample lines.

    The proposal says payload_lines and its reason says to check exactly
    this, because counting the lines would record a command as taking
    four boundary indices when it takes a list.
    """
    command = ManualCommand(
        name="ASSIGN_AEROELASTIC_SURFACES",
        page=1,
        inline_args=("NUM_BOUNDARIES",),
        sample=("ASSIGN_AEROELASTIC_SURFACES 1", "1", "2", "3"),
    )
    layout, why = propose_layout(command)
    assert layout == "payload_lines"
    assert "variable-length" in why


def test_coverage_names_all_three_sets():
    manual = parse_signatures({316: INLINE_PAGE, 330: CONTINUATION_PAGE})
    report = coverage_against(manual, recorded=["SET_BASE_REGION_CP", "START_SOLVER"])
    assert report.absent == ("SET_PROP_ACTUATOR_PROFILE",)
    assert report.recorded == ("SET_BASE_REGION_CP",)
    assert report.undocumented == ("START_SOLVER",)
    assert "absent from the database" in report.summary()


def test_coverage_carries_the_detail_of_what_is_absent():
    """So a maintainer can start writing without re-reading the manual."""
    manual = parse_signatures({330: CONTINUATION_PAGE})
    report = coverage_against(manual, recorded=[])
    detail = report.details["SET_PROP_ACTUATOR_PROFILE"]
    assert detail.page == 330
    assert detail.inline_args == ("INDEX", "UNITS", "BLADES")


def test_the_module_imports_nothing_from_the_package():
    """It sits at the bottom of the layer rule, so it may not reach up.

    Read from the source rather than from the import graph: a deferred
    import inside a function would not appear in ``sys.modules`` and is
    exactly the shape this assertion has to catch. The one permitted
    mention is the extras refusal, which is imported inside the pdf
    reader precisely so the parsing half needs nothing.
    """
    import pathlib

    import pyflightstream.utils.manual as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    reaching = [
        line.strip()
        for line in source.splitlines()
        if "import pyflightstream" in line or "from pyflightstream" in line
    ]
    assert reaching == [
        "from pyflightstream.utils.errors import ManualDraftError",
        "from pyflightstream.extras import missing_extra",
    ], reaching


# --- drafting, and its refusals -------------------------------------------


def test_a_drafted_entry_leaves_the_unanswerable_unanswered():
    """A draft must not load, and that is the safety property.

    An argument TYPE the parameter table does not decide is written
    ``???``. The database schema refuses that value, so an unreviewed
    draft turns the suite red instead of quietly becoming grammar the
    emitter validates other people's scripts against.

    The claim narrowed on 2026-08-05 and is worth stating in its new
    form: it used to be one ``???`` per inline argument, because the
    drafter read only the signature line and no signature carries a
    type. Since it reads the parameter table too, the two arguments this
    fixture describes as an index and a value are typed, and the one
    whose description no rule reads is not. What did NOT narrow is the
    safety property: an entry with a single unanswered field still
    cannot load.
    """
    from pyflightstream.utils import render_entry

    command = parse_signatures({316: INLINE_PAGE}, sections={"SET_BASE_REGION_CP": "Base Regions"})[
        "SET_BASE_REGION_CP"
    ]
    entry = render_entry(command, source="SRC-741", versions={"26.100": "documented"})
    assert "    - name: model\n      type: ???" in entry, "no rule reads that description"
    assert "    - name: base_index\n      type: int" in entry, "the table names an index"
    assert 'manual_ref: "SRC-741 p.316"' in entry
    assert '"26.100": {status: documented}' in entry


def test_a_drafted_entry_says_it_was_drafted_and_by_what():
    """One grep finds every machine-drafted entry, which is what makes a
    tranche reviewable and what stops a draft becoming evidence."""
    from pyflightstream.utils import render_entry

    command = parse_signatures({316: INLINE_PAGE})["SET_BASE_REGION_CP"]
    entry = render_entry(command, source="SRC-741", versions={"26.100": "documented"})
    assert "drafted:" in entry
    assert "pyflightstream.utils.manual" in entry
    assert "SRC-741 p.316" in entry


def test_the_phase_is_left_unanswered_when_the_section_does_not_decide_it():
    """Guessing a phase would make the ordering checks refuse a correct
    script, which is worse than refusing to answer."""
    from pyflightstream.utils import render_entry

    command = ManualCommand(name="X_COMMAND", page=1, section="Some Section Nobody Mapped")
    assert "phase: ???" in render_entry(
        command, source="SRC-741", versions={"26.100": "documented"}
    )


def test_a_manual_cannot_draft_a_probed_status():
    """verified and broken are promoted from a committed probe report by
    the sanctioned path; a manual is not evidence of solver behaviour."""
    from pyflightstream.utils import render_entry

    command = parse_signatures({316: INLINE_PAGE})["SET_BASE_REGION_CP"]
    with pytest.raises(ValueError, match="invariant 3"):
        render_entry(command, source="SRC-741", versions={"26.100": "verified"})


def test_the_default_writes_nothing(tmp_path):
    from pyflightstream.utils import render_chapter, write_chapter

    target = tmp_path / "drafts.yaml"
    body = render_chapter(
        parse_signatures({316: INLINE_PAGE}).values(),
        source="SRC-741",
        versions={"26.100": "documented"},
    )
    message = write_chapter(body, path=target)
    assert not target.exists(), "the default must not touch the filesystem"
    assert "dry run" in message and "nothing written" in message


def test_writing_is_possible_and_says_what_it_left_unanswered(tmp_path):
    from pyflightstream.utils import render_chapter, write_chapter

    target = tmp_path / "nested" / "drafts.yaml"
    body = render_chapter(
        parse_signatures({316: INLINE_PAGE}).values(),
        source="SRC-741",
        versions={"26.100": "documented"},
    )
    message = write_chapter(body, path=target, write=True)
    assert target.read_text(encoding="utf-8") == body
    assert "wrote" in message and "review" in message


def test_the_chapter_header_says_nothing_was_reviewed():
    from pyflightstream.utils import render_chapter

    body = render_chapter(
        parse_signatures({316: INLINE_PAGE, 330: CONTINUATION_PAGE}).values(),
        source="SRC-741",
        versions={"26.100": "documented"},
    )
    assert "none reviewed" in body
    # Sorted, so two runs over the same manual produce the same file.
    assert body.index("SET_BASE_REGION_CP:") < body.index("SET_PROP_ACTUATOR_PROFILE:")


# --- the parameter table, and the types it can and cannot decide -------------
#
# Synthetic as everything else here: the shape of a parameter table, none
# of the vendor's prose. The point of the block is the pair of claims the
# module makes about itself, that it answers about three arguments in five
# and proposes nothing where no rule reads a type, so a draft says '???'
# rather than guessing.

TYPED_PLACEHOLDERS = "TOGGLE UNITS AXIS COUNT TARGET PATH LABEL SPAN_LENGTH MYSTERY".replace(
    " ", "> <"
)
TYPED_PAGE = f"""Function name: SET_EVERY_SHAPE <{TYPED_PLACEHOLDERS}>
Function parameters:
Parameter Value
TOGGLE switch the behaviour on or off. ENABLE/DISABLE
UNITS one of the following: FEET, METERS
AXIS the axis to use. X, Y or Z
COUNT Number of boundaries in the list
TARGET Index of the boundary being addressed
PATH File name with path to the file
LABEL Assign name to the created object
SPAN_LENGTH the span of the section
MYSTERY something the rules were never written for
Sample:
SET_EVERY_SHAPE ENABLE FEET X 3 1 out.txt WING 2.0 42
"""


def typed_command():
    found = parse_signatures({300: TYPED_PAGE})
    return found["SET_EVERY_SHAPE"]


def test_the_parameter_table_is_read_and_keyed_by_the_signature():
    command = typed_command()
    assert set(command.parameters) == {
        "TOGGLE",
        "UNITS",
        "AXIS",
        "COUNT",
        "TARGET",
        "PATH",
        "LABEL",
        "SPAN_LENGTH",
        "MYSTERY",
    }
    # A row's prose is kept whole, which is what lets a rule read it; the
    # module never renders it, which is what keeps invariant 1.
    assert command.parameters["COUNT"].startswith("Number of")


@pytest.mark.parametrize(
    ("placeholder", "expected", "values"),
    [
        ("TOGGLE", "enum", ("ENABLE", "DISABLE")),
        ("UNITS", "enum", ("FEET", "METERS")),
        ("AXIS", "enum", ("X", "Y", "Z")),
        ("COUNT", "int", ()),
        ("TARGET", "int", ()),
        ("PATH", "path", ()),
        ("LABEL", "str", ()),
        ("SPAN_LENGTH", "float", ()),
    ],
)
def test_each_rule_reads_the_type_it_claims(placeholder, expected, values):
    command = typed_command()
    proposed, tokens, reason = propose_type(placeholder, command.parameters[placeholder])
    assert proposed == expected
    assert tokens == values
    assert reason  # every proposal says which rule answered


def test_a_description_no_rule_reads_proposes_nothing():
    command = typed_command()
    proposed, tokens, reason = propose_type("MYSTERY", command.parameters["MYSTERY"])
    assert proposed is None and tokens == ()
    assert "no rule" in reason


def test_a_command_with_no_table_says_so_rather_than_guessing():
    proposed, _tokens, reason = propose_type("ANYTHING", "")
    assert proposed is None
    assert "no parameter table" in reason


def test_the_toggle_rule_matches_the_tokens_as_printed():
    """Ordinary words must not pass for the tokens.

    The rule matched case-insensitively at first, so a sentence saying
    boundaries are 'enabled' and others 'disabled' proposed an enum for
    a count. It was the only disagreement against the hand-authored
    corpus, and this is the fixture it was fixed against.

    The fixture was REBUILT on 2026-08-06, because a later fix disarmed
    it. Its description opened "Number of boundaries being enabled...",
    so once the counting openings moved above the toggle rule the
    counting rule answered first and the toggle rule was never reached:
    the assertion still passed, for a reason that had nothing to do with
    what it guards. A fixture whose subject rule cannot run is a
    green test measuring another rule. This one carries no counting
    opening, so the toggle rule is the only rule that can answer it.
    """
    proposed, _tokens, _reason = propose_type(
        "VISCOUS_LIST",
        "The boundaries being enabled for viscous coupling; the rest are disabled.",
    )
    assert proposed is None, (
        "lowercase 'enabled' and 'disabled' are ordinary words here, and the toggle "
        "rule is the only rule that can read this description"
    )
    # The control, on the same rule: the tokens AS PRINTED are read.
    proposed, tokens, _reason = propose_type(
        "VISCOUS_LIST", "Switch viscous coupling on the list. ENABLE/DISABLE"
    )
    assert proposed == "enum" and tokens == ("ENABLE", "DISABLE")


def test_a_counting_opening_wins_over_the_toggle_rule():
    """The rule ORDER, which shipped twice with nothing failing on a revert.

    The counting openings were moved above the enum rules and the toggle
    rule stayed above them, so "Number of boundaries. ENABLE or DISABLE
    the list" still drafted as an enum. Moving it down fixed that and
    carried no test: reverting the move left the whole tier 1 suite
    green, because the one fixture that could have caught it opened with
    a counting phrase and so answered before the toggle rule either way.
    """
    proposed, tokens, _reason = propose_type(
        "NUM_BOUNDARIES", "Number of boundaries. ENABLE or DISABLE the list"
    )
    assert proposed == "int" and tokens == ()


def test_a_drafted_entry_carries_the_types_it_read_and_marks_the_rest():
    command = typed_command()
    rendered = render_entry(command, source="SRC-000", versions={"26.120": "documented"})
    assert "      type: enum\n      values: [ENABLE, DISABLE]" in rendered
    assert "    - name: count\n      type: int" in rendered
    # The one argument no rule reads still refuses to load, which is the
    # safety property the whole module is built around.
    assert "    - name: mystery\n      type: ???" in rendered
    assert "8 argument type(s) read from the parameter table and 1 left unanswered" in rendered


# --- the rule ORDER, and the sentence boundary ------------------------------
#
# Both were found by reading drafts of a chapter nobody has written, not
# by the measurement: the corpus the percentages come from is the set of
# commands somebody chose to author first, so it under-represents exactly
# the shapes that were wrong.


@pytest.mark.parametrize(
    ("placeholder", "description"),
    [
        ("NUM_BOUNDARIES", "Number of boundaries in the STL or OBJ import"),
        ("NUM_STEPS", "Number of steps. Set to A or B"),
        ("BODY_INDEX", "Index of the body. Value > 0 for a solid or a sheet"),
    ],
)
def test_a_count_whose_description_mentions_alternatives_is_still_a_count(placeholder, description):
    """The enum rules read tokens out of a sentence, so they run last.

    With the alternatives rule ahead of the counting openings, a
    description that happens to spell "X or Y" made a count draft as
    `values: [CFD, FEM]`. A wrong `???` costs a reviewer a minute; an
    invented token list loads into the schema and then validates other
    people's scripts.
    """
    proposed, values, _reason = propose_type(placeholder, description)
    assert proposed == "int"
    assert values == ()


def test_the_float_suffix_rule_runs_after_the_openings():
    """A count of time steps ends in a float suffix and is whole.

    The ordering is stated in the module and was unguarded: moving the
    suffix check above the openings passed the whole file.
    """
    proposed, _values, _reason = propose_type("SWEEP_TIME", "Number of time slices to sweep")
    assert proposed == "int"
    # The control, so a rule that answered int for everything would fail:
    # the same suffix with no opening is a real dimension.
    proposed, _values, _reason = propose_type("SPAN_LENGTH", "the span of the section")
    assert proposed == "float"


@pytest.mark.parametrize(
    ("placeholder", "description", "expected"),
    [
        (
            "LOGIC",
            "Comparison direction for the cutoff. One of the following: ABOVE or BELOW. "
            "Faces on the matching side are handed to the ACTION argument named next.",
            ("ABOVE", "BELOW"),
        ),
        (
            "PLANE",
            "Symmetry plane the copy is reflected in. One of the following: XY , XZ or YZ",
            ("XY", "XZ", "YZ"),
        ),
    ],
)
def test_an_enum_reads_one_sentence_and_the_short_tokens_in_it(placeholder, description, expected):
    """Two shapes in one claim, because the fix had to serve both.

    Reading the whole description took CAD out of the sentence after the
    list. Restricting to one sentence then lost the coordinate planes,
    whose tokens are two characters, so the alternatives pattern is tried
    inside that sentence before the general one.
    """
    proposed, values, _reason = propose_type(placeholder, description)
    assert proposed == "enum"
    assert values == expected


# --- the pdf reader refuses a range it cannot honour ------------------------


@pytest.mark.parametrize(("first", "last"), [(370, 273), (0, 5), (-1, 5), (5, 4)])
def test_a_page_range_that_is_not_one_based_and_ascending_is_refused(first, last):
    """A swapped or zero-based range used to answer confidently from nothing.

    A reversed pair read no pages, and `coverage_against` reads an empty
    manual as one documenting nothing: every database command lands under
    "recorded here but not in this manual" and none under "absent". A
    `first` of zero indexed the pdf at -1, keying the manual's LAST page
    as page 0, so a drafted entry cited `p.0`.

    The refusal is raised before pypdf is touched, which is what lets
    this test run without the extra and without a pdf.
    """
    with pytest.raises(ManualDraftError, match="one-based ascending"):
        read_pdf_pages("nonexistent.pdf", first=first, last=last)


# --- the command line -------------------------------------------------------


def test_the_page_range_flag_refuses_a_non_numeric_page_through_the_parser():
    """A typo used to surface as a raw ValueError traceback.

    Exit code 2 is the usage code the rest of this package's CLIs
    return, and the message names the flag the user typed.
    """
    with pytest.raises(SystemExit) as caught:
        cli_main(
            [
                "coverage",
                "--manual",
                "x.pdf",
                "--source",
                "SRC-000",
                "--chapter-pages",
                "abc-370",
                "--index-pages",
                "1-2",
            ]
        )
    assert caught.value.code == 2


def test_write_without_a_destination_is_refused_before_the_manual_is_opened():
    """The refusal the commit that added --write is named after.

    It used to fire after two full pdf reads and a render, so a mistyped
    invocation cost the whole run on a 400-page document. The manual path
    here does not exist, so reaching pypdf at all would raise something
    else.
    """
    with pytest.raises(SystemExit) as caught:
        cli_main(
            [
                "draft",
                "--manual",
                "nonexistent.pdf",
                "--source",
                "SRC-000",
                "--chapter-pages",
                "1-2",
                "--index-pages",
                "3-4",
                "--fs-version",
                "26.120",
                "--write",
            ]
        )
    assert caught.value.code == 2


# --- the rule ORDER, now data rather than control flow ----------------------


def test_the_rule_order_is_pinned_and_every_rule_is_named():
    """Three rounds each found one rule in the wrong place.

    The openings below the enum rules, then the toggle pair above the
    openings, then the dimension suffix below them. Each time the fix
    was invisible on a revert, because the order lived in the shape of a
    chain of ifs and nothing could read it. It is a list now, and this
    is the list.
    """
    assert [rule.name for rule in TYPE_RULES] == [
        "opening",
        "integer-word",
        "dimension",
        "enumeration",
        "alternatives",
        "toggle",
    ]
    assert len({rule.name for rule in TYPE_RULES}) == len(TYPE_RULES)
    assert all(rule.reason for rule in TYPE_RULES)


#: One description per ADJACENT pair of TYPE_RULES, readable by both
#: rules of the pair, with the answer the earlier one gives. Adjacent is
#: the whole point: a QA pass applied all five adjacent transpositions
#: and the previous parametrisation stayed green for every one, because
#: not one of its four rows named a pair that is actually adjacent. A
#: table that cannot see a neighbour swap does not pin an order.
ADJACENT_ORDER_CASES = (
    ("opening", "integer-word", "NUM_STEPS", "Number of steps. Integer value above zero", "int"),
    ("integer-word", "dimension", "SPAN_LENGTH", "Integer value counting the span", "int"),
    (
        "dimension",
        "enumeration",
        "SPAN_LENGTH",
        "Span. One of the following: SHORT or LONG",
        "float",
    ),
    (
        "enumeration",
        "alternatives",
        "MODE",
        "One of the following: ALPHA or BETA. Choose GAMMA or DELTA elsewhere.",
        "enum",
    ),
    ("alternatives", "toggle", "MODE", "Set it to ENABLE or DISABLE as needed", "enum"),
)


def test_every_adjacent_pair_of_rules_carries_a_case_that_pins_it():
    """The table must cover each neighbour, or a swap of two goes unseen.

    Five rules in sequence make five adjacent pairs, and the guard is
    only as strong as the pairs it names. The previous version of this
    test named four pairs and none of them adjacent, so all five
    transpositions passed.
    """
    names = [rule.name for rule in TYPE_RULES]
    adjacent = {(names[i], names[i + 1]) for i in range(len(names) - 1)}
    covered = {(row[0], row[1]) for row in ADJACENT_ORDER_CASES}
    assert covered == adjacent, (
        f"the order cases cover {sorted(covered)} and the rule table has adjacent pairs "
        f"{sorted(adjacent)}; a pair with no case is a transposition nothing catches"
    )


@pytest.mark.parametrize(
    ("earlier", "later", "placeholder", "description", "expected"), ADJACENT_ORDER_CASES
)
def test_the_earlier_rule_answers_where_two_adjacent_rules_both_could(
    earlier, later, placeholder, description, expected
):
    """Each row is a description BOTH named rules can read.

    Without the pairing the order is untested: a rule that never
    competes with another cannot show that it sits in the right place.
    The row asserts that both rules answer it before asserting which
    one wins, so a fixture that stops reaching the later rule fails
    here instead of passing for the wrong reason, which is how the
    round-1 toggle fixture was silently disarmed.
    """
    names = [rule.name for rule in TYPE_RULES]
    assert names.index(earlier) + 1 == names.index(later), (
        f"{earlier} and {later} are no longer adjacent in TYPE_RULES"
    )
    by_name = {rule.name: rule for rule in TYPE_RULES}
    upper = placeholder.upper()
    assert by_name[earlier].read(upper, description) is not None, "the earlier rule must answer"
    assert by_name[later].read(upper, description) is not None, (
        "the later rule must also answer, or this row does not test the order"
    )
    proposed, _values, reason = propose_type(placeholder, description)
    assert proposed == expected
    assert reason == by_name[earlier].reason


def test_a_leading_article_does_not_hide_an_opening():
    """ "The number of boundaries" and "Number of boundaries" are one statement.

    Only the second was read, because the opening rules match with
    startswith. The manual writes both.
    """
    for description in ("Number of boundaries in the list", "The number of boundaries in the list"):
        proposed, _values, _reason = propose_type("NUM_BOUNDARIES", description)
        assert proposed == "int", description


def test_an_enumeration_that_contains_the_toggle_tokens_is_not_truncated():
    """The toggle rule sits below the explicit enumeration for this case."""
    proposed, tokens, _reason = propose_type(
        "MODE", "Can be one of ENABLE, DISABLE or AUTO for the automatic setting."
    )
    assert proposed == "enum"
    assert set(tokens) >= {"ENABLE", "DISABLE", "AUTO"}


# --- the parameter table against the printed sample -------------------------
#
# The defect these hold: propose_type read the parameter table and
# nothing else, so a table that contradicts the sample printed beneath it
# produced a confident wrong type. Measured on 2026-08-06, 19 enumeration
# positions across seven commands of this database declared a value set
# that refuses the token their own manual sample passes.


def _rotate_shaped_command():
    """A command whose table names three letters and whose sample passes an index.

    The shape of CAD_BODY_ROTATE, carrying none of the manual's text: the
    parameter prose here is written for this test.
    """
    return ManualCommand(
        name="X_ROTATE",
        page=1,
        inline_args=("INDEX", "AXIS", "ANGLE"),
        sample=("X_ROTATE 1 2 20.0",),
        parameters={
            "INDEX": "Index of the item to rotate.",
            "AXIS": "Axis of rotation. One of the following: X, Y or Z.",
            "ANGLE": "Rotation angle in degrees.",
        },
    )


def test_a_table_that_contradicts_the_sample_is_reported():
    command = _rotate_shaped_command()
    proposed, values, _reason = propose_type("AXIS", command.parameters["AXIS"])
    assert proposed == "enum" and set(values) == {"X", "Y", "Z"}, (
        "this fixture only means something while the table rule still answers"
    )
    assert sample_contradiction(command, index=1, proposed=proposed, values=values) == "2"


def test_a_table_the_sample_confirms_is_not_reported():
    command = _rotate_shaped_command()
    assert sample_contradiction(command, index=0, proposed="int", values=()) is None


def test_an_enumeration_matches_its_sample_token_case_insensitively():
    command = ManualCommand(
        name="X_SET_MODE",
        page=1,
        inline_args=("MODE",),
        sample=("X_SET_MODE enable",),
    )
    assert (
        sample_contradiction(command, index=0, proposed="enum", values=("ENABLE", "DISABLE"))
        is None
    )


@pytest.mark.parametrize(
    ("proposed", "token", "reported"),
    [
        ("int", "2.5", "2.5"),
        ("int", "-1", None),
        ("int", "TRUE", "TRUE"),
        ("float", "2.5", None),
        ("float", "2", None),
        ("float", "RETAIN", "RETAIN"),
        ("path", "anything at all", None),
        ("str", "anything at all", None),
        ("int_list", "1,2,3", None),
    ],
)
def test_a_numeric_proposal_is_checked_against_the_sample_token(proposed, token, reported):
    """A float where an int was proposed is the shape of a MISALIGNED list.

    CREATE_NEW_CIRCLE_VOLUME_SECTION declares an enumeration in a
    position whose sample passes 2.5, which is neither of its tokens and
    not an index either: the argument list itself is out of step with the
    signature, and the only way the tool can say so is by checking.
    """
    command = ManualCommand(name="X_CMD", page=1, inline_args=("A",), sample=(f"X_CMD {token}",))
    assert sample_contradiction(command, index=0, proposed=proposed, values=()) == reported


@pytest.mark.parametrize(
    ("command", "why"),
    [
        (
            ManualCommand(name="X_CMD", page=1, inline_args=("A",)),
            "a command with no sample block",
        ),
        (
            ManualCommand(name="X_CMD", page=1, inline_args=("A",), sample=("SOMETHING ELSE 1",)),
            "a sample whose first line is not the call",
        ),
        (
            ManualCommand(name="X_CMD", page=1, inline_args=("A", "B"), sample=("X_CMD 1",)),
            "a sample with fewer tokens than the signature has placeholders",
        ),
    ],
)
def test_a_sample_that_cannot_answer_is_silent_rather_than_confirming(command, why):
    """Silence is not agreement, and the three silent cases are stated.

    A caller that read None as "the sample confirms it" would be wrong
    for exactly these three, which is why the docstring names them and
    why this test exists next to the one that reports a real
    contradiction.
    """
    assert (
        sample_contradiction(
            command, index=len(command.inline_args) - 1, proposed="enum", values=("X",)
        )
        is None
    ), why


def test_an_unanswered_type_is_never_contradicted():
    """None refuses nothing, so it cannot disagree with a sample."""
    command = _rotate_shaped_command()
    assert sample_contradiction(command, index=1, proposed=None, values=()) is None


def test_a_contradicted_type_is_drafted_unanswered_rather_than_written():
    """The behaviour, not just the report: `???` is what the schema refuses.

    A draft that wrote `enum` with the table's tokens would LOAD, and
    would then validate other people's scripts against a value set the
    manual's own sample violates. Writing `???` instead makes the
    disagreement stop the file rather than ship in it.
    """
    entry = render_entry(
        _rotate_shaped_command(), source="SRC-000", versions={"26.120": "documented"}
    )
    axis = entry.split("- name: axis")[1].split("- name:")[0]
    assert "type: ???" in axis
    assert "values:" not in axis, "the table's tokens must not be written beside the ???"
    assert "would REFUSE the token the sample passes, for AXIS (the sample passes 2)" in entry


def test_an_uncontradicted_type_is_still_drafted_normally():
    """The guard must not turn every enumeration into a question.

    Without this the previous test passes just as well under a
    render_entry that wrote `???` for everything.
    """
    command = ManualCommand(
        name="X_SET_MODE",
        page=1,
        inline_args=("MODE",),
        sample=("X_SET_MODE DISABLE",),
        parameters={"MODE": "Mode to use. One of the following: ENABLE or DISABLE."},
    )
    entry = render_entry(command, source="SRC-000", versions={"26.120": "documented"})
    assert "type: enum" in entry
    assert "values: [ENABLE, DISABLE]" in entry
    assert "would REFUSE" not in entry


def test_the_enumeration_rule_reads_one_sentence_and_this_fixture_proves_it():
    """A LIVE trap for the one-sentence rule, which had none.

    The rule exists because reading a whole description took tokens out
    of the sentences after the one that lists them. The fixtures written
    for it spell their tokens with "or", so `_alternatives_in` matches
    them wherever the span ends and the extra token in the next sentence
    never had a chance to be picked up: widening the span back to the
    whole description leaves the suite green.

    This description spells its tokens as a COMMA LIST with no "or", so
    the alternatives shape does not match and `_tokens_in` falls through
    to the bare token scan, which is the path the sentence limit
    protects. The following sentence carries one more uppercase token,
    so the two spans give different answers and the mutation is caught.
    """
    description = (
        "Mode this operation runs in. One of the following: ENABLE, DISABLE, AUTO. "
        "The chosen mode is recorded in the SNAPSHOT written afterwards."
    )
    proposed, tokens, _reason = propose_type("MODE", description)
    assert proposed == "enum"
    assert set(tokens) == {"ENABLE", "DISABLE", "AUTO"}, (
        "SNAPSHOT belongs to the sentence after the list and must not be a value"
    )


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_an_index_outside_the_signature_is_refused_rather_than_answered(index):
    """A caller bug must not come back as a plausible finding.

    The index used to address the sample tokens directly, so passing the
    1-based position a person reads off the manual page returned the
    NEXT argument's token and the draft then wrote a confident sentence
    about it. A report that looks exactly like a real one is worse than
    a crash.
    """
    command = _rotate_shaped_command()
    with pytest.raises(ManualDraftError, match="outside them"):
        sample_contradiction(command, index=index, proposed="enum", values=("X",))


def test_the_index_is_zero_based_against_the_signature():
    """The control for the refusal above: index 1 is the SECOND argument."""
    command = _rotate_shaped_command()
    assert sample_contradiction(command, index=1, proposed="enum", values=("X",)) == "2"
    assert sample_contradiction(command, index=2, proposed="float", values=()) is None


def test_an_enum_proposal_without_its_tokens_is_refused():
    """Otherwise every sample token comes back as a contradiction.

    With the documented default of no token set, the membership test
    runs against an empty set and reports the sample token for EVERY
    enumeration position, which render_entry then writes out as a page
    of confident findings. That is the caller-bug shape the index
    refusal was added for, sitting on the parameter beside it: a caller
    who takes propose_type's type and forgets its tokens gets plausible
    sentences instead of a refusal.
    """
    command = _rotate_shaped_command()
    for kind in ("enum", "enum_list"):
        with pytest.raises(ManualDraftError, match="no token set"):
            sample_contradiction(command, index=1, proposed=kind)


def test_a_non_enum_proposal_still_takes_no_tokens():
    """The control: the refusal is about enumerations, not about the default.

    Without this the test above passes under a rule that demanded a
    token set from every caller, which would be wrong for the numeric
    and path types that have none.
    """
    command = _rotate_shaped_command()
    assert sample_contradiction(command, index=0, proposed="int") is None


def test_a_signature_heading_that_wraps_is_read_whole():
    """A short signature is the worst thing this module can produce.

    Five commands wrap their heading, identically in all four registered
    editions, and the parser reported every one short until 2026-08-07,
    CREATE_NEW_RECTANGLE_VOLUME_SECTION by three arguments. The
    shortfall is silent all the way down: a short entry LOADS, the
    emitter then accepts a short call, and the solver reads the line
    differently with nothing in between to object.
    """
    page = (
        "Function name: X_MAKE_SECTION <FRAME> <PLANE> <OFFSET> <IPTS> <JPTS> <PRISMS>\n"
        "<THICKNESS> <LAYERS> <GROWTH_RATE>\n"
        "Function parameters:\n"
        "Parameter Value\n"
        "FRAME Index of the coordinate system.\n"
        "Sample:\n"
        "X_MAKE_SECTION 1 XZ 0.1 20 40 PRISMS 0.3 20 1.2\n"
    )
    command = parse_signatures({366: page})["X_MAKE_SECTION"]
    assert command.inline_args == (
        "FRAME",
        "PLANE",
        "OFFSET",
        "IPTS",
        "JPTS",
        "PRISMS",
        "THICKNESS",
        "LAYERS",
        "GROWTH_RATE",
    )
    assert len(command.inline_args) == len(command.sample[0].split()) - 1, (
        "the whole point of reading the wrap is that the signature and the sample "
        "then agree on how many arguments the command takes"
    )


@pytest.mark.parametrize(
    "following",
    [
        "Function parameters:",
        "Sample:",
        "The value is one of the following: X, Y or Z.",
        "X_MAKE_SECTION 1 XZ 0.1",
        # The case that actually bites, and the only one of the five that
        # does: a heading whose neighbour is another heading. The manual
        # prints these back to back for bare commands, and a rule that
        # appended any following line would give the FIRST command the
        # SECOND one's arguments. The other four rows carry no
        # placeholders at all, so they pass under a broken rule too and
        # are kept only as the readable half of the statement.
        "Function name: X_OTHER_COMMAND <ALPHA> <BETA>",
    ],
)
def test_only_a_line_of_pure_placeholders_continues_a_signature(following):
    """The control: the rule must not swallow the line after every heading.

    Without this the test above passes under a rule that appended
    whatever came next, which would read a following signature's
    arguments into this command.
    """
    page = f"Function name: X_MAKE_SECTION <FRAME> <PLANE>\n{following}\n"
    command = parse_signatures({1: page})["X_MAKE_SECTION"]
    assert command.inline_args == ("FRAME", "PLANE"), following


# ---------------------------------------------------------------------
# The multi-edition sweep: what NO edition has an entry for.
#
# The pdf reads are monkeypatched away rather than fixtured, because a
# fixture would have to be a pdf and the only pdfs this repository can
# reach are the licensed manuals (invariant 1). What is under test here
# is the UNION rule and the manifest, not the extraction, which the
# tests above already cover.
# ---------------------------------------------------------------------


def _edition(tmp_path, label, chapter, index=None, source=None):
    manual = tmp_path / f"{label}.pdf"
    manual.write_bytes(b"not a pdf; the reader is injected")
    return Edition(label=label, manual=manual, chapter=chapter, index=index, source=source)


def _recording_reader(pages):
    """A reader that records the ranges it was asked for.

    The ranges are the point. `sweep_editions` makes TWO reads per
    edition, the chapter one feeding the signature parse and the index
    one feeding the section labels, and a reader that ignores `first`
    and `last` cannot tell them apart. Swapping the two ranges is
    exactly the mistake `Edition` is keyword-only to prevent, so a test
    that cannot see the mistake is not testing the plumbing.
    """
    calls: list[tuple[str, int, int]] = []

    def read(manual, *, first, last):
        calls.append((manual.stem, first, last))
        return pages[manual.stem][first]

    return read, calls


def test_a_command_one_edition_documents_is_swept_with_that_edition_named(tmp_path):
    """The union, and the per-edition membership that a version row needs.

    A command dropped by the newest build still has to be entered, and
    entered for the editions that carry it and no others. Recording the
    membership is therefore the sweep's output, not a convenience.
    """
    pages = {
        "old": {1: {1: "Function name: X_GONE <A>\nFunction name: X_BOTH <A>\n"}},
        "new": {1: {1: "Function name: X_BOTH <A>\nFunction name: X_NEW <A>\n"}},
    }
    read, _calls = _recording_reader(pages)
    swept = sweep_editions(
        [_edition(tmp_path, "old", (1, 1)), _edition(tmp_path, "new", (1, 1))],
        recorded=[],
        reader=read,
    )
    assert [command.name for command in swept] == ["X_BOTH", "X_GONE", "X_NEW"]
    assert {command.name: command.editions for command in swept} == {
        "X_BOTH": ("old", "new"),
        "X_GONE": ("old",),
        "X_NEW": ("new",),
    }


def test_the_sweep_records_the_page_each_edition_prints_a_command_on(tmp_path):
    """A version row cites its own edition's page, so the sweep carries all of them.

    One page number would be useless: the four registered editions print
    the same command on four different pages, which is the whole reason
    the ranges are per edition.
    """
    pages = {
        "old": {7: {7: "Function name: X_BOTH <A>\n"}},
        "new": {9: {9: "Function name: X_BOTH <A>\n"}},
    }
    read, _calls = _recording_reader(pages)
    (command,) = sweep_editions(
        [_edition(tmp_path, "old", (7, 7)), _edition(tmp_path, "new", (9, 9))],
        recorded=[],
        reader=read,
    )
    assert command.pages == {"old": 7, "new": 9}
    assert command.detail.page == 9, "the detail is the newest edition's statement"


def test_the_chapter_range_is_read_for_signatures_and_the_index_range_for_labels(tmp_path):
    """The two reads per edition go to the two ranges, and not the other way.

    Swapping them constructs cleanly and reads the Script Index as the
    scripting reference, so nothing downstream can detect it; this is
    the only place that can.
    """
    pages = {
        "ed": {
            10: {10: "Function name: X_BOTH <A>\n"},
            50: {50: "X_BOTH Some Section\n"},
        }
    }
    read, calls = _recording_reader(pages)
    (command,) = sweep_editions(
        [_edition(tmp_path, "ed", (10, 10), index=(50, 50))], recorded=[], reader=read
    )
    assert calls == [("ed", 50, 50), ("ed", 10, 10)]
    assert command.section == "Some Section", (
        "the index range supplies the section label, which is the only thing it is for"
    )


def test_an_edition_with_no_index_range_is_read_once_and_left_unlabelled(tmp_path):
    """The control for the test above, and the reason the index is optional."""
    pages = {"ed": {10: {10: "Function name: X_BOTH <A>\n"}}}
    read, calls = _recording_reader(pages)
    (command,) = sweep_editions([_edition(tmp_path, "ed", (10, 10))], recorded=[], reader=read)
    assert calls == [("ed", 10, 10)]
    assert command.section is None


def test_a_command_recorded_in_the_database_is_not_swept(tmp_path):
    """The control: absence is measured against the database."""
    pages = {"new": {1: {1: "Function name: X_BOTH <A>\nFunction name: X_NEW <A>\n"}}}
    read, _calls = _recording_reader(pages)
    swept = sweep_editions([_edition(tmp_path, "new", (1, 1))], recorded=["X_BOTH"], reader=read)
    assert [command.name for command in swept] == ["X_NEW"]


def test_a_sweep_of_no_editions_refuses_rather_than_reporting_nothing_absent():
    """An empty manifest must not read as the good answer.

    With no manual read, nothing is documented and the sweep returns
    zero absent, which is indistinguishable from the complete database
    it is run to confirm. A configuration error that looks like success
    is the one shape worth refusing outright.
    """
    with pytest.raises(ManualDraftError, match="indistinguishable from a complete database"):
        sweep_editions([], recorded=["X_BOTH"])


def _manifest(tmp_path, body, *, manuals=("x.pdf",)):
    for name in manuals:
        (tmp_path / name).write_bytes(b"not a pdf")
    manifest = tmp_path / "editions.yaml"
    manifest.write_text(body, encoding="utf-8")
    return manifest


def test_the_manifest_round_trips_a_full_edition_row(tmp_path, monkeypatch):
    """Every field a row can carry, read back as the sweep will use it."""
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path,
        '- label: "26.121"\n'
        "  source: SRC-740\n"
        "  manual: x.pdf\n"
        "  chapter: 284-379\n"
        "  index: 380-386\n",
    )
    (edition,) = read_edition_manifest(manifest)
    assert edition.label == "26.121"
    assert edition.source == "SRC-740"
    assert edition.chapter == (284, 379)
    assert edition.index == (380, 386)


def test_an_edition_without_an_index_is_read_unlabelled_rather_than_skipped(tmp_path, monkeypatch):
    """The index supplies section labels only, so it is optional.

    Skipping an edition for want of one would silently drop a whole
    build from the union, which is the failure this sweep exists to
    prevent.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(tmp_path, '- label: "26.121"\n  manual: x.pdf\n  chapter: 1-2\n')
    (edition,) = read_edition_manifest(manifest)
    assert edition.index is None


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ('- label: "a"\n  manual: x.pdf\n', "missing 'chapter'"),
        ("- manual: x.pdf\n  chapter: 1-2\n", "missing 'label'"),
        ('- label: "a"\n  manual: x.pdf\n  chapter: 12\n', "FIRST-LAST"),
        ('- label: "a"\n  manual: x.pdf\n  chapter: 20-2\n', "ends before it starts"),
        ('- label: "a"\n  manual: x.pdf\n  chapter: one-two\n', "FIRST-LAST"),
        ('- label: "a"\n  manual: x.pdf\n  chapter: 1-2\n  indexpages: 3-4\n', "unknown key"),
    ],
)
def test_a_malformed_manifest_row_is_refused(tmp_path, monkeypatch, row, message):
    """A manifest is hand-edited and rarely, so every refusal says what is wrong."""
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(tmp_path, row)
    with pytest.raises(ManualDraftError, match=message):
        read_edition_manifest(manifest)


def test_a_refusal_names_the_row_it_is_about(tmp_path, monkeypatch):
    """The position, which a single-row manifest cannot show.

    A real manifest has one row per registered build, so "which row" is
    the first thing a maintainer needs and the last thing a one-row
    fixture can prove.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path,
        '- label: "good"\n  manual: x.pdf\n  chapter: 1-2\n'
        '- label: "bad"\n  manual: x.pdf\n  chapter: 9-3\n',
    )
    with pytest.raises(ManualDraftError, match=r"entry 2"):
        read_edition_manifest(manifest)


def test_a_row_naming_a_manual_that_does_not_exist_is_refused_before_any_pdf_opens(
    tmp_path, monkeypatch
):
    """Every row is checked before the first manual is read.

    Without this, a typo in the fourth row surfaces only after three
    manuals have each had two page ranges extracted, which on a
    400-page pdf is minutes of work thrown away for information that
    was available at manifest-read time.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path,
        '- label: "good"\n  manual: x.pdf\n  chapter: 1-2\n'
        '- label: "typo"\n  manual: nope.pdf\n  chapter: 1-2\n',
    )
    with pytest.raises(ManualDraftError, match="is not a readable file"):
        read_edition_manifest(manifest)


def test_a_manifest_that_is_not_a_list_of_rows_is_refused(tmp_path):
    """The shape check, so a mapping does not iterate as its keys."""
    manifest = tmp_path / "editions.yaml"
    manifest.write_text('label: "26.121"\n', encoding="utf-8")
    with pytest.raises(ManualDraftError, match="list of edition mappings"):
        read_edition_manifest(manifest)


def test_the_sweep_cli_prints_the_absent_commands_flat_and_grouped(tmp_path, monkeypatch, capsys):
    """The subcommand itself, which nothing exercised.

    `--by-section` is built entirely on the section label, and the flat
    form prints the per-edition pages; both are the maintainer's actual
    interface to this tool.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path, '- label: "26.121"\n  manual: x.pdf\n  chapter: 10-10\n  index: 50-50\n'
    )
    pages = {
        10: {10: "Function name: X_NOT_IN_THE_DATABASE <A>\n"},
        50: {50: "X_NOT_IN_THE_DATABASE Some Section\n"},
    }
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: pages[first],
    )

    assert cli_main(["sweep", "--editions", str(manifest)]) == 0
    flat = capsys.readouterr().out
    assert "1 edition(s) read (26.121): 1 command(s) absent" in flat
    assert "X_NOT_IN_THE_DATABASE" in flat
    assert "26.121:p.10" in flat

    assert cli_main(["sweep", "--editions", str(manifest), "--by-section"]) == 0
    grouped = capsys.readouterr().out
    assert "Some Section  [1]" in grouped


def test_the_sweep_cli_fails_only_when_asked_to(tmp_path, monkeypatch, capsys):
    """Reporting is the ordinary use, so a non-empty sweep is not a failure.

    The flag exists for the other use, asserting completeness, which is
    the claim this milestone rests on and which stdout parsing is a poor
    way to check.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(tmp_path, '- label: "26.121"\n  manual: x.pdf\n  chapter: 10-10\n')
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: {10: "Function name: X_NOT_IN_THE_DATABASE <A>\n"},
    )
    assert cli_main(["sweep", "--editions", str(manifest)]) == 0
    capsys.readouterr()
    assert cli_main(["sweep", "--editions", str(manifest), "--fail-if-absent"]) == 1


def test_the_sweep_cli_exits_zero_with_the_flag_when_nothing_is_absent(
    tmp_path, monkeypatch, capsys
):
    """The control: --fail-if-absent passes on a complete database."""
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(tmp_path, '- label: "26.121"\n  manual: x.pdf\n  chapter: 10-10\n')
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: {10: "Function name: SET_SOLVER_STEADY\n"},
    )
    assert cli_main(["sweep", "--editions", str(manifest), "--fail-if-absent"]) == 0
    assert "0 command(s) absent" in capsys.readouterr().out


# ---------------------------------------------------------------------
# The command surface per edition, and what changes between builds.
# Added 2026-08-09 with the 25 series, whose whole point is comparison:
# the registry gained three builds registered for reproducibility of
# published runs, and the first question about them is what their
# scripting surface has that the newer ones do not.
# ---------------------------------------------------------------------


def test_the_surface_of_each_edition_is_what_its_chapter_documents(tmp_path):
    pages = {
        "old": {1: {1: "Function name: A_COMMAND <A>\nFunction name: DROPPED_LATER <A>\n"}},
        "new": {1: {1: "Function name: A_COMMAND <A>\nFunction name: ADDED_LATER <A>\n"}},
    }
    read, _calls = _recording_reader(pages)
    surfaces = edition_surfaces(
        [_edition(tmp_path, "old", (1, 1)), _edition(tmp_path, "new", (1, 1))],
        reader=read,
    )
    # Sorted within an edition, so a diff of two editions is stable and
    # reviewable; the ORDER OF THE EDITIONS is the manifest's and is
    # asserted separately, because that one carries meaning.
    assert surfaces == {
        "old": ("A_COMMAND", "DROPPED_LATER"),
        "new": ("ADDED_LATER", "A_COMMAND"),
    }
    assert list(surfaces) == ["old", "new"]


def test_the_surface_read_never_opens_the_script_index(tmp_path):
    """One read per edition, the chapter body.

    The index is incomplete: a command can carry a signature heading and
    no index row, which is why the sweep is body-driven. Reading the
    index here would report a smaller surface for every edition and the
    difference would look like the vendor removing commands.
    """
    pages = {
        "ed": {
            10: {10: "Function name: BODY_ONLY <A>\n"},
            50: {50: "INDEXED_ONLY  Some Section\n"},
        }
    }
    read, calls = _recording_reader(pages)
    surfaces = edition_surfaces([_edition(tmp_path, "ed", (10, 10), index=(50, 50))], reader=read)
    assert calls == [("ed", 10, 10)]
    assert surfaces["ed"] == ("BODY_ONLY",)


def test_consecutive_builds_are_compared_in_the_order_given():
    """Insertion order, because sorting the labels picks wrong neighbours.

    "26.100" and "26.101" sort into release order by luck; "26.12" sorts
    between them and is neither's neighbour. The manifest's order is the
    release order and this must use it.
    """
    surfaces = {
        "26.100": ["KEPT", "DROPPED"],
        "26.101": ["KEPT", "ADDED"],
        "26.120": ["KEPT", "ADDED", "LATER"],
    }
    changes = surface_changes(surfaces)
    assert [(c.older, c.newer) for c in changes] == [("26.100", "26.101"), ("26.101", "26.120")]
    assert changes[0].gained == ("ADDED",)
    assert changes[0].lost == ("DROPPED",)
    assert changes[1].gained == ("LATER",)
    assert changes[1].lost == ()


def test_one_edition_yields_no_comparison_rather_than_a_self_comparison():
    assert surface_changes({"26.121": ["ONLY"]}) == ()


def test_reading_no_edition_is_refused_rather_than_reported_as_empty():
    with pytest.raises(ManualDraftError, match="at least one edition"):
        edition_surfaces([])


def test_two_editions_sharing_a_label_are_refused(tmp_path):
    """A repeated label would compare a build against itself.

    The result is keyed by label, so the second reading overwrites the
    first and the pair vanishes from the comparison entirely; the report
    then shows one fewer change than there are neighbours and says
    nothing about it.
    """
    pages = {
        "a": {1: {1: "Function name: X_ONE <A>\n"}},
        "b": {1: {1: "Function name: X_TWO <A>\n"}},
    }
    read, _calls = _recording_reader(pages)
    editions = [_edition(tmp_path, "a", (1, 1)), _edition(tmp_path, "b", (1, 1))]
    editions[1] = Edition(label="a", manual=editions[1].manual, chapter=(1, 1))
    with pytest.raises(ManualDraftError, match="more than one edition the label"):
        edition_surfaces(editions, reader=read)


# ---------------------------------------------------------------------
# Reading a pdf that a renderer produced, not the vendor's typesetter
# (2026-08-10). The 25.000 install ships only a compiled help archive,
# so its manual is converted to pdf before it can be cited by page. Two
# properties of the reader turned out to be load bearing for that, and
# both were measured across all six vendor editions before changing:
# neither costs a single command there.
# ---------------------------------------------------------------------


def test_a_signature_behind_a_margin_glyph_is_still_read():
    """Layout extraction keeps a margin glyph in its own column.

    The line then reads as that glyph, a run of spaces, and only then
    the heading. Anchored at position zero the match fails and the
    command is invisible; measured at two commands of 272 in the
    converted 25.000 pdf.
    """
    page = "\ufffd" + " " * 40 + "Function name: CLOSE_FLIGHTSTREAM\n"
    found = parse_signatures({343: page})
    assert "CLOSE_FLIGHTSTREAM" in found, (
        "a heading preceded by a margin glyph is not read, so every command whose "
        "page carries one is invisible"
    )


def test_the_heading_is_still_required_to_stand_on_its_own():
    """Tolerating a prefix must not tolerate a mention inside a word.

    The widened pattern requires the heading to begin a line or follow
    whitespace. Without that it would match inside another token and
    invent commands out of prose, which is the failure mode a looser
    pattern buys.
    """
    assert parse_signatures({1: "xFunction name: NOT_A_COMMAND\n"}) == {}


def test_the_pdf_reader_asks_for_layout_extraction(monkeypatch, tmp_path):
    """The default mode joins separate visual lines into one.

    A sample block and the signature heading after it then come back as
    a single line, and a parser reading line by line sees neither. On
    the converted 25.000 pdf the default found 58 commands of 272 and
    layout found 270; on all six vendor editions the two modes agree
    exactly, so this costs nothing and is not visible in any count.
    A silent revert to the default would be.
    """
    import pypdf

    from pyflightstream.utils import manual as manual_module

    seen = {}

    class Page:
        def extract_text(self, **kwargs):
            seen.update(kwargs)
            return "Function name: SOMETHING <A>\n"

    class Reader:
        def __init__(self, _path):
            self.pages = [Page()]

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    target = tmp_path / "manual.pdf"
    target.write_bytes(b"%PDF-1.4 not a real pdf; the reader is stubbed")
    manual_module.read_pdf_pages(target, first=1, last=1)
    assert seen.get("extraction_mode") == "layout", (
        f"read_pdf_pages asked for {seen!r}; it must request layout extraction, or a "
        "converted manual loses three quarters of its commands"
    )


# ---------------------------------------------------------------------
# Citations re-checked against the document they cite. Added 2026-08-10,
# after ten rows were found citing a 25.000 manual that had moved five
# pages underneath them: the conversion of that edition was corrected to
# strip a generator footer, and the rows written from the earlier
# conversion kept its numbers. Every one pointed at a real page of a
# real manual, so nothing about them looked wrong.
# ---------------------------------------------------------------------


class _FakeRegistry:
    """The two attributes the check reads off a loaded registry."""

    def __init__(self, commands):
        self.commands = commands


class _Row:
    """The two fields of a version row this check reads."""

    def __init__(self, note=None, status=None):
        self.note = note
        self.status = status


class _Entry:
    def __init__(self, versions):
        self.versions = versions


class _Status:
    def __init__(self, value):
        self.value = value


def test_a_citation_pointing_at_the_wrong_page_is_a_finding(tmp_path):
    pages = {"ed": {1: {1: "Function name: A_COMMAND <A>\n", 7: "Function name: A_COMMAND <A>\n"}}}
    read, _calls = _recording_reader(pages)
    registry = {"A_COMMAND": _Entry({"ed": _Row(note="SRC-999 p.7, this edition")})}
    (finding,) = stale_citations(
        [_edition(tmp_path, "ed", (1, 1))], recorded=_FakeRegistry(registry), reader=read
    )
    assert (finding.command, finding.edition, finding.cited, finding.found) == (
        "A_COMMAND",
        "ed",
        7,
        1,
    )


def test_a_citation_on_the_right_page_is_silent(tmp_path):
    pages = {"ed": {1: {1: "Function name: A_COMMAND <A>\n"}}}
    read, _calls = _recording_reader(pages)
    registry = {"A_COMMAND": _Entry({"ed": _Row(note="SRC-999 p.1, this edition")})}
    assert (
        stale_citations(
            [_edition(tmp_path, "ed", (1, 1))], recorded=_FakeRegistry(registry), reader=read
        )
        == ()
    )


def test_a_command_the_edition_does_not_print_reports_no_page(tmp_path):
    """The two findings are different and the field says which.

    A moved page is a citation to correct. A row citing an edition that
    does not document the command at all is a row that should not exist,
    and reporting both as `found=<some page>` would hide the second
    inside the first.
    """
    pages = {"ed": {1: {1: "Function name: OTHER_COMMAND <A>\n"}}}
    read, _calls = _recording_reader(pages)
    registry = {"A_COMMAND": _Entry({"ed": _Row(note="SRC-999 p.1, this edition")})}
    (finding,) = stale_citations(
        [_edition(tmp_path, "ed", (1, 1))], recorded=_FakeRegistry(registry), reader=read
    )
    assert finding.found is None


def test_a_removed_row_cites_the_edition_that_states_the_withdrawal(tmp_path):
    """Not a finding, and the reason is what `removed` means.

    A removed row's citation is evidence ABOUT an absence, so the page
    it names is one where the command is legitimately not printed.
    Checking it the same way would report every honest removal record as
    a defect, which is the fastest way to get a check switched off.
    """
    pages = {"ed": {1: {1: "Function name: OTHER_COMMAND <A>\n"}}}
    read, _calls = _recording_reader(pages)
    registry = {
        "A_COMMAND": _Entry(
            {"ed": _Row(note="SRC-999 p.1, stops printing it", status=_Status("removed"))}
        )
    }
    assert (
        stale_citations(
            [_edition(tmp_path, "ed", (1, 1))], recorded=_FakeRegistry(registry), reader=read
        )
        == ()
    )


def test_an_edition_outside_the_manifest_is_not_checked_and_not_reported(tmp_path):
    """Silence is never a claim that a row is right.

    Six of the seven registered builds could be dropped from a manifest
    by mistake and this would still return nothing, which is why the
    function returns findings and the caller prints how many editions it
    read.
    """
    pages = {"ed": {1: {1: "Function name: A_COMMAND <A>\n"}}}
    read, _calls = _recording_reader(pages)
    registry = {"A_COMMAND": _Entry({"unlisted": _Row(note="SRC-999 p.4444, this edition")})}
    assert (
        stale_citations(
            [_edition(tmp_path, "ed", (1, 1))], recorded=_FakeRegistry(registry), reader=read
        )
        == ()
    )


def test_a_row_with_no_page_in_its_note_is_not_checked(tmp_path):
    pages = {"ed": {1: {1: "Function name: A_COMMAND <A>\n"}}}
    read, _calls = _recording_reader(pages)
    registry = {"A_COMMAND": _Entry({"ed": _Row(note="verified by probe, no page")})}
    assert (
        stale_citations(
            [_edition(tmp_path, "ed", (1, 1))], recorded=_FakeRegistry(registry), reader=read
        )
        == ()
    )


def test_a_page_span_is_satisfied_by_either_page(tmp_path):
    """Twenty-six shipped rows cite a span and none of them was tested.

    Narrowing the pattern from `pp?` to `p` left every citation test
    green while dropping those twenty-six rows from the check, and
    reading only the first page of a span reports a correct citation as
    wrong whenever the heading sits on the second. Both halves are
    pinned here: the span is accepted, and either page satisfies it.
    """
    read, calls = _recording_reader(
        {"ed": {7: {7: "Function name: ON_SEVEN <A>\n", 8: "Function name: ON_EIGHT <A>\n"}}}
    )
    registry = _FakeRegistry(
        {
            "ON_SEVEN": _Entry({"ed": _Row(note="SRC-999 pp.7-8, this edition")}),
            "ON_EIGHT": _Entry({"ed": _Row(note="SRC-999 pp.7-8, this edition")}),
        }
    )
    edition = _edition(tmp_path, "ed", (7, 8), source="SRC-999")
    assert stale_citations([edition], recorded=registry, reader=read) == ()
    # The recording reader is used rather than a local one so the range
    # asked for is visible: a reader returning the same text for every
    # page would let this pass while the check read the wrong pages.
    assert calls == [("ed", 7, 8)]
    # ASSERT THE REACH, NOT THE SILENCE. Narrowing the pattern from `pp?`
    # to `p` also produces no findings, because every span row then
    # fails to match and is skipped, and an empty tuple cannot tell a
    # span that was read from one that was never looked at.
    assert citation_reach == {"ed": [2, 2]}

    # And the span must still be able to FAIL, on a page outside it.
    outside = _FakeRegistry({"ON_SEVEN": _Entry({"ed": _Row(note="SRC-999 pp.4-5, this edition")})})
    (finding,) = stale_citations([edition], recorded=outside, reader=read)
    assert (finding.cited, finding.found, finding.reason) == (4, 7, "moved")


def test_a_citation_naming_another_edition_is_a_finding(tmp_path):
    """Half a citation checked is worse than none, because it reads clean.

    A note carries a source id and a page. Reading the page alone runs a
    26.121 row against the 26.121 pdf while the note says SRC-003, whose
    pages differ from it by a uniform three, so the wrong document is
    checked and a coincidence is cheap.
    """
    pages = {"ed": {1: "Function name: A_COMMAND <A>\n"}}

    def read(manual, *, first, last):
        return {page: pages["ed"][1] for page in range(first, last + 1)}

    registry = _FakeRegistry({"A_COMMAND": _Entry({"ed": _Row(note="SRC-003 p.1, another")})})
    edition = Edition(label="ed", manual=tmp_path / "ed.pdf", chapter=(1, 1), source="SRC-999")
    (tmp_path / "ed.pdf").write_bytes(b"injected reader")
    (finding,) = stale_citations([edition], recorded=registry, reader=read)
    assert finding.command == "A_COMMAND"
    # And it says WHICH finding it is: `found is None` alone carried
    # both "the edition does not print it" and "the note names another
    # document", and the report printed the first for both.
    assert finding.reason == "wrong source"


def test_the_citation_check_refuses_a_configuration_that_would_read_clean(tmp_path):
    """Three refusals, all of the same shape as the siblings' own.

    An empty manifest, a duplicate label and a database with no version
    rows each return no findings, and no findings is what this function
    says when everything is right. A configuration error reading as the
    good outcome is the one shape worth refusing outright, which this
    module already says twice about its neighbours.
    """
    registry = _FakeRegistry({"A": _Entry({"ed": _Row(note="SRC-999 p.1, x")})})
    read, _calls = _recording_reader({"ed": {1: {1: "Function name: A <X>\n"}}})
    with pytest.raises(ManualDraftError, match="at least one edition"):
        stale_citations([], recorded=registry, reader=read)
    with pytest.raises(ManualDraftError, match="more than one edition the label"):
        stale_citations(
            [_edition(tmp_path, "ed", (1, 1)), _edition(tmp_path, "ed", (1, 1))],
            recorded=registry,
            reader=read,
        )
    with pytest.raises(ManualDraftError, match="no version rows"):
        stale_citations(
            [_edition(tmp_path, "ed", (1, 1))],
            recorded=_FakeRegistry({"A": _Entry({})}),
            reader=read,
        )


def test_the_citations_cli_exits_non_zero_on_a_finding(tmp_path, monkeypatch, capsys):
    """The subcommand's whole distinguishing property, which nothing pinned.

    It is the only one of the five that gates on exit code, and the
    incident it was built for is a citation nobody re-read. A `return 0`
    on findings, or a dropped dispatch branch, would leave the only
    mechanism against that incident silently green.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path, '- label: "26.121"\n  source: SRC-740\n  manual: x.pdf\n  chapter: 10-11\n'
    )
    # Two pages, neither of them holding the command the row cites.
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: {
            10: "Function name: START_SOLVER <A>\n",
            11: "Function name: STOP <A>\n",
        },
    )
    assert cli_main(["citations", "--editions", str(manifest)]) == 1
    out = capsys.readouterr().out
    assert "do not hold" in out
    # And the reach line, because a clean count of editions over an
    # unchecked database is what this report used to print.
    assert "version rows carry a citation this can re-read" in out


def test_the_citations_cli_names_the_builds_the_manifest_left_out(tmp_path, monkeypatch, capsys):
    """A one-build manifest must not read as a clean bill for eight."""
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path, '- label: "26.121"\n  source: SRC-740\n  manual: x.pdf\n  chapter: 10-10\n'
    )
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: {10: "Function name: START_SOLVER <A>\n"},
    )
    cli_main(["citations", "--editions", str(manifest)])
    out = capsys.readouterr().out
    assert "no manifest row for" in out
    assert "25.000" in out


def test_the_real_registry_satisfies_the_protocol_the_checks_declare():
    """The seam between `utils` and `commands`, pinned from the low side.

    `utils.manual` sits below `commands` and cannot import it, so the
    citation and reachability checks read the database structurally.
    Every read had a swallowing default, which means renaming
    `VersionStatus.note` would have made the citation check return no
    findings forever, over a green suite, and the report would have said
    every citation holds. The protocol makes the contract writable and
    this makes it checkable; the fixtures elsewhere in this module are
    doubles and prove nothing about the real type.
    """
    from pyflightstream.commands import CommandRegistry
    from pyflightstream.utils.manual import RegistryLike

    registry = CommandRegistry.load()
    assert isinstance(registry, RegistryLike)
    entry = registry.commands["START_SOLVER"]
    assert isinstance(entry.versions, dict)
    row = next(iter(entry.versions.values()))
    # The two attributes read by name, so a rename is a red here rather
    # than silence in the report.
    assert hasattr(row, "note")
    assert hasattr(row.status, "value")


def _reg(commands, view=None):
    """A registry double carrying the two attributes the checks read."""

    class _R:
        def __init__(self):
            self.commands = commands

        def for_version(self, label):
            if view is None:
                raise _UnknownVersionError(f"FlightStream version {label!r} is not registered")
            return view

    return _R()


class _View:
    """A version view that refuses the names it was told to refuse."""

    def __init__(self, refuses=()):
        self._refuses = set(refuses)

    def __getitem__(self, name):
        if name in self._refuses:
            raise _RefusalError(f"{name} has no recorded evidence")
        return name


class _UnknownVersionError(Exception):
    """Stands in for UnknownVersionError, which this layer cannot import.

    Named rather than a bare ValueError because the code under test
    matches the class NAME across the layer boundary, so a double that
    raises something else proves nothing about the seam. The real thing
    is covered by the sweep test that uses the registry itself.
    """


_UnknownVersionError.__name__ = "UnknownVersionError"


class _RefusalError(Exception):
    """Stands in for CommandNotInVersionError, which this layer cannot import."""


_RefusalError.__name__ = "CommandNotInVersionError"


def test_a_documented_command_with_no_entry_is_unreachable(tmp_path):
    """The first of the two reasons, and the one the sweep already saw."""
    read, _calls = _recording_reader({"ed": {1: {1: "Function name: NOT_IN_THE_DATABASE <A>\n"}}})
    (found,) = unreachable_commands(
        [_edition(tmp_path, "ed", (1, 1))], recorded=_reg({}, _View()), reader=read
    )
    assert (found.command, found.reason) == ("NOT_IN_THE_DATABASE", "no entry")


def test_an_entry_with_no_row_for_the_edition_is_unreachable(tmp_path):
    """The second reason, and the one the coverage sweep is blind to.

    This is the whole point of the measure: the entry EXISTS, so a
    comparison of entry names reports nothing, while the build cannot
    emit a command its own manual documents.
    """
    read, _calls = _recording_reader({"ed": {1: {1: "Function name: HAS_AN_ENTRY <A>\n"}}})
    (found,) = unreachable_commands(
        [_edition(tmp_path, "ed", (1, 1))],
        recorded=_reg({"HAS_AN_ENTRY": object()}, _View(refuses=["HAS_AN_ENTRY"])),
        reader=read,
    )
    assert (found.command, found.reason) == ("HAS_AN_ENTRY", "refused")


def test_a_command_reachable_only_by_inheritance_is_not_reported(tmp_path):
    """The control a row-counting implementation would get wrong.

    Reachability is the measure and row presence is not, because a
    genuine hotfix carries its base release's records: 26.122 holds
    twenty direct rows and reaches 375, so counting rows would report it
    as missing hundreds.
    """
    read, _calls = _recording_reader({"ed": {1: {1: "Function name: INHERITED <A>\n"}}})
    assert (
        unreachable_commands(
            [_edition(tmp_path, "ed", (1, 1))],
            recorded=_reg({"INHERITED": object()}, _View()),
            reader=read,
        )
        == ()
    )


def test_an_unregistered_build_is_swept_and_reported_rather_than_raising(tmp_path):
    """Reading a new manual before registering the build is the first workflow.

    `Edition.label` promises that nothing resolves it against the
    version registry. Asking for a version view does resolve it, so
    this reports the label as unmeasurable instead of letting an
    UnknownVersionError out of a CLI, which is what it did for one
    commit.
    """
    read, _calls = _recording_reader({"ed": {1: {1: "Function name: ANY_COMMAND <A>\n"}}})
    (found,) = unreachable_commands(
        [_edition(tmp_path, "ed", (1, 1))], recorded=_reg({}), reader=read
    )
    assert found.reason == "label resolves to no single build"


def test_the_reachability_check_refuses_a_configuration_that_would_read_clean(tmp_path):
    """Same two refusals as its siblings, for the same reason."""
    read, _calls = _recording_reader({"ed": {1: {1: "Function name: A <X>\n"}}})
    with pytest.raises(ManualDraftError, match="at least one edition"):
        unreachable_commands([], recorded=_reg({}, _View()), reader=read)
    with pytest.raises(ManualDraftError, match="more than one edition the label"):
        unreachable_commands(
            [_edition(tmp_path, "ed", (1, 1)), _edition(tmp_path, "ed", (1, 1))],
            recorded=_reg({}, _View()),
            reader=read,
        )


def test_the_sweep_fails_on_a_row_level_gap_alone(tmp_path, monkeypatch, capsys):
    """The second half of the disjunction, which the first hid.

    `--fail-if-absent` reads `absent or unreachable`, and the test that
    covered it used a command that is both, so either half could be
    deleted with a green suite. This uses a command the database HAS an
    entry for and no row for on the swept build: absent is empty and the
    run must still fail, which is the whole reason the second measure
    exists.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path, '- label: "25.000"\n  source: SRC-749\n  manual: x.pdf\n  chapter: 10-10\n'
    )
    # IMPORT_CAD is in the database and deliberately carries no 25.000
    # row, its older editions using a layout a version row cannot
    # express (PLN-20260810-1200).
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: {10: "Function name: IMPORT_CAD <A>\n"},
    )
    assert cli_main(["sweep", "--editions", str(manifest), "--fail-if-absent"]) == 1
    out = capsys.readouterr().out
    assert "0 command(s) absent" in out
    assert "cannot emit" in out


def test_an_edition_read_with_no_rows_is_not_reported_as_missing_from_the_manifest(
    tmp_path, monkeypatch, capsys
):
    """Two states the report used to print as one, and it printed the wrong one.

    The reach dict only gained a key inside the walk over the database,
    so a manifest edition that no entry has a row for never entered it,
    and the CLI then said "no manifest row for" a build whose manual it
    had just read. That is the same hiding the reach counter was added
    to end, one level down.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path,
        '- label: "26.130"\n  source: SRC-999\n  manual: x.pdf\n  chapter: 10-10\n',
    )
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: {10: "Function name: START_SOLVER <A>\n"},
    )
    cli_main(["citations", "--editions", str(manifest)])
    out = capsys.readouterr().out
    assert "26.130  0 of 0   <- read, and no entry carries a row for it" in out
    assert "no manifest row for 26.130" not in out


@pytest.mark.parametrize("label", ["26.130", "26.12"])
def test_a_label_the_registry_cannot_resolve_is_reported_by_the_real_sweep(
    label, tmp_path, monkeypatch, capsys
):
    """Both refusals, against the REAL registry rather than a double.

    A version registry refuses a label two ways: the name is
    unregistered, or it is a vendor alias several builds share. The
    first version of this handling matched the wording of one, so a
    manifest naming 26.12, which is the name the pdf prints and the
    likelier of the two in the read-before-you-register workflow, put an
    AmbiguousVersionAliasError through the CLI as a traceback.
    """
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(
        tmp_path,
        f'- label: "{label}"\n  source: SRC-999\n  manual: x.pdf\n  chapter: 10-10\n',
    )
    monkeypatch.setattr(
        "pyflightstream.utils.manual.read_pdf_pages",
        lambda manual, *, first, last: {10: "Function name: START_SOLVER <A>\n"},
    )
    assert cli_main(["sweep", "--editions", str(manifest)]) == 0
    assert "label resolves to no single build" in capsys.readouterr().out


def test_the_reach_record_is_cleared_before_the_manuals_are_read():
    """A failed run must not leave the previous manifest's numbers behind.

    The reset sat after the loop that opens the manuals, so a reader
    that raised left the last good run's counts in place for a caller
    that caught the error and printed the reach. Moving it earlier fixed
    that and nothing asserted it, so the ordering could drift back.
    """
    from pyflightstream.utils.manual import citation_reach

    class _BoomError(Exception):
        pass

    good = _FakeRegistry({"A_COMMAND": _Entry({"ed": _Row(note="SRC-999 p.1, x")})})
    edition = Edition(label="ed", manual=pathlib.Path("x.pdf"), chapter=(1, 1), source="SRC-999")

    stale_citations(
        [edition],
        recorded=good,
        reader=lambda manual, *, first, last: {1: "Function name: A_COMMAND <A>\n"},
    )
    assert citation_reach == {"ed": [1, 1]}

    def explode(manual, *, first, last):
        raise _BoomError("pdf unreadable")

    with pytest.raises(_BoomError):
        stale_citations([edition], recorded=good, reader=explode)
    assert citation_reach == {"ed": [0, 0]}, (
        "a run whose reader raised left the previous manifest's reach in place, so a "
        "caller catching the error and printing the reach would report numbers from "
        "a different measurement"
    )
