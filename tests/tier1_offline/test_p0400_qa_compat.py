"""P0400-COMPAT: compat reports, promotions and the executable identity.

PFS-2003.10.03: a probe report row shows a missing observation as missing.
PFS-2102.032, PFS-2088.016: promotions go into the repository's own database.
PFS-2102.030: a partial report is refused in the catalogued type.
PFS-2102.031: a broken promotion keeps the row's edition page citation.
PFS-2102.003: a registry with no build recorded confirms nothing.
"""

from __future__ import annotations

import dataclasses

import pytest
import yaml

from pyflightstream.qa import compat
from pyflightstream.qa.compat import (
    COMPAT_SCHEMA,
    ExecutableVerdict,
    apply_compat,
    classify_executable,
    write_compat_report,
)
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.probes import ProbeOutcome, ProbeResult, ProbeRun

META = 'versions:\n  - canonical: "26.120"\n    alias: "26.12"\n'
CHAPTER = """\
STOP:
  layout: bare
  phase: control
  args: []
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented, note: "SRC-741 p.358 documents it on this edition"}
"""


def _commands(folder):
    folder.mkdir(parents=True)
    (folder / "_meta.yaml").write_text(META, encoding="utf-8")
    (folder / "script_controls.yaml").write_text(CHAPTER, encoding="utf-8")
    return folder


def _report(root, commands):
    folder = root / "reports" / "compat"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "CMP-26120_2026-10-12.yaml"
    document = {"schema": COMPAT_SCHEMA, "fs_version": "26.120", "commands": commands}
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_p0400_compat_a_missing_observation_reads_missing(tmp_path):
    """P0400-COMPAT (PFS-2003.10.03) the expectation is never printed as the observation."""
    result = ProbeResult(
        command="STOP",
        outcome=ProbeOutcome.VERIFIED,
        detail="script processing continued past the command",
        expected="the script halts at the command",
        observation=None,
    )
    run = ProbeRun(
        version="26.120",
        solver_identity=(),
        fs_exe_name="FlightStream.exe",
        package_version="0.40.0",
        results=(result,),
    )
    yaml_path, md_path = write_compat_report(run, tmp_path, date="2026-10-12")
    row = next(
        line for line in md_path.read_text(encoding="utf-8").splitlines() if "| STOP |" in line
    )
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[3] == "the script halts at the command"
    assert cells[4] == "missing"
    body = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))["commands"]["STOP"]
    assert body["observation"] is None
    assert body["expected"] == "the script halts at the command"


def test_p0400_compat_the_database_defaults_to_the_repository_and_never_leaves_it(tmp_path):
    """P0400-COMPAT (PFS-2102.032, PFS-2088.016) the promotion writes the tree --root names."""
    root = tmp_path / "repo"
    inside = _commands(root / "src" / "pyflightstream" / "commands")
    assert compat.resolve_commands_dir(root) == inside.resolve()
    outside = _commands(tmp_path / "elsewhere" / "commands")
    report = _report(root, {"STOP": {"outcome": "verified", "detail": "halted"}})
    before = (outside / "script_controls.yaml").read_text(encoding="utf-8")
    with pytest.raises(QaEvidenceError, match="not under the repository root"):
        apply_compat(report, repo_root=root, commands_dir=outside)
    assert (outside / "script_controls.yaml").read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "document",
    [
        {"fs_version": "26.120", "commands": None},
        {"fs_version": "26.120", "commands": {"STOP": "verified"}},
        {"commands": {"STOP": {"outcome": "verified"}}},
    ],
)
def test_p0400_compat_a_partial_report_is_refused_in_the_catalogued_type(tmp_path, document):
    """P0400-COMPAT (PFS-2102.030) no KeyError, TypeError or AttributeError escapes."""
    commands_dir = _commands(tmp_path / "commands")
    path = tmp_path / "reports" / "compat" / "CMP-26120_2026-10-12.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({"schema": COMPAT_SCHEMA, **document}), encoding="utf-8")
    with pytest.raises(QaEvidenceError):
        apply_compat(path, repo_root=tmp_path, commands_dir=commands_dir)


def test_p0400_compat_a_broken_promotion_keeps_the_page_citation(tmp_path):
    """P0400-COMPAT (PFS-2102.031) the edition's note survives and the measurement is added."""
    commands_dir = _commands(tmp_path / "commands")
    report = _report(tmp_path, {"STOP": {"outcome": "broken", "detail": "no halt observed"}})
    apply_compat(report, repo_root=tmp_path, commands_dir=commands_dir)
    row = yaml.safe_load((commands_dir / "script_controls.yaml").read_text(encoding="utf-8"))
    entry = row["STOP"]["versions"]["26.120"]
    assert entry["status"] == "broken"
    assert "SRC-741 p.358" in entry["note"], entry["note"]
    assert "no halt observed" in entry["note"], entry["note"]
    apply_compat(report, repo_root=tmp_path, commands_dir=commands_dir)
    again = yaml.safe_load((commands_dir / "script_controls.yaml").read_text(encoding="utf-8"))
    assert again["STOP"]["versions"]["26.120"]["note"] == entry["note"], "promoted twice"


def test_p0400_compat_a_registry_without_a_build_confirms_nothing(tmp_path, monkeypatch):
    """P0400-COMPAT (PFS-2102.003) no match is claimed against a build never recorded."""
    exe = tmp_path / "FlightStream.exe"
    exe.write_bytes(b"bytes of a solver")
    real = compat.resolve
    monkeypatch.setattr(
        compat, "resolve", lambda version: dataclasses.replace(real(version), build=None)
    )
    answer = classify_executable(
        exe, version="26.123", baseline={"26.123": {"sha256": "0" * 64}}, printed_build="8112026"
    )
    assert answer.verdict is ExecutableVerdict.UNKNOWN
    assert "holds no build" in answer.message
