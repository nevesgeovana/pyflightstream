"""The verdict on a run that imported trailing edges, read off the solver's own count.

G02 of 0.27.0 (RPT-061, RPT-065). Private to the run layer: the point path and
the collect path both apply it, so it lives beneath both rather than in the
package module one of them would otherwise reach into. The rule that finds a
point's solver log among its collected outputs lives here for the same reason:
the package's assessor finds its log by it, and the count is read from the log
it finds whichever assessor judged the point.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pyflightstream.results import (
    IncompleteOutputError,
    imported_trailing_edges,
    parse_residual_history,
)
from pyflightstream.workspace import RunStatus

__all__ = [
    "collected_solver_log",
    "reads_as_residual_history",
    "wake_edge_import_verdict",
    "with_wake_edge_verdict",
]


def reads_as_residual_history(path: Path) -> bool:
    """Whether one collected file parses as a solver residual history.

    The identification is by CONTENT and never by name, the same rule
    the loads table is found under: a swept case names its outputs per
    point, so no literal could name them all. False on anything that
    does not parse, including a file this process cannot read, because
    the caller's fallback is the judgment that existed before and never
    an error about a file nobody asked it to read.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    try:
        return bool(parse_residual_history(text))
    except (IncompleteOutputError, ValueError):
        return False


def collected_solver_log(folder: Path, collected: Sequence[str], named: str | None) -> str | None:
    """Return the text of the solver log among a point's collected outputs, or None.

    WHICHEVER ASSESSOR JUDGED THE POINT. The package's own assessor names the
    file it read (``log_file_used``), and that file is read. An assessor a
    caller passes answers with a status and need not name anything, so the log
    is then found as the package's own assessor finds it: the one collected
    output that parses as a residual history. Until this, a caller's assessor
    left a collected log unread, and a point whose log carried every imported
    edge was recorded FAILED_INCOMPLETE_OUTPUT with the remedy to export the
    log it had exported (the qa lens, 2026-09-24).

    Parameters
    ----------
    folder : Path
        The simulation folder the collected entries are relative to.
    collected : sequence of str
        The point's collected outputs.
    named : str or None
        The file name the assessor says it read, when it says one.

    Returns
    -------
    str or None
        The log's text; None when no collected output is the log, or when
        several parse as one, since which of them is this point's would be a
        guess.
    """
    paths = [folder / entry for entry in collected]
    if named:
        for path in paths:
            if path.name == named and path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")
    candidates = [path for path in paths if path.is_file() and reads_as_residual_history(path)]
    if len(candidates) == 1:
        return candidates[0].read_text(encoding="utf-8", errors="replace")
    return None


def wake_edge_import_verdict(
    expected: int | None, log_text: str | None
) -> tuple[RunStatus, str] | None:
    """Judge a run that imported trailing edges by the count the solver logged.

    G02 (RPT-061, RPT-065). The import marks nothing and says nothing for a
    point that matches no mesh edge, and initialisation does not add what
    it missed, so the solver's ``N trailing edges imported`` line is the one
    statement that tells a file that marked from one that did not.

    Parameters
    ----------
    expected : int or None
        The points the script wrote (``Script.wake_edge_points``); None
        for a script that imports nothing, which is never judged here, so a
        continuation that opens a saved state is not held to a count.
    log_text : str or None
        The run's solver log.

    Returns
    -------
    tuple of (RunStatus, str) or None
        None when there is nothing to object to; FAILED_INCOMPLETE_OUTPUT
        when no log was read; FAILED_SCRIPT when the logged count differs
        from the points written. Each with its reason.
    """
    if expected is None:
        return None
    if log_text is None:
        return (
            RunStatus.FAILED_INCOMPLETE_OUTPUT,
            f"the script imported {expected} trailing-edge points and no solver log was "
            "read, so whether the file marked anything cannot be told: a file whose "
            "points match no edge marks nothing and says nothing. Export the solver log "
            "among the row's outputs",
        )
    counts = imported_trailing_edges(log_text)
    logged = sum(counts.values())
    if logged == expected:
        return None
    per_boundary = ", ".join(f"{count} for {name}" for name, count in counts.items()) or "none"
    return (
        RunStatus.FAILED_SCRIPT,
        f"the script wrote {expected} trailing-edge points and the solver logged "
        f"{logged} imported (per boundary: {per_boundary}); a point matching no mesh edge "
        "is dropped in silence, so this run's wake is not the one declared",
    )


def with_wake_edge_verdict(
    status: RunStatus, error: str | None, verdict: tuple[RunStatus, str] | None
) -> tuple[RunStatus, str | None]:
    """Apply a wake-edge verdict over a status that is not already a failure."""
    if verdict is None or str(status).startswith("FAILED"):
        return status, error
    return verdict[0], "; ".join(part for part in (error, verdict[1]) if part)
