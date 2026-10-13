"""P0400-GOLDENSIMPORT (PFS-2135.076): gen_workflow_goldens.py imports in a fresh interpreter.

The script put only tests/tier1_offline on sys.path and imported
test_workflows, which imports ``tests.support_helpers``; run as its own guard
tells a reader to run it, it ended in ``ModuleNotFoundError: No module named
'tests'``. Run here in a child interpreter started outside the repository, so
the pytest process's own path cannot hide the failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_p0400_goldensimport_the_script_starts_outside_pytest(tmp_path: Path) -> None:
    """P0400-GOLDENSIMPORT: ``--help`` exits 0, so every import at the top succeeded."""
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    done = subprocess.run(
        [sys.executable, "-B", str(REPO / "scripts" / "gen_workflow_goldens.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert "--check" in done.stdout
