"""A geometry build is one transaction: staged, verified, then promoted whole or not at all.

P0400-RFIXR6-SWEEP (PFS-2081.120, REL6-002; FR-471 R3, R7, R8 and FR-472). Every
record a build leaves names files that exist beside it, wherever the build
stopped: promoted into the geometry folders after a success, kept in the
``.partial`` folders after a solver, audit or overlay failure (the passing
siblings of a failed sweep included), and absent rather than wrong after an
interruption. The command offers ``geometry accept`` for promoted geometries
only, and ``accept`` refuses a partial folder. The runners stand in for the
solver on the committed fixtures; no licensed solver is called.
"""

# ruff: noqa: N999 - the lane contract prescribes the rfixR6 filename.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.run import _cli_geometry
from pyflightstream.workspace import _geometry_build
from pyflightstream.workspace._geometry_build import (
    GeometryBuildError,
    SolverOutcome,
    apply_geometry_build,
    plan_geometry_build,
)
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0400_geometry_build import verified_registry
from tests.tier1_offline.test_p0400_geometry_complete import _body_runner, _sweep

TAGS = ("Base-100", "Base+000", "Base+100")


def _with_outputs(folder: Path, outputs: str) -> None:
    instruction = folder / "wing.geometry.toml"
    instruction.write_text(f"outputs = {outputs}\n" + instruction.read_text(), encoding="utf-8")


def _plan(folder: Path, only: tuple[str, ...] = ()):
    return plan_geometry_build(folder, cwd=folder.parent, only=only, registry=verified_registry())


def _runner(failure: str | None = None, on: str = "Base+100"):
    """The body runner; ``failure`` fails the solver of, or the audit of, the variant ``on``."""
    body = _body_runner()

    def run(script: Path, work: Path) -> SolverOutcome:
        if failure == "solver" and on in script.name:
            return SolverOutcome(True, 1, 0.0, "licence refused", "exited 1")
        outcome = body(script, work)
        if failure == "audit" and on in script.name:
            with (work / script.name.replace(".build.txt", ".obj")).open("a") as handle:
                handle.write("f 1 1 2\n")
        return outcome

    return run


def _resolving(record_path: Path) -> dict:
    """Return the record after checking that every file it names is beside it, as hashed."""
    record = json.loads(record_path.read_text(encoding="utf-8"))
    base = record_path.parent
    for item in (record["instruction"], *record["inputs"], record["script"], *record["outputs"]):
        path = base / item["file"]
        assert path.is_file(), f"{record_path.name} names {item['file']}, absent from {base}"
        assert file_sha256(path) == item["sha256"], path
    if record["audit"]["file"] is not None:
        audit = base / record["audit"]["file"]
        assert audit.is_file(), f"{record_path.name} names the audit {audit.name}, absent"
    return record


def _records_under(geometries: Path) -> list[Path]:
    return sorted(
        path for path in geometries.rglob("*.build.json") if ".previous" not in path.parent.name
    )


@pytest.mark.requirement("FR-471", "FR-472")
@pytest.mark.parametrize("outputs", ['["fsm"]', '["obj"]', '["fsm", "obj"]'])
@pytest.mark.parametrize("failure", ["solver", "audit", "overlay"])
def test_p0400_rfixr6_a_failed_sweep_keeps_every_record_true_to_its_partial_folder(
    tmp_path, monkeypatch, outputs, failure
):
    """P0400-RFIXR6-SWEEP: nothing promoted, and each kept record resolves where it is kept."""
    _, folder = _sweep(tmp_path)
    _with_outputs(folder, outputs)
    if failure == "overlay":

        def broken(*args):
            raise OSError("synthetic overlay failure")

        monkeypatch.setattr(_geometry_build, "write_sweep_vtk", broken)
    plan = _plan(folder, ("Base-100", "Base+100"))
    run = _runner(failure)
    if failure == "audit":
        built = apply_geometry_build(plan, runner=run)
    else:
        with pytest.raises(GeometryBuildError):
            apply_geometry_build(plan, runner=run)
    geometries = folder.parent
    for tag in ("Base-100", "Base+100"):
        assert not geometries.joinpath(f"wing_{tag}").exists(), f"{tag} was promoted"
        assert not geometries.joinpath(f"wing_{tag}_obj").exists(), f"{tag} mesh was promoted"
    assert not (folder / "wing.sweep.vtk").exists()
    kept = _records_under(geometries)
    expected = {"Base-100"} if failure == "solver" else {"Base-100", "Base+100"}
    assert {path.parent.name for path in kept} == {f"wing_{tag}.partial" for tag in expected}
    for record_path in kept:
        _resolving(record_path)
    if failure == "audit":
        assert [item.passed for item in built] == [True, False]
        assert [getattr(item, "promoted", None) for item in built] == [False, False]
        assert [item.folder.name for item in built] == [
            "wing_Base-100.partial",
            "wing_Base+100.partial",
        ]


@pytest.mark.requirement("FR-471", "FR-472")
@pytest.mark.parametrize("failure", ["audit", "solver"])
def test_p0400_rfixr6_the_command_never_offers_to_accept_an_unpromoted_geometry(
    tmp_path, monkeypatch, capsys, failure
):
    """P0400-RFIXR6-SWEEP: the CLI names what was kept and why, and accept refuses it."""
    root, folder = _sweep(tmp_path)
    original = _cli_geometry.plan_geometry_build
    monkeypatch.setattr(
        _cli_geometry,
        "plan_geometry_build",
        lambda *a, **k: original(*a, **k, registry=verified_registry()),
    )
    monkeypatch.setattr(_cli_geometry, "_runner", lambda executable: _runner(failure))
    monkeypatch.chdir(folder.parent)
    code = main(["geometry", "build", "wing", "--apply", "--only", "Base-100,Base+100"])
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert code == (1 if failure == "audit" else 3)
    assert "geometry accept" not in text
    if failure == "audit":
        kept = folder.parent / "wing_Base-100.partial"
        assert str(kept) in text
        assert "not promoted" in text
        assert "Base+100" in text.split("not promoted", 1)[1].splitlines()[0]
    capsys.readouterr()
    workspace = ["--workspace", str(root)]
    assert main(["geometry", "accept", "wing_Base-100.partial", *workspace]) == 2
    record = folder.parent / "wing_Base-100.partial" / "wing_Base-100.build.json"
    assert json.loads(record.read_text(encoding="utf-8"))["inspected"] is None


@pytest.mark.requirement("FR-471", "FR-472")
@pytest.mark.parametrize("outputs", ['["fsm"]', '["obj"]', '["fsm", "obj"]'])
def test_p0400_rfixr6_a_built_sweep_promotes_every_record_true_to_its_folder(
    tmp_path, monkeypatch, capsys, outputs
):
    """P0400-RFIXR6-SWEEP: success leaves no partial folder, and accept is offered for each."""
    _, folder = _sweep(tmp_path)
    _with_outputs(folder, outputs)
    original = _cli_geometry.plan_geometry_build
    monkeypatch.setattr(
        _cli_geometry,
        "plan_geometry_build",
        lambda *a, **k: original(*a, **k, registry=verified_registry()),
    )
    monkeypatch.setattr(_cli_geometry, "_runner", lambda executable: _runner())
    monkeypatch.chdir(folder.parent)
    assert main(["geometry", "build", "wing", "--apply"]) == 0
    out = capsys.readouterr().out
    assert (
        "accept after inspection: pyfs-workspace geometry accept "
        + ",".join(f"wing_{tag}" for tag in TAGS)
        in out
    )
    geometries = folder.parent
    assert not list(geometries.glob("*.partial"))
    assert (folder / "wing.sweep.vtk").is_file()
    records = _records_under(geometries)
    expected = {f"wing_{tag}" for tag in TAGS}
    if "obj" in outputs and "fsm" in outputs:
        expected |= {f"wing_{tag}_obj" for tag in TAGS}
    assert {path.parent.name for path in records} == expected
    for record_path in records:
        _resolving(record_path)


@pytest.mark.requirement("FR-471", "FR-472")
def test_p0400_rfixr6_an_interrupted_promotion_leaves_no_false_record_and_recovers(
    tmp_path, monkeypatch
):
    """P0400-RFIXR6-SWEEP: a record is written last and the overlay after every variant."""
    _, folder = _sweep(tmp_path)
    _with_outputs(folder, '["fsm", "obj"]')
    original = _geometry_build._move_into
    calls = []

    def interrupted(sources, destination, overwrite):
        calls.append(destination)
        if len(calls) == 2:
            raise KeyboardInterrupt("synthetic interruption during promotion")
        return original(sources, destination, overwrite)

    monkeypatch.setattr(_geometry_build, "_move_into", interrupted)
    with pytest.raises(KeyboardInterrupt):
        apply_geometry_build(_plan(folder), runner=_runner())
    geometries = folder.parent
    assert not (folder / "wing.sweep.vtk").exists(), "the overlay claims an unpromoted sweep"
    for record_path in _records_under(geometries):
        _resolving(record_path)
    assert not list(geometries.glob("*.pending*")) and not list(folder.glob("*.pending*"))
    monkeypatch.setattr(_geometry_build, "_move_into", original)
    built = apply_geometry_build(_plan(folder), runner=_runner(), overwrite=True)
    assert all(getattr(item, "promoted", True) and item.passed for item in built)
    assert (folder / "wing.sweep.vtk").is_file()
    records = _records_under(geometries)
    assert {path.parent.name for path in records} == {
        f"wing_{tag}{end}" for tag in TAGS for end in ("", "_obj")
    }
    for record_path in records:
        _resolving(record_path)
