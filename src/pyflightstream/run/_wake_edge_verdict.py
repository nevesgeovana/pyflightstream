"""The verdict on a run that imported trailing edges, read off the solver's own count.

G02 of 0.27.0 (RPT-061, RPT-065). Private to the run layer: the point path and
the collect path both apply it, so it lives beneath both rather than in the
package module one of them would otherwise reach into.
"""

from __future__ import annotations

from pyflightstream.results import imported_trailing_edges
from pyflightstream.workspace import RunStatus

__all__ = ["wake_edge_import_verdict", "with_wake_edge_verdict"]


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
