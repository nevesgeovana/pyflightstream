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
    ManualCommand,
    coverage_against,
    parse_script_index,
    parse_signatures,
    propose_layout,
)

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
    assert reaching == ["from pyflightstream.extras import missing_extra"], reaching
