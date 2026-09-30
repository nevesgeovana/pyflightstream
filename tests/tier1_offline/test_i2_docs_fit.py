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

GUIDE = Path(__file__).parents[2] / "guide" / "pyflightstream_user_guide.tex"

_LISTING = re.compile(r"\\begin\{lstlisting\}(?:\[[^\]]*\])?(.*?)\\end\{lstlisting\}", re.S)
_CALL = re.compile(r"^helpers\.(\w+)\(", re.M)


def _helper_calls() -> list[tuple[str, ast.Call]]:
    """Every ``helpers.<name>(...)`` statement of every listing, parsed whole."""
    calls: list[tuple[str, ast.Call]] = []
    text = GUIDE.read_text(encoding="utf-8")
    for listing in _LISTING.findall(text):
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
            try:
                node = ast.parse(re.sub(r"#[^\n]*", "", source), mode="eval").body
            except SyntaxError:
                continue
            if isinstance(node, ast.Call):
                calls.append((match.group(1), node))
    return calls


def test_p0320_i2_every_helper_call_in_the_guide_binds_to_its_signature():
    """P0320-I2-GUIDE-CALLS: a listing that raises TypeError teaches a call that fails."""
    assert _helper_calls(), "the guide has helper listings; the reader found none"
    broken = []
    for name, node in _helper_calls():
        function = getattr(helpers, name, None)
        if function is None:
            continue
        positional = [object()] * len(node.args)
        keywords = {kw.arg: object() for kw in node.keywords if kw.arg}
        try:
            inspect.signature(function).bind(*positional, **keywords)
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
        if len(cells) == 4 and "`[[raw]]`" in cells[1]:
            for command in _COMMAND.findall(cells[2]):
                spec = database.get(command)
                # A block the row names in its own In pyfs cell is named as out of reach.
                if (
                    spec is not None
                    and spec.layout not in (Layout.BARE, Layout.INLINE)
                    and f"`{command}`" not in cells[1]
                ):
                    offered.append(f"{command} ({spec.layout.value}) in: {cells[0]}")
    assert not offered, "the raw route is offered for block commands:\n  " + "\n  ".join(offered)


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


_DEFINITIONS = Path(__file__).parents[2] / "docs" / "post-processing-definitions.md"


def _section(text: str, heading: str) -> str:
    """The body of one ``## `` section of the definitions page."""
    start = text.index(f"\n## {heading}")
    end = text.find("\n## ", start + 4)
    return text[start : end if end != -1 else len(text)]


def test_p0320_i2_the_contents_lists_every_section_the_release_added():
    """P0320-I2-CONTENTS: a section a reader cannot find from the contents does not exist."""
    text = _DEFINITIONS.read_text(encoding="utf-8")
    contents = _section(text, "Contents")
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
