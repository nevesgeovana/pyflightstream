# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.0
# last_modified_at: 2026-09-27T23:43:03.876Z
# last_modified_by: OpenAI / Codex / unknown / api-designer-pyflightstream
# dependencies: [pyflightstream.workspace.excel_sync, pyflightstream.workspace.fsi_setup]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Verify release refusals retain builtin catches and join the catalog.
# revision_source: git
# GEOVERSE_HEADER_END

"""Public input refusals retain built-in catches and the package error boundary."""

import numpy as np
import pytest

from pyflightstream.cases.field_coverage import spatial_envelope
from pyflightstream.cases.workflows import unsteady_action_command_line
from pyflightstream.exceptions import (
    CampaignConfigError,
    CommandArgumentError,
    ProductArgumentError,
    ProductError,
    PyflightstreamError,
)
from pyflightstream.post.diagnostics import render_post_diagnostics
from pyflightstream.post.field_frames import native_velocity_proof
from pyflightstream.post.probe_fields import write_probe_field
from pyflightstream.post.writers import OutputProvenance
from pyflightstream.script import Script, helpers


def test_field_coverage_refusal_keeps_valueerror():
    with pytest.raises(CampaignConfigError, match="no mesh vertices") as caught:
        spatial_envelope([], [], [])
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, PyflightstreamError)


def test_probe_field_refusal_keeps_valueerror(tmp_path):
    with pytest.raises(ProductError, match="explicit REFERENCE frame") as caught:
        write_probe_field(
            tmp_path / "field",
            np.ones((4, 3)),
            np.ones((4, 3)),
            source=tmp_path / "unused",
            provenance=OutputProvenance(
                run_id="test/point",
                setup=helpers.solver_settings(Script("26.124"), velocity=30.0),
            ),
            frame="unknown",
        )
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, PyflightstreamError)
    assert not list(tmp_path.iterdir())


def test_native_proof_refusal_keeps_valueerror():
    with pytest.raises(ProductError, match="no evidence") as caught:
        native_velocity_proof({}, solver_identity={}, export_kind="unproved")
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, PyflightstreamError)


def test_action_interpreter_refusal_keeps_valueerror(tmp_path, monkeypatch):
    import pyflightstream.cases.workflows as workflows

    monkeypatch.setattr(workflows.sys, "platform", "win32")
    with pytest.raises(CampaignConfigError, match="pythonw.exe") as caught:
        unsteady_action_command_line(str(tmp_path / "python.exe"))
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, PyflightstreamError)


@pytest.mark.parametrize(
    "method,args",
    [
        ("bind_native_solver_identity", {"executable_sha256": "bad", "build": "build"}),
        ("bind_native_solver_identity", {"executable_sha256": "a" * 64, "build": ""}),
        ("record_opened_length_unit", {"unit": "unknown"}),
    ],
)
def test_script_evidence_refusal_keeps_valueerror(method, args):
    script = Script("26.124")
    with pytest.raises(CommandArgumentError) as caught:
        getattr(script, method)(**args)
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, PyflightstreamError)


def test_diagnostics_refusal_keeps_outward_typeerror(tmp_path):
    log = tmp_path / "post.json"
    log.write_text('{"records": [1]}', encoding="utf8")
    with pytest.raises(ProductArgumentError, match="each diagnostic record") as caught:
        render_post_diagnostics([log])
    assert isinstance(caught.value, TypeError)
    assert not isinstance(caught.value, ValueError)
    assert log.read_text(encoding="utf8") == '{"records": [1]}'
