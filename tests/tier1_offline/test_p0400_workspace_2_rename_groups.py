"""P0400-RENAMEGROUPS: the group-rename migration skips only the workspace's own archive/."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pyflightstream.workspace.rename_groups import rename_group_products, unmapped_group_numbers


def test_p0400_renamegroups_a_root_under_a_folder_named_archive_is_migrated(tmp_path):
    """P0400-RENAMEGROUPS (PFS-2094.024): a workspace at .../archive/campaign2025 has its
    products renamed and reported; only archive/ INSIDE the root is skipped."""
    root = tmp_path / "archive" / "campaign2025"
    (root / "post" / "m").mkdir(parents=True)
    (root / "archive").mkdir()
    (root / "post" / "m" / "loads_g1.csv").write_text("x\n", encoding="utf-8")
    (root / "post" / "m" / "loads_g2.csv").write_text("x\n", encoding="utf-8")
    (root / "archive" / "old_g1.csv").write_text("x\n", encoding="utf-8")
    assert list(unmapped_group_numbers(root, {1: "WING"})) == [2]
    moved = rename_group_products(root, {1: "WING"}, archive=False)
    assert [entry.after.name for entry in moved] == ["loads_WING.csv"]
    assert (root / "archive" / "old_g1.csv").is_file()


def test_p0400_renamegroups_the_archive_stamp_is_local_time(tmp_path, monkeypatch):
    """P0400-RENAMEGROUPS (PFS-2087.003): the archive folder is stamped on the local clock, as
    every other ARCHIVE_STAMP writer stamps. A fixed non-UTC clock makes the test
    discriminate between local and UTC even on a UTC CI host."""
    from pyflightstream.workspace import rename_groups

    local = datetime(2026, 10, 13, 21, 30, 45, tzinfo=timezone(timedelta(hours=-3)))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return local.replace(tzinfo=None) if tz is None else local.astimezone(tz)

    monkeypatch.setattr(rename_groups, "datetime", Clock)
    # A product lives under post/ (PFS-2096.012: nothing else is renamed).
    (tmp_path / "post" / "m").mkdir(parents=True)
    (tmp_path / "post" / "m" / "loads_g1.csv").write_text("x\n", encoding="utf-8")
    (moved,) = rename_group_products(tmp_path, {1: "WING"})
    assert moved.archived is not None
    folder = next(p.name for p in moved.archived.parents if p.name.startswith("rename-groups-"))
    assert folder == "rename-groups-20261013-213045"
