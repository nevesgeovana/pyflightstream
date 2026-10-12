"""Tier 1, 0.40.0: the geometry instruction file, read and refused (FR-470).

P0400-GEOM-FILE (PFS-2081.41). One source table, the stated boundaries as the
contract, the operations undone to find the names the source makes, and every
refusal of the file itself before any solver starts. The CCS fixture is a
synthetic symmetric airfoil lofted between two stations, never a research
geometry.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases._geometry_instruction import source_names, variant_tag
from pyflightstream.workspace._geometry_instruction import read_geometry_instruction

CCS_WING = (
    'fs_build = "26.125"\nboundaries = ["WING", "AIL"]\n'
    '[ccs]\nfile = "wing_sections.csv"\nunits = "METER"\nkind = "wing"\ncomponent = 1\n'
    '[[ccs.control_surfaces]]\nname = "AIL"\nv0 = 0.5\nv1 = 0.9\nu0 = 0.25\nu1 = 0.25\n'
    "hinge_height = 0.5\nangle_deg = 0.0\nslot_gap_pct = 1.0\n"
)


def ccs_text() -> str:
    """A one-component CCS file: a symmetric airfoil at two stations."""
    points = []
    for k in range(7):
        x = 1.0 - k / 6
        points.append((x, 0.06 * math.sin(math.pi * x)))
    for k in range(1, 7):
        x = k / 6
        points.append((x, -0.06 * math.sin(math.pi * x)))
    lines = ["Aircraft;PYFS_TEST", "Units;Meter", "", "Component;CCS_WING", "LiftingSurface;true"]
    for y in (0.0, 4.0):
        lines.append("CrossSection;" + ";".join(f"{x:.4f};{y:.4f};{z:.4f}" for x, z in points))
    return "\n".join(lines) + "\n"


def write(tmp_path: Path, text: str, files: dict[str, str] | None = None, name: str = "g") -> Path:
    folder = tmp_path / "inputs" / "geometries" / name
    folder.mkdir(parents=True, exist_ok=True)
    for file, content in (files or {}).items():
        (folder / file).write_text(content, encoding="utf-8")
    path = folder / f"{name}.geometry.toml"
    path.write_text(text, encoding="utf-8")
    return path


MESH = '[mesh]\nfile = "m.obj"\nunits = "METER"\n'
OBJ = {"m.obj": "v 0 0 0\nv 1 0 0\nv 0 1 0\ng Blade\nf 1 2 3\n"}


@pytest.mark.requirement("FR-470")
def test_p0400_geom_file_each_source_reads_with_its_defaults(tmp_path):
    """P0400-GEOM-FILE (PFS-2081.41): R1 and R2, the default outputs per source."""
    ccs = read_geometry_instruction(
        write(tmp_path, CCS_WING, {"wing_sections.csv": ccs_text()}, "w")
    )
    assert (ccs.kind, ccs.outputs, ccs.name) == ("ccs", ("fsm",), "w")
    mesh = read_geometry_instruction(write(tmp_path, 'boundaries = ["Blade"]\n' + MESH, OBJ, "m"))
    assert (mesh.kind, mesh.outputs, mesh.fs_build) == ("mesh", ("obj",), None)
    create = read_geometry_instruction(
        write(
            tmp_path,
            'boundaries = ["Sphere"]\n[create]\n[[create.bodies]]\nshape = "sphere"\n'
            "center_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n",
            name="s",
        )
    )
    assert (create.kind, create.outputs) == ("create", ("fsm",))


@pytest.mark.requirement("FR-470")
def test_p0400_geom_file_the_source_names_are_the_boundaries_with_the_operations_undone(tmp_path):
    """P0400-GEOM-FILE (PFS-2081.41): R3, a rename then a copy, undone in reverse."""
    text = (
        'boundaries = ["Blade1", "Blade2", "Blade3"]\n'
        + MESH
        + '[[operations]]\nop = "rename"\nsurface = "Blade"\nto = "Blade1"\n'
        + '[[operations]]\nop = "circular_copy"\nsurface = "Blade1"\naxis = "X"\ncount = 3\n'
        + 'angle_deg = 120.0\nnames = ["Blade2", "Blade3"]\n'
    )
    instruction = read_geometry_instruction(write(tmp_path, text, OBJ))
    assert source_names(instruction) == ["Blade"]


REFUSED = [
    ("no source", 'boundaries = ["A"]\n', "exactly one source table"),
    (
        "two sources",
        'boundaries = ["A"]\n' + MESH + '[cad]\nfile = "m.obj"\n',
        "exactly one source table",
    ),
    ("unknown key", 'boundaries = ["A"]\ncolour = 1\n' + MESH, "does not read colour"),
    ("a path", 'boundaries = ["A"]\n[mesh]\nfile = "sub/m.obj"\nunits = "METER"\n', "is a path"),
    (
        "absent",
        'boundaries = ["A"]\n[mesh]\nfile = "x.obj"\nunits = "METER"\n',
        "holds no such file",
    ),
    ("step", 'boundaries = ["A"]\n[cad]\nfile = "m.step"\n', "STEP is refused"),
    ("empty outputs", 'boundaries = ["Blade"]\noutputs = []\n' + MESH, "outputs"),
    ("other output", 'boundaries = ["Blade"]\noutputs = ["stl"]\n' + MESH, "outputs"),
    ("space in a name", 'boundaries = ["Bla de"]\n' + MESH, "whitespace"),
    ("no boundaries", MESH, "boundaries"),
    (
        "units OTHER",
        'boundaries = ["Blade"]\n[mesh]\nfile = "m.obj"\nunits = "OTHER"\n',
        "names no length",
    ),
    (
        "translate",
        'boundaries = ["Blade"]\n'
        + MESH
        + '[[operations]]\nop = "translate"\nvector = [1.0, 0.0, 0.0]\n',
        "TRANSLATE and\nROTATE|stay in the run",
    ),
    (
        "rotate",
        'boundaries = ["Blade"]\n'
        + MESH
        + '[[operations]]\nop = "rotate"\naxis = "X"\nangle_deg = 5.0\n',
        "stay in the run",
    ),
    (
        "names that do not follow",
        'boundaries = ["Blade", "Other"]\n'
        + MESH
        + '[[operations]]\nop = "rename"\nsurface = "Blade"\nto = "X"\n',
        "names",
    ),
    (
        "sweep off a wing",
        'boundaries = ["Blade"]\n' + MESH + '[sweep]\ncontrol_surface = "AIL"\nangle_deg = [1.0]\n',
        "sweep",
    ),
]


@pytest.mark.requirement("FR-470")
@pytest.mark.parametrize(("label", "text", "words"), REFUSED, ids=[case[0] for case in REFUSED])
def test_p0400_geom_file_every_refusal_names_the_file(tmp_path, label, text, words):
    """P0400-GEOM-FILE (PFS-2081.41): R6, each refused before any solver starts."""
    files = dict(OBJ)
    files["m.step"] = "x"
    path = write(tmp_path, text, files)
    with pytest.raises(InputArtifactError) as raised:
        read_geometry_instruction(path)
    assert str(path) in str(raised.value)
    import re

    assert re.search(words, str(raised.value)), str(raised.value)


@pytest.mark.requirement("FR-470")
def test_p0400_geom_file_the_ccs_table_keeps_the_sidecars_refusals(tmp_path):
    """P0400-GEOM-FILE (PFS-2081.41): R2 and R6, the REAL form and the file unit."""
    files = {"wing_sections.csv": ccs_text()}
    real = CCS_WING.replace("slot_gap_pct = 1.0\n", 'slot_gap_pct = 1.0\nspace = "REAL"\n')
    with pytest.raises(InputArtifactError, match="REAL"):
        read_geometry_instruction(write(tmp_path, real, files, "r"))
    file_unit = CCS_WING.replace('units = "METER"', 'units = "FILE"')
    with pytest.raises(InputArtifactError, match="FILE"):
        read_geometry_instruction(write(tmp_path, file_unit, files, "f"))
    trailing = CCS_WING + '[trailing_edges]\ndetect = "auto"\n'
    with pytest.raises(InputArtifactError, match="mark\\s+their own"):
        read_geometry_instruction(write(tmp_path, trailing, files, "t"))


@pytest.mark.requirement("FR-470")
def test_p0400_geom_file_a_second_instruction_in_one_folder_is_refused(tmp_path):
    """P0400-GEOM-FILE (PFS-2081.41): the folder holds one instruction."""
    from pyflightstream.workspace._geometry_build import locate_instruction

    path = write(tmp_path, 'boundaries = ["Blade"]\n' + MESH, OBJ)
    (path.parent / "other.geometry.toml").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="holds 2 instructions"):
        locate_instruction(None, path.parent)


def test_p0400_geom_file_the_variant_tag_keeps_tenths_and_a_sign():
    """P0400-GEOM-FILE (PFS-2081.41): the tag a sweep folder carries (FR-472)."""
    assert [variant_tag("AIL", a) for a in (-10.0, 0.0, 10.0, 2.5)] == [
        "AIL-100",
        "AIL+000",
        "AIL+100",
        "AIL+025",
    ]
