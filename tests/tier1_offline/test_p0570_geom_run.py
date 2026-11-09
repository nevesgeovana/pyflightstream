"""0.57.0 PFS-2220 (G3): the runner of the geometry pipeline and its parameter loop.

Written from the requirement (C3: a failed parameter set returns a report naming its stage and
its check, so a loop can continue) and the public signatures of
:mod:`pyflightstream.workspace.geometry_pipeline`. A failure is planted in a stage function of
the table; the reports and the stage records are read back from disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._records import check_entry, exit_code, geometry_report
from pyflightstream.geometry._stage_table import STAGE_ROWS
from pyflightstream.workspace import _geom_run
from pyflightstream.workspace._geom_run import StageOutcome

BODY = {"components": {"FUS": {"type": "body", "length": 2.0}}}


def _failing_at(stage_id, *, when_length=None, checks=None):
    """A stage function that fails when the body length equals ``when_length`` (always if None)."""

    def run(context):
        length = context.resolved["components"]["FUS"]["length"]["value"]
        if when_length is not None and length != when_length:
            return StageOutcome(checks=[check_entry("law.monotonic", "passed", 0.0, 1.0)])
        return StageOutcome(
            checks=checks or [check_entry("law.monotonic", "failed", 2.5, 1.0, where={"x": 3})]
        )

    return run


@pytest.fixture
def isolated_off(monkeypatch):
    monkeypatch.setenv("PYFLIGHTSTREAM_GMSH_ISOLATE", "0")


def test_p0570_g3_a_planted_failure_stops_the_run_and_names_stage_and_check(tmp_path, monkeypatch):
    monkeypatch.setitem(_geom_run.STAGE_FUNCTIONS, "S4", _failing_at("S4"))
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S9")
    assert report["status"] == "failed"
    assert (report["stage"], report["check"]) == ("S4", "law.monotonic")
    assert (report["measured"], report["limit"], report["where"]) == (2.5, 1.0, {"x": 3})
    assert [s["stage"] for s in report["stages"]] == ["S0", "S1", "S2", "S3", "S4"]
    on_disk = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert on_disk == report
    assert (tmp_path / "S4.json").is_file() and not (tmp_path / "S5.json").exists()


def test_p0570_g3_the_first_failed_check_of_a_stage_is_the_one_named(tmp_path, monkeypatch):
    checks = [
        check_entry("law.fewest_stations", "passed", 0.0, 1.0),
        check_entry("law.ruled_twist", "failed", 9.0, 1.0),
        check_entry("law.monotonic", "failed", 5.0, 1.0),
    ]
    monkeypatch.setitem(_geom_run.STAGE_FUNCTIONS, "S4", _failing_at("S4", checks=checks))
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S9")
    assert report["check"] == "law.ruled_twist"


def _every_stage_passing(monkeypatch, *, omit=(), skip=()):
    """Give every stage a function passing each check of its row, but ``omit`` and ``skip``."""
    for row in STAGE_ROWS:

        def run(context, row=row):
            checks = [
                check_entry(cid, "skipped", note="no original")
                if cid in skip
                else check_entry(cid, "passed", 0.0, 1.0)
                for cid, _ in row.checks
                if cid not in omit
            ]
            return StageOutcome(checks=checks)

        monkeypatch.setitem(_geom_run.STAGE_FUNCTIONS, row.stage, run)


def test_p0570_g3_until_ends_the_run_and_a_clean_run_is_accepted(tmp_path, monkeypatch):
    _every_stage_passing(monkeypatch, skip=("skin.distance",))
    monkeypatch.setitem(_geom_run.STAGE_FUNCTIONS, "S6", _failing_at("S6"))
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S5")
    assert report["status"] == "accepted" and len(report["stages"]) == 6
    assert report["not_run"] == []
    assert not (tmp_path / "S6.json").exists()
    _every_stage_passing(monkeypatch, skip=("skin.distance",))
    report = _geom_run.run_geometry(BODY, out=tmp_path / "full")
    assert report["status"] == "accepted" and exit_code(report) == 0, report["not_run"]


def test_p0570_r18_001_a_run_through_an_unbuilt_stage_is_incomplete_never_accepted(tmp_path):
    """C3 and C6: a check that never ran is named, and the run is not read as accepted."""
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S3")
    assert report["status"] == "incomplete" and exit_code(report) == 3
    assert "S1 section.residual" in report["not_run"]
    assert "S3 compat.common_vector" in report["not_run"]
    assert not any(item.startswith("S0 ") for item in report["not_run"])
    on_disk = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "incomplete" and on_disk["not_run"] == report["not_run"]


def test_p0570_r18_001_a_check_a_built_stage_omits_is_recorded_and_named(tmp_path, monkeypatch):
    _every_stage_passing(monkeypatch, omit=("law.fewest_stations",), skip=("skin.distance",))
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S6")
    assert report["status"] == "incomplete"
    assert report["not_run"] == ["S4 law.fewest_stations"]
    record = json.loads((tmp_path / "S4.json").read_text(encoding="utf-8"))
    entry = next(c for c in record["checks"] if c["id"] == "law.fewest_stations")
    assert entry["status"] == "skipped" and "not measured" in entry["note"]
    assert record["status"] == "passed"


def test_p0570_r18_001_an_accepted_report_with_checks_not_run_is_refused():
    with pytest.raises(InputValueError, match="not accepted"):
        geometry_report("accepted", "p", not_run=["S1 section.residual"])


def test_p0570_g3_an_unbuilt_stage_is_recorded_skipped_and_the_report_says_so(tmp_path):
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S3")
    assert [s["status"] for s in report["stages"]] == ["passed", "skipped", "skipped", "skipped"]
    assert any("S1 Section law: stage not built" in w for w in report["warnings"])
    record = json.loads((tmp_path / "S1.json").read_text(encoding="utf-8"))
    assert {c["status"] for c in record["checks"]} == {"skipped"} and record["checks"][0]["note"]


@pytest.mark.parametrize(
    ("kwargs", "text"),
    [
        ({"overrides": {"FUS.lenght": 3.0}}, "unknown parameter"),
        ({"overrides": {"WING.length": 3.0}}, "declared component"),
        ({"overrides": {"length": 3.0}}, "declared component"),
        ({"configuration": "nope"}, "configuration 'nope': unknown"),
        ({"variant": "nope"}, "variant 'nope': unknown"),
    ],
)
def test_p0570_g3_a_bad_input_is_refused_before_any_stage_runs(tmp_path, kwargs, text):
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S9", **kwargs)
    assert report["status"] == "refused" and text in report["message"]
    assert report["stage"] == "S0" and not list(tmp_path.glob("S*.json"))


def test_p0570_g3_an_unknown_until_and_an_empty_file_are_refused(tmp_path):
    with pytest.raises(InputValueError, match="stage 'S99'"):
        _geom_run.run_geometry(BODY, out=tmp_path, until="S99")
    empty = tmp_path / "empty.geom.toml"
    empty.write_text("", encoding="utf-8")
    report = _geom_run.run_geometry(empty, out=tmp_path / "o")
    assert report["status"] == "refused" and "components" in report["message"]


def test_p0570_g3_an_override_changes_the_identity_and_a_repeat_keeps_it(tmp_path):
    a = _geom_run.run_geometry(BODY, out=tmp_path / "a", until="S0")
    b = _geom_run.run_geometry(BODY, out=tmp_path / "b", until="S0")
    c = _geom_run.run_geometry(BODY, out=tmp_path / "c", until="S0", overrides={"FUS.length": 3.0})
    assert a["parameter_id"] == b["parameter_id"] != c["parameter_id"]


def test_p0570_g3_a_loop_continues_after_a_failed_set(tmp_path, monkeypatch, isolated_off):
    monkeypatch.setitem(_geom_run.STAGE_FUNCTIONS, "S4", _failing_at("S4", when_length=3.0))
    sets = [{"FUS.length": 2.5}, {"FUS.length": 3.0}, {"FUS.length": 3.5}]
    reports = list(_geom_run.run_doe(BODY, sets, out=tmp_path, until="S9"))
    assert [r["status"] for r in reports] == ["incomplete", "failed", "incomplete"]
    assert (reports[1]["stage"], reports[1]["check"]) == ("S4", "law.monotonic")
    assert len({r["parameter_id"] for r in reports}) == 3
    assert (tmp_path / "set-0002" / "report.json").is_file()


def test_p0570_g3_a_loop_continues_after_a_refused_set_through_real_workers(tmp_path):
    sets = [{"FUS.length": 2.5}, {"FUS.nope": 1.0}, {"FUS.length": 3.5}]
    reports = list(_geom_run.run_doe(BODY, sets, out=tmp_path, until="S9"))
    assert [r["status"] for r in reports] == ["incomplete", "refused", "incomplete"]
    assert "unknown parameter" in reports[1]["message"]
    folder = tmp_path / "set-0003"
    on_disk = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "incomplete" and "S9 continuity.bluff_jump" in on_disk["not_run"]
    assert (folder / "S9.json").is_file()


def test_p0570_g3_a_worker_that_does_not_answer_is_a_failed_set_and_the_loop_goes_on(
    tmp_path, monkeypatch
):
    """A real worker ended by its time limit: that set fails at ``worker``, the next one runs."""
    sets = [{"FUS.length": 2.5}, {"FUS.length": 3.5}]
    loop = _geom_run.run_doe(BODY, sets, out=tmp_path, until="S2")
    monkeypatch.setenv("PYFLIGHTSTREAM_GMSH_TIMEOUT", "0.01")
    first = next(loop)
    monkeypatch.delenv("PYFLIGHTSTREAM_GMSH_TIMEOUT")
    second = next(loop)
    assert first["status"] == "failed"
    assert (first["stage"], first["check"]) == ("worker", "worker.completed")
    assert "ran longer than 0.01 s" in first["message"]
    assert second["status"] == "incomplete"


def test_p0570_g3_workers_below_one_and_an_unknown_until_are_refused(tmp_path):
    with pytest.raises(InputValueError, match="workers"):
        list(_geom_run.run_doe(BODY, [{}], out=tmp_path, workers=0))
    with pytest.raises(InputValueError, match="stage 'S14'"):
        list(_geom_run.run_doe(BODY, [{}], out=tmp_path, until="S14"))


def test_p0570_g3_unbuilt_geometry_entries_refuse_and_write_nothing(tmp_path):
    with pytest.raises(InputValueError, match="not built yet"):
        _geom_run.add_control_surfaces(tmp_path / "a.igs", "WING", [{}], tmp_path / "o")
    with pytest.raises(InputValueError, match="not built yet"):
        _geom_run.split_symmetry(tmp_path / "a.igs", tmp_path / "half.igs")
    with pytest.raises(InputValueError, match="plane"):
        _geom_run.split_symmetry(tmp_path / "a.igs", tmp_path / "half.igs", plane="q")
    assert not list(tmp_path.iterdir())


#: The release that owns PFS-2220. Its preparation commit sets this version in pyproject.toml,
#: and from then on no geometry entry may refuse as not built. Deferring an entry to a later
#: release is a decision that edits this line.
_RELEASE = "0.57.0"


def _tree_version():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]


def _not_built_entries(folder):
    """Return the geometry entries that refuse as not built yet in this tree."""
    calls = {
        "add_control_surfaces": lambda: _geom_run.add_control_surfaces(
            folder / "a.igs", "WING", [{}], folder / "o"
        ),
        "split_symmetry": lambda: _geom_run.split_symmetry(folder / "a.igs", folder / "h.igs"),
    }
    found = []
    for name, call in calls.items():
        try:
            call()
        except Exception as error:  # any refusal but "not built" is a built entry's own
            if "not built yet" in str(error):
                found.append(name)
    return found


def test_p0570_r18_002_a_not_built_entry_cannot_reach_the_release(tmp_path):
    """C8: split-symmetry and add-control-surface ship built, or the release commit is red."""
    from packaging.version import Version

    if Version(_tree_version()) >= Version(_RELEASE):
        assert _not_built_entries(tmp_path) == []


def test_p0570_g3_the_export_stage_writes_an_iges_the_report_names(tmp_path):
    from tests.tier1_offline._kernel_support import kernel_or_skip

    kernel_or_skip()
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S11")
    assert report["status"] == "incomplete", report
    assert "S11 area.read_back" in report["not_run"]
    assert "S11 profile.surfaces_only" not in report["not_run"]
    assert Path(report["outputs"]["iges"]).is_file()
    assert Path(report["outputs"]["iges"]).parent == tmp_path
