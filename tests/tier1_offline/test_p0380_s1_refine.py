"""P0380-REFINE (FR-915 to FR-928): a level written by refine_mesh and by pyfs-matrix refine.

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
import contextlib
import csv
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path

import numpy
import pytest

import pyflightstream
import pyflightstream.workspace as workspace
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.run import cli
from pyflightstream.workspace import RefinedMesh, refine_mesh
from pyflightstream.workspace._refine._grid import recover_grid
from pyflightstream.workspace.sidecars import ensure_inventory, obj_face_counts
from tests.p0380_mesh_fixtures import (
    Composite,
    body_of_revolution,
    face_coordinates,
    l_sheet,
    read_mesh,
    sheet_with_strips,
    write_source,
)

PACKAGE = Path(pyflightstream.__file__).resolve().parent
#: The row spacings of the triangle strip T beyond the grid's tip station.
STRIP = (0.03, 0.04, 0.05, 0.065, 0.08)
WITH_T = (("T", "tri", STRIP),)
WITH_TU = (("T", "tri", STRIP), ("U", "tri", (0.1, 0.1)))
#: The audit warning the strip T draws beside a refined G (its growth check fails).
GROWTH_ON_T = "audit check growth failed on T"


def test_p0500_retired_refine_requirements_reserve_their_uids():
    """Retired sector and keep-row promises must not remain implemented requirements."""
    root = PACKAGE.parents[1]
    with (root / "tests/requirements_l3.csv").open(encoding="utf-8", newline="") as stream:
        rows = {row["uid"]: row for row in csv.DictReader(stream)}
    retired = (root / "docs/unpublished/requirements/retired.md").read_text(encoding="utf-8")
    identities = json.loads((root / "docs/srs/reserved-ids.json").read_text())
    with (root / "docs/srs/uid-migration.csv").open(encoding="utf-8", newline="") as stream:
        migration = {row["uid"]: row for row in csv.DictReader(stream)}
    retired_uids = {
        427,
        428,
        430,
        942,
        943,
        944,
        945,
        946,
        950,
        951,
        952,
        953,
        954,
        955,
        956,
        957,
        958,
        971,
        1507,
        1508,
        1509,
        1510,
        1511,
        1512,
        1513,
        1516,
        3020,
        3021,
        3023,
    }
    for uid in (f"FR-{number}" for number in sorted(retired_uids)):
        assert uid in identities["reserved_ids"], uid
        assert migration[uid]["destination"] in {"retired", "merged"}, uid
        assert uid not in rows or rows[uid]["status"] == "retired", uid
        assert f"| {uid} |" in retired, uid
    active = (root / "docs/unpublished/requirements/spcm.md").read_text(encoding="utf-8")
    assert "| FR-3020 |" not in active


@pytest.mark.parametrize(
    "key",
    ["keep_first_row", "trailing_edge_direction", "axial", "circumferential", "axis", "origin"],
)
def test_p0500_retired_refine_family_keys_warn_and_skip(tmp_path, key):
    """Even malformed retired values leave the resolved family specification unchanged."""
    from pyflightstream.workspace._refine._config import read_refine_file

    path = tmp_path / "retired.refine.toml"
    base = "[families.G]\nfactor = 2\n"
    path.write_text(base, encoding="utf-8")
    expected = read_refine_file(path, ["G"])
    path.write_text(base + f'{key} = "obsolete"\n', encoding="utf-8")
    with pytest.warns(PyflightstreamWarning, match=key + " is no longer read"):
        assert read_refine_file(path, ["G"]) == expected


def test_p0500_short_factor_tags_keep_exact_record_factors(tmp_path):
    """The retired keep-row suffix is absent while the record retains the exact factor."""
    value = 1.000001
    mesh = source(tmp_path, perimeter=False)
    with pytest.warns(PyflightstreamWarning, match="keep_first_row is no longer read"):
        level = refine_mesh(mesh, value, keep_first_row=["G"])
    assert level.folder.name == "wing_R1"
    assert _json(_record(level))["specs"]["G"]["factor"] == value


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
    """Return the refusal text, checking only its diagnostic PDF was written."""
    pdf = src.with_name(src.stem + ".refine-refusal.pdf")
    before = _snapshot(src.parent)
    with pytest.raises(error) as caught:
        refine_mesh(src, *args, **kwargs)
    text = str(caught.value)
    assert text.endswith(f"A diagnostic PDF: {pdf}."), text
    assert pdf.read_bytes().startswith(b"%PDF")
    assert _left(root) == []
    after = _snapshot(src.parent)
    before.pop(pdf.name, None)
    after.pop(pdf.name)
    assert after == before
    return text


def _command(capsys, *argv: str) -> tuple[int, str, str]:
    """Run ``pyfs-matrix refine`` in-process; return the exit status, stdout and stderr."""
    capsys.readouterr()
    code = cli.main(["refine", *argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _record(level: RefinedMesh) -> Path:
    """Return the level's ``refine.json``, whatever the per-family files before it."""
    return next(p for p in level.files if p.name.endswith(".refine.json"))


# ---------------------------------------------------------------- FR-915 factors


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan")], ids=["zero", "negative", "nan"])
def test_r1_a_factor_not_above_zero_is_refused_by_both_routes(tmp_path, capsys, value):
    """P0380-REFINE (FR-915, FR-925): zero, negative and not-a-number factors are refused.

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
    """P0380-REFINE (FR-915, FR-925): FACTOR ``two`` is refused alike by the function and command.

    The command exits 2 with the function's own text, which names the value
    and ends with its diagnostic PDF path. Control: the number 2 passes both.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src, "two")
    assert f"{src} FACTOR: the factor 'two' is not a number; give a number above zero" in text
    code, _, err = _command(capsys, str(src), "two")
    assert code == 2 and text in err and _left(tmp_path) == []
    assert isinstance(refine_mesh(src, 2.0), RefinedMesh)
    assert _command(capsys, str(src), "2", "--overwrite")[0] == 0


@pytest.mark.parametrize("flag", ["normal", "parallel"])
def test_r1_a_direction_that_is_not_a_number_is_refused_by_both_routes(tmp_path, capsys, flag):
    """P0380-REFINE (FR-915, FR-925): ``--normal two`` and ``--parallel two`` alike.

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
        (
            {"factor": 0.05, "force_factors": False},
            ["0.05", "--strict-factors"],
            "the normal factor is 0.05, below 1/18",
        ),
        (
            {"factor": 1.0, "parallel": 0.1, "force_factors": False},
            ["1", "--parallel", "0.1", "--strict-factors"],
            "parallel factor is 0.1",
        ),
    ],
    ids=["factor", "spanwise"],
)
def test_r1_a_factor_below_one_over_m_is_refused_naming_family_direction_value(
    tmp_path, capsys, kwargs, argv, said
):
    """P0380-REFINE (FR-915, FR-925): a factor leaving no interval is refused before any work.

    The grid G has 18 chordwise and 8 spanwise intervals. Control: exactly
    1/8 spanwise is accepted by the command and leaves one interval.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src, **kwargs)
    assert text.startswith("family G: ") and said in text
    code, _, err = _command(capsys, str(src), *argv)
    assert code == 2 and text in err and _left(tmp_path) == []
    code, _, _ = _command(capsys, str(src), "1", "--parallel", "0.125")
    assert code == 0
    report = _json(tmp_path / "wing_R1s0p125" / "wing_R1s0p125.refine.json")
    assert report["families"]["G"]["intervals"]["spanwise"] == [8, 1]


# ------------------------------------------------- FR-916 where the factors come from


def test_r2_factor_applies_and_normal_replaces_one_direction(tmp_path):
    """P0380-REFINE (FR-916, FR-919): FACTOR doubles both directions; --normal replaces one.

    Control: the same FACTOR without --normal doubles the chordwise count.
    """
    src = _source(tmp_path)
    both = refine_mesh(src, 2.0)
    one = refine_mesh(src, 2.0, normal=1.0)
    assert both.report["G"]["intervals"] == {"chordwise": [18, 36], "spanwise": [8, 16]}
    assert one.report["G"]["intervals"] == {"chordwise": [18, 18], "spanwise": [8, 16]}
    assert (both.folder.name, one.folder.name) == ("wing_R2", "wing_R2c1")


def test_r2_the_file_gives_the_factors_only_when_the_call_gives_none(tmp_path):
    """P0380-REFINE (FR-916): ``<stem>.refine.toml`` is read for factors only without FACTOR.

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
    assert _json(_record(called))["config"] == "wing.refine.toml"
    other = tmp_path / "coarse.toml"
    other.write_bytes(
        b'[[perimeter]]\nfile = "src/wing.te_nodes.txt"\nexport_te_per_family = true\n'
        b'[refine]\ntag = "coarse"\n\n[families.G]\nfactor = 0.5\n'
    )
    named = refine_mesh(src, config=other)
    assert named.folder.name == "wing_coarse"
    assert named.report["G"]["intervals"]["spanwise"] == [8, 4]


def test_r2_components_are_read_whatever_gives_the_factors(tmp_path):
    """P0380-REFINE (FR-916; FR-935): [components] applies when FACTOR is given.

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
    """P0380-REFINE (FR-916, FR-925): ``--families`` selects when the file gives the factors.

    The file states factor 2 for A and B; ``families=["A"]`` changes A alone
    and B is written as the source holds it. A selected name the mesh does
    not hold is refused on this route as on the FACTOR route, and so is a
    selection the file states no factor for. Control: without the selection
    both tubes are refined.

    Release review of 0.38.0: proves the fix of RV-05.
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
    """P0380-REFINE (FR-916, FR-918): a [families.*] table the refinement does not read is said.

    With FACTOR, the file's family tables are not read for their factors
    (FR-916), and with ``--families`` on the file's factors an unselected table is
    not read: each is a warning naming the tables, and ``refine.json`` lists
    them under ``ignored_families_tables``. Control: the file's factors for
    every family warn of nothing and record an empty list.

    Release review of 0.38.0: proves the fix of RV-05.
    """
    src = _two_tubes(tmp_path, BOTH_TABLES)
    with pytest.warns(PyflightstreamWarning, match=r"\[families\.A\], \[families\.B\]") as seen:
        called = refine_mesh(src, 1.0, out_dir=tmp_path / "called")
    assert "FACTOR, --parallel or --normal gives the factors" in str(seen[0].message)
    assert _json(_record(called))["ignored_families_tables"] == ["A", "B"]
    with pytest.warns(PyflightstreamWarning, match=r"\[families\.B\]") as seen:
        one = refine_mesh(src, families=["A"], out_dir=tmp_path / "one")
    assert "--families selects A" in str(seen[0].message)
    assert _json(_record(one))["ignored_families_tables"] == ["B"]
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        every = refine_mesh(src, out_dir=tmp_path / "every")
    assert not [w for w in caught if "families." in str(w.message)]
    assert _json(_record(every))["ignored_families_tables"] == []


def test_r2_no_factor_and_no_file_is_refused_by_both_routes(tmp_path, capsys):
    """P0380-REFINE (FR-916, FR-925): no FACTOR, no direction and no file is refused.

    A file that states no factor (only [components]) is refused the same way.
    Control: the same command with FACTOR exits 0.
    """
    src = _source(tmp_path)
    text = _refused(tmp_path, src)
    assert (
        f"{src}: no factor was given and no refinement file states one; give FACTOR "
        f"or add a [families.<name>] factor table to {src.with_name('wing.refine.toml')}. "
        f"No level was written. A diagnostic PDF: {src.with_suffix('.refine-refusal.pdf')}."
    ) == text
    code, _, err = _command(capsys, str(src))
    assert code == 2 and text in err and _left(tmp_path) == []
    src.with_name("wing.refine.toml").write_bytes(b'[components]\nAll = ["G"]\n')
    assert _refused(tmp_path, src) == text
    assert _command(capsys, str(src), "1")[0] == 0


def test_r2_a_direction_on_a_remeshed_family_is_refused(tmp_path):
    """P0380-REFINE (FR-916, FR-925): --normal on a family that is no grid is refused.

    T recovers no grid, so it would be remeshed. Control: --normal on G
    alone is accepted, and ``accept_remesh`` warns and remeshes T with its factor.

    PUSH-W12-QA-2: the growth check of the strip T fails on this fixture, a
    warning the test asserts, so it fails if the warning disappears.
    """
    src = _source(tmp_path, WITH_T)
    text = _refused(tmp_path, src, normal=2.0)
    assert text.startswith(f"{src} family T: parallel_factor and normal_factor apply to a grid, ")
    assert "this family is remeshed" in text and "--accept-remesh" in text
    with pytest.warns(PyflightstreamWarning, match=GROWTH_ON_T):
        level = refine_mesh(src, normal=2.0, families=["G"])
    assert level.folder.name == "wing_R-G1c2"
    with pytest.warns(PyflightstreamWarning, match="it is remeshed with factor 1"):
        accepted = refine_mesh(src, normal=2.0, accept_remesh=True, out_dir=tmp_path / "acc")
    assert accepted.report["T"]["method"] == "remesh"


def test_arch48_accept_remesh_remeshes_a_demanded_grid_that_is_not_recovered(tmp_path):
    """ARCH48-R2: ``method = "grid"`` on T is refused; ``accept_remesh`` warns and remeshes it."""
    toml = '[families.T]\nfactor = 2\nmethod = "grid"\n'
    src = _source(tmp_path, WITH_T, refine_toml=toml)
    assert "method is grid and no grid was recovered" in _refused(tmp_path, src)
    with pytest.warns(PyflightstreamWarning, match="it is remeshed with factor 2"):
        level = refine_mesh(src, accept_remesh=True, out_dir=tmp_path / "acc")
    assert level.report["T"]["method"] == "remesh"


def test_arch48_accept_unknown_skips_the_entries_the_refinement_does_not_know(tmp_path):
    """ARCH48-R1: unknown tables, keys, family tables, members and names are refused by default.

    Under ``accept_unknown`` each is warned and skipped, and the level is
    written from what is known.
    """
    toml = (
        "[extra]\nx = 1\n[refine]\nbogus = 1\n"
        "[families.G]\nfactor = 2\nfactr = 3\n[families.Nope]\nfactor = 2\n"
        '[components]\nAll = ["G", "Ghost"]\nNone = ["Phantom"]\n'
    )
    src = _source(tmp_path, WITH_T, refine_toml=toml)
    assert "unknown table [extra]" in _refused(tmp_path, src)
    with pytest.warns(PyflightstreamWarning) as caught:
        level = refine_mesh(
            src, families=["G", "Missing"], accept_unknown=True, out_dir=tmp_path / "acc"
        )
    said = "\n".join(str(w.message) for w in caught)
    for word in ("[extra]", "'bogus'", "'factr'", "'Nope'", "'Ghost'", "None names no", "Missing"):
        assert word in said, word
    assert level.report["G"]["method"] == "grid"
    assert "All" in level.obj.read_text(encoding="utf-8")


def test_arch48_accept_empty_writes_nothing_when_no_trailing_edge_is_found(tmp_path, capsys):
    """ARCH48-R4: no trailing edge found is refused; --accept-empty writes nothing, exit 0."""
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace.wake_edges import write_trailing_edges_identified

    src = _source(tmp_path, WITH_T)
    with pytest.warns(PyflightstreamWarning, match="holds no family 'Nope'"):
        with pytest.raises(InputArtifactError, match="no trailing edge was found on Nope"):
            write_trailing_edges_identified(src, families=["Nope"])
    with pytest.warns(
        PyflightstreamWarning, match="no trailing edge was found.*nothing is written"
    ):
        assert write_trailing_edges_identified(src, families=["Nope"], accept_empty=True) == []
    with pytest.warns(PyflightstreamWarning, match="nothing is written"):
        code = workspace_cli.main(
            ["geometry", "identify-te", str(src), "--families", "Nope", "--accept-empty"]
        )
    assert code == 0 and capsys.readouterr().out == ""
    assert not src.with_name(f"{src.stem}.Nope.fs.te.txt").exists()


def test_arch48_force_factors_raises_a_factor_below_the_least_the_grid_allows(tmp_path):
    """ARCH48-R6: a factor below 1/m is raised to 1/m, warned, by default; strict refuses it.

    G has 18 chordwise and 8 spanwise intervals: 0.05 is raised to 1/18 and 1/8,
    and the level holds one interval in each direction. ``force_factors=False``
    (CLI ``--strict-factors``) refuses it.
    """
    src = _source(tmp_path)
    assert "below 1/18" in _refused(tmp_path, src, factor=0.05, force_factors=False)
    with pytest.warns(PyflightstreamWarning, match="raised to 0.0555556 and 0.125"):
        level = refine_mesh(src, 0.05, out_dir=tmp_path / "acc")
    intervals = level.report["G"]["intervals"]
    assert intervals["chordwise"] == [18, 1] and intervals["spanwise"] == [8, 1]


def test_the_command_raises_a_factor_below_the_least_by_default(tmp_path, capsys):
    """ARCH48-R6: pyfs-matrix refine warns and writes the level; --strict-factors refuses."""
    src = _source(tmp_path)
    with pytest.warns(PyflightstreamWarning, match="raised to 0.0555556"):
        code, _, _ = _command(capsys, str(src), "0.05")
    assert code == 0
    code, _, err = _command(capsys, str(src), "0.05", "--strict-factors", "--overwrite")
    assert code == 2 and "below 1/18" in err


def test_drev48_r2_a_factor_of_one_over_m_is_accepted_for_every_m():
    """DREV48-R2-001: 1/m is the least factor the refusal names, and the one force_factors
    raises to; in floating point (1/49) * 49 is below 1, so for 49 intervals both were
    refused. Control: a factor just below 1/m stays refused.
    """
    from pyflightstream.workspace._refine._grid import check_factors, least_factors
    from tests.p0380_mesh_fixtures import Fixture, build_grid

    fx = build_grid(Fixture("sheet", False, 9, 50, ("edge", "edge"), None))
    grid = recover_grid(fx.verts, fx.faces, fx.te)
    assert grid.intervals == (49, 8)
    check_factors(grid, "G", chordwise=1 / 49, spanwise=1 / 8)
    least = least_factors(grid, 0.001, 0.001)
    check_factors(grid, "G", chordwise=least[0], spanwise=least[1])
    with pytest.raises(InputArtifactError, match="below 1/49"):
        check_factors(grid, "G", chordwise=0.0204, spanwise=1.0)


def test_arch48_accept_unknown_skips_an_implicit_refine_file_that_cannot_be_read(tmp_path):
    """ARCH48-R7: a <stem>.refine.toml that is not TOML is refused; accept_unknown skips it.

    The factors then come from FACTOR. Control: the same file named by
    ``config`` stays refused under the option.
    """
    src = _source(tmp_path)
    beside = src.with_name("wing.refine.toml")
    beside.write_bytes(b"[families\nfactor = = 2\n")
    assert "cannot be read" in _refused(tmp_path, src, 2.0)
    with pytest.warns(PyflightstreamWarning, match="cannot be read and is not named"):
        level = refine_mesh(src, 2.0, accept_unknown=True, out_dir=tmp_path / "acc")
    assert level.folder.name == "wing_R2" and level.obj.is_file()
    with pytest.raises(InputArtifactError, match="cannot be read"):
        refine_mesh(src, 2.0, config=beside, accept_unknown=True, out_dir=tmp_path / "c")


def test_arch48_accept_unknown_skips_the_values_the_refinement_cannot_read(tmp_path):
    """ARCH48-R3: a value of the wrong kind in the refinement file is refused by default.

    Under ``accept_unknown`` the key takes its default (method auto, elements
    triangles), a table left with no factor is skipped, and a tag that is not
    one folder name falls back to the built one.
    """
    toml = (
        '[refine]\ntag = "a/b"\nelements = "hexes"\n'
        '[families.G]\nfactor = 2\nmethod = "gird"\nelements = "blobs"\n'
        "[families.T]\nfactor = -1\n"
    )
    src = _source(tmp_path, WITH_T, refine_toml=toml)
    assert "is not an element mode" in _refused(tmp_path, src)
    with pytest.warns(PyflightstreamWarning) as caught:
        level = refine_mesh(src, accept_unknown=True, out_dir=tmp_path / "acc")
    said = "\n".join(str(w.message) for w in caught)
    for word in ("'a/b'", "'hexes'", "'gird'", "'blobs'", "[families.T] factor", "T] states no"):
        assert word in said, word
    assert level.folder.name == "wing_R-G2"
    assert level.report["G"]["method"] == "grid"
    assert level.report["T"]["method"] in ("unchanged", "copied")


# --------------------------------------------------------- FR-917 the refinement file


@pytest.mark.parametrize(
    ("toml", "said"),
    [
        (
            "[families.G]\nfactr = 2\n",
            "[families.G]: unknown key 'factr'; the known keys are factor, "
            "parallel_factor, normal_factor, method, elements",
        ),
        (
            "[families.Fin]\nfactor = 2\n",
            "[families.Fin]: the mesh holds no family 'Fin'; it holds G",
        ),
        (
            '[families.G]\nmethod = "remesh"\nnormal_factor = 2\n',
            "[families.G]: parallel_factor and normal_factor apply to a grid; "
            "a remeshed family takes factor",
        ),
        (
            '[families.G]\nmethod = "grid"\n',
            "the table states no factor, parallel_factor or normal_factor",
        ),
        (
            '[refinement]\ntag = "x"\n',
            "unknown table [refinement]; the tables are refine, families, components, perimeter",
        ),
    ],
    ids=["unknown-key", "unknown-family", "chordwise-on-remesh", "no-factor", "unknown-table"],
)
def test_r3_the_refinement_file_is_refused_naming_file_table_and_key(tmp_path, capsys, toml, said):
    """P0380-REFINE (FR-917, FR-925): each bad file is refused by both routes, naming its path.

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
    """P0380-REFINE (FR-917, FR-925): valid TOML whose table is a scalar, a list or falsey.

    Each is refused by the function and the command alike with the standard
    refusal (the file, the table, what to write, its diagnostic PDF path), not
    a Python exception. The factor is given in the call, so the file is read
    only for its tables. Control: the file's tables written as tables pass.

    Release review of 0.38.0: proves the fix of RV-07.
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


# ---------------------------------------------------------- FR-918 what a level holds


def test_r4_a_level_holds_its_files_and_refine_json_reports_each_family(tmp_path):
    """P0380-REFINE (FR-918, FR-919, FR-923): the five files, the record and the audit beside it.

    G is a grid, T is remeshed (no grid recovered), U is copied; the source's
    folder is not touched. The returned RefinedMesh is frozen and names every
    file the folder holds.
    """
    src = _source(tmp_path, WITH_TU)
    before = _snapshot(src.parent)
    level = refine_mesh(src, 2.0, families=["G", "T"])
    stem = "wing_R-G2-T2"
    suffixes = (
        ".obj",
        ".te.txt",
        ".obj.boundaries.toml",
        ".G.te.txt",
        # FR-3296: the quad families' trailing edges for the solver and as ANSA node lists
        ".nodes.te.txt",
        ".nodes.txt",
        ".G.fs.te.txt",
        ".G.nodes.txt",
        ".refine.json",
        ".audit.json",
    )
    names = [stem + suffix for suffix in suffixes]
    assert [p.name for p in level.files] == names
    assert sorted(p.name for p in level.folder.iterdir()) == sorted(names)
    assert level.folder == tmp_path / stem and level.obj == level.files[0]
    assert _snapshot(src.parent) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        level.folder = tmp_path  # type: ignore[misc]
    record = _json(level.folder / f"{stem}.refine.json")
    faces = {n: len(fs) for n, fs in read_mesh(level.obj)[1].items()}
    assert record["schema_version"] == 2 and record["source"] == "wing.obj"
    assert record["level"] == stem and record["faces"] == faces
    g, t, u = (record["families"][n] for n in ("G", "T", "U"))
    assert g["method"] == "grid" and g["reason"].startswith("a sheet of 9 stations by 19")
    assert g["faces"] == [144, 576] and g["layout"] == "sheet"
    assert g["trailing_edge"] == "perimeter" and len(g["trailing_edge_points"]) > 0
    assert t["method"] == "remesh" and t["reason"].startswith("no grid recovered: ")
    assert (t["faces_before"], t["faces_after"]) == (180, faces["T"])
    assert u == {"method": "copied"} and faces["U"] == 72
    assert record["families"] == level.report
    te = (level.folder / f"{stem}.te.txt").read_text(encoding="utf-8").splitlines()
    assert te[0] == "METER" and len(te) == 1 + 16
    side = (level.folder / f"{stem}.obj.boundaries.toml").read_text(encoding="utf-8")
    assert 'file = "wing.te.txt"' in side
    audit = _json(level.folder / f"{stem}.audit.json")
    assert (audit["schema_version"], audit["mesh"], audit["source"]) == (
        1,
        f"{stem}.obj",
        "wing.obj",
    )
    assert level.audit is not None and level.audit.path == level.files[-1]


def test_r4_r9_a_source_without_points_file_gets_none_and_auto_remeshes(tmp_path):
    """P0380-REFINE (FR-918, FR-923): no points file in, none out; auto names why it remeshed.

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


# ------------------------------------------------------ FR-919 where a level goes


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
    """P0380-REFINE (FR-919): the tag forms, and the default out-dir is the source's parent.

    Control: ``out_dir`` places the same level in the folder it names.

    PUSH-W12-QA-2: with the strip T beside G (the subset case) its growth
    check fails, a warning asserted on both calls.
    """
    src = _source(tmp_path, strips, refine_toml=toml)

    def warned():
        if strips:
            return pytest.warns(PyflightstreamWarning, match=GROWTH_ON_T)
        return contextlib.nullcontext()

    with warned():
        level = refine_mesh(src, **kwargs)
    assert level.folder == tmp_path / folder and _left(tmp_path) == [folder]
    other = tmp_path / "elsewhere"
    with warned():
        moved = refine_mesh(src, out_dir=other, **kwargs)
    assert moved.folder == other / folder and _left(other) == [folder]
    assert _left(tmp_path) == sorted([folder, "elsewhere"])


def test_r5_the_command_writes_the_tagged_level_and_prints_its_files(tmp_path, capsys):
    """P0380-REFINE (FR-919): the command exits 0 and prints each file it wrote."""
    src = _source(tmp_path)
    code, out, _ = _command(capsys, str(src), "1", "--normal", "1.5", "--parallel", "0.7")
    folder = tmp_path / "wing_R1c1p5s0p7"
    assert code == 0 and "G: grid" in out
    for path in sorted(folder.iterdir()):
        assert str(path) in out


def test_r5_the_refine_help_states_its_exit_status_beside_audit_meshs(capsys):
    """P0380-REFINE (FR-424; FR-937): ``refine --help`` says a failed audit still exits 0.

    The help states that ``refine`` exits 0 when the level is written, a
    failed audit being a warning with the audit written, that ``audit-mesh``
    exits 1 on a failed audit, and that a refusal exits 2. Control: the
    ``audit-mesh`` help states its own exit status.
    """
    help_text = {}
    for verb in ("refine", "audit-mesh"):
        capsys.readouterr()
        with pytest.raises(SystemExit):
            cli.main([verb, "--help"])
        help_text[verb] = " ".join(capsys.readouterr().out.split())
    said = help_text["refine"]
    assert "Exits 0 when the level is written, even when its audit fails" in said, said
    # argparse may wrap the help at the hyphen of "audit-mesh".
    assert "audit-mesh exits 1 on the same audit" in said.replace("audit- mesh", "audit-mesh")
    assert "Exits 2 when the request is refused" in said
    assert "Exits 0 when every gate and check passes, 1 when one fails" in help_text["audit-mesh"]


def test_r5_an_existing_level_is_refused_unless_overwrite(tmp_path, capsys):
    """P0380-REFINE (FR-919, FR-925): a second run is refused and leaves the first level alone.

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
        f"No level was written. A diagnostic PDF: {src.with_suffix('.refine-refusal.pdf')}."
    )
    code, _, err = _command(capsys, str(src), "2")
    assert code == 2 and text in err
    assert _snapshot(first.folder) == kept and _left(tmp_path) == ["wing_R2"]
    code, _, _ = _command(capsys, str(src), "2", "--overwrite")
    assert code == 0 and not (first.folder / "planted.txt").exists()
    assert _left(tmp_path) == ["wing_R2"]


def test_r5_an_error_while_writing_leaves_no_level_and_no_partial_folder(
    tmp_path, capsys, monkeypatch
):
    """P0380-REFINE (FR-919): an error in the write step leaves no level and no ``.partial``.

    The publish fails after the files were written into the staging folder (a
    file occupying the level's path is refused before any work, X-F-0599, so the
    failure is made at the publish): the staging folder is removed and the
    existing level is kept; the command exits 2 the same way. Control: a
    ``.partial`` folder the run did not create, which the observation sees, is
    kept by the next run that writes that level, whose own staging folder is
    gone (IND-01).
    """
    src = _source(tmp_path)
    occupied = tmp_path / "wing_R2"
    occupied.mkdir()
    (occupied / "keep.txt").write_bytes(b"occupied")
    real_rename = Path.rename

    def rename(self, target):
        if self.parent.name.startswith("wing_R2.partial-") and self.name == "wing_R2":
            raise OSError("the publish failed")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError):
        refine_mesh(src, 2.0, overwrite=True)
    assert _left(tmp_path) == ["wing_R2"] and (occupied / "keep.txt").read_bytes() == b"occupied"
    code, _, err = _command(capsys, str(src), "2", "--overwrite")
    assert code == 2 and err.strip() and _left(tmp_path) == ["wing_R2"]
    monkeypatch.undo()
    stale = tmp_path / "wing_R0p5.partial"
    stale.mkdir()
    (stale / "stale.txt").write_bytes(b"x")
    assert _left(tmp_path) == ["wing_R0p5.partial", "wing_R2"]
    refine_mesh(src, 0.5)
    assert _left(tmp_path) == ["wing_R0p5", "wing_R0p5.partial", "wing_R2"]
    assert (stale / "stale.txt").read_bytes() == b"x"


def _resampled_while(call) -> list[str]:
    """Run ``call()`` and return the grid resamplings it started (a profile, no patching)."""
    seen: list[str] = []

    def profile(frame, event, arg):
        if event == "call" and frame.f_code.co_name in ("refine_grid", "refine_blocks"):
            seen.append(frame.f_code.co_name)

    sys.setprofile(profile)
    try:
        call()
    finally:
        sys.setprofile(None)
    return seen


@pytest.mark.parametrize(
    ("sidecar", "said"),
    [
        ('boundaries = ["G"\n', "not TOML"),
    ],
    ids=["malformed-sidecar"],
)
def test_r11_a_sidecar_the_audit_refuses_is_refused_before_any_work(
    tmp_path, capsys, sidecar, said
):
    """P0380-REFINE (FR-919, FR-925; FR-938 G4): the inputs the audit reads are checked first.

    A boundaries file naming a points file that does not exist, or that is not
    TOML, is refused by the function and the command before any family is
    resampled (a profile records every call of the grid resampling), and no
    level folder is published. With ``overwrite`` the level already there is
    kept byte for byte. Controls: the audit refuses the same sidecar with the
    same reason, and the profile sees the resampling of a run that is not
    refused.

    Release review of 0.38.0: proves the fix of RV-01.
    """
    from pyflightstream.workspace import audit_mesh

    src = _source(tmp_path)
    assert _resampled_while(lambda: refine_mesh(src, 2.0)) == ["refine_grid"]
    first = tmp_path / "wing_R2"
    kept = _snapshot(first)
    src.with_name("wing.boundaries.toml").write_bytes(sidecar.encode("utf-8"))
    caught: list[InputArtifactError] = []

    def refused() -> None:
        with pytest.raises(InputArtifactError) as error:
            refine_mesh(src, 2.0, overwrite=True)
        caught.append(error.value)

    assert _resampled_while(refused) == []
    text = str(caught[0])
    assert said in text and text.endswith(
        f"A diagnostic PDF: {src.with_suffix('.refine-refusal.pdf')}."
    ), text
    assert _left(tmp_path) == ["wing_R2"] and _snapshot(first) == kept
    code, _, err = _command(capsys, str(src), "1")
    assert code == 2 and said in err and _left(tmp_path) == ["wing_R2"]
    with pytest.raises(InputArtifactError, match=said):
        audit_mesh(src)


def test_r5_an_audit_that_raises_publishes_nothing_and_keeps_the_old_level(tmp_path):
    """P0380-REFINE (FR-918, FR-919): the level is published only after its audit is written.

    The audit runs inside the staging folder. Coarsening the strip T at 0.5
    fails its growth check, a warning, which a caller running with warnings
    as errors turns into an exception raised by the audit: no level folder is
    published, no staging folder is left, and with ``overwrite`` the previous
    level is kept byte for byte. Control: the same call with warnings shown
    replaces the level, and the returned audit names the published folder.

    Release review of 0.38.0: proves the fix of RV-01.
    """
    import warnings

    pytest.importorskip("trimesh")
    src = _source(tmp_path, WITH_T)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        first = refine_mesh(src, 0.5)
    assert not first.audit.passed
    (first.folder / "planted.txt").write_bytes(b"x")
    kept = _snapshot(first.folder)
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        with pytest.raises(PyflightstreamWarning, match="audit check growth failed on T"):
            refine_mesh(src, 0.5, overwrite=True)
        assert _left(tmp_path) == ["wing_R0p5"] and _snapshot(first.folder) == kept
        with pytest.raises(PyflightstreamWarning):
            refine_mesh(src, 0.5, out_dir=tmp_path / "other")
        assert not any((tmp_path / "other").iterdir())
    with pytest.warns(PyflightstreamWarning, match="growth failed on T"):
        level = refine_mesh(src, 0.5, overwrite=True)
    assert not (level.folder / "planted.txt").exists() and _left(tmp_path) == ["other", "wing_R0p5"]
    assert level.audit is not None
    assert level.audit.path == level.folder / "wing_R0p5.audit.json" == level.files[-1]
    assert level.audit.mesh == level.obj and level.audit.path.is_file()


#: The same boundaries file spelled in six legal TOML ways (the fixture's own form first).
SIDECARS = {
    "double-quoted": (
        'boundaries = ["G", "T"]\n\n[trailing_edges]\nfile = "wing.te.txt"\ntype = "STANDARD"\n'
    ),
    "literal-strings": (
        "boundaries = ['G', 'T']\n[trailing_edges]\nfile = 'wing.te.txt'\ntype = 'STANDARD'\n"
    ),
    "multi-line-commented": (
        '# the boundaries\nboundaries = [\n  "G", # the grid\n  "T",\n] # end\n'
        '[trailing_edges]\nfile = "wing.te.txt" # the points\ntype = "STANDARD"\n'
    ),
    "inline-table-escapes": (
        'boundaries = ["\\u0047", "T"]\n'
        'trailing_edges = { file = "wing\\u002ete.txt", type = "STANDARD" }\n'
    ),
    "dotted-key": (
        "boundaries = ['G', 'T']\ntrailing_edges.file = 'wing.te.txt'\n"
        "trailing_edges.type = 'STANDARD'\n"
    ),
    "quoted-keys": (
        '"boundaries" = ["G", "T"]\n"trailing_edges"."file" = "wing.te.txt"\n'
        '"trailing_edges"."type" = "STANDARD"\n'
    ),
}


def test_p0430_f1492_detection_selectors_follow_the_component_grouping(tmp_path):
    """F-1492: ``detect = { surfaces = [...] }`` names the components, never the removed members."""
    import tomllib

    src = _source(tmp_path, WITH_T, refine_toml='[components]\nWing = ["G", "T"]\n')
    text = (
        'boundaries = ["G", "T"]\n'
        "[trailing_edges]\n"
        'detect = { surfaces = ["G", "T"], sweep_angle = 20 }\n'
    )
    src.with_name("wing.boundaries.toml").write_text(text, encoding="utf-8")
    level = refine_mesh(src, 1.0)
    written = tomllib.loads(level.files[2].read_text(encoding="utf-8"))
    assert written["boundaries"] == ["Wing"]
    assert written["trailing_edges"]["detect"] == {"surfaces": ["Wing"], "sweep_angle": 20}


def test_rb5_f1492_the_wake_termination_selector_follows_the_component_grouping(tmp_path):
    """F-1492 (RB5): ``[wake_termination] detect = { surfaces = [...] }`` is the other table whose
    selector names families; a grouped level names the component there too, never a member the
    level no longer holds. Control: the trailing-edge selector is rewritten beside it."""
    import tomllib

    src = _source(tmp_path, WITH_T, refine_toml='[components]\nWing = ["G", "T"]\n')
    text = (
        'boundaries = ["G", "T"]\n'
        "[trailing_edges]\n"
        'detect = { surfaces = ["G", "T"], sweep_angle = 20 }\n'
        "[wake_termination]\n"
        'detect = { surfaces = ["T", "G"] }\n'
    )
    src.with_name("wing.boundaries.toml").write_text(text, encoding="utf-8")
    level = refine_mesh(src, 1.0)
    written = tomllib.loads(level.files[2].read_text(encoding="utf-8"))
    assert written["trailing_edges"]["detect"]["surfaces"] == ["Wing"]
    assert written["wake_termination"]["detect"] == {"surfaces": ["Wing"]}


@pytest.mark.parametrize("spelling", list(SIDECARS))
def test_r4_the_boundaries_file_is_rewritten_by_its_toml_values(tmp_path, spelling):
    """P0380-REFINE (FR-918; FR-935): the level's boundaries file is the source's, rewritten.

    The source's boundaries file is spelled with literal strings, comments,
    a multi-line array, an inline table with escapes or a dotted key, beside
    an unrelated ``[import]`` table and a comment. With ``[components]
    Wing = ["G", "T"]`` the level's file names the component and the new
    points file, its other values are the source's, its comments are kept, and
    its boundaries are the output OBJ's families. Control: the fixture's own
    double-quoted spelling gives the same values.

    Release review of 0.38.0: proves the fix of RV-06.
    """
    text = SIDECARS[spelling] + '\n[import]\nunits = "METER" # stated, never assumed\n'
    src = _source(tmp_path, WITH_T, refine_toml='[components]\nWing = ["G", "T"]\n')
    src.with_name("wing.boundaries.toml").write_text(text, encoding="utf-8")
    level = refine_mesh(src, 1.0)
    written = level.files[2].read_text(encoding="utf-8")
    import tomllib

    values = tomllib.loads(written)
    assert values["boundaries"] == ["Wing"] == list(read_mesh(level.obj)[1])
    assert (
        values["trailing_edges"] == {"file": "wing.te.txt", "type": "STANDARD"}
        and level.files[1].is_file()
    )
    assert values["import"] == {"units": "METER"} and "# stated, never assumed" in written
    if spelling == "multi-line-commented":
        assert "# the points" in written and written.startswith("# the boundaries\n")
    assert next(g for g in level.audit.gates if g.name == "G4").passed


def _points_in(src: Path, unit: str, scale: float, mesh_unit: str | None) -> list[str]:
    """Rewrite the source's points file in ``unit`` (coordinates times ``scale``).

    The boundaries file gains ``[import] units = mesh_unit`` when one is given;
    return the rows written after the unit line.
    """
    side = src.with_name("wing.boundaries.toml")
    if mesh_unit is not None:
        side.write_text(
            side.read_text(encoding="utf-8") + f'\n[import]\nunits = "{mesh_unit}"\n',
            encoding="utf-8",
        )
    points = src.with_name("wing.te.txt")
    rows = points.read_text(encoding="utf-8").split()[1:]
    scaled = [",".join(repr(float(x) * scale) for x in row.split(",")) for row in rows]
    points.write_text("\n".join([unit, *scaled]) + "\n", encoding="utf-8")
    return scaled


def _g4(audit) -> dict:
    return dict(next(g for g in audit.gates if g.name == "G4").values)


@pytest.mark.parametrize("factor", [1.0, 2.0])
def test_r4_points_in_another_unit_are_converted_to_the_meshs_unit(tmp_path, capsys, factor):
    """P0380-REFINE (FR-918, FR-920; FR-938 G4): the points file's unit line is honoured.

    The OBJ is in metres (``[import] units = "METER"`` of its boundaries file,
    the package's convention) and its trailing-edge points are the same
    physical mid-points written in millimetres. The audit matches every point
    to an edge, and the level's points file keeps the MILLIMETER unit line with
    one mid-point per trailing-edge edge, in millimetres; the level's audit
    passes G4 with the source's chain count. At factor 1 the level's points are
    the source's. Controls: the same file declaring the mesh in MILLIMETER
    matches no point (G4 fails), and a unit that names no scale is refused.

    Release review of 0.38.0: proves the fix of RV-02.
    """
    src = _source(tmp_path)
    rows = _points_in(src, "MILLIMETER", 1000.0, "METER")
    from pyflightstream.workspace import audit_mesh

    alone = audit_mesh(src)
    assert _g4(alone)["points_on_edges"] == _g4(alone)["points"] == len(rows) > 0
    capsys.readouterr()
    assert cli.main(["audit-mesh", str(src)]) == 0
    alone.path.unlink()
    level = refine_mesh(src, factor)
    lines = level.files[1].read_text(encoding="utf-8").split()
    assert level.files[1].name == f"{level.folder.name}.te.txt"
    # The trailing edge now comes from the perimeter nodes, in the mesh's unit.
    assert lines[0] == "METER"
    written = numpy.array([[float(x) for x in r.split(",")] for r in lines[1:]])
    source = numpy.array([[float(x) for x in r.split(",")] for r in rows]) / 1000.0
    if factor == 1.0:
        assert numpy.allclose(written, source, rtol=0, atol=1e-6)
    else:
        assert len(written) == 2 * len(source)
    g4 = _g4(level.audit)
    assert g4["points_on_edges"] == g4["points"] == len(written)
    assert g4["chains"] == g4["source_chains"] == 1 and level.audit.passed
    control = _source(tmp_path / "control")
    _points_in(control, "MILLIMETER", 1000.0, "MILLIMETER")
    assert _g4(audit_mesh(control))["points_on_edges"] == 0
    other = _source(tmp_path / "other")
    _points_in(other, "OTHER", 1.0, "METER")
    with pytest.raises(InputArtifactError, match="OTHER"):
        audit_mesh(other)


# ----------------------------------------------------------------- FR-921 face order


def _mesh_lines(path: Path, tags: tuple[str, ...] = ("v", "g", "f")) -> list[str]:
    """Return the OBJ's lines of the given statements, in order (the header aside)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.split(" ", 1)[0] in tags]


def test_r7_factor_one_writes_the_sources_vertex_and_face_lines(tmp_path):
    """P0380-REFINE (FR-921): at factor 1 the OBJ's v and f lines are the source's, in order.

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


def _sheet_source(folder: Path, scale: float) -> tuple[Path, numpy.ndarray]:
    """Write the L-shaped multiblock sheet scaled by ``scale``, each coordinate round-trip exact."""
    sheet = l_sheet()
    verts = sheet.verts * scale
    lines = ["v " + " ".join(format(float(x), ".17g") for x in p) for p in verts] + ["g S"]
    lines += ["f " + " ".join(str(v + 1) for v in f) for f in sheet.faces]
    folder.mkdir(parents=True)
    src = folder / "plate.obj"
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return src, verts


@pytest.mark.parametrize("scale", [1e-7, 0.01, 1.0, 1e3])
def test_r7_factor_one_keeps_every_source_coordinate_at_any_precision(tmp_path, scale):
    """P0380-REFINE (FR-921; FR-938 G1, G6): coordinates are written so they read back equal.

    A source written with 17 significant digits, at scales from 1e-7 to 1e3,
    refined at factor 1 reads back with every coordinate equal to the
    source's and G6 passes; refined at factor 2 its new nodes stay distinct
    (G1 finds no two nodes at one position). Control: the source's
    coordinates written with nine decimals, as the writer wrote them, are
    not the source's at these scales.

    Release review of 0.38.0: proves the fix of RV-10.
    """
    src, verts = _sheet_source(tmp_path / "src", scale)
    level = refine_mesh(src, 1.0)
    new, _ = read_mesh(level.obj)
    assert numpy.array_equal(new, verts)
    assert all(g.passed for g in level.audit.gates)
    assert next(g for g in level.audit.gates if g.name == "G6").verdict == "pass"
    finer = refine_mesh(src, 2.0)
    g1 = next(g for g in finer.audit.gates if g.name == "G1")
    assert g1.values["node_pairs_at_one_position"] == 0 and g1.passed
    nine = numpy.array([[float(f"{x:.9f}") for x in p] for p in verts])
    assert scale == 1.0 or not numpy.array_equal(nine, verts)


def _swap_two_faces(obj: Path) -> None:
    """Exchange the first two face lines of an OBJ in place."""
    lines = obj.read_text(encoding="utf-8").splitlines()
    a, b = [i for i, line in enumerate(lines) if line.startswith("f ")][:2]
    lines[a], lines[b] = lines[b], lines[a]
    obj.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("components", [None, '[components]\nWing = ["G"]\n'])
def test_r7_a_saved_factor_one_level_is_reaudited_with_g6(tmp_path, capsys, components):
    """P0380-REFINE (FR-921; FR-937, FR-938 G6): G6 is judged from the level's refine.json.

    refine.json lists the grid families written at factor 1 (a component
    whose every member is one counts as one), and audit_mesh, and so the
    command, read it for a level audited against the source it names. A saved
    factor-1 level with two faces exchanged fails G6 and audit-mesh exits 1.
    Controls: the unmodified level passes with G6 judged; refine.json naming
    another source leaves G6 not judged.

    Release review of 0.38.0: proves the fix of RV-09.
    """
    from pyflightstream.workspace import audit_mesh

    src = _source(tmp_path, refine_toml=components)
    level = refine_mesh(src, 1.0)
    family = "G" if components is None else "Wing"
    record = _json(_record(level))
    assert record["unchanged_grids"] == [family]
    again = audit_mesh(level.obj, against=src)
    assert [(g.family, g.verdict) for g in again.gates if g.name == "G6"] == [(family, "pass")]
    _swap_two_faces(level.obj)
    failed = audit_mesh(level.obj, against=src)
    assert [(g.family, g.verdict) for g in failed.gates if g.name == "G6"] == [(family, "fail")]
    capsys.readouterr()
    assert cli.main(["audit-mesh", str(level.obj), "--against", str(src)]) == 1
    record["source"] = "another.obj"
    _record(level).write_text(json.dumps(record), encoding="utf-8")
    other = audit_mesh(level.obj, against=src)
    assert next(g for g in other.gates if g.name == "G6").verdict == "not judged"


# --------------------------------------------------------------------- FR-923 method


def test_r9_method_grid_without_a_grid_is_refused_and_auto_remeshes(tmp_path):
    """P0380-REFINE (FR-923, FR-925): ``grid`` on T is refused naming why; ``auto`` remeshes it.

    Controls: ``grid`` on G (a recovered grid) is accepted, and ``remesh``
    on G remeshes it although it is a grid, giving that reason.
    """
    toml = '[families.T]\nfactor = 2\nmethod = "grid"\n'
    src = _source(tmp_path, WITH_T, refine_toml=toml)
    text = _refused(tmp_path, src)
    assert text.startswith(f"{src} family T: method is grid and no grid was recovered: ")
    src.with_name("wing.refine.toml").write_bytes(b"[families.T]\nfactor = 2\n")
    why = text.split("no grid was recovered: ", 1)[1].split(". No level was written.", 1)[0]
    entry = refine_mesh(src).report["T"]
    assert (entry["method"], entry["reason"]) == ("remesh", f"no grid recovered: {why}")
    src.with_name("wing.refine.toml").write_bytes(
        b'[[perimeter]]\nfile = "wing.te_nodes.txt"\nexport_te_per_family = true\n'
        b'[families.G]\nfactor = 1\nmethod = "grid"\n'
    )
    assert refine_mesh(src).report["G"]["method"] == "grid"
    src.with_name("wing.refine.toml").write_bytes(
        b'[refine]\ntag = "G-remeshed"\n\n[families.G]\nfactor = 1\nmethod = "remesh"\n'
    )
    entry = refine_mesh(src).report["G"]
    assert (entry["method"], entry["reason"]) == ("remesh", "the refinement file states remesh")


# ---------------------------------------------------------------- FR-934 the band


def test_r10_the_band_of_an_unchanged_neighbour_is_written_where_the_shared_curve_changes(tmp_path):
    """P0380-REFINE (FR-934): only G is selected, beside the unchanged strip T.

    G's tip station, the curve they share, gains nodes at factor 2, so T is
    remeshed in its band. Control: at chordwise 1 and spanwise 2 the shared
    station keeps its nodes, so no band is needed and T is copied.

    PUSH-W12-QA-2: the growth check of the strip T fails on this fixture, a
    warning the test asserts, so it fails if the warning disappears.
    """
    src = _source(tmp_path, WITH_T)
    kept = refine_mesh(src, 1.0, families=["G"], parallel=2.0)
    assert kept.report["T"] == {"method": "copied"}
    with pytest.warns(PyflightstreamWarning, match=GROWTH_ON_T):
        level = refine_mesh(src, 2.0, families=["G"])
    assert level.report["T"]["method"] == "unchanged" and level.report["T"]["band"] > 0


# ------------------------------------------------------- FR-926, FR-927 the bytes written


def _digests(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_r12_two_runs_under_different_hash_seeds_write_identical_bytes(tmp_path):
    """P0380-REFINE (FR-926): two processes with other hash seeds write the same files.

    A grid refined, a neighbour remeshed onto its new nodes and a family
    copied, each run in its own interpreter (PYTHONHASHSEED 1 and 2).
    Control: the same refinement at factor 0.5 differs from them by digest.

    PUSH-W12-QA-2: coarsening the strip T at 0.5 fails its growth check, a
    warning the control asserts.
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
    assert runs[0] == runs[1] and len(runs[0]) == 10
    with pytest.warns(PyflightstreamWarning, match=GROWTH_ON_T):
        other = refine_mesh(src, 0.5, families=["G", "T"], out_dir=tmp_path / "control")
    coarse = _digests(other.folder)
    assert coarse["wing_R-G0p5-T0p5.obj"] != runs[0]["wing_R-G2-T2.obj"]


def test_r13_generated_files_use_lf_and_declarations_keep_source_bytes(tmp_path):
    """P0380-REFINE (FR-927), PFS-2172: generated files use LF; declarations retain CRLF.

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
    assert len(level.files) == 10
    side = level.obj.with_suffix(".obj.boundaries.toml")
    assert side.read_bytes() == src.with_suffix(".boundaries.toml").read_bytes()
    assert [p.name for p in level.folder.iterdir() if p != side and b"\r" in p.read_bytes()] == []


# ------------------------------------------------------------------- FR-928 layering


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
    """P0380-REFINE (FR-928): an AST walk of every import, deferred ones included.

    ``workspace/_refine`` imports nothing of ``pyflightstream.run``; ``_audit``
    imports no module of the refinement package but the shared helpers
    ``_geometry`` and ``_obj`` (the list is read from the package's files);
    the command reaches the refinement only through public names of
    ``pyflightstream.workspace``. Controls: each rule run on a planted source
    holding the forbidden import (deferred, inside a function) reports it,
    every refinement module among them.

    Release review of 0.38.0: proves the fix of RV-14.
    """
    refine = PACKAGE / "workspace" / "_refine"
    files = sorted(refine.glob("*.py"))
    assert {p.name for p in files} >= {"_audit.py", "_config.py", "_grid.py", "_level.py"}
    for path in files:
        assert _reaching(_file_imports(path), ("pyflightstream.run",)) == [], path.name
    assert _reaching(_file_imports(refine / "_audit.py"), PRIVATE) == []
    found = _file_imports(PACKAGE / "run" / "_cli_mesh.py")
    assert _reaching(found, (REFINE,)) == []
    # The names bound from the package itself. The module also holds the inventory
    # command (moved from run/cli.py by the 0.40.0 architecture ratchet), whose
    # imports of workspace.inputs and workspace._geometry_clean reach no refinement
    # module, which the _reaching check above already proves.
    submodules = {p.stem for p in (PACKAGE / "workspace").iterdir()}
    public = [
        name
        for m in found
        if m.startswith("pyflightstream.workspace.") and m.count(".") == 2
        if (name := m.rpartition(".")[2]) not in submodules
    ]
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
    names = {"_blocks", "_config", "_grid", "_level", "_lines", "_remesh"}
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
    "OPENING_FRACTION",
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
    """P0380-REFINE (FR-424, thresholds rule): a shared threshold is defined once, in _geometry.

    No module of the refinement package but ``_geometry`` spells the value of
    a shared fraction as a literal; the remesher's own tuning constants are
    named in ``_remesh`` and not shared, so it is not scanned. The rule of a
    node on a shared curve (``ON_CURVE_FRACTION``) is read by the grid's
    interfaces. Control: a planted source that
    spells the trailing-edge distance as a literal is reported.

    Release review of 0.38.0: proves the fix of RV-13.
    """
    from pyflightstream.workspace._refine import _geometry

    values = {float(getattr(_geometry, name)) for name in SHARED_THRESHOLDS} - {0.25}
    folder = PACKAGE / "workspace" / "_refine"
    for path in sorted(folder.glob("*.py")):
        if path.stem in ("_geometry", "_remesh", "__init__"):
            continue
        assert _threshold_literals(path.read_text(encoding="utf-8"), values) == [], path.name
    planted = "def hit(d, scale):\n    return d < 1e-6 * scale\n"
    assert _threshold_literals(planted, values) == [(2, 1e-6)]


def test_p0430_f731_a_symlinked_source_protects_the_folder_of_the_file_it_points_at(
    tmp_path, monkeypatch
):
    """F-731: the level folder may not be the folder of the real file behind a source symlink.

    A symlink is simulated by mapping the link's resolution to the real file (creating a symlink
    needs a privilege some machines lack); the guard must refuse on the real file's folder."""
    real = write_source(tmp_path / "real" / "wing_R2", "wing", sheet_with_strips(()))
    links = tmp_path / "links"
    links.mkdir()
    link = links / "wing.obj"
    link.write_bytes(real.read_bytes())
    link_resolved, real_resolved = link.resolve(), real.resolve()
    original = Path.resolve

    def fake(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        return real_resolved if result == link_resolved else result

    monkeypatch.setattr(Path, "resolve", fake)
    with pytest.raises(InputArtifactError, match="source's folder"):
        refine_mesh(link, 2.0, out_dir=tmp_path / "real", overwrite=True)
    assert sorted(p.name for p in real.parent.iterdir()) == sorted(
        ["wing.obj", "wing.te.txt", "wing.te_nodes.txt", "wing.boundaries.toml", "wing.refine.toml"]
    )
    # control: the same level folder beside an unrelated source is accepted
    monkeypatch.undo()
    other = _source(tmp_path / "other")
    done = refine_mesh(other, 2.0, out_dir=tmp_path / "out", overwrite=True)
    assert done.obj.parent.name == "wing_R2"


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


def test_f1516_an_unselected_family_table_is_not_validated(tmp_path):
    """F-1516 (FR-916): the tables of unselected families are not read, so a bad one is no refusal.

    B's table states a factor that is not a number; with ``families=["A"]`` the
    file's factors for B are never read and the level is written, B is
    warned as not read. Control: selecting B refuses the same table.
    """
    toml = '[families.A]\nfactor = 2\n[families.B]\nfactor = "wide"\n'
    src = _two_tubes(tmp_path, toml)
    with pytest.warns(PyflightstreamWarning, match=r"\[families\.B\]"):
        one = refine_mesh(src, families=["A"], out_dir=tmp_path / "one")
    assert _json(_record(one))["ignored_families_tables"] == ["B"]
    with pytest.warns(PyflightstreamWarning, match=r"\[families\.B\]"):
        called = refine_mesh(src, 2.0, families=["A"], out_dir=tmp_path / "called")
    assert called.report["B"] == {"method": "copied"}
    with pytest.raises(InputArtifactError, match=r"\[families\.B\]"):
        refine_mesh(src, families=["B"], out_dir=tmp_path / "two")


def _lock(folder: Path, locked: bool) -> None:
    """Make ``folder/held`` refuse removal (a read-only file; a sealed folder off Windows)."""
    held = folder / "held"
    if sys.platform == "win32":
        os.chmod(held / "held.txt", 0o444 if locked else 0o666)
    else:
        os.chmod(held, 0o500 if locked else 0o700)


def test_pfs_2119_061_a_staging_folder_left_behind_is_warned(tmp_path):
    """PFS-2119.061 (FR-919): a staging folder that cannot be removed is named in one warning."""
    import shutil
    import warnings

    src = _source(tmp_path)
    refine_mesh(src, 2.0)
    held = tmp_path / "wing_R2" / "held"
    held.mkdir()
    (held / "held.txt").write_text("old", encoding="utf-8")
    _lock(tmp_path / "wing_R2", True)
    try:
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            refine_mesh(src, 2.0, overwrite=True)
        said = [
            str(w.message) for w in seen if "staging folder could not be removed" in str(w.message)
        ]
        left = [p for p in tmp_path.iterdir() if p.name.startswith("wing_R2.partial-")]
        assert len(said) == 1 and len(left) == 1 and str(left[0]) in said[0]
    finally:
        for stale in tmp_path.glob("wing_R2.partial-*"):
            _lock(stale / "wing_R2.previous", False)
            shutil.rmtree(stale, ignore_errors=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        refine_mesh(src, 2.0, overwrite=True)
    assert not [p for p in tmp_path.iterdir() if ".partial-" in p.name]
    assert not [w for w in caught if "staging folder" in str(w.message)]


def test_f1514_f1515_an_oversized_integer_is_the_catalogued_refusal(tmp_path):
    from pyflightstream.workspace._refine import _config

    with pytest.raises(InputArtifactError, match="too large"):
        _config.positive("[refine] factor", 10**400)
    toml = f"[families.G]\nfactor = {10**400}\n"
    src = _source(tmp_path, refine_toml=toml)
    with pytest.raises(InputArtifactError, match="too large"):
        refine_mesh(src)


def test_the_periodic_table_is_warned_and_skipped(tmp_path):
    """[periodic] is no longer read: the level is the one written without it."""
    toml = "[periodic]\naxis = [1, 0, 0]\norigin = [0, 0, 0]\ncopies = 3\n"
    src = _source(tmp_path / "a", refine_toml=toml)
    with pytest.warns(PyflightstreamWarning, match=r"\[periodic\] is no longer read"):
        level = refine_mesh(src, 2.0, out_dir=tmp_path / "x")
    plain = refine_mesh(_source(tmp_path / "b"), 2.0, out_dir=tmp_path / "y")
    assert level.obj.read_bytes() == plain.obj.read_bytes()


def test_x_f_0599_a_file_in_the_place_of_the_level_is_refused_before_any_work(tmp_path):
    src = _source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "wing_R2").write_text("a file", encoding="utf-8")
    for overwrite in (True, False):
        with pytest.raises(InputArtifactError, match="held by a file"):
            refine_mesh(src, 2.0, out_dir=out, overwrite=overwrite)
    assert [p.name for p in out.iterdir()] == ["wing_R2"]
    assert (out / "wing_R2").read_text(encoding="utf-8") == "a file"


def test_x_f_1266_a_factor_below_one_over_m_states_its_reason_exactly(tmp_path):
    src = _source(tmp_path)
    text = _refused(tmp_path, src, 0.05, force_factors=False)
    assert "below 1/18: scaled by it, its 18 source intervals come to fewer than one" in text
    # refine-r1 TW-F1: the advice names the setting that raises it, the default.
    assert "leave force_factors at True, the default" in text and "force_factors=False" not in text
    # TW-F2: a factor that is not a number above zero is never raised, and is not told so.
    text = _refused(tmp_path, src, -1.0, force_factors=False)
    assert "above zero" in text and "strict-factors" not in text


# ------------------------------------------- the level's own inventory (0.44.0)

# P0440-INVENTORY (FR-348, FR-919): a level's boundaries file states its own faces and digest.
#
# A boundaries file written by the package for an OBJ without one carries the
# mesh's inventory, ``mesh_faces``, ``boundary_faces`` and ``mesh_sha256``,
# of that OBJ. The level's boundaries file is the source's with the values a
# level changes rewritten, and these three are the LEVEL's: counted in the
# level's OBJ as written, in the level's boundaries order after the
# ``[components]`` merge, and its sha256. The source is synthetic
# (tests/p0380_mesh_fixtures.py): the sheet grid G, the triangle strips T and U.

INVENTORY_STRIPS = (("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)), ("U", "tri", (0.1, 0.1)))
INVENTORY_KEYS = ("mesh_faces", "boundary_faces", "mesh_sha256")


def _level_boundaries(folder) -> dict:
    return tomllib.loads(
        (folder / f"{folder.name}.obj.boundaries.toml").read_text(encoding="utf-8")
    )


def test_the_levels_boundaries_file_states_the_levels_faces_and_sha256(tmp_path):
    """P0440-INVENTORY (FR-348): refined at 2, the level states its own three values.

    The level's ``mesh_faces`` is the face count of its OBJ, ``boundary_faces``
    the count of each of its boundaries (Wing, the merged G and T, then U)
    and ``mesh_sha256`` the sha256 of its OBJ's bytes, each different from
    the source's. Control: a source boundaries file without the inventory
    gives a level boundaries file without it.
    """
    toml = '[components]\nWing = ["G", "T"]\n'
    mesh = sheet_with_strips(INVENTORY_STRIPS)
    src = write_source(tmp_path / "src", "wing", mesh, boundaries=False, refine_toml=toml)
    source = tomllib.loads(ensure_inventory(src).read_text(encoding="utf-8"))
    assert all(key in source for key in INVENTORY_KEYS), source
    level = refine_mesh(src, 2.0, families=["G", "T"])
    got = _level_boundaries(level.folder)
    counts = obj_face_counts(level.obj)
    assert got["boundaries"] == ["Wing", "U"]
    assert got["boundary_faces"] == list(counts) and len(counts) == 2
    assert got["mesh_faces"] == sum(counts) != source["mesh_faces"]
    assert got["mesh_sha256"] == hashlib.sha256(level.obj.read_bytes()).hexdigest()
    assert got["mesh_sha256"] != source["mesh_sha256"]
    assert got["boundary_faces"] != source["boundary_faces"]
    # The header comment names the OBJ's sha256 too: the level's, and the source's nowhere.
    header = "# the OBJ's sha256 was "
    assert f"{header}{source['mesh_sha256']}" in src.with_name("wing.boundaries.toml").read_text(
        encoding="utf-8"
    )
    text = (level.folder / f"{level.folder.name}.obj.boundaries.toml").read_text(encoding="utf-8")
    assert f"{header}{got['mesh_sha256']}" in text and source["mesh_sha256"] not in text
    plain = write_source(tmp_path / "plain" / "src", "wing", mesh, refine_toml=toml)
    level = refine_mesh(plain, 2.0, families=["G", "T"])
    assert not any(key in _level_boundaries(level.folder) for key in INVENTORY_KEYS)


def test_p0440_rb5_46_rewritten_sidecar_escapes_del(tmp_path):
    from pyflightstream.workspace._refine._obj import rewrite_value

    wanted = {"boundaries": ["Wing\x7f"]}
    result = rewrite_value(
        tmp_path / "wing.boundaries.toml", 'boundaries = ["Wing"]\n', "boundaries", ["Wing"], wanted
    )
    assert tomllib.loads(result) == wanted


def source(tmp_path: Path, config: str = "", *, perimeter: bool = True) -> Path:
    """Write the sheet source; its refine file carries ``config`` and, by default, the perimeter."""
    mesh = write_source(tmp_path / "src", "wing", sheet_with_strips(()), boundaries=False)
    if perimeter:
        config += '\n[[perimeter]]\nfile = "wing.te_nodes.txt"\nexport_te_per_family = true\n'
    mesh.with_suffix(".refine.toml").write_text(config, encoding="utf-8")
    return mesh


def test_the_keep_first_row_keyword_is_warned_and_skipped(tmp_path):
    """keep_first_row is no longer read: the call warns and writes the level without it."""
    mesh = source(tmp_path, perimeter=False)
    with pytest.warns(PyflightstreamWarning, match="keep_first_row is no longer read"):
        level = refine_mesh(mesh, 2, keep_first_row=["G"], out_dir=tmp_path / "kept")
    plain = refine_mesh(mesh, 2, out_dir=tmp_path / "plain")
    assert level.report == plain.report


@pytest.mark.parametrize("option", ["normal", "parallel"])
def test_parallel_and_normal_factors_need_no_trailing_edge(tmp_path, option):
    """A grid family with no [[perimeter]] still takes parallel and normal factors."""
    mesh = source(tmp_path, perimeter=False)
    level = refine_mesh(mesh, 2, **{option: 1})
    assert level.report["G"]["method"] == "grid"


def test_p0460_neighbour_points_are_not_refine_input(tmp_path):
    mesh = source(tmp_path, perimeter=False)
    mesh.with_suffix(".te.txt").write_text("deliberately unreadable", encoding="utf-8")
    try:
        level = refine_mesh(mesh, 1)
    except InputArtifactError as error:
        pytest.fail(f"refine read an undeclared points file: {error}")
    assert not level.obj.with_suffix(".te.txt").exists()


def test_p0460_explicit_refine_points_and_preserved_declarations(tmp_path):
    mesh = source(tmp_path)
    declarations = (
        'fs_build = "26.125"\n[import]\nunits = "METER"\n'
        "# Keep this declaration exactly.\n[trailing_edges.wing]\n"
        'file = "marking.te.txt" # authored choice\ntype = "RELAXED"\n'
    )
    mesh.with_suffix(".obj.boundaries.toml").write_text(declarations, encoding="utf-8")
    mesh.with_suffix(".boundaries.toml").write_text("invalid TOML", encoding="utf-8")
    try:
        with pytest.warns(UserWarning, match=r"marking.te.txt.*wing_R2.te.txt"):
            level = refine_mesh(mesh, 2)
    except InputArtifactError as error:
        pytest.fail(f"explicit refine input was refused: {error}")
    assert level.obj.with_suffix(".te.txt").is_file()
    assert level.obj.with_suffix(".obj.boundaries.toml").read_text() == declarations
    assert not level.obj.with_suffix(".boundaries.toml").exists()


def test_p0460_per_family_te_is_written(tmp_path):
    mesh = source(tmp_path)
    try:
        level = refine_mesh(mesh, 2)
    except InputArtifactError as error:
        pytest.fail(f"per-family refine input was refused: {error}")
    family = level.folder / f"{level.obj.stem}.G.te.txt"
    assert family.read_bytes() == level.obj.with_suffix(".te.txt").read_bytes()
    from pyflightstream.workspace import plan_mark_boundaries

    level.obj.with_suffix(".obj.boundaries.toml").write_text(
        'fs_build = "26.125"\nboundaries = ["G"]\n'
        f'mesh_sha256 = "{hashlib.sha256(level.obj.read_bytes()).hexdigest()}"\n'
        f"boundary_faces = [{sum(obj_face_counts(level.obj))}]\n"
        f'mesh_faces = {sum(obj_face_counts(level.obj))}\n[import]\nunits = "METER"\n'
        f'[trailing_edges.selected]\nfile = "{family.name}"\ntype = "STANDARD"\n',
        encoding="utf-8",
    )
    assert plan_mark_boundaries(level.obj).mesh == level.obj


def test_p0460_named_detection_component_rename_preserves_declaration(tmp_path):
    mesh = source(
        tmp_path,
        '[components]\nWing = ["G"]\n',
    )
    text = (
        'boundaries = ["G"]\nfs_build = "26.125"\n'
        '[trailing_edges.chosen]\ntype = "STANDARD" # keep\n'
        'detect = { surfaces = ["G"], sweep_angle = 30.0 }\n'
    )
    mesh.with_suffix(".obj.boundaries.toml").write_text(text, encoding="utf-8")
    level = refine_mesh(mesh, 1)
    assert level.obj.with_suffix(".obj.boundaries.toml").read_text() == text.replace(
        '["G"]', '["Wing"]'
    )


@pytest.mark.parametrize("value", ["file = 3", 'file = ""', 'per_family = "yes"', "typo = true"])
def test_p0460_refine_trailing_edge_table_is_warned_and_skipped(tmp_path, value):
    """[trailing_edge] is no longer read: any content is warned of and skipped, nothing else."""
    mesh = source(tmp_path, "[trailing_edge]\n" + value + "\n")
    with pytest.warns(PyflightstreamWarning, match=r"\[trailing_edge\] is no longer read"):
        level = refine_mesh(mesh, 1)
    assert level.report["G"]["method"] == "grid"


def test_p0460_base_family_key_is_renamed_without_reformatting(tmp_path):
    mesh = source(tmp_path, '[components]\nWing = ["G"]\n')
    text = 'boundaries = ["G"]\n[base_regions.G] # keep\ncp = -0.2\n'
    mesh.with_suffix(".obj.boundaries.toml").write_text(text, encoding="utf-8")
    level = refine_mesh(mesh, 1)
    assert (
        level.obj.with_suffix(".obj.boundaries.toml")
        .read_text()
        .startswith('boundaries = ["Wing"]\n[base_regions."Wing"] # keep\ncp = -0.2\n')
    )


def test_p0460_audit_protects_qualified_boundaries(tmp_path):
    from pyflightstream.workspace import audit_mesh

    mesh = source(tmp_path)
    side = mesh.with_suffix(".obj.boundaries.toml")
    side.write_text('boundaries = ["G"]\n', encoding="utf-8")
    before = side.read_bytes()
    audit = audit_mesh(mesh)
    with pytest.raises(InputArtifactError, match="boundaries file"):
        audit.write_csv(side)
    assert side.read_bytes() == before


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_p0460_declarations_keep_source_newline_bytes(tmp_path, ending):
    mesh = source(tmp_path)
    side = mesh.with_suffix(".obj.boundaries.toml")
    text = ending.join([b"# authored comment", b"[trailing_edges]", b"none = true", b""])
    side.write_bytes(text)
    level = refine_mesh(mesh, 1)
    assert level.obj.with_suffix(".obj.boundaries.toml").read_bytes() == text


@pytest.mark.parametrize("grouped", [False, True])
def test_p0460_per_family_exports_partition_two_trailing_edges(tmp_path, grouped):
    from pyflightstream.workspace._refine._obj import read_te

    one = sheet_with_strips(())
    offset = numpy.array([0, 5, 0])
    mesh = Composite(
        numpy.vstack([one.verts, one.verts + offset]),
        {
            "A": one.families["G"],
            "B": [[v + len(one.verts) for v in face] for face in one.families["G"]],
        },
        numpy.vstack([one.te, one.te + offset]),
        {},
    )
    config = ""
    if grouped:
        config += '[components]\nWing = ["A", "B"]\n'
    src = write_source(tmp_path / "src", "wing", mesh, refine_toml=config)
    level = refine_mesh(src, 2)
    names = ["Wing"] if grouped else ["A", "B"]
    points = []
    for name in names:
        path = level.folder / f"{level.obj.stem}.{name}.te.txt"
        assert path in level.files
        unit, family_points = read_te(path)
        assert unit == "METER" and len(family_points)
        if not grouped:
            assert (
                numpy.all(family_points[:, 1] < 3)
                if name == "A"
                else numpy.all(family_points[:, 1] > 4)
            )
        points.extend(map(tuple, family_points))
    _, combined = read_te(level.obj.with_suffix(".te.txt"))
    assert sorted(points) == sorted(map(tuple, combined))


def test_p0460_inventory_digest_does_not_rewrite_declaration_filename(tmp_path):
    mesh = source(tmp_path)
    digest = hashlib.sha256(mesh.read_bytes()).hexdigest()
    declaration = f'[trailing_edges.wing]\nfile = "{digest}.te.txt"\ntype = "STANDARD"\n'
    text = f'# the OBJ\'s sha256 was {digest}\nmesh_sha256 = "{digest}"\n' + declaration
    mesh.with_suffix(".obj.boundaries.toml").write_bytes(text.encode())
    level = refine_mesh(mesh, 2)
    copied = level.obj.with_suffix(".obj.boundaries.toml").read_text()
    assert copied.endswith(declaration)
    new_digest = hashlib.sha256(level.obj.read_bytes()).hexdigest()
    assert tomllib.loads(copied)["mesh_sha256"] == new_digest != digest
    assert f"# the OBJ's sha256 was {new_digest}" in copied


# ------------------------------------------------------ [[perimeter]] node lists


def _sheet_lines():
    """Return the sheet's trailing-edge nodes (u = 0) and its root station's, by vertex."""
    from tests.p0380_mesh_fixtures import sheet_quads

    fx = sheet_quads()
    place = {p: v for v, p in fx.place.items()}
    te = [place[(k, 0)] for k in range(fx.stations)]
    root = [place[(0, i)] for i in range(fx.nodes)]
    return fx, te, root


def _same_level(a: Path, b: Path) -> bool:
    """Return whether two level OBJs hold the same nodes and the same families."""
    (va, fa), (vb, fb) = read_mesh(a), read_mesh(b)
    return numpy.array_equal(va, vb) and fa == fb


def _node_list(path: Path, verts, ids, *, first: int = 1001, extra=()) -> Path:
    """Write the ASCII list ANSA saves from a SET's node window, in a scrambled order."""
    rows = ["#  Id, Name, X , Y, Z"]
    order = list(ids)[1::2] + list(ids)[::2]
    rows += [f"{first + v}, , {x:.6f}, {y:.6f}, {z:.6f}" for v in order for x, y, z in [verts[v]]]
    rows += [f"{node}, , {x}, {y}, {z}" for node, (x, y, z) in extra]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_perimeter_node_lists_orient_the_grid_and_export_only_the_marked_trailing_edge(tmp_path):
    """[[perimeter]] lists: node ids from ANSA, rounded and out of order, replace the points file.

    Control: the level is the one the exact trailing-edge points file gives with
    the same factors. Only the list marked export_te_per_family is written per
    family; the root station's list orients nothing here and is never written.
    """
    fx, te, root = _sheet_lines()
    factors = "[families.G]\nparallel_factor = 2\nnormal_factor = 1.5\n"
    old = refine_mesh(_source(tmp_path / "old", refine_toml=factors), out_dir=tmp_path / "o")
    src = _source(tmp_path / "new", te=False, refine_toml=None)
    _node_list(src.with_name("te_nodes.txt"), fx.verts, te)
    _node_list(src.with_name("root_nodes.txt"), fx.verts, root, first=5001)
    src.with_name("wing.refine.toml").write_text(
        factors
        + '[[perimeter]]\nfile = "root_nodes.txt"\n'
        + '[[perimeter]]\nfile = "te_nodes.txt"\nexport_te_per_family = true\n',
        encoding="utf-8",
    )
    new = refine_mesh(src, out_dir=tmp_path / "n")
    assert new.report["G"]["method"] == "grid"
    assert _same_level(new.obj, old.obj)
    from pyflightstream.workspace._refine._obj import read_te

    _, written = read_te(new.folder / f"{new.obj.stem}.G.te.txt")
    _, exact = read_te(old.obj.with_suffix(".te.txt"))
    assert len(written) == 2 * (len(te) - 1)
    assert numpy.allclose(numpy.sort(written, axis=0), numpy.sort(exact, axis=0), atol=1e-9)


def test_a_trailing_edge_and_a_root_in_one_list_are_told_apart_at_their_corner(tmp_path):
    """One [[perimeter]] list holding the trailing edge and the root, joined at a corner.

    The whole list is not a grid line, so the list is cut at its corner and the
    piece that recovers the grid orients it. Control: the level is the one the
    trailing edge alone gives.
    """
    fx, te, root = _sheet_lines()
    factors = "[families.G]\nparallel_factor = 2\nnormal_factor = 1.5\n"
    alone = refine_mesh(_source(tmp_path / "a", refine_toml=factors), out_dir=tmp_path / "x")
    src = _source(tmp_path / "b", te=False)
    _node_list(src.with_name("lines.txt"), fx.verts, [*te, *root[1:]])
    src.with_name("wing.refine.toml").write_text(
        factors + '[[perimeter]]\nfile = "lines.txt"\n', encoding="utf-8"
    )
    level = refine_mesh(src, out_dir=tmp_path / "y")
    assert level.report["G"]["method"] == "grid"
    assert _same_level(level.obj, alone.obj)


def test_a_node_left_out_of_a_list_is_completed_from_the_grid_line(tmp_path):
    """A list missing one middle node of the trailing edge is completed, with a warning.

    The two edges at the missing node have an end no list holds, so the grid
    line completes them. Control: the level is the one the whole list gives.
    """
    fx, te, _ = _sheet_lines()
    factors = "[families.G]\nparallel_factor = 2\n"
    whole = refine_mesh(_source(tmp_path / "a", refine_toml=factors), out_dir=tmp_path / "x")
    src = _source(tmp_path / "b", te=False)
    _node_list(src.with_name("te.txt"), fx.verts, [v for v in te if v != te[4]])
    src.with_name("wing.refine.toml").write_text(
        factors + '[[perimeter]]\nfile = "te.txt"\nexport_te_per_family = true\n',
        encoding="utf-8",
    )
    with pytest.warns(PyflightstreamWarning, match="the perimeter list is incomplete"):
        level = refine_mesh(src, out_dir=tmp_path / "y")
    assert _same_level(level.obj, whole.obj)


def test_a_perimeter_node_off_the_mesh_is_warned_and_skipped(tmp_path):
    """A listed node that matches no vertex is named by its id and skipped; the rest orient."""
    fx, te, _ = _sheet_lines()
    src = _source(tmp_path, te=False)
    _node_list(src.with_name("te.txt"), fx.verts, te, extra=[(9999, (50.0, 50.0, 50.0))])
    src.with_name("wing.refine.toml").write_text(
        '[families.G]\nparallel_factor = 2\n[[perimeter]]\nfile = "te.txt"\n', encoding="utf-8"
    )
    with pytest.warns(PyflightstreamWarning, match=r"1 of 10 node\(s\) match no mesh vertex.*9999"):
        level = refine_mesh(src)
    assert level.report["G"]["method"] == "grid"
    assert not (level.folder / f"{level.obj.stem}.G.te.txt").exists()


def test_chordwise_and_spanwise_are_read_as_normal_and_parallel_with_a_warning(tmp_path):
    """The earlier key names still refine, warned; the level is the one the new names give."""
    new = refine_mesh(
        _source(
            tmp_path / "a", refine_toml="[families.G]\nparallel_factor = 2\nnormal_factor = 3\n"
        ),
        out_dir=tmp_path / "x",
    )
    with pytest.warns(PyflightstreamWarning, match="chordwise is read as normal_factor"):
        old = refine_mesh(
            _source(tmp_path / "b", refine_toml="[families.G]\nspanwise = 2\nchordwise = 3\n"),
            out_dir=tmp_path / "y",
        )
    assert _same_level(old.obj, new.obj)
    with pytest.warns(PyflightstreamWarning, match="spanwise is read as parallel"):
        call = refine_mesh(_source(tmp_path / "c"), spanwise=2, chordwise=3, out_dir=tmp_path / "z")
    assert _same_level(call.obj, new.obj)


def test_convert2midnodes_orders_a_scrambled_list_of_two_lines(tmp_path, capsys):
    """pyfs-workspace geometry convert2midnodes: one mid-point per neighbouring pair, per line.

    Two trailing edges in one list, out of order: the sheet's and a copy of it
    ten units above, as a second component's would be.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace._refine._obj import read_te

    fx, te, _ = _sheet_lines()
    verts = numpy.vstack([fx.verts, fx.verts[te] + (0.0, 0.0, 10.0)])
    second = list(range(len(fx.verts), len(verts)))
    listed = _node_list(tmp_path / "nodes.txt", verts, [*te, *second])
    out = tmp_path / "nodes.te.txt"
    code = workspace_cli.main(
        ["geometry", "convert2midnodes", str(listed), str(out), "--unit", "MILLIMETER"]
    )
    assert code == 0 and capsys.readouterr().out.strip() == str(out)
    unit, points = read_te(out)
    expected = numpy.vstack([0.5 * (verts[ids[:-1]] + verts[ids[1:]]) for ids in (te, second)])
    assert unit == "MILLIMETER" and len(points) == len(expected)
    near = numpy.linalg.norm(points[:, None] - expected[None], axis=2).min(axis=1)
    assert near.max() < 1e-5


def test_drev48_convert2midnodes_reads_coincident_nodes_once(tmp_path):
    """DREV48-001: a list naming every trailing-edge position twice (an open trailing
    edge's upper and lower nodes, two ids at one position) gives the edge mid-points.

    Each node's spacing was its twin's distance, zero, so every line was a twin
    pair and its mid-point the node itself. Control: the list with each
    position once gives the same points; the repeat is warned.
    """
    from pyflightstream.workspace._refine._obj import read_te
    from pyflightstream.workspace.wake_edges import write_trailing_edge_midnodes

    fx, te, _ = _sheet_lines()
    twins = [(5000 + v, tuple(f"{c:.6f}" for c in fx.verts[v])) for v in te]
    listed = _node_list(tmp_path / "twins.txt", fx.verts, te, extra=twins)
    with pytest.warns(PyflightstreamWarning, match=r"9 node\(s\) repeat the position"):
        _, points = read_te(write_trailing_edge_midnodes(listed, tmp_path / "twins.te.txt"))
    once = _node_list(tmp_path / "once.txt", fx.verts, te)
    _, alone = read_te(write_trailing_edge_midnodes(once, tmp_path / "once.te.txt"))
    exact = 0.5 * (fx.verts[te[:-1]] + fx.verts[te[1:]])
    assert len(points) == len(alone) == len(exact)
    near = numpy.linalg.norm(points[:, None] - exact[None], axis=2).min(axis=1)
    assert near.max() < 1e-5


def test_convert2midnodes_per_family_writes_the_mesh_edges_of_each_family(tmp_path, capsys):
    """convert2midnodes --per-family MESH: one file per family, the mesh's own edge mid-points.

    The list holds the trailing edges of the sheet G and of the quadrilateral
    strip Q beside it, rounded and out of order; the strip T is untouched and
    gets no file.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace._refine._obj import read_te

    mesh = sheet_with_strips((("Q", "quad", (0.2, 0.2)), ("T", "tri", (0.1,))))
    src = write_source(tmp_path / "src", "wing", mesh)
    rows = mesh.rows
    lines = {"G": [r[0] for r in rows["G"]], "Q": [r[0] for r in rows["Q"]]}
    listed = _node_list(tmp_path / "nodes.txt", mesh.verts, sorted({*lines["G"], *lines["Q"]}))
    out = tmp_path / "nodes.te.txt"
    code = workspace_cli.main(
        ["geometry", "convert2midnodes", str(listed), str(out), "--per-family", str(src)]
    )
    printed = capsys.readouterr().out.split()
    assert code == 0 and printed == [str(tmp_path / f"nodes.{n}.te.txt") for n in ("G", "Q")]
    for name, ids in lines.items():
        unit, points = read_te(tmp_path / f"nodes.{name}.te.txt")
        expected = 0.5 * (mesh.verts[ids[:-1]] + mesh.verts[ids[1:]])
        assert unit == "METER" and len(points) == len(expected)
        near = numpy.linalg.norm(points[:, None] - expected[None], axis=2).min(axis=1)
        assert near.max() < 1e-8  # the OBJ holds nine decimals
    assert not out.exists()


# ------------------------------------------- one node list, te_families, identify-te


def _whole_boundary(fx) -> list[int]:
    """Return every boundary node of the sheet: trailing edge, leading edge, root and tip."""
    from pyflightstream.workspace._refine._lines import boundary_sides

    return sorted({v for side in boundary_sides(fx.verts, fx.faces) for v in side})


def _te_families_level(tmp_path: Path, extra: str = ""):
    fx, te, _ = _sheet_lines()
    factors = "[families.G]\nparallel_factor = 2\nnormal_factor = 1.5\n"
    src = _source(tmp_path / "b", te=False)
    _node_list(src.with_name("nodes.txt"), fx.verts, _whole_boundary(fx))
    src.with_name("wing.refine.toml").write_text(
        factors + extra + '[[perimeter]]\nfile = "nodes.txt"\n' + 'te_families = ["Wing"]\n',
        encoding="utf-8",
    )
    return fx, te, factors, src


def test_one_node_list_and_te_families_write_the_rearmost_line_by_output_family(tmp_path):
    """One list holds the whole perimeter; te_families picks each family's rearmost line.

    The sheet's trailing edge (the line its surface lies forward of, +x aft)
    orients the grid and is written for the output family Wing, the component G
    is grouped into. Control: the level and its points are those the trailing
    edge listed alone gives.
    """
    fx, te, factors, src = _te_families_level(tmp_path, '[components]\nWing = ["G"]\n')
    level = refine_mesh(src, out_dir=tmp_path / "y")
    alone = refine_mesh(
        _source(tmp_path / "a", refine_toml=factors + '[components]\nWing = ["G"]\n'),
        out_dir=tmp_path / "x",
    )
    assert level.report["G"]["method"] == "grid"
    assert _same_level(level.obj, alone.obj)
    from pyflightstream.workspace._refine._obj import read_te

    _, written = read_te(level.folder / f"{level.obj.stem}.Wing.te.txt")
    _, exact = read_te(alone.obj.with_suffix(".te.txt"))
    assert len(written) == len(exact) == 2 * (len(te) - 1)
    assert numpy.allclose(numpy.sort(written, axis=0), numpy.sort(exact, axis=0), atol=1e-9)


def test_a_te_families_name_of_nothing_is_warned_and_skipped(tmp_path):
    """A te_families name that is neither a family nor a component is warned; nothing is written."""
    _, _, _, src = _te_families_level(tmp_path)
    with pytest.warns(PyflightstreamWarning, match="te_families names 'Wing'"):
        level = refine_mesh(src, out_dir=tmp_path / "y")
    assert not list(level.folder.glob("*.Wing.te.txt"))


def test_identify_te_writes_the_solver_node_file_of_a_refined_merged_family(tmp_path, capsys):
    """pyfs-workspace geometry identify-te: the refined level's Wing trailing edge, solver format.

    The source's node list is read along a level whose nodes are not the listed
    ones (parallel factor 2); the file is the count, one unread coordinate line
    and one mid-point per trailing-edge edge, the points the refine wrote.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace._refine._obj import read_te

    _, _, _, src = _te_families_level(tmp_path, '[components]\nWing = ["G"]\n')
    level = refine_mesh(src, out_dir=tmp_path / "y")
    with pytest.warns(PyflightstreamWarning, match="holds no family 'Nope'"):
        code = workspace_cli.main(
            [
                "geometry",
                "identify-te",
                str(level.obj),
                str(src.with_name("nodes.txt")),
                "--families",
                "Wing,Nope",
                "--overwrite",  # the level's own <level>.Wing.te.txt is rewritten alike
            ]
        )
    out = level.obj.with_name(f"{level.obj.stem}.Wing.fs.te.txt")
    package = level.obj.with_name(f"{level.obj.stem}.Wing.te.txt")
    assert code == 0 and capsys.readouterr().out.split() == [str(out), str(package)]
    rows = out.read_text(encoding="utf-8").split()
    count = int(rows[0])
    points = numpy.array([[float(c) for c in r.split(",")] for r in rows[2:]])
    _, refined = read_te(level.folder / f"{level.obj.stem}.Wing.te.txt")
    assert count == len(points) == len(refined)
    assert numpy.allclose(numpy.sort(points, axis=0), numpy.sort(refined, axis=0), atol=1e-9)


# ------------------------------------------------------------------ prepare-to-refine


def _one_family_wing(tmp_path: Path) -> Path:
    """Write Wing: a quad sheet and the quad strip beside it, triangles, then another quad strip."""
    mesh = sheet_with_strips(
        (("Q", "quad", (0.2, 0.2)), ("T", "tri", (0.1,)), ("R", "quad", (0.2, 0.2)))
    )
    faces = [f for name in ("G", "Q", "T", "R") for f in mesh.families[name]]
    wing = Composite(mesh.verts, {"Wing": faces}, numpy.zeros((0, 3)), {})
    return write_source(tmp_path / "src", "wing", wing, boundaries=False)


def test_prepare_to_refine_writes_patches_ordered_by_span_a_refine_file_and_a_node_list(
    tmp_path, capsys
):
    """pyfs-workspace geometry prepare-to-refine: patches, the refine file and the node list.

    Wing holds two quad pieces the triangles separate: the sheet with its strip
    (2.4 along y) and the far strip (0.4), each a grid patch numbered by its
    extent along y, and the triangles, a mixed patch. Each grid patch lists its
    rearmost line, the trailing edge (11 and 3 nodes), ordered along y; the
    refine file reads with no warning and refines.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace._refine import _config
    from pyflightstream.workspace._refine._obj import read_node_list, read_obj

    src = _one_family_wing(tmp_path)
    code = workspace_cli.main(["geometry", "prepare-to-refine", str(src)])
    assert code == 0, capsys.readouterr()
    out = capsys.readouterr().out.splitlines()
    names = ["Wing_001_grid", "Wing_002_grid", "Wing_003_mixed"]
    assert out[0] == "Wing: " + ", ".join(names)
    obj = src.with_name("wing_patches.obj")
    patches = read_obj(obj)
    assert list(patches.families) == names
    source = read_obj(src)
    assert sum(len(f) for f in patches.families.values()) == len(source.families["Wing"])
    spans = [numpy.ptp(patches.verts[patches.family_vertices(n), 1]) for n in names[:2]]
    assert spans[0] > 1.0 > spans[1]
    nodes = read_node_list(src.with_name("wing_patches.nodes.txt"))
    assert len(nodes.ids) == 11 + 3
    assert numpy.all(numpy.diff(nodes.points[:, 1]) > 0)
    assert numpy.allclose(nodes.points[:, 0], patches.verts[numpy.array(nodes.ids) - 1, 0])
    config = src.with_name("wing_patches.refine.toml")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        stated = _config.read_refine_file(config, names)
    assert {n: s.method for n, s in stated["specs"].items()} == {
        "Wing_001_grid": "grid",
        "Wing_002_grid": "grid",
        "Wing_003_mixed": "remesh",
    }
    assert stated["components"] == {"Wing": names}
    assert [p.te_families for p in stated["perimeters"]] == [("Wing",)]
    text = config.read_text(encoding="utf-8").replace(
        '[families.Wing_001_grid]\nmethod = "grid"\nfactor = 1.0',
        '[families.Wing_001_grid]\nmethod = "grid"\nparallel_factor = 2.0',
    )
    config.write_text(text, encoding="utf-8")
    level = refine_mesh(obj, out_dir=tmp_path / "out")
    assert level.report["Wing_001_grid"]["method"] == "grid"
    te = level.folder / f"{level.obj.stem}.Wing.te.txt"
    from pyflightstream.workspace._refine._obj import read_te

    assert len(read_te(te)[1]) == 2 * 10 + 1 + 2  # the grid at factor 2, T and R at 1


def test_prepare_to_refine_keeps_an_earlier_run_unless_asked(tmp_path):
    """A second run refuses to replace the prepared files; overwrite replaces them."""
    from pyflightstream.workspace import prepare_to_refine

    src = _one_family_wing(tmp_path)
    prepare_to_refine(src)
    with pytest.raises(InputArtifactError, match="exists; pass overwrite"):
        prepare_to_refine(src)
    assert prepare_to_refine(src, overwrite=True).obj.is_file()


@pytest.mark.parametrize("stated", ["wing_fine", "wing_fine.obj"])
def test_refine_filename_names_the_level_and_its_folder(tmp_path, stated):
    """[refine] filename (with or without .obj) names the level's folder and OBJ.

    Control: the same file with tag names them <stem>_<tag>; with both, the
    filename names the level and the tag is warned and skipped.
    """
    factors = "[families.G]\nfactor = 2\n"
    named = _source(tmp_path / "a", refine_toml=f'[refine]\nfilename = "{stated}"\n' + factors)
    level = refine_mesh(named, out_dir=tmp_path / "x")
    assert level.folder.name == "wing_fine" and level.obj.name == "wing_fine.obj"
    tagged = _source(tmp_path / "b", refine_toml='[refine]\ntag = "fine"\n' + factors)
    assert refine_mesh(tagged, out_dir=tmp_path / "y").obj.name == "wing_fine.obj"
    both = _source(
        tmp_path / "c",
        refine_toml='[refine]\ntag = "t"\nfilename = "other.obj"\n' + factors,
    )
    with pytest.warns(PyflightstreamWarning, match="the tag is skipped"):
        assert refine_mesh(both, out_dir=tmp_path / "z").obj.name == "other.obj"


def test_refine_filename_that_is_not_a_file_name_is_warned_and_the_tag_names_the_level(tmp_path):
    """A filename with a path separator is warned and skipped; the level keeps its tag."""
    src = _source(tmp_path, refine_toml='[refine]\nfilename = "a/b"\n[families.G]\nfactor = 2\n')
    with pytest.warns(PyflightstreamWarning, match="filename .* not one file name"):
        level = refine_mesh(src, out_dir=tmp_path / "x")
    assert level.obj.name == "wing_R2.obj"


@pytest.mark.parametrize("closed", [False, True])
def test_identify_te_from_the_obj_alone_writes_the_trailing_edge_and_its_node_list(
    tmp_path, capsys, closed
):
    """identify-te OBJ, no node list: the trailing edge found from the mesh, solver and ANSA files.

    On an open sheet the trailing edge is a boundary; on a closed wing it is
    the sharp edge between the upper and the lower surface. The leading edge,
    the root and the tip are not written. Control: --families writes the same
    points in the family's own file.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace._refine._obj import read_node_list
    from tests.p0380_mesh_fixtures import sheet_quads, tube_pole_quads

    fx = tube_pole_quads() if closed else sheet_quads()
    src = write_source(
        tmp_path / "src",
        "wing",
        Composite(fx.verts, {"Wing": fx.faces}, numpy.zeros((0, 3)), {}),
        boundaries=False,
    )
    assert workspace_cli.main(["geometry", "identify-te", str(src)]) == 0
    solver, listing = src.with_name("wing.nodes.te.txt"), src.with_name("wing.nodes.txt")
    package = src.with_name("wing.te.txt")
    assert capsys.readouterr().out.split() == [str(solver), str(package), str(listing)]
    from pyflightstream.workspace._refine._obj import read_te

    unit, stated = read_te(package)
    assert unit == "METER"
    place = {p: n for n, p in fx.place.items()}
    te = [place[(k, 0)] for k in range(fx.stations)]
    exact = 0.5 * (fx.verts[te[:-1]] + fx.verts[te[1:]])

    def points(path):
        rows = path.read_text(encoding="utf-8").split()
        assert int(rows[0]) == len(rows) - 2
        return numpy.array([[float(c) for c in r.split(",")] for r in rows[2:]])

    got = points(solver)
    assert numpy.allclose(numpy.sort(stated, axis=0), numpy.sort(got, axis=0), atol=1e-9)
    assert len(got) == len(exact)
    assert numpy.allclose(numpy.sort(got, axis=0), numpy.sort(exact, axis=0), atol=1e-9)
    nodes = read_node_list(listing)
    assert sorted(i - 1 for i in nodes.ids) == sorted(te)
    assert numpy.all(numpy.diff(nodes.points[:, 1]) > 0)
    code = workspace_cli.main(
        ["geometry", "identify-te", str(src), "--families", "Wing", "--overwrite"]
    )
    assert code == 0
    capsys.readouterr()
    own = points(src.with_name("wing.Wing.fs.te.txt"))
    assert numpy.allclose(numpy.sort(own, axis=0), numpy.sort(exact, axis=0), atol=1e-9)


@pytest.mark.parametrize(
    ("turn", "most", "kept"), [(0.0, 45.0, True), (25.0, 45.0, True), (25.0, 20.0, False)]
)
def test_a_rearmost_line_is_a_trailing_edge_within_the_angle_of_the_yz_plane(turn, most, kept):
    """A rearmost edge is kept when it lies within the maximum angle of the yz plane.

    A flat plate with a hole has two rearmost lines along y, its aft edge and
    the hole's front edge. Turned about z by 25 degrees they are 25 degrees
    from the yz plane: kept within 45, left out within 20 (its sides, turned
    the other way, are not rearmost, their surface 65 degrees from forward).
    """
    from pyflightstream.workspace._refine._prepare import rearmost_lines
    from tests.p0380_mesh_fixtures import holed_plate

    plate = holed_plate()
    plate.verts[:, 2] = 0.0
    c, s = numpy.cos(numpy.radians(turn)), numpy.sin(numpy.radians(turn))
    turned = plate.verts @ numpy.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    found = rearmost_lines(turned, plate.families["P"], max_angle=most)
    assert bool(found) is kept
    if turn == 0.0:  # one perimeter only, the outer aft edge: the hole's front edge is not added
        tangents = numpy.array([turned[b] - turned[a] for a, b in found])
        assert numpy.allclose(tangents[:, 0], 0.0, atol=1e-12)
        ends = sorted({v for e in found for v in e})
        assert numpy.allclose(turned[ends, 0], turned[:, 0].max(), atol=1e-12)


def test_drev48_the_maximum_angle_is_taken_from_the_plane_across_the_aft_direction(tmp_path):
    """DREV48-002: with --aft along y, the trailing edge runs along x and is found.

    The sheet is turned so its nose to tail direction is +y. The angle was
    measured from the yz plane whatever the aft direction, so the trailing
    edge, 90 degrees from that plane, was left out and identify-te refused.
    Control: the sheet as built, aft +x, gives the same edges.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace._refine._prepare import rearmost_lines
    from tests.p0380_mesh_fixtures import sheet_quads

    fx = sheet_quads()
    turn = numpy.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])  # x to y
    turned = fx.verts @ turn
    control = rearmost_lines(fx.verts, fx.faces)
    assert len(control) == fx.stations - 1
    assert rearmost_lines(turned, fx.faces, aft=(0.0, 1.0, 0.0)) == control
    src = write_source(
        tmp_path / "src",
        "wing",
        Composite(turned, {"Wing": fx.faces}, numpy.zeros((0, 3)), {}),
        boundaries=False,
    )
    assert workspace_cli.main(["geometry", "identify-te", str(src), "--aft", "0", "1", "0"]) == 0
    rows = src.with_name("wing.nodes.te.txt").read_text(encoding="utf-8").split()
    assert int(rows[0]) == fx.stations - 1


def test_drev48_identify_te_units_of_its_three_files(tmp_path, capsys):
    """DREV48-005: identify-te writes the solver file in --simulation-unit, converted, the
    package points file under the --unit line, unconverted, and the node list as read.

    The default unit is the mesh's ``[import] units``. Control: the same mesh
    with no unit stated writes METER and no conversion.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace._refine._obj import read_node_list, read_te
    from tests.p0380_mesh_fixtures import sheet_quads

    fx = sheet_quads()
    src = write_source(
        tmp_path / "src",
        "wing",
        Composite(fx.verts, {"Wing": fx.faces}, numpy.zeros((0, 3)), {}),
        boundaries=False,
    )

    def solver_points():
        rows = src.with_name("wing.nodes.te.txt").read_text(encoding="utf-8").split()
        return numpy.array([[float(c) for c in r.split(",")] for r in rows[2:]])

    assert workspace_cli.main(["geometry", "identify-te", str(src)]) == 0
    plain_unit, plain = read_te(src.with_name("wing.te.txt"))
    assert plain_unit == "METER"
    assert numpy.allclose(numpy.sort(solver_points(), axis=0), numpy.sort(plain, axis=0))
    listed = read_node_list(src.with_name("wing.nodes.txt")).points
    command = ["geometry", "identify-te", str(src), "--simulation-unit", "METER", "--overwrite"]
    src.with_name("wing.obj.boundaries.toml").write_text(
        '[import]\nunits = "MILLIMETER"\n', encoding="utf-8"
    )
    assert workspace_cli.main(command) == 0, capsys.readouterr().err
    unit, stated = read_te(src.with_name("wing.te.txt"))
    assert unit == "MILLIMETER"
    assert numpy.allclose(numpy.sort(stated, axis=0), numpy.sort(plain, axis=0))
    assert numpy.allclose(
        numpy.sort(solver_points(), axis=0), numpy.sort(plain, axis=0) / 1000.0, atol=1e-12
    )
    assert numpy.allclose(read_node_list(src.with_name("wing.nodes.txt")).points, listed)


def test_drev48_an_aft_of_zeros_is_warned_and_plus_x_taken(tmp_path, capsys):
    """DREV48-003: --aft 0 0 0 states no direction; it is warned and +x taken.

    A refine file's [[perimeter]] aft of zeros is warned and +x taken; the
    commands divided by its length and found no trailing edge (identify-te
    refused, prepare-to-refine wrote an empty node list). Control: the same
    files the default aft writes.
    """
    from pyflightstream.workspace import cli as workspace_cli
    from pyflightstream.workspace import prepare_to_refine
    from tests.p0380_mesh_fixtures import sheet_quads

    fx = sheet_quads()
    src = write_source(
        tmp_path / "src",
        "wing",
        Composite(fx.verts, {"Wing": fx.faces}, numpy.zeros((0, 3)), {}),
        boundaries=False,
    )
    with pytest.warns(PyflightstreamWarning, match=r"aft .* not a direction.*\+x is taken"):
        code = workspace_cli.main(["geometry", "identify-te", str(src), "--aft", "0", "0", "0"])
    assert code == 0, capsys.readouterr().err
    zeros = src.with_name("wing.nodes.te.txt").read_bytes()
    assert workspace_cli.main(["geometry", "identify-te", str(src), "--overwrite"]) == 0
    assert src.with_name("wing.nodes.te.txt").read_bytes() == zeros
    with pytest.warns(PyflightstreamWarning, match=r"aft .* not a direction.*\+x is taken"):
        prepared = prepare_to_refine(_one_family_wing(tmp_path / "p"), aft=(0.0, 0.0, 0.0))
    assert len(prepared.nodes.read_text(encoding="utf-8").splitlines()) == 1 + 11 + 3


def test_a_sharp_trailing_edge_of_a_closed_wing_with_a_smooth_leading_edge_is_found():
    """A finely meshed closed wing is one piece (its leading edge is smooth); its sharp
    trailing edge, an inside edge of that piece, is its rearmost perimeter.

    Control: the coarse wing, cut at the leading edge too, gives the same column.
    """
    from pyflightstream.workspace._refine._prepare import rearmost_lines
    from tests.p0380_mesh_fixtures import Fixture, build_grid

    for nodes in (24, 96):
        fx = build_grid(Fixture("closed", True, 9, nodes, ("open", "pole"), None))
        found = rearmost_lines(fx.verts, fx.faces)
        assert len(found) == fx.stations - 1
        assert {fx.place[v][1] for e in found for v in e} == {0}


def test_the_rearmost_perimeter_of_a_piece_is_one_loop_the_one_reaching_furthest_aft():
    """rearmost_perimeter (te_families, identify-te, prepare-to-refine) keeps one loop per piece.

    Given every boundary edge of a plate with a hole, it returns the outer loop
    alone. Control: given the hole's loop alone, it returns that loop.
    """
    from pyflightstream.workspace._refine._geometry import edge_faces
    from pyflightstream.workspace._refine._obj import rearmost_perimeter
    from tests.p0380_mesh_fixtures import holed_plate

    plate = holed_plate()
    faces = plate.families["P"]
    boundary = {e for e, fs in edge_faces(faces).items() if len(fs) == 1}
    outer = rearmost_perimeter(plate.verts, faces, boundary)
    hole = boundary - outer
    assert outer and hole
    assert numpy.isclose(
        plate.verts[sorted({v for e in outer for v in e}), 0].max(), plate.verts[:, 0].max()
    )
    assert rearmost_perimeter(plate.verts, faces, hole) == hole


def test_the_level_boundaries_file_lists_each_components_trailing_edge_for_mark_boundaries(
    tmp_path,
):
    """After a refine that writes per-component trailing edges, the level's boundaries file
    declares them, one [trailing_edges.<component>] each typed STANDARD, and mark-boundaries plans
    the level from it.

    Control: the file names exactly the per-component files the level holds.
    """
    from pyflightstream.workspace import plan_mark_boundaries

    _, _, _, src = _te_families_level(tmp_path, '[components]\nWing = ["G"]\n')
    level = refine_mesh(src, out_dir=tmp_path / "y")
    side = level.obj.with_suffix(".obj.boundaries.toml")
    stated = tomllib.loads(side.read_text(encoding="utf-8"))["trailing_edges"]
    own = sorted(p.name for p in level.folder.glob(f"{level.obj.stem}.*.te.txt"))
    stem = level.obj.stem
    assert own == [f"{stem}.Wing.fs.te.txt", f"{stem}.Wing.te.txt", f"{stem}.nodes.te.txt"]
    assert stated == {"Wing": {"file": own[1], "type": "STANDARD"}}
    block = side.read_text(encoding="utf-8").split("# The level's trailing edges")[1]
    faces = sum(obj_face_counts(level.obj))
    side.write_text(  # the inventory and units a user's boundaries file states, then the block
        f'fs_build = "26.125"\nboundaries = ["Wing"]\n'
        f'mesh_sha256 = "{hashlib.sha256(level.obj.read_bytes()).hexdigest()}"\n'
        f'boundary_faces = [{faces}]\nmesh_faces = {faces}\n[import]\nunits = "METER"\n'
        "# The level's trailing edges" + block,
        encoding="utf-8",
    )
    assert plan_mark_boundaries(level.obj).mesh == level.obj


def test_a_trailing_edge_listed_in_two_parts_is_one_perimeter():
    """A trailing edge whose node list leaves a node out gives two chains on one perimeter
    of the piece: both are kept. Control: a hole's loop stays out (one perimeter only).
    """
    from pyflightstream.workspace._refine._geometry import edge_faces
    from pyflightstream.workspace._refine._obj import rearmost_perimeter
    from tests.p0380_mesh_fixtures import holed_plate

    fx, te, _ = _sheet_lines()
    pairs = {(min(a, b), max(a, b)) for a, b in zip(te, te[1:], strict=False)}
    gap = sorted(pairs)[len(pairs) // 2]
    kept = rearmost_perimeter(fx.verts, fx.faces, pairs - {gap})
    assert kept == pairs - {gap}
    plate = holed_plate()
    faces = plate.families["P"]
    boundary = {e for e, fs in edge_faces(faces).items() if len(fs) == 1}
    assert rearmost_perimeter(plate.verts, faces, boundary) < boundary


def test_fr3296_the_level_node_list_ids_are_the_level_obj_vertex_numbers(tmp_path):
    """FR-3296 (refine-r1 QA-F1): <level>.nodes.txt rows are 1-based OBJ vertices on the TE."""
    src = _source(tmp_path)
    level = refine_mesh(src, 0.5)
    verts = [
        [float(c) for c in line.split()[1:4]]
        for line in level.obj.read_text(encoding="utf-8").splitlines()
        if line.startswith("v ")
    ]
    listing = level.folder / f"{level.obj.stem}.nodes.txt"
    rows = listing.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("#")
    body = [[c.strip() for c in r.split(",")] for r in rows[1:]]
    assert body and all(name == "G" for _, name, *_ in body)
    for vid, _, x, y, z in body:
        assert verts[int(vid) - 1] == pytest.approx([float(x), float(y), float(z)], abs=1e-6)
    te = (level.folder / f"{level.obj.stem}.te.txt").read_text(encoding="utf-8").splitlines()
    assert len(body) <= len(te)  # only trailing-edge vertices, not every vertex of G


def test_refine_r2_qa4_a_sheet_oriented_by_its_longest_side_writes_no_trailing_edge(tmp_path):
    """FR-3297 (refine-r2 QA-4): the reference of a sheet with no line listed is not a TE file."""
    mesh = source(tmp_path, perimeter=False)
    with pytest.warns(PyflightstreamWarning, match="longest side of its boundary"):
        level = refine_mesh(mesh, 2, parallel=1)
    assert level.report["G"]["method"] == "grid"
    written = [p.name for p in level.folder.iterdir() if p.name.endswith(("te.txt", "nodes.txt"))]
    assert written == []


@pytest.mark.parametrize("key", ["periodic", "trailing_edge"])
@pytest.mark.parametrize("value", ["{}", "false", '"obsolete"'])
def test_p0500_retired_refine_tables_warn_and_skip_even_empty_values(tmp_path, key, value):
    """P0500-SRS: every stated retired table warns, even empty or malformed values."""
    from pyflightstream.workspace._refine._config import read_refine_file

    path = tmp_path / "retired.refine.toml"
    base = "[families.G]\nfactor = 2\n"
    path.write_text(base, encoding="utf-8")
    expected = read_refine_file(path, ["G"])
    path.write_text(f"{key} = {value}\n" + base, encoding="utf-8")
    with pytest.warns(PyflightstreamWarning, match=key + ".*no longer read"):
        actual = read_refine_file(path, ["G"])
    assert actual == expected


def test_p0501_api002_an_empty_selection_is_said_on_stderr(tmp_path, capsys):
    """REL4-API-002: no family selected writes no level and says so on stderr, not stdout."""
    src = _source(tmp_path, refine_toml="[families.G]\nfactor = 2\n")
    with pytest.warns(PyflightstreamWarning, match="no family is selected"):
        code, out, err = _command(capsys, str(src), "2", "--families", ",")
    assert code == 0, err
    assert "no family selected: no level written" in err, err
    assert "no family selected" not in out, out
    assert _left(tmp_path) == []
