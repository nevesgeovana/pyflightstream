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

import pytest

from pyflightstream.utils import (
    TYPE_RULES,
    ManualCommand,
    coverage_against,
    parse_script_index,
    parse_signatures,
    propose_layout,
    propose_type,
    read_pdf_pages,
    render_entry,
)
from pyflightstream.utils.cli import main as cli_main
from pyflightstream.utils.errors import ManualDraftError

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
    report = coverage_against(manual, ["SET_BASE_REGION_CP", "START_SOLVER"])
    assert report.absent == ("SET_PROP_ACTUATOR_PROFILE",)
    assert report.recorded == ("SET_BASE_REGION_CP",)
    assert report.undocumented == ("START_SOLVER",)
    assert "absent from the database" in report.summary()


def test_coverage_carries_the_detail_of_what_is_absent():
    """So a maintainer can start writing without re-reading the manual."""
    manual = parse_signatures({330: CONTINUATION_PAGE})
    report = coverage_against(manual, [])
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
    message = write_chapter(target, body)
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
    message = write_chapter(target, body, write=True)
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
        ("NUM_BOUNDARIES", "Number of boundaries in the CFD or FEM mesh"),
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
            "The threshold logic to be used. One of the following: ABOVE or BELOW. "
            "The CAD faces that meet this criterion are subject to the action below.",
            ("ABOVE", "BELOW"),
        ),
        (
            "PLANE",
            "Plane of the reference coordinate system to be used for the mirror "
            "operation. One of the following: XY , XZ or YZ",
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


@pytest.mark.parametrize(
    ("earlier", "later", "placeholder", "description", "expected"),
    [
        # One worked case per adjacent pair whose order was wrong once.
        ("opening", "toggle", "NUM_BOUNDARIES", "Number of boundaries. ENABLE or DISABLE", "int"),
        (
            "opening",
            "dimension",
            "SWEEP_TIME",
            "Number of time slices to sweep",
            "int",
        ),
        (
            "dimension",
            "alternatives",
            "SECTION_LENGTH",
            "Length of the section, measured along X or Y",
            "float",
        ),
        (
            "enumeration",
            "toggle",
            "MODE",
            "One of the following: ENABLE, DISABLE, AUTO",
            "enum",
        ),
    ],
)
def test_the_earlier_rule_answers_where_two_rules_both_could(
    earlier, later, placeholder, description, expected
):
    """Each row is a description BOTH named rules can read.

    Without the pairing the order is untested: a rule that never
    competes with another cannot show that it sits in the right place.
    """
    names = [rule.name for rule in TYPE_RULES]
    assert names.index(earlier) < names.index(later)
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
