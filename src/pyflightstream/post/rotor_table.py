"""The rotor table: one coefficient table per rotor the reference declares.

One of the product families of :mod:`pyflightstream.post`, written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports every name here.

``polars/P<sim>-<sweep>_<ROTOR>_rotor.csv``: one row per point, the rotor's
loads in its own shaft frame (:class:`RotorShaftLoads`,
:func:`rotor_shaft_loads`) and its thrust, torque and power coefficients
with the in-plane ones (:func:`rotor_coefficients`,
:data:`ROTOR_COEFFICIENT_COLUMNS`, :data:`ROTOR_IN_PLANE_COLUMNS`,
:func:`rotor_coefficient_columns`), written by the retired ``write_rotor_table``.
The geometry comes from the resolved reference definition retained with the
run record, including the shaft, hub and diameter. An
unsteady row reads the rotor's plot group, time-averaged over the row's
window (the plan of :mod:`pyflightstream.post._rotor_plan` names the group a
rotor's history is read from); a steady row reads its loads export.

The rotor products of the backlog that are tables of a rotor per point (a
trimmed rotor, a further coefficient set) join this module beside the
writer they extend.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from pyflightstream._deprecations import removed_names_hook
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.cases import (
    select_group_members,
)
from pyflightstream.cases.workflows import (
    advancing_tip_mach_number,
    free_stream_direction_at,
    rotor_mach_numbers,
)
from pyflightstream.post._tables import (
    NOT_APPLICABLE,
    ProductError,
    ReferenceValues,
)
from pyflightstream.post.axes import (
    RotorFrame,
    free_stream_in_export_frame,
)
from pyflightstream.post.polar import GEOMETRY_ANALYSIS_FRAMES

if TYPE_CHECKING:
    pass

__all__ = [
    "ROTOR_COEFFICIENT_COLUMNS",
    "ROTOR_IN_PLANE_COLUMNS",
    "RotorShaftLoads",
    "rotor_coefficient_columns",
    "ROTOR_DECLARED_AFT_WARNING",
    "rotor_coefficients",
    "rotor_frame_coefficients",
    "rotor_shaft_loads",
    "warn_rotor_declared_aft",
]


#: The six coefficients a rotor table carries, in this order, for each rotor:
#: J, CT, CQ, CP, ETA and ETAW (the efficiency in wind axes).
ROTOR_COEFFICIENT_COLUMNS: tuple[str, ...] = ("J", "CT", "CQ", "CP", "ETA", "ETAW")


#: The rotor's in-plane coefficients (G8), the LAST four columns of its
#: table, after `MTIP_<alias>` and `MHEL_<alias>`: the force along the normal
#: and side axes and the moment about them, in the rotor's `(T, S, N)` axes
#: (:func:`pyflightstream.post.axes.rotor_in_plane_axes`).
ROTOR_IN_PLANE_COLUMNS: tuple[str, ...] = ("CN", "CS", "CMN", "CMS")


# The rotor alias is the ROTOR column after POL on every row. The first
# line is the CSV header, so a loaded table retains rotor identity without
# a non-tabular preamble.


def rotor_coefficient_columns(alias: str) -> tuple[str, ...]:
    """Return the rotor coefficient columns of ONE rotor, suffixed with its alias.

    The constraint is physical rather than cosmetic: these coefficients have a
    physical meaning for one rotor only, never for several together. Two rotors
    summed into one CT is not a worse CT, it is not a CT at all -- the diameters and
    the speeds that normalise it are different numbers. The alias in every
    column name is what makes summing them impossible by accident.

    Parameters
    ----------
    alias : str
        The rotor's alias, stripped of surrounding blanks.

    Returns
    -------
    tuple of str
        ``J``, ``CT``, ``CQ``, ``CP``, ``ETA`` and ``ETAW``, each followed by
        ``_`` and the alias.

    Raises
    ------
    ProductError
        If the alias is empty (a ``ValueError``).
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

    WHY BOTH, AND WHY THE ANGLE IS NOT ENOUGH. A cosine projects the SHAFT direction
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
    #: components; None where those two are not a number (for the
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

    Parameters
    ----------
    surfaces : mapping of str to mapping of str to float
        The loads table by surface name: the coefficients ``Cx, Cy, Cz, CMx,
        CMy, CMz`` of each surface.
    rotor : object
        The rotor, read for its ``axis_vector``, ``members`` (families), and
        hub position ``x_m``, ``y_m`` and ``z_m``.
    reference : ReferenceValues
        Reference area, length and moment point the export's coefficients were
        taken against.
    density_kg_m3 : float
        Air density in kg/m^3.
    speed_m_s : float
        The export's reference velocity in m/s, the speed its coefficients are divided
        by; zero or below gives NaN loads. A static free stream with a positive
        reference velocity gives dimensional loads.
    aliases : mapping of str to sequence of str, optional
        The boundary aliases a rotor member may name.
    alpha_deg : float, optional
        Angle of attack in degrees, for the angle to the free stream.
    beta_deg : float, optional
        Sideslip angle in degrees.
    analysis_frame : str, optional
        The frame the export states its loads in; one that is not the
        geometry's axes gives NaN loads.

    Returns
    -------
    RotorShaftLoads
        Thrust and torque about the shaft in N and N m, the angle between the
        shaft and the stream, the force along the stream, and the surfaces
        summed. The loads are NaN at rest and in a frame other than the
        geometry's.
    """
    declared_axis = getattr(rotor, "axis_vector", (0.0, 0.0, 1.0))
    shaft = _unit(declared_axis)
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
    owned = {
        name.casefold()
        for name in select_group_members(families, list(surfaces), aliases, strict=False)
    }

    force = [0.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    used: list[str] = []
    for name, row in surfaces.items():
        if str(name).casefold() not in owned:
            continue
        used.append(str(name))
        # A coefficient the export does not state is not a zero: it makes the sum
        # NaN, so the thrust and every coefficient of the row read NA.
        for index, key in enumerate(("Cx", "Cy", "Cz")):
            stated = row.get(key)
            force[index] += math.nan if stated is None else float(stated)
        for index, key in enumerate(("CMx", "CMy", "CMz")):
            stated = row.get(key)
            moment[index] += math.nan if stated is None else float(stated)

    # The dynamic pressure the export's own coefficients were taken against.
    # THE SPEED IS THE EXPORT'S REFERENCE VELOCITY (VREF), not the free stream. The
    # export's coefficients are divided by 0.5 rho VREF^2, so multiplying them back
    # recovers newtons whenever VREF is positive, a static free stream (hover) included
    # (reports/PFS-2127.001_hover-normalization_2026-10-16.md: batch 9, arms H20, H40 and
    # H80). Only a ZERO reference velocity has nothing to recover: it is divided away, and
    # a 0.0 would be a lie a reader believes, so the loads are NOT A NUMBER and the
    # funnel writes `NA`. At a zero free stream J is zero and the efficiency stays NA.
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
    if float(speed_m_s) < 0.0 or not pressure > 0.0 or not _names_a_direction(declared_axis):
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
        # Compute wind-axis Fx_W from geometry-frame force. The rotor-to-body
        # round trip cancels as R^T R for orthonormal R, so only the body-to-wind
        # rotation remains: dot the force with the free-stream unit vector.
        # The export frame is checked for the whole row above; a nongeometry
        # frame cannot be rotated by alpha and beta as though it were geometry
        # axes. An absent label does not establish a frame.
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

    The rotation uses ``post.axes`` so the rotor table and polar share the same free-stream
    direction and signs.

    THE SENSE IS THE SHAFT'S, so `ETAW` reduces to `ETA` when the shaft lies
    along the stream WHICHEVER WAY the reference points the rotor's axis. A
    thrust is `force . shaft`; an axis declared pointing aft makes a pulling
    rotor's thrust negative and one declared pointing forward makes it positive,
    and the efficiency, a ratio, is the same number either way. The wind-axis
    force has to follow the same sense or that ratio flips sign with a choice
    that is the user's to make.

    THE SENSE IS FIXED ONCE PER ROTOR, against the body's +x, the stream of a
    level row (PFS-2105.017): taken against each row's own stream it flipped
    where the shaft is square to the stream, so a lift rotor's ETAW changed
    sign between alpha -2 and +2 while its thrust and CP did not. A shaft
    square to +x keeps the sense +1.
    """
    stream = free_stream_in_export_frame(alpha_deg, beta_deg)
    sense = -1.0 if _unit(shaft)[0] < 0.0 else 1.0
    return sense * sum(float(a) * float(b) for a, b in zip(newtons, stream, strict=True))


def _names_a_direction(vector: Sequence[float]) -> bool:
    """Return whether ``vector`` is finite and not the zero vector."""
    parts = [float(component) for component in vector]
    return all(math.isfinite(part) for part in parts) and any(part != 0.0 for part in parts)


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

    `ETAW` IS DEFINED AS A ROTATION CHAIN. Multiplying ETA by the cosine of
    the shaft angle would omit off-shaft forces. The definition is:

        [Fx_rotor_axis Fy_rotor_axis Fz_rotor_axis]
            * R^T(rotor axes -> airframe body axes)
            * R(alpha)      -> Fx_W

    with BOTH alpha and beta applied by the AIAA axis convention, and
    `ETAW` remaining a dimensionless efficiency.

    WHY A COSINE IS INSUFFICIENT. A cosine of the shaft
    angle projects the SHAFT and keeps only what lies along it, so every
    component of the rotor's force that is off the shaft is discarded -- which
    on an installed rotor is exactly the part the rotation chain preserves. It is a
    scalar where the physics is a vector, and the two agree only when the shaft
    and the stream are already aligned, which is the case that needs no
    correction.

    Parameters
    ----------
    thrust_n : float
        Thrust along the shaft in N.
    torque_nm : float
        Torque about the shaft in N m, signed about the fixed rotor axis.
    rps : float
        Signed revolutions per second; the sign is the sense of rotation.
    diameter_m : float
        Rotor diameter in m.
    density_kg_m3 : float
        Air density in kg/m^3.
    speed_m_s : float
        Free-stream speed in m/s.
    shaft_angle_deg : float, optional
        Angle between the shaft and the free stream in degrees; reported
        beside the coefficients and used in none of them.
    wind_force_n : float, optional
        The rotor's force along the free stream in N; ``ETAW`` reads ``NA``
        where it is None or not finite.
    in_plane_loads : sequence of float, optional
        Normal force, side force, and the moments about the normal and side
        axes at the hub, in N and N m; the four in-plane columns read ``NA``
        where it is None or does not hold four finite numbers.

    Returns
    -------
    dict of str to float or str
        ``J``, ``CT``, ``CQ``, ``CP``, ``ETA``, ``ETAW``, ``CN``, ``CS``,
        ``CMN`` and ``CMS``; a coefficient that cannot be formed reads ``NA``.

    Raises
    ------
    ProductError
        If the rotor is not turning or its diameter is not positive. Every
        coefficient divides by the square of the speed; a stationary rotor has no
        coefficients rather than infinite ones.
    """
    if rps == 0:
        raise ProductError(
            "rps is zero: the rotor is not turning, so it has no thrust or torque coefficient: "
            "every one of them divides by the square of its speed"
        )
    if diameter_m <= 0:
        raise ProductError("diameter_m must be positive to define rotor coefficients")
    if math.isinf(rps) or math.isinf(diameter_m):
        # An infinite rate or diameter divides every coefficient to a finite zero
        # that would pass for a measurement.
        raise ProductError("rps and diameter_m must be finite to define rotor coefficients")

    if not density_kg_m3 > 0:
        raise ProductError(
            f"density_kg_m3 must be positive to define rotor coefficients, got {density_kg_m3!r}"
        )
    # rps carries the rotation sense. Its magnitude normalises J, CT and CQ.
    # Power is Q times omega: reversing both torque and rotation preserves
    # shaft power, so CP = 2 pi CQ * sign(n), with magnitude-rate normalisation
    # P / (rho |n|^3 D^5). CQ retains the signed torque about the fixed shaft
    # axis, distinguishing driving from braking.
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
    # G8: THE IN-PLANE SET, by the same `rho n^2 D^4` and `D^5` as
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


#: The text a rotor declared with its axis aft is warned with, once per rotor
#: (the migration map of the post tree); ``{alias}`` is filled in.
ROTOR_DECLARED_AFT_WARNING = (
    "Rotor {alias} declares its axis aft; 0.58.0 counts thrust positive "
    "forward, so CT, CQ, ETA, T and the in-plane signs of this rotor are opposite to "
    "0.57.0. "
    "See docs/upgrading.md#0580-post-tree."
)


def warn_rotor_declared_aft(alias: str, frame: RotorFrame) -> bool:
    """Warn that a rotor declared aft reads with the thrust sign opposite to the rotor table.

    Parameters
    ----------
    alias : str
        The rotor's alias.
    frame : RotorFrame
        Its frame, from :func:`pyflightstream.post.axes.rotor_frame`.

    Returns
    -------
    bool
        Whether the warning was given (the rotor's declared axis points aft).

    Examples
    --------
    >>> from pyflightstream.post.axes import rotor_frame
    >>> warn_rotor_declared_aft("TRACTOR", rotor_frame((-1.0, 0.0, 0.0)))
    False
    """
    if not frame.declared_aft:
        return False
    warn(ROTOR_DECLARED_AFT_WARNING.format(alias=alias), PyflightstreamWarning)
    return True


def _usable(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    number = float(value)  # type: ignore[arg-type]
    return number if math.isfinite(number) else None


def _over(numerator: float, denominator: float | None) -> float | str:
    """``numerator / denominator``, or ``NA`` where it is not a finite number."""
    if denominator is None or denominator == 0.0 or not math.isfinite(numerator):
        return NOT_APPLICABLE
    value = numerator / denominator
    return value + 0.0 if math.isfinite(value) else NOT_APPLICABLE


def _efficiency(
    advance: float | None, thrust_coefficient: float | str, cp: float | str
) -> float | str:
    if advance is None or advance == 0.0 or not isinstance(thrust_coefficient, float):
        return NOT_APPLICABLE
    if not isinstance(cp, float) or cp == 0.0:
        return NOT_APPLICABLE
    return advance * thrust_coefficient / cp + 0.0


def _rotor_frame_loads(
    force_n: Sequence[float], moment_hub_nm: Sequence[float], turn: NDArray[np.float64]
) -> tuple[float, float, float, float, float, float]:
    """Return ``(T, Y, Z, Q, M, N)`` of a force and hub moment turned into one frame."""
    force = turn @ np.asarray(force_n, dtype=float)
    moment = turn @ np.asarray(moment_hub_nm, dtype=float)
    return (
        float(force[0]),
        float(force[1]),
        -float(force[2]),
        float(moment[0]),
        float(moment[1]),
        float(moment[2]),
    )


def rotor_frame_coefficients(
    *,
    force_n: Sequence[float],
    moment_hub_nm: Sequence[float],
    frame: RotorFrame,
    rotations: Mapping[str, NDArray[np.float64]],
    rpm: float | None,
    diameter_m: float,
    density_kg_m3: float,
    vinf_m_s: float | None,
    sref_m2: float,
    cref_m: float,
    bref_m: float,
) -> dict[str, float | str]:
    """Return the RCOEF values of one family or group inside rotor ``frame``.

    THE DEFINITIONS (``docs/definitions/rotor-coefficients.md``). ``F_R`` and
    ``M_R`` are the force and the moment about the hub in the frame R<id>;
    ``n`` is the rate in rev/s signed about ``x_R`` (``sense RPM / 60``),
    ``D`` the diameter, ``A = pi D^2 / 4``, ``q = 0.5 RHO VINF^2`` and
    ``J = VINF / (|n| D)``::

        T = F_R,x    Y = F_R,y    Z = -F_R,z    Q = M_R,x    M = M_R,y    N = M_R,z
        P  = 2 pi n Q / 1000                       (kW)
        CT = T / (RHO n^2 D^4)    CQ = Q / (RHO n^2 D^5)    CP = 2 pi CQ sign(n)
        CFZ, CFY = Z, Y / (RHO n^2 D^4)            CMZ, CMY = N, M / (RHO n^2 D^5)
        ETA = J CT / CP
        TC, YC, ZC = T, Y, Z / (q A)               QC, NC, MC = Q, N, M / (q A D)
        TCA, YCA, ZCA = T, Y, Z / (q SREF)         QCA, NCA = Q, N / (q SREF BREF)
        MCA = M / (q SREF CREF)
        CT<f> = F_f,x / (RHO n^2 D^4)   CQ<f> = M_f,x / (RHO n^2 D^5)   ETA<f> = J CT<f> / CP

    THE NA RULES. A static point (``VINF = 0``) states no ``ETA``, no
    ``ETA<f>`` and none of ``TC`` to ``MCA``. A rotor not turning or of unknown
    speed states no coefficient over ``n^2`` and no ``ETA``; ``P`` is 0 at
    ``RPM = 0`` and ``NA`` when the speed is unknown. A load that is not a
    number gives ``NA`` wherever it enters.

    Parameters
    ----------
    force_n : sequence of float
        The force in N, in the export frame.
    moment_hub_nm : sequence of float
        The moment about the rotor's hub in N m, in the export frame.
    frame : RotorFrame
        The frame of the rotor the family or group sits in.
    rotations : mapping of str to numpy.ndarray
        The export-to-frame matrices of every frame, as
        :func:`pyflightstream.post.axes.frame_rotations` returns them; the
        per-frame set runs over them in their order.
    rpm : float or None
        The rotor's speed signed about its declared axis; None when unknown.
    diameter_m : float
        The rotor's diameter.
    density_kg_m3 : float
        The point's density.
    vinf_m_s : float or None
        The free-stream speed; None when unknown.
    sref_m2, cref_m, bref_m : float
        The airframe reference area, chord and span.

    Returns
    -------
    dict of str to float or str
        The rotor-frame columns of
        :data:`pyflightstream.post._family_columns.ROTOR_FRAME_COLUMNS` in their
        order, then ``CT<f>, CQ<f>, ETA<f>`` per frame; ``NA`` where a value
        does not exist.

    Examples
    --------
    >>> from pyflightstream.post.axes import frame_rotations, rotor_frame
    >>> frame = rotor_frame((-1.0, 0.0, 0.0))
    >>> row = rotor_frame_coefficients(
    ...     force_n=(-100.0, 0.0, 0.0), moment_hub_nm=(-5.0, 0.0, 0.0), frame=frame,
    ...     rotations=frame_rotations(0.0, 0.0, [frame]), rpm=600.0, diameter_m=1.0,
    ...     density_kg_m3=1.0, vinf_m_s=10.0, sref_m2=1.0, cref_m=1.0, bref_m=1.0)
    >>> row["T"], row["CT"], row["CTR0"] == row["CT"]
    (100.0, 1.0, True)
    """
    speed = _usable(rpm)
    rate = None if speed is None else frame.sense * speed / 60.0
    turning = rate is not None and rate != 0.0
    diameter = float(diameter_m)
    rho = float(density_kg_m3)
    vinf = _usable(vinf_m_s)
    force_scale = rho * rate**2 * diameter**4 if turning and rate is not None else None
    moment_scale = None if force_scale is None else force_scale * diameter
    advance = None if not turning or vinf is None or rate is None else vinf / (abs(rate) * diameter)
    pressure = None if vinf is None or vinf == 0.0 else 0.5 * rho * vinf**2
    area = math.pi * diameter**2 / 4.0
    own = rotations[frame.name]
    thrust, side, normal, torque, pitching, yawing = _rotor_frame_loads(force_n, moment_hub_nm, own)
    values: dict[str, float | str] = {
        "T": _over(thrust, 1.0),
        "Q": _over(torque, 1.0),
        "P": NOT_APPLICABLE if rate is None else _over(2.0 * math.pi * rate * torque, 1000.0),
        "CT": _over(thrust, force_scale),
        "CQ": _over(torque, moment_scale),
    }
    cq = values["CQ"]
    values["CP"] = (
        2.0 * math.pi * cq * (1.0 if rate and rate > 0 else -1.0) + 0.0
        if isinstance(cq, float)
        else NOT_APPLICABLE
    )
    values.update(
        {
            "CFZ": _over(normal, force_scale),
            "CFY": _over(side, force_scale),
            "CMZ": _over(yawing, moment_scale),
            "CMY": _over(pitching, moment_scale),
            "ETA": _efficiency(advance, values["CT"], values["CP"]),
        }
    )
    values.update(
        _loadings(
            (thrust, side, normal, torque, yawing, pitching),
            pressure=pressure,
            area=area,
            diameter=diameter,
            reference=(float(sref_m2), float(cref_m), float(bref_m)),
        )
    )
    values.update(
        _per_frame(
            (force_n, moment_hub_nm),
            rotations,
            scales=(force_scale, moment_scale),
            advance=advance,
            cp=values["CP"],
        )
    )
    return values


def _loadings(
    loads: tuple[float, float, float, float, float, float],
    *,
    pressure: float | None,
    area: float,
    diameter: float,
    reference: tuple[float, float, float],
) -> dict[str, float | str]:
    """``TC`` to ``MCA``: the loads ``(T, Y, Z, Q, N, M)`` over the disc and the airframe."""
    thrust, side, normal, torque, yawing, pitching = loads
    sref, cref, bref = reference
    disc = None if pressure is None else pressure * area
    airframe = None if pressure is None else pressure * sref
    return {
        "TC": _over(thrust, disc),
        "YC": _over(side, disc),
        "ZC": _over(normal, disc),
        "QC": _over(torque, None if disc is None else disc * diameter),
        "NC": _over(yawing, None if disc is None else disc * diameter),
        "MC": _over(pitching, None if disc is None else disc * diameter),
        "TCA": _over(thrust, airframe),
        "YCA": _over(side, airframe),
        "ZCA": _over(normal, airframe),
        "QCA": _over(torque, None if airframe is None else airframe * bref),
        "NCA": _over(yawing, None if airframe is None else airframe * bref),
        "MCA": _over(pitching, None if airframe is None else airframe * cref),
    }


def _per_frame(
    loads: tuple[Sequence[float], Sequence[float]],
    rotations: Mapping[str, NDArray[np.float64]],
    *,
    scales: tuple[float | None, float | None],
    advance: float | None,
    cp: float | str,
) -> dict[str, float | str]:
    """``CT<f>``, ``CQ<f>`` and ``ETA<f>`` for every frame, in the order of ``rotations``."""
    force_n, moment_hub_nm = loads
    force_scale, moment_scale = scales
    values: dict[str, float | str] = {}
    for name, turn in rotations.items():
        along, _side, _normal, about, _pitching, _yawing = _rotor_frame_loads(
            force_n, moment_hub_nm, turn
        )
        values[f"CT{name}"] = _over(along, force_scale)
        values[f"CQ{name}"] = _over(about, moment_scale)
        values[f"ETA{name}"] = _efficiency(advance, values[f"CT{name}"], cp)
    return values


def _angle_of(attitude: Mapping[object, object], key: str) -> float | None:
    """Return the row's ALPHA or BETA, read case-folded, or None where it states none."""
    for name, value in attitude.items():
        if str(name).casefold() == key.casefold():
            try:
                angle = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            return angle if math.isfinite(angle) else None
    return None


def _say_the_na_rows(
    product: str,
    alias: str,
    *,
    unangled: Sequence[str],
    at_rest: Sequence[str],
) -> None:
    """Warn once per table for rows with NA cells, naming the missing inputs."""
    if unangled:
        warn(
            f"point={unangled[0] or 'NA'} product={product}: {len(unangled)} row(s) of rotor "
            f"{alias} state no ALPHA or BETA, or one that is not a finite number "
            f"({', '.join(r or 'NA' for r in unangled)}), so the shaft angle and "
            f"ETAW_{alias} read NA there.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if at_rest:
        warn(
            f"point={at_rest[0] or 'NA'} product={product}: {len(at_rest)} row(s) of rotor "
            f"{alias} are static points ({', '.join(r or 'NA' for r in at_rest)}): the export's "
            "coefficients were divided by a zero dynamic pressure, so every rotor coefficient "
            "but J reads NA there (a static point).",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _row_number(row: Mapping[str, object], key: str, default: float = 0.0) -> float:
    """Return the row's number under ``key``; ``default`` where it states none."""
    stated = row.get(key)
    return float(stated) if isinstance(stated, int | float) else default


def _row_refusal(
    row: Mapping[str, object],
    alias: str,
    *,
    diameter: float,
    rate: float,
    density_kg_m3: float,
) -> str | None:
    """Why the table refuses this row, or None where it takes it."""
    if not rate > 0.0:
        return (
            f"{alias}: the row states no rotor speed, so every "
            "coefficient here would divide by zero"
        )
    if not diameter > 0.0:
        return f"{alias}: the reference states no diameter for this rotor"
    if not density_kg_m3 > 0.0:
        return f"{alias}: the row states no air density"
    stated_frame = row.get("frame")
    if isinstance(stated_frame, str) and (
        stated_frame.strip().casefold() not in GEOMETRY_ANALYSIS_FRAMES
    ):
        return (
            f"{alias}: its loads export states analysis frame {stated_frame!r}; the "
            "rotor's thrust, torque and wind-axis force need forces in the geometry's "
            "axes, and this frame's rotation is unknown"
        )
    return None


def _mach_cells(
    air: object,
    rpm: float,
    diameter: float,
    angles: tuple[float | None, float | None],
    shaft: tuple[float, float, float],
) -> tuple[tuple[float | None, float | None], float | None]:
    """Return the tip, helical and advancing-tip Mach of a row; NA where the air is unresolved."""
    if not (
        isinstance(air, tuple)
        and len(air) == 2
        and all(isinstance(value, int | float) for value in air)
    ):
        return (None, None), None
    try:
        machs = rotor_mach_numbers(
            rpm=rpm,
            diameter_m=diameter,
            velocity_m_per_s=float(air[0]),
            sonic_velocity_m_per_s=float(air[1]),
        )
        # FR-1201: the advancing tip, on the rotor's own axis and the row's attitude.
        # An unstated ALPHA or BETA is 0.0, stated as the default (FR-69), so MADV is
        # computed, not NA.
        madv = advancing_tip_mach_number(
            rpm=rpm,
            diameter_m=diameter,
            velocity_m_per_s=float(air[0]),
            sonic_velocity_m_per_s=float(air[1]),
            flow_direction=free_stream_direction_at(
                angles[0] if angles[0] is not None else 0.0,
                angles[1] if angles[1] is not None else 0.0,
            ),
            axis=shaft,
        )[0]
    except ValueError:
        # A speed of sound or a velocity that is not a positive
        # finite number costs these cells and never the row.
        return (None, None), None
    return machs, madv


# The names retired with their products answer by name (FR-457).
__getattr__ = removed_names_hook(__name__)
