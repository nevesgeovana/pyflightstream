"""The per-machine cost file of 0.35: ``inputs/costs/c<NNN>.toml`` (FR-398)."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.run import PlannedPointCost
from pyflightstream.workspace.costs import (
    estimate_seconds,
    priced_rows,
    read_cost_file,
    resolve_cost_file,
    select_cost_file,
    unmarked_cost_files,
)

REPO = Path(__file__).resolve().parents[2]

_FILE = """# synthetic test file
[machine]
name = "m"
fs_build = "26.1"
[reference]
mesh_faces = 1000
ncpus = 4
wall_time_s = 100.0
steps = 10
[parallel]
ncpus = [2, 4, 8]
speedup = [1.0, 2.0, 6.0]
[mesh]
exponent_b = 2.0
[steps]
exponent = 0.5
[flags]
viscous_coupling = 3.0
"""


@pytest.fixture(autouse=True)
def _clear_selection():
    select_cost_file(None)
    yield
    select_cost_file(None)


def _inputs(tmp_path: Path, *stems: str, text: str = _FILE) -> Path:
    costs = tmp_path / "inputs" / "costs"
    costs.mkdir(parents=True)
    for stem in stems:
        (costs / f"{stem}.toml").write_text(text, encoding="utf-8")
    return tmp_path / "inputs"


def _cost(tmp_path: Path):
    return resolve_cost_file(_inputs(tmp_path, "c001"))


def test_reference_point_returns_the_anchor_time(tmp_path):
    """P0350-COST-FILE (FR-398): the anchor run's own figures give its wall time."""
    est = estimate_seconds(_cost(tmp_path), faces=1000, steps=10, ncpus=4)
    assert est.seconds == 100.0


def test_efficiency_curve_is_interpolated_linearly(tmp_path):
    """P0350-COST-FILE (FR-398 R1): ncpus 6 sits halfway between 4 and 8."""
    cost = _cost(tmp_path)
    assert cost.speedup_at(6) == pytest.approx(4.0)
    est = estimate_seconds(cost, faces=1000, steps=10, ncpus=6)
    assert est.seconds == pytest.approx(50.0)


def test_outside_the_range_is_never_extrapolated(tmp_path):
    """P0350-COST-FILE (FR-398 R1): 16 CPUs exceeds the curve, so no estimate."""
    cost = _cost(tmp_path)
    assert cost.speedup_at(16) is None
    est = estimate_seconds(cost, faces=1000, steps=10, ncpus=16)
    assert est.seconds is None
    assert "outside the stated efficiency range" in est.basis


def test_mesh_and_step_exponents(tmp_path):
    """P0350-COST-FILE (FR-398 R2): time follows faces^b and steps^exponent."""
    cost = _cost(tmp_path)
    assert estimate_seconds(cost, faces=2000, steps=10, ncpus=4).seconds == pytest.approx(400.0)
    assert estimate_seconds(cost, faces=1000, steps=40, ncpus=4).seconds == pytest.approx(200.0)


def test_flag_multiplier_applies_only_to_a_flag_the_point_sets(tmp_path):
    """P0350-COST-FILE (FR-398 R3): a stated flag multiplies; an unstated one does not."""
    cost = _cost(tmp_path)
    base = {"faces": 1000, "steps": 10, "ncpus": 4}
    assert estimate_seconds(cost, **base, flags=["viscous_coupling"]).seconds == 300.0
    assert estimate_seconds(cost, **base, flags=["unknown_flag"]).seconds == 100.0


def test_several_files_are_refused_unless_one_is_selected(tmp_path):
    """P0350-COST-FILE (FR-398): several cost files are refused by name, then --cost-file picks."""
    inputs = _inputs(tmp_path, "c001", "c002")
    with pytest.raises(InputArtifactError, match=re.escape("--cost-file")):
        resolve_cost_file(inputs)
    select_cost_file("c002")
    chosen = resolve_cost_file(inputs)
    assert chosen is not None
    assert chosen.path.stem == "c002"
    select_cost_file("c009")
    with pytest.raises(InputArtifactError, match=r"c009.*c001, c002"):
        resolve_cost_file(inputs)


def test_an_unknown_key_is_refused_by_name(tmp_path):
    """P0350-COST-FILE (FR-398): a key nothing reads is refused, not ignored."""
    inputs = _inputs(tmp_path, "c001", text=_FILE.replace("[mesh]", "[mesh]\nexponent = 1"))
    with pytest.raises(InputArtifactError, match="exponent"):
        resolve_cost_file(inputs)


def _row(run_id="r1", processors=4):
    return PlannedPointCost(
        run_id=run_id,
        panels=1000,
        trailing_edges=0,
        farfield_layers=5,
        viscous_coupling=False,
        unsteady=False,
        time_iterations=10,
        processors=processors,
        seconds=7.0,
        samples=2,
        basis="fitted",
    )


def test_no_cost_file_leaves_the_rows_untouched(tmp_path):
    """P0350-COST-FILE (FR-398 R4): without a cost file the 0.34.0 rows come back as they are."""
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    rows = [_row()]
    assert priced_rows(rows, {"r1": SimpleNamespace()}, inputs) == rows


def test_a_cost_file_prices_the_rows_and_warns_outside_the_range(tmp_path):
    """P0350-COST-FILE (FR-398): the row takes the file's time; an unanswerable one warns."""
    inputs = _inputs(tmp_path, "c001")
    case = SimpleNamespace(solver=SimpleNamespace(viscous_coupling=True), variables={})
    (priced,) = priced_rows([_row()], {"r1": case}, inputs)
    assert priced.seconds == 300.0
    assert "c001.toml" in priced.basis
    assert dataclasses.replace(priced, seconds=7.0, samples=2, basis="fitted") == _row()
    with pytest.warns(PyflightstreamWarning, match="outside the stated"):
        (unknown,) = priced_rows([_row("r2", processors=64)], {"r2": case}, inputs)
    assert unknown.seconds is None


def test_the_shipped_example_reads_and_is_synthetic():
    """P0350-COST-FILE (FR-398 R5): the example parses; the tree has no unmarked cost file."""
    example = read_cost_file(REPO / "examples" / "costs" / "c000.toml")
    assert example.flags["viscous_coupling"] == 2.0
    assert unmarked_cost_files(REPO) == []


def test_the_guard_catches_a_planted_non_synthetic_file(tmp_path):
    """P0350-COST-FILE (FR-398 R5): a measured-looking file in the tree is caught."""
    planted = tmp_path / "examples" / "costs"
    planted.mkdir(parents=True)
    (planted / "c001.toml").write_text(_FILE.replace("# synthetic test file\n", ""), "utf-8")
    (planted / "c002.toml").write_text(_FILE, "utf-8")
    assert [p.name for p in unmarked_cost_files(tmp_path)] == ["c001.toml"]
