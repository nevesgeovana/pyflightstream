"""Tier 1: the LQ1 tool's one-pass check counts the point's own post export (FR-338).

Property: the capped point's post ran exactly once when, leaving out only the
package's per-call archive folder ``fsi_archive/``, the point holds exactly
one convergence log with one row and exactly one sectional loads export, and
that export records the solver iteration the row records.

The package copies each structural call's input into
``fsi_archive/call_NNNN/``, so a coupled point that ran its post once still
holds two files named ``FS_SurfaceSection_Loads.txt``. The folder below is a
synthetic point: one own export, one archive copy and a one-row log.
"""

from __future__ import annotations

from pathlib import Path

from tests.tier3_licensed.fsi_lq1 import one_pass

LOG = (
    "# pyflightstream FSI convergence log\n"
    "call,step,phase,revolutions,solver_iteration,total_normal_force_n\n"
    "1,1,fixed_wing,,64,3744.830000\n"
)
LOADS = "     Current solver iteration number:            64\n"
NAME = "FS_SurfaceSection_Loads.txt"


def _point(root: Path) -> Path:
    """A capped point after one pass: its log, its own export and the package's archive copy."""
    point = root / "DP-M147RE342AL+050"
    archive = point / "fsi_archive" / "call_0001"
    archive.mkdir(parents=True)
    (point / "fsi_convergence_log.csv").write_text(LOG, encoding="utf-8")
    (point / NAME).write_text(LOADS, encoding="utf-8")
    (archive / NAME).write_text(LOADS, encoding="utf-8")
    return point


def test_one_pass_counts_the_own_export_and_not_the_archive_copy_fr_338(tmp_path):
    """FR-338: one own export beside its fsi_archive/ copy is one pass of the post."""
    single, evidence = one_pass(_point(tmp_path))
    assert single, evidence


def test_one_pass_is_false_when_the_own_export_appears_twice_fr_338(tmp_path):
    """FR-338: a second own export outside fsi_archive/ still refuses the one-pass reading."""
    point = _point(tmp_path)
    (point / "second").mkdir()
    (point / "second" / NAME).write_text(LOADS, encoding="utf-8")
    single, evidence = one_pass(point)
    assert not single, evidence
