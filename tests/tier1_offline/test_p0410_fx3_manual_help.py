"""P0410: asking the manual converter for help needs no archive or browser."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("flag", ["--help", "-h"], ids=["P0410-help", "P0410-short-help"])
def test_p0410_fx3_converter_help_succeeds(flag):
    script = Path(__file__).resolve().parents[2] / "scripts" / "chm_to_pdf.py"
    result = subprocess.run([sys.executable, str(script), flag], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
    assert "PYFS_CHROME" in result.stdout
    assert not result.stderr
