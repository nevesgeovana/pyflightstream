"""P0380-REFINE (FR-424 R1 to R14): a level written by refine_mesh and by pyfs-matrix refine.

Every source is synthetic (tests/p0380_mesh_fixtures.py): the cambered sheet
grid ``G`` alone, or followed by strips extruded from its tip station that
share its last row of nodes (``T``, triangles that are no grid; ``U``,
triangles beyond ``T``). The source sits in ``<tmp>/src/`` so the default
out-dir is ``<tmp>``, and every refusal is asserted by its message text and
by the absence of any folder beside ``src`` (no level, no ``.partial``).
Each behaviour is also run on an input it must reject, or with the step it
rests on taken away, so a check that accepts everything cannot pass.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy
import pytest

import pyflightstream
import pyflightstream.workspace as workspace
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.extras import MissingExtraError
from pyflightstream.run import cli
from pyflightstream.workspace import RefinedMesh, refine_mesh
from pyflightstream.workspace._refine._grid import recover_grid
from tests.p0380_mesh_fixtures import (
    Composite,
    body_of_revolution,
    face_coordinates,
    read_mesh,
    sheet_with_strips,
    write_source,
)

PACKAGE = Path(pyflightstream.__file__).resolve().parent
#: The row spacings of the triangle strip T beyond the grid's tip station.
STRIP = (0.03, 0.04, 0.05, 0.065, 0.08)
WITH_T = (("T", "tri", STRIP),)
WITH_TU = (("T", "tri", STRIP), ("U", "tri", (0.1, 0.1)))


def _source(tmp_path: Path, strips=(), *, te=True, boundaries=True, refine_toml=None) -> Path:
    """Write a synthetic source as ``<tmp>/src/wing.obj`` and return its path."""
    mesh = sheet_with_strips(strips, te=te)
    return write_source(
        tmp_path / "src", "wing", mesh, boundaries=boundaries, refine_toml=refine_toml
    )


def _left(root: Path) -> list[str]:
    """Return every entry beside the source's folder: the levels and any staging folder."""
    return sorted(p.name for p in root.iterdir() if p.name != "src")


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def _refused(root: Path, src: Path, *args, error=InputArtifactError, **kwargs) -> str:
    """Return the text of a refine_mesh refusal, asserting nothing was written."""
    before = _snapshot(src.parent)
    with pytest.raises(error) as caught:
        refine_mesh(src, *args, **kwargs)
    text = str(caught.value)
    assert text.endswith("Nothing was written."), text
    assert _left(root) == []
    assert _snapshot(src.parent) == before
    return text


def _command(capsys, *argv: str) -> tuple[int, str, str]:
    """Run ``pyfs-matrix refine`` in-process; return the exit status, stdout and stderr."""
    capsys.readouterr()
    code = cli.main(["refine", *argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- R1 factors


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan")], ids=["zero", "negative", "nan"])
def test_r1_a_factor_not_above_zero_is_refused_by_both_routes(tmp_path, capsys, value):
    """P0380-REFINE (FR-424 R1, R11): zero, negative and not-a-number factors are refused.

    The function and the command give the same text, the command exits 2,
    and no level is left. Control: factor 2 is accepted and exits 0.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src, value)
    assert f"{src} FACTOR: the factor {value:g} is not above zero" in text
    code, _, err = _command(capsys, str(src), str(value))
    assert code == 2 and text in err and _left(tmp_path) == []
    code, _, _ = _command(capsys, str(src), "2")
    assert code == 0 and _left(tmp_path) == ["wing_R2"]


def test_r1_a_factor_that_is_not_a_number_is_refused_by_both_routes(tmp_path, capsys):
    """P0380-REFINE (FR-424 R1, R11): FACTOR ``two`` is refused alike by the function and command.

    The command exits 2 with the function's own text, which names the value
    and ends "Nothing was written.". Control: the number 2 passes both.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src, "two")
    assert f"{src} FACTOR: the factor 'two' is not a number; give a number above zero" in text
    code, _, err = _command(capsys, str(src), "two")
    assert code == 2 and text in err and _left(tmp_path) == []
    assert isinstance(refine_mesh(src, 2.0), RefinedMesh)
    assert _command(capsys, str(src), "2", "--overwrite")[0] == 0


@pytest.mark.parametrize("flag", ["chordwise", "spanwise"])
def test_r1_a_direction_that_is_not_a_number_is_refused_by_both_routes(tmp_path, capsys, flag):
    """P0380-REFINE (FR-424 R1, R11): ``--chordwise two`` and ``--spanwise two`` alike.

    The command's refusal is the function's text, naming the flag and the
    value. Control: the same flag with the number 2 exits 0.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src, 1.0, **{flag: "two"})
    assert f"{src} --{flag}: the factor 'two' is not a number" in text
    code, _, err = _command(capsys, str(src), "1", f"--{flag}", "two")
    assert code == 2 and text in err and _left(tmp_path) == []
    assert _command(capsys, str(src), "1", f"--{flag}", "2")[0] == 0


@pytest.mark.parametrize(
    ("kwargs", "argv", "said"),
    [
        ({"factor": 0.05}, ["0.05"], "the chordwise factor is 0.05, below 1/18"),
        ({"factor": 1.0, "spanwise": 0.1}, ["1", "--spanwise", "0.1"], "spanwise factor is 0.1"),
    ],
    ids=["factor", "spanwise"],
)
def test_r1_a_factor_below_one_over_m_is_refused_naming_family_direction_value(
    tmp_path, capsys, kwargs, argv, said
):
    """P0380-REFINE (FR-424 R1, R11): a factor leaving no interval is refused before any work.

    The grid G has 18 chordwise and 8 spanwise intervals. Control: exactly
    1/8 spanwise is accepted by the command and leaves one interval.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src, **kwargs)
    assert text.startswith("family G: ") and said in text
    code, _, err = _command(capsys, str(src), *argv)
    assert code == 2 and text in err and _left(tmp_path) == []
    code, _, _ = _command(capsys, str(src), "1", "--spanwise", "0.125")
    assert code == 0
    report = _json(tmp_path / "wing_R1s0p125" / "wing_R1s0p125.refine.json")
    assert report["families"]["G"]["intervals"]["spanwise"] == [8, 1]


# ------------------------------------------------- R2 where the factors come from


def test_r2_factor_applies_and_chordwise_replaces_one_direction(tmp_path):
    """P0380-REFINE (FR-424 R2, R5): FACTOR doubles both directions; --chordwise replaces one.

    Control: the same FACTOR without --chordwise doubles the chordwise count.
    """
    src = _source(tmp_path)
    both = refine_mesh(src, 2.0)
    one = refine_mesh(src, 2.0, chordwise=1.0)
    assert both.report["G"]["intervals"] == {"chordwise": [18, 36], "spanwise": [8, 16]}
    assert one.report["G"]["intervals"] == {"chordwise": [18, 18], "spanwise": [8, 16]}
    assert (both.folder.name, one.folder.name) == ("wing_R2", "wing_R2c1")


def test_r2_the_file_gives_the_factors_only_when_the_call_gives_none(tmp_path):
    """P0380-REFINE (FR-424 R2): ``<stem>.refine.toml`` is read for factors only without FACTOR.

    Without a factor the file's 0.5 halves the grid; with FACTOR 2 the file's
    factor is not used but the file is still named in refine.json. A file
    named by ``config`` replaces the one beside the mesh, its tag included.
    """
    src = _source(tmp_path, refine_toml="[families.G]\nfactor = 0.5\n")
    from_file = refine_mesh(src)
    assert from_file.report["G"]["intervals"] == {"chordwise": [18, 9], "spanwise": [8, 4]}
    assert from_file.folder.name == "wing_R0p5"
    called = refine_mesh(src, 2.0)
    assert called.report["G"]["intervals"]["chordwise"] == [18, 36]
    assert _json(called.files[3])["config"] == "wing.refine.toml"
    other = tmp_path / "coarse.toml"
    other.write_bytes(b'[refine]\ntag = "coarse"\n\n[families.G]\nfactor = 0.5\n')
    named = refine_mesh(src, config=other)
    assert named.folder.name == "wing_coarse"
    assert named.report["G"]["intervals"]["spanwise"] == [8, 4]


def test_r2_components_are_read_whatever_gives_the_factors(tmp_path):
    """P0380-REFINE (FR-424 R2; FR-425 R4): [components] applies when FACTOR is given.

    Control: the same call with no refinement file keeps the two families.
    """
    plain = _source(tmp_path / "plain", WITH_T)
    level = refine_mesh(plain, 1.0, families=["G"])
    assert list(read_mesh(level.obj)[1]) == ["G", "T"]
    src = _source(tmp_path, WITH_T, refine_toml='[components]\nWing = ["G", "T"]\n')
    level = refine_mesh(src, 1.0, families=["G"])
    assert list(read_mesh(level.obj)[1]) == ["Wing"]


def _two_tubes(tmp_path: Path, refine_toml: str) -> Path:
    """Write two disconnected smooth tubes, families A and B, as ``<tmp>/src/tubes.obj``."""
    body = body_of_revolution()
    n = len(body.verts)
    mesh = Composite(
        numpy.vstack([body.verts, body.verts + [0.0, 4.0, 0.0]]),
        {"A": body.faces, "B": [[v + n for v in f] for f in body.faces]},
        numpy.zeros((0, 3)),
        {},
    )
    return write_source(tmp_path / "src", "tubes", mesh, refine_toml=refine_toml)


BOTH_TABLES = "[families.A]\nfactor = 2\n[families.B]\nfactor = 2\n"


def test_r2_families_selects_from_the_files_factors_by_both_routes(tmp_path, capsys):
    """P0380-REFINE (FR-424 R2, R11): ``--families`` selects when the file gives the factors.

    The file states factor 2 for A and B; ``families=["A"]`` changes A alone
    and B is written as the source holds it. A selected name the mesh does
    not hold is refused on this route as on the FACTOR route, and so is a
    selection the file states no factor for. Control: without the selection
    both tubes are refined.
    """
    src = _two_tubes(tmp_path, BOTH_TABLES)
    text = _refused(tmp_path, src, families=["A", "Z"])
    assert f"{src}: the mesh holds no family 'Z'; it holds A, B" in text
    code, _, err = _command(capsys, str(src), "--families", "A,Z")
    assert code == 2 and text in err and _left(tmp_path) == []
    src.with_name("tubes.refine.toml").write_bytes(b"[families.A]\nfactor = 2\n")
    text = _refused(tmp_path, src, families=["B"])
    assert "states no factor for the selected families B" in text
    src.with_name("tubes.refine.toml").write_bytes(BOTH_TABLES.encode("utf-8"))
    sv, sf = read_mesh(src)
    level = refine_mesh(src, families=["A"], out_dir=tmp_path / "one")
    lv, lf = read_mesh(level.obj)
    assert len(lf["A"]) == 4 * len(sf["A"])
    assert face_coordinates(lv, lf["B"]) == face_coordinates(sv, sf["B"])
    assert level.folder.name == "tubes_R-A2" and level.report["B"] == {"method": "copied"}
    code, _, _ = _command(capsys, str(src), "--families", "A", "--out-dir", str(tmp_path / "cmd"))
    assert code == 0
    assert len(read_mesh(tmp_path / "cmd" / "tubes_R-A2" / "tubes_R-A2.obj")[1]["B"]) == 144
    both = refine_mesh(src, out_dir=tmp_path / "all")
    assert both.folder.name == "tubes_R2" and len(read_mesh(both.obj)[1]["B"]) == 576


def test_r2_the_files_family_tables_not_read_are_warned_and_recorded(tmp_path):
    """P0380-REFINE (FR-424 R2, R4): a [families.*] table the refinement does not read is said.

    With FACTOR, the file's family tables are not read for their factors
    (R2), and with ``--families`` on the file's factors an unselected table is
    not read: each is a warning naming the tables, and ``refine.json`` lists
    them under ``ignored_families_tables``. Control: the file's factors for
    every family warn of nothing and record an empty list.
    """
    src = _two_tubes(tmp_path, BOTH_TABLES)
    with pytest.warns(PyflightstreamWarning, match=r"\[families\.A\], \[families\.B\]") as seen:
        called = refine_mesh(src, 1.0, out_dir=tmp_path / "called")
    assert "FACTOR, --chordwise or --spanwise gives the factors" in str(seen[0].message)
    assert _json(called.files[2])["ignored_families_tables"] == ["A", "B"]
    with pytest.warns(PyflightstreamWarning, match=r"\[families\.B\]") as seen:
        one = refine_mesh(src, families=["A"], out_dir=tmp_path / "one")
    assert "--families selects A" in str(seen[0].message)
    assert _json(one.files[2])["ignored_families_tables"] == ["B"]
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        every = refine_mesh(src, out_dir=tmp_path / "every")
    assert not [w for w in caught if "families." in str(w.message)]
    assert _json(every.files[2])["ignored_families_tables"] == []


def test_r2_no_factor_and_no_file_is_refused_by_both_routes(tmp_path, capsys):
    """P0380-REFINE (FR-424 R2, R11): no FACTOR, no direction and no file is refused.

    A file that states no factor (only [components]) is refused the same way.
    Control: the same command with FACTOR exits 0.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src)
    assert (
        f"{src}: no factor was given and no refinement file states one; give FACTOR "
        "or write wing.refine.toml beside the mesh. Nothing was written."
    ) == text
    code, _, err = _command(capsys, str(src))
    assert code == 2 and text in err and _left(tmp_path) == []
    src.with_name("wing.refine.toml").write_bytes(b'[components]\nAll = ["G"]\n')
    assert _refused(tmp_path, src) == text
    assert _command(capsys, str(src), "1")[0] == 0


def test_r2_a_direction_on_a_remeshed_family_is_refused(tmp_path):
    """P0380-REFINE (FR-424 R2, R11): --chordwise on a family that is no grid is refused.

    T recovers no grid, so it would be remeshed. Control: --chordwise on G
    alone is accepted.
    """
    src = _source(tmp_path, WITH_T)
    text = _refused(tmp_path, src, chordwise=2.0)
    assert text.startswith(f"{src} family T: chordwise and spanwise apply to a grid")
    assert refine_mesh(src, chordwise=2.0, families=["G"]).folder.name == "wing_R-G1c2"


# --------------------------------------------------------- R3 the refinement file


@pytest.mark.parametrize(
    ("toml", "said"),
    [
        (
            "[families.G]\nfactr = 2\n",
            "[families.G]: unknown key 'factr'; the known keys are factor, chordwise, "
            "spanwise, method, axial, circumferential, axis, origin, elements",
        ),
        (
            "[families.Fin]\nfactor = 2\n",
            "[families.Fin]: the mesh holds no family 'Fin'; it holds G",
        ),
        (
            '[families.G]\nmethod = "remesh"\nchordwise = 2\n',
            "[families.G]: chordwise and spanwise apply to a grid; a remeshed family takes factor",
        ),
        ('[families.G]\nmethod = "grid"\n', "the table states no factor, chordwise or spanwise"),
        (
            '[refinement]\ntag = "x"\n',
            "unknown table [refinement]; the tables are refine, families, components, periodic",
        ),
    ],
    ids=["unknown-key", "unknown-family", "chordwise-on-remesh", "no-factor", "unknown-table"],
)
def test_r3_the_refinement_file_is_refused_naming_file_table_and_key(tmp_path, capsys, toml, said):
    """P0380-REFINE (FR-424 R3, R11): each bad file is refused by both routes, naming its path.

    Control: a valid file (``factor = 2``) writes the level.
    """
    src = _source(tmp_path, refine_toml=toml)
    text = _refused(tmp_path, src)
    assert text.startswith(str(src.with_name("wing.refine.toml"))) and said in text
    code, _, err = _command(capsys, str(src))
    assert code == 2 and text in err and _left(tmp_path) == []
    src.with_name("wing.refine.toml").write_bytes(b"[families.G]\nfactor = 2\n")
    assert _command(capsys, str(src))[0] == 0 and _left(tmp_path) == ["wing_R2"]


@pytest.mark.parametrize(
    ("toml", "said"),
    [
        ("families = 3\n", "[families]: the value 3 is not a table"),
        ("families = []\n", "[families]: the value [] is not a table"),
        ("[families]\nG = 3\n", "[families.G]: the value 3 is not a table"),
        ("refine = 3\n", "[refine]: the value 3 is not a table"),
        ("refine = false\n", "[refine]: the value False is not a table"),
        ("components = 0\n", "[components]: the table must map a component name"),
        ("[refine]\ntag = 3\n", "[refine] tag: 3 is not a text"),
    ],
    ids=["families-scalar", "families-empty-list", "family-scalar", "refine-scalar",
         "refine-false", "components-zero", "tag-number"],
)  # fmt: skip
def test_r3_a_table_of_the_wrong_shape_is_refused_by_both_routes(tmp_path, capsys, toml, said):
    """P0380-REFINE (FR-424 R3, R11): valid TOML whose table is a scalar, a list or falsey.

    Each is refused by the function and the command alike with the standard
    refusal (the file, the table, what to write, "Nothing was written."), not
    a Python exception. The factor is given in the call, so the file is read
    only for its tables. Control: the file's tables written as tables pass.
    """
    src = _source(tmp_path, refine_toml=toml)
    text = _refused(tmp_path, src, 1.0)
    assert text.startswith(str(src.with_name("wing.refine.toml"))) and said in text, text
    code, _, err = _command(capsys, str(src), "1")
    assert code == 2 and text in err and _left(tmp_path) == []
    src.with_name("wing.refine.toml").write_bytes(
        b'[refine]\ntag = "t"\n[families.G]\nfactor = 1\n[components]\nAll = ["G"]\n'
    )
    assert _command(capsys, str(src), "1")[0] == 0


@pytest.mark.parametrize(
    ("toml", "said"),
    [
        (
            "[periodic]\naxis = [1, 0, 0]\nspin = 1\n",
            "unknown key spin; missing keys origin, copies; the keys are axis, origin, copies",
        ),
        (
            "[periodic]\naxis = [1, 0, 0]\norigin = [0, 0, 0]\n",
            "missing key copies; the keys are axis, origin, copies",
        ),
        (
            "[periodic]\naxis = [1, 0, 0]\norigin = [0, 0, 0]\ncopies = 3\nturns = 1\nspin = 2\n",
            "unknown keys spin, turns; the keys are axis, origin, copies",
        ),
    ],
    ids=["unknown-and-missing", "missing", "unknown"],
)
def test_r3_a_periodic_table_names_its_unknown_and_its_missing_keys(tmp_path, toml, said):
    """P0380-REFINE (FR-424 R3; FR-427 R2): the refusal names each unknown and each missing key.

    The unknown keys and the missing keys are named separately, not as one
    "unknown or missing" key.
    """
    src = _source(tmp_path, refine_toml=toml)
    text = _refused(tmp_path, src, 1.0)
    assert f"{src.with_name('wing.refine.toml')} [periodic]: {said}" in text, text


# ---------------------------------------------------------- R4 what a level holds


def test_r4_a_level_holds_its_files_and_refine_json_reports_each_family(tmp_path):
    """P0380-REFINE (FR-424 R4, R5, R9): the five files, the record and the audit beside it.

    G is a grid, T is remeshed (no grid recovered), U is copied; the source's
    folder is not touched. The returned RefinedMesh is frozen and names every
    file the folder holds.
    """
    src = _source(tmp_path, WITH_TU)
    before = _snapshot(src.parent)
    level = refine_mesh(src, 2.0, families=["G", "T"])
    stem = "wing_R-G2-T2"
    suffixes = (".obj", ".te.txt", ".boundaries.toml", ".refine.json", ".audit.json")
    names = [stem + suffix for suffix in suffixes]
    assert [p.name for p in level.files] == names
    assert sorted(p.name for p in level.folder.iterdir()) == sorted(names)
    assert level.folder == tmp_path / stem and level.obj == level.files[0]
    assert _snapshot(src.parent) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        level.folder = tmp_path  # type: ignore[misc]
    record = _json(level.folder / f"{stem}.refine.json")
    faces = {n: len(fs) for n, fs in read_mesh(level.obj)[1].items()}
    assert record["schema_version"] == 1 and record["source"] == "wing.obj"
    assert record["level"] == stem and record["faces"] == faces
    g, t, u = (record["families"][n] for n in ("G", "T", "U"))
    assert g["method"] == "grid" and g["reason"].startswith("a sheet of 9 stations by 19")
    assert g["faces"] == [144, 576] and g["layout"] == "sheet"
    assert t["method"] == "remesh" and t["reason"].startswith("no grid recovered: ")
    assert (t["faces_before"], t["faces_after"]) == (180, faces["T"])
    assert u == {"method": "copied"} and faces["U"] == 72
    assert record["families"] == level.report
    te = (level.folder / f"{stem}.te.txt").read_text(encoding="utf-8").splitlines()
    assert te[0] == "METER" and len(te) == 1 + 16
    side = (level.folder / f"{stem}.boundaries.toml").read_text(encoding="utf-8")
    assert f'file = "{stem}.te.txt"' in side and "wing.te.txt" not in side
    audit = _json(level.folder / f"{stem}.audit.json")
    assert (audit["schema_version"], audit["mesh"], audit["source"]) == (
        1,
        f"{stem}.obj",
        "wing.obj",
    )
    assert level.audit is not None and level.audit.path == level.files[-1]


def test_r4_r9_a_source_without_points_file_gets_none_and_auto_remeshes(tmp_path):
    """P0380-REFINE (FR-424 R4, R9): no points file in, none out; auto names why it remeshed.

    Without trailing-edge points no grid is recovered, so under ``auto`` the
    sheet is remeshed and refine.json gives the recovery's own reason. (The
    control of the points file is the test above, whose source has one and
    whose level has one.)
    """
    src = _source(tmp_path, te=False, boundaries=False)
    level = refine_mesh(src, 2.0)
    assert [p.name for p in level.files] == [
        "wing_R2.obj",
        "wing_R2.refine.json",
        "wing_R2.audit.json",
    ]
    verts, families = read_mesh(src)
    why = recover_grid(verts, families["G"], set())
    assert isinstance(why, str) and why
    assert level.report["G"] == {**level.report["G"], "method": "remesh"}
    assert level.report["G"]["reason"] == f"no grid recovered: {why}"


# ------------------------------------------------------ R5 where a level goes


@pytest.mark.parametrize(
    ("strips", "toml", "kwargs", "folder"),
    [
        ((), None, {"factor": 2.0}, "wing_R2"),
        ((), None, {"factor": 0.5}, "wing_R0p5"),
        ((), None, {"chordwise": 1.5, "spanwise": 0.7}, "wing_R1c1p5s0p7"),
        (WITH_T, None, {"factor": 2.0, "families": ["G"]}, "wing_R-G2"),
        ((), '[refine]\ntag = "fine"\n', {"factor": 2.0}, "wing_fine"),
    ],
    ids=["R2", "R0p5", "R1c1p5s0p7", "subset", "file-tag"],
)
def test_r5_the_tag_names_the_level_beside_the_sources_folder(
    tmp_path, strips, toml, kwargs, folder
):
    """P0380-REFINE (FR-424 R5): the tag forms, and the default out-dir is the source's parent.

    Control: ``out_dir`` places the same level in the folder it names.
    """
    src = _source(tmp_path, strips, refine_toml=toml)
    level = refine_mesh(src, **kwargs)
    assert level.folder == tmp_path / folder and _left(tmp_path) == [folder]
    other = tmp_path / "elsewhere"
    moved = refine_mesh(src, out_dir=other, **kwargs)
    assert moved.folder == other / folder and _left(other) == [folder]
    assert _left(tmp_path) == sorted([folder, "elsewhere"])


def test_r5_the_command_writes_the_tagged_level_and_prints_its_files(tmp_path, capsys):
    """P0380-REFINE (FR-424 R5): the command exits 0 and prints each file it wrote."""
    src = _source(tmp_path)
    code, out, _ = _command(capsys, str(src), "1", "--chordwise", "1.5", "--spanwise", "0.7")
    folder = tmp_path / "wing_R1c1p5s0p7"
    assert code == 0 and "G: grid" in out
    for path in sorted(folder.iterdir()):
        assert str(path) in out


def test_r5_an_existing_level_is_refused_unless_overwrite(tmp_path, capsys):
    """P0380-REFINE (FR-424 R5, R11): a second run is refused and leaves the first level alone.

    With ``--overwrite`` the level is replaced: a file planted in it is gone.
    """
    src = _source(tmp_path)
    first = refine_mesh(src, 2.0)
    (first.folder / "planted.txt").write_bytes(b"x")
    kept = _snapshot(first.folder)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, 2.0)
    text = str(caught.value)
    assert text == (
        f"{first.folder}: the level exists; give overwrite=True (--overwrite) to replace it. "
        "Nothing was written."
    )
    code, _, err = _command(capsys, str(src), "2")
    assert code == 2 and text in err
    assert _snapshot(first.folder) == kept and _left(tmp_path) == ["wing_R2"]
    code, _, _ = _command(capsys, str(src), "2", "--overwrite")
    assert code == 0 and not (first.folder / "planted.txt").exists()
    assert _left(tmp_path) == ["wing_R2"]


def test_r5_an_error_while_writing_leaves_no_level_and_no_partial_folder(tmp_path, capsys):
    """P0380-REFINE (FR-424 R5): an error in the write step leaves no level and no ``.partial``.

    The level's path is occupied by a file, so with ``overwrite`` the files
    are written into the staging folder and replacing the level then fails:
    the error comes from inside the write step. The staging folder is
    removed and the occupying file is kept; the command exits 2 the same way.
    Control: a stale ``.partial`` folder, which the observation sees, is
    cleared by the next run that writes that level.
    """
    src = _source(tmp_path)
    occupied = tmp_path / "wing_R2"
    occupied.write_bytes(b"occupied")
    with pytest.raises(OSError):
        refine_mesh(src, 2.0, overwrite=True)
    assert _left(tmp_path) == ["wing_R2"] and occupied.read_bytes() == b"occupied"
    code, _, err = _command(capsys, str(src), "2", "--overwrite")
    assert code == 2 and err.strip() and _left(tmp_path) == ["wing_R2"]
    stale = tmp_path / "wing_R0p5.partial"
    stale.mkdir()
    (stale / "stale.txt").write_bytes(b"x")
    assert _left(tmp_path) == ["wing_R0p5.partial", "wing_R2"]
    refine_mesh(src, 0.5)
    assert _left(tmp_path) == ["wing_R0p5", "wing_R2"]


@pytest.mark.parametrize(
    ("sidecar", "said"),
    [
        (
            'boundaries = ["G"]\n[trailing_edges]\nfile = "missing.te.txt"\n',
            "names the trailing-edge file missing.te.txt, which does not exist",
        ),
        ('boundaries = ["G"\n', "not TOML"),
    ],
    ids=["missing-points-file", "malformed-sidecar"],
)
def test_r11_a_sidecar_the_audit_refuses_is_refused_before_any_work(
    tmp_path, capsys, monkeypatch, sidecar, said
):
    """P0380-REFINE (FR-424 R5, R11; FR-426 R2 G4): the inputs the audit reads are checked first.

    A boundaries file naming a points file that does not exist, or that is not
    TOML, is refused by the function and the command before any family is
    resampled (the grid's resampling is replaced by one that fails the test if
    called), and no level folder is published. With ``overwrite`` the level
    already there is kept byte for byte. Control: the audit refuses the same
    sidecar with the same reason.
    """
    from pyflightstream.workspace import audit_mesh
    from pyflightstream.workspace._refine import _grid

    src = _source(tmp_path)
    first = refine_mesh(src, 2.0)
    kept = _snapshot(first.folder)
    src.with_name("wing.boundaries.toml").write_bytes(sidecar.encode("utf-8"))

    def never(*args, **kwargs):
        raise AssertionError("a family was resampled before the refusal")

    monkeypatch.setattr(_grid, "refine_grid", never)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, 2.0, overwrite=True)
    text = str(caught.value)
    assert said in text and text.endswith("Nothing was written."), text
    assert _left(tmp_path) == ["wing_R2"] and _snapshot(first.folder) == kept
    code, _, err = _command(capsys, str(src), "1")
    assert code == 2 and said in err and _left(tmp_path) == ["wing_R2"]
    with pytest.raises(InputArtifactError, match=said):
        audit_mesh(src)


def test_r5_an_audit_that_fails_to_run_publishes_nothing_and_keeps_the_old_level(
    tmp_path, monkeypatch
):
    """P0380-REFINE (FR-424 R4, R5): the level is published only after its audit is written.

    The audit runs inside the staging folder; when it raises (here an error
    writing audit.json), no level folder is published, no staging folder is
    left, and with ``overwrite`` the previous level is kept byte for byte.
    Control: the same call without the error replaces the level and the
    returned audit names the published folder.
    """
    from pyflightstream.workspace._refine import _level

    src = _source(tmp_path)
    first = refine_mesh(src, 2.0)
    (first.folder / "planted.txt").write_bytes(b"x")
    kept = _snapshot(first.folder)
    real = _level.audit_mesh

    def failing(*args, **kwargs):
        raise OSError("the audit could not be written")

    monkeypatch.setattr(_level, "audit_mesh", failing)
    with pytest.raises(OSError, match="the audit could not be written"):
        refine_mesh(src, 2.0, overwrite=True)
    assert _left(tmp_path) == ["wing_R2"] and _snapshot(first.folder) == kept
    with pytest.raises(OSError):
        refine_mesh(src, 0.5)
    assert _left(tmp_path) == ["wing_R2"]
    monkeypatch.setattr(_level, "audit_mesh", real)
    level = refine_mesh(src, 2.0, overwrite=True)
    assert not (level.folder / "planted.txt").exists() and _left(tmp_path) == ["wing_R2"]
    assert level.audit is not None and level.audit.path == level.folder / "wing_R2.audit.json"
    assert level.audit.mesh == level.obj and level.audit.path.is_file()
    assert level.files[-1] == level.audit.path


# ----------------------------------------------------------------- R7 face order


def _mesh_lines(path: Path, tags: tuple[str, ...] = ("v", "g", "f")) -> list[str]:
    """Return the OBJ's lines of the given statements, in order (the header aside)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.split(" ", 1)[0] in tags]


def test_r7_factor_one_writes_the_sources_vertex_and_face_lines(tmp_path):
    """P0380-REFINE (FR-424 R7): at factor 1 the OBJ's v and f lines are the source's, in order.

    The source's vertex numbering is shuffled, so the level must number its
    nodes as the source does, not by first use. Controls: the level's faces
    reversed, and rotated by one vertex, fail the face comparison; the
    source's v lines in the order of first use (what a level numbered by
    first use writes) are not the source's v lines.
    """
    src = _source(tmp_path)
    level = refine_mesh(src, 1.0)
    assert _mesh_lines(level.obj) == _mesh_lines(src)
    sv, sf = read_mesh(src)
    lv, lf = read_mesh(level.obj)
    source = face_coordinates(sv, sf["G"])
    assert face_coordinates(lv, lf["G"]) == source
    assert face_coordinates(lv, lf["G"][::-1]) != source
    assert face_coordinates(lv, [f[1:] + f[:1] for f in lf["G"]]) != source
    assert level.report["G"]["order"] == "sweep"
    order = list(dict.fromkeys(v for f in sf["G"] for v in f))
    vertex_lines = _mesh_lines(src, ("v",))
    assert [vertex_lines[v] for v in order] != vertex_lines
    assert sorted(vertex_lines[v] for v in order) == sorted(vertex_lines)


# --------------------------------------------------------------------- R9 method


def test_r9_method_grid_without_a_grid_is_refused_and_auto_remeshes(tmp_path):
    """P0380-REFINE (FR-424 R9, R11): ``grid`` on T is refused naming why; ``auto`` remeshes it.

    Controls: ``grid`` on G (a recovered grid) is accepted, and ``remesh``
    on G remeshes it although it is a grid, giving that reason.
    """
    toml = '[families.T]\nfactor = 2\nmethod = "grid"\n'
    src = _source(tmp_path, WITH_T, refine_toml=toml)
    text = _refused(tmp_path, src)
    assert text.startswith(f"{src} family T: method is grid and no grid was recovered: ")
    src.with_name("wing.refine.toml").write_bytes(b"[families.T]\nfactor = 2\n")
    why = text.split("no grid was recovered: ", 1)[1].removesuffix(". Nothing was written.")
    entry = refine_mesh(src).report["T"]
    assert (entry["method"], entry["reason"]) == ("remesh", f"no grid recovered: {why}")
    src.with_name("wing.refine.toml").write_bytes(b'[families.G]\nfactor = 1\nmethod = "grid"\n')
    assert refine_mesh(src).report["G"]["method"] == "grid"
    src.with_name("wing.refine.toml").write_bytes(
        b'[refine]\ntag = "G-remeshed"\n\n[families.G]\nfactor = 1\nmethod = "remesh"\n'
    )
    entry = refine_mesh(src).report["G"]
    assert (entry["method"], entry["reason"]) == ("remesh", "the refinement file states remesh")


# --------------------------------------------------------------- R10 the extra


def test_r10_without_scipy_and_rtree_a_grid_refines_and_a_remesh_is_refused(
    tmp_path, monkeypatch, capsys
):
    """P0380-REFINE (FR-424 R10, R11): scipy and rtree unimportable (``sys.modules`` None).

    The grid-only refinement writes its level. The one that must remesh T is
    refused by both routes naming T and ``pip install pyflightstream[geom]``,
    before any file. Control: with the extra importable again the same
    refinement writes the level, T remeshed.
    """
    alone = _source(tmp_path / "alone")
    root = tmp_path / "remesh"
    src = _source(root, WITH_T)
    with monkeypatch.context() as blocked:
        for name in ("scipy", "scipy.spatial", "rtree"):
            blocked.setitem(sys.modules, name, None)
        level = refine_mesh(alone, 2.0)
        assert level.report["G"]["method"] == "grid" and len(level.files) == 5
        text = _refused(root, src, 2.0, error=MissingExtraError)
        assert "family T" in text and "pip install pyflightstream[geom]" in text
        code, _, err = _command(capsys, str(src), "2")
        assert code == 2 and text in err and _left(root) == []
    level = refine_mesh(src, 2.0)
    assert level.report["T"]["method"] == "remesh" and _left(root) == ["wing_R2"]


# ------------------------------------------------------- R12, R13 the bytes written


def _digests(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_r12_two_runs_under_different_hash_seeds_write_identical_bytes(tmp_path):
    """P0380-REFINE (FR-424 R12): two processes with other hash seeds write the same files.

    A grid refined, a neighbour remeshed onto its new nodes and a family
    copied, each run in its own interpreter (PYTHONHASHSEED 1 and 2).
    Control: the same refinement at factor 0.5 differs from them by digest.
    """
    src = _source(tmp_path, WITH_TU)
    script = "import sys\nfrom pyflightstream.run.cli import main\nsys.exit(main(sys.argv[1:]))"
    root = str(PACKAGE.parent)
    runs = []
    for seed in ("1", "2"):
        out = tmp_path / f"run{seed}"
        env = {**os.environ, "PYTHONPATH": root, "PYTHONHASHSEED": seed}
        argv = ["refine", str(src), "2", "--families", "G,T", "--out-dir", str(out)]
        done = subprocess.run(
            [sys.executable, "-c", script, *argv], capture_output=True, env=env, timeout=300
        )
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
        runs.append(_digests(out / "wing_R-G2-T2"))
    assert runs[0] == runs[1] and len(runs[0]) == 5
    other = refine_mesh(src, 0.5, families=["G", "T"], out_dir=tmp_path / "control")
    coarse = _digests(other.folder)
    assert coarse["wing_R-G0p5-T0p5.obj"] != runs[0]["wing_R-G2-T2.obj"]


def test_r13_no_written_file_holds_a_carriage_return(tmp_path):
    """P0380-REFINE (FR-424 R13): every level file is free of CR, from a source written in CRLF.

    The source's OBJ, points file, boundaries file and refinement file are all
    CRLF (the control: the same byte scan finds CR in each of them).
    """
    src = _source(
        tmp_path, WITH_T, refine_toml="[families.G]\nfactor = 2\n[families.T]\nfactor = 2\n"
    )
    for path in src.parent.iterdir():
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert all(b"\r" in p.read_bytes() for p in src.parent.iterdir())
    level = refine_mesh(src)
    assert len(level.files) == 5
    assert [p.name for p in level.folder.iterdir() if b"\r" in p.read_bytes()] == []


# ------------------------------------------------------------------- R14 layering


def _imports(text: str, package: str) -> set[str]:
    """Return every module a source imports, at module level or deferred, relative ones resolved.

    ``from a.b import c`` yields both ``a.b`` and ``a.b.c`` (c may be a module).
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                parts = parts[: len(parts) - node.level + 1]
                base = ".".join([*parts, base] if base else parts)
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def _file_imports(path: Path) -> set[str]:
    package = ".".join(("pyflightstream", *path.relative_to(PACKAGE).parent.parts))
    return _imports(path.read_text(encoding="utf-8"), package)


def _reaching(found: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(m for m in found if any(m == p or m.startswith(p + ".") for p in prefixes))


REFINE = "pyflightstream.workspace._refine"
#: The modules of the refinement package the audit may import: the shared helpers.
AUDIT_MAY_IMPORT = ("_audit", "_geometry", "_obj")


def _refinement_modules() -> tuple[str, ...]:
    """Return every module of the refinement package the audit must not import.

    Read from the package's files, so a module added to the refinement is
    covered without editing a list (the shared helpers are the exceptions).
    """
    folder = PACKAGE / "workspace" / "_refine"
    names = sorted(p.stem for p in folder.glob("*.py") if p.stem != "__init__")
    return tuple(f"{REFINE}.{n}" for n in names if n not in AUDIT_MAY_IMPORT)


PRIVATE = _refinement_modules()


def test_r14_the_refinement_audit_and_command_import_only_what_the_layering_allows():
    """P0380-REFINE (FR-424 R14): an AST walk of every import, deferred ones included.

    ``workspace/_refine`` imports nothing of ``pyflightstream.run``; ``_audit``
    imports no module of the refinement package but the shared helpers
    ``_geometry`` and ``_obj`` (the list is read from the package's files);
    the command reaches the refinement only through public names of
    ``pyflightstream.workspace``. Controls: each rule run on a planted source
    holding the forbidden import (deferred, inside a function) reports it,
    every refinement module among them.
    """
    refine = PACKAGE / "workspace" / "_refine"
    files = sorted(refine.glob("*.py"))
    assert {p.name for p in files} >= {"_audit.py", "_config.py", "_grid.py", "_level.py"}
    for path in files:
        assert _reaching(_file_imports(path), ("pyflightstream.run",)) == [], path.name
    assert _reaching(_file_imports(refine / "_audit.py"), PRIVATE) == []
    found = _file_imports(PACKAGE / "run" / "_cli_mesh.py")
    assert _reaching(found, (REFINE,)) == []
    public = [m.rpartition(".")[2] for m in found if m.startswith("pyflightstream.workspace.")]
    assert "refine_mesh" in public and "audit_mesh" in public
    assert all(name in workspace.__all__ and not name.startswith("_") for name in public)
    planted = _imports(
        "def f():\n    from ...run import cli\n    from . import _grid, _level\n", REFINE
    )
    assert _reaching(planted, ("pyflightstream.run",)) == [
        "pyflightstream.run",
        "pyflightstream.run.cli",
    ]
    assert _reaching(planted, PRIVATE) == [f"{REFINE}._grid", f"{REFINE}._level"]
    names = {"_blocks", "_config", "_grid", "_level", "_periodic", "_remesh"}
    assert {m.rpartition(".")[2] for m in PRIVATE} >= names
    for module in PRIVATE:
        leaf = module.rpartition(".")[2]
        planted = _imports(f"def f():\n    from . import {leaf}\n", REFINE)
        assert _reaching(planted, PRIVATE) == [module], leaf
        planted = _imports(f"from {module} import x\n", REFINE)
        assert module in _reaching(planted, PRIVATE), leaf
    command = _imports(
        "def g():\n    from pyflightstream.workspace._refine._level import refine_mesh\n",
        "pyflightstream.run",
    )
    assert _reaching(command, (REFINE,)) == [f"{REFINE}._level", f"{REFINE}._level.refine_mesh"]


#: The shared engineering thresholds of the section, defined once in ``_geometry``.
SHARED_THRESHOLDS = (
    "DUPLICATE_FRACTION",
    "TE_POINT_FRACTION",
    "GRID_SURFACE_DISTANCE",
    "ZERO_AREA_FRACTION",
    "ON_CURVE_FRACTION",
)


def _threshold_literals(text: str, values: set[float]) -> list[tuple[int, float]]:
    """Return the line and value of every numeric literal of the source equal to a threshold."""
    return sorted(
        (node.lineno, float(node.value))
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, float)
        and float(node.value) in values
    )


def test_the_shared_thresholds_have_one_home_read_by_every_consumer():
    """P0380-REFINE (section thresholds rule): a shared threshold is defined once, in _geometry.

    No module of the refinement package but ``_geometry`` spells the value of
    a shared fraction as a literal; the remesher's own tuning constants are
    named in ``_remesh`` and not shared, so it is not scanned. The rule of a
    node on a shared curve (``ON_CURVE_FRACTION``) is read by the grid's
    interfaces and the periodic cuts alike. Control: a planted source that
    spells the trailing-edge distance as a literal is reported.
    """
    from pyflightstream.workspace._refine import _geometry, _level, _periodic

    values = {float(getattr(_geometry, name)) for name in SHARED_THRESHOLDS} - {0.25}
    folder = PACKAGE / "workspace" / "_refine"
    for path in sorted(folder.glob("*.py")):
        if path.stem in ("_geometry", "_remesh", "__init__"):
            continue
        assert _threshold_literals(path.read_text(encoding="utf-8"), values) == [], path.name
    assert _periodic.ON_CURVE_FRACTION is _geometry.ON_CURVE_FRACTION
    assert _level._geometry is _geometry
    assert not hasattr(_periodic, "ON_CUT_FRACTION")
    planted = "def hit(d, scale):\n    return d < 1e-6 * scale\n"
    assert _threshold_literals(planted, values) == [(2, 1e-6)]


def test_a_remeshed_family_at_factor_1_is_copied_unchanged(tmp_path):
    """P0380-REFINE (FR-424, UNCHANGED FAMILY): a family that is not a grid, at factor 1, is a
    remeshed family at factor 1 and is copied as the source holds it: the level writes the
    strip T face for face and refine.json reports it unchanged. Control: at factor 1.5 the
    same strip is remeshed and its faces change."""
    pytest.importorskip("trimesh")
    src = _source(tmp_path, WITH_T)
    verts, fams = read_mesh(src)
    level = refine_mesh(src, 1.0)
    assert level.report["T"]["method"] == "unchanged", level.report["T"]
    lv, lf = read_mesh(level.obj)
    assert face_coordinates(lv, lf["T"]) == face_coordinates(verts, fams["T"])
    other = refine_mesh(src, 1.5, families=["T"])
    assert other.report["T"]["method"] == "remesh"
    ov, of = read_mesh(other.obj)
    assert face_coordinates(ov, of["T"]) != face_coordinates(verts, fams["T"])
