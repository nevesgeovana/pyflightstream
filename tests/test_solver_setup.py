"""Tier 1: solver-setup snapshot, provenance, deferral, and regeneration."""

import json
import warnings

import pytest

from pyflightstream.commands import CommandRegistry
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptReferenceError,
    helpers,
)
from pyflightstream.script.solver_setup import (
    FLAG_SPECS,
    LIBRARY_MINIMUM_CP,
    SNAPSHOT_FAMILIES,
    VORTICITY_COMMAND,
    BulkSeparation,
    SolverSetup,
    script_from_setup,
    with_vorticity_selection,
)
from pyflightstream.workspace import RunRecord, RunStatus


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
    script = Script(version="26.12")
    setup = helpers.solver_settings(script, vorticity_drag_boundaries="all")
    assert set(setup.flags) == family_commands() | {VORTICITY_COMMAND}
    assert setup.fs_version == "26.120"


# --- provenance markers and evidence ----------------------------------------


def test_provenance_markers_and_default_evidence():
    script = Script(version="26.12")
    setup = helpers.solver_settings(script, aoa=2.0, vorticity_drag_boundaries="all")
    flags = setup.flags
    aoa = flags["SOLVER_SET_AOA"]
    assert aoa.provenance == "explicit" and aoa.value == 2.0 and aoa.emitted
    assert aoa.evidence is None
    minimum_cp = flags["SOLVER_MINIMUM_CP"]
    assert minimum_cp.provenance == "default"
    assert minimum_cp.value == LIBRARY_MINIMUM_CP
    assert minimum_cp.emitted
    assert "SRC-003 p.221" in minimum_cp.evidence
    assert "reseed-cp100" in minimum_cp.evidence
    boundary_layer = flags["SET_BOUNDARY_LAYER_TYPE"]
    assert boundary_layer.provenance == "default"
    assert boundary_layer.value == "TRANSITIONAL"
    assert not boundary_layer.emitted
    assert boundary_layer.evidence == "SRC-003 p.203"
    farfield = flags["SOLVER_SET_FARFIELD_LAYERS"]
    assert farfield.provenance == "default"
    assert farfield.value == 3
    assert farfield.evidence == "SRC-003 p.344"
    unknown = flags["SET_WAKE_ON_WAKE_INDUCTION"]
    assert unknown.provenance == "unknown"
    assert unknown.value is None and unknown.evidence is None and not unknown.emitted
    vorticity = flags[VORTICITY_COMMAND]
    assert vorticity.provenance == "explicit" and vorticity.value == "all" and vorticity.emitted
    counts = setup.provenance_counts()
    assert counts["explicit"] == 2  # aoa and the vorticity selection
    assert counts["default"] == 3  # minimum_cp, boundary_layer, farfield_layers
    assert counts["explicit"] + counts["default"] + counts["unknown"] == len(flags)


def test_defaults_of_commands_absent_from_the_version_stay_unknown():
    # 26.100 records no evidence for the advanced_settings commands, so
    # the library default is not emitted and nothing is claimed.
    script = Script(version="26.1")
    setup = helpers.solver_settings(script, vorticity_drag_boundaries="all")
    assert "SOLVER_MINIMUM_CP" not in script.render()
    assert setup.flags["SOLVER_MINIMUM_CP"].provenance == "unknown"
    assert setup.flags["SET_BOUNDARY_LAYER_TYPE"].provenance == "unknown"


# --- the optional vorticity selection ---------------------------------------


def test_an_unset_selection_emits_nothing_and_leaves_the_solver_default():
    # SRC-003 p.202: boundaries outside the vorticity CDi list use the
    # solver's surface pressure integration, a complete drag calculation.
    # Omitting the selection must therefore build a valid script, not a
    # refusal (the legacy reproduction path leaves the list unset).
    script = Script(version="26.12")
    setup = helpers.solver_settings(script, aoa=3.0, velocity=30.0)
    helpers.start_solver(script)
    text = script.render()
    assert VORTICITY_COMMAND not in text
    assert "SOLVER_SET_AOA 3.0" in text and "START_SOLVER" in text
    record = setup.flags[VORTICITY_COMMAND]
    assert record.provenance == "default"
    assert record.value == [] and not record.emitted
    assert "SRC-003 p.202" in record.evidence
    # The snapshot stays total, with the flag counted as a default.
    counts = setup.provenance_counts()
    assert counts["explicit"] == 2  # aoa and velocity
    assert counts["default"] == 4  # minimum_cp, boundary_layer, farfield, vorticity
    assert counts["explicit"] + counts["default"] + counts["unknown"] == len(setup.flags)


def test_an_unset_selection_stays_unknown_without_the_command_in_the_version():
    # 26.000 records no evidence for the selection command, so the
    # library claims no default there (invariant 3, honest unknown).
    script = Script(version="26.0")
    setup = helpers.solver_settings(script)
    record = setup.flags[VORTICITY_COMMAND]
    assert record.provenance == "unknown"
    assert record.value is None and record.evidence is None and not record.emitted


def test_an_unset_selection_round_trips_through_the_snapshot():
    first = Script(version="26.12")
    setup = helpers.solver_settings(first, aoa=3.0)
    helpers.start_solver(first)
    second = Script(version="26.12")
    regenerated = script_from_setup(
        second, SolverSetup.model_validate_json(setup.model_dump_json())
    )
    helpers.start_solver(second)
    assert second.render() == first.render()
    assert VORTICITY_COMMAND not in second.render()
    assert regenerated == setup


@pytest.mark.parametrize("empty", [[], ()])
def test_an_empty_selection_is_refused_and_emits_nothing(empty):
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="empty sequence"):
        helpers.solver_settings(script, vorticity_drag_boundaries=empty)
    assert script.render() == "\n"  # nothing was emitted


def test_a_second_settings_call_keeps_the_selection_in_script_and_snapshot():
    # solver_settings emits only what it is passed, so a second call on
    # the same script must not drop the selection of the first: the
    # script would lose the vorticity integration silently and the
    # snapshot would record a default that never applied.
    script = Script(version="26.12")
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
    script = Script(version="26.12")
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
    script = Script(version="26.12")
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
    script = Script(version="26.12")
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
    script = Script(version="26.12")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    script.emit("START_SOLVER")
    with pytest.raises(CommandArgumentError, match="empty sequence"):
        helpers.analysis_setup(script, vorticity_drag_boundaries=[])
    assert VORTICITY_COMMAND not in script.render()  # the selection survives


@pytest.mark.parametrize("selection", ["all", [1, 2]])
def test_with_vorticity_selection_restamps_without_touching_the_input(selection):
    script = Script(version="26.12")
    setup = helpers.solver_settings(script, aoa=3.0)
    restamped = with_vorticity_selection(setup, selection)
    record = restamped.flags[VORTICITY_COMMAND]
    assert record.provenance == "explicit" and record.emitted
    assert record.value == selection and record.evidence is None
    assert setup.flags[VORTICITY_COMMAND].provenance == "default"  # input untouched


def test_a_bare_vorticity_label_is_rejected_with_the_fix():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match=r"\['wing'\]"):
        helpers.solver_settings(script, vorticity_drag_boundaries="wing")


def test_vorticity_labels_resolve_and_range_check_at_call_time():
    script = Script(version="26.12")
    script.declare_existing(boundaries={"wing": 1, "tail": 2})
    helpers.solver_settings(script, vorticity_drag_boundaries=["tail"])
    helpers.start_solver(script)
    assert "START_SOLVER\nSET_VORTICITY_DRAG_BOUNDARIES 1\n2" in script.render()
    bad = Script(version="26.12")
    bad.declare_existing(boundaries=2)
    with pytest.raises(ScriptReferenceError, match="solver_settings"):
        helpers.solver_settings(bad, vorticity_drag_boundaries=[3])
    assert "SOLVER_MINIMUM_CP" not in bad.render()  # nothing emitted before the error


# --- deferred emission of the analysis-phase selection ----------------------


def test_vorticity_defers_until_the_solver_starts():
    script = Script(version="26.12")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    assert VORTICITY_COMMAND not in script.render()
    helpers.start_solver(script)
    assert "START_SOLVER\nSET_VORTICITY_DRAG_BOUNDARIES -1" in script.render()
    # The flush happens once; a second analysis helper does not repeat it.
    helpers.export_results(script, spreadsheet="C:/out/loads.txt")
    assert script.render().count(VORTICITY_COMMAND) == 1


def test_export_results_flushes_a_pending_selection():
    script = Script(version="26.12")
    helpers.solver_settings(script, vorticity_drag_boundaries=[1, 2])
    script.emit("START_SOLVER")
    helpers.export_results(script, spreadsheet="C:/out/loads.txt")
    text = script.render()
    assert "SET_VORTICITY_DRAG_BOUNDARIES 2\n1,2" in text
    assert text.index(VORTICITY_COMMAND) < text.index("EXPORT_SOLVER_ANALYSIS_SPREADSHEET")


def test_analysis_setup_flushes_only_when_it_reaches_the_analysis_phase():
    script = Script(version="26.12")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    # symmetry_loads alone is an init-phase call: no flush yet.
    helpers.analysis_setup(script, symmetry_loads=True)
    assert VORTICITY_COMMAND not in script.render()
    script.emit("START_SOLVER")
    helpers.analysis_setup(script, load_units="COEFFICIENTS")
    text = script.render()
    assert "SET_VORTICITY_DRAG_BOUNDARIES -1" in text
    assert text.index(VORTICITY_COMMAND) < text.index("SET_LOADS_AND_MOMENTS_UNITS")


# --- the library minimum-Cp default -----------------------------------------


def test_minimum_cp_library_default_is_emitted_when_unset():
    script = Script(version="26.12")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    assert "SOLVER_MINIMUM_CP -100" in script.render()


def test_minimum_cp_override_wins_and_is_explicit():
    script = Script(version="26.12")
    setup = helpers.solver_settings(script, vorticity_drag_boundaries="all", minimum_cp=-40)
    text = script.render()
    assert "SOLVER_MINIMUM_CP -40" in text
    assert "-100" not in text
    record = setup.flags["SOLVER_MINIMUM_CP"]
    assert record.provenance == "explicit" and record.value == -40 and record.emitted


# --- solver mode and bulk separation validation -----------------------------


def test_unsteady_mode_needs_both_time_arguments():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="both time_iterations and delta_time"):
        helpers.solver_settings(script, vorticity_drag_boundaries="all", mode="UNSTEADY")
    with pytest.raises(CommandArgumentError, match="belong to the unsteady solver"):
        helpers.solver_settings(script, vorticity_drag_boundaries="all", delta_time=0.01)
    with pytest.raises(CommandArgumentError, match="STEADY or UNSTEADY"):
        helpers.solver_settings(script, vorticity_drag_boundaries="all", mode="HOVER")


def test_steady_mode_and_bulk_separation_emit():
    script = Script(version="26.12")
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
    first = Script(version="26.12")
    setup = helpers.solver_settings(first, **ROUND_TRIP_KWARGS)
    helpers.start_solver(first)
    assert first.solver_setup is setup

    payload = setup.model_dump_json()
    restored = SolverSetup.model_validate_json(payload)
    assert restored == setup

    second = Script(version="26.12")
    regenerated = script_from_setup(second, restored)
    helpers.start_solver(second)
    assert second.render() == first.render()
    assert regenerated == setup
    assert second.solver_setup is regenerated


def test_round_trip_with_defaults_only():
    first = Script(version="26.12")
    setup = helpers.solver_settings(first, vorticity_drag_boundaries="all")
    helpers.start_solver(first)
    second = Script(version="26.12")
    script_from_setup(second, SolverSetup.model_validate_json(setup.model_dump_json()))
    helpers.start_solver(second)
    assert second.render() == first.render()
    assert "SOLVER_MINIMUM_CP -100" in second.render()


# --- deprecation of the analysis_setup path ---------------------------------


def test_analysis_setup_vorticity_is_deprecated_but_works():
    script = Script(version="26.12")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    script.emit("START_SOLVER")
    with pytest.warns(
        DeprecationWarning,
        match=r"deprecated.*will leave analysis_setup in a future minor "
        r"release; this explicit call replaces the selection deferred by "
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
    script = Script(version="26.12")
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
