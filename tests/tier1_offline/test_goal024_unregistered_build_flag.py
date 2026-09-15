"""Tier 1: an installed build other than the registered one runs only on request (GOAL-024).

The owner's decision of 2026-09-15: when the build exists but is not the
registered one, `plan` and `run` take `--accept-unregistered-build`, and then its
compatibility is the user's responsibility. Without the flag the refusal stands
and names it.

The test names carry ``goal024_unregistered_build_flag`` so the goal's checker can select them.
"""

from __future__ import annotations

import json
import warnings

import pytest

from pyflightstream.results import VersionMismatchWarning
from pyflightstream.run import (
    ACCEPT_UNREGISTERED_BUILD_FLAG,
    ExecutorConfigurationError,
    check_solver_identity,
)
from pyflightstream.versions import resolve
from tests.tier1_offline.test_run import IdentitySolver

#: The 26.120 install, which the tests point a 26.121 campaign at.
OTHER_BUILD = "7012026"


def test_goal024_unregistered_build_flag_the_refusal_names_the_flag(tmp_path):
    solver = IdentitySolver(build=OTHER_BUILD)
    with pytest.raises(ExecutorConfigurationError) as refused:
        check_solver_identity(solver, resolve("26.121"), tmp_path)
    message = str(refused.value)
    assert ACCEPT_UNREGISTERED_BUILD_FLAG in message and "Nothing ran" in message


def test_goal024_unregistered_build_flag_accepting_warns_and_does_not_refuse(tmp_path):
    solver = IdentitySolver(build=OTHER_BUILD)
    with pytest.warns(VersionMismatchWarning) as warned:
        check_solver_identity(solver, resolve("26.121"), tmp_path, accept_unregistered_build=True)
    text = str(warned[0].message)
    assert f"#{OTHER_BUILD}" in text and ACCEPT_UNREGISTERED_BUILD_FLAG in text


def test_goal024_unregistered_build_flag_the_registered_build_is_silent_either_way(tmp_path):
    """The control: the flag changes nothing where the build is the registered one."""
    solver = IdentitySolver(build="7262026")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_solver_identity(solver, resolve("26.121"), tmp_path, accept_unregistered_build=True)


@pytest.mark.filterwarnings("ignore:none of the")
@pytest.mark.parametrize("accepted", [False, True])
def test_goal024_unregistered_build_flag_run_passes_it_and_every_record_says_so(
    tmp_path, monkeypatch, accepted
):
    import pyflightstream.run as run_module
    from tests.tier1_offline.test_matrix_run import (
        REGISTRY_FIXTURE,
        make_library,
        real_executable,
        run_for_records,
    )

    seen = []

    def spy(executor, version, workdir, **options):
        seen.append(options.get("accept_unregistered_build"))

    monkeypatch.setattr(run_module, "check_solver_identity", spy)
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    records = run_for_records(REGISTRY_FIXTURE, workspace, accept_unregistered_build=accepted)
    assert records and seen and set(seen) == {accepted}
    assert all(record.accept_unregistered_build is accepted for record in records)
    manifest = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert all(row.get("accept_unregistered_build", False) is accepted for row in manifest)


@pytest.mark.filterwarnings("ignore:none of the")
def test_goal024_unregistered_build_flag_plan_records_it(tmp_path):
    from pyflightstream.run.matrix import plan_matrix
    from tests.tier1_offline.test_matrix_run import (
        RECIPES,
        REGISTRY_FIXTURE,
        make_library,
        matrix_recipe,
        real_executable,
    )

    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    plan = plan_matrix(
        REGISTRY_FIXTURE,
        workspace,
        name="prov",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry={"steady": matrix_recipe},
        accept_unregistered_build=True,
    )
    written = json.loads(plan.plan_file.read_text(encoding="utf-8"))
    assert written["accept_unregistered_build"] is True


@pytest.mark.parametrize("command", ["plan", "run"])
def test_goal024_unregistered_build_flag_both_commands_offer_it(command, capsys):
    from pyflightstream.run.cli import main

    with pytest.raises(SystemExit):
        main([command, "--help"])
    assert ACCEPT_UNREGISTERED_BUILD_FLAG in capsys.readouterr().out
