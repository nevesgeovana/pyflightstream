# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.1
# last_modified_at: 2026-10-13T15:30:59-03:00
# last_modified_by: OpenAI / Codex / GPT-6 / reviewer
# dependencies: [pytest, pyflightstream.fsi.external]
# authority: pyflightstream
# status: active
# confidentiality: internal
# change_summary: Reuse the measured failing REL8-001 guards for its missing integration, REL9-001.
# revision_source: git
# GEOVERSE_HEADER_END
"""REL8-001: outputs=['call.json.'] must never replace the call's archive record.

REL9-001: the integration retained these tests but omitted the source fix.
The invariant is checked at input resolution, planning and execution, including
an actual two-call program whose distinct output bytes would otherwise be lost.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.fsi.external import EXTERNAL_MANIFEST, external_step
from pyflightstream.workspace.fsi_external_setup import FsiExternalSetupError, resolve_external_fsi
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_p0400_gaps_rt_fsiext import (
    INPUT,
    STAND_IN,
    _external_case,
    _inputs,
    _point,
)

pytestmark = pytest.mark.requirement("FR-462")


@pytest.mark.parametrize("name", ["call.json.", "call.json "])
def test_rel8_001_resolve_refuses_archive_alias(tmp_path, name):
    path = _inputs(tmp_path, INPUT.replace('outputs = ["struct_log.txt"]', f'outputs = ["{name}"]'))
    with pytest.raises(FsiExternalSetupError, match="archiving step"):
        resolve_external_fsi(path)


@pytest.mark.parametrize("name", ["call.json.", "call.json "])
def test_rel8_001_plan_refuses_archive_alias(tmp_path, name):
    case, structure = _external_case(tmp_path)
    changed = structure.model_copy(update={"outputs": [name]})
    with pytest.raises(CampaignConfigError, match="reserved-name collision"):
        _lines(case.model_copy(update={"fsi_external": changed}))


@pytest.mark.parametrize("name", ["call.json.", "call.json "])
def test_rel8_001_two_calls_cannot_overwrite_archive_metadata(tmp_path, name):
    folder = _point(tmp_path)
    program = folder / "stand_in.py"
    program.write_text(
        STAND_IN
        + "\nfrom pathlib import Path\n"
        + "counter = Path('counter.txt')\n"
        + "count = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        + "counter.write_text(str(count))\n"
        + f"Path({name!r}).write_text(str(count))\n",
        encoding="utf-8",
    )
    path = folder / EXTERNAL_MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["inputs_sha256"]["stand_in.py"] = hashlib.sha256(program.read_bytes()).hexdigest()
    manifest["outputs"] = [name]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    results = [external_step(folder), external_step(folder)]
    mismatches = []
    for record_path in (folder / "fsi_archive").glob("call_*/call.json"):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        for output, digest in record["written_sha256"].items():
            if hashlib.sha256((record_path.parent / output).read_bytes()).hexdigest() != digest:
                mismatches.append((record["call"], output))
    assert results == [1, 1], f"accepted alias: {results}; archive digest mismatches: {mismatches}"
    assert not (folder / "counter.txt").exists(), "the structural program ran"
    assert not (folder / "fsi_archive").exists()
    assert "archiving step" in (folder / "pyfs_fsi_error.log").read_text(encoding="utf-8")
