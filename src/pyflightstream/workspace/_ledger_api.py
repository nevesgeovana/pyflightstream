"""Plain-data Python entry points for the workspace ledger (FR-388).

Pipeline role: adapt paths or existing snapshots to the same row functions
the command renderers use. No optional dependency is imported here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyflightstream.workspace._ledger_history import diff_rows, history_rows

if TYPE_CHECKING:
    from pyflightstream.workspace.ledger import Ledger


def _snapshot(root: str | Path | Ledger, runs: str | None) -> Ledger:
    from pyflightstream.workspace.ledger import Ledger, read_ledger

    return root if isinstance(root, Ledger) else read_ledger(root, runs=runs)


def status_rows(
    root: str | Path | Ledger,
    *,
    runs: str | None = None,
    sims: Iterable[str] | None = None,
    matrix: str | None = None,
    statuses: Sequence[str] = (),
    failed: bool = False,
) -> list[dict[str, object]]:
    """Return the polar rows printed by ``status --json``.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or an already read snapshot.
    runs : str, optional
        Manifest name when reading a root.
    sims : iterable of str, optional
        Simulation ids to select.
    matrix : str, optional
        Matrix stem or file name.
    statuses : sequence of str, optional
        Recorded words, with an optional trailing wildcard.
    failed : bool, optional
        Select polars containing a failed point.

    Returns
    -------
    list of dict
        JSON-serializable polar rows.

    Examples
    --------
    >>> status_rows("campaign", sims=["2006"])  # doctest: +SKIP
    """
    return _snapshot(root, runs).status(sims=sims, matrix=matrix, statuses=statuses, failed=failed)


def point_rows(
    root: str | Path | Ledger,
    *,
    runs: str | None = None,
    sims: Iterable[str] | None = None,
    matrix: str | None = None,
    statuses: Sequence[str] = (),
    failed: bool = False,
) -> list[dict[str, object]]:
    """Return the datapoint rows printed by ``status --points --json``.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.
    runs : str, optional
        Manifest name.
    sims : iterable of str, optional
        Simulation ids.
    matrix : str, optional
        Matrix stem.
    statuses : sequence of str, optional
        Recorded status filters.
    failed : bool, optional
        Select failed points only.

    Returns
    -------
    list of dict
        JSON-serializable datapoint rows.

    Examples
    --------
    >>> point_rows("campaign", failed=True)  # doctest: +SKIP
    """
    return _snapshot(root, runs).points(sims=sims, matrix=matrix, statuses=statuses, failed=failed)


def point_card(
    root: str | Path | Ledger, run_id: str, *, runs: str | None = None
) -> dict[str, object] | None:
    """Return the effective record of one point, without reading archives.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.
    run_id : str
        Effective datapoint run id.
    runs : str, optional
        Manifest name.

    Returns
    -------
    dict or None
        JSON-serializable outcome-first card, or None when absent.

    Examples
    --------
    >>> point_card("campaign", "camp/sim_2006/A0")  # doctest: +SKIP
    """
    from pyflightstream.workspace._query_point import _card

    return _card(_snapshot(root, runs), run_id)


def history(
    root: str | Path | Ledger, target: str, *, runs: str | None = None
) -> list[dict[str, Any]]:
    """Return every recorded attempt with its source, archive stamp and continuation.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.
    target : str
        Simulation id, point name, sim_<id>/<point>, or run id.
    runs : str, optional
        Manifest name; its archived copies are read as well.

    Returns
    -------
    list of dict
        History rows and explicitly identified unreadable archive rows.

    Examples
    --------
    >>> history("campaign", "2006")  # doctest: +SKIP
    """
    return history_rows(_snapshot(root, runs), target)


def diff(
    root: str | Path | Ledger, run_a: str, run_b: str, *, runs: str | None = None
) -> list[dict[str, Any]]:
    """Return changed record fields and attributed script differences between two runs.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.
    run_a, run_b : str
        Run ids, optionally suffixed with @<archive stamp>.
    runs : str, optional
        Present manifest name.

    Returns
    -------
    list of dict
        Changed fields with a and b values, and script comparison availability.

    Raises
    ------
    WorkspaceError
        When a selector is absent or ambiguous.

    Examples
    --------
    >>> diff("campaign", "camp/sim_2006/A0@20261001-120000",
    ...      "camp/sim_2006/A0")  # doctest: +SKIP
    """
    return diff_rows(_snapshot(root, runs), run_a, run_b)


def additional_rows(root: str | Path | Ledger) -> list[dict[str, Any]]:
    """Return the additional register's fields exactly as recorded (FR-393).

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.

    Returns
    -------
    list of dict
        Recorded entries without model defaults or derived fields.

    Raises
    ------
    WorkspaceError
        If the additional register does not hold a list of records.

    Examples
    --------
    >>> additional_rows("campaign")  # doctest: +SKIP
    """
    from pyflightstream.workspace._query_logs import _additional

    return _additional(_snapshot(root, None))


def activity_rows(
    root: str | Path | Ledger,
    *,
    sims: Iterable[str] | None = None,
    run: str | None = None,
    stage: str | None = None,
    since: str | None = None,
    problems: bool = False,
    open_only: bool = False,
) -> list[dict[str, Any]]:
    """Return recorded activity rows oldest first, optionally selected by identity.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.
    sims : iterable of str, optional
        Simulation ids.
    run : str, optional
        Run id.
    stage : str, optional
        Recorded stage name.
    since : str, optional
        ISO time or duration.
    problems : bool, optional
        Only events carrying problems or failure.
    open_only : bool, optional
        Only started stages without a finish.

    Returns
    -------
    list of dict
        JSON-serializable activity records.

    Raises
    ------
    WorkspaceError
        If an activity line is not a JSON object.

    Examples
    --------
    >>> activity_rows("campaign", stage="run")  # doctest: +SKIP
    """
    from pyflightstream.workspace._query_logs import _activity, _select_logs

    return _select_logs(
        _activity(_snapshot(root, None)),
        sims=list(sims or ()),
        run=run,
        stage=stage,
        since=since,
        problems=problems,
        open_only=open_only,
    )


def post_log_groups(
    root: str | Path | Ledger, matrix: str, *, sims: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """Return recorded post diagnostics grouped by category, family and message shape.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.
    matrix : str
        Matrix stem.
    sims : iterable of str, optional
        Simulation ids to select.

    Returns
    -------
    list of dict
        Each category, family and shape with a count and one example.

    Examples
    --------
    >>> post_log_groups("campaign", "sample")  # doctest: +SKIP
    """
    from pyflightstream.workspace._query_logs import _post_groups

    return _post_groups(_snapshot(root, None), matrix, list(sims or ()))


def trace_product(root: str | Path | Ledger, product: str) -> list[dict[str, Any]]:
    """Return a product index entry and its effective run identities.

    Parameters
    ----------
    root : str, Path or Ledger
        Workspace root or snapshot.
    product : str
        Product path relative to the workspace, or absolute.

    Returns
    -------
    list of dict
        Index entries with records and provenance paths; empty for an unknown path.

    Examples
    --------
    >>> trace_product("campaign", "post/sample/polar.csv")  # doctest: +SKIP
    """
    from pyflightstream.workspace._query_point import _trace

    return _trace(_snapshot(root, None), product)
