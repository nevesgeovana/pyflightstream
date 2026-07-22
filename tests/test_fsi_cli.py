"""Tier 1: WP1 dummy executable behavior of pyfs-fsi."""

import json

from pyflightstream.fsi import cli


def test_init_dummy_then_step_writes_zero_displacements(tmp_path):
    assert cli.main(["init-dummy", "--node-count", "6", "--dir", str(tmp_path)]) == 0
    # A loads export left by the solver must be archived by the call.
    loads = tmp_path / "FS_SurfaceSection_Loads.txt"
    loads.write_text("fixture content\n", encoding="utf-8")

    assert cli.main(["step", "--dir", str(tmp_path)]) == 0

    disp = (tmp_path / cli.DISPLACEMENT_FILE).read_text(encoding="utf-8").splitlines()
    assert len(disp) == 6
    # Comma separated dx,dy,dz per line (SRC-003 p.273).
    assert all(line.split(",") == ["0.000000000000e+00"] * 3 for line in disp)
    archived = tmp_path / cli.ARCHIVE_DIR / "call_0001" / "FS_SurfaceSection_Loads.txt"
    assert archived.read_text(encoding="utf-8") == "fixture content\n"
    assert (tmp_path / cli.ARCHIVE_DIR / "call_0001" / "directory_listing.txt").is_file()


def test_repeated_steps_count_calls_and_keep_archives(tmp_path):
    cli.main(["init-dummy", "--node-count", "3", "--dir", str(tmp_path)])
    for _ in range(3):
        assert cli.main(["step", "--dir", str(tmp_path)]) == 0
    state = json.loads((tmp_path / cli.STATE_FILE).read_text(encoding="utf-8"))
    assert state["calls"] == 3
    calls = sorted(p.name for p in (tmp_path / cli.ARCHIVE_DIR).iterdir())
    assert calls == ["call_0001", "call_0002", "call_0003"]
    log_lines = (tmp_path / cli.CALL_LOG).read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 3


def test_bare_call_without_config_leaves_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main([]) == 1
    error = (tmp_path / cli.ERROR_LOG).read_text(encoding="utf-8")
    assert "pyfs_fsi_dummy.json" in error
    assert "directory listing" in error


def test_unknown_call_convention_is_executed_and_recorded(tmp_path, monkeypatch):
    """If the Toolbox passes arguments, the step runs and records them."""
    cli.main(["init-dummy", "--node-count", "2", "--dir", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    assert cli.main(["some", "toolbox", "args"]) == 0
    assert (tmp_path / cli.DISPLACEMENT_FILE).is_file()
    log = (tmp_path / cli.CALL_LOG).read_text(encoding="utf-8")
    assert "argv ['some', 'toolbox', 'args']" in log
    assert f"cwd {tmp_path}" in log
