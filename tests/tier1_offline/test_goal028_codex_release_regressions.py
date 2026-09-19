"""Release regressions for expanded plot names and non-loads exports."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from pyflightstream.cases import ForcePlotGroup
from pyflightstream.post.products import global_frame_plot_groups, rotor_plot_source


def test_all_families_can_shadow_the_automatic_rotor_name():
    pproc = SimpleNamespace(
        plots=SimpleNamespace(
            parameters=["FX", "FY", "FZ", "MX", "MY", "MZ"],
            groups=[ForcePlotGroup(name="ROTOR_{family}", frame="SMRP", families="all")],
        )
    )
    candidates, _ = rotor_plot_source(
        pproc, "PROP", rotor_families=["PROP"], inventory=["Wing", "PROP"]
    )
    assert "ROTOR_PROP" not in candidates, (
        "families='all' emits ROTOR_PROP in SMRP; it cannot supply global rotor loads"
    )


def test_each_family_can_shadow_the_automatic_total_name():
    pproc = SimpleNamespace(
        plots=SimpleNamespace(
            parameters=["FX", "FY", "FZ", "MX", "MY", "MZ"],
            groups=[ForcePlotGroup(name="MRP_{family}", frame="CUSTOM", families="each")],
        )
    )
    candidates = global_frame_plot_groups(pproc, inventory=["Wing", "TOTAL"])
    assert "MRP_TOTAL" not in candidates, (
        "families='each' emits MRP_TOTAL in CUSTOM; it cannot supply global axes"
    )


def test_surface_section_export_with_angles_is_skipped(tmp_path, monkeypatch):
    script = Path(__file__).parents[2] / "scripts" / "extract_recorded_total_rows.py"
    spec = importlib.util.spec_from_file_location("extract_recorded_total_rows", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "sim_1001" / "raw" / "POLAR-1001_M10AL+000BE+000_cp.txt"
    path.parent.mkdir(parents=True)
    path.write_text(
        "Angle of attack (Deg) 0\nSide-slip angle (Deg) 0\nX, Y, Z, Cp\n0, 0, 0, -1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "SIMS", tmp_path)
    assert module.rows() == [], "a surface-section export is not a loads export"


# --- AN AMBIGUOUS NAME IS NEVER READ AS GLOBAL (the third review before the tag) ------


def test_a_declared_global_name_another_group_could_emit_is_not_a_source():
    """`MRP_TOTAL` declared in MRP over an absent family, and `MRP_{family}` in a custom
    frame over `TOTAL`: only the custom history is emitted under that name, so the name is
    ambiguous and the axes are never computed from it."""
    pproc = SimpleNamespace(
        plots=SimpleNamespace(
            parameters=["FX", "FY", "FZ", "MX", "MY", "MZ"],
            groups=[
                ForcePlotGroup(name="MRP_TOTAL", frame="MRP", families=["Absent"]),
                ForcePlotGroup(name="MRP_{family}", frame="CUSTOM", families="each"),
            ],
        )
    )
    candidates = global_frame_plot_groups(pproc, inventory=["Wing", "TOTAL"])
    assert "MRP_TOTAL" not in candidates, candidates


def test_the_original_frame_suffix_can_occupy_the_automatic_rotor_name():
    """The builder appends `_ORIGINAL` to a group plotted in a retained original frame, so a
    declaration named `ROTOR_PROP` also emits `ROTOR_PROP_ORIGINAL`, the automatic name of a
    rotor aliased `PROP_ORIGINAL`: the matcher must count that emission."""
    from pyflightstream.post.products import _plot_name_can_emit

    def emits(template: str, name: str) -> bool:
        return _plot_name_can_emit(template, name, (), inventory=(), is_blade=lambda _f: False)

    assert emits("ROTOR_PROP", "ROTOR_PROP_ORIGINAL")
    assert emits("ROTOR_{family}", "ROTOR_PROP_ORIGINAL")
    assert not emits("ROTOR_PROP", "ROTOR_PROPELLER")
