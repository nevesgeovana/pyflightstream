"""Tier 1: the pyfs-fsi items of the FSI lane of 0.40.0.

P0400-STEPECHO (PFS-2085.003), P0400-FAILARCHIVE (PFS-2085.004),
P0400-AERONODES (PFS-2085.005) and P0400-NOEXTRA (PFS-2095.014). Each test
failed on the code before its fix.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pyflightstream.fsi import cli, driver
from tests.tier1_offline.test_fsi_driver import stage_run, write_loads

ROOT = Path(__file__).resolve().parents[2]


def test_p0400_stepecho_an_explicit_step_says_why_it_failed(tmp_path, capsys):
    """P0400-STEPECHO: the console gets the cause and the log's path."""
    stage_run(tmp_path)  # no loads file: the coupled call fails
    assert cli.main(["step", "--dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "pyfs-fsi step failed: FileNotFoundError" in err
    assert str(tmp_path / cli.ERROR_LOG) in err


def test_p0400_stepecho_the_solvers_bare_call_stays_silent(tmp_path, capsys, monkeypatch):
    """P0400-STEPECHO: the control; the bare call's failure goes to the log alone."""
    stage_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cli.main([]) == 1
    assert "pyfs-fsi step failed" not in capsys.readouterr().err
    assert "coupled step failed" in (tmp_path / cli.ERROR_LOG).read_text(encoding="utf-8")


def test_p0400_failarchive_a_failed_call_keeps_the_loads_that_broke_it(tmp_path):
    """P0400-FAILARCHIVE: archived under fsi_archive/failed_<stamp>/."""
    stage_run(tmp_path)
    write_loads(tmp_path, 100)
    (tmp_path / driver.FAMILY_MAP_FILE).unlink()  # the call fails after reading the loads
    assert cli.coupled_step(tmp_path) == 1
    failed = sorted((tmp_path / cli.ARCHIVE_DIR).glob("failed_*"))
    assert len(failed) == 1
    kept = (failed[0] / driver.LOADS_FILE).read_text(encoding="utf-8")
    assert kept == (tmp_path / driver.LOADS_FILE).read_text(encoding="utf-8")


def test_p0400_aeronodes_the_solvers_node_list_is_archived_with_the_call(tmp_path):
    """P0400-AERONODES: FSInodes.txt, when the solver wrote one, is part of the replay."""
    stage_run(tmp_path)
    write_loads(tmp_path, 100)
    (tmp_path / "FSInodes.txt").write_text("0.0,0.0,0.5\n", encoding="utf-8")
    assert cli.coupled_step(tmp_path) == 0
    archived = tmp_path / cli.ARCHIVE_DIR / "call_0001" / "FSInodes.txt"
    assert archived.read_text(encoding="utf-8") == "0.0,0.0,0.5\n"


def test_p0400_noextra_a_missing_fsi_extra_reaches_the_error_log(tmp_path):
    """P0400-NOEXTRA: PyNite blocked, the coupled call logs the didactic refusal.

    In a fresh interpreter, because the driver and its beam are already
    imported in this one.
    """
    stage_run(tmp_path)
    script = (
        "import sys\n"
        "sys.modules['Pynite'] = None\n"
        "from pathlib import Path\n"
        "from pyflightstream.fsi import cli\n"
        "sys.exit(10 + cli.coupled_step(Path(sys.argv[1])))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 11, done.stderr
    error = (tmp_path / cli.ERROR_LOG).read_text(encoding="utf-8")
    assert "coupled step failed" in error
    assert "fsi" in error and "Traceback" in error
