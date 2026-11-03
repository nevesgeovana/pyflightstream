"""P0540-WHEEL-OBJ: the OBJ route of sector-to-wheel, its files and its command.

Pipeline role: tier-1 oracle of PFS-2186.02 (FR-3463, FR-3465, FR-3468). The sector is built
in numpy by ``test_p0540_wheel.build_sector``: a spinner without a base, a blade whose
trailing edge is blunt (two rims, a base of one quad row) or sharp (one rim, no base), and a
nacelle with a base and a rim. The names, the counts and the files are asserted from the
construction, not from the output.
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, InputValueError, NotApplicableWarning
from pyflightstream.workspace._wheel import sector_to_wheel, validate_blades
from pyflightstream.workspace.sidecars import read_boundary_declarations
from tests.tier1_offline.test_p0540_wheel import build_sector, read_wheel

COPIES = 6


def _wheel(tmp_path, **kwargs):
    sector = build_sector(tmp_path, **kwargs.pop("sector", {}))
    out = tmp_path / "out" / "wheel.obj"
    out.parent.mkdir(exist_ok=True)
    result = sector_to_wheel(sector.obj, copies=COPIES, blades=["Blade1"], out=out, **kwargs)
    return sector, result


def _points(path):
    rows = path.read_text(encoding="utf-8").split()
    assert rows[0] == "METER"
    return np.array([[float(c) for c in r.split(",")] for r in rows[1:]])


@pytest.mark.requirement("FR-3465")
def test_p0540_a_blunt_blade_gets_two_rims_and_a_base_per_copy(tmp_path):
    sector, result = _wheel(tmp_path)
    wheel, groups = read_wheel(result.output)
    blades = [f"Blade{k}" for k in range(1, COPIES + 1)]
    bases = [f"Base{k}" for k in range(1, COPIES + 1)]
    assert list(groups) == [*blades, *bases, "S", "N", "NBase"]
    blade_faces = len(sector.families["Blade1"])
    assert {len(groups[b]) for b in bases} == {sector.base_faces}
    assert {len(groups[b]) for b in blades} == {blade_faces - sector.base_faces}
    assert len(groups["S"]) == COPIES * len(sector.families["S"])
    assert len(groups["NBase"]) == COPIES * sector.notes["disc"]
    # the three-node rule: every node of a base face lies on the trailing edge line x = 0.7
    # (about the axis, the copy's own frame), and a blade face has one that does not
    for name in bases:
        for face in groups[name]:
            nodes = wheel[face]
            assert np.allclose(nodes[:, 0], 0.7, atol=1e-12)
            assert (np.hypot(nodes[:, 1], nodes[:, 2]) > 0.3).all()
    for face in groups["Blade1"]:
        assert not np.allclose(wheel[face][:, 0], 0.7, atol=1e-12)
    # two rim point files per blade and one for the nacelle, in the named form
    for k in range(1, COPIES + 1):
        for label in ("TE_a", "TE_b"):
            points = _points(result.output.with_name(f"wheel.{label}_{k}.te.txt"))
            assert len(points) == sector.base_faces and np.allclose(points[:, 0], 0.7, atol=1e-12)
    assert len(_points(result.output.with_name("wheel.N.te.txt"))) == COPIES * 4
    declared = read_boundary_declarations(result.output.with_name("wheel.obj.boundaries.toml"))
    labels = {e.label for e in declared.trailing_edges}
    assert labels == {f"{x}_{k}" for x in ("TE_a", "TE_b") for k in range(1, 7)} | {"N"}
    merged = {r.family: r.merge_into for r in declared.base_regions}
    assert merged == {**{f"Base{k}": f"Blade{k}" for k in range(1, 7)}, "NBase": "N"}


@pytest.mark.requirement("FR-3465")
def test_p0540_a_sharp_blade_gets_one_rim_and_no_base(tmp_path):
    sector, result = _wheel(tmp_path, sector={"blunt": False})
    _, groups = read_wheel(result.output)
    assert list(groups) == [*[f"Blade{k}" for k in range(1, 7)], "S", "N", "NBase"]
    assert not any(name.startswith("Base") for name in groups)
    assert {len(groups[f"Blade{k}"]) for k in range(1, 7)} == {len(sector.families["Blade1"])}
    assert not result.output.with_name("wheel.TE_a_1.te.txt").exists()
    assert len(_points(result.output.with_name("wheel.TE_3.te.txt"))) == 3
    declared = read_boundary_declarations(result.output.with_name("wheel.obj.boundaries.toml"))
    assert {r.family for r in declared.base_regions} == {"NBase"}


@pytest.mark.requirement("FR-3465")
def test_p0540_a_sector_that_already_names_its_bases_keeps_the_same_wheel(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, split = _wheel(tmp_path / "a")
    sector = build_sector(tmp_path / "b", separate_base=True)
    out = tmp_path / "b" / "wheel.obj"
    result = sector_to_wheel(sector.obj, copies=COPIES, blades=["Blade1"], out=out)
    _, groups = read_wheel(result.output)
    _, expected = read_wheel(split.output)
    assert list(groups) == list(expected)
    assert {n: len(f) for n, f in groups.items()} == {n: len(f) for n, f in expected.items()}


@pytest.mark.requirement("FR-3466")
def test_p0540_the_wheel_sidecar_reads_clean_and_plans_a_marking_on_26_124(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    _, result = _wheel(tmp_path)
    sidecar = result.output.with_name("wheel.obj.boundaries.toml")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        declared = read_boundary_declarations(sidecar)
    assert declared.fs_build == "26.124"
    plan = plan_mark_boundaries(result.output)
    kept = tuple(
        n for n in read_wheel(result.output)[1] if not n.startswith("Base") and n != "NBase"
    )
    assert plan.names == kept  # the bases are merged into their parents by the pass
    assert plan.script.count("SURFACE_COMBINE") == COPIES + 1
    assert plan.script.count("CREATE_NEW_BASE_REGION") == COPIES + 1
    assert not plan.work.exists()


@pytest.mark.requirement("FR-3469")
def test_p0540_the_record_states_the_source_the_axis_and_the_checks(tmp_path):
    sector, result = _wheel(tmp_path, hub=(0.0, 0.0, 0.0))
    record = json.loads(result.output.with_name("wheel.wheel.json").read_text(encoding="utf-8"))
    import hashlib

    assert record["source_sha256"] == hashlib.sha256(sector.obj.read_bytes()).hexdigest()
    assert record["copies"] == COPIES and record["axis"] == [1.0, 0.0, 0.0]
    assert record["tolerance_m"] == 1e-4 and record["hub"] == [0.0, 0.0, 0.0]
    assert record["nodes"]["merged"] > 0 and record["area_ratio"] == pytest.approx(1.0, rel=1e-12)
    assert record["open_edges"]["merged"] < record["open_edges"]["unmerged"]
    assert record["control"]["faces_mapped"] < record["control"]["faces"]
    assert [g["name"] for g in record["groups"]][:2] == ["Blade1", "Blade2"]


@pytest.mark.requirement("FR-3465")
def test_p0540_a_sector_without_a_boundaries_file_is_warned_and_still_copied(tmp_path):
    sector = build_sector(tmp_path, declare=False)
    sector.obj.with_name("sector.obj.boundaries.toml").unlink()
    with pytest.warns(Warning, match="no trailing edge and no base"):
        result = sector_to_wheel(sector.obj, copies=COPIES, blades=["Blade1"])
    assert result.output.name == "sector_wheel.obj"
    _, groups = read_wheel(result.output)
    assert list(groups) == [*[f"Blade{k}" for k in range(1, 7)], "S", "N"]


@pytest.mark.requirement("FR-3465")
def test_p0540_the_blades_and_the_copies_are_checked_before_anything_is_written(tmp_path):
    sector = build_sector(tmp_path)
    for kwargs, text in (
        ({"blades": ["Nope"]}, "not a group of the sector"),
        ({"blades": []}, "names no group"),
        ({"blades": ["Blade1"], "copies": 1}, "needs 2 or more"),
    ):
        args = {"copies": 6, **kwargs}
        with pytest.raises(InputValueError, match=text):
            sector_to_wheel(sector.obj, **args)
    assert sorted(p.name for p in tmp_path.iterdir() if "wheel" in p.name) == []
    with pytest.raises(InputValueError, match="would give copies"):
        validate_blades(["Wing1", "Wing2"], ["Wing1", "Wing2"], 6, "group")


@pytest.mark.requirement("FR-3460")
def test_p0540_an_existing_wheel_needs_overwrite_and_the_other_kind_is_warned(tmp_path):
    sector = build_sector(tmp_path)
    first = sector_to_wheel(sector.obj, copies=COPIES, blades=["Blade1"])
    before = first.output.read_bytes()
    with pytest.raises(InputArtifactError, match="--overwrite"):
        sector_to_wheel(sector.obj, copies=COPIES, blades=["Blade1"])
    assert first.output.read_bytes() == before
    again = sector_to_wheel(sector.obj, copies=COPIES, blades=["Blade1"], overwrite=True)
    assert again.output.read_bytes() == before
    with pytest.warns(NotApplicableWarning, match="takes the sector's kind"):
        other = sector_to_wheel(
            sector.obj, copies=COPIES, blades=["Blade1"], out=tmp_path / "w.fsm"
        )
    assert other.output.name == "w.obj" and not (tmp_path / "w.fsm").exists()


@pytest.mark.requirement("FR-3460")
def test_p0540_the_command_runs_end_to_end_through_pyfs_workspace(tmp_path, capsys):
    from pyflightstream.workspace.cli import main as workspace_main

    sector = build_sector(tmp_path)
    out = tmp_path / "cli_wheel.obj"
    argv = [
        "geometry",
        "sector-to-wheel",
        str(sector.obj),
        "--copies",
        "6",
        "--axis",
        "x",
        "--blades",
        "Blade1",
        "--out",
        str(out),
    ]
    assert workspace_main(argv) == 0
    printed = capsys.readouterr().out
    assert f"wrote {out}" in printed and "area ratio" in printed and "invariance 60 deg" in printed
    assert out.with_name("cli_wheel.wheel.json").is_file()
    assert workspace_main(argv) == 2
    assert "--overwrite" in capsys.readouterr().err
    assert workspace_main([*argv, "--overwrite", "--tolerance", "1e-5"]) == 0
    assert workspace_main([*argv[:-2], "--out", str(tmp_path / "z.obj"), "--blades", "X"]) == 2
