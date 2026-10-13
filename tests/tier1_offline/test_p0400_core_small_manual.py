"""P0400-MANUALDRAFT: the manual drafter and the edition manifest reader.

P0400-MANUALDRAFT-LABEL (PFS-2102.019): an unquoted manifest label 26.120 is
the YAML number 26.12 and was read as the string "26.12"; it is refused with
the quote hint, as the command loader refuses its unquoted version keys.

P0400-MANUALDRAFT-SOURCE (PFS-2102.020): a blank ``source:`` is YAML null and
became the four letters "None", which passed the citation refusal.

P0400-MANUALDRAFT-PHASE (PFS-2102.021, PFS-2102.022): the section-to-phase map
proposed ``solve`` and ``post``, which are not Phase members, and ``init`` for
the file sections.

P0400-MANUALDRAFT-SPLICE (PFS-2102.023): insert_version_row split with
str.splitlines, which also breaks on form feed and NEL, and rejoined every
line with one newline, rewriting a file of mixed line ends.

P0400-MANUALDRAFT-PREFIX (PFS-2102.025): the parameter-table reader merged a
FRAME_TYPE row into FRAME, the earlier placeholder its name starts with.

P0400-MANUALDRAFT-ENUM (PFS-2102.026): drafted enum tokens were written
unquoted, so YAML 1.1 loaded ON and OFF as booleans.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pyflightstream.commands import Phase
from pyflightstream.utils import (
    ManualCommand,
    insert_version_row,
    parse_signatures,
    read_edition_manifest,
    render_entry,
)
from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.utils.manual import _PHASE_BY_SECTION


def _manifest(tmp_path: Path, row: str) -> Path:
    (tmp_path / "m.pdf").write_bytes(b"%PDF-1.4")
    path = tmp_path / "manifest.yaml"
    path.write_text(f"- manual: {tmp_path / 'm.pdf'}\n  chapter: 1-2\n{row}", encoding="utf-8")
    return path


@pytest.mark.parametrize("label", ["26.120", "26.000", "26"])
def test_p0400_manualdraft_label_unquoted_number_is_refused(tmp_path: Path, label: str) -> None:
    """P0400-MANUALDRAFT-LABEL: a bare number label is refused with the quote hint."""
    path = _manifest(tmp_path, f"  label: {label}\n  source: SRC-751\n")
    with pytest.raises(ManualDraftError, match=r'quote it in the YAML \(label: "26.120"\)'):
        read_edition_manifest(path)


def test_p0400_manualdraft_label_quoted_is_read_as_written(tmp_path: Path) -> None:
    """P0400-MANUALDRAFT-LABEL: the quoted label reaches the edition unchanged."""
    path = _manifest(tmp_path, '  label: "26.120"\n  source: SRC-751\n')
    assert read_edition_manifest(path)[0].label == "26.120"


def test_p0400_manualdraft_source_blank_is_refused(tmp_path: Path) -> None:
    """P0400-MANUALDRAFT-SOURCE: a blank source is refused naming the row, before any reader."""
    path = _manifest(tmp_path, '  label: "26.120"\n  source:\n')
    with pytest.raises(ManualDraftError, match=r"entry 1: source None parsed as NoneType"):
        read_edition_manifest(path)


def test_p0400_manualdraft_phase_map_holds_phase_members_only() -> None:
    """P0400-MANUALDRAFT-PHASE: every value of the section map is a Phase member."""
    members = {phase.value for phase in Phase}
    assert {section: p for section, p in _PHASE_BY_SECTION.items() if p not in members} == {}
    assert _PHASE_BY_SECTION["Mesh Import   Export"] == "geometry"


@pytest.mark.parametrize("section", ["Unsteady Solver", "Solver Analysis", "Output Status"])
def test_p0400_manualdraft_phase_mixed_section_drafts_a_question(section: str) -> None:
    """P0400-MANUALDRAFT-PHASE: a section whose entries span phases drafts ``???``."""
    command = ManualCommand(name="X_COMMAND", page=1, section=section)
    entry = render_entry(command, source="SRC-741", versions={"26.100": "documented"})
    assert "phase: ???" in entry


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_p0400_manualdraft_splice_leaves_every_other_byte(newline: str) -> None:
    """P0400-MANUALDRAFT-SPLICE: mixed line ends and a form feed in a note survive the splice."""
    text = (
        f"# chapter{newline}"
        f"X_CMD:{newline}"
        "  layout: inline\n"
        f"  versions:{newline}"
        f'    "26.120": {{status: documented, note: "a\x0cb\x85c"}}{newline}'
        f"Y_CMD:{newline}"
        "  layout: inline"
    )
    edited = insert_version_row(
        text, command="X_CMD", canonical="26.123", status="documented", note="SRC-751 p.1"
    )
    row = f'    "26.123": {{status: documented, note: "SRC-751 p.1"}}{newline}'
    marker = f'note: "a\x0cb\x85c"}}{newline}'
    assert edited == text.replace(marker, marker + row)


def test_p0400_manualdraft_prefix_placeholder_opens_its_own_row() -> None:
    """P0400-MANUALDRAFT-PREFIX: FRAME_TYPE is its own row, not FRAME's continuation."""
    page = (
        "Function name: SET_FOO <FRAME> <FRAME_TYPE>\n"
        "Function parameters:\n"
        "Parameter Value\n"
        "FRAME Index of the coordinate system\n"
        "FRAME_TYPE Can be one of the following: LOCAL, GLOBAL.\n"
        "Sample:\n"
        "SET_FOO 1 LOCAL\n"
    )
    parameters = parse_signatures({300: page})["SET_FOO"].parameters
    assert parameters == {
        "FRAME": "Index of the coordinate system",
        "FRAME_TYPE": "Can be one of the following: LOCAL, GLOBAL.",
    }


def test_p0400_manualdraft_enum_tokens_load_back_as_strings() -> None:
    """P0400-MANUALDRAFT-ENUM: a drafted ON/OFF enum loads back as the strings."""
    page = (
        "Function name: SET_SWITCH <TOGGLE>\n"
        "Function parameters:\n"
        "Parameter Value\n"
        "TOGGLE Turns the feature on or off. Can be ON or OFF\n"
        "Sample:\n"
        "SET_SWITCH ON\n"
    )
    command = parse_signatures({300: page})["SET_SWITCH"]
    entry = render_entry(command, source="SRC-741", versions={"26.100": "documented"})
    loaded = yaml.safe_load(entry)
    assert loaded["SET_SWITCH"]["args"][0]["values"] == ["ON", "OFF"]
