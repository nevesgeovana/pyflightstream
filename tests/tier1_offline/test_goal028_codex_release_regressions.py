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


def test_a_format_spec_in_the_family_field_is_still_a_wildcard():
    """The builder applies `str.format`, so `MRP_{family}{family:.0}` over TOTAL emits
    MRP_TOTAL (`:.0` prints nothing): every replacement field may put any text, or none."""
    from pyflightstream.post.products import _plot_name_can_emit

    def emits(template: str, name: str) -> bool:
        return _plot_name_can_emit(template, name, (), inventory=(), is_blade=lambda _f: False)

    assert emits("MRP_{family}{family:.0}", "MRP_TOTAL")
    assert emits("ROTOR_{family}{family:.0}", "ROTOR_PROP")
    assert emits("ROTOR_{family:.0}PROP", "ROTOR_PROP")
    assert not emits("HUB_{family}", "ROTOR_PROP")


def test_a_plot_name_with_a_format_spec_or_conversion_is_refused_when_read():
    """The pproc refuses any replacement field but a bare {family}: the builder formats
    names with str.format, and a spec or conversion can make a name print anything."""
    import pytest

    for name in ("MRP_{family}{family:.0}", "MRP_{family}{family:.{family:.0}0}", "R_{family!r}"):
        # Refused; which of the name validators speaks first is not the property.
        with pytest.raises(ValueError, match=r"plot group .*\{family"):
            ForcePlotGroup(name=name, frame="LOCAL_AXIS", families="all")
    assert ForcePlotGroup(name="LOCAL_{family}", frame="LOCAL_AXIS", families="all")


def test_a_nested_format_spec_is_still_one_wildcard_in_the_matcher():
    from pyflightstream.post.products import _plot_name_can_emit

    def emits(template: str, name: str) -> bool:
        return _plot_name_can_emit(template, name, (), inventory=(), is_blade=lambda _f: False)

    assert emits("MRP_{family}{family:.{family:.0}0}", "MRP_TOTAL")
    assert emits("ROTOR_{family}{family:.{family:.0}0}", "ROTOR_PROP")


def test_a_plot_name_outside_the_closed_alphabet_is_refused_when_read():
    """The export reader strips whitespace from column names, so a name with a trailing
    space emitted a history the post stage matched to another group."""
    import pytest

    for name in ("MRP_{family} ", "MRP_TOTAL ", " HUB", "HUB-A", "HUB.A"):
        with pytest.raises(ValueError, match="plot group"):
            ForcePlotGroup(name=name, frame="MRP", families="all")
    assert ForcePlotGroup(name="HUB_PUSHER2", frame="MRP", families="all")
