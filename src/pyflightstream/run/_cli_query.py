"""The read-only query verbs of ``pyfs-matrix`` (0.35.0): ``status``.

Pipeline role: the command side of :mod:`pyflightstream.workspace.ledger`.
:func:`run_query` is what :mod:`pyflightstream.run.cli` dispatches a query verb
to; each verb reads one ledger snapshot and renders the rows the ledger returns,
as a table, as JSON or as CSV (FR-385, FR-388 R3), so the three forms print the
same rows and a Python caller of the ledger gets them too.

A query writes nothing (FR-383): it is not a live-log command, it starts no
stage, so no activity entry is made, and it takes no manifest lock. The console
opening block and the signature stay on standard error, so standard output
carries the data alone under ``--json`` and ``--csv``.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._console import table
from pyflightstream._errors import PyflightstreamError
from pyflightstream.run._cli_query_history import add_history_parsers, run_history_query
from pyflightstream.run._cli_query_point import _add_parsers, _run_point_query
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.ledger import (
    PLANNED,
    POINT_COLUMNS,
    STATUS_COLUMNS,
    Ledger,
    listed_sims,
    point_rows,
    read_ledger,
    status_rows,
    status_text,
)

#: The read-only verbs this module answers, dispatched by :mod:`pyflightstream.run.cli`.
QUERY_COMMANDS = ("status", "show", "log", "trace", "history", "diff")

#: The table heading of a row key; a key not here is printed upper case.
_HEADINGS = {"iterations": "ITER", "wall_s": "WALL"}

#: What the footer says of a plan, by the state :meth:`Ledger.freshness` gives.
_PLAN_STATES = {
    "current": "made from the matrix on disk",
    "stale": "made from another revision of the matrix; plan it again (pyfs-matrix plan {stem})",
    "unpinned": "does not say which matrix it measured; plan it again (pyfs-matrix plan {stem})",
    "no matrix": "the matrix {stem} is in neither matrix home of the workspace",
    "unreadable": "the plan cannot be read",
    "absent": "no plan",
}


def add_query_parsers(subparsers: Any) -> None:
    """Register the read-only query verbs of 0.35.0: ``status`` (FR-379 to FR-385).

    Parameters
    ----------
    subparsers : argparse subparsers action
        The ``pyfs-matrix`` subcommand table, from
        :func:`pyflightstream.run._cli_parsers._build_parser`.
    """
    status = subparsers.add_parser(
        "status",
        help="one row per polar: simulation, polar, sweep, datapoints, matrix and status "
        "(reads only)",
        description=(
            "Reads the run records, the plans and the posts, and changes no file: no "
            "record, log or lock is written. A polar whose datapoints share one status "
            "shows that word; a mixed polar shows the count of each. A point a plan names "
            "and no record carries is shown as `planned`, in lower case because no "
            "recorded status is written so."
        ),
    )
    status.add_argument(
        "--additional", action="store_true", help="list the additional register as recorded"
    )
    status.add_argument(
        "--sims",
        default=None,
        help="only these simulations, comma separated, with or without brackets: "
        "2006,2007 or [2006,2007]",
    )
    status.add_argument(
        "--matrix",
        default=None,
        metavar="STEM",
        help="only the polars of this matrix, by its stem (found in the workspace root or "
        "inputs/matrices/)",
    )
    status.add_argument(
        "--status",
        dest="statuses",
        action="append",
        default=[],
        metavar="WORD",
        help="only the polars with a datapoint in this status, as recorded (repeatable; a "
        "trailing * matches every word it begins, for example FAILED_*)",
    )
    status.add_argument(
        "--failed",
        action="store_true",
        help="only the polars with at least one failed datapoint",
    )
    status.add_argument(
        "--points",
        dest="per_point",
        action="store_true",
        help="one row per datapoint instead of one per polar",
    )
    output = status.add_mutually_exclusive_group()
    output.add_argument(
        "--json", action="store_true", help="print the rows as one JSON document on stdout"
    )
    output.add_argument(
        "--csv", action="store_true", help="print the rows as CSV on stdout, LF line ends"
    )
    status.add_argument(
        "--workspace",
        default=".",
        help="the workspace root carrying runs.json (default: the current directory)",
    )
    status.add_argument(
        "--runs",
        default=None,
        metavar="NAME",
        help="another manifest in the workspace root, read in place of runs.json",
    )
    _add_parsers(subparsers)
    add_history_parsers(subparsers)


def run_query(args: argparse.Namespace) -> int:
    """Run one query verb of ``pyfs-matrix``; returns the process exit code.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line of a verb of :data:`QUERY_COMMANDS`.

    Returns
    -------
    int
        0 when it printed; 1 when ``--sims`` named only simulations that hold
        no record and no planned point; 2 for a refused argument or a manifest
        that is not JSON.
    """
    if args.subcommand in ("history", "diff"):
        return run_history_query(args)
    if args.subcommand != "status" or args.additional:
        return _run_point_query(args, _emit)
    return _cmd_status(args)


def _status_words(words: Sequence[str]) -> list[str]:
    """Return the ``--status`` words, refusing one no recorded or derived status takes."""
    known = [status.value for status in RunStatus] + [PLANNED]
    for word in words:
        stem = word[:-1] if word.endswith("*") else None
        if (stem is None and word not in known) or (
            stem is not None and not any(item.startswith(stem) for item in known)
        ):
            raise ValueError(
                f"status (CLI: --status) names {word!r}, which no status takes; the words "
                f"are {', '.join(known)}, and a trailing * matches every word it begins"
            )
    return list(words)


def _cmd_status(args: argparse.Namespace) -> int:
    """``pyfs-matrix status``: one row per polar, or per datapoint (FR-379 to FR-385)."""
    try:
        statuses = _status_words(args.statuses)
        sims = None if args.sims is None else listed_sims(args.sims)
        if sims is not None and not sims:
            raise ValueError(
                "sims (CLI: --sims) names no simulation; give the ids comma separated, for "
                "example --sims 2006,2007"
            )
        ledger = read_ledger(args.workspace, runs=args.runs)
    except (PyflightstreamError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    select = {"sims": sims, "matrix": args.matrix, "statuses": statuses, "failed": args.failed}
    rows = point_rows(ledger, **select) if args.per_point else status_rows(ledger, **select)
    columns = POINT_COLUMNS if args.per_point else STATUS_COLUMNS
    unmatched = ledger.unmatched(sims or ())
    _say_what_was_not_read(ledger, unmatched)
    if args.json:
        _emit(json.dumps(ledger.document(rows), indent=2) + _textio.LINE_END)
    elif args.csv:
        _emit(_csv_text(rows, columns))
    else:
        for line in table([_headings(columns), *(_cells(row, columns) for row in rows)], indent=""):
            print(line)
        for line in _footer(ledger, rows, per_point=args.per_point, matrix=args.matrix):
            print(line)
    # The exit status of a selection that matched nothing is an open choice; this is
    # the stand-in script's: 1 only when every simulation named holds nothing.
    return 1 if sims and len(unmatched) == len(set(sims)) else 0


def _say_what_was_not_read(ledger: Ledger, unmatched: Sequence[str]) -> None:
    """Name, on standard error, each id that matched nothing and each unreadable row."""
    for sim in unmatched:
        folders = ledger.sim_folders(sim)
        where = f" (its folder is at {', '.join(folders)})" if folders else ""
        print(
            f"sims (CLI: --sims): simulation {sim} holds no record and no planned point{where}",
            file=sys.stderr,
        )
    for item in ledger.unreadable:
        print(
            f"{ledger.manifest.name} row {item['position']} (run {item['run_id']}) cannot be "
            f"read: {item['error']}; the other rows are shown",
            file=sys.stderr,
        )


def _headings(columns: Sequence[str]) -> list[str]:
    return [_HEADINGS.get(column, column.upper()) for column in columns]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _cells(row: Mapping[str, object], columns: Sequence[str]) -> list[str]:
    return [_cell(row.get(column)) for column in columns]


def _csv_text(rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> str:
    """Return the rows as CSV, a heading row first, every record ending in LF (NFR-32)."""
    buffer = io.StringIO()
    writer = _textio.csv_writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(_cells(row, columns))
    return buffer.getvalue()


def _emit(text: str) -> None:
    """Write ``text`` to standard output as UTF-8 bytes, so its LF line ends stay LF."""
    sys.stdout.flush()
    raw = getattr(sys.stdout, "buffer", None)
    if raw is None:
        sys.stdout.write(text)
        return
    raw.write(text.encode("utf-8"))
    raw.flush()


def _footer(
    ledger: Ledger,
    rows: Sequence[Mapping[str, object]],
    *,
    per_point: bool,
    matrix: str | None,
) -> list[str]:
    """Return the totals, then per matrix whether its plan and its post are current."""
    stems = {row["matrix"] for row in rows}
    if per_point:
        counts = Counter(str(row["status"]) for row in rows)
        lines = [f"{len(rows)} datapoint(s): {status_text(counts) or 'none'}"]
    else:
        counts = Counter()
        for row in rows:
            polar = row.get("counts")
            if isinstance(polar, Mapping):
                counts.update({str(word): int(count) for word, count in polar.items()})
        lines = [
            f"{len(rows)} polar(s), {sum(counts.values())} datapoint(s): "
            f"{status_text(counts) or 'none'}"
        ]
    for item in ledger.freshness(matrix=matrix):
        if item["matrix"] in stems:
            lines += _freshness_lines(item)
    return lines


def _freshness_lines(item: Mapping[str, object]) -> list[str]:
    stem = str(item["matrix"])
    plan = _PLAN_STATES[str(item["plan"])].format(stem=stem)
    if item["post"] == "absent":
        post = "no post yet"
    else:
        state = "complete" if item["post"] == "complete" else "NOT complete"
        post = f"written {item['posted_at']}, {state}"
    missing = item["not_posted"]
    if isinstance(missing, list) and missing and item["post"] != "absent":
        post += f", {len(missing)} recorded run(s) not yet posted (pyfs-matrix post {stem})"
    return [f"plan/{stem}: {plan}", f"post/{stem}: {post}"]
