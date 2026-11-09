"""search-log-batch: write the log of a batch point from the job's master log.

A point of a grouped job that ended with all its outputs but neither its log nor
its cumulative log is SUBMITTED, and collect waits for it. Its log is a segment
of the job's master log: the job's ``<job stem>.job-log.txt``, the scheduler's
``FTS<first sim>.l*``, or the only ``FTS*.l*`` in the job's folder. This command
cuts that segment with the code collect uses, so the point's log has the bytes
collect would have written, and leaves ``runs.json`` alone: collect then judges
the point from its log.

Like the other commands that change files it previews unless ``--apply`` is
given. A profile that names a ``native_log`` is read first. Several candidate
master logs, no master log, or a master log with fewer points than the job
are named and nothing is written for that point; ``--master`` chooses the file.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases.workflows._vocabulary import CUMULATIVE_LOG_SUFFIX, JOB_LOG_SUFFIX
from pyflightstream.results.log import split_job_log
from pyflightstream.run._batch_collect import (
    _LOG_SUFFIX,
    _Job,
    _job_dir,
    _matches,
    _opening_orders,
    _point,
    _write_log,
    job_of,
)
from pyflightstream.run._ids import _add_sim_ids
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace.hpc import resolve_hpc_profile
from pyflightstream.workspace.ledger import SIMS_IDS_HELP
from pyflightstream.workspace.manifest import RunRecord

__all__ = ["add_search_log_batch_parser", "cmd_search_log_batch", "search_log_batch"]

#: The scheduler's log pattern when no profile names one, then the only one of its kind.
_SCHEDULER_PATTERNS = ("FTS{first}.l*", "FTS*.l*")


def _master_log(
    folder: Path,
    entry: Any,
    members: Sequence[RunRecord],
    chosen: str | None,
    native: str | None,
) -> tuple[Path | None, str]:
    """Return the job's master log, or None and the reason; never a guess between files."""
    if chosen:
        path = folder / chosen
        return (path, "") if path.is_file() else (None, f"no master log at {path}")
    if native:
        found = _matches(folder, native, entry)
        if len(found) == 1:
            return found[0], ""
        if found:
            return None, _several(folder, found)
    exported = folder / (PurePosixPath(entry["script"]).stem + JOB_LOG_SUFFIX)
    if exported.is_file():
        return exported, ""
    first = (entry.get("values") or {}).get("sim") or members[0].sim_id
    for pattern in _SCHEDULER_PATTERNS:
        found = sorted(path for path in folder.glob(pattern.format(first=first)) if path.is_file())
        if len(found) == 1:
            return found[0], ""
        if found:
            return None, _several(folder, found)
    return None, f"no master log in {folder} ({exported.name} or FTS*.l*)"


def _several(folder: Path, found: Sequence[Path]) -> str:
    names = ", ".join(path.name for path in found)
    return f"several master logs in {folder} ({names}): choose one with --master"


def search_log_batch(
    root: str | Path,
    *,
    sims: Sequence[str] | None = None,
    apply: bool = False,
    master: str | None = None,
) -> dict[str, list[str]]:
    """Write the missing logs of the SUBMITTED points of the grouped jobs of a workspace.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    sims : sequence of str, optional
        Only the points of these simulations; every simulation without it.
    apply : bool, default False
        Write. Without it nothing changes and the result says what would be written.
    master : str, optional
        The master log's name in the job's folder, instead of the search order.

    Returns
    -------
    dict
        The run ids per outcome label (``written`` or ``would write``, or the
        reason a point was left alone, which names the file and the remedy).
    """
    workspace = CampaignWorkspace(root)
    native = getattr(resolve_hpc_profile(workspace.inputs_dir), "native_log", None)
    wanted = {str(item) for item in sims} if sims else None
    jobs: dict[tuple[str, str], list[RunRecord]] = defaultdict(list)
    for record in workspace.read_manifest():
        entry = job_of(record)
        if entry is not None:
            jobs[(str(entry["dir"]), str(entry["script"]))].append(record)
    outcome: dict[str, list[str]] = defaultdict(list)
    for members in jobs.values():
        entry = job_of(members[0])
        if entry is None:
            continue
        found, why = _master_log(_job_dir(workspace, entry), entry, members, master, native)
        segments = None
        for record in members:
            job = job_of(record)
            if job is None or (wanted is not None and str(record.sim_id) not in wanted):
                continue
            point = _point(workspace, record, job, in_batch=job["kind"] == "batch")
            if point.log_name is None:
                if record.status is RunStatus.SUBMITTED:
                    outcome["declares no log, left alone"].append(record.run_id)
                continue
            names = [point.log_name, point.log_name[: -len(_LOG_SUFFIX)] + CUMULATIVE_LOG_SUFFIX]
            if any((at / name).exists() for at in (point.work, point.target) for name in names):
                continue
            if record.status is not RunStatus.SUBMITTED:
                outcome[f"already {record.status}, left alone"].append(record.run_id)
                continue
            if found is None:
                outcome[why].append(record.run_id)
                continue
            if segments is None:
                segments = split_job_log(found.read_bytes().decode("utf-8", errors="replace"))
            if job["order"] > len(segments):
                outcome[f"master log {found.name} has only {len(segments)} points"].append(
                    record.run_id
                )
                continue
            if not apply:
                outcome["would write"].append(record.run_id)
                continue
            point.target.mkdir(parents=True, exist_ok=True)
            holder = _Job(
                job=job,
                members=list(members),
                profile=None,
                watch=None,  # type: ignore[arg-type]
                opening=_opening_orders(workspace, job),
            )
            _write_log(point, found, complete=True, start=holder.polar_start(record))
            outcome["written"].append(record.run_id)
    return dict(outcome)


def add_search_log_batch_parser(subparsers: Any) -> None:
    """Register ``search-log-batch``, appended last as every later command is."""
    parser = subparsers.add_parser(
        "search-log-batch",
        help="write the log of a batch point that has its other files, from the job's "
        "master log (preview unless --apply)",
        description=(
            "A point of a batch whose outputs are all there but whose log is not stays "
            "SUBMITTED. Its log is a segment of the job's master log, found as "
            "<job stem>.job-log.txt, the scheduler's FTS<first sim>.l*, or the only "
            "FTS*.l* of the job's folder (a profile's native_log is read first). The "
            "segment is cut as collect cuts it; runs.json is not changed, and "
            "pyfs-matrix collect then judges the point from its log. Several candidate "
            "master logs, none, or too few points are named and nothing is written."
        ),
    )
    _add_sim_ids(parser, help=SIMS_IDS_HELP + "; every simulation without it")
    parser.add_argument(
        "--master",
        default=None,
        metavar="FILE",
        help="the master log's name in the job's folder, instead of the search; use with --sims",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="the workspace root carrying runs.json (default: the current directory)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the logs; without it the command previews and changes nothing",
    )


def cmd_search_log_batch(args: argparse.Namespace) -> int:
    """Run ``pyfs-matrix search-log-batch`` and print what it did, or would do."""
    from pyflightstream.run._alias import listed_ids

    try:
        result = search_log_batch(
            args.workspace,
            sims=listed_ids(args.sims) or None,
            apply=args.apply,
            master=args.master,
        )
    except (PyflightstreamError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if not result:
        print("no SUBMITTED point of a batch is missing its log")
    for label, run_ids in result.items():
        print(f"{label}: {len(run_ids)}")
        for run_id in run_ids:
            print(f"  {run_id}")
    if not args.apply and "would write" in result:
        print("preview only: run again with --apply, then pyfs-matrix collect")
    return 0
