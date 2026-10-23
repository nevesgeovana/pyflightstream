"""The row readers: one typed value per ``VAR_NAMES_VALUES`` key.

A case converted from a run matrix carries its cells as strings, so every
value a workflow takes off a row is converted here, with a refusal naming
the case and the key: :func:`_variable` and the ``_required_*`` readers, the
angle and the velocity, the rotor speed (:func:`rotor_speed`) and the rotor
Mach numbers, the restart and wall-time cells, the case kind of a
quasi-steady rotor, the rotor a row names, and the refusals of a key the
run type does not register (:func:`_refuse_unregistered_keys`).

A new row key that needs a typed reader gains it here, beside the readers
of the same kind.
"""

from __future__ import annotations

import math
from collections.abc import (
    Mapping,
)
from dataclasses import (
    dataclass,
)
from pathlib import (
    PurePath,
)
from typing import (
    cast,
)

from pyflightstream._errors import (
    PyflightstreamWarning,
    warn,
)
from pyflightstream._fsm import (
    MeshReadError,
    saved_length_unit,
)
from pyflightstream._lengths import (
    scale,
)
from pyflightstream.cases import (
    CampaignConfigError,
    RotorBlock,
    SimCase,
)
from pyflightstream.cases._skipped_families import names_a_row_can_cite
from pyflightstream.cases.windows import ExportThresholdRecord, StoppedStepRecord
from pyflightstream.script import (
    Script,
)

from ._conventions import (
    WORKFLOWS,
    _workflow_cell,
)
from ._row_cells import (
    _required_float as _required_float,
)
from ._row_cells import (
    _required_int as _required_int,
)
from ._row_cells import (
    _variable as _variable,
)
from ._row_cells import (
    row_walltime_is_best as row_walltime_is_best,
)
from ._row_cells import (
    row_walltime_s as row_walltime_s,
)
from ._row_cells import (
    row_walltime_text as row_walltime_text,
)
from ._row_cells import (
    walltime_margin_s as walltime_margin_s,
)
from ._vocabulary import (
    ACTUATOR_VARIABLE,
    ADVANCE_RATIO_VARIABLE,
    ALPHA_VARIABLE,
    BETA_VARIABLE,
    CONVERTER_PREFIX,
    LAST_ITERS_AVG_VARIABLE,
    LAST_REVS_AVG_VARIABLE,
    MOTIONS_VARIABLE,
    MOVING_BC_ALIAS_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    NCPUS_VARIABLE,
    PERIODIC_COPIES_VARIABLE,
    QSTEADY_ROTOR,
    RATE_VARIABLES,
    RESERVED_CONTINUATION_VARIABLES,
    RESTART_ADDITIONAL_ITERS,
    RESTART_ADDITIONAL_REVS,
    RESTART_FINISH_PENDING,
    RESTART_FORMS,
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    ROTOR_ORIGIN_POINT_KEY,
    ROTOR_SHEDDING_VARIABLE,
    RPM_SIGN_VARIABLE,
    RPM_VARIABLE,
    SIMULATION_SUFFIX,
    SWEEP_WORD,
    SYMMETRY_LOADS_VARIABLE,
    SYMMETRY_VARIABLE,
    VELOCITY_VARIABLE,
    _refuse_retired_window_keys,
)

# --- reading the row ----------------------------------------------------------


# Rotor speed and clock. An advance ratio and azimuthal step determine
# rev/min and seconds at the run's velocity. Both direct and derived
# forms are accepted; the derived form preserves those design choices
# when the flight condition changes.


@dataclass(frozen=True)
class RotorSpeed:
    """The rotor speed of one case, and which form the row stated.

    Attributes
    ----------
    sim_id : str
        The case this speed was resolved from. It exists so that a speed
        HANDED to another function can be checked against the case that
        function was given: without it, a speed resolved from a
        different row produces a clock and a rotor motion that are
        internally consistent, export, and are wrong, and nothing
        anywhere could refuse it.
    stated_form : str
        ``rpm`` or ``advance_ratio``: what the user wrote.
    stated_value : float
        Their value, verbatim and unconverted.
    rpm : float
        The rotor speed in rev/min, signed. Derived where the form is an
        advance ratio, and the stated value itself where it is not.
    advance_ratio : float or None
        The ratio, where one was stated.
    velocity_m_per_s, diameter_m : float or None
        The two quantities the derivation consumed; None where nothing
        was derived, so a record cannot claim inputs it never read.
    """

    sim_id: str
    stated_form: str
    stated_value: float
    rpm: float
    advance_ratio: float | None
    velocity_m_per_s: float | None
    diameter_m: float | None

    def record(self) -> dict[str, object]:
        """Return the stated form, the derived one, and every input consumed.

        NOTHING IN THIS PACKAGE CONSUMES THIS YET; see
        :meth:`TimeStepping.record`, which states the position both are
        in and why they exist before a consumer does.
        """
        return {
            "form": self.stated_form,
            "stated": self.stated_value,
            "rpm": self.rpm,
            "advance_ratio": self.advance_ratio,
            "velocity_m_per_s": self.velocity_m_per_s,
            "diameter_m": self.diameter_m,
        }


def _admit_a_row_hand(case: SimCase, rotor: RotorBlock, stated: str) -> None:
    """Admit a row's `RPM_SIGN` beside a declared rotor when it equals the rotor's hand.

    The hand of a rotation is the rotor's, declared once beside its axis and its
    origin; a row that states the SAME value says nothing the block does not, so it
    passes. A row that states a DIFFERENT value is a second opinion and is refused
    (the rule of X-F-1147 and X-F-1157: only the disagreement is refused).
    One home for the sentence, because the record path (`_motion_view`) and the
    row path (`_rpm_sign`) enforce the same rule.
    """
    hand = _hand_of(stated)
    if hand not in (1, -1):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {RPM_SIGN_VARIABLE} as {stated!r}; "
            "the sign of a rotor speed is 1 or -1. State one of those two values."
        )
    if hand == rotor.rpm_sign:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {RPM_SIGN_VARIABLE} as {stated!r} and the rotor "
        f"{rotor.alias!r} declares {rotor.rpm_sign} in the reference, which disagrees "
        "with it. The hand of a rotation is the rotor's, declared once beside its axis "
        f"and its origin. Remove {RPM_SIGN_VARIABLE} from the row, or state the rotor's "
        f"own value; to turn it the other way, set 'rpm_sign' on the {rotor.alias!r} "
        "block of the reference artifact."
    )


def _hand_of(text: object) -> int | None:
    """Return the integer a row's `RPM_SIGN` text states, or None when it is not one."""
    try:
        return int(str(text).strip())
    except ValueError:
        return None


def _rotor_the_row_names(case: SimCase) -> RotorBlock | None:
    """Return the rotor block a row names by alias IN ITS OWN VARIABLES, or None.

    A row may cite its rotor in two places: one record of a ``MOTIONS``
    list, or the row's own ``MOVING_BC_ALIAS`` cell when it turns a single
    rotor and states no list. Both are supported spellings and the second
    is the one the blade-count refusal recommends in those words.

    Both motion records and flat rows resolve a declared rotor's hand
    through its reference block. A speed is a magnitude; its written sign
    cannot override the block (FIX-0220).

    Returns None for a row that states a ``MOTIONS`` list, because a record
    row's alias is the RECORD's and is answered by the view; the matrix
    reader refuses the flat cell beside a list, so the two cannot both be
    the row's.
    """
    if case.motions:
        return None
    alias = case.variables.get(MOVING_BC_ALIAS_VARIABLE)
    if alias is not None:
        return _rotor_of(case, {MOVING_BC_ALIAS_VARIABLE: str(alias)})
    # A flat row whose moving boundary belongs to a declared rotor block
    # takes that block's hand, just as a MOTIONS row does. If the reference
    # declares no matching block, the row's own RPM_SIGN supplies the hand.
    # WITH NO SELECTOR AT ALL, THE SOLE BLOCK THE REFERENCE DECLARES IS THE ROTOR THE ROW
    # TURNS (the same answer :func:`_the_rotor_a_flat_row_turns` gives every run type): its
    # hand and its diameter are the row's, not a default of 1 and the reference's top-level
    # diameter (F-036, F-037).
    moving = case.variables.get(MOVING_BOUNDARIES_VARIABLE)
    if moving is None:
        return _the_rotor_a_flat_row_turns(case)
    named = [part.strip() for part in str(moving).replace(",", " ").split() if part.strip()]
    if not named:
        return _the_rotor_a_flat_row_turns(case)
    # THE SELECTOR IS RESOLVED, NOT SPELT-MATCHED. A row may name the families
    # themselves, the rotor's own alias, or a SETUP ALIAS that stands for them,
    # and the three are the same selection. Comparing the raw tokens matched the
    # first two and missed the third, so a row turning `PROP` -- an alias of the
    # rotor's own blade -- read as turning no declared rotor and kept the row's
    # hand: +800 against a block declaring -1, silent (Codex, FIX-0220).
    vocabulary = _the_names_a_rotor_answers_to(case)
    families = {
        family.casefold()
        for token in named
        for family in (vocabulary.get(token) or vocabulary.get(token.upper()) or [token])
    }
    families |= {token.casefold() for token in named}
    # AND THE TEST IS INTERSECTION, NOT SUBSET. A row turning a rotor's blade
    # AND a non-rotor surface in the same cell is an ordinary row, and under a
    # subset test it matched no block at all -- the same silence again, and the
    # likeliest shape of the three.
    touched = [
        block
        for block in case.rotors.values()
        if families
        & {
            name.casefold()
            for name in (*block.families_general, *block.families_blades, block.alias)
        }
    ]
    if not touched:
        return None
    if len(touched) > 1:
        hands = ", ".join(f"{block.alias} ({block.rpm_sign:+d})" for block in touched)
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {MOVING_BOUNDARIES_VARIABLE}: {moving}, which "
            f"reaches {len(touched)} rotors the reference declares -- {hands} -- and the "
            "row states ONE speed for them. Which way that speed turns has as many "
            "answers as there are rotors, so it is refused rather than answered by "
            f"whichever block was read first. State each rotor as its own motion, with "
            f"{MOTIONS_VARIABLE} and {MOVING_BC_ALIAS_VARIABLE}, so each takes its own "
            "block's hand and its own speed."
        )
    return touched[0]


def _rpm_sign(case: SimCase) -> int:
    """Return the HAND of this rotor's rotation, defaulting to 1.

    The reference's rotor block declares it, and it reaches this function by
    whichever of the two routes the row uses: `_motion_view` fills it into the
    view it builds for a MOTIONS record, and `_rotor_the_row_names` resolves it
    for a row that names its rotor in its own cell. It applies to a speed STATED
    in rev/min exactly as it applies to one derived from an advance ratio: the
    row says how fast and the block says which way.

    A row that declares no rotor block keeps the hand in its own ``RPM_SIGN``,
    which is the only home such a row has.
    """
    text = _variable(case, RPM_SIGN_VARIABLE)
    block = _rotor_the_row_names(case)
    if block is not None:
        if text is not None:
            _admit_a_row_hand(case, block, text)
        return block.rpm_sign
    if text is None:
        return 1
    try:
        sign = int(str(text).strip())
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {RPM_SIGN_VARIABLE} as {text!r}, and the "
            "sign of a rotor speed is 1 or -1. It is the hand of the rotation and not "
            "a magnitude, so anything else is a value nobody measured."
        ) from None
    if sign not in (1, -1):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {RPM_SIGN_VARIABLE} as {sign}, and the sign "
            "of a rotor speed is 1 or -1."
        )
    return sign


#: The decimals a rotor speed derived from an advance ratio is emitted at:
#: the reference tooling wrote four, and the recorded runs turned at that value.
_DERIVED_RPM_DECIMALS = 4


#: The swept axis's own key on a point, which is where a row that writes
#: `ADVANCE_RATIO:sweep` in its flight condition puts the VALUE.
_POINT_ADVANCE_RATIO = "advance_ratio"


def _the_cell_states_both(case: SimCase) -> bool:
    """Say whether the ROW'S CELL states the rotor speed and the advance ratio, and no velocity.

    Read from ``condition_order``, which is the cell's own declared keys in the
    cell's order, so this asks what the ROW wrote rather than what reached
    `variables`: a motion record stating both forms is a different thing and
    keeps the refusal it has always had.
    """
    declared = set(case.condition_order)
    if not {"RPM", "ADVANCE_RATIO"} <= declared:
        return False
    # P0320-D-RIG: WHAT THE CELL WROTE, NOT WHAT THE POINT RESOLVED. At a point
    # the case's flight condition carries the velocity the rig derived from
    # J x (RPM/60) x D, so asking it whether a velocity is there answered yes
    # for every planned point and refused the very row this form exists for.
    return not any(key in declared for key in ("MACH", "TASmps"))


def _stated_rpm(case: SimCase) -> str | None:
    """Resolve the rotor speed this row states, from `variables` or its POINT.

    The same two homes as the advance ratio, and for the same reason: a row
    writing ``RPM:sweep`` in its flight condition puts the VALUE on the point,
    because the held coordinates of a sweep are merged into `variables` and the
    swept one is not. A MOTION RECORD stating its own speed wins over both, and
    it wins here rather than by a rule of its own: the record's variables are
    merged over the row's before this is read.
    """
    stated = _variable(case, RPM_VARIABLE)
    if stated is not None:
        return stated
    value = (getattr(case, "point", None) or {}).get(RPM_VARIABLE)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stated_advance_ratio(case: SimCase) -> str | None:
    """Resolve the advance ratio this row states, from `variables` or its POINT.

    ONE FACT WITH TWO HOMES.
    A row stating `ADVANCE_RATIO:sweep` in its flight condition puts the VALUE
    on the point: the HELD coordinates of a sweep are merged into `variables`
    and the SWEPT one is not, so `variables` carries `ALPHA` and `BETA` and no
    `ADVANCE_RATIO` at all. Both the script emitter and reduction planner
    must read the point's swept value when it is absent from `variables`.

    THE POINT IS CONSULTED ONLY WHEN `variables` STATE NEITHER FORM. A row that
    states `RPM` keeps `RPM`; a motion record carrying its own speed keeps it;
    the two-forms refusal and the sweep-word refusal read `variables` alone and
    fire exactly where they fired before. The narrowness is the point: this
    adds a reading where there was none, and changes none that existed.
    """
    stated = _variable(case, ADVANCE_RATIO_VARIABLE)
    if stated is not None or _variable(case, RPM_VARIABLE) is not None:
        return stated
    value = (getattr(case, "point", None) or {}).get(_POINT_ADVANCE_RATIO)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def rotor_speed(case: SimCase) -> RotorSpeed:
    """Resolve the rotor speed a row states, in either form.

    Parameters
    ----------
    case : SimCase
        The case. It states ``ADVANCE_RATIO`` or ``RPM``, exactly one.
        The ratio form also reads ``RPM_SIGN`` (default 1), the case's
        free-stream velocity, and the rotor diameter carried on the
        case reference.

    Returns
    -------
    RotorSpeed

    Raises
    ------
    CampaignConfigError
        If the row states both forms or neither, except the static-rig
        form, where the row's own cell states ``RPM`` and ``ADVANCE_RATIO``
        and no velocity: the speed is taken and the ratio has already
        fixed the run's velocity. Also if a ratio is stated with no rotor
        diameter on the reference, naming the artifact field to add; or
        if the ratio, the velocity or the diameter is not a positive
        number.
    """
    # THE POINT IS A HOME FOR THIS VALUE TOO, and a swept row's only one.
    # `_stated_advance_ratio` falls back to it when the variables state neither
    # form, so a row writing `ADVANCE_RATIO:sweep` resolves here as it already
    # resolved in the script emitter, which reads the point and writes
    # `SET_MOTION_ROTOR_RPM` from it.
    ratio_text = _stated_advance_ratio(case)
    rpm_text = _stated_rpm(case)
    # READ FROM `variables`, NOT from the fallback: this refusal is about a
    # MOTION RECORD writing the word `sweep`, and a point carries a number.
    for key, text in (
        (ADVANCE_RATIO_VARIABLE, _variable(case, ADVANCE_RATIO_VARIABLE)),
        (RPM_VARIABLE, rpm_text),
    ):
        if isinstance(text, str) and text.strip().casefold() == SWEEP_WORD.casefold():
            # SWEEPING IS THE CONDITION'S JOB (FR-70). A record that writes
            # the word is asking the motion to vary, and a row varies ONE
            # variable, stated once, where every other reader can see it.
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key}: {text.strip()} on a motion record. "
                "Sweeping is stated in FLIGHT_CONDITION, once for the row, and it then "
                "reaches every motion that states no speed of its own; a record states a "
                "VALUE, which is how one rotor holds while another is swept."
            )
    if ratio_text is not None and rpm_text is not None and _the_cell_states_both(case):
        # The speed and the ratio together, with no
        # velocity stated, are the static-rig form. They do not disagree: the
        # ratio fixed the VELOCITY of the run, V = J x (RPM/60) x D, and the
        # rotor turns at the speed the row wrote. So the speed is taken and the
        # ratio is left where it already did its work, one layer above.
        ratio_text = None
    if ratio_text is not None and rpm_text is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states its rotor speed twice: "
            f"{ADVANCE_RATIO_VARIABLE} as {ratio_text!r} and {RPM_VARIABLE} as "
            f"{rpm_text!r}. The rev/min are what the ratio works out to at this run's "
            "velocity, so a second stated form is a second number nobody keeps in "
            f"agreement with the first. Keep {ADVANCE_RATIO_VARIABLE} and let the speed "
            f"be derived, or keep {RPM_VARIABLE} and state the speed directly."
        )
    if ratio_text is None and rpm_text is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states no rotor speed, and a rotary motion turns at "
            f"one. State '{ADVANCE_RATIO_VARIABLE}: <J>', which is resolved as "
            "n = V / (J D) against this run's velocity and the reference rotor "
            f"diameter, or '{RPM_VARIABLE}: <rev/min>' to state the speed itself."
        )

    if ratio_text is None:
        stated = _required_float(
            case, RPM_VARIABLE, quantity="rotor speed", unit="rev/min", text=rpm_text
        )
        # A ROW'S RPM IS A MAGNITUDE. The
        # hand is the reference's, and a row carrying a sign of its own would be
        # a second answer to a question the rotor block already answers.
        if stated < 0.0:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {RPM_VARIABLE} as {stated}, and a row's "
                "rotor speed is a MAGNITUDE: it says how fast, not which way. The hand "
                f"of the rotation is the rotor's {RPM_SIGN_VARIABLE}, declared once in "
                "the reference beside its axis and its origin. Write the speed positive "
                "and set the hand there."
            )
        return RotorSpeed(
            sim_id=case.sim_id,
            stated_form="rpm",
            stated_value=stated,
            # Apply the reference's hand to a stated RPM magnitude, just as to
            # a speed derived from advance ratio.
            rpm=_rpm_sign(case) * stated,
            advance_ratio=None,
            velocity_m_per_s=None,
            diameter_m=None,
        )

    ratio = _required_float(
        case,
        ADVANCE_RATIO_VARIABLE,
        quantity="advance ratio",
        unit="dimensionless",
        text=ratio_text,
    )
    if ratio <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ADVANCE_RATIO_VARIABLE} as {ratio}, and an "
            "advance ratio is positive: it is the axial distance travelled per "
            "revolution over the diameter. The HAND of the rotation is "
            f"{RPM_SIGN_VARIABLE}, which is where a negative sign belongs."
        )
    reference = case.reference
    # THE NAMED ROTOR'S OWN DIAMETER where the row names (or the reference declares) one
    # rotor block; the reference's single top-level diameter only where no block answers.
    block = _rotor_the_row_names(case)
    diameter = (
        block.diameter_m
        if block is not None and block.diameter_m
        else (None if reference is None else reference.rotor_diameter)
    )
    if diameter is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ADVANCE_RATIO_VARIABLE} as {ratio} and its "
            "reference carries no rotor diameter, so the ratio names no rotor "
            "speed: J is a ratio against the diameter and n = V / (J D) cannot be "
            "evaluated without it. Add 'rotor_diameter_m' to the reference "
            "artifact this row's REF code names, beside the other reference lengths."
        )
    velocity = _velocity(case)
    if velocity <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} resolves a free-stream velocity of {velocity} m/s, "
            f"and an advance ratio needs a moving aircraft: J = V / (n D) inverts to "
            "n = V / (J D), which is a stopped rotor at V = 0. A static case states "
            f"{RPM_VARIABLE} directly."
        )
    # n in rev/s is V / (J D); rev/min is sixty times that.
    # Use the reference tooling's four-decimal precision: recorded script
    # 9001 states SET_MOTION_ROTOR_RPM 1 473.1723 0.0 0.0 (RPT-040), whereas
    # the unrounded derivation is 473.17227304. The reference tables were
    # computed at the four-decimal speed. A ten-thousandth of a rev/min is
    # below the solver's resolution.
    rpm = round(60.0 * velocity / (ratio * diameter), _DERIVED_RPM_DECIMALS)
    return RotorSpeed(
        sim_id=case.sim_id,
        stated_form="advance_ratio",
        stated_value=ratio,
        rpm=_rpm_sign(case) * rpm,
        advance_ratio=ratio,
        velocity_m_per_s=velocity,
        diameter_m=diameter,
    )


def _own_speed(case: SimCase, speed: RotorSpeed | None) -> RotorSpeed:
    """Return the speed for this case, refusing one resolved from another.

    A HANDED SPEED ALSO SKIPS EVERY REFUSAL `rotor_speed` MAKES, which is
    the half that matters more than the mix-up: a row stating both
    ADVANCE_RATIO and RPM, or a ratio with no rotor diameter, is
    refused inside `rotor_speed` and builds a clean script when a caller
    supplies a speed instead. Checking the identity is what makes the
    parameter an optimisation rather than a way past the guards.
    """
    if speed is None:
        return rotor_speed(case)
    if speed.sim_id != case.sim_id:
        raise CampaignConfigError(
            f"a rotor speed resolved from case {speed.sim_id!r} was passed for case "
            f"{case.sim_id!r}. A speed carries the row it came from precisely so this "
            "cannot happen quietly: the run would emit a rotor speed and a clock that "
            "agree with each other and with no row."
        )
    if not case.motions:
        # The identity alone does not make a handed speed the row's: resolve
        # the row's own and refuse one that differs, which also applies every
        # refusal `rotor_speed` makes. A row with MOTIONS takes the clock
        # motion's speed, which no flat read reproduces.
        own = rotor_speed(case)
        if own != speed:
            raise CampaignConfigError(
                f"a rotor speed of {speed.rpm:g} rev/min was passed for case "
                f"{case.sim_id!r}, whose row states {own.rpm:g} rev/min "
                f"({own.stated_form}: {own.stated_value:g}). A handed speed must be the "
                "one the row itself resolves to."
            )
    return speed


# --- the tip and helical Mach numbers of a rotor (M1) ----------------

#: The factor from a rotor speed in rev/min, the unit of every speed this
#: package resolves (:attr:`RotorSpeed.rpm`), to its angular rate in rad/s.
RAD_PER_S_PER_REV_PER_MIN = 2.0 * math.pi / 60.0

#: The helical Mach number at and above which ``plan`` names a point: the
#: blade tip meets the flow at the speed of sound or faster.
SONIC_HELICAL_MACH = 1.0


def rotor_mach_numbers(
    *,
    rpm: float,
    diameter_m: float,
    velocity_m_per_s: float,
    sonic_velocity_m_per_s: float,
) -> tuple[float, float]:
    """Return a rotor's tip and helical Mach numbers, ``(M_tip, M_hel)``.

    The one home of both definitions; the plan, the run record and the rotor
    table all call it::

        Omega = 2 pi RPM / 60            (rad/s)
        M_tip = Omega R / a
        M_hel = sqrt(V^2 + (Omega R)^2) / a

    with ``R`` half the rotor diameter, ``V`` the free-stream speed and ``a``
    the speed of sound of the point's resolved flight condition.

    Parameters
    ----------
    rpm : float
        The rotor speed in rev/min. Its sign is the hand of the rotation and
        is not read: both numbers are of the tip SPEED.
    diameter_m : float
        The rotor diameter in m, greater than zero.
    velocity_m_per_s : float
        The free-stream speed in m/s, zero or more.
    sonic_velocity_m_per_s : float
        The speed of sound in m/s, greater than zero.

    Returns
    -------
    tuple of float
        ``(M_tip, M_hel)``.

    Raises
    ------
    CampaignConfigError
        A diameter or a speed of sound that is not a positive finite number,
        or a free-stream speed or rotor speed that is not finite.

    Examples
    --------
    >>> tip, helical = rotor_mach_numbers(
    ...     rpm=3000.0, diameter_m=2.0, velocity_m_per_s=100.0, sonic_velocity_m_per_s=340.0
    ... )
    >>> round(tip, 4), round(helical, 4)
    (0.924, 0.9697)
    """
    for name, value in (
        ("rpm", rpm),
        ("diameter_m", diameter_m),
        ("velocity_m_per_s", velocity_m_per_s),
        ("sonic_velocity_m_per_s", sonic_velocity_m_per_s),
    ):
        if not math.isfinite(value):
            raise CampaignConfigError(
                f"rotor_mach_numbers: {name} = {value!r} is not a finite number"
            )
    if diameter_m <= 0.0:
        raise CampaignConfigError(
            f"rotor_mach_numbers: diameter_m = {diameter_m!r}; a rotor has a size"
        )
    if sonic_velocity_m_per_s <= 0.0:
        raise CampaignConfigError(
            f"rotor_mach_numbers: sonic_velocity_m_per_s = {sonic_velocity_m_per_s!r}; "
            "a speed of sound is positive"
        )
    if velocity_m_per_s < 0.0:
        raise CampaignConfigError(
            f"rotor_mach_numbers: velocity_m_per_s = {velocity_m_per_s!r}; a free-stream "
            "speed is a magnitude, zero or more (the direction is the flow direction's)"
        )
    tip_speed = abs(rpm) * RAD_PER_S_PER_REV_PER_MIN * diameter_m / 2.0
    return (
        tip_speed / sonic_velocity_m_per_s,
        math.hypot(velocity_m_per_s, tip_speed) / sonic_velocity_m_per_s,
    )


def free_stream_direction(case: SimCase) -> tuple[float, float, float]:
    """Return the unit vector of the point's free stream in the body frame.

    ``(cos(alpha) cos(beta), -cos(alpha) sin(beta), sin(alpha))`` for the
    incidence and sideslip the point resolves to (:func:`_angle`), the
    convention every other reader of the free stream in this package uses;
    both zero gives ``+X``.
    """
    return free_stream_direction_at(_angle(case, "alpha"), _angle(case, "beta"))


def free_stream_direction_at(alpha_deg: float, beta_deg: float) -> tuple[float, float, float]:
    """Return the unit free-stream vector for an incidence and sideslip in degrees.

    Parameters
    ----------
    alpha_deg : float
        Incidence angle in degrees.
    beta_deg : float
        Sideslip angle in degrees.

    Returns
    -------
    tuple[float, float, float]
        Unit free-stream vector in reference axes.
    """
    alpha = math.radians(alpha_deg)
    beta = math.radians(beta_deg)
    return (
        math.cos(alpha) * math.cos(beta),
        -math.cos(alpha) * math.sin(beta),
        math.sin(alpha),
    )


def _unit_or_none(vector: tuple[float, float, float] | None) -> tuple[float, float, float] | None:
    """Return ``vector`` scaled to length one, or None where it names no direction."""
    if vector is None:
        return None
    length = math.sqrt(sum(component * component for component in vector))
    if not math.isfinite(length) or length <= 1e-12:
        return None
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def advancing_tip_mach_number(
    *,
    rpm: float,
    diameter_m: float,
    velocity_m_per_s: float,
    sonic_velocity_m_per_s: float,
    flow_direction: tuple[float, float, float] | None = None,
    axis: tuple[float, float, float] | None = None,
) -> tuple[float, bool]:
    """Return a rotor's advancing-tip Mach number and whether its axis was used (FR-1201).

    The sibling of :func:`rotor_mach_numbers`, in the same home::

        M_adv = sqrt((Omega R + V_ip)^2 + V_ax^2) / a

    with ``V_ax`` the free-stream component along the rotor axis and
    ``V_ip = |V - V_ax axis|`` the component in the rotor plane. It equals
    ``M_hel`` in axial flow and ``(Omega R + V) / a`` edgewise. Where the
    flow direction or the axis is not given (the row's rotor axis cannot be
    resolved), it is the edgewise bound ``(Omega R + V) / a``, and the second
    value is False so the plan can say so.

    Parameters
    ----------
    rpm, diameter_m, velocity_m_per_s, sonic_velocity_m_per_s : float
        As for :func:`rotor_mach_numbers`, with the same refusals.
    flow_direction : tuple of float, optional
        The free stream's direction, any non-zero length, in the frame of
        ``axis`` (:func:`free_stream_direction`).
    axis : tuple of float, optional
        The rotor axis, any non-zero length, in the same frame.

    Returns
    -------
    tuple
        ``(M_adv, axis_used)``.

    Raises
    ------
    CampaignConfigError
        As :func:`rotor_mach_numbers`.

    Examples
    --------
    >>> m_adv, used = advancing_tip_mach_number(
    ...     rpm=3000.0, diameter_m=2.0, velocity_m_per_s=100.0, sonic_velocity_m_per_s=340.0,
    ...     flow_direction=(1.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0),
    ... )
    >>> round(m_adv, 4), used
    (1.2181, True)
    """
    tip, _helical = rotor_mach_numbers(
        rpm=rpm,
        diameter_m=diameter_m,
        velocity_m_per_s=velocity_m_per_s,
        sonic_velocity_m_per_s=sonic_velocity_m_per_s,
    )
    tip_speed = tip * sonic_velocity_m_per_s
    unit_axis = _unit_or_none(axis)
    unit_flow = _unit_or_none(flow_direction)
    if unit_axis is None or unit_flow is None:
        return (tip_speed + velocity_m_per_s) / sonic_velocity_m_per_s, False
    axial = velocity_m_per_s * sum(f * a for f, a in zip(unit_flow, unit_axis, strict=True))
    in_plane = math.sqrt(max(velocity_m_per_s**2 - axial**2, 0.0))
    return math.hypot(tip_speed + in_plane, axial) / sonic_velocity_m_per_s, True


@dataclass(frozen=True)
class RotorMach:
    """The tip and helical Mach numbers of one rotor or disc at one point, or why not.

    Attributes
    ----------
    alias : str
        The rotor, by the reference's alias (``ROTOR`` for a row that turns a
        rotor its reference does not declare), or the actuator disc, by the
        name of its reference block.
    rpm : float or None
        The speed in rev/min, signed by the hand, as the run turns it; a
        disc's is its block's ``rpm_sign`` times the speed, the opposite of
        the speed its script hands the solver (FR-331).
    diameter_m : float or None
        The diameter the numbers were taken at: a rotor block's
        ``diameter_m``, else the reference's ``rotor_diameter_m``; a disc's
        twice its ``tip_radius_m``.
    velocity_m_per_s, sonic_velocity_m_per_s : float or None
        The free-stream speed and the speed of sound of the point's
        resolved flight condition.
    tip, helical : float or None
        ``M_tip`` and ``M_hel`` (:func:`rotor_mach_numbers`); None where
        ``note`` says why they are not known.
    advancing : float or None
        ``M_adv`` (:func:`advancing_tip_mach_number`, FR-1201); None where
        ``tip`` is.
    axis_resolved : bool
        False where ``advancing`` is the edgewise bound ``(Omega R + V) / a``
        because the row's rotor axis could not be resolved.
    note : str or None
        Why the two numbers are not known, naming the row; None where they are.
    kind : str
        ``"rotor"`` or ``"actuator"``: which of the two the numbers are of.
    """

    alias: str
    rpm: float | None
    diameter_m: float | None
    velocity_m_per_s: float | None
    sonic_velocity_m_per_s: float | None
    tip: float | None
    helical: float | None
    note: str | None = None
    kind: str = "rotor"
    advancing: float | None = None
    axis_resolved: bool = False

    def record(self) -> dict[str, object]:
        """Return the JSON-ready entry the plan and the run record carry."""
        return {
            "kind": self.kind,
            "rpm": self.rpm,
            "diameter_m": self.diameter_m,
            "velocity_m_per_s": self.velocity_m_per_s,
            "sonic_velocity_m_per_s": self.sonic_velocity_m_per_s,
            "mach_tip": self.tip,
            "mach_helical": self.helical,
            "mach_advancing": self.advancing,
            "mach_advancing_bound": (
                None if self.advancing is None else ("axis" if self.axis_resolved else "edgewise")
            ),
            "note": self.note,
        }


def _states_a_rotor_speed(case: SimCase) -> bool:
    """Say whether a row states a rotor speed: ``RPM`` on the row, its point or a motion."""
    return _stated_rpm(case) is not None or any(RPM_VARIABLE in record for record in case.motions)


# --- PFS-2025.05: the rotor motion, off the row ------------------------------


def _the_aliases_the_row_names(case: SimCase) -> list[str | None]:
    """Return the rotor aliases a sector row names, from its motion records or its variables."""
    aliases = [
        record.get(MOVING_BC_ALIAS_VARIABLE)
        for record in (case.motions or [])
        if record.get(MOVING_BC_ALIAS_VARIABLE)
    ]
    if not aliases:
        alias = _variable(case, MOVING_BC_ALIAS_VARIABLE)
        aliases = [str(alias)] if alias else []
    if not aliases and case.recipe == QSTEADY_ROTOR:
        # A QUASI-STEADY ROW HAS NO MOTION RECORD TO NAME ITS ROTOR: its rotor is the
        # reference's one isolated rotor, which is what the run type already solves.
        try:
            aliases = [_the_isolated_rotor(case).alias]
        except CampaignConfigError:
            aliases = []
    return aliases


def _the_copies_the_sector_stands_for(case: SimCase, script: Script) -> tuple[int | None, str]:
    """Return the copy count a sector row implies, and WHY not (FR-59, FR-61).

    THE COUNT IS THE MESH'S AND IS READ FROM THE MESH. FR-61 draws the
    line and this function stands on it: ``PERIODIC_COPIES`` states what
    the FILE THE ROW OPENS is, a sector of a wheel, while the blade COUNT
    it was also read for belongs to the reference (FR-68). So the count is
    the wheel's blades divided by the blades this file carries, which is
    how many times the slice repeats:

        copies = len(block.families_blades) // (those the geometry carries)

    The reference 91_LIFTER_SECTOR carries LH and LB_1 of a rotor declared with four
    blade families, so it stands for four copies; the same rotor meshed as
    a half, carrying two of them, stands for two. The count therefore needs
    the mesh inventory as well as the reference's full-wheel blade count.

    ONE ROTOR ONLY, and deliberately: a sector is a slice of ONE wheel, so
    a row turning several rotors has no single count and is left to state
    one.

    THE SECOND RETURN IS THE REASON, distinguishing the row shapes that
    return None so the refusal can explain the missing information.
    """
    aliases = _the_aliases_the_row_names(case)
    named = {str(alias).strip().casefold() for alias in aliases}
    if not named:
        if case.recipe == "unsteady_rotor":
            return None, (
                f"Add it to the row's variables, or name the rotor by alias "
                f"({MOVING_BC_ALIAS_VARIABLE}) and let its block's blades say it."
            )
        # The other run types register no MOVING_BC_ALIAS key, so naming it would
        # send the row to a second refusal.
        return None, f"Add {PERIODIC_COPIES_VARIABLE} to the row's variables."
    if len(named) != 1:
        return None, (
            f"This row turns {len(named)} rotors, so there is no single wheel for the "
            "sector to be a slice of; a sector row states one count of its own."
        )
    block = next(
        (rotor for name, rotor in case.rotors.items() if name.casefold() in named),
        None,
    )
    if block is None:
        return None, (
            f"The row names {', '.join(sorted(named))}, which the reference declares as "
            "no rotor, so its blades cannot say the count."
        )
    if not block.families_blades:
        return None, (
            f"The row names {block.alias}, whose reference block lists no "
            "families_blades, so its blades cannot say the count either: add them to "
            "the block, or state the count on the row."
        )
    inventory = {name.casefold() for name in script.entities.labels("boundaries")}
    carried = [name for name in block.families_blades if name.casefold() in inventory]
    if not carried:
        return None, (
            f"The row names {block.alias}, whose blade list "
            f"({', '.join(block.families_blades)}) reaches no boundary of the geometry "
            "this row opens, so the file cannot say how many of itself it stands for. "
            "State the count on the row, or name in the reference the blade families "
            "this mesh actually carries."
        )
    whole, sector = len(block.families_blades), len(carried)
    if whole == sector:
        # A full wheel is not a slice: treating the derived one copy as a sector
        # would initialise the whole mesh as a sector of itself. A half-model row
        # also needs an explicit choice rather than an inferred blade-sector count.
        return None, (
            f"The row names {block.alias} and the geometry carries all "
            f"{whole} of its blade families, so the file is the whole wheel "
            "rather than a slice of it and there is nothing for it to stand "
            f"for {whole} of. State {PERIODIC_COPIES_VARIABLE} on the row if "
            "the periodicity is of something else, such as a half model, or "
            f"write {SYMMETRY_VARIABLE} as the mode that mesh actually is."
        )
    if whole % sector:
        return None, (
            f"The row names {block.alias}, whose reference declares {whole} blade "
            f"families while the geometry carries {sector} of them "
            f"({', '.join(carried)}), and {whole} is not a whole number of {sector}. A "
            "periodic sector repeats an exact number of times, so this pair cannot be "
            "one: state the count on the row."
        )
    return whole // sector, ""


# --- the builders -------------------------------------------------------------


def _angle(case: SimCase, axis: str) -> float:
    """Return the incidence or the sideslip the row states, in degrees (FR-69).

    THE POINT FIRST, THEN THE ROW, THEN ZERO. A swept angle is the point's.
    An unswept angle comes from the row's FLIGHT_CONDITION; an unstated
    angle is zero.

    THE ROW-STATED ANGLE IS USUALLY IN THE POINT ALREADY, and this
    function is what answers when it is not. The point's coordinates are
    run IDENTITY, so a held angle written in FLIGHT_CONDITION joins every
    point of the sweep, and a row spelled `ALPHA:sweep, BETA:0.0` tags its
    points exactly as the paired `AL/BE` row it was upgraded from did (see
    `SweepAxis.held`). What reaches the row and not the point is the
    advance ratio a row holds, and an angle written among the free
    variables rather than in the cell.
    """
    key = ALPHA_VARIABLE if axis == "alpha" else BETA_VARIABLE
    if axis in case.point:
        return _required_float(
            case, key, quantity="flow angle", unit="degrees", text=str(case.point[axis])
        )
    stated = _variable(case, key)
    if stated is None:
        return 0.0
    return _required_float(case, key, quantity="flow angle", unit="degrees", text=stated)


def angles_not_stated(case: SimCase) -> tuple[str, ...]:
    """Return the flow angles a point takes at their 0.0 default (FR-69).

    An angle is stated when the point sweeps it or the row writes it; the
    other is the default, 0.0 degrees, and the plan and the run record say
    so instead of leaving the zero to be read as a choice.

    Parameters
    ----------
    case : SimCase
        The case at one point.

    Returns
    -------
    tuple of str
        ``"ALPHA"`` and/or ``"BETA"``, in that order; empty when both are stated.
    """
    return tuple(
        key
        for axis, key in (("alpha", ALPHA_VARIABLE), ("beta", BETA_VARIABLE))
        if axis not in case.point
        and case.sweep.type not in (axis, "alpha_beta")
        and _variable(case, key) is None
    )


def _same_number(text: str, number: float) -> bool:
    """Whether the cell text reads as the number (an unreadable cell is not the same)."""
    try:
        return math.isclose(float(text), float(number), rel_tol=1e-9)
    except ValueError:
        return False


def _velocity(case: SimCase) -> float:
    if case.velocity is not None:
        stated = _variable(case, VELOCITY_VARIABLE)
        if stated is not None and not _same_number(stated, case.velocity):
            # X-F-1157: two different speeds are refused, not resolved by precedence.
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the VELOCITY cell ({stated}) contradicts the velocity "
                f"the row already resolves, {case.velocity:g} m/s, through FLIGHT_CONDITION "
                "(TASmps or MACH) or its resolved flow state. Remove VELOCITY from "
                "VAR_NAMES_VALUES and state the velocity in FLIGHT_CONDITION."
            )
        return float(case.velocity)
    return _required_float(case, VELOCITY_VARIABLE, quantity="free-stream velocity", unit="m/s")


#: THE RADICAL OF A ROTOR THAT HAS NO ALIAS. Only one path produces one: a
#: matrix converted with no workspace, where `to_campaign` reads the row and
#: never an artifact, so there is no block to take a name from. It keeps the
#: shape every other rotor frame name has rather than reviving the
#: package-level PROP_MRP, which named one propulsor because a reference
#: described one.
UNNAMED_ROTOR_RADICAL = "ROTOR"


def _uses_letter_frame(rotor: RotorBlock) -> bool:
    """Keep a letter basis only when its native radial datum is the declared one.

    PFS-2119.024, licensed/EVIDENCE-5.md batch 8: the letter path ignores
    blade1.zero. A different datum therefore needs the shaft-aligned basis.
    """
    return (
        isinstance(rotor.axis, str)
        and rotor.blade1.zero.lstrip("+") == {"X": "Z", "Y": "X", "Z": "X"}[rotor.axis]
    )


def _rotor_frame_axis(rotor: RotorBlock) -> str:
    """Return the shaft axis in the basis selected for this rotor."""
    return str(rotor.axis) if _uses_letter_frame(rotor) else "Z"


def _the_rotor_a_flat_row_turns(case: SimCase) -> RotorBlock | None:
    """Return the one rotor a row with no MOTIONS list turns, or None.

    A row that states MOTIONS says which rotor each record moves and never
    reaches here. A row without one has to be told, and the reference is
    what tells it: exactly one rotor block means exactly one answer.

    IT ANSWERS None RATHER THAN RAISING when the reference declares
    several. Every run type asks this, including the ones that turn
    nothing, so a refusal here fired on a steady row whose reference
    happened to describe a twin. The refusal belongs to the run that
    actually needs a hub, and :func:`_refuse_an_unanswered_hub` is where
    it lives.
    """
    # `case.rotors`, NOT `case.reference`. The blocks are lifted onto the
    # case when the matrix resolves, and a case built directly carries them
    # with no reference beside them; asking for the reference here made the
    # helper answer None for every hand-built rotor case, which is a guard
    # that refuses what it was written to accept.
    if len(case.rotors) != 1:
        return None
    return next(iter(case.rotors.values()))


def row_ncpus(case: SimCase, from_setup: int | None) -> int | None:
    """Resolve the processor count from the row (FR-93).

    ONE NUMBER FOR EVERY PLATFORM. It reaches
    ``SET_MAX_PARALLEL_THREADS`` as the solver's thread count and, on a
    submitting run, the scheduler's ``ncpus``. They cannot disagree
    because there is only one of them.

    ``from_setup`` is the preset's count. A row that states nothing inherits
    it; a row that states a count overrides it. The upgrade moves
    it into the column, which is why this reads the row FIRST and the
    preset second rather than the other way round.
    """
    stated = _variable(case, NCPUS_VARIABLE)
    if stated is None:
        return from_setup
    # READ AS EVERY COUNT OF A ROW IS READ: 4 or 4.0, and never 4.5.
    value = _required_int(case, NCPUS_VARIABLE, quantity="processor count", unit="processors")
    if value < 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {NCPUS_VARIABLE}: {value}, and a run needs at "
            "least one processor."
        )
    return value


def row_symmetry_loads(case: SimCase, from_setup: bool | None) -> bool | None:
    """Resolve the symmetry-loads flag: the ROW's when it states one (FR-66).

    Whether the solver reports the loads of the
    meshed SECTOR or of the whole wheel is a per-row choice, because one
    preset serves a sector row and a full-wheel row. A row stating it
    OVERRIDES the preset and warns naming the case, both values and the one used;
    a row stating nothing inherits silently.

    The first decision that hour was to refuse both stating it, as the rotor
    speed is refused; it was changed the same hour, and the warning is what
    keeps the override from being silent.

    Parameters
    ----------
    case : SimCase
        The row's case; its symmetry-loads variable is read.
    from_setup : bool or None
        The value the setup preset states, or None when it states none.

    Returns
    -------
    bool or None
        The row's value when it states one, else ``from_setup``.

    Raises
    ------
    CampaignConfigError
        If the row states a value that is none of true, false, ENABLE or
        DISABLE.

    Warns
    -----
    PyflightstreamWarning
        If the row's value differs from the preset's, naming both; the row
        wins.
    """
    stated = _variable(case, SYMMETRY_LOADS_VARIABLE)
    if stated is None:
        return from_setup
    word = str(stated).strip().upper()
    # THE ROW'S OWN VOCABULARY, which is the cell a user types: TRUE and
    # FALSE as the presets write them, and the solver's own ENABLE and
    # DISABLE, which is what `resolve_toggle` accepts one layer down.
    value = {"TRUE": True, "FALSE": False, "ENABLE": True, "DISABLE": False}.get(word)
    if value is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {SYMMETRY_LOADS_VARIABLE}: {stated!r}, which is "
            "not a yes or a no. Write true or false, or the solver's own ENABLE or "
            "DISABLE. True means the solver reports the loads of the whole wheel; false "
            "means the loads of the sector that was meshed."
        )
    if from_setup is not None and from_setup != value:
        warn(
            f"case {case.sim_id!r} states {SYMMETRY_LOADS_VARIABLE}: {value} and its setup "
            f"preset states {from_setup}. The ROW wins, and the run reports the loads of "
            f"{'the whole wheel' if value else 'the meshed sector'}.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return value


def row_solver_setting(case: SimCase, key: str) -> tuple[int | bool | None, bool]:
    """Return a solver setting and whether an exact, nonblank row key supplied it.

    Inspection uses the builder's parsers without repeating its override
    vocabulary or emitting the builder's symmetry conflict warning.
    """
    if key == "max_threads":
        return row_ncpus(case, case.solver.max_threads), _variable(case, NCPUS_VARIABLE) is not None
    if key == "symmetry_loads":
        stated = _variable(case, SYMMETRY_LOADS_VARIABLE) is not None
        return row_symmetry_loads(case, None if stated else case.solver.symmetry_loads), stated
    raise ValueError(f"unknown row solver setting {key!r}; use max_threads or symmetry_loads")


def _stated_rate(case: SimCase, key: str) -> float | None:
    """Return one body rate this row states, from `variables` or its POINT."""
    stated = _variable(case, key)
    if stated is None:
        value = (getattr(case, "point", None) or {}).get(key)
        stated = None if value is None else str(value)
    if stated is None:
        return None
    # THROUGH THE ONE READER, so a NaN rate is refused here: it compared
    # unequal to zero and turned the free stream at a rate of NaN.
    return _required_float(case, key, quantity="body rate", unit="deg/s", text=stated)


def _turning_rate(case: SimCase) -> tuple[str, str, float] | None:
    """Return the (key, axis name, deg/s) this row turns the free stream by, or None.

    A row states at most one non-zero rate: the matrix reader refuses two where
    the cell is read, and this refuses them again for a case authored in
    Python, which reaches no reader.
    """
    turning: list[tuple[str, str, float]] = [
        (key, axis, rate)
        for key, axis in RATE_VARIABLES
        if (rate := _stated_rate(case, key)) is not None and rate != 0.0
    ]
    if not turning:
        return None
    if len(turning) > 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {len(turning)} non-zero body rates "
            f"({', '.join(key for key, _, _ in turning)}), and a rotating free stream "
            "turns about ONE axis at one speed. State one rate, and write the others as 0."
        )
    return turning[0]


def _the_names_a_rotor_answers_to(case: SimCase) -> dict[str, list[str]]:
    """Return the setup's aliases with each rotor's own name added to them.

    A ROTOR'S NAME IS AN ALIAS FOR ITS OWN FAMILIES, which is FR-65's
    sentence "a rotor name in that set is its own union" written where
    both readers can use it. The reference `lifters = ["LIFT_L1", "LIFT_L2"]` lists
    ROTORS rather than families, which is the natural way to write a group
    of rotors. Expanding each name to its own families lets those members
    resolve through the shared alias table.

    ONE MAP FOR BOTH PATHS, deliberately. The expanding path and the
    common-frame path read the same words out of the same file, and the
    first fix gave the vocabulary to the expanding one alone: an entry
    written `frame = "MRP", families = ["lifters", "PUSHER"]`, which is
    how the total of the rotors in the moment frame is asked for, then
    selected NOTHING and warned that the geometry carries no family of it.

    The reference table takes precedence, so a study that gives one of these
    names a meaning of its own keeps it. The map is built in the cases layer
    (:func:`pyflightstream.cases._skipped_families.names_a_row_can_cite`), so
    the study vocabulary of FR-435 reads the same names.
    """
    return names_a_row_can_cite(case)


def _point_from_metres(
    case: SimCase, script: Script, point: tuple[float, float, float], what: str
) -> tuple[float, float, float]:
    """Convert a declared physical point once before native frame placement."""
    factor = _from_metres(case, script, what)
    return point[0] * factor, point[1] * factor, point[2] * factor


def _from_metres(case: SimCase, script: Script, what: str) -> float:
    """Return the factor that writes a length in metres in the simulation's unit (G05, G06).

    The disc's and the section's lengths are stated in metres, and their
    commands carry no unit: the solver reads them in the SIMULATION's length
    unit, which an opened saved simulation keeps from its save. The unit is
    taken, in this order:

    * the unit THIS SCRIPT set, which the phase order puts after the open
      (:attr:`~pyflightstream.script.Script.simulation_length_unit`): the
      metres a raw mesh is set to after its import, or a unit a setup line
      states;
    * else, on a saved simulation, the unit it was saved in, as far as
      :func:`pyflightstream._fsm.saved_length_unit` reads it: metres for the
      head every save read carries, and refused for any other;
    * else nothing states a unit (a case that opens nothing, or a placeholder
      with no global block, which no solver save lacks), and the lengths are
      written as stated, as such a file's boundary inventory is left
      undeclared.

    The conversion is the package's one table (:mod:`pyflightstream._lengths`),
    the table the trailing-edge node file is converted with.

    Raises
    ------
    CampaignConfigError
        The saved geometry cannot be read; the filesystem cause is retained.
        Naming ``what``: the saved simulation's unit is not one this package
        has read, or the script set a unit that names no scale (OTHER).
    """
    unit = script.simulation_length_unit
    geometry = case.geometry
    if (
        unit is None
        and geometry is not None
        and PurePath(str(geometry)).suffix.lower() == SIMULATION_SUFFIX
    ):
        try:
            unit = saved_length_unit(geometry)
        except MeshReadError as error:
            if isinstance(error.__cause__, OSError):
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: the saved geometry {str(geometry)!r} "
                    f"could not be read: {error}. Restore the file or correct its path."
                ) from error
            raise CampaignConfigError(
                f"case {case.sim_id!r}: {what} are in metres, and the solver reads them in "
                f"the simulation's length unit, which this saved simulation does not let the "
                f"package know: {error}. State the unit it was saved in after the open, the "
                "row's RAW: {COMMAND: SET_SIMULATION_LENGTH_UNITS <unit> / BEFORE: setup} or "
                "the same line in its setup's [[raw]], and the lengths are converted into it."
            ) from error
    if unit is not None and script.simulation_length_unit is None:
        script.record_opened_length_unit(unit)
    if unit is None:
        return 1.0
    factor = scale("METER", unit)
    if factor is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {what} are in metres, and this script sets the "
            f"simulation's length unit to {unit!r}, which names no scale, so no metre can be "
            "written in it. Set a unit with a scale."
        )
    return factor


#: Archive folder naming belongs to workspace. A continuation feature in
#: cases must receive the folder name from the run layer rather than define
#: a second constant or import upward from workspace.


@dataclass(frozen=True)
class RestartRequest:
    """What a row asks for when it continues a run the clock stopped.

    Attributes
    ----------
    form : str
        One of :data:`RESTART_FORMS`.
    value : float or None
        The number of steps or revolutions to add. None for
        ``FINISH_PENDING``, which asks for what the row originally stated
        and therefore carries no number of its own.
    """

    form: str
    value: float | None


def parse_restart(case: SimCase) -> RestartRequest | None:
    """Read the row's RESTART cell, or None where it states none (FR-96).

    ``RESTART: {FINISH_PENDING}``, ``RESTART: {ADDITIONAL_ITERS=120}`` or
    ``RESTART: {ADDITIONAL_REVS=2}``. The braces are the row's own record
    syntax and the form inside is one of three words; anything else is
    refused NAMING THE THREE, because a misspelt continuation that planned
    READY would spend a seat re-running a point that was nearly done.
    """
    stated = case.variables.get(RESTART_VARIABLE)
    if stated is None:
        return None
    text = str(stated).strip()
    if not (text.startswith("{") and text.endswith("}")):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {RESTART_VARIABLE}: {stated!r}, which is not a "
            f"brace-closed record. Write one of "
            f"{{{RESTART_FINISH_PENDING}}}, {{{RESTART_ADDITIONAL_ITERS}=<n>}} or "
            f"{{{RESTART_ADDITIONAL_REVS}=<n>}}."
        )
    body = text[1:-1].strip()
    name, sep, raw = body.partition("=")
    form = name.strip().upper()
    if form not in RESTART_FORMS:
        raise CampaignConfigError(
            f"case {case.sim_id!r} asks {RESTART_VARIABLE} to do {form!r}, which is not "
            f"one of {', '.join(RESTART_FORMS)}."
        )
    if form == RESTART_FINISH_PENDING:
        if sep:
            raise CampaignConfigError(
                f"case {case.sim_id!r} gives {RESTART_FINISH_PENDING} a value of "
                f"{raw.strip()!r}. It asks for what the row already stated and takes no "
                "number; the two that do are "
                f"{RESTART_ADDITIONAL_ITERS} and {RESTART_ADDITIONAL_REVS}."
            )
        return RestartRequest(form=form, value=None)
    if not sep:
        raise CampaignConfigError(
            f"case {case.sim_id!r} asks for {form} and states no number. Write "
            f"{{{form}=<n>}}: how many more to run is the whole of what it says."
        )
    # THROUGH THE ONE READER: a NaN or an infinity passed `value <= 0` and
    # died later as a bare ValueError or OverflowError, and a step count is
    # a count, so ADDITIONAL_ITERS=0.5 is refused rather than run as zero.
    value: float
    if form == RESTART_ADDITIONAL_ITERS:
        value = _required_int(
            case, RESTART_VARIABLE, quantity=f"{form} step count", unit="steps", text=raw.strip()
        )
    else:
        value = _required_float(
            case, RESTART_VARIABLE, quantity=f"{form} count", unit="revolutions", text=raw.strip()
        )
    if value <= 0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} asks for {form}={value:g}, and a continuation that "
            "adds nothing is a run that need not happen."
        )
    return RestartRequest(form=form, value=value)


def restart_iterations(request: RestartRequest, record: Mapping[str, object]) -> int:
    """How many time steps the continuation runs, from the record it continues.

    FINISH_PENDING SUBTRACTS, which is why a WALLTIME_REACHED record must
    say where it stopped: what remains is what the row asked for minus what
    the earlier run reached. A record that cannot say is refused here
    rather than silently re-running the whole thing.

    AN ABSENT ``stopped_at`` IS NOT ZERO. ``stopped_at`` is written by the
    WALL CLOCK, and :data:`~pyflightstream.run.CONTINUABLE` also admits
    ``COMPLETED_MAX_ITER``, which never carries it. Treating absence as zero
    would repeat all requested steps from an already advanced saved state.
    This state is reachable from one cell,
    because a row whose post-processing artifact turns the log off has no
    residual history and is therefore recorded COMPLETED_MAX_ITER rather than
    CONVERGED. FINISH_PENDING therefore requires a recorded stopped step.
    """
    stopped = cast(StoppedStepRecord | None, record.get("stopped_at"))
    reached: int | None = None
    if isinstance(stopped, Mapping):
        step = stopped.get("step")
        if step is not None:
            reached = int(step)
    if request.form == RESTART_FINISH_PENDING and reached is None:
        raise CampaignConfigError(
            f"{RESTART_FINISH_PENDING} subtracts what the earlier run reached from what the row "
            "asked for, and the record it continues does not say where it stopped. Only a run "
            "the WALL CLOCK stopped records that; a run recorded at its iteration limit reached "
            "everything it was asked for, so there is nothing pending to finish. Treating the "
            "absence as zero would re-march the whole history and spend a seat doing it. State "
            f"{RESTART_ADDITIONAL_ITERS} or {RESTART_ADDITIONAL_REVS}, which say outright how "
            "much further to go."
        )
    reached = reached or 0
    if request.form == RESTART_FINISH_PENDING:
        window = cast(ExportThresholdRecord | None, record.get("export_window"))
        asked = 0
        if isinstance(window, Mapping):
            asked = int(window.get("time_iterations") or 0)
        if not asked:
            raise CampaignConfigError(
                f"{RESTART_FINISH_PENDING} needs to know what the row originally asked "
                "for, and the record it continues does not say how many time steps that "
                f"was. State {RESTART_ADDITIONAL_ITERS} or {RESTART_ADDITIONAL_REVS} "
                "instead, which say it outright."
            )
        remaining = asked - reached
        if remaining <= 0:
            raise CampaignConfigError(
                f"{RESTART_FINISH_PENDING} has nothing to finish: the run reached step "
                f"{reached} of the {asked} it asked for."
            )
        return remaining
    if request.form == RESTART_ADDITIONAL_ITERS:
        return int(request.value or 0)
    # ADDITIONAL_REVS, turned into steps by the clock the row already states.
    window = cast(ExportThresholdRecord | None, record.get("export_window"))
    step_deg = None
    if isinstance(window, Mapping):
        step_deg = window.get("step_deg")
    if not step_deg:
        raise CampaignConfigError(
            f"{RESTART_ADDITIONAL_REVS} counts revolutions and the record it continues "
            "states no azimuthal step, so there is no arithmetic from one to the other. "
            f"State {RESTART_ADDITIONAL_ITERS} instead."
        )
    # Rounded to nine decimals before the ceiling, as the wake conversion is,
    # so float noise on a whole number of steps does not add one.
    return int(math.ceil(round(float(request.value or 0) * 360.0 / float(step_deg), 9)))


def continuation_of(case: SimCase) -> tuple[str, int] | None:
    """Return the saved simulation and the step count a continuation runs, or None.

    None where the row states no RESTART, which is every ordinary row.
    """
    request = parse_restart(case)
    if request is None:
        return None
    saved = case.variables.get(RESTART_FROM_VARIABLE)
    iterations = case.variables.get(RESTART_ITERATIONS_VARIABLE)
    if not saved or iterations is None or iterations == "":
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {RESTART_VARIABLE}: {{{request.form}"
            + (f"={request.value:g}" if request.value is not None else "")
            + "}, and nothing resolved the run it continues. A continuation needs a "
            "recorded run that STOPPED, because the saved simulation it reopens and "
            "the steps it still owes both come from that record and not from the row. "
            "Run the row once and let the wall clock stop it, or remove the "
            f"{RESTART_VARIABLE} key to march it from the start."
        )
    return str(saved), int(float(str(iterations)))


def _rotor_of(case: SimCase, record: Mapping[str, str]) -> RotorBlock | None:
    """Return the rotor a motion record names by alias, or None when it names none.

    A record citing a word the reference does not declare as a rotor is
    refused here rather than at the boundary resolver, because the
    resolver's message would be about a mesh family and the mistake is
    about a rotor.
    """
    alias = record.get(MOVING_BC_ALIAS_VARIABLE)
    if alias is None:
        return None
    token = str(alias).strip()
    rotor = case.rotors.get(token) or next(
        (block for name, block in case.rotors.items() if name.casefold() == token.casefold()),
        None,
    )
    if rotor is None:
        declared = ", ".join(sorted(case.rotors)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {MOVING_BC_ALIAS_VARIABLE}: {token}, and the "
            f"reference artifact declares no rotor of that name. The rotors it declares "
            f"are {declared}. A rotor is a block of the reference whose kind is rotor, "
            "and the block's name is the word a row moves."
        )
    return rotor


# --- the quasi-steady rotor -----------------------------------------


def qsteady_case_kind(case: SimCase) -> str:
    """Return which quasi-steady case a ``qsteady_rotor`` row is: ``"sector"`` or ``"wheel"``.

    THE ROW'S SYMMETRY DECIDES, because it states what was meshed. ``PERIODIC``
    is a sector, one blade standing for the wheel, solved once, steady, in a
    free stream turning at the rotor's speed. No symmetry (``NONE``, or none
    stated) is the wheel, every blade meshed.

    Raises
    ------
    CampaignConfigError
        If the symmetry is ``MIRROR``, or any other: a rotor turning about its shaft is
        not its own mirror image, so a mirrored rotor is neither case.

    Parameters
    ----------
    case : SimCase
        The ``qsteady_rotor`` row's case; its symmetry variable is read.

    Returns
    -------
    str
        ``"sector"`` for ``PERIODIC``, ``"wheel"`` for ``NONE`` or no symmetry.
    """
    stated = _variable(case, SYMMETRY_VARIABLE)
    mode = "NONE" if stated is None else str(stated).strip().upper()
    if mode == "PERIODIC":
        return "sector"
    if mode == "NONE":
        return "wheel"
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} and states "
        f"{SYMMETRY_VARIABLE} {mode}. The quasi-steady rotor solves either a periodic "
        f"sector ({SYMMETRY_VARIABLE} PERIODIC, one blade standing for the wheel) or the "
        f"whole wheel (no {SYMMETRY_VARIABLE}); a turning rotor is not its own mirror image, "
        "so a mirrored one is neither."
    )


#: The sentence every refusal of a row that is not an isolated rotor ends on.
_ONLY_AN_ISOLATED_ROTOR = (
    "The quasi-steady rotor is valid ONLY for an isolated, axisymmetric rotor: the blades "
    "are held still and the rotation is carried by the free stream, which is the same "
    "flow only where nothing else is in it and every blade is alike. A rotor installed "
    "on an airframe, or beside another body, runs as unsteady_rotor."
)


def _the_isolated_rotor(case: SimCase) -> RotorBlock:
    """Return the one rotor a quasi-steady row solves, refusing a row that is not one.

    THE CRITERION, DETECTABLE BEFORE ANY LINE IS WRITTEN: the reference
    declares exactly one rotor block; the row turns no second rotor
    (``MOTIONS``), loads no actuator disc and turns the free stream by no body
    rate, since the free stream's one rotation is the rotor's. That no surface
    of the opened geometry lies outside the rotor is checked once the geometry
    is open (:func:`_refuse_what_is_not_the_rotor`). Whether the blades are
    alike is the user's to know: the mesh is not compared blade by blade.
    """
    if len(case.rotors) != 1:
        declared = ", ".join(sorted(case.rotors)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} and its reference "
            f"declares {len(case.rotors)} rotor block(s) ({declared}); it must declare "
            f"exactly one. {_ONLY_AN_ISOLATED_ROTOR}"
        )
    if case.motions:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} and states "
            f"{MOTIONS_VARIABLE}; the quasi-steady rotor moves nothing, it turns the free "
            f"stream. State the speed as RPM in the row. {_ONLY_AN_ISOLATED_ROTOR}"
        )
    if _variable(case, ACTUATOR_VARIABLE) is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} and loads the actuator "
            f"disc {_variable(case, ACTUATOR_VARIABLE)!r}, a second body in the flow. "
            f"{_ONLY_AN_ISOLATED_ROTOR}"
        )
    if case.sweep.type in {key for key, _ in RATE_VARIABLES} or _turning_rate(case) is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} and turns the free stream "
            "by a body rate. A run has one SET_FREESTREAM, and on this run type it turns at the "
            "rotor's speed about the rotor's shaft; write the body rates as 0."
        )
    return next(iter(case.rotors.values()))


def _qsteady_speed(case: SimCase, rotor: RotorBlock) -> RotorSpeed:
    """Resolve the row's speed signed by the HAND of the one rotor it solves.

    A quasi-steady row names its rotor nowhere, because the reference declares
    one; the speed resolver reads the hand of the block a row names, so it is
    asked through a view naming that block by its alias, the spelling a flat
    rotor row uses (:func:`_rotor_the_row_names`). Without it the row's number
    turned right-handed whatever the block declared.
    """
    update: dict[str, object] = {
        "variables": {**case.variables, MOVING_BC_ALIAS_VARIABLE: rotor.alias}
    }
    # THE DIAMETER IS THIS ROTOR'S (P0310-J-OWN-DIAMETER), as an unsteady rotor
    # row resolves it (:func:`_motion_view`): J is a ratio against the diameter of the
    # rotor that turns, not the reference's single top-level rotor_diameter_m.
    if case.reference is not None:
        update["reference"] = case.reference.model_copy(update={"rotor_diameter": rotor.diameter_m})
    view = case.model_copy(update=update)
    return rotor_speed(view)


def _require_the_averaging_window(case: SimCase, name: str) -> None:
    """Refuse an unsteady row that states no averaging window.

    The definitions page states it: the window lives on the matrix and is a
    mandatory input. Refuse its absence before a run so post-processing
    cannot treat the last time step as a steady polar or choose an unstated
    averaging window.

    ONLY A NEW PLAN IS REFUSED. A record already written without a window is never
    refused at post: it is averaged over the window the run defaulted to, and the
    post stage says which.
    """
    _refuse_retired_window_keys(case)
    revs = _variable(case, LAST_REVS_AVG_VARIABLE)
    iters = _variable(case, LAST_ITERS_AVG_VARIABLE)
    # THE VALUE IS READ HERE TOO, and not only its presence: a zero, a text or
    # both keys planned READY and failed when the run built the point record,
    # where the window is first read (`_reductions._averaging_window`).
    if revs is not None and iters is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states both {LAST_REVS_AVG_VARIABLE} = {revs} and "
            f"{LAST_ITERS_AVG_VARIABLE} = {iters}, and they are two ways to say one "
            "window. State the revolutions on a row that turns a rotor and the "
            "iterations on one that does not."
        )
    if revs is not None:
        turns = _required_float(
            case, LAST_REVS_AVG_VARIABLE, quantity="averaging window", unit="revolutions"
        )
        if turns <= 0.0:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {LAST_REVS_AVG_VARIABLE} = {revs}, and an "
                "averaging window is a positive number of revolutions."
            )
        return
    if iters is not None:
        steps = _required_int(
            case, LAST_ITERS_AVG_VARIABLE, quantity="averaging window", unit="iterations"
        )
        if steps < 1:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {LAST_ITERS_AVG_VARIABLE} = {iters}, and an "
                "averaging window is at least one solver step."
            )
        return
    key, example, other = (
        (LAST_REVS_AVG_VARIABLE, "0.5' averages the last half revolution", LAST_ITERS_AVG_VARIABLE)
        if name == "unsteady_rotor"
        else (
            LAST_ITERS_AVG_VARIABLE,
            "100' averages the last hundred steps",
            LAST_REVS_AVG_VARIABLE,
        )
    )
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the run type {name} and states no {key}. An unsteady "
        "point's polar, its time average and its per-blade table are all averaged over that "
        f"window, so the row must say it: '{key}: {example}. "
        f"(A row that turns {'no' if name == 'unsteady_rotor' else 'a'} rotor "
        f"states {other} instead.)"
    )


def _refuse_rotor_shedding(case: SimCase) -> None:
    stated = _variable(case, ROTOR_SHEDDING_VARIABLE)
    if stated is not None:
        # Names the case (its sim_id IS the matrix POL) and the key, and says
        # the fix, like every sibling refusal of a row.
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ROTOR_SHEDDING_VARIABLE} as {stated!r}, and "
            "every matrix workflow refuses it: no workflow command applies the "
            "wake direction of a relaxed trailing edge, so the run would shed a wake the "
            f"row did not ask for. Remove {ROTOR_SHEDDING_VARIABLE} from the row. "
            "CCS_SHEDDING controls the shedding digit on the CCS file-import route; "
            "it is not a general rotor wake-direction switch. From Python, "
            "rotor_relaxed_trailing_edges sets the direction in the specifications of "
            "the component definition."
        )


def _refuse_unregistered_keys(case: SimCase, name: str) -> None:
    """Refuse a row stating a key the run type does not register.

    PFS-2008.02.01: refuse keys the script does not carry before spending
    a solver seat. The refusal names the case (its ``sim_id`` is
    the matrix POL), the run type, every key outside the vocabulary with
    the run types that DO read it, and the keys this run type registers.

    CALLED BY EACH BUILDER AFTER ITS OWN REFUSALS AND BEFORE ITS FIRST
    EMISSION, not by :func:`build_script` ahead of the builder, and the
    placement is the point: a rotor key on the run type that turns
    nothing, or an export threshold on the run type with no time loop,
    is refused by the builder's own sentence, which says WHY the key
    cannot be honored there; this check is the general rule behind
    those sentences and catches what they do not name.

    A row selected through its RECIPE keeps its keys: a LEGACY row whose
    RECIPE code maps to a run type, or a case authored in Python naming
    the type as its recipe, is the recipe path, and the recipe is the
    reader of its keys (design 68). The
    converter's own ``matrix_`` keys and the workspace's
    ``ROTOR_ORIGIN_POINT`` are not the row's and are left alone.
    """
    _refuse_rotor_shedding(case)
    if _workflow_cell(case) is None:
        return
    workflow = WORKFLOWS[name]
    # A FLAG'S OWN WORD IS A KEY THE ROW MAY STATE (PFS-2035.20). The
    # setup declared it, so it is registered by declaration rather than by
    # the run type's table, and refusing it here would refuse the one key
    # the preset just said the row could write.
    declared = {flag.name.strip().casefold() for flag in case.flags}
    for port in case.solver.ports:
        for variable in (port.velocity_variable, port.profile_variable):
            if variable is not None:
                declared.add(variable.casefold())
    # The continuation facts (RESTART_FROM, RESTART_ITERATIONS and the step
    # offset) are set on the point case by the run layer from the stopped
    # record, never by the row, so they are not the row's keys either.
    stated = sorted(
        key
        for key in case.variables
        if not key.startswith(CONVERTER_PREFIX)
        and key != ROTOR_ORIGIN_POINT_KEY
        and key not in RESERVED_CONTINUATION_VARIABLES
        and key not in workflow.keys
        and key.strip().casefold() not in declared
    )
    if not stated:
        return
    described = []
    for key in stated:
        readers = [name for name, other in WORKFLOWS.items() if key in other.keys]
        described.append(
            f"{key} (a key of {', '.join(readers)})" if readers else f"{key} (a key of no run type)"
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the run type {workflow.name!r} and states "
        f"{', '.join(described)}, which that run type does not register. A key nothing "
        "reads would change nothing about the run while reading as though it had, so it "
        f"is refused rather than ignored. The keys {workflow.name!r} registers are: "
        f"{', '.join(sorted(workflow.keys))}. A LEGACY row keeps its own keys, because its "
        "RECIPE is their reader; docs/workspace-and-workflows.md says what each key means."
    )
