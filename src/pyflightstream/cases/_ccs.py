"""The CCS geometry route's vocabulary: the sidecar table, the row key, the file reader.

Pipeline role: the cases row, the declarations the plan binds and the builders
read. A matrix row names a CCS file (Component Cross-Section, the solver's
parametric geometry format, which the manual says may carry the ``.ccs`` or the
``.csv`` extension) in its ``GEOMETRY`` cell, and the ``[import.ccs]`` table of
the file's ``<stem>.boundaries.toml`` says how the solver makes a mesh of it
(0.32.0, FR-240 to FR-244)::

    boundaries = ["WING"]

    [import]
    units = "METER"

    [import.ccs]
    kind = "wing"
    component = 1

    [[import.ccs.control_surfaces]]
    name = "AIL"
    v0 = 0.5
    v1 = 0.9
    u0 = 0.25
    u1 = 0.25
    hinge_height = 0.5
    angle_deg = 20.0
    slot_gap_pct = 1.0

``kind`` is ``wing``, ``fuselage`` or ``revolution`` for the CURVE ROUTE, which
lofts ONE component (``component``, counted from 1 in the file's order) and
names the boundary it makes after the sidecar's first ``boundaries`` entry;
``kind = "file"`` is the FILE ROUTE, ``CCS_IMPORT``, which imports every
component whole and names each boundary after its ``Component`` line. The route
is emitted by :func:`pyflightstream.cases.ccs_wing.emit_ccs_geometry`.

This module imports only pydantic and the script row's relaxed trailing-edge
reader, so :mod:`pyflightstream.cases` may import it while it loads, as it
imports :mod:`pyflightstream.cases.corrections`: the table is a field of
:class:`~pyflightstream.cases.MeshImport`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pyflightstream.script import helpers

__all__ = [
    "CCS_FORMATS",
    "CCS_KINDS",
    "CCS_LOFT_KINDS",
    "CCS_SHEDDING_COPY_SUFFIX",
    "CCS_SHEDDING_VARIABLE",
    "CcsControlSurface",
    "CcsImportOptions",
    "CcsSubdivisions",
    "ccs_component_names",
    "restate_relaxed_trailing_edges",
]

#: The suffixes a workflow reads as a CCS file. The manual states both, so the
#: suffix routes the file and says nothing more about its content.
CCS_FORMATS = frozenset({".ccs", ".csv"})

#: The three kinds the curve route lofts, one component each.
CCS_LOFT_KINDS: tuple[str, ...] = ("wing", "fuselage", "revolution")

#: Every kind the ``[import.ccs]`` table takes: the three lofts and ``file``.
CCS_KINDS: tuple[str, ...] = (*CCS_LOFT_KINDS, "file")

#: G35: the row key choosing the direction of every ``Relaxed_TE`` shedding line
#: of a CCS file imported by the file route, ``AXIAL`` (0) or ``AZIMUTH`` (1).
CCS_SHEDDING_VARIABLE = "CCS_SHEDDING"

#: What the run's own copy of a CCS file restated in the row's direction is
#: called, after the stem of the user's file: ``g35.csv`` is imported as
#: ``g35.ccs_shedding.csv`` from the folder the script runs in.
CCS_SHEDDING_COPY_SUFFIX = ".ccs_shedding"

#: The keys each kind reads beyond ``kind``; a key set on another kind is refused.
_KIND_KEYS: dict[str, frozenset[str]] = {
    "wing": frozenset(
        {
            "component",
            "mark_trailing_edges",
            "trailing_edge",
            "close_ends",
            "loft_u",
            "loft_v",
            "subdivisions",
            "control_surfaces",
        }
    ),
    "fuselage": frozenset({"component", "close_ends", "loft_u", "loft_v"}),
    "revolution": frozenset(
        {"component", "close_ends", "loft_u", "loft_v", "axis", "start_angle_deg", "end_angle_deg"}
    ),
    "file": frozenset(),
}

#: The documented loft defaults: C2 chordwise and C0 spanwise on a wing, C2 in
#: both directions on a fuselage and a body of revolution (SRC-752 p.83).
_LOFT_DEFAULTS: dict[str, tuple[str, str]] = {
    "wing": ("C2", "C0"),
    "fuselage": ("C2", "C2"),
    "revolution": ("C2", "C2"),
}


def _one_token(value: str, what: str) -> str:
    """Refuse a name the solver's line would split into several tokens."""
    if not value or any(character.isspace() for character in value):
        raise ValueError(
            f"{what} {value!r} is empty or carries whitespace, and the solver reads the "
            "line as tokens separated by spaces; write one word, such as AIL"
        )
    return value


class CcsControlSurface(BaseModel):
    """One gapped control surface of a CCS wing (CCS-2), ``[[import.ccs.control_surfaces]]``.

    The ten parameters of ``NEW_CCS_WING_CONTROL_SURFACE`` (SRC-752 p.303),
    every one written on the line: licensed round 1 on 26.124 refused the
    eight-token line the manual's sample prints, so SPACE and AXIS are never
    left out. The ranges are the manual's: the spanwise limits between 0 and 1
    in PARAMETRIC space with ``v1`` above ``v0``, the chordwise depths from the
    trailing edge above 0 and below 0.5, the hinge between the upper (0) and
    the lower (1) surface.

    Attributes
    ----------
    name : str
        The control surface's name, one word.
    v0, v1 : float
        Inner and outer spanwise limits, parametric (0 to 1) or, with
        ``space = "REAL"``, coordinates along ``axis`` of the reference frame.
    u0, u1 : float
        Chordwise depths at the inner and outer limits, from the trailing edge.
    hinge_height : float
        Hinge height from the upper surface downward, 0.5 at mid thickness.
    angle_deg : float
        Deflection angle, in degrees.
    slot_gap_pct : float
        Slot gap on either side, in percent of span.
    space : str
        ``PARAMETRIC`` (the default) or ``REAL``.
    axis : str
        The reference axis of REAL spanwise limits; written on every line.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: The control surface's name, one word.
    name: str
    #: Inner spanwise limit.
    v0: float
    #: Outer spanwise limit, above the inner one.
    v1: float
    #: Chordwise depth at the inner limit, from the trailing edge, in (0, 0.5).
    u0: float = Field(gt=0.0, lt=0.5)
    #: Chordwise depth at the outer limit, from the trailing edge, in (0, 0.5).
    u1: float = Field(gt=0.0, lt=0.5)
    #: Hinge height from the upper surface downward, 0 to 1.
    hinge_height: float = Field(ge=0.0, le=1.0)
    #: Deflection angle, in degrees.
    angle_deg: float
    #: Slot gap on either side, in percent of span.
    slot_gap_pct: float = Field(ge=0.0)
    #: How the spanwise limits are read: PARAMETRIC or REAL.
    space: Literal["PARAMETRIC", "REAL"] = "PARAMETRIC"
    #: The reference axis REAL spanwise limits lie along.
    axis: Literal["X", "Y", "Z"] = "Y"

    @field_validator("name")
    @classmethod
    def _name_is_one_word(cls, value: str) -> str:
        return _one_token(value, "the control surface name")

    @model_validator(mode="after")
    def _spanwise_limits_hold(self) -> CcsControlSurface:
        if self.v1 <= self.v0:
            raise ValueError(
                f"v1 ({self.v1}) is not above v0 ({self.v0}); the outer spanwise limit "
                "of a control surface lies beyond the inner one (SRC-752 p.303)"
            )
        if self.space == "PARAMETRIC" and not (0.0 <= self.v0 and self.v1 <= 1.0):
            raise ValueError(
                f"v0 and v1 ({self.v0}, {self.v1}) are PARAMETRIC spanwise limits and lie "
                'between 0 and 1; write space = "REAL" for coordinates along an axis'
            )
        return self


class CcsSubdivisions(BaseModel):
    """The node counts of a CCS wing mesh, ``subdivisions = { chord = 30, span = 12 }``.

    Each one stated becomes a ``CCS_WING_MESH_SUBDIVISIONS`` line before the
    loft; round 1 on 26.124 measured ``CHORD 30`` changing the wing's faces
    from 4484 to 588 (C2 against C1).

    Attributes
    ----------
    chord : int or None
        Grid nodes in the chordwise direction.
    span : int or None
        Grid nodes in the spanwise direction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Grid nodes in the chordwise direction.
    chord: int | None = Field(default=None, gt=0, strict=True)
    #: Grid nodes in the spanwise direction.
    span: int | None = Field(default=None, gt=0, strict=True)


class CcsImportOptions(BaseModel):
    """How a CCS file becomes a mesh: the ``[import.ccs]`` table of its sidecar (0.32.0).

    Attributes
    ----------
    kind : str
        ``wing``, ``fuselage`` or ``revolution`` (the curve route, one
        component), or ``file`` (``CCS_IMPORT``, every component).
    component : int or None
        The component the curve route lofts, counted from 1 in the file.
    mark_trailing_edges : bool
        Whether the wing loft marks its trailing edges (a wing only).
    trailing_edge : str
        The wing's trailing-edge geometry (a wing only).
    close_ends : str
        Whether the loft closes the component's ends.
    loft_u, loft_v : str or None
        The loft continuity in the component's two directions; None takes
        the kind's documented default.
    axis : str
        The reference axis a body of revolution turns about.
    start_angle_deg, end_angle_deg : float
        The angles a body of revolution is swept between.
    subdivisions : CcsSubdivisions or None
        The wing mesh's node counts (a wing only).
    control_surfaces : tuple of CcsControlSurface
        The wing's gapped control surfaces (a wing only).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: wing, fuselage or revolution (the curve route), or file (CCS_IMPORT).
    kind: Literal["wing", "fuselage", "revolution", "file"]
    #: The component the curve route lofts, counted from 1 in the file's order.
    component: int | None = Field(default=None, ge=1, strict=True)
    #: Whether the wing loft marks its trailing edges.
    mark_trailing_edges: bool = True
    #: The wing's trailing-edge geometry.
    trailing_edge: Literal["SHARP", "BLUNT", "BLEND", "OPEN"] = "SHARP"
    #: Whether the loft closes the component's ends (TRUE, OPEN or CLOSED).
    close_ends: Literal["TRUE", "OPEN", "CLOSED"] = "TRUE"
    #: Loft continuity chordwise on a wing, radial on a fuselage or body of revolution.
    loft_u: Literal["C2", "C0"] | None = None
    #: Loft continuity spanwise on a wing, axial on a fuselage or body of revolution.
    loft_v: Literal["C2", "C0"] | None = None
    #: The reference axis a body of revolution turns about.
    axis: Literal["X", "Y", "Z"] = "X"
    #: The angle a body of revolution starts at, in degrees.
    start_angle_deg: float = 0.0
    #: The angle a body of revolution ends at, in degrees.
    end_angle_deg: float = 360.0
    #: The wing mesh's node counts, each a CCS_WING_MESH_SUBDIVISIONS line.
    subdivisions: CcsSubdivisions | None = None
    #: The wing's gapped control surfaces, each a NEW_CCS_WING_CONTROL_SURFACE line.
    control_surfaces: tuple[CcsControlSurface, ...] = ()

    @model_validator(mode="after")
    def _keys_of_the_kind(self) -> CcsImportOptions:
        allowed = _KIND_KEYS[self.kind]
        stray = sorted(self.model_fields_set - allowed - {"kind"})
        if stray:
            raise ValueError(
                f"kind = {self.kind!r} reads {', '.join(sorted(allowed)) or 'no other key'}, "
                f"and the table also states {', '.join(stray)}, which that kind does not "
                "read; delete it rather than leave a key nothing applies"
            )
        if self.kind in CCS_LOFT_KINDS and self.component is None:
            raise ValueError(
                f"kind = {self.kind!r} lofts one component of the file and the table names "
                "none; write component = 1 for the file's first Component line"
            )
        return self

    @property
    def lofts(self) -> tuple[str, str]:
        """The two loft continuities the line writes, a default filled where none is stated."""
        default_u, default_v = _LOFT_DEFAULTS.get(self.kind, ("C2", "C2"))
        return (self.loft_u or default_u, self.loft_v or default_v)


def ccs_component_names(text: str) -> tuple[str, ...]:
    """Return the component names a CCS file declares, in the file's order.

    Parameters
    ----------
    text : str
        The CCS file's text.

    Returns
    -------
    tuple of str
        The second field of every ``Component;<name>`` line, which is the
        name the file route gives each boundary (round 1, C0 on 26.124).
    """
    names = []
    for line in text.splitlines():
        fields = [field.strip() for field in line.split(";")]
        if len(fields) >= 2 and fields[0].casefold() == "component":
            names.append(fields[1])
    return tuple(names)


def restate_relaxed_trailing_edges(text: str, direction: str | int) -> tuple[str, int]:
    """Restate every ``Relaxed_TE`` line of a CCS file in one shedding direction (G35).

    Parameters
    ----------
    text : str
        The CCS file's text.
    direction : str or int
        ``AXIAL``/0 or ``AZIMUTH``/1.

    Returns
    -------
    tuple of (str, int)
        The restated text, every other byte as it was, and how many
        ``Relaxed_TE`` lines the file carries.

    Raises
    ------
    CommandArgumentError
        A ``Relaxed_TE`` line the reader refuses, or a direction that is
        neither, from :func:`pyflightstream.script.helpers.parse_relaxed_trailing_edge`.
    """
    lines = text.splitlines(keepends=True)
    count = 0
    for position, line in enumerate(lines):
        body = line.rstrip("\r\n")
        if body.split(";", 1)[0].strip().casefold() != helpers.RELAXED_TE_KEYWORD.casefold():
            continue
        count += 1
        edge = helpers.parse_relaxed_trailing_edge(body).with_shedding(direction)
        lines[position] = edge.render() + line[len(body) :]
    return "".join(lines), count
