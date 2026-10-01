"""The entity selections of an input artifact, and the refusal of an empty one.

PFS-2005.02. A key whose list selects the entities a command applies to (a
setup's boundary and family lists, an alias of its ``[aliases]`` table, a
pproc's groups and the families of its plot groups and section
distributions) looks like stating no preference when handed an empty list,
and it is not: the command it feeds is either not emitted, which is the
solver's own default and is asked for by dropping the key, or emitted naming
nothing, and either way the run proceeds against a setup nobody selected.
:data:`ENTITY_SELECTIONS` holds one :class:`EntitySelection` per key with the
domain seat's verdict on an empty list (admitted, refused, or not yet decided
and so refused) and its reason, and :func:`refuse_empty_selections` applies it
to a setup or a pproc artifact before its model validates.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.workspace.inputs`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyflightstream._errors import InputArtifactError

__all__ = [
    "ALIASES_TABLE",
    "ENTITY_SELECTIONS",
    "EntitySelection",
    "refuse_empty_selections",
]


#: The table of a setup artifact that names groups of boundaries (the reference
#: decision of 2026-09-09): ``[aliases]``, one key per alias, a list of
#: boundary names or families. Read by the documentation. Its home is here,
#: beside the selection rule that reads it, since 0.33.0 (AD-11); the setup
#: reader of :mod:`pyflightstream.workspace.inputs` imports it from here.
ALIASES_TABLE = "aliases"


@dataclass(frozen=True)
class EntitySelection:
    """One artifact key whose list selects the entities a command applies to.

    PFS-2005.02. Handing such a key an empty list looks like stating no
    preference, and it is not: the command the list feeds is either not
    emitted at all, which is the solver's own default and is asked for
    by dropping the key, or emitted naming nothing, and either way the
    run proceeds against a setup nobody selected and still reports
    numbers. Whether an empty list can mean anything is decided one key
    at a time, by the domain seat, and the decision is written beside
    the key so the refusal can say whose it is.

    Attributes
    ----------
    kind : str
        The artifact kind the key lives in, ``setup`` or ``pproc``.
    key : str
        The key as the file spells it; a placeholder marks a table whose
        every entry is a selection (``groups.<name>``) or a list of
        tables (``plots.groups[].families``).
    consumer : str
        What the list feeds: the FlightStream command, or the product
        this package writes from it.
    empty_admitted : bool or None
        True where an empty list has a documented meaning and is
        accepted, False where it is refused on the manual's word, and
        None where the domain seat has not yet decided, in which case it
        is refused until the owning seat rules.
    reason : str
        The sentence the refusal prints beside the verdict: what the
        manual says, or that nothing does yet.
    """

    kind: str
    key: str
    consumer: str
    empty_admitted: bool | None
    reason: str


_VORTICITY_EMPTY = (
    "The solver's default, surface pressure integration on every boundary, is "
    "expressed by never emitting the command (SRC-003 p.202), so a stated empty list "
    "asks for a selection and names none, and the run would converge and publish "
    "induced drag against a setup nobody selected."
)

_ANALYSIS_EMPTY = (
    "The command enables the boundaries it lists and leaves every other one out of the "
    "analysis (SRC-003 p.351), and every boundary entering the loads, the solver's "
    "default, is expressed by never emitting it; so a stated empty list asks for a "
    "selection and names none, and the loads table would sum a setup nobody selected."
)

#: Every artifact key that selects entities, with the domain seat's verdict on
#: an empty list beside it. The readers consult this table; the docs page
#: repeats it. A key that is not here is not an entity selection, and a new
#: one enters here with its verdict before its reader accepts it.
ENTITY_SELECTIONS: tuple[EntitySelection, ...] = (
    EntitySelection(
        "setup",
        "vorticity_drag_boundaries",
        "SET_VORTICITY_DRAG_BOUNDARIES",
        False,
        _VORTICITY_EMPTY,
    ),
    EntitySelection(
        "setup",
        "set_vorticity_drag_boundaries",
        "SET_VORTICITY_DRAG_BOUNDARIES",
        False,
        _VORTICITY_EMPTY,
    ),
    EntitySelection(
        "setup", "vorticity_drag_families", "SET_VORTICITY_DRAG_BOUNDARIES", False, _VORTICITY_EMPTY
    ),
    EntitySelection(
        "setup", "analysis_families", "SET_SOLVER_ANALYSIS_BOUNDARIES", False, _ANALYSIS_EMPTY
    ),
    EntitySelection(
        "setup",
        "set_solver_analysis_boundaries",
        "SET_SOLVER_ANALYSIS_BOUNDARIES",
        False,
        _ANALYSIS_EMPTY,
    ),
    EntitySelection(
        "setup",
        "aliases.<name>",
        "every boundary-citing key of a row naming this preset",
        False,
        "An alias stands for the boundary names or families listed after it, and over none "
        "it would name nothing while reading as though it named a set; the empty list that "
        "means every family is the pproc group's, one line below.",
    ),
    EntitySelection(
        "pproc",
        "groups.<name>",
        "the polar table written per group (products.polars)",
        True,
        "An empty group is every family the geometry carries, the design decision of "
        "2026-09-09: the polar table sums every surface row of the loads table, and a "
        "motion naming the group moves every boundary of the file.",
    ),
    EntitySelection(
        "pproc",
        "plots.groups[].families",
        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
        False,
        "The entry exists to emit one plot per parameter over the families it names; "
        "over none it would emit nothing while reading as though it had. A family "
        "the geometry does not carry is left out at emission, which is the documented "
        "way an entry resolves to fewer families than it names.",
    ),
    EntitySelection(
        "pproc",
        "sections.distributions[].families",
        "NEW_SURFACE_SECTION_DISTRIBUTION",
        False,
        "The entry exists to emit one distribution per plane over the families it "
        "names; over none it would emit nothing while reading as though it had. A "
        "family the geometry does not carry is left out at emission, which is the "
        "documented way an entry resolves to fewer families than it names.",
    ),
    EntitySelection(
        "pproc",
        "base_regions",
        "DETECT_BASE_REGIONS_BY_SURFACE",
        True,
        "An empty list is the documented off switch of the base-region autodetect "
        "(PFS-2029.10): none means no detection, and the row's BASE_REGIONS key is "
        "how one row turns it on.",
    ),
)

_SELECTION_BY_KEY = {(rule.kind, rule.key): rule for rule in ENTITY_SELECTIONS}


def _stated_empty_selections(
    kind: str, data: Mapping[str, Any]
) -> list[tuple[str, EntitySelection]]:
    """Return every entity-selecting key the file states as an empty list.

    Walks the shapes the table names: a plain key of a setup, the
    ``[groups]`` table of a pproc artifact, and the ``families`` of its
    plot groups and section distributions. Returns the key as the file
    spells it beside the table entry that judges it.
    """
    found: list[tuple[str, EntitySelection]] = []
    if kind == "setup":
        for rule in ENTITY_SELECTIONS:
            if rule.kind == kind and data.get(rule.key) == []:
                found.append((rule.key, rule))
        aliases = data.get(ALIASES_TABLE)
        if isinstance(aliases, Mapping):
            rule = _SELECTION_BY_KEY[("setup", "aliases.<name>")]
            found.extend(
                (f'{ALIASES_TABLE}."{name}"', rule)
                for name, members in aliases.items()
                if members == []
            )
        return found
    groups = data.get("groups")
    if isinstance(groups, Mapping):
        for name, members in groups.items():
            if members == []:
                found.append((f'groups."{name}"', _SELECTION_BY_KEY[("pproc", "groups.<name>")]))
    for table, entries, key in (
        ("plots", "groups", "plots.groups[].families"),
        ("sections", "distributions", "sections.distributions[].families"),
    ):
        section = data.get(table)
        listed = section.get(entries) if isinstance(section, Mapping) else None
        if not isinstance(listed, list):
            continue
        for position, entry in enumerate(listed):
            if isinstance(entry, Mapping) and entry.get("families") == []:
                found.append(
                    (f"{table}.{entries}[{position}].families", _SELECTION_BY_KEY[("pproc", key)])
                )
    return found


def refuse_empty_selections(kind: str, path: Path, data: Mapping[str, Any]) -> None:
    """Refuse an artifact stating an empty list for an entity-selecting key.

    PFS-2005.02. Called by the readers before the model validates, so the
    refusal names the artifact FILE, the key as the file spells it, and
    what the empty list would have disabled, with the domain seat's
    verdict beside it. The model's own validators stay: they guard the
    Python path, and this guards the file a matrix row names.

    Parameters
    ----------
    kind : str
        ``setup`` or ``pproc``.
    path : Path
        The artifact file, for the message.
    data : mapping
        The file's TOML table as loaded.

    Raises
    ------
    InputArtifactError
        The first key stated empty whose verdict is not "admitted".
    """
    for key, rule in _stated_empty_selections(kind, data):
        if rule.empty_admitted:
            continue
        if rule.empty_admitted is None:
            verdict = (
                "Whether an empty list can mean anything here is the domain seat's call, "
                "not yet decided, and it is refused until that is settled"
            )
        else:
            verdict = "An empty list is refused"
        raise InputArtifactError(
            f"the {kind} artifact {path} states {key} = [], an empty list, and that list "
            f"selects what {rule.consumer} applies to. {rule.reason} {verdict}. Name the "
            "entities, or drop the key."
        )
