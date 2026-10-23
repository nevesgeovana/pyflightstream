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
from pyflightstream.run._alias import _aliases, _resolve, _with_aliases
from pyflightstream.workspace.ledger import diff, history, read_ledger


def add_history_parsers(subparsers: Any) -> None:
    """Register history and diff, whose selectors may name archived runs."""
    history_parser = subparsers.add_parser(
        "history",
        help="every record of a simulation or point, including archives (reads only)",
        description="Read present and archived records with continuation links and archive "
        "stamps. No log, lock, record or extracted file is written.",
    )
    history_parser.add_argument("target", help="simulation id, point name, run id or alias")
    diff_parser = subparsers.add_parser(
        "diff",
        help="compare two runs' recorded identities and scripts (reads only)",
        description="Compare versions, digests, solver flags, flight condition and outcome. "
        "Use run_id@<archive stamp> for an archived copy. Script changes name line numbers "
        "and candidate inputs using rebuild's comparison.",
    )
    diff_parser.add_argument("run_a", help="first run id or alias, optionally @<archive stamp>")
    diff_parser.add_argument("run_b", help="second run id or alias, optionally @<archive stamp>")
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
            history(ledger, _history_target(ledger, args.target, all_attempts=True))
            if args.subcommand == "history"
            else diff(
                ledger, _history_target(ledger, args.run_a), _history_target(ledger, args.run_b)
            )
        )
        rows = _with_aliases(ledger, rows)
        for row in rows:
            if row.get("field") == "run_id":
                for side in ("a", "b"):
                    row[f"{side}_alias"] = _with_aliases(ledger, {"run_id": row[side]}).get(
                        "run_id_alias"
                    )
    except (PyflightstreamError, ValueError, OSError, LookupError) as error:
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


def _history_target(ledger: Any, target: str, *, all_attempts: bool = False) -> str:
    """Resolve known aliases while retaining history's broader and archived selectors."""
    name, separator, stamp = target.partition("@")
    pair = _aliases(ledger).get(name)
    if pair is None:
        return target
    point = f"sim_{pair[0]}/{pair[1]}"
    if all_attempts:
        return point
    if separator:
        matches = {
            row["run_id"]
            for row in history(ledger, point)
            if row.get("archive_stamp") == stamp and "record" in row
        }
        if len(matches) != 1:
            raise LookupError(f"run (CLI: diff): {target!r} needs one archived run id")
        resolved = matches.pop()
    else:
        resolved = _resolve(ledger, name)
    return f"{resolved}@{stamp}" if separator else resolved


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
