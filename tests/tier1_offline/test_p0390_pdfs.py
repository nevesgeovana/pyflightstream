"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


GUIDE = REPO / "guide"


USER_GUIDE_TEX = GUIDE / "pyflightstream_user_guide.tex"


V0380_R1_LINE = (
    r"    \item \code{n} is signed revolutions per SECOND: its magnitude sets \code{J}, "
    r"its rotation sign multiplies \code{CP}, and \code{CQ} keeps the torque sign about the "
    r"fixed rotor axis. \code{CTW} is the rotor's force projected on the free stream, against "
    r"it, over \code{rho n^2 D^4}. \code{ETAW} equals \code{ETA} when the shaft lies along the "
    r"stream."
)


def _strip_verbatim_and_math(tex: str) -> str:
    text = re.sub(r"(?<!\\)%.*", "", tex)
    text = re.sub(r"\\begin\{(lstlisting|verbatim)\}.*?\\end\{\1\}", "", text, flags=re.S)
    text = re.sub(r"\\lstinline(.)(.*?)\1", "", text)
    text = re.sub(r"\$\$.*?\$\$", "", text, flags=re.S)
    text = re.sub(r"(?<!\\)\$.*?(?<!\\)\$", "", text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", "", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", "", text, flags=re.S)
    return text


def superscript_defects(tex: str) -> list[str]:
    """FR-1196: the lines with a ``^`` outside math and verbatim; pdfTeX stops on each ("Missing
    $").
    """
    text = _strip_verbatim_and_math(tex)
    return [line.strip() for line in text.splitlines() if "^" in line]


def test_the_user_guide_source_writes_no_superscript_outside_math():
    """P0390-PDFS (FR-1196) the coefficient expression is in a form the typesetter accepts."""
    tex = USER_GUIDE_TEX.read_text(encoding="utf-8")
    defects = superscript_defects(tex)
    assert not defects, f"a superscript outside math stops the build: {defects}"


def test_the_v0380_line_fails_the_superscript_check():
    """P0390-PDFS (FR-1196) control: the v0.38.0 line is refused, its math form accepted."""
    assert superscript_defects(V0380_R1_LINE), "the v0.38.0 line passed the R1 check"
    assert not superscript_defects(r"\item over $\rho n^2 D^4$, \(D^5\)")
    assert not superscript_defects("\\begin{lstlisting}\nCT = T/(rho n^2 D^4)\n\\end{lstlisting}")
    assert not superscript_defects(r"% a comment with n^2")
