"""What each far-field analysis of a row needs, and whether it is reused, added or refused.

Pipeline role: the ONE resolver of the far-field inputs (FR-455), called by
the plan and by post so the two cannot disagree. From the pproc artifact, the
row's run type and its facts, it states for every selected analysis and every
input one of four states: ``reused`` (the artifact declares it), ``added``
(the plan adds it), ``not_applicable`` (the analysis does not apply to the run
type, FR-456 R7) or ``refused`` (it cannot be produced, FR-455 R6), each with
its source and its reason. It reads nothing from disk and imports no layer
above ``cases``.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field

from pyflightstream.cases._farfield_spec import FarfieldSpec

__all__ = [
    "FARFIELD_STATES",
    "FarfieldInput",
    "FarfieldResolution",
    "ROTOR_RUN_TYPES",
    "STRIP_BIAS_PERCENT",
    "UNSTEADY_RUN_TYPES",
    "applies",
    "few_stations_warning",
    "resolve_farfield",
]

#: The four states of a far-field input (FR-455).
FARFIELD_STATES: tuple[str, ...] = ("reused", "added", "not_applicable", "refused")

#: The run types whose rows are rotors: a helical wake is not a streamwise sheet.
ROTOR_RUN_TYPES = frozenset({"unsteady_rotor", "qsteady_rotor"})
UNSTEADY_RUN_TYPES = frozenset({"unsteady", "unsteady_rotor"})
#: The strip bias of E_T on an elliptic loading, in percent, at the station
#: counts per side the definitions page measured (The far-field family, The
#: discretization bias).
STRIP_BIAS_PERCENT: dict[int, float] = {40: 1.05, 80: 0.52, 160: 0.26}

#: The command each input reaches, checked against the selected build (FR-455 R6).
_COMMANDS = {
    "section_distribution": "NEW_SURFACE_SECTION_DISTRIBUTION",
    "sectional_loads_export": "EXPORT_SURFACE_SECTIONAL_LOADS",
    "vtk_export": "EXPORT_SOLVER_ANALYSIS_VTK",
    "vtk_wake": "SET_VTK_EXPORT_VARIABLES",
    "probe_points": "NEW_PROBE_POINT",
    "probe_export": "EXPORT_PROBE_POINTS",
}


@dataclass(frozen=True)
class FarfieldInput:
    """One input of one analysis and how the row gets it.

    Attributes
    ----------
    analysis : str
        ``trefftz:sections``, ``trefftz:wake``, ``trefftz:plane`` or ``ledgers``.
    input : str
        What the analysis reads: ``section_distribution``,
        ``sectional_loads_export``, ``vtk_export``, ``vtk_wake``,
        ``probe_points`` or ``probe_export``.
    state : str
        One of :data:`FARFIELD_STATES`.
    source : str
        The declaration reused, or what the plan adds.
    reason : str
        Why the input is not applicable or refused; empty otherwise.
    """

    analysis: str
    input: str
    state: str
    source: str = ""
    reason: str = ""

    def as_record(self) -> dict[str, str]:
        """Return the input as the plan output states it (FR-455 R4)."""
        return {
            "analysis": self.analysis,
            "input": self.input,
            "state": self.state,
            "source": self.source,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FarfieldResolution:
    """Every input of every selected analysis of one row."""

    inputs: tuple[FarfieldInput, ...] = field(default_factory=tuple)

    @property
    def refused(self) -> tuple[FarfieldInput, ...]:
        """The inputs that cannot be produced; any one stops the plan."""
        return tuple(item for item in self.inputs if item.state == "refused")

    @property
    def added(self) -> tuple[FarfieldInput, ...]:
        """The inputs the plan adds to the row's script."""
        return tuple(item for item in self.inputs if item.state == "added")

    def state_of(self, analysis: str) -> str:
        """Return the analysis's state: refused, not_applicable, or ready (reused and added)."""
        states = {item.state for item in self.inputs if item.analysis == analysis}
        if "refused" in states:
            return "refused"
        if states == {"not_applicable"}:
            return "not_applicable"
        return "ready"

    def as_record(self) -> dict[str, object]:
        """Return the row's ``farfield`` object of ``plan.json`` (FR-455 R4)."""
        return {"inputs": [item.as_record() for item in self.inputs]}


def applies(analysis: str, run_type: str, *, rotor: bool = False) -> str:
    """Return why ``analysis`` does not apply to ``run_type``, or ``""`` (FR-456 R7).

    ``rotor`` marks a steady row whose far field is a rotor's.

    Parameters
    ----------
    analysis : str
        Far-field analysis name, such as trefftz:sections or trefftz:wake.
    run_type : str
        Resolved workflow name of the row.
    rotor : bool
        Whether the row describes a rotor rather than a wing configuration.

    Returns
    -------
    str
        Reason the analysis is inapplicable, or an empty string when applicable.

    Examples
    --------
    >>> applies('trefftz:sections', 'steady')
    ''
    >>> bool(applies('trefftz:wake', 'unsteady_rotor'))
    True
    """
    if analysis in ("trefftz:sections", "trefftz:wake"):
        if rotor or run_type in ROTOR_RUN_TYPES:
            return "a rotor's helical wake is not a streamwise sheet"
        if run_type in UNSTEADY_RUN_TYPES:
            return "variants A and B serve steady rows in 0.40.0"
    return ""


def few_stations_warning(family: str, per_side: int, stations: int) -> str:
    """Return the WARNING of a family traced on fewer stations than asked (FR-451 R10).

    One sentence, said by the plan and by post alike: the family, its station
    count per side, the count ``[farfield.trefftz] stations`` asks for, and the
    strip bias of ``E_T`` the definitions page measured at the nearest count
    (:data:`STRIP_BIAS_PERCENT`).

    Parameters
    ----------
    family : str
        The family the trace is of.
    per_side : int
        Its station count per side of the symmetry plane.
    stations : int
        The count per side ``[farfield.trefftz] stations`` asks for.

    Returns
    -------
    str
        The sentence, or ``""`` where the family has enough stations.
    """
    if per_side >= stations:
        return ""
    nearest = min(STRIP_BIAS_PERCENT, key=lambda count: (abs(count - per_side), count))
    return (
        f"family {family} has {per_side} stations per side, fewer than the {stations} of "
        f"[farfield.trefftz]; the strip bias of E_T measured on the definitions page is "
        f"{STRIP_BIAS_PERCENT[nearest]} percent at {nearest} stations per side (FR-451 R10)"
    )


def _analyses(spec: FarfieldSpec) -> list[str]:
    out = []
    if spec.trefftz is not None:
        out += [f"trefftz:{variant}" for variant in spec.trefftz.variant]
    if spec.ledgers is not None:
        out.append("ledgers")
    return out


def resolve_farfield(
    spec: FarfieldSpec,
    *,
    run_type: str,
    covered_families: Collection[str],
    selected_families: Sequence[str],
    exports: dict[str, bool],
    declares_lattice: bool,
    declares_plane: bool,
    coupled: bool,
    admits_probes: bool,
    has_command: Callable[[str], bool],
    rotor: bool = False,
) -> FarfieldResolution:
    """Resolve the inputs of every analysis ``spec`` selects for one row (FR-455).

    Parameters
    ----------
    spec : FarfieldSpec
        The row's ``[farfield]`` table.
    run_type : str
        The row's run type (``steady``, ``unsteady``, ``unsteady_rotor``,
        ``qsteady_rotor``).
    covered_families : collection of str
        The families a declared ``[sections]`` distribution cuts in plane XZ of a
        reference-axes frame (FR-455 R2).
    selected_families : sequence of str
        The families ``[farfield] families`` resolves to on the row's geometry.
    exports : dict of str to bool
        The artifact's ``[exports]`` table, as stated.
    declares_lattice, declares_plane : bool
        Whether a ``[[probes]]`` entry declares the lattice or the plane the far
        field reuses (identity is the caller's test, FR-455 R2).
    coupled : bool
        Whether the row is a coupled FSI row.
    admits_probes : bool
        Whether the row type takes probes at all (a steady coupled row does not).
    has_command : callable
        Whether the selected build's command database records a command.
    rotor : bool
        Whether a steady row's far field is a rotor's (FR-456 R7).

    Returns
    -------
    FarfieldResolution
        Every input with its state, source and reason.
    """
    resolver = _Resolver(
        spec=spec,
        run_type=run_type,
        covered=frozenset(covered_families),
        exports=dict(exports),
        has_command=has_command,
        rotor=rotor or run_type in ROTOR_RUN_TYPES,
    )
    if not selected_families:
        for analysis in _analyses(spec):
            resolver.item(
                analysis,
                "families",
                "refused",
                reason=f"[farfield] families = {spec.families!r} names no family of the geometry",
            )
        return FarfieldResolution(tuple(resolver.inputs))
    for analysis in _analyses(spec):
        why = applies(analysis, run_type, rotor=rotor)
        if why:
            resolver.item(analysis, "run_type", "not_applicable", reason=why)
        elif analysis == "trefftz:sections":
            resolver.sections(analysis, selected_families, coupled)
        elif analysis == "trefftz:wake":
            resolver.export(analysis, "vtk", "vtk_export", False)
            resolver.needed(
                analysis, "vtk_wake", False, "", "the wake switched on in the VTK export"
            )
        elif not admits_probes:
            resolver.item(
                analysis,
                "probe_points",
                "refused",
                reason="this row type takes no probes (a steady coupled FSI row)",
            )
        else:
            declared = declares_lattice if analysis == "ledgers" else declares_plane
            resolver.probes(analysis, declared)
    return FarfieldResolution(tuple(resolver.inputs))


@dataclass
class _Resolver:
    """The resolution of one row, input by input."""

    spec: FarfieldSpec
    run_type: str
    covered: frozenset[str]
    exports: dict[str, bool]
    has_command: Callable[[str], bool]
    rotor: bool
    inputs: list[FarfieldInput] = field(default_factory=list)

    def item(
        self, analysis: str, name: str, state: str, source: str = "", reason: str = ""
    ) -> None:
        self.inputs.append(FarfieldInput(analysis, name, state, source, reason))

    def lacks(self, analysis: str, name: str) -> bool:
        if self.has_command(_COMMANDS[name]):
            return False
        self.item(analysis, name, "refused", reason=f"the selected build has no {_COMMANDS[name]}")
        return True

    def needed(self, analysis: str, name: str, declared: bool, source: str, added: str) -> None:
        if self.lacks(analysis, name):
            return
        if declared:
            self.item(analysis, name, "reused", source)
        else:
            self.item(analysis, name, "added", added)

    def export(self, analysis: str, kind: str, name: str, default_on: bool) -> None:
        if self.lacks(analysis, name):
            return
        stated = self.exports.get(kind)
        if stated is True or (stated is None and default_on):
            self.item(analysis, name, "reused", f"[exports] {kind}")
        elif stated is False:
            self.item(
                analysis,
                name,
                "added",
                f"[exports] {kind} turned on for this row",
                reason=f"[exports] {kind} = false and {analysis} needs it (WARNING)",
            )
        else:
            self.item(analysis, name, "added", f"the {kind} export")

    def sections(self, analysis: str, selected: Sequence[str], coupled: bool) -> None:
        missing = [name for name in selected if name not in self.covered]
        if coupled and missing:
            self.item(
                analysis,
                "section_distribution",
                "refused",
                reason=(
                    "a coupled row admits exactly one section distribution, and it does not "
                    f"cover {', '.join(missing)}"
                ),
            )
        else:
            stations = self.spec.trefftz.stations if self.spec.trefftz else 80
            self.needed(
                analysis,
                "section_distribution",
                not missing,
                "[sections] distributions",
                f"a distribution over {', '.join(missing)}, frame MRP, plane XZ, "
                f"{stations} stations per side",
            )
        self.export(analysis, "sectional_loads", "sectional_loads_export", True)

    def probes(self, analysis: str, declared: bool) -> None:
        shape = "lattice" if analysis == "ledgers" or self.rotor else "plane"
        self.needed(
            analysis,
            "probe_points",
            declared,
            f"the declared [[probes]] {shape}",
            f"the far-field {shape} as probe points",
        )
        if self.run_type in UNSTEADY_RUN_TYPES:
            self.item(analysis, "probe_export", "added", "per-step fluid plots of every point")
        else:
            self.export(analysis, "probes", "probe_export", True)
