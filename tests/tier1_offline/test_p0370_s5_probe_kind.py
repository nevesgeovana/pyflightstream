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

import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.post.products import read_csv_table, write_campaign_products
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
