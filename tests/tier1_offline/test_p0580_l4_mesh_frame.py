"""Tier 1, 0.58.0 PFS-2233 (FR-3790 to FR-3794): the solver gets every mesh in the expected frame.

Written from the approved design page (section 5.1). The expected frame is x aft,
y right, z up; ``mesh_frame = [...]`` in the boundaries sidecar states what the
mesh's +x, +y and +z point to. Every case runs through ``run_campaign``, the
path that stages the mesh the solver opens.
"""

from __future__ import annotations

import hashlib

import pytest

from pyflightstream.run import run_campaign
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_run_campaign import (
    WRITES_LOADS,
    StubSolver,
    converged,
    make_campaign,
    steady_recipe,
)

OBJ = (
    "# a wing, three vertices and two groups\n"
    "v 1.0 2.0 3.0\n"
    "v -4.5 0.0 +6.0\n"
    "v 7 8 9\n"
    "vn 0.0 1.0 0.0\n"
    "g Wing\n"
    "f 1//1 2//1 3//1\n"
    "g Tail\n"
    "f 3//1 2//1 1//1\n"
)


def _run(tmp_path, geometry_name, frame_line, text):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    geometry = tmp_path / geometry_name
    (tmp_path / "wing.fsm").unlink()
    geometry.write_text(text, encoding="utf-8", newline="\n")
    campaign.sims[0].geometry = str(geometry)
    if frame_line is not None:
        (tmp_path / f"{geometry_name}.boundaries.toml").write_text(frame_line, encoding="utf-8")
    workspace = CampaignWorkspace(tmp_path / "camp")
    try:
        records = run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    except Exception:  # the refusal is read from the record, as every preparation failure is
        records = []
    return workspace, geometry, records or workspace.read_manifest()


def test_p0580_l4_a_declared_frame_is_converted_before_the_solver_opens_the_mesh(tmp_path):
    workspace, geometry, records = _run(
        tmp_path, "wing.obj", 'mesh_frame = ["forward", "left", "up"]\n', OBJ
    )
    assert records[0].status is RunStatus.CONVERGED, records[0].error
    converted = workspace.sim_dir("9001") / "mesh_frame" / "wing.obj"
    lines = converted.read_text(encoding="utf-8").splitlines()
    # +x forward and +y left reverse x and y; +z up stays. The digits are those written.
    assert lines[1:5] == ["v -1.0 -2.0 3.0", "v 4.5 -0.0 +6.0", "v -7 -8 9", "vn -0.0 -1.0 0.0"]
    # THE LIBRARY FILE IS NOT REWRITTEN.
    assert geometry.read_text(encoding="utf-8") == OBJ


def test_p0580_l4_face_order_and_group_names_are_kept_byte_for_byte(tmp_path):
    workspace, _, _ = _run(tmp_path, "wing.obj", 'mesh_frame = ["forward", "left", "up"]\n', OBJ)
    converted = (workspace.sim_dir("9001") / "mesh_frame" / "wing.obj").read_text(encoding="utf-8")
    kept = [line for line in OBJ.splitlines() if line[:2] in ("# ", "g ", "f ")]
    assert [line for line in converted.splitlines() if line[:2] in ("# ", "g ", "f ")] == kept


def test_p0580_l4_the_vertices_are_in_the_expected_frame(tmp_path):
    """A mesh declared up, forward, left: +x is up, +y is forward, +z is left."""
    workspace, _, records = _run(
        tmp_path, "wing.obj", 'mesh_frame = ["up", "forward", "left"]\n', "v 1 2 3\n"
    )
    assert records[0].status is RunStatus.CONVERGED, records[0].error
    converted = workspace.sim_dir("9001") / "mesh_frame" / "wing.obj"
    # expected x (aft) = -(mesh y) = -2; expected y (right) = -(mesh z) = -3;
    # expected z (up) = mesh x = 1
    assert converted.read_text(encoding="utf-8") == "v -2 -3 1\n"


def test_p0580_l4_the_run_record_carries_the_declared_frame_and_the_digests(tmp_path):
    workspace, geometry, records = _run(
        tmp_path, "wing.obj", 'mesh_frame = ["forward", "left", "up"]\n', OBJ
    )
    frame = records[0].mesh_frame
    assert frame is not None
    assert frame["declared"] == ["forward", "left", "up"]
    assert frame["matrix"] == [[-1, 0, 0], [0, -1, 0], [0, 0, 1]]
    assert frame["source_sha256"] == hashlib.sha256(geometry.read_bytes()).hexdigest()
    converted = workspace.sim_dir("9001") / "mesh_frame" / "wing.obj"
    assert frame["converted_sha256"] == hashlib.sha256(converted.read_bytes()).hexdigest()
    assert frame["converted_sha256"] != frame["source_sha256"]


def test_p0580_l4_the_script_opens_the_converted_copy(tmp_path):
    workspace, _, _ = _run(tmp_path, "wing.obj", 'mesh_frame = ["forward", "left", "up"]\n', OBJ)
    scripts = [
        path
        for path in workspace.sim_dir("9001").rglob("*.txt")
        if "OPEN" in path.read_text(errors="replace")
    ]
    opened = "\n".join(path.read_text(errors="replace") for path in scripts)
    assert "mesh_frame/wing.obj" in opened.replace("\\", "/")
    assert "inputs/wing.obj" not in opened.replace("\\", "/")


def test_p0580_l4_a_left_handed_declaration_is_refused_by_name(tmp_path):
    _, _, records = _run(tmp_path, "wing.obj", 'mesh_frame = ["forward", "right", "up"]\n', OBJ)
    assert records[0].status is not RunStatus.CONVERGED
    assert "mesh_frame = ['forward', 'right', 'up']" in records[0].error
    assert "left-handed" in records[0].error


def test_p0580_l4_a_saved_simulation_in_another_frame_is_refused_by_name(tmp_path):
    _, _, records = _run(
        tmp_path, "wing.fsm", 'mesh_frame = ["forward", "left", "up"]\n', "geometry"
    )
    assert records[0].status is not RunStatus.CONVERGED
    assert "mesh_frame = ['forward', 'left', 'up']" in records[0].error
    assert "saved simulation" in records[0].error


def test_p0580_l4_a_saved_simulation_in_the_expected_frame_runs_as_before(tmp_path):
    workspace, _, records = _run(
        tmp_path, "wing.fsm", 'mesh_frame = ["aft", "right", "up"]\n', "geometry"
    )
    assert records[0].status is RunStatus.CONVERGED, records[0].error
    assert not (workspace.sim_dir("9001") / "mesh_frame" / "wing.fsm").exists()


@pytest.mark.parametrize(
    ("declared", "text"),
    [
        ('["forward", "left"]', "three words"),
        ('["forward", "sideways", "up"]', "sideways"),
        ('["forward", "aft", "up"]', "names an axis twice"),
    ],
)
def test_p0580_l4_a_malformed_declaration_is_refused_naming_it(tmp_path, declared, text):
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace.sidecars import read_mesh_frame

    sidecar = tmp_path / "wing.obj.boundaries.toml"
    sidecar.write_text(f"mesh_frame = {declared}\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match=text):
        read_mesh_frame(sidecar)


def test_p0580_l4_the_words_are_case_insensitive(tmp_path):
    from pyflightstream.workspace.sidecars import read_mesh_frame

    sidecar = tmp_path / "wing.obj.boundaries.toml"
    sidecar.write_text('mesh_frame = ["Forward", "LEFT", "Up"]\n', encoding="utf-8")
    assert read_mesh_frame(sidecar) == ("forward", "left", "up")


def _declared_obj(tmp_path):
    obj = tmp_path / "wing.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng Wing\nf 1 2 3\n", encoding="utf-8")
    (tmp_path / "wing.obj.boundaries.toml").write_text(
        'mesh_frame = ["forward", "left", "up"]\n', encoding="utf-8"
    )
    return obj


def test_p0580_l4_mark_boundaries_refuses_a_declared_frame_by_name(tmp_path):
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace import plan_mark_boundaries

    with pytest.raises(InputArtifactError) as refused:
        plan_mark_boundaries(_declared_obj(tmp_path))
    text = str(refused.value)
    assert "mesh_frame = ['forward', 'left', 'up']" in text and "['aft', 'right', 'up']" in text
    # The FSI route reads the same inputs first, so this is also its plan-time message.
    assert "the FSI route and mark-boundaries do not convert a mesh to the expected" in text
    assert "staged FSI mesh differs" not in text


@pytest.mark.parametrize("name", ["wing.obj", "wing.fsm"])
def test_p0580_l4_an_absent_key_changes_nothing(tmp_path, name):
    workspace, geometry, records = _run(tmp_path, name, None, OBJ if name.endswith("obj") else "x")
    assert records[0].status is RunStatus.CONVERGED, records[0].error
    assert records[0].mesh_frame is None
    assert not (workspace.sim_dir("9001") / "mesh_frame").exists()
    assert (workspace.sim_dir("9001") / "inputs" / name).read_bytes() == geometry.read_bytes()
