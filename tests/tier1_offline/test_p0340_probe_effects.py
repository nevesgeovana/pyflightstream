"""Tier 1: the effect assertions of the 0.34.0 probe entries judge what they read (FR-333, FR-342).

Marker P0340-QA-PROMOTE. The licensed run is the session's; these tests hand each assertion the
files a probe would leave and check the three answers it can give: verified when the effect is in
the file, broken only where the instrument alone could have produced the reading, and unprobed
when the reading is silent (a probe may never guess).
"""

from __future__ import annotations

from pyflightstream._fsm import MESH_MARKER
from pyflightstream.qa import specs
from tests.tier1_offline._p0340_probe_support import artifacts_in

HEADER = "Columns: Observer time (sec), PL (Pa), PT (Pa), PO (Pa)\n"


def _signals(blocks: dict[str, list[tuple[float, float]]]) -> str:
    text = ""
    for name, rows in blocks.items():
        text += f"Observer: {name}\nPosition: 0,1,0\n{HEADER}"
        text += "".join(f"  {t:.6E}  {p:.6E}  0.0  {p:.6E}\n" for t, p in rows)
    return text


def _write(workdir, text: str) -> None:
    (workdir / "signals.txt").write_text(text, encoding="utf-8")


def _effect(command: str, workdir):
    return specs.PROBE_SPECS[command].assert_effect(artifacts_in(workdir))


def test_the_sources_are_verified_only_by_a_nonzero_pressure_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: silence and zeros record unprobed, never broken."""
    assert _effect("ACOUSTIC_SOURCES", tmp_path) is None
    _write(tmp_path, _signals({"PYFS_OBS1": [(0.05, 0.0), (0.06, 0.0)]}))
    assert _effect("ACOUSTIC_SOURCES", tmp_path) is None
    _write(tmp_path, _signals({"PYFS_OBS1": [(0.05, 0.0), (0.06, 0.25)]}))
    assert _effect("ACOUSTIC_SOURCES", tmp_path) is True


def test_the_observer_is_judged_by_its_name_in_the_signals_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: a file with blocks and no such name is broken."""
    _write(tmp_path, _signals({"PYFS_OBS1": [(0.05, 1.0)]}))
    assert _effect("CREATE_NEW_ACOUSTIC_OBSERVER", tmp_path) is True
    _write(tmp_path, _signals({"Observer 2": [(0.05, 1.0)]}))
    assert _effect("CREATE_NEW_ACOUSTIC_OBSERVER", tmp_path) is False


def test_the_observer_import_counts_the_blocks_named_by_index_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: two imported observers read back as Observer N."""
    rows = [(0.05, 1.0)]
    _write(tmp_path, _signals({"PYFS_OBS1": rows, "Observer 2": rows, "Observer 3": rows}))
    assert _effect("ACOUSTIC_OBSERVERS_IMPORT", tmp_path) is True
    _write(tmp_path, _signals({"PYFS_OBS1": rows}))
    assert _effect("ACOUSTIC_OBSERVERS_IMPORT", tmp_path) is False


def test_the_observer_time_needs_sixteen_rows_from_the_start_time_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: the requested window is read from the rows."""
    good = [(0.05 + 0.01 * i, 1.0) for i in range(16)]
    _write(tmp_path, _signals({"PYFS_OBS1": good}))
    assert _effect("SET_ACOUSTIC_OBSERVER_TIME", tmp_path) is True
    _write(tmp_path, _signals({"PYFS_OBS1": good[:8]}))
    assert _effect("SET_ACOUSTIC_OBSERVER_TIME", tmp_path) is False


def test_the_observer_deletions_read_who_is_left_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: one of two left is verified, both left is broken."""
    rows = [(0.05, 1.0)]
    _write(tmp_path, _signals({"PYFS_OBS2": rows}))
    assert _effect("DELETE_ACOUSTIC_OBSERVER", tmp_path) is True
    _write(tmp_path, _signals({"PYFS_OBS1": rows, "PYFS_OBS2": rows}))
    assert _effect("DELETE_ACOUSTIC_OBSERVER", tmp_path) is False
    _write(tmp_path, "")
    assert _effect("DELETE_ALL_ACOUSTIC_OBSERVERS", tmp_path) is True
    _write(tmp_path, _signals({"PYFS_OBS1": rows}))
    assert _effect("DELETE_ALL_ACOUSTIC_OBSERVERS", tmp_path) is False


def test_a_loft_is_judged_by_its_name_in_the_saved_simulation_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: the lofts are strict, their preparation is lax."""
    assert _effect("CAD_CREATE_WING_MESH_FROM_CCS", tmp_path) is None
    (tmp_path / "saved.fsm").write_bytes(b"... PYFS_WING ...")
    assert _effect("CAD_CREATE_WING_MESH_FROM_CCS", tmp_path) is True
    assert _effect("CAD_CREATE_FUSELAGE_MESH_FROM_CCS", tmp_path) is False
    assert _effect("CAD_CREATE_CURVE_SELECT", tmp_path) is True
    (tmp_path / "saved.fsm").write_bytes(b"nothing here")
    assert _effect("CAD_CREATE_CURVE_SELECT", tmp_path) is None


def test_a_setting_is_verified_only_by_a_different_mesh_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: equal or missing lofts record unprobed."""
    obj = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    (tmp_path / "reference.obj").write_text(obj, encoding="utf-8")
    assert _effect("CCS_WING_MESH_SUBDIVISIONS", tmp_path) is None
    (tmp_path / "variant.obj").write_text(obj, encoding="utf-8")
    assert _effect("CCS_WING_MESH_SUBDIVISIONS", tmp_path) is None
    (tmp_path / "variant.obj").write_text(obj + "v 1 1 0\nf 2 4 3\n", encoding="utf-8")
    assert _effect("CCS_WING_MESH_SUBDIVISIONS", tmp_path) is True


def test_an_undoing_command_needs_the_restored_loft_to_equal_the_first_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: set, undo, and the first mesh comes back."""
    first = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    changed = first + "v 1 1 0\nf 2 4 3\n"
    for name, text in (("reference", first), ("variant", changed), ("restored", first)):
        (tmp_path / f"{name}.obj").write_text(text, encoding="utf-8")
    assert _effect("DELETE_CCS_WING_REFINEMENT_ZONES", tmp_path) is True
    (tmp_path / "restored.obj").write_text(changed, encoding="utf-8")
    assert _effect("DELETE_CCS_WING_REFINEMENT_ZONES", tmp_path) is None


def _saved(workdir, filename: str, names) -> None:
    body = [MESH_MARKER, "9999", "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$"]
    text = "\r\n".join(body) + "\r\n"
    (workdir / filename).write_text(text, encoding="utf-8", newline="")


def test_the_surface_removal_reads_the_inventories_before_and_after_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: one boundary gone, the rest renumbered, is verified."""
    before = ("Body", "Base", "Blade1", "Blade2")
    _saved(tmp_path, "state_before.fsm", before)
    _saved(tmp_path, "state_after.fsm", before[1:])
    assert _effect("DELETE_SURFACES", tmp_path) is True
    _saved(tmp_path, "state_after.fsm", before)
    assert _effect("DELETE_SURFACES", tmp_path) is False
    (tmp_path / "state_after.fsm").write_text("not a simulation", encoding="utf-8")
    assert _effect("DELETE_SURFACES", tmp_path) is None


def test_the_section_export_is_verified_by_a_file_the_solver_added_fr_333(tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: instrument files and the build listing do not count."""
    (tmp_path / "listing_at_build.txt").write_text("keep.txt", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
    (tmp_path / "log_after.txt").write_text("x", encoding="utf-8")
    assert _effect("EXPORT_SURFACE_SECTIONS", tmp_path) is None
    (tmp_path / "section_1.txt").write_text("x", encoding="utf-8")
    assert _effect("EXPORT_SURFACE_SECTIONS", tmp_path) is True
