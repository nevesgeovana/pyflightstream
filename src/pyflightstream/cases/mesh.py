"""The mesh models: how a geometry enters the solver and what its mesh declares (0.34.0).

Pipeline role: describes the geometry side of a case. :class:`MeshImport` and
:class:`CadImportOptions` say how a mesh or a CAD file is imported;
:class:`MeshOperation` the operations applied to it; :class:`TrailingEdgeMarking`
how its trailing edges are found; :class:`RawMeshConditions` the boundary
conditions a raw mesh's sidecar declares; and :class:`BaseRegionOperation` and
:class:`PortBoundary` the base regions and the ports a setup declares.

The cut of AD-16 (0.34.0) moved these models out of the package root, which
re-exports every one of them. This module imports none of the other five model
modules and never the package root; :mod:`pyflightstream.cases.settings`
imports it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The CCS geometry table (0.32.0), a table of a geometry sidecar's [import]; its
# module imports only pydantic and the script row, so the package may import it
# while it loads.
from pyflightstream.cases._ccs import CcsImportOptions

__all__ = [
    "EVERY_SURFACE",
    "CadImportOptions",
    "MeshImport",
    "MeshOperation",
    "RawMeshConditions",
    "TrailingEdgeMarking",
    "BaseRegionOperation",
]


#: The word a mesh operation's ``surface`` takes for every surface of the file.
EVERY_SURFACE = "all"

#: The keys each mesh operation of an import states besides ``op`` and
#: ``surface`` (G03), and the only ones it may state.
_MESH_OPERATION_KEYS: Mapping[str, tuple[str, ...]] = {
    "scale": ("factors",),
    "rename": ("to",),
    "mirror": ("plane",),
    "translate": ("vector",),
    "rotate": ("axis", "angle_deg"),
}


class MeshOperation(BaseModel):
    """One mesh operation applied right after a raw mesh is imported (G03).

    Declared in the geometry's sidecar, beside the unit, as one
    ``[[import.operations]]`` table each, and applied in the order written,
    in the reference frame:

    * ``scale``: ``factors = [fx, fy, fz]``, each greater than zero;
    * ``rename``: ``surface`` and ``to``, the new name;
    * ``mirror``: ``surface`` and ``plane`` (``YZ``, ``XZ`` or ``XY``); the
      mirrored copy joins its source, so the surface count is unchanged;
    * ``translate``: ``vector = [x, y, z]``, in the ``[import]`` unit;
    * ``rotate``: ``axis`` (``X``, ``Y`` or ``Z``) and ``angle_deg``.

    ``surface`` names the surface acted on by the name the file gives it,
    or by a name an earlier rename gave; never by position. It is
    :data:`EVERY_SURFACE` by default, which ``rename`` and ``mirror`` do not
    take: each acts on one named surface.

    Attributes
    ----------
    op : {'scale', 'rename', 'mirror', 'translate', 'rotate'}
        Which operation, and so which of the keys below it states.
    surface : str
        The surface acted on, by the file's name or an earlier rename's;
        ``"all"`` for every surface, which a rename and a mirror do not take.
    factors : tuple of three floats, optional
        A scale's factor along each axis, each greater than zero.
    vector : tuple of three floats, optional
        A translation's vector, in the ``[import]`` unit.
    axis : {'X', 'Y', 'Z'}, optional
        The axis a rotation turns about.
    angle_deg : float, optional
        The angle of a rotation, in degrees.
    plane : {'YZ', 'XZ', 'XY'}, optional
        The plane a mirror reflects in; the copy joins its source.
    to : str, optional
        A rename's new name, one word.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["scale", "rename", "mirror", "translate", "rotate"]
    surface: str = EVERY_SURFACE
    factors: tuple[float, float, float] | None = None
    vector: tuple[float, float, float] | None = None
    axis: Literal["X", "Y", "Z"] | None = None
    angle_deg: float | None = None
    plane: Literal["YZ", "XZ", "XY"] | None = None
    to: str | None = None

    @field_validator("surface", "to", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _its_own_keys_and_sound_values(self) -> MeshOperation:
        own = _MESH_OPERATION_KEYS[self.op]
        every = {key for keys in _MESH_OPERATION_KEYS.values() for key in keys}
        missing = [key for key in own if getattr(self, key) is None]
        if missing:
            raise ValueError(
                f"a {self.op} states {' and '.join(own)}; {', '.join(missing)} is not stated"
            )
        foreign = sorted(key for key in every - set(own) if getattr(self, key) is not None)
        if foreign:
            raise ValueError(
                f"a {self.op} does not read {', '.join(foreign)}; it states "
                f"{' and '.join(own)} and, optionally, surface"
            )
        if not self.surface:
            raise ValueError(
                f'surface is empty; name a surface of the file, or write "{EVERY_SURFACE}"'
            )
        if self.op in ("rename", "mirror") and self.surface == EVERY_SURFACE:
            raise ValueError(
                f'a {self.op} names the surface it acts on, as surface = "<a name of the '
                'file>"; it has no every-surface form'
            )
        numbers = [*(self.factors or ()), *(self.vector or ())]
        if self.angle_deg is not None:
            numbers.append(self.angle_deg)
        if not all(math.isfinite(number) for number in numbers):
            raise ValueError(f"a {self.op} states a value that is not a finite number")
        if self.factors is not None and min(self.factors) <= 0:
            raise ValueError(
                f"each scale factor must be greater than zero, the manual's rule; "
                f"got {list(self.factors)}"
            )
        if self.to is not None and (not self.to or any(char.isspace() for char in self.to)):
            raise ValueError(
                f"to = {self.to!r} is not a surface name the solver reads as one word; "
                "write a name with no spaces"
            )
        if self.to == EVERY_SURFACE:
            raise ValueError(
                f'to = "{EVERY_SURFACE}" would name a surface with the word for every surface'
            )
        return self


class CadImportOptions(BaseModel):
    """Native CAD tessellation and conversion declared under [import.cad].

    The source file supplies its own units. These controls select how its
    bodies become a mesh; successful conversion does not establish mesh quality.

    Examples
    --------
    >>> options = CadImportOptions(body_index=2)
    >>> options.tessellation_density, options.num_curvature, options.body_index
    ('MEDIUM', 80, 2)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Native tessellation preset, as documented by IMPORT_CAD.
    tessellation_density: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    #: Include patches that the source CAD assembly does not reference.
    unreferenced_patches: bool = True
    #: Tessellation subdivisions around a complete circle, not a length.
    num_curvature: int = Field(default=80, gt=0, strict=True)
    #: Native CAD body index; -1 converts every body.
    body_index: int = Field(default=-1, strict=True)

    @field_validator("body_index")
    @classmethod
    def _positive_or_all(cls, value: int) -> int:
        if value != -1 and value < 1:
            raise ValueError("CAD body_index must be -1 (all bodies) or a positive index")
        return value


class MeshImport(BaseModel):
    """How a raw mesh is imported: the ``[import]`` table of its sidecar (G01).

    A raw mesh (``.obj``, ``.stl``) carries no length unit, so the file
    that names its boundaries, ``<stem>.boundaries.toml`` beside it,
    states the unit it is written in, and a workflow row naming the mesh
    is refused without it rather than imported under an assumed one.

    ``units`` goes to ``IMPORT`` and nowhere else. The simulation's own
    length unit is always metres, because every length the reference and
    the row state is in metres; the builder sets it after the import
    (:data:`pyflightstream.cases.workflows.SIMULATION_LENGTH_UNIT`). The
    value is only normalised here: which spellings a build takes is read
    from the command database by the builder, per build.

    CAD files additionally declare ``cad`` and ``units="FILE"`` because
    IMPORT_CAD has no units argument. CAD translations after conversion are
    in metres; tessellation is followed by explicit conversion to a mesh.

    ``operations`` are the mesh operations applied right after the import,
    in the order written (G03, :class:`MeshOperation`); empty when the
    table declares none.

    Attributes
    ----------
    units : str
        The raw mesh length unit, or FILE for CAD metadata; never assumed.
    operations : tuple of MeshOperation
        The mesh operations applied right after the import, in the order
        written.

    Examples
    --------
    >>> imported = MeshImport(units="mm")
    >>> imported.units, imported.operations
    ('MM', ())
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    units: str
    #: Explicit CAD conversion; units must be FILE because IMPORT_CAD reads file metadata.
    cad: CadImportOptions | None = None
    #: How a CCS file is lofted or imported by the solver's CCS commands (0.32.0).
    ccs: CcsImportOptions | None = None
    operations: tuple[MeshOperation, ...] = ()

    @field_validator("units", mode="before")
    @classmethod
    def _one_word_in_capitals(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        spelled = value.strip().upper()
        if not spelled:
            raise ValueError(
                "`units` is empty; write the length unit the mesh file is written in, "
                'as units = "MILLIMETER"'
            )
        return spelled

    @property
    def moving_operations(self) -> tuple[MeshOperation, ...]:
        """The operations that move, scale or copy the body: every one but ``rename``.

        A trailing-edge points file names edges of the mesh as the FILE
        holds it, and is checked against that file; one of these would
        carry the body's edges away from the points (G02).
        """
        return tuple(operation for operation in self.operations if operation.op != "rename")

    def names_after_renames(self, names: Sequence[str]) -> tuple[str, ...]:
        """Return the boundary names as this import's renames leave them, in order.

        The inventory a row cites for a raw mesh is the sidecar's
        ``boundaries`` as the ``rename`` operations leave them (G03), which
        is what the builder declares. This applies them and judges nothing:
        a rename whose surface is absent at its step, or carried twice, is
        passed over here and refused by the builder.
        """
        renamed = list(names)
        for operation in self.operations:
            if operation.op != "rename" or operation.to is None:
                continue
            found = [index for index, name in enumerate(renamed) if name == operation.surface]
            if len(found) == 1:
                renamed[found[0]] = operation.to
        return tuple(renamed)


#: The ``[trailing_edges]`` routes a raw mesh's sidecar may take (G02): a
#: file of edge mid-points, the default, or detection, applied only when
#: written.
TrailingEdgeRoute = Literal["file", "detect", "none"]


class TrailingEdgeMarking(BaseModel):
    """How a raw mesh's trailing edges are marked: its sidecar's ``[trailing_edges]`` (G02).

    A raw mesh carries no trailing edge, and without one the solver makes
    no wake and runs and answers anyway, so a raw mesh declares one.

    ``route = "file"`` is the default route. ``points_m`` are the mid-points
    of the trailing-edge mesh edges, in metres, the simulation's length unit, read
    from the points file the table names and checked against the mesh when
    the row is bound (:mod:`pyflightstream.workspace.wake_edges`); the
    builder writes them as the solver's node file and imports it with
    ``IMPORT_WAKE_EDGES_FROM_FILE``, giving every edge ``edge_type`` and
    matching within ``tolerance``. ``points_file`` is where they were read
    from, for a refusal to name; it is kept out of every dump, since it is
    a path on one machine.

    ``route = "detect"`` marks by the solver's detection:
    ``detect_surfaces`` names the surfaces to detect on, by the sidecar's
    names, and is empty for every surface; ``sweep_angle_deg`` is set
    before the detection when stated. Detection gives every edge the
    STANDARD type and reads no tolerance.

    Examples
    --------
    >>> marking = TrailingEdgeMarking(route="detect")
    >>> marking.route, marking.edge_type, marking.detect_surfaces
    ('detect', 'STANDARD', ())
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: TrailingEdgeRoute
    edge_type: str = "STANDARD"
    tolerance: float = 0.0001
    points_m: tuple[tuple[float, float, float], ...] = ()
    points_file: str | None = Field(default=None, exclude=True)
    detect_surfaces: tuple[str, ...] = ()
    sweep_angle_deg: float | None = None

    @field_validator("edge_type", mode="before")
    @classmethod
    def _one_word_in_capitals(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _one_route_and_sound_values(self) -> TrailingEdgeMarking:
        if self.route == "none":
            if (
                self.points_m
                or self.points_file
                or self.detect_surfaces
                or self.sweep_angle_deg is not None
            ):
                raise ValueError("no trailing edge cannot also supply points or detection")
            return self
        if not math.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise ValueError(
                f"tolerance = {self.tolerance!r}; it is the distance, in the simulation's "
                "length unit, within which an edge's mid-point counts as a point of the "
                "file, and it must be positive and finite"
            )
        if self.route == "file":
            if self.detect_surfaces or self.sweep_angle_deg is not None:
                raise ValueError("the file route takes no detection surfaces and no sweep angle")
            return self
        if self.points_m or self.points_file is not None:
            raise ValueError("the detect route reads no points file")
        if not all(name.strip() for name in self.detect_surfaces):
            raise ValueError("a detection surface is named by an empty string")
        if self.sweep_angle_deg is not None and not math.isfinite(self.sweep_angle_deg):
            raise ValueError(f"sweep_angle = {self.sweep_angle_deg!r} is not a finite number")
        return self


class RadialBoundaryMesh(BaseModel):
    """A radial inlet/outlet mesh, applied after port creation and before initialization."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    #: Inner hole radius in metres; zero requests a disk instead of an annulus.
    inner_radius_m: float = Field(default=0.0, ge=0)
    #: Number of radial faces created from each wall boundary edge.
    radial_faces: int = Field(ge=1)
    #: Successive radial growth or growth from both sides, native scheme 1 or 2.
    growth_scheme: Literal["successive", "dual_sided"] = "successive"
    #: Radial growth factor; one is uniform, greater than one refines the outer wall.
    growth_rate: float = Field(default=1.0, gt=0)


class BaseRegionOperation(BaseModel):
    """One explicit base-region action, executed in its declared order before initialization."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    #: Action on a base region; select_faces changes application selection, not the flow model.
    operation: Literal[
        "create",
        "set_pressure",
        "delete",
        "mark_trailing_edges",
        "mark_outflow_edges",
        "remesh",
        "select_faces",
    ]
    #: Mesh boundary for creation or outflow marking; all is only allowed for outflow marking.
    boundary: str | Annotated[int, Field(ge=1)] | None = None
    #: Current base-region index; all is only allowed for trailing-edge marking or face selection.
    index: Annotated[int, Field(ge=1)] | Literal["all"] | None = None
    #: Explicit pressure model; USER is a creator token, while the setter requires CUSTOM.
    model: Literal["EMPIRICAL", "AXISYMMETRIC", "USER", "CUSTOM"] | None = None
    #: Pressure coefficient; required by creation and a CUSTOM pressure update.
    cp: float | None = None
    #: Radial remesh parameters; applied to the selected region, with radius stated in metres.
    mesh: RadialBoundaryMesh | None = None

    @model_validator(mode="after")
    def _arguments_match_operation(self) -> BaseRegionOperation:
        allowed = {
            "create": {"boundary", "model", "cp"},
            "mark_outflow_edges": {"boundary"},
            "set_pressure": {"index", "model", "cp"},
            "remesh": {"index", "mesh"},
        }.get(self.operation, {"index"})
        for name in ("boundary", "index", "model", "cp", "mesh"):
            if name not in allowed and getattr(self, name) is not None:
                raise ValueError(f"{name} does not apply to base-region {self.operation}")
        if self.operation == "create":
            if self.boundary is None or self.model is None or self.cp is None:
                raise ValueError("base-region create requires boundary, model and cp")
            if isinstance(self.boundary, str) and not self.boundary.strip():
                raise ValueError("base-region boundary cannot be empty")
        elif self.operation == "mark_outflow_edges":
            if self.boundary is None or self.boundary == "":
                raise ValueError("base-region mark_outflow_edges requires boundary")
        elif self.index is None:
            raise ValueError(f"base-region {self.operation} requires index")
        if self.boundary == "all" and self.operation != "mark_outflow_edges":
            raise ValueError("base-region create has no documented all form")
        if self.index == "all" and self.operation not in {"mark_trailing_edges", "select_faces"}:
            raise ValueError(f"base-region {self.operation} has no documented all form")
        if self.operation == "set_pressure":
            if self.model is None or self.model == "USER":
                raise ValueError(
                    "base-region set_pressure requires EMPIRICAL, AXISYMMETRIC or CUSTOM"
                )
            if self.model == "CUSTOM" and self.cp is None:
                raise ValueError("CUSTOM base pressure requires cp")
        if self.operation == "remesh" and self.mesh is None:
            raise ValueError("base-region remesh requires mesh parameters")
        return self


class PortBoundary(BaseModel):
    """A normal-velocity inlet or outlet; an inlet may also bind a native profile."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    #: Geometry-sidecar port identity selected by the setup.
    port: str | None = Field(default=None, min_length=1)
    #: Physical role of the selected port, independent of its geometric identity.
    kind: Literal["inlet", "outlet"] | None = None
    #: MATRIX key carrying signed native velocity; defaults to <PORT>_VELOCITY when omitted.
    velocity_variable: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    #: Optional MATRIX key naming a profile under inputs/profiles; no profile when omitted.
    profile_variable: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    #: Resolved exact surface name; workspace setups use port instead of declaring this value.
    boundary: str | None = Field(default=None, min_length=1)
    #: Resolved signed velocity in simulation units; the workspace reads its MATRIX variable.
    velocity: float | None = None
    #: Optional inlet-profile file; exact bytes are staged, with native format unchanged.
    profile: str | None = None
    #: Optional radial remesh, performed before assigning the inlet profile.
    remesh: RadialBoundaryMesh | None = None
    #: Source digest captured by workspace binding and checked before staging.
    profile_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _port_source_is_unambiguous(self) -> PortBoundary:
        if self.kind == "outlet" and (
            self.profile is not None or self.profile_variable is not None
        ):
            raise ValueError("an outlet profile has no documented native command")
        if self.port is not None and self.kind is None:
            raise ValueError("a setup port requires kind = inlet or outlet")
        if self.port is None and (self.boundary is None or self.velocity is None):
            raise ValueError(
                "a port requires a geometry identity or a resolved boundary and velocity"
            )
        return self


class RawMeshConditions(BaseModel):
    """The boundary conditions a raw mesh's sidecar declares (G02, Q1 of 0.27.0).

    ``trailing_edges`` is required of every raw mesh a workflow imports,
    and the builder refuses one without it. ``wake_termination`` detects
    wake-termination nodes, ``"auto"`` over every surface or by the
    surfaces named; ``base_regions = "auto"`` detects base regions over
    the whole mesh. Both are None unless written.

    Examples
    --------
    >>> conditions = RawMeshConditions(
    ...     trailing_edges=TrailingEdgeMarking(route="detect"), base_regions="auto"
    ... )
    >>> conditions.trailing_edges.route, conditions.wake_termination, conditions.base_regions
    ('detect', None, 'auto')
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Stable geometric port identities mapped to exact surface names after import renames.
    ports: dict[str, str] = Field(default_factory=dict)
    trailing_edges: TrailingEdgeMarking | None = None
    wake_termination: Literal["auto"] | tuple[str, ...] | None = None
    base_regions: Literal["auto"] | None = None
    inlets: tuple[PortBoundary, ...] = ()
    outlets: tuple[PortBoundary, ...] = ()

    @model_validator(mode="after")
    def _one_port_per_boundary(self) -> RawMeshConditions:
        # A port's boundary may still be unresolved (None) here; two such ports are
        # refused as one boundary, as they always were.
        seen: set[str | None] = set()
        for port in (*self.inlets, *self.outlets):
            if port.boundary in seen:
                raise ValueError(
                    f"boundary {port.boundary!r} assigned more than once to inlet/outlet ports; "
                    "the native solver can replace the prior assignment and renumber the ports"
                )
            seen.add(port.boundary)
        return self
