"""A matrix row's own setup keys, stated over the preset its SET cell names (FR-316).

Pipeline role: resolution, called by :func:`pyflightstream.workspace.matrix.resolve_matrix`
once per row, after the row's preset has been loaded. A VAR_NAMES_VALUES key
that is a field of :class:`~pyflightstream.cases.SolverSettings`, or one of the
solver's own spellings in :data:`~pyflightstream.workspace.matrix.PRESET_ALIASES`,
is a SETUP key of that row, written with its native name, so one basic preset
serves a matrix whose rows each vary one setup factor.

THE RULE, AND ITS ONE DEFAULT. ``plan`` warns for every row that writes setup
keys, naming the row and the keys. A key the preset does not state is added
for that row only; a key the preset states with an EQUAL value is accepted and
changes nothing; a key the preset states with a DIFFERENT value is refused,
naming the row, the key and both values. There is no silent override of the
preset and no flag that allows one.

ONE LOADER, NOT TWO. Every value the row states is validated by the loader the
preset itself went through (the caller passes it in), on a copy of the
preset's table with the row's key in it: a value is legal on a row exactly when
it is legal in a preset, and the two cannot drift. Two values are equal when
the loader turns them into the same setting, so ``1e-6`` in a cell equals
``convergence = 0.000001`` in the file.

WHAT A CELL CAN CARRY. The cell grammar (:func:`pyflightstream.cases.matrix.read_matrix`)
splits pairs on a slash and gives each value as text. A number, a word, true
or false, and a list of names written comma-separated fit that; a TABLE does
not, because a table's own pairs would need the slash and a record list the
comma. So the table-valued keys (the separation models, the port and trailing
edge tables, the operations lists and the per-step actions) are a preset's
only, and a row naming one is refused with the list of them.

A key that is both a run-type key and a setup key, or a row stating one setting
in both vocabularies (``SYMMETRY_LOADS`` and ``symmetry_loads``), is refused as
ambiguous. A key that is neither stays refused by the run type, unchanged.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import SimCase, SolverSettings
from pyflightstream.cases.matrix import MatrixError, MatrixRow
from pyflightstream.cases.workflows import WORKFLOWS
from pyflightstream.script.toggles import resolve_toggle
from pyflightstream.workspace import InputArtifactError
from pyflightstream.workspace.inputs import SetupArtifact

__all__ = ["resolve_stabilization", "row_setup", "structured_setup_keys"]

#: The loader a preset goes through, ``(artifact, set_code) -> SolverSettings``.
Loader = Callable[[SetupArtifact, str], SolverSettings]

#: The two preset keys that together state ``solver_stabilization``.
_STABILIZATION_PAIR = ("stabilization", "stabilization_strength")


def resolve_stabilization(settings: Mapping[str, object], set_code: str) -> float | None:
    """Resolve the two-key stabilization pair into one strength, or None.

    A preset gates the strength with its own ENABLE/DISABLE key, and the
    emitter takes a single number. Disabled therefore means ABSENT and
    not zero: zero is a stabilization of zero strength that is still
    switched on, and emitting it would be a different run from the one
    the file describes.
    """
    if all(key not in settings for key in _STABILIZATION_PAIR):
        return None
    gate = settings.get("stabilization")
    enabled = True if gate is None else resolve_toggle(gate, context="stabilization")
    if not enabled:
        return None
    strength = settings.get("stabilization_strength")
    if strength is None:
        raise InputArtifactError(
            f"setup preset {set_code!r} enables stabilization and states no "
            "stabilization_strength, so there is no number to emit. Add the strength, "
            "or disable it."
        )
    # NARROWED RATHER THAN COERCED. A TOML value arrives as `object`, and
    # `float(object)` is both untypeable and a worse refusal: a string
    # would raise a bare ValueError naming neither the preset nor the
    # key. A bool is excluded on its own line because it is an int in
    # Python, so `True` would silently become a stabilization of 1.0.
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        raise InputArtifactError(
            f"setup preset {set_code!r} states stabilization_strength as {strength!r}, "
            "and a stabilization strength is a number."
        )
    return float(strength)


def _leaves(annotation: Any) -> list[Any]:
    """Flatten a field annotation into its leaf types and literal values."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _leaves(get_args(annotation)[0])
    if origin in (Union, UnionType):
        return [leaf for arg in get_args(annotation) for leaf in _leaves(arg)]
    if origin is Literal:
        return list(get_args(annotation))
    if origin in (list, tuple, dict):
        return [origin, *(leaf for arg in get_args(annotation) for leaf in _leaves(arg))]
    return [annotation]


def _is_table(leaf: Any) -> bool:
    return leaf in (dict, tuple) or (isinstance(leaf, type) and issubclass(leaf, BaseModel))


def structured_setup_keys() -> tuple[str, ...]:
    """Return the setup keys whose value is a table, which a matrix cell cannot carry."""
    return tuple(
        sorted(
            name
            for name, field in SolverSettings.model_fields.items()
            if any(_is_table(leaf) for leaf in _leaves(field.annotation))
        )
    )


def _cell_value(field: str, text: str) -> object:
    """Turn a cell's text into the value the preset loader reads for ``field``.

    A list field takes names separated by commas (``all`` where the field
    takes it); true and false become booleans; anything else stays text,
    which the loader converts or refuses exactly as it would in a preset.
    """
    leaves = _leaves(SolverSettings.model_fields[field].annotation)
    if list in leaves:
        if text.strip().casefold() == "all" and "all" in leaves:
            return "all"
        return [part.strip() for part in text.split(",") if part.strip()]
    if text.strip().casefold() in ("true", "false") and (bool in leaves or True in leaves):
        return text.strip().casefold() == "true"
    return text


def _refuse_ambiguous(
    pol: str, stated: Mapping[str, str], row: Mapping[str, str], run_type_keys: frozenset[str]
) -> None:
    folded = {key.casefold(): key for key in run_type_keys}
    for key in stated:
        twin = folded.get(key.casefold())
        if twin is None:
            continue
        if twin == key or twin in row:
            written = key if twin == key else f"{twin} and {key}"
            raise MatrixError(
                f"POL {pol}: the row states {written}, which names both a run-type key and "
                f"a setup key, so it is ambiguous which one the row means (FR-316). State "
                f"the setting once: {twin} as the run type reads it, or {key.lower()} as "
                "the setup reads it, not both."
            )


def _preset_spellings(
    settings: Mapping[str, object], aliases: Mapping[str, str]
) -> dict[str, list[str]]:
    """Map every setting the preset states to the key(s) it states it with."""
    spellings: dict[str, list[str]] = {}
    for key in settings:
        spellings.setdefault(aliases.get(key, key), []).append(key)
    pair = [key for key in _STABILIZATION_PAIR if key in settings]
    if pair:
        spellings.setdefault("solver_stabilization", []).extend(pair)
    return spellings


def _load(
    loader: Loader, setup: SetupArtifact, settings: dict[str, object], set_code: str, pol: str
) -> SolverSettings:
    # THE PRESET'S OWN WARNINGS WERE GIVEN WHEN IT LOADED, once; a row's
    # re-load would repeat them for every row naming the preset.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        try:
            return loader(setup.model_copy(update={"settings": settings}), set_code)
        except InputArtifactError as error:
            raise MatrixError(
                f"POL {pol}: a setup key the row states does not fit its preset "
                f"{set_code!r} (FR-316): {error}"
            ) from error


def row_setup(
    setup: SetupArtifact,
    preset: SolverSettings,
    row: MatrixRow,
    case: SimCase,
    *,
    aliases: Mapping[str, str],
    loader: Loader,
) -> dict[str, object]:
    """Return the case fields the row's setup keys set: its solver, and the keys it stated.

    ``preset`` is the loaded preset. With no setup key on the row the result
    is ``{"solver": preset}``; otherwise it also carries ``setup_from_row``
    (each key to its cell text, which the run record carries) and the case's
    ``variables`` without those keys, since the solver now holds them (FR-316).
    """
    fields = set(SolverSettings.model_fields)
    stated = {k: text for k, text in row.variables.items() if aliases.get(k, k) in fields}
    if not stated:
        return {"solver": preset}
    pol, set_code = row.pol, row.set_code
    run_type_keys = frozenset().union(*(workflow.keys for workflow in WORKFLOWS.values()))
    _refuse_ambiguous(pol, stated, row.variables, run_type_keys)
    seen: dict[str, str] = {}
    for key in stated:
        field = aliases.get(key, key)
        if field in seen:
            raise MatrixError(
                f"POL {pol}: the row states the setting {field!r} twice, as {seen[field]!r} "
                f"and as {key!r}, two spellings of one setting (FR-316). Keep one."
            )
        seen[field] = key
    tables = sorted(key for key in stated if aliases.get(key, key) in structured_setup_keys())
    if tables:
        raise MatrixError(
            f"POL {pol}: the row states {', '.join(tables)}, a setup key whose value is a "
            "table, and a VAR_NAMES_VALUES cell cannot carry a table: its pairs are "
            "separated by a slash and its records by a comma (FR-316). A row carries a "
            "setup key whose value is a number, a word, true or false, or a comma-separated "
            f"list of names; these are a preset's only: {', '.join(structured_setup_keys())}."
        )
    settings = dict(setup.settings)
    spellings = _preset_spellings(settings, aliases)
    added: dict[str, object] = {}
    for key, text in stated.items():
        field = aliases.get(key, key)
        value = _cell_value(field, text)
        if field not in spellings:
            added[key] = value
            continue
        candidate = {k: v for k, v in settings.items() if k not in spellings[field]}
        effective = getattr(_load(loader, setup, {**candidate, key: value}, set_code, pol), field)
        if effective != getattr(preset, field):
            written = ", ".join(f"{k} = {settings[k]!r}" for k in spellings[field])
            raise MatrixError(
                f"POL {pol}: the row states {key} = {text} and its setup preset {set_code!r} "
                f"states {written}. By default a row does not overwrite what its preset "
                "states, and the two values differ, so the row is refused rather than one of "
                "them silently winning (FR-316). Make the row agree with the preset, drop "
                "the key from the row, or give the row a preset that does not state it."
            )
    solver = _load(loader, setup, {**settings, **added}, set_code, pol) if added else preset
    warnings.warn(
        f"POL {pol}: the row writes setup key(s) "
        f"{', '.join(f'{key} = {text}' for key, text in stated.items())} over its setup "
        f"preset {set_code!r}, for this row only (FR-316).",
        PyflightstreamWarning,
        stacklevel=3,
    )
    return {
        "solver": solver,
        "setup_from_row": dict(stated),
        "variables": {k: v for k, v in case.variables.items() if k not in stated},
    }
