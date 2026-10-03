"""The dispatch and the shared helpers of the grouped run modes.

Pipeline role: ``run --batch N`` and ``run --polar-sweep`` (0.35.0) run several
points as one solver job. The command line chooses between the per-point
functions it always called and the grouped ones through :func:`runner_for` and
:func:`planner_for`; the grouped functions are imported only when a grouped mode
is asked, so the default per-point mode never reaches them. The helpers here
are the ones the grouped planner, runner and collector share: the refusal of
options a grouped run does not take, the case a job builds, and the gate that
decides whether a grouped run may proceed on the receipt it has.
"""

from __future__ import annotations

import argparse
import functools
import importlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pyflightstream.cases import SimCase
from pyflightstream.cases.workflows import WALLTIME_VARIABLE
from pyflightstream.run._plan import plan_receipt_error
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace._batches import GroupedJob, GroupingReceipt


def _mode_of(args: argparse.Namespace) -> str | None:
    """Return ``polar_sweep``, ``batch`` or None from the parsed options."""
    if args.polar_sweep:
        return "polar_sweep"
    return "batch" if args.batch is not None else None


def runner_for(args: argparse.Namespace, default: Callable[..., Any]) -> Callable[..., Any]:
    """Return the function ``run`` calls to run the matrix.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed ``run`` options (``polar_sweep`` and ``batch``).
    default : callable
        The per-point function, returned unchanged when no grouped mode is asked.

    Returns
    -------
    callable
        ``default``, or ``run_grouped_matrix`` bound to the asked mode.
    """
    mode = _mode_of(args)
    if mode is None:
        return default
    grouped = importlib.import_module("pyflightstream.run._batch_run").run_grouped_matrix
    return functools.partial(grouped, mode=mode, batch=args.batch)


def planner_for(args: argparse.Namespace, default: Callable[..., Any]) -> Callable[..., Any]:
    """Return the function ``plan`` calls to plan the matrix.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed ``plan`` options (``polar_sweep`` and ``batch``).
    default : callable
        The per-point function, returned unchanged when no grouped mode is asked.

    Returns
    -------
    callable
        ``default``, or ``plan_grouped_matrix`` bound to the asked mode.
    """
    mode = _mode_of(args)
    if mode is None:
        return default
    grouped = importlib.import_module("pyflightstream.run._batch_plan").plan_grouped_matrix
    return functools.partial(grouped, mode=mode, batch=args.batch)


def refuse_grouped_options(
    *,
    force_rerun: Sequence[str] | None,
    force_rerun_all: bool,
    sweep_csv: str | Path | None,
) -> str | None:
    """Say why a grouped run may not take these options, or return None.

    Parameters
    ----------
    force_rerun : sequence of str, optional
        The ``--force-rerun`` selection.
    force_rerun_all : bool
        The ``--force-rerun-all`` switch.
    sweep_csv : str or Path, optional
        The ``--sweep-csv`` path.

    Returns
    -------
    str or None
        The refusal sentence, or None when none of the three is given.
    """
    given = [
        flag
        for flag, present in (
            ("--force-rerun", bool(force_rerun)),
            ("--force-rerun-all", force_rerun_all),
            ("--sweep-csv", sweep_csv is not None),
        )
        if present
    ]
    if not given:
        return None
    return (
        f"a grouped run (--batch, --polar-sweep) does not take {', '.join(given)} "
        "in this release; run the points one by one for that."
    )


def grouped_case(case: SimCase) -> SimCase:
    """Return the case a grouped job builds: its WALLTIME variable removed.

    The job's clock replaces the point's, so the per-point script registers no
    clock of its own. Nothing else of the case changes.

    Parameters
    ----------
    case : SimCase
        The point's case.

    Returns
    -------
    SimCase
        A copy without the WALLTIME variable.
    """
    variables = {k: v for k, v in case.variables.items() if k != WALLTIME_VARIABLE}
    return case.model_copy(update={"variables": variables})


def read_receipt(workspace: CampaignWorkspace, matrix_stem: str) -> GroupingReceipt | None:
    """Return the grouping receipt of a matrix's plan, or None.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The campaign workspace.
    matrix_stem : str
        The matrix file name without extension.

    Returns
    -------
    GroupingReceipt or None
        The ``grouping`` block of ``plan.json``; None when the plan has none
        or cannot be read.
    """
    plan_file = workspace.plan_dir(matrix_stem) / "plan.json"
    try:
        block = json.loads(plan_file.read_text(encoding="utf-8")).get("grouping")
    except (OSError, ValueError, AttributeError):
        return None
    return None if block is None else GroupingReceipt.from_json(block)


def _job_ran(root: Path, job: GroupedJob, *, mode: str) -> bool:
    """Whether a receipt's job already ran in its folder.

    A polar sweep's job folder is its sim folder, which the plan itself
    allocates (empty ``inputs/``, ``scripts/``, ``datapoints/``), so only its
    job script says the job ran; a batch folder is the job's own, so any file
    in it does.
    """
    if mode == "polar_sweep":
        return (root / job.script).is_file()
    folder = root / job.dir
    return folder.is_dir() and any(p.is_file() for p in folder.rglob("*"))


def batch_receipt_error(
    workspace: CampaignWorkspace,
    matrix_path: str | Path | None,
    matrix_stem: str,
    *,
    mode: str,
    batch: int | None,
    sims: Sequence[str] | None,
    points: Sequence[str] | None,
) -> str | None:
    """Say why a grouped run may not run on the receipt it has, or return None.

    The plain plan gate answers first (the matrix digest has one
    implementation); then the grouping block must exist, name this mode, this
    N and this selection, and none of its job folders may already hold files.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The campaign workspace.
    matrix_path : str or Path, optional
        The matrix file the run reads.
    matrix_stem : str
        The matrix file name without extension.
    mode : str
        ``batch`` or ``polar_sweep``.
    batch : int, optional
        The N of ``--batch N``.
    sims : sequence of str, optional
        The ``--sims`` selection.
    points : sequence of str, optional
        The ``--points`` selection.

    Returns
    -------
    str or None
        The refusal sentence, or None when the run may proceed.
    """
    stale = plan_receipt_error(workspace, matrix_path, matrix_stem)
    if stale is not None:
        return stale
    receipt = read_receipt(workspace, matrix_stem)
    if receipt is None:
        return "the plan holds no grouping: plan it again with the same --batch or --polar-sweep."
    if receipt.mode != mode:
        return f"the plan was made for mode {receipt.mode}, not {mode}: plan it again."
    if receipt.requested != batch:
        return f"the plan was made for --batch {receipt.requested}, not {batch}: plan it again."
    selection = {"sims": list(sims) if sims else None, "points": list(points) if points else None}
    if receipt.selection != selection:
        return "the plan was made for another --sims/--points selection: plan it again."
    for job in receipt.jobs:
        if _job_ran(workspace.root, job, mode=mode):
            return (
                f"the job folder {job.dir} already holds files: this plan's jobs ran; plan again."
            )
    return None
