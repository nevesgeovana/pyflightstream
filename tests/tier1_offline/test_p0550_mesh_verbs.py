"""P0550-MESH-VERBS: what running every mesh verb of 0.54.0 on synthetic geometry found.

Pipeline role: tier-1 oracle of the fixes of PFS-2187.01 to PFS-2187.03. Each test runs the
command line a user runs and reads what the user reads: the exit code, the message and the files.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace import cli as workspace_cli
from pyflightstream.workspace import plan_mark_boundaries, refine_mesh

ROOT = Path(__file__).resolve().parents[2]
SECTION = ((1.0, 0.0), (0.75, 0.04), (0.25, 0.06), (0.0, 0.0), (0.25, -0.06), (0.75, -0.04))
RINGS = 5


def _wing(path: Path) -> Path:
    """Write a wing of quads along y whose sharp trailing edge is the line x = 1, z = 0."""
    lines = [f"v {x} {float(j)} {z}" for j in range(RINGS) for x, z in SECTION]
    lines.append("g Wing")
    count = len(SECTION)
    for j in range(RINGS - 1):
        for k in range(count):
            a, b = j * count + k + 1, j * count + (k + 1) % count + 1
            lines.append(f"f {a} {b} {b + count} {a + count}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _declared(path: Path, points: str) -> None:
    """Inventory the mesh and declare its trailing edge by the points file named."""
    assert workspace_cli.main(["geometry", "inventory", str(path)]) == 0
    side = path.with_name(f"{path.name}.boundaries.toml")
    side.write_text(
        side.read_text(encoding="utf-8")
        + f'\nfs_build = "26.125"\n\n[import]\nunits = "METER"\n\n[trailing_edges.wing]\n'
        f'file = "{points}"\ntype = "STANDARD"\n',
        encoding="utf-8",
    )


def _instruction(tmp_path: Path, build: str, boundaries: str, operation: str) -> Path:
    """Write a geometry folder with one operation on a mesh source; return the folder."""
    folder = _wing(tmp_path / "inputs" / "geometries" / "box" / "body.obj").parent
    (folder / "box.geometry.toml").write_text(
        f'fs_build = "{build}"\nboundaries = {boundaries}\n\n[mesh]\nfile = "body.obj"\n'
        f'units = "METER"\n\n[trailing_edges]\nnone = true\n\n[[operations]]\n{operation}\n',
        encoding="utf-8",
    )
    return folder


@pytest.mark.requirement("FR-3288")
def test_p0550_the_points_file_the_how_to_names_is_the_one_marking_reads(tmp_path):
    mesh = _wing(tmp_path / "W1" / "W1.obj")
    assert workspace_cli.main(["geometry", "identify-te", str(mesh)]) == 0
    _declared(mesh, "W1.te.txt")
    assert plan_mark_boundaries(mesh).script
    # the other file identify-te writes is the solver's format: it is the one marking refuses
    side = mesh.with_name("W1.obj.boundaries.toml")
    side.write_text(
        side.read_text(encoding="utf-8").replace("W1.te.txt", "W1.nodes.te.txt"), encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="unit line"):
        plan_mark_boundaries(mesh)
    page = (ROOT / "docs" / "mesh" / "how-to.md").read_text(encoding="utf-8")
    assert '`[trailing_edges.<label>] file = "W1.te.txt"`' in page
    assert '`[trailing_edges.<label>] file = "W1.nodes.te.txt"`' not in page


@pytest.mark.requirement("FR-424")
def test_p0550_a_stale_declaration_names_a_way_to_a_file_that_exists(tmp_path):
    mesh = _wing(tmp_path / "W1" / "W1.obj")
    assert workspace_cli.main(["geometry", "identify-te", str(mesh)]) == 0
    _declared(mesh, "W1.te.txt")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        refine_mesh(mesh, 2)
    level = tmp_path / "W1_R2"
    texts = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    stale = [text for text in texts if "preserved trailing-edge declaration" in text]
    assert stale, texts
    assert not (level / "W1_R2.te.txt").exists()
    assert "geometry identify-te W1_R2.obj" in stale[0]
    assert "review W1_R2.te.txt" not in stale[0]


@pytest.mark.requirement("FR-1110")
@pytest.mark.parametrize(
    ("build", "boundaries", "operation", "command"),
    [
        (
            "26.100",
            '["Wing", "Band"]',
            'op = "extract_faces"\nquantity = "X"\nmin = 0.5\nsurface = "Wing"\nname = "Band"',
            "SURFACE_SELECT_BY_ID",
        ),
        (
            "26.126",
            '["Wing", "WingR"]',
            'op = "remesh_from_sections"\nsurface = "Wing"\naxis = "Y"\ncount = 3\n'
            'loft = "wing"\nname = "WingR"',
            "CAD_CREATE_AUTO_CROSS_SECTIONS",
        ),
    ],
)
def test_p0550_a_command_with_no_script_is_refused_at_the_preview(
    tmp_path, monkeypatch, capsys, build, boundaries, operation, command
):
    folder = _instruction(tmp_path, build, boundaries, operation)
    before = sorted(p.name for p in folder.iterdir())
    monkeypatch.chdir(folder)
    assert workspace_cli.main(["geometry", "build", "--build", build]) == 2
    err = capsys.readouterr().err
    assert command in err
    assert "Traceback" not in err
    assert sorted(p.name for p in folder.iterdir()) == before


@pytest.mark.requirement("FR-424")
def test_p0550_the_refine_help_reads(capsys):
    with pytest.raises(SystemExit):
        workspace_cli.main(["geometry", "refine", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "else a the" not in text
    assert "else the family's longest boundary side" in text
