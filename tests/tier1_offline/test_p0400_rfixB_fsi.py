# ruff: noqa: N999
"""External FSI refuses coupling-file collisions and checks structural node bytes."""

import hashlib
import json
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases._fsi_external import EXTERNAL_NODES_FILE
from pyflightstream.fsi.external import external_step
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_p0400_gaps_rt_fsiext import _external_case, _point


@pytest.mark.requirement("FR-462")
@pytest.mark.parametrize(
    "name",
    [
        EXTERNAL_NODES_FILE,
        "fsi_callback.py",
        "fsi_external.json",
        "fsi_post.txt",
        "FSI_CALLBACK.PY",
    ],
)
@pytest.mark.parametrize("kind", ["inputs", "outputs"])
def test_p0400_rfixb_reserved_fsi_names_are_refused_before_staging(tmp_path, name, kind):
    """P0400-RFIXB-FSI-COLLISION: user files cannot replace the coupling payloads."""
    case, structure = _external_case(tmp_path)
    value = {name: structure.structural_nodes} if kind == "inputs" else [name]
    changed = structure.model_copy(update={kind: value})
    with pytest.raises(CampaignConfigError, match="reserved-name collision"):
        _lines(case.model_copy(update={"fsi_external": changed}))


@pytest.mark.requirement("FR-462")
@pytest.mark.parametrize("name", ["f010.toml", "f010.model.dat"])
def test_p0400_rfixb_output_cannot_clobber_an_input(tmp_path, name):
    """P0400-RFIXB-FSI-COLLISION: the program's outputs cannot overwrite provenance or inputs."""
    case, structure = _external_case(tmp_path)
    changed = structure.model_copy(update={"outputs": [name]})
    with pytest.raises(CampaignConfigError, match="reserved-name collision"):
        _lines(case.model_copy(update={"fsi_external": changed}))


@pytest.mark.requirement("FR-462")
def test_p0400_rfixb_changed_same_count_nodes_are_not_staged(tmp_path):
    """P0400-RFIXB-FSI-NODES: three different nodes still violate the planned digest."""
    case, structure = _external_case(tmp_path)
    Path(structure.structural_nodes).write_text("0,0,0\n1,1,1\n2,2,2\n", encoding="utf-8")
    with pytest.raises(CampaignConfigError, match="node file changed"):
        _lines(case)


@pytest.mark.requirement("FR-462")
@pytest.mark.parametrize("changed", ["missing", "changed"])
def test_p0400_rfixb_step_checks_nodes_before_starting_program(tmp_path, changed):
    """P0400-RFIXB-FSI-DIGEST: missing or changed nodes refuse before any program call."""
    folder = _point(tmp_path)
    nodes = folder / EXTERNAL_NODES_FILE
    if changed == "missing":
        nodes.unlink()
    else:
        nodes.write_text("0,0,0\n1,1,1\n2,2,2\n", encoding="utf-8")
    assert external_step(folder) == 1
    assert not (folder / "struct_log.txt").exists()
    assert "structural node file" in (folder / "pyfs_fsi_error.log").read_text()


@pytest.mark.requirement("FR-462")
def test_p0400_rfixb_call_records_the_verified_node_digest(tmp_path):
    """P0400-RFIXB-FSI-DIGEST: the call records the staged node bytes actually read."""
    folder = _point(tmp_path)
    assert external_step(folder) == 0
    record = json.loads((folder / "fsi_archive" / "call_0001" / "call.json").read_text())
    assert (
        record["read_sha256"][EXTERNAL_NODES_FILE]
        == hashlib.sha256((folder / EXTERNAL_NODES_FILE).read_bytes()).hexdigest()
    )
