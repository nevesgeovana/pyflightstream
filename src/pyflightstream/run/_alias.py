"""The run id alias of a datapoint, ``<sim>_<index>`` (0.35.0, FR-395, P0350-RUN-ID-ALIAS).

A run id of a continuation is long and changes; the alias is short and stable. It is
DERIVED and NEVER STORED, so no recorded file changes.

THE INDEX IS READ FROM THE RECORDS FIRST, not from today's plan. The points a
simulation has recorded come first, in the sweep order the plan lists them (a
recorded point the plan no longer lists follows them, in the order it was recorded;
a job's ``points_ran`` is read point by point); a re-run or a continuation of a point
adds a record and never moves it. The planned points that have no record yet follow,
in the order the plan lists them. So adding points to the matrix moves
no alias a record already holds, and neither does re-running or continuing a point.
A polar recorded out of its sweep order (``--points`` chosen by hand) is the one
case that moves an alias when its first point is recorded.

Where a verb DESTROYS something, the alias is also read the other way, from the plan
as ``plan.json`` lists it, and a disagreement between the two readings is a refusal
that names both (:func:`resolve_alias`, ``strict``).

This module sits at the bottom of the run package: it reads rows and names and
imports nothing of the run machinery.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.workspace import JOB_TAG

#: What joins the simulation id and the index: ``2006_3``.
ALIAS_JOINER = "_"


class AliasError(MatrixError):
    """An alias that names no point, or whose two readings disagree (FR-395 R5)."""


def alias_of(sim_id: str, index: int) -> str:
    """Return the alias of the ``index``-th (1-based) point of simulation ``sim_id``.

    Parameters
    ----------
    sim_id : str
        The simulation id as the matrix spells it.
    index : int
        The 1-based position of the point.

    Returns
    -------
    str
        ``<sim>_<index>``, for example ``2006_3``.
    """
    return f"{sim_id}{ALIAS_JOINER}{index}"


def read_alias(text: str, sims: Collection[str]) -> tuple[str, int] | None:
    """Return ``(sim, index)`` when ``text`` is the alias of a point of a known simulation.

    Parameters
    ----------
    text : str
        What the person typed.
    sims : collection of str
        The simulation ids that exist; a text whose simulation is not among them is
        not an alias (it may be a point name, which has underscores of its own).

    Returns
    -------
    tuple of (str, int) or None
        None when ``text`` is not shaped ``<known sim>_<positive integer>``.
    """
    sim, joiner, number = text.strip().rpartition(ALIAS_JOINER)
    if not joiner or not number.isdigit() or int(number) < 1 or sim not in sims:
        return None
    return sim, int(number)


def _row_tags(row: Mapping[str, Any]) -> list[str]:
    """Return the point tags one manifest row stands for, in the order it ran them."""
    run_id = row.get("run_id")
    if not isinstance(run_id, str):
        return []
    tag = run_id.rsplit("/", 1)[-1]
    if tag != JOB_TAG:
        return [tag]
    ran = row.get("points_ran")
    entries = ran if isinstance(ran, list) else []
    return [str(e.get("tag") or "") for e in entries if isinstance(e, Mapping)]


def recorded_tags(rows: Iterable[Mapping[str, Any]], sim_id: str) -> list[str]:
    """Return the point tags simulation ``sim_id`` has recorded, by first appearance.

    Parameters
    ----------
    rows : iterable of mapping
        The manifest's rows as written (``runs.json``); a delete-sims note is skipped.
    sim_id : str
        The simulation.

    Returns
    -------
    list of str
        Each point once, at the place its first record took; a re-run or a
        continuation adds a record and moves nothing.
    """
    tags: list[str] = []
    for row in rows:
        if row.get("deleted_sim") is not None or str(row.get("sim_id")) != sim_id:
            continue
        tags.extend(tag for tag in _row_tags(row) if tag and tag not in tags)
    return tags


def alias_order(
    rows: Iterable[Mapping[str, Any]], sim_id: str, planned: Sequence[str]
) -> list[str]:
    """Return the point tags of ``sim_id`` in alias order: recorded first, then the plan's rest.

    Parameters
    ----------
    rows : iterable of mapping
        The manifest's rows.
    sim_id : str
        The simulation.
    planned : sequence of str
        The point names the plan lists for it, in plan order.

    Returns
    -------
    list of str
        Alias ``<sim>_1`` is the first element.
    """
    recorded = recorded_tags(rows, sim_id)
    in_sweep_order = [tag for tag in planned if tag in recorded]
    no_longer_planned = [tag for tag in recorded if tag not in planned]
    return [*in_sweep_order, *no_longer_planned, *(tag for tag in planned if tag not in recorded)]


def alias_lines(
    rows: Sequence[Mapping[str, Any]], planned_by_sim: Mapping[str, Sequence[str]]
) -> list[tuple[str, str, str]]:
    """Return ``(alias, sim, point)`` for every point of every simulation named.

    Parameters
    ----------
    rows : sequence of mapping
        The manifest's rows.
    planned_by_sim : mapping of str to sequence of str
        The planned point names of each simulation, in plan order.

    Returns
    -------
    list of tuple
        One entry per point, simulations in the order given.
    """
    return [
        (alias_of(sim, number), sim, tag)
        for sim, planned in planned_by_sim.items()
        for number, tag in enumerate(alias_order(rows, sim, planned), start=1)
    ]


def planned_from_plan_files(root: str | Path) -> dict[str, list[str]]:
    """Return the points each simulation was planned with, read from the ``plan.json`` files.

    Parameters
    ----------
    root : str or Path
        The workspace root; ``plan.json`` is read there and in ``post/<matrix>/``.

    Returns
    -------
    dict of str to list of str
        Per simulation, the point names in the order the (first) plan lists them; a
        file that cannot be read is skipped.
    """
    base = Path(root)
    found: dict[str, list[str]] = {}
    for plan_file in [base / "plan.json", *sorted(base.glob("post/*/plan.json"))]:
        try:
            points = json.loads(plan_file.read_text(encoding="utf-8")).get("points", [])
        except (OSError, ValueError, AttributeError):
            continue
        for entry in points if isinstance(points, list) else []:
            if isinstance(entry, Mapping) and isinstance(entry.get("run_id"), str):
                tags = found.setdefault(str(entry.get("sim_id")), [])
                tag = entry["run_id"].rsplit("/", 1)[-1]
                if tag not in tags:
                    tags.append(tag)
    return found


def resolve_alias(
    text: str,
    rows: Sequence[Mapping[str, Any]],
    planned_by_sim: Mapping[str, Sequence[str]],
    *,
    strict: bool = False,
) -> tuple[str, str] | None:
    """Return ``(sim, point name)`` for an alias, None when ``text`` is not one (FR-395).

    Parameters
    ----------
    text : str
        What the person typed.
    rows : sequence of mapping
        The manifest's rows.
    planned_by_sim : mapping of str to sequence of str
        The planned point names of each simulation, in plan order. A simulation the
        mapping lacks is not known, so its aliases are not read.
    strict : bool
        For a verb that destroys: the record reading and the plan reading must
        name the same point.

    Returns
    -------
    tuple of (str, str) or None
        The simulation and the point name, or None when ``text`` is no alias.

    Raises
    ------
    AliasError
        When the simulation has no such index (naming how many points it has), or
        under ``strict`` when the record reading and the plan reading disagree
        (naming both).
    """
    parsed = read_alias(text, planned_by_sim)
    if parsed is None:
        return None
    sim, number = parsed
    planned = list(planned_by_sim[sim])
    order = alias_order(rows, sim, planned)
    if number > len(order):
        raise AliasError(
            f"alias {text!r} names no point: simulation {sim} has {len(order)} point(s), "
            f"{alias_of(sim, 1)} to {alias_of(sim, len(order))}. Nothing was done."
        )
    point = order[number - 1]
    if strict and planned and (number > len(planned) or planned[number - 1] != point):
        read_by_plan = planned[number - 1] if number <= len(planned) else "no point"
        raise AliasError(
            f"alias {text!r} is ambiguous: the records read it as {point!r} and the plan "
            f"reads it as {read_by_plan!r}. Name the point instead (sims (CLI: --sims) "
            "takes a simulation id; the point name is the end of its run id). "
            "Nothing was done."
        )
    return sim, point


def selection_with_aliases(
    sims: Sequence[str] | None,
    points: Sequence[str] | None,
    rows: Sequence[Mapping[str, Any]],
    planned_by_sim: Mapping[str, Sequence[str]],
) -> tuple[Sequence[str] | None, Sequence[str] | None]:
    """Return ``sims`` and ``points`` with every alias in ``points`` read as its point name.

    An alias names its simulation, so ``--points 2006_3`` alone selects that point of
    simulation 2006; given with ``--sims``, the alias's simulation must be among them.

    Parameters
    ----------
    sims : sequence of str, optional
        ``--sims`` as typed.
    points : sequence of str, optional
        ``--points`` as typed, point names or aliases.
    rows : sequence of mapping
        The manifest's rows.
    planned_by_sim : mapping of str to sequence of str
        The planned point names of each simulation.

    Returns
    -------
    tuple
        The two sequences, unchanged where ``points`` holds no alias.

    Raises
    ------
    AliasError
        An alias with no point, or one whose simulation ``sims`` leaves out.
    """
    if not points:
        return sims, points
    names: list[str] = []
    chosen = list(sims or [])
    given = bool(chosen)
    for text in points:
        found = resolve_alias(text, rows, planned_by_sim)
        if found is None:
            names.append(text)
            continue
        sim, point = found
        if given and sim not in chosen:
            raise AliasError(
                f"points (CLI: --points) names {text!r}, a point of simulation {sim}, "
                f"which sims (CLI: --sims) leaves out ({', '.join(chosen)}). Nothing was run."
            )
        if sim not in chosen:
            chosen.append(sim)
        names.append(point)
    return (chosen or sims), names


def row_selected(row: Mapping[str, Any], tags: Collection[str] | None) -> bool:
    """Return whether a manifest row belongs to the points ``tags`` (None means all of them).

    Parameters
    ----------
    row : mapping
        One manifest row.
    tags : collection of str, optional
        The point names; None selects the row whatever its point.

    Returns
    -------
    bool
        True when the row's own point, or a point its job ran, is among ``tags``.
    """
    return tags is None or any(tag in tags for tag in _row_tags(row))


def split_typed_ids(
    items: Sequence[str], root: str | Path, *, manifest: str = "runs.json", whole_only: bool = False
) -> tuple[list[str], dict[str, list[str]]]:
    """Split typed simulation ids from run id aliases, for a verb that destroys (FR-395 R2).

    Parameters
    ----------
    items : sequence of str
        What was typed after ``--sims``: simulation ids and aliases.
    root : str or Path
        The workspace root, whose records and ``plan.json`` files read the aliases.
    manifest : str
        The manifest the verb reads, by name in the root.
    whole_only : bool
        The verb removes whole simulations (``delete-sims``), so an alias is refused
        and the simulation id it carries is named.

    Returns
    -------
    tuple
        The simulation ids and, per simulation, the point names the aliases name;
        every alias read STRICTLY (the records and the plan must agree).

    Raises
    ------
    AliasError
        An alias with no point, whose two readings disagree, or, with ``whole_only``,
        any alias.
    """
    try:
        rows = json.loads((Path(root) / manifest).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    known: dict[str, Sequence[str]] = {str(row.get("sim_id")): [] for row in rows}
    known.update(planned_from_plan_files(root))
    sims: list[str] = []
    points: dict[str, list[str]] = {}
    for text in items:
        found = resolve_alias(text, rows, known, strict=True)
        if found is None:
            sims.append(text)
        elif whole_only:
            raise AliasError(
                f"sims (CLI: --sims) names {text!r}, a point of simulation {found[0]}, and "
                "this command removes whole simulations; name the simulation "
                f"({found[0]}) to remove all of it. Nothing was done."
            )
        else:
            points.setdefault(found[0], []).append(found[1])
    return sims, points


def _record_sim(record: Any) -> str:
    """Return the simulation id of a failed record, from its field or else from its run id."""
    sim = getattr(record, "sim_id", None)
    if sim is not None:
        return str(sim)
    parts = str(record.run_id).split("/")
    return parts[-2].removeprefix("sim_") if len(parts) > 1 else ""


def failure_alias_lines(failures: Sequence[Any], rows: list[dict[str, Any]]) -> list[str]:
    """Name the run id alias beside each failed run id (FR-395 R3), read from the records.

    Parameters
    ----------
    failures : sequence
        The failed records (each with ``sim_id`` and ``run_id``).
    rows : list of dict
        The manifest rows, as ``CampaignWorkspace.read_raw_manifest`` returns them.

    Returns
    -------
    list of str
        ``"  alias <alias> = <run id>"`` for each failure that has an alias.
    """
    sims: dict[str, list[str]] = {str(row.get("sim_id")): [] for row in rows}
    found = {(sim, tag): alias for alias, sim, tag in alias_lines(rows, sims)}
    return [
        f"  alias {found[key]} = {record.run_id}"
        for record in failures
        if (key := (_record_sim(record), record.run_id.rsplit("/", 1)[-1])) in found
    ]
