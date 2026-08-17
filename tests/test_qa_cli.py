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
    # The vendor build number, which the two solvers print, and not the
    # hotfix digit: see test_versions.py for why that wording moved.
    assert "vendor build 7262026" in error


def test_an_unregistered_version_exits_two_and_lists_the_registered_ones(capsys):
    exit_code = main(["probe", "--fs-version", "25.3", "--fs-exe", "nowhere.exe"])
    assert exit_code == 2
    error = capsys.readouterr().err
    assert error.startswith("version not resolved: ")
    assert "25.3" in error
    for canonical in ("26.000", "26.100", "26.101", "26.120", "26.121"):
        assert canonical in error


def test_probe_refuses_an_existing_report_before_it_starts_the_solver(
    tmp_path, monkeypatch, capsys
):
    """The whole behaviour change of this commit, and it had no test.

    Measured by the QA review pass on 2026-08-17: deleting the entire
    early-refusal block left 87 tests passing. What that lets back
    through is the incident it was written for. A full campaign on
    26.123 ran to completion, 111 command probes over five minutes of
    licensed solver, and the write then refused on a stem that already
    existed; the verdicts lived only in the process that was exiting.
    The refusal was right and its POSITION was wrong, about a collision
    knowable from the command line.

    The solver is replaced by a probe_version that RAISES if it is
    reached, so this fails loudly rather than by a count.
    """
    from pyflightstream.qa import cli as cli_module
    from pyflightstream.qa.compat import compat_report_paths

    reports = tmp_path / "reports"
    reports.mkdir()
    # The REAL path computation, not a stand-in, so this also pins the
    # label arm the early check depends on: if the label stopped reaching
    # the stem, the pre-flight would inspect a name nothing collides with
    # and the run would reach the solver and collide at write time, which
    # is the incident again by another route.
    existing, _ = compat_report_paths("26.123", reports, label="full-sim")
    assert existing.name.endswith("_full-sim.yaml"), existing.name
    existing.write_text("stub", encoding="utf-8")

    def never(*args, **kwargs):
        raise AssertionError("the solver was started, so a licensed seat was spent")

    monkeypatch.setattr(cli_module, "probe_version", never)

    exit_code = cli_module.main(
        [
            "probe",
            "--fs-version",
            "26.123",
            "--fs-exe",
            "nowhere.exe",
            "--report-dir",
            str(reports),
            "--label",
            "full-sim",
        ]
    )
    error = capsys.readouterr().err
    assert exit_code == 2
    assert "nothing run" in error, error
    assert "--label" in error and "--report-dir" in error, (
        "the refusal must name the escapes THIS command line has; it used to say "
        "'pick another date', and pyfs-qa probe has no date flag"
    )


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


def _chapter_and_report(tmp_path):
    """A fixture tree the promotion path can actually run against."""
    import yaml

    from pyflightstream.qa import COMPAT_SCHEMA

    commands = tmp_path / "commands"
    commands.mkdir()
    (commands / "_meta.yaml").write_text(
        'versions:\n  - canonical: "26.120"\n    alias: "26.12"\n', encoding="utf-8"
    )
    (commands / "script_controls.yaml").write_text(
        "PRINT:\n"
        "  layout: inline\n"
        "  phase: control\n"
        "  args:\n"
        "    - name: message\n"
        "      type: str\n"
        '  manual_ref: "SRC-003 p.281"\n'
        "  versions:\n"
        '    "26.120": {status: documented}\n',
        encoding="utf-8",
    )
    reports = tmp_path / "reports" / "compat"
    reports.mkdir(parents=True)

    def write(date: str, outcome: str, label: str = "") -> str:
        stem = f"CMP-26120_{date}" + (f"_{label}" if label else "")
        path = reports / f"{stem}.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "schema": COMPAT_SCHEMA,
                    "fs_version": "26.120",
                    "date": date,
                    "commands": {"PRINT": {"outcome": outcome, "detail": "measured"}},
                }
            ),
            encoding="utf-8",
        )
        return str(path)

    return commands, write


def test_apply_compat_refuses_a_superseded_report_without_a_traceback(tmp_path, capsys):
    """The trap added on 2026-08-11, which had no test on any path.

    The library's refusals here say which report supersedes this one and
    which page contradicts a measured removal; a traceback buries that
    under a stack the operator did not ask for, and says nothing about
    whether the database was written.
    """
    _, write = _chapter_and_report(tmp_path)
    older = write("2026-07-21", "broken")
    write("2026-07-23", "verified", "reprobe")

    code = main(["apply-compat", older, "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 2
    assert "superseded evidence" in captured.err
    assert "Traceback" not in captured.err


def test_apply_compat_says_what_to_do_when_nothing_is_promotable(tmp_path, capsys):
    """The message names the promotable set and a next step, not a symptom."""
    import yaml

    from pyflightstream.qa import COMPAT_SCHEMA

    reports = tmp_path / "reports" / "compat"
    reports.mkdir(parents=True)
    path = reports / "CMP-26120_2026-08-11_identity.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": COMPAT_SCHEMA,
                "fs_version": "26.120",
                "date": "2026-08-11",
                "commands": {"PRINT": {"outcome": "unprobed", "detail": "not probed in this run"}},
            }
        ),
        encoding="utf-8",
    )
    code = main(["apply-compat", str(path), "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0
    # A DIFFERENT prefix from the refusal, which also began "nothing
    # promoted": on a terminal the two outcomes were distinguishable
    # only by the stream and the exit code, and a pipe loses both.
    assert "nothing to promote" in captured.out
    for outcome in ("verified", "broken", "removed"):
        assert outcome in captured.out
    assert "identity-only" in captured.out, (
        "the report records 'not probed in this run', so the remedy is a fuller run "
        "rather than a new probe specification"
    )
