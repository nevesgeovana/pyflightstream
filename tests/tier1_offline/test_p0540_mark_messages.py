"""P0540-MARK: the marking errors name the command that refreshes a generated OBJ's sidecar."""

from __future__ import annotations

import re

import pytest

from pyflightstream._errors import InputArtifactError

OBJ = "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 1 1 0\ng wing\nf 1 2 3\n"
TABLES = '\nfs_build = "26.125"\n[import]\nunits = "METER"\n[trailing_edges]\nnone = true\n'


def _generated(tmp_path):
    from pyflightstream.workspace.sidecars import write_inventory

    mesh = tmp_path / "wing.obj"
    mesh.write_text(OBJ)
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write(TABLES)
    return mesh, sidecar


def _run(args):
    from pyflightstream.workspace.cli import main

    try:
        return main(args)
    except SystemExit as error:
        return error.code or 0


@pytest.mark.requirement("FR-3479")
def test_p0540_a_stale_hash_names_the_refresh_and_the_refresh_lets_the_marking_plan(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh, sidecar = _generated(tmp_path)
    mesh.write_text(OBJ.replace("v 1 1 0", "v 2 2 0"))
    with pytest.raises(InputArtifactError) as caught:
        plan_mark_boundaries(mesh)
    message = str(caught.value)
    assert "mesh_sha256 is stale" in message
    found = re.search(r"`pyfs-workspace (geometry inventory (\S+) --refresh)`", message)
    assert found, message
    before = sidecar.read_text()
    assert _run(found.group(1).replace(found.group(2), str(mesh)).split()) == 0
    after = sidecar.read_text()
    # Every line but the three counted keys is kept, in place.
    counted = ("mesh_faces", "boundary_faces", "mesh_sha256")
    other = [ln for ln in before.splitlines() if not ln.startswith(counted)]
    assert [ln for ln in after.splitlines() if not ln.startswith(counted)] == other
    assert "mesh_faces = 1" in after and "boundary_faces = [1]" in after
    assert after.splitlines().count("[import]") == 1 and "none = true" in after
    plan = plan_mark_boundaries(mesh)
    assert plan.faces == (1,)


@pytest.mark.requirement("FR-3479")
def test_p0540_missing_face_counts_name_the_refresh_and_it_restores_them(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh, sidecar = _generated(tmp_path)
    kept = [
        ln
        for ln in sidecar.read_text().splitlines()
        if not ln.startswith(("boundary_faces", "mesh_faces"))
    ]
    sidecar.write_text("\n".join(kept) + "\n")
    with pytest.raises(InputArtifactError) as caught:
        plan_mark_boundaries(mesh)
    assert f"pyfs-workspace geometry inventory {mesh.resolve()} --refresh" in str(caught.value)
    assert _run(["geometry", "inventory", str(mesh), "--refresh"]) == 0
    assert plan_mark_boundaries(mesh).faces == (1,)


@pytest.mark.requirement("FR-3479")
def test_p0540_refresh_refuses_a_boundary_list_that_changed_and_writes_nothing(tmp_path, capsys):
    mesh, sidecar = _generated(tmp_path)
    mesh.write_text(OBJ + "g flap\nf 2 4 3\n")
    before = sidecar.read_bytes()
    assert _run(["geometry", "inventory", str(mesh), "--refresh"]) == 2
    assert "boundaries differ" in capsys.readouterr().err
    assert sidecar.read_bytes() == before


@pytest.mark.requirement("FR-3479")
def test_p0540_refresh_rewrites_the_legacy_sidecar_the_marking_reads(tmp_path):
    """REL-K-009: the marking reads a legacy sidecar and names the refresh, which must take it."""
    from pyflightstream.workspace import plan_mark_boundaries

    mesh, sidecar = _generated(tmp_path)
    legacy = mesh.with_name("wing.boundaries.toml")
    sidecar.rename(legacy)
    mesh.write_text(OBJ + "f 2 4 3\n")
    with pytest.raises(InputArtifactError, match="--refresh"):
        plan_mark_boundaries(mesh)
    assert _run(["geometry", "inventory", str(mesh), "--refresh"]) == 0
    assert not sidecar.exists()
    assert plan_mark_boundaries(mesh).faces == (2,)


@pytest.mark.requirement("FR-3479")
def test_p0540_refresh_replaces_a_counted_key_written_over_several_lines(tmp_path):
    """REL-K-010: the continuation lines of a replaced array go with it; the TOML stays valid."""
    import tomllib

    mesh, sidecar = _generated(tmp_path)
    text = sidecar.read_text()
    wrapped = re.sub(r"boundary_faces = \[(\d+)\]", r"boundary_faces = [\n  \1,\n]", text)
    assert wrapped != text
    sidecar.write_text(wrapped)
    mesh.write_text(OBJ + "f 2 4 3\n")
    assert _run(["geometry", "inventory", str(mesh), "--refresh"]) == 0
    stated = tomllib.loads(sidecar.read_text())
    assert stated["boundary_faces"] == [2] and stated["mesh_faces"] == 2
    assert stated["fs_build"] == "26.125" and stated["trailing_edges"] == {"none": True}


@pytest.mark.requirement("FR-3479")
def test_p0540_refresh_counts_no_bracket_of_a_comment_and_keeps_other_comments(tmp_path):
    """REL-K-010: a bracket in a comment on a continuation line does not end or extend the key."""
    import tomllib

    mesh, sidecar = _generated(tmp_path)
    text = sidecar.read_text()
    wrapped = re.sub(r"boundary_faces = \[(\d+)\]", r"boundary_faces = [\n  \1, # ] [ [\n]", text)
    assert wrapped != text
    sidecar.write_text(wrapped.replace('fs_build = "26.125"', 'fs_build = "26.125" # kept'))
    mesh.write_text(OBJ + "f 2 4 3\n")
    assert _run(["geometry", "inventory", str(mesh), "--refresh"]) == 0
    assert tomllib.loads(sidecar.read_text())["boundary_faces"] == [2]
    assert 'fs_build = "26.125" # kept' in sidecar.read_text()


@pytest.mark.requirement("FR-3479")
def test_p0540_refresh_writes_nothing_when_the_result_would_not_read_back(
    tmp_path, monkeypatch, capsys
):
    """REL-K-010: the sidecar holds the declarations, so a rewrite is proved before writing."""
    from pyflightstream.workspace import sidecars

    mesh, sidecar = _generated(tmp_path)
    before = sidecar.read_bytes()
    mesh.write_text(OBJ + "f 2 4 3\n")
    monkeypatch.setattr(sidecars, "_with_counted_keys", lambda lines, fresh: ["not toml ["])
    assert _run(["geometry", "inventory", str(mesh), "--refresh"]) == 2
    assert "nothing was changed" in capsys.readouterr().err
    assert sidecar.read_bytes() == before


@pytest.mark.requirement("FR-3479")
def test_p0540_plain_inventory_still_leaves_an_existing_obj_sidecar_alone(tmp_path):
    mesh, sidecar = _generated(tmp_path)
    before = sidecar.read_bytes()
    assert _run(["geometry", "inventory", str(mesh)]) == 2
    assert sidecar.read_bytes() == before
