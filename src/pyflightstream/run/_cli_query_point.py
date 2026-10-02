"""CLI selection and rendering of show, log, trace and the additional register.

The data readers live in workspace so the Python API can use the same rows.
This module never invokes a pipeline stage or writes a workspace file.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Callable
from typing import Any
from zipfile import BadZipFile

from pyflightstream._console import table
from pyflightstream._errors import PyflightstreamError
from pyflightstream.run._alias import alias_lines, planned_from_plan_files
from pyflightstream.workspace._query_files import _json
from pyflightstream.workspace._query_logs import (
    _select_logs,
    _storage,
)
from pyflightstream.workspace._query_point import _trace_run
from pyflightstream.workspace.ledger import (
    Ledger,
    listed_sims,
    read_ledger,
)
from pyflightstream.workspace.ledger import (
    activity_rows as _activity,
)
from pyflightstream.workspace.ledger import (
    additional_rows as _additional,
)
from pyflightstream.workspace.ledger import (
    point_card as _card,
)
from pyflightstream.workspace.ledger import (
    post_log_groups as _post_groups,
)
from pyflightstream.workspace.ledger import (
    trace_product as _trace,
)


def _add_parsers(subparsers: Any) -> None:
    show = subparsers.add_parser("show", help="print an outcome-first datapoint card (reads only)")
    show.add_argument("target", help="run id, alias, or simulation id")
    show.add_argument("--point", help="point name or 1-based alias index within the simulation")
    log = subparsers.add_parser("log", help="read recorded activity, post or storage calls")
    source = log.add_mutually_exclusive_group()
    source.add_argument("--post", metavar="MATRIX", help="group a matrix's saved post warnings")
    source.add_argument("--storage", action="store_true", help="list the recorded storage calls")
    log.add_argument("--sims", help="only these simulation ids, comma separated")
    log.add_argument("--run", help="only events naming this run id or alias")
    log.add_argument("--stage", help="only this recorded stage (storage: command)")
    log.add_argument("--since", help="events since an ISO time or duration, e.g. 2h, 7d")
    log.add_argument("--problems", action="store_true", help="only problems and failed outcomes")
    log.add_argument(
        "--open",
        dest="open_only",
        action="store_true",
        help="stages started without a finish in the records; never asks a scheduler",
    )
    trace = subparsers.add_parser(
        "trace", help="follow an indexed product to its runs (reads only)"
    )
    trace.add_argument(
        "product", nargs="?", help="product path relative to the workspace or absolute"
    )
    trace.add_argument("--run", help="print the provenance tree of this run id or alias")
    for parser in (show, log, trace):
        parser.add_argument(
            "--workspace", default=".", help="workspace root (default: current directory)"
        )
        parser.add_argument("--runs", help="another run manifest in the workspace root")
        output = parser.add_mutually_exclusive_group()
        output.add_argument("--json", action="store_true", help="print a JSON document of the rows")
        output.add_argument("--csv", action="store_true", help="print CSV; nested cells are JSON")


def _aliases(ledger: Ledger) -> dict[str, tuple[str, str]]:
    planned = planned_from_plan_files(ledger.root)
    for row in ledger.points():
        planned.setdefault(str(row["sim"]), [])
    return {
        alias: (sim, point)
        for alias, sim, point in alias_lines(_json(ledger.manifest, []), planned)
    }


def _resolve(ledger: Ledger, target: str) -> str:
    pair = _aliases(ledger).get(target)
    if pair is not None:
        matches = [row for row in ledger.points(sims=[pair[0]]) if row["point"] == pair[1]]
        if matches and matches[0]["run_id"]:
            return str(matches[0]["run_id"])
    if ledger.card(target) is not None:
        return target
    raise LookupError(f"run (CLI: --run): {target!r} names no effective recorded point")


def _with_aliases(ledger: Ledger, value: Any) -> Any:
    aliases = {pair: alias for alias, pair in _aliases(ledger).items()}
    return _annotate(value, aliases)


def _annotate(value: Any, aliases: dict[tuple[str, str], str]) -> Any:
    if isinstance(value, list):
        return [_annotate(item, aliases) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _annotate(item, aliases) for key, item in value.items()}
    run_id = value.get("run_id")
    if isinstance(run_id, str):
        parts = run_id.split("/")
        sim = next((p[4:] for p in parts if p.startswith("sim_")), "")
        result["run_id_alias"] = aliases.get((sim, parts[-1]))
    return result


def _show(ledger: Ledger, args: argparse.Namespace) -> list[dict[str, Any]]:
    target = args.target
    if args.point:
        target = (
            f"{target}_{args.point}"
            if args.point.isdigit()
            else next(
                (
                    str(row["run_id"])
                    for row in ledger.points(sims=[target])
                    if row["point"] == args.point
                ),
                "",
            )
        )
    elif not ledger.unmatched([target]):
        points = ledger.points(sims=[target])
        cards = [
            _card(ledger, str(row["run_id"]))
            for row in points
            if str(row["status"]).startswith("FAILED")
        ]
        return [{"points": points, "failed": cards}]
    card = _card(ledger, _resolve(ledger, target))
    return [card] if card else []


def _log(ledger: Ledger, args: argparse.Namespace) -> list[dict[str, Any]]:
    sims = listed_sims(args.sims) if args.sims else []
    if args.storage and args.open_only:
        raise ValueError("open_only (CLI: --open) applies to activity stages, not storage calls")
    if args.post:
        if any((args.run, args.stage, args.since, args.problems, args.open_only)):
            raise ValueError("post (CLI: --post) combines only with sims (CLI: --sims)")
        return _post_groups(ledger, args.post, sims=sims)
    run = args.run
    if run and "/" not in run:
        run = _resolve(ledger, run)
    rows = _storage(ledger) if args.storage else _activity(ledger)
    return _select_logs(
        rows,
        sims=sims,
        run=run,
        stage=args.stage,
        since=args.since,
        problems=args.problems,
        open_only=args.open_only,
    )


def _trace_rows(ledger: Ledger, args: argparse.Namespace) -> list[dict[str, Any]]:
    if bool(args.product) == bool(args.run):
        raise ValueError("product (CLI: product) needs a path or run (CLI: --run), exactly one")
    if args.run:
        return [_trace_run(ledger, _resolve(ledger, args.run))]
    rows = _trace(ledger, args.product)
    if not rows:
        raise LookupError(
            f"product (CLI: product): {args.product!r} is not named in the products index"
        )
    return rows


def _render(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    ledger: Ledger,
    emit: Callable[[str], None],
) -> None:
    if args.json:
        emit(
            json.dumps(
                {"schema": "pyfs-query/1", "workspace": str(ledger.root), "rows": rows}, indent=2
            )
            + "\n"
        )
    elif args.csv:
        columns = list(dict.fromkeys(key for row in rows for key in row))
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {
                key: json.dumps(value) if isinstance(value, dict | list) else value
                for key, value in row.items()
            }
            for row in rows
        )
        emit(buffer.getvalue())
    else:
        for row in rows:
            _print_row(row)


def _print_row(row: dict[str, Any]) -> None:
    if "points" not in row or "failed" not in row:
        print(_tree(row))
        return
    columns = ("sim", "point", "run_id", "run_id_alias", "status")
    cells = [[str(point.get(key) or "") for key in columns] for point in row["points"]]
    for line in table([["SIM", "POINT", "RUN ID", "ALIAS", "STATUS"], *cells], indent=""):
        print(line)
    for card in row["failed"]:
        print(_tree(card))


def _tree(value: Any, indent: str = "") -> str:
    if isinstance(value, dict):
        return "\n".join(
            f"{indent}{key}:\n{_tree(item, indent + '  ')}" for key, item in value.items()
        )
    if isinstance(value, list):
        return "\n".join(_tree(item, indent) for item in value) or f"{indent}[]"
    return f"{indent}{value}"


def _run_point_query(args: argparse.Namespace, emit: Callable[[str], None]) -> int:
    try:
        ledger = read_ledger(args.workspace, runs=args.runs)
        for item in ledger.unreadable:
            print(
                f"{ledger.manifest.name} row {item['position']} (run {item['run_id']}) "
                f"cannot be read: {item['error']}; the other rows are shown",
                file=sys.stderr,
            )
        commands = {"show": _show, "log": _log, "trace": _trace_rows}
        if args.subcommand == "status":
            rows = _additional(ledger)
        else:
            rows = commands[args.subcommand](ledger, args)
            if args.subcommand != "log":
                rows = _with_aliases(ledger, rows)
        _render(rows, args, ledger, emit)
        return 0
    except LookupError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (PyflightstreamError, ValueError, OSError, BadZipFile) as error:
        print(str(error), file=sys.stderr)
        return 2
