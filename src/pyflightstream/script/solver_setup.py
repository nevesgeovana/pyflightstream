"""Solver-setup snapshot: total provenance of the solver flags.

Pipeline role: records, for every solver flag of the runtime_settings,
solver_settings, and advanced_settings command families (plus the
induced-drag boundary selection of SET_VORTICITY_DRAG_BOUNDARIES), the
effective value of one built script and where that value came from:
``explicit`` when the caller passed it, ``default`` when the library or
the manual documents the value that applies without user input (the
citation travels with the record), and ``unknown`` when no in-repo
evidence exists. Unknown is stated honestly, never guessed: an opened
simulation file can carry saved solver settings, so the library refuses
to claim knowledge it does not have (evidence rule, CLAUDE.md
invariant 3).

The snapshot travels with the run. The curated helper
:func:`pyflightstream.script.helpers.solver_settings` builds it and
attaches it to the :class:`~pyflightstream.script.Script` as
``script.solver_setup``; the campaign loop serializes it into the
manifest record (:attr:`pyflightstream.workspace.RunRecord.solver_setup`);
and :func:`script_from_setup` regenerates the same settings emissions
from a stored snapshot, closing the provenance loop.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from pyflightstream.commands import CommandEntry, CommandRegistry
from pyflightstream.versions import resolve

if TYPE_CHECKING:  # typing only; the runtime import would be circular
    from pyflightstream.script import Script

__all__ = [
    "FLAG_SPECS",
    "LIBRARY_MINIMUM_CP",
    "SNAPSHOT_FAMILIES",
    "VORTICITY_COMMAND",
    "BulkSeparation",
    "FlagRecord",
    "SolverSetup",
    "script_from_setup",
]

#: Command-database chapters whose every command is a snapshot flag.
SNAPSHOT_FAMILIES = ("runtime_settings", "solver_settings", "advanced_settings")

#: The induced-drag boundary selection, snapshotted although it lives in
#: the solver_analysis chapter: it is the drag-method decision of
#: :func:`pyflightstream.script.helpers.solver_settings`, recorded
#: whether the caller made it or left the solver default in place.
VORTICITY_COMMAND = "SET_VORTICITY_DRAG_BOUNDARIES"

#: Minimum pressure coefficient (dimensionless Cp) the library emits
#: whenever the caller does not pass ``minimum_cp``. The solver's own
#: default is -20 (SRC-003 p.221), which clips the suction peaks of
#: rotor blades; -100 is the author's library default of 2026-07-22,
#: retiring the earlier reference-velocity workaround. The physics
#: references were re-validated under this default on a licensed
#: 26.120 machine: 30 of 30 metrics bit-identical, report
#: reports/physics/PHY-26120_2026-07-23_reseed-cp100-2026-07-23.
LIBRARY_MINIMUM_CP = -100

_EXPLICIT: Literal["explicit"] = "explicit"
_DEFAULT: Literal["default"] = "default"
_UNKNOWN: Literal["unknown"] = "unknown"


@dataclass(frozen=True)
class FlagSpec:
    """Mapping of one snapshot flag to its command and value shape.

    Attributes
    ----------
    param : str
        Keyword of :func:`pyflightstream.script.helpers.solver_settings`
        that carries the flag (the two solver-mode commands share
        ``mode``).
    command : str
        FlightStream command the flag emits.
    kind : str
        Value shape: ``scalar`` (number), ``toggle`` (bool rendered
        ENABLE/DISABLE), ``enum`` (token), ``boundary_list`` (sequence
        of boundary indices or labels), ``boundary_selection`` (the
        same plus the ``"all"`` form), ``mode_steady`` /
        ``mode_unsteady`` (the solver-mode pair), and
        ``bulk_separation`` (the :class:`BulkSeparation` model).
    """

    param: str
    command: str
    kind: str


#: Every snapshot flag, in the emission order of the curated helper.
FLAG_SPECS: tuple[FlagSpec, ...] = (
    FlagSpec("mode", "SET_SOLVER_STEADY", "mode_steady"),
    FlagSpec("mode", "SET_SOLVER_UNSTEADY", "mode_unsteady"),
    FlagSpec("aoa", "SOLVER_SET_AOA", "scalar"),
    FlagSpec("sideslip", "SOLVER_SET_SIDESLIP", "scalar"),
    FlagSpec("velocity", "SOLVER_SET_VELOCITY", "scalar"),
    FlagSpec("mach", "SOLVER_SET_MACH_NUMBER", "scalar"),
    FlagSpec("ref_velocity", "SOLVER_SET_REF_VELOCITY", "scalar"),
    FlagSpec("ref_mach", "SOLVER_SET_REF_MACH_NUMBER", "scalar"),
    FlagSpec("ref_area", "SOLVER_SET_REF_AREA", "scalar"),
    FlagSpec("ref_length", "SOLVER_SET_REF_LENGTH", "scalar"),
    FlagSpec("iterations", "SOLVER_SET_ITERATIONS", "scalar"),
    FlagSpec("convergence", "SOLVER_SET_CONVERGENCE", "scalar"),
    FlagSpec("max_threads", "SET_MAX_PARALLEL_THREADS", "scalar"),
    FlagSpec("forced_iterations", "SOLVER_SET_FORCED_ITERATIONS", "toggle"),
    FlagSpec("boundary_layer", "SET_BOUNDARY_LAYER_TYPE", "enum"),
    FlagSpec("viscous_coupling", "SET_SOLVER_VISCOUS_COUPLING", "toggle"),
    FlagSpec("viscous_excluded", "SET_VISCOUS_EXCLUDED_BOUNDARIES", "boundary_list"),
    FlagSpec("bulk_separation", "CREATE_BULK_SEPARATION", "bulk_separation"),
    FlagSpec("convergence_iterations", "SET_SOLVER_CONVERGENCE_ITERATIONS", "scalar"),
    FlagSpec("minimum_cp", "SOLVER_MINIMUM_CP", "scalar"),
    FlagSpec("reynolds_averaged_drag", "REYNOLDS_AVERAGED_DRAG_FORCES", "toggle"),
    FlagSpec("mesh_induced_wake_velocity", "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY", "toggle"),
    FlagSpec("farfield_layers", "SOLVER_SET_FARFIELD_LAYERS", "scalar"),
    FlagSpec("unsteady_pressure_and_kutta", "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA", "toggle"),
    FlagSpec("wake_termination_time_steps", "SET_WAKE_TERMINATION_TIME_STEPS", "scalar"),
    FlagSpec("wake_on_wake_induction", "SET_WAKE_ON_WAKE_INDUCTION", "toggle"),
    FlagSpec("additional_wake_relaxation", "ADDITIONAL_WAKE_RELAXATION_ITERATION", "toggle"),
    FlagSpec("aeroelastic_rbf_type", "AEROELASTIC_RBF_TYPE", "enum"),
    FlagSpec("vorticity_drag_boundaries", VORTICITY_COMMAND, "boundary_selection"),
)

_SPEC_BY_COMMAND: dict[str, FlagSpec] = {spec.command: spec for spec in FLAG_SPECS}


class BulkSeparation(BaseModel):
    """One bulk (bluff-body) flow-separation assignment (SRC-003 p.342).

    Bluff bodies shed their wake from a separation line rather than a
    trailing edge; the bulk model assigns that behavior to the listed
    mesh boundaries (SRC-003 p.207). This is the 26.12 four-argument
    grammar with SEPARATION_TYPE; the three-argument 26.1 form
    (SRC-725 p.341) is not covered by the helper and needs direct
    emission.

    Attributes
    ----------
    name : str
        Display name of the separation assignment in the interface.
    separation_type : str
        Bulk model sub-type, ``CYLINDRICAL`` or ``FLAT_PLATE``
        (SRC-003 p.207).
    diameter : float
        Characteristic body diameter, in simulation length units.
    boundaries : list of int or str, or ``"all"``
        Mesh boundaries carrying the model, by 1-based index in
        geometry-tree order or by declared boundary label; ``"all"``
        selects every boundary (the -1 form of SRC-003 p.342).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    separation_type: Literal["CYLINDRICAL", "FLAT_PLATE"]
    diameter: float
    boundaries: list[int | str] | Literal["all"] = "all"


class FlagRecord(BaseModel):
    """Effective value and provenance of one solver flag in one script.

    Attributes
    ----------
    command : str
        FlightStream command the flag belongs to.
    family : str
        Command-database chapter of the command (``runtime_settings``,
        ``solver_settings``, ``advanced_settings``, or
        ``solver_analysis`` for the induced-drag selection).
    provenance : str
        ``explicit`` (the caller passed the flag), ``default`` (the
        value applies without user input: either emitted by the
        library, or the documented solver default with its citation),
        or ``unknown`` (no in-repo evidence; the value is None and
        never guessed). A documented default is recorded only when the
        command exists in the script's FlightStream version, because
        defaults are per-version facts.
    value : JSON value
        Effective value in helper vocabulary (bool for toggles,
        mapping for the unsteady mode and the bulk separation); None
        when unknown. A boundary selection is a list of indices or
        labels, or the string ``all``; the empty list is the recorded
        no-selection default of the induced-drag flag, so read the
        provenance before reading an empty value: ``[]`` with
        ``default`` is knowledge (no boundary was selected), None with
        ``unknown`` is the absence of it.
    emitted : bool
        Whether the script this snapshot describes carries the
        emission. The induced-drag selection is emitted deferred, at
        the first curated call reaching the analysis phase, and may
        have been emitted by an earlier settings call on the same
        script, so this is a fact about the script rather than about
        the single call. A documented-but-unemitted default is the
        solver's own behavior, assuming the opened file did not
        override it.
    evidence : str, optional
        Citation of a ``default`` value; None for explicit values (the
        script line is the evidence) and for unknown flags.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str
    family: str
    provenance: Literal["explicit", "default", "unknown"]
    value: JsonValue = None
    emitted: bool = False
    evidence: str | None = None


class SolverSetup(BaseModel):
    """The complete solver-flag snapshot of one built script.

    One :class:`FlagRecord` per command of the three settings families
    plus the induced-drag boundary selection, keyed by command name.
    Serialize with ``model_dump_json()`` (or ``model_dump(mode="json")``
    for the manifest) and restore with ``model_validate_json()``;
    :func:`script_from_setup` then regenerates the settings emissions.

    Attributes
    ----------
    fs_version : str
        Canonical FlightStream version the script was built for; the
        per-version defaults were resolved against it.
    flags : mapping of str to FlagRecord
        The snapshot, keyed by FlightStream command name.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fs_version: str
    flags: dict[str, FlagRecord]

    def explicit_kwargs(self) -> dict[str, object]:
        """Return the helper keywords that reproduce the explicit flags.

        Only ``explicit`` records are reconstructed: the library
        defaults (the minimum-Cp emission) are regenerated by
        :func:`pyflightstream.script.helpers.solver_settings` itself,
        so a snapshot replays to the same emitted lines without ever
        freezing a library default as if the user had chosen it.

        Returns
        -------
        dict of str to object
            Keyword arguments for
            :func:`pyflightstream.script.helpers.solver_settings`.
        """
        kwargs: dict[str, object] = {}
        for name, record in self.flags.items():
            if record.provenance != _EXPLICIT:
                continue
            spec = _SPEC_BY_COMMAND.get(name)
            if spec is None:
                raise ValueError(
                    f"snapshot flag {name!r} has no solver_settings parameter; the "
                    "snapshot model and the helper must cover the same flag set "
                    "(see FLAG_SPECS in pyflightstream.script.solver_setup)"
                )
            if spec.kind == "mode_steady":
                kwargs["mode"] = "STEADY"
            elif spec.kind == "mode_unsteady":
                value = dict(record.value)  # type: ignore[arg-type]
                kwargs["mode"] = "UNSTEADY"
                kwargs["time_iterations"] = value["time_iterations"]
                kwargs["delta_time"] = value["delta_time"]
            elif spec.kind == "bulk_separation":
                kwargs[spec.param] = BulkSeparation.model_validate(record.value)
            else:
                kwargs[spec.param] = record.value
        return kwargs

    def provenance_counts(self) -> dict[str, int]:
        """Return how many flags carry each provenance marker."""
        counts = {_EXPLICIT: 0, _DEFAULT: 0, _UNKNOWN: 0}
        for record in self.flags.values():
            counts[record.provenance] += 1
        return counts


def _normalize(value: object) -> JsonValue:
    """Return ``value`` with sequences turned into JSON-stable lists."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        return value  # type: ignore[return-value]
    return [_normalize(item) for item in value]


def _minimum_cp_evidence(entry: CommandEntry) -> str:
    """Compose the citation trail of the emitted library minimum-Cp."""
    return (
        f"library default {LIBRARY_MINIMUM_CP} (author decision of 2026-07-22; physics "
        "references re-validated under it, 30 of 30 metrics bit-identical, report "
        f"PHY-26120_2026-07-23_reseed-cp100-2026-07-23); solver default {entry.default} "
        f"({entry.default_ref})"
    )


def _family_record(
    spec: FlagSpec,
    entry: CommandEntry,
    passed: Mapping[str, object],
    *,
    available: bool,
    minimum_cp_default_emitted: bool,
) -> FlagRecord:
    """Build the snapshot record of one settings-family command."""
    base = {"command": entry.name, "family": entry.chapter}
    if spec.kind == "mode_steady":
        if passed.get("mode") == "STEADY":
            return FlagRecord(**base, provenance=_EXPLICIT, value=True, emitted=True)
    elif spec.kind == "mode_unsteady":
        if passed.get("mode") == "UNSTEADY":
            value = {
                "time_iterations": passed["time_iterations"],
                "delta_time": passed["delta_time"],
            }
            return FlagRecord(**base, provenance=_EXPLICIT, value=value, emitted=True)
    elif spec.kind == "bulk_separation":
        bulk = passed.get("bulk_separation")
        if bulk is not None:
            assert isinstance(bulk, BulkSeparation)
            value = bulk.model_dump(mode="json")
            return FlagRecord(**base, provenance=_EXPLICIT, value=value, emitted=True)
    else:
        value = passed.get(spec.param)
        if value is not None:
            return FlagRecord(**base, provenance=_EXPLICIT, value=_normalize(value), emitted=True)
        if entry.name == "SOLVER_MINIMUM_CP" and minimum_cp_default_emitted:
            return FlagRecord(
                **base,
                provenance=_DEFAULT,
                value=LIBRARY_MINIMUM_CP,
                emitted=True,
                evidence=_minimum_cp_evidence(entry),
            )
        if entry.default is not None and available:
            return FlagRecord(
                **base,
                provenance=_DEFAULT,
                value=entry.default,
                emitted=False,
                evidence=entry.default_ref,
            )
    return FlagRecord(**base, provenance=_UNKNOWN, value=None, emitted=False)


def with_vorticity_selection(
    setup: SolverSetup,
    selection: Sequence[int] | Literal["all"],
) -> SolverSetup:
    """Return the snapshot with the induced-drag selection replaced.

    Helper-facing like :func:`build_setup`, and deliberately outside
    ``__all__``: the snapshot is built by the curated helpers, never
    hand-stamped by a caller.

    The deprecated
    :func:`pyflightstream.script.helpers.analysis_setup` selection path
    emits its own SET_VORTICITY_DRAG_BOUNDARIES after the settings call
    already built the snapshot. Restamping the record keeps the manifest
    describing the script that will actually run: a snapshot that says
    "no selection" while the script selects boundaries would be the
    provenance record lying about its own script.

    Parameters
    ----------
    setup : SolverSetup
        Snapshot built by the settings call.
    selection : sequence of int, or ``"all"``
        Boundaries the later call selected, as resolved 1-based
        indices, the same vocabulary the settings call records.

    Returns
    -------
    SolverSetup
        A new snapshot; the input is left untouched (the model is
        frozen).
    """
    record = setup.flags[VORTICITY_COMMAND].model_copy(
        update={
            "provenance": _EXPLICIT,
            "value": _normalize(selection),
            "emitted": True,
            "evidence": None,
        }
    )
    return setup.model_copy(update={"flags": {**setup.flags, VORTICITY_COMMAND: record}})


def _vorticity_record(
    entry: CommandEntry,
    passed: Mapping[str, object],
    *,
    available: bool,
) -> FlagRecord:
    """Build the snapshot record of the induced-drag boundary selection.

    The selection is optional, so its record has two shapes. A passed
    selection is ``explicit`` and emitted (deferred to the analysis
    phase). No selection is the documented solver behavior rather than
    an absence of knowledge: the script places no boundary on the
    vorticity CDi list, and boundaries outside that list keep the
    surface pressure integration of the solver, a complete induced-drag
    calculation (SRC-003 p.202). That case is recorded as a ``default``
    carrying the empty selection, so a reader of the manifest sees that
    the script selected no boundary instead of an unexplained blank.
    The record describes the script, not the session: a simulation file
    opened by the script can carry a selection of its own, the same
    caveat the module docstring states for the settings families. On a
    FlightStream version without the command the library claims
    nothing: per-version facts need the command to exist.
    """
    base = {"command": entry.name, "family": entry.chapter}
    selection = passed.get("vorticity_drag_boundaries")
    if selection is not None:
        return FlagRecord(**base, provenance=_EXPLICIT, value=_normalize(selection), emitted=True)
    if available:
        return FlagRecord(
            **base,
            provenance=_DEFAULT,
            value=[],
            emitted=False,
            evidence=(
                "the script emits no selection, so it places no boundary on the "
                "vorticity CDi list; boundaries outside that list use the solver's "
                "surface pressure integration (SRC-003 p.202). A simulation file "
                "opened by the script may carry a selection of its own"
            ),
        )
    return FlagRecord(**base, provenance=_UNKNOWN, value=None, emitted=False)


def build_setup(
    *,
    version: str,
    passed: Mapping[str, object],
    minimum_cp_default_emitted: bool,
) -> SolverSetup:
    """Build the snapshot of one solver_settings call.

    Called by :func:`pyflightstream.script.helpers.solver_settings`
    after its emissions succeeded; the snapshot covers every command of
    the three settings families whether passed or not, so nothing is
    silently missing from the record.

    Parameters
    ----------
    version : str
        FlightStream version of the script, canonical or alias.
    passed : mapping of str to object
        The helper keywords exactly as received (None meaning not
        passed), plus the validated ``bulk_separation`` model, the
        upper-cased ``mode``, and the effective
        ``vorticity_drag_boundaries`` selection: labels already
        resolved to indices, and carried forward from an earlier
        settings call of the same script when this one omitted it,
        because the snapshot describes the script rather than the
        single call.
    minimum_cp_default_emitted : bool
        Whether the helper emitted the library minimum-Cp default (it
        does whenever ``minimum_cp`` was not passed and the command
        exists in the version).

    Returns
    -------
    SolverSetup
        The snapshot, ready to attach to the script.

    Raises
    ------
    RuntimeError
        If a command of the three families has no snapshot flag; the
        model must never silently lag the command database.
    """
    registry = CommandRegistry.load()
    view = registry.for_version(version)
    flags: dict[str, FlagRecord] = {}
    for name, entry in registry.commands.items():
        if entry.chapter not in SNAPSHOT_FAMILIES:
            continue
        spec = _SPEC_BY_COMMAND.get(name)
        if spec is None:
            raise RuntimeError(
                f"command {name} of family {entry.chapter} has no solver-setup flag; "
                "extend FLAG_SPECS and the solver_settings signature in "
                "pyflightstream.script (the snapshot must cover every command of the "
                "three settings families, or the provenance record would silently lag "
                "the command database)"
            )
        flags[name] = _family_record(
            spec,
            entry,
            passed,
            available=name in view,
            minimum_cp_default_emitted=minimum_cp_default_emitted,
        )
    flags[VORTICITY_COMMAND] = _vorticity_record(
        registry.commands[VORTICITY_COMMAND],
        passed,
        available=VORTICITY_COMMAND in view,
    )
    return SolverSetup(fs_version=resolve(version).canonical, flags=flags)


def script_from_setup(script: Script, setup: SolverSetup) -> SolverSetup:
    """Regenerate the settings portion of a script from a snapshot.

    Replays the explicit flags of ``setup`` through
    :func:`pyflightstream.script.helpers.solver_settings`, so the
    emitted settings lines (including the library minimum-Cp default
    and the deferred induced-drag selection) are identical to the ones
    the original call produced, and a fresh snapshot is attached to the
    script. Boundary labels stored in the snapshot need the same
    declarations (:meth:`~pyflightstream.script.Script.declare_existing`)
    on the target script.

    Replay onto a fresh script: the induced-drag selection is the one
    flag with per-script rather than per-call lifetime, so a target
    script that already carries a selection keeps it, and the returned
    snapshot then records that selection instead of the stored one.
    The campaign loop builds one script per point, which is the shape
    this function is written for.

    Parameters
    ----------
    script : Script
        Script under construction, bound to a FlightStream version in
        which every explicit flag of the snapshot exists; fresh, per
        the note above.
    setup : SolverSetup
        Stored snapshot, for example
        ``SolverSetup.model_validate_json(...)`` of a manifest record.

    Returns
    -------
    SolverSetup
        The fresh snapshot of the regenerated call.
    """
    from pyflightstream.script import helpers  # local: helpers imports this module

    return helpers.solver_settings(script, **setup.explicit_kwargs())
