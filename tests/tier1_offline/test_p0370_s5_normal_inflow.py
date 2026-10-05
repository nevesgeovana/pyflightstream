"""P0370-S5-NORMAL-INFLOW (FR-418): the reusable inflow from normal probes of an unsteady run.

A normal ``[[probes]]`` entry with ``reusable_inflow = true`` on an unsteady
row records the steady probe-points layout and is posted through the steady
route, so its ``<stem>.inflow.dat`` is the one a steady row writes from the
same probe values: the steady route's own output is the oracle. The product
states the instant it holds, the run's last time step.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run._pending import _write_probe_points
from pyflightstream.script import Script, helpers
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_post_products import _unsteady_workspace
from tests.tier1_offline.test_workflows import (
    _wb_geometry,
    _with_pproc,
    steady_case,
    unsteady_case,
)

_RECTANGLE = {
    "origin": [0.0, -1.0, -2.0],
    "along_u": [0.0, 1.0, -2.0],
    "along_v": [0.0, -1.0, 2.0],
    "points_u": 2,
    "points_v": 3,
}


def _pproc_toml(kind: str) -> str:
    return (
        '[groups]\n"1" = "all"\n\n[[probes]]\nframe = "REFERENCE"\n'
        f'kind = "{kind}"\nreusable_inflow = true\nfield_formats = ["tecplot"]\n'
        "rectangles = [{origin = [0.0, -1.0, -2.0], along_u = [0.0, 1.0, -2.0], "
        "along_v = [0.0, -1.0, 2.0], points_u = 2, points_v = 3}]\n"
    )


def _built(tmp_path: Path, *, steady: bool, kind: str = "normal") -> Script:
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "probes": [
                {
                    "frame": "REFERENCE",
                    "kind": kind,
                    "reusable_inflow": True,
                    "field_formats": ["tecplot"],
                    "rectangles": [_RECTANGLE],
                }
            ],
        }
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    case = _with_pproc(
        steady_case() if steady else unsteady_case(), _wb_geometry(tmp_path), pproc=spec
    )
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    # The saved-mesh fixture states no GLOBAL units; a run records them.
    script.record_opened_length_unit("METER")
    return script


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


def _posted(tmp_path, monkeypatch, *, steady: bool, kind: str = "normal") -> Path:
    """Post one recorded point of the two routes, from the same probe values."""
    monkeypatch.undo()  # the manifest of an earlier call is not this workspace's
    script = _built(tmp_path / "build", steady=steady, kind=kind)
    workspace = _unsteady_workspace(
        tmp_path / "w", reductions=None, recipe="steady" if steady else "unsteady"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        _pproc_toml(kind), encoding="utf-8", newline="\n"
    )
    relative = _write_probe_points(workspace.sim_dir("7001"), "7001", script.probe_points)
    rows = [
        (x, y, z, 30.0 + y, 0.25 * z, -0.5 + y * z) for _, x, y, z, _frame in script.probe_points
    ]
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_probes.txt").write_text(_probe_export(rows), encoding="utf-8", newline="\n")
    (record,) = workspace.read_manifest()
    record = record.model_copy(
        update={
            "probe_points_file": relative,
            "package_version": "0.37.0",
            "reductions": None if steady else {"time_iterations": 96},
            "probe_field_layout": script.probe_field_layout,
            "frame_motions": script.frame_motions,
            "solver_setup": helpers.solver_settings(Script("26.124"), velocity=30).model_dump(),
            "fs_exe_sha256": "9" * 64,
            "fs_build": "8172026",
            "outputs": [
                "outputs/AL-020.txt",
                "outputs/AL-020_probes.txt",
                "outputs/AL-020_plots.txt",
            ],
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    return workspace.root / "post" / "products" / "fields"


def _numbers(path: Path) -> np.ndarray:
    return np.array(
        [[float(value) for value in line.split()] for line in path.read_text().splitlines()]
    )


def test_p0370_s5_normal_entry_records_the_steady_layout(tmp_path):
    """P0370-S5-NORMAL-INFLOW (FR-418 R1, R3): the steady export kind; unsteady keeps 0.36.0."""
    normal = _built(tmp_path / "n", steady=False).probe_field_layout
    steady = _built(tmp_path / "s", steady=True).probe_field_layout
    assert normal[0]["export_kind"] == "steady-probe"
    assert normal[0]["coordinate_source"] == "native-export-reference"
    assert normal[0]["sampled_at"] == "last-time-step"
    assert {k: v for k, v in normal[0].items() if k != "sampled_at"} == steady[0]
    fluid = _built(tmp_path / "u", steady=False, kind="unsteady").probe_field_layout
    assert fluid[0]["export_kind"] == "unsteady-fluid-plot" and "sampled_at" not in fluid[0]


def test_p0370_s5_normal_inflow_equals_the_steady_routes(tmp_path, monkeypatch):
    """P0370-S5-NORMAL-INFLOW (FR-418, R2): value for value the steady route's inflow."""
    oracle = _posted(tmp_path / "steady", monkeypatch, steady=True)
    posted = _posted(tmp_path / "unsteady", monkeypatch, steady=False)
    expected = oracle / "AL-020_field_01.inflow.dat"
    assert expected.is_file(), sorted(p.name for p in oracle.iterdir())
    written = posted / "AL-020_field_01_step_96.inflow.dat"
    assert written.is_file(), sorted(p.name for p in posted.iterdir()) if posted.is_dir() else []
    assert np.array_equal(_numbers(written), _numbers(expected)), (
        "the inflow of a normal probe is not the steady route's from the same values"
    )
    assert _numbers(written).shape == (6, 6)
    sampling = json.loads(Path(str(written) + ".provenance.json").read_text())["sampling"]
    assert sampling["sampled_at"] == "last-time-step" and sampling["step"] == "96"
    assert sampling["export_kind"] == "steady-probe"


def test_p0370_s5_unsteady_inflow_entry_keeps_its_history_route(tmp_path):
    """P0370-S5-NORMAL-INFLOW (FR-418 R3): an unsteady entry still samples fluid plots."""
    kind = "unsteady"
    script = _built(tmp_path, steady=False, kind=kind)
    text = script.render()
    assert text.count("UNSTEADY_SOLVER_NEW_FLUID_PLOT\n") == 6 * 3
    assert "EXPORT_PROBE_POINTS" not in text and "UNSTEADY_SOLVER_DELETE_ALL_PLOTS" in text
    names = PprocSpec.model_validate(
        {"probes": [{"kind": kind, "reusable_inflow": True, "rectangles": [_RECTANGLE]}]}
    ).outputs(True)
    assert "{name}_plots.txt" in names and "{name}_probes.txt" not in names
