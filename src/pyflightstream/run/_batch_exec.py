"""The two adapters a grouped run hands to the per-point campaign loop (0.35.0).

Pipeline role: ``run --batch N`` and ``run --polar-sweep`` reuse the per-point
run path unchanged and add only what is new around it (IMPL-0350 section 1).
The campaign loop is handed two adapters instead of the plain ones:

- :class:`GroupingExecutor` satisfies the ``Executor`` and ``Submitting``
  protocols. When the loop asks it to run a point of a grouped job, it runs
  nothing: it remembers the point's script and folder and answers with a
  zero-time result, so the loop writes exactly the ``SUBMITTED`` record a
  submitted point writes, with the job's entry in ``submission`` (FR-366). Any
  other call, the identity pre-flight's probe in a temporary folder, goes to
  the real executor, so a local run still checks the installed build.
- :class:`BatchStagingWorkspace` answers ``sim_dir`` with the simulation's
  folder inside its batch, so every file the loop writes for a point lands in
  the batch folder from the start (FR-358), and every absolute path the
  per-point scripts name already points there.

:class:`JobCollector` maps each simulation to its job and keeps the points the
executor remembered, in the order the loop ran them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath

from pyflightstream.run._executors import ExecutionResult, Executor, Submitting
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace._batches import GroupedJob, GroupingReceipt, JobEntry
from pyflightstream.workspace.hpc import HpcProfile
from pyflightstream.workspace.naming import SIM_DATAPOINTS_DIR, NamingTemplate

#: The prefix of a simulation's folder name, ``sim_<id>``.
_SIM_PREFIX = "sim_"


@dataclass(frozen=True)
class CollectedPoint:
    """One point of a grouped job, as the campaign loop wrote it.

    Attributes
    ----------
    sim_id : str
        The simulation the point belongs to.
    point_name : str
        The point's name, as the plan prints it.
    script_path : Path
        The per-point script the loop wrote, absolute.
    working_dir : Path
        The point's datapoint folder, absolute.
    """

    sim_id: str
    point_name: str
    script_path: Path
    working_dir: Path


def receipt_digest(receipt: GroupingReceipt) -> str:
    """Return the sha256 of a grouping receipt, read from its JSON form.

    Parameters
    ----------
    receipt : GroupingReceipt
        The receipt the run runs on.

    Returns
    -------
    str
        The hexadecimal digest of the receipt's canonical JSON (keys sorted).
    """
    text = json.dumps(receipt.to_json(), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class JobCollector:
    """Map each simulation of a receipt to its job, and keep the points remembered.

    One per run call.

    Parameters
    ----------
    receipt : GroupingReceipt
        The receipt the run runs on.
    root : Path
        The workspace root.
    job_roots : mapping of str to PurePath
        The root each job's script names its paths from, by job label
        (IMPL-0350 section 8, reading 3).
    values : mapping of str to mapping, optional
        The placeholder values of each job's descriptor, by job label
        (reading 9); recorded in every point's job entry.
    """

    def __init__(
        self,
        receipt: GroupingReceipt,
        *,
        root: Path,
        job_roots: Mapping[str, PurePath],
        values: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self.receipt = receipt
        self.root = Path(root)
        self.job_roots = dict(job_roots)
        self.values = {label: dict(bound) for label, bound in (values or {}).items()}
        self.receipt_sha256 = receipt_digest(receipt)
        self._job_of_sim = {sim: job for job in receipt.jobs for sim in job.sims}
        self._points: dict[str, list[CollectedPoint]] = {job.label: [] for job in receipt.jobs}

    def job_for(self, sim_id: str) -> GroupedJob | None:
        """Return the job a simulation runs in, or None for one the receipt does not hold.

        Parameters
        ----------
        sim_id : str
            The simulation id.

        Returns
        -------
        GroupedJob or None
            The job, or None.
        """
        return self._job_of_sim.get(sim_id)

    def remember(self, point: CollectedPoint) -> None:
        """Keep one point of a job, in the order the loop ran it.

        Parameters
        ----------
        point : CollectedPoint
            The point the executor was asked to run.
        """
        job = self.job_for(point.sim_id)
        if job is not None:
            self._points[job.label].append(point)

    def points_of(self, job: GroupedJob) -> list[CollectedPoint]:
        """Return the points of a job remembered so far, in run order.

        Parameters
        ----------
        job : GroupedJob
            A job of the receipt.

        Returns
        -------
        list of CollectedPoint
            The points, possibly none.
        """
        return list(self._points.get(job.label, []))

    def entry(self, job: GroupedJob, *, executor: str) -> JobEntry:
        """Return the job entry the latest point of ``job`` carries in its record.

        Parameters
        ----------
        job : GroupedJob
            The job of the point just remembered.
        executor : str
            ``local`` or ``submitting``.

        Returns
        -------
        JobEntry
            The entry of 4.3, with this point's position in the job.
        """
        bound = self.values.get(job.label, {})
        return JobEntry(
            kind="batch" if self.receipt.mode == "batch" else "polar_sweep",
            name=job.name,
            batch_id=job.batch_id,
            label=job.label,
            dir=job.dir.rstrip("/"),
            script=PurePath(job.script).name,
            root=PurePath(self.job_roots.get(job.label, self.root / job.dir)).as_posix(),
            executor="local" if executor == "local" else "submitting",
            values={str(key): str(value) for key, value in bound.items()},
            order=len(self._points.get(job.label, [])),
            points=len(job.points),
            receipt_sha256=self.receipt_sha256,
        )


def _sim_of(working_dir: Path) -> str | None:
    """Return the simulation id of a datapoint folder ``.../sim_<id>/datapoints/DP-x``."""
    parent = working_dir.parent
    if parent.name != SIM_DATAPOINTS_DIR or not parent.parent.name.startswith(_SIM_PREFIX):
        return None
    return parent.parent.name.removeprefix(_SIM_PREFIX)


class GroupingExecutor:
    """The executor a grouped run hands to the campaign loop (``Executor``, ``Submitting``).

    A point of a simulation the collector knows is remembered and answered
    with a zero-time result, so the loop records it ``SUBMITTED`` with the
    job's entry; every other call is the inner executor's.

    Parameters
    ----------
    inner : Executor
        The executor the jobs launch through.
    collector : JobCollector
        The run's collector.
    profile : HpcProfile, optional
        The inner's profile, or the workspace's under a forced local run, so
        the per-point scripts keep the machine's ``export_log`` decision.
    """

    #: Present on an instance ONLY when the inner submits, so the identity
    #: pre-flight skips a submitting run and probes a local one, as it does
    #: for the inner alone.
    descriptor_path: Path | None

    def __init__(
        self, inner: Executor, collector: JobCollector, *, profile: HpcProfile | None
    ) -> None:
        self.inner = inner
        self.collector = collector
        self.profile = profile
        self.forced_local = bool(getattr(inner, "forced_local", False))
        self.submits = isinstance(inner, Submitting)
        self.values: dict[str, object] = {}
        self._record: dict | None = None
        if self.submits:
            self.descriptor_path = None

    def bind_point(self, values: Mapping[str, object], *, replace: bool = False) -> None:
        """Keep the values of the point the loop is about to run.

        Parameters
        ----------
        values : mapping of str to object
            The point's descriptor values (its simulation and point name).
        replace : bool
            Rebuild rather than merge, as the submitting executor does.
        """
        self.values = dict(values) if replace else {**self.values, **values}

    def submission_record(self) -> dict | None:
        """Return the job's submission entry of the point remembered last, or None.

        Returns
        -------
        dict or None
            ``descriptor``, ``profile``, ``application_id`` and ``submitted``
            of the JOB (None, None, None and False under a local run), the
            ``job`` entry, and ``batch`` for a batch.
        """
        return None if self._record is None else dict(self._record)

    def _job_record(self, job: GroupedJob) -> dict:
        """Compose the submission entry every point of ``job`` carries."""
        kind = "submitting" if self.submits else "local"
        profile = self.profile if self.submits else None
        descriptor = (
            (self.collector.root / job.dir / profile.descriptor_name).as_posix()
            if profile is not None
            else None
        )
        record: dict[str, object] = {
            "descriptor": descriptor,
            "profile": profile.path.as_posix() if profile is not None else None,
            "application_id": profile.application_id if profile is not None else None,
            "submitted": bool(getattr(self.inner, "submit", False)) if self.submits else False,
            "job": dict(self.collector.entry(job, executor=kind)),
        }
        if self.collector.receipt.mode == "batch":
            record["batch"] = job.label
        return record

    def run_script(
        self, script_path: Path, working_dir: Path, timeout_s: float | None = None
    ) -> ExecutionResult:
        """Remember a point of a grouped job, or delegate any other run to the inner.

        Parameters
        ----------
        script_path : Path
            The per-point script.
        working_dir : Path
            The folder it would run in.
        timeout_s : float, optional
            The limit, passed to the inner on a delegated run.

        Returns
        -------
        ExecutionResult
            Return code 0 and no wall time for a remembered point; the inner's
            result otherwise.
        """
        sim = _sim_of(Path(working_dir))
        job = self.collector.job_for(sim) if sim is not None else None
        if sim is None or job is None:
            return self.inner.run_script(script_path, working_dir, timeout_s)
        self.collector.remember(
            CollectedPoint(
                sim_id=sim,
                point_name=str(self.values.get("point", Path(working_dir).name)),
                script_path=Path(script_path),
                working_dir=Path(working_dir),
            )
        )
        self._record = self._job_record(job)
        return ExecutionResult(
            return_code=0,
            wall_time_s=0.0,
            timed_out=False,
            log_text=None,
            stdout="",
            stderr="",
            argv=(),
            cwd=str(working_dir),
            timeout_s=timeout_s,
        )


class BatchStagingWorkspace(CampaignWorkspace):
    """A workspace whose simulations of a batch live in the batch folder (FR-358).

    Every file the campaign loop writes for a point (scripts, datapoint
    folders, parked inputs, action programs, the ``inputs`` link) goes through
    :meth:`sim_dir`, so it lands in ``sims/batch/<matrix>_b<ID>/sim_<id>/``.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    naming : NamingTemplate, optional
        The naming template.
    homes : mapping of str to Path
        The folder of each simulation of a batch, by simulation id.
    """

    def __init__(
        self,
        root: str | Path,
        naming: NamingTemplate | None = None,
        *,
        homes: Mapping[str, Path],
    ) -> None:
        super().__init__(root, naming)
        self.homes = {sim: Path(home) for sim, home in homes.items()}

    def sim_dir(self, sim_id: str) -> Path:
        """Return the folder of one simulation: its batch home, or the managed folder.

        Parameters
        ----------
        sim_id : str
            The simulation id, refused as the managed folder refuses it.

        Returns
        -------
        Path
            ``homes[sim_id]`` for a simulation of a batch, else ``sims/sim_<id>``.
        """
        managed = super().sim_dir(sim_id)
        return self.homes.get(sim_id, managed)
