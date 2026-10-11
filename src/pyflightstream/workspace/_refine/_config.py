"""What a refinement is asked to do: the arguments and the refinement file (FR-424 R1 to R3).

The factors come from the call (FACTOR, ``--chordwise``, ``--spanwise``) or,
when the call gives none, from the refinement file: ``--config FILE`` or
``<stem>.refine.toml`` beside the mesh. The file's ``[components]``,
``[periodic]``, ``[refine] tag`` and the element modes (``[refine] elements``
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

import dataclasses
import hashlib
import math
import tomllib
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace._refine._obj import KIND

#: The methods a family may state (FR-424 R9).
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
    "chordwise",
    "spanwise",
    "method",
    "axial",
    "circumferential",
    "axis",
    "origin",
    "elements",
    "keep_first_row",
)
#: The keys of ``[refine]``.
REFINE_KEYS = ("tag", "elements")
#: The keys of ``[periodic]`` (FR-427).
PERIODIC_KEYS = ("axis", "origin", "copies")
#: The top-level tables of a refinement file.
TABLES = ("refine", "families", "components", "periodic")


@dataclass(frozen=True)
class FamilySpec:
    """How one family is refined: its factors, its method and, for a body, its axis.

    ``keep_first_row`` (REF-FIRSTROW, 0.39 development) asks a grid with a
    trailing edge to keep the spanwise width of its end row at the interface
    with another component, refining that row chordwise only.
    """

    factor: float = 1.0
    chordwise: float | None = None
    spanwise: float | None = None
    method: str = "auto"
    axial: float | None = None
    circumferential: float | None = None
    axis: tuple[float, float, float] | None = None
    origin: tuple[float, float, float] | None = None
    keep_first_row: bool = False

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
        stated = [self.factor, *self.directions, self.axial, self.circumferential]
        return all(v is None or v == 1.0 for v in stated)


@dataclass(frozen=True)
class Periodic:
    """The rotation that maps one cut face of a sector onto the other (FR-427)."""

    axis: tuple[float, float, float]
    origin: tuple[float, float, float]
    copies: int


@dataclass(frozen=True)
class RefineRequest:
    """Everything a refinement was asked: specs, tag, components, periodicity and element modes.

    ``elements`` holds the modes the file states per family, and
    ``default_elements`` the mode of ``[refine] elements`` (else triangles).
    ``ignored`` names the families whose ``[families.<name>]`` table states
    factors the refinement does not read: every one when the call gives the
    factors, and the unselected ones when ``families`` selects from the
    file's factors.
    """

    specs: dict[str, FamilySpec]
    tag: str | None = None
    components: dict[str, list[str]] = field(default_factory=dict)
    periodic: Periodic | None = None
    config: Path | None = None
    elements: dict[str, str] = field(default_factory=dict)
    default_elements: str = TRIANGLES
    ignored: tuple[str, ...] = ()

    def elements_of(self, family: str) -> str:
        """Return the element mode of a family: its own, else the file's default."""
        return self.elements.get(family, self.default_elements)


def _refuse(where: str, reason: str) -> InputArtifactError:
    """Return a refusal of the request: where, why, and that nothing was written."""
    return InputArtifactError(f"{where}: {reason}. Nothing was written.", kind=KIND)


#: The characters a level's folder name never holds (FR-424 R5): the path separators,
#: the drive colon and the characters Windows reserves in a file name.
UNSAFE_CHARACTERS = '/\\:<>"|?*'


def folder_name_problem(name: str) -> str | None:
    """Return why ``name`` is not one portable folder name, or None when it is (FR-424 R5).

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
    """Return a factor as a float, refusing anything but a finite number above zero (R1)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _refuse(where, f"the factor {value!r} is not a number; give a number above zero")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise _refuse(where, f"the factor {number:g} is not above zero; give a number above zero")
    return number


def _vector(where: str, value: Any, *, nonzero: bool) -> tuple[float, float, float]:
    ok = isinstance(value, list | tuple) and len(value) == 3
    ok = ok and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)
    numbers = tuple(float(v) for v in value) if ok else ()
    if not ok or not all(math.isfinite(v) for v in numbers):
        raise _refuse(where, f"{value!r} is not three finite numbers")
    if nonzero and not any(numbers):
        raise _refuse(where, "the axis is zero; give a direction")
    return numbers[0], numbers[1], numbers[2]


def elements_mode(where: str, value: Any) -> str:
    """Return an element mode, refusing anything but one of :data:`ELEMENTS`."""
    if value not in ELEMENTS:
        raise _refuse(
            f"{where} elements",
            f"{value!r} is not an element mode; the modes are {', '.join(ELEMENTS)}",
        )
    return str(value)


def _family_spec(where: str, table: Mapping[str, Any]) -> FamilySpec:
    unknown = sorted(set(table) - set(FAMILY_KEYS))
    if unknown:
        raise _refuse(
            where, f"unknown key {unknown[0]!r}; the known keys are {', '.join(FAMILY_KEYS)}"
        )
    method = table.get("method", "auto")
    if method not in METHODS:
        raise _refuse(f"{where} method", f"{method!r} is not one of {', '.join(METHODS)}")
    if "elements" in table and method == "grid":
        raise _refuse(
            f"{where} elements", "elements applies to a remeshed family; a grid keeps its cells"
        )
    table = {k: v for k, v in table.items() if k not in ("elements", "keep_first_row")}
    if any(k in table for k in ("axial", "circumferential")):
        return _body_spec(where, table, method)
    if not any(k in table for k in ("factor", "chordwise", "spanwise")):
        raise _refuse(where, "the table states no factor, chordwise or spanwise")
    if method == "remesh" and any(k in table for k in ("chordwise", "spanwise")):
        raise _refuse(
            where, "chordwise and spanwise apply to a grid; a remeshed family takes factor"
        )
    if any(k in table for k in ("axis", "origin")):
        raise _refuse(where, "axis and origin go with axial and circumferential")
    return FamilySpec(
        factor=positive(f"{where} factor", table.get("factor", 1.0)),
        chordwise=_optional(where, table, "chordwise"),
        spanwise=_optional(where, table, "spanwise"),
        method=method,
    )


def _keep_flag(where: str, table: Mapping[str, Any]) -> bool:
    """Return a table's ``keep_first_row`` (FR-430 R1), refusing a value not true or false (R6)."""
    keep = table.get("keep_first_row", False)
    if not isinstance(keep, bool):
        raise _refuse(where, f"keep_first_row = {keep!r} is not true or false")
    return keep


def with_kept_rows(where: str, spec: FamilySpec) -> FamilySpec:
    """Return a family's spec asked to keep its interface rows, or refuse it (FR-430 R6).

    ``keep_first_row`` applies to a grid family: a family stated with
    ``method = "remesh"``, or with ``axial`` or ``circumferential`` (a body
    remeshed along and around its axis), is refused before any work.
    """
    if spec.axial is not None or spec.circumferential is not None:
        raise _refuse(
            where,
            "keep_first_row applies to a grid family with a trailing edge; axial and "
            "circumferential remesh a body",
        )
    if spec.method == "remesh":
        raise _refuse(
            where,
            "keep_first_row applies to a grid family with a trailing edge; this one is remeshed "
            '(method = "remesh")',
        )
    return dataclasses.replace(spec, keep_first_row=True)


def _optional(where: str, table: Mapping[str, Any], key: str) -> float | None:
    return positive(f"{where} {key}", table[key]) if key in table else None


def _body_spec(where: str, table: Mapping[str, Any], method: str) -> FamilySpec:
    """Return the spec of a body refined along and around its axis (FR-428)."""
    clash = [k for k in ("factor", "chordwise", "spanwise") if k in table]
    if clash:
        raise _refuse(
            where, f"axial and circumferential replace {clash[0]}; state one or the other"
        )
    if "axis" not in table:
        raise _refuse(where, "axial and circumferential need axis, three numbers")
    if method == "grid":
        raise _refuse(where, "axial and circumferential apply to a remeshed family, not a grid")
    origin = table.get("origin")
    return FamilySpec(
        method="remesh",
        axial=positive(f"{where} axial", table.get("axial", 1.0)),
        circumferential=positive(f"{where} circumferential", table.get("circumferential", 1.0)),
        axis=_vector(f"{where} axis", table["axis"], nonzero=True),
        origin=None if origin is None else _vector(f"{where} origin", origin, nonzero=False),
    )


def _components(path: Path, raw: Any, names: Sequence[str]) -> dict[str, list[str]]:
    """Return ``[components]`` checked against the mesh's families (FR-425 R4)."""
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
            raise _refuse(
                f"{where} {name}",
                f"the mesh holds no family {missing[0]!r}; it holds {', '.join(names)}",
            )
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


def _periodic(path: Path, raw: Any) -> Periodic:
    """Return ``[periodic]`` (FR-427): axis, origin and the number of copies in a turn."""
    where = f"{path} [periodic]"
    if not isinstance(raw, dict):
        raise _refuse(where, "the table must hold axis, origin and copies")
    unknown = sorted(set(raw) - set(PERIODIC_KEYS))
    missing = [k for k in PERIODIC_KEYS if k not in raw]
    if unknown or missing:
        said = [_keys("unknown", unknown), _keys("missing", missing)]
        raise _refuse(
            where,
            f"{'; '.join(s for s in said if s)}; the keys are {', '.join(PERIODIC_KEYS)}",
        )
    copies = raw["copies"]
    if isinstance(copies, bool) or not isinstance(copies, int) or copies < 2:
        raise _refuse(f"{where} copies", f"{copies!r} is not an integer of at least 2")
    return Periodic(
        axis=_vector(f"{where} axis", raw["axis"], nonzero=True),
        origin=_vector(f"{where} origin", raw["origin"], nonzero=False),
        copies=copies,
    )


def _family_tables(
    source: Path, families: Mapping[str, Any], names: Sequence[str], mesh: str | Path | None
) -> tuple[dict[str, FamilySpec], dict[str, str], list[str]]:
    """Return the specs, the element modes and the kept families of ``[families.<name>]``."""
    specs: dict[str, FamilySpec] = {}
    elements: dict[str, str] = {}
    keep: list[str] = []
    for name, raw in families.items():
        where = f"{source} [families.{name}]"
        table = _table(
            where, raw, f"write [families.{name}] with the keys {', '.join(FAMILY_KEYS)}"
        )
        if name not in names:
            raise _refuse(where, f"the mesh holds no family {name!r}; it holds {', '.join(names)}")
        if "elements" in table:
            elements[name] = elements_mode(where, table["elements"])
        named = f"{mesh} family {name} keep_first_row ({where})" if mesh else where
        if _keep_flag(named, table):
            keep.append(name)
        if set(table) != {"elements"}:
            specs[name] = _family_spec(where, table)
    return specs, elements, keep


def read_refine_file(
    path: str | Path, names: Sequence[str], mesh: str | Path | None = None
) -> dict[str, Any]:
    """Read a refinement file against the mesh's family names, refusing what it cannot honour.

    ``keep`` lists the families whose table states ``keep_first_row = true``
    (FR-430 R1); a refusal of that key names ``mesh``, the source, as well.
    """
    source = Path(path)
    try:
        data = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise _refuse(str(source), f"the refinement file cannot be read ({error})") from error
    unknown = sorted(set(data) - set(TABLES))
    if unknown:
        raise _refuse(
            str(source), f"unknown table [{unknown[0]}]; the tables are {', '.join(TABLES)}"
        )
    families = _table(
        f"{source} [families]",
        data.get("families", {}),
        f"write one [families.<name>] table per family, with the keys {', '.join(FAMILY_KEYS)}",
    )
    specs, elements, keep = _family_tables(source, families, names, mesh)
    refine = _table(
        f"{source} [refine]",
        data.get("refine", {}),
        f"write [refine] with the keys {', '.join(REFINE_KEYS)}",
    )
    unknown = sorted(set(refine) - set(REFINE_KEYS))
    if unknown:
        raise _refuse(
            f"{source} [refine]",
            f"unknown key {unknown[0]!r}; the known keys are {', '.join(REFINE_KEYS)}",
        )
    tag = refine.get("tag")
    if tag is not None and (not isinstance(tag, str) or not tag):
        raise _refuse(
            f"{source} [refine] tag",
            f'{tag!r} is not a text; give the tag as a non-empty string, such as tag = "fine"',
        )
    problem = None if tag is None else folder_name_problem(tag)
    if problem is not None:
        raise _refuse(
            f"{source} [refine] tag",
            f'{tag!r} {problem}, so it is not one folder name (no / \\ : < > " | ? *, no .., '
            "not ending with a dot or a space); the level folder is <stem>_<tag> beside the "
            'source\'s folder, so give a name such as tag = "fine"',
        )
    default = refine.get("elements", TRIANGLES)
    return {
        "specs": specs,
        "keep": keep,
        "elements": elements,
        "default_elements": elements_mode(f"{source} [refine]", default),
        "tag": tag,
        "components": _components(source, data.get("components", {}), names),
        "periodic": _periodic(source, data["periodic"]) if "periodic" in data else None,
    }


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
    chordwise: float | None = None,
    spanwise: float | None = None,
    config: str | Path | None = None,
    keep_first_row: Sequence[str] | None = None,
) -> RefineRequest:
    """Return what the refinement is asked, from the call and the refinement file (FR-424 R2).

    ``keep_first_row`` names the families that keep their interface rows
    (FR-430 R1), with the families whose table states the key when the
    file's tables give the factors.
    """
    file = refine_file_of(mesh, config)
    stated = (
        read_refine_file(file, names, mesh)
        if file
        else {
            "specs": {},
            "keep": [],
            "elements": {},
            "default_elements": TRIANGLES,
            "tag": None,
            "components": {},
            "periodic": None,
        }
    )
    chosen = list(names) if families is None else list(families)
    missing = [n for n in chosen if n not in names]
    if missing:
        raise _refuse(
            str(mesh), f"the mesh holds no family {missing[0]!r}; it holds {', '.join(names)}"
        )
    stated_specs: dict[str, FamilySpec] = stated["specs"]
    if factor is None and chordwise is None and spanwise is None:
        if not stated_specs:
            raise _refuse(
                str(mesh),
                "no factor was given and no refinement file states one; give FACTOR "
                f"or write {mesh.stem}.refine.toml beside the mesh",
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
        ignored = tuple(n for n in stated_specs if n not in specs)
        asked = [n for n in stated["keep"] if n in specs]
    else:
        base = positive(f"{mesh} FACTOR", 1.0 if factor is None else factor)
        specs = {
            n: FamilySpec(
                factor=base,
                chordwise=None if chordwise is None else positive(f"{mesh} --chordwise", chordwise),
                spanwise=None if spanwise is None else positive(f"{mesh} --spanwise", spanwise),
            )
            for n in chosen
        }
        reason = "FACTOR, --chordwise or --spanwise gives the factors (FR-424 R2)"
        ignored = tuple(stated_specs)
        asked = []
    if ignored:
        tables = ", ".join(f"[families.{n}]" for n in ignored)
        warnings.warn(
            f"{file}: the tables {tables} are not read for their factors, methods and "
            f"keep_first_row, because {reason}; an elements key in them still applies.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    specs = _kept(mesh, names, specs, [*asked, *(keep_first_row or ())])
    return RefineRequest(
        specs=specs,
        tag=stated["tag"],
        components=stated["components"],
        periodic=stated["periodic"],
        config=file,
        elements=stated["elements"],
        default_elements=stated["default_elements"],
        ignored=ignored,
    )


def _kept(
    mesh: Path, names: Sequence[str], specs: dict[str, FamilySpec], asked: Sequence[str]
) -> dict[str, FamilySpec]:
    """Return the specs with ``keep_first_row`` set on each family asked (FR-430 R1, R6).

    A family the mesh does not hold, or one the selection leaves out, is
    refused before any work, naming the source, the family and the option.
    """
    out = dict(specs)
    for name in dict.fromkeys(asked):
        where = f"{mesh} family {name} keep_first_row"
        if name not in names:
            raise _refuse(where, f"the mesh holds no family {name!r}; it holds {', '.join(names)}")
        if name not in out:
            raise _refuse(
                where,
                f"the selection leaves the family out (it selects {', '.join(out)}); select it "
                "or ask keep_first_row of a selected family",
            )
        out[name] = with_kept_rows(where, out[name])
    return out


def _fmt(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def spec_tag(spec: FamilySpec) -> str:
    """Return a family's part of a level's tag: R5 of FR-424, a and t for a body (FR-428).

    A family asked to keep its first row carries ``k`` (FR-430 R8), so a level
    with kept rows and one without never share a tag.
    """
    if spec.axial is not None or spec.circumferential is not None:
        tag = f"a{_fmt(spec.axial or 1.0)}t{_fmt(spec.circumferential or 1.0)}"
    else:
        tag = _fmt(spec.factor)
        if spec.chordwise is not None:
            tag += f"c{_fmt(spec.chordwise)}"
        if spec.spanwise is not None:
            tag += f"s{_fmt(spec.spanwise)}"
    return tag + ("k" if spec.keep_first_row else "")


#: The longest built tag that stays the tag of 0.38.0; a longer one is summarised (FR-433 R2).
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
    """Return one option value as the canonical selection writes it (FR-433 R2, R3).

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
    """Return the canonical selection a summary tag hashes (FR-433 R2).

    One line per selected family, in the source's order: the family's name,
    then every option its table states that changes the level, as sorted
    ``key=value`` pairs separated by single spaces.
    """
    lines = []
    for name in picked:
        spec = request.specs[name]
        options: dict[str, object] = {"factor": spec.factor}
        for key in ("chordwise", "spanwise", "axial", "circumferential"):
            if getattr(spec, key) is not None:
                options[key] = getattr(spec, key)
        if spec.method != "auto":
            options["method"] = spec.method
        if request.elements_of(name) != TRIANGLES:
            options["elements"] = request.elements_of(name)
        if spec.keep_first_row:
            options["keep_first_row"] = True
        pairs = " ".join(f"{k}={_value(options[k])}" for k in sorted(options))
        lines.append(f"{name} {pairs}")
    return "\n".join(lines)


def tag_selection(request: RefineRequest, names: Sequence[str]) -> list[str] | None:
    """Return the selected families when the level's tag is the summary and hash, else None."""
    if request.tag:
        return None
    tag, picked, uniform = _built_tag(request, names)
    return picked if not uniform and len(tag) > TAG_MAX else None


def level_tag(request: RefineRequest, names: Sequence[str], where: str = "the mesh") -> str:
    """Return the level's tag: the file's, else ``R<factors>``, else ``R-<family><factors>-...``.

    A built tag of more than 32 characters is ``R-<n>fam-<hash>`` (FR-433 R2):
    ``<hash>`` the first 8 hexadecimal characters of the SHA-256 of the
    :func:`canonical_selection`, encoded as UTF-8. A tag built from family
    names is one folder name (FR-424 R5): a family whose name would put a
    path separator, ``..``, a drive or a reserved character into it is
    refused naming the family, before any work (R11); the uniform tag
    ``R<factors>`` and the summary form hold no family name and are not
    refused (FR-433 R5), as on 0.38.0.
    """
    if request.tag:
        return str(request.tag)
    tag, picked, uniform = _built_tag(request, names)
    if uniform:
        return tag
    if len(tag) > TAG_MAX:
        digest = hashlib.sha256(canonical_selection(request, picked).encode("utf-8")).hexdigest()[
            :8
        ]
        return f"R-{len(picked)}fam-{digest}"
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
