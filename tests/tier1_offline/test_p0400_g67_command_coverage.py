# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.0
# artifact_id: P0400-G67-command-coverage-tests
# last_modified_at: 2026-10-12T00:00:00-03:00
# last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
# dependencies: [scripts/build_command_coverage.py; commands/*.yaml; RPT-165]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Guard the coverage partition and prove missing commands fail on copied data.
# revision_source: git
# GEOVERSE_HEADER_END
"""P0400-G67: setup and boundary commands have a named route or an explicit reason."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest
import yaml
from scripts.build_command_coverage import (
    BUILD,
    CHAPTERS,
    ROOT,
    STEM,
    _emissions,
    build_coverage,
    render_markdown,
)


def _assert_twins(root: Path, report: dict) -> None:
    expected = {
        ".json": json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        ".md": render_markdown(report),
    }
    for suffix, regenerated in expected.items():
        path = root / "reports" / (STEM + suffix)
        assert path.read_text("utf-8") == regenerated, f"coverage twin differs: {path.name}"


def test_p0400_g67_every_command_has_one_column_and_twins_regenerate():
    """P0400-G67: the full database/emitter rebuild equals both filed representations."""
    report = build_coverage()
    assert len(report["rows"]) >= 150, "an empty or narrowed inventory cannot satisfy coverage"
    assert {row["chapter"] for row in report["rows"]} == set(CHAPTERS)
    assert len({row["command"] for row in report["rows"]}) == len(report["rows"])
    for row in report["rows"]:
        assert bool(row["reachable"]) != bool(row["not_offered"]), row
        assert row["evidence"], row
        if row["reachable"]:
            assert row["build_status"] in {"documented", "verified"}, row
        for evidence in row["evidence"]:
            assert (ROOT / evidence.split(":", 1)[0]).is_file(), evidence
    assert sum(report["counts"].values()) == len(report["rows"])
    _assert_twins(ROOT, report)


@pytest.fixture
def copied_database(tmp_path: Path) -> Path:
    """Copy the database for mutation controls; no real command entry is touched."""
    return Path(shutil.copytree(ROOT / "src/pyflightstream/commands", tmp_path / "commands"))


@pytest.mark.parametrize("chapter", ["solver_settings", "advanced_settings", "boundary_conditions"])
@pytest.mark.parametrize("status", ["documented", "verified"])
def test_p0400_g67_fake_supported_command_fails_the_partition(
    copied_database: Path, chapter: str, status: str
):
    """P0400-G67 control: a new supported command in either family fails the rebuild."""
    path = copied_database / f"{chapter}.yaml"
    entries = yaml.safe_load(path.read_text("utf-8"))
    command = "G67_FAKE_UNCOVERED_COMMAND"
    entries[command] = {
        "layout": "bare",
        "phase": "setup",
        "args": [],
        "manual_ref": "SRC-753 p.353",
        "versions": {
            BUILD: {
                "status": status,
                **(
                    {"report": "reports/compat/CMP-26125_2026-10-05_probe-campaign.yaml"}
                    if status == "verified"
                    else {}
                ),
            }
        },
    }
    path.write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{command}: command in neither"):
        build_coverage(database=copied_database)
    assert command not in (ROOT / "src/pyflightstream/commands" / path.name).read_text("utf-8")


@pytest.mark.parametrize("suffix", [".json", ".md"])
def test_p0400_g67_stale_table_fails(tmp_path: Path, suffix: str):
    """P0400-G67 control: changing either filed representation is detected."""
    report = build_coverage()
    shutil.copytree(
        ROOT / "reports",
        tmp_path / "reports",
        ignore=lambda _, names: [name for name in names if not name.startswith(STEM)],
    )
    path = tmp_path / "reports" / (STEM + suffix)
    path.write_text(path.read_text("utf-8") + "stale coverage\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="coverage twin differs"):
        _assert_twins(tmp_path, report)


def test_p0400_g67_emission_census_ignores_lookups_and_prose(tmp_path: Path):
    """P0400-G67 control: an entry lookup or a docstring cannot prove emission."""
    source = tmp_path / "src/pyflightstream/cases"
    source.mkdir(parents=True)
    path = source / "synthetic.py"
    command = "G67_SYNTHETIC_COMMAND"
    path.write_text(
        f'def route(script):\n    """{command}"""\n    script.entry("{command}")\n',
        encoding="utf-8",
    )
    assert _emissions(tmp_path, {command}) == {}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f'    script.emit("{command}")\n')
    assert command in _emissions(tmp_path, {command})


def test_p0400_g67_lost_emitter_table_row_fails(tmp_path: Path):
    """P0400-G67 control: a live key/register without its actual emitter row fails."""
    copied_root = tmp_path / "repo"
    shutil.copytree(ROOT / "src/pyflightstream", copied_root / "src/pyflightstream")
    path = copied_root / "src/pyflightstream/script/_settings.py"
    text = path.read_text("utf-8")
    old = 'Row("convergence", "SOLVER_SET_CONVERGENCE")'
    assert old in text
    path.write_text(text.replace(old, 'Row("convergence", "G67_REMOVED_ROUTE")'), encoding="utf-8")
    with pytest.raises(ValueError, match="SOLVER_SET_CONVERGENCE:.*no executable emission"):
        build_coverage(root=copied_root)


def test_p0400_g67_scope_matches_the_existing_database_chapter_register():
    """The existing setup/BC register supplies categories, with the 26.125 addition."""
    path = ROOT / "tests/tier1_offline/test_goal034_setup_operational_commands.py"
    for statement in ast.parse(path.read_text("utf-8")).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SETUP_CHAPTERS" for t in statement.targets
        ):
            assert set(CHAPTERS) == set(ast.literal_eval(statement.value)) | {"free_surfaces"}
            break
    else:
        pytest.fail("the setup/BC chapter register is missing")
