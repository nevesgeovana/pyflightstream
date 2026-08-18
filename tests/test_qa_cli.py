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


def _compat_paths(out_dir, **kwargs):
    from pyflightstream.qa.compat import compat_report_paths

    return compat_report_paths("26.123", out_dir, **kwargs)


def _physics_paths(out_dir, **kwargs):
    from pyflightstream.qa.physics import physics_report_paths

    return physics_report_paths("26.120", out_dir, **kwargs)


def _drift_paths(out_dir, **kwargs):
    from pyflightstream.qa.drift import drift_report_paths

    return drift_report_paths("26.122", "26.123", out_dir, **kwargs)


@pytest.mark.parametrize(
    ("subcommand", "paths_for", "stem_prefix", "argv"),
    [
        (
            "probe",
            _compat_paths,
            "CMP-26123_",
            ["probe", "--fs-version", "26.123", "--fs-exe", "nowhere.exe"],
        ),
        (
            "physics",
            _physics_paths,
            "PHY-26120_",
            ["physics", "--fs-version", "26.120", "--fs-exe", "nowhere.exe"],
        ),
        (
            "drift",
            _drift_paths,
            "DRF-26122-26123_",
            [
                "drift",
                "--fs-versions",
                "26.122,26.123",
                "--fs-exe",
                "26.122=a.exe",
                "--fs-exe",
                "26.123=b.exe",
            ],
        ),
    ],
)
def test_every_evidence_writer_refuses_before_it_starts_the_solver(
    subcommand, paths_for, stem_prefix, argv, tmp_path, monkeypatch, capsys
):
    """THREE writers, one rule, and only one of them had it.

    The refusal on an existing report is right and its POSITION was
    wrong. It was hoisted for `probe` on 2026-08-17, after a full
    campaign of 111 command probes over five minutes of licensed solver
    ran to completion and was then discarded on a stem collision knowable
    from the command line. `physics` and `drift` kept the defect: the
    whole Tier 3 matrix could run and then die on an uncaught
    FileExistsError, which is WORSE than the original, because probe at
    least caught it and printed.

    Three copies of one rule is why a repair reached one of them. The
    rule now has one home, `qa/reports.py`, and this walks all three.

    EVERY RUNNER IS POISONED, not just the one under test: reaching any
    of them raises, so the test fails loudly rather than by a count.

    AND THE NAME COMES FROM THE SERIES' OWN HELPER, which is the
    correction of 2026-08-18. This test used to build the expected stem
    from a literal prefix and a literal build key handed in by the
    parameter list, so it asserted that the CLI agreed with the TEST. The
    review pass measured what that permits: sabotaging
    `write_physics_report`'s own prefix from PHY to PHZ left 45 tests
    green, because nothing tied the name the pre-flight asks about to the
    name the writer produces. Each case now goes through the same
    `*_report_paths` helper the writer itself calls, and the writer side
    of that pairing is asserted in each writer's own test module.
    """
    from pyflightstream.qa import cli as cli_module

    def never(*args, **kwargs):
        raise AssertionError("the solver was started, so a licensed seat was spent")

    for runner in ("probe_version", "run_physics", "run_drift"):
        monkeypatch.setattr(cli_module, runner, never)

    existing, _ = paths_for(tmp_path, label="x")
    # The helper is asked, and the shape it returns is still checked: a
    # helper that answered a constant would otherwise make every arm of
    # this test agree with itself.
    assert existing.name.startswith(stem_prefix), existing.name
    existing.write_text("stub", encoding="utf-8")

    code = cli_module.main(argv + ["--report-dir", str(tmp_path), "--label", "x"])
    error = capsys.readouterr().err

    assert code == 2, f"{subcommand} did not refuse"
    assert "nothing run" in error, error
    assert "--label" in error and "--report-dir" in error, (
        "the refusal must name the escapes THIS command line has; it used to say "
        "'pick another date', and none of these CLIs has a date flag"
    )


class _StubRun:
    """Enough of a run for a CLI tail to print, and nothing more."""

    version = "26.120"
    version_a = "26.122"
    version_b = "26.123"
    fs_exe_name = "nowhere.exe"
    results = ()
    solver_identity = ()

    def verdict_counts(self):
        return {"pass": 0, "warn": 0, "fail": 0, "no_reference": 0}

    def outcome_counts(self):
        return {"verified": 0}


@pytest.mark.parametrize(
    ("runner", "writer", "argv"),
    [
        (
            "probe_version",
            "write_compat_report",
            ["probe", "--fs-version", "26.123", "--fs-exe", "nowhere.exe"],
        ),
        (
            "run_physics",
            "write_physics_report",
            ["physics", "--fs-version", "26.120", "--fs-exe", "nowhere.exe"],
        ),
        (
            "run_drift",
            "write_drift_report",
            [
                "drift",
                "--fs-versions",
                "26.122,26.123",
                "--fs-exe",
                "26.122=a.exe",
                "--fs-exe",
                "26.123=b.exe",
            ],
        ),
    ],
)
def test_one_date_serves_the_pre_flight_and_the_write(runner, writer, argv, tmp_path, monkeypatch):
    """The stem asked about and the stem written are the same stem.

    Each `_cmd_*` used to resolve today's date for its pre-flight and
    then call its writer with no `date=`, so the writer resolved today
    AGAIN a moment later. Two resolutions agree on every day except the
    one that matters: a Tier 3 matrix started at 23:59 clears the
    collision check against day D and writes under day D+1. The failure
    is a MISSED refusal, so its cost is the licensed seat the pre-flight
    exists to protect, and the pairing is exactly the one
    `INC-20260817-2210` was about.

    `datetime` is replaced in the CLI's own namespace by one that hands
    out a DIFFERENT date on every call, so a second resolution cannot
    coincide with the first. The date the writer receives must be the
    date the pre-flight used.
    """
    import datetime as real_datetime

    from pyflightstream.qa import cli as cli_module

    handed_out = []

    class _WalkingDate:
        @staticmethod
        def today():
            handed_out.append(real_datetime.date(2026, 1, 1 + len(handed_out)))
            return handed_out[-1]

    class _FakeDatetime:
        date = _WalkingDate

    monkeypatch.setattr(cli_module, "datetime", _FakeDatetime)
    monkeypatch.setattr(cli_module, runner, lambda *a, **k: _StubRun())

    seen = {}

    def capture(run, out_dir, **kwargs):
        seen.update(kwargs)
        return tmp_path / "stub.yaml", tmp_path / "stub.md"

    monkeypatch.setattr(cli_module, writer, capture)

    cli_module.main(argv + ["--report-dir", str(tmp_path)])

    assert "date" in seen, (
        f"{writer} was called with no date, so it resolved its own; the pre-flight "
        "then checked a stem the write need not use"
    )
    assert len(handed_out) == 1, (
        f"today() was resolved {len(handed_out)} times in one run, so a run crossing "
        "midnight checks one stem and writes another"
    )
    assert seen["date"] == handed_out[0].isoformat()


def test_the_cli_rewords_a_library_refusal_into_its_own_flags(monkeypatch, capsys):
    """The claim `tests/test_qa_physics.py` makes about this file, made true.

    That test's own message says "The CLI owns that translation, and
    tests/test_qa_cli.py pins it". It did not: `--cases` appeared in the
    whole test tree exactly once, as the NEGATIVE assertion on the library
    side, so `_in_command_line_words` could be replaced with
    `return message` and 421 tests stayed green while the operator read
    Python list syntax at a command line.

    Two properties, and the second is the one a regex over a message
    invites losing: the datum is translated, and NOTHING AFTER IT is
    dropped.
    """
    from pyflightstream.qa import cli as cli_module
    from pyflightstream.qa.physics import PhysicsEnvironmentError

    def refusing(*args, **kwargs):
        raise PhysicsEnvironmentError(
            "case(s) PHY-05 have no command evidence for FlightStream 26.101. "
            "To run a subset deliberately, name it: cases=['PHY-01', 'PHY-02'] "
            "(SMI cases need smi_root)"
        )

    monkeypatch.setattr(cli_module, "run_physics", refusing)
    code = cli_module.main(
        ["physics", "--fs-version", "26.101", "--fs-exe", "nowhere.exe", "--report-dir", "."]
    )
    error = capsys.readouterr().err

    assert code == 2
    assert "--cases PHY-01,PHY-02" in error, error
    assert "cases=[" not in error, "the library spelling reached the operator"
    assert "(SMI cases need --smi-root)" in error, (
        "either a parameter name went untranslated, or the tail after the translated "
        "datum was dropped, which is what a message[: match.start()] return does the "
        "day the datum is not the last token"
    )


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
