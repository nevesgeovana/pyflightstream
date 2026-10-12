"""P0400 simulation-stage defects (post-1 lane).

P0400-OBJREMEDY (PFS-2100.011): the FR-348 mesh-faces warning names a remedy
that works for the geometry's kind; --overwrite is always refused for an OBJ.
P0400-INSTANTGROUPS (PFS-2105.011): an unsteady simulation with no window gets
group polars marked kind: instant, as its rotor table is, and a post.log line.
P0400-EMPTYPLOTS (PFS-2105.031, not a bug): a plots export holding no step is
refused by the parser, so the post names it as holding no step and replaces the
pre-recorded "missing plots history" reason; this pins that it stays so.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pyflightstream.post import _sim
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_goal028_rotor_table_average import REFERENCE, _pproc
from tests.tier1_offline.test_post_superfile import _MATRIX, _PLOTS, _post, _workspace


@pytest.mark.parametrize(("name", "overwrite"), [("wing.obj", False), ("wing.fsm", True)])
def test_p0400_objremedy_names_a_remedy_that_runs(tmp_path, monkeypatch, name, overwrite):
    """P0400-OBJREMEDY: an OBJ is never told --overwrite; a saved simulation still is."""
    faces = SimpleNamespace(
        same_bytes=False,
        sidecar=tmp_path / f"{name}.inventory.toml",
        mesh_faces=12,
        counted_sha256="a" * 12,
        recorded_sha256="b" * 12,
        name=name,
    )
    monkeypatch.setattr(_sim, "recorded_mesh_faces", lambda *_args: faces)
    workspace = SimpleNamespace(sim_dir=lambda sim: tmp_path / sim, resolve_geometry=None)
    record = SimpleNamespace(sim_id="1", run_id="r1", inputs_sha256={})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert _sim._mesh_faces_of(cast(Any, workspace), cast(Any, record), "P1") == "12"
    (message,) = [str(warning.message) for warning in caught]
    assert ("--overwrite" in message) is overwrite, message
    if not overwrite:
        assert "docs/mesh-inputs.md" in message, message


def _without_a_window(tmp_path: Path, *, plots: str | None = None) -> tuple[dict, list[str]]:
    """The superfile fixture's rotor simulation, its record stating a speed and no window."""
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(REFERENCE, encoding="utf-8")
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        '[groups]\n"1" = "all"\n\n' + _pproc("HUB_PUSHER", "MRP", '["B"]').split("\n\n", 1)[1],
        encoding="utf-8",
    )
    (workspace.root / "matriz.fs").write_text(_MATRIX, encoding="utf-8")
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            plan = {"rotors": {"PUSHER": {"blades": 6, "rpm": 2200.0}}}
            record = record.model_copy(update={"reductions": plan})
            if plots is not None:
                export = next(o for o in record.outputs if o.endswith("_plots.txt"))
                (workspace.sim_dir("6002") / export).write_text(plots, encoding="utf-8")
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    return json.loads(manifest.read_text(encoding="utf-8")), [str(w.message) for w in caught]


def test_p0400_instantgroups_are_marked_and_said(tmp_path):
    """P0400-INSTANTGROUPS: every group polar of 6002 is kind: instant, and post.log says why."""
    manifest, caught = _without_a_window(tmp_path)
    polars = {
        key: entry
        for key, entry in manifest["products"].items()
        if key.startswith("polars/")
        and "6002" in key
        and entry.get("kind") != "rotor_table"
        and not key.endswith("_rotor.csv")
        and "SUPER" not in key
    }
    assert polars, sorted(manifest["products"])
    assert {entry.get("kind") for entry in polars.values()} == {"instant"}, polars
    assert any("simulation 6002" in m and "LAST TIME STEP" in m for m in caught), caught


def test_p0400_emptyplots_says_the_export_holds_no_step(tmp_path):
    """P0400-EMPTYPLOTS: the export is on disk; the skip says it holds no time step."""
    # The header and the column line, written before the first step was.
    empty = _PLOTS.partition("1.0000,")[0]
    manifest, _caught = _without_a_window(tmp_path, plots=empty)
    reasons = {key: why for key, why in manifest["skipped"].items() if "6002" in key}
    plots = [why for key, why in reasons.items() if key.endswith("_plots.csv")]
    assert plots and "holds no time step" in plots[0], reasons
    assert not any("missing plots history export" in why for why in reasons.values()), reasons
