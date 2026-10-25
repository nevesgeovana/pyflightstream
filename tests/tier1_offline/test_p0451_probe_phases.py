"""P0451: build a C last-step plane beside a D averaging-window lattice.

The public builder must import each set in the latest required phase, with
one CSV per phase. No solver is invoked.
"""

import time
import warnings
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.workflows import normal_probe_creation, row_outputs
from tests.tier1_offline import test_regression_farfield_products as products
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___script,
    _p0450_rotor_case,
)


def _plane(export_type="last_step", **extra):
    return dict(variant="plane", export_type=export_type, spacing_bref=0.25, **extra)


def _power():
    return dict(
        variant="power",
        rotor="ROTOR",
        stations=[-10, 1, 2],
        station=1,
        export_type="avg_window",
        last_steps=2,
        n_r=3,
        n_psi=16,
    )


def _case(tmp_path, entries, probes=(), run_type="unsteady_rotor"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    case = _p0450_rotor_case(tmp_path, [], run_type)
    spec = PprocSpec.model_validate(dict(farfields=entries, probes=list(probes)))
    case = case.model_copy(update={"pproc": spec})
    return case.model_copy(update={"outputs": row_outputs(case, run_type)})


def _build(case):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _farfield_plan___script(case)


def _imports(script):
    lines = script.render().splitlines()
    return [
        (i, lines[i + 3], int(script.pending_input_files[lines[i + 3]].splitlines()[0]))
        for i, line in enumerate(lines)
        if line == "PROBE_POINTS_IMPORT"
    ]


@pytest.mark.parametrize("run_type", ["unsteady_rotor", "unsteady"])
def test_p0451_split_imports_exclude_last_step_plane_from_window(tmp_path, run_type):
    case = _case(tmp_path, [_plane(), _power()], run_type=run_type)
    script = _build(case)
    imports = _imports(script)
    march = script.render().splitlines().index("START_SOLVER")
    assert len(imports) == 1
    assert imports[0][0] > march
    assert imports[0][2] == 35
    action = normal_probe_creation(case, "26.124").splitlines()
    assert action.count("PROBE_POINTS_IMPORT") == 1
    path = action[action.index("PROBE_POINTS_IMPORT") + 3]
    assert int(script.pending_input_files[path].splitlines()[0]) == 192
    assert "DELETE_PROBE_POINTS" not in script.render().splitlines()[march + 1 :]
    records = script.farfield_layout[-1]["shapes"]
    assert [record["exports"] for record in records] == [["final"], ["window", "final"]]


def test_p0451_last_step_only_has_no_window_creation(tmp_path):
    case = _case(tmp_path, [_plane()])
    script = _build(case)
    imports = _imports(script)
    assert len(imports) == 1 and imports[0][2] == 35
    assert imports[0][0] > script.render().splitlines().index("START_SOLVER")
    assert normal_probe_creation(case, "26.124") == ""


def test_p0451_shared_plane_imported_once_at_window_start(tmp_path):
    case = _case(
        tmp_path, [_plane(name="final"), _plane("avg_window", name="window", last_steps=2)]
    )
    script = _build(case)
    imports = _imports(script)
    assert not imports
    action = normal_probe_creation(case, "26.124").splitlines()
    assert action.count("PROBE_POINTS_IMPORT") == 1
    path = action[action.index("PROBE_POINTS_IMPORT") + 3]
    assert int(script.pending_input_files[path].splitlines()[0]) == 35


def _entry(kind):
    return dict(
        kind=kind,
        frame="REFERENCE",
        parameters=["VX"],
        points=3,
        lines=[dict(start=[3, 0, 0], end=[4, 0, 0])],
    )


def test_p0451_mixed_row_loads_and_places_each_kind_in_its_phase(tmp_path):
    try:
        case = _case(tmp_path, [], [_entry("instantaneous"), _entry("default")])
    except CampaignConfigError as error:
        pytest.fail(f"mixed probe kinds must load: {error}")
    script = _build(case)
    lines = script.render().splitlines()
    march = lines.index("START_SOLVER")
    assert lines.index("UNSTEADY_SOLVER_NEW_FLUID_PLOT") < march
    imports = _imports(script)
    assert len(imports) == 1 and imports[0][2] == 3 and imports[0][0] > march
    assert "{name}_plots.txt" in case.outputs and "{name}_probes.txt" in case.outputs


@pytest.mark.parametrize("run_type", ["steady", "qsteady_rotor"])
def test_p0451_steady_declared_lines_keep_their_commands(tmp_path, run_type):
    script = _build(_case(tmp_path, [], [_entry("default"), _entry("default")], run_type))
    imports = _imports(script)
    assert not imports
    lines = script.render().splitlines()
    commands = [i for i, line in enumerate(lines) if line.startswith("NEW_PROBE_LINE ")]
    assert len(commands) == 2
    assert commands[0] > lines.index("START_SOLVER")


def test_p0451_split_exports_post_c_final_and_d_window(tmp_path):
    plane = products._RFIXF_LAYOUT___LAID.points
    lattice = products._FFPROOF_POST___POINTS_M
    table = (
        products._RFIXF_LAYOUT___TABLE_1M
        + "\n"
        + products._FFPROOF_POST___LEDGERS.replace(
            "[[farfields]]", '[[farfields]]\nexport_type = "avg_window"'
        )
    )
    files = products._p0450_probe_series(lattice)
    final = f"{products._FFPROOF_POST___STEM}_farfield_survey.txt"
    files[final] = products._ffproof_post___probe_export(np.vstack([lattice, plane]), 18.0)
    workspace = products._ffproof_post___campaign(
        tmp_path,
        pproc=table,
        files=files,
        recipe="unsteady_rotor",
        reductions=products._FFPROOF_POST___WINDOW,
    )
    plane_record = dict(
        products._RFIXF_LAYOUT___PLANE_RECORD["shapes"][0],
        farfield_entry="plane",
        exports=["final"],
        import_phase="after-march",
        offset=0,
        final_offset=len(lattice),
    )
    lattice_record = dict(
        kind="lattice",
        source="added",
        entry=None,
        count=len(lattice),
        farfield_entry="power",
        axis="X",
        origin_m=[0, 0, 0],
        positions_frame="REFERENCE",
        exports=["window", "final"],
        import_phase="window-start",
        offset=0,
        final_offset=0,
        lattice=products._FFPROOF_POST___SHAPE.build(1.0).model_dump(mode="json"),
    )
    products._ffproof_post___set_record(
        workspace, farfield_layout={"shapes": [plane_record, lattice_record]}
    )
    products._ffproof_post___post(workspace)
    root = Path(workspace.root)
    instant = products._rfixf_layout___rows(root, "farfield/*_trefftz_instant.csv")
    average = products._rfixf_layout___rows(root, "farfield/*_trefftz_average.csv")
    assert {(row["VARIANT"], row["STEP"]) for row in instant} == {("C", "8"), ("D", "8")}
    assert {(row["VARIANT"], row["STEP"]) for row in average} == {("D", "AVERAGE")}
    assert all(row["P_AXIAL_W"] != "NA" for row in average)


def test_p0451_mixed_post_writes_last_step_and_history_tables(tmp_path, monkeypatch):
    from pyflightstream.post.products import read_csv_table, write_campaign_products
    from tests.tier1_offline.test_p0370_s5_probe_kind import _normal_workspace
    from tests.tier1_offline.test_post_products import PLOTS_HEADER

    workspace = _normal_workspace(tmp_path, monkeypatch)
    pproc = workspace.inputs_dir / "pproc" / "p001.toml"
    pproc.write_text(
        pproc.read_text(encoding="utf-8")
        + '\n[[probes]]\nkind = "instantaneous"\nframe = "MRP"\nparameters = ["VX"]\n'
        "points = 3\nlines = [{start = [0, 0, 0], end = [1, 0, 0]}]\n",
        encoding="utf-8",
    )
    path = workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt"
    path.write_text(
        PLOTS_HEADER
        + "Time-step,VX1,VX2,VX3\n1,11,12,13,\n2,21,22,23,\n"
        + "-" * 60
        + "\n     Force Units: Coefficients\n"
        "Software : Flightstream version 26.1, build #7012026\n",
        encoding="utf-8",
    )
    write_campaign_products(workspace)
    root = workspace.root / "post/products/probes"
    assert (root / "AL-020_probes.csv").is_file()
    assert (root / "AL-020_probes_history.csv").is_file()
    _, final = read_csv_table(root / "AL-020_probes.csv")
    _, history = read_csv_table(root / "AL-020_probes_history.csv")
    assert {row["STEP"] for row in final} == {"96"}
    assert [float(row["vx"]) for row in final] == [31, 32, 33]
    assert len(history) == 6 and {row["STEP"] for row in history} == {"1", "2"}


@pytest.mark.parametrize("kind", ["default", "instantaneous"], ids=lambda k: f"P0451-{k}")
def test_p0451_new_kind_values_load(kind):
    try:
        spec = PprocSpec.model_validate(dict(probes=[_entry(kind)]))
    except ValidationError as error:
        pytest.fail(f"the public probe kind {kind!r} must load: {error}")
    assert spec.probes[0].kind == kind


def test_p0451_absent_kind_samples_only_after_march(tmp_path):
    entry = _entry("default")
    del entry["kind"]
    script = _build(_case(tmp_path, [], [entry]))
    lines = script.render().splitlines()
    assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" not in lines
    imports = _imports(script)
    assert len(imports) == 1 and imports[0][0] > lines.index("START_SOLVER")


@pytest.mark.parametrize(
    "alias,canonical",
    [("normal", "default"), ("unsteady", "instantaneous")],
    ids=["P0451-normal-alias", "P0451-unsteady-alias"],
)
def test_p0451_alias_warns_once_and_normalizes(alias, canonical):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec = PprocSpec.model_validate(dict(probes=[_entry(alias)]))
    notices = [item for item in caught if issubclass(item.category, PyflightstreamWarning)]
    assert len(notices) == 1
    assert canonical in str(notices[0].message)
    assert spec.probes[0].kind == canonical


def test_p0451_unknown_kind_names_the_two_values_and_aliases():
    with pytest.raises(ValidationError) as caught:
        PprocSpec.model_validate(dict(probes=[_entry("unknown")]))
    for spelling in ("default", "instantaneous", "normal", "unsteady"):
        assert spelling in str(caught.value)


@pytest.mark.parametrize("run_type", ["steady", "qsteady_rotor"])
def test_p0451_instantaneous_on_steady_keeps_default_script(tmp_path, run_type):
    default = _build(_case(tmp_path, [], [_entry("default")], run_type)).render()
    instant = _build(_case(tmp_path, [], [_entry("instantaneous")], run_type)).render()
    assert instant == default


@pytest.mark.parametrize("alias,canonical", [("normal", "default"), ("unsteady", "instantaneous")])
def test_p0451_alias_and_canonical_scripts_are_identical(tmp_path, alias, canonical):
    with pytest.warns(PyflightstreamWarning, match=canonical):
        alias_case = _case(tmp_path, [], [_entry(alias)])
    assert _build(alias_case).render() == _build(_case(tmp_path, [], [_entry(canonical)])).render()


def test_p0451_instantaneous_keeps_init_plots(tmp_path):
    script = _build(_case(tmp_path, [], [_entry("instantaneous")]))
    lines = script.render().splitlines()
    assert lines.count("UNSTEADY_SOLVER_NEW_FLUID_PLOT") == 3
    assert lines.index("UNSTEADY_SOLVER_NEW_FLUID_PLOT") < lines.index("START_SOLVER")
    assert not _imports(script)


def test_p0451_probesets_equal_coordinates_keep_declared_identity(tmp_path):
    script = _build(_case(tmp_path, [], [_entry("default"), _entry("default")]))
    records = script.probe_field_layout
    assert [record["probe_ids"] for record in records] == [[1, 2, 3], [4, 5, 6]]
    assert [record.get("offset") for record in records] == [0, 3]
    assert len({record.get("id") for record in records}) == 2


def test_p0451_probesets_shared_plane_has_constructed_offsets(tmp_path):
    script = _build(_case(tmp_path, [_plane(name="a"), _plane("avg_window", name="b")]))
    records = script.farfield_layout[-1]["shapes"]
    assert [record.get("offset") for record in records] == [0, 0]
    assert records[0].get("id") == records[1].get("id")
    assert records[0].get("id") is not None
    assert not _imports(script)


def test_p0451_probesets_reused_lattice_has_one_window_set(tmp_path):
    lattice = dict(rotor="ROTOR", stations=[-10, 1, 2], n_r=3, n_psi=16)
    declared = dict(kind="default", frame="REFERENCE", parameters=["VX"], lattices=[lattice])
    script = _build(_case(tmp_path, [_power()], [declared]))
    shape = script.farfield_layout[-1]["shapes"][0]
    record = script.probe_field_layout[0]
    assert shape["source"] in {"reused", "declared"}
    assert shape.get("id") == record.get("id") and shape.get("id") is not None
    assert shape.get("offset") == record.get("offset") == 0
    assert record.get("import_phase") == "window-start"
    assert not _imports(script)


def test_p0451_probesets_two_large_points_plan_under_two_seconds(tmp_path):
    import sys

    from pyflightstream.cases import Campaign, SweepAxis
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run import plan_campaign
    from pyflightstream.workspace import CampaignWorkspace

    # A plane has odd axis counts: 123 * 123 is the nearest square above 15000.
    plane = dict(
        _plane("avg_window"), half_width_bref=0.61, half_height_bref=0.61, spacing_bref=0.01
    )
    power = dict(_power(), n_psi=90)
    case = _case(tmp_path, [plane, power], [_entry("default"), _entry("default")])
    case = case.model_copy(update={"sweep": SweepAxis(type="alpha", values=[0, 1])})
    campaign = Campaign(name="probe_sets", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    start = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_campaign(
            campaign,
            CampaignWorkspace(tmp_path / "campaign"),
            write_plan=False,
            recipes=workflow_registry(),
        )
    elapsed = time.perf_counter() - start
    print(f"PROBESETS two-point plan: {elapsed:.6f} seconds")
    assert len(plan.ready) == 2, plan.summary()
    assert elapsed < 2.0, f"two-point plan took {elapsed:.6f}s"
    scripts = [_build(case.model_copy(update={"point": {"ALPHA": alpha}})) for alpha in (0, 1)]
    for script in scripts:
        shapes = script.farfield_layout[-1]["shapes"]
        assert [shape["count"] for shape in shapes] == [15129, 1080]
        assert [shape.get("offset") for shape in shapes] == [0, 15129]
        assert [record.get("offset") for record in script.probe_field_layout] == [0, 3]
        assert [record["probe_ids"] for record in script.probe_field_layout] == [
            [16210, 16211, 16212],
            [16213, 16214, 16215],
        ]
        assert _imports(script)[0][2] == 6
        action = script.pending_input_files["farfield_window_create.txt"].splitlines()
        csv_name = action[action.index("PROBE_POINTS_IMPORT") + 3]
        rows = script.pending_input_files[csv_name].splitlines()
        assert int(rows[0]) == 16209
        for shape in shapes:
            from pyflightstream.post.farfield_fields import recorded_layout

            layout = recorded_layout([shape])
            expected = layout.plane_m if shape["kind"] == "plane" else layout.lattice_m
            start = shape["offset"] + 1
            actual = [
                [float(v) for v in row.split(",")[:3]]
                for row in rows[start : start + shape["count"]]
            ]
            np.testing.assert_allclose(actual, np.round(expected, 5), atol=1e-5)


def test_p0451_probesets_post_uses_identity_with_equal_coordinates(tmp_path):
    from pyflightstream.post.farfield_fields import ProbeSamples, far_samples, recorded_layout

    script = _build(_case(tmp_path, [_plane()]))
    record = dict(script.farfield_layout[-1]["shapes"][0])
    count = record["count"]
    # Two distinct sets can have the same coordinates, including a permuted block.
    # The recorded span remains authoritative for selecting their different values.
    record.update(id="farfield:plane:second", offset=count, final_offset=count)
    layout = recorded_layout([record])
    points = np.vstack([layout.plane_m[::-1], layout.plane_m])
    samples = ProbeSamples(points, np.arange(2 * count * 3).reshape(-1, 3), np.zeros(2 * count))
    _, selected, reason = far_samples(samples, layout, per_m=1)
    assert not reason
    assert selected == slice(count, 2 * count)
    points[:count] = layout.plane_m
    _, selected, reason = far_samples(samples, layout, per_m=1)
    assert not reason and selected == slice(count, 2 * count)


def test_p0451_probesets_steady_offsets_follow_declared_points(tmp_path):
    script = _build(_case(tmp_path, [_plane()], [_entry("default")], "steady"))
    record = script.farfield_layout[-1]["shapes"][0]
    assert record.get("offset") == 0
    assert record.get("final_offset") == 3
    assert record.get("import_phase") == "after-march"
    assert _imports(script)[0][2] == record["count"]


@pytest.mark.parametrize("run_type", ["steady", "unsteady_rotor"])
def test_p0451_probesets_reused_component_keeps_its_entry_and_span(tmp_path, run_type):
    lattice = dict(rotor="ROTOR", stations=[-10, 1, 2], n_r=3, n_psi=16)
    declared = dict(_entry("default"), lattices=[lattice])
    power = _power() if run_type == "unsteady_rotor" else dict(_power(), export_type="last_step")
    if run_type == "steady":
        power.pop("last_steps")
    script = _build(_case(tmp_path, [power], [declared], run_type))
    shape = script.farfield_layout[-1]["shapes"][0]
    if run_type == "unsteady_rotor":
        assert not _imports(script), "a reused declaration must not be split between imports"
    assert shape.get("offset") == 0
    assert shape.get("sample_offset") == 3
    assert shape["count"] == 192
    if run_type == "unsteady_rotor":
        record = script.probe_field_layout[0]
        assert record["count"] == 195
        assert record["import_phase"] == "window-start"
        assert not _imports(script)


@pytest.mark.parametrize("second_export", ["avg_window", "last_step"])
def test_p0451_rv1_distinct_history_lattices_keep_their_conventional_samples(
    tmp_path, second_export
):
    from pyflightstream.post.farfield_fields import ProbeSamples, far_samples, recorded_layout

    first = _power()
    second = dict(_power(), name="second", stations=[-10, 3, 4], station=3)
    lattices = [
        {key: value for key, value in entry.items() if key in {"rotor", "stations", "n_r", "n_psi"}}
        for entry in (first, second)
    ]
    second["export_type"] = second_export
    if second_export == "last_step":
        second.pop("last_steps")
    probe = dict(kind="instantaneous", frame="REFERENCE", parameters=["VX"], lattices=lattices)
    script = _build(_case(tmp_path, [first, second], [probe]))
    records = script.farfield_layout[-1]["shapes"]
    action = script.pending_input_files["farfield_window_create.txt"].splitlines()
    window_path = action[action.index("PROBE_POINTS_IMPORT") + 3]
    window = script.pending_input_files[window_path].splitlines()
    expected_window_count = 384 if second_export == "avg_window" else 192
    assert int(window[0]) == expected_window_count
    assert records[0]["id"] != records[1]["id"]
    rows = window[1:]
    for _, path, _ in _imports(script):
        rows += script.pending_input_files[path].splitlines()[1:]
    points = np.array([[float(value) for value in row.split(",")[:3]] for row in rows])
    assert len(points) == 384
    samples = ProbeSamples(points, np.zeros_like(points), np.zeros(len(points)))
    for record in records:
        layout = recorded_layout([record])
        selected, _, reason = far_samples(samples, layout, per_m=1)
        assert not reason
        np.testing.assert_allclose(points[selected], layout.lattice_m, atol=1e-5)


@pytest.mark.parametrize(
    "version,kind,history",
    [
        ("0.45.0", None, True),
        ("0.45.1", None, False),
        ("0.45.0", "default", False),
        ("0.45.0", "instantaneous", True),
    ],
)
def test_p0451_rv1_old_run_keeps_its_implicit_probe_history(tmp_path, version, kind, history):
    from pyflightstream.post.products import read_csv_table, write_campaign_products
    from pyflightstream.run._pending import _write_probe_points
    from tests.tier1_offline.test_post_products import PLOTS_HEADER, _unsteady_workspace

    workspace = _unsteady_workspace(tmp_path, reductions=None, recipe="unsteady")
    table = '[[probes]]\nframe = "MRP"\nparameters = ["VX"]\n'
    if kind is not None:
        table += f'kind = "{kind}"\n'
    (workspace.inputs_dir / "pproc/p001.toml").write_text(table, encoding="utf-8")
    positions = _write_probe_points(workspace.sim_dir("7001"), "7001", [(1, 0.0, 1.0, 2.0, "MRP")])
    products._ffproof_post___set_record(
        workspace, package_version=version, probe_points_file=positions
    )
    (workspace.sim_dir("7001") / "outputs/AL-020_plots.txt").write_text(
        PLOTS_HEADER
        + "Time-step,VX1\n1,11,\n2,21,\n"
        + "-" * 60
        + "\n     Force Units: Coefficients\n"
        "Software : Flightstream version 26.1, build #7012026\n",
        encoding="utf-8",
    )
    write_campaign_products(workspace)
    target = workspace.root / "post/products/probes/AL-020_probes.csv"
    assert target.is_file() is history
    if history:
        _, rows = read_csv_table(target)
        assert [row["STEP"] for row in rows] == ["1", "2"]
        assert [float(row["VX"]) for row in rows] == [11.0, 21.0]
