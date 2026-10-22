"""P0390-FIRSTROW (FR-430): a grid keeps the spanwise width of its row at another component.

Every source is synthetic (tests/p0380_mesh_fixtures.py and the builders
below): the cambered sheet grid ``G`` with its trailing edge, ``T``, a strip
of triangles sharing G's tip station node for node, and ``U``, a strip sharing
T's last row; ``R``, a strip of triangles at G's root station; a second sheet
``H`` with its own strip ``S``; and a wing tube ``Wing`` with a sharp trailing
edge whose root ring a strip ``Body`` continues. A family of another
component than the grid's (its ``[components]`` entry, else its name up to the
first ``_``) makes the end station it shares an edge with an interface. Each
behaviour is run against its control: the same refinement without
``keep_first_row``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.run import cli
from pyflightstream.workspace import audit_mesh, refine_mesh
from tests.p0380_mesh_fixtures import (
    Composite,
    holed_plate,
    l_sheet,
    open_loop_count,
    read_mesh,
    sheet_with_strips,
    write_source,
)

STRIP = (0.03, 0.04, 0.05, 0.065, 0.08)
GTU = (("T", "tri", STRIP), ("U", "tri", (0.1, 0.1)))
ROOT = (0.05, 0.06, 0.08)


def _toml(factor: float, *, keep: object = True, extra: str = "") -> str:
    lines = ["[families.G]", f"factor = {factor}"]
    if keep is not None:
        lines.append(f"keep_first_row = {str(keep).lower() if isinstance(keep, bool) else keep}")
    return "\n".join(lines) + "\n" + extra


def _with_root(mesh: Composite, name: str = "R", widths=ROOT) -> Composite:
    """Return the mesh with a strip of triangles extruded from G's station 0 toward -y."""
    verts = [mesh.verts]
    count = len(mesh.verts)
    last = list(mesh.rows["G"][0])
    section = mesh.verts[last]
    y = float(section[0, 1])
    rows = [last]
    for w in widths:
        y -= w
        row = section.copy()
        row[:, 1] = y
        verts.append(row)
        rows.append(list(range(count, count + len(row))))
        count += len(row)
    faces = []
    for j in range(len(rows) - 1):
        lo, hi = rows[j], rows[j + 1]
        for i in range(len(lo) - 1):
            a, b, c, d = lo[i], lo[i + 1], hi[i + 1], hi[i]
            faces += [[a, d, c], [a, c, b]] if (i + j) % 2 else [[a, d, b], [b, d, c]]
    families = {name: faces, **mesh.families}
    return Composite(np.vstack(verts), families, mesh.te, {**mesh.rows, name: rows})


def _level(tmp_path: Path, toml: str, mesh: Composite | None = None, name: str = "src", **kw):
    mesh = sheet_with_strips(GTU) if mesh is None else mesh
    src = write_source(tmp_path / name, "wing", mesh, refine_toml=toml, **kw)
    return src, refine_mesh(src, overwrite=True, out_dir=tmp_path / f"out_{name}")


def _family(obj: Path, name: str):
    verts, families = read_mesh(obj)
    return verts, families[name]


def _stations(verts: np.ndarray, faces) -> np.ndarray:
    """Return the sorted spanwise positions (y) of a sheet family's stations."""
    used = sorted({v for f in faces for v in f})
    return np.unique(np.round(verts[used, 1], 9))


def _te_y(path: Path) -> np.ndarray:
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    return np.sort(np.array([float(r.split(",")[1]) for r in rows if r.strip()]))


def _te_file(level) -> Path:
    return next(p for p in level.files if p.name.endswith(".te.txt"))


def _record(level) -> dict:
    record = next(p for p in level.files if p.name.endswith(".refine.json"))
    return json.loads(record.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ FR-952, FR-958


@pytest.mark.parametrize("factor", [2.0, 0.5])
@pytest.mark.parametrize(
    ("root", "tip", "kept"),
    [
        (False, True, ["far station"]),
        (True, False, ["station 0"]),
        (True, True, ["station 0", "far station"]),
    ],
    ids=["far", "station0", "both"],
)
def test_a_kept_row_keeps_its_width_and_the_rest_take_the_factor(tmp_path, factor, root, tip, kept):
    """P0390-FIRSTROW (FR-952, FR-958): each kept row is the source's, the others take the factor.

    A grid kept at the far station, one kept at station 0 and one kept at
    both: each kept row's width equals the source's while the same refinement
    without the option moves it (the control); the m source intervals
    between the kept rows take max(1, round(m * factor)) intervals, held by
    one station more; ``kept_rows`` names the kept stations in refine.json
    and is absent from the control's.
    """
    mesh = sheet_with_strips(GTU if tip else ())
    mesh = _with_root(mesh) if root else mesh
    src_y = _stations(mesh.verts, mesh.families["G"])
    _, level = _level(tmp_path, _toml(factor), mesh, name="kept")
    _, plain = _level(tmp_path, _toml(factor, keep=None), mesh, name="plain")
    kept_y = _stations(*_family(level.obj, "G"))
    plain_y = _stations(*_family(plain.obj, "G"))
    ends = [(0, 1)] if root else []
    ends += [(-1, -2)] if tip else []
    for outer, inner in ends:
        width = abs(src_y[outer] - src_y[inner])
        assert abs(kept_y[outer] - kept_y[inner]) == pytest.approx(width, abs=1e-9)
        assert abs(plain_y[outer] - plain_y[inner]) != pytest.approx(width, abs=1e-6)
    m = len(src_y) - 1 - len(ends)
    between = kept_y[1 if root else 0 : len(kept_y) - (1 if tip else 0)]
    assert len(between) - 1 == max(1, round(m * factor))
    assert len(between) == max(1, round(m * factor)) + 1
    assert kept_y[0] == pytest.approx(src_y[0]) and kept_y[-1] == pytest.approx(src_y[-1])
    assert _record(level)["families"]["G"]["kept_rows"] == kept
    assert "kept_rows" not in _record(plain)["families"]["G"]


# ---------------------------------------------------------------------- FR-953


@pytest.mark.parametrize("root", [False, True], ids=["far", "station0"])
def test_the_last_wake_filament_keeps_its_distance_from_the_adjacent_component(tmp_path, root):
    """P0390-FIRSTROW (FR-953): the kept row's trailing-edge mid-point stays the source's.

    In the level's trailing-edge points file, the mid-point of the kept row's
    trailing-edge edge is at the source's distance from the interface
    station; the control, refined spanwise, moves it toward the component.
    """
    mesh = _with_root(sheet_with_strips(())) if root else sheet_with_strips(GTU)
    end = float(_stations(mesh.verts, mesh.families["G"])[0 if root else -1])
    src = write_source(tmp_path / "s", "wing", mesh)
    te = _te_y(src.with_suffix(".te.txt"))
    source_gap = abs(end - te[0 if root else -1])
    _, level = _level(tmp_path, _toml(2.0), mesh, name="kept")
    _, plain = _level(tmp_path, _toml(2.0, keep=None), mesh, name="plain")
    kept_te, plain_te = _te_y(_te_file(level)), _te_y(_te_file(plain))
    assert abs(end - kept_te[0 if root else -1]) == pytest.approx(source_gap, abs=1e-9)
    assert abs(end - plain_te[0 if root else -1]) < 0.75 * source_gap


# ---------------------------------------------------------------------- FR-954


def test_the_level_stays_closed_and_passes_every_gate(tmp_path):
    """P0390-FIRSTROW (FR-954): the neighbours follow FR-425 and the audit gates pass.

    The unselected neighbour takes the grid's new tip nodes in its band, the
    level's open boundary loops are the source's and no gate of the audit
    fails, as for the same refinement without the option.
    """
    mesh = sheet_with_strips(GTU)
    _, level = _level(tmp_path, _toml(2.0))
    verts, families = read_mesh(level.obj)
    all_faces = [f for fs in families.values() for f in fs]
    source_faces = [f for fs in mesh.families.values() for f in fs]
    assert open_loop_count(all_faces) == open_loop_count(source_faces)
    assert not [g for g in level.audit.gates if g.verdict == "fail"]


# ---------------------------------------------------------------------- FR-955


def _plate_source() -> Composite:
    """Return the holed plate ``P`` (no grid) with the trailing edge listed on its first row."""
    obj = holed_plate()
    row = list(range(13))
    te = 0.5 * (obj.verts[row[:-1]] + obj.verts[row[1:]])
    return Composite(obj.verts, dict(obj.families), te, {})


def _l_source() -> Composite:
    """Return the L-shaped quadrilateral sheet ``L`` (multiblock) with an edge listed."""
    sheet = l_sheet()
    first = sorted((ij[0], v) for v, ij in sheet.place.items() if ij[1] == 0)
    ids = [v for _, v in first]
    te = 0.5 * (sheet.verts[ids[:-1]] + sheet.verts[ids[1:]])
    return Composite(sheet.verts, {"L": sheet.faces}, te, {})


#: The fixture's file route (tests/p0380_mesh_fixtures.py): the points file and the edge
#: type the owner made required (PFS-2124.055). Detection reads neither, so a test that
#: routes the table to detection replaces both lines.
FILE_ROUTE = 'file = "wing.te.txt"\ntype = "STANDARD"'


def _tube_source(*, te: bool = False, sharp_le: bool = False) -> Composite:
    """Return the wing tube ``Wing`` with a sharp trailing edge and ``Body`` at its root ring.

    The section x = (1 + cos t) / 2, z = 0.12 sin t (1 - cos t) / 2 + 0.01 sin t
    over 48 nodes has a round leading edge (no edge sharper than 40 degrees)
    and a sharp trailing edge at t = 0, its chordwise index 0. ``te`` lists
    the trailing-edge mid-points; without it the source has no points file.
    ``sharp_le`` makes the section the lens z = sin t |sin t| / 4, whose
    leading edge (x = 0) is as sharp as its trailing edge (x = 1), about 90
    degrees each, numbered from the leading edge (t from pi), so its node 0
    is a leading-edge node.
    """
    n, stations = 48, 6
    t = 2.0 * np.pi * np.arange(n) / n + (np.pi if sharp_le else 0.0)
    x = 0.5 * (1.0 + np.cos(t))
    z = 0.12 * np.sin(t) * (1.0 - np.cos(t)) / 2.0 + 0.01 * np.sin(t)
    if sharp_le:
        z = np.sin(t) * np.abs(np.sin(t)) / 4.0
    ys = np.linspace(0.0, 2.0, stations)
    wing = np.array([[xi, y, zi] for y in ys for xi, zi in zip(x, z, strict=True)])
    faces = [
        [k * n + i, k * n + (i + 1) % n, (k + 1) * n + (i + 1) % n, (k + 1) * n + i]
        for k in range(stations - 1)
        for i in range(n)
    ]
    body_rows = [list(range(n))]
    verts = [wing]
    count = len(wing)
    for y in (-0.1, -0.25):
        ring = np.column_stack([x, np.full(n, y), z])
        verts.append(ring)
        body_rows.append(list(range(count, count + n)))
        count += n
    body = []
    for j in range(len(body_rows) - 1):
        lo, hi = body_rows[j], body_rows[j + 1]
        for i in range(n):
            a, b, c, d = lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]
            body += [[a, d, c], [a, c, b]]
    all_verts = np.vstack(verts)
    column = [k * n for k in range(stations)]
    points = 0.5 * (all_verts[column[:-1]] + all_verts[column[1:]]) if te else np.zeros((0, 3))
    return Composite(all_verts, {"Body": body, "Wing": faces}, points, {})


def _point_fan(mesh: Composite, at: tuple[int, int], name: str = "P") -> Composite:
    """Return the mesh with a family of two triangles, each touching one node of G's tip row."""
    tip = mesh.rows["G"][-1]
    verts = [mesh.verts]
    faces = []
    count = len(mesh.verts)
    for i in at:
        base = mesh.verts[tip[i]]
        verts.append(np.array([base + [0.01, 0.2, 0.0], base + [-0.01, 0.2, 0.01]]))
        faces.append([tip[i], count, count + 1])
        count += 2
    return Composite(np.vstack(verts), {**mesh.families, name: faces}, mesh.te, dict(mesh.rows))


def _between() -> Composite:
    """Return G, a quadrilateral grid strip T of two rows at its tip, and U beyond T."""
    return sheet_with_strips((("T", "quad", (0.03, 0.04)), ("U", "tri", (0.1, 0.1))))


def _after() -> Composite:
    """Return G and a quadrilateral grid strip T of three rows at its tip, refined after G."""
    return sheet_with_strips((("T", "quad", (0.03, 0.04, 0.05)),))


DETECT = '[import]\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n'


def _refusal_cases():
    """Each FR-955 refusal: its source, its refinement file, the keyword, and words of its
    message.
    """
    body = _toml(2.0).replace("factor = 2.0", "axial = 2.0\naxis = [0.0, 1.0, 0.0]")
    remesh = _toml(2.0).replace("factor = 2.0", 'factor = 2.0\nmethod = "remesh"')
    return [
        ("not-a-bool", sheet_with_strips(GTU), _toml(2.0, keep='"yes"'), {}, "G",
         "keep_first_row = 'yes' is not true or false"),
        ("remesh", sheet_with_strips(GTU), remesh, {}, "G", 'is remeshed (method = "remesh")'),
        ("body", sheet_with_strips(GTU), body, {}, "G", "axial and circumferential remesh a body"),
        ("no-grid", _plate_source(), "[families.P]\nfactor = 2.0\nkeep_first_row = true\n", {},
         "P", "no grid was recovered"),
        ("multiblock", _l_source(), "[families.L]\nfactor = 2.0\nkeep_first_row = true\n", {},
         "L", "is a multiblock grid"),
        ("no-trailing-edge", sheet_with_strips(GTU, te=False), _toml(2.0), {}, "G",
         "does not route its trailing edge to detection"),
        ("detected-nothing", sheet_with_strips(GTU, te=False), _toml(2.0), {"detect": True}, "G",
         "the detection marks no edge of the family"),
        ("alone", sheet_with_strips(()), _toml(2.0), {}, "G", "no interface row to keep"),
        ("same-prefix", sheet_with_strips((("G_tip", "tri", STRIP),)), _toml(2.0), {}, "G",
         "no interface row to keep"),
        ("same-component", sheet_with_strips(GTU),
         _toml(2.0, extra='[components]\nWing = ["G", "T"]\n'), {}, "G",
         "no interface row to keep"),
        ("grid-after-grid", _after(),
         "[families.G]\nfactor = 2.0\n[families.T]\nfactor = 2.0\nkeep_first_row = true\n", {},
         "T", "shares nodes with a grid refined first and is remeshed"),
        ("no-interval-left", _between(), "[families.T]\nfactor = 2.0\nkeep_first_row = true\n",
         {}, "T", "leave none to refine"),
        ("not-in-mesh", sheet_with_strips(GTU), _toml(2.0, keep=None),
         {"keep_first_row": ["Nope"]}, "Nope", "the mesh holds no family 'Nope'"),
        ("left-out", sheet_with_strips(GTU), _toml(2.0, keep=None),
         {"keep_first_row": ["T"]}, "T", "the selection leaves the family out"),
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("case", "mesh", "toml", "kw", "family", "said"),
    _refusal_cases(),
    ids=[c[0] for c in _refusal_cases()],
)
def test_every_refusal_names_the_source_family_and_option_and_writes_nothing(
    tmp_path, case, mesh, toml, kw, family, said
):
    """P0390-FIRSTROW (FR-955): each refusal by its message text, before any work.

    A value not true or false; a family stated with method = "remesh" or
    with axial and circumferential; a family whose grid is not recovered; a
    multiblock grid; a grid without a trailing edge, neither listed nor
    detected (a family with no points and no detection route, and one whose
    boundaries file routes it to detection that marks no edge); a grid with
    no end at another component; a grid remeshed because it shares nodes
    with a grid refined first; a grid whose kept rows leave no spanwise
    interval; and, in the keyword, a family the mesh does not hold or that
    the selection leaves out. Each names the source, the family and
    keep_first_row, ends "Nothing was written." and leaves the output empty.
    """
    detect = kw.pop("detect", False)
    src = write_source(tmp_path / "src", "wing", mesh, refine_toml=toml)
    if detect:
        sidecar = src.with_name("wing.boundaries.toml")
        sidecar.write_text(sidecar.read_text(encoding="utf-8") + DETECT, encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, out_dir=tmp_path / "out", **kw)
    text = str(caught.value)
    assert said in text, text
    assert str(src) in text and f"family {family}" in text and "keep_first_row" in text, text
    assert text.endswith("Nothing was written.")
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())


def test_the_command_refuses_with_exit_2_and_writes_nothing(tmp_path, capsys):
    """P0390-FIRSTROW (FR-955): the command refuses a family the mesh does not hold, exit 2.

    Control: the same command naming a family the mesh holds exits 0.
    """
    src = write_source(tmp_path / "src", "wing", sheet_with_strips(GTU))
    out = tmp_path / "out"
    capsys.readouterr()
    code = cli.main(["refine", str(src), "--families", "G", "--spanwise", "2",
                     "--keep-first-row", "Nope", "--out", str(out)])  # fmt: skip
    err = capsys.readouterr().err
    assert code == 2 and "family Nope keep_first_row" in err
    assert "the mesh holds no family 'Nope'" in err and "Nothing was written." in err
    assert not out.exists() or not any(out.iterdir())
    code = cli.main(["refine", str(src), "--families", "G", "--spanwise", "2",
                     "--keep-first-row", "G", "--out", str(out)])  # fmt: skip
    assert code == 0


# ---------------------------------------------------------------------- FR-956


def test_a_listed_and_a_detected_trailing_edge_each_state_their_provenance(tmp_path):
    """P0390-FIRSTROW (FR-956): listed in the points file, else detected; refine.json says.

    The wing tube with its trailing edge listed keeps its root row with
    ``trailing_edge = "points file"``; the same tube with no points file and
    a boundaries file routing the trailing edge to detection is recovered on
    the detected edges (those sharper than the ridge angle: the trailing
    edge alone here) and keeps the same row with ``"detected"``, and its
    kept row's spanwise width is the source's. Control: without the
    detection route the same source is refused, the trailing edge being
    neither listed nor detected.
    """
    toml = "[families.Wing]\nspanwise = 2.0\nkeep_first_row = true\n"
    _, listed = _level(tmp_path, toml, _tube_source(te=True), name="listed")
    assert listed.report["Wing"]["trailing_edge"] == "points file"
    assert listed.report["Wing"]["kept_rows"] == ["station 0"]
    src = write_source(tmp_path / "det", "wing", _tube_source(), refine_toml=toml)
    sidecar = src.with_name("wing.boundaries.toml")
    plain = sidecar.read_text(encoding="utf-8")
    with pytest.raises(InputArtifactError, match="does not route its trailing edge"):
        refine_mesh(src, out_dir=tmp_path / "out_none")
    sidecar.write_text(plain + DETECT, encoding="utf-8")
    detected = refine_mesh(src, out_dir=tmp_path / "out_det")
    entry = detected.report["Wing"]
    assert entry["trailing_edge"] == "detected" and entry["kept_rows"] == ["station 0"]
    assert entry["method"] == "grid"
    y = _stations(*_family(detected.obj, "Wing"))
    assert y[1] - y[0] == pytest.approx(0.4, abs=1e-9)  # the source's root row
    assert len(y) == 1 + max(1, round(4 * 2.0)) + 1
    assert (
        "trailing_edge" not in _record(_level(tmp_path, _toml(2.0, keep=None))[1])["families"]["G"]
    )


@pytest.mark.parametrize(
    ("units", "line"), [("METER", "METER"), ("MILLIMETER", "MILLIMETER")], ids=["m", "mm"]
)
def test_a_detected_trailing_edge_is_written_to_the_level_points_file(tmp_path, units, line):
    """P0390-FIRSTROW (FR-953, FR-956): a detected kept row's trailing edge is in the points file.

    The wing tube with no trailing-edge points file anywhere in the source,
    its boundaries file routing the trailing edge to detection, keeps its
    root row. The level writes ``<stem>.te.txt`` under the mesh's unit (the
    boundaries file's ``[import] units``, else ``METER``): one mid-point per
    detected trailing-edge edge, all on x = 1, the kept row's at the
    source's distance from the interface station (y = 0.2, the source's
    first edge), the eight edges after it at the refined spacing. The
    level's boundaries file still routes the trailing edge to detection and
    names no points file, and its audit passes G4: the record states Wing
    detected, so the source counts that chain (``source_chains_detected``).
    Controls: the source holds no points file; the same level audited
    against the source with no record beside it keeps the verdict of a
    source without a points file, G4 failed with the values of 0.38.0.
    """
    toml = "[families.Wing]\nspanwise = 2.0\nkeep_first_row = true\n"
    src = write_source(tmp_path / "det", "wing", _tube_source(), refine_toml=toml)
    assert not list(src.parent.glob("*.te.txt"))
    sidecar = src.with_name("wing.boundaries.toml")
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8") + DETECT.replace("METER", units), encoding="utf-8"
    )
    level = refine_mesh(src, out_dir=tmp_path / "out")
    assert level.report["Wing"]["trailing_edge"] == "detected"
    te = level.folder / f"{level.folder.name}.te.txt"
    assert te in level.files and te.is_file()
    rows = te.read_text(encoding="utf-8").splitlines()
    assert rows[0] == line
    points = np.array([[float(c) for c in r.split(",")] for r in rows[1:] if r.strip()])
    assert points[:, 0] == pytest.approx(np.ones(len(points)), abs=1e-9)
    expected = [0.2] + [0.4 + 0.2 * k + 0.1 for k in range(8)]
    assert np.sort(points[:, 1]) == pytest.approx(expected, abs=1e-9)
    routed = level.folder / f"{level.folder.name}.boundaries.toml"
    text = routed.read_text(encoding="utf-8")
    assert 'detect = "auto"' in text and "file =" not in text
    g4 = _g4(level.audit)
    assert g4.passed and g4.values["chains"] == g4.values["source_chains"] == 1, g4.values
    assert g4.values["source_chains_detected"] == 1
    _record_path(level).unlink()
    with pytest.warns(PyflightstreamWarning, match="G4 failed"):
        alone = audit_mesh(level.obj, against=src)
    g4 = _g4(alone)
    assert not g4.passed, g4.values
    assert dict(g4.values) == {
        "points": 9,
        "points_on_edges": 9,
        "points_sharing_an_edge": 0,
        "chains": 1,
        "source_chains": 0,
        "length": 2.0,
        "source_length": 0.0,
        "source_ends": 0,
        "source_ends_missing": 0,
    }


def _g4(audit):
    return next(g for g in audit.gates if g.name == "G4")


def _record_path(level) -> Path:
    return next(p for p in level.files if p.name.endswith(".refine.json"))


def _fold_degrees(mesh: Composite, column: int, n: int = 48) -> float:
    """Return the angle between the normals of the two Wing faces at its root edge ``column``."""
    faces = mesh.families["Wing"]
    normals = []
    for face in (faces[(column - 1) % n], faces[column]):
        p = mesh.verts[face]
        v = np.cross(p[2] - p[0], p[3] - p[1])
        normals.append(v / np.linalg.norm(v))
    return float(np.degrees(np.arccos(np.clip(normals[0] @ normals[1], -1.0, 1.0))))


def test_a_sharp_leading_edge_is_not_taken_for_the_trailing_edge(tmp_path):
    """P0390-FIRSTROW (FR-956): the detected trailing edge is the aft sharp line alone.

    The lens wing tube's leading edge (x = 0, chordwise node 0) and trailing
    edge (x = 1, node 24) are both sharper than the ridge angle, measured on
    the source. The points file lists one edge of ``Body`` alone, so the
    level writes one, and the boundaries file routes Wing's trailing edge to
    detection (``detect = { surfaces = ["Wing"] }``). The level is recovered
    on the trailing edge alone: every trailing-edge mid-point it writes for
    Wing lies on x = 1, none on the leading edge, and the kept root row keeps
    the source's width. G4 passes with two chains on both sides: Body's
    listed edge, and Wing's line, detected on the source as the record
    states. Taking every edge sharper than the ridge angle takes
    the leading edge too, recovers the grid from it, and writes the leading
    edge as Wing's trailing edge.
    """
    lens = _tube_source(sharp_le=True)
    assert _fold_degrees(lens, 0) > 40.0 and _fold_degrees(lens, 24) > 40.0
    far_ring = 6 * 48 + 48  # Body's ring at y = -0.25
    body_edge = 0.5 * (lens.verts[far_ring + 12] + lens.verts[far_ring + 13])
    mesh = Composite(lens.verts, lens.families, body_edge[None, :], {})
    toml = (
        "[families.Wing]\nspanwise = 2.0\nkeep_first_row = true\n"
        "trailing_edge_direction = [1.0, 0.0, 0.0]\n"
    )
    src = write_source(tmp_path / "lens", "wing", mesh, refine_toml=toml)
    sidecar = src.with_name("wing.boundaries.toml")
    text = sidecar.read_text(encoding="utf-8")
    sidecar.write_text(
        text.replace(FILE_ROUTE, 'detect = { surfaces = ["Wing"] }')
        + '\n[import]\nunits = "METER"\n',
        encoding="utf-8",
    )
    level = refine_mesh(src, out_dir=tmp_path / "out")
    entry = level.report["Wing"]
    assert entry["trailing_edge"] == "detected" and entry["kept_rows"] == ["station 0"]
    rows = _te_file(level).read_text(encoding="utf-8").splitlines()[1:]
    points = np.array([[float(c) for c in r.split(",")] for r in rows if r.strip()])
    wing = points[points[:, 1] >= 0.0]
    assert len(points) == len(wing) + 1 and len(wing) == 1 + max(1, round(4 * 2.0))
    assert wing[:, 0] == pytest.approx(np.ones(len(wing)), abs=1e-9)
    y = _stations(*_family(level.obj, "Wing"))
    assert y[1] - y[0] == pytest.approx(0.4, abs=1e-9)
    g4 = _g4(level.audit)  # the listed Body chain and the detected Wing line, on both sides
    assert g4.passed and g4.values["chains"] == g4.values["source_chains"] == 2, g4.values
    assert g4.values["source_chains_detected"] == 1


def _joined_level(tmp_path: Path, units: str | None):
    """Return the source and level of the tube whose listed Body edges continue Wing's line.

    The points file lists the two Body edges from Wing's trailing-edge node
    at the root (node 0) along the body (y = -0.1, then -0.25), and the
    boundaries file routes Wing's trailing edge to detection; Wing keeps its
    root row at spanwise factor 2. With ``units`` the mesh is in that unit
    (``[import] units``) and the points file in METER, its points scaled to
    it, so the recorded mid-points are in METER.
    """
    tube = _tube_source()
    ring1, ring2 = 6 * 48, 6 * 48 + 48
    column = [0, ring1, ring2]
    body = 0.5 * (tube.verts[column[:-1]] + tube.verts[column[1:]])
    mesh = Composite(tube.verts, tube.families, body, {})
    toml = "[families.Wing]\nspanwise = 2.0\nkeep_first_row = true\n"
    src = write_source(tmp_path / "joined", "wing", mesh, refine_toml=toml)
    sidecar = src.with_name("wing.boundaries.toml")
    text = sidecar.read_text(encoding="utf-8")
    text = text.replace(FILE_ROUTE, 'detect = { surfaces = ["Wing"] }')
    if units is not None:
        text += f'\n[import]\nunits = "{units}"\n'
        rows = ["METER"] + [",".join(f"{c / 1000.0:.12f}" for c in p) for p in body]
        src.with_name("wing.te.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    else:
        text += '\n[import]\nunits = "METER"\n'
    sidecar.write_text(text, encoding="utf-8")
    return src, refine_mesh(src, out_dir=tmp_path / "out")


@pytest.mark.parametrize("units", [None, "MILLIMETER"], ids=["same-unit", "mm-mesh"])
def test_a_listed_edge_joining_the_detected_line_is_one_source_chain(tmp_path, units):
    """P0390-FIRSTROW (FR-954): G4 counts the listed and detected source edges together.

    The listed Body edges continue Wing's detected trailing-edge line at the
    root node, so on the source they form one chain with it, and the intact
    level's trailing edge is one chain too. ``refine.json`` records the
    detected line under Wing (``trailing_edge_points``, its five edges'
    mid-points on x = 1, in the unit of the points file), and G4 passes with
    ``chains == source_chains == 1``. Counting one more source chain per
    detected family (0.39.0 W1) gives two and fails the intact level.
    """
    src, level = _joined_level(tmp_path, units)
    entry = _record(level)["families"]["Wing"]
    assert entry["trailing_edge"] == "detected"
    recorded = np.array(entry["trailing_edge_points"], dtype=float)
    scale = 1.0 if units is None else 0.001
    assert recorded.shape == (5, 3)
    assert recorded[:, 0] == pytest.approx(np.full(5, scale), abs=1e-12)
    assert np.sort(recorded[:, 1]) == pytest.approx(scale * (0.2 + 0.4 * np.arange(5)), abs=1e-12)
    g4 = _g4(level.audit)
    assert g4.passed, g4.values
    assert g4.values["chains"] == g4.values["source_chains"] == 1, g4.values
    assert g4.values["source_chains_detected"] == 1
    again = _g4(audit_mesh(level.obj, against=src))
    assert again.passed and again.values["source_chains"] == 1, again.values


def test_a_level_missing_a_middle_detected_edge_fails_g4(tmp_path):
    """P0390-FIRSTROW (FR-954): a broken trailing edge is two chains against the source's one.

    The level of the joined tube is re-audited after the middle Wing
    mid-point (y > 0) is taken out of its points file, so its trailing edge
    is two chains, the root part with the Body edges and the tip part. The
    source's listed and detected edges together are one chain, so G4 fails.
    Counting one more source chain per detected family gives two source
    chains and passes the broken level.
    """
    src, level = _joined_level(tmp_path, None)
    te = _te_file(level)
    lines = te.read_text(encoding="utf-8").splitlines()
    rows = [r for r in lines[1:] if r.strip()]
    wing = sorted((float(r.split(",")[1]), r) for r in rows if float(r.split(",")[1]) > 0.0)
    middle = wing[len(wing) // 2][1]
    te.write_text("\n".join([lines[0]] + [r for r in rows if r != middle]) + "\n", "utf-8")
    with pytest.warns(PyflightstreamWarning, match="G4 failed"):
        broken = audit_mesh(level.obj, against=src)
    g4 = _g4(broken)
    assert not g4.passed, g4.values
    assert g4.values["chains"] == 2 and g4.values["source_chains"] == 1, g4.values


# ---------------------------------------------------------------------- FR-957


def test_the_tag_of_a_kept_selection_carries_k(tmp_path):
    """P0390-FIRSTROW (FR-957): the option puts the family's k into the level's tag.

    Two otherwise identical selections, one with the option and one without,
    are written into folders whose tags differ by the k.
    """
    _, level = _level(tmp_path, _toml(2.0), name="kept")
    _, plain = _level(tmp_path, _toml(2.0, keep=None), name="plain")
    assert plain.folder.name == "wing_R-G2"
    assert level.folder.name == "wing_R-G2k"


# ---------------------------------------------------------------------- FR-950


def _two_sheets() -> Composite:
    """Return G with T at its tip, and a second sheet H with S at its tip, far from it."""
    one = sheet_with_strips((("T", "tri", STRIP),))
    two = sheet_with_strips((("S", "tri", STRIP),))
    shift = len(one.verts)
    families = dict(one.families)
    for old, new in (("G", "H"), ("T", "S")):
        source = two.families["G" if old == "G" else "S"]
        families[new] = [[v + shift for v in f] for f in source]
    verts = np.vstack([one.verts, two.verts + [5.0, 0.0, 0.0]])
    te = np.vstack([one.te, two.te + [5.0, 0.0, 0.0]])
    return Composite(verts, families, te, {})


FILE_GH = (
    "[families.G]\nspanwise = 2.0\nkeep_first_row = true\n"
    "[families.H]\nspanwise = 2.0\nkeep_first_row = true\n"
)


def _bytes(level) -> list[bytes]:
    return [p.read_bytes() for p in level.files if p.suffix in (".obj", ".txt")]


def test_the_command_the_keyword_and_the_file_write_the_same_level(tmp_path, capsys):
    """P0390-FIRSTROW (FR-950): three routes, one family set, one level.

    ``pyfs-matrix refine --keep-first-row G,H``, ``refine_mesh(keep_first_row=
    ["G", "H"])`` and ``keep_first_row = true`` in the tables of G and H write
    the same level (its tag, its OBJ and points file bytes, its kept rows);
    ``keep_first_row=None`` and ``[]`` write the level without the option.
    """
    mesh = _two_sheets()
    src = write_source(tmp_path / "call", "wing", mesh)
    capsys.readouterr()
    code = cli.main(["refine", str(src), "--families", "G,H", "--spanwise", "2",
                     "--keep-first-row", "G,H", "--out", str(tmp_path / "cmd")])  # fmt: skip
    assert code == 0, capsys.readouterr().err
    by_kw = refine_mesh(
        src, families=["G", "H"], spanwise=2.0, keep_first_row=["G", "H"], out_dir=tmp_path / "kw"
    )
    from_file = write_source(tmp_path / "file", "wing", mesh, refine_toml=FILE_GH)
    by_file = refine_mesh(from_file, out_dir=tmp_path / "toml")
    by_cmd = tmp_path / "cmd" / by_kw.folder.name
    assert by_kw.folder.name == by_file.folder.name == "wing_R-G1s2k-H1s2k"
    assert by_cmd.is_dir()
    cmd_files = sorted(p for p in by_cmd.iterdir() if p.suffix in (".obj", ".txt"))
    assert [p.read_bytes() for p in cmd_files] == _bytes(by_kw) == _bytes(by_file)
    for level in (by_kw, by_file):
        assert level.report["G"]["kept_rows"] == level.report["H"]["kept_rows"] == ["far station"]
    for empty in (None, []):
        plain = refine_mesh(
            src,
            families=["G", "H"],
            spanwise=2.0,
            keep_first_row=empty,
            out_dir=tmp_path / f"plain{empty is None}",
        )
        assert plain.folder.name == "wing_R-G1s2-H1s2"
        assert "kept_rows" not in plain.report["G"] and "kept_rows" not in plain.report["H"]


def test_factors_from_the_call_warn_that_the_tables_keep_first_row_is_not_read(tmp_path):
    """P0390-FIRSTROW (FR-950): with FACTOR the tables are not read, keep_first_row named.

    The warning that names the tables not read names keep_first_row among
    what they no longer state, and the level keeps no row. Control: the
    file's own factors keep the row.
    """
    from pyflightstream._errors import PyflightstreamWarning

    src = write_source(tmp_path / "src", "wing", sheet_with_strips(GTU), refine_toml=_toml(2.0))
    with pytest.warns(PyflightstreamWarning, match="keep_first_row") as seen:
        called = refine_mesh(src, 2.0, families=["G"], out_dir=tmp_path / "called")
    assert "[families.G]" in str(seen[0].message)
    assert "kept_rows" not in called.report["G"]
    assert refine_mesh(src, out_dir=tmp_path / "file").report["G"]["kept_rows"] == ["far station"]


# ---------------------------------------------------------------------- FR-951


def test_two_shared_nodes_that_are_not_an_edge_make_no_interface(tmp_path):
    """P0390-FIRSTROW (FR-951): an interface is an edge of the end station, not two nodes.

    A family of another component touching G's tip station at two nodes that
    are not consecutive makes no interface: alone, the option is refused
    for want of an interface; with a strip at G's root, only station 0 is
    kept. Control: the same family touching two consecutive nodes (an edge)
    makes the tip an interface.
    """
    apart = _point_fan(sheet_with_strips(()), (3, 7))
    with pytest.raises(InputArtifactError, match="no interface row to keep"):
        _level(tmp_path, _toml(1.0).replace("factor = 1.0", "spanwise = 2.0"), apart, "apart")
    toml = _toml(1.0).replace("factor = 1.0", "spanwise = 2.0")
    _, rooted = _level(tmp_path, toml, _with_root(apart), "rooted")
    assert rooted.report["G"]["kept_rows"] == ["station 0"]
    edge = _point_fan(sheet_with_strips(()), (3, 4))
    tip = edge.rows["G"][-1]
    edge.families["P"].append([tip[3], tip[4], len(edge.verts) - 1])
    _, joined = _level(tmp_path, toml, edge, "joined")
    assert joined.report["G"]["kept_rows"] == ["far station"]
