"""What a refinement is asked to do: the arguments and the refinement file (FR-915 to FR-917).

The factors come from the call (FACTOR, ``--parallel``, ``--normal``) or,
when the call gives none, from the refinement file: ``--config FILE`` or
``<stem>.refine.toml`` beside the mesh. The file's ``[components]``,
``[refine] tag`` and the element modes (``[refine] elements``
and each family's ``elements``) are read whenever the file exists, whatever
gives the factors. ``families`` selects the families to change on either
route: from the call's factors, or from the file's tables, whose unselected
tables are then not read. A file table whose factors are not read is a
warning naming it, and ``refine.json`` lists it. Every refusal names the
file, the table and the key, lists the known keys, and is raised before any
family is touched.

THE ELEMENT MODE of a remeshed family is ``"triangles"`` (the default) or
``"quad-dominant"`` (its triangles are then paired into quadrilaterals,
:mod:`._remesh`). ``[refine] elements`` gives the mode of every remeshed
family, and a family's own ``elements`` replaces it for that family; a table
may state ``elements`` alone. A grid family keeps its cells: ``elements`` in a
table that states ``method = "grid"`` is refused, and a mode that reaches a
family resolved to a grid under ``"auto"`` is ignored and ``refine.json`` says
so.
"""

from __future__ import annotations

import hashlib
import math
import tomllib
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace._refine._geometry import TE_POINT_FRACTION
from pyflightstream.workspace._refine._obj import KIND

#: The methods a family may state (FR-923).
METHODS = ("auto", "grid", "remesh")
#: The element mode of a remeshed family that states none (today's triangles).
TRIANGLES = "triangles"
#: The element mode whose triangles are paired into quadrilaterals after the remesh.
QUAD_DOMINANT = "quad-dominant"
#: The element modes a remeshed family may state, the default first.
ELEMENTS = (TRIANGLES, QUAD_DOMINANT)
#: The keys of a ``[families.<name>]`` table.
FAMILY_KEYS = (
    "factor",
    "parallel_factor",
    "normal_factor",
    "method",
    "elements",
)
#: Keys a [families.<name>] table may still state from earlier releases; each is warned
#: and skipped: a row kept at an interface is a family of its own.
RETIRED_FAMILY_KEYS = (
    "keep_first_row",
    "trailing_edge_direction",
    "axial",
    "circumferential",
    "axis",
    "origin",
)
#: The earlier names of a grid's two factors, still read with a warning: the factor
#: along the reference perimeter (``spanwise``) and the one across it (``chordwise``).
FACTOR_ALIASES = {"spanwise": "parallel_factor", "chordwise": "normal_factor"}
#: The keys of a ``[[perimeter]]`` table: one ANSA node list of reference perimeters.
PERIMETER_KEYS = ("file", "export_te_per_family", "te_families", "aft")
#: The keys of ``[refine]``.
REFINE_KEYS = ("tag", "filename", "elements")
#: The top-level tables of a refinement file.
TABLES = ("refine", "families", "components", "perimeter")
#: Tables a refinement file may still state from earlier releases; each is warned and skipped.
RETIRED_TABLES = ("trailing_edge", "periodic")


@dataclass(frozen=True)
class FamilySpec:
    """How one family is refined: its factors and its method.

    ``spanwise`` holds the ``parallel_factor`` (along the reference perimeter)
    and ``chordwise`` the ``normal_factor`` (across it); the level's tag and
    the canonical selection keep these names, so a level's folder is unchanged.
    """

    factor: float = 1.0
    chordwise: float | None = None
    spanwise: float | None = None
    method: str = "auto"

    @property
    def directions(self) -> tuple[float, float]:
        """Return the chordwise and spanwise factors of a grid (each falls back to the factor)."""
        return (
            self.factor if self.chordwise is None else self.chordwise,
            self.factor if self.spanwise is None else self.spanwise,
        )

    @property
    def unchanged(self) -> bool:
        """Return whether every factor this spec states is 1."""
        return all(v == 1.0 for v in (self.factor, *self.directions))


@dataclass(frozen=True)
class Perimeter:
    """One ``[[perimeter]]``: an ANSA SET node list whose lines orient the grids it lies on.

    With ``export_te_per_family`` its lines are trailing edges too, written per
    family into the level as ``<level>.<family>.te.txt``. With ``te_families``
    only the rearmost lines of those families are (:func:`._obj.rearmost_edges`,
    ``aft`` the direction from the nose to the tail), written per output family.
    """

    file: Path
    export_te_per_family: bool = False
    te_families: tuple[str, ...] = ()
    aft: tuple[float, float, float] = (1.0, 0.0, 0.0)

    @property
    def exported(self) -> bool:
        """Return whether some of the list's lines are written as trailing edges."""
        return self.export_te_per_family or bool(self.te_families)


@dataclass(frozen=True)
class RefineRequest:
    """Everything a refinement was asked: specs, tag, components and element modes.

    ``elements`` holds the modes the file states per family, and
    ``default_elements`` the mode of ``[refine] elements`` (else triangles).
    ``ignored`` names the families whose ``[families.<name>]`` table states
    factors the refinement does not read: every one when the call gives the
    factors, and the unselected ones when ``families`` selects from the
    file's factors.
    """

    specs: dict[str, FamilySpec]
    tag: str | None = None
    #: The level's name, ``[refine] filename`` without ``.obj``: the folder and the OBJ
    #: are ``<filename>`` instead of ``<stem>_<tag>``.
    filename: str | None = None
    components: dict[str, list[str]] = field(default_factory=dict)
    config: Path | None = None
    elements: dict[str, str] = field(default_factory=dict)
    default_elements: str = TRIANGLES
    ignored: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    #: How close a listed point lies to the mid-point of the edge it names, as a fraction
    #: of the mesh size; ``refine.json`` records it for the audit's G4.
    point_fraction: float = TE_POINT_FRACTION
    perimeters: tuple[Perimeter, ...] = ()
    accept_remesh: bool = False
    #: Raise a grid factor below the least its grid allows to that least, with a
    #: warning, instead of refusing it (CLI ``--force-factors``).
    force_factors: bool = False

    def elements_of(self, family: str) -> str:
        """Return the element mode of a family: its own, else the file's default."""
        return self.elements.get(family, self.default_elements)


def _refuse(where: str, reason: str) -> InputArtifactError:
    """Return a refusal of the request: where, why, and that nothing was written."""
    return InputArtifactError(f"{where}: {reason}. Nothing was written.", kind=KIND)


#: The characters a level's folder name never holds (FR-919): the path separators,
#: the drive colon and the characters Windows reserves in a file name.
UNSAFE_CHARACTERS = '/\\:<>"|?*'


def folder_name_problem(name: str) -> str | None:
    """Return why ``name`` is not one portable folder name, or None when it is (FR-919).

    A name holding a path separator, a drive colon, a character Windows
    reserves, a control character or ``..``, a name that is ``.``, and a name
    ending with a dot or a space (which Windows drops, naming another folder)
    are not one.
    """
    bad = sorted({c for c in name if c in UNSAFE_CHARACTERS or ord(c) < 32})
    if bad:
        return f"holds {' '.join(repr(c) for c in bad)}"
    if name == "." or ".." in name:
        return "is . or holds .."
    if name != name.rstrip(". "):
        return "ends with a dot or a space"
    return None


def positive(where: str, value: Any) -> float:
    """Return a factor as a float, refusing anything but a finite number above zero (FR-915)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _refuse(where, f"the factor {value!r} is not a number; give a number above zero")
    try:
        number = float(value)
    except OverflowError:
        raise _refuse(where, "the factor is too large a number; give a finite number") from None
    if not math.isfinite(number) or number <= 0.0:
        raise _refuse(where, f"the factor {number:g} is not above zero; give a number above zero")
    return number


def _vector(where: str, value: Any, *, nonzero: bool) -> tuple[float, float, float]:
    ok = isinstance(value, list | tuple) and len(value) == 3
    ok = ok and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)
    try:
        numbers = tuple(float(v) for v in value) if ok else ()
    except OverflowError:
        raise _refuse(
            where, "a component is too large a number; give three finite numbers"
        ) from None
    if not ok or not all(math.isfinite(v) for v in numbers):
        raise _refuse(where, f"{value!r} is not three finite numbers")
    if nonzero and not any(numbers):
        raise _refuse(where, "the axis is zero; give a direction")
    return numbers[0], numbers[1], numbers[2]


def elements_mode(where: str, value: Any, accept: bool = False) -> str:
    """Return an element mode, refusing anything but one of :data:`ELEMENTS`.

    Under ``accept`` another value is warned and skipped: triangles are taken.
    """
    if value not in ELEMENTS:
        _unknown(
            f"{where} elements",
            f"{value!r} is not an element mode; the modes are {', '.join(ELEMENTS)}",
            accept,
        )
        return TRIANGLES
    return str(value)


def _unknown(where: str, reason: str, accept: bool) -> None:
    """Refuse an entry the refinement does not know or cannot read, or warn and skip it.

    ``accept`` (``accept_unknown``, CLI ``--accept-unknown``) chooses the warning.
    """
    if not accept:
        raise _refuse(where, reason)
    _skip(where, reason)


DIRECTIONAL_KEYS = ("parallel_factor", "normal_factor")


def _family_spec(where: str, table: Mapping[str, Any], accept: bool = False) -> FamilySpec | None:
    """Return a family's spec, refusing what cannot be read, or None for a table skipped whole.

    Under ``accept`` a key the refinement cannot read is warned and skipped
    (its default taken); a table left with no factor is warned and skipped.
    """
    table = _renamed_factors(where, table)
    unknown = sorted(set(table) - set(FAMILY_KEYS))
    if unknown:
        _unknown(
            where,
            f"unknown key {unknown[0]!r}; the known keys are {', '.join(FAMILY_KEYS)}",
            accept,
        )
        table = {k: v for k, v in table.items() if k in FAMILY_KEYS}
    method = table.get("method", "auto")
    if method not in METHODS:
        _unknown(f"{where} method", f"{method!r} is not one of {', '.join(METHODS)}", accept)
        method = "auto"
    if "elements" in table and method == "grid":
        _unknown(
            f"{where} elements",
            "elements applies to a remeshed family; a grid keeps its cells",
            accept,
        )
    table = {k: v for k, v in table.items() if k != "elements"}
    if not any(k in table for k in ("factor", *DIRECTIONAL_KEYS)):
        _unknown(
            where,
            "the table states no factor, parallel_factor or normal_factor; add one of them to it",
            accept,
        )
        return None
    if method == "remesh" and any(k in table for k in DIRECTIONAL_KEYS):
        _unknown(
            where,
            "parallel_factor and normal_factor apply to a grid; a remeshed family takes factor",
            accept,
        )
        table = {k: v for k, v in table.items() if k not in DIRECTIONAL_KEYS}
    factors = _read_factors(where, table, accept)
    if not factors:
        _skip(where, "states no factor that can be read")
        return None
    return FamilySpec(
        factor=factors.get("factor", 1.0),
        chordwise=factors.get("normal_factor"),
        spanwise=factors.get("parallel_factor"),
        method=method,
    )


def _read_factors(where: str, table: Mapping[str, Any], accept: bool) -> dict[str, float]:
    """Return the factor keys a table states, each read as a number above zero.

    Under ``accept`` a factor that is not one is warned and skipped.
    """
    factors: dict[str, float] = {}
    for key in ("factor", *DIRECTIONAL_KEYS):
        if key not in table:
            continue
        try:
            factors[key] = positive(f"{where} {key}", table[key])
        except InputArtifactError:
            if not accept:
                raise
            _skip(f"{where} {key}", f"{table[key]!r} is not a number above zero")
    return factors


def _renamed_factors(where: str, table: Mapping[str, Any]) -> dict[str, Any]:
    """Return a family table with ``chordwise`` and ``spanwise`` read as their new names.

    An earlier name is warned and read; beside its new name it is warned and skipped.
    """
    out = dict(table)
    for old, new in FACTOR_ALIASES.items():
        if old not in out:
            continue
        value = out.pop(old)
        if new in out:
            text = f"{where}: {old} is skipped; {new} is stated and gives the factor"
        else:
            text = f"{where}: {old} is read as {new}; rename the key to {new}"
            out[new] = value
        warnings.warn(text, PyflightstreamWarning, stacklevel=4)
    return out


def _components(
    path: Path, raw: Any, names: Sequence[str], accept: bool = False
) -> dict[str, list[str]]:
    """Return ``[components]`` checked against the mesh's families (FR-935).

    A member the mesh does not hold is refused, or warned and left out under
    ``accept``; a component left without a member is then skipped.
    """
    where = f"{path} [components]"
    if not isinstance(raw, dict):
        raise _refuse(where, "the table must map a component name to a list of families")
    seen: dict[str, str] = {}
    out: dict[str, list[str]] = {}
    for name, members in raw.items():
        if (
            not isinstance(members, list)
            or not members
            or not all(isinstance(m, str) for m in members)
        ):
            raise _refuse(f"{where} {name}", "give a non-empty list of family names")
        missing = [m for m in members if m not in names]
        if missing:
            _unknown(
                f"{where} {name}",
                f"the mesh holds no family {missing[0]!r}; it holds {', '.join(names)}",
                accept,
            )
            members = [m for m in members if m not in missing]
            if not members:
                _skip(f"{where} {name}", "names no family of the mesh")
                continue
        for m in members:
            if m in seen:
                raise _refuse(f"{where} {name}", f"family {m!r} is also in component {seen[m]!r}")
            seen[m] = name
        if name in names and name not in members:
            raise _refuse(
                f"{where} {name}", "a family of the mesh already has this name and is not a member"
            )
        out[name] = list(members)
    return out


def _keys(kind: str, names: Sequence[str]) -> str:
    """Return ``unknown key a`` or ``unknown keys a, b`` (empty when there is none)."""
    if not names:
        return ""
    return f"{kind} key{'s' if len(names) > 1 else ''} {', '.join(names)}"


def _table(where: str, value: Any, remedy: str) -> dict[str, Any]:
    """Return a TOML table, refusing a value of another shape (a number, a list, false)."""
    if not isinstance(value, dict):
        raise _refuse(where, f"the value {value!r} is not a table; {remedy}")
    return value


def _family_tables(
    source: Path,
    families: Mapping[str, Any],
    names: Sequence[str],
    read: Sequence[str] | None = None,
    accept: bool = False,
) -> tuple[dict[str, FamilySpec], dict[str, str], list[str]]:
    """Return the specs, element modes and unread tables of ``[families.<name>]``.

    ``read`` names the families whose factors are read; a table of any other
    family is checked for its name and its ``elements`` only (F-1516), and
    ``None`` reads them all. Under ``accept`` a table of a family the mesh
    does not hold, and an unknown key, are warned and skipped.
    """
    specs: dict[str, FamilySpec] = {}
    elements: dict[str, str] = {}
    unread: list[str] = []
    for name, raw in families.items():
        where = f"{source} [families.{name}]"
        table = _table(
            where, raw, f"write [families.{name}] with the keys {', '.join(FAMILY_KEYS)}"
        )
        if name not in names:
            _unknown(
                where, f"the mesh holds no family {name!r}; it holds {', '.join(names)}", accept
            )
            continue
        table = _without_retired(where, table)
        if not table:
            continue
        if "elements" in table:
            elements[name] = elements_mode(where, table["elements"], accept)
        if read is not None and name not in read:
            _check_unread(where, table, accept)
            if set(table) != {"elements"}:
                unread.append(name)
            continue
        if set(table) - {"elements"}:
            spec = _family_spec(where, table, accept)
            if spec is not None:
                specs[name] = spec
    return specs, elements, unread


def _without_retired(where: str, table: Mapping[str, Any]) -> dict[str, Any]:
    """Return a family table without its retired keys, each warned and skipped."""
    for key in RETIRED_FAMILY_KEYS:
        if key in table:
            _skip(f"{where} {key}", "is no longer read")
    return {k: v for k, v in table.items() if k not in RETIRED_FAMILY_KEYS}


def _check_unread(where: str, table: Mapping[str, Any], accept: bool = False) -> None:
    """Refuse ``elements`` on a grid in a table whose factors are not read (F-1516)."""
    if "elements" in table and table.get("method") == "grid":
        _unknown(
            f"{where} elements",
            "elements applies to a remeshed family; a grid keeps its cells",
            accept,
        )


def read_refine_file(
    path: str | Path,
    names: Sequence[str],
    mesh: str | Path | None = None,
    read: Sequence[str] | None = None,
    *,
    accept_unknown: bool = False,
) -> dict[str, Any]:
    """Read a refinement file against the mesh's family names, refusing what it cannot honour.

    ``read`` names the families whose factors are read: the other tables are
    not validated beyond their name and ``elements`` (F-1516). ``mesh`` is
    accepted for the callers that name it and is not read. Under
    ``accept_unknown`` an entry the refinement does not know (a table, a key,
    a family the mesh does not hold) or cannot read (a factor that is not a
    number above zero, an element mode or a method that is none, a key that
    contradicts the method, a tag that is not one folder name) is warned and
    skipped instead of refused: the key takes its default, a table left with
    no factor is skipped, and the tag falls back to the built one.
    """
    source = Path(path)
    try:
        data = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        # Not UTF-8 text is a refusal like any unreadable file (PFS-2099.004).
        raise _refuse(str(source), f"the refinement file cannot be read ({error})") from error
    unknown = sorted(set(data) - set(TABLES) - set(RETIRED_TABLES))
    if unknown:
        _unknown(
            str(source),
            f"unknown table [{unknown[0]}]; the tables are {', '.join(TABLES)}",
            accept_unknown,
        )
    families = _table(
        f"{source} [families]",
        data.get("families", {}),
        f"write one [families.<name>] table per family, with the keys {', '.join(FAMILY_KEYS)}",
    )
    specs, elements, unread = _family_tables(source, families, names, read, accept_unknown)
    refine = _table(
        f"{source} [refine]",
        data.get("refine", {}),
        f"write [refine] with the keys {', '.join(REFINE_KEYS)}",
    )
    unknown = sorted(set(refine) - set(REFINE_KEYS))
    if unknown:
        _unknown(
            f"{source} [refine]",
            f"unknown key {unknown[0]!r}; the known keys are {', '.join(REFINE_KEYS)}",
            accept_unknown,
        )
    tag = refine.get("tag")
    if tag is not None and (not isinstance(tag, str) or not tag):
        _unknown(
            f"{source} [refine] tag",
            f'{tag!r} is not a text; give the tag as a non-empty string, such as tag = "fine"',
            accept_unknown,
        )
        tag = None
    problem = None if tag is None else folder_name_problem(tag)
    if problem is not None:
        _unknown(
            f"{source} [refine] tag",
            f'{tag!r} {problem}, so it is not one folder name (no / \\ : < > " | ? *, no .., '
            "not ending with a dot or a space); the level folder is <stem>_<tag> beside the "
            'source\'s folder, so give a name such as tag = "fine"',
            accept_unknown,
        )
        tag = None
    default = refine.get("elements", TRIANGLES)
    filename = _filename(source, refine.get("filename"))
    _trailing_edge(source, data.get("trailing_edge", {}))
    if "periodic" in data:
        _skip(f"{source} [periodic]", "is no longer read; a periodic sector is refined as any mesh")
    return {
        "perimeters": _perimeters(source, data.get("perimeter", [])),
        "specs": specs,
        "unread": unread,
        "elements": elements,
        "default_elements": elements_mode(f"{source} [refine]", default, accept_unknown),
        "tag": tag,
        "filename": filename,
        "components": _components(source, data.get("components", {}), names, accept_unknown),
    }


def _trailing_edge(source: Path, value: object) -> None:
    """Warn that ``[trailing_edge]`` is no longer read: the trailing edges are ``[[perimeter]]``."""
    if value:
        _skip(
            f"{source} [trailing_edge]",
            "is no longer read; list the trailing-edge nodes in a [[perimeter]] file with "
            "export_te_per_family = true",
        )


def _perimeters(source: Path, value: object) -> tuple[Perimeter, ...]:
    """Return the ``[[perimeter]]`` tables; a table that cannot be read is warned and skipped."""
    tables = value if isinstance(value, list) else [value]
    out = []
    for number, table in enumerate(tables, start=1):
        where = f"{source} [[perimeter]] {number}"
        if not isinstance(table, dict):
            _skip(where, "is not a table with file and export_te_per_family")
            continue
        for key in sorted(set(table) - set(PERIMETER_KEYS)):
            _skip(f"{where} {key}", f"is not a key; the keys are {', '.join(PERIMETER_KEYS)}")
        named = table.get("file")
        if not isinstance(named, str) or not named.strip():
            _skip(where, "states no file, the node list saved from an ANSA SET")
            continue
        export = table.get("export_te_per_family", False)
        if not isinstance(export, bool):
            _skip(f"{where} export_te_per_family", "is not true or false; false is taken")
            export = False
        chosen = table.get("te_families", [])
        if not isinstance(chosen, list) or not all(isinstance(n, str) for n in chosen):
            _skip(f"{where} te_families", "is not a list of family names")
            chosen = []
        aft = (1.0, 0.0, 0.0)
        if "aft" in table:
            try:
                aft = _vector(f"{where} aft", table["aft"], nonzero=True)
            except InputArtifactError:
                _skip(f"{where} aft", "is not three numbers, not all zero; +x is taken")
        out.append(Perimeter(source.parent / named, export, tuple(chosen), aft))
    return tuple(out)


def _filename(source: Path, value: object) -> str | None:
    """Return ``[refine] filename`` without ``.obj``; a name that is not one is warned, skipped."""
    if value is None:
        return None
    where = f"{source} [refine] filename"
    if not isinstance(value, str) or not value.strip():
        _skip(where, f"{value!r} is not a text; the level is named by its tag")
        return None
    name = value.strip()
    if name.lower().endswith(".obj"):
        name = name[:-4]
    problem = folder_name_problem(name) if name else "is empty"
    if problem is not None:
        _skip(
            where, f"{value!r} {problem}, so it is not one file name; the level is named by its tag"
        )
        return None
    return name


def _skip(where: str, reason: str) -> None:
    warnings.warn(f"{where} {reason}; it is skipped", PyflightstreamWarning, stacklevel=4)


def refine_file_of(mesh: Path, config: str | Path | None) -> Path | None:
    """Return the refinement file: the stated one, else ``<stem>.refine.toml`` if present."""
    if config is not None:
        path = Path(config)
        if not path.is_file():
            raise _refuse(str(path), "the refinement file does not exist")
        return path
    beside = mesh.with_name(mesh.stem + ".refine.toml")
    return beside if beside.is_file() else None


def resolve_request(  # noqa: PLR0913 (the call's own keywords, one per command option)
    mesh: Path,
    names: Sequence[str],
    *,
    factor: float | None = None,
    families: Sequence[str] | None = None,
    parallel: float | None = None,
    normal: float | None = None,
    config: str | Path | None = None,
    keep_first_row: Sequence[str] | None = None,
    accept_remesh: bool = False,
    accept_unknown: bool = False,
    force_factors: bool = False,
) -> RefineRequest:
    """Return what the refinement is asked, from the call and the refinement file (FR-916).

    ``keep_first_row``, an earlier option, is warned and skipped when given.
    Under ``accept_unknown`` a selected family the mesh does not hold, and an
    unknown entry of the refinement file, are warned and skipped.
    """
    file = refine_file_of(mesh, config)
    from_file = factor is None and parallel is None and normal is None
    chosen = list(names) if families is None else list(families)
    missing = [n for n in chosen if n not in names]
    if missing and accept_unknown:
        _skip(f"{mesh} families {', '.join(missing)}", "not held by the mesh")
        chosen = [n for n in chosen if n in names]
    stated = _stated(
        file, names, mesh, chosen if from_file else [], config=config, accept=accept_unknown
    )
    # AN EMPTY SELECTION SELECTS NOTHING TO CHANGE (PFS-2099.005): on the factor route it
    # wrote an unchanged copy of the source as a level tagged R-.
    if not chosen:
        raise _refuse(
            str(mesh),
            "no family is selected; name at least one in families (CLI: --families), "
            "or omit it to refine every family",
        )
    if missing and not accept_unknown:
        raise _refuse(
            str(mesh), f"the mesh holds no family {missing[0]!r}; it holds {', '.join(names)}"
        )
    stated_specs: dict[str, FamilySpec] = stated["specs"]
    missing_tables: tuple[str, ...] = ()
    if from_file:
        if not stated_specs and not stated["unread"]:
            raise _refuse(
                str(mesh),
                "no factor was given and no refinement file states one; give FACTOR "
                f"or add a [families.<name>] factor table to "
                f"{file if file is not None else mesh.with_name(mesh.stem + '.refine.toml')}",
            )
        specs = {n: s for n, s in stated_specs.items() if n in chosen}
        if not specs:
            raise _refuse(
                str(file),
                f"the refinement file states no factor for the selected families "
                f"{', '.join(chosen)}; add a [families.<name>] table for one of them, "
                "or give FACTOR",
            )
        reason = f"--families selects {', '.join(chosen)}"
        missing_tables = tuple(n for n in chosen if n not in stated_specs)
        for name in missing_tables:
            warnings.warn(
                f"{file}: selected family {name!r} has no refinement table and is copied "
                f"unchanged; add [families.{name}] to {file}, or give FACTOR.",
                PyflightstreamWarning,
                stacklevel=3,
            )
        ignored = tuple(n for n in (*stated_specs, *stated["unread"]) if n not in specs)
    else:
        base = positive(f"{mesh} FACTOR", 1.0 if factor is None else factor)
        specs = {
            n: FamilySpec(
                factor=base,
                chordwise=None if normal is None else positive(f"{mesh} --normal", normal),
                spanwise=None if parallel is None else positive(f"{mesh} --parallel", parallel),
            )
            for n in chosen
        }
        reason = "FACTOR, --parallel or --normal gives the factors (FR-916)"
        ignored = (*stated_specs, *stated["unread"])
    if ignored:
        tables = ", ".join(f"[families.{n}]" for n in ignored)
        warnings.warn(
            f"{file}: the tables {tables} are not read for their factors and methods, "
            f"because {reason}; an elements key in them still applies.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if keep_first_row:
        _skip(f"{mesh} keep_first_row", "is no longer read; keep such a row as a family of its own")
    return RefineRequest(
        specs=specs,
        tag=stated["tag"],
        filename=stated["filename"],
        components=stated["components"],
        config=file,
        elements=stated["elements"],
        default_elements=stated["default_elements"],
        ignored=ignored,
        missing=missing_tables,
        accept_remesh=accept_remesh,
        force_factors=force_factors,
        perimeters=stated.get("perimeters", ()),
    )


def _stated(
    file: Path | None,
    names: Sequence[str],
    mesh: Path,
    read: Sequence[str],
    *,
    config: str | Path | None,
    accept: bool,
) -> dict[str, Any]:
    """Return what the refinement file states, or the empty statement without one.

    An implicit ``<stem>.refine.toml`` that cannot be read is refused, or
    under ``accept_unknown`` warned and skipped as if absent; a file named by
    ``config`` that cannot be read is refused either way.
    """
    empty: dict[str, Any] = {
        "specs": {},
        "unread": [],
        "elements": {},
        "default_elements": TRIANGLES,
        "tag": None,
        "filename": None,
        "components": {},
    }
    if file is None:
        return empty
    try:
        return read_refine_file(file, names, mesh, read, accept_unknown=accept)
    except InputArtifactError as error:
        if config is not None or not accept or "cannot be read" not in str(error):
            raise
        _skip(str(file), "cannot be read and is not named by config (CLI: --config)")
        return empty


def _fmt(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def spec_tag(spec: FamilySpec) -> str:
    """Return a family's part of a level's tag (FR-919): the factor, then ``c`` and ``s`` ones."""
    tag = _fmt(spec.factor)
    if spec.chordwise is not None:
        tag += f"c{_fmt(spec.chordwise)}"
    if spec.spanwise is not None:
        tag += f"s{_fmt(spec.spanwise)}"
    return tag


#: Maximum length for an unsummarised built tag (FR-970).
TAG_MAX = 32


def _built_tag(request: RefineRequest, names: Sequence[str]) -> tuple[str, list[str], bool]:
    """Return the built tag, the selected families in the source's order, and whether it is uniform.

    A uniform tag, ``R<factors>``, is one factor on every family of the mesh:
    it holds no family name.
    """
    tags = {n: spec_tag(s) for n, s in request.specs.items()}
    picked = [n for n in names if n in request.specs]
    if set(request.specs) == set(names) and len(set(tags.values())) == 1:
        return "R" + next(iter(tags.values())), picked, True
    return "R-" + "-".join(f"{n}{tags[n]}" for n in picked), picked, False


def _value(value: object) -> str:
    """Return one option value as the canonical selection writes it (FR-970, FR-971).

    A number is written in the shortest text that reads back to the same
    float (:func:`repr`), without a trailing ``.0``, so two factors that
    differ in any digit give two texts (``1.000001`` and ``1.000002``) and a
    whole factor is written as ``2``. The short tag keeps its own spelling.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        text = repr(value)
        return text[:-2] if text.endswith(".0") else text
    return str(value)


def canonical_selection(request: RefineRequest, picked: Sequence[str]) -> str:
    """Return the canonical selection a summary tag hashes (FR-970).

    One line per selected family, in the source's order: the family's name,
    then every option its table states that changes the level, as sorted
    ``key=value`` pairs separated by single spaces.
    """
    lines = []
    for name in picked:
        spec = request.specs[name]
        options: dict[str, object] = {"factor": spec.factor}
        for key in ("chordwise", "spanwise"):
            if getattr(spec, key) is not None:
                options[key] = getattr(spec, key)
        if spec.method != "auto":
            options["method"] = spec.method
        # The element mode reaches a remeshed family only: a grid keeps its cells.
        if request.elements_of(name) != TRIANGLES and spec.method != "grid":
            options["elements"] = request.elements_of(name)
        pairs = " ".join(f"{k}={_value(options[k])}" for k in sorted(options))
        lines.append(f"{name} {pairs}")
    return "\n".join(lines)


def tag_selection(request: RefineRequest, names: Sequence[str]) -> list[str] | None:
    """Return the selected families when the level's tag is the summary and hash, else None."""
    if request.tag:
        return None
    tag, picked, _ = _built_tag(request, names)
    return picked if len(tag) > TAG_MAX else None


def level_tag(request: RefineRequest, names: Sequence[str], where: str = "the mesh") -> str:
    """Return the level's tag: the file's, else ``R<factors>``, else ``R-<family><factors>-...``.

    A built tag of more than 32 characters is ``R-<n>fam-<hash>`` (FR-970):
    ``<hash>`` the first 8 hexadecimal characters of the SHA-256 of the
    :func:`canonical_selection`, encoded as UTF-8. A tag built from family
    names is one folder name (FR-919): a family whose name would put a
    path separator, ``..``, a drive or a reserved character into it is
    refused naming the family, before any work (FR-925); the uniform tag
    ``R<factors>`` and the summary form hold no family name and are not
    refused (FR-973).
    """
    tag, picked, uniform = _built_tag(request, names)
    if not picked:
        raise _refuse(where, "no family is selected, so the level would change nothing")
    if request.tag:
        return str(request.tag)
    if len(tag) > TAG_MAX:
        digest = hashlib.sha256(canonical_selection(request, picked).encode("utf-8")).hexdigest()[
            :8
        ]
        return f"R-{len(picked)}fam-{digest}"
    if uniform:
        return tag
    tags = {n: spec_tag(s) for n, s in request.specs.items()}
    for name in picked:
        problem = folder_name_problem(f"R-{name}{tags[name]}")
        if problem is not None:
            raise _refuse(
                where,
                f"the family {name!r} {problem}, so the level's tag {tag!r} would not be one "
                "folder name; rename the family, or give the level its name in the refinement "
                'file config (CLI: --config) as [refine] tag = "fine"',
            )
    return tag
