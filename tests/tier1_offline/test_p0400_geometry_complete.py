"""Tier 1, 0.40.0: the rest of the geometry design (FR-471 R10, FR-472 R5 to R7, FR-473 R5).

P0400-GEOM-ROWS, P0400-GEOM-PARALLEL, P0400-GEOM-OVERLAY, P0400-GEOM-MIRROR and
P0400-GEOM-CARRY (PFS-2081.41). The sweep is built on the committed
solver-written ``20_BODY.fsm`` (boundaries ``Body`` and ``Base``), standing for
a wing ``Body`` with a control surface ``Base``; the runner stands in for the
solver as in ``test_p0400_geometry_build.py``.
"""

from __future__ import annotations

import json
import shutil
import threading
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace._geometry_build import (
    SolverOutcome,
    apply_geometry_build,
    plan_geometry_build,
)
from pyflightstream.workspace._geometry_record import judge_the_row_geometry
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0400_geometry_build import (
    MESH_INSTRUCTION,
    WING_FSM,
    geometry,
    runner,
    verified_registry,
    wing_obj,
    workspace,
)
from tests.tier1_offline.test_p0400_geometry_instruction import ccs_text

BODY_FSM = WING_FSM.with_name("20_BODY.fsm")

SWEEP = (
    'fs_build = "26.125"\nboundaries = ["Body", "Base"]\n'
    '[ccs]\nfile = "wing_sections.csv"\nunits = "METER"\nkind = "wing"\ncomponent = 1\n'
    "mark_trailing_edges = false\n"
    '[[ccs.control_surfaces]]\nname = "Base"\nv0 = 0.5\nv1 = 0.9\nu0 = 0.25\nu1 = 0.25\n'
    "hinge_height = 0.5\nangle_deg = 0.0\nslot_gap_pct = 1.0\n"
    '[sweep]\ncontrol_surface = "Base"\nangle_deg = [-10.0, 0.0, 10.0]\n'
)

HEADER = (
    "POL  | HIDDEN | RUN | AIRCRAFT  | CONFIGURATION | DESCRIPTION   | FLIGHT_CONDITION"
    "                 | SWEEP_VALUES | GEOMETRY | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS"
    " | NCPUS | WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES"
)
ROW = (
    "9401 |    1   |  1  | DemoWing  | clean         | LOFTED_WING   | MACH:0.15, REmi:2.0, "
    "ALPHA:sweep | 0.0,4.0,8.0  | wing.fsm | r040 | s040 | p040  | NONE     | -              | 8"
    "     | 1h       | 26.125   | steady   | -"
)


def _sweep(tmp_path):
    root = workspace(tmp_path)
    folder = geometry(root, "wing", SWEEP, source=None)
    (folder / "wing_sections.csv").write_text(ccs_text(), encoding="utf-8")
    return root, folder


def _body_runner(fail_once: str | None = None):
    """A runner saving the two-boundary body; ``fail_once`` fails that variant's first run."""
    failed: set[str] = set()
    lock = threading.Lock()

    def run(script: Path, work: Path) -> SolverOutcome:
        name = script.name.removesuffix(".build.txt")
        with lock:
            fail = fail_once is not None and name.endswith(fail_once) and name not in failed
            failed.add(name)
        if fail:
            return SolverOutcome(True, 1, 1.0, "licence refused", "exited 1")
        shutil.copyfile(BODY_FSM, work / f"{name}.fsm")
        wing_obj(work / f"{name}.obj", group="Body")
        return SolverOutcome(False, 0, 1.0, "log", "")

    return run


@pytest.mark.requirement("FR-472")
def test_p0400_geom_rows_one_row_per_variant_copied_from_the_template(
    tmp_path, monkeypatch, capsys
):
    """P0400-GEOM-ROWS (PFS-2081.41): R5, three cells set per row; matrix untouched."""
    _, folder = _sweep(tmp_path)
    matrix = tmp_path / "m.fs"
    matrix.write_text(HEADER + "\n" + "-" * 40 + "\n" + ROW + "\n", encoding="utf-8")
    before = matrix.read_bytes()
    monkeypatch.chdir(folder.parent)
    assert main(["geometry", "build", "wing", "--rows", "9401", "--matrix", str(matrix)]) == 0
    out = capsys.readouterr().out
    rows = [
        line.strip()
        for line in out.splitlines()
        if line.strip().startswith(("9402", "9403", "9404"))
    ]
    assert len(rows) == 3
    cells = [[cell.strip() for cell in row.split("|")] for row in rows]
    assert [c[4] for c in cells] == ["Base-100", "Base+000", "Base+100"]
    assert [c[8] for c in cells] == ["wing_Base-100.fsm", "wing_Base+000.fsm", "wing_Base+100.fsm"]
    assert all(c[3] == "DemoWing" and c[12] == "NONE" for c in cells)
    assert matrix.read_bytes() == before


@pytest.mark.requirement("FR-472")
def test_p0400_geom_rows_refusals(tmp_path, monkeypatch, capsys):
    """P0400-GEOM-ROWS (PFS-2081.41): R5, a POL the matrix lacks, and --rows without --matrix."""
    _, folder = _sweep(tmp_path)
    matrix = tmp_path / "m.fs"
    matrix.write_text(HEADER + "\n" + ROW + "\n", encoding="utf-8")
    monkeypatch.chdir(folder.parent)
    assert main(["geometry", "build", "wing", "--rows", "1", "--matrix", str(matrix)]) == 2
    assert "holds no row POL 1" in capsys.readouterr().err
    assert main(["geometry", "build", "wing", "--rows", "9401"]) == 2
    assert "--matrix" in capsys.readouterr().err


@pytest.mark.requirement("FR-472")
def test_p0400_geom_parallel_builds_every_variant_and_reruns_a_failed_one_alone(
    tmp_path, monkeypatch
):
    """P0400-GEOM-PARALLEL (PFS-2081.41): R6, two at once; the refused variant runs again alone."""
    from tests.tier1_offline.test_p0400_rfixB_geometry import (
        test_p0400_rfixb_parallel_calls_overlap_and_retry_runs_alone as overlap_proof,
    )

    overlap_proof(tmp_path, monkeypatch)
    plan = plan_geometry_build(
        "wing", cwd=tmp_path / "ws" / "inputs" / "geometries", registry=verified_registry()
    )
    with pytest.raises(InputArtifactError, match=r"parallel \(CLI: --parallel\) 3"):
        apply_geometry_build(plan, runner=_body_runner(), parallel=3, overwrite=True)


@pytest.mark.requirement("FR-472")
def test_p0400_geom_overlay_holds_the_control_surface_of_every_variant(tmp_path):
    """P0400-GEOM-OVERLAY (PFS-2081.41): R7, one file in the base folder, tagged per variant."""
    _, folder = _sweep(tmp_path)
    plan = plan_geometry_build("wing", cwd=folder.parent, registry=verified_registry())
    apply_geometry_build(plan, runner=_body_runner())
    text = (folder / "wing.sweep.vtk").read_text(encoding="utf-8")
    assert "SCALARS variant int 1" in text
    assert "tags 1 3 string\nBase-100\nBase+000\nBase+100" in text
    cells = int(text.split("CELL_DATA ")[1].split()[0])
    variants = text.split("LOOKUP_TABLE default\n")[1].split("\nFIELD")[0].split()
    assert len(variants) == cells and set(variants) == {"1", "2", "3"}


@pytest.mark.requirement("FR-473")
def test_p0400_geom_mirror_of_a_deflected_body_is_warned(tmp_path):
    """P0400-GEOM-MIRROR (PFS-2081.41): R5, MIRROR over a nonzero angle; NONE and 0 silent."""
    _, folder = _sweep(tmp_path)
    plan = plan_geometry_build("wing", cwd=folder.parent, registry=verified_registry())
    apply_geometry_build(plan, runner=_body_runner())
    record = json.loads(
        (folder.parent / "wing_Base+100" / "wing_Base+100.build.json").read_text(encoding="utf-8")
    )
    assert record["control_surfaces"] == [{"name": "Base", "angle_deg": 10.0}]

    def said(name: str, symmetry: str) -> list[str]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            judge_the_row_geometry(
                folder.parent / name / f"{name}.fsm",
                "9413",
                fs_build="26.125",
                mesh_import=None,
                symmetry=symmetry,
            )
        return [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]

    assert any(
        "SYMMETRY MIRROR" in text and "Base at 10.0 deg" in text
        for text in said("wing_Base+100", "MIRROR")
    )
    assert not any("SYMMETRY MIRROR" in text for text in said("wing_Base+100", "NONE"))
    assert not any("SYMMETRY MIRROR" in text for text in said("wing_Base+000", "MIRROR"))


@pytest.mark.requirement("FR-471")
def test_p0400_geom_carry_the_runs_operations_into_the_built_mesh_sidecar(tmp_path):
    """P0400-GEOM-CARRY (PFS-2081.41): R10, from the source's sidecar, then kept by a rebuild."""
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    (folder / "src.boundaries.toml").write_text(
        'boundaries = ["Wing"]\n[import]\nunits = "METER"\n'
        '[[import.operations]]\nop = "translate"\nvector = [1.0, 0.0, 0.0]\n'
        '[wake_termination]\ndetect = "auto"\n',
        encoding="utf-8",
    )
    plan = plan_geometry_build(folder, registry=verified_registry())
    (built,) = apply_geometry_build(plan, runner=runner())
    sidecar = folder.with_name("wing_obj") / "wing_obj.boundaries.toml"
    text = sidecar.read_text(encoding="utf-8")
    assert 'op = "translate"' in text and "[wake_termination]" in text
    assert 'detect = "auto"' in text.split("[trailing_edges]")[1]
    assert any("carried over the sidecar operations translate" in note for note in built.notes)
    sidecar.write_text(
        text.replace('op = "translate"', 'op = "rotate"').replace(
            "vector = [1.0, 0.0, 0.0]", 'axis = "X"\nangle_deg = 5.0'
        ),
        encoding="utf-8",
    )
    apply_geometry_build(plan, runner=runner(), overwrite=True)
    rebuilt = sidecar.read_text(encoding="utf-8")
    assert 'op = "rotate"' in rebuilt and 'op = "translate"' not in rebuilt
