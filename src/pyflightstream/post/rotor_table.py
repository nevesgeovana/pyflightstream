"""The rotor table: one coefficient table per rotor the reference declares.

One of the product families of :mod:`pyflightstream.post`, written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports every name here.

``polars/P<sim>-<sweep>_<ROTOR>_rotor.csv``: one row per point, the rotor's
loads in its own shaft frame (:class:`RotorShaftLoads`,
:func:`rotor_shaft_loads`) and its thrust, torque and power coefficients
with the in-plane ones (:func:`rotor_coefficients`,
:data:`ROTOR_COEFFICIENT_COLUMNS`, :data:`ROTOR_IN_PLANE_COLUMNS`,
:func:`rotor_coefficient_columns`), written by :func:`write_rotor_table`.
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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._tokens import POLAR_ID_COLUMN, ROTOR_ID_COLUMN
from pyflightstream.cases import (
    select_group_members,
)
from pyflightstream.cases.workflows import (
    advancing_tip_mach_number,
    free_stream_direction_at,
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
        Free-stream speed in m/s; zero or below gives NaN loads.
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
    product: str, alias: str, *, unangled: Sequence[str], at_rest: Sequence[str]
) -> None:
    """Warn once per table for the rows written with NA cells, naming them and why."""
    if unangled:
        warn(
            f"point={unangled[0] or 'NA'} product={product}: {len(unangled)} row(s) of rotor "
            f"{alias} state no ALPHA or BETA ({', '.join(r or 'NA' for r in unangled)}), so "
            f"the shaft angle and ETAW_{alias} read NA there; nothing is taken as level flight.",
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
    if rate <= 0.0:
        return (
            f"{alias}: the row states no rotor speed, so every "
            "coefficient here would divide by zero"
        )
    if diameter <= 0.0:
        return f"{alias}: the reference states no diameter for this rotor"
    if density_kg_m3 <= 0.0:
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
        # FR-1201: the advancing tip, on the rotor's own axis and the
        # row's attitude (an unstated angle is zero, as in the loads above).
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
    """Write one rotor's coefficient table from the admitted rows.

    ``left_out`` collects ``(run_id, reason)`` for every row this refuses, and
    ``written_runs`` collects the run id of every row it DID write. Both are
    out-parameters because the caller owns the manifest and must distinguish
    omitted rows from the runs contributing to the written table.

    ``pol`` is the polar the rows come from, the matrix row's POL, written in
    the first column of every row; `NA` where the caller states none.

    `rotor_coefficients` and `rotor_coefficient_columns` existed with no
    caller: pieces of a table and no table. This is the table.

    THE FIRST LINE IS THE HEADER (G16). The table opens with `POL` and then
    `ROTOR`, the rotor's alias, on every row, because a script that has already
    LOADED the file no longer has its name -- it holds an array of numbers, and
    the alias has to be inside the bytes. a legacy table places the alias
    alone on the first line instead, before the header, and no CSV reader took
    the file as written.

    EVERY COLUMN CARRIES THE ALIAS TOO, which is physical rather than cosmetic:
    two rotors summed into one `CT` is not a worse `CT`, it is not a `CT` at
    all, because the diameters and speeds that normalise them are different
    numbers. The suffix is what makes the mistake impossible by accident.

    Return None without writing when no row survives validation. Refused rows
    are named in ``left_out``. A valid static row is retained, with unavailable
    coefficients written as ``NA``.

    Parameters
    ----------
    path : str or Path
        Destination file.
    rotor : object
        The rotor, read for its ``alias``, ``diameter_m``, ``axis_vector`` and
        hub position.
    rows : sequence of mapping
        One mapping per run, holding its ``run_id``, ``rpm``, ``density``,
        ``speed``, ``free_stream``, ``condition``, ``air``, ``surfaces``,
        ``aliases`` and ``frame`` where it has them. ``speed`` is the reference
        velocity used to dimensionalize loads; ``free_stream`` is the flight
        speed used for advance ratio and efficiencies, defaulting to ``speed``.
    reference : ReferenceValues
        The reference lengths and moment point of the run.
    left_out : list of tuple of str, optional
        Receives ``(run_id, reason)`` for every row refused.
    written_runs : list of str, optional
        Receives the run id of every row written.
    pol : str or int, optional
        The polar the rows come from, written first in every row; ``NA`` where
        None.

    Returns
    -------
    Path or None
        The file written, or None when no row survives validation.

    Raises
    ------
    ProductError
        If the rotor has no alias to carry in the column names (a
        ``ValueError``).
    """
    alias = str(getattr(rotor, "alias", "") or "")
    # State speed and diameter beside coefficients normalised by rho n^2 D^4
    # or D^5; RHO is in the shared block. POL and ROTOR lead (G16), followed
    # by the coefficient and condition columns, then tip and helical Mach
    # (M1) and the four in-plane coefficients (G8).
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
        f"MADV_{alias}",
    )
    diameter = float(getattr(rotor, "diameter_m", 0.0) or 0.0)
    # G8: the rotor's (T, S, N) axes are the same for every row, so
    # an axis along the reference frame's up, which has no normal and no side
    # axis, is said once for the table and its four in-plane columns read NA.
    shaft = _unit(getattr(rotor, "axis_vector", (0.0, 0.0, 1.0)))
    in_plane_defined = rotor_in_plane_axes(shaft) is not None
    in_plane_said = False

    written: list[tuple[object, ...]] = []
    # Normalise both out-parameters once so each skipped row reports its
    # reason and each written row reports its run to the manifest.
    refused = [] if left_out is None else left_out
    emitted = [] if written_runs is None else written_runs
    unangled: list[str] = []
    at_rest: list[str] = []
    for row in rows:
        stated = row.get("run_id")
        run_id = str(stated) if isinstance(stated, str) else ""
        # NARROWED HERE rather than annotated away: the row is a plain
        # mapping the caller assembles, so its values arrive as `object`
        # and a `float(...)` on one is a claim the type checker is right
        # to refuse. A row stating a speed that is not a number states no
        # speed, and there is no table to write for it.
        rpm = _row_number(row, "rpm")
        # Negative RPM identifies rotation direction, not a stopped rotor.
        # Use the magnitude for rate normalisation: CT is quadratic in n and
        # J = V / (n D) must not change sign for a forward-flying counter-rotor.
        # Keep signed torque and rotation for the power calculation.
        rate = abs(rpm)
        # Normalise with this point's air and velocity, never another point
        # of the sweep's state; see _rotor_tables.
        density_kg_m3 = _row_number(row, "density")
        speed_m_s = _row_number(row, "speed")
        # THE ADVANCE RATIO IS THE FREE STREAM'S. `speed` is the export's
        # REFERENCE velocity, which is right for taking a coefficient back to
        # Newtons and wrong for `J = V / (n D)`, a ratio of the flight speed. The
        # two are equal in every campaign recorded so far; a row that states no
        # free stream keeps the speed it has.
        flight_m_s = _row_number(row, "free_stream", speed_m_s)
        # THE ROW'S OWN ATTITUDE REACHES THE ANGLE. Left to default, every
        # point reports the level-flight shaft angle and `ETAW` carries the
        # aircraft's pitch as an omission -- the defect one level up from the
        # one item 19 removed.
        stated = row.get("condition")
        attitude = stated if isinstance(stated, Mapping) else {}
        # ONE PREMISE, ONE VERDICT, AND THE ROW SAYS IT (PFS-2105.040): a loads
        # export in another frame gave a row of NA listed as written, with no
        # reason anywhere; the frame check refuses the whole row, named.
        reason = _row_refusal(row, alias, diameter=diameter, rate=rate, density_kg_m3=density_kg_m3)
        if reason is not None:
            refused.append((run_id, reason))
            continue
        angles = (_angle_of(attitude, "ALPHA"), _angle_of(attitude, "BETA"))
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
            alpha_deg=angles[0] if angles[0] is not None else 0.0,
            beta_deg=angles[1] if angles[1] is not None else 0.0,
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
        if None in angles:
            # NO ATTITUDE IS NOT LEVEL FLIGHT (PFS-2105.018): the shaft angle and
            # the wind-axis force need the row's ALPHA and BETA, and read NA.
            loads = replace(loads, shaft_angle_deg=math.nan, wind_force_n=math.nan)
            unangled.append(run_id)
        if 0.5 * density_kg_m3 * speed_m_s**2 <= 0.0:
            at_rest.append(run_id)
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
            # G8: the same force and hub moment the thrust and the
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
                "reference frame's vertical axis (+z or -z), so it has no normal and no side "
                f"axis, and CN_{alias}, CS_{alias}, CMN_{alias} and CMS_{alias} read NA "
                "on every row of this table.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        eta = coefficients.get("ETA")
        if isinstance(eta, int | float) and eta > 1:
            warn(
                f"point={run_id or 'NA'} product={Path(path).name}: rotor {alias} "
                f"efficiency ETA={eta:g} exceeds 1; check the wake and loads.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        stated_condition = row.get("condition")
        condition = dict(stated_condition) if isinstance(stated_condition, Mapping) else {}
        # M1: `NA` where the point's air did not resolve, never a guess.
        machs, madv = _mach_cells(row.get("air"), rpm, diameter, angles, shaft)
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
                madv,
            )
        )
        emitted.append(run_id)

    if not written:
        return None
    _say_the_na_rows(Path(path).name, alias, unangled=unangled, at_rest=at_rest)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # THROUGH `write_csv_table`, which is THE funnel: every cell of every
    # product is rendered by `_cell` there, so a value this table cannot fill
    # reads `NA` like every other product rather than by a rule of its own.
    # Writing the rows here with `csv.writer` would be a fifth family spelling
    # its own absences, which is the drift item 5 repaired.
    return write_csv_table(target, columns, written)
