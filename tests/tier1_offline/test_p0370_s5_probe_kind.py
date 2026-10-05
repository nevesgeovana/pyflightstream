"""P0370-S5-PROBE-KIND (FR-417): a probe entry of an unsteady row states its kind.

An UNSTEADY probe (the default, 0.36.0) is one fluid plot per point and
parameter, a history at every time step. A NORMAL probe is a probe point
created after the time march with the steady commands, updated and exported
once, so it holds the last time step. These tests render both kinds on the two
unsteady run types, hold the script of a pproc that states no kind to the
0.36.0 render, refuse a mixture and an unknown kind, and post a recorded
normal export into the probes table with the run's last time step.
"""

from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.cases import CampaignConfigError, PprocSpec, SimCase
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    UNSTEADY_ACTION_PROGRAM,
    UNSTEADY_ACTION_SCRIPT,
    WorkflowConventions,
    action_export_lines,
    build_script,
    normal_probe_creation,
)
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.run._actions_counter import stage_counter
from pyflightstream.run._pending import _write_probe_points
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_post_products import _products_manifest, _unsteady_workspace
from tests.tier1_offline.test_workflows import (
    GOLDEN_RENDERS,
    GOLDEN_WORKFLOWS,
    _case_for,
    _wb_geometry,
    _with_pproc,
    golden_name,
    render_or_refusal,
    steady_case,
)

UNSTEADY_TYPES = ("unsteady", "unsteady_rotor")


def _entry(kind: str | None = None, **extra: object) -> dict[str, object]:
    """One probe entry in the reference frame: a line of three and a 2 by 2 rectangle."""
    entry: dict[str, object] = {
        "frame": "REFERENCE",
        "parameters": ["VX", "VY", "VZ"],
        "points": 3,
        "lines": [{"start": [0.0, 0.0, 0.0], "end": [1.0, 0.0, 0.0]}],
        "rectangles": [
            {
                "origin": [0.0, -1.0, -2.0],
                "along_u": [0.0, 1.0, -2.0],
                "along_v": [0.0, -1.0, 2.0],
                "points_u": 2,
                "points_v": 2,
            }
        ],
        **extra,
    }
    if kind is not None:
        entry["kind"] = kind
    return entry


def _spec(*entries: dict[str, object], **extra: object) -> PprocSpec:
    return PprocSpec.model_validate({"groups": {"1": "all"}, "probes": list(entries), **extra})


def _script(tmp_path: Path, run_type: str, spec: PprocSpec) -> Script:
    """Build one row of ``run_type`` naming ``spec``, its outputs as the pproc declares them."""
    base = steady_case() if run_type == "steady" else _case_for(run_type)
    tmp_path.mkdir(parents=True, exist_ok=True)
    case = _with_pproc(base, _wb_geometry(tmp_path), pproc=spec)
    names = [name.replace("{name}", "P") for name in spec.outputs(run_type != "steady")]
    case = case.model_copy(update={"outputs": names})
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script


def _commands(script: Script) -> list[str]:
    return [line for line in script.render().splitlines() if line[:1].isalpha()]


def _heads(script: Script) -> list[str]:
    return [line.split()[0] for line in _commands(script)]


_PROBE_CREATION = ("NEW_PROBE_LINE", "NEW_PROBE_POINT", "PROBE_POINTS_IMPORT")


@pytest.mark.parametrize("run_type", UNSTEADY_TYPES)
def test_p0370_s5_normal_entry_is_probe_points_after_the_march(tmp_path, run_type):
    """P0370-S5-PROBE-KIND (FR-417 R1, R3): steady shapes after the march, update, export."""
    spec = _spec(_entry("normal"))
    script = _script(tmp_path, run_type, spec)
    heads = _heads(script)
    assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" not in heads, (
        "a normal entry emitted a fluid plot; a normal probe is a probe point (FR-417 R3)"
    )
    march = heads.index("START_SOLVER")
    created = [i for i, head in enumerate(heads) if head in _PROBE_CREATION]
    assert created, "a normal entry created no probe point"
    assert min(created) > march, "a normal probe was created before the time march"
    assert heads.count("UPDATE_PROBE_POINTS") == 1 and heads.count("EXPORT_PROBE_POINTS") == 1
    update = heads.index("UPDATE_PROBE_POINTS")
    assert max(created) < update < heads.index("EXPORT_PROBE_POINTS"), (
        "the probe points must be updated after they are created and before the export"
    )
    lines = script.render().splitlines()
    exported = lines[lines.index("EXPORT_PROBE_POINTS") + 1]
    assert "{name}_probes.txt" in spec.outputs(True), "the export is not a declared output"
    assert exported.endswith("P_probes.txt"), exported
    # THE SAME COMMANDS, IN THE SAME ORDER, AS A STEADY ROW (R1).
    steady = _script(tmp_path / "steady", "steady", spec)
    assert [line for line in _commands(script) if line.split()[0] in _PROBE_CREATION] == [
        line for line in _commands(steady) if line.split()[0] in _PROBE_CREATION
    ]
    assert [point[0] for point in script.probe_points] == list(range(1, 8))


@pytest.mark.parametrize("run_type", UNSTEADY_TYPES)
def test_p0370_s5_unsteady_kind_and_no_kind_render_as_0_36_0(tmp_path, run_type):
    """P0370-S5-PROBE-KIND (FR-417 R3): no kind is unsteady, byte for byte, and the goldens hold."""
    unstated = _script(tmp_path / "a", run_type, _spec(_entry()))
    stated = _script(tmp_path / "b", run_type, _spec(_entry("unsteady")))
    assert stated.render().replace(str(tmp_path / "b"), "<T>") == unstated.render().replace(
        str(tmp_path / "a"), "<T>"
    )
    heads = _heads(unstated)
    assert heads.count("UNSTEADY_SOLVER_NEW_FLUID_PLOT") == 7 * 3
    assert not set(heads) & {*_PROBE_CREATION, "UPDATE_PROBE_POINTS", "EXPORT_PROBE_POINTS"}
    assert "{name}_probes.txt" not in _spec(_entry()).outputs(True)
    for name, label, build in GOLDEN_RENDERS:
        if name == run_type:
            golden = GOLDEN_WORKFLOWS / golden_name(name, label, build)
            assert render_or_refusal(name, label, build) == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("run_type", UNSTEADY_TYPES)
def test_p0370_s5_mixed_kinds_are_refused_naming_both_lists(tmp_path, run_type):
    """P0370-S5-PROBE-KIND (FR-417 R2): one unsteady row samples its entries one way."""
    spec = _spec(_entry("normal"), _entry(), _entry("normal"))
    with pytest.raises(CampaignConfigError) as refused:
        _script(tmp_path, run_type, spec)
    message = str(refused.value)
    assert "unsteady (fluid plots at every time step) 2;" in message, message
    assert "normal (probe points at the last time step) 1, 3." in message, message
    assert "State one kind on every entry" in message, message
    sectioned = _spec(
        _entry("normal"),
        volume_section={
            "shape": "rectangle",
            "frame": "REFERENCE",
            "plane": "YZ",
            "offset_m": 0,
            "corners_m": [-1, -2, 1, 2],
            "points": [2, 2],
            "format": "vtk",
        },
    )
    with pytest.raises(CampaignConfigError, match=r"\[volume_section\]; normal"):
        _script(tmp_path / "vsec", run_type, sectioned)


def test_p0370_s5_a_steady_row_accepts_kind_and_changes_nothing(tmp_path):
    """P0370-S5-PROBE-KIND (FR-417 R2): on a steady row `kind` is accepted and inert."""
    mixed = _script(tmp_path / "a", "steady", _spec(_entry("normal"), _entry("unsteady")))
    plain = _script(tmp_path / "b", "steady", _spec(_entry(), _entry()))
    assert mixed.render().replace(str(tmp_path / "a"), "<T>") == plain.render().replace(
        str(tmp_path / "b"), "<T>"
    )


@pytest.mark.parametrize("value", ["instant", "Normal", "", 1])
def test_p0370_s5_an_unknown_kind_is_refused_naming_the_two(value):
    """P0370-S5-PROBE-KIND (FR-417 R5): the pproc model refuses any other kind."""
    with pytest.raises(ValidationError) as refused:
        _spec(_entry(value))  # type: ignore[arg-type]
    message = str(refused.value)
    assert "'unsteady' or 'normal'" in message, message
    assert _spec(_entry("normal")).probes[0].kind == "normal"
    assert _spec(_entry()).probes[0].kind == "unsteady"


def _probe_export(rows: list[tuple[float, ...]]) -> str:
    """An EXPORT_PROBE_POINTS file holding ``rows`` of X, Y, Z, VX, VY, VZ."""
    fixture = Path(__file__).parent / "fixtures" / "probe_points_26.120.txt"
    lines = fixture.read_text(encoding="utf-8").splitlines()
    count = next(i for i, line in enumerate(lines) if "Number of Probe Points" in line)
    head = lines[: count + 4]
    head[count] = f"     Number of Probe Points:                     {len(rows)}"
    body = [
        "     "
        + ",".join(f"{value: .6E}" for value in (x, y, z, 0.08, 0.05, vx, vy, vz, 29.0))
        + "".join(f",{0.0: .4E}" for _ in range(7))
        + ","
        for x, y, z, vx, vy, vz in rows
    ]
    return "\n".join([*head, *body, *lines[count + 4 + 12 :]]) + "\n"


def _normal_workspace(tmp_path, monkeypatch, *, stopped_at=None, export=True):
    """A recorded unsteady point whose pproc's one entry is normal, with its export."""
    workspace = _unsteady_workspace(tmp_path, reductions=None, recipe="unsteady")
    pproc = (
        '[groups]\n"1" = "all"\n\n[[probes]]\nframe = "MRP"\nkind = "normal"\n'
        'parameters = ["VX"]\npoints = 3\nlines = [{start = [0, 0, 0], end = [1, 0, 0]}]\n'
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8", newline="\n")
    positions = [(n, n - 1.0, 0.5, 0.0, "MRP") for n in (1, 2, 3)]
    relative = _write_probe_points(workspace.sim_dir("7001"), "7001", positions)
    outputs = workspace.sim_dir("7001") / "outputs"
    if export:
        rows = [(n - 1.0, 0.5, 0.0, 30.0 + n, 0.1 * n, -0.2 * n) for n in (1, 2, 3)]
        (outputs / "AL-020_probes.txt").write_text(
            _probe_export(rows), encoding="utf-8", newline="\n"
        )
    (record,) = workspace.read_manifest()
    record = record.model_copy(
        update={
            "probe_points_file": relative,
            "package_version": "0.37.0",
            "reductions": {"time_iterations": 96},
            "stopped_at": stopped_at,
            "outputs": [
                "outputs/AL-020.txt",
                "outputs/AL-020_probes.txt",
                "outputs/AL-020_plots.txt",
            ],
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    return workspace


@pytest.mark.parametrize("stopped_at,step", [(None, "96"), ({"step": 40}, "40")])
def test_p0370_s5_post_writes_the_normal_table_at_the_last_step(
    tmp_path, monkeypatch, stopped_at, step
):
    """P0370-S5-PROBE-KIND (FR-417 R4): the steady spine, STEP the run's last time step."""
    workspace = _normal_workspace(tmp_path, monkeypatch, stopped_at=stopped_at)
    write_campaign_products(workspace)
    columns, rows = read_csv_table(workspace.root / "post/products/probes/AL-020_probes.csv")
    assert columns[:7] == ("POL", "PROBE", "X", "Y", "Z", "FRAME", "STEP"), columns
    assert [int(row["PROBE"]) for row in rows] == [1, 2, 3]
    assert {row["STEP"] for row in rows} == {step}, "STEP is the run's last time step"
    assert {row["FRAME"] for row in rows} == {"MRP"}
    assert [float(row["vx"]) for row in rows] == [31.0, 32.0, 33.0]
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_probes.csv" in manifest["products"]
    assert not any("AL-020_probes" in name for name in manifest.get("skipped", {}))


def test_p0370_s5_post_names_a_missing_normal_export(tmp_path, monkeypatch):
    """P0370-S5-PROBE-KIND (FR-417 R4): no export, no table, and the skip says why."""
    workspace = _normal_workspace(tmp_path, monkeypatch, export=False)
    write_campaign_products(workspace)
    assert not (workspace.root / "post/products/probes/AL-020_probes.csv").exists()
    skipped = _products_manifest(workspace).get("skipped", {})
    reason = skipped.get("probes/AL-020_probes.csv", "")
    assert "probe points export" in reason and 'kind = "normal"' in reason, skipped


def _continuation(tmp_path: Path, run_type: str, spec: PprocSpec) -> tuple[Script, Script]:
    """The full script of a row and the script continuing it from its saved state."""
    full = _script(tmp_path / "full", run_type, spec)
    form = "{ADDITIONAL_REVS=1}" if run_type == "unsteady_rotor" else "{ADDITIONAL_ITERS=12}"
    base = _case_for(run_type)
    restart = {
        RESTART_VARIABLE: form,
        RESTART_FROM_VARIABLE: "datapoints/DP-AL+000/archive/20260914-010000/point.fsm",
        RESTART_ITERATIONS_VARIABLE: "12",
    }
    (tmp_path / "cont").mkdir(parents=True)
    case = _with_pproc(
        base.model_copy(update={"variables": {**base.variables, **restart}}),
        _wb_geometry(tmp_path / "cont"),
        pproc=spec,
    )
    names = [name.replace("{name}", "P") for name in spec.outputs(True)]
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case.model_copy(update={"outputs": names}), script)
    return full, script


_FRAME_HEADS = ("CREATE_NEW_COORDINATE_SYSTEM", "SET_COORDINATE_SYSTEM", "INITIALIZE_SOLVER")


@pytest.mark.parametrize("run_type", UNSTEADY_TYPES)
def test_p0370_s5_a_continuation_creates_the_normal_probes_after_its_march(tmp_path, run_type):
    """P0370-S5-PROBE-KIND (FR-417 R6): the full script's probe commands, after the march."""
    spec = _spec(_entry("normal", frame="MRP"))
    full, continued = _continuation(tmp_path, run_type, spec)
    heads = _heads(continued)
    assert heads[0] == "OPEN" and not set(heads) & set(_FRAME_HEADS), (
        "a continuation emits no frame, motion or initialization (FR-396)"
    )
    probes = [line for line in _commands(continued) if line.split()[0] in _PROBE_CREATION]
    assert probes, "the continuation never created the normal probes the stopped run lacked"
    assert probes == [line for line in _commands(full) if line.split()[0] in _PROBE_CREATION]
    created = [i for i, head in enumerate(heads) if head in _PROBE_CREATION]
    assert heads.index("START_SOLVER") < min(created)
    assert max(created) < heads.index("UPDATE_PROBE_POINTS") < heads.index("EXPORT_PROBE_POINTS")
    assert continued.probe_points == full.probe_points


@pytest.mark.parametrize("run_type", UNSTEADY_TYPES)
def test_p0370_s5_a_continuation_without_normal_probes_creates_none(tmp_path, run_type):
    """P0370-S5-PROBE-KIND (FR-417 R6): no normal entry, no probe command, as in 0.36.0."""
    _, continued = _continuation(tmp_path, run_type, _spec(_entry()))
    heads = _heads(continued)
    assert not set(heads) & {*_PROBE_CREATION, "UPDATE_PROBE_POINTS", "EXPORT_PROBE_POINTS"}
    assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" not in heads and continued.probe_points == []


@pytest.mark.parametrize("kind", ["unsteady", "normal"])
def test_p0370_s5_a_continuation_that_cannot_place_its_normal_probes_is_refused(tmp_path, kind):
    """P0370-S5-PROBE-KIND (FR-417 R6): without its full script, a rerun from the mesh."""
    spec = _spec(_entry(kind, frame="MRP"), _entry(kind, frame="MRP"))
    base = _case_for("unsteady")
    restart = {
        RESTART_VARIABLE: "{ADDITIONAL_ITERS=12}",
        RESTART_FROM_VARIABLE: "datapoints/DP-AL+000/archive/20260914-010000/point.fsm",
        RESTART_ITERATIONS_VARIABLE: "12",
    }
    case = _with_pproc(
        base.model_copy(update={"variables": {**base.variables, **restart}}),
        _wb_geometry(tmp_path),
        pproc=spec,
    ).model_copy(
        update={
            "geometry": str(tmp_path / "moved_away.fsm"),
            "outputs": [name.replace("{name}", "P") for name in spec.outputs(True)],
        }
    )
    script = Script("26.124")
    if kind == "unsteady":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            build_script(case, script)
        assert _heads(script)[0] == "OPEN", "a continuation never reads the mesh"
        return
    with pytest.raises(CampaignConfigError) as refused:
        build_script(case, script)
    message = str(refused.value)
    assert "normal probes (entries 1, 2)" in message, message
    assert "moved_away.fsm" in message and "pyfs-matrix run --force-rerun <point>" in message


def _windowed(tmp_path: Path, run_type: str, kind: str = "normal") -> tuple[SimCase, Script]:
    """A row with one probe entry of ``kind`` and a per-step window from step 2."""
    spec = _spec(_entry(kind, frame="MRP"))
    key = "EXPORT_UNSTEADY_AFTER_ITER" if run_type == "unsteady" else "EXPORT_UNSTEADY_LAST_ITER"
    base = _case_for(run_type)
    tmp_path.mkdir(parents=True, exist_ok=True)
    case = _with_pproc(
        base.model_copy(update={"variables": {**base.variables, key: "2"}}),
        _wb_geometry(tmp_path),
        pproc=spec,
    )
    case = case.model_copy(
        update={"outputs": [name.replace("{name}", "P") for name in spec.outputs(True)]}
    )
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return case, script


@pytest.mark.parametrize("run_type", UNSTEADY_TYPES)
def test_p0370_s5_a_window_updates_and_exports_normal_probes_every_step(tmp_path, run_type):
    """P0370-S5-PROBE-KIND (FR-417 R7): the per-step action updates, then exports the probes."""
    case, script = _windowed(tmp_path, run_type)
    action = action_export_lines(WorkflowConventions(), case, version="26.124")
    assert "UPDATE_PROBE_POINTS" in action, "the per-step action does not update the probes"
    export = action.index("EXPORT_PROBE_POINTS")
    assert action[export + 1] == "P_probes.txt" and action.index("UPDATE_PROBE_POINTS") < export
    rescue = action_export_lines(WorkflowConventions(), case, whole_run=True, version="26.124")
    assert "EXPORT_PROBE_POINTS" not in rescue, "the rescue may fire before the points exist"
    created = [line for line in _commands(script) if line.split()[0] in _PROBE_CREATION]
    creation = normal_probe_creation(case, "26.124")
    assert creation == "".join(f"{line}\n" for line in ["DELETE_PROBE_POINTS", *created])
    heads = _heads(script)
    march = heads.index("START_SOLVER")
    assert heads[march + 1] == "DELETE_PROBE_POINTS", "the post-march creation deletes first"
    unwindowed = _script(tmp_path / "plain", run_type, _spec(_entry("normal", frame="MRP")))
    assert "DELETE_PROBE_POINTS" not in _heads(unwindowed)
    windowless = {k: v for k, v in case.variables.items() if not k.startswith("EXPORT_UNSTEADY")}
    assert normal_probe_creation(case.model_copy(update={"variables": windowless}), "26.124") == ""
    fluid_case, _ = _windowed(tmp_path / "fluid", run_type, kind="unsteady")
    assert normal_probe_creation(fluid_case, "26.124") == ""


def _run_counter(tmp_path: Path, case: SimCase, script: Script, steps: int) -> list[str]:
    """Stage the point's counter program and run it ``steps`` times, as the solver does."""
    work = tmp_path / "work"
    for name, text in script.pending_action_scripts.items():  # as the run stages them
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(text, encoding="utf-8", newline="\n")
    stage_counter(work, script, case, "26.124", {})
    program = work / UNSTEADY_ACTION_PROGRAM
    written = []
    for _ in range(steps):
        # The environment stated, without the package on the path, as the solver runs it.
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        subprocess.run([sys.executable, str(program)], env=environment, check=True)
        written.append((work / UNSTEADY_ACTION_SCRIPT).read_text(encoding="utf-8"))
    return written


def test_p0370_s5_the_first_exporting_step_creates_the_points_once(tmp_path):
    """P0370-S5-PROBE-KIND (FR-417 R7): creation on the first exporting step, then exports."""
    case, script = _windowed(tmp_path, "unsteady")
    steps = _run_counter(tmp_path, case, script, 4)
    creation = normal_probe_creation(case, "26.124")
    assert creation.startswith("DELETE_PROBE_POINTS\nNEW_PROBE_LINE")
    assert steps[0] == "", "step 1 precedes the window"
    assert steps[1].startswith(creation), "the first exporting step does not create the points"
    assert "UPDATE_PROBE_POINTS\n" in steps[1] and "EXPORT_PROBE_POINTS\nP_probes.txt\n" in steps[1]
    for later in steps[2:]:
        assert "NEW_PROBE" not in later and "DELETE_PROBE_POINTS" not in later, later
        assert "UPDATE_PROBE_POINTS\n" in later and "EXPORT_PROBE_POINTS\nP_probes.txt\n" in later
    fluid_case, fluid = _windowed(tmp_path / "fluid", "unsteady", kind="unsteady")
    program = _run_counter(tmp_path / "fluid", fluid_case, fluid, 2)
    assert "PROBE" not in "".join(program)


def test_p0370_s5_stamped_normal_exports_feed_the_probes_series(tmp_path, monkeypatch):
    """P0370-S5-PROBE-KIND (FR-417 R7): one series row per probe and exporting step."""
    workspace = _normal_workspace(tmp_path, monkeypatch)
    (record,) = workspace.read_manifest()
    window = {
        "stated_form": "iterations",
        "stated_value": 95.0,
        "first_step": 95,
        "time_iterations": 96,
        "delta_time_s": 0.01,
    }
    record = record.model_copy(update={"export_window": window})
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    for step in (95, 96):
        rows = [(n - 1.0, 0.5, 0.0, step + n, 0.0, 0.0) for n in (1, 2, 3)]
        (workspace.sim_dir("7001") / f"AL-020_probes_iteration={step}.txt").write_text(
            _probe_export(rows), encoding="utf-8", newline="\n"
        )
    write_campaign_products(workspace)
    series = next((workspace.root / "post").rglob("AL-020_probes_series.csv"))
    _, rows = read_csv_table(series)
    assert [(int(row["STEP"]), int(row["PROBE"])) for row in rows] == [
        (step, probe) for step in (95, 96) for probe in (1, 2, 3)
    ]
    assert [float(row["vx"]) for row in rows] == [96.0, 97.0, 98.0, 97.0, 98.0, 99.0]


def test_p0370_s5_a_raw_probe_line_is_not_replayed_by_the_continuation(tmp_path):
    """P0370-S5-PROBE-KIND (FR-417 R6): the setup's own probe line appears once, not twice."""
    from pyflightstream.cases import RawCommand

    raw = RawCommand(command="NEW_PROBE_POINT VOLUME 7.0 8.0 9.0", before="analysis")
    spec = _spec(_entry("normal", frame="MRP"))
    base = _case_for("unsteady")
    restart = {
        RESTART_VARIABLE: "{ADDITIONAL_ITERS=12}",
        RESTART_FROM_VARIABLE: "datapoints/DP-AL+000/archive/20260914-010000/point.fsm",
        RESTART_ITERATIONS_VARIABLE: "12",
    }
    case = _with_pproc(
        base.model_copy(update={"variables": {**base.variables, **restart}, "raw_commands": [raw]}),
        _wb_geometry(tmp_path),
        pproc=spec,
    ).model_copy(update={"outputs": [n.replace("{name}", "P") for n in spec.outputs(True)]})
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    assert _commands(script).count("NEW_PROBE_POINT VOLUME 7.0 8.0 9.0") == 1
    assert "NEW_PROBE_LINE" in _heads(script), "the normal probes were not created"
