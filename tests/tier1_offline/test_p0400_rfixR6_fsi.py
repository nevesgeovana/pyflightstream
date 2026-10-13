"""No declared external FSI file can land on a name the archiving step owns (FR-462 R3, R4).

P0400-RFIXR6-FSI (PFS-2081.121, REL6-001). The step writes ``call.json`` into
every per-call archive beside the loads file, the displacement file and the
declared outputs, and reads or writes a handful of files in the point folder.
A declared input or output under one of those names would be overwritten, or
would overwrite the step's own file, while the call reports success; each layer
that reads the declaration refuses it instead, and no user byte is lost.
"""

# ruff: noqa: N999 - the lane contract prescribes the rfixR6 filename.

from __future__ import annotations

import hashlib
import json

import pytest

import pyflightstream.fsi.external as external
from pyflightstream.cases import CampaignConfigError
from pyflightstream.fsi.external import EXTERNAL_MANIFEST, external_step
from pyflightstream.fsi.state import DISPLACEMENT_FILE, LOADS_FILE
from pyflightstream.workspace.fsi_external_setup import (
    FsiExternalSetupError,
    resolve_external_fsi,
)
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_p0400_gaps_rt_fsiext import INPUT, _external_case, _inputs, _point

pytestmark = pytest.mark.requirement("FR-462")


def test_p0400_rfixr6_the_step_names_its_archive_record_and_point_files():
    """P0400-RFIXR6-FSI: one home names every file the step owns, the record among them."""
    assert external.ARCHIVE_RECORD == "call.json"
    for name in (
        "call.json",
        EXTERNAL_MANIFEST,
        LOADS_FILE,
        DISPLACEMENT_FILE,
        "fsi_external_nodes.csv",
        "fsi_external_calls.csv",
        "pyfs_fsi_error.log",
        "fsi_external_stdout.txt",
        "fsi_archive",
    ):
        assert name in external.STEP_NAMES, name


@pytest.mark.parametrize("name", ["call.json", "Call.JSON", "fsi_external_stdout.txt"])
def test_p0400_rfixr6_a_step_name_as_output_is_refused_at_reading(tmp_path, name):
    """P0400-RFIXR6-FSI: resolve refuses the output, naming it, before any plan."""
    path = _inputs(tmp_path, INPUT.replace('outputs = ["struct_log.txt"]', f'outputs = ["{name}"]'))
    with pytest.raises(FsiExternalSetupError, match="the archiving step") as raised:
        resolve_external_fsi(path)
    assert repr(name) in str(raised.value)


def test_p0400_rfixr6_a_step_name_as_input_is_refused_at_reading(tmp_path):
    """P0400-RFIXR6-FSI: an input staged as call.json is refused the same way."""
    path = _inputs(tmp_path, INPUT.replace('inputs = ["f010.model.dat"]', 'inputs = ["call.json"]'))
    (path.parent / "call.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(FsiExternalSetupError, match="'call.json'"):
        resolve_external_fsi(path)


def test_p0400_rfixr6_the_archive_record_name_is_refused_at_plan(tmp_path):
    """P0400-RFIXR6-FSI: a structure carrying call.json as output never reaches a script."""
    case, structure = _external_case(tmp_path)
    changed = structure.model_copy(update={"outputs": ["struct_log.txt", "CALL.json"]})
    with pytest.raises(CampaignConfigError, match="reserved-name collision") as raised:
        _lines(case.model_copy(update={"fsi_external": changed}))
    assert "call.json" in str(raised.value).casefold()


def test_p0400_rfixr6_the_step_refuses_a_manifest_that_would_overwrite_its_record(tmp_path):
    """P0400-RFIXR6-FSI: the program is not run, nothing is archived, the user's file stays."""
    folder = _point(tmp_path)
    users = folder / "call.json"
    users.write_bytes(b"the structural program's own call.json\n")
    manifest = json.loads((folder / EXTERNAL_MANIFEST).read_text(encoding="utf-8"))
    manifest["outputs"] = ["struct_log.txt", "call.json"]
    (folder / EXTERNAL_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert external_step(folder) == 1
    error = (folder / "pyfs_fsi_error.log").read_text(encoding="utf-8")
    assert "'call.json'" in error and "the archiving step" in error
    assert not (folder / "struct_log.txt").exists(), "the program ran"
    assert not (folder / DISPLACEMENT_FILE).exists()
    assert not (folder / "fsi_archive").exists()
    assert users.read_bytes() == b"the structural program's own call.json\n"


def test_p0400_rfixr6_every_archived_byte_matches_its_recorded_digest(tmp_path):
    """P0400-RFIXR6-FSI: across two calls, each archive holds what its record says it holds."""
    folder = _point(tmp_path)
    assert external_step(folder) == 0
    (folder / LOADS_FILE).write_text("loads of the second call\n", encoding="utf-8")
    assert external_step(folder) == 0
    for call in ("call_0001", "call_0002"):
        archive = folder / "fsi_archive" / call
        record = json.loads((archive / "call.json").read_text(encoding="utf-8"))
        assert set(record["written_sha256"]) == {DISPLACEMENT_FILE, "struct_log.txt"}
        for name, digest in record["written_sha256"].items():
            assert hashlib.sha256((archive / name).read_bytes()).hexdigest() == digest, name
        assert (
            hashlib.sha256((archive / LOADS_FILE).read_bytes()).hexdigest()
            == record["read_sha256"][LOADS_FILE]
        )
    first = folder / "fsi_archive" / "call_0001" / LOADS_FILE
    assert first.read_text(encoding="utf-8") == "loads of the call\n"
