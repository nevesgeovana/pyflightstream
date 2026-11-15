"""PFS-2260 and PFS-2261 guard: no source, page, guide or requirement row names a moved command.

The geometry group of ``pyfs-workspace`` and the four ``pyfs-matrix`` mesh verbs are refused
since 0.58.0, so a message, a page or a cheatsheet line that still tells a user to type one
sends them to a refusal. The refusal table (``_retired_names.py``), the history in
``CHANGELOG.md`` and the old-to-new tables of ``docs/upgrading.md`` are the only places that
may name an old form, and the tests that prove the refusals.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Where an old form is the subject: the refusal table, the history and the upgrading page.
_ALLOWED = {
    "src/pyflightstream/_retired_names.py",
    "CHANGELOG.md",
    "docs/upgrading.md",
}

_MOVED = (
    "refine|prepare-to-refine|audit|inventory|degenerate|trailing-edge|convert2midnodes|"
    "identify-te|collapse-te|visual-inspect|merge|scale|morph|repitch|hub-rings|"
    "sector-to-wheel|sector-remesh|power-off-body|prop-slice|iges-grid|mesh-generated|mesh|"
    "mark-boundaries|export-surface-mesh|build|accept|from-sidecar|iges-convert|beam"
)

#: The records, storage and query verbs pyfs-workspace holds since 0.58.0 (PFS-2261).
_RECORDS = (
    "space-in-use|free-space|delete-sims|sync|restore|rebuild|mark-failed|mark-converged|"
    "search-log-batch|show|log|trace|history|diff"
)

#: The old spellings: the group with or without a verb, the four pyfs-matrix mesh verbs, and
#: the short ``geometry <verb>`` a code span or a cheatsheet entry writes as a command.
_OLD = re.compile(
    r"pyfs-workspace\s+geometry\b"
    r"|pyfs-matrix(?:\s+--?[\w-]+(?:[ =][^\s-]\S*)?)*\s+"
    r"(?:refine|audit-mesh|inventory|degenerate|visual-inspect|" + _RECORDS + r")(?![\w-])"
    r"|(?:`{1,2}|\\sub\{|\\cmd\{|\\code\{|\\pyfs\{)geometry\s+(?:" + _MOVED + r")(?![\w-])"
)


def _old_forms(text: str) -> list[str]:
    """Every old spelling ``text`` holds, as written."""
    return [match.group(0) for match in _OLD.finditer(text)]


def _files() -> list[Path]:
    found = [REPO / "README.md", REPO / "tests" / "requirements_l3.csv"]
    for top, suffixes in (
        ("src", {".py"}),
        ("docs", {".md", ".py", ".toml"}),
        ("guide/latex-sources", {".tex"}),
        ("examples", {".md", ".py", ".toml"}),
    ):
        found += [
            p
            for p in (REPO / top).rglob("*")
            if p.suffix in suffixes and "__pycache__" not in p.parts
        ]
    return [p for p in found if p.is_file() and p.relative_to(REPO).as_posix() not in _ALLOWED]


def test_p0580_no_file_names_a_moved_geometry_command():
    offenders = []
    for path in _files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for form in _old_forms(line):
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{number}: {form}")
    assert len(_files()) > 200  # non-vacuity: the walk found the tree
    assert not offenders, "name the new command (pyfs-mesh, pyfs-geom, pyfs-fsi):\n  " + (
        "\n  ".join(offenders)
    )


def test_p0580_the_guard_sees_each_old_spelling():
    planted = (
        "run `pyfs-workspace geometry refine wing.obj 2`; "
        "pyfs-matrix audit-mesh wing.obj; pyfs-matrix sync runs; "
        r"\sub{geometry inventory <geometry>}{...}; "
        "``geometry beam``; "
        "pyfs-workspace geometry --help; "
        "pyfs-matrix --workspace W sync; pyfs-matrix visual-inspect --name x"
    )
    assert _old_forms(planted) == [
        "pyfs-workspace geometry",
        "pyfs-matrix audit-mesh",
        "pyfs-matrix sync",
        r"\sub{geometry inventory",
        "``geometry beam",
        "pyfs-workspace geometry",
        "pyfs-matrix --workspace W sync",
        "pyfs-matrix visual-inspect",
    ]
    for new in (
        "pyfs-matrix --workspace W plan m.fs",
        "pyfs-mesh refine",
        "pyfs-matrix plan",
        "pyfs-matrix status",
        "pyfs-workspace sync",
        "a geometry build of a body",
        "pyfs-geom iges-convert",
        "`pyfs-mesh audit`",
        "pyfs-mesh visual-inspect wing.obj",
        "pyfs-matrix plot-sweeps --name x",
    ):
        assert not _old_forms(new), new
