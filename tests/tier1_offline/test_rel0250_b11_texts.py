"""The four texts of scope item B11 say what the code and the records say.

Each assertion reads a published text against the thing it describes:
``rotor_coefficients`` applies ``abs(rps)`` to J and the rotation sign to CP;
the CITATION tally's count word is the last ordinal of the list it heads; the
RPT-029 per-module table predates its recount; a blade's window follows its
own rotor's clock.
"""

from __future__ import annotations

import re
from pathlib import Path

from pyflightstream.post.products import rotor_coefficients

ROOT = Path(__file__).resolve().parents[2]

ORDINALS = (
    "FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH "
    "THIRTEENTH FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTEENTH NINETEENTH TWENTIETH"
).split()
COUNTS = (
    "ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN "
    "FIFTEEN SIXTEEN SEVENTEEN EIGHTEEN NINETEEN TWENTY"
).split()


def test_rotor_coefficients_docstring_states_the_rotation_sign() -> None:
    doc = rotor_coefficients.__doc__ or ""
    assert "J    = V / (|n| D)" in doc
    assert "CP   = 2 pi CQ sign(n)" in doc


def test_guide_states_the_rotation_sign() -> None:
    guide = (ROOT / "guide" / "pyflightstream_user_guide.tex").read_text(encoding="utf-8")
    assert "J  = V/(|n|D)" in guide
    assert "CP = 2 pi CQ sign(n)" in guide


def test_citation_tally_word_is_the_highest_ordinal_it_lists() -> None:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    comment = " ".join(
        line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")
    )
    word = re.search(r"in one commit ([A-Z]+) times", comment)
    assert word, "the tally sentence is not found"
    listed = [w for w in re.findall(r"\b([A-Z]{4,})\b", comment[word.end() :]) if w in ORDINALS]
    assert listed, "the tally lists no ordinal"
    # The HIGHEST ordinal: later prose of the same comment names lower ones again.
    assert COUNTS.index(word.group(1)) == max(ORDINALS.index(w) for w in listed)


def test_rpt029_old_table_is_marked_superseded() -> None:
    (report,) = (ROOT / "reports").glob("RPT-029_*.md")
    text = report.read_text(encoding="utf-8")
    assert "## The debt, per module (historical)" in text
    assert "Superseded by the recount" in text


def test_definitions_page_says_a_blade_follows_its_own_rotor_clock() -> None:
    page = (ROOT / "docs" / "post-processing-definitions.md").read_text(encoding="utf-8")
    assert "each blade follows its own rotor's clock" in " ".join(page.split())
