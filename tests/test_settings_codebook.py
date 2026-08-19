"""Tier 1: the all-numeric settings form and the codebook that freezes it.

Pipeline role: quality gate on PFS-2012.12. The settings record that
PFS-2012.11 puts beside every result is strings and mixed types, which a
plotting script or a spreadsheet cannot treat as data, so an OPTIONAL
second form carries nothing but numbers.

THE MEASUREMENT THAT DECIDES THE LAYOUT, reproduced here because the
whole design rests on it: across the sixty-five flags of a bare snapshot
on 26.120 the value field holds FIVE Python types (fifty-seven None, two
int, four float, one str, one list). One column cannot carry that and
stay numeric, and a sentinel inside it collides the moment a real
setting equals the sentinel.

THE RULE: a sentinel may only appear in a column whose domain we
control. The code columns are ours, assigned densely from 1, so 999 is
free there by construction. The value columns are not: they carry
iteration counts, angles and boundary indices, any of which can
legitimately be 999. So unknown stops being a magic number and becomes
the provenance code it always was, and the value columns are left empty.

AND THE PAGE IS THE SOURCE. This repository's own rule is that
documentation is not a guard, so the page is not a description of the
code: the test below reads ``docs/settings-codebook.md`` and fails when
the code disagrees with it. A flag that gains a state without the page
moving is what makes every file written afterwards misread.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from pyflightstream.exceptions import MalformedOutputError, OutputExistsError
from pyflightstream.post.settings_table import (
    CODEBOOK_VERSION,
    ENUMERATIONS,
    FLAG_IDS,
    LOSSY_KINDS,
    PROVENANCE_CODES,
    TIDY_COLUMNS,
    VALUE_KINDS,
    codebook,
    read_settings_table,
    settings_table,
    write_settings_table,
)
from pyflightstream.script import Script, helpers
from pyflightstream.script.solver_setup import FLAG_SPECS

PAGE = Path(__file__).resolve().parents[1] / "docs" / "settings-codebook.md"


def snapshot(**keywords):
    """A real snapshot, so the table under test is one a campaign writes."""
    script = Script(version="26.120")
    return helpers.solver_settings(script, velocity=30.0, **keywords)


# --- the page IS the source -------------------------------------------------


def _page_table(heading: str) -> list[tuple[str, ...]]:
    """Return the rows of the markdown table under one heading."""
    text = PAGE.read_text(encoding="utf-8")
    body = text.split(heading, 1)[1]
    rows = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = tuple(cell.strip() for cell in stripped.strip("|").split("|"))
            if set("".join(cells)) <= set("-: "):
                continue
            rows.append(cells)
        elif rows and not stripped:
            break
    return rows[1:]  # drop the header row


def test_the_page_exists_and_names_the_codebook_version():
    """A file names the codebook that wrote it, so the page must too."""
    text = PAGE.read_text(encoding="utf-8")
    assert re.search(rf"codebook version[^0-9]*{CODEBOOK_VERSION}\b", text, re.IGNORECASE), (
        "the page does not state the codebook version the library writes, so a file "
        "naming a version cannot be resolved against it"
    )


def test_the_page_and_the_code_agree_on_every_flag_id():
    """Sixty-five rows, and the same ids in both homes.

    Read from the page and compared against the code, in that direction:
    the page is the contract and the code is what must match it.
    """
    rows = _page_table("## Flag ids")
    published = {command: int(flag_id) for flag_id, command in rows}
    assert published == FLAG_IDS, (
        "the flag-id table on docs/settings-codebook.md and post.settings_table.FLAG_IDS "
        "disagree; every file written between the two moving is misread from then on"
    )


def test_the_page_and_the_code_agree_on_the_provenance_and_kind_codes():
    provenance = {name: int(code) for code, name in _page_table("## Provenance codes")}
    kinds = {name: int(code) for code, name in _page_table("## Value kind codes")}
    assert provenance == PROVENANCE_CODES
    assert kinds == VALUE_KINDS


def test_the_page_and_the_code_agree_on_every_per_flag_enumeration():
    rows = _page_table("## Per-flag enumerations")
    published: dict[str, dict[str, int]] = {}
    for command, code, token in rows:
        published.setdefault(command, {})[token] = int(code)
    coded = {
        command: {token: index for index, token in enumerate(tokens, start=1)}
        for command, tokens in ENUMERATIONS.items()
    }
    assert published == coded, (
        "a per-flag enumeration differs between the page and the code, so 999 is the "
        "sentinel in one reading and a value in the other"
    )


def test_every_flag_the_library_knows_has_a_frozen_id():
    """A new flag joins the codebook deliberately, or the guard fires."""
    missing = [spec.command for spec in FLAG_SPECS if spec.command not in FLAG_IDS]
    assert not missing, (
        f"{missing} carry no frozen flag id. FLAG_SPECS grows whenever a build adds a "
        "settings command; the id must be APPENDED to the codebook and the page moved "
        "in the same commit, never derived from the position in FLAG_SPECS, which shifts"
    )
    assert sorted(FLAG_IDS.values()) == list(range(1, len(FLAG_IDS) + 1)), (
        "flag ids must be dense from 1, which is what makes 999 free in a code column"
    )


# --- the tidy form ----------------------------------------------------------


def test_the_tidy_form_is_entirely_numeric_and_one_row_per_flag():
    rows = settings_table([snapshot()])
    assert len(rows) == len(FLAG_IDS)
    assert tuple(rows[0]) == TIDY_COLUMNS
    for row in rows:
        for column, value in row.items():
            assert value is None or isinstance(value, (int, float)), (
                f"column {column} holds {value!r}, which is not a number; the whole point "
                "of this form is that a tool that cannot read strings can read it"
            )


def test_an_unknown_flag_is_the_provenance_code_with_the_value_columns_empty():
    """Unknown is a code, never a magic number in a value column."""
    rows = {row["flag_id"]: row for row in settings_table([snapshot()])}
    unknown = [
        row for row in rows.values() if row["provenance_code"] == PROVENANCE_CODES["unknown"]
    ]
    assert unknown, "no flag came out unknown, which no bare 26.120 call can be true of"
    for row in unknown:
        assert row["value_num"] is None
        assert row["value_code"] is None
        assert row["value_count"] is None


def test_a_value_column_carries_the_value_and_nothing_else():
    """The explicit velocity lands in value_num as itself."""
    rows = {row["flag_id"]: row for row in settings_table([snapshot()])}
    velocity = rows[FLAG_IDS["SOLVER_SET_VELOCITY"]]
    assert velocity["provenance_code"] == PROVENANCE_CODES["explicit"]
    assert velocity["value_kind"] == VALUE_KINDS["float"]
    assert velocity["value_num"] == pytest.approx(30.0)
    assert velocity["value_code"] is None


def test_an_enumerated_flag_takes_its_per_flag_code():
    rows = {row["flag_id"]: row for row in settings_table([snapshot()])}
    layer = rows[FLAG_IDS["SET_BOUNDARY_LAYER_TYPE"]]
    assert layer["value_kind"] == VALUE_KINDS["enumerated"]
    assert layer["value_code"] == ENUMERATIONS["SET_BOUNDARY_LAYER_TYPE"].index("TRANSITIONAL") + 1
    assert layer["value_num"] is None


def test_a_list_flag_contributes_its_length_and_says_it_is_lossy():
    rows = {row["flag_id"]: row for row in settings_table([snapshot()])}
    selection = rows[FLAG_IDS["SET_VORTICITY_DRAG_BOUNDARIES"]]
    assert selection["value_kind"] == VALUE_KINDS["list"]
    assert selection["value_count"] == 0
    assert codebook()["lossy_kinds"] == ["list", "mapping"]


def test_an_unknown_enumeration_token_is_refused_rather_than_coded():
    """A token with no frozen code cannot be given one at write time."""
    setup = snapshot()
    flags = dict(setup.flags)
    layer = flags["SET_BOUNDARY_LAYER_TYPE"]
    flags["SET_BOUNDARY_LAYER_TYPE"] = layer.model_copy(update={"value": "PLASMA"})
    tampered = setup.model_copy(update={"flags": flags})

    with pytest.raises(MalformedOutputError, match="PLASMA"):
        settings_table([tampered])


# --- fill -------------------------------------------------------------------


def test_a_fill_reaches_the_code_columns_only():
    rows = settings_table([snapshot()], fill=999)
    unknown = [row for row in rows if row["provenance_code"] == PROVENANCE_CODES["unknown"]]
    assert unknown
    for row in unknown:
        assert row["value_kind"] == 999
        assert row["value_code"] == 999
        assert row["value_num"] is None, "the fill reached a value column"
        assert row["value_count"] is None, "the fill reached a value column"


def test_asking_to_fill_a_value_column_is_refused_naming_the_flags():
    """The collision, refused rather than reintroduced wearing an option."""
    with pytest.raises(MalformedOutputError) as refused:
        settings_table([snapshot()], fill=999, fill_values=True)

    message = str(refused.value)
    assert "999" in message
    assert "SOLVER_SET_ITERATIONS" in message, (
        "the refusal must name the flags whose legal range contains the fill; a refusal "
        "that only states the rule leaves the caller to guess which flags it protects"
    )


# --- the wide form ----------------------------------------------------------


def test_the_wide_form_is_one_row_per_run_with_two_columns_per_flag():
    rows = settings_table([snapshot(), snapshot(aoa=2.0)], wide=True)
    assert len(rows) == 2
    columns = list(rows[0])
    assert columns[:2] == ["codebook_version", "run_index"]
    assert len(columns) == 2 + 2 * len(FLAG_IDS)

    velocity = FLAG_IDS["SOLVER_SET_VELOCITY"]
    assert rows[0][f"f{velocity}_value"] == pytest.approx(30.0)
    assert rows[0][f"f{velocity}_prov"] == PROVENANCE_CODES["explicit"]
    aoa = FLAG_IDS["SOLVER_SET_AOA"]
    assert rows[0][f"f{aoa}_prov"] == PROVENANCE_CODES["unknown"]
    assert rows[1][f"f{aoa}_value"] == pytest.approx(2.0)


# --- the file names the codebook that wrote it ------------------------------


def test_the_written_pair_carries_its_own_legend(tmp_path):
    """The file is readable alone: it names the codebook and carries it."""
    table, legend = write_settings_table(tmp_path / "settings.csv", [snapshot()])

    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(FLAG_IDS)
    assert {int(row["codebook_version"]) for row in rows} == {CODEBOOK_VERSION}

    published = json.loads(legend.read_text(encoding="utf-8"))
    assert published["codebook_version"] == CODEBOOK_VERSION
    assert published["flag_ids"] == FLAG_IDS
    assert published["provenance_codes"] == PROVENANCE_CODES
    assert published["value_kinds"] == VALUE_KINDS
    assert published["enumerations"] == {
        name: list(tokens) for name, tokens in ENUMERATIONS.items()
    }
    assert published["lossy_kinds"] == list(LOSSY_KINDS)
    assert "lossy" in published["lossy_note"].lower(), (
        "the legend must SAY that this form loses information, or a reader takes the "
        "length of a boundary selection for the selection"
    )


def test_a_file_written_under_another_codebook_is_refused_not_reinterpreted(tmp_path):
    """Never silently reinterpreted: that is the whole reason for the stamp."""
    table, _legend = write_settings_table(tmp_path / "settings.csv", [snapshot()])
    text = table.read_text(encoding="utf-8")
    aged = text.replace(f"\n{CODEBOOK_VERSION},", f"\n{CODEBOOK_VERSION + 7},")
    (tmp_path / "aged.csv").write_text(aged, encoding="utf-8")

    with pytest.raises(MalformedOutputError) as refused:
        read_settings_table(tmp_path / "aged.csv")
    message = str(refused.value)
    assert str(CODEBOOK_VERSION + 7) in message and str(CODEBOOK_VERSION) in message


def test_a_file_written_under_this_codebook_round_trips(tmp_path):
    table, _legend = write_settings_table(tmp_path / "settings.csv", [snapshot()])
    rows = read_settings_table(table)
    assert len(rows) == len(FLAG_IDS)
    assert rows[0]["codebook_version"] == CODEBOOK_VERSION


def test_a_table_with_no_rows_says_so_rather_than_blaming_its_header(tmp_path):
    """Two different failures, two different messages.

    A file with the column and no rows describes no run; telling that
    reader the column is missing sends them looking for a defect in a
    file that has none.
    """
    table, _legend = write_settings_table(tmp_path / "empty.csv", [])
    with pytest.raises(MalformedOutputError, match="no rows"):
        read_settings_table(table)

    headerless = tmp_path / "headerless.csv"
    headerless.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(MalformedOutputError, match="no codebook_version column"):
        read_settings_table(headerless)


def test_the_writer_refuses_an_existing_destination(tmp_path):
    write_settings_table(tmp_path / "settings.csv", [snapshot()])
    with pytest.raises(OutputExistsError, match="already exists"):
        write_settings_table(tmp_path / "settings.csv", [snapshot()])
