"""The geometry instruction file: one body, how it is made, before any run (FR-470).

Pipeline role: the cases row, beside the import models of the run. A
geometry folder of the workspace (``inputs/geometries/<folder>/``) may hold
one ``<name>.geometry.toml``; ``pyfs-workspace geometry build`` reads it,
emits the script that makes the body (:mod:`pyflightstream.cases._geometry_emit`)
and records the build. This module holds the models of the file and their
own refusals; the file is read and its trailing-edge points resolved by
:mod:`pyflightstream.workspace._geometry_instruction`.

ONE SOURCE TABLE, then the operations. ``[ccs]`` takes every key of the
sidecar's ``[import.ccs]`` (:class:`~pyflightstream.cases._ccs.CcsImportOptions`)
plus ``file``, ``units`` and ``shedding``; ``[cad]`` every key of
``[import.cad]`` plus ``file``, ``units`` and the CAD body operations;
``[create]`` the CAD Create recipe; ``[mesh]`` a raw mesh and its unit.

THE STATED NAMES ARE THE CONTRACT. ``boundaries`` are the names the saved body
must carry, in order; every operation that creates a surface states the names
of what it creates. The names the SOURCE makes are therefore derived from the
stated ones by undoing the operations (:func:`source_names`), and the build
reads the saved file back and fails when the two differ, so a name trusted at
the emission is checked before any row can name the body.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pyflightstream._lengths import UNIT_THAT_NAMES_NO_LENGTH
from pyflightstream.cases._ccs import CcsImportOptions
from pyflightstream.cases.mesh import CadImportOptions, TrailingEdgeMarking

__all__ = [
    "INSTRUCTION_SUFFIX",
    "SOLVED_QUANTITIES",
    "CadBodyOperation",
    "CadSource",
    "CcsSource",
    "CreateBody",
    "CreateLoft",
    "CreateSection",
    "CreateSource",
    "GeometryInstruction",
    "GeometryOperation",
    "GeometrySweep",
    "MeshSource",
    "names_after",
    "source_names",
    "variant_tag",
]

#: The suffix of an instruction file: ``<name>.geometry.toml``.
INSTRUCTION_SUFFIX = ".geometry.toml"

#: The thresholds a selection cannot read before the solver runs: the
#: operations are emitted before any initialisation, so nothing is solved.
SOLVED_QUANTITIES = frozenset({"VELOCITY", "VX", "VY", "VZ", "CP", "MACH", "SOLVER_QUALITY"})

#: The quantities an ``extract_faces`` or ``delete_faces`` selection reads.
_GEOMETRIC_QUANTITIES = ("X", "Y", "Z", "AREA", "QUALITY")

#: The keys each ``[[operations]]`` kind states (required first, then optional).
_OPERATION_KEYS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "scale": (("factors",), ("surface",)),
    "rename": (("surface", "to"), ()),
    "mirror": (("surface", "plane"), ()),
    "circular_copy": (("surface", "axis", "count", "angle_deg", "names"), ()),
    "linear_copy": (("surface", "count", "vector", "names"), ()),
    "cut": (("surface", "plane", "offset", "names"), ()),
    "fill_holes": (("surface",), ()),
    "delete_degenerate_faces": ((), ()),
    "extract_faces": (("quantity", "name"), ("min", "max", "surface")),
    "delete_faces": (("quantity",), ("min", "max", "surface")),
    "transform_nodes": (("mesh_sha256", "nodes", "vector"), ()),
}

#: The every-surface word of a sidecar, which no surface-creating kind takes.
_EVERY = "all"

#: Where the move of a body belongs (her rule of 2026-10-12: they stay in the run).
_TRANSLATE_ROTATE = (
    "translate and rotate stay in the run: write them in the sidecar of the built mesh "
    "([[import.operations]] of <name>.boundaries.toml) or as the row keys TRANSLATE and "
    "ROTATE of the matrix (docs/geometry.md)"
)


def _one_word(value: str, what: str) -> str:
    """Refuse a name the solver would read as several tokens."""
    if not value or any(character.isspace() for character in value):
        raise ValueError(f"{what} {value!r} is empty or carries whitespace; write one word")
    return value


def _finite(values: Sequence[float], what: str) -> None:
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{what} states a value that is not a finite number")


class GeometryOperation(BaseModel):
    """One ``[[operations]]`` table: a mesh operation applied after the source (FR-474).

    ``scale``, ``rename`` and ``mirror`` keep the keys and rules of the
    sidecar's ``[[import.operations]]``; the kinds of FR-474 state the names
    of every surface they create. ``translate`` and ``rotate`` are refused:
    they stay in the run.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: str
    surface: str | None = None
    factors: tuple[float, float, float] | None = None
    to: str | None = None
    plane: Literal["XY", "XZ", "YZ"] | None = None
    axis: Literal["X", "Y", "Z"] | None = None
    count: int | None = Field(default=None, ge=2, strict=True)
    angle_deg: float | None = None
    names: tuple[str, ...] | None = None
    vector: tuple[float, float, float] | None = None
    offset: float | None = None
    quantity: str | None = None
    min: float | None = None
    max: float | None = None
    name: str | None = None
    mesh_sha256: str | None = None
    nodes: tuple[int, ...] | None = None

    @field_validator("op")
    @classmethod
    def _a_known_kind(cls, value: str) -> str:
        if value in ("translate", "rotate"):
            raise ValueError(f"op = {value!r} is not a geometry operation: {_TRANSLATE_ROTATE}")
        if value not in _OPERATION_KEYS:
            raise ValueError(
                f"op = {value!r} is no operation of the instruction; write one of "
                f"{', '.join(sorted(_OPERATION_KEYS))}"
            )
        return value

    @model_validator(mode="after")
    def _its_own_keys(self) -> GeometryOperation:
        required, optional = _OPERATION_KEYS[self.op]
        stated = {
            key for key in type(self).model_fields if key != "op" and getattr(self, key) is not None
        }
        missing = [key for key in required if getattr(self, key) is None]
        if missing:
            raise ValueError(
                f"a {self.op} states {', '.join(required)}; {', '.join(missing)} is not stated"
            )
        foreign = sorted(stated - set(required) - set(optional))
        if foreign:
            raise ValueError(f"a {self.op} does not read {', '.join(foreign)}")
        self._check_values()
        return self

    def _check_values(self) -> None:
        numbers = [*(self.factors or ()), *(self.vector or ())]
        numbers += [
            value
            for value in (self.angle_deg, self.offset, self.min, self.max)
            if value is not None
        ]
        _finite(numbers, f"a {self.op}")
        if self.factors is not None and min(self.factors) <= 0:
            raise ValueError(
                f"each scale factor must be greater than zero; got {list(self.factors)}"
            )
        for name in (self.to, self.name, *(self.names or ())):
            if name is not None:
                _one_word(name, "the surface name")
        if self.op in ("rename", "mirror", "circular_copy", "linear_copy", "cut", "fill_holes"):
            if self.surface == _EVERY:
                raise ValueError(
                    f'a {self.op} names the one surface it acts on; it has no "{_EVERY}" form'
                )
        if self.op in ("circular_copy", "linear_copy") and self.names is not None:
            assert self.count is not None  # required above
            if len(self.names) != self.count - 1:
                raise ValueError(
                    f"a {self.op} of count {self.count} (the original included) creates "
                    f"{self.count - 1} surface(s), and names lists {len(self.names)}; write one "
                    "name per new surface, in creation order"
                )
        if self.op == "cut" and self.names is not None and len(self.names) < 2:
            raise ValueError(
                "a cut leaves at least two surfaces; names lists the surfaces it leaves, in order"
            )
        if self.quantity is not None:
            self._check_selection()
        if self.op == "transform_nodes":
            assert self.mesh_sha256 is not None and self.nodes is not None
            if len(self.mesh_sha256) != 64 or any(
                c not in "0123456789abcdef" for c in self.mesh_sha256
            ):
                raise ValueError(
                    "mesh_sha256 is the sha256 of the source mesh, 64 lower-case hex digits"
                )
            if not self.nodes or min(self.nodes) < 1:
                raise ValueError(
                    "nodes lists the 1-based node numbers of the source mesh, at least one"
                )

    def _check_selection(self) -> None:
        assert self.quantity is not None
        if self.quantity in SOLVED_QUANTITIES:
            raise ValueError(
                f"quantity = {self.quantity!r} is a solved quantity, and the operations run "
                "before the solver initialises, so there is nothing solved to select by; "
                f"write one of {', '.join(_GEOMETRIC_QUANTITIES)}"
            )
        if self.quantity not in _GEOMETRIC_QUANTITIES:
            raise ValueError(
                f"quantity = {self.quantity!r}; write one of {', '.join(_GEOMETRIC_QUANTITIES)}"
            )
        if self.min is None and self.max is None:
            raise ValueError(
                f"a {self.op} states min, max or both: the range of {self.quantity} it selects"
            )
        if self.min is not None and self.max is not None and self.max <= self.min:
            raise ValueError(f"max ({self.max}) is not above min ({self.min})")

    def apply(self, names: list[str], position: int) -> None:
        """Apply this operation to a list of names, in place, refusing a missing surface."""
        where = f"operation {position} ({self.op})"
        if self.op == "rename":
            assert self.to is not None
            index = _found(names, self.surface, where)
            if self.to in names and names[index] != self.to:
                raise ValueError(
                    f"{where} renames {self.surface!r} to {self.to!r}, which another "
                    "surface carries"
                )
            names[index] = self.to
        elif self.op in ("circular_copy", "linear_copy"):
            _found(names, self.surface, where)
            names.extend(self.names or ())
        elif self.op == "cut":
            index = _found(names, self.surface, where)
            names[index : index + 1] = list(self.names or ())
        elif self.op == "extract_faces":
            if self.surface is not None:
                _found(names, self.surface, where)
            assert self.name is not None
            names.append(self.name)
        elif self.surface is not None and self.surface != _EVERY:
            _found(names, self.surface, where)
        if len(set(names)) != len(names):
            raise ValueError(f"after {where} two surfaces carry one name: {', '.join(names)}")

    def undo(self, names: list[str], position: int) -> None:
        """Undo this operation on the names it leaves, in place: the names it was given."""
        where = f"operation {position} ({self.op})"
        if self.op == "rename":
            assert self.to is not None and self.surface is not None
            names[_found(names, self.to, where)] = self.surface
        elif self.op in ("circular_copy", "linear_copy") or self.op == "extract_faces":
            created = list(self.names or ()) if self.name is None else [self.name]
            if names[len(names) - len(created) :] != created:
                raise ValueError(
                    f"{where} creates {', '.join(created)}, which the names it leaves end with; "
                    f"they end with {', '.join(names[-len(created) :]) or 'nothing'}"
                )
            del names[len(names) - len(created) :]
        elif self.op == "cut":
            left = list(self.names or ())
            for index in range(len(names) - len(left) + 1):
                if names[index : index + len(left)] == left:
                    names[index : index + len(left)] = [self.surface or ""]
                    return
            raise ValueError(
                f"{where} leaves {', '.join(left)}, which do not follow one another in the names"
            )


def _found(names: Sequence[str], surface: str | None, where: str) -> int:
    """Return the position of one named surface, refusing a name absent at that step."""
    if surface is None or surface not in names:
        raise ValueError(
            f"{where} names the surface {surface!r}, and the surfaces at that step are "
            f"{', '.join(repr(name) for name in names) or 'none'}"
        )
    return list(names).index(surface)


class CcsSource(BaseModel):
    """The ``[ccs]`` source: a CCS file lofted or imported whole (FR-470 R2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str
    units: str
    shedding: str | int | None = None
    options: CcsImportOptions


class CadBodyOperation(BaseModel):
    """One ``[[cad.operations]]`` table, applied before the conversion (FR-475 R1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["delete", "delete_by_threshold", "mirror", "scale", "translate", "rotate"]
    body: int | None = Field(default=None, ge=1, strict=True)
    axis: Literal["X", "Y", "Z"] | None = None
    above_m: float | None = None
    below_m: float | None = None
    plane: Literal["XY", "XZ", "YZ"] | None = None
    factor: float | None = Field(default=None, gt=0.0)
    vector_m: tuple[float, float, float] | None = None
    angle_deg: float | None = None

    @model_validator(mode="after")
    def _its_own_keys(self) -> CadBodyOperation:
        own = {
            "delete": ("body",),
            "delete_by_threshold": ("axis",),
            "mirror": ("body", "plane"),
            "scale": ("body", "factor"),
            "translate": ("body", "vector_m"),
            "rotate": ("body", "axis", "angle_deg"),
        }[self.op]
        missing = [key for key in own if getattr(self, key) is None]
        if missing:
            raise ValueError(
                f"a CAD {self.op} states {', '.join(own)}; {', '.join(missing)} is not stated"
            )
        allowed = set(own) | ({"above_m", "below_m"} if self.op == "delete_by_threshold" else set())
        stated = {
            key for key in type(self).model_fields if key != "op" and getattr(self, key) is not None
        }
        if stated - allowed:
            raise ValueError(f"a CAD {self.op} does not read {', '.join(sorted(stated - allowed))}")
        if self.op == "delete_by_threshold" and (self.above_m is None) == (self.below_m is None):
            raise ValueError("a delete_by_threshold states one of above_m and below_m")
        _finite(
            [
                *(self.vector_m or ()),
                *(v for v in (self.angle_deg, self.above_m, self.below_m) if v is not None),
            ],
            "a CAD operation",
        )
        return self


class CadSource(BaseModel):
    """The ``[cad]`` source: an IGES file, its body operations, the conversion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str
    units: Literal["FILE"] = "FILE"
    options: CadImportOptions = Field(default_factory=CadImportOptions)
    operations: tuple[CadBodyOperation, ...] = ()


class CreateBody(BaseModel):
    """One ``[[create.bodies]]`` table: a solver primitive, in metres (FR-475 R2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shape: Literal["box", "sphere", "cylinder", "sheet"]
    center_m: tuple[float, float, float] | None = None
    corner_m: tuple[float, float, float] | None = None
    lengths_m: tuple[float, ...] | None = None
    radius_m: float | None = Field(default=None, gt=0.0)
    radii_m: tuple[float, float] | None = None
    length_m: float | None = Field(default=None, gt=0.0)
    plane: Literal["XY", "XZ", "YZ"] | None = None
    offset_m: float | None = None

    @model_validator(mode="after")
    def _its_own_keys(self) -> CreateBody:
        own = {
            "box": ("corner_m", "lengths_m"),
            "sphere": ("center_m", "radius_m"),
            "cylinder": ("center_m", "radii_m", "length_m"),
            "sheet": ("plane", "offset_m", "lengths_m"),
        }[self.shape]
        missing = [key for key in own if getattr(self, key) is None]
        stated = {
            key
            for key in type(self).model_fields
            if key != "shape" and getattr(self, key) is not None
        }
        if missing or stated - set(own):
            raise ValueError(
                f"a {self.shape} states {', '.join(own)}"
                + (f"; {', '.join(missing)} is not stated" if missing else "")
                + (
                    f"; it does not read {', '.join(sorted(stated - set(own)))}"
                    if stated - set(own)
                    else ""
                )
            )
        wanted = 3 if self.shape == "box" else 2
        if self.lengths_m is not None and (
            len(self.lengths_m) != wanted or min(self.lengths_m) <= 0
        ):
            raise ValueError(f"a {self.shape} states {wanted} lengths, each above zero")
        if self.radii_m is not None and min(self.radii_m) <= 0:
            raise ValueError("a cylinder's two radii are each above zero")
        return self


class CreateSection(BaseModel):
    """One ``[[create.sections]]`` table: a section file placed at a station (FR-475 R2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str
    format: Literal["txt"] = "txt"
    units: str
    chord_m: float = Field(gt=0.0)
    twist_deg: float = 0.0
    leading_edge_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    plane: Literal["XY", "XZ", "YZ"] = "XZ"


class CreateLoft(BaseModel):
    """``[create.loft]``: the CCS wing loft that ends the section route."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["wing"] = "wing"
    mark_trailing_edges: bool = True
    trailing_edge: Literal["SHARP", "BLUNT", "BLEND", "ROUNDED_BLEND", "OPEN"] = "SHARP"
    close_ends: Literal["TRUE", "OPEN", "CLOSED"] = "TRUE"
    loft_u: Literal["C2", "C0"] = "C2"
    loft_v: Literal["C2", "C0"] = "C0"
    export_ccs: bool = False


class CreateSource(BaseModel):
    """The ``[create]`` source: the CAD Create recipe (FR-475 R2, her P2-Q1 under G-Q12)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    merge_tolerance_pct: float | None = Field(default=None, gt=0.0)
    spline_segments: int | None = Field(default=None, ge=1, strict=True)
    spline_loft: Literal["C2", "C0"] | None = None
    curvature_points_per_circle: int | None = Field(default=None, ge=3, strict=True)
    bodies: tuple[CreateBody, ...] = ()
    sections: tuple[CreateSection, ...] = ()
    loft: CreateLoft | None = None

    @model_validator(mode="after")
    def _one_route(self) -> CreateSource:
        if bool(self.bodies) == bool(self.sections):
            raise ValueError(
                "[create] states [[create.bodies]] or [[create.sections]], exactly one of them"
            )
        if self.sections and len(self.sections) < 2:
            raise ValueError("a loft from sections states at least two [[create.sections]]")
        if self.bodies and self.loft is not None:
            raise ValueError("[create.loft] lofts sections; a [[create.bodies]] recipe states none")
        return self


class MeshSource(BaseModel):
    """The ``[mesh]`` source: a raw mesh and the unit it is written in."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str
    units: str


class GeometrySweep(BaseModel):
    """``[sweep]``: one control surface's deflection, one geometry per value (FR-472)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    control_surface: str
    angle_deg: tuple[float, ...]

    @model_validator(mode="after")
    def _distinct_values(self) -> GeometrySweep:
        if not self.angle_deg:
            raise ValueError("angle_deg lists the angles to build, at least one")
        _finite(self.angle_deg, "[sweep]")
        tags = [variant_tag(self.control_surface, angle) for angle in self.angle_deg]
        if len(set(tags)) != len(tags):
            raise ValueError(
                "two values of angle_deg give one tag (the tag keeps tenths of a degree): "
                + ", ".join(tags)
            )
        return self


def variant_tag(surface: str, angle_deg: float) -> str:
    """Return the tag of one deflection: ``AIL+100`` for 10 degrees, ``AIL-025`` for -2.5.

    Examples
    --------
    >>> variant_tag("AIL", 10.0), variant_tag("AIL", -2.5), variant_tag("AIL", 0.0)
    ('AIL+100', 'AIL-025', 'AIL+000')
    """
    tenths = round(angle_deg * 10)
    return f"{surface}{'-' if tenths < 0 else '+'}{abs(tenths):03d}"


SourceKind = Literal["ccs", "cad", "create", "mesh"]


class GeometryInstruction(BaseModel):
    """A whole instruction file, read and checked (FR-470).

    Attributes
    ----------
    name : str
        The stem of every built file.
    fs_build : str or None
        The build id the solver runs on; the command's ``--build`` may state it.
    outputs : tuple of str
        ``fsm``, ``obj`` or both.
    boundaries : tuple of str
        The names the saved body must carry, in order.
    kind : str
        Which source table the file states.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    fs_build: str | None = None
    outputs: tuple[Literal["fsm", "obj"], ...]
    boundaries: tuple[str, ...]
    kind: SourceKind
    ccs: CcsSource | None = None
    cad: CadSource | None = None
    create: CreateSource | None = None
    mesh: MeshSource | None = None
    operations: tuple[GeometryOperation, ...] = ()
    trailing_edges: TrailingEdgeMarking | None = None
    sweep: GeometrySweep | None = None

    @model_validator(mode="after")
    def _whole_file(self) -> GeometryInstruction:
        if not self.name or any(not (c.isalnum() or c in "_-") for c in self.name):
            raise ValueError(f"name = {self.name!r}; write letters, digits, _ and - only")
        if not self.outputs or len(set(self.outputs)) != len(self.outputs):
            raise ValueError('outputs lists "fsm", "obj" or both, each once')
        if not self.boundaries:
            raise ValueError("boundaries lists the names the saved body must carry; it is empty")
        for name in self.boundaries:
            _one_word(name, "the boundary name")
        if len(set(self.boundaries)) != len(self.boundaries):
            raise ValueError("boundaries names one surface twice")
        self._check_units()
        self._check_trailing_edges()
        self._check_sweep()
        if any(op.op == "transform_nodes" for op in self.operations) and self.kind != "mesh":
            raise ValueError(
                "transform_nodes moves nodes of a raw mesh; it is read for a [mesh] source only"
            )
        names = source_names(self)
        names_after(self, names)
        return self

    def _check_units(self) -> None:
        for unit in (
            None if self.mesh is None else self.mesh.units,
            None if self.ccs is None else self.ccs.units,
            *(section.units for section in (self.create.sections if self.create else ())),
        ):
            if unit == UNIT_THAT_NAMES_NO_LENGTH:
                raise ValueError(
                    f'units = "{UNIT_THAT_NAMES_NO_LENGTH}" names no length, so the solver would '
                    'choose the scale; write the unit the file is written in, such as "METER"'
                )
        if self.ccs is not None:
            route = self.ccs.options.kind == "file"
            if route != (self.ccs.units == "FILE"):
                raise ValueError(
                    'kind = "file" reads the file\'s own Units line and takes units = "FILE"; '
                    'a loft reads its curves in a length unit, such as units = "METER"'
                )
            if self.ccs.shedding is not None and not route:
                raise ValueError(
                    'shedding is read on kind = "file" only, the route that reads Relaxed_TE lines'
                )
            if any(surface.space == "REAL" for surface in self.ccs.options.control_surfaces):
                raise ValueError(
                    'a control surface with space = "REAL" is refused (RPT-097): write the '
                    'spanwise limits as fractions of the span and space = "PARAMETRIC"'
                )

    def _check_trailing_edges(self) -> None:
        marks_itself = self.kind == "ccs" or (
            self.create is not None and self.create.loft is not None
        )
        if marks_itself and self.trailing_edges is not None:
            raise ValueError(
                "[trailing_edges] is refused beside a CCS source or a section loft, which mark "
                "their own trailing edges (mark_trailing_edges); a second pass would mark twice"
            )

    def _check_sweep(self) -> None:
        if self.sweep is None:
            return
        if self.ccs is None or self.ccs.options.kind != "wing":
            raise ValueError(
                "[sweep] varies a control surface of a [ccs] wing, and the source is not one"
            )
        declared = [surface.name for surface in self.ccs.options.control_surfaces]
        if self.sweep.control_surface not in declared:
            raise ValueError(
                f"[sweep] varies {self.sweep.control_surface!r}, and the wing declares "
                f"{', '.join(declared) or 'no control surface'}"
            )

    def marks_trailing_edges(self) -> bool:
        """Return whether the built body must carry marked trailing edges (FR-471 R5)."""
        if self.ccs is not None:
            return self.ccs.options.kind == "wing" and self.ccs.options.mark_trailing_edges
        if self.create is not None and self.create.loft is not None:
            return self.create.loft.mark_trailing_edges
        return self.trailing_edges is not None and self.trailing_edges.route != "none"

    def source_file(self) -> str | None:
        """Return the file name the source table names, or None for a ``[create]`` recipe."""
        for source in (self.ccs, self.cad, self.mesh):
            if source is not None:
                return source.file
        return None


def source_names(instruction: GeometryInstruction) -> list[str]:
    """Return the names the source makes: ``boundaries`` with every operation undone.

    Raises
    ------
    ValueError
        When the stated boundaries are not what the operations leave.
    """
    names = list(instruction.boundaries)
    for position in range(len(instruction.operations), 0, -1):
        instruction.operations[position - 1].undo(names, position)
    return names


def names_after(
    instruction: GeometryInstruction, names: Sequence[str]
) -> list[tuple[str, tuple[str, ...]]]:
    """Return the names after the source and after each operation, refusing a mismatch."""
    current = list(names)
    steps = [("source", tuple(current))]
    for position, operation in enumerate(instruction.operations, start=1):
        operation.apply(current, position)
        steps.append((f"operation {position} ({operation.op})", tuple(current)))
    if tuple(current) != instruction.boundaries:
        raise ValueError(
            f"the operations leave {', '.join(current)} and boundaries states "
            f"{', '.join(instruction.boundaries)}"
        )
    return steps
