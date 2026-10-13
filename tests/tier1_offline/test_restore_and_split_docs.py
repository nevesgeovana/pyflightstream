"""Documentation guards for CLI forms and references moved by page splits."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from pyflightstream.run._cli_parsers import _build_parser

ROOT = Path(__file__).resolve().parents[2]


def test_doc_restore_and_rebuild_commands_parse():
    """Every pyfs-matrix command shown on the restore page reaches argparse."""
    page = (ROOT / "docs/restore-and-rebuild.md").read_text(encoding="utf-8")
    parser = _build_parser()
    commands = [
        shlex.split(line.strip(), comments=True)[1:]
        for line in page.splitlines()
        if line.strip().startswith("pyfs-matrix ")
    ]
    assert commands
    for command in commands:
        parser.parse_args(command)


def test_split_definition_pages_have_no_above_below_cross_references():
    """Moved sections must use a page and anchor rather than their former position."""
    pattern = re.compile(r"\([^)]*,\s*(?:above|below)\)", re.IGNORECASE)
    pages = [
        ROOT / "docs/definitions/the-additional-post.md",
        ROOT / "docs/definitions/the-boundary-layer-profile-is-not-produced.md",
        ROOT / "docs/definitions/the-solvers-own-plots.md",
    ]
    found = {page.name: pattern.findall(page.read_text(encoding="utf-8")) for page in pages}
    found = {name: refs for name, refs in found.items() if refs}
    assert not found, f"split-page positional references remain: {found}"
