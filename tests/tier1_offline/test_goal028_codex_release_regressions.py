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
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)
    path = tmp_path / "sim_1001" / "raw" / "POLAR-1001_M10AL+000BE+000_cp.txt"
    path.parent.mkdir(parents=True)
    path.write_text(
        "Angle of attack (Deg) 0\nSide-slip angle (Deg) 0\nX, Y, Z, Cp\n0, 0, 0, -1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script_module, "SIMS", tmp_path)
    assert script_module.rows() == [], "a surface-section export is not a loads export"


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
    from pyflightstream.post._rotor_plan import _plot_name_can_emit

    def emits(template: str, name: str) -> bool:
        return _plot_name_can_emit(template, name, (), inventory=(), is_blade=lambda _f: False)

    assert emits("ROTOR_PROP", "ROTOR_PROP_ORIGINAL")
    assert emits("ROTOR_{family}", "ROTOR_PROP_ORIGINAL")
    assert not emits("ROTOR_PROP", "ROTOR_PROPELLER")


def test_a_format_spec_in_the_family_field_is_still_a_wildcard():
    """The builder applies `str.format`, so `MRP_{family}{family:.0}` over TOTAL emits
    MRP_TOTAL (`:.0` prints nothing): every replacement field may put any text, or none."""
    from pyflightstream.post._rotor_plan import _plot_name_can_emit

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
    from pyflightstream.post._rotor_plan import _plot_name_can_emit

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


def test_names_equal_but_for_case_are_taken_as_able_to_collide():
    """Whether the solver keeps a plot name's case is not measured: conservative."""
    from pyflightstream.post._rotor_plan import _plot_name_can_emit

    def emits(template: str, name: str) -> bool:
        return _plot_name_can_emit(template, name, (), inventory=(), is_blade=lambda _f: False)

    assert emits("mrp_{family}", "MRP_TOTAL")
    assert emits("Rotor_Prop", "ROTOR_PROP")


def _span_ctx(variables, reductions, *, rotors=("R",), window=(1, 100)):
    record = SimpleNamespace(reductions=reductions)
    return SimpleNamespace(
        windows={"p": window},
        window=window,
        by_run={"run": record},
        sources={"p": ["run"]},
        matrix_row=SimpleNamespace(variables=variables),
        rotors={name: object() for name in rotors},
    )


def test_f130_a_row_with_no_window_key_keeps_the_row_window_for_every_rotor():
    """F-130: the recorded prose of the time average does not replan the rotor's window."""
    from pyflightstream.post._rotor_plan import _rotor_windows

    reductions = {
        "time_average": {"window_from": "LAST_REVS_AVG = 1 revolution of the clock rotor"},
        "rotors": {"R": {"steps_per_revolution": 10}},
    }
    assert _rotor_windows(_span_ctx({}, reductions), "R") == {"p": (1, 100)}


def test_f131_a_rotor_with_no_clock_keeps_the_row_window():
    """F-131: a count of turns with no clock of this rotor averages over the row's window."""
    from pyflightstream.post._rotor_plan import _rotor_windows

    reductions = {"rotors": {"R": {"steps_per_revolution": 10}, "S": {}}}
    ctx = _span_ctx({"LAST_REVS_AVG": "2"}, reductions, rotors=("R", "S"))
    assert _rotor_windows(ctx, "S") == {"p": (1, 100)}
    assert _rotor_windows(ctx, "R") == {"p": (81, 100)}


def test_f489_a_mixed_source_rotor_table_names_every_history_group(tmp_path):
    """F-489: the second point's group does not erase the first point's from the manifest."""
    from pyflightstream.post import _rotor_plan as module
    from pyflightstream.post.products import ReferenceValues

    parts = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    groups = {"A": "HUB_ONE", "B": "HUB_TWO", "C": "HUB_ONE"}
    plots, by_run, sources = {}, {}, {}
    for name, group in groups.items():
        table = tmp_path / f"{name}_plots.csv"
        lines = ["POL,Time-step," + ",".join(f"{part}_{group}" for part in parts)]
        lines += [f"1,{step}," + ",".join("1.0" for _ in parts) for step in (1, 2)]
        table.write_text("\n".join(lines) + "\n", encoding="utf-8")
        plots[name] = table
        sources[name] = [f"run/{name}"]
        by_run[f"run/{name}"] = SimpleNamespace(
            reductions={
                "plot_groups": [
                    {
                        "name": group,
                        "families": ["Blade1"],
                        "frame": "MRP",
                        "parameters": list(parts),
                    }
                ]
            }
        )
    ctx = SimpleNamespace(
        sources_read={},
        windows={name: (1, 2) for name in groups},
        window=(1, 2),
        reference=ReferenceValues(sref_m2=1.0, cref_m=1.0, bref_m=1.0),
        aliases={},
        pproc=SimpleNamespace(plots=SimpleNamespace(parameters=list(parts), groups=[])),
        plots=plots,
        sources=sources,
        by_run=by_run,
        matrix_row=SimpleNamespace(variables={}),
        frozen={},
        sim_id="1",
        rotors={"HUB": object()},
    )
    rotor = SimpleNamespace(families_blades=["Blade1"])
    for name in groups:
        point = SimpleNamespace(name=name, loads=SimpleNamespace(surfaces={"Blade1": {}}))
        left_out: list[tuple[str, str]] = []
        selected = module._rotor_row_surfaces(
            ctx,
            point,
            "HUB",
            rotor,
            density=1.2,
            speed=10.0,
            quasi=None,
            run_id=f"run/{name}",
            left_out=left_out,
        )
        assert selected is not None and not left_out, left_out
    assert ctx.sources_read == {"HUB": "HUB_ONE, HUB_TWO"}


def test_f1372_the_recorded_rpm_lookup_folds_case_like_the_clock_lookup(tmp_path):
    """F-1372: a block recorded as ``Pusher`` serves the alias ``PUSHER``."""
    from pyflightstream.post.products import read_csv_table
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    def thrust_coefficient(root: Path, key: str) -> str:
        workspace = _workspace(root)
        (workspace.inputs_dir / "references" / "r002.toml").write_text(
            "\n".join(
                [
                    "area_m2 = 50.0",
                    "chord_m = 2.526",
                    "span_m = 20.0",
                    "",
                    "[rotors.PUSHER]",
                    'alias = "PUSHER"',
                    "x_m = 0.0",
                    "y_m = 0.0",
                    "z_m = 0.0",
                    'axis = "X"',
                    "rpm_sign = 1",
                    "diameter_m = 1.2",
                    'families_blades = ["B"]',
                    'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        if key != "PUSHER":
            records = workspace.read_manifest()
            (workspace.root / "runs.json").unlink()
            for record in records:
                plan = record.reductions
                if record.sim_id == "6002" and isinstance(plan, dict):
                    rotors = {key: plan["rotors"]["PUSHER"]}
                    record = record.model_copy(update={"reductions": {**plan, "rotors": rotors}})
                workspace.append_record(record)
        written = _post(workspace)
        (table,) = [Path(p) for p in written if str(p).endswith("_rotor.csv")]
        return read_csv_table(table)[1][0]["CT_PUSHER"]

    exact = thrust_coefficient(tmp_path / "exact", "PUSHER")
    folded = thrust_coefficient(tmp_path / "folded", "Pusher")
    assert exact != "NA" and float(exact) != 0.0
    assert folded == exact
