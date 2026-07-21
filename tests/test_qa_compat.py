"""Tier 1: compat report writing, reading, and status promotion."""

import pytest
import yaml

from pyflightstream.commands import CommandEntry
from pyflightstream.qa import (
    COMPAT_SCHEMA,
    ProbeOutcome,
    ProbeResult,
    ProbeRun,
    apply_compat,
    read_compat_report,
    write_compat_report,
)

# A chapter fixture with documented statuses, independent of the live
# database files (which carry real promotions as evidence lands).
CHAPTER_FIXTURE = """\
# Chapter: fixture for apply-compat tests.

STOP:
  layout: bare
  phase: control
  args: []
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented}

PRINT:
  layout: inline
  phase: control
  args:
    - name: message
      type: str
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented}

RUN_SCRIPT:
  layout: param_lines
  phase: control
  args:
    - name: script_path
      type: path
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented}
"""


def write_chapter_fixture(commands_dir):
    commands_dir.mkdir()
    (commands_dir / "script_controls.yaml").write_text(CHAPTER_FIXTURE, encoding="utf-8")


def make_run():
    return ProbeRun(
        version="26.120",
        solver_identity=("FlightStream version 26.1 build #0000000",),
        fs_exe_name="Fake.exe",
        package_version="0.0.1.dev0",
        results=(
            ProbeResult(
                "PRINT",
                ProbeOutcome.VERIFIED,
                "effect observed",
                sentinel_before=True,
                sentinel_after=True,
                effect=True,
                wall_time_s=0.051,
                return_code=0,
                script_sha256="abc123",
            ),
            ProbeResult("STOP", ProbeOutcome.BROKEN, 'did not halt | "quoted"'),
            ProbeResult("OPEN", ProbeOutcome.UNPROBED, "no probe specification yet"),
        ),
    )


def test_report_pair_round_trips(tmp_path):
    yaml_path, md_path = write_compat_report(make_run(), tmp_path, date="2026-07-21")
    assert yaml_path.name == "CMP-26120_2026-07-21.yaml"
    report = read_compat_report(yaml_path)
    assert report["fs_version"] == "26.120"
    assert report["summary"] == {"verified": 1, "broken": 1, "unprobed": 1}
    assert report["commands"]["PRINT"]["signals"]["effect"] is True
    assert report["commands"]["PRINT"]["wall_time_s"] == 0.05
    markdown = md_path.read_text(encoding="utf-8")
    assert "| PRINT | verified | effect observed |" in markdown
    assert "did not halt \\|" in markdown


def test_reports_are_never_overwritten(tmp_path):
    write_compat_report(make_run(), tmp_path, date="2026-07-21")
    with pytest.raises(FileExistsError, match="never\n?.*overwritten"):
        write_compat_report(make_run(), tmp_path, date="2026-07-21")


def test_read_refuses_a_non_report_file(tmp_path):
    stray = tmp_path / "stray.yaml"
    stray.write_text("just: data\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a compat report"):
        read_compat_report(stray)


def write_report(tmp_path, commands):
    report_dir = tmp_path / "reports" / "compat"
    report_dir.mkdir(parents=True)
    path = report_dir / "CMP-26120_2026-07-21.yaml"
    document = {"schema": COMPAT_SCHEMA, "fs_version": "26.120", "commands": commands}
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_apply_compat_promotes_citing_the_report(tmp_path):
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_report(
        tmp_path,
        {
            "PRINT": {"outcome": "verified", "detail": "effect observed"},
            "STOP": {"outcome": "broken", "detail": 'no halt, "quoted" detail'},
            "RUN_SCRIPT": {"outcome": "unprobed", "detail": "not probed"},
        },
    )
    promotions = apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert sorted(promotions) == [
        ("PRINT", "verified", "script_controls.yaml"),
        ("STOP", "broken", "script_controls.yaml"),
    ]
    text = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    citation = "reports/compat/CMP-26120_2026-07-21.yaml"
    assert f'"26.120": {{status: verified, report: "{citation}"}}' in text
    assert "note: \"no halt, 'quoted' detail\"" in text
    # The chapter comments and the untouched entry survive the edit.
    assert text.startswith("# Chapter: fixture for apply-compat tests.")
    data = yaml.safe_load(text)
    assert data["RUN_SCRIPT"]["versions"]["26.120"] == {"status": "documented"}
    for name in ("PRINT", "STOP", "RUN_SCRIPT"):
        CommandEntry(name=name, chapter="script_controls", **data[name])
    assert data["PRINT"]["versions"]["26.120"]["report"] == citation


def test_apply_compat_refuses_unknown_commands(tmp_path):
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_report(tmp_path, {"NOT_A_COMMAND": {"outcome": "verified", "detail": "x"}})
    with pytest.raises(ValueError, match="NOT_A_COMMAND"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


def test_apply_compat_refuses_a_multiline_version_entry(tmp_path):
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "fake.yaml").write_text(
        "FAKE_CMD:\n"
        "  layout: bare\n"
        "  phase: control\n"
        "  args: []\n"
        '  manual_ref: "SRC-003 p.281"\n'
        "  versions:\n"
        '    "26.120":\n'
        "      status: documented\n",
        encoding="utf-8",
    )
    report_path = write_report(tmp_path, {"FAKE_CMD": {"outcome": "verified", "detail": "x"}})
    with pytest.raises(ValueError, match="no single-line version entry"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
