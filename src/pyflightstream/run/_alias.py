"""The run id alias of a datapoint, ``<sim>_<index>`` (FR-395, P0350-RUN-ID-ALIAS).

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

# Re-exported through this module for callers using this path.
from pyflightstream.workspace.ledger import SIMS_IDS_HELP as SIMS_IDS_HELP
from pyflightstream.workspace.ledger import listed_sims

#: What joins the simulation id and the index: ``2006_3``.
ALIAS_JOINER = "_"


class AliasError(MatrixError):
    """An alias that names no point, or whose two readings disagree (FR-797)."""


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
        None when ``text`` is not shaped ``<known sim>_<positive integer>`` (ASCII
        digits only), and None when ``text`` is itself a known simulation: a simulation
        id may hold an underscore (``2006_1`` beside ``2006``), and a known id always wins.
    """
    if text.strip() in sims:
        return None
    sim, joiner, number = text.strip().rpartition(ALIAS_JOINER)
    if (
        not joiner
        or not (number.isascii() and number.isdigit())
        or int(number) < 1
        or sim not in sims
    ):
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


#: The ``plan.json`` key holding each simulation's WHOLE sweep, in sweep order.
#: A plan of a selection (``--sims``/``--points``) lists only the selected points
#: under ``points``; an alias is numbered against the whole sweep, as ``run``
#: numbers it, so the plan writes the whole sweep here as well.
PLANNED_ORDER_KEY = "planned_order"


def _plan_order(payload: object) -> dict[str, list[str]]:
    """Return one plan's point names per simulation: its whole sweep, else its points."""
    if not isinstance(payload, Mapping):
        return {}
    found: dict[str, list[str]] = {}
    whole = payload.get(PLANNED_ORDER_KEY)
    if isinstance(whole, Mapping):
        for sim, names in whole.items():
            if isinstance(names, list):
                found[str(sim)] = [str(name) for name in names]
    points = payload.get("points", [])
    for entry in points if isinstance(points, list) else []:
        if isinstance(entry, Mapping) and isinstance(entry.get("run_id"), str):
            tags = found.setdefault(str(entry.get("sim_id")), [])
            tag = entry["run_id"].rsplit("/", 1)[-1]
            if tag not in tags:
                tags.append(tag)
    return found


def planned_by_sim(
    rows: Iterable[Mapping[str, Any]], orders: Iterable[Mapping[str, Sequence[str]]]
) -> dict[str, list[str]]:
    """Return the planned point names of each simulation, the one reading every verb uses.

    Parameters
    ----------
    rows : iterable of mapping
        The manifest's rows; a simulation they record and no plan lists is known,
        with no planned point.
    orders : iterable of mapping of str to sequence of str
        The plans' point names per simulation, first plan first; a later plan adds
        only the names an earlier one lacks.

    Returns
    -------
    dict of str to list of str
        Per simulation, the point names in plan order.
    """
    found: dict[str, list[str]] = {}
    for order in orders:
        for sim, names in order.items():
            tags = found.setdefault(str(sim), [])
            tags.extend(name for name in names if name not in tags)
    for row in rows:
        if isinstance(row, Mapping):
            found.setdefault(str(row.get("sim_id")), [])
    return found


def _plan_file_orders(root: str | Path) -> list[dict[str, list[str]]]:
    """Return the point order of each readable ``plan.json`` of a workspace, root's first."""
    base = Path(root)
    orders: list[dict[str, list[str]]] = []
    for plan_file in [base / "plan.json", *sorted(base.glob("post/*/plan.json"))]:
        try:
            payload = json.loads(plan_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        orders.append(_plan_order(payload))
    return orders


def planned_from_plan_files(root: str | Path) -> dict[str, list[str]]:
    """Return the points each simulation was planned with, read from the ``plan.json`` files.

    Parameters
    ----------
    root : str or Path
        The workspace root; ``plan.json`` is read there and in ``post/<matrix>/``.

    Returns
    -------
    dict of str to list of str
        Per simulation, the point names in the order the (first) plan lists them,
        its whole sweep where the plan wrote one; a file that cannot be read is
        skipped.
    """
    return planned_by_sim((), _plan_file_orders(root))


def planned_in_workspace(
    root: str | Path, rows: Iterable[Mapping[str, Any]]
) -> dict[str, list[str]]:
    """Return the planned point names of each simulation of a workspace (FR-395).

    The ``plan.json`` files and the manifest's simulations, read by
    :func:`planned_by_sim`: what ``show``, ``log``, ``trace``, ``mark-failed``,
    ``mark-converged``, ``delete-sims`` and the failure lines of ``run`` number
    aliases against.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    rows : iterable of mapping
        The manifest's rows.

    Returns
    -------
    dict of str to list of str
        Per simulation, the point names in plan order.
    """
    return planned_by_sim(rows, _plan_file_orders(root))


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
    if strict and not planned:
        raise AliasError(
            f"alias {text!r} cannot be confirmed: the plan evidence for simulation {sim} is "
            f"not there, so the records alone read it as {point!r}. Name the point instead "
            "(sims (CLI: --sims) takes a simulation id; the point name is the end of its "
            "run id). Nothing was done."
        )
    if strict and (number > len(planned) or planned[number - 1] != point):
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
    """Split typed simulation ids from run id aliases, for a verb that destroys (FR-794).

    Parameters
    ----------
    items : sequence of str
        What was typed after ``--sims``: simulation ids and aliases.
    root : str or Path
        The workspace root, whose records and ``plan.json`` files read the aliases.
    manifest : str
        The manifest the verb reads, by name in the root.
    whole_only : bool
        The verb acts on whole simulations (``delete-sims``, ``rebuild``), so an alias
        resolves to the simulation that holds it and acts only when the selection
        names EVERY point of that simulation; a selection that names part of it is
        refused, naming the simulation and its points, so the verb never acts on more
        than was named (PFS-2124.004).

    Returns
    -------
    tuple
        The simulation ids and, per simulation, the point names the aliases name
        (none with ``whole_only``, whose aliases are folded into the simulation ids);
        every alias read STRICTLY (the records and the plan must agree).

    Raises
    ------
    AliasError
        An alias with no point, whose two readings disagree, or, with ``whole_only``,
        aliases that name only part of a simulation's points.
    """
    from pyflightstream.workspace.record_document import read_rows

    rows = read_rows(Path(root) / manifest)
    rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    known = planned_in_workspace(root, rows)
    sims: list[str] = []
    points: dict[str, list[str]] = {}
    named: dict[str, list[tuple[str, str]]] = {}
    for text in items:
        found = resolve_alias(text, rows, known, strict=True)
        if found is None:
            sims.append(text)
        elif whole_only:
            named.setdefault(found[0], []).append((text, found[1]))
        else:
            points.setdefault(found[0], []).append(found[1])
    for sim, entries in named.items():
        every = alias_order(rows, sim, known.get(sim, []))
        left = [point for point in every if point not in {name for _, name in entries}]
        if left and sim not in sims:
            typed = ", ".join(repr(text) for text, _ in entries)
            raise AliasError(
                f"sims (CLI: --sims) names {typed}, {len(entries)} of the {len(every)} "
                f"point(s) of simulation {sim} ({', '.join(every)}), and this command acts "
                "on whole simulations, so it would act on points you did not name. Name every "
                f"point of {sim}, or the simulation ({sim}) to act on all of it. Nothing was done."
            )
        if sim not in sims:
            sims.append(sim)
    return sims, points


def _record_sim(record: Any) -> str:
    """Return the simulation id of a failed record, from its field or else from its run id."""
    sim = getattr(record, "sim_id", None)
    if sim is not None:
        return str(sim)
    parts = str(record.run_id).split("/")
    return parts[-2].removeprefix("sim_") if len(parts) > 1 else ""


def failure_alias_lines(
    failures: Sequence[Any], rows: list[dict[str, Any]], root: str | Path | None = None
) -> list[str]:
    """Name the run id alias beside each failed run id (FR-795).

    Read as every other reader of an alias reads it (:func:`planned_in_workspace`),
    so a failed point recorded out of its sweep order is named by the alias that
    ``--points``, ``show`` and ``mark-failed`` resolve back to it.

    Parameters
    ----------
    failures : sequence
        The failed records (each with ``sim_id`` and ``run_id``).
    rows : list of dict
        The manifest rows, as ``CampaignWorkspace.read_raw_manifest`` returns them.
    root : str or Path, optional
        The workspace root, whose ``plan.json`` files give the sweep order; without
        it the records alone are read, in the order they were recorded.

    Returns
    -------
    list of str
        ``"  alias <alias> = <run id>"`` for each failure that has an alias.
    """
    sims = planned_in_workspace(root, rows) if root is not None else planned_by_sim(rows, ())
    found = {(sim, tag): alias for alias, sim, tag in alias_lines(rows, sims)}
    return [
        f"  alias {found[key]} = {record.run_id}"
        for record in failures
        if (key := (_record_sim(record), record.run_id.rsplit("/", 1)[-1])) in found
    ]


def listed_ids(values: Sequence[str] | None) -> list[str]:
    """Read ids given as words, commas or both, through the one reader of the form.

    Each value is split on whitespace (so one quoted ``"2006 2007"`` reads as two
    ids), the words are joined with commas and read by
    :func:`pyflightstream.workspace.ledger.listed_sims`, so ``2006 2007``,
    ``2006,2007`` and ``[2006,2007]`` read alike; a repeated id is read once.
    """
    return list(
        dict.fromkeys(
            listed_sims(",".join(part for value in values or [] for part in str(value).split()))
        )
    )
