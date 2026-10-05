"""A length of rotor wake converted into time steps: the one conversion of a rotor row.

TWO KEYS READ IT. The wake termination a rotor row keeps
(``wake_termination_length``, FR-321) and the run length a rotor row may state
as a target wake length (``RUN_WAKE_LENGTH_R``, FR-422) are the same number of
the same physics: how many steps it takes the wake to travel ``L`` rotor radii
at the axial convection speed ``V_ax``, ``n = ceil(L R Omega / (V_ax dtheta))``,
with ``R`` the tip radius in metres, ``Omega`` the rotor speed in rad/s and
``dtheta`` the step angle in rad. One function computes it, with one rule for
``V_ax`` (the free stream, or the momentum-theory induced velocity of a stated
thrust where it is the larger), so the plan, the script, the record and the
post read one source.

IT LIVES BELOW THE CLOCK. :mod:`._freestream`, which emits the wake
termination, reads the run's clock from :mod:`._timing`; the run length is the
clock, so the clock resolves it here, and the wake termination reads the same
functions from here.

THE LENGTH IS NOMINAL: the helical travel of the wake at ``V_ax`` under the
convention of FR-321, not a measured wake (FR-422 R5).
"""

from __future__ import annotations

import math
from dataclasses import (
    dataclass,
)

from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)

from ._rows import (
    _rotor_of,
    _the_rotor_a_flat_row_turns,
    _velocity,
)
from ._vocabulary import (
    REVOLUTIONS_VARIABLE,
    RUN_WAKE_LENGTH_R_VARIABLE,
)

#: The rules that give V_ax, as the record and the plan name them (FR-323 R6).
FREE_STREAM, INDUCED_VELOCITY = "free_stream", "induced_velocity"

#: The setup key whose thrust convects the wake near hover (FR-323 R1).
_THRUST_KEY = "wake_termination_thrust_n"

#: The wake termination's remedy for a thrust with no fluid density (FR-323 R1).
_CAP_REMEDY = "State the row's flight condition, or use wake_termination_revolutions_cap."


def _radius_and_hub(case: SimCase) -> tuple[float | None, float | None]:
    """Return the largest tip radius the row turns, in metres, and that rotor's hub X."""
    blocks = (
        [_rotor_of(case, record) for record in case.motions]
        if case.motions
        else [_the_rotor_a_flat_row_turns(case)]
    )
    fallback = None if case.reference is None else case.reference.rotor_diameter
    sized = [
        (block.diameter_m if block is not None else fallback, block)
        for block in blocks
        if block is not None or fallback is not None
    ]
    if not sized:
        return None, None
    diameter, block = max(sized, key=lambda pair: float(pair[0] or 0.0))
    return float(diameter or 0.0) / 2.0, None if block is None else block.x_m


def _induced(case: SimCase, radius: float, v_inf: float, *, remedy: str = "") -> tuple[float, str]:
    """Return V_ax and its rule for a length: v_i where a thrust is stated and exceeds V_inf.

    ``remedy`` is the last sentence of the refusal of a thrust with no fluid
    density, which differs by the key the length came from; empty, it is the
    wake termination's (FR-323 R1).
    """
    thrust = case.solver.wake_termination_thrust_n
    if thrust is None:
        return v_inf, FREE_STREAM
    if case.fluid is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {_THRUST_KEY} = {thrust} and resolves "
            "no fluid density, so the induced velocity sqrt(T / (2 rho A)) cannot be "
            "evaluated (FR-323 R1). " + (remedy or _CAP_REMEDY)
        )
    induced = math.sqrt(thrust / (2.0 * case.fluid.density_kg_m3 * math.pi * radius**2))
    return (induced, INDUCED_VELOCITY) if induced > v_inf else (v_inf, FREE_STREAM)


def _clock_rates(
    rpm: float | None, delta_time_s: float, steps_per_revolution: float | None
) -> tuple[float, float]:
    """Return Omega in rad/s and dtheta in rad of a run's clock.

    dtheta is one revolution over the clock's steps per revolution where it
    has them, else Omega times the step in seconds.
    """
    per_revolution = steps_per_revolution or 0.0
    omega = abs(rpm or 0.0) * 2.0 * math.pi / 60.0
    dtheta = 2.0 * math.pi / per_revolution if per_revolution else omega * delta_time_s
    return omega, dtheta


def _wake_steps(length: float, radius: float, omega: float, v_ax: float, dtheta: float) -> int:
    """Return ``ceil(L R Omega / (V_ax dtheta))``, rounded upward so the wake is never shorter.

    The quotient is rounded to nine decimals first, so float noise on a whole
    number does not add a step (FR-321 R2).
    """
    return math.ceil(round(length * radius * omega / (v_ax * dtheta), 9))


@dataclass(frozen=True)
class RunWakeLength:
    """The run length an ``unsteady_rotor`` row states as a target wake length (FR-422).

    Attributes
    ----------
    length_r : float
        The length asked, in rotor radii, as the row states ``RUN_WAKE_LENGTH_R``.
    radius_m : float
        The tip radius R in metres (the largest rotor the row turns).
    omega_rad_s : float
        The rotor speed of the run's clock in rad/s.
    dtheta_rad : float
        The step angle of the run's clock in rad.
    v_inf_m_s : float
        The free-stream speed of the point in m/s.
    v_ax_m_s : float
        The axial convection speed used, in m/s.
    rule : str
        ``free_stream`` or ``induced_velocity``: which gave ``v_ax_m_s``.
    time_iterations : int
        The resolved step count of the run.
    """

    length_r: float
    radius_m: float
    omega_rad_s: float
    dtheta_rad: float
    v_inf_m_s: float
    v_ax_m_s: float
    rule: str
    time_iterations: int

    @property
    def revolutions(self) -> float:
        """Return the revolutions the resolved count turns, ``n dtheta / (2 pi)``."""
        return self.time_iterations * self.dtheta_rad / (2.0 * math.pi)

    def record(self) -> dict[str, object]:
        """Return the fields and the revolutions, as the plan writes them."""
        return {
            "length_r": self.length_r,
            "radius_m": self.radius_m,
            "omega_rad_s": self.omega_rad_s,
            "dtheta_rad": self.dtheta_rad,
            "v_inf_m_s": self.v_inf_m_s,
            "v_ax_m_s": self.v_ax_m_s,
            "rule": self.rule,
            "time_iterations": self.time_iterations,
            "revolutions": self.revolutions,
        }

    def derived(self) -> dict[str, str]:
        """Return the values the run record carries beside the solver settings (FR-422 R3).

        The length asked, the rule and the V_ax it gave, and the resulting
        ``time_iterations``.
        """
        return {
            "run_wake_length": f"{self.length_r:g} R",
            "run_wake_rule": self.rule,
            "run_wake_v_ax_m_s": f"{self.v_ax_m_s:.6g}",
            "run_wake_time_iterations": str(self.time_iterations),
        }


def run_wake_length(case: SimCase, length: float, *, omega: float, dtheta: float) -> RunWakeLength:
    """Resolve the run length of a row stating ``RUN_WAKE_LENGTH_R`` (FR-422).

    Parameters
    ----------
    case : SimCase
        The point's case; its rotor, free stream, fluid and setup give R and V_ax.
    length : float
        The positive, finite length asked, in rotor radii.
    omega : float
        The rotor speed of the run's clock in rad/s, positive.
    dtheta : float
        The step angle of the run's clock in rad, positive.

    Returns
    -------
    RunWakeLength
        The resolved count with what it came from.

    Raises
    ------
    CampaignConfigError
        If no rotor radius is known, if a thrust is stated with no fluid
        density, or if the axial velocity is not positive (FR-422 R2); each
        names the remedy.
    """
    radius, _ = _radius_and_hub(case)
    if not radius:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {RUN_WAKE_LENGTH_R_VARIABLE} = {length:g} and the "
            "rotor it turns has no known radius, so a length in rotor radii has no length "
            "in metres. Declare the rotor block's diameter_m, or rotor_diameter_m, on the "
            f"reference, or state {REVOLUTIONS_VARIABLE} instead."
        )
    remedy = (
        "State the row's flight condition, or state "
        f"{REVOLUTIONS_VARIABLE} instead of {RUN_WAKE_LENGTH_R_VARIABLE}."
    )
    v_inf = abs(_velocity(case))
    v_ax, rule = _induced(case, radius, v_inf, remedy=remedy)
    if v_ax <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {RUN_WAKE_LENGTH_R_VARIABLE} = {length:g} at an "
            f"axial velocity of {v_ax:g} m/s, and a wake that does not convect never "
            f"reaches a length. State {_THRUST_KEY} (the rotor's thrust in newtons, whose "
            "induced velocity convects the wake) in the setup, or state "
            f"{REVOLUTIONS_VARIABLE} instead of {RUN_WAKE_LENGTH_R_VARIABLE}."
        )
    exact = length * radius * omega / (v_ax * dtheta)
    if not math.isfinite(exact):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {RUN_WAKE_LENGTH_R_VARIABLE} = {length:g}, which "
            f"at V_ax = {v_ax:g} m/s is no finite number of time steps. State a larger "
            f"free-stream speed or a shorter length, or state {REVOLUTIONS_VARIABLE} instead."
        )
    return RunWakeLength(
        length_r=length,
        radius_m=radius,
        omega_rad_s=omega,
        dtheta_rad=dtheta,
        v_inf_m_s=v_inf,
        v_ax_m_s=v_ax,
        rule=rule,
        # A positive target must march once even when the shared wake
        # conversion's roundoff tolerance erases a sub-step duration.
        time_iterations=max(1, _wake_steps(length, radius, omega, v_ax, dtheta)),
    )
