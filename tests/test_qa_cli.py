"""Tier 1: the ``pyfs-qa`` command line's refusal paths.

Pipeline role: quality gate on the one surface every licensed-machine
user meets before the solver runs. A version string reaches the CLI
straight from argparse and both refusals it can meet are ordinary user
error, so neither may reach the terminal as a traceback.

These paths had no test at all when they were written (PFS-B1, QA pass),
which mattered more than usual: the ambiguous-alias refusal is a
BREAKING change, so the message it prints is the whole migration for a
user whose script stopped working.
"""

from __future__ import annotations

import pytest

from pyflightstream.qa.cli import main


def test_an_ambiguous_vendor_name_exits_two_and_names_both_builds(capsys):
    exit_code = main(["probe", "--fs-version", "26.12", "--fs-exe", "nowhere.exe"])
    assert exit_code == 2
    error = capsys.readouterr().err
    assert error.startswith("version not resolved: ")
    # The message must carry the choice, not merely report a failure: a
    # user who typed the vendor name off the solver's splash screen has
    # to learn which identifier to type instead.
    assert "26.120" in error
    assert "26.121" in error
    assert "hotfix build 1" in error


def test_an_unregistered_version_exits_two_and_lists_the_registered_ones(capsys):
    exit_code = main(["probe", "--fs-version", "25.3", "--fs-exe", "nowhere.exe"])
    assert exit_code == 2
    error = capsys.readouterr().err
    assert error.startswith("version not resolved: ")
    assert "25.3" in error
    for canonical in ("26.000", "26.100", "26.101", "26.120", "26.121"):
        assert canonical in error


def test_the_refusal_happens_before_the_executable_is_touched(capsys):
    # nowhere.exe does not exist. If the version were resolved first and
    # the executor built second, this would fail on the executable
    # instead, which is a worse message for a version typo.
    exit_code = main(["probe", "--fs-version", "26.12", "--fs-exe", "nowhere.exe"])
    assert exit_code == 2
    assert "nowhere.exe" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["physics", "--fs-version", "26.12", "--fs-exe", "nowhere.exe"],
        ["drift", "--fs-versions", "26.12,26.120", "--fs-exe", "26.120=nowhere.exe"],
        ["drift", "--fs-versions", "26.100,26.120", "--fs-exe", "26.12=nowhere.exe"],
    ],
)
def test_every_subcommand_taking_a_version_refuses_the_same_way(argv, capsys):
    # drift resolves versions in two places, the --versions pair and the
    # VERSION half of --fs-exe, so both are exercised.
    assert main(argv) == 2
    assert capsys.readouterr().err.startswith("version not resolved: ")
