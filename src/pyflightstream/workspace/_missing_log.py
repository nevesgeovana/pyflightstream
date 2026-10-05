"""The one rule that names a run whose solver log is absent, RAN_MISSING_LOG (FR-413, 0.37.0).

Pipeline role: beneath the run layer's collect, its grouped collect and its
rebuild, which all ask :func:`absent_solver_logs` of one point's files BEFORE
any rule that would wait for the log or read the job's end files; the post
reads only the status they recorded. A point whose settled outputs (its
declared outputs other than its solver log) are all present while its
declared solver log is absent ENDED with its outputs: it is collected and
posted, and its record says what only the log could have said.

WHAT "DECLARED" MEANS. The solver log of a point is the file its script told
the solver to write its log to, recorded at submission under
``declared_logs``, and present among its ``declared_outputs``. A machine whose
HPC profile states ``[log] export_log = false`` writes no log from the
script, so nothing is declared there and the rule never fires (R5): that
machine's log is the scheduler's, and collect keeps its 0.36.0 handling.

WHAT IS UNAVAILABLE, said once here and read by every writer and reader of
the status (:data:`UNAVAILABLE_WITHOUT_LOG`): the residual history, the
convergence verdict, the frozen-point reading, the solver clock and the
solver's own iteration count. On 26.124 an unsteady log carries no
completion line either (RPT-088), so the status says the run ended with its
outputs, never that it completed or converged.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from pyflightstream.workspace.manifest import RunRecord, RunStatus

__all__ = [
    "UNAVAILABLE_WITHOUT_LOG",
    "absent_solver_logs",
    "missing_log_fields",
    "missing_log_note",
    "missing_log_warning",
    "point_absent_logs",
]

#: What only a solver log carries, in the order every message names it (FR-413 R7).
UNAVAILABLE_WITHOUT_LOG: tuple[str, ...] = (
    "the residual history",
    "the convergence verdict",
    "the frozen-point reading",
    "the solver clock (wall_time_s)",
    "the solver's own iteration count",
)

#: The record fields that only a log can fill, each written null (R2): never zero,
#: never estimated, never carried over from an assessment that read no log.
_LOG_ONLY_FIELDS: tuple[str, ...] = (
    "wall_time_s",
    "iterations",
    "residual",
    "solver_run_time_s",
    "solver_initialization_s",
    "log_file_used",
)


def _listed(items: Sequence[str]) -> str:
    """Join names the way a sentence lists them: ``a, b and c``."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _name(path: str) -> str:
    """Return the file name of a declared output, whichever separator the record uses."""
    return PureWindowsPath(PurePosixPath(str(path)).name).name


def absent_solver_logs(
    outputs: Sequence[str],
    logs: Iterable[str],
    folder: Path,
    *,
    written_here: Collection[str] = (),
) -> tuple[str, ...]:
    """Return the declared solver logs absent from ``folder`` while every other output is there.

    THE ONE DECISION OF RAN_MISSING_LOG (FR-413 R6). Empty when no output of
    ``outputs`` is a declared log, when every declared log is present, or when
    any other declared output (those the package writes itself, such as a
    translated Tecplot, excepted) is missing: a point missing an output other
    than its log is FAILED_INCOMPLETE_OUTPUT as before (R7).

    Parameters
    ----------
    outputs : sequence of str
        The point's declared outputs, as its record states them.
    logs : iterable of str
        The files its script exports its solver log to (``declared_logs``).
    folder : Path
        Where the point's job wrote them.
    written_here : collection of str, optional
        Declared outputs the package writes after collection, not waited for.

    Returns
    -------
    tuple of str
        The absent log names, in the order of ``outputs``; empty otherwise.
    """
    declared = {_name(name) for name in logs}
    log_outputs = [name for name in outputs if _name(name) in declared]
    absent = [name for name in log_outputs if not (folder / name).exists()]
    if not absent:
        return ()
    others = [name for name in outputs if name not in log_outputs and name not in written_here]
    if not others or not all((folder / name).is_file() for name in others):
        return ()
    return tuple(absent)


def point_absent_logs(record: RunRecord, folder: Path) -> tuple[str, ...]:
    """Ask :func:`absent_solver_logs` of one SUBMITTED record's declared files in ``folder``.

    Parameters
    ----------
    record : RunRecord
        The record, whose ``submission`` declares its outputs and logs.
    folder : Path
        Where its job wrote them.

    Returns
    -------
    tuple of str
        The absent log names, or empty when the rule does not apply.
    """
    submission: Mapping[str, Any] = record.submission or {}
    outputs = submission.get("declared_outputs")
    logs = submission.get("declared_logs")
    if not isinstance(outputs, list | tuple) or not isinstance(logs, list | tuple):
        return ()
    written = {
        str(entry.get("dat"))
        for entry in record.surface_translations or []
        if isinstance(entry, Mapping)
    }
    return absent_solver_logs(
        [str(name) for name in outputs],
        [str(name) for name in logs],
        folder,
        written_here=written,
    )


def missing_log_note(logs: Sequence[str]) -> str:
    """Return the ``residual_note`` of a RAN_MISSING_LOG record (R2)."""
    return (
        f"the solver log {_listed([_name(name) for name in logs])} is absent, so "
        f"{_listed(UNAVAILABLE_WITHOUT_LOG)} are unavailable; the run ended with its "
        "outputs, which says nothing of whether it completed or converged"
    )


def missing_log_fields(logs: Sequence[str]) -> dict[str, object]:
    """Return the record fields a RAN_MISSING_LOG point is completed with (R2, R7).

    The status, the note naming the absent log and what it would have
    carried, and every field only a log fills set to null.
    """
    fields: dict[str, object] = dict.fromkeys(_LOG_ONLY_FIELDS)
    fields.update(status=RunStatus.RAN_MISSING_LOG, residual_note=missing_log_note(logs))
    return fields


def missing_log_warning(run_id: str, *, check_frozen: bool) -> str:
    """Return the one ``post.log`` WARNING of a RAN_MISSING_LOG point (R3)."""
    frozen = (
        "; the frozen-point check (--check-frozen) cannot read its freeze, and the point is "
        "admitted"
        if check_frozen
        else ""
    )
    return (
        f"point={run_id} product=all: the recorded status is {RunStatus.RAN_MISSING_LOG.value}: "
        f"its solver log is absent, so {_listed(UNAVAILABLE_WITHOUT_LOG)} are unavailable; "
        f"every product is written from its outputs{frozen}. Recollect the log to settle them."
    )
