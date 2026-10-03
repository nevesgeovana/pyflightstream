"""Preset binding and the context shared by matrix resolution phases."""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import Campaign, InputKey, SimCase, SolverSettings
from pyflightstream.cases.matrix import MatrixRow
from pyflightstream.workspace import (
    CampaignWorkspace,
    InputArtifactError,
    PprocArtifact,
    ReferenceArtifact,
    SetupArtifact,
)
from pyflightstream.workspace._row_setup import resolve_stabilization, row_setup
from pyflightstream.workspace.flight_condition import (
    PINNED_KEYS,
    ResolvedCondition,
    canonical_condition_defaults,
)
from pyflightstream.workspace.fsi_setup import ResolvedFsiSetup
from pyflightstream.workspace.inputs import FLAGS_TABLE, RAW_TABLE, RegisteredBuild


@dataclass(frozen=True)
class ResolvedMatrix:
    """A matrix bound to a workspace input library, ready to plan or run.

    Attributes
    ----------
    campaign : Campaign
        The canonical campaign form, with the resolved reference data
        applied to each case (``reference``), the solver preset applied
        to each case's runtime settings (``solver``), and the resolved
        library path of the row's ``GEOMETRY`` applied to each case's
        ``geometry`` where the row named one; the historical codes and
        the ``GEOMETRY`` stem itself stay in the case variables, so
        nothing of the matrix is lost.
    conditions : dict of str to ResolvedCondition
        The resolved flow state of every row that STATED a flight
        condition, keyed by POL (PFS-2027.02, .04). A row that states
        none has no entry, which is not the same as an empty one.

        It rides here rather than on the case because a case is not a
        record: the density, the temperature, the viscosity, the length
        the Reynolds number was measured against and WHICH branch
        produced the density are what the run record must carry so a
        reader can recompute the resolution rather than trust it.
    references : dict of str to ReferenceArtifact
        Resolved reference-data artifacts, keyed by REF code.
    setups : dict of str to SetupArtifact
        Resolved solver-setup presets, keyed by SET code; the raw
        preset table is kept verbatim for consumers beyond the runtime
        subset (see :func:`resolve_matrix`).
    pprocs : dict of str to PprocArtifact
        Resolved post-processing artifacts, keyed by PPROC code; group members
        are boundary labels or indices, verbatim, for the script layer
        and the post-processing aggregation.
    fs_exe : Path
        The executable the CAMPAIGN ITSELF binds to, which is the one
        answering for rows whose FS_BUILD cell names no build;
        existence is checked by the executor at construction, not here.

        Its meaning is unchanged by the multi-build support added at
        PFS-2009.05, deliberately, because everything downstream reads
        it as the campaign's own installation. Where several builds are
        in play, ``builds`` below is what says which executable each
        row's own build is; where only one is, the two agree and this
        field is that one.

        Where no active row names a build, the campaign default answers
        for every row and this is its executable. Where EVERY active row
        names one, no row runs on the campaign's own installation at
        all, and this field takes the first active row's build rather
        than the default's, so it still names an installation this
        matrix really uses instead of one that would merely have to be
        registered.
    builds : dict of str to RegisteredBuild
        The registry entry of each build id an active row NAMES, keyed
        by that id: its executable and the version it declares, or None
        where it declares none. Empty under the explicit ``fs_exe``
        override, which overrules the column, and empty for a matrix
        whose every active row is silent, because neither names a
        build.

        A build id appears here whether or not it is also the campaign
        default: what puts it here is a row naming it, which is the same
        condition that puts a non-None entry in ``row_builds``.
    row_builds : tuple of (str or None)
        Where each case's build came from, one entry per case of
        ``campaign.sims`` and in the same order: the build id the ROW's
        FS_BUILD cell named, or None when the cell named none and the
        campaign default answered for it (PFS-2009.08.02).

        It is the ONE fact only this function knows. ``fs_exe`` says
        WHICH installation was selected, and by the time a manifest
        record is written nothing can still tell whether the row asked
        for it or inherited it, because both arrive as the same
        executable. :func:`pyflightstream.run.matrix.run_matrix` turns
        each entry into :attr:`pyflightstream.cases.SimCase.fs_build`
        and the matching ``builds`` mapping, which is what makes the
        record's ``fs_version_source`` say ``row`` rather than
        ``campaign_default``.

        Every entry is None under an explicit ``fs_exe`` override, and
        that is a statement rather than a gap: the override runs every
        point on one caller-named executable and overrules whatever the
        cells said, which is exactly what the warning it raises says
        will be recorded.
    additional_pprocs : dict of str to PprocArtifact
        The additional pproc of every row stating ``ADDITIONAL_PPROC`` (G12 of
        0.27.0), keyed by its id, resolved and judged at plan so a key the
        additional post could not honour is refused before the run spends a
        seat. Empty for a matrix whose rows state none. LAST, so a caller
        building this by position keeps working.
    """

    campaign: Campaign
    conditions: dict[str, ResolvedCondition] = field(default_factory=dict)
    references: dict[str, ReferenceArtifact] = field(default_factory=dict)
    setups: dict[str, SetupArtifact] = field(default_factory=dict)
    pprocs: dict[str, PprocArtifact] = field(default_factory=dict)
    fs_exe: Path = Path()
    builds: dict[str, RegisteredBuild] = field(default_factory=dict)
    row_builds: tuple[str | None, ...] = ()
    additional_pprocs: dict[str, PprocArtifact] = field(default_factory=dict)
    fsis: dict[str, ResolvedFsiSetup] = field(default_factory=dict)


#: Preset spellings that name a :class:`SolverSettings` field under a
#: different word, and the field they name.
#:
#: These are the SOLVER's own key names, which is what a preset
#: transcribed from a working FlightStream session carries. The library
#: field names follow the emitter's keyword arguments instead, so the
#: two vocabularies genuinely differ and neither is the wrong one. The
#: alias table is where they meet, and it is a table rather than a
#: rename so the file a user already has keeps working.
_PRESET_ALIASES = {
    "NITER": "iterations",
    "boundary_layer_type": "boundary_layer",
    "max_parallel_threads": "max_threads",
    "set_solver_model": "solver_model",
    "proximity_avoidance": "wall_collision_avoidance",
    "solver_minimum_cp": "minimum_cp",
    "induced_wake_velocity": "mesh_induced_wake_velocity",
    "unsteady_pressure_kutta": "unsteady_pressure_and_kutta",
    "additional_wake_relaxation_iteration": "additional_wake_relaxation",
    "reynolds_averaged_drag_forces": "reynolds_averaged_drag",
    "unsteady_N_revolutions_wake": "wake_termination_revolutions",
    # The settings the reference scripts state and 0.10.1 did not emit (FR-54).
    "reference_velocity_mps": "reference_velocity_m_per_s",
    "vorticity_drag_boundaries": "vorticity_drag_families",
    "set_vorticity_drag_boundaries": "vorticity_drag_families",
    # The selections of the loads analysis (G09 of 0.27.0), by the command's name.
    "set_solver_analysis_boundaries": "analysis_families",
    "set_loads_and_moments_units": "load_units",
    "set_inviscid_loads": "inviscid_loads",
    # G14 of 0.27.0, by the command's name.
    "set_vorticity_lift_model": "vorticity_lift_model",
    "set_unsteady_viscous_coupling_iteration": "unsteady_viscous_coupling_iteration",
}

#: Preset keys that are RECORDED and deliberately emit nothing, each
#: with the reason, which is printed when a reader asks why.
#:
#: This set is the difference between "we read your file" and "we read
#: the part of your file we happened to have a field for". A key here
#: is a decision; a key in neither this set nor the alias table nor the
#: model is a REFUSAL, because silently dropping a solver setting is how
#: a run answers a question nobody asked.
#: The tables a setup artifact is refused for naming, because they are
#: post-processing and the pproc artifact is their home (PFS-2029.16).
_POST_PROCESSING_KEYS = ("sections", "plots", "probes", "products", "exports", "groups")

_PRESET_RECORDED_ONLY = {
    "solver": (
        "the run TYPE, which the matrix WORKFLOW column names: a preset shared by "
        "several rows cannot decide whether one of them is steady"
    ),
    "motion": ("the motion type, which the workflow creates from the row's own rotor keys"),
    "symmetry_type": (
        "symmetry describes what was MESHED, so it belongs to the row's geometry and "
        "is stated in the row's SYMMETRY key; a preset value would silently overrule "
        "the mesh it knows nothing about"
    ),
    # `symmetry_loads` LEFT THIS TABLE on 2026-09-02, the design decision (PFS-2028.05)
    # with the measurement in hand: the 0.10.1 reproduction of the reference isolated
    # rotor reported loads six times the reference because the reference preset stated the
    # symmetry loads off and nothing was emitted. A STATED key now reaches
    # SET_ANALYSIS_SYMMETRY_LOADS as stated; an absent key still emits nothing.
    "unsteady_delta_theta_deg": (
        "superseded by the row's DELTA_THETA, which is where the azimuthal step is "
        "stated now that the clock is derived from it"
    ),
    "unsteady_N_revolutions": ("superseded by the row's REVOLUTIONS, for the same reason"),
    "set_base_region_trailing_edges": (
        "a separation model that selects boundaries, and a preset carries no boundary "
        "selection; state it in a recipe"
    ),
    "wake_layers": "no emitter in this package",
}

#: Reserved preset key by which a FILE declares its own recorded-only
#: keys, as a list of names.
#:
#: The library table above covers the keys the library knows about, and
#: it cannot cover a setting from a solver build or a workflow nobody
#: here has seen. Without this, such a key would be refused with no way
#: forward except editing the library, so the decision is handed to the
#: person who wrote the file: name the key here and it is kept, emits
#: nothing, and says so. What it is NOT is a way to be quiet about it:
#: a declared key still warns on every resolve, because the whole point
#: is that the user knows their setting is not reaching the solver.
_PRESET_RECORDED_ONLY_KEY = "recorded_only"

#: The table a setup carries for the FLIGHT CONDITION rather than for the
#: solver (PFS-2030.08). It is not a solver setting and is consumed before
#: the key loop that would otherwise refuse it as one; its contents are
#: judged by the resolver, which owns the pin vocabulary.
_FLIGHT_CONDITION_TABLE = "flight_condition"

#: The two preset tables above, read-only and public, for the generated
#: input glossary ``INPUTS.md`` (G08 of 0.27.0): the solver's own spelling
#: to the field it names, and each recorded-only key to its reason.
PRESET_ALIASES: Mapping[str, str] = MappingProxyType(_PRESET_ALIASES)
PRESET_RECORDED_ONLY: Mapping[str, str] = MappingProxyType(_PRESET_RECORDED_ONLY)

#: THE KEYS A PRESET MAY STATE THAT ARE NOT SOLVER SETTINGS, each with what it
#: holds, for the same glossary. Every one of them is consumed before the loop
#: that refuses a key naming no setting (:func:`_solver_from_setup`, and
#: :func:`pyflightstream.workspace.inputs.resolve_setup` for the two tables).
#: The tables a preset is refused for naming since 0.15.0, ``[[frames]]`` and
#: ``[aliases]``, are not here: their home is the reference.
PRESET_RESERVED_KEYS: Mapping[str, InputKey] = MappingProxyType(
    {
        _PRESET_RECORDED_ONLY_KEY: InputKey(
            "The keys of this preset to keep in the artifact and emit nowhere; each "
            "still warns, naming itself.",
            "a list of key names",
        ),
        _FLIGHT_CONDITION_TABLE: InputKey(
            "Fluid pins every row naming this setup inherits; a row stating one wins over it.",
            "a table of the pins below",
        ),
        "stabilization": InputKey(
            "Switches the stabilization whose strength stabilization_strength states; "
            "disabled, nothing is emitted.",
            "true or false, or ENABLE or DISABLE; beside solver_stabilization, refused",
            "SOLVER_STABILIZATION",
        ),
        "stabilization_strength": InputKey(
            "The strength of the stabilization the key above switches.",
            "a number",
            "SOLVER_STABILIZATION",
        ),
        RAW_TABLE: InputKey(
            "Solver command lines stated verbatim, every row naming this setup emitting "
            "each before the phase it names.",
            "an array of tables; see `[[raw]]` below",
        ),
        FLAGS_TABLE: InputKey(
            "Solver commands this setup exposes to the matrix under a word, the row "
            "stating the value.",
            "an array of tables; see `[[flags]]` below",
        ),
    }
)


def condition_defaults_origin(set_code: str) -> str:
    """Name the setup a defaults table came from, id AND path.

    One home, because it is written in a refusal the user acts on and
    recorded on the resolved state, and an interface review found the two
    disagreeing by two quote characters. THE PATH IS THE POINT: an id
    tells a reader WHICH artifact is wrong and not which of a dozen files
    under ``inputs/setups/`` to open.
    """
    return f"setup {set_code!r} (inputs/setups/{set_code}.toml)"


def _condition_defaults(setup: SetupArtifact, set_code: str) -> dict[str, float]:
    """Read a setup's flight-condition defaults, refusing what is not a number.

    WHAT THIS FUNCTION DECIDES AND WHAT IT DOES NOT. It decides the
    SHAPE: that the key names a table and that every value in it is a
    finite number. It does NOT decide which keys may appear, because that
    is the pin vocabulary and it lives with the resolver that owns it; it
    CALLS that rule rather than restating it
    (:func:`~pyflightstream.workspace.flight_condition.canonical_condition_defaults`),
    so a key added to the pins is accepted here the day it is added
    there, with no second list to move.

    IT CALLS IT HERE, once per setup, and that placement is the finding
    of an architecture review on 2026-09-04 rather than a preference:
    while the vocabulary was judged only inside the resolver, it ran once
    per ROW THAT STATED A CONDITION, so one file was legal or illegal
    depending on other rows' cells.

    Two exception classes leave this function, and the split is the one
    the rest of the package makes: a malformed FILE is an
    ``InputArtifactError``, and a well-formed file stating the wrong
    CONSTANT is a ``FlightConditionError`` from the rule above.

    A bool is excluded on its own line because it is an int in Python, so
    ``MUPas = true`` would otherwise pin a viscosity of 1.0.
    """
    table = setup.settings.get(_FLIGHT_CONDITION_TABLE)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise InputArtifactError(
            f"setup preset {set_code!r} states {_FLIGHT_CONDITION_TABLE} as {table!r}, "
            f"and it is a TABLE of flight-condition pins, for example "
            f"[{_FLIGHT_CONDITION_TABLE}] with MUPas = 1.789e-5 under it."
        )
    defaults: dict[str, float] = {}
    for key, value in table.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputArtifactError(
                f"setup preset {set_code!r} states {_FLIGHT_CONDITION_TABLE}.{key} as "
                f"{value!r}, and a flight-condition pin is a number."
            )
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise InputArtifactError(
                f"setup preset {set_code!r} states {_FLIGHT_CONDITION_TABLE}.{key} as "
                f"{value!r}, which is not a finite number. A fluid constant cannot be "
                "stated as a NaN or an infinity, and one would otherwise reach the "
                "emitted script unrefused."
            )
        defaults[key] = number
    return canonical_condition_defaults(defaults, condition_defaults_origin(set_code))


def _validate_setup_ports(settings: dict, set_code: str) -> None:
    ports = settings.get("ports", ())
    if not isinstance(ports, (list, tuple)):
        raise InputArtifactError(f"setup {set_code!r}: write ports as [[ports]] array tables")
    for entry in ports:
        if not isinstance(entry, dict) or not entry.get("port") or not entry.get("kind"):
            raise InputArtifactError(
                f"setup {set_code!r}: [[ports]] requires port and kind; map the identity "
                "to its surface in boundaries.toml and put condition values in MATRIX."
            )
        if any(key in entry for key in ("boundary", "velocity", "profile", "profile_sha256")):
            raise InputArtifactError(
                f"setup {set_code!r}: [[ports]] selects velocity_variable/profile_variable; "
                "surface identity belongs to boundaries.toml and condition values to MATRIX."
            )


def _recorded_names(settings: dict, set_code: str) -> set[str]:
    declared = settings.pop(_PRESET_RECORDED_ONLY_KEY, None)
    if declared is None:
        declared_names: set[str] = set()
    elif isinstance(declared, (list, tuple)) and all(isinstance(name, str) for name in declared):
        declared_names = {str(name) for name in declared}
    else:
        raise InputArtifactError(
            f"setup preset {set_code!r} states {_PRESET_RECORDED_ONLY_KEY} as "
            f"{declared!r}, and it is a list of key NAMES, for example "
            f"{_PRESET_RECORDED_ONLY_KEY} = ['my_setting']."
        )
    return declared_names


def _match_settings(
    settings: dict, set_code: str, declared_names: set[str]
) -> tuple[dict[str, object], list[str], list[str]]:
    known = set(SolverSettings.model_fields)
    matched: dict[str, object] = {}
    if "mesh_order_list" in settings:
        # PFS-2029.06.01. Until 0.11.0 the key was recorded-only: kept,
        # warned about, never emitted. Recorded-only was the wrong answer
        # for the one key whose value is CHECKABLE against the file it
        # describes, because a preset several geometries share cannot
        # state the order of any one of them, and a wrong order that is
        # merely warned about is read as documentation by the next reader.
        raise InputArtifactError(
            f"setup preset {set_code!r} states mesh_order_list, which is the boundary "
            "order of one mesh and belongs beside that mesh, not in a preset several "
            "geometries share. Write it from the file itself: `pyfs-matrix inventory "
            "inputs/geometries/<file>` reads the mesh block and writes "
            "<stem>.boundaries.toml beside the geometry, and the run refuses a sidecar "
            "that disagrees with the file (PFS-2029.06). Remove the key from the setup."
        )
    refused: list[str] = []
    recorded: list[str] = []
    spelled: dict[str, str] = {}
    for key, value in settings.items():
        field = _PRESET_ALIASES.get(key, key)
        if field in known:
            # TWO SPELLINGS OF ONE SETTING ARE REFUSED. They are distinct TOML
            # keys, so the file parses, and both map onto one field: assigning
            # let the one the file lists LAST win, and reordering two lines of a
            # preset changed the solve with nothing saying so.
            if field in spelled:
                raise InputArtifactError(
                    f"setup preset {set_code!r} states the solver setting {field!r} "
                    f"twice, as {spelled[field]!r} and as {key!r}, which are two "
                    "spellings of one setting. Keep the one the preset means and "
                    "remove the other."
                )
            spelled[field] = key
            matched[field] = value
        elif key in _PRESET_RECORDED_ONLY or key in declared_names:
            recorded.append(key)
        else:
            refused.append(key)
    return matched, refused, recorded


def _refuse_setup_keys(refused: list[str], set_code: str) -> None:
    known = set(SolverSettings.model_fields)
    near_miss = sorted(
        key
        for key in refused
        if key.strip().lower().replace("-", "_").replace(" ", "_").rstrip("s")
        == _FLIGHT_CONDITION_TABLE.rstrip("s")
    )
    if near_miss:
        # A MISSPELLING OF THE TABLE MUST NOT BE ANSWERED BY THE GENERIC
        # REFUSAL, and an interface review found why on 2026-09-04. That
        # message calls the key a solver setting, which this table is
        # explicitly not, and its closing sentence offers `recorded_only`
        # as the remedy -- which would make the table legal, silent and
        # INERT, four pinned fluid constants reaching no script, on a
        # surface whose whole premise is that a silent drop costs a
        # result.
        raise InputArtifactError(
            f"setup preset {set_code!r} states key(s) {', '.join(near_miss)}, which "
            f"look like the flight-condition table misspelled. That table is spelled "
            f"exactly [{_FLIGHT_CONDITION_TABLE}] and holds the fluid pins "
            f"({', '.join(PINNED_KEYS)}) every row naming this setup inherits. Rename "
            f"it. Do NOT name it in {_PRESET_RECORDED_ONLY_KEY}: that would make it "
            "legal, silent and inert, and the constants under it would reach no "
            "script."
        )
    post_processing = sorted(set(refused) & set(_POST_PROCESSING_KEYS))
    if post_processing:
        # PFS-2029.16: a setup artifact carries solver settings only. The reference
        # SET files carried a second table of post-processing, and that
        # table's home is the pproc artifact the row's PPROC cell names.
        raise InputArtifactError(
            f"setup preset {set_code!r} states key(s) {', '.join(post_processing)}, "
            "which name post-processing, not a solver setting. Post-processing does "
            "not belong in a setup artifact: sections, plots, probes, products, "
            "exports and groups live in the pproc artifact the row's PPROC cell names "
            "(inputs/pproc/p001.toml, PFS-2029.07). Move the table there."
        )
    if refused:
        # THE CONSUMED KEYS BELONG IN THE LIST. `stabilization`,
        # `stabilization_strength` and the reserved `recorded_only` are
        # all accepted and are all taken out of `settings` before this
        # loop, so the first version of this message refused
        # `stabilisation` with a list of "keys that apply" that did not
        # contain the word its writer meant, which is the one case where
        # the list is the whole value of the refusal.
        available = sorted(
            known
            | set(_PRESET_ALIASES)
            | {
                "stabilization",
                "stabilization_strength",
                _PRESET_RECORDED_ONLY_KEY,
                _FLIGHT_CONDITION_TABLE,
            }
        )
        raise InputArtifactError(
            f"setup preset {set_code!r} states key(s) {', '.join(sorted(refused))}, "
            "which name no solver setting this package can emit and are not declared "
            "as recorded-only. A key that reaches no script would change nothing about "
            "the run while reading as though it had, so it is refused rather than "
            f"dropped. The keys that apply are: {', '.join(available)}. The keys this "
            "package already records without emitting are: "
            f"{', '.join(sorted(_PRESET_RECORDED_ONLY))}. If the setting really is one "
            "this package cannot emit and you want it kept in the artifact anyway, "
            f"name it in {_PRESET_RECORDED_ONLY_KEY} in the preset file."
        )


def _warn_recorded_settings(recorded: list[str], set_code: str) -> None:
    if recorded:
        # THE WARNING SURVIVES, and it is the useful half now that the
        # silent drop is gone: the keys it lists are exactly the ones an
        # user might still believe reached the solver.
        reasons = ", ".join(
            f"{key} ({_PRESET_RECORDED_ONLY.get(key, 'declared recorded-only by this preset')})"
            for key in sorted(recorded)
        )
        warnings.warn(
            f"setup preset {set_code!r}: key(s) {reasons} are RECORDED in the artifact "
            "and emit nothing, so the solver takes its own default for each. Every "
            "other key of this preset reaches the script.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _solver_from_setup(setup: SetupArtifact, set_code: str) -> SolverSettings:
    """Map one preset onto the case solver settings, refusing what it cannot.

    Three outcomes per key, and the third is the change. A key that
    names a :class:`~pyflightstream.cases.SolverSettings` field, or an
    alias of one, APPLIES. A key declared recorded-only is kept in the
    artifact and emits nothing, on the stated ground written beside it.
    Anything else is REFUSED, naming the key and what is available.

    UNTIL THIS RELEASE THE THIRD CASE WAS A WARNING AND A SILENT DROP,
    and that is the defect this closes. A preset asking for
    ``SUBSONIC_PRANDTL_GLAUERT`` ran INCOMPRESSIBLE and a preset asking
    for a turbulent boundary layer ran the solver's default. Each of
    those is a run that converges, exports and publishes numbers against
    a physics nobody selected. A refusal costs an edit; a silent drop
    costs a result.

    ``NITER`` WAS IN THE SAME POSITION AND IS DELIBERATELY NOT OFFERED
    as a third instance: the campaign that surfaced this states 500 and
    the model default is 500, so both of its runs emitted the same line
    and it cannot be demonstrated from them. An earlier version of this
    docstring listed it beside the other two, which made an unmeasured
    instance read like a measured one.
    """
    settings = dict(setup.settings)
    _validate_setup_ports(settings, set_code)
    declared_names = _recorded_names(settings, set_code)
    # THE PAIR IS CONSUMED BEFORE THE LOOP, so neither half reaches the
    # recorded-only report. An earlier version left them in it, and the
    # warning then told a user that a stabilization they had switched
    # ON emitted nothing, while the strength was in fact reaching the
    # script. A message that names the wrong outcome is worse than none.
    # THE FLIGHT-CONDITION TABLE IS CONSUMED HERE, for the same reason
    # the pair below it is: it is accepted, it is not a solver setting,
    # and a key left in `settings` reaches the loop that refuses anything
    # naming no setting this package can emit. `_condition_defaults`
    # reads it from the artifact, so nothing is lost by dropping it.
    # Its CONTENTS are read by `_condition_defaults` above, and the two
    # are load-bearing on each other through this constant alone: delete
    # this pop and a valid file is refused, delete that read and valid
    # pins are silently ignored.
    settings.pop(_FLIGHT_CONDITION_TABLE, None)
    if "solver_stabilization" in settings and (
        "stabilization" in settings or "stabilization_strength" in settings
    ):
        raise InputArtifactError(
            f"setup preset {set_code!r} states solver_stabilization alongside "
            "stabilization or stabilization_strength, which are two declarations of "
            "one solver setting. Keep the direct strength or the gated pair, not both."
        )
    stabilization = resolve_stabilization(settings, set_code)
    gated = "stabilization" in settings or "stabilization_strength" in settings
    settings.pop("stabilization", None)
    settings.pop("stabilization_strength", None)
    matched, refused, recorded = _match_settings(settings, set_code, declared_names)
    _refuse_setup_keys(refused, set_code)
    _warn_recorded_settings(recorded, set_code)
    if stabilization is not None:
        matched["solver_stabilization"] = stabilization
    elif gated:
        warnings.warn(
            f"setup preset {set_code!r}: stabilization is DISABLED, so no "
            "stabilization strength is emitted and the solver takes its own default. "
            "A disabled stabilization is an absent one and not a strength of zero, "
            "which would still be switched on.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    try:
        # `model_validate` AND NOT `SolverSettings(**matched)`. The dict is
        # `dict[str, object]` by construction, because a preset table is
        # untyped until it is validated, and unpacking it as keywords
        # typechecks `object` against every field: the checker could not
        # see that any preset value had the right type, on the one call
        # whose whole purpose is that preset values reach solver fields.
        # Passing the mapping is the same validation and it is typed.
        return SolverSettings.model_validate(matched)
    except ValidationError as error:
        raise InputArtifactError(
            f"setup preset {set_code!r} does not fit the case solver settings: {error}"
        ) from error


#: The row-setup resolver bound to this module's preset loader and alias table.
_setup_of_the_row = partial(row_setup, aliases=_PRESET_ALIASES, loader=_solver_from_setup)


def _port_profile(
    variables: Mapping[str, Any], profile_variable: str, inputs_dir: Path
) -> dict[str, str]:
    profile_value = variables.get(profile_variable)
    if not profile_value or not isinstance(profile_value, str):
        raise InputArtifactError(f"MATRIX must state profile {profile_variable}")
    folder = (inputs_dir / "profiles").resolve()
    profile = (folder / profile_value).resolve()
    if not profile.is_relative_to(folder) or not profile.is_file() or not profile.stat().st_size:
        raise InputArtifactError(
            f"MATRIX profile is missing, empty or outside inputs/profiles: {profile_value}"
        )
    return {"profile": str(profile), "profile_sha256": file_sha256(profile)}


def _bind_setup_ports(case: SimCase, inputs_dir: Path) -> SimCase:
    """Bind setup port selections to geometry identities and this row's MATRIX values."""
    if not case.solver.ports:
        return case
    conditions = case.raw_mesh_conditions
    identities = {} if conditions is None else conditions.ports
    bound = []
    seen: set[str] = set()
    for entry in case.solver.ports:
        if entry.port is None or entry.kind is None or entry.port not in identities:
            raise InputArtifactError(
                f"case {case.sim_id}: setup port {entry.port!r} is absent from geometry [ports]"
            )
        boundary = identities[entry.port]
        if boundary in seen:
            raise InputArtifactError(f"boundary {boundary!r} assigned more than once to ports")
        seen.add(boundary)
        variable = entry.velocity_variable or f"{entry.port.upper()}_VELOCITY"
        value = case.variables.get(variable)
        if value is None or isinstance(value, bool):
            raise InputArtifactError(
                f"case {case.sim_id}: MATRIX must state {variable} as a number"
            )
        try:
            velocity = float(value)
        except (ValueError, TypeError) as exc:
            raise InputArtifactError(f"MATRIX {variable} must be a finite number") from exc
        if not math.isfinite(velocity):
            raise InputArtifactError(f"MATRIX {variable} must be a finite number")
        updates: dict[str, Any] = {
            "boundary": boundary,
            "velocity": velocity,
            "velocity_variable": variable,
        }
        if entry.profile_variable is not None:
            updates.update(_port_profile(case.variables, entry.profile_variable, inputs_dir))
        bound.append(entry.model_copy(update=updates))
    solver = case.solver.model_copy(update={"ports": tuple(bound)})
    return case.model_copy(update={"solver": solver})


@dataclass
class _Binding:
    """One resolution's inputs and the values shared by its ordered phases."""

    workspace: CampaignWorkspace
    rows: list[MatrixRow]
    campaign: Campaign
    fs_exe: Path
    builds: dict[str, RegisteredBuild]
    row_builds: tuple[str | None, ...]
    fs_version: str | None
    campaign_version: str
    ignore_missing_families: bool
    references: dict[str, ReferenceArtifact] = field(default_factory=dict)
    setups: dict[str, SetupArtifact] = field(default_factory=dict)
    pprocs: dict[str, PprocArtifact] = field(default_factory=dict)
    solvers: dict[str, SolverSettings] = field(default_factory=dict)
    setup_pins: dict[str, dict[str, float]] = field(default_factory=dict)
    conditions: dict[str, ResolvedCondition] = field(default_factory=dict)
    fsis: dict[str, ResolvedFsiSetup] = field(default_factory=dict)
    additional_pprocs: dict[str, PprocArtifact] = field(default_factory=dict)
    sims: list[SimCase] = field(default_factory=list)
