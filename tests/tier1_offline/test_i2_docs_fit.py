"""Tier 1: the guide's helper listings bind to the helpers' signatures (package I2).

Pipeline role: quality gate on the didactic material. The guide taught
``helpers.probe_points(..., units="METER")`` and ``helpers.probe_line(...,
units="METER", ...)``, two keywords the helpers do not take, so both listings
raised TypeError in a reader's session while the name-only guard
(test_guide_api_names) stayed green: a name that exists is not a call that binds.
"""

import ast
import inspect
import re
from pathlib import Path

from pyflightstream.script import helpers
from tests.tier1_offline._workflow_docs import DEFINITION_DOCS

GUIDE = Path(__file__).parents[2] / "guide" / "pyflightstream_user_guide.tex"

_LISTING = re.compile(r"\\begin\{lstlisting\}(?:\[[^\]]*\])?(.*?)\\end\{lstlisting\}", re.S)
_CALL = re.compile(r"helpers\.(\w+)\(")
_COMMENT = re.compile(r"#[^\n]*")
_PLACEHOLDER = re.compile(r",?\s*\.\.\.\s*\)$")


def _helper_calls() -> list[tuple[str, ast.Call, bool]]:
    """Every ``helpers.<name>(...)`` call of every listing, parsed whole, wherever it stands.

    A call after ``disc = `` or indented under ``for`` is a call too. A trailing ``...`` (the
    slide's "and the rest") is dropped and the call is marked partial: its arguments are
    checked, its completeness is not.
    """
    calls: list[tuple[str, ast.Call, bool]] = []
    text = GUIDE.read_text(encoding="utf-8")
    for listing in _LISTING.findall(text):
        listing = _COMMENT.sub("", listing)
        for match in _CALL.finditer(listing):
            start = match.start()
            depth = 0
            for offset, char in enumerate(listing[start:]):
                depth += char == "("
                depth -= char == ")"
                if depth == 0 and char == ")":
                    source = listing[start : start + offset + 1]
                    break
            else:
                continue
            partial = bool(_PLACEHOLDER.search(source))
            source = _PLACEHOLDER.sub(")", source)
            try:
                node = ast.parse(source, mode="eval").body
            except SyntaxError:
                continue
            if isinstance(node, ast.Call):
                calls.append((match.group(1), node, partial))
    return calls


def test_p0320_i2_the_guide_call_guard_reads_every_helper_call_of_the_listings():
    """P0320-I2-GUIDE-ALL: a guard that skips a call it cannot reach guards nothing there.

    The first form read only calls that opened a line at column zero, 21 of the 32 the
    listings hold; the eleven after ``disc = `` or indented were never bound.
    """
    text = GUIDE.read_text(encoding="utf-8")
    present = sum(len(_CALL.findall(_COMMENT.sub("", body))) for body in _LISTING.findall(text))
    assert len(_helper_calls()) == present


def test_p0320_i2_every_helper_call_in_the_guide_binds_to_its_signature():
    """P0320-I2-GUIDE-CALLS: a listing that raises TypeError teaches a call that fails."""
    assert _helper_calls(), "the guide has helper listings; the reader found none"
    broken = []
    for name, node, partial in _helper_calls():
        function = getattr(helpers, name, None)
        if function is None:
            broken.append(f"helpers.{name}: there is no such helper")
            continue
        positional = [object()] * len(node.args)
        keywords = {kw.arg: object() for kw in node.keywords if kw.arg}
        signature = inspect.signature(function)
        try:
            (signature.bind_partial if partial else signature.bind)(*positional, **keywords)
        except TypeError as error:
            broken.append(f"helpers.{name}: {error}")
    assert not broken, "guide listings that raise TypeError:\n  " + "\n  ".join(broken)


_PAGE = Path(__file__).parents[2] / "docs" / "gui-to-pyfs.md"
_COMMAND = re.compile(r"`([A-Z][A-Z0-9_]+)`")


def _rows() -> list[list[str]]:
    rows = []
    for line in _PAGE.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            rows.append([cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip()[1:-1])])
    return rows


def test_p0320_i2_the_raw_route_is_offered_only_for_commands_it_carries():
    """P0320-I2-RAW-ROUTE: a raw line is one line, so a block is refused before the run.

    ``Script.emit_raw`` carries a bare or an inline command and refuses a keyword block, a
    payload or a parameter list. A row of the page that sends a reader to setup table
    ``[[raw]]`` for a block command teaches a route that does not exist.
    """
    from pyflightstream.commands import CommandRegistry, Layout

    database = CommandRegistry.load().commands
    offered = []
    for cells in _rows():
        if len(cells) == 4 and ("`[[raw]]`" in cells[1] or "#the-raw-route" in cells[1]):
            clauses = cells[1].split(";")
            for command in _COMMAND.findall(cells[2]):
                spec = database.get(command)
                if spec is None or spec.layout in (Layout.BARE, Layout.INLINE):
                    continue
                # A block may be NAMED in the cell, but only as out of reach: its own clause
                # says "block" and does not say the raw route "carries" it (a review mutant
                # that wrote "carries `BOOLEAN_UNITE_MESH`" passed the first form of this test).
                clause = next((text for text in clauses if f"`{command}`" in text), "")
                if "block" not in clause or "carries" in clause:
                    offered.append(f"{command} ({spec.layout.value}) in: {cells[0]}")
    assert not offered, "the raw route is offered for block commands:\n  " + "\n  ".join(offered)


def test_p0320_i2_the_surface_removal_row_names_the_command_its_key_writes():
    """P0320-I2-DELETE-SURFACES: `delete_surfaces` writes DELETE_SURFACES, not SURFACE_DELETE.

    SURFACE_DELETE is the keyword-block command of the mesh operations; the setup key emits the
    inline DELETE_SURFACES of the geometry phase (``setup_surfaces._DELETE``). The row that sends
    a reader to the key must list the command the key writes, in the column that says so.
    """
    from pyflightstream.cases import setup_surfaces

    written = setup_surfaces._DELETE
    rows = [cells for cells in _rows() if len(cells) == 4 and "`delete_surfaces`" in cells[1]]
    assert rows, "no row of the page sends a reader to the setup key delete_surfaces"
    for cells in rows:
        assert f"`{written}`" in cells[2], f"row {cells[0]!r} omits {written} from its commands"


def test_p0320_i2_no_step_says_not_yet_for_what_a_key_already_does():
    """P0320-I2-NOT-YET: a probe file and an actuator's wake and switch have keys."""
    said_not_yet = [
        cells[0]
        for cells in _rows()
        if len(cells) == 4
        and "not yet" in cells[1]
        and any(name in cells[2] for name in ("PROBE_POINTS_IMPORT", "SET_ACTUATOR_WAKE_TYPE"))
    ]
    assert not said_not_yet, f"a step a key covers still says not yet: {said_not_yet}"


_DEFINITIONS = DEFINITION_DOCS


def _section(text: str, heading: str) -> str:
    """The body of one ``## `` section of the definitions page."""
    start = text.index(f"\n## {heading}")
    end = text.find("\n## ", start + 4)
    return text[start : end if end != -1 else len(text)]


def test_p0320_i2_the_contents_lists_every_section_the_release_added():
    """P0320-I2-CONTENTS: a section a reader cannot find from the contents does not exist."""
    text = _DEFINITIONS.read_text(encoding="utf-8")
    contents = text.split("<h2>Contents</h2>", 1)[1].split("\n## ", 1)[0]
    missing = [
        heading
        for heading in (
            "The installed-frame copy of a product table",
            "The inflow tools' products",
            "The quasi-steady rotor",
            "The acoustic signals product",
            "The post of other records",
        )
        if heading.lower().replace("'", "") not in contents.lower().replace("'", "")
    ]
    assert not missing, f"the contents of the definitions page omits: {missing}"


def test_p0320_i2_the_acoustic_and_disc_map_definitions_state_every_column_and_the_manifest():
    """P0320-I2-DEFINITIONS: every column the code writes for a new product is on the page."""
    from pyflightstream.post import disc_maps

    text = _DEFINITIONS.read_text(encoding="utf-8")
    acoustics = _section(text, "The acoustic signals product")
    columns = (
        "TIME_S PRESSURE_PA FREQUENCY_HZ AMPLITUDE_PA LEVEL_DB OBSERVER X_M Y_M Z_M SAMPLES "
        "TIME_START_S TIME_END_S SAMPLE_RATE_HZ BIN_HZ OASPL_DB ROTOR HARMONIC ANGLE_DEG RADIUS_M"
    ).split()
    absent = [name for name in columns if f"`{name}`" not in acoustics]
    assert not absent, f"the acoustic definition omits the columns {absent}"
    for phrase in ("acoustic_signals", "`kind` `acoustics`", "acoustic_section"):
        assert phrase in acoustics, f"the acoustic definition does not say {phrase!r}"
    discs = _section(text, "The disc maps")
    unnamed = [name for name in disc_maps.DISC_MAP_COLUMNS[-8:] if f"`{name}`" not in discs]
    assert not unnamed, f"the disc map definition omits the columns {unnamed}"
    installed = _section(text, "The installed-frame copy of a product table")
    assert "out=" in installed, "the installed-frame definition omits its out= argument"
    inflow = _section(text, "The inflow tools' products")
    for name in ("std_vx", "std_vy", "std_vz", "std_mag"):
        assert name in inflow, f"the fluctuation report definition omits {name}"


def test_p0320_i2_field_operations_page_names_every_command_and_option_of_field():
    """P0320-I2-FIELD-OPS: the page that teaches `pyfs-workspace field` lists all of its surface."""
    import argparse

    from pyflightstream.workspace import cli

    page = (Path(__file__).parents[2] / "docs" / "field-operations.md").read_text(encoding="utf-8")
    parser = cli._build_parser()
    field = next(
        action.choices["field"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    operations = next(
        action.choices
        for action in field._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    missing = []
    for name, sub in operations.items():
        if f"field {name}" not in page:
            missing.append(f"field {name}")
        for action in sub._actions:
            for option in action.option_strings:
                if option.startswith("--") and option not in ("--help",) and option not in page:
                    missing.append(f"field {name} {option}")
    assert not missing, f"docs/field-operations.md omits: {sorted(set(missing))}"
