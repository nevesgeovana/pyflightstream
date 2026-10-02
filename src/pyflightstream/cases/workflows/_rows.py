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
    NoReturn,
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
from pyflightstream.script import (
    Script,
    ScriptReferenceError,
)

from ._conventions import (
    WORKFLOWS,
    _workflow_cell,
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
    WALLTIME_BEST,
    WALLTIME_MARGIN_DEFAULT_S,
    WALLTIME_UNITS,
    WALLTIME_UNITS_GLOSS,
    WALLTIME_VARIABLE,
    _refuse_retired_window_keys,
)

# --- reading the row ----------------------------------------------------------


def _variable(case: SimCase, key: str) -> str | None:
    value = case.variables.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_float(
    case: SimCase, key: str, *, quantity: str, unit: str, text: str | None = None
) -> float:
    """One numeric case variable, refused by CASE and KEY rather than by command.

    ``text`` is for a caller that has ALREADY resolved the value from somewhere
    other than ``variables``, which today means the advance ratio a swept row
    puts on its POINT. It exists so that the conversion,
    the not-a-number refusal and the non-finite refusal keep ONE home: the first
    fix for that incident hand-rolled a second conversion beside the fallback
    and silently dropped the non-finite half, which two existing cases caught.
    """
    if text is None:
        text = _variable(case, key)
    if text is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares no {key}, and the run type it names needs "
            f"the {quantity} in {unit}. Add it to the row's variables as "
            f"'{key}: <value>'."
        )
    try:
        value = float(text)
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {text!r}, which is not a number. "
            f"It is the {quantity} in {unit}. Matrix variables arrive as text, so the "
            "conversion happens here rather than at the command, where the refusal "
            "would name only the command and not the cell you typed."
        ) from None
    # NAN AND INFINITY ARE REFUSED HERE, and this is the one place every
    # numeric cell of every rotor row passes through, which is why the
    # check lives here rather than beside each bound.
    #
    # `float("nan")` succeeds, so the conversion above lets it past, and
    # then EVERY COMPARISON AGAINST IT IS FALSE: a NaN advance ratio
    # passes a `<= 0` guard, resolves a NaN rotor speed, and reaches the
    # command layer; a NaN azimuthal step passes its range guard and dies
    # in `int(round(...))` with a bare ValueError naming neither the case
    # nor the key. This package already recorded that class once, on the
    # convergence threshold (PYFS-016), and answered it there with
    # `allow_inf_nan=False`. These keys arrive as TEXT and never touch
    # that model, so they needed their own.
    if not math.isfinite(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {text!r}, which is not a finite "
            f"number. It is the {quantity} in {unit}, and a value that is NaN or "
            "infinite compares false against every bound, so it would pass each check "
            "below and be emitted, or fail much later where the refusal could name "
            "neither this case nor this key."
        )
    return value


def _required_int(case: SimCase, key: str, *, quantity: str, unit: str) -> int:
    value = _required_float(case, key, quantity=quantity, unit=unit)
    if value != int(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {value!r}, and the {quantity} is a "
            f"count in {unit}, which has no fractional part."
        )
    return int(value)


# --- the rotor speed, and the clock it sets ----------------------------------
#
# TWO DERIVATIONS THAT WERE INPUTS, and the reason they are one section.
# A rotor study is designed in an advance ratio and an azimuthal step;
# the rev/min and the seconds are what those work out to at the run's own
# velocity. Until this release the matrix took the DERIVED numbers, so a
# row carried three constants (rpm, delta_time, time_iterations) that a
# reader had to divide back into the two decisions behind them, and a
# change of flight condition left all three silently meaning something
# else. Both forms are kept: a matrix written in the derived numbers is
# still read exactly as it was.


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


def _refuse_a_row_restating_the_hand(case: SimCase, rotor: RotorBlock, stated: str) -> NoReturn:
    """Refuse a row that writes `RPM_SIGN` beside a rotor the reference declares.

    ONE HOME FOR THE REFUSAL, because there are two places a row can name its
    rotor and the sentence must not drift between them: the record path fills
    the view in `_motion_view`, and the row path resolves the block in
    `_rpm_sign`. The rule they both enforce is the same one.

    AND IT REFUSES WHETHER OR NOT IT AGREES. A row that agrees today says
    nothing when the REFERENCE is corrected tomorrow: the block flips, the row
    keeps the old hand, and the two disagree with nobody to notice -- which is
    the shape of the defect this rule exists to close. So the refusal is about
    where the key goes rather than about its value, and it says which of the two
    cases the reader is in, because "it already agrees" is the objection a user
    will otherwise raise.
    """
    agreement = (
        "which agrees with it today and would not survive the reference being corrected"
        if str(stated).strip() == str(rotor.rpm_sign)
        else "which disagrees with it"
    )
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {RPM_SIGN_VARIABLE} as {stated!r} and the rotor "
        f"{rotor.alias!r} declares {rotor.rpm_sign} in the reference, {agreement}. The "
        "hand of a rotation is the rotor's, declared once beside its axis and its "
        f"origin. Remove {RPM_SIGN_VARIABLE} from the row; to turn it the other way, "
        f"set 'rpm_sign' on the {rotor.alias!r} block of the reference artifact."
    )


def _rotor_the_row_names(case: SimCase) -> RotorBlock | None:
    """Return the rotor block a row names by alias IN ITS OWN VARIABLES, or None.

    A row may cite its rotor in two places: one record of a ``MOTIONS``
    list, or the row's own ``MOVING_BC_ALIAS`` cell when it turns a single
    rotor and states no list. Both are supported spellings and the second
    is the one the blade-count refusal recommends in those words.

    ONLY THE FIRST REACHED THE HAND, and that was this release's own defect
    surviving on the other shape. `_motion_view` fills the block's
    ``RPM_SIGN`` into the view it builds per RECORD; a row with no records
    never enters it, so `_rpm_sign` found nothing, returned 1, and the row
    turned whichever way its number was written while the reference said
    otherwise -- no refusal and no warning, which is the exact failure the
    magnitude rule exists to end (the architect lens, FIX-0220, reproduced
    at 800 rev/min against a block declaring -1).

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
    # AND THE FLAT SPELLING, WHEN THE REFERENCE DECLARES THE ROTOR IT MOVES.
    # The rule was written as "a flat row has nowhere else to put the hand", and
    # that is true only of a row whose reference declares NO rotor. A flat row
    # binds a reference like any other: when the boundary it turns is one of a
    # declared block's own families, that block is THIS ROTOR, it states a hand,
    # and reading the row's number instead was the release's own defect on its
    # third row shape -- measured emitting +800 against a block declaring -1,
    # with no refusal and no warning (the qa lens, FIX-0220).
    #
    # A ROW WHOSE REFERENCE DECLARES NOTHING IS UNTOUCHED, which is the whole of
    # the pre-0.15.0 exemption: no block, no hand to take, and the row's own
    # RPM_SIGN answers as it always has.
    moving = case.variables.get(MOVING_BOUNDARIES_VARIABLE)
    if moving is None:
        return None
    named = [part.strip() for part in str(moving).replace(",", " ").split() if part.strip()]
    if not named:
        return None
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
    which is the pre-0.15.0 spelling and the only home such a row has.
    """
    text = _variable(case, RPM_SIGN_VARIABLE)
    block = _rotor_the_row_names(case)
    if block is not None:
        if text is not None:
            _refuse_a_row_restating_the_hand(case, block, text)
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

    ONE FACT WITH TWO HOMES, and until 2026-09-11 only one of them was read.
    A row stating `ADVANCE_RATIO:sweep` in its flight condition puts the VALUE
    on the point: the HELD coordinates of a sweep are merged into `variables`
    and the SWEPT one is not, so `variables` carries `ALPHA` and `BETA` and no
    `ADVANCE_RATIO` at all. The script emitter resolves the point correctly and
    writes the speed into the script; the reduction planner asked `variables`
    and concluded the row stated no speed, so every unsteady reduction of every
    such point was recorded as SKIPPED with a message prescribing the thing the
    row had already done. Four of four points, three of three reductions each,
    on the licensed runs of 2026-09-11. Measured on four of four
    points of two licensed runs on 2026-09-11, three of three reductions each.

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
        If the row states both forms or neither; if a ratio is stated
        with no rotor diameter on the reference, naming the artifact
        field to add; or if the ratio, the velocity or the diameter is
        not a positive number.
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
            # THE SAME SIGN THE DERIVED FORM TAKES. Until 0.21.1 it was applied
            # to the derived speed alone, so a row stating RPM turned whichever
            # way the number happened to be written and the reference's hand was
            # dropped in silence.
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
    diameter = None if reference is None else reference.rotor_diameter
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
    # FOUR DECIMALS, the reference tooling's precision for the derived speed: the recorded
    # 9001 script states SET_MOTION_ROTOR_RPM 1 473.1723 0.0 0.0 (quoted in
    # reports/RPT-040, the reproduction report, from the recorded script)
    # where the unrounded derivation gives 473.17227304, and the run that
    # produced the reference tables turned at the four-decimal value. The scripts arm
    # of GOAL-011 found it as the one difference on that point on 2026-09-03.
    # A ten-thousandth of a rev/min is below anything the solver resolves.
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
    return speed


# --- the tip and helical Mach numbers of a rotor (0.30.0, M1) ----------------

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
    tip_speed = abs(rpm) * RAD_PER_S_PER_REV_PER_MIN * diameter_m / 2.0
    return (
        tip_speed / sonic_velocity_m_per_s,
        math.hypot(velocity_m_per_s, tip_speed) / sonic_velocity_m_per_s,
    )


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
        the speed its script hands the solver since 0.34.0 (FR-331).
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
            "note": self.note,
        }


def _states_a_rotor_speed(case: SimCase) -> bool:
    """Say whether a row states a rotor speed: ``RPM`` on the row, its point or a motion."""
    return _stated_rpm(case) is not None or any(RPM_VARIABLE in record for record in case.motions)


# --- PFS-2025.05: the rotor motion, off the row ------------------------------


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
    a half, carrying two of them, stands for two. The first writing of
    this default returned the wheel's four in BOTH cases, because it read
    the reference alone, and that is the SRS and the code saying different
    things about the same key (the architecture lens, 2026-09-10).

    ONE ROTOR ONLY, and deliberately: a sector is a slice of ONE wheel, so
    a row turning several rotors has no single count and is left to state
    one.

    THE SECOND RETURN IS THE REASON, because five different rows reach the
    same None and the refusal used to tell all of them the same thing,
    including one that told a row to do what it had already done (the
    interface lens, 2026-09-10).
    """
    aliases = [
        record.get(MOVING_BC_ALIAS_VARIABLE)
        for record in (case.motions or [])
        if record.get(MOVING_BC_ALIAS_VARIABLE)
    ]
    if not aliases:
        alias = _variable(case, MOVING_BC_ALIAS_VARIABLE)
        aliases = [str(alias)] if alias else []
    named = {str(alias).strip().casefold() for alias in aliases}
    if not named:
        return None, (
            f"Add it to the row's variables, or name the rotor by alias "
            f"({MOVING_BC_ALIAS_VARIABLE}) and let its block's blades say it."
        )
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
        # THE FILE IS THE WHOLE WHEEL, so it is not a slice of anything and
        # the arithmetic would answer one copy, which passes the positive
        # check above and initializes a full mesh as a sector of itself. A
        # row that means a half MODEL rather than a blade sector lands here
        # too, and it is the row 0.14.0 refused for the missing key (the QA
        # lens, 2026-09-10). Both are questions rather than counts.
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

    THE POINT FIRST, THEN THE ROW, THEN ZERO. A swept angle is the
    point's, which is what it has always been. An angle the row states in
    its FLIGHT_CONDITION and does not sweep is the row's, and until this
    release there was nowhere to write one: a row sweeping the advance
    ratio reached the solver at incidence zero, and the only record of the
    incidence was that nobody had written one (measured 2026-09-09 while
    reading the reference p001).

    THE ROW-STATED ANGLE IS USUALLY IN THE POINT ALREADY, and this
    function is what answers when it is not. The point's coordinates are
    run IDENTITY, so a held angle written in FLIGHT_CONDITION joins every
    point of the sweep, and a row spelled `ALPHA:sweep, BETA:0.0` tags its
    points exactly as the paired `AL/BE` row it was upgraded from did (see
    `SweepAxis.held`). What reaches the row and not the point is the
    advance ratio a row holds, and an angle written among the free
    variables rather than in the cell.
    """
    if axis in case.point:
        return float(case.point[axis])
    stated = _variable(case, ALPHA_VARIABLE if axis == "alpha" else BETA_VARIABLE)
    return 0.0 if stated is None else float(stated)


def _velocity(case: SimCase) -> float:
    if case.velocity is not None:
        return float(case.velocity)
    return _required_float(case, VELOCITY_VARIABLE, quantity="free-stream velocity", unit="m/s")


#: THE RADICAL OF A ROTOR THAT HAS NO ALIAS. Only one path produces one: a
#: matrix converted with no workspace, where `to_campaign` reads the row and
#: never an artifact, so there is no block to take a name from. It keeps the
#: shape every other rotor frame name has rather than reviving the
#: package-level PROP_MRP, which named one propulsor because a reference
#: described one.
UNNAMED_ROTOR_RADICAL = "ROTOR"


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
    """Resolve the processor count: the ROW's, since v0.17.0 (FR-93).

    ONE NUMBER FOR EVERY PLATFORM. It reaches
    ``SET_MAX_PARALLEL_THREADS`` as the solver's thread count and, on a
    submitting run, the scheduler's ``ncpus``. They cannot disagree
    because there is only one of them.

    ``from_setup`` is what a preset written before this release still
    carries. A row that states nothing inherits it, so nothing already
    written stops emitting the command; a row that states a count
    overrides it. The preset key is on its way out and the upgrade moves
    it into the column, which is why this reads the row FIRST and the
    preset second rather than the other way round.
    """
    stated = _variable(case, NCPUS_VARIABLE)
    if stated is None:
        return from_setup
    text = str(stated).strip()
    try:
        value = int(text)
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {NCPUS_VARIABLE}: {stated!r}, which is not a "
            "whole number of processors. It is the count the solver is given and, on a "
            "cluster, the count the job asks the scheduler for."
        ) from None
    if value < 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {NCPUS_VARIABLE}: {value}, and a run needs at "
            "least one processor."
        )
    return value


def row_symmetry_loads(case: SimCase, from_setup: bool | None) -> bool | None:
    """Resolve the symmetry-loads flag: the ROW's when it states one (FR-66).

    The design decision of 2026-09-10. Whether the solver reports the loads of the
    meshed SECTOR or of the whole wheel is a per-row choice, because one
    preset serves a sector row and a full-wheel row. A row stating it
    OVERRIDES the preset and warns naming both files and the value used;
    a row stating nothing inherits silently, as every row written before
    this release does.

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


def _stated_rate(case: SimCase, key: str) -> float | None:
    """Return one body rate this row states, from `variables` or its POINT."""
    stated = _variable(case, key)
    if stated is None:
        value = (getattr(case, "point", None) or {}).get(key)
        stated = None if value is None else str(value)
    if stated is None:
        return None
    try:
        return float(stated)
    except ValueError as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} as {stated!r}, and a body rate is a "
            "number of degrees per second."
        ) from error


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
    of rotors and the shape the whole per-rotor economy is for, and its
    members resolved to nothing because a rotor's name was a family name
    to nobody and sat in no alias table (the QA lens, 2026-09-10).

    ONE MAP FOR BOTH PATHS, deliberately. The expanding path and the
    common-frame path read the same words out of the same file, and the
    first fix gave the vocabulary to the expanding one alone: an entry
    written `frame = "MRP", families = ["lifters", "PUSHER"]`, which is
    how the total of the rotors in the moment frame is asked for, then
    selected NOTHING and warned that the geometry carries no family of it.

    The reference table takes precedence, so a study that gives one of these
    names a meaning of its own keeps it.
    """
    return {
        **{
            name: [*block.families_general, *block.families_blades]
            for name, block in case.rotors.items()
        },
        **case.aliases,
    }


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
    ScriptReferenceError
        The saved geometry cannot be read; the filesystem cause is retained.
    CampaignConfigError
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
                raise ScriptReferenceError(
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


#: DELETED 2026-09-14: `RESTART_ARCHIVE_DIR = "archive"` stood here, unused.
#: It was a THIRD literal spelling of the archive folder name, added in the
#: same release whose `workspace/naming.py` says the constants were moved down
#: "rather than being copied into a second home that would drift from the
#: first" and whose `post/products.py` repeats the claim. The claim was false
#: while this line existed, and the name was public surface acquired by
#: accident. It is deleted rather than deduplicated because `cases` sits below
#: `workspace` and cannot import `ARCHIVE_DIR`: if a future continuation
#: feature here needs the folder name, it is a run-layer argument and not a
#: cases-layer constant. Found by the architect lens of the 0.18.0 round.


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
    try:
        value = float(raw.strip())
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} asks for {form}={raw.strip()!r}, which is not a number."
        ) from None
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

    AN ABSENT ``stopped_at`` IS NOT ZERO, and reading it as zero was a defect
    that spent a licensed seat in silence. ``stopped_at`` is written by the
    WALL CLOCK, and :data:`~pyflightstream.run.CONTINUABLE` also admits
    ``COMPLETED_MAX_ITER``, which never carries it: a row that asked for 400
    steps, reached all 400 and was recorded at its iteration limit came back
    from this function with 400 MORE steps owed, and the run path printed
    "continuing for 400 more step(s)" while re-marching the entire history
    from a saved state that already held it. It is reachable from one cell,
    because a row whose post-processing artifact turns the log off has no
    residual history and is therefore recorded COMPLETED_MAX_ITER rather than
    CONVERGED. Found by the independent lens of the 0.18.0 release round,
    2026-09-14, which measured it rather than reading it.
    """
    stopped = record.get("stopped_at")
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
        window = record.get("export_window")
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
    window = record.get("export_window")
    step_deg = None
    if isinstance(window, Mapping):
        step_deg = window.get("step_deg")
    if not step_deg:
        raise CampaignConfigError(
            f"{RESTART_ADDITIONAL_REVS} counts revolutions and the record it continues "
            "states no azimuthal step, so there is no arithmetic from one to the other. "
            f"State {RESTART_ADDITIONAL_ITERS} instead."
        )
    return int(math.ceil(float(request.value or 0) * 360.0 / float(step_deg)))


def walltime_margin_s(case: SimCase) -> float:
    """Return the margin the setup states, or the default of twenty minutes.

    In the SETUP because it is a property of how you are willing to solve:
    how much time to leave for the exports is the same question on every
    platform and does not vary with the row, where the wall clock does.
    """
    solver = getattr(case, "solver", None)
    stated = getattr(solver, "walltime_margin_s", None) if solver is not None else None
    if stated is None:
        stated = case.variables.get("WALLTIME_MARGIN_S")
    if stated is None:
        return float(WALLTIME_MARGIN_DEFAULT_S)
    try:
        value = float(stated)
    except (TypeError, ValueError):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the walltime margin is {stated!r}, which is not a "
            "number of seconds. It is how long before the wall clock the run stops to "
            "write its exports."
        ) from None
    if value < 0:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the walltime margin is {value}, and a margin is a "
            "length of time before the clock rather than after it."
        )
    return value


def row_walltime_text(case: SimCase) -> str | None:
    """Return the wall clock the ROW states, AS WRITTEN, or None.

    What a descriptor carries by default (0.21.0): the scheduler's field takes
    the cell's own text, so a profile writing `#SBATCH --time={walltime}` gets
    `4h` where the row wrote `4h`.
    """
    stated = case.variables.get(WALLTIME_VARIABLE)
    if stated is None or str(stated).strip() in ("", "-"):
        return None
    return str(stated).strip()


def row_walltime_is_best(case: SimCase) -> bool:
    """Whether the row's WALLTIME cell asks the package for the wall clock (FR-364).

    ``BEST`` is read in any letter case. The grouped modes (``plan --batch`` and
    ``--polar-sweep``) compute the clock from the estimate; the default mode has
    none to compute it from and refuses the cell by name in :func:`row_walltime_s`.

    Parameters
    ----------
    case : SimCase
        The row's case.

    Returns
    -------
    bool
        True when the cell reads ``BEST``.
    """
    stated = row_walltime_text(case)
    return stated is not None and stated.upper() == WALLTIME_BEST


def row_walltime_s(case: SimCase) -> float | None:
    """Return the wall clock the ROW states, in seconds, or None (FR-93).

    TWO CONSUMERS, which is what earned it a column rather than a place in
    an HPC profile: on a cluster it is what the job asks the scheduler for,
    and anywhere at all it is what this watchdog counts down to.

    THE CELL CARRIES ITS UNIT since 0.21.0, and a bare number is refused by
    name. It read as SECONDS here and as minutes on the cluster it was written
    for, and neither reading is visible in the file: the same `240` is four
    minutes to this watchdog and four hours to the scheduler.
    """
    stated = row_walltime_text(case)
    if stated is None:
        return None
    if row_walltime_is_best(case):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}. BEST asks the "
            "package for the walltime, which plan --batch and --polar-sweep compute; "
            "write a wall clock with its unit for the default mode."
        )
    unit = stated[-1:].lower()
    if unit not in WALLTIME_UNITS:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}, which carries "
            "no unit. Write the unit with the number, as 240m or 4h: a bare number read "
            "as seconds here and as minutes on the scheduler, and a wall clock that means "
            f"two things is a job that dies early or holds a node for a day. The units "
            f"are {WALLTIME_UNITS_GLOSS}."
        )
    try:
        value = float(stated[:-1].strip())
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}, which is not a "
            f"number followed by one of {WALLTIME_UNITS_GLOSS}."
        ) from None
    if value <= 0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}, and a run needs "
            "a positive wall clock or none at all."
        )
    return value * WALLTIME_UNITS[unit]


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


# --- the quasi-steady rotor (0.30.0) -----------------------------------------


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
    """Refuse an unsteady row that states no averaging window (0.24.0).

    The definitions page states it: the window lives on the matrix and is a
    mandatory input. 0.23.0 did not refuse. A row without the key planned,
    ran, and then took the STEADY route at post: group polars read off the LAST
    TIME STEP under the steady names, beside a time average over a window the
    package had defaulted, with nothing in either file saying which was which.

    ONLY A NEW PLAN IS REFUSED. A record already written without a window is never
    refused at post: it is averaged over the window the run defaulted to, and the
    post stage says which.
    """
    _refuse_retired_window_keys(case)
    stated = (
        LAST_REVS_AVG_VARIABLE,
        LAST_ITERS_AVG_VARIABLE,
    )
    if any(_variable(case, key) is not None for key in stated):
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
            "0.29.0 refuses it in every matrix workflow: no workflow command applies the "
            "wake direction of a relaxed trailing edge, so the run would shed a wake the "
            f"row did not ask for. Remove {ROTOR_SHEDDING_VARIABLE} from the row. "
            "Direction control from the matrix is planned for 0.30.0; from Python, "
            "rotor_relaxed_trailing_edges sets the direction in the specifications of "
            "the component definition."
        )


def _refuse_unregistered_keys(case: SimCase, name: str) -> None:
    """Refuse a row stating a key the run type does not register.

    PFS-2008.02.01, measured on 2026-09-08: a one-row copy of the tier-3
    tour with ``FOO_BAR: 1`` appended planned READY on every point, and
    the run would have spent a seat on a row stating something the
    script does not carry. The refusal names the case (its ``sim_id`` is
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
    reader of its keys (the rule of 2026-09-08, design 68). The
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
    stated = sorted(
        key
        for key in case.variables
        if not key.startswith(CONVERTER_PREFIX)
        and key != ROTOR_ORIGIN_POINT_KEY
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
