"""Tier 1, 0.34.0: the thin-blade command and its --boundary option (FR-330, P0340-THIN-BLADE).

Pipeline role: quality gate on ``pyfs-matrix degenerate --kind thin-blade``
(FR-330 R1, R7 and R9): the parser of the family, the command that runs it, its
refusals by name, the selection of the blade among the bodies of one file, and
the two places that must name it (the generated command-line reference and the
cheatsheet). The geometry itself is the library core's, held by
``test_p0340_thin_blade.py``; what is held here is the wiring, so the blades
are the synthetic ones that file builds, and the one saved simulation is the
tier-3 library's pusher, which holds three boundaries in one file.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy
import pytest

from pyflightstream.run import cli
from pyflightstream.workspace import InputArtifactError, _degenerate
from pyflightstream.workspace._degenerate import derive_thin_blade, thin_blade_path
from pyflightstream.workspace.sidecars import read_inventory
from tests.tier1_offline.test_p0340_thin_blade import _blade, _read_obj, _sha, _write_obj

REPO = Path(__file__).resolve().parents[2]
_LIBRARY = REPO / "tests" / "tier3_licensed" / "inputs" / "geometries"

#: A box of side 0.3 about the origin: a spinner the blade grows out of.
_BOX = [[x, y, z] for x in (-0.15, 0.15) for y in (-0.15, 0.15) for z in (-0.15, 0.15)]
_BOX_FACES = [
    [0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
    [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3],
]  # fmt: skip


def _with_spinner(path: Path, *, boundary: str = "Blade1") -> Path:
    """Write an OBJ of a spinner first and the blade after it, two groups, shared numbering."""
    vertices, faces = _blade()
    lines = ["o Spinner"]
    lines += [f"v {x!r} {y!r} {z!r}" for x, y, z in _BOX]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in _BOX_FACES]
    lines += [f"o {boundary}"]
    lines += [f"v {x!r} {y!r} {z!r}" for x, y, z in vertices.tolist()]
    lines += [f"f {a + 9} {b + 9} {c + 9}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    """Run ``pyfs-matrix`` on ``argv``; return its exit code and what it printed."""
    code = cli.main(list(argv))
    seen = capsys.readouterr()
    return code, seen.out, seen.err


def test_the_command_derives_the_thin_blade_beside_the_source(tmp_path, capsys):
    """FR-330 R1 and R4 (P0340-THIN-BLADE): the command writes what the library writes,
    beside the source, names both files, and leaves the source's bytes alone."""
    # P0340-THIN-BLADE, FR-330 R1: pyfs-matrix degenerate GEOMETRY --kind thin-blade --root-offset.
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "blade.obj", vertices, faces)
    before = _sha(source)
    code, out, err = _run(
        capsys, "degenerate", str(source), "--kind", "thin-blade", "--root-offset", "0.05"
    )
    assert code == 0, err
    mesh = thin_blade_path(source)
    assert out.splitlines() == [str(mesh), str(mesh.with_name("blade_thin_blade.boundaries.toml"))]
    assert "the root moved outward by 0.05" in err
    assert _sha(source) == before and read_inventory(tmp_path / "blade_thin_blade.boundaries.toml")
    # The same bytes as the library function writes for the same offset.
    other = tmp_path / "again"
    other.mkdir()
    twin = _write_obj(other / "blade.obj", vertices, faces)
    assert _sha(derive_thin_blade(twin, root_offset=0.05).mesh) == _sha(mesh)


def test_the_kind_defaults_to_thin_blade_and_no_other_kind_is_accepted(tmp_path, capsys):
    """FR-330 R1 (P0340-THIN-BLADE): thin-blade is the one kind and the default of --kind."""
    # P0340-THIN-BLADE, FR-330 R1: --kind thin-blade, the default; a later kind is a new choice.
    with pytest.raises(SystemExit) as helped:
        cli.main(["degenerate", "--help"])
    assert helped.value.code == 0
    shown = " ".join(capsys.readouterr().out.split())
    assert "--kind {thin-blade}" in shown and "(default: thin-blade)" in shown
    assert "--root-offset LENGTH" in shown and "--boundary NAME" in shown
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "blade.obj", vertices, faces)
    with pytest.raises(SystemExit) as refused:
        cli.main(["degenerate", str(source), "--kind", "fat-blade", "--root-offset", "0.05"])
    assert refused.value.code == 2
    assert "invalid choice: 'fat-blade'" in capsys.readouterr().err
    assert not thin_blade_path(source).exists()


def test_a_missing_or_unusable_root_offset_is_refused_by_name(tmp_path, capsys):
    """FR-330 R1, R3 and R6 (P0340-THIN-BLADE): the offset is required, and one that is not a
    positive length is refused naming the file, with nothing written."""
    # P0340-THIN-BLADE, FR-330 R3: the command requires --root-offset, a positive length.
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "blade.obj", vertices, faces)
    with pytest.raises(SystemExit) as missing:
        cli.main(["degenerate", str(source)])
    assert missing.value.code == 2 and "--root-offset" in capsys.readouterr().err
    for bad in ("-0.1", "0", "nan"):
        code, out, err = _run(capsys, "degenerate", str(source), "--root-offset", bad)
        assert code == 2 and out == ""
        assert str(source) in err and "not a positive length" in err, err
    code, _, err = _run(capsys, "degenerate", str(source), "--root-offset", "5")
    assert code == 2 and str(source) in err and "a length shorter than the blade" in err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["blade.obj"]


def test_a_mesh_the_command_cannot_use_is_refused_by_name_and_nothing_is_written(tmp_path, capsys):
    """FR-330 R4 and R6 (P0340-THIN-BLADE): an absent file, a file of another kind and an
    existing output without --overwrite exit 2 naming the file and the reason."""
    # P0340-THIN-BLADE, FR-330 R6: refusals by name, exit 2, standard error, nothing written.
    absent = tmp_path / "absent.obj"
    code, out, err = _run(capsys, "degenerate", str(absent), "--root-offset", "0.05")
    assert code == 2 and out == "" and str(absent) in err and "it is not a file" in err
    wrong = tmp_path / "blade.stl"
    wrong.write_text("solid\n", encoding="utf-8")
    code, _, err = _run(capsys, "degenerate", str(wrong), "--root-offset", "0.05")
    assert code == 2 and str(wrong) in err and "saved simulation (.fsm) or an OBJ" in err
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "blade.obj", vertices, faces)
    assert _run(capsys, "degenerate", str(source), "--root-offset", "0.05")[0] == 0
    written = _sha(thin_blade_path(source))
    code, out, err = _run(capsys, "degenerate", str(source), "--root-offset", "0.07")
    assert code == 2 and out == ""
    assert "already exists; pass overwrite" in err and "Nothing was written" in err
    assert _sha(thin_blade_path(source)) == written
    code, _, _ = _run(capsys, "degenerate", str(source), "--root-offset", "0.07", "--overwrite")
    assert code == 0 and _sha(thin_blade_path(source)) != written


def test_a_file_holding_several_bodies_is_refused_until_the_blade_is_named(tmp_path, capsys):
    """FR-330 R6 and R9 (P0340-THIN-BLADE): without --boundary the file with a spinner is
    refused naming its groups and the option; with it, the blade alone is derived, equal to the
    sheet of the blade file alone, under a name that carries the boundary."""
    # P0340-THIN-BLADE, FR-330 R9: --boundary NAME selects the blade of a file of several bodies.
    source = _with_spinner(tmp_path / "rotor.obj")
    code, out, err = _run(capsys, "degenerate", str(source), "--root-offset", "0.05")
    assert code == 2 and out == ""
    assert "Spinner, Blade1" in err and "--boundary" in err and str(source) in err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rotor.obj"]
    code, out, err = _run(
        capsys, "degenerate", str(source), "--root-offset", "0.05", "--boundary", "Blade1"
    )
    assert code == 0, err
    mesh = tmp_path / "rotor_Blade1_thin_blade.obj"
    assert out.splitlines()[0] == str(mesh) == str(thin_blade_path(source, "Blade1"))
    assert read_inventory(mesh.with_name("rotor_Blade1_thin_blade.boundaries.toml")) == ("Blade1",)
    alone = tmp_path / "alone"
    alone.mkdir()
    vertices, faces = _blade()
    reference = derive_thin_blade(
        _write_obj(alone / "rotor.obj", vertices, faces), root_offset=0.05
    )
    assert numpy.allclose(_read_obj(mesh), _read_obj(reference.mesh), rtol=0, atol=1e-12)
    # The name differs only by the boundary, so a second blade of one file does not collide.
    assert thin_blade_path(source) != thin_blade_path(source, "Blade1")
    assert thin_blade_path(source, "Blade 2/x").name == "rotor_Blade_2_x_thin_blade.obj"


def test_a_boundary_the_file_does_not_hold_is_refused_naming_what_it_holds(tmp_path, capsys):
    """FR-330 R6 and R9 (P0340-THIN-BLADE): an unknown boundary of an OBJ, of a saved
    simulation and one named twice in a saved simulation are each refused, nothing written."""
    # P0340-THIN-BLADE, FR-330 R9: an unknown or ambiguous boundary is refused by name.
    source = _with_spinner(tmp_path / "rotor.obj")
    code, out, err = _run(
        capsys, "degenerate", str(source), "--root-offset", "0.05", "--boundary", "Nacelle"
    )
    assert code == 2 and out == ""
    assert "no boundary named 'Nacelle'" in err and "Spinner, Blade1" in err
    saved = shutil.copy(_LIBRARY / "40_PUSHER.fsm", tmp_path / "pusher.fsm")
    code, _, err = _run(
        capsys, "degenerate", str(saved), "--root-offset", "0.01", "--boundary", "Propeller"
    )
    assert code == 2 and "no boundary named 'Propeller'" in err and "Body, Base, Blade1" in err
    with pytest.raises(InputArtifactError, match="holds 3 boundaries") as several:
        derive_thin_blade(saved, root_offset=0.01)
    assert "Body, Base, Blade1" in str(several.value) and "--boundary" in str(several.value)
    twice = _degenerate.boundary_names
    try:
        _degenerate.boundary_names = lambda _path: ("Body", "Body", "Blade1")  # type: ignore[assignment]
        with pytest.raises(InputArtifactError, match="names 2 of its boundaries") as ambiguous:
            derive_thin_blade(saved, root_offset=0.01, boundary="Body")
    finally:
        _degenerate.boundary_names = twice
    assert str(saved) in str(ambiguous.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pusher.fsm", "rotor.obj"]


def test_the_boundary_of_a_saved_simulation_is_cut_out_of_its_mesh_block(tmp_path, capsys):
    """FR-330 R9 (P0340-THIN-BLADE): of the pusher's three boundaries only the named one's
    faces are read, so the sheet lies inside the body's own span and is written under its name."""
    # P0340-THIN-BLADE, FR-330 R9: --boundary on a saved simulation holding three boundaries.
    saved = shutil.copy(_LIBRARY / "40_PUSHER.fsm", tmp_path / "pusher.fsm")
    code, out, err = _run(
        capsys, "degenerate", str(saved), "--root-offset", "0.01", "--boundary", "Body"
    )
    assert code == 0, err
    mesh = tmp_path / "pusher_Body_thin_blade.obj"
    assert out.splitlines()[0] == str(mesh) and "in METER" in err
    sheet = _read_obj(mesh)
    whole = numpy.asarray(_degenerate.surface_mesh(saved)[0])
    assert 0 < len(sheet) and sheet[:, 0].max() <= whole[:, 0].max() + 1e-9
    assert read_inventory(tmp_path / "pusher_Body_thin_blade.boundaries.toml") == ("Body",)


def test_the_cli_reference_and_the_cheatsheet_name_the_command_and_its_options():
    """FR-330 R7 (P0340-THIN-BLADE): the generated reference lists degenerate with its four
    options, and both pages of the cheatsheet that name the commands carry it."""
    # P0340-THIN-BLADE, FR-330 R7: the CLI reference and the cheatsheet name the command.
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from gen_cli_reference import cli_reference_pages
    finally:
        sys.path.pop(0)
    pages = cli_reference_pages()
    matrix = next(text for path, text in pages.items() if path.endswith("pyfs-matrix.md"))
    for word in (
        "degenerate",
        "--kind",
        "--root-offset",
        "--boundary",
        "--overwrite",
        "thin-blade",
    ):
        assert word in matrix, word
    sheets = REPO / "guide" / "latex-sources" / "04-cheatsheet" / "text"
    for name in ("01-matrix-and-tools.tex", "02-by-stage.tex"):
        text = (sheets / name).read_text(encoding="utf-8")
        for word in ("degenerate", "--root-offset", "--boundary", "thin-blade"):
            assert word in text, (name, word)
