"""P0410: prepare the three licensed frame experiments without launching a solver."""

from pathlib import Path


def test_p0410_frame_probe_workspace_is_solver_free(tmp_path, monkeypatch):
    from lanes.ph_b1_licensed import prepare

    from pyflightstream.run import LocalExecutor

    def forbidden(*args, **kwargs):
        raise AssertionError("probe preparation launched a licensed solver")

    monkeypatch.setattr(LocalExecutor, "run_script", forbidden)
    prepared = prepare(tmp_path, Path("FlightStream_26124.exe"))
    assert set(prepared) == {"recut", "post_edit", "linked"}
    recut = prepared["recut"].read_text()
    assert recut.count("CREATE_NEW_SURFACE_SECTION") >= 2
    assert "sections_before.txt" in recut and "sections_recut.txt" in recut
    post = (prepared["post_edit"].parent / "fsi_post.txt").read_text()
    assert "EDIT_COORDINATE_SYSTEM" in post
    linked = prepared["linked"].read_text()
    assert "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS 2" in linked
    assert "MIDSPAN_PROBE" in linked
    assert (prepared["linked"].parent / "fsi_frozen_displacements.txt").is_file()
    assert "frame_before.fsm" in linked
    assert "frame_after.fsm" in (prepared["linked"].parent / "fsi_post.txt").read_text()
    assert linked.rstrip().endswith("EXECUTE_AEROELASTIC_ANALYSIS")
    assert (tmp_path / "harmonics" / "harmonics.fs").is_file()
    assert (tmp_path / "harmonics" / "post" / "harmonics" / "plan.json").is_file()
