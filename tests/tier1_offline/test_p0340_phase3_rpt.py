"""The PHASE3 evidence is a summary report in the repository (FR-343).

Marker P0340-PHASE3-RPT. RPT-131 summarises, in one facts table, the facts of
a private licensed campaign that committed reports use: each row carries the
fact, its number, the date, the solver build and the command or script step.
These tests read the report as a Markdown table, check that the specification
and the reports that take a fact from the campaign cite it, and scan it for
the forbidden identifiers the repository's own house-style guard holds, with a
planted identifier as the control.
"""

import re
from pathlib import Path

import pytest

from tests.tier1_offline.test_house_style import (
    FORBIDDEN,
    FORBIDDEN_WORDS,
    PRIVATE_LEDGER_ID,
    _identifier_offenses,
)
from tests.tier1_offline.test_p0330_no_executable_hash import scan

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
RPT_131 = next(REPORTS.glob("RPT-131_*.md"))
SRS = ROOT / "docs" / "srs" / "functional-requirements.md"

COLUMNS = ["fact", "number", "date", "solver build", "command or script step"]
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _tables(text: str) -> list[list[list[str]]]:
    """Every Markdown table of ``text`` as its list of rows of cells."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _facts(text: str) -> tuple[list[str], list[list[str]]]:
    tables = _tables(text)
    assert len(tables) == 1, f"RPT-131 must carry exactly one table, found {len(tables)}"
    header, rule, *rows = tables[0]
    assert all(set(cell) <= set("-: ") for cell in rule), rule
    return [cell.casefold() for cell in header], rows


def _offences(text: str) -> list[str]:
    """The forbidden identifiers of the house-style guard found in ``text``."""
    found = []
    for char, name in FORBIDDEN.items():
        if char in text:
            found.append(f"an {name}")
    for word in FORBIDDEN_WORDS:
        if word.casefold() in text.casefold():
            found.append("a forbidden name")
    found.extend(_identifier_offenses(text))
    if PRIVATE_LEDGER_ID.search(text):
        found.append("a private ledger identifier")
    return found


def test_rpt_131_is_one_facts_table_with_exactly_the_five_columns():
    """P0340-PHASE3-RPT, FR-343 R1: columns, and a value in every cell of every row."""
    header, rows = _facts(RPT_131.read_text(encoding="utf-8"))
    assert header == COLUMNS
    assert len(rows) >= 8, "the table must hold the facts the committed reports use"
    for row in rows:
        assert len(row) == len(COLUMNS), row
        fact, number, date, build, command = row
        assert fact and number and build and command, row
        assert ISO_DATE.match(date), row
        assert "26.124" in build, row


def test_the_facts_table_check_refuses_a_missing_cell_and_an_extra_column():
    """P0340-PHASE3-RPT, FR-343 R1: the table reader fails what it exists to catch."""
    good = (
        "| fact | number | date | solver build | command or script step |\n|---|---|---|---|---|\n"
    )
    row = "| a fact | 3 | 2026-09-28 | 26.124 | `START_SOLVER` |\n"
    header, rows = _facts(good + row)
    assert header == COLUMNS and rows == [[c.strip() for c in row.strip().strip("|").split("|")]]
    empty = "| a fact |  | 2026-09-28 | 26.124 | `START_SOLVER` |\n"
    _, rows = _facts(good + empty)
    assert not all(rows[0]), "an empty number cell must read as empty"
    extra = good.replace("step |", "step | note |").replace("---|\n", "---|---|\n")
    header, _ = _facts(extra)
    assert header != COLUMNS
    two = good + row + "\ntext\n\n" + good + row
    with pytest.raises(AssertionError):
        _facts(two)


def test_the_specification_and_the_reports_that_use_the_campaign_cite_rpt_131():
    """P0340-PHASE3-RPT, FR-343 R2: every citation of the private file resolves."""
    srs = SRS.read_text(encoding="utf-8")
    start = srs.index('requirement "FR-343')
    end = srs.index('requirement "FR-344', start)
    assert "RPT-131" in srs[start:end]
    for pattern in ("RPT-089_*.md", "RPT-093_*.md"):
        report = next(REPORTS.glob(pattern)).read_text(encoding="utf-8")
        assert "RPT-131" in report, pattern
    index = (REPORTS / "README.md").read_text(encoding="utf-8")
    assert RPT_131.name in index


def test_rpt_131_carries_no_forbidden_identifier_and_the_scan_finds_a_planted_one():
    """P0340-PHASE3-RPT, FR-343 R3 and R4: the house-style scan, with its control."""
    text = RPT_131.read_text(encoding="utf-8")
    assert _offences(text) == []
    for planted in (
        text + "\ncontact " + "someone" + chr(64) + "company.org\n",
        text + "\nsee C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "run\n",
        text + "\nthe employer " + FORBIDDEN_WORDS[0] + "\n",
        text + "\n" + "PL" + "N-1234\n",
        text + "\na dash " + chr(0x2014) + " here\n",
    ):
        assert _offences(planted), planted[-40:]
    offenders, read = scan([RPT_131])
    assert read == 1 and offenders == [], offenders
