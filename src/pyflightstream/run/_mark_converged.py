"""mark-converged: a person's verdict of CONVERGED, its reason, and runs.json archived (FR-414).

A person reading a point's products can know that it converged where the
package could not say so (a log deleted, a march that reached its last step),
and recording that by editing ``runs.json`` by hand loses the status it had.
``mark-converged`` records the verdict in the package's
own form, the twin of ``mark-failed`` (FR-309): under the manifest lock, the
previous ``runs.json`` copied to ``archive/`` first, each record keeping under
``marked`` the status it had, the time, the reason and the verdict given.

What a verdict needs is the outputs it is about, so four points are refused,
each named with its reason and the remedy, and nothing is written while any is
named: a point still SUBMITTED, a point whose loads export is not on disk, a
simulation deleted by ``delete-sims``, and a point marked failed. A point
already CONVERGED is listed and left alone. Every other status, the failures
included, takes the person's verdict.

This module also registers the two marking commands' parsers, which share
their options, and prints the command's lines.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import classify_outputs
from pyflightstream.run._assessment import worse_of
from pyflightstream.run._record_files import _now_stamp, _relative, manifest_lock
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace._verdicts import marked_units
from pyflightstream.workspace.naming import ARCHIVE_DIR, DEFAULT_MANIFEST, RunsManifestError

__all__ = [
    "add_mark_converged_parser",
    "add_mark_parsers",
    "cmd_mark_converged",
    "keep_verdict",
    "mark_converged",
    "person_verdicts",
]

#: The two shapes ``--sims`` takes in mark-converged, mark-failed and rebuild.
SIMS_SHAPES = "simulation ids: 2006 2007 or 2006,2007"

#: What to do when a named simulation or point has no record.
_REMEDY = "check the ids against runs.json, or rebuild it with pyfs-matrix rebuild"

#: The verdict this command gives, written into ``marked``.
_VERDICT = RunStatus.CONVERGED


def _listed(values: Sequence[str] | None) -> list[str]:
    """Read ids given as words, commas or both: ``2006 2007`` or ``2006,2007``."""
    words = [part.strip().strip("[]") for value in values or [] for part in str(value).split(",")]
    return list(dict.fromkeys(word for word in words if word))


def _units(row: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Return a record's points as (point name, run id, the dict holding its status).

    A steady job is one record over several points (``points_ran``); each
    point is its own unit, its entry holding its status.
    """
    entries = row.get("points_ran") or []
    if not entries:
        return [(str(row.get("point_name") or ""), str(row["run_id"]), row)]
    prefix = str(row["run_id"]).rsplit("/", 1)[0]
    return [(str(entry.get("tag")), f"{prefix}/{entry.get('tag')}", entry) for entry in entries]


def _loads_on_disk(workspace: CampaignWorkspace, row: Mapping[str, Any], unit: Mapping) -> bool:
    """Say whether the point's loads export is in its simulation folder."""
    outputs = [str(name) for name in unit.get("outputs") or row.get("outputs") or []]
    name = classify_outputs(outputs).get("loads")
    if not name:
        return False
    return (workspace.sim_dir(str(row.get("sim_id"))) / name).is_file()


def _refusal(workspace: CampaignWorkspace, row: Mapping, unit: Mapping) -> str | None:
    """Why one point cannot take a verdict of CONVERGED, with the remedy; None when it can."""
    status = unit.get("status")
    if status == RunStatus.SUBMITTED.value:
        return (
            "still SUBMITTED: its job's outputs were never collected; collect it first "
            "(pyfs-matrix collect), then read it and mark it"
        )
    if status == RunStatus.FAILED_MARKED.value:
        return (
            "marked failed by a person (mark-failed); one verdict is not laid over another: "
            "restore runs.json from before that mark (pyfs-matrix restore runs) first"
        )
    if not _loads_on_disk(workspace, row, unit):
        return (
            "its loads export is not on disk, and a verdict is about the outputs it reads; "
            "restore the simulation folder, or collect the point again"
        )
    return None


def _plan(
    workspace: CampaignWorkspace, rows: list[dict[str, Any]], ids: list[str], points: list[str]
) -> tuple[list[tuple[dict, dict, str, str]], list[str], dict[str, str]]:
    """Return the points to mark, those already CONVERGED, and those refused with why."""
    live = [row for row in rows if row.get("deleted_sim") is None]
    deleted = {str(row["deleted_sim"]) for row in rows if row.get("deleted_sim") is not None}
    known = {str(row.get("sim_id")) for row in live}
    refused = {
        f"sim_{sim}": "deleted by delete-sims, so no record of it is left to mark; run it again"
        for sim in ids
        if sim in deleted and sim not in known
    }
    unknown = [sim for sim in ids if sim not in known and f"sim_{sim}" not in refused]
    if unknown:
        raise RunsManifestError(
            f"no record in {DEFAULT_MANIFEST} for simulation(s) {', '.join(unknown)}; nothing "
            f"was marked; {_REMEDY}"
        )
    todo: list[tuple[dict, dict, str, str]] = []
    already: list[str] = []
    held: list[str] = []
    for row in live:
        if str(row.get("sim_id")) not in ids:
            continue
        for name, run_id, unit in _units(row):
            held.append(name)
            if points and name not in points:
                continue
            why = _refusal(workspace, row, unit)
            if why is not None:
                refused[run_id] = why
            elif unit.get("status") == _VERDICT.value:
                already.append(run_id)
            else:
                todo.append((row, unit, run_id, str(unit.get("status"))))
    missing = [point for point in points if point not in held]
    if missing:
        raise RunsManifestError(
            f"no record of simulation(s) {', '.join(ids)} names the point(s) "
            f"{', '.join(missing)}; nothing was marked; their records hold "
            f"{', '.join(dict.fromkeys(held)) or 'no point'}; {_REMEDY}"
        )
    return todo, already, refused


def _checked_plan(workspace, rows, ids, wanted, *, reason, apply):
    """Plan against the rows actually read, refusing apply before any file is written."""
    todo, already, refused = _plan(workspace, rows, ids, wanted)
    result: dict[str, Any] = {
        "applied": False,
        "marked": [
            {"sim_id": str(row.get("sim_id")), "run_id": run_id, "from": was}
            for row, _unit, run_id, was in todo
        ],
        "already": already,
        "refused": refused,
        "reason": reason,
    }
    if refused and apply:
        raise RunsManifestError(
            "mark-converged refused, nothing was written:\n"
            + "\n".join(f"  {who}: {why}" for who, why in refused.items())
        )
    return todo, result


def mark_converged(
    root: str | Path,
    sims: Sequence[str],
    *,
    reason: str,
    points: Sequence[str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Record a person's verdict of CONVERGED on the named points (FR-414).

    Parameters
    ----------
    root : str or Path
        The workspace root.
    sims : sequence of str
        Simulation ids; each may hold several, comma separated.
    reason : str
        Why the person judges them converged, recorded as given; required.
    points : sequence of str, optional
        Point names; only the records of these points of the named simulations
        are marked. Without it every point of them is.
    apply : bool, default False
        Write. Without it nothing changes and the result says what would.

    Returns
    -------
    dict
        ``applied``, ``marked`` (per point: ``sim_id``, ``run_id``, ``from``),
        ``already`` (the run ids already CONVERGED, left as they are),
        ``refused`` (by run id or ``sim_<id>``, the reason and remedy),
        ``reason`` and, when applied, ``runs_archived_as``.

    Raises
    ------
    RunsManifestError
        No reason, no simulation named, no ``runs.json``, a simulation or a
        point no record names; applying while any point is refused, naming
        each, with nothing written.
    """
    if not str(reason or "").strip():
        raise RunsManifestError(
            "mark-converged records a person's verdict and needs its reason (CLI: --reason)"
        )
    base = Path(root)
    manifest = base / DEFAULT_MANIFEST
    ids, wanted = _listed(sims), _listed(points)
    if not ids:
        raise RunsManifestError(
            "name the simulations to mark in sims (CLI: --sims), e.g. 2006 2007"
        )
    if not manifest.is_file():
        raise RunsManifestError(f"{manifest} does not exist, so no run can be marked")
    workspace = CampaignWorkspace(base)
    todo, result = _checked_plan(
        workspace, _read(manifest), ids, wanted, reason=reason, apply=apply
    )
    if not apply or not todo:
        return result
    at = dt.datetime.now(dt.UTC).isoformat()
    with manifest_lock(base):
        rows = _read(manifest)
        todo, result = _checked_plan(workspace, rows, ids, wanted, reason=reason, apply=True)
        if not todo:
            return result
        archived = base / ARCHIVE_DIR / f"{manifest.stem}-{_now_stamp()}.json"
        archived.parent.mkdir(exist_ok=True)
        shutil.copy2(manifest, archived)
        for row, unit, _run_id, was in todo:
            unit["marked"] = {"from": was, "at": at, "reason": reason, "verdict": _VERDICT.value}
            unit["status"] = _VERDICT.value
            if unit is not row:
                row["status"] = _worst(row)
        workspace._replace_manifest(rows)
    result.update(applied=True, runs_archived_as=_relative(base, archived))
    return result


def person_verdicts(manifest: Path) -> dict[str, dict[str, Any]]:
    """Return, by run id, the rows of a manifest that carry a person's verdict (``marked``).

    Empty when the manifest is absent or unreadable: a rebuild of a lost
    ``runs.json`` has no verdict to keep.
    """
    try:
        rows = _read(manifest)
    except (OSError, ValueError, RunsManifestError):
        return {}
    return {
        str(row["run_id"]): row
        for row in rows
        if isinstance(row, dict) and marked_units(row) and row.get("run_id")
    }


def keep_verdict(record: dict[str, Any], row: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return ``record`` keeping the person's verdict ``row`` carries (FR-414 R4).

    A writer that makes a record again (the rebuild) never replaces a person's
    verdict by a computed status in silence: the record keeps ``marked`` and
    the status it gave, and says which status the files supported.
    """
    if row is None:
        return record
    units = marked_units(row)
    if any(key for key in units):
        points = record.get("points_ran") or []
        missing = set(units) - {"", *(str(point.get("tag")) for point in points)}
        if missing:
            raise RunsManifestError(
                f"rebuild would lose marked point(s) {', '.join(sorted(missing))}; "
                "restore the point declarations before rebuilding"
            )
        record = {
            **record,
            "points_ran": [
                keep_verdict(point, units.get(str(point.get("tag")))) for point in points
            ],
        }
        record["status"] = _worst(record)
    if not row.get("marked"):
        return record
    note = (
        f"a person's verdict is kept: {row.get('status')} by mark ({row['marked'].get('at')}); "
        f"the files on disk support {record.get('status')}"
    )
    warnings = [*list(record.get("warnings") or []), note]
    return {**record, "marked": row["marked"], "status": row.get("status"), "warnings": warnings}


def _worst(row: Mapping[str, Any]) -> str:
    """Return a steady job's status after a mark: its worst point's, by the one order."""
    worst = RunStatus.CONVERGED
    for entry in row.get("points_ran") or []:
        worst = worse_of(worst, RunStatus(entry["status"]))
    return worst.value


def _read(manifest: Path) -> list[dict[str, Any]]:
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RunsManifestError(f"{manifest} is not a list of run records")
    return rows


def add_mark_parsers(subparsers: Any, *, workspace_help: str, apply_help: str) -> None:
    """Register ``mark-failed`` (0.33.0, FR-309) among the records commands."""
    mark = subparsers.add_parser(
        "mark-failed",
        help="mark every run record of the named simulations FAILED_MARKED, whatever it "
        "ended in (preview unless --apply)",
        description=(
            "A run can end CONVERGED and be found wrong later. Its records become "
            "FAILED_MARKED, which the post, the re-run and delete-sims treat as any "
            "failure, and each keeps the status it had, when and why under 'marked'; "
            "runs.json is copied to archive/ first (FR-309)."
        ),
    )
    mark.add_argument(
        "--sims",
        required=True,
        nargs="+",
        metavar="ID",
        help=SIMS_SHAPES + "; a run id alias (2006_3) marks that point's record alone",
    )
    mark.add_argument("--reason", default=None, help="why, recorded as given")
    mark.add_argument("--workspace", default=".", help=workspace_help)
    mark.add_argument("--apply", action="store_true", help=apply_help)


def add_mark_converged_parser(subparsers: Any) -> None:
    """Register ``mark-converged`` (0.37.0, FR-414), appended last as every later command is."""
    workspace_help = "the workspace root carrying runs.json (default: the current directory)"
    apply_help = "change files; without it the command previews and changes nothing"
    converged = subparsers.add_parser(
        "mark-converged",
        help="record your verdict that the named points CONVERGED, with its reason "
        "(preview unless --apply)",
        description=(
            "You know from your own reading that points converged where the package could "
            "not say so. Their records become CONVERGED, each keeping under 'marked' the "
            "status it had, when, your reason and the verdict; runs.json is copied to "
            "archive/ first. A point SUBMITTED, without its loads export, deleted, or "
            "marked failed is refused by name and nothing is written (FR-414)."
        ),
    )
    converged.add_argument(
        "--sims",
        required=True,
        nargs="+",
        metavar="ID",
        help=SIMS_SHAPES + "; to mark some of their points, name them with --points "
        "(a run id alias such as 2006_3 is not read here)",
    )
    converged.add_argument(
        "--points",
        nargs="+",
        default=None,
        metavar="NAME",
        help="the point names to mark; every point of the simulations without it",
    )
    converged.add_argument("--reason", required=True, help="why, recorded as given")
    converged.add_argument("--workspace", default=".", help=workspace_help)
    converged.add_argument("--apply", action="store_true", help=apply_help)


def cmd_mark_converged(args: argparse.Namespace) -> int:
    """Run ``pyfs-matrix mark-converged`` and print what it did, or would do (FR-414)."""
    try:
        entry = mark_converged(
            args.workspace, args.sims, reason=args.reason, points=args.points, apply=args.apply
        )
    except (PyflightstreamError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    verb = "marked" if entry["applied"] else "would mark"
    for item in entry["marked"]:
        print(f"{verb} CONVERGED: sim {item['sim_id']} {item['run_id']} (was {item['from']})")
    for run_id in entry["already"]:
        print(f"already CONVERGED, left as it is: {run_id}")
    for who, why in entry["refused"].items():
        print(f"refused: {who}: {why}")
    if entry["applied"]:
        print(f"runs.json as it was: {entry['runs_archived_as']}")
    elif entry["marked"] or entry["refused"]:
        print("preview: nothing was written; run again with --apply")
    return 0
