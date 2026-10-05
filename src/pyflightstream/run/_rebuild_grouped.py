"""What a rebuild reads about a grouped run: the batch home and the job a point ran in (FR-412).

A point of a ``--batch`` job runs from ``sims/batch/<matrix>_b<ID>/sim_<id>/``
and its script names its inputs and outputs there (FR-358); collect moves the
simulation home once the job ended (FR-367). The rebuild renders the row as a
point run alone, so until 0.37.0 it compared a script naming
``sims/sim_<id>/`` with one naming the batch folder and refused every grouped
simulation, and it never looked inside a batch folder at all. Here: where a
simulation's folder is now (home, or still in its batch), which batch the
executed script names, the rendered script read at that home, and the job
entry a rebuilt record carries, read off the plan receipt that gated the run
(``post/<stem>/plan.json``, ``grouping``). Nothing here writes.

A ``--polar-sweep`` point runs from its own ``sims/sim_<id>/``, so its script
is the alone script; only the receipt tells its job. A batch point whose
receipt is gone is still rebuilt, naming its batch from its script, without
a job entry; one still in its batch folder is left for ``collect``, which
needs the job entry to move it, and is refused without one.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from pyflightstream.run._batch_exec import receipt_digest
from pyflightstream.workspace._batches import GroupedJob, GroupingReceipt, batch_sim_dirs

__all__ = [
    "GroupedPoint",
    "batch_label",
    "grouped_facts",
    "grouped_point",
    "rendered_at_home",
    "simulation_home",
    "with_job",
]

#: The submission fields a rebuilt grouped record keeps, as the minted row states them.
_DECLARED = ("declared_outputs", "working_dir", "declared_logs")


@dataclass(frozen=True)
class GroupedPoint:
    """What a rebuilt record says of the grouped job one point ran in.

    Attributes
    ----------
    label : str or None
        The batch (``<matrix>_b<ID>``), None for a point that ran from its own
        simulation folder.
    entry : dict or None
        The ``submission["job"]`` entry, from the plan receipt; None when no
        receipt names the point.
    job_dir : Path or None
        The job folder, when it holds the scheduler descriptor.
    descriptor : str or None
        That descriptor's path, spelled from the run's own root.
    in_batch : bool
        The simulation's files are still in its batch folder.
    """

    label: str | None
    entry: dict[str, Any] | None
    job_dir: Path | None
    descriptor: str | None
    in_batch: bool


def simulation_home(base: Path, sim: str, scripts: list[str]) -> Path:
    """Return the folder of ``sim`` holding every one of ``scripts``: home first, then a batch.

    ``sims/sim_<id>/`` when it holds them (a point run alone, a polar sweep, a
    batch moved home), else the batch's copy ``sims/batch/<label>/sim_<id>/``
    that does (a batch not moved yet), else ``sims/sim_<id>/``, whose missing
    script the caller names.
    """
    home = base / "sims" / f"sim_{sim}"
    for folder in [home, *batch_sim_dirs(base).get(sim, [])]:
        if all((folder / script).is_file() for script in scripts):
            return folder
    return home


def batch_label(executed: str, sim: str) -> str | None:
    """Return the batch folder a point's executed script names its simulation in, or None."""
    found = re.search(rf"/sims/batch/([^/\s]+)/sim_{re.escape(sim)}/", executed.replace("\\", "/"))
    return found.group(1) if found else None


def rendered_at_home(rendered: str, shadow: Path, sim: str, label: str | None) -> str:
    """Return the shadow's rendering read at the batch home the point ran from.

    The alone script names ``<shadow>/sims/sim_<id>/``; the batch point's names
    ``<root>/sims/batch/<label>/sim_<id>/``, and nothing else differs (FR-366).
    Both sides are compared with forward slashes, so the text comes back so.
    """
    text = rendered.replace("\\", "/")
    if label is None:
        return text
    shadow_form = str(shadow).replace("\\", "/")
    return text.replace(
        f"{shadow_form}/sims/sim_{sim}/", f"{shadow_form}/sims/batch/{label}/sim_{sim}/"
    )


def _receipt(base: Path, stem: str) -> GroupingReceipt | None:
    """Read the grouping receipt of ``post/<stem>/plan.json``; None when there is none."""
    try:
        plan = json.loads((base / "post" / stem / "plan.json").read_text(encoding="utf-8"))
        block = plan.get("grouping") if isinstance(plan, Mapping) else None
        return GroupingReceipt.from_json(block) if isinstance(block, Mapping) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _entry(
    receipt: GroupingReceipt, job: GroupedJob, run_id: str, *, run_root: str, submitted: bool
) -> dict[str, Any]:
    """Return the job entry collect wrote for this point, from the receipt and the job folder.

    What only the submission carried is left unstated, never invented (FR-412
    R4): ``values``, the scheduler's fields bound when the job was submitted,
    is empty.
    """
    folder = job.dir.rstrip("/")
    return {
        "kind": "batch" if receipt.mode == "batch" else "polar_sweep",
        "name": job.name,
        "batch_id": job.batch_id,
        "label": job.label,
        "dir": folder,
        "script": PurePath(job.script).name,
        "root": f"{run_root}/{folder}",
        "executor": "submitting" if submitted else "local",
        "values": {},
        "order": job.points.index(run_id) + 1,
        "points": len(job.points),
        "receipt_sha256": receipt_digest(receipt),
    }


def grouped_point(
    base: Path,
    stem: str,
    run_id: str,
    *,
    executed: str,
    home: Path,
    run_root: str | None,
    descriptor_name: str | None,
) -> GroupedPoint | None:
    """Return what the rebuilt record of ``run_id`` says of its grouped job, or None.

    Parameters
    ----------
    base : Path
        The workspace root.
    stem : str
        The matrix stem, whose ``post/<stem>/plan.json`` holds the receipt.
    run_id : str
        The point's run id, as the receipt lists it.
    executed : str
        The point's executed script, which names its batch folder.
    home : Path
        Where the simulation's folder is now (:func:`simulation_home`).
    run_root : str or None
        The workspace root as the run spelled it, for the entry's ``root``.
    descriptor_name : str or None
        The scheduler descriptor's file name, from the HPC profile.

    Returns
    -------
    GroupedPoint or None
        None for a point that ran alone: no batch named and no receipt naming it.
    """
    sim = home.name[len("sim_") :]
    label = batch_label(executed, sim)
    receipt = _receipt(base, stem)
    job = next((item for item in (receipt.jobs if receipt else ()) if run_id in item.points), None)
    if job is None and label is None:
        return None
    job_dir = base / (job.dir if job is not None else f"sims/batch/{label}")
    submitted = descriptor_name is not None and (job_dir / descriptor_name).is_file()
    root = (run_root or str(base)).replace("\\", "/").rstrip("/")
    entry = None
    if receipt is not None and job is not None:
        entry = _entry(receipt, job, run_id, run_root=root, submitted=submitted)
    if label is None and job is not None and job.batch_id is not None:
        label = job.label
    relative = job_dir.relative_to(base).as_posix()
    return GroupedPoint(
        label=label,
        entry=entry,
        job_dir=job_dir if submitted else None,
        descriptor=f"{root}/{relative}/{descriptor_name}" if submitted else None,
        in_batch=base / "sims" / "batch" in home.parents,
    )


def with_job(
    record: dict[str, Any], grouped: GroupedPoint, minted: Mapping[str, Any]
) -> dict[str, Any]:
    """Return ``record`` naming its batch and its job, as collect records a grouped point.

    A rebuilt record that keeps no submission block (a point the rebuild takes
    as run here) is given one holding what the minted row declared, so the
    batch and the job have a place.
    """
    submission = dict(record.get("submission") or {})
    if not submission:
        submission = {key: minted[key] for key in _DECLARED if key in minted}
        submission.update(descriptor=None, submitted=False)
    if grouped.entry is not None:
        submission["job"] = dict(grouped.entry)
    if grouped.label is not None:
        submission["batch"] = grouped.label
    if grouped.descriptor is not None:
        submission["descriptor"] = grouped.descriptor
    return {**record, "submission": submission}


def grouped_facts(facts: dict[str, Any], grouped: GroupedPoint | None) -> str | None:
    """Put a grouped point's job folder into its facts; a refusal when it cannot be rebuilt.

    A point whose job folder holds the scheduler descriptor was submitted, as
    a point run alone whose own folder holds it (FR-372). A point whose files
    are still in its batch folder is left SUBMITTED with its job entry, for
    ``collect`` to move home and complete (FR-412 R1b): a rebuild writes nothing
    in the tree, and a record completed there would name outputs the post does
    not find. Without a plan receipt naming its job, collect could not move it.
    """
    if grouped is None:
        return None
    if grouped.job_dir is not None and facts.get("descriptor_dir") is None:
        facts.update(descriptor_dir=grouped.job_dir, submitted_here=True)
    if not grouped.in_batch:
        return None
    where = f"sims/batch/{grouped.label}/"
    if grouped.entry is None:
        return (
            f"its files are still in the batch folder {where} and no plan receipt "
            "(post/<matrix>/plan.json) names its job, so collect could not move them home; "
            "restore the plan receipt (CLI: pyfs-matrix restore plan --matrix STEM) and rebuild "
            "again"
        )
    facts.setdefault(
        "keep_submitted",
        f"its files are still in the batch folder {where}: pyfs-matrix collect moves them home "
        "and completes the record",
    )
    return None
