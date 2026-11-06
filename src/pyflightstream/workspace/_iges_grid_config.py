"""The grid control file of ``geometry iges-grid``: one table per component, read and checked.

``grid.toml`` holds an optional top-level ``fs_build``, a ``[defaults]`` table (``size``,
``tolerance``, ``te_angle_deg``) and one ``[component.<Name>]`` table per component named in the
IGES. A key that does not apply is warned and skipped; a value that cannot be read is refused
before anything is imported, with nothing written.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyflightstream._errors import InputValueError, NotApplicableWarning, warn

__all__ = ["LAWS", "ComponentGrid", "Direction", "GridConfig", "read_grid"]

#: The spacing laws a direction may name.
LAWS = ("cosine", "geometric", "tanh", "uniform")
#: The ratio a law takes when none is given: geometric, the growth of a cell over the next one
#: away from the clustered end; tanh, the coefficient of the one-sided law (nearer 1 clusters
#: harder). cosine has none: its end-to-middle ratio follows the count.
DEFAULT_RATIO = {"geometric": 1.1, "tanh": 1.05}
#: The angle between the normals of two faces above which their shared edge is a trailing edge
#: when ``trailing_edge = "auto"`` and their bisector faces downstream: 60 degrees takes the sharp
#: trailing edge and both rims of a blunt one (each near 90 degrees).
DEFAULT_TE_ANGLE_DEG = 60.0

_TOP = {"fs_build", "defaults", "component"}
_DEFAULTS = {"size", "tolerance", "te_angle_deg"}
_COMPONENT = {
    "size",
    "chord",
    "span",
    "span_axis",
    "le_cluster",
    "te_cluster",
    "structured",
    "trailing_edge",
    "te_angle_deg",
}
_DIRECTION = {"count", "law", "ratio"}
_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise InputValueError(f"grid: {message}. Nothing was written.")


def _positive(value: object, where: str) -> float:
    _need(
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0,
        f"{where} must be a positive number",
    )
    return float(value)  # type: ignore[arg-type]


def _skip(keys: set[str], allowed: set[str], where: str) -> None:
    for key in sorted(keys - allowed):
        warn(f"{where}.{key} does not apply and is skipped", NotApplicableWarning)


@dataclass(frozen=True)
class Direction:
    """The cells along one parameter direction of a four-sided patch and their spacing law."""

    count: int | None
    law: str = "uniform"
    ratio: float | None = None


@dataclass
class ComponentGrid:
    """The grid one component asks for."""

    name: str
    size: float | None = None
    chord: Direction | None = None
    span: Direction | None = None
    span_axis: tuple[float, float, float] | None = None
    le_cluster: float | None = None
    te_cluster: float | None = None
    structured: bool = True
    trailing_edge: str | list[str] | None = None
    te_angle_deg: float | None = None


@dataclass
class GridConfig:
    """The whole control file: build, defaults and the components in the file's order."""

    fs_build: str | None
    size: float | None
    tolerance: float | None
    te_angle_deg: float
    components: dict[str, ComponentGrid] = field(default_factory=dict)


def _direction(value: object, where: str) -> Direction:
    _need(
        isinstance(value, dict), f'{where} must be a table such as {{count = 40, law = "cosine"}}'
    )
    assert isinstance(value, dict)
    _skip(set(value), _DIRECTION, where)
    count = value.get("count")
    _need(
        count is None or (type(count) is int and count >= 1),
        f"{where}.count must be a whole number of cells, 1 or more",
    )
    law = value.get("law", "uniform")
    _need(law in LAWS, f"{where}.law must be one of {', '.join(LAWS)}")
    ratio = value.get("ratio")
    if ratio is not None:
        ratio = _positive(ratio, f"{where}.ratio")
        if law in ("geometric", "tanh"):
            _need(ratio >= 1.0, f"{where}.ratio of the {law} law must be 1 or more")
        if law == "uniform":
            warn(
                f"{where}.ratio does not apply to the uniform law and is skipped",
                NotApplicableWarning,
            )
            ratio = None
    return Direction(count=count, law=str(law), ratio=ratio)


def _axis(value: object, where: str) -> tuple[float, float, float]:
    if isinstance(value, str):
        _need(value.lower() in _AXES, f"{where} must be x, y, z or three numbers")
        return _AXES[value.lower()]
    _need(
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value),
        f"{where} must be x, y, z or three numbers",
    )
    assert isinstance(value, list)
    norm = math.sqrt(sum(float(v) ** 2 for v in value))
    _need(norm > 0, f"{where} must not be zero")
    return (value[0] / norm, value[1] / norm, value[2] / norm)


def _trailing(value: object, where: str) -> str | list[str] | None:
    if value is None or value is False:
        return None
    if value == "auto":
        return "auto"
    _need(
        isinstance(value, list)
        and bool(value)
        and all(isinstance(v, str) and bool(v) for v in value),
        f'{where} must be "auto" or a list of IGES curve names',
    )
    assert isinstance(value, list)
    return [str(v) for v in value]


def _component(name: str, table: object) -> ComponentGrid:
    where = f"component.{name}"
    _need(isinstance(table, dict), f"[{where}] must be a table")
    assert isinstance(table, dict)
    _skip(set(table), _COMPONENT, where)
    out = ComponentGrid(name=name)
    if "size" in table:
        out.size = _positive(table["size"], f"{where}.size")
    for key in ("chord", "span"):
        if key in table:
            setattr(out, key, _direction(table[key], f"{where}.{key}"))
    if "span_axis" in table:
        out.span_axis = _axis(table["span_axis"], f"{where}.span_axis")
    for key in ("le_cluster", "te_cluster"):
        if key in table:
            value = _positive(table[key], f"{where}.{key}")
            _need(value <= 1.0, f"{where}.{key} is the end cell over the middle cell, 1 or less")
            setattr(out, key, value)
    if "structured" in table:
        _need(isinstance(table["structured"], bool), f"{where}.structured must be true or false")
        out.structured = bool(table["structured"])
    out.trailing_edge = _trailing(table.get("trailing_edge"), f"{where}.trailing_edge")
    if "te_angle_deg" in table:
        out.te_angle_deg = _positive(table["te_angle_deg"], f"{where}.te_angle_deg")
    return out


def read_grid(path: str | Path) -> GridConfig:
    """Read and check a grid control file.

    Raises
    ------
    InputValueError
        The file is missing, not TOML, or a value cannot be read; nothing was written.
    """
    source = Path(path)
    _need(source.is_file(), f"{source} is not a file; name the grid control file")
    try:
        data: dict[str, Any] = tomllib.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise InputValueError(
            f"grid: {source} is not TOML ({error}). Nothing was written."
        ) from error
    _skip(set(data), _TOP, "grid")
    build = data.get("fs_build")
    _need(
        build is None or (isinstance(build, str) and build.strip() != ""),
        'fs_build must be a build such as "26.127"',
    )
    defaults = data.get("defaults", {})
    _need(isinstance(defaults, dict), "[defaults] must be a table")
    _skip(set(defaults), _DEFAULTS, "defaults")
    size = _positive(defaults["size"], "defaults.size") if "size" in defaults else None
    tolerance = (
        _positive(defaults["tolerance"], "defaults.tolerance") if "tolerance" in defaults else None
    )
    angle = (
        _positive(defaults["te_angle_deg"], "defaults.te_angle_deg")
        if "te_angle_deg" in defaults
        else DEFAULT_TE_ANGLE_DEG
    )
    tables = data.get("component", {})
    _need(isinstance(tables, dict), "[component.<Name>] tables must be tables")
    components = {name: _component(name, table) for name, table in tables.items()}
    return GridConfig(
        fs_build=build.strip() if isinstance(build, str) else None,
        size=size,
        tolerance=tolerance,
        te_angle_deg=angle,
        components=components,
    )
