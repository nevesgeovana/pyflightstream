"""The `pyfs-matrix` verbs shown in code blocks are verbs that command still has (DOC-058-01)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MATRIX_VERBS = {
    "plan",
    "run",
    "collect",
    "post",
    "noise",
    "plot-sweeps",
    "support",
    "status",
    "inspect-setups",
}
_VERB = re.compile(r"^\s*(?:\$\s*)?pyfs-matrix\s+([a-z][a-z0-9-]*)", re.MULTILINE)


def _blocks():
    tex = REPO / "guide" / "pyflightstream_user_guide.tex"
    text = tex.read_text(encoding="utf-8")
    for m in re.finditer(r"\\begin\{lstlisting\}.*?\\end\{lstlisting\}", text, re.DOTALL):
        yield tex.name, m.group(0)
    for md in sorted((REPO / "docs").rglob("*.md")):
        for m in re.finditer(r"^```[^\n]*\n(.*?)^```", md.read_text(encoding="utf-8"), re.M | re.S):
            yield str(md.relative_to(REPO)), m.group(1)


def test_matrix_verbs_in_code_blocks_exist():
    bad = sorted(
        {
            (name, verb)
            for name, block in _blocks()
            for verb in _VERB.findall(block)
            if verb not in MATRIX_VERBS
        }
    )
    assert bad == []
