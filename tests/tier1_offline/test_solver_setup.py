"""Tier 1: solver-setup snapshot, provenance, deferral, and regeneration."""

import inspect
import json
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    CampaignConfigError,
    MeshImport,
    RawMeshConditions,
    ReferenceData,
    SimCase,
    SolverSettings,
    SweepAxis,
    TrailingEdgeMarking,
)
from pyflightstream.cases._setup_link import analysis_frame_and_moments, moments_model_of
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._solver_settings import _settings
from pyflightstream.commands import CommandNotInVersionError, CommandRegistry
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptReferenceError,
    helpers,
    solver_setup,
)
from pyflightstream.script.solver_setup import (
    FLAG_SPECS,
    LIBRARY_MINIMUM_CP,
    SNAPSHOT_FAMILIES,
    VORTICITY_COMMAND,
    AirfoilSeparation,
    AxialVortexSeparation,
    BulkSeparation,
    CylindricalBulkSeparation,
    SolverSetup,
    StratfordBulkSeparation,
    script_from_setup,
    with_vorticity_selection,
)
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace._row_setup import structured_setup_keys
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline._no_evidence import registry_without
from tests.tier1_offline.test_matrix_run import RECIPES as _FR316_ROW_SETUP_KEYS__RECIPES
from tests.tier1_offline.test_matrix_run import make_library as _fr316_row_setup_keys__make_library
from tests.tier1_offline.test_matrix_run import write_matrix as _fr316_row_setup_keys__write_matrix
from tests.tier1_offline.test_workflows import (
    WORKFLOW_KEY as _FR317_FR318_MOMENTS_MODEL__WORKFLOW_KEY,
)
from tests.tier1_offline.test_workflows import rotor_case as _fr317_fr318_moments_model__rotor_case


def family_commands() -> set[str]:
    registry = CommandRegistry.load()
    return {name for name, entry in registry.commands.items() if entry.chapter in SNAPSHOT_FAMILIES}


# --- completeness: the model can never silently lag the database ------------


def test_every_family_command_is_a_snapshot_flag():
    covered = {spec.command for spec in FLAG_SPECS}
    missing = family_commands() - covered
    assert not missing, (
        f"commands {sorted(missing)} of the settings families have no snapshot flag; "
        "extend FLAG_SPECS and solver_settings"
    )


def test_the_snapshot_itself_covers_every_family_command():
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, vorticity_drag_boundaries="all")
    assert set(setup.flags) == family_commands() | {VORTICITY_COMMAND}
    assert setup.fs_version == "26.120"


# --- the two joins the snapshot rests on, neither guarded before -------------


def test_no_command_carries_two_snapshot_flags():
    """`_SPEC_BY_COMMAND` is a dict comprehension: a duplicate wins silently.

    Adding a second row for a command that already has one passes every
    completeness test in this file, because both compare SETS and a
    duplicate changes no set. The later row then replaces the earlier in
    the lookup, so `explicit_kwargs` replays that flag into the wrong
    helper keyword. This became reachable when five parameters started
    carrying two rows each, since one-row-per-command stopped being a
    shape a reader can see at a glance.
    """
    commands = [spec.command for spec in FLAG_SPECS]
    duplicates = sorted({name for name in commands if commands.count(name) > 1})
    assert not duplicates, (
        f"commands {duplicates} carry more than one FlagSpec; _SPEC_BY_COMMAND keeps "
        "the last and the earlier row silently stops existing"
    )


def test_every_snapshot_flag_names_a_real_solver_settings_keyword():
    """The replay path splats `spec.param` into the helper.

    `build_setup` guards the other direction (every family command has a
    spec) and nothing guarded this one. A misspelled `param` surfaces as
    a TypeError at manifest-replay time, on whichever flag happened to
    be explicit, which is the worst moment to learn it. Thirteen
    keywords and eleven rows crossed this join in one change.
    """
    import inspect

    keywords = set(inspect.signature(helpers.solver_settings).parameters) - {"script"}
    params = {spec.param for spec in FLAG_SPECS}
    unknown = sorted(params - keywords)
    assert not unknown, (
        f"FLAG_SPECS names parameters {unknown} that solver_settings does not accept; "
        "SolverSetup.explicit_kwargs would raise TypeError on replay"
    )
    # The reverse, with the two deliberate exceptions named rather than
    # subtracted silently: the unsteady pair rides on the `mode` flag,
    # which records them inside its own value.
    uncovered = sorted(keywords - params - {"time_iterations", "delta_time"})
    assert not uncovered, (
        f"solver_settings accepts {uncovered} with no FlagSpec, so the snapshot cannot "
        "record them; add a row or name the exception here"
    )


# --- provenance markers and evidence ----------------------------------------


def test_provenance_markers_and_default_evidence():
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, aoa=2.0, vorticity_drag_boundaries="all")
    flags = setup.flags
    aoa = flags["SOLVER_SET_AOA"]
    assert aoa.provenance == "explicit" and aoa.value == 2.0 and aoa.emitted
    assert aoa.evidence is None
    minimum_cp = flags["SOLVER_MINIMUM_CP"]
    assert minimum_cp.provenance == "default"
    assert minimum_cp.value == LIBRARY_MINIMUM_CP
    assert minimum_cp.emitted
    assert "FSM-26.120 p.221" in minimum_cp.evidence
    assert "reseed-cp100" in minimum_cp.evidence
    boundary_layer = flags["SET_BOUNDARY_LAYER_TYPE"]
    assert boundary_layer.provenance == "default"
    assert boundary_layer.value == "TRANSITIONAL"
    assert not boundary_layer.emitted
    assert boundary_layer.evidence == "FSM-26.120 p.203"
    farfield = flags["SOLVER_SET_FARFIELD_LAYERS"]
    assert farfield.provenance == "default"
    assert farfield.value == 3
    assert farfield.evidence == "FSM-26.120 p.344"
    unknown = flags["SET_WAKE_ON_WAKE_INDUCTION"]
    assert unknown.provenance == "unknown"
    assert unknown.value is None and unknown.evidence is None and not unknown.emitted
    vorticity = flags[VORTICITY_COMMAND]
    assert vorticity.provenance == "explicit" and vorticity.value == "all" and vorticity.emitted
    counts = setup.provenance_counts()
    assert counts["explicit"] == 2  # aoa and the vorticity selection
    # Six since 2026-08-08, when the three wake and rotor knobs of the
    # Advanced Settings chapter moved their manual defaults out of prose
    # and into the structured `default` field. A default the database
    # records is a default the snapshot reports, which is the point of
    # the field.
    assert counts["default"] == 6, (
        "minimum_cp, boundary_layer, farfield_layers, and the three wake and rotor "
        "defaults added with the Advanced Settings chapter"
    )
    assert counts["explicit"] + counts["default"] + counts["unknown"] == len(flags)


def test_defaults_of_commands_absent_from_the_version_stay_unknown():
    # 26.101 records no evidence for SOLVER_MINIMUM_CP or
    # SOLVER_SET_FARFIELD_LAYERS, so the library default is not emitted
    # and nothing is claimed. Naming the two commands rather than the
    # advanced_settings family, which is no longer empty on that build:
    # LAMINAR_SEPARATION is recorded there.
    #
    # This test named SET_BOUNDARY_LAYER_TYPE until 2026-08-07, when the
    # review found the May edition documents that command (FSM-26.101 p.340)
    # and the entry had no row for it. The command became emittable on
    # 26.101 and the assertion turned green in the wrong direction: a
    # default WAS now claimed there, correctly. The two named above are
    # the ones the May manual genuinely does not carry.
    registry = CommandRegistry.load()
    witnesses = {
        version: sorted(
            name
            for name, entry in registry.commands.items()
            if entry.default is not None and name not in registry.for_version(version)
        )
        for version in ("26.100", "26.101")
    }
    if not any(witnesses.values()):
        pytest.skip(
            "no witness in the current database: every command carrying a library "
            "default is now available on every registered build, after the 2026-08-08 "
            "backfill of the early editions. The rule this test guards is still "
            "implemented, and it has no live case to exercise, which is the state "
            "PLN-20260808-1400 records rather than papers over"
        )
    version, absent = next((v, names) for v, names in witnesses.items() if names)
    script = Script(version=version)
    setup = helpers.solver_settings(script, vorticity_drag_boundaries="all")
    for name in absent:
        assert name not in script.render()
        assert setup.flags[name].provenance == "unknown"


# --- the optional vorticity selection ---------------------------------------


def test_an_unset_selection_emits_nothing_and_leaves_the_solver_default():
    # FSM-26.120 p.202: boundaries outside the vorticity CDi list use the
    # solver's surface pressure integration, a complete drag calculation.
    # Omitting the selection must therefore build a valid script, not a
    # refusal (the legacy reproduction path leaves the list unset).
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, aoa=3.0, velocity=30.0)
    helpers.start_solver(script)
    text = script.render()
    assert VORTICITY_COMMAND not in text
    assert "SOLVER_SET_AOA 3.0" in text and "START_SOLVER" in text
    record = setup.flags[VORTICITY_COMMAND]
    assert record.provenance == "default"
    assert record.value == [] and not record.emitted
    assert "FSM-26.120 p.202" in record.evidence
    # The snapshot stays total, with the flag counted as a default.
    counts = setup.provenance_counts()
    assert counts["explicit"] == 2  # aoa and velocity
    # Seven since 2026-08-08: the four below plus the three wake and
    # rotor defaults the Advanced Settings chapter brought in as
    # structured `default` fields.
    assert counts["default"] == 7, (
        "minimum_cp, boundary_layer, farfield, vorticity, and the three wake and "
        "rotor defaults added with the Advanced Settings chapter"
    )
    assert counts["explicit"] + counts["default"] + counts["unknown"] == len(setup.flags)


def test_the_unset_selection_reads_its_default_and_citation_from_the_command_entry():
    """PFS-2006.01: the default and its citation live in the command entry, not in code.

    The empty selection and "FSM-26.120 p.202" were restated in the snapshot's
    Python while the entry carried neither, so no validator could see them.
    The entry now records both, and the record reads them: a registry whose
    entry cites another page is cited in the record, the literal is not.
    """
    registry = CommandRegistry.load()
    entry = registry.commands[VORTICITY_COMMAND]
    assert entry.default == () and entry.default_ref == "FSM-26.120 p.202"
    moved = CommandRegistry(
        commands={
            **registry.commands,
            VORTICITY_COMMAND: entry.model_copy(update={"default_ref": "FSM-26.124 p.202"}),
        }
    )
    setup = helpers.solver_settings(Script(version="26.120", registry=moved), aoa=3.0)
    record = setup.flags[VORTICITY_COMMAND]
    assert record.provenance == "default" and record.value == [] and not record.emitted
    assert "FSM-26.124 p.202" in record.evidence and "FSM-26.120 p.202" not in record.evidence


def test_an_unset_selection_stays_unknown_without_the_command_in_the_version(monkeypatch):
    """No evidence for the selection command means no claimed default.

    Invariant 3, the honest unknown. 26.000 played this part until its
    own manual was read on 2026-08-10; the command is documented by
    every registered build now, so the silence is made rather than
    found.
    """
    # Monkeypatched rather than passed: build_setup calls
    # CommandRegistry.load() itself and ignores the registry its Script
    # was built with, so a registry argument here would be honoured by
    # the emitter and ignored by the snapshot (PLN-20260810-1100).
    silent = registry_without(VORTICITY_COMMAND)
    monkeypatch.setattr(solver_setup.CommandRegistry, "load", classmethod(lambda cls: silent))
    script = Script(version="26.0", registry=silent)
    setup = helpers.solver_settings(script)
    record = setup.flags[VORTICITY_COMMAND]
    assert record.provenance == "unknown"
    assert record.value is None and record.evidence is None and not record.emitted


def test_an_unset_selection_round_trips_through_the_snapshot():
    first = Script(version="26.120")
    setup = helpers.solver_settings(first, aoa=3.0)
    helpers.start_solver(first)
    second = Script(version="26.120")
    regenerated = script_from_setup(
        second, SolverSetup.model_validate_json(setup.model_dump_json())
    )
    helpers.start_solver(second)
    assert second.render() == first.render()
    assert VORTICITY_COMMAND not in second.render()
    assert regenerated == setup


@pytest.mark.parametrize("empty", [[], ()])
def test_an_empty_selection_is_refused_and_emits_nothing(empty):
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="empty sequence"):
        helpers.solver_settings(script, vorticity_drag_boundaries=empty)
    assert script.render() == "\n"  # nothing was emitted


def test_a_snapshot_marked_explicit_with_an_empty_selection_is_refused_naming_the_flag():
    """PFS-2012.01, the regeneration half. A snapshot edited by hand into a
    state no helper call writes used to reach the helper's own refusal, which
    tells the user to omit an argument they never wrote; the snapshot names
    the flag and says the record is what to fix.
    """
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, vorticity_drag_boundaries=[1, 2], aoa=1.0)
    dumped = setup.model_dump(mode="json")
    dumped["flags"][VORTICITY_COMMAND]["value"] = []
    edited = SolverSetup.model_validate(dumped)
    with pytest.raises(CommandArgumentError) as refused:
        script_from_setup(Script(version="26.120"), edited)
    message = str(refused.value)
    assert VORTICITY_COMMAND in message and "vorticity_drag_boundaries" in message, message
    assert "omit" not in message.lower(), f"no argument was written: {message}"
    # The control: the snapshot as written replays.
    assert script_from_setup(Script(version="26.120"), setup) == setup


def test_a_second_settings_call_keeps_the_selection_in_script_and_snapshot():
    # solver_settings emits only what it is passed, so a second call on
    # the same script must not drop the selection of the first: the
    # script would lose the vorticity integration silently and the
    # snapshot would record a default that never applied.
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries=[1, 2], velocity=30.0)
    setup = helpers.solver_settings(script, aoa=5.0)
    helpers.start_solver(script)
    text = script.render()
    assert "SET_VORTICITY_DRAG_BOUNDARIES 2\n1,2" in text
    assert text.count(VORTICITY_COMMAND) == 1  # kept, not rearmed
    record = setup.flags[VORTICITY_COMMAND]
    assert record.provenance == "explicit" and record.value == [1, 2] and record.emitted


def test_the_deprecated_selection_restamps_the_snapshot():
    # The deprecated path emits its own selection after the snapshot was
    # built; the record must follow, or the manifest would describe a
    # script that was never built.
    script = Script(version="26.120")
    settings_setup = helpers.solver_settings(script, aoa=3.0)
    script.emit("START_SOLVER")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        helpers.analysis_setup(script, vorticity_drag_boundaries=[1])
    # Nothing was deferred, so the warning must not claim a replacement.
    assert "replaces the selection deferred" not in str(caught[0].message)
    assert "SET_VORTICITY_DRAG_BOUNDARIES 1\n1" in script.render()
    record = script.solver_setup.flags[VORTICITY_COMMAND]
    assert record.provenance == "explicit" and record.value == [1] and record.emitted
    assert record.evidence is None
    # The returned snapshot is frozen: restamping produced a new one.
    assert settings_setup.flags[VORTICITY_COMMAND].provenance == "default"


def test_the_deprecated_selection_records_resolved_indices_not_labels():
    # One vocabulary in the manifest: both paths store 1-based indices,
    # so a stored snapshot is readable without the label declarations.
    script = Script(version="26.120")
    script.declare_existing(boundaries={"wing": 1, "tail": 2})
    helpers.solver_settings(script, aoa=3.0)
    script.emit("START_SOLVER")
    with pytest.warns(DeprecationWarning):
        helpers.analysis_setup(script, vorticity_drag_boundaries=["tail"])
    assert script.solver_setup.flags[VORTICITY_COMMAND].value == [2]


def test_a_failed_deprecated_call_leaves_script_and_snapshot_untouched():
    # The label resolves at call time, before any emission or record, so
    # a bad label cannot leave a snapshot claiming a selection the
    # script does not carry, nor destroy the deferred one.
    script = Script(version="26.120")
    script.declare_existing(boundaries={"wing": 1})
    setup = helpers.solver_settings(script, vorticity_drag_boundaries=["wing"])
    script.emit("START_SOLVER")
    with pytest.raises(ScriptReferenceError, match="analysis_setup"):
        helpers.analysis_setup(script, load_units="COEFFICIENTS", vorticity_drag_boundaries=["gh"])
    assert script.solver_setup is setup  # the record was not restamped
    assert "SET_LOADS_AND_MOMENTS_UNITS" not in script.render()
    # The deferred selection survived and still reaches the script.
    helpers.export_results(script, spreadsheet="C:/out/loads.txt")
    assert "SET_VORTICITY_DRAG_BOUNDARIES 1\n1" in script.render()


def test_the_deprecated_path_refuses_an_empty_selection_too():
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    script.emit("START_SOLVER")
    with pytest.raises(CommandArgumentError, match="empty sequence"):
        helpers.analysis_setup(script, vorticity_drag_boundaries=[])
    assert VORTICITY_COMMAND not in script.render()  # the selection survives


@pytest.mark.parametrize("selection", ["all", [1, 2]])
def test_with_vorticity_selection_restamps_without_touching_the_input(selection):
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, aoa=3.0)
    restamped = with_vorticity_selection(setup, selection)
    record = restamped.flags[VORTICITY_COMMAND]
    assert record.provenance == "explicit" and record.emitted
    assert record.value == selection and record.evidence is None
    assert setup.flags[VORTICITY_COMMAND].provenance == "default"  # input untouched


def test_a_bare_vorticity_label_is_rejected_with_the_fix():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match=r"\['wing'\]"):
        helpers.solver_settings(script, vorticity_drag_boundaries="wing")


def test_vorticity_labels_resolve_and_range_check_at_call_time():
    script = Script(version="26.120")
    script.declare_existing(boundaries={"wing": 1, "tail": 2})
    helpers.solver_settings(script, vorticity_drag_boundaries=["tail"])
    helpers.start_solver(script)
    assert "START_SOLVER\nSET_VORTICITY_DRAG_BOUNDARIES 1\n2" in script.render()
    bad = Script(version="26.120")
    bad.declare_existing(boundaries=2)
    with pytest.raises(ScriptReferenceError, match="solver_settings"):
        helpers.solver_settings(bad, vorticity_drag_boundaries=[3])
    assert "SOLVER_MINIMUM_CP" not in bad.render()  # nothing emitted before the error


# --- deferred emission of the analysis-phase selection ----------------------


def test_vorticity_defers_until_the_solver_starts():
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    assert VORTICITY_COMMAND not in script.render()
    helpers.start_solver(script)
    assert "START_SOLVER\nSET_VORTICITY_DRAG_BOUNDARIES -1" in script.render()
    # The flush happens once; a second analysis helper does not repeat it.
    helpers.export_results(script, spreadsheet="C:/out/loads.txt")
    assert script.render().count(VORTICITY_COMMAND) == 1


def test_export_results_flushes_a_pending_selection():
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries=[1, 2])
    script.emit("START_SOLVER")
    helpers.export_results(script, spreadsheet="C:/out/loads.txt")
    text = script.render()
    assert "SET_VORTICITY_DRAG_BOUNDARIES 2\n1,2" in text
    assert text.index(VORTICITY_COMMAND) < text.index("EXPORT_SOLVER_ANALYSIS_SPREADSHEET")


def test_analysis_setup_flushes_only_when_it_reaches_the_analysis_phase():
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    # symmetry_loads alone is an init-phase call: no flush yet.
    helpers.analysis_setup(script, symmetry_loads=True)
    assert VORTICITY_COMMAND not in script.render()
    script.emit("START_SOLVER")
    helpers.analysis_setup(script, load_units="COEFFICIENTS")
    text = script.render()
    assert "SET_VORTICITY_DRAG_BOUNDARIES -1" in text
    assert text.index(VORTICITY_COMMAND) < text.index("SET_LOADS_AND_MOMENTS_UNITS")


def test_the_loads_frame_and_moments_model_leave_the_selection_deferred_to_the_start():
    """B05, RPT-064: the init group precedes START_SOLVER and does not flush.

    The loads frame and the moments model are init-phase settings since
    0.27.0, emitted before the start. Flushing the induced-drag selection
    with them, as a call carrying them did while they were analysis
    commands, would put an analysis-phase line before the start, and the
    phase guard would then refuse START_SOLVER on every row naming
    vorticity-drag families. The selection lands after the start, as it
    always did.
    """
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    helpers.analysis_setup(script, loads_frame=1, moments_model="PRESSURE")
    assert VORTICITY_COMMAND not in script.render()
    helpers.start_solver(script)
    lines = script.render().splitlines()
    frame_at = lines.index("SET_SOLVER_ANALYSIS_LOADS_FRAME 1")
    model_at = lines.index("SET_ANALYSIS_MOMENTS_MODEL PRESSURE")
    start_at = lines.index("START_SOLVER")
    assert frame_at < model_at < start_at < lines.index("SET_VORTICITY_DRAG_BOUNDARIES -1")


@pytest.mark.parametrize(
    "arguments", [{"loads_frame": 1}, {"moments_model": "PRESSURE"}], ids=["frame", "model"]
)
def test_the_loads_frame_after_the_start_is_refused(arguments):
    """B05, RPT-064: the position that reached the final export only is refused.

    A command has one phase, so reclassifying the two as init refuses
    the post-start position everywhere, a hand-built script included.
    That is the intent: that position wrote step exports whose moments
    are about the reference origin, with nothing said.
    """
    from pyflightstream.script import ScriptOrderError

    script = Script(version="26.120")
    helpers.start_solver(script)
    with pytest.raises(ScriptOrderError, match="is a init command"):
        helpers.analysis_setup(script, **arguments)


# --- the library minimum-Cp default -----------------------------------------


def test_minimum_cp_library_default_is_emitted_when_unset():
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    assert "SOLVER_MINIMUM_CP -100" in script.render()


def test_minimum_cp_override_wins_and_is_explicit():
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, vorticity_drag_boundaries="all", minimum_cp=-40)
    text = script.render()
    assert "SOLVER_MINIMUM_CP -40" in text
    assert "-100" not in text
    record = setup.flags["SOLVER_MINIMUM_CP"]
    assert record.provenance == "explicit" and record.value == -40 and record.emitted


# --- solver mode and bulk separation validation -----------------------------


def test_unsteady_mode_needs_both_time_arguments():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="both time_iterations and delta_time"):
        helpers.solver_settings(script, vorticity_drag_boundaries="all", mode="UNSTEADY")
    with pytest.raises(CommandArgumentError, match="belong to the unsteady solver"):
        helpers.solver_settings(script, vorticity_drag_boundaries="all", delta_time=0.01)
    with pytest.raises(CommandArgumentError, match="STEADY or UNSTEADY"):
        helpers.solver_settings(script, vorticity_drag_boundaries="all", mode="HOVER")


def test_steady_mode_and_bulk_separation_emit():
    script = Script(version="26.120")
    script.allow_broken("CREATE_BULK_SEPARATION", reason=_BULK_GRAMMAR)
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        mode="STEADY",
        bulk_separation={
            "name": "hub",
            "separation_type": "CYLINDRICAL",
            "diameter": 0.4,
            "boundaries": [1],
        },
    )
    text = script.render()
    assert "SET_SOLVER_STEADY" in text
    assert "CREATE_BULK_SEPARATION hub CYLINDRICAL 1 0.4\n1" in text
    with pytest.raises(CommandArgumentError, match="bulk_separation takes a BulkSeparation"):
        helpers.solver_settings(
            script, vorticity_drag_boundaries="all", bulk_separation={"name": "x"}
        )


#: CREATE_BULK_SEPARATION is broken on 26.120 since 2026-10-12 (RPT-166: the
#: solver deprecates it for CREATE_CYLINDRICAL_BULK_SEPARATION and stops at the
#: line). The tests below test the grammar and order the renderer writes, which
#: no solver reads, so they emit it under the recorded waiver.
_BULK_GRAMMAR = "renderer grammar test; no solver reads this script"

# --- round trip: snapshot -> json -> script_from_setup ----------------------


ROUND_TRIP_KWARGS = dict(
    vorticity_drag_boundaries=[1, 2],
    mode="UNSTEADY",
    time_iterations=120,
    delta_time=0.001,
    aoa=4.0,
    sideslip=-1.0,
    velocity=30.0,
    ref_velocity=150.0,
    ref_area=0.8,
    ref_length=0.25,
    iterations=400,
    convergence=1e-5,
    forced_iterations=True,
    max_threads=8,
    boundary_layer="TURBULENT",
    viscous_coupling=True,
    viscous_excluded=[2],
    bulk_separation=BulkSeparation(
        name="hub", separation_type="FLAT_PLATE", diameter=0.3, boundaries="all"
    ),
    convergence_iterations=25,
    minimum_cp=-60,
    reynolds_averaged_drag=False,
    mesh_induced_wake_velocity=True,
    farfield_layers=4,
    unsteady_pressure_and_kutta=False,
    wake_termination_time_steps=40,
    wake_on_wake_induction=True,
    additional_wake_relaxation=False,
    aeroelastic_rbf_type="GAUSSIAN",
)


def test_round_trip_regenerates_identical_lines():
    first = Script(version="26.120")
    first.allow_broken("CREATE_BULK_SEPARATION", reason=_BULK_GRAMMAR)
    setup = helpers.solver_settings(first, **ROUND_TRIP_KWARGS)
    helpers.start_solver(first)
    assert first.solver_setup is setup

    payload = setup.model_dump_json()
    restored = SolverSetup.model_validate_json(payload)
    assert restored == setup

    second = Script(version="26.120")
    second.allow_broken("CREATE_BULK_SEPARATION", reason=_BULK_GRAMMAR)
    regenerated = script_from_setup(second, restored)
    helpers.start_solver(second)
    assert second.render() == first.render()
    assert regenerated == setup
    assert second.solver_setup is regenerated


def test_round_trip_with_defaults_only():
    first = Script(version="26.120")
    setup = helpers.solver_settings(first, vorticity_drag_boundaries="all")
    helpers.start_solver(first)
    second = Script(version="26.120")
    script_from_setup(second, SolverSetup.model_validate_json(setup.model_dump_json()))
    helpers.start_solver(second)
    assert second.render() == first.render()
    assert "SOLVER_MINIMUM_CP -100" in second.render()


# --- deprecation of the analysis_setup path ---------------------------------


def test_analysis_setup_vorticity_is_deprecated_but_works():
    script = Script(version="26.120")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    script.emit("START_SOLVER")
    # The promise names its release (PFS-2021.02): it stays until 1.0.0,
    # and the text comes from the ledger entry, so this regex and the
    # deadline guard read the same version.
    with pytest.warns(
        DeprecationWarning,
        match=r"vorticity_drag_boundaries of analysis_setup .*will be removed in "
        r"v1\.0\.0.*This explicit call replaces the selection deferred by "
        r"solver_settings",
    ):
        helpers.analysis_setup(script, vorticity_drag_boundaries=[1])
    text = script.render()
    # The deprecated explicit call replaced the deferred selection.
    assert text.count(VORTICITY_COMMAND) == 1
    assert "SET_VORTICITY_DRAG_BOUNDARIES 1\n1" in text


# --- manifest round trip ----------------------------------------------------


def make_record(**overrides) -> RunRecord:
    body = dict(
        run_id="camp/sim_1/a+00.0",
        sim_id="1",
        fs_version_requested="26.120",
        package_version="0.0.0-synthetic",
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
    )
    body.update(overrides)
    return RunRecord(**body)


def test_manifest_record_round_trips_with_the_snapshot():
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, aoa=2.0, vorticity_drag_boundaries="all")
    record = make_record(solver_setup=setup.model_dump(mode="json"))
    reloaded = RunRecord.model_validate(json.loads(record.model_dump_json()))
    assert reloaded == record
    restored = SolverSetup.model_validate(reloaded.solver_setup)
    assert restored == setup


def test_old_manifest_records_without_the_field_still_load():
    record = make_record()
    payload = json.loads(record.model_dump_json())
    del payload["solver_setup"]  # a pre-v0.3.0 manifest never wrote the field
    reloaded = RunRecord.model_validate(payload)
    assert reloaded.solver_setup is None


# --- the flow-separation family ---------------------------------------------
#
# Two generations that never coexist: the per-mechanism boundary lists of
# 26.100 and the named assignment models of 26.101 and later. RPT-018
# measured each on the licensed builds, and these tests hold the emitter
# to what it measured.


def test_the_february_separation_lists_emit_their_own_grammar():
    script = Script(version="26.100")
    helpers.solver_settings(
        script,
        axial_separation_boundaries="all",
        crossflow_separation_boundaries=[1, 2, 4],
        crossflow_separation_diameter=3.5,
        crossflow_separation_axisymmetric=True,
        laminar_separation=True,
    )
    text = script.render()
    # "all" is the -1 form with no index line; a listed selection is the
    # count followed by its own line. Both are asserted, because an
    # emitter that produced one shape for both would satisfy either alone.
    assert "SET_AXIAL_SEPARATION_BOUNDARIES -1" in text
    assert "SET_CROSSFLOW_SEPARATION_BOUNDARIES 3\n1,2,4" in text
    assert "SET_CROSSFLOW_SEPARATION_DIAMETER 3.5" in text
    assert "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC ENABLE" in text
    assert "LAMINAR_SEPARATION ENABLE" in text


@pytest.mark.parametrize(
    ("keyword", "set_command", "delete_command", "version"),
    [
        (
            "viscous_excluded",
            "SET_VISCOUS_EXCLUDED_BOUNDARIES",
            "DELETE_VISCOUS_EXCLUDED_BOUNDARIES",
            "26.120",
        ),
        (
            "axial_separation_boundaries",
            "SET_AXIAL_SEPARATION_BOUNDARIES",
            "DELETE_AXIAL_SEPARATION_BOUNDARIES",
            "26.100",
        ),
        # The Valarezo pair is deliberately NOT here. Its erase emits a
        # name RPT-018 measured as unrecognized, so the helper refuses
        # it; the row lived in this list once, which made tier 1 assert
        # a known-broken emission in the same shape as the three that
        # work. It has its own test below, carrying its own history.
        (
            "crossflow_separation_boundaries",
            "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
            "DELETE_CROSSFLOW_SEPARATION_BOUNDARIES",
            "26.100",
        ),
    ],
)
def test_an_empty_selection_erases_the_list_and_a_full_one_sets_it(
    keyword, set_command, delete_command, version
):
    """The empty sequence is the erase, with a control that it is not the only path."""
    erasing = Script(version=version)
    helpers.solver_settings(erasing, **{keyword: []})
    erased = erasing.render()
    assert delete_command in erased
    assert set_command not in erased

    setting = Script(version=version)
    helpers.solver_settings(setting, **{keyword: [1, 2]})
    was_set = setting.render()
    assert f"{set_command} 2\n1,2" in was_set
    assert delete_command not in was_set


@pytest.mark.parametrize(
    ("keyword", "set_command", "delete_command", "version"),
    [
        (
            "viscous_excluded",
            "SET_VISCOUS_EXCLUDED_BOUNDARIES",
            "DELETE_VISCOUS_EXCLUDED_BOUNDARIES",
            "26.120",
        ),
        (
            "axial_separation_boundaries",
            "SET_AXIAL_SEPARATION_BOUNDARIES",
            "DELETE_AXIAL_SEPARATION_BOUNDARIES",
            "26.100",
        ),
        (
            "crossflow_separation_boundaries",
            "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
            "DELETE_CROSSFLOW_SEPARATION_BOUNDARIES",
            "26.100",
        ),
    ],
)
def test_an_erased_list_is_recorded_against_the_delete_command_alone(
    keyword, set_command, delete_command, version
):
    """The setter half must stay silent, or the snapshot claims both.

    Parametrised over every SET/DELETE pair rather than over
    ``viscous_excluded`` alone, which is how it was written. The three
    separation keywords share one dispatch branch with it, and a
    mutation deleting their kind from that branch left the whole suite
    green: the snapshot then recorded the setter as explicit and emitted
    for a command the script does not contain, and the replay still
    round-tripped because both sides read the same wrong record.
    """
    script = Script(version=version)
    setup = helpers.solver_settings(script, **{keyword: []})
    assert setup.flags[delete_command].provenance == "explicit"
    assert setup.flags[delete_command].value == []
    assert setup.flags[delete_command].emitted
    assert setup.flags[set_command].provenance == "unknown"
    assert not setup.flags[set_command].emitted


@pytest.mark.parametrize("empty", [[], ()])
def test_an_empty_selection_of_any_sequence_type_reaches_the_same_verdict(empty):
    """A tuple is a Sequence, and the two halves used to disagree on it.

    The emitter decided emptiness by length and the snapshot by equality
    with a list literal, so an empty tuple emitted the erase and recorded
    the setter as explicitly emitted. The manifest then named a command
    the script does not contain.
    """
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, viscous_excluded=empty)
    assert "DELETE_VISCOUS_EXCLUDED_BOUNDARIES" in script.render()
    assert setup.flags["DELETE_VISCOUS_EXCLUDED_BOUNDARIES"].provenance == "explicit"
    assert setup.flags["SET_VISCOUS_EXCLUDED_BOUNDARIES"].provenance == "unknown"


def test_the_valarezo_erase_emits_the_name_the_solver_answers_to():
    """The one erase of this family whose two names disagree.

    RPT-018 probed both spellings on the February build: the manual's own
    DELETE_VALAREZO_CRITERION_BOUNDARIES is unrecognized and the
    undocumented DELETE_VALAREZO_SEPARATION_BOUNDARIES is accepted.

    The helper REFUSED the empty sequence between 2026-08-05 and
    2026-08-06, because the working name could not be recorded: every
    entry needed a manual page and no edition prints that one. The
    author's decision of 2026-08-06 admits a committed probe report in
    the page's place, so the command has an entry, the erase emits it,
    and the emitter validates it like any other. The refusal was the
    right answer to a database that could not hold the fact, and the
    wrong answer once it could.
    """
    script = Script(version="26.100")
    helpers.solver_settings(script, valarezo_separation_boundaries=[])
    assert "DELETE_VALAREZO_SEPARATION_BOUNDARIES" in script.render()
    # The documented name stays in the database, because a reader of
    # FSM-26.100 p.339 has to be able to find out here that it fails, and it
    # is never emitted.
    assert "CRITERION" not in script.render()

    setting = Script(version="26.100")
    helpers.solver_settings(setting, valarezo_separation_boundaries=[1, 2])
    assert "SET_VALAREZO_SEPARATION_BOUNDARIES 2\n1,2" in setting.render()


def test_the_documented_valarezo_erase_is_recorded_and_never_emitted():
    """A command in a settings family needs a flag; this one can never be set.

    Its snapshot record is `unknown` in every script, which is the truth:
    the helper has no path that emits it. Recording it as anything else
    would put a command in the manifest that the script does not carry.
    """
    script = Script(version="26.100")
    setup = helpers.solver_settings(script, valarezo_separation_boundaries=[])
    assert setup.flags["DELETE_VALAREZO_CRITERION_BOUNDARIES"].provenance == "unknown"
    assert not setup.flags["DELETE_VALAREZO_CRITERION_BOUNDARIES"].emitted
    assert setup.flags["DELETE_VALAREZO_SEPARATION_BOUNDARIES"].provenance == "explicit"


@pytest.mark.parametrize(
    "keyword",
    [
        "airfoil_separation",
        "axial_vortex_separation",
        "cylindrical_bulk_separation",
        "stratford_bulk_separation",
    ],
)
def test_an_empty_sequence_of_assignment_models_is_refused_not_ignored(keyword):
    """The empty sequence means the erase three keywords earlier in the same call.

    Accepting it here as a silent no-op is the third meaning of ``[]``
    in one signature, and the only undocumented one. The solver has no
    per-type erase, so the message names what does.
    """
    script = Script(version="26.121")
    with pytest.raises(CommandArgumentError, match="delete_separations"):
        helpers.solver_settings(script, aoa=3.0, **{keyword: []})
    assert script.render() == "\n", "a refusal must leave the caller's script untouched"


def test_the_named_separation_models_emit_in_the_recorded_order():
    script = Script(version="26.121")
    helpers.solver_settings(
        script,
        delete_separations="all",
        airfoil_separation=[
            AirfoilSeparation(name="WING", valarezo_criterion=True, boundaries=[1, 2, 4])
        ],
        axial_vortex_separation=[
            AxialVortexSeparation(name="FUSELAGE", diameter=0.5, frame=1, body_axis="X")
        ],
        cylindrical_bulk_separation=[CylindricalBulkSeparation(name="GEAR", diameter=0.2)],
        stratford_bulk_separation=[StratfordBulkSeparation(name="STRUT", boundaries=[7])],
    )
    text = script.render()
    assert "DELETE_SEPARATION -1" in text
    assert "CREATE_AIRFOIL_SEPARATION WING 3 ENABLE\n1,2,4" in text
    assert "CREATE_AXIAL_VORTEX_SEPARATION FUSELAGE -1 1 X 0.5 DISABLE" in text
    assert "CREATE_CYLINDRICAL_BULK_SEPARATION GEAR -1 0.2" in text
    assert "CREATE_STRATFORD_BULK_SEPARATION STRUT 1\n7" in text
    # The solver indexes the models in creation order and
    # DELETE_SEPARATION addresses them by that index, so the order is a
    # promise of FLAG_SPECS and not an accident of the call.
    positions = [
        text.index("DELETE_SEPARATION -1"),
        text.index("CREATE_AIRFOIL_SEPARATION"),
        text.index("CREATE_AXIAL_VORTEX_SEPARATION"),
        text.index("CREATE_CYLINDRICAL_BULK_SEPARATION"),
        text.index("CREATE_STRATFORD_BULK_SEPARATION"),
    ]
    assert positions == sorted(positions)


def test_the_separation_order_is_the_flag_spec_order_not_the_call_order():
    """Passing the keywords backwards must not reorder the emissions.

    Every adjacent pair is asserted, not just the ends: a swap of two
    middle commands leaves the first-before-last comparison true, and a
    mutation swapping the airfoil and axial-vortex rows was caught only
    by the sibling test until this one walked the whole sequence.
    """
    script = Script(version="26.121")
    helpers.solver_settings(
        script,
        stratford_bulk_separation=[StratfordBulkSeparation(name="STRUT")],
        cylindrical_bulk_separation=[CylindricalBulkSeparation(name="GEAR", diameter=0.2)],
        axial_vortex_separation=[AxialVortexSeparation(name="FUSELAGE", diameter=0.5)],
        airfoil_separation=[AirfoilSeparation(name="WING")],
    )
    text = script.render()
    expected = [
        "CREATE_AIRFOIL_SEPARATION",
        "CREATE_AXIAL_VORTEX_SEPARATION",
        "CREATE_CYLINDRICAL_BULK_SEPARATION",
        "CREATE_STRATFORD_BULK_SEPARATION",
    ]
    emitted = sorted(expected, key=text.index)
    assert emitted == expected


def test_a_separation_snapshot_replays_to_the_same_script():
    original = Script(version="26.121")
    setup = helpers.solver_settings(
        original,
        airfoil_separation=[AirfoilSeparation(name="WING", boundaries=[1, 2])],
        stratford_bulk_separation=[StratfordBulkSeparation(name="STRUT")],
        delete_separations=2,
    )
    # The INDEX form asserted against rendered text, not only through the
    # replay: both sides of a round trip run the same emitter, so a
    # mutation replacing the index with -1 is symmetric and invisible
    # there. -1 deletes every model where 2 deletes the second.
    assert "DELETE_SEPARATION 2\n" in original.render()
    stored = SolverSetup.model_validate_json(setup.model_dump_json())
    replayed = Script(version="26.121")
    script_from_setup(replayed, stored)
    assert replayed.render() == original.render()


def test_an_erased_list_replays_as_the_erase():
    original = Script(version="26.120")
    setup = helpers.solver_settings(original, viscous_excluded=[])
    replayed = Script(version="26.120")
    script_from_setup(replayed, SolverSetup.model_validate_json(setup.model_dump_json()))
    assert replayed.render() == original.render()
    assert "DELETE_VISCOUS_EXCLUDED_BOUNDARIES" in replayed.render()


@pytest.mark.parametrize("index", [0, -5])
def test_delete_separations_refuses_an_index_the_solver_does_not_number(index):
    script = Script(version="26.121")
    with pytest.raises(CommandArgumentError, match="1-based index"):
        helpers.solver_settings(script, delete_separations=index)
    assert "SEPARATION" not in script.render()


def test_a_malformed_separation_model_names_the_fields_it_wanted():
    script = Script(version="26.121")
    with pytest.raises(CommandArgumentError, match="AirfoilSeparation") as caught:
        helpers.solver_settings(script, airfoil_separation=[{"nome": "WING"}])
    assert "valarezo_criterion" in str(caught.value)
    assert "SEPARATION" not in script.render()


def test_a_bare_label_where_a_separation_sequence_belongs_says_so():
    script = Script(version="26.100")
    with pytest.raises(CommandArgumentError, match="a sequence of indices or labels"):
        helpers.solver_settings(script, axial_separation_boundaries="WING")


@pytest.mark.parametrize(
    ("version", "keyword", "value", "command"),
    [
        ("26.100", "airfoil_separation", [{"name": "WING"}], "CREATE_AIRFOIL_SEPARATION"),
        ("26.100", "delete_separations", "all", "DELETE_SEPARATION"),
        # 26.101 is the row the first version of this test omitted, and
        # it is the only one that was failing: the May build sits at a
        # hotfix index behind the February one, so it inherited the
        # February family and the emitter wrote it. Every later build is
        # listed now, because "the build that does not carry it" is a
        # claim about all of them and was tested on one.
        ("26.101", "axial_separation_boundaries", "all", "SET_AXIAL_SEPARATION_BOUNDARIES"),
        ("26.101", "valarezo_separation_boundaries", "all", "SET_VALAREZO_SEPARATION_BOUNDARIES"),
        (
            "26.101",
            "crossflow_separation_axisymmetric",
            True,
            "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC",
        ),
        ("26.120", "axial_separation_boundaries", "all", "SET_AXIAL_SEPARATION_BOUNDARIES"),
        ("26.121", "axial_separation_boundaries", "all", "SET_AXIAL_SEPARATION_BOUNDARIES"),
        ("26.121", "crossflow_separation_diameter", 3.5, "SET_CROSSFLOW_SEPARATION_DIAMETER"),
    ],
)
def test_each_generation_is_refused_on_the_build_that_does_not_carry_it(
    version, keyword, value, command
):
    """RPT-018: neither generation exists on the other's build.

    The refusal is matched on the COMMAND it names, not only on the
    exception type. Any mis-wiring that reached a different absent
    command on the wrong build raises the same type, and a bare
    ``pytest.raises`` reads that as proof of the gating it does not
    have.
    """
    script = Script(version=version)
    with pytest.raises(CommandNotInVersionError, match=command):
        helpers.solver_settings(script, **{keyword: value})


# --- round 2: the round-1 fixes, each with the guard it shipped without ------


def test_the_erase_precedes_the_bulk_create_so_one_call_can_rebuild():
    """Round 1 moved DELETE_SEPARATION ahead of CREATE_BULK_SEPARATION and
    left no test: no case in the suite passed both keywords, so reverting
    the move was invisible. Passing both used to create the bulk model
    and delete it, while the snapshot recorded it as emitted.
    """
    script = Script(version="26.120")
    script.allow_broken("CREATE_BULK_SEPARATION", reason=_BULK_GRAMMAR)
    setup = helpers.solver_settings(
        script,
        bulk_separation={"name": "GEAR", "separation_type": "FLAT_PLATE", "diameter": 0.2},
        delete_separations="all",
    )
    text = script.render()
    assert text.index("DELETE_SEPARATION -1") < text.index("CREATE_BULK_SEPARATION")
    # The snapshot describes a script whose bulk model survives.
    assert setup.flags["CREATE_BULK_SEPARATION"].provenance == "explicit"
    assert setup.flags["DELETE_SEPARATION"].provenance == "explicit"


@pytest.mark.parametrize(
    ("keyword", "delete_command", "version"),
    [
        ("viscous_excluded", "DELETE_VISCOUS_EXCLUDED_BOUNDARIES", "26.120"),
        ("axial_separation_boundaries", "DELETE_AXIAL_SEPARATION_BOUNDARIES", "26.100"),
        ("crossflow_separation_boundaries", "DELETE_CROSSFLOW_SEPARATION_BOUNDARIES", "26.100"),
    ],
)
def test_an_empty_tuple_reaches_the_same_verdict_on_every_pair(keyword, delete_command, version):
    """The materialisation fix was guarded for one keyword of three.

    `_as_selection` runs over all four selections, and the test that
    proved it covered `viscous_excluded` alone, so dropping the
    materialisation for the three separation pairs left the suite green
    and reproduced the emitter-versus-snapshot split there.
    """
    script = Script(version=version)
    setup = helpers.solver_settings(script, **{keyword: ()})
    assert delete_command in script.render()
    assert setup.flags[delete_command].provenance == "explicit"


@pytest.mark.parametrize("spelling", ["ALL", "All", "aLL"])
def test_the_delete_sentinel_is_read_case_insensitively(spelling):
    """ "ALL" reached a `< 1` comparison and raised a bare TypeError.

    Every other refusal in this helper is didactic; this one escaped as
    a stdlib error out of a type the signature accepts.
    """
    script = Script(version="26.121")
    helpers.solver_settings(script, delete_separations=spelling)
    assert "DELETE_SEPARATION -1" in script.render()


def test_a_string_that_is_not_the_sentinel_is_refused_didactically():
    script = Script(version="26.121")
    with pytest.raises(CommandArgumentError, match="the string 'all'"):
        helpers.solver_settings(script, delete_separations="every")
    assert "SEPARATION" not in script.render()


def test_one_assignment_model_may_be_passed_without_a_sequence():
    """`bulk_separation` takes a single model, so the habit crosses over.

    It used to die on `object of type CylindricalBulkSeparation has no
    len()`, from the emptiness check added in round 1.
    """
    script = Script(version="26.121")
    helpers.solver_settings(
        script,
        cylindrical_bulk_separation=CylindricalBulkSeparation(name="GEAR", diameter=0.2),
    )
    assert "CREATE_CYLINDRICAL_BULK_SEPARATION GEAR -1 0.2" in script.render()


def test_an_assignment_on_no_boundary_is_refused_rather_than_emitted():
    """The count-0-plus-blank-line emission, on the surface round 1 missed.

    Round 1 refused exactly this for `viscous_excluded` and left it
    reachable through a model's own `boundaries=[]`, which renders
    `CREATE_CYLINDRICAL_BULK_SEPARATION GEAR 0 0.2` and then a line
    carrying nothing.
    """
    script = Script(version="26.121")
    with pytest.raises(CommandArgumentError, match="selects no boundary"):
        helpers.solver_settings(
            script,
            cylindrical_bulk_separation=[
                CylindricalBulkSeparation(name="GEAR", diameter=0.2, boundaries=[])
            ],
        )
    assert "SEPARATION" not in script.render()
    # The control: a real selection and the "all" default both still emit.
    working = Script(version="26.121")
    helpers.solver_settings(
        working,
        cylindrical_bulk_separation=[
            CylindricalBulkSeparation(name="GEAR", diameter=0.2, boundaries=[3]),
            CylindricalBulkSeparation(name="STRUT", diameter=0.1),
        ],
    )
    assert "CREATE_CYLINDRICAL_BULK_SEPARATION GEAR 1 0.2\n3" in working.render()
    assert "CREATE_CYLINDRICAL_BULK_SEPARATION STRUT -1 0.1" in working.render()


def test_every_separation_model_appears_in_all_four_parallel_lists():
    """A model has to be added in four places and nothing joined them.

    `SEPARATION_MODELS` maps keyword to class, the helper builds a
    `given_models` dict, the emission loop carries a keyword-to-command
    tuple, and `FLAG_SPECS` carries the rows. Three of the four are
    written out by hand in one function, so a fifth model added to two of
    them would emit nothing and record nothing, silently.
    """
    from pyflightstream.script.solver_setup import SEPARATION_MODELS

    spec_params = {spec.param for spec in FLAG_SPECS if spec.kind == "separation_models"}
    assert spec_params == set(SEPARATION_MODELS), (
        "FLAG_SPECS and SEPARATION_MODELS disagree on which keywords carry assignment "
        f"models: {spec_params ^ set(SEPARATION_MODELS)}"
    )
    keywords = set(inspect.signature(helpers.solver_settings).parameters)
    assert set(SEPARATION_MODELS) <= keywords
    # The emission tuple was source inside solver_settings and was read as
    # source; since 0.34.0 (AD-17) it is the data table of the separation
    # family in script/_settings.py, so it is read as data, exactly.
    from pyflightstream.script._settings import ASSIGNMENT_COMMANDS

    emitted = [keyword for keyword, command in ASSIGNMENT_COMMANDS if command.startswith("CREATE")]
    for keyword in SEPARATION_MODELS:
        assert keyword in emitted, (
            f"{keyword} is a separation model keyword with no row in the emission "
            "tuple of solver_settings, so it would validate and emit nothing"
        )
    assert len(emitted) == len(ASSIGNMENT_COMMANDS) == len(SEPARATION_MODELS)


@pytest.mark.parametrize(
    ("keyword", "model", "version"),
    [
        (
            "bulk_separation",
            {"name": "GEAR", "separation_type": "CYLINDRICAL", "diameter": 0.2, "boundaries": []},
            "26.120",
        ),
        ("airfoil_separation", {"name": "WING", "boundaries": []}, "26.121"),
        (
            "cylindrical_bulk_separation",
            {"name": "GEAR", "diameter": 0.2, "boundaries": []},
            "26.121",
        ),
        ("stratford_bulk_separation", {"name": "STRUT", "boundaries": []}, "26.121"),
        (
            "axial_vortex_separation",
            {"name": "FUSELAGE", "diameter": 0.5, "boundaries": []},
            "26.121",
        ),
    ],
)
def test_no_assignment_keyword_can_emit_a_selection_of_nothing(keyword, model, version):
    """Parametrised over ALL FIVE models, which is the point of the row count.

    The refusal was written into `_separation_arguments`, and
    `bulk_separation` had its own emission block predating that function,
    so it was the one assignment keyword the refusal never reached: it
    kept emitting the count 0 and a blank index line, the malformed shape
    the refusal exists for, one round after the refusal shipped. The bulk
    path routes through the same renderer now, and this covers the five
    keywords rather than the four that happened to share a code path.
    """
    script = Script(version=version)
    # A SECOND, emitting flag is passed on purpose. Every refusal test in
    # this file used to pass the offending keyword alone, so
    # `"SEPARATION" not in render()` held whether the assignments were
    # rendered before the first emission or inside the emission loop:
    # the guard for that repair could not fail on a revert. With `aoa`
    # here, a refusal raised mid-emission leaves SOLVER_SET_AOA behind
    # and the empty-script assertion catches it.
    with pytest.raises(CommandArgumentError, match="selects no boundary"):
        helpers.solver_settings(script, aoa=3.0, delete_separations="all", **{keyword: model})
    assert script.render() == "\n", "a refusal must leave the caller's script untouched"


def test_the_bulk_model_still_emits_its_own_grammar_through_the_shared_renderer():
    """The control for the routing change: same lines as before.

    Moving `bulk_separation` onto `_separation_arguments` had to keep
    SEPARATION_TYPE in its documented position, which the generic
    renderer produces from the model's field order.
    """
    script = Script(version="26.120")
    script.allow_broken("CREATE_BULK_SEPARATION", reason=_BULK_GRAMMAR)
    helpers.solver_settings(
        script,
        bulk_separation=BulkSeparation(
            name="GEAR", separation_type="FLAT_PLATE", diameter=0.2, boundaries=[1, 3]
        ),
    )
    assert "CREATE_BULK_SEPARATION GEAR FLAT_PLATE 2 0.2\n1,3" in script.render()

    every = Script(version="26.120")
    every.allow_broken("CREATE_BULK_SEPARATION", reason=_BULK_GRAMMAR)
    helpers.solver_settings(
        every,
        bulk_separation=BulkSeparation(name="GEAR", separation_type="CYLINDRICAL", diameter=0.2),
    )
    assert "CREATE_BULK_SEPARATION GEAR CYLINDRICAL -1 0.2" in every.render()


@pytest.mark.parametrize("value", [[1, 2], 0.5, True, {"index": 1}])
def test_delete_separations_refuses_every_type_that_is_not_an_index(value):
    """The first type check split str from EVERYTHING ELSE.

    Anything not a string fell into `< 1`, so a list raised
    "'<' not supported between instances of 'list' and 'int'" out of a
    helper whose every other refusal names its cause. bool is an int in
    Python and is not an index, so it is refused by name rather than
    quietly read as 1.
    """
    script = Script(version="26.121")
    with pytest.raises(CommandArgumentError, match="1-based index"):
        helpers.solver_settings(script, delete_separations=value)
    assert "SEPARATION" not in script.render()


def test_bulk_separation_is_refused_on_a_build_whose_grammar_drops_the_type():
    """The 26.101 form is three arguments and BulkSeparation models four.

    Added in round four with no test, which is why round five found it:
    the message it exists to replace is the binder's generic one, which
    names an argument the caller never typed and cites the 26.120 manual
    page to somebody whose grammar is documented at FSM-26.101 p.341.
    """
    script = Script(version="26.101")
    with pytest.raises(CommandArgumentError, match="does not take") as caught:
        helpers.solver_settings(
            script,
            aoa=3.0,
            bulk_separation=BulkSeparation(name="GEAR", separation_type="FLAT_PLATE", diameter=0.2),
        )
    message = str(caught.value)
    assert "26.101" in message, "the refusal must name the build the caller is on"
    assert "FSM-26.101 p.341" in message, "and the page where their own grammar lives"
    assert "Script.emit" in message, "and the way through"
    assert script.render() == "\n", "a refusal must leave the caller's script untouched"

    # The control: the four-argument form is exactly right on 26.120, so
    # the refusal is about the version and not about the model.
    working = Script(version="26.120")
    working.allow_broken("CREATE_BULK_SEPARATION", reason=_BULK_GRAMMAR)
    helpers.solver_settings(
        working,
        bulk_separation=BulkSeparation(name="GEAR", separation_type="FLAT_PLATE", diameter=0.2),
    )
    assert "CREATE_BULK_SEPARATION GEAR FLAT_PLATE -1 0.2" in working.render()


def test_the_two_new_settings_keywords_emit_and_record_their_provenance():
    """Surface roughness and thin boundaries, added with the chapter.

    The snapshot guard is what required them: every command of the
    settings families must carry a FlagSpec, or the provenance record
    silently lags the database. That guard is why this pair has a
    keyword at all, and this asserts both halves, the emission and the
    snapshot entry.
    """
    script = Script(version="26.120")
    script.declare_existing(boundaries=6)
    setup = helpers.solver_settings(script, surface_roughness=23.5, thin_boundaries=[1, 2, 4])
    text = script.render()
    assert "SET_SURFACE_ROUGHNESS 23.5" in text
    assert "SET_THIN_BOUNDARIES 3\n1,2,4\n" in text

    roughness = setup.flags["SET_SURFACE_ROUGHNESS"]
    assert roughness.provenance == "explicit" and roughness.value == 23.5 and roughness.emitted
    thin = setup.flags["SET_THIN_BOUNDARIES"]
    assert thin.provenance == "explicit" and thin.emitted


def test_the_all_boundaries_thin_form_is_reachable_and_the_three_states_differ():
    """None, "all" and the empty sequence are three different things.

    Until 2026-08-07 the helper refused ``"all"`` and its refusal
    recommended ``["all"]``, which then failed again as an unknown
    boundary label. The command's own -1 form marks every mesh boundary
    thin and takes no index line (FSM-26.120 p.343).
    """
    everything = Script(version="26.120")
    everything.declare_existing(boundaries=6)
    setup = helpers.solver_settings(everything, thin_boundaries="all")
    assert "SET_THIN_BOUNDARIES -1" in everything.render()
    assert "DELETE_THIN_BOUNDARIES" not in everything.render()
    # The snapshot too, not the emission alone: the state whose emission
    # was the defect is the one the provenance record had no guard for.
    marked = setup.flags["SET_THIN_BOUNDARIES"]
    assert marked.provenance == "explicit" and marked.value == "all" and marked.emitted
    assert setup.flags["DELETE_THIN_BOUNDARIES"].provenance != "explicit"

    erased = Script(version="26.120")
    erased.declare_existing(boundaries=6)
    helpers.solver_settings(erased, thin_boundaries=[])
    assert "DELETE_THIN_BOUNDARIES" in erased.render()
    assert "SET_THIN_BOUNDARIES" not in erased.render()

    untouched = Script(version="26.120")
    untouched.declare_existing(boundaries=6)
    helpers.solver_settings(untouched)
    assert "THIN_BOUNDARIES" not in untouched.render()


def test_the_thin_boundary_keyword_names_the_build_that_lacks_the_command():
    """The pair is absent from the February 2026 build.

    The helper emits unconditionally, so the refusal surfaces from the
    emitter. That is fine, and it is exactly what must not be swallowed
    or downgraded by a later helper change: the message has to name the
    build and what evidence does exist. Surface roughness is the
    control, because that command IS in February (FSM-26.100 p.338) and
    must go on emitting there.
    """
    february = Script(version="26.100")
    with pytest.raises(CommandNotInVersionError) as caught:
        helpers.solver_settings(february, thin_boundaries=[1])
    message = str(caught.value)
    assert "SET_THIN_BOUNDARIES" in message
    assert "26.100" in message, "the refusal must name the build the caller is on"
    assert "26.101" in message, "and the earliest build that does carry it"

    control = Script(version="26.100")
    helpers.solver_settings(control, surface_roughness=23.5)
    assert "SET_SURFACE_ROUGHNESS 23.5" in control.render()


def test_an_empty_thin_boundary_list_erases_rather_than_setting_none():
    """The same rule as viscous_excluded, and for the same reason.

    A count of zero with an empty index line asks the parser to read a
    line that carries nothing; the solver has a command for the erase.
    """
    script = Script(version="26.120")
    helpers.solver_settings(script, thin_boundaries=[])
    text = script.render()
    assert "DELETE_THIN_BOUNDARIES" in text
    assert "SET_THIN_BOUNDARIES" not in text


# --- the two settings flags of the tail, and the kind one of them needed -----


def test_the_bare_request_flag_emits_a_command_with_no_argument():
    """DISABLE_SOLVER_REF_VELOCITY takes nothing, so True IS its whole value.

    The kind exists because every other flag records a value the command
    carries and this one carries none. Untested until the 2026-08-08 QA
    pass, which is how a snapshot could have silently dropped or
    duplicated a command that changes what a reported Cp is normalised
    by.
    """
    script = Script(version="26.121")
    setup = helpers.solver_settings(script, disable_ref_velocity=True)
    assert script.render().count("DISABLE_SOLVER_REF_VELOCITY") == 1
    record = setup.flags["DISABLE_SOLVER_REF_VELOCITY"]
    assert (record.provenance, record.value, record.emitted) == ("explicit", True, True)


def test_a_bare_request_not_made_is_unknown_rather_than_an_explicit_false():
    """False is the ABSENCE of the request, not the opposite request.

    The solver has no way to be told NOT to do this, so recording an
    explicit False would claim the script settled a question it never
    asked. That distinction is the whole reason the kind is not a
    toggle.
    """
    script = Script(version="26.121")
    setup = helpers.solver_settings(script, disable_ref_velocity=False)
    assert "DISABLE_SOLVER_REF_VELOCITY" not in script.render()
    record = setup.flags["DISABLE_SOLVER_REF_VELOCITY"]
    assert (record.provenance, record.emitted) == ("unknown", False)


def test_a_bare_request_round_trips_through_the_snapshot():
    """The snapshot has to rebuild a command whose value is its presence."""
    first = Script(version="26.121")
    setup = helpers.solver_settings(first, disable_ref_velocity=True, solver_stabilization=0.5)
    second = Script(version="26.121")
    helpers.solver_settings(second, **setup.explicit_kwargs())
    assert second.render() == first.render()


def test_the_stabilization_strength_keeps_its_documented_zero():
    """Zero is a documented value here and not an unset flag.

    The manual states that 0 is the same as disabling the stabilization,
    so it is a strength that happens to reach zero. A falsy-value
    regression in the helper would drop the line and leave the solver on
    whatever the previous state was.
    """
    script = Script(version="26.121")
    setup = helpers.solver_settings(script, solver_stabilization=0.0)
    assert "SOLVER_STABILIZATION 0.0" in script.render()
    assert setup.flags["SOLVER_STABILIZATION"].provenance == "explicit"


def _fr316_row_setup_keys___row(pol: str, cell: str) -> str:
    """One active steady row naming preset s002, with ``cell`` as its VAR_NAMES_VALUES."""
    return (
        f"{pol} | TestWing | ROW_SETUP | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
        f"| 003 |          | 0 | 1 | {cell}"
    )


def _fr316_row_setup_keys___resolve(tmp_path, *rows: str) -> dict[str, SimCase]:
    workspace = _fr316_row_setup_keys__make_library(tmp_path)
    path = _fr316_row_setup_keys__write_matrix(tmp_path / "rows.fs", list(rows))
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("| LEGACY ", "| steady "), encoding="utf-8")
    resolved = resolve_matrix(
        path,
        workspace,
        name="rows",
        fs_version="26.124",
        recipes=_FR316_ROW_SETUP_KEYS__RECIPES,
        fs_exe="C:/fs/FlightStream.exe",
    )
    return {sim.sim_id: sim for sim in resolved.campaign.sims}


def _fr316_row_setup_keys___settings_lines(case: SimCase) -> list[str]:
    script = Script(version="26.124")
    _settings(case, script)
    return script.render().splitlines()


class TestFr316RowSetupKeys:
    """Tier 1: a matrix row states native setup keys over its preset (FR-316).

    The evidence line of FR-316 cites this module
    (docs/unpublished/requirements/functional-requirements.md).

    The rule under test: ``plan`` warns for every row that writes setup keys,
    naming the row and the keys; a key the preset does not state is added for that
    row only; an equal value is accepted; a different value for a key the preset
    states is refused, naming the row, the key and both values. The preset here is
    ``s002`` of the synthetic library: ``iterations = 800`` and
    ``convergence = 1e-6``.
    """

    @staticmethod
    def test_a_key_the_preset_lacks_is_added_for_that_row_only_and_warned(tmp_path):
        """FR-316: warn-only on a key the preset does not state; the next row keeps its preset."""
        with pytest.warns(PyflightstreamWarning, match=r"POL 9401.*viscous_coupling = ENABLE"):
            cases = _fr316_row_setup_keys___resolve(
                tmp_path,
                _fr316_row_setup_keys___row("9401", "viscous_coupling: ENABLE"),
                _fr316_row_setup_keys___row("9402", ""),
            )
        stated, control = cases["9401"], cases["9402"]
        assert stated.solver.viscous_coupling is True
        assert stated.setup_from_row == {"viscous_coupling": "ENABLE"}
        assert "viscous_coupling" not in stated.variables
        # THE CONTROL: the override does not leak into the next row of the same preset.
        assert control.solver.viscous_coupling is None
        assert control.setup_from_row == {}
        assert "SET_SOLVER_VISCOUS_COUPLING ENABLE" in _fr316_row_setup_keys___settings_lines(
            stated
        )
        assert not any(
            "VISCOUS_COUPLING" in line for line in _fr316_row_setup_keys___settings_lines(control)
        )

    @staticmethod
    def test_an_equal_value_is_accepted_with_the_warning(tmp_path):
        """FR-316: warn-only on an equal value, judged by the loader (1e-6 equals 0.000001)."""
        with pytest.warns(PyflightstreamWarning, match=r"POL 9403.*iterations = 800"):
            cases = _fr316_row_setup_keys___resolve(
                tmp_path,
                _fr316_row_setup_keys___row("9403", "iterations: 800 / convergence: 0.000001"),
            )
        case = cases["9403"]
        assert case.solver.iterations == 800
        assert case.solver.convergence == pytest.approx(1e-6)
        assert case.setup_from_row == {"iterations": "800", "convergence": "0.000001"}

    @staticmethod
    def test_a_differing_value_for_a_key_the_preset_states_is_refused(tmp_path):
        """FR-316: refused at plan, naming the row, the key and both values."""
        with pytest.raises(MatrixError) as refused:
            _fr316_row_setup_keys___resolve(
                tmp_path, _fr316_row_setup_keys___row("9404", "iterations: 500")
            )
        said = str(refused.value)
        assert "9404" in said, said
        assert "iterations = 500" in said, said
        assert "iterations = 800" in said, said
        assert "does not overwrite" in said, said

    @staticmethod
    def test_a_solver_alias_is_a_setup_key_and_follows_the_same_rule(tmp_path):
        """FR-316: NITER, the solver's spelling of iterations, differing from 800, is refused."""
        with pytest.raises(MatrixError, match=r"NITER = 500.*iterations = 800"):
            _fr316_row_setup_keys___resolve(
                tmp_path, _fr316_row_setup_keys___row("9405", "NITER: 500")
            )

    @staticmethod
    def test_an_unstated_row_resolves_its_preset_unchanged(tmp_path):
        """FR-316 control: a row stating no setup key carries the preset's own settings object."""
        cases = _fr316_row_setup_keys___resolve(tmp_path, _fr316_row_setup_keys___row("9406", ""))
        case = cases["9406"]
        assert case.setup_from_row == {}
        assert case.solver.iterations == 800
        assert case.solver.viscous_coupling is None

    @staticmethod
    def test_an_unknown_key_is_still_refused(tmp_path):
        """FR-316 control: a key that is neither a run-type key nor a setup field stays refused."""
        from pyflightstream.cases import CampaignConfigError
        from pyflightstream.cases.workflows import build_script

        cases = _fr316_row_setup_keys___resolve(
            tmp_path, _fr316_row_setup_keys___row("9407", "viscous_couplingg: ENABLE")
        )
        with pytest.raises(CampaignConfigError, match="viscous_couplingg"):
            build_script(cases["9407"], Script(version="26.124"))

    @staticmethod
    def test_a_table_valued_key_is_refused_naming_what_a_row_can_carry(tmp_path):
        """FR-316: a cell cannot carry a table, so the key is a preset's only."""
        assert "airfoil_separation" in structured_setup_keys()
        assert "vorticity_drag_families" not in structured_setup_keys()
        with pytest.raises(MatrixError, match=r"airfoil_separation.*cannot carry a table"):
            _fr316_row_setup_keys___resolve(
                tmp_path, _fr316_row_setup_keys___row("9408", "airfoil_separation: wing")
            )

    @staticmethod
    def test_a_list_of_names_is_carried_comma_separated(tmp_path):
        """FR-316: a list-valued key is written in the cell as comma-separated names."""
        with pytest.warns(PyflightstreamWarning):
            cases = _fr316_row_setup_keys___resolve(
                tmp_path, _fr316_row_setup_keys___row("9409", "vorticity_drag_families: wing, tail")
            )
        assert cases["9409"].solver.vorticity_drag_families == ["wing", "tail"]

    @staticmethod
    def test_one_setting_in_both_vocabularies_is_refused_as_ambiguous(tmp_path):
        """FR-316: SYMMETRY_LOADS (run type) beside symmetry_loads (setup) names one setting twice."""  # noqa: E501
        with pytest.raises(MatrixError, match=r"ambiguous"):
            _fr316_row_setup_keys___resolve(
                tmp_path,
                _fr316_row_setup_keys___row(
                    "9410", "SYMMETRY_LOADS: DISABLE / symmetry_loads: ENABLE"
                ),
            )

    @staticmethod
    def test_an_invalid_value_is_refused_by_the_presets_own_loader(tmp_path):
        """FR-316: the value is validated by the loader the preset went through, naming the row."""
        with pytest.raises(MatrixError, match=r"(?s)POL 9411.*farfield_layers"):
            _fr316_row_setup_keys___resolve(
                tmp_path, _fr316_row_setup_keys___row("9411", "farfield_layers: 9")
            )

    @staticmethod
    def test_the_row_keys_reach_the_setup_snapshot_of_the_run_record(tmp_path):
        """FR-316: the snapshot the record carries says which effective values came from the row."""
        with pytest.warns(PyflightstreamWarning):
            cases = _fr316_row_setup_keys___resolve(
                tmp_path, _fr316_row_setup_keys___row("9412", "viscous_coupling: ENABLE")
            )
        script = Script(version="26.124")
        _settings(cases["9412"], script)
        assert script.solver_setup is not None
        dumped = script.solver_setup.model_dump(mode="json")
        assert dumped["from_row"] == {"viscous_coupling": "ENABLE"}
        assert dumped["flags"]["SET_SOLVER_VISCOUS_COUPLING"]["value"] in (True, "ENABLE")
        # THE CONTROL: a snapshot with nothing from the row serializes without the key.
        bare = Script(version="26.124")
        _settings(
            _fr316_row_setup_keys___resolve(
                tmp_path / "b", _fr316_row_setup_keys___row("9413", "")
            )["9413"],
            bare,
        )
        assert bare.solver_setup is not None
        assert "from_row" not in bare.solver_setup.model_dump(mode="json")

    @staticmethod
    def test_one_setting_in_two_spellings_of_a_row_is_refused_as_stated_twice(tmp_path):
        # Verifies FR-316.
        with pytest.raises(MatrixError, match="twice"):
            _fr316_row_setup_keys___resolve(
                tmp_path, _fr316_row_setup_keys___row("9414", "iterations: 800 / NITER: 800")
            )


_FR317_FR318_MOMENTS_MODEL__BUILD = "26.124"


def _fr317_fr318_moments_model___wing(tmp_path, **solver: object) -> SimCase:
    """A steady wing-body row over a saved geometry whose boundaries are W and B."""
    return SimCase(
        sim_id="6201",
        aircraft="WB",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[2.0]),
        variables={"WORKFLOW": "steady", "VELOCITY": "30.0"},
        geometry=str(tmp_path / "wb.obj"),
        inventory=("W", "B"),
        inventory_source="sidecar",
        mesh_import=MeshImport(units="METER"),
        raw_mesh_conditions=RawMeshConditions(trailing_edges=TrailingEdgeMarking(route="detect")),
        solver=SolverSettings(**solver),
        reference=ReferenceData(area=50.0, length=2.5, span_m=20.0, moment_point_m=(0.6, 0.0, 0.0)),
        point={"alpha": 2.0, "beta": 0.0},
        outputs=["AL+020.txt"],
    )


def _fr317_fr318_moments_model___lines(case: SimCase) -> list[str]:
    script = Script(_FR317_FR318_MOMENTS_MODEL__BUILD)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    return script.render().splitlines()


def _fr317_fr318_moments_model___families(moments_model: str | None = None) -> SimCase:
    solver = SolverSettings(vorticity_drag_families=["Blade"], moments_model=moments_model)
    return _fr317_fr318_moments_model__rotor_case().model_copy(update={"solver": solver})


class TestFr317Fr318MomentsModel:
    """Tier 1: the moments model is a setup key, linked to the vorticity drag on a rotor.

    The evidence lines of FR-317 and FR-318 cite this module
    (docs/unpublished/requirements/functional-requirements.md).

    FR-317: ``moments_model`` states SET_ANALYSIS_MOMENTS_MODEL; unstated, the
    script is byte-identical to the one the package wrote before the key existed.
    FR-318: on a row turning a rotor, ``vorticity_drag_families`` with no
    ``moments_model`` implies VORTICITY (warned, recorded in the snapshot), and
    ``moments_model = PRESSURE`` beside it is refused at plan naming both keys.
    """

    @staticmethod
    def test_an_unstated_moments_model_leaves_the_script_byte_identical(tmp_path):
        """FR-317 control: unstated and PRESSURE write the same bytes, as before the key."""
        unstated = _fr317_fr318_moments_model___lines(_fr317_fr318_moments_model___wing(tmp_path))
        pressure = _fr317_fr318_moments_model___lines(
            _fr317_fr318_moments_model___wing(tmp_path, moments_model="PRESSURE")
        )
        assert unstated == pressure
        assert "SET_ANALYSIS_MOMENTS_MODEL PRESSURE" in unstated

    @staticmethod
    def test_a_stated_moments_model_changes_that_line_and_no_other(tmp_path):
        """FR-317: VORTICITY reaches SET_ANALYSIS_MOMENTS_MODEL, before START_SOLVER."""
        control = _fr317_fr318_moments_model___lines(_fr317_fr318_moments_model___wing(tmp_path))
        stated = _fr317_fr318_moments_model___lines(
            _fr317_fr318_moments_model___wing(tmp_path, moments_model="vorticity")
        )
        changed = [(a, b) for a, b in zip(control, stated, strict=True) if a != b]
        assert changed == [
            ("SET_ANALYSIS_MOMENTS_MODEL PRESSURE", "SET_ANALYSIS_MOMENTS_MODEL VORTICITY")
        ]
        assert stated.index("SET_ANALYSIS_MOMENTS_MODEL VORTICITY") < stated.index("START_SOLVER")

    @staticmethod
    def test_a_moments_model_the_command_does_not_take_is_refused():
        """FR-317: the tokens are the command database's, PRESSURE and VORTICITY."""
        with pytest.raises(ValueError, match=r"PRESSURE, VORTICITY"):
            SolverSettings(moments_model="CIRCULATION")

    @staticmethod
    def test_a_stated_moments_model_is_emitted_where_no_frame_is_placed():
        """FR-317: without a moment point the model is still stated; unstated, nothing is emitted."""  # noqa: E501
        stated = SimCase(
            sim_id="1",
            aircraft="A",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            solver=SolverSettings(moments_model="VORTICITY"),
        )
        script = Script(_FR317_FR318_MOMENTS_MODEL__BUILD)
        analysis_frame_and_moments(stated, script, None, rotor=False)
        assert script.render().splitlines() == ["SET_ANALYSIS_MOMENTS_MODEL VORTICITY"]
        bare = Script(_FR317_FR318_MOMENTS_MODEL__BUILD)
        analysis_frame_and_moments(
            stated.model_copy(update={"solver": SolverSettings()}), bare, None, rotor=False
        )
        assert bare.render().strip() == ""

    @staticmethod
    def test_on_a_rotor_vorticity_drag_implies_vorticity_moments_warned_and_recorded():
        """FR-318: an unstated model follows the drag list on a rotor, warned and recorded."""
        case = _fr317_fr318_moments_model___families()
        script = Script(_FR317_FR318_MOMENTS_MODEL__BUILD)
        helpers.solver_settings(script, iterations=10)
        with pytest.warns(PyflightstreamWarning, match=r"vorticity_drag_families.*moments_model"):
            analysis_frame_and_moments(case, script, None, rotor=True)
        assert "SET_ANALYSIS_MOMENTS_MODEL VORTICITY" in script.render().splitlines()
        assert script.solver_setup is not None
        derived = script.solver_setup.model_dump(mode="json")["derived"]
        assert derived["moments_model"].startswith("VORTICITY"), derived
        assert "FR-318" in derived["moments_model"]

    @staticmethod
    def test_on_a_rotor_pressure_moments_beside_vorticity_drag_are_refused():
        """FR-318: an explicit PRESSURE beside the drag list is refused, naming both keys."""
        with pytest.raises(CampaignConfigError) as refused:
            moments_model_of(_fr317_fr318_moments_model___families("PRESSURE"), rotor=True)
        said = str(refused.value)
        assert "vorticity_drag_families" in said and "moments_model = PRESSURE" in said, said
        assert "7001" in said, said

    @staticmethod
    def test_the_link_holds_only_on_a_rotor_and_only_with_a_drag_list():
        """FR-318 controls: no rotor, or no drag list, leaves the model as stated."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", PyflightstreamWarning)
            assert moments_model_of(_fr317_fr318_moments_model___families(), rotor=False) == (
                None,
                False,
            )
            bare = _fr317_fr318_moments_model__rotor_case()
            assert moments_model_of(bare, rotor=True) == (None, False)
            assert moments_model_of(
                _fr317_fr318_moments_model___families("VORTICITY"), rotor=True
            ) == ("VORTICITY", False)
            assert moments_model_of(
                _fr317_fr318_moments_model___families("PRESSURE"), rotor=False
            ) == ("PRESSURE", False)

    @staticmethod
    def test_a_rotor_row_is_recognised_by_the_builder(tmp_path):
        """FR-318 through the builder: the unsteady_rotor row with a drag list states VORTICITY.

        It also pins the order: the moments model, then the vorticity drag list,
        then START_SOLVER (FR-568 of 0.35.0, RPT-133; 0.34.0 emitted the list after
        START_SOLVER, the limit FR-318 stated).
        """
        case = _fr317_fr318_moments_model__rotor_case().model_copy(
            update={
                "geometry": str(tmp_path / "rotor.obj"),
                "inventory": ("Blade", "Hub"),
                "inventory_source": "sidecar",
                "mesh_import": MeshImport(units="METER"),
                "raw_mesh_conditions": RawMeshConditions(
                    trailing_edges=TrailingEdgeMarking(route="detect")
                ),
                "reference": ReferenceData(area=1.0, length=0.1, span_m=1.0),
                "solver": SolverSettings(vorticity_drag_families=["Blade"]),
            }
        )
        script = Script(_FR317_FR318_MOMENTS_MODEL__BUILD)
        with pytest.warns(PyflightstreamWarning, match="FR-318"):
            build_script(case, script)
        lines = script.render().splitlines()
        start = lines.index("START_SOLVER")
        drag = next(
            i for i, line in enumerate(lines) if line.startswith("SET_VORTICITY_DRAG_BOUNDARIES")
        )
        assert lines.index("SET_ANALYSIS_MOMENTS_MODEL VORTICITY") < drag < start

    @staticmethod
    def test_a_steady_row_stating_a_rotor_speed_follows_the_vorticity_link(tmp_path):
        # Verifies FR-318.
        case = _fr317_fr318_moments_model__rotor_case(
            **{_FR317_FR318_MOMENTS_MODEL__WORKFLOW_KEY: None}
        ).model_copy(
            update={
                "recipe": "steady",
                "geometry": str(tmp_path / "rotor.obj"),
                "inventory": ("Blade", "Hub"),
                "inventory_source": "sidecar",
                "mesh_import": MeshImport(units="METER"),
                "raw_mesh_conditions": RawMeshConditions(
                    trailing_edges=TrailingEdgeMarking(route="detect")
                ),
                "reference": ReferenceData(area=1.0, length=0.1, span_m=1.0),
                "solver": SolverSettings(vorticity_drag_families=["Blade"]),
            }
        )
        script = Script(_FR317_FR318_MOMENTS_MODEL__BUILD)
        with pytest.warns(PyflightstreamWarning, match="FR-318"):
            build_script(case, script)
        assert "SET_ANALYSIS_MOMENTS_MODEL VORTICITY" in script.render().splitlines()
