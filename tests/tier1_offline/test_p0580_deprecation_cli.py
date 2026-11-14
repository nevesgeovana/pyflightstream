"""P0580-DEPRECATION-CLI (PFS-2229): a deprecated key or flag is seen by a CLI user.

A ``PyflightstreamDeprecationWarning`` is a ``DeprecationWarning``, which the interpreter's
default filters hide outside ``__main__``. A person who runs the command line and states the
old ``hub_rings`` key ``width`` or the old ``--hub`` flag would see nothing until the alias
was removed. These tests run the real command in a fresh interpreter under the default
filters, and require the message once, naming the new spelling.
"""

import os
import subprocess
import sys
from pathlib import Path

from tests.tier1_offline.test_p0540_wheel_obj import build_sector
from tests.tier1_offline.test_p0560_morph import build, control

_SRC = str(Path(__file__).resolve().parents[2] / "src")
# The tree under test, not an installed copy; no warning option from the caller's shell.
_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONWARNINGS"} | {"PYTHONPATH": _SRC}
_DRIVER = "import sys; from pyflightstream.workspace.cli import main; sys.exit(main(sys.argv[1:]))"


def _run(argv, *options):
    """Run the workspace command in a fresh interpreter, the default warning filters in force."""
    return subprocess.run(
        [sys.executable, *options, "-c", _DRIVER, *argv],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=_ENV,
    )


def test_p0580_cli_old_hub_rings_width_key_is_seen_once_naming_band_width(tmp_path):
    source = build(tmp_path)
    cfg = control(tmp_path, "[hub_rings]\nrings = 4\nwidth = 0.04\n")
    done = _run(
        [
            "geometry",
            "hub-rings",
            str(source),
            "--morphing",
            str(cfg),
            "--out",
            str(tmp_path / "rings.obj"),
        ]
    )
    shown = done.stdout + done.stderr
    assert shown.count("hub_rings.width is deprecated; use hub_rings.band_width") == 1, shown


def test_p0580_cli_old_hub_flag_is_seen_once_naming_center(tmp_path):
    sector = build_sector(tmp_path)
    done = _run(
        [
            "geometry",
            "sector-to-wheel",
            str(sector.obj),
            "--copies",
            "6",
            "--blades",
            "Blade1",
            "--out",
            str(tmp_path / "wheel.obj"),
            "--hub",
            "0",
            "0",
            "0",
        ]
    )
    shown = done.stdout + done.stderr
    assert done.returncode == 0, shown
    assert shown.count("use center (CLI: --center)") == 1, shown


def test_p0580_cli_a_user_filter_still_wins(tmp_path):
    """A person who ignored the deprecation on the command line keeps that choice."""
    source = build(tmp_path)
    cfg = control(tmp_path, "[hub_rings]\nrings = 4\nwidth = 0.04\n")
    done = _run(
        [
            "geometry",
            "hub-rings",
            str(source),
            "--morphing",
            str(cfg),
            "--out",
            str(tmp_path / "rings.obj"),
        ],
        "-W",
        "ignore::DeprecationWarning",
    )
    assert done.returncode == 0, done.stderr
    assert "is deprecated" not in done.stdout + done.stderr
