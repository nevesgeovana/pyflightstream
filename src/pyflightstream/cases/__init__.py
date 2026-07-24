"""Simulation and campaign definitions.

Pipeline role: describes what to run. A :class:`SimCase` (identified
by ``sim_id``) is one solver configuration with its sweep; a
:class:`Campaign` groups cases with the FlightStream version and the
executable path, both required and explicit: nothing is read from
environment variables or guessed (SAD Section 5). Native persistence
is ``campaign.toml``; the pipe-delimited ``matrix.fs`` run matrix
is read unchanged, forever, by the matrix reader
(:mod:`pyflightstream.cases.matrix`, FR-10).

Script recipes are explicitly imported functions satisfying the
:class:`ScriptRecipe` protocol: ``build(case, script) -> None``. The
campaign loop specializes the case per sweep point (filling
:attr:`SimCase.point`) and the recipe translates it into script
emissions, usually through the curated helpers. Recipe references are
``"package.module:function"`` strings, replacing the historical
import-by-number system (PP-7, FR-12).
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterator
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from pyflightstream.script import Script
from pyflightstream.script.toggles import resolve_toggle
from pyflightstream.versions import resolve

__all__ = [
    "Campaign",
    "ReferenceData",
    "ScriptRecipe",
    "SimCase",
    "SolverSettings",
    "SolverToggle",
    "SweepAxis",
    "check_recipe",
    "load_campaign",
    "point_tag",
    "resolve_recipe",
]

_TAG_PREFIXES = (("alpha", "a"), ("beta", "b"), ("advance_ratio", "j"))


@runtime_checkable
class ScriptRecipe(Protocol):
    """A function that turns one case point into script emissions.

    Implementations receive the per-point specialized case (the
    campaign loop fills :attr:`SimCase.point` and stages the geometry)
    and an empty :class:`~pyflightstream.script.Script` bound to the
    campaign's FlightStream version; they emit the whole script,
    usually through the curated helpers. Output files must use paths
    relative to the execution directory, so the collected evidence
    stays inside the managed simulation folder, and must be the names
    the loop rendered into :attr:`SimCase.outputs`: those are the ones
    it collects, and they carry the sweep point.
    """

    def __call__(self, case: SimCase, script: Script) -> None:
        """Emit the complete script for one case point."""
        ...


class SweepAxis(BaseModel):
    """The sweep of one case: which axis varies and its values.

    Attributes
    ----------
    type : str
        ``alpha`` (angle of attack, deg), ``beta`` (side slip, deg),
        ``alpha_beta`` (paired values), or ``advance_ratio``
        (propeller advance ratio J, dimensionless).
    values : list
        Axis values; for ``alpha_beta`` each entry is an
        ``[alpha, beta]`` pair in deg.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["alpha", "beta", "alpha_beta", "advance_ratio"]
    values: list[float] | list[tuple[float, float]]

    @model_validator(mode="after")
    def _values_match_the_axis_type(self) -> SweepAxis:
        pairs = self.type == "alpha_beta"
        for value in self.values:
            if pairs != isinstance(value, tuple):
                expected = "[alpha, beta] pairs" if pairs else "scalar values"
                raise ValueError(f"a {self.type} sweep takes {expected}, got {value!r}")
        return self

    def points(self) -> Iterator[dict[str, float]]:
        """Iterate the sweep as named point coordinates.

        Yields
        ------
        dict of str to float
            One mapping per point, keyed ``alpha``, ``beta``, or
            ``advance_ratio`` (both keys for ``alpha_beta``).
        """
        for value in self.values:
            if self.type == "alpha_beta":
                alpha, beta = value
                yield {"alpha": alpha, "beta": beta}
            else:
                yield {self.type: value}


def point_tag(point: dict[str, float]) -> str:
    """Return the stable file-name tag of one sweep point.

    The tag encodes the point coordinates in a fixed axis order with
    signed fixed-width values, for example ``a+02.0_b+00.0``; it names
    the generated script and ends the ``run_id``.

    Parameters
    ----------
    point : dict of str to float
        Point coordinates as produced by :meth:`SweepAxis.points`.
    """
    parts = [f"{prefix}{point[axis]:+05.1f}" for axis, prefix in _TAG_PREFIXES if axis in point]
    if not parts:
        raise ValueError(f"point {point!r} has no known axis (alpha, beta, advance_ratio)")
    return "_".join(parts)


class ReferenceData(BaseModel):
    """Reference quantities for coefficient normalization.

    Attributes
    ----------
    area : float
        Reference area S_ref in simulation length units squared.
    length : float
        Reference length L_ref in simulation length units.
    velocity : float, optional
        Reference velocity in m/s; None lets the recipe default it to
        the free-stream velocity (steady runs) or a characteristic
        velocity such as the rotor tip speed (SRC-003 p.201).
    """

    model_config = ConfigDict(extra="forbid")

    area: float
    length: float
    velocity: float | None = None


def _resolve_settings_toggle(value: object) -> object:
    """Resolve a settings toggle in either vocabulary, before validation.

    Runs ahead of pydantic's bool parsing, and resolves every value
    itself rather than only strings, so the settings field and the
    helper keyword it mirrors accept exactly the same thing: True and
    False, and the solver's own ENABLE and DISABLE. Pydantic's lax
    coercions (``"yes"``, ``"on"``, ``1``) are deliberately not
    accepted here, because a settings file that says ``1`` for a flag
    the solver writes as a word is more likely a mistake than an
    intent. The refusal is a ValueError, which pydantic reports as a
    ValidationError naming the field, so the message survives.
    """
    if value is None:
        return value
    return resolve_toggle(value, context="a solver settings toggle")


#: Settings toggle: a bool, or the solver's own ENABLE and DISABLE.
SolverToggle = Annotated[bool, BeforeValidator(_resolve_settings_toggle)]


class SolverSettings(BaseModel):
    """Solver runtime settings of one case.

    Field names match the keyword arguments of
    :func:`pyflightstream.script.helpers.solver_settings`, so recipes
    can forward them directly.

    Attributes
    ----------
    iterations : int
        Solver iteration limit.
    convergence : float
        Residual threshold declaring convergence (SRC-003 p.200).
    forced_iterations : bool, optional
        Run the full iteration count regardless of convergence. The
        solver's own words are accepted too (see below).
    boundary_layer : str, optional
        ``LAMINAR``, ``TRANSITIONAL``, or ``TURBULENT``.
    viscous_coupling : bool, optional
        Couple the boundary layer model to the potential solution.
        The solver's own words are accepted too (see below).
    max_threads : int, optional
        Parallel core count.
    timeout_s : float, optional
        Wall-clock limit for one point's solver process; enforced by
        the executor, not by FlightStream.

    Notes
    -----
    The toggles accept the solver's own vocabulary as well as Python
    booleans: ``viscous_coupling = 'DISABLE'`` in a settings file means
    False, the same as ``viscous_coupling = false``. A settings preset
    carried over from the solver speaks ENABLE and DISABLE, and a
    preset is often mixed (one flag in each vocabulary), so the model
    reads both and stores the bool
    (:func:`pyflightstream.script.toggles.resolve_toggle`). Any other
    string is refused by name.
    """

    model_config = ConfigDict(extra="forbid")

    iterations: int = 500
    convergence: float = 1e-5
    forced_iterations: SolverToggle | None = None
    boundary_layer: str | None = None
    viscous_coupling: SolverToggle | None = None
    max_threads: int | None = None
    timeout_s: float | None = None


class SimCase(BaseModel):
    """One solver configuration with its sweep (SAD Section 5).

    Attributes
    ----------
    sim_id : str
        Case identity; also names the managed folder
        ``sims/sim_<sim_id>``.
    aircraft : str
        Aircraft or configuration name.
    description : str
        Free-text description.
    reynolds : float, optional
        Chord Reynolds number of the condition.
    mach : float, optional
        Free-stream Mach number.
    velocity : float, optional
        Free-stream velocity in m/s.
    geometry : str, optional
        Path of the geometry or simulation file the recipe opens or
        imports (an ``.fsm`` for OPEN, a mesh file for IMPORT); the
        campaign loop stages
        it into ``inputs/`` and rewrites this field to the staged
        copy, so recipes OPEN exactly what the manifest hashed.
    sweep : SweepAxis
        The sweep of this case.
    reference : ReferenceData, optional
        Coefficient normalization references.
    solver : SolverSettings
        Runtime settings; defaults apply when omitted.
    recipe : str
        Script recipe reference, ``"package.module:function"``, or a
        name registered with the campaign loop.
    variables : dict
        Free per-case variables for the recipe (strings, numbers, or
        booleans), for example a symmetry declaration.
    outputs : list of str
        Output files the recipe's script exports, relative to the
        execution directory; the loop collects them into ``raw/`` and
        a missing one marks the point FAILED_INCOMPLETE_OUTPUT. Names
        may carry the naming placeholders, and the loop renders them
        for the point being built before the recipe runs, so a recipe
        exports ``case.outputs[i]`` rather than a literal. Every point
        of a case runs in one folder, so a case whose points would
        render the same output name is blocked before it runs.
    point : dict of str to float
        The current sweep point; filled by the campaign loop before
        the recipe builds, empty on the authored case.
    """

    model_config = ConfigDict(extra="forbid")

    sim_id: str
    aircraft: str
    description: str = ""
    reynolds: float | None = None
    mach: float | None = None
    velocity: float | None = None
    geometry: str | None = None
    sweep: SweepAxis
    reference: ReferenceData | None = None
    solver: SolverSettings = Field(default_factory=SolverSettings)
    recipe: str
    variables: dict[str, str | float | int | bool] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    point: dict[str, float] = Field(default_factory=dict)


class Campaign(BaseModel):
    """A named group of cases bound to one FlightStream installation.

    Attributes
    ----------
    name : str
        Campaign name; prefixes every ``run_id``.
    fs_version : str
        FlightStream version, canonical or alias; validated against
        the registered versions at load time, resolved to canonical in
        the manifest.
    fs_exe : str
        Explicit path of the FlightStream executable; existence is
        checked by the executor at construction, not here, so a
        campaign file can be authored away from the licensed machine.
    sims : list of SimCase
        The cases of the campaign.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    fs_version: str
    fs_exe: str
    sims: list[SimCase]

    @field_validator("fs_version")
    @classmethod
    def _version_is_registered(cls, value: str) -> str:
        resolve(value)
        return value


def load_campaign(path: str | Path) -> Campaign:
    """Load and validate a ``campaign.toml`` file.

    The file holds one ``[campaign]`` table (name, fs_version,
    fs_exe) and one ``[[sim]]`` array entry per case, as in SAD
    Section 5.

    Parameters
    ----------
    path : str or Path
        Location of the TOML file.

    Returns
    -------
    Campaign
        Validated campaign; version aliases are checked against the
        registered versions immediately, so a typo fails at load
        time, not at the first point.
    """
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    if "campaign" not in data:
        raise ValueError(
            f"{path} has no [campaign] table; campaign.toml needs [campaign] with "
            "name, fs_version, and fs_exe, plus one [[sim]] entry per case"
        )
    return Campaign(**data["campaign"], sims=data.get("sim", []))


def resolve_recipe(reference: str) -> Callable[[SimCase, Script], None]:
    """Import the recipe function a reference string names.

    Parameters
    ----------
    reference : str
        ``"package.module:function"``; the module must be importable
        and the attribute callable. Explicit references replace the
        historical import-by-number system (PP-7, FR-12).

    Returns
    -------
    callable
        The recipe function, satisfying :class:`ScriptRecipe`.
    """
    module_name, separator, function_name = reference.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError(
            f"recipe reference {reference!r} is not of the form 'package.module:function'"
        )
    try:
        module = import_module(module_name)
    except ImportError as error:
        raise ValueError(
            f"recipe module {module_name!r} cannot be imported: {error}. Recipes are "
            "explicitly imported functions; check the module path and the environment."
        ) from error
    recipe = getattr(module, function_name, None)
    if not callable(recipe):
        raise ValueError(
            f"recipe {reference!r} does not name a callable in {module_name!r}; found {recipe!r}"
        )
    check_recipe(reference, recipe)
    return recipe


def check_recipe(reference: str, recipe: Callable) -> None:
    """Refuse a callable the campaign loop could not call.

    The loose form of a script builder, ``build(workdir) -> Script``,
    is what everyone arriving from a driver script has; called by the
    loop it raises a bare TypeError once per point, after the pre-flight
    has already accepted the campaign. Refusing at resolution names the
    protocol and the signature found, once, before anything runs.
    Callables whose signature cannot be read (builtins, C extensions)
    pass: the library does not refuse what it cannot inspect.
    """
    try:
        parameters = signature(recipe).parameters.values()
    except (TypeError, ValueError):
        return
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD, Parameter.VAR_POSITIONAL)
    ]
    if any(parameter.kind is Parameter.VAR_POSITIONAL for parameter in positional):
        return
    required = [parameter for parameter in positional if parameter.default is Parameter.empty]
    unfillable = [
        parameter.name
        for parameter in parameters
        if parameter.kind is Parameter.KEYWORD_ONLY and parameter.default is Parameter.empty
    ]
    if len(positional) >= 2 and len(required) <= 2 and not unfillable:
        return
    found = ", ".join(parameter.name for parameter in parameters) or "no arguments"
    raise ValueError(
        f"recipe {reference!r} does not satisfy the ScriptRecipe protocol: the campaign "
        f"loop calls build(case, script) -> None, and this one takes ({found}). A loose "
        "builder that creates and returns its own Script emits into a script the loop "
        "never sees; take the case and the script it hands you, and return None."
    )
