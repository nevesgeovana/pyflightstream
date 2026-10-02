"""The reference blocks of a geometry: rotors, actuator discs and blade datums (0.34.0).

Pipeline role: describes what the reference artifact declares about the moving
parts of a geometry. A :class:`RotorBlock` names a rotor's families, axis,
origin and hand; an :class:`ActuatorBlock` an actuator disc; a
:class:`BladeDatum` the in-plane direction a blade's frame is built from; and
:func:`frame_basis_for_shaft` turns a shaft axis into the frame the workflows
emit. The two errors a case definition raises live here too:
:class:`CampaignConfigError`, which every model of the package raises for a
definition that cannot be used as written, and :class:`AliasCycleError`.

The cut of AD-16 (0.34.0) moved these models out of the package root, which
re-exports every one of them. This module is the floor of the six model
modules: it imports none of them and never the package root.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pyflightstream._errors import PyflightstreamError

__all__ = [
    "AXIS_UNIT_VECTORS",
    "AliasCycleError",
    "BladeDatum",
    "ROTOR_BLADE_ROTATION_AXIS",
    "RotorBlock",
    "ActuatorBlock",
    "CampaignConfigError",
]


class CampaignConfigError(PyflightstreamError, ValueError):
    """A campaign or case definition cannot be used as written.

    A sweep point that cannot be tagged, a campaign file that does not
    load, a recipe that does not resolve to a callable or whose
    signature the loop cannot call. Distinct from
    :class:`~pyflightstream.cases.matrix.MatrixError`, which is about
    the pipe-delimited run-matrix format specifically.

    Added 2026-08-03 for FR-39, keeping ``ValueError`` as a second base.
    """


#: How closely a blade datum may lie along the shaft before its azimuth means
#: nothing. It is compared against `|cos(angle between shaft and datum)|`,
#: which is 1 when they are PARALLEL and 0 when they are square, so the
#: number is `cos(5 degrees)` and the refusal fires ABOVE it: a datum within
#: five degrees of the shaft is refused, and a datum at any other angle,
#: however far from square, is accepted.
#:
#: IT WAS `cos(85 degrees)` UNTIL 0.23.0's RELEASE ROUND, which is the
#: complement, and the complement refused every datum more than five degrees
#: from SQUARE -- an ordinary installation at 30 degrees among them. Both
#: datum tests of the day used a datum exactly square or one degree from
#: parallel, and those two verdicts are the same under either reading, so
#: nothing could tell them apart. The message made it worse by printing the
#: angle from the shaft and then saying the datum "nearly lies along" it.
#:
#: The FIVE is a JUDGEMENT rather than a measurement and is written as one;
#: what is not a judgement is that some bound must exist, because an axis that
#: can point anywhere makes "nearly parallel" the ordinary case.
_DATUM_ALIGNMENT_LIMIT = 0.9961946980917455

#: Below this, a vector has no length worth normalising and names no
#: direction. It is a LENGTH tolerance rather than a component one, so a
#: direction stated in millimetres is not refused for being small.
_AXIS_TOLERANCE = 1e-12

#: The unit vector each axis letter has always meant. The letter path resolves
#: through this rather than through a branch, so "Z is (0,0,1)" is a lookup a
#: reader can check instead of a claim.
#:
#: PUBLIC, and a guard made it so. It was `_AXIS_LETTERS` and `cases.workflows`
#: imported it from `cases`, which the layer test refuses: an underscore-private
#: name taken out of a public sibling is a boundary crossed for a helper.
#: Publishing it is the fix the guard names, and it is the honest one -- a
#: reader writing a rotor block needs to know what a letter means.
AXIS_UNIT_VECTORS: dict[str, tuple[float, float, float]] = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}

_AXIS_TOKEN = re.compile(r"^[+-]?[XYZ]$")

#: The axis a blade's azimuth is turned about, as the emitted command names it.
#:
#: IT IS A LETTER AND ALWAYS WILL BE, because the axis it names belongs to the
#: HUB FRAME rather than to the geometry. `ROTATE_COORDINATE_SYSTEM` declares
#: `rotation_axis` as an enum over X, Y, Z, 1, 2 and 3, and the blade frames are
#: turned about the hub -- whose third axis IS the shaft, by construction of
#: :func:`frame_basis_for_shaft`. So the shaft's direction rides on the FRAME
#: and never on this argument, and a rotor installed at any pitch and toe emits
#: the same letter as one installed square.
#:
#: The blade frame builder passed `rotor.axis` straight into that argument until
#: 0.23.0's release round, and `axis` had just been widened to take three
#: components -- so a rotor stating its installation vector emitted a PYTHON
#: TUPLE where the solver expects one letter. Nothing caught it because every
#: test of the item stopped at the basis and none emitted a script.
ROTOR_BLADE_ROTATION_AXIS = "Z"


class BladeDatum(BaseModel):
    """Where blade one sits, and the axis its azimuth is measured from (FR-60).

    The decision of 2026-09-10, on the first reading of the use case: an
    azimuth ALONE carries a hidden convention, zero at which axis, that
    two people fill differently and nobody sees. So the datum is written
    beside it: ``{ azimuth_deg = 45.0, zero = "X" }``, the zero being an
    axis letter with an optional sign, refused when it is parallel to the
    axis the rotor turns about, because an angle measured from that axis
    locates nothing.

    Attributes
    ----------
    azimuth_deg : float
        Where blade one is, measured from ``zero`` about the rotor's axis.
    zero : str
        The axis letter the azimuth is measured from, with at most one sign.
    """

    model_config = ConfigDict(extra="forbid")

    azimuth_deg: float = 0.0
    zero: str = "X"

    @field_validator("zero", mode="before")
    @classmethod
    def _an_axis_letter(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        token = value.strip().upper()
        # ONE SIGN AT MOST, and the pattern says so: `lstrip("+-")` strips a
        # RUN, so "+-X" and "-+X" validated and were then stored verbatim,
        # a spelling this package never meant to accept (the interface lens
        # of 2026-09-10).
        if not _AXIS_TOKEN.match(token):
            raise ValueError(
                f"blade1 states zero = {value!r}, which is not an axis; write X, Y or Z, "
                "with at most one leading sign. The sign reverses the direction the "
                "azimuth is measured FROM, not the sense in which it increases"
            )
        return token


class RotorBlock(BaseModel):
    """One rotor, declared as one block of the reference artifact (FR-60).

    The design of 2026-09-10. The block's NAME is an alias over
    everything the rotor owns, the union of :attr:`families_general` and
    :attr:`families_blades` in that order: what a row moves when it cites
    it, and what a group summing the rotor sums.

    THE NAME IS FREE, AND A TRAILING DIGIT IS FINE: the eight lifters of
    a four-a-side aircraft are ``LIFT_L1`` to ``LIFT_R4``. What it may
    not carry is ``_SMRP`` or ``_RMRP``, the radical of the frames the
    package builds from it (the static and rotating moment reference
    points of the rotor), because then a rotor and a frame spell the
    same. PFS-2035.02 said a name ending in a digit is refused, which was
    true of the frame names of 0.14.0 and would refuse the reference study
    under these: the number in ``<ALIAS>_RMRP<k>`` follows ``RMRP``, never
    the alias.

    Attributes
    ----------
    alias : str
        The word a row moves. It is the block's NAME, and this field is a
        restatement of it: a reference file may leave it out and the
        reader fills it in from the name before the block is built;
        stated, it must equal the name, case folded, and a block whose two
        names disagree is refused naming both. Whether the field is worth
        keeping at all is an open question of 2026-09-10.

        IT IS REQUIRED ON THE MODEL even though a file may omit it,
        because everything downstream reads it as the rotor's identity:
        it is the radical of the frames, the word written back into
        MOVING_BC_ALIAS, and what a refusal names. An optional field left
        None built frames called ``None_RMRP1`` rather than refusing, and
        a type check is what found it.
    x_m, y_m, z_m : float
        The hub, in the geometry's own frame.
    axis : str
        The axis it turns about.
    rpm_sign : int
        ``+1`` is the right-hand rule about ``axis``, which is the one
        reading that does not depend on where the reader stands.
    diameter_m : float
        The length an ADVANCE_RATIO resolves against, PER ROTOR: one
        ratio written once in the flight condition gives each rotor a
        speed of its own (FR-63).
    families_general : list of str
        What turns with the rotor and is NOT a blade, the spinner and the
        hub. It has no local axis of its own: its local frame IS the
        rotor's.
    families_blades : list of str
        One entry per blade, in order. THE BLADE COUNT IS THE LENGTH OF
        THIS LIST, so a row states no blade count and a sector mesh
        carrying one blade of four still reduces over four.
    blade1 : BladeDatum
        Where blade one sits, and the axis its azimuth is measured from.
    kind : str
        ``"rotor"``, which is what makes a top-level table of the reference
        a rotor block.
    """

    model_config = ConfigDict(extra="forbid")

    alias: str
    axis: str | tuple[float, float, float] | list[float]
    diameter_m: float = Field(gt=0.0)
    families_blades: list[str]
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    rpm_sign: int = 1
    families_general: list[str] = Field(default_factory=list)
    blade1: BladeDatum = Field(default_factory=BladeDatum)
    kind: str = "rotor"

    @property
    def blade_count(self) -> int:
        """The number of blades, which is the length of :attr:`families_blades`."""
        return len(self.families_blades)

    @property
    def members(self) -> list[str]:
        """Everything the rotor owns, general families first, in the order written."""
        return [*self.families_general, *self.families_blades]

    @property
    def origin(self) -> tuple[float, float, float]:
        """The hub, as the three coordinates a motion is built on."""
        return (self.x_m, self.y_m, self.z_m)

    @field_validator("axis", mode="before")
    @classmethod
    def _an_axis(cls, value: object) -> object:
        """Accept a LETTER or a three-component VECTOR (v0.23.0 item 19).

        The letter keeps its exact meaning: `Z` IS the vector (0, 0, 1), so the
        old spelling is a special case of the new one and every reference
        written before this release asks the solver for exactly what it always
        did. The vector exists because a mesh can arrive with its pitch and toe
        already in it, and a shaft installed at an angle lies on no geometry
        axis at all.
        """
        if isinstance(value, str):
            token = value.strip().upper()
            if token not in ("X", "Y", "Z"):
                # "not an axis" IS THE CONTRACT and the vocabulary test pins it:
                # it is the phrase a user greps for and the one the reference
                # documentation carries. Widening what `axis` accepts may add to
                # the sentence and may not replace it.
                raise ValueError(
                    f"axis = {value!r} is not an axis; write X, Y or Z, or the three "
                    "components of the shaft direction for a rotor installed at an angle"
                )
            return token
        if isinstance(value, (list, tuple)):
            if len(value) != 3:
                raise ValueError(
                    f"axis = {value!r} has {len(value)} components; a direction in space has three"
                )
            try:
                components = tuple(float(component) for component in value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"axis = {value!r} is not three numbers: {error}") from error
            length = math.sqrt(sum(component * component for component in components))
            if length <= _AXIS_TOLERANCE:
                raise ValueError(
                    f"axis = {value!r} has no length, so it names no direction, and a rotor "
                    "turns about a direction"
                )
            return components
        return value

    @property
    def axis_vector(self) -> tuple[float, float, float]:
        """The shaft direction as a UNIT vector, whichever way it was written.

        Every frame the package builds for this rotor is built on this, rather
        than on the geometry's own axes. Until 0.23.0 seven call sites created
        a rotor's frames with `x_axis=(1,0,0)` and `y_axis=(0,1,0)`, which is
        to assume the rotor is installed at zero pitch and zero toe.
        """
        stated = self.axis
        if isinstance(stated, str):
            return AXIS_UNIT_VECTORS[stated]
        components = tuple(float(component) for component in stated)
        length = math.sqrt(sum(component * component for component in components))
        return (components[0] / length, components[1] / length, components[2] / length)

    @field_validator("rpm_sign")
    @classmethod
    def _a_sign(cls, value: int) -> int:
        if value not in (1, -1):
            raise ValueError(
                f"rpm_sign = {value!r} is not a sign; write 1 or -1, where +1 is the "
                "right-hand rule about axis"
            )
        return value

    @model_validator(mode="after")
    def _a_rotor_with_blades_and_a_usable_datum(self) -> RotorBlock:
        if not self.families_blades:
            raise ValueError(
                "families_blades is empty, and the blade count is its length, so this "
                "rotor has no blades; name one mesh family per blade, in order"
            )
        # BY ANGLE AND NOT BY SPELLING since 0.23.0 item 19. This compared two
        # STRINGS, so it caught `axis = Z, zero = Z` and was blind to a shaft
        # at (0, 0.02, 0.9998) with a datum at Z, which is one degree from
        # parallel: an azimuth measured from it locates nothing and it reported
        # a number rather than refusing. A string comparison cannot see
        # "nearly", and once the axis can be any direction, nearly is the
        # ordinary case rather than the exotic one.
        shaft = self.axis_vector
        datum = AXIS_UNIT_VECTORS[self.blade1.zero.lstrip("+-")]
        alignment = abs(sum(a * b for a, b in zip(shaft, datum, strict=True)))
        if alignment > _DATUM_ALIGNMENT_LIMIT:
            degrees = math.degrees(math.acos(min(1.0, alignment)))
            raise ValueError(
                f"blade1 measures its azimuth from {self.blade1.zero}, which is "
                f"{degrees:.2f} degrees from the shaft direction {shaft}. An azimuth "
                "measured from a datum that nearly lies along the shaft locates nothing, "
                "so it is refused rather than reported. Choose a datum square to the disk"
            )
        return self


class ActuatorOperation(BaseModel):
    """An explicit action on one saved or newly created actuator, by its current name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Lifecycle action; disable remains subject to the selected build's command availability.
    op: Literal["rename", "delete", "enable", "disable"]
    #: Exact native actuator name at this step; no positional index is guessed.
    actuator: str = Field(min_length=1)
    #: New single-token native name, required only for rename.
    name: str | None = None

    @model_validator(mode="after")
    def _rename_has_its_own_name(self) -> ActuatorOperation:
        if (self.op == "rename") != (self.name is not None):
            raise ValueError("actuator rename requires name; other actions do not accept name")
        for value in (self.actuator, self.name):
            if value is not None and (not value.strip() or any(c.isspace() for c in value)):
                raise ValueError("actuator and rename name must be nonempty single-token names")
        return self


class ActuatorBlock(BaseModel):
    """One actuator disc, declared as one block of the reference artifact (G06).

    The linearized propeller slipstream the solver models with an actuator
    (SRC-003 pp.185-187). Its GEOMETRY is the configuration's, so it lives in
    the reference beside the rotors and the frames, as a top-level table with
    ``kind = "actuator"`` whose NAME is the disc's name; its LOADING is the
    condition's, so a row states it (``ACTUATOR``, ``ACTUATOR_RPM`` and one of
    ``ACTUATOR_THRUST`` or ``PROFILE``). A reference declaring a disc moves
    nothing on a row that names none.

    Attributes
    ----------
    kind : str
        ``"actuator"``, which is what makes a top-level table of the reference
        an actuator disc.
    frame : str
        The frame the disc's axis belongs to: a name the reference's
        ``[[frames]]`` declares, ``MRP``, or a rotor's frame. The command
        places a disc on a local frame, never on the reference frame, and a
        name the run did not create is refused when the script is built.
    axis : {'X', 'Y', 'Z'}
        The frame's axis the disc turns about.
    offset_m : float
        The disc's position along that axis, from the frame's origin.
    tip_radius_m : float
        The disc's outer radius.
    hub_radius_m : float
        The disc's inner radius, ``0 <= hub < tip``.
    rpm_sign : int
        ``+1`` is the right-hand rule about ``axis``, and the disc swirls as a
        rotor of this sign turns (FR-331, RPT-137); ``ACTUATOR_RPM`` is the magnitude.
    blades : int, optional
        The blade count a profile file's distribution is read per; required
        by a row stating ``PROFILE``.
    swirl : float, optional
        The fraction, 0 to 1, of the swirl velocity kept downstream
        (``SET_PROP_ACTUATOR_SWIRL``); unstated, no swirl command is emitted.
    profile_units : str
        The force unit a profile file is written in, as the command database
        spells ``SET_PROP_ACTUATOR_PROFILE``'s ``units_type``.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    kind: Literal["actuator"] = "actuator"
    frame: str
    axis: Literal["X", "Y", "Z"]
    offset_m: float = 0.0
    tip_radius_m: float = Field(gt=0.0)
    hub_radius_m: float = Field(ge=0.0)
    rpm_sign: int = 1
    blades: int | None = Field(default=None, ge=1)
    swirl: float | None = Field(default=None, ge=0.0, le=1.0)
    profile_units: Literal["NEWTONS", "KILO-NEWTONS", "POUND-FORCE", "KILOGRAM-FORCE"] = "NEWTONS"
    #: Native net-thrust convention for ACTUATOR_THRUST; independent of profile file units.
    thrust_units: Literal["NEWTONS", "POUNDS", "COEFFICIENT"] = "NEWTONS"
    #: Prescribed RIGID or flow-relaxed wake; omitted preserves the saved/native default.
    wake_type: Literal["RIGID", "RELAXED"] | None = None

    @field_validator("frame")
    @classmethod
    def _a_frame_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "frame names the frame the disc's axis belongs to, a name the reference's "
                "[[frames]] declares; it is empty"
            )
        return value

    @field_validator("rpm_sign")
    @classmethod
    def _a_sign(cls, value: int) -> int:
        if value not in (1, -1):
            raise ValueError(
                f"rpm_sign = {value!r} is not a sign; write 1 or -1, where +1 is the "
                "right-hand rule about axis"
            )
        return value

    @model_validator(mode="after")
    def _the_hub_is_inside_the_tip(self) -> ActuatorBlock:
        if self.hub_radius_m >= self.tip_radius_m:
            raise ValueError(
                f"hub_radius_m = {self.hub_radius_m} is not inside tip_radius_m = "
                f"{self.tip_radius_m}: a disc is the annulus between the two"
            )
        return self


def frame_basis_for_shaft(
    shaft: tuple[float, float, float],
    datum: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return the ``x_axis`` and ``y_axis`` of a frame whose THIRD axis is ``shaft``.

    v0.23.0 item 19. `coordinate_frame` completes a basis with the right-handed
    cross product, so handing it two axes square to the shaft puts the shaft on
    the frame's third axis by construction rather than by arithmetic anyone has
    to check.

    ``x_axis`` is the blade datum PROJECTED INTO THE DISK PLANE. That is what
    makes an azimuth well defined on a tilted rotor: the datum a user names is
    a direction in the geometry, and the angle is measured in the plane the
    blades actually sweep, not in the plane the geometry's axes happen to
    define. On an untilted rotor the projection changes nothing, which is why
    a reference written before this release produces the same frame.

    The caller is responsible for the datum not lying along the shaft;
    `RotorBlock` refuses that by ANGLE before anything reaches here.
    """
    along = sum(a * b for a, b in zip(shaft, datum, strict=True))
    projected = tuple(d - along * s for s, d in zip(shaft, datum, strict=True))
    length = math.sqrt(sum(component * component for component in projected))
    if length <= _AXIS_TOLERANCE:
        raise CampaignConfigError(
            f"the blade datum {datum} lies along the shaft {shaft}, so it projects to "
            "nothing in the disk plane and no azimuth can be measured from it"
        )
    x_axis = (projected[0] / length, projected[1] / length, projected[2] / length)
    y_axis = (
        shaft[1] * x_axis[2] - shaft[2] * x_axis[1],
        shaft[2] * x_axis[0] - shaft[0] * x_axis[2],
        shaft[0] * x_axis[1] - shaft[1] * x_axis[0],
    )
    return x_axis, y_axis


class AliasCycleError(PyflightstreamError, ValueError):
    """An alias resolves through itself, and both sides are named (FR-59).

    The design of 2026-09-10 lets an alias name another alias, resolved to
    the end. That is what makes a cycle possible, so the reader refuses one
    rather than recursing: the message names the alias that closed the ring
    and the member that closed it, because a reader holding only one of the
    two names has to open the file to find the other.
    """
