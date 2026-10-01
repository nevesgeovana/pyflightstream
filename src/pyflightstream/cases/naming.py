"""The names of a point and of a sweep: the identity a run carries (0.34.0).

Pipeline role: turns a case's flight condition into the name that ends its
``run_id``, names its datapoint folder and stems every file it writes
(:func:`point_name`, :func:`sweep_name`, :func:`name_field` and the code table
:data:`POINT_NAME_FIELDS`), keeps the 0.20 tag a recorded workspace is read by
(:func:`point_tag`), and owns the one-sweep-per-case rule
(:func:`multiplied_sweep`).

The cut of AD-16 (0.34.0) moved these functions out of the package root, which
re-exports every one of them. They read a case and a sweep through the
attributes they use, stated as two protocols, so this module never imports the
package root that defines :class:`~pyflightstream.cases.SimCase` and
:class:`~pyflightstream.cases.SweepAxis`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pyflightstream.cases.reference_blocks import CampaignConfigError

__all__ = [
    "ROTATION_OFFSET_KEY",
    "ROTATION_SWEEP_KEY",
    "geometric_sweep_values",
    "multiplied_sweep",
    "NameField",
    "POINT_AXIS_KEYS",
    "POINT_NAME_FIELDS",
    "SWEEP_NAME_VALUE",
    "name_field",
    "point_name",
    "point_tag",
    "sweep_name",
]

#: The axes a point tag can name, and therefore the axes a run can be
#: IDENTIFIED by. All three are aerodynamic. Nothing geometric appears
#: here, which is the mechanical half of the reason a geometric sweep is
#: not allowed to multiply with an aerodynamic one; the reasoning is in
#: :func:`multiplied_sweep`.
_TAG_PREFIXES = (("alpha", "a"), ("beta", "b"), ("advance_ratio", "j"))

#: The case variable naming a rigid-body rotation of the geometry held
#: FIXED for the whole case: one angle in degrees, about the axis the
#: recipe or the workflow applies it to. This is the form that composes
#: with an aerodynamic sweep, and it is what a refusal points at.
ROTATION_OFFSET_KEY = "angle_deg"

#: The case variable naming a rotation the study SWEEPS: several angles
#: in degrees, comma separated, in the one string a case variable can
#: hold. A case naming two or more of these AND an aerodynamic sweep of
#: two or more points is refused (:func:`multiplied_sweep`).
ROTATION_SWEEP_KEY = "angle_sweep_deg"


@dataclass(frozen=True)
class NameField:
    """How one flight-condition variable is written in a point name (0.21.0).

    ``code`` then the value times ``scale``, rounded, zero-padded to
    ``width`` characters; a signed field counts its sign in the width.

    ``magnitude`` writes the field WITHOUT its sign whatever sign the value
    carries. It lives here, beside ``signed``, because it is the same kind of
    fact about the same field, and a reader adding a variable reads this
    dataclass and the table below. Held in a second table keyed by the same
    keys, it had to be remembered at each call site and was remembered at one of
    three: the sweep name and the duplicate-identity guard were writing the sign
    the point name had just dropped (the architect lens, FIX-0220).
    """

    code: str
    scale: float
    width: int
    signed: bool
    magnitude: bool = False


#: THE POINT NAME'S CODE TABLE (SCOPE-0210 section 1),
#: keyed by the canonical FLIGHT_CONDITION key. Codes differ in LETTERS and never
#: only in case, because a Windows file name does not distinguish case.
POINT_NAME_FIELDS: dict[str, NameField] = {
    "MACH": NameField("M", 1000.0, 3, False),
    "TASmps": NameField("V", 10.0, 4, False),
    "REmi": NameField("RE", 100.0, 3, False),
    "ALTFT": NameField("ALT", 1.0, 5, False),
    "dISA": NameField("DT", 10.0, 4, True),
    "RHOkgm3": NameField("RHO", 10000.0, 5, False),
    "MUPas": NameField("MU", 1e9, 5, False),
    "ASMPS": NameField("A", 10.0, 4, False),
    "TK": NameField("T", 10.0, 4, False),
    "PPA": NameField("PS", 1.0, 6, False),
    "ALPHA": NameField("AL", 10.0, 4, True),
    "BETA": NameField("BE", 10.0, 4, True),
    "ADVANCE_RATIO": NameField("J", 100.0, 4, True),
    # A MAGNITUDE, AND THEREFORE UNSIGNED. The hand of a rotation is the
    # reference rotor's and never the point's, so a folder named `RPM-0473`
    # would be naming a property of the ROTOR in the identity of a POINT, and
    # two runs of one speed in opposite directions would get two names for one
    # operating point.
    #
    # THE SIGN IS NOT DECORATION, IT IS A DIGIT. Written signed, the `+` could
    # never be a `-` and it cost the fifth character: 10000 rev/min wrote
    # `RPM+10000`, EIGHT characters where every other name is seven, so the
    # fixed-width scheme broke silently on any rotor past 9999. Unsigned, the
    # same width reaches 99999 and every name is the same length.
    "RPM": NameField("RPM", 1.0, 5, False, magnitude=True),
    "roll_rate": NameField("P", 10.0, 4, True),
    "pitch_rate": NameField("Q", 10.0, 4, True),
    "yaw_rate": NameField("R", 10.0, 4, True),
}

#: The point axes, by the name a sweep point uses, and the FLIGHT_CONDITION key
#: each one is. THE THREE HISTORICAL AXES KEEP THEIR LOWER-CASE NAMES, which
#: every manifest, product table and point mapping ever written here carries;
#: the variables that became sweepable at 0.21.0 are named by their cell key,
#: so a reader of a row and a reader of a point read one vocabulary.
#:
#: THE ORDER IS THE NAME'S FALLBACK ORDER, used by a case with no cell: the
#: flow keys, then the angles, then the rotor and the rates, which is the order
#: the reference matrices declare them in.
POINT_AXIS_KEYS: dict[str, str] = {
    "MACH": "MACH",
    "TASmps": "TASmps",
    "REmi": "REmi",
    "ALTFT": "ALTFT",
    "dISA": "dISA",
    "RHOkgm3": "RHOkgm3",
    "MUPas": "MUPas",
    "ASMPS": "ASMPS",
    "TK": "TK",
    "PPA": "PPA",
    "alpha": "ALPHA",
    "beta": "BETA",
    "advance_ratio": "ADVANCE_RATIO",
    "RPM": "RPM",
    "roll_rate": "roll_rate",
    "pitch_rate": "pitch_rate",
    "yaw_rate": "yaw_rate",
}

#: What a swept field carries in place of its value in a name about a whole
#: sweep (a one-job script, a superfile): ``AL+sweep``.
SWEEP_NAME_VALUE = "+sweep"


def name_field(key: str, value: float) -> str:
    """Write one variable the way a point name carries it, for example ``M144`` or ``AL-020``.

    Parameters
    ----------
    key : str
        The FLIGHT_CONDITION key, a key of :data:`POINT_NAME_FIELDS`.
    value : float
        The variable's value on the point.

    Returns
    -------
    str
        The field: its code, then the scaled value, zero-padded to its width.

    Raises
    ------
    CampaignConfigError
        If the key has no code, or an unsigned variable is negative.

    Examples
    --------
    >>> name_field("MACH", 0.144)
    'M144'
    >>> name_field("ALPHA", -2.0)
    'AL-020'
    """
    field = POINT_NAME_FIELDS.get(key)
    if field is None:
        raise CampaignConfigError(
            f"{key!r} has no code in the point name, so a point declaring it cannot be "
            f"named; the codes are for {', '.join(POINT_NAME_FIELDS)}."
        )
    # A MAGNITUDE FIELD REFUSES A SIGN RATHER THAN ABSORBING ONE, and the
    # difference is a whole defect. Absorbing it is silent, and silence is what
    # this rule exists to end: a swept `RPM` over `600, -600` had its two points
    # named identically, so the user met a FILE NAME COLLISION instead of the
    # sentence that says where the hand belongs, on a row whose scalar form
    # refuses correctly (the qa lens, FIX-0220).
    #
    # It is checked HERE, in the one funnel every name goes through, because
    # three call sites write a field through this function -- the point name,
    # the sweep name and the guard that refuses two points sharing one name --
    # and a rule applied at one of them made those three disagree.
    if field.magnitude and float(value) < 0.0:
        raise CampaignConfigError(
            f"{key} is {value!r}, and a row's rotor speed is a MAGNITUDE: it says how "
            "fast, not which way. The hand of the rotation is the rotor's, declared "
            "once in the reference beside its axis and its origin. Write the speed "
            "positive and set 'rpm_sign' there; on a row that names no rotor block, "
            "write 'RPM_SIGN: -1' beside the speed."
        )
    number = round(float(value) * field.scale)
    if field.signed:
        return f"{field.code}{number:+0{field.width}d}"
    if number < 0:
        raise CampaignConfigError(
            f"{key} is {value!r}, and a point name writes {key} without a sign, so the "
            f"point name cannot carry a negative {key}. The flight condition itself can "
            "hold one; it is the name of the point that has no place for the sign."
        )
    return f"{field.code}{number:0{field.width}d}"


class _NamedSweep(Protocol):
    """The attributes of a :class:`~pyflightstream.cases.SweepAxis` a name reads.

    A protocol and not the class, because the class lives in the package root
    and this module may not import the root (AD-16): the root imports this
    module while it loads.
    """

    @property
    def type(self) -> str:
        """The swept axis, or ``alpha_beta``."""
        ...

    @property
    def values(self) -> Sequence[object]:
        """The swept values."""
        ...

    def points(self) -> Iterator[dict[str, float]]:
        """Yield each point of the sweep."""
        ...


class _NamedCase(Protocol):
    """The attributes of a :class:`~pyflightstream.cases.SimCase` a name reads.

    A protocol for the reason :class:`_NamedSweep` states.
    """

    @property
    def sim_id(self) -> str:
        """The case's identity."""
        ...

    @property
    def mach(self) -> float | None:
        """The case's Mach number, if it states one."""
        ...

    @property
    def sweep(self) -> _NamedSweep:
        """The case's aerodynamic sweep."""
        ...

    @property
    def flight_condition(self) -> Mapping[str, float]:
        """The case's FLIGHT_CONDITION values."""
        ...

    @property
    def condition_order(self) -> Sequence[str]:
        """The FLIGHT_CONDITION keys in the row's order."""
        ...

    @property
    def variables(self) -> Mapping[str, object]:
        """The case's free variables."""
        ...


def _name_order(case: _NamedCase, point: Mapping[str, float]) -> list[str]:
    """Return the declared FLIGHT_CONDITION keys in row order, or a cell-less case's fallback."""
    order = list(case.condition_order)
    if not order:
        if case.mach is not None:
            order.append("MACH")
        order.extend(POINT_AXIS_KEYS[axis] for axis in POINT_AXIS_KEYS if axis in point)
    # A point axis the order does not state still names the point, at the end:
    # two points of one case must never share a name for want of a key.
    order.extend(
        POINT_AXIS_KEYS[axis]
        for axis in POINT_AXIS_KEYS
        if axis in point and POINT_AXIS_KEYS[axis] not in order
    )
    return order


def _as_a_number(case: _NamedCase, key: str, stated: object, where: str) -> float:
    """Return ``stated`` as a number, or raise the refusal this path promises.

    ONE conversion for all four places a declared variable's value can come
    from, so a fifth cannot be added past the refusal. The first writing wrapped
    the `variables` branch alone and left the other three raising a bare
    `ValueError` out of `float()` -- including `flight_condition`, which is where
    a MATRIX CELL's value lands and is the branch the requirement is about
    (measured by the closing round, 2026-09-16: a cell stating `MACH: fast` gave
    `could not convert string to float: 'fast'`).
    """
    try:
        return float(stated)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} in its flight condition and states "
            f"{stated!r} for it in {where}, which is not a number, so the point cannot "
            "be named."
        ) from None


def _name_value(case: _NamedCase, point: Mapping[str, float], key: str) -> float:
    for axis, axis_key in POINT_AXIS_KEYS.items():
        if key == axis_key and axis in point:
            return _as_a_number(case, key, point[axis], "this point")
    if key in case.flight_condition:
        return _as_a_number(case, key, case.flight_condition[key], "its FLIGHT_CONDITION")
    if key == "MACH" and case.mach is not None:
        return _as_a_number(case, key, case.mach, "its Mach number")
    if key in case.variables:
        return _as_a_number(case, key, case.variables[key], "its variables")
    raise CampaignConfigError(
        f"case {case.sim_id!r} declares {key} in its flight condition and this point carries "
        f"no value for it, so the point cannot be named."
    )


def point_name(case: _NamedCase, point: Mapping[str, float]) -> str:
    """Return the name of one point of a case: its identity, folder and file stem (0.21.0).

    Every variable the row's FLIGHT_CONDITION declares, in the order the row
    declares them, written as :data:`POINT_NAME_FIELDS` says, with the point's
    own value for a swept one: ``M144RE438AL+000BE+000J+080``. A case with no
    cell (authored in Python) is named by its Mach number when it has one and
    then by the axes of its point. It ends the ``run_id``, names the datapoint
    folder ``DP-<name>`` and is the stem of every file ``P<POL>-<name>``.

    Parameters
    ----------
    case : SimCase
        The case the point belongs to.
    point : mapping of str to float
        The point's coordinates, as :meth:`SweepAxis.points` yields them.

    Returns
    -------
    str
        The point name, every field of :func:`name_field` in the row's order.

    Raises
    ------
    CampaignConfigError
        If a declared variable has no value on this point or no code.

    Examples
    --------
    >>> from pyflightstream.cases import SimCase, SweepAxis
    >>> case = SimCase(
    ...     sim_id="7002",
    ...     aircraft="Wing",
    ...     recipe="steady",
    ...     sweep=SweepAxis(type="alpha", values=[0.0, 2.0]),
    ...     mach=0.144,
    ... )
    >>> point_name(case, {"alpha": 2.0})
    'M144AL+020'
    """
    return "".join(
        name_field(key, _name_value(case, point, key)) for key in _name_order(case, point)
    )


def sweep_name(case: _NamedCase) -> str:
    """Return the name of a case's whole sweep, each swept field written ``<code>+sweep``.

    Parameters
    ----------
    case : SimCase
        The case whose sweep is named.

    Returns
    -------
    str
        The name of the case's first point with every swept field written
        :data:`SWEEP_NAME_VALUE` in place of its value, for example
        ``M144AL+sweep``.
    """
    swept = {POINT_AXIS_KEYS[axis] for axis in _swept_axes(case.sweep)}
    first = next(case.sweep.points(), {})
    parts = []
    for key in _name_order(case, first):
        if key in swept:
            parts.append(f"{POINT_NAME_FIELDS[key].code}{SWEEP_NAME_VALUE}")
        else:
            parts.append(name_field(key, _name_value(case, first, key)))
    return "".join(parts)


def _swept_axes(sweep: _NamedSweep) -> tuple[str, ...]:
    return ("alpha", "beta") if sweep.type == "alpha_beta" else (sweep.type,)


def point_tag(point: dict[str, float]) -> str:
    """Return the 0.20.x file-name tag of one sweep point.

    The tag encodes the point coordinates in a fixed axis order with
    signed fixed-width values, for example ``a+02.0_b+00.0``. Until 0.20.x it
    named the generated script and ended the ``run_id``; SINCE 0.21.0 NEITHER
    IS TRUE, and :func:`point_name` is both. This is kept for the two readers
    of a recorded workspace: `pyfs-matrix rename`, which maps a 0.20 record to
    its new name with it, and anything reading a manifest written before the
    rename.

    Parameters
    ----------
    point : dict of str to float
        Point coordinates as produced by :meth:`SweepAxis.points`.

    Returns
    -------
    str
        The tag, one signed fixed-width field per axis the point carries.

    Raises
    ------
    CampaignConfigError
        If the point carries none of ``alpha``, ``beta`` and ``advance_ratio``.

    Examples
    --------
    >>> point_tag({"alpha": 2.0, "beta": 0.0})
    'a+02.0_b+00.0'
    """
    parts = [f"{prefix}{point[axis]:+05.1f}" for axis, prefix in _TAG_PREFIXES if axis in point]
    if not parts:
        raise CampaignConfigError(f"point {point!r} has no known axis (alpha, beta, advance_ratio)")
    return "_".join(parts)


def geometric_sweep_values(variables: Mapping[str, object]) -> list[str]:
    """Return the angles a case's geometric sweep variable declares.

    The variable is :data:`ROTATION_SWEEP_KEY`, and its values are
    comma separated because a case variable holds one scalar or one
    string and never a list. Values are returned as written, in degrees,
    without being converted: this function counts how many angles were
    asked for, and whether each is a number is the recipe's or the
    workflow's refusal to make, naming the key the user typed.

    The key is matched CASE-INSENSITIVELY. Its spelling is settled
    elsewhere, and a limit that fires only for one casing is a limit a
    user gets past by shouting.

    EVERY matching key is read and their values are POOLED, rather than
    the first match winning. Two keys differing only in case are two
    distinct entries in a variables mapping, so a first-match rule let a
    one-angle ``angle_sweep_deg`` stand in front of a three-angle
    ``ANGLE_SWEEP_DEG`` and carry the whole declaration past the limit.
    Pooling closes that and is right on its own terms besides: two keys
    naming one rotation is an ambiguity, and counting both is what makes
    the ambiguous case meet a refusal rather than a coin toss.

    Parameters
    ----------
    variables : mapping of str to object
        A case's free variables, as :attr:`SimCase.variables` holds them
        or as the run matrix reader parsed its ``VAR_NAMES_VALUES`` cell.

    Returns
    -------
    list of str
        The declared angles in degrees, in the order written, pooled
        across every key that spells :data:`ROTATION_SWEEP_KEY` in any
        casing. Empty when no such key is present or all of them hold
        nothing but separators, which are the same fact here: no
        geometric sweep was asked for.

    Examples
    --------
    >>> geometric_sweep_values({"angle_sweep_deg": "0.0,5.0,10.0"})
    ['0.0', '5.0', '10.0']
    >>> geometric_sweep_values({"angle_sweep_deg": "5.0", "ANGLE_SWEEP_DEG": "7.5"})
    ['5.0', '7.5']
    >>> geometric_sweep_values({"CONFIG": "NSX"})
    []
    """
    angles: list[str] = []
    for name, value in variables.items():
        if name.strip().lower() == ROTATION_SWEEP_KEY:
            angles += [token.strip() for token in str(value).split(",") if token.strip()]
    return angles


def multiplied_sweep(sweep: _NamedSweep, variables: Mapping[str, object]) -> list[str]:
    """Return the geometric angles that would MULTIPLY with the sweep.

    This is the single owner of the one-sweep-per-case limit, called from
    both places a case can be declared: the ``campaign.toml`` model
    (:class:`SimCase`) and the run matrix reader
    (:func:`pyflightstream.cases.matrix.read_matrix`). Two owners would
    be two rules, and the drift would be discovered by a user whose
    hand-written campaign ran what the matrix refuses.

    THE DECISION IT ENFORCES (design note DD-28): a geometric sweep does
    NOT multiply with
    the aerodynamic one. A case carries one aerodynamic sweep and at most
    one FIXED geometric offset (:data:`ROTATION_OFFSET_KEY`); a study OF
    the geometry is one case per geometry, each with its own ``sim_id``.
    Multiplication was rejected on identity rather than on taste. A run
    is identified by :func:`point_tag`, whose axes are
    :data:`_TAG_PREFIXES`, and none of the three is geometric, so the
    three angles of a rotation sweep crossed with an eleven point alpha
    sweep are thirty three runs wearing eleven identities: each group of
    three renders one tag, one ``run_id`` and one set of output file
    names. That is exactly the collision
    :meth:`SweepAxis._points_have_distinct_tags` already refuses within
    one axis, and it is not made safe by arriving from a second axis. The
    same collapse reaches the evidence:
    :class:`pyflightstream.qa.cost.PointKey` keys a cost row by
    ``sim_id`` and the recorded point, so three geometries under one
    ``sim_id`` average into one cell and the geometry that got slower
    cannot be seen.

    Parameters
    ----------
    sweep : SweepAxis
        The case's aerodynamic sweep.
    variables : mapping of str to object
        The case's free variables.

    Returns
    -------
    list of str
        The geometric angles in degrees when BOTH sweeps carry two or
        more values, which is the multiplying shape. Empty otherwise, so
        a fixed offset beside a sweep, a rotation sweep on a single point
        case, and a case with no geometric variable at all all pass: each
        of those is one sweep, and one sweep is what a case may have.

    Examples
    --------
    >>> from pyflightstream.cases import SweepAxis
    >>> sweep = SweepAxis(type="alpha", values=[0.0, 2.0, 4.0])
    >>> multiplied_sweep(sweep, {"angle_sweep_deg": "0.0,5.0"})
    ['0.0', '5.0']
    >>> multiplied_sweep(sweep, {"angle_deg": "5.0"})
    []
    """
    angles = geometric_sweep_values(variables)
    if len(angles) < 2 or len(sweep.values) < 2:
        return []
    return angles
