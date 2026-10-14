"""Build disjoint sweep subsets, then rebuild with and without overwrite.

The runners use existing offline fixtures; no licensed solver is called.
"""

# ruff: noqa: N999 - The lane contract prescribes the rfixR5 filename.

from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import _geometry_build
from pyflightstream.workspace._geometry_build import (
    GeometryBuildError,
    SolverOutcome,
    apply_geometry_build,
    plan_geometry_build,
)
from tests.tier1_offline.test_p0400_geometry_build import verified_registry
from tests.tier1_offline.test_p0400_geometry_complete import _body_runner, _sweep
from tests.tier1_offline.test_regression_qa_tools import _GAPPROBES_SPECS__QUAD_BLOCK as QUAD_BLOCK


def _plan(folder, only):
    return plan_geometry_build(folder, cwd=folder.parent, only=only, registry=verified_registry())


@pytest.mark.requirement("FR-471", "FR-472")
@pytest.mark.parametrize("fail", [False, True])
def test_p0400_rfixr5_existing_overlay_refuses_disjoint_subset(tmp_path, fail):
    """P0400-RFIXR5-117: refuse before a successful or failing second runner."""
    _, folder = _sweep(tmp_path)
    apply_geometry_build(_plan(folder, ("Base-100",)), runner=_body_runner())
    target = folder / "wing.sweep.vtk"
    before = target.read_bytes()
    calls = []

    def run(script, work):
        calls.append(script)
        if fail:
            return SolverOutcome(True, 1, 0, "failure", "exited 1")
        return _body_runner()(script, work)

    try:
        apply_geometry_build(_plan(folder, ("Base+100",)), runner=run)
    except (InputArtifactError, GeometryBuildError) as error:
        assert isinstance(error, InputArtifactError)
        assert "--overwrite" in str(error)
    else:
        pytest.fail("existing overlay was replaced without overwrite")
    assert target.read_bytes() == before
    assert not calls


@pytest.mark.requirement("FR-471", "FR-472")
@pytest.mark.parametrize("failure", ["solver", "writer", "none"])
def test_p0400_rfixr5_overwrite_retains_previous_overlay(tmp_path, monkeypatch, failure):
    """P0400-RFIXR5-117: preserve old evidence and publish only a complete overlay."""
    _, folder = _sweep(tmp_path)
    target = folder / "wing.sweep.vtk"
    target.write_bytes(b"old overlay")
    previous = target.with_name(target.name + ".previous")
    previous.write_bytes(b"older overlay")

    def broken_writer(path, *args):
        path.write_bytes(b"incomplete")
        raise OSError("synthetic write failure")

    if failure == "writer":
        monkeypatch.setattr(_geometry_build, "write_sweep_vtk", broken_writer)
    run = (
        _body_runner()
        if failure != "solver"
        else lambda s, w: SolverOutcome(True, 1, 0, "failure", "exited 1")
    )
    if failure == "none":
        apply_geometry_build(_plan(folder, ("Base+100",)), runner=run, overwrite=True)
        assert b"POLYGONS 24" in target.read_bytes()
    else:
        with pytest.raises(GeometryBuildError):
            apply_geometry_build(_plan(folder, ("Base+100",)), runner=run, overwrite=True)
        assert not target.exists()
    assert previous.read_bytes() == b"older overlay"
    archived = target.with_name(target.name + ".previous.1")
    assert archived.is_file()
    assert archived.read_bytes() == b"old overlay"
    assert not list(folder.glob("*.pending*"))


@pytest.mark.requirement("FR-472")
@pytest.mark.parametrize("outputs", ['["obj"]', '["fsm"]'])
def test_p0400_rfixr5_quad_overlay(tmp_path, outputs):
    """P0400-RFIXR5-118: quadrilateral fallback keeps only the named surface and ordinal."""
    _, folder = _sweep(tmp_path)
    instruction = folder / "wing.geometry.toml"
    instruction.write_text(
        "outputs = "
        + outputs
        + chr(10)
        + instruction.read_text().replace('["Body", "Base"]', '["Base"]'),
        encoding="utf-8",
    )

    def run(script: Path, work: Path):
        name = script.name.removesuffix(".build.txt")
        (work / f"{name}.fsm").write_text(QUAD_BLOCK.replace("Wing", "Base"))
        rows = [
            "v 0 0 0",
            "v 1 0 0",
            "v 1 1 0",
            "v 0 1 0",
            "v 3 0 0",
            "v 4 0 0",
            "v 3 1 0",
            "g Body",
            "f 5 6 7",
            "g Base",
            "f 1 2 3 4",
        ]
        (work / f"{name}.obj").write_text(chr(10).join(rows) + chr(10))
        return SolverOutcome(False, 0, 0, "log", "")

    try:
        built = apply_geometry_build(_plan(folder, ("Base+100",)), runner=run)
    except GeometryBuildError as error:
        pytest.fail(str(error))
    assert built[0].passed
    text = (folder / "wing.sweep.vtk").read_text()
    assert "POLYGONS 1 5" in text
    assert chr(10).join(["LOOKUP_TABLE default", "3", "FIELD tags 1"]) in text
    assert text.split(" string" + chr(10))[1].splitlines() == ["Base+100"]


@pytest.mark.requirement("FR-471")
@pytest.mark.parametrize("suffix", [".build.log", ".build.txt", ".boundaries.toml"])
def test_p0400_rfixr5_preflight_all_promoted_files(tmp_path, suffix):
    """P0400-SWEEP-01: an unrecorded generated file is refused before the runner."""
    _, folder = _sweep(tmp_path)
    # A nonsweep base folder can contain user files without a build record.
    instruction = folder / "wing.geometry.toml"
    instruction.write_text(instruction.read_text().split("[sweep]")[0])
    target = folder / ("wing" + suffix)
    target.write_bytes(b"user evidence")
    calls = []

    def run(script, work):
        calls.append(script)
        return _body_runner()(script, work)

    try:
        apply_geometry_build(_plan(folder, ()), runner=run)
    except InputArtifactError:
        pass
    else:
        pytest.fail("existing promoted file was not refused")
    assert not calls
    assert target.read_bytes() == b"user evidence"


@pytest.mark.requirement("FR-471", "FR-472")
@pytest.mark.parametrize("failure", ["solver", "overlay", "audit"])
def test_p0400_rfixr5_sweep_failure_preserves_variant_outputs(tmp_path, monkeypatch, failure):
    """P0400-SWEEP-02: do not promote a replacement until the sweep build succeeds."""
    _, folder = _sweep(tmp_path)
    apply_geometry_build(_plan(folder, ("Base-100",)), runner=_body_runner())
    variant = folder.with_name("wing_Base-100")
    before = {path.name: path.read_bytes() for path in variant.iterdir() if path.is_file()}

    def run(script, work):
        if failure == "solver" and "Base+100" in script.name:
            return SolverOutcome(True, 1, 0, "failure", "exited 1")
        result = _body_runner()(script, work)
        if failure == "audit" and "Base+100" in script.name:
            obj = work / script.name.replace(".build.txt", ".obj")
            with obj.open("a") as handle:
                handle.write("f 1 1 2" + chr(10))
        return result._replace(log="new build log")

    def broken_writer(*args):
        raise OSError("synthetic overlay failure")

    if failure == "overlay":
        monkeypatch.setattr(_geometry_build, "write_sweep_vtk", broken_writer)
    plan = _plan(folder, ("Base-100", "Base+100"))
    if failure == "audit":
        built = apply_geometry_build(plan, runner=run, overwrite=True)
        assert [item.passed for item in built] == [True, False]
        assert not (folder / "wing.sweep.vtk").exists()
    else:
        with pytest.raises(GeometryBuildError):
            apply_geometry_build(plan, runner=run, overwrite=True)
    assert {path.name: path.read_bytes() for path in variant.iterdir() if path.is_file()} == before
