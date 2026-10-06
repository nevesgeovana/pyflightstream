"""What a refinement is asked to do: the arguments and the refinement file (FR-424 R1 to R3).

The factors come from the call (FACTOR, ``--chordwise``, ``--spanwise``) or,
when the call gives none, from the refinement file: ``--config FILE`` or
``<stem>.refine.toml`` beside the mesh. The file's ``[components]``,
``[periodic]`` and ``[refine] tag`` are read whenever the file exists. Every
refusal names the file, the table and the key, lists the known keys, and is
raised before any family is touched.
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._refine._obj import KIND

#: The methods a family may state (FR-424 R9).
METHODS = ("auto", "grid", "remesh")
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
)
#: The keys of ``[periodic]`` (FR-427).
PERIODIC_KEYS = ("axis", "origin", "copies")
#: The top-level tables of a refinement file.
TABLES = ("refine", "families", "components", "periodic")


@dataclass(frozen=True)
class FamilySpec:
    """How one family is refined: its factors, its method and, for a body, its axis."""

    factor: float = 1.0
    chordwise: float | None = None
    spanwise: float | None = None
    method: str = "auto"
    axial: float | None = None
    circumferential: float | None = None
    axis: tuple[float, float, float] | None = None
    origin: tuple[float, float, float] | None = None

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
    """Everything a refinement was asked: specs, tag, components and periodicity."""

    specs: dict[str, FamilySpec]
    tag: str | None = None
    components: dict[str, list[str]] = field(default_factory=dict)
    periodic: Periodic | None = None
    config: Path | None = None


def _refuse(where: str, reason: str) -> InputArtifactError:
    """Return a refusal of the request: where, why, and that nothing was written."""
    return InputArtifactError(f"{where}: {reason}. Nothing was written.", kind=KIND)


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


def _family_spec(where: str, table: Mapping[str, Any]) -> FamilySpec:
    unknown = sorted(set(table) - set(FAMILY_KEYS))
    if unknown:
        raise _refuse(
            where, f"unknown key {unknown[0]!r}; the known keys are {', '.join(FAMILY_KEYS)}"
        )
    method = table.get("method", "auto")
    if method not in METHODS:
        raise _refuse(f"{where} method", f"{method!r} is not one of {', '.join(METHODS)}")
    body = [k for k in ("axial", "circumferential") if k in table]
    if body:
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


def _periodic(path: Path, raw: Any) -> Periodic:
    """Return ``[periodic]`` (FR-427): axis, origin and the number of copies in a turn."""
    where = f"{path} [periodic]"
    if not isinstance(raw, dict):
        raise _refuse(where, "the table must hold axis, origin and copies")
    unknown = sorted(set(raw) - set(PERIODIC_KEYS))
    missing = [k for k in PERIODIC_KEYS if k not in raw]
    if unknown or missing:
        key = unknown[0] if unknown else missing[0]
        raise _refuse(
            where, f"key {key!r} unknown or missing; the keys are {', '.join(PERIODIC_KEYS)}"
        )
    copies = raw["copies"]
    if isinstance(copies, bool) or not isinstance(copies, int) or copies < 2:
        raise _refuse(f"{where} copies", f"{copies!r} is not an integer of at least 2")
    return Periodic(
        axis=_vector(f"{where} axis", raw["axis"], nonzero=True),
        origin=_vector(f"{where} origin", raw["origin"], nonzero=False),
        copies=copies,
    )


def read_refine_file(path: str | Path, names: Sequence[str]) -> dict[str, Any]:
    """Read a refinement file against the mesh's family names, refusing what it cannot honour."""
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
    families = data.get("families") or {}
    specs: dict[str, FamilySpec] = {}
    for name, table in families.items():
        where = f"{source} [families.{name}]"
        if name not in names:
            raise _refuse(where, f"the mesh holds no family {name!r}; it holds {', '.join(names)}")
        specs[name] = _family_spec(where, table)
    refine = data.get("refine") or {}
    if set(refine) - {"tag"}:
        raise _refuse(f"{source} [refine]", "the only key is tag")
    return {
        "specs": specs,
        "tag": refine.get("tag"),
        "components": _components(source, data.get("components") or {}, names),
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
) -> RefineRequest:
    """Return what the refinement is asked, from the call and the refinement file (FR-424 R2)."""
    file = refine_file_of(mesh, config)
    stated = (
        read_refine_file(file, names)
        if file
        else {"specs": {}, "tag": None, "components": {}, "periodic": None}
    )
    if factor is None and chordwise is None and spanwise is None:
        if not stated["specs"]:
            raise _refuse(
                str(mesh),
                "no factor was given and no refinement file states one; give FACTOR "
                f"or write {mesh.stem}.refine.toml beside the mesh",
            )
        specs = stated["specs"]
    else:
        chosen = list(names) if families is None else list(families)
        missing = [n for n in chosen if n not in names]
        if missing:
            raise _refuse(
                str(mesh), f"the mesh holds no family {missing[0]!r}; it holds {', '.join(names)}"
            )
        base = positive(f"{mesh} FACTOR", 1.0 if factor is None else factor)
        specs = {
            n: FamilySpec(
                factor=base,
                chordwise=None if chordwise is None else positive(f"{mesh} --chordwise", chordwise),
                spanwise=None if spanwise is None else positive(f"{mesh} --spanwise", spanwise),
            )
            for n in chosen
        }
    return RefineRequest(
        specs=specs,
        tag=stated["tag"],
        components=stated["components"],
        periodic=stated["periodic"],
        config=file,
    )


def _fmt(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def spec_tag(spec: FamilySpec) -> str:
    """Return a family's part of a level's tag: R5 of FR-424, and a and t for a body (FR-428)."""
    if spec.axial is not None or spec.circumferential is not None:
        return f"a{_fmt(spec.axial or 1.0)}t{_fmt(spec.circumferential or 1.0)}"
    tag = _fmt(spec.factor)
    if spec.chordwise is not None:
        tag += f"c{_fmt(spec.chordwise)}"
    if spec.spanwise is not None:
        tag += f"s{_fmt(spec.spanwise)}"
    return tag


def level_tag(request: RefineRequest, names: Sequence[str]) -> str:
    """Return the level's tag: the file's, else ``R<factors>``, else ``R-<family><factors>-...``."""
    if request.tag:
        return str(request.tag)
    tags = {n: spec_tag(s) for n, s in request.specs.items()}
    if set(request.specs) == set(names) and len(set(tags.values())) == 1:
        return "R" + next(iter(tags.values()))
    return "R-" + "-".join(f"{n}{tags[n]}" for n in names if n in request.specs)
