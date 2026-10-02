"""Read-only history and diff command adapters for the workspace ledger.

Pipeline role: parse the two archive-aware query verbs and render their plain
rows as tables, JSON or CSV. No execution stage or workspace writer is entered.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._console import table
from pyflightstream._errors import PyflightstreamError
from pyflightstream.workspace.ledger import diff, history, read_ledger


def add_history_parsers(subparsers: Any) -> None:
    """Register history and diff, whose selectors may name archived runs."""
    history_parser = subparsers.add_parser(
        "history",
        help="every record of a simulation or point, including archives (reads only)",
        description="Read present and archived records with continuation links and archive "
        "stamps. No log, lock, record or extracted file is written.",
    )
    history_parser.add_argument("target", help="simulation id, point name or run id")
    diff_parser = subparsers.add_parser(
        "diff",
        help="compare two runs' recorded identities and scripts (reads only)",
        description="Compare versions, digests, solver flags, flight condition and outcome. "
        "Use run_id@<archive stamp> for an archived copy. Script changes name line numbers "
        "and candidate inputs using rebuild's comparison.",
    )
    diff_parser.add_argument("run_a", help="first run id, optionally @<archive stamp>")
    diff_parser.add_argument("run_b", help="second run id, optionally @<archive stamp>")
    for parser in (history_parser, diff_parser):
        parser.add_argument(
            "--workspace", default=".", help="workspace root (default: current directory)"
        )
        parser.add_argument(
            "--runs", default=None, metavar="NAME", help="another root manifest and its archives"
        )
        output = parser.add_mutually_exclusive_group()
        output.add_argument("--json", action="store_true", help="print one JSON document on stdout")
        output.add_argument(
            "--csv", action="store_true", help="print the same rows as CSV, with LF line ends"
        )


def run_history_query(args: argparse.Namespace) -> int:
    """Render history or diff; 1 means no target, 2 means an invalid request."""
    try:
        ledger = read_ledger(args.workspace, runs=args.runs)
        rows = (
            history(ledger, args.target)
            if args.subcommand == "history"
            else diff(ledger, args.run_a, args.run_b)
        )
    except (PyflightstreamError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for item in (*ledger.unreadable, *(row for row in rows if "error" in row)):
        print(
            f"{item.get('source', ledger.manifest.name)} row {item.get('position')} "
            f"(run {item.get('run_id')}) cannot be read: {item['error']}",
            file=sys.stderr,
        )
    document = ledger.document(rows)
    document["schema"] = f"pyfs-{args.subcommand}/1"
    _render(rows, document, args)
    if args.subcommand == "history" and not any("record" in row for row in rows):
        print(f"target (CLI: history): {args.target!r} holds no recorded run", file=sys.stderr)
        return 1
    return 0


def _cell(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True)
    return "" if value is None else str(value)


def _render(
    rows: list[dict[str, Any]], document: dict[str, object], args: argparse.Namespace
) -> None:
    if args.json:
        _emit(json.dumps(document, indent=2) + "\n")
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    cells = [[_cell(row.get(key)) for key in columns] for row in rows]
    if args.csv:
        stream = io.StringIO(newline="")
        writer = _textio.csv_writer(stream)
        writer.writerows([columns, *cells])
        _emit(stream.getvalue())
    elif cells:
        for line in table([[key.upper() for key in columns], *cells], indent=""):
            print(line)
    else:
        print("No differences." if args.subcommand == "diff" else "No records.")


def _emit(text: str) -> None:
    raw = getattr(sys.stdout, "buffer", None)
    if raw is None:
        sys.stdout.write(text)
    else:
        sys.stdout.flush()
        raw.write(text.encode("utf-8"))
        raw.flush()
