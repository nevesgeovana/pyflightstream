"""P0520-ACCEPT-ROW-BUILD (FR-3405): the acceptance flag applies to the builds the rows state.

A matrix whose rows state an FS_BUILD such as 26.127, a build id the package does not
register, mapped in ``executables.toml``, is planned with
``--accept-unregistered-build`` and no ``--fs-version``: its scripts are
written for the newest registered version not after the build id, and the
plan warns, naming both. An entry that declares its ``version`` is written
for that version, flag or not.
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
#: The build after the newest one the package registers (26.127 at the 0.51.0
#: base): a vendor build mapped in executables.toml before the package knows it.
_MAJOR, _MINOR = known_versions()[-1].canonical.split(".")
NEW_BUILD = f"{_MAJOR}.{int(_MINOR) + 1:03d}"


def _plan(tmp_path: Path, *extra: str, table: bool = False) -> tuple[int, list[str], str]:
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=(NEW_BUILD, exe.as_posix()))
    newest = known_versions()[-1].canonical
    if table:
        (workspace.inputs_dir / "executables.toml").write_text(
            f'"{NEW_BUILD}" = {{ path = "{exe.as_posix()}", version = "{newest}" }}\n',
            encoding="utf-8",
        )
    matrix = workspace.root / "inputs" / "matrices" / "m.fs"
    matrix.parent.mkdir(parents=True, exist_ok=True)
    matrix.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("| 26.120   |", f"| {NEW_BUILD}   |"),
        encoding="utf-8",
    )
    args = ["plan", str(matrix), "--workspace", str(workspace.root), *RECIPE, *extra]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            code = main(args)
        except SystemExit as stop:
            code = int(stop.code or 0)
    return code, [str(item.message) for item in caught], newest


@pytest.mark.requirement("FR-3405")
def test_p0520_rows_naming_an_unregistered_build_plan_with_the_flag_alone(tmp_path):
    # P0520-ACCEPT-ROW-BUILD
    code, said, newest = _plan(tmp_path, "--accept-unregistered-build")
    assert code == 0, said
    named = [m for m in said if f"FS_BUILD '{NEW_BUILD}'" in m]
    assert named and newest in named[0] and "--accept-unregistered-build" in named[0], said


@pytest.mark.requirement("FR-3405")
def test_p0520_without_the_flag_the_unregistered_build_is_still_refused(tmp_path):
    # P0520-ACCEPT-ROW-BUILD: the control; acceptance stays explicit.
    code, said, _ = _plan(tmp_path)
    assert code != 0
    assert not [m for m in said if f"FS_BUILD '{NEW_BUILD}'" in m]


@pytest.mark.requirement("FR-3405")
def test_p0520_an_entry_declaring_its_version_plans_without_a_default(tmp_path):
    # P0520-ACCEPT-ROW-BUILD: the declared version answers for the campaign too.
    code, said, _ = _plan(tmp_path, "--accept-unregistered-build", table=True)
    assert code == 0, said
    assert not [m for m in said if f"FS_BUILD '{NEW_BUILD}'" in m]
