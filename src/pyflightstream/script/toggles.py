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

from pyflightstream.script import CommandArgumentError

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
    CommandArgumentError
        If the value is neither a bool nor one of the solver's words.
        It is a ``ValueError``, so inside a pydantic model it surfaces
        as a ``ValidationError`` naming the field, and the message below
        is what survives.

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
    raise CommandArgumentError(
        f"{context} takes True or False, or the solver's own ENABLE or DISABLE; got {value!r}"
    )


# The readers the curated helpers share, here since 0.34.0 (AD-17) so that
# script.helpers and its private family modules read toggles from one home.


def _read(helper: str, argument: str, value: Toggle) -> bool:
    """Resolve one toggle, re-raising in the script layer's vocabulary."""
    try:
        return resolve_toggle(value, context=f"{helper}: {argument}")
    except ValueError as error:
        raise CommandArgumentError(str(error)) from error


def _optional_toggle(helper: str, argument: str, value: Toggle | None) -> bool | None:
    """Resolve an optional toggle up front, before the helper emits."""
    if value is None:
        return None
    return _read(helper, argument, value)


def _toggle(value: bool) -> str:
    """Render a resolved toggle as the solver writes it.

    Takes a bool only: every helper resolves its toggles through
    :func:`_read` or :func:`_optional_toggle` before emitting, so a
    string never reaches this function and truthiness is never the
    thing that decides a flag.
    """
    return "ENABLE" if value else "DISABLE"
