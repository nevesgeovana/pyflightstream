"""P0520-ACCEPT-ROW-BUILD (FR-3405): the acceptance flag accepts an unregistered build.

A build id the package does not register (a vendor build such as 26.127,
mapped in ``executables.toml``) is planned with ``--accept-unregistered-build``
in each of the three forms a matrix names it: in every row's FS_BUILD with
``--fs-version`` naming it too, in ``--fs-version`` alone with the rows' cells
empty, and in the rows alone. Its scripts are written with the command database
of the newest registered version at or below it, on the executable of its own
registry entry, and the plan warns, naming both. Without the flag it stays
refused; an entry declaring its ``version`` is written for that version.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.run.cli import main
from pyflightstream.versions import known_versions
from tests.tier1_offline.test_matrix_run import make_library, real_executable

FIXTURE = Path(__file__).parent / "fixtures" / "matrix_registry.fs"
RECIPE = ["--recipe", "003=tests.tier1_offline.test_matrix_run:matrix_recipe"]
FLAG = "--accept-unregistered-build"
#: The build after the newest one the package registers (26.127 at the 0.51.0
#: base): a vendor build mapped in executables.toml before the package knows it.
NEWEST = known_versions()[-1].canonical
_MAJOR, _MINOR = NEWEST.split(".")
NEW_BUILD = f"{_MAJOR}.{int(_MINOR) + 1:03d}"


def _plan(tmp_path: Path, *extra: str, cell: str = NEW_BUILD, table: bool = False):
    """Plan the registry fixture with every FS_BUILD cell set to ``cell``; return code, warnings."""
    exe = real_executable(tmp_path)
    # Only the new build is registered: a plan that looked up another entry fails.
    workspace = make_library(tmp_path, register_build=(NEW_BUILD, exe.as_posix()))
    if table:
        (workspace.inputs_dir / "executables.toml").write_text(
            f'"{NEW_BUILD}" = {{ path = "{exe.as_posix()}", version = "{NEWEST}" }}\n',
            encoding="utf-8",
        )
    matrix = workspace.root / "inputs" / "matrices" / "m.fs"
    matrix.parent.mkdir(parents=True, exist_ok=True)
    text = FIXTURE.read_text(encoding="utf-8")
    matrix.write_text(text.replace("| 26.120   |", f"| {cell:<8} |"), encoding="utf-8")
    args = ["plan", str(matrix), "--workspace", str(workspace.root), *RECIPE, *extra]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            code = main(args)
        except SystemExit as stop:
            code = int(stop.code or 0)
    return code, [str(item.message) for item in caught]


def _accepted(said: list[str]) -> list[str]:
    return [m for m in said if f"{NEW_BUILD!r} is not a FlightStream version" in m]


@pytest.mark.requirement("FR-3405")
@pytest.mark.parametrize(
    ("cell", "extra"),
    [
        (NEW_BUILD, ["--fs-version", NEW_BUILD]),
        ("", ["--fs-version", NEW_BUILD]),
        (NEW_BUILD, []),
    ],
    ids=["rows-and-fs-version", "fs-version-alone", "rows-alone"],
)
def test_p0520_an_unregistered_build_is_planned_with_the_flag(tmp_path, cell, extra):
    # P0520-ACCEPT-ROW-BUILD
    code, said = _plan(tmp_path, FLAG, *extra, cell=cell)
    assert code == 0, said
    named = _accepted(said)
    assert named and NEWEST in named[0] and FLAG in named[0], said
    assert "command database" in named[0]


@pytest.mark.requirement("FR-3405")
@pytest.mark.parametrize("extra", [[], ["--fs-version", NEW_BUILD]], ids=["rows", "fs-version"])
def test_p0520_without_the_flag_the_unregistered_build_is_still_refused(tmp_path, extra):
    # P0520-ACCEPT-ROW-BUILD: the control; acceptance stays explicit.
    code, said = _plan(tmp_path, *extra)
    assert code != 0
    assert not _accepted(said)


@pytest.mark.requirement("FR-3405")
def test_p0520_an_entry_declaring_its_version_plans_without_a_default(tmp_path):
    # P0520-ACCEPT-ROW-BUILD: the declared version answers for the campaign too.
    code, said = _plan(tmp_path, FLAG, table=True)
    assert code == 0, said
    assert not _accepted(said)
