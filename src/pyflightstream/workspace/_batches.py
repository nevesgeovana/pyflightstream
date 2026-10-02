"""The batch layout, the grouping receipt and the job entry of a grouped run.

Pipeline role: the workspace-layer home of what a grouped run (``run --batch N``
and ``run --polar-sweep``, 0.35.0) writes and reads back. It names the folders
a batch lives in (``sims/batch/<matrix>_b<ID>``), numbers them, and holds the
receipt the plan writes under the ``grouping`` key of ``plan.json`` and the
entry every point of a grouped job carries in ``RunRecord.submission["job"]``.
It launches nothing: the planner, the runner and the collector in ``run`` build
on these names, and ``workspace.storage`` may read the layout without importing
``run``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from pyflightstream.cases.workflows._vocabulary import BATCH_DIR, BATCH_STEM_PREFIX

if TYPE_CHECKING:
    from pyflightstream.workspace import RunRecord

GROUPING_SCHEMA = "pyfs-grouping/1"
"""The schema name of the ``grouping`` block of ``plan.json``."""

_BATCH_FOLDER = re.compile(r"^(?P<matrix>.+)_b(?P<id>\d+)$")


def batch_label(matrix_stem: str, batch_id: int) -> str:
    """Return the label of a batch, ``<matrix>_b<ID>``.

    Parameters
    ----------
    matrix_stem : str
        The matrix file name without extension.
    batch_id : int
        The batch number, from 1.

    Returns
    -------
    str
        The label, which names the batch folder.
    """
    return f"{matrix_stem}_b{batch_id}"


def batch_dir(root: Path, matrix_stem: str, batch_id: int) -> Path:
    """Return the folder of one batch, ``<root>/sims/batch/<matrix>_b<ID>``.

    Parameters
    ----------
    root : Path
        The campaign workspace root.
    matrix_stem : str
        The matrix file name without extension.
    batch_id : int
        The batch number, from 1.

    Returns
    -------
    Path
        The batch folder (it may not exist yet).
    """
    return root / "sims" / BATCH_DIR / batch_label(matrix_stem, batch_id)


def batch_script_name(first_sim: str, last_sim: str) -> str:
    """Return the script file name of a batch, ``BATCH-<first>-<last>.txt``.

    Parameters
    ----------
    first_sim : str
        The first simulation id of the batch.
    last_sim : str
        The last simulation id; equal to the first for a batch of one polar.

    Returns
    -------
    str
        The file name.
    """
    return f"{BATCH_STEM_PREFIX}{first_sim}-{last_sim}.txt"


def batch_dirs(root: Path) -> list[Path]:
    """Return every ``sims/batch/*_b<int>`` folder of a workspace, sorted.

    Parameters
    ----------
    root : Path
        The campaign workspace root.

    Returns
    -------
    list of Path
        The batch folders; empty when the workspace has none.
    """
    base = root / "sims" / BATCH_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and _BATCH_FOLDER.match(p.name))


def next_batch_id(root: Path, matrix_stem: str) -> int:
    """Return the next free batch number of one matrix.

    Parameters
    ----------
    root : Path
        The campaign workspace root.
    matrix_stem : str
        The matrix file name without extension; batches of another matrix do
        not count.

    Returns
    -------
    int
        One more than the largest existing ID of the matrix, else 1.
    """
    largest = 0
    for folder in batch_dirs(root):
        found = _BATCH_FOLDER.match(folder.name)
        if found is not None and found["matrix"] == matrix_stem:
            largest = max(largest, int(found["id"]))
    return largest + 1


def batch_sim_dirs(root: Path) -> dict[str, list[Path]]:
    """Map every simulation id held inside a batch to its folders.

    Parameters
    ----------
    root : Path
        The campaign workspace root.

    Returns
    -------
    dict of str to list of Path
        Simulation id to the ``sims/batch/*/sim_<id>`` folders holding it.
    """
    found: dict[str, list[Path]] = {}
    for folder in batch_dirs(root):
        for sim in sorted(folder.glob("sim_*")):
            if sim.is_dir():
                found.setdefault(sim.name[len("sim_") :], []).append(sim)
    return found


@dataclass(frozen=True)
class GroupedJob:
    """One job of a grouping plan: a batch of polars or one polar sweep.

    Attributes
    ----------
    name : str
        ``BATCH-<first>-<last>`` or ``FULL-POLAR``.
    batch_id : int or None
        The batch number; None for a polar sweep.
    label : str
        ``<matrix>_b<ID>`` for a batch, the simulation id for a polar sweep.
    dir : str
        The job folder, root-relative, with a trailing slash.
    script : str
        The job script, root-relative.
    sims : tuple of str
        The simulation ids the job holds.
    points : tuple of str
        The run ids of its points, in order.
    fs_build : str
        The solver build the job runs on.
    ncpus : int
        The processor count.
    estimate_s : float or None
        The estimated run time in seconds.
    estimate_basis : str
        How the estimate was made.
    fallback_points : tuple of str
        Points estimated by a fallback.
    unestimated_points : tuple of str
        Points with no estimate.
    overheads_s : dict of str to float
        The overheads added, by name.
    factor : float
        The safety factor applied.
    margin_s : float
        The margin added, in seconds.
    walltime_s : int or None
        The walltime of the job in seconds.
    walltime_written : str
        The walltime as written in the scheduler or clock text.
    walltime_source : str
        ``BEST``, ``matrix``, ``max_walltime`` or ``none``.
    fits : bool
        Whether the job fits the profile's maximum walltime.
    shortfall_s : float or None
        By how much it does not fit, when it does not.
    """

    name: str
    batch_id: int | None
    label: str
    dir: str
    script: str
    sims: tuple[str, ...]
    points: tuple[str, ...]
    fs_build: str
    ncpus: int
    estimate_s: float | None
    estimate_basis: str
    fallback_points: tuple[str, ...]
    unestimated_points: tuple[str, ...]
    overheads_s: dict[str, float]
    factor: float
    margin_s: float
    walltime_s: int | None
    walltime_written: str
    walltime_source: str
    fits: bool
    shortfall_s: float | None

    def to_json(self) -> dict[str, object]:
        """Return the job as the plain mapping the receipt stores."""
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> GroupedJob:
        """Rebuild a job from :meth:`to_json`'s mapping."""
        data = dict(payload)
        for key in ("sims", "points", "fallback_points", "unestimated_points"):
            data[key] = tuple(data[key])
        return cls(**data)


@dataclass(frozen=True)
class GroupingReceipt:
    """The ``grouping`` block of ``plan.json`` (schema ``pyfs-grouping/1``).

    Attributes
    ----------
    schema : str
        Always ``pyfs-grouping/1``.
    mode : str
        ``batch`` or ``polar_sweep``.
    requested : int or None
        The N of ``--batch N``; None for a polar sweep.
    selection : dict
        The ``sims`` and ``points`` selections the plan was made with.
    jobs : tuple of GroupedJob
        The jobs, stored under the key ``batches``.
    left_out : tuple of dict
        Simulations left out, each with a reason.
    total_estimate_s : float or None
        The sum of the job estimates.
    longest_estimate_s : float or None
        The longest job estimate.
    max_walltime_s : int or None
        The profile's maximum walltime.
    warnings : tuple of str
        The warnings the plan raised.
    """

    schema: str
    mode: str
    requested: int | None
    selection: dict[str, Any]
    jobs: tuple[GroupedJob, ...]
    left_out: tuple[dict[str, Any], ...]
    total_estimate_s: float | None
    longest_estimate_s: float | None
    max_walltime_s: int | None
    warnings: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        """Return the receipt as the mapping stored under ``grouping``."""
        return {
            "schema": self.schema,
            "mode": self.mode,
            "requested": self.requested,
            "selection": self.selection,
            "batch_count": len(self.jobs),
            "batches": [job.to_json() for job in self.jobs],
            "left_out": list(self.left_out),
            "total_estimate_s": self.total_estimate_s,
            "longest_estimate_s": self.longest_estimate_s,
            "max_walltime_s": self.max_walltime_s,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> GroupingReceipt:
        """Rebuild a receipt from :meth:`to_json`'s mapping.

        Parameters
        ----------
        payload : Mapping
            The ``grouping`` mapping of a ``plan.json``.

        Returns
        -------
        GroupingReceipt
            The receipt.

        Raises
        ------
        ValueError
            When the payload names another schema.
        """
        if payload.get("schema") != GROUPING_SCHEMA:
            raise ValueError(
                f"the grouping block names schema {payload.get('schema')!r}, "
                f"not {GROUPING_SCHEMA!r}"
            )
        return cls(
            schema=payload["schema"],
            mode=payload["mode"],
            requested=payload["requested"],
            selection=dict(payload["selection"]),
            jobs=tuple(GroupedJob.from_json(job) for job in payload["batches"]),
            left_out=tuple(dict(item) for item in payload["left_out"]),
            total_estimate_s=payload["total_estimate_s"],
            longest_estimate_s=payload["longest_estimate_s"],
            max_walltime_s=payload["max_walltime_s"],
            warnings=tuple(payload["warnings"]),
        )


class JobEntry(TypedDict):
    """The ``submission["job"]`` entry every point of a grouped job carries."""

    kind: Literal["batch", "polar_sweep"]
    name: str
    batch_id: int | None
    label: str
    dir: str
    script: str
    root: str
    executor: Literal["local", "submitting"]
    values: dict[str, str]
    order: int
    points: int
    receipt_sha256: str


def job_of(record: RunRecord) -> JobEntry | None:
    """Return the job entry of a record, or None for a point run alone.

    Parameters
    ----------
    record : RunRecord
        Any run record.

    Returns
    -------
    JobEntry or None
        ``record.submission["job"]`` when present.
    """
    submission = record.submission
    if not submission or not isinstance(submission.get("job"), dict):
        return None
    return cast("JobEntry", submission["job"])
