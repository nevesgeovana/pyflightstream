"""The 6DOF input a row names by its ``SIXDOF`` key (FR-461).

A file ``inputs/sixdof/d<id>.toml`` states a body free to move under its
loads: the moving families and the body frame, the mass and inertia, gravity,
the initial state, which of the six freedoms are free, and the forces applied
to it. Every vector key names its frame and its unit, because the solver reads
gravity in the REFERENCE system and velocities and forces in the BODY system,
and its arguments say neither (the command database's chapter notes).

This module imports only the floor, so the cases package may import it while
it loads; the file is read and hashed by
:mod:`pyflightstream.workspace.sixdof_setup`.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "SIXDOF_FREEDOMS",
    "SIXDOF_VARIABLE",
    "SixDofCustomForce",
    "SixDofExternalForce",
    "SixDofSpec",
    "SixDofSpringForce",
]

#: The row key naming a 6DOF input of ``inputs/sixdof/``.
SIXDOF_VARIABLE = "SIXDOF"

#: The six freedoms, in the order ``SET_MOTION_6DOF_ACTIVE_VARIABLES`` reads them.
SIXDOF_FREEDOMS: tuple[str, ...] = ("u", "v", "w", "p", "q", "r")

Vector = tuple[float, float, float]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SixDofMass(_Strict):
    """Mass and inertia, in the order ``SET_MOTION_MASS_PROPERTIES`` reads them."""

    mass_kg: float
    #: IXX, IYY, IZZ, IXY, IYZ, IZX: the third product pairs Z with X.
    inertia_kg_m2: tuple[float, float, float, float, float, float]

    @model_validator(mode="after")
    def _a_body(self) -> SixDofMass:
        if not self.mass_kg > 0.0:
            raise ValueError(f"[mass] mass_kg = {self.mass_kg}: a body's mass is above zero")
        ixx, iyy, izz, ixy, iyz, izx = self.inertia_kg_m2
        # Sylvester: a symmetric tensor is positive definite when its three
        # leading principal minors are.
        minor2 = ixx * iyy - ixy * ixy
        minor3 = (
            ixx * (iyy * izz - iyz * iyz)
            - ixy * (ixy * izz - iyz * izx)
            + izx * (ixy * iyz - iyy * izx)
        )
        if not (ixx > 0.0 and minor2 > 0.0 and minor3 > 0.0):
            raise ValueError(
                f"[mass] inertia_kg_m2 = {list(self.inertia_kg_m2)} (IXX, IYY, IZZ, IXY, IYZ, "
                "IZX) is not a positive definite inertia tensor; a rigid body's is"
            )
        return self


class SixDofGravity(_Strict):
    """Gravity, in the REFERENCE system."""

    vector_reference_m_per_s2: Vector = (0.0, 0.0, -9.80665)


class SixDofInitial(_Strict):
    """The initial state, in the BODY system."""

    velocity_body_m_per_s: Vector = (0.0, 0.0, 0.0)
    angular_velocity_body_deg_per_s: Vector = (0.0, 0.0, 0.0)


class SixDofFree(_Strict):
    """Which freedoms are free; every one is locked unless stated true."""

    u: bool = Field(default=False, strict=True)
    v: bool = Field(default=False, strict=True)
    w: bool = Field(default=False, strict=True)
    p: bool = Field(default=False, strict=True)
    q: bool = Field(default=False, strict=True)
    r: bool = Field(default=False, strict=True)


class SixDofExternalForce(_Strict):
    """A force at a body point for a window of time (``CREATE_NEW_6DOF_EXTERNAL_FORCE``)."""

    kind: Literal["external"]
    point_body_m: Vector
    force_body_n: Vector
    start_s: float = Field(ge=0.0)
    #: A DURATION, not an end time (the database note).
    duration_s: float

    @model_validator(mode="after")
    def _a_window(self) -> SixDofExternalForce:
        if not self.duration_s > 0.0:
            raise ValueError(
                f"[[forces]] external duration_s = {self.duration_s}: the force runs from "
                "start_s for duration_s, a duration above zero (not an end time)"
            )
        return self


class SixDofSpringForce(_Strict):
    """A spring on the body (``CREATE_NEW_6DOF_SPRING_FORCE``)."""

    kind: Literal["spring"]
    point_body_m: Vector
    axis_body: Vector
    free_length_m: float
    solid_length_m: float
    initial_length_m: float
    rate_n_per_m: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _lengths(self) -> SixDofSpringForce:
        lengths = (self.free_length_m, self.solid_length_m, self.initial_length_m)
        if min(lengths) <= 0.0:
            raise ValueError(
                "[[forces]] spring free_length_m, solid_length_m and initial_length_m are "
                f"each above zero (the manual), got {list(lengths)}"
            )
        if self.solid_length_m > self.free_length_m:
            raise ValueError(
                f"[[forces]] spring solid_length_m = {self.solid_length_m} exceeds "
                f"free_length_m = {self.free_length_m}: the fully compressed length is the shorter"
            )
        if math.hypot(*self.axis_body) == 0.0:
            raise ValueError("[[forces]] spring axis_body is a direction and cannot be zero")
        return self


class SixDofCustomForce(_Strict):
    """A force profile read from a staged file (``CREATE_NEW_6DOF_CUSTOM_FORCE``)."""

    kind: Literal["custom"]
    type: Literal["FORCE_VS_TIME", "FORCE_VS_DISTANCE"]
    #: A file of ``inputs/sixdof/``, by name; resolved and hashed by the plan.
    file: str = Field(min_length=1)
    #: The absolute path the plan resolved; never written by a user.
    resolved_file: str | None = Field(default=None, exclude=True)


SixDofForce = Annotated[
    SixDofExternalForce | SixDofSpringForce | SixDofCustomForce, Field(discriminator="kind")
]


class SixDofExport(_Strict):
    """What the motion exports."""

    trajectory: bool = Field(default=True, strict=True)


class SixDofSpec(_Strict):
    """One body free to move under its loads (FR-1084).

    Attributes
    ----------
    families : list of str
        The moving surfaces, by family name.
    frame : str
        The body frame, at the pivot: a frame the run creates.
    mass, gravity, initial, free : tables
        As their classes state.
    forces : list
        The applied forces, in the order written.
    symmetry_loads : bool
        Include the loads on the symmetry boundary (a mirrored half model).
    export : SixDofExport
        Whether the trajectory is exported.
    """

    families: list[str] = Field(min_length=1)
    frame: str = Field(min_length=1)
    mass: SixDofMass
    gravity: SixDofGravity = Field(default_factory=SixDofGravity)
    initial: SixDofInitial = Field(default_factory=SixDofInitial)
    free: SixDofFree = Field(default_factory=SixDofFree)
    forces: list[SixDofForce] = Field(default_factory=list)
    symmetry_loads: bool = Field(default=False, strict=True)
    export: SixDofExport = Field(default_factory=SixDofExport)

    @model_validator(mode="after")
    def _something_moves(self) -> SixDofSpec:
        if not any(getattr(self.free, name) for name in SIXDOF_FREEDOMS):
            raise ValueError(
                "[free] locks every freedom, so nothing moves and the row is an ordinary "
                "unsteady row; free at least one of u, v, w, p, q, r, or remove SIXDOF"
            )
        return self

    def active_lines(self) -> list[str]:
        """Return the six lines of ``SET_MOTION_6DOF_ACTIVE_VARIABLES``, U V W P Q R in order."""
        return [
            f"{name.upper()} {'ENABLE' if getattr(self.free, name) else 'DISABLE'}"
            for name in SIXDOF_FREEDOMS
        ]
