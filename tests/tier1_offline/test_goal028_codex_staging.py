"""Staging must not collapse Windows names or write through existing file links."""

import os

import pytest

from pyflightstream.workspace import CampaignWorkspace, WorkspaceError


@pytest.mark.skipif(os.name != "nt", reason="Windows file names are case insensitive")
def test_case_insensitive_staging_collision_is_refused_before_copying(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    sources = []
    for folder, name, data in (("a", "Wing.fsm", b"first"), ("b", "wing.fsm", b"second")):
        source = tmp_path / folder / name
        source.parent.mkdir()
        source.write_bytes(data)
        sources.append(source)
    with pytest.raises(WorkspaceError, match="base name"):
        workspace.stage_inputs("9001", sources)
    assert not list((workspace.sim_dir("9001") / "inputs").iterdir())


def test_staging_does_not_overwrite_a_users_input_through_a_hardlink(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    inputs = workspace.create_sim("9001") / "inputs"
    original = tmp_path / "original.fsm"
    original.write_bytes(b"user geometry")
    target = inputs / "wing.fsm"
    os.link(original, target)
    source = tmp_path / "wing.fsm"
    source.write_bytes(b"new geometry")
    try:
        workspace.stage_inputs("9001", [source])
    except WorkspaceError:
        pass  # Refusing a linked destination also preserves the user's input.
    assert original.read_bytes() == b"user geometry", "staging overwrote the linked user input"
