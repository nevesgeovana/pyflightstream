"""Tier 1: the evidence reports read the invocation off the run (PFS-2012.04).

The executor sentence of a compat, drift or physics report used to be
ASSERTED: ``describe_invocation()`` described the executor the QA layer
builds by default, and every report carried it whether or not that was
the executor that ran. These tests hold the other reading: when the run
carries a record of the invocation, the sentence is built from it.
"""

from __future__ import annotations

import re
from dataclasses import fields

import yaml

from pyflightstream.qa.compat import write_compat_report
from pyflightstream.qa.probes import ProbeRun
from pyflightstream.run import describe_invocation


def _probe_run(**overrides) -> ProbeRun:
    body = dict(
        version="26.120",
        solver_identity=("Flightstream version 26.120, build 7012026",),
        fs_exe_name="fake",
        package_version="0.0.0",
        results=(),
    )
    body.update(overrides)
    return ProbeRun(**body)


def test_a_report_reads_the_executor_line_from_the_record(tmp_path):
    """A run that records a visible run under another executor says so."""
    assert "executor" in {member.name for member in fields(ProbeRun)}, (
        "ProbeRun carries no executor record, so the report can only assert the "
        "invocation rather than read it (PFS-2012.04)"
    )
    record = {"class_name": "FakeExecutor", "argv": ["fs.exe", "-script", "probe.txt"]}
    yaml_path, md_path = write_compat_report(
        _probe_run(executor=record), tmp_path, date="2026-09-08"
    )
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert document["executor"].startswith("FakeExecutor, -script"), document["executor"]
    assert "-hidden" not in document["executor"], (
        "the record ran without -hidden and the report asserts it anyway"
    )
    assert "| Executor | FakeExecutor, `-script`" in md_path.read_text(encoding="utf-8")


def test_a_report_without_a_record_states_the_asserted_line(tmp_path):
    """The control: no record, and the sentence is the stated fallback."""
    yaml_path, _ = write_compat_report(_probe_run(), tmp_path, date="2026-09-08")
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert document["executor"] == describe_invocation()
    assert "as run" not in document["executor"], (
        "a report with no record must not claim its sentence was read from one"
    )


def test_the_sentence_built_from_a_record_says_it_was_read():
    """The two sentences differ by construction, so a reader can tell them apart."""
    record = {"class_name": "LocalExecutor", "argv": ["fs.exe", "-hidden", "-script", "p.txt"]}
    read = describe_invocation(record)
    assert read.startswith("LocalExecutor, -hidden -script (as run;")
    assert describe_invocation(record, markdown=True).replace("`", "") == read
    assert describe_invocation({"class_name": "FakeExecutor", "argv": []}).startswith(
        "FakeExecutor, no argv recorded"
    )


#: A dimensional value of a propeller or its run, from which a length can be
#: recovered: a force or moment in newtons, a speed, a density, a rotor speed,
#: a time step, or a run id's rotor-speed token.
_DIMENSIONAL = re.compile(
    r"\d\s?(?:N m|N|m/s|kg/m3|rev/min)\b|RPM\d|\"rpm\"|_Nm?\"|delta_time_s|velocity_m_s"
)


def test_x_f_1217_a_label_too_long_for_a_file_name_is_refused_before_the_run(tmp_path):
    """The pre-flight refuses a 300-character label that could fail at write on a short-path
    file system, and names the longest it accepts."""
    import pytest

    from pyflightstream.qa.errors import QaEvidenceError
    from pyflightstream.qa.reports import report_paths

    report_paths(tmp_path, series="CMP", versions=["26.120"], date="2026-10-21", label="x" * 64)
    with pytest.raises(QaEvidenceError, match=r"300 characters long.*longest.*is 64"):
        report_paths(
            tmp_path, series="CMP", versions=["26.120"], date="2026-10-21", label="x" * 300
        )


def test_f_1866_the_report_series_comment_points_at_nothing_absent():
    import pyflightstream.qa.reports as reports

    source = open(reports.__file__, encoding="utf-8").read()
    assert "reports/README.md" not in source
