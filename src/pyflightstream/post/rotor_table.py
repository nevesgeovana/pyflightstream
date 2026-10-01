"""The rotor table: one coefficient table per rotor the reference declares.

One of the product families of :mod:`pyflightstream.post` (AD-13, work
package WP5 of 0.33.0), written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports every name here.

``polars/P<sim>-<sweep>_<ROTOR>_rotor.csv``: one row per point, the rotor's
loads in its own shaft frame (:class:`RotorShaftLoads`,
:func:`rotor_shaft_loads`) and its thrust, torque and power coefficients
with the in-plane ones (:func:`rotor_coefficients`,
:data:`ROTOR_COEFFICIENT_COLUMNS`, :data:`ROTOR_IN_PLANE_COLUMNS`,
:func:`rotor_coefficient_columns`), written by :func:`write_rotor_table`.
The geometry comes from the reference file the matrix row names, not from
the record, which keeps neither the shaft, the hub nor the diameter. An
unsteady row reads the rotor's plot group, time-averaged over the row's
window (the plan of :mod:`pyflightstream.post._rotor_plan` names the group a
rotor's history is read from); a steady row reads its loads export.

The rotor products of the backlog that are tables of a rotor per point (a
trimmed rotor, a further coefficient set) join this module beside the
writer they extend.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._tokens import POLAR_ID_COLUMN, ROTOR_ID_COLUMN
from pyflightstream.cases import (
    select_group_members,
)
from pyflightstream.cases.workflows import (
    rotor_mach_numbers,
)
from pyflightstream.post._tables import (
    CONTEXT_COLUMNS,
    NOT_APPLICABLE,
    ProductError,
    ReferenceValues,
    context_row,
    write_csv_table,
)
from pyflightstream.post.axes import (
    free_stream_in_export_frame,
    rotor_in_plane_axes,
    rotor_in_plane_loads,
)
from pyflightstream.post.polar import GEOMETRY_ANALYSIS_FRAMES

if TYPE_CHECKING:
    pass

__all__ = [
    "ROTOR_COEFFICIENT_COLUMNS",
    "ROTOR_IN_PLANE_COLUMNS",
    "RotorShaftLoads",
    "rotor_coefficient_columns",
    "rotor_coefficients",
    "rotor_shaft_loads",
    "write_rotor_table",
]


#: The six coefficients a rotor table carries, in this order, for each rotor:
#: J, CT, CQ, CP, ETA and ETAW (the efficiency in wind axes).
ROTOR_COEFFICIENT_COLUMNS: tuple[str, ...] = ("J", "CT", "CQ", "CP", "ETA", "ETAW")


#: The rotor's in-plane coefficients (0.31.0, G8), the LAST four columns of its
#: table, after `MTIP_<alias>` and `MHEL_<alias>`: the force along the normal
#: and side axes and the moment about them, in the rotor's `(T, S, N)` axes
#: (:func:`pyflightstream.post.axes.rotor_in_plane_axes`).
ROTOR_IN_PLANE_COLUMNS: tuple[str, ...] = ("CN", "CS", "CMN", "CMS")


# `rotor_table_alias_line` WAS HERE, and 0.27.0 (G16) retired it with the line it
# wrote. From 0.23.0 (item 18) a rotor table opened with its alias alone on the
# first line, because a script that has LOADED the file no longer has its name
# and the alias has to be inside the bytes. That reason stands; the form did not:
# a line before the header is a file no CSV reader takes as written. The alias is
# the `ROTOR` column now, right after `POL`, on every row, so a loaded table still
# knows which rotor and which polar it holds, and its first line is the header.


def rotor_coefficient_columns(alias: str) -> tuple[str, ...]:
    """Return the rotor coefficient columns of ONE rotor, suffixed with its alias.

    The constraint is physical rather than cosmetic: these coefficients have a
    physical meaning for one rotor only, never for several together. Two rotors
    summed into one CT is not a worse CT, it is not a CT at all -- the diameters and
    the speeds that normalise it are different numbers. The alias in every
    column name is what makes summing them impossible by accident.
    """
    token = str(alias).strip()
    if not token:
        raise ProductError("a rotor coefficient column needs the rotor's alias to carry")
    return tuple(f"{name}_{token}" for name in ROTOR_COEFFICIENT_COLUMNS)


@dataclass(frozen=True)
class RotorShaftLoads:
    """One rotor's thrust and torque about its OWN shaft, in newtons and N m.

    ``wind_force_n`` is the rotor's force along the FREE STREAM, which is what
    `ETAW` is built on. ``shaft_angle_deg`` is the angle between the shaft and
    that same stream; it is kept because it is a fact a reader of the table may
    want, and it is NO LONGER what `ETAW` is computed from.

    WHY BOTH, AND WHY THE ANGLE IS NOT ENOUGH. `ETAW` was formerly
    `ETA * cos(theta)`, and that was wrong. A cosine projects the SHAFT direction
    and therefore keeps only the thrust that lies along the shaft --
    it discards every component of the rotor's force that does not, which on an
    installed rotor is exactly the part the definition keeps. The definition:

        [Fx_rotor_axis Fy_rotor_axis Fz_rotor_axis] * R^T(rotor axes ->
        airframe body axes) * R(alpha) = Fx_W

    with both alpha AND beta applied by the AIAA axis convention, and `ETAW`
    still a dimensionless efficiency.
    """

    thrust_n: float
    torque_nm: float
    shaft_angle_deg: float
    wind_force_n: float
    families_used: tuple[str, ...]
    #: The rotor's force in N and its moment about the HUB in N m, both in the
    #: loads frame's axes, of which the thrust and the torque are the shaft
    #: components; None where those two are not a number (0.30.0, for the
    #: quasi-steady rotor's in-plane loads).
    force_n: tuple[float, float, float] | None = None
    moment_hub_nm: tuple[float, float, float] | None = None


def rotor_shaft_loads(
    surfaces: Mapping[str, Mapping[str, float]],
    *,
    rotor: object,
    reference: ReferenceValues,
    density_kg_m3: float,
    speed_m_s: float,
    aliases: Mapping[str, Sequence[str]] | None = None,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    analysis_frame: str | None = None,
) -> RotorShaftLoads:
    """Return one rotor's THRUST and TORQUE from the loads the run already left.

    Item 6's missing half. `rotor_coefficients` has taken `thrust_n` and
    `torque_nm` since this release opened and nothing computed them, so the
    coefficients were a formula with an empty socket.

    NO RE-RUN IS NEEDED, which is what puts this inside the release's acceptance
    rule: an item that requires re-running the solver is not ready. Everything
    here is read from what a finished campaign already holds: the loads export's
    per-surface `Cx, Cy, Cz, CMx, CMy, CMz`, the reference area, length and
    MOMENT POINT, and the rotor's hub, diameter and shaft.

    THE MOMENT TRANSFER IS THE ONE STEP THAT IS NOT ARITHMETIC. The export's
    moments are about the moment reference point; a rotor's torque is about its
    own shaft through its HUB, and the two differ by the moment of the force
    about the offset between them::

        M_hub = M_mrp + (r_mrp - r_hub) x F

    That is elementary statics rather than a convention, so it is implemented
    rather than asked: choosing the other reading reports a torque no rotor
    produces. The DEFINITION of `ETAW` is not made here: it is stated where it is
    computed, in :func:`rotor_coefficients`.

    ONLY THE ROTOR'S OWN FAMILIES ARE SUMMED. The airframe sits in the same
    table, and a rotor's thrust is its own -- which is the same reason item 6
    suffixes every column with the alias.
    """
    shaft = _unit(getattr(rotor, "axis_vector", (0.0, 0.0, 1.0)))
    # THROUGH THE PACKAGE'S ONE RESOLVER, not an exact-name match. A rotor's
    # `members` are FAMILIES -- the field is named `families_blades` -- and
    # `select_group_members` is the single rule for turning a member token into
    # surface names: an exact name, an alias of the row's setup, or a FAMILY,
    # the label without its trailing number, so `Blade` selects `Blade1` to
    # `Blade6`. `group_coefficients` forty lines above calls it.
    # Matching by exact name summed NOTHING for a rotor declared the way the
    # resolver exists to serve, and wrote 0.00000 thrust with no refusal -- a
    # physically false zero, in the one product item 6 delivers, indistinguishable
    # from the documented static row. Every fixture used exact surface names, so
    # no test in the range could fail on it; a V&V round read it instead.
    families = [str(name) for name in getattr(rotor, "members", [])]
    owned = {name.casefold() for name in select_group_members(families, list(surfaces), aliases)}

    force = [0.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    used: list[str] = []
    for name, row in surfaces.items():
        if str(name).casefold() not in owned:
            continue
        used.append(str(name))
        for index, key in enumerate(("Cx", "Cy", "Cz")):
            force[index] += float(row.get(key, 0.0) or 0.0)
        for index, key in enumerate(("CMx", "CMy", "CMz")):
            moment[index] += float(row.get(key, 0.0) or 0.0)

    # The dynamic pressure the export's own coefficients were taken against.
    # AT V = 0 IT IS ZERO, AND NOTHING IS RECOVERABLE. The export states
    # DIMENSIONLESS coefficients, normalised by this pressure; at rest there is
    # no pressure to divide by and a hovering rotor's real thrust has been
    # divided away. Returning 0.0 would be a lie a reader believes -- a static
    # rotor produces plenty of thrust -- so the loads are NOT A NUMBER and the
    # funnel writes `NA`.
    # This is a finding rather than a design: item 6's coefficients cannot be
    # derived from a dimensionless export for a static point at all, whatever
    # is wired. A hover figure of merit needs the run to state a force.
    # ONE PREMISE, ONE VERDICT. The frame check guarded `wind_force_n` alone for
    # one commit, and a test of mine PINNED that asymmetry -- "the thrust is
    # unaffected: it is a projection on the shaft, which needs no wind axes".
    # That sentence is wrong: `shaft` is a vector in GEOMETRY axes, so the dot
    # product `force . shaft` rests on exactly the premise the wind rotation
    # rests on. A rotated analysis frame breaks both, and guarding one meant
    # `CT`, `CQ`, `CP` and `ETA` published silently wrong numbers while only
    # `ETAW` went visibly absent. The V&V lens of the closing round found the
    # test holding the asymmetry in place.
    if analysis_frame is not None and (
        str(analysis_frame).strip().casefold() not in GEOMETRY_ANALYSIS_FRAMES
    ):
        return RotorShaftLoads(
            thrust_n=math.nan,
            torque_nm=math.nan,
            shaft_angle_deg=_shaft_angle(shaft, alpha_deg, beta_deg),
            wind_force_n=math.nan,
            families_used=tuple(used),
        )
    pressure = 0.5 * float(density_kg_m3) * float(speed_m_s) ** 2
    if pressure <= 0.0:
        return RotorShaftLoads(
            thrust_n=math.nan,
            torque_nm=math.nan,
            shaft_angle_deg=_shaft_angle(shaft, alpha_deg, beta_deg),
            wind_force_n=math.nan,
            families_used=tuple(used),
        )
    area = float(reference.sref_m2)
    length = float(reference.cref_m)
    newtons = [component * pressure * area for component in force]
    about_mrp = [component * pressure * area * length for component in moment]

    offset = (
        float(reference.xmom_m) - float(getattr(rotor, "x_m", 0.0)),
        float(reference.ymom_m) - float(getattr(rotor, "y_m", 0.0)),
        float(reference.zmom_m) - float(getattr(rotor, "z_m", 0.0)),
    )
    about_hub = [
        about_mrp[index]
        + offset[(index + 1) % 3] * newtons[(index + 2) % 3]
        - offset[(index + 2) % 3] * newtons[(index + 1) % 3]
        for index in range(3)
    ]

    return RotorShaftLoads(
        force_n=(newtons[0], newtons[1], newtons[2]),
        moment_hub_nm=(about_hub[0], about_hub[1], about_hub[2]),
        thrust_n=sum(a * b for a, b in zip(newtons, shaft, strict=True)),
        torque_nm=sum(a * b for a, b in zip(about_hub, shaft, strict=True)),
        shaft_angle_deg=_shaft_angle(shaft, alpha_deg, beta_deg),
        # THE WIND-AXIS FORCE `Fx_W`, WITH THE ROUND TRIP COLLAPSED.
        # The definition starts from the force in the ROTOR frame and carries
        # it to the body frame by the TRANSPOSE of the rotor-to-body rotation.
        # `newtons` is that force in the frame THE EXPORT STATES, which is checked
        # against `GEOMETRY_ANALYSIS_FRAMES` above and refuses the whole row when
        # it is not the geometry's. THIS COMMENT SAID "which the export states in
        # the geometry frame", flatly, and the correction of that very sentence
        # is twenty lines below it in the same function -- the false claim and
        # its retraction shipped together, and the false one is what the
        # identity argument rests on. The QA lens of the closing round found it.
        # so resolving it into the rotor frame and straight back out is `R^T R`,
        # the identity, for any orthonormal `R`. Writing the two rotations would
        # give the same number with two more places to make a sign error.
        #
        # What remains is the second rotation: body axes to WIND axes, by alpha
        # and beta, taking the X component. That is exactly the dot product of
        # the body-frame force with the free-stream unit vector, which
        # `post.axes` builds and `_shaft_angle` uses for the angle.
        # `NA` WHERE THE EXPORT IS NOT IN THE GEOMETRY FRAME. The body-to-wind
        # rotation assumes the force is stated in the geometry's own axes; a
        # campaign that sets `analysis_setup(loads_frame=...)` states it in a
        # created coordinate system instead, and rotating THAT by alpha and beta
        # yields a plausible efficiency of nothing. The V&V lens of the release
        # round found the field parsed, carried on `LoadsReport`, and read by
        # nobody -- while a comment asserted the geometry frame as a property of
        # the EXPORT. It is a property of the campaign's setup, and this is the
        # witness. An absent label means the export stated none.
        # The frame was settled above, for the whole row rather than this column.
        wind_force_n=_force_along_the_stream(newtons, shaft, alpha_deg, beta_deg),
        families_used=tuple(used),
    )


def _shaft_angle(shaft: Sequence[float], alpha_deg: float, beta_deg: float) -> float:
    """Return the angle between the shaft and the FREE STREAM, in degrees.

    This read `acos(shaft[0])` for one commit -- the angle to body +X -- under a
    comment calling +X "this package's convention everywhere". IT IS NOT, and
    the same module says so: `polar_row` turns stability-axis forces into body
    axes THROUGH ALPHA, and its docstring records that the wind and stability
    axes coincide here only because every reference polar carried `BETA 0.0`.

    So body +X is the free stream at alpha = 0 and beta = 0 and nowhere else. On
    an alpha sweep -- the ordinary shape of a polar -- the angle was off by
    alpha on every row, and `ETAW = ETA * cos(theta)` with it. That is the
    aircraft's pitch reintroduced as an omission, which is precisely the defect
    item 19 was raised to remove and which `rotor_coefficients` warns about in
    its own docstring.

    The free stream comes from :func:`pyflightstream.post.axes.free_stream_in_export_frame`,
    `(cos a cos b, -cos a sin b, sin a)` in the export's frame, which reduces to
    +X exactly when both angles are zero -- so a case that states neither gets
    the same answer it did.
    """
    projection = sum(
        a * b
        for a, b in zip(free_stream_in_export_frame(alpha_deg, beta_deg), _unit(shaft), strict=True)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, projection))))


def _force_along_the_stream(
    newtons: Sequence[float], shaft: Sequence[float], alpha_deg: float, beta_deg: float
) -> float:
    """Return the force along the free stream, in the SENSE of the shaft.

    THE ROTATION IS `post.axes` AND NOTHING ELSE (0.24.0). Until then this
    module built its own free-stream vector, `(ca cb, +sb, -sa cb)`, whose y and
    z terms carried the opposite sign to its x term: on a recorded export at
    alpha 4, beta 2 it projected the total force to -0.01058 where the export
    states a drag of +0.03578. It had been derived and never scored against an
    export. `tests/tier1_offline/test_goal028_axes_recorded_exports.py` scores it.

    THE SENSE IS THE SHAFT'S, so `ETAW` reduces to `ETA` when the shaft lies
    along the stream WHICHEVER WAY the reference points the rotor's axis. A
    thrust is `force . shaft`; an axis declared pointing aft makes a pulling
    rotor's thrust negative and one declared pointing forward makes it positive,
    and the efficiency, a ratio, is the same number either way. The wind-axis
    force has to follow the same sense or that ratio flips sign with a choice
    that is the user's to make.
    """
    stream = free_stream_in_export_frame(alpha_deg, beta_deg)
    along = sum(a * b for a, b in zip(stream, _unit(shaft), strict=True))
    sense = -1.0 if along < 0.0 else 1.0
    return sense * sum(float(a) * float(b) for a, b in zip(newtons, stream, strict=True))


def _unit(vector: Sequence[float]) -> tuple[float, float, float]:
    """Return ``vector`` normalised, or +Z where it names no direction."""
    length = math.sqrt(sum(float(component) ** 2 for component in vector))
    if length <= 0.0:
        return (0.0, 0.0, 1.0)
    return tuple(float(component) / length for component in vector)  # type: ignore[return-value]


def rotor_coefficients(
    *,
    thrust_n: float,
    torque_nm: float,
    rps: float,
    diameter_m: float,
    density_kg_m3: float,
    speed_m_s: float,
    shaft_angle_deg: float = 0.0,
    wind_force_n: float | None = None,
    in_plane_loads: Sequence[float] | None = None,
) -> dict[str, float | str]:
    """Return the six standard coefficients of one rotor, and its four in-plane ones.

    THE DEFINITIONS, written here because a coefficient whose formula lives
    only in code is a number nobody can check. ``n`` is signed revolutions per
    second and ``D`` the diameter. Its magnitude normalises the coefficients;
    its rotation sign enters power. ``CQ`` retains the signed torque about the
    fixed rotor axis, while reversing rotation alone does not change ``J``::

        J    = V / (|n| D)
        CT   = T / (rho n^2 D^4)
        CQ   = Q / (rho n^2 D^5)
        CP   = 2 pi CQ sign(n)
        ETA  = J CT / CP
        CTW  = Fx_W / (rho n^2 D^4)
        ETAW = J CTW / CP
        CN   = N / (rho n^2 D^4)
        CS   = S / (rho n^2 D^4)
        CMN  = MN / (rho n^2 D^5)
        CMS  = MS / (rho n^2 D^5)

    ``N``, ``S``, ``MN`` and ``MS`` are ``in_plane_loads``, the rotor's force
    along its normal and side axes and its moment about them at the hub
    (:func:`pyflightstream.post.axes.rotor_in_plane_loads`); the four read
    ``NA`` where the caller states none, or states one that is not a number.

    ``Fx_W`` is ``wind_force_n``: the rotor's whole force vector carried from the
    rotor frame to the airframe body frame and then to wind axes by the AIAA
    rotation with alpha and beta, X component (``rotor_shaft_loads`` computes
    it; the definition of record is ``docs/post-processing-definitions.md``,
    section ``ETAW``). It is two rotations on a vector and never the cosine of
    an angle; ``ETAW`` equals ``ETA`` when the shaft lies along the stream, and
    reads ``NA`` when no wind-axis force is stated.

    ``shaft_angle_deg`` is the angle between the rotor's SHAFT and the free
    stream, reported beside the coefficients and entering none of them. It
    rests on item 19: until the installation vector
    existed the shaft was assumed to lie on a geometry axis, so a rotor
    installed at pitch reported the wind-axis efficiency of an aligned rotor.
    A rotor tilted out of the flight direction does not put all of its thrust
    into going forward, and `ETAW` is the half that does.

    ETA AND ETAW ARE `NA` ON A STATIC POINT. At V = 0 both are 0/0: the rotor
    produces thrust and absorbs torque and no useful propulsive power, so any
    number there is an artifact of the algebra rather than a measurement. `CT`
    and `CQ` are still real and still written. The static measure is a figure
    of merit, which the package does not choose: a user who runs a static
    point defines one.

    `ETAW` IS DEFINED AS A ROTATION CHAIN, NOT A COSINE. It was formerly
    implemented as the thrust component along the free stream -- `ETA` times the
    cosine of the shaft angle -- and that form was wrong. The definition is:

        [Fx_rotor_axis Fy_rotor_axis Fz_rotor_axis]
            * R^T(rotor axes -> airframe body axes)
            * R(alpha)      -> Fx_W

    with BOTH alpha and beta applied by the AIAA axis convention, and
    `ETAW` remaining a dimensionless efficiency.

    WHY THE COSINE WAS WRONG AND NOT MERELY IMPRECISE. A cosine of the shaft
    angle projects the SHAFT and keeps only what lies along it, so every
    component of the rotor's force that is off the shaft is discarded -- which
    on an installed rotor is exactly the part the rotation chain preserves. It is a
    scalar where the physics is a vector, and the two agree only when the shaft
    and the stream are already aligned, which is the case that needs no
    correction.

    Raises
    ------
    ZeroDivisionError
        If the rotor is not turning. Every coefficient divides by the square of
        the speed, and a rotor at zero rev/min has no coefficients rather than
        infinite ones.
    """
    if rps == 0:
        raise ZeroDivisionError(
            "the rotor is not turning, so it has no thrust or torque coefficient: "
            "every one of them divides by the square of its speed"
        )
    # `rps` IS SIGNED AND THE SIGN IS THE SENSE OF ROTATION. Both halves of that
    # sentence are load-bearing and one of them was got wrong on 2026-09-18.
    #
    # THE RATE NORMALISES. `J = V/(n D)` would go NEGATIVE for a rotor flying
    # forwards and `CT` is quadratic anyway, so the magnitude is what divides.
    #
    # THE SIGN REACHES THE POWER, AND ONLY THE POWER. `CP` is a normalised
    # POWER and power is `P = Q * omega`: reverse a rotor AND its torque and the
    # shaft power is UNCHANGED, because both factors flipped. Writing
    # `CP = 2 pi CQ` against a magnitude rate therefore flips `CP`, `ETA` and
    # `ETAW` for a counter-rotating rotor whose torque is the signed projection
    # on a FIXED axis -- which is what `rotor_shaft_loads` returns.
    #
    #     CP = P / (rho |n|^3 D^5) = 2 pi Q n / (rho |n|^3 D^5)
    #        = 2 pi CQ * sign(n)
    #
    # MEASURED, by the independent lens over the first fix: at T=10, V=5,
    # rho=D=1, reversing +600 rpm with +2 N m to -600 with -2 N m held
    # `Q*omega` at +125.664 and flipped the returned `CP` from +0.125664 to
    # -0.125664, and `ETA` with it.
    #
    # `CQ` KEEPS ITS OWN SIGN and is not touched: it is the torque about the
    # rotor's fixed axis, so its sign says which way the shaft is loaded, and
    # taking its magnitude would erase the difference between driving and
    # braking. That distinction is real and the estate does not get to lose it
    # for tidiness.
    rate = abs(rps)
    sense = 1.0 if rps > 0 else -1.0
    advance_ratio = speed_m_s / (rate * diameter_m)
    thrust_coefficient = thrust_n / (density_kg_m3 * rate**2 * diameter_m**4)
    torque_coefficient = torque_nm / (density_kg_m3 * rate**2 * diameter_m**5)
    power_coefficient = 2.0 * math.pi * torque_coefficient * sense
    values: dict[str, float | str] = {
        "J": advance_ratio,
        "CT": thrust_coefficient,
        "CQ": torque_coefficient,
        "CP": power_coefficient,
    }
    # 0.31.0 (G8): THE IN-PLANE SET, by the same `rho n^2 D^4` and `D^5` as
    # `CT` and `CQ`, with the magnitude of the rate: a side force is not a
    # power, so the sense of rotation does not enter it.
    stated_in_plane = (
        tuple(float(value) for value in in_plane_loads) if in_plane_loads is not None else ()
    )
    if len(stated_in_plane) == 4 and all(math.isfinite(value) for value in stated_in_plane):
        force_scale = density_kg_m3 * rate**2 * diameter_m**4
        moment_scale = force_scale * diameter_m
        normal, side, about_normal, about_side = stated_in_plane
        values["CN"] = normal / force_scale
        values["CS"] = side / force_scale
        values["CMN"] = about_normal / moment_scale
        values["CMS"] = about_side / moment_scale
    else:
        for name in ROTOR_IN_PLANE_COLUMNS:
            values[name] = NOT_APPLICABLE
    if speed_m_s == 0 or power_coefficient == 0:
        values["ETA"] = NOT_APPLICABLE
        values["ETAW"] = NOT_APPLICABLE
        return values
    efficiency = advance_ratio * thrust_coefficient / power_coefficient
    values["ETA"] = efficiency
    # ETAW USES THE WIND-AXIS FORCE, NOT A COSINE.
    # It read `ETA * cos(shaft_angle)`, which projects the SHAFT direction and
    # so keeps only the part of the rotor's force that lies along the shaft --
    # discarding exactly the components an installed rotor produces off it. The
    # current definition carries the whole force vector through two rotations and takes the wind X
    # component, which `rotor_shaft_loads` computes as `wind_force_n`.
    # `ETAW` STAYS DIMENSIONLESS: the wind-axis
    # force is nondimensionalised exactly as the thrust is, and enters the same
    # efficiency where `CT` enters. So `ETAW` reduces to `ETA` when the shaft is
    # aligned with the stream, which is the property that makes it readable.
    # A CALLER THAT STATES NO WIND FORCE GETS `NA`, never the cosine. Falling
    # back to the old form would publish the superseded number under the
    # corrected name, and a reader could not tell which they were holding.
    if wind_force_n is None or not math.isfinite(wind_force_n):
        values["ETAW"] = NOT_APPLICABLE
        return values
    wind_coefficient = wind_force_n / (density_kg_m3 * rps**2 * diameter_m**4)
    values["ETAW"] = advance_ratio * wind_coefficient / power_coefficient
    return values


def write_rotor_table(
    path: str | Path,
    *,
    rotor: object,
    rows: Sequence[Mapping[str, object]],
    reference: ReferenceValues,
    left_out: list[tuple[str, str]] | None = None,
    written_runs: list[str] | None = None,
    pol: str | int | None = None,
) -> Path | None:
    """Write ONE rotor's coefficient table (items 6 and 18, and G16 of 0.27.0).

    ``left_out`` collects ``(run_id, reason)`` for every row this refuses, and
    ``written_runs`` collects the run id of every row it DID write. Both are
    out-parameters because the caller owns the manifest: a row dropped here
    used to leave the table shorter with the provenance still naming its run,
    so the file claimed a point it does not contain.

    ``pol`` is the polar the rows come from, the matrix row's POL, written in
    the first column of every row; `NA` where the caller states none.

    `rotor_coefficients` and `rotor_coefficient_columns` existed with no
    caller: pieces of a table and no table. This is the table.

    THE FIRST LINE IS THE HEADER (G16). The table opens with `POL` and then
    `ROTOR`, the rotor's alias, on every row, because a script that has already
    LOADED the file no longer has its name -- it holds an array of numbers, and
    the alias has to be inside the bytes. From 0.23.0 to 0.26.x the alias stood
    alone on the first line instead, before the header, and no CSV reader took
    the file as written.

    EVERY COLUMN CARRIES THE ALIAS TOO, which is physical rather than cosmetic:
    two rotors summed into one `CT` is not a worse `CT`, it is not a `CT` at
    all, because the diameters and speeds that normalise them are different
    numbers. The suffix is what makes the mistake impossible by accident.

    Returns None without writing when no row states a speed, since every
    coefficient here divides by one: there is no table to write rather than a
    table of `NA`.
    """
    alias = str(getattr(rotor, "alias", "") or "")
    # 0.24.0: THE SPEED AND THE DIAMETER THE COEFFICIENTS DIVIDED BY, beside them.
    # Every coefficient here is over `rho n^2 D^4` or `D^5`; `RHO` is in the shared
    # block, and the rotor's own `n` and `D` were stated nowhere in the file.
    # 0.27.0 (G16): the polar and the rotor lead, and every column after them
    # keeps its name and its order.
    # 0.30.0 (M1): the tip and helical Mach numbers LAST, so every column
    # before them keeps its position.
    # 0.31.0 (G8): the four in-plane coefficients after them, last again.
    columns = (
        POLAR_ID_COLUMN,
        ROTOR_ID_COLUMN,
        *CONTEXT_COLUMNS,
        f"RPM_{alias}",
        f"DIAMETER_{alias}",
        *rotor_coefficient_columns(alias),
        f"MTIP_{alias}",
        f"MHEL_{alias}",
        *(f"{name}_{alias}" for name in ROTOR_IN_PLANE_COLUMNS),
    )
    diameter = float(getattr(rotor, "diameter_m", 0.0) or 0.0)
    # 0.31.0 (G8): the rotor's (T, S, N) axes are the same for every row, so
    # an axis along the reference frame's up, which has no normal and no side
    # axis, is said once for the table and its four in-plane columns read NA.
    shaft = _unit(getattr(rotor, "axis_vector", (0.0, 0.0, 1.0)))
    in_plane_defined = rotor_in_plane_axes(shaft) is not None
    in_plane_said = False

    written: list[tuple[object, ...]] = []
    # THE TWO OUT-PARAMETERS, normalised once so every `continue` below can
    # report without checking for None. A row refused here is a point of the
    # matrix that the table does not contain, and the manifest has to be able
    # to say so: both of these paths were bare `continue`s, counted by the
    # independent lens of 2026-09-18.
    refused = [] if left_out is None else left_out
    emitted = [] if written_runs is None else written_runs
    for row in rows:
        stated = row.get("run_id")
        run_id = str(stated) if isinstance(stated, str) else ""
        # NARROWED HERE rather than annotated away: the row is a plain
        # mapping the caller assembles, so its values arrive as `object`
        # and a `float(...)` on one is a claim the type checker is right
        # to refuse. A row stating a speed that is not a number states no
        # speed, and there is no table to write for it.
        stated = row.get("rpm")
        rpm = float(stated) if isinstance(stated, int | float) else 0.0
        # A NEGATIVE RPM IS A DIRECTION, NOT A STOPPED ROTOR, and this read
        # `rpm <= 0.0` until the independent review of 2026-09-18. The plan
        # records the speed SIGNED -- `rpm=_rpm_sign(case) * stated` in
        # `cases.workflows` -- precisely so the sense of rotation survives, and
        # the same module divides by `abs(self.rpm)` where it needs a RATE. So
        # every counter-rotating rotor lost its ENTIRE table here, with no
        # product and no skip line saying why it was absent. On a
        # contra-rotating pair that is half the aircraft, silently.
        #
        # `rate` IS THE MAGNITUDE because a coefficient divides by revolutions
        # per second, which has no sign: `CT = T / (rho n^2 D^4)` is quadratic
        # in `n` and `J = V / (n D)` would go negative for a rotor flying
        # forwards. The SIGN stays on the torque, which is where it is physical
        # and where the export already put it.
        rate = abs(rpm)
        if rate <= 0.0:
            refused.append(
                (
                    run_id,
                    f"{alias}: the row states no rotor speed, so every "
                    "coefficient here would divide by zero",
                )
            )
            continue
        if diameter <= 0.0:
            refused.append((run_id, f"{alias}: the reference states no diameter for this rotor"))
            continue
        # THIS ROW'S OWN AIR AND ITS OWN VELOCITY. These were one pair of
        # arguments for the WHOLE table until 2026-09-18, read off the first
        # point of the sweep, so every row but the first was normalised by
        # another point's state -- see `_rotor_tables`.
        stated = row.get("density")
        density_kg_m3 = float(stated) if isinstance(stated, int | float) else 0.0
        stated = row.get("speed")
        speed_m_s = float(stated) if isinstance(stated, int | float) else 0.0
        # THE ADVANCE RATIO IS THE FREE STREAM'S (0.24.0). `speed` is the export's
        # REFERENCE velocity, which is right for taking a coefficient back to
        # Newtons and wrong for `J = V / (n D)`, a ratio of the flight speed. The
        # two are equal in every campaign recorded so far; a row that states no
        # free stream keeps the speed it has.
        stated = row.get("free_stream")
        flight_m_s = float(stated) if isinstance(stated, int | float) else speed_m_s
        if density_kg_m3 <= 0.0:
            refused.append((run_id, f"{alias}: the row states no air density"))
            continue
        # THE ROW'S OWN ATTITUDE REACHES THE ANGLE. Left to default, every
        # point reports the level-flight shaft angle and `ETAW` carries the
        # aircraft's pitch as an omission -- the defect one level up from the
        # one item 19 removed.
        stated = row.get("condition")
        attitude = stated if isinstance(stated, Mapping) else {}
        loads = rotor_shaft_loads(
            surfaces if isinstance(surfaces := row.get("surfaces"), Mapping) else {},
            rotor=rotor,
            reference=reference,
            density_kg_m3=density_kg_m3,
            speed_m_s=speed_m_s,
            aliases=(
                stated_aliases
                if isinstance(stated_aliases := row.get("aliases"), Mapping)
                else None
            ),
            alpha_deg=float(attitude.get("ALPHA") or 0.0),
            beta_deg=float(attitude.get("BETA") or 0.0),
            # THE CALL SITE IS WHAT DELIVERS THE CHECK. The witness field and
            # the refusal both existed for a few minutes without this line, and
            # `ETAW` would have gone on being computed from a force in whatever
            # frame the campaign chose.
            analysis_frame=(
                stated_frame if isinstance(stated_frame := row.get("frame"), str) else None
            ),
        )
        if not loads.families_used:
            # A FALSE ZERO IS REFUSED, NOT PUBLISHED (WT-02). `families_used` was
            # filled and read by nothing: a rotor whose families are not in the
            # export summed to zero thrust and the table printed CT 0.00000 down
            # the whole sweep with nothing skipped. Zero is a value a rotor can
            # have, which is exactly why it cannot stand for "no surface".
            carried = ", ".join(sorted(map(str, surfaces))) if isinstance(surfaces, Mapping) else ""
            refused.append(
                (
                    run_id,
                    f"{alias}: its families {', '.join(map(str, getattr(rotor, 'members', [])))} "
                    f"select no surface of this point's loads export ({carried}), so there is "
                    "no force to take a coefficient of",
                )
            )
            continue
        coefficients = rotor_coefficients(
            thrust_n=loads.thrust_n,
            torque_nm=loads.torque_nm,
            # THE SIGNED RATE, not the magnitude. `rotor_coefficients` needs the
            # sense of rotation to keep `CP` a power, and takes the magnitude
            # itself for everything that normalises. Passing `rate` here flipped
            # CP, ETA and ETAW on every counter-rotating rotor.
            rps=rpm / 60.0,
            diameter_m=diameter,
            density_kg_m3=density_kg_m3,
            speed_m_s=flight_m_s,
            shaft_angle_deg=loads.shaft_angle_deg,
            # THE CALL SITE PASSES THE WIND-AXIS FORCE. The formula and the
            # wind-axis force both existed for a few minutes without this line,
            # and `ETAW` would have gone on being the cosine it was.
            wind_force_n=loads.wind_force_n,
            # 0.31.0 (G8): the same force and hub moment the thrust and the
            # torque are turned from, resolved on the rotor's normal and side
            # axes; None (NA) where they are not a number or the axes are
            # undefined.
            in_plane_loads=(
                rotor_in_plane_loads(loads.force_n, loads.moment_hub_nm, shaft)
                if loads.force_n is not None and loads.moment_hub_nm is not None
                else None
            ),
        )
        if not in_plane_defined and not in_plane_said:
            in_plane_said = True
            warn(
                f"point={run_id or 'NA'} product={Path(path).name}: rotor {alias}'s axis "
                f"{tuple(round(component, 6) for component in shaft)} lies along the "
                "reference frame's up direction (+z), so it has no normal and no side "
                f"axis, and CN_{alias}, CS_{alias}, CMN_{alias} and CMS_{alias} read NA "
                "on every row of this table.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        stated_condition = row.get("condition")
        condition = dict(stated_condition) if isinstance(stated_condition, Mapping) else {}
        # 0.30.0 (M1): `NA` where the point's air did not resolve, never a guess.
        machs: tuple[float | None, float | None] = (None, None)
        air = row.get("air")
        if (
            isinstance(air, tuple)
            and len(air) == 2
            and all(isinstance(value, int | float) for value in air)
        ):
            try:
                machs = rotor_mach_numbers(
                    rpm=rpm,
                    diameter_m=diameter,
                    velocity_m_per_s=float(air[0]),
                    sonic_velocity_m_per_s=float(air[1]),
                )
            except ValueError:
                # A speed of sound or a velocity that is not a positive
                # finite number costs these two cells and never the row.
                machs = (None, None)
        written.append(
            (
                pol,
                alias,
                *context_row(condition, reference.as_lengths()),
                rpm,
                diameter,
                *(coefficients[name] for name in ROTOR_COEFFICIENT_COLUMNS),
                *machs,
                *(coefficients[name] for name in ROTOR_IN_PLANE_COLUMNS),
            )
        )
        emitted.append(run_id)

    if not written:
        return None
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # THROUGH `write_csv_table`, which is THE funnel: every cell of every
    # product is rendered by `_cell` there, so a value this table cannot fill
    # reads `NA` like every other product rather than by a rule of its own.
    # Writing the rows here with `csv.writer` would be a fifth family spelling
    # its own absences, which is the drift item 5 repaired.
    # THE SCRATCH FILE IS REMOVED WHATEVER HAPPENS, and it was not for one
    # commit. `write_csv_table` refuses a malformed row, and the refusal left
    # `<product>.rows` behind IN THE POLARS FOLDER, and nothing on any later run
    # cleans it up. A QA round reproduced it by shrinking the column tuple.
    # It goes in a TEMPORARY DIRECTORY rather than beside the product, so a
    # process killed or a row refused before the table is whole leaves nothing
    # in the user's workspace at all. This machine killed three runs for memory
    # in one day; that is not a hypothetical.
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir) / "rows.csv"
        write_csv_table(scratch, columns, written)
        table = scratch.read_bytes()
    # ONE WRITE, AND NOTHING BEFORE THE HEADER (G16). Until 0.27.0 the alias was
    # written alone on the first line and the table appended after it, through a
    # text-mode write that ended its lines the platform's way; the alias is the
    # `ROTOR` column now, so the file is the funnel's bytes, line ends included,
    # as every other table's is.
    target.write_bytes(table)
    return target
