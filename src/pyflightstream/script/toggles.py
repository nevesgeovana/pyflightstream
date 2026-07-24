"""The solver's on/off vocabulary, read in both directions.

Pipeline role: leaf of the script layer. FlightStream writes every
on/off flag as the words ENABLE and DISABLE (SRC-003 pp.339-346), so a
setup carried over from the solver, a preset, or an interface export
speaks that vocabulary while Python speaks ``True`` and ``False``. This
module is the single home of the translation: the curated helpers
render it, the case models read it, and neither can drift from the
other.

Why a reader at all, rather than passing the value through: a non-empty
Python string is truthy, so ``'DISABLE'`` tested as a bare condition is
True and would emit ENABLE, inverting the physics of the run with no
error anywhere (incident INC-20260723-2027-pyflightstream). Truthiness
has no failure mode; this reader does.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

__all__ = ["SOLVER_TOGGLE_WORDS", "Toggle", "resolve_toggle"]

#: The solver's own words for an on/off flag, immutable: extending the
#: vocabulary at runtime would change what every helper and every case
#: model accepts, process wide.
SOLVER_TOGGLE_WORDS: Mapping[str, bool] = MappingProxyType({"ENABLE": True, "DISABLE": False})

#: A solver toggle as callers may write it: a Python bool, or the
#: solver's own ``ENABLE`` or ``DISABLE`` (any case, surrounding
#: whitespace ignored). Nothing else is a toggle.
Toggle = bool | str


def resolve_toggle(value: object, *, context: str = "a solver toggle") -> bool:
    """Resolve a solver toggle written in either vocabulary.

    Parameters
    ----------
    value : bool or str
        True or False, or ``"ENABLE"`` or ``"DISABLE"`` in any case.
    context : str
        What is being resolved, quoted in the refusal; callers inside
        the library use the ``helper: argument`` shape of the entity
        resolver.

    Returns
    -------
    bool
        The toggle state.

    Raises
    ------
    ValueError
        If the value is neither a bool nor one of the solver's words.
        Callers in the script layer re-raise this as
        :class:`~pyflightstream.script.CommandArgumentError`; inside a
        pydantic model it surfaces as a ``ValidationError`` naming the
        field, and the message below is what survives.

    Examples
    --------
    A preset line carried over from the solver:

    >>> resolve_toggle("DISABLE", context="solver_settings: viscous_coupling")
    False
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        word = value.strip().upper()
        if word in SOLVER_TOGGLE_WORDS:
            return SOLVER_TOGGLE_WORDS[word]
    raise ValueError(
        f"{context} takes True or False, or the solver's own ENABLE or DISABLE; got {value!r}"
    )
