"""Review regressions for frame deletion, export identity and version defaults.

Reproductions: delete reference frame 1, export a sweep over a loads file,
and build a 26.125 solver snapshot without an explicit jet decay length.
"""

import pytest

from pyflightstream.script import CommandArgumentError, Script, helpers


@pytest.mark.parametrize(
    "locals_count", [0, 2], ids=["P0400-REFDELETE-empty", "P0400-REFDELETE-local"]
)
def test_p0400_reference_frame_cannot_be_deleted(locals_count):
    script = Script("26.124")
    script.declare_existing(frames=locals_count)
    before = script.render()
    with pytest.raises(CommandArgumentError, match="reference frame"):
        script.emit("DELETE_COORDINATE_SYSTEM", 1)
    assert script.render() == before
    assert script.num_local_frames == locals_count
    script.emit("CREATE_NEW_COORDINATE_SYSTEM", label="next")
    assert script.entities.labels("frames")["next"] == locals_count + 2


@pytest.mark.parametrize(
    "sweep_first", [True, False], ids=["P0400-SWEEPEXPORT-first", "P0400-SWEEPEXPORT-last"]
)
def test_p0400_sweep_exports_share_output_identity(sweep_first):
    script = Script("26.124")
    commands = ["SWEEPER_EXPORT_SPREADSHEET", "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"]
    if not sweep_first:
        commands.reverse()
    script.emit(commands[0], "results.txt")
    before = script.render()
    with pytest.raises(CommandArgumentError, match="already exports to"):
        script.emit(commands[1], "sub/../RESULTS.txt")
    assert script.render() == before


@pytest.mark.parametrize(
    "command",
    ["CAD_CREATE_CURVE_EXPORT_CCS", "STABILITY_TOOLBOX_EXPORT", "UNSTEADY_SOLVER_EXPORT_PLOTS"],
    ids=["P0400-EXPORT-cad", "P0400-EXPORT-stability", "P0400-EXPORT-unsteady"],
)
def test_p0400_exports_with_other_prefixes_share_output_identity(command):
    script = Script("26.124")
    script.emit(command, "results.txt")
    before = script.render()
    with pytest.raises(CommandArgumentError, match="already exports to"):
        script.emit(command, "sub/../RESULTS.txt")
    assert script.render() == before


@pytest.mark.parametrize(
    "version", ["26.124", "26.125"], ids=["P0400-JETDEFAULT-earlier", "P0400-JETDEFAULT-changed"]
)
def test_p0400_jet_default_never_claims_the_wrong_editions_value(version):
    script = Script(version)
    setup = helpers.solver_settings(script)
    record = setup.flags["SET_JET_WAKE_DECAY_NORMALIZED_LENGTH"]
    if version == "26.124":
        assert (record.provenance, record.value) == ("default", 100.0)
    else:
        # The accepted fallback until per-version defaults have a schema.
        assert (record.provenance, record.value, record.evidence) == ("unknown", None, None)
    assert not record.emitted
    setup = helpers.solver_settings(script, jet_wake_decay_normalized_length=17.0)
    explicit = setup.flags["SET_JET_WAKE_DECAY_NORMALIZED_LENGTH"]
    assert (explicit.provenance, explicit.value, explicit.emitted) == ("explicit", 17.0, True)
