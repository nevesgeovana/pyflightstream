"""`pyfs-matrix inventory` writes the boundary sidecar from the file (PFS-2029.06.02)."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from pyflightstream._fsm import boundary_names, saved_solver_actions
from pyflightstream._fsm_fresh import (
    FRESH_IMPORT,
    KEPT_BLOCKS,
    block_lines,
    common_blocks,
    reset_to_fresh_import,
)
from pyflightstream.run.cli import main
from pyflightstream.workspace.inputs import InputArtifactError, clean_saved_actions
from tests.support_helpers import saved_mesh_fixture as _saved_simulation


def test_inventory_writes_the_sidecar_beside_the_geometry(tmp_path, capsys):
    geometry = _saved_simulation(tmp_path / "30_WB.fsm", ["W", "B", "Blade1"])
    assert main(["inventory", str(geometry)]) == 0
    sidecar = tmp_path / "30_WB.boundaries.toml"
    assert sidecar.is_file()
    assert capsys.readouterr().out.strip() == str(sidecar)
    data = tomllib.loads(sidecar.read_text(encoding="utf-8"))
    assert data == {"file": "30_WB.fsm", "boundaries": ["W", "B", "Blade1"]}


def test_inventory_refuses_to_overwrite_without_the_flag(tmp_path, capsys):
    geometry = _saved_simulation(tmp_path / "30_WB.fsm", ["W", "B"])
    sidecar = tmp_path / "30_WB.boundaries.toml"
    sidecar.write_text('boundaries = ["edited"]\n', encoding="utf-8")
    assert main(["inventory", str(geometry)]) == 2
    err = capsys.readouterr().err
    assert "30_WB.boundaries.toml" in err and "--overwrite" in err
    assert sidecar.read_text(encoding="utf-8") == 'boundaries = ["edited"]\n', (
        "the refusal rewrote it"
    )
    assert main(["inventory", str(geometry), "--overwrite"]) == 0
    assert tomllib.loads(sidecar.read_text(encoding="utf-8"))["boundaries"] == ["W", "B"]


def test_a_file_without_a_mesh_block_is_refused_by_name(tmp_path, capsys):
    raw = tmp_path / "raw_blade.stl"
    raw.write_bytes(b"solid blade\n")
    assert main(["inventory", str(raw)]) == 2
    err = capsys.readouterr().err
    assert "raw_blade.stl" in err and "no mesh block" in err
    assert not (tmp_path / "raw_blade.boundaries.toml").exists()
    assert main(["inventory", str(tmp_path / "absent.fsm")]) == 2
    assert "absent.fsm" in capsys.readouterr().err


def test_a_missing_geometry_is_named_before_a_stale_sidecar(tmp_path, capsys):
    """The refusal names the cause that is the cause: a file that is not there."""
    stale = tmp_path / "renamed.boundaries.toml"
    stale.write_text('boundaries = ["W"]\n', encoding="utf-8")
    assert main(["inventory", str(tmp_path / "renamed.fsm")]) == 2
    err = capsys.readouterr().err
    assert "renamed.fsm" in err and "not a file" in err
    assert "--overwrite" not in err, "the stale sidecar was named as the cause"


_FR312_INVENTORY_CLEAN__TIER3 = (
    Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs" / "geometries"
)


_FR312_INVENTORY_CLEAN__MEASURED = ("7012026", "METER")


_FR312_INVENTORY_CLEAN__CLOCK = '"<install>" "actions/pfs_walltime_clock.py"'


def _fr312_inventory_clean___text(path: Path) -> str:
    return path.read_bytes().decode("latin-1")


def _fr312_inventory_clean___replace_block(text: str, name: str, lines: list[str]) -> str:
    eol = "\r\n" if "\r\n" in text else "\n"
    rows = text.split(eol)
    start = rows.index(f"${name}_START$")
    end = rows.index(f"${name}_END$")
    return eol.join([*rows[: start + 1], *lines, *rows[end:]])


def _fr312_inventory_clean___dirty(text: str) -> str:
    """A tier-3 fresh import as a run would leave it: settings changed, actions saved."""
    wake = list(block_lines(text)["WAKE"])
    wake[0] = " 2.50000000000000000E+00"
    solver = list(block_lines(text)["SOLVER"])
    assert solver[-1] == "0", "the fresh import ends its SOLVER block with no action"
    solver[0] = "3"
    solver[-1] = "1"
    solver += [
        "pfs_walltime_clock".ljust(70),
        _FR312_INVENTORY_CLEAN__CLOCK.ljust(70),
        f"{len(_FR312_INVENTORY_CLEAN__CLOCK)},1, F",
    ]
    stability = [" T" + block_lines(text)["STABILITY"][0][2:]]
    text = _fr312_inventory_clean___replace_block(text, "WAKE", wake)
    text = _fr312_inventory_clean___replace_block(text, "SOLVER", solver)
    return _fr312_inventory_clean___replace_block(text, "STABILITY", stability)


def _fr312_inventory_clean___unmeasured_build(text: str) -> str:
    """The block structure of a 26.124 save, from its block names and line counts only.

    Build 8172026 in the head and the global block, and one line more in
    CADCREATE and STABILITY than 26.120 writes; no value of any real save.
    """
    text = text.replace("\r\n7012026\r\n", "\r\n8172026\r\n", 2)
    blocks = block_lines(text)
    text = _fr312_inventory_clean___replace_block(text, "CADCREATE", [*blocks["CADCREATE"], "0"])
    return _fr312_inventory_clean___replace_block(text, "STABILITY", [*blocks["STABILITY"], " 0.0"])


class TestFr312InventoryClean:
    """FR-312: --clean reduces a geometry to its meshes and applied boundary conditions.

    The blocks reset, and the content each is reset to, come from a measurement
    this module repeats: the ten committed tier-3 geometries are fresh imports on
    26.120 (build 7012026) in metres, and the blocks they all hold with the same
    lines are the fresh import's. A tier-3 geometry is then dirtied in those
    blocks, with saved actions and settings a run would leave, and cleaned: the
    result must be the fresh import byte for byte, the meshes and boundary
    conditions untouched. A file of a build with no measured fresh import (the
    block structure of a 26.124 save, reproduced synthetically from its block
    names and line counts only) keeps every block but the saved actions, and says
    so. What the solver does with a cleaned file is owed by the licensed round.
    """

    @staticmethod
    def test_fr312_the_fresh_import_table_is_the_measurement_of_the_ten_tier3_geometries():
        requirement = "FR-312"
        files = sorted(_FR312_INVENTORY_CLEAN__TIER3.glob("*.fsm"))
        assert len(files) == 10, files
        texts = [_fr312_inventory_clean___text(path) for path in files]
        measured = common_blocks(texts)
        table = FRESH_IMPORT[_FR312_INVENTORY_CLEAN__MEASURED]
        assert {name: measured[name] for name in table} == dict(table), requirement
        # Every block the table leaves out is either kept by a stated reason or differs.
        assert set(measured) - set(table) <= set(KEPT_BLOCKS), requirement
        assert not set(table) & set(KEPT_BLOCKS)
        assert "MESH" in KEPT_BLOCKS and "PHYSICS" in KEPT_BLOCKS
        # The control: one planted difference takes the block out of the measurement.
        planted = [_fr312_inventory_clean___replace_block(texts[0], "WAKE", ["1"]), *texts[1:]]
        assert "WAKE" not in common_blocks(planted), requirement

    @staticmethod
    @pytest.mark.parametrize("geometry", ["10_WING.fsm", "30_BLADE.fsm", "41_TWIN.fsm"])
    def test_fr312_clean_resets_the_measured_blocks_to_the_fresh_import(geometry, tmp_path, capsys):
        requirement = "FR-312"
        fresh = _FR312_INVENTORY_CLEAN__TIER3 / geometry
        target = tmp_path / geometry
        target.write_bytes(
            _fr312_inventory_clean___dirty(_fr312_inventory_clean___text(fresh)).encode("latin-1")
        )
        dirty = target.read_bytes()
        # The control: the dirtied file is not the fresh import.
        assert dirty != fresh.read_bytes()
        assert main(["inventory", str(target), "--clean"]) == 0
        err = capsys.readouterr().err
        assert "removed saved action pfs_walltime_clock [COMMAND_LINE]" in err, err
        for name in ("WAKE", "SOLVER", "STABILITY"):
            assert f"reset block {name} to its fresh-import content" in err, (requirement, err)
        assert target.read_bytes() == fresh.read_bytes(), requirement
        assert boundary_names(target) == boundary_names(fresh)
        assert saved_solver_actions(target) == ()
        backups = list(tmp_path.glob(f"{geometry}.bak-*"))
        assert len(backups) == 1 and backups[0].read_bytes() == dirty

    @staticmethod
    def test_fr312_the_meshes_and_boundary_conditions_are_never_touched(tmp_path):
        requirement = "FR-312"
        fresh = _fr312_inventory_clean___text(_FR312_INVENTORY_CLEAN__TIER3 / "40_PUSHER.fsm")
        dirty = _fr312_inventory_clean___dirty(fresh)
        cleaned = reset_to_fresh_import(dirty, "METER", "40_PUSHER.fsm")
        before, after = block_lines(dirty), block_lines(cleaned.text)
        for name in KEPT_BLOCKS:
            assert after[name] == before[name], (requirement, name)
        assert cleaned.blocks == ("WAKE", "SOLVER", "STABILITY"), cleaned.blocks

    @staticmethod
    @pytest.mark.parametrize("block", sorted(FRESH_IMPORT[_FR312_INVENTORY_CLEAN__MEASURED]))
    def test_fr312_each_reset_block_dirtied_alone_is_put_back_byte_for_byte(block, tmp_path):
        """Every block of the table, one at a time: a value changed and a line added.

        The added line changes the block's length, so a reset that kept the old
        line count, skipped the block or wrote it under another name leaves the
        file different from the fresh import. The control is the dirtied file,
        which differs from the fresh import before the clean.
        """
        requirement = "FR-312"
        fresh = _FR312_INVENTORY_CLEAN__TIER3 / "10_WING.fsm"
        text = _fr312_inventory_clean___text(fresh)
        lines = list(block_lines(text)[block])
        # A line in the middle: the head of GLOBAL is the length unit, which the
        # reset keys on, and the tail of SOLVER is the action count of FR-308.
        middle = len(lines) // 2
        lines[middle] = lines[middle] + "9"
        lines.insert(middle + 1, " 1.00000000000000000E+00")
        target = tmp_path / "10_WING.fsm"
        target.write_bytes(
            _fr312_inventory_clean___replace_block(text, block, lines).encode("latin-1")
        )
        assert target.read_bytes() != fresh.read_bytes(), "the control: the block is dirtied"
        result = clean_saved_actions(target, stamp="20260930-000000")
        assert result.blocks_reset == (block,), (requirement, result.blocks_reset)
        assert result.actions == () and result.note is None
        assert target.read_bytes() == fresh.read_bytes(), (requirement, block)
        assert boundary_names(target) == boundary_names(fresh)

    @staticmethod
    def test_fr312_a_clean_file_is_not_rewritten(tmp_path, capsys):
        requirement = "FR-312"
        target = tmp_path / "20_BODY.fsm"
        shutil.copyfile(_FR312_INVENTORY_CLEAN__TIER3 / "20_BODY.fsm", target)
        before = target.read_bytes()
        result = clean_saved_actions(target, stamp="20260930-000000")
        assert (result.backup, result.blocks_reset, result.actions) == (None, (), ()), requirement
        assert target.read_bytes() == before
        assert not list(tmp_path.glob("*.bak-*"))

    @staticmethod
    def test_fr312_a_build_with_no_measured_fresh_import_keeps_every_block(tmp_path, capsys):
        requirement = "FR-312"
        target = tmp_path / "unmeasured.fsm"
        target.write_bytes(
            _fr312_inventory_clean___unmeasured_build(
                _fr312_inventory_clean___dirty(
                    _fr312_inventory_clean___text(_FR312_INVENTORY_CLEAN__TIER3 / "10_WING.fsm")
                )
            ).encode("latin-1")
        )
        before = block_lines(_fr312_inventory_clean___text(target))
        assert main(["inventory", str(target), "--clean"]) == 0
        err = capsys.readouterr().err
        assert "no fresh import of build 8172026" in err, (requirement, err)
        assert "reset block" not in err
        after = block_lines(_fr312_inventory_clean___text(target))
        assert saved_solver_actions(target) == (), "the saved actions still go (FR-308)"
        for name, lines in before.items():
            if name != "SOLVER":
                assert after[name] == lines, (requirement, name)
        assert after["SOLVER"] == before["SOLVER"][:-3][:-1] + ("0",)

    @staticmethod
    def test_fr312_a_measured_build_missing_a_block_is_refused_writing_nothing(tmp_path):
        requirement = "FR-312"
        text = _fr312_inventory_clean___dirty(
            _fr312_inventory_clean___text(_FR312_INVENTORY_CLEAN__TIER3 / "10_WING.fsm")
        )
        eol = "\r\n"
        rows = text.split(eol)
        start, end = rows.index("$WAKE_START$"), rows.index("$WAKE_END$")
        target = tmp_path / "nowake.fsm"
        target.write_bytes(eol.join(rows[:start] + rows[end + 1 :]).encode("latin-1"))
        before = target.read_bytes()
        with pytest.raises(InputArtifactError, match="WAKE"):
            clean_saved_actions(target, stamp="20260930-000000")
        assert target.read_bytes() == before, requirement
        assert not list(tmp_path.glob("*.bak-*"))

    @staticmethod
    def test_fr312_a_clean_that_changes_a_mesh_line_is_put_back_and_refused(tmp_path, monkeypatch):
        # Verifies FR-312.
        import os

        from tests.tier1_offline.test_fsm_saved_actions import ACTIONS, _saved_simulation

        geometry = _saved_simulation(tmp_path / "01_ROTOR.fsm", ACTIONS)
        original = geometry.read_bytes()
        real = os.replace

        def replacing_then_corrupting(source, target):
            real(source, target)
            target = Path(target)
            target.write_bytes(target.read_bytes().replace(b".500,.500,.500", b".600,.500,.500", 1))

        monkeypatch.setattr(os, "replace", replacing_then_corrupting)
        with pytest.raises(InputArtifactError, match="put back"):
            clean_saved_actions(geometry, stamp="20261001-000000")
        monkeypatch.undo()
        assert geometry.read_bytes() == original
