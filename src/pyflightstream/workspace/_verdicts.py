"""Human verdict identity for record writers, including steady job point entries.

The manifest can store a mark on a record or on a point in ``points_ran``.
A sync must preserve both the mark and the status it gave, even if the
incoming record also contains a mark. Rebuild uses the same inventory to
decide which existing records require preservation.
"""

from collections.abc import Mapping
from typing import Any

from pyflightstream.workspace.manifest import RunStatus

#: A manifest note identifying a simulation removed by delete-sims.
DELETED_SIM_KEY = "deleted_sim"


def marked_units(row: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return marked units keyed by point tag, with the record under the empty key.

    Parameters
    ----------
    row : mapping
        A serialized run record.
    """
    units = {"": row, **{str(p.get("tag")): p for p in row.get("points_ran") or []}}
    return {key: unit for key, unit in units.items() if unit.get("marked")}


def verdict_changed(mine: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
    """Whether replacing a row would remove or change any existing human verdict.

    Parameters
    ----------
    mine, other : mapping
        The current record and its proposed replacement.
    """
    incoming = marked_units(other)
    return any(
        key not in incoming
        or unit.get("marked") != incoming[key].get("marked")
        or unit.get("status") != incoming[key].get("status")
        for key, unit in marked_units(mine).items()
    )


def merge_runs(
    main_rows: list[dict[str, Any]], other_rows: list[dict[str, Any]], prefer_other: bool
):
    """Merge run rows without replacing a person's verdict or a deleted simulation.

    Parameters
    ----------
    main_rows, other_rows : list of dict
        Current records and incoming records.
    prefer_other : bool
        Prefer incoming completed records where no human verdict would change.
    """
    deleted = {
        str(run)
        for row in main_rows
        if row.get(DELETED_SIM_KEY) is not None
        for run in row.get("deleted_run_ids", [])
    }
    index = {row.get("run_id"): i for i, row in enumerate(main_rows)}
    merged = [dict(row) for row in main_rows]
    added: list[str] = []
    replaced: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for row in other_rows:
        run_id = row.get("run_id")
        if not run_id:
            conflicts.append({"run_id": None, "reason": "a record without run_id"})
            continue
        if str(run_id) in deleted:
            conflicts.append({"run_id": run_id, "reason": "deleted in main by delete-sims"})
            continue
        if run_id not in index:
            index[run_id] = len(merged)
            merged.append(row)
            added.append(str(run_id))
            continue
        mine = merged[index[run_id]]
        if mine == row:
            continue
        # FR-414 R4: a row carrying a person's verdict (``marked``) is never
        # replaced by one that does not; the merge names it as a conflict.
        verdict_lost = verdict_changed(mine, row)
        if (mine.get("status") == RunStatus.SUBMITTED.value or prefer_other) and not verdict_lost:
            merged[index[run_id]] = row
            replaced.append(
                {
                    "run_id": run_id,
                    "from": mine.get("status"),
                    "to": row.get("status"),
                    "forced": mine.get("status") != RunStatus.SUBMITTED.value,
                }
            )
        else:
            conflicts.append(
                {
                    "run_id": run_id,
                    "main_status": mine.get("status"),
                    "other_status": row.get("status"),
                }
            )
    return merged, added, replaced, conflicts
