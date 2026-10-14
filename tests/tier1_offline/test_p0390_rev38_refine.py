"""P0390-REV38: refinement structure and geometry regression coverage.

Retain module boundaries, import paths and tuning-constant locations, plus
coarse-source surface bounds, pole-fan limits and split-sheet recovery.
All geometry fixtures are synthetic.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

import pyflightstream
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine._geometry import GRID_SURFACE_DISTANCE
from pyflightstream.workspace._refine._grid import Grid, recover_grid, refine_grid
from tests.p0380_mesh_fixtures import Composite, Fixture, build_grid, write_source
from tests.tier1_offline.test_p0380_s1_grid import _distance_to_surface

REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(pyflightstream.__file__).resolve().parent
REFINE_DIR = PACKAGE / "workspace" / "_refine"
REFINE = "pyflightstream.workspace._refine"
REMESH = f"{REFINE}._remesh"

_SPEC = importlib.util.spec_from_file_location(
    "arch_metrics_rev38", REPO / "scripts" / "arch_metrics.py"
)
assert _SPEC is not None and _SPEC.loader is not None
am = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = am
_SPEC.loader.exec_module(am)


# ------------------------------------------------------------ PUSH-W3-ARCH-1


def _size_findings(sources: dict[str, str]) -> list[str]:
    """Return what the guard says of refinement modules: over its size, or not deep."""
    out = []
    for name, text in sorted(sources.items()):
        lines = am.code_lines(text)
        if lines > am.SOFT_LINES:
            out.append(f"{name}: {lines} code lines, above {am.SOFT_LINES}")
        defs = am.top_level_defs(text)
        if name != "__init__.py" and (defs < am.DEEP_MIN_DEFS or lines < am.DEEP_MIN_LINES):
            out.append(f"{name}: {defs} definitions and {lines} code lines, not deep")
    return out


def test_push_w3_arch_1_every_refinement_module_is_under_the_guards_size():
    """P0390-REV38 (NFR-45 R3, PUSH-W3-ARCH-1): no refinement module is above the size guard.

    The unit and the limit are the architecture guard's (``scripts/arch_metrics.py``):
    code lines without docstrings, at most ``SOFT_LINES``, the size above
    which a module needs a baseline entry or a size exemption; and a module
    is deep (at least ``DEEP_MIN_DEFS`` definitions and ``DEEP_MIN_LINES``
    code lines). None of the refinement modules holds an entry or an
    exemption. Control: a remesher grown past the limit is reported.
    """
    sources = {p.name: p.read_text(encoding="utf-8") for p in sorted(REFINE_DIR.glob("*.py"))}
    assert {"_remesh.py", "_remesh_group.py", "_remesh_pairs.py"} <= set(sources)
    assert _size_findings(sources) == []
    baselines = json.loads(am.BASELINES.read_text(encoding="utf-8"))
    table = {p for p in baselines["module_code_lines"] if "_refine/" in p}
    assert table == set()
    grown = sources["_remesh.py"] + "".join(f"X{i} = {i}\n" for i in range(am.SOFT_LINES))
    assert _size_findings({"_remesh.py": grown}) == [
        f"_remesh.py: {am.code_lines(grown)} code lines, above {am.SOFT_LINES}"
    ]


def _remesh_reads() -> set[str]:
    """Return every name another module or test reads from the remesher, by syntax tree."""
    found: set[str] = set()
    files = [*PACKAGE.rglob("*.py"), *(REPO / "tests").rglob("*.py")]
    for path in files:
        if path.name.startswith("_remesh") and path.parent == REFINE_DIR:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == REMESH:
                found.update(a.name for a in node.names)
            if isinstance(node, ast.ImportFrom) and node.module == REFINE:
                aliases.update(a.asname or a.name for a in node.names if a.name == "_remesh")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
            ):
                found.add(node.attr)
    return found


def _defined(path: Path) -> set[str]:
    """Return the names a module defines at its top level (assignments, functions, classes)."""
    out = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef | ast.ClassDef):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
    return out


def test_push_w3_arch_1_the_remesher_split_keeps_every_import_path():
    """P0390-REV38 (NFR-45 R3, PUSH-W3-ARCH-1): the remesher is split and its paths hold.

    The group a remesh works on and the pairing of triangles into
    quadrilaterals are modules of their own; each name defined there is
    defined nowhere else in the package. Every name another module or a test
    reads from ``_remesh`` (read from the syntax tree of the package and of
    the tests, so a new reader is covered without editing a list) resolves,
    and a name defined in a section is the very object of its section.
    Control: a name no reader uses is not in the set read.
    """
    remesh = importlib.import_module(REMESH)
    sections = {f"{REFINE}.{m}": REFINE_DIR / f"{m}.py" for m in ("_remesh_group", "_remesh_pairs")}
    homes = {}
    for module, path in sections.items():
        names = _defined(path)
        assert names, module
        assert not names & _defined(REFINE_DIR / "_remesh.py"), module
        homes.update(dict.fromkeys(names, importlib.import_module(module)))
    read = _remesh_reads()
    assert {"refine_group", "require_geometry_extra", "element_report", "Patch"} <= read
    assert "INDEX_MODULES" not in read
    for name in sorted(read):
        assert hasattr(remesh, name), name
        if name in homes:
            assert getattr(remesh, name) is getattr(homes[name], name), name


# ------------------------------------------------------------ PUSH-W12-ARCH-1


def _constant_comments(path: Path) -> dict[str, str]:
    """Return each module-level numeric constant of a source with its ``#:`` comment."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    module = importlib.import_module(f"{REFINE}.{path.stem}")
    out = {}
    for node in ast.parse(text).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id.isupper()):
            continue
        value = getattr(module, target.id)
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        comment: list[str] = []
        row = node.lineno - 2
        while row >= 0 and lines[row].startswith("#:"):
            comment.insert(0, lines[row][2:].strip())
            row -= 1
        out[target.id] = " ".join(comment)
    return out


def test_push_w12_arch_1_the_thresholds_paragraph_names_where_each_constant_lives():
    """P0390-REV38 (NFR-45 R3, PUSH-W12-ARCH-1): each tuning constant is where _geometry says.

    The module docstring of ``_geometry`` holds the thresholds the
    requirements name and names the remesher's own tuning constants as
    ``_module.NAME``. Each one it names is defined at the top level of that
    module and not in ``_geometry``; every numeric constant of a remesh
    module (``_remesh`` and its sections, read from the package's files) is
    named there; and none of them cites a requirement in its comment, since
    a threshold a requirement names is defined in ``_geometry`` (the layers
    of FR-432 R2 among them). Controls: a constant named in the paragraph
    but defined elsewhere, and a remesh constant whose comment cites a
    requirement, are each reported.
    """
    geometry = importlib.import_module(f"{REFINE}._geometry")
    named = re.findall(r"``(_\w+)\.([A-Z][A-Z0-9_]*)``", geometry.__doc__ or "")
    assert named

    def misplaced(pairs, own):
        return [
            f"{m}.{n}"
            for m, n in pairs
            if not (REFINE_DIR / f"{m}.py").is_file()
            or n not in _defined(REFINE_DIR / f"{m}.py")
            or n in own
        ]

    own = _defined(REFINE_DIR / "_geometry.py")
    assert misplaced(named, own) == []
    assert misplaced([("_remesh", "AUGMENT_DEPTH")], own) == ["_remesh.AUGMENT_DEPTH"]
    constants = {}
    for path in sorted(REFINE_DIR.glob("_remesh*.py")):
        for name, comment in _constant_comments(path).items():
            constants[f"{path.stem}.{name}"] = comment
    assert set(constants) == {f"{m}.{n}" for m, n in named}
    cites = re.compile(r"\b(FR|NFR)-\d+")
    assert [k for k, c in constants.items() if cites.search(c)] == []
    assert cites.search("#: The layers of FR-432 R2.") is not None
    assert "SHARED_LAYERS" in own and geometry.SHARED_LAYERS == 2


# ------------------------------------------------------------------- RC-QA-1


def _dense_surface(fx: Fixture, per: int) -> tuple[np.ndarray, list[list[int]]]:
    """Return the fixture's analytic surface as triangles ``per`` times finer than its cells."""
    cols = fx.nodes if fx.wrap else fx.nodes - 1
    s = np.linspace(0.0, cols, cols * per + 1)
    t = np.linspace(0.0, fx.stations - 1, (fx.stations - 1) * per + 1)
    pts = fx.surface(s, t)
    rows, width = pts.shape[:2]
    gid = np.arange(rows * width).reshape(rows, width)
    faces = []
    for k in range(rows - 1):
        for i in range(width - 1):
            a, b, c, d = gid[k, i], gid[k, i + 1], gid[k + 1, i + 1], gid[k + 1, i]
            faces += [[int(a), int(b), int(c)], [int(a), int(c), int(d)]]
    return pts.reshape(-1, 3), faces


def test_rc_qa_1_a_coarse_source_bounds_the_level_by_the_spline_surface():
    """P0390-REV38 (NFR-45 R4, RC-QA-1; FR-424 R6): the bound is met on the spline surface.

    A coarse cambered sheet of 4 stations by 4 chordwise nodes (three
    intervals each way, the fewest the not-a-knot spline takes) is refined
    at factor 2. Its coordinates are cubic in the grid indices, so the spline
    through the source's nodes is the analytic surface; that surface is
    sampled 16 times finer than the cells, which places it within a tenth of
    the bound (checked). Every level node lies within
    ``GRID_SURFACE_DISTANCE`` of the size from that surface, while the
    source's panels lie farther than the bound from the level's nodes: a
    distance measured to the panels fails on this fixture. Control: the
    linear interpolation of the same nodes (a resampling that stays on the
    panels) is farther than the bound from the surface.
    """
    fx = build_grid(Fixture("coarse-sheet", False, 4, 4, ("edge", "edge"), None))
    grid = recover_grid(fx.verts, fx.faces, fx.te)
    assert isinstance(grid, Grid), grid
    level = refine_grid(fx.verts, fx.faces, grid, chordwise=2.0, spanwise=2.0)
    assert len(level.points) == 7 * 7
    bound = GRID_SURFACE_DISTANCE * fx.size
    dense, faces = _dense_surface(fx, 16)
    between = fx.surface(np.arange(0.25, 3.0, 0.5), np.arange(0.25, 3.0, 0.5)).reshape(-1, 3)
    assert _distance_to_surface(between, dense, faces).max() < 0.1 * bound
    assert _distance_to_surface(level.points, dense, faces).max() <= bound
    assert _distance_to_surface(level.points, fx.verts, fx.faces).max() > bound
    at = {place: v for v, place in fx.place.items()}
    corners = [
        fx.verts[[at[(k, i)], at[(k, i + 1)], at[(k + 1, i)], at[(k + 1, i + 1)]]]
        for k in range(3)
        for i in range(3)
    ]
    linear = np.array([0.25 * (a + b + c + d) for a, b, c, d in corners])
    assert _distance_to_surface(linear, dense, faces).max() > bound


# ------------------------------------------------- IND4-01 and PUSH-IND3-QA-3


def _volume(verts: np.ndarray, faces: list[list[int]]) -> float:
    total = 0.0
    for f in faces:
        for j in range(1, len(f) - 1):
            a, b, c = verts[f[0]], verts[f[j]], verts[f[j + 1]]
            total += float(np.dot(a, np.cross(b, c))) / 6.0
    return total


def _two_pole_tube(around: int, split: bool) -> tuple[Composite, Fixture]:
    """Return a wing tube of 5 stations closed by a pole fan at each end, ``around`` nodes round.

    The lateral cells are quadrilaterals, or split into triangles with
    mirrored diagonals; the tip fan is the fixture's own and the root fan is
    wound like it around a pole 0.05 of the span inboard of the root section.
    """
    diag = {i: (0 if i < around // 2 else 1) for i in range(around)} if split else None
    fx = build_grid(Fixture(f"tube-{around}", True, 5, around, ("open", "pole"), diag))
    at = {place: v for v, place in fx.place.items()}
    ring = [at[(0, i)] for i in range(around)]
    center = fx.verts[ring].mean(axis=0) - [0.0, 0.05, 0.0]
    verts = np.vstack([fx.verts, center[None, :]])
    pole = len(verts) - 1
    faces = [list(f) for f in fx.faces]
    faces += [[pole, ring[(i + 1) % around], ring[i]] for i in range(around)]
    if _volume(verts, faces) < 0:
        faces = [f[::-1] for f in faces]
    column = [at[(k, 0)] for k in range(fx.stations)]
    te = 0.5 * (verts[column[:-1]] + verts[column[1:]])
    return Composite(verts, {"W": faces}, te, {}), fx


@pytest.mark.parametrize(
    ("around", "split", "shared"),
    [(4, False, 20), (5, True, 6), (6, True, 20)],
    ids=["4-quadrilaterals", "5-split-cells", "6-split-cells"],
)
def test_ind4_01_a_pole_fan_size_shared_by_other_nodes_is_remeshed_never_a_wrong_grid(
    tmp_path, around, split, shared
):
    """P0390-REV38 (NFR-45 R4, IND4-01, PUSH-IND3-QA-3; FR-424 R9): the limit of 0.38.0 is pinned.

    A two-pole tube is recovered only when its two poles are the only nodes
    of their fan size. Here the fan size is shared: 4 around a tube of
    quadrilaterals (every lateral node has 4 faces), 5 around a tube of
    split cells (the near-pole ring's valence, PUSH-IND3-QA-3) and 6 (the
    split cells' interior valence). No grid is recovered, the reason is
    named, and ``refine_mesh`` under ``auto`` remeshes the family, never
    writing a wrong grid. Control: 8 around, a size only the poles have, is
    recovered as the tube's grid of 5 stations by 8 nodes.
    """
    pytest.importorskip("trimesh")
    mesh, fx = _two_pole_tube(around, split)
    faces = mesh.families["W"]
    sizes = np.bincount(np.array([v for f in faces for v in f]))
    assert int((sizes == around).sum()) == shared + 2
    te = {v for v, (k, i) in fx.place.items() if i == 0}
    found = recover_grid(mesh.verts, faces, te)
    assert isinstance(found, str) and found, found
    src = write_source(tmp_path / "src", "wing", mesh)
    entry = refine_mesh(src, 2.0).report["W"]
    assert (entry["method"], entry["reason"]) == ("remesh", f"no grid recovered: {found}")
    control, cfx = _two_pole_tube(8, split)
    cte = {v for v, (k, i) in cfx.place.items() if i == 0}
    grid = recover_grid(control.verts, control.families["W"], cte)
    assert isinstance(grid, Grid) and grid.ends == ("pole", "pole") and grid.ids.shape == (5, 8)


# ------------------------------------------------------------ PUSH-IND2-QA-1


def _split_faces(fx: Fixture, diagonal) -> list[list[int]]:
    """Return a fixture's quadrilaterals each split into two triangles along ``diagonal(k, i)``."""
    out = []
    for quad in fx.faces:
        k, i = (min(fx.place[v][j] for v in quad) for j in (0, 1))
        a, b, c, d = quad
        out += [[a, b, c], [a, c, d]] if diagonal(k, i) == 0 else [[a, b, d], [b, c, d]]
    return out


def _corner_faces(faces: list[list[int]], grid: Grid) -> list[int]:
    """Return how many faces hold each corner of the grid."""
    corners = [grid.ids[0, 0], grid.ids[0, -1], grid.ids[-1, 0], grid.ids[-1, -1]]
    return [sum(int(c) in f for f in faces) for c in corners]


def test_push_ind2_qa_1_a_square_split_sheet_is_recovered_with_its_corners():
    """P0390-REV38 (NFR-45 R4, PUSH-IND2-QA-1; FR-424 GRID FAMILY, IND-08): a square sheet.

    A cambered sheet of 9 by 9 nodes (8 by 8 cells, so both sides have the
    same count and the corner search cannot tell them apart by length) is
    split along a-c, which puts two corners in two triangles: the boundary
    reading misses it and the corners come from the cells. The grid is the
    unsplit sheet's, node for node. Control: the unsplit sheet's corners
    each lie in one face.
    """
    fx = build_grid(Fixture("square", False, 9, 9, ("edge", "edge"), None))
    quads = recover_grid(fx.verts, fx.faces, fx.te)
    assert isinstance(quads, Grid) and _corner_faces(fx.faces, quads) == [1, 1, 1, 1]
    faces = _split_faces(fx, lambda k, i: 0)
    grid = recover_grid(fx.verts, faces, fx.te)
    assert isinstance(grid, Grid), grid
    assert sorted(_corner_faces(faces, grid)) == [1, 1, 2, 2]
    assert grid.layout == "sheet" and np.array_equal(grid.ids, quads.ids)
    assert grid.cell_diag is not None and grid.ids.shape == (9, 9)


def test_push_ind2_qa_1_a_one_by_n_split_strip_is_recovered_with_its_corners():
    """P0390-REV38 (NFR-45 R4, PUSH-IND2-QA-1; FR-424 GRID FAMILY, IND-08): a strip of one cell.

    A cambered strip of 2 stations by 19 chordwise nodes (one cell by 18) is
    split along a-c: every node lies on the boundary, and the corner search
    must place the short sides at the strip's ends. The grid is the unsplit
    strip's, node for node, with the trailing edge at chordwise index 0, for
    the strip split along a-c and along b-d. Control: the unsplit strip.
    """
    fx = build_grid(Fixture("strip", False, 2, 19, ("edge", "edge"), None))
    quads = recover_grid(fx.verts, fx.faces, fx.te)
    assert isinstance(quads, Grid) and quads.ids.shape == (2, 19)
    for rule in (0, 1):
        faces = _split_faces(fx, lambda k, i, rule=rule: rule)
        grid = recover_grid(fx.verts, faces, fx.te)
        assert isinstance(grid, Grid), grid
        assert np.array_equal(grid.ids, quads.ids), rule
        assert {int(v) for v in grid.ids[:, 0]} == fx.te


def _pinwheel() -> tuple[np.ndarray, list[list[int]]]:
    """Return a cambered 2 by 2 sheet whose four diagonals all meet at its center node.

    Node ``3 k + i`` is at station k, chordwise i. Every corner then lies in
    two triangles and so does every side's middle node, and both sets of four
    are corners of a 2 by 2 sheet whose cells are these triangles.
    """
    k, i = np.meshgrid(np.arange(3), np.arange(3), indexing="ij")
    verts = np.stack([0.5 * i, 0.6 * k, 0.04 * np.sin(np.pi * i / 2.0)], axis=-1)
    a_c = lambda a, b, c, d: [[a, b, c], [a, c, d]]  # noqa: E731
    b_d = lambda a, b, c, d: [[a, b, d], [b, c, d]]  # noqa: E731
    faces = a_c(0, 1, 4, 3) + b_d(1, 2, 5, 4) + b_d(3, 4, 7, 6) + a_c(4, 5, 8, 7)
    return verts.reshape(-1, 3).astype(float), faces


def test_push_ind2_qa_1_two_sheets_fitting_the_cells_are_refused_naming_the_family(tmp_path):
    """P0390-REV38 (NFR-45 R4, PUSH-IND2-QA-1; FR-424 R9, R11, IND-08): the ambiguity refusal.

    The pinwheel sheet's triangles are the cells of two 2 by 2 sheets, one
    cornered at the corners and one at the sides' middle nodes, and the
    trailing edge (the chordwise index 0 line and the edge from its first
    node to the next) is a grid line of both. No grid is recovered and the
    reason says two sheets fit; ``method = "grid"`` is refused naming the
    file's family and that reason, and ``auto`` remeshes it giving the same
    reason. Control: the trailing edge of the chordwise line alone gives the
    one sheet cornered at the corners.
    """
    pytest.importorskip("trimesh")
    verts, faces = _pinwheel()
    alone = recover_grid(verts, faces, {0, 3, 6})
    assert isinstance(alone, Grid) and sorted(alone.ids[:, 0].tolist()) == [0, 3, 6]
    reason = "2 sheets of split quadrilaterals fit its cells"
    assert recover_grid(verts, faces, {0, 1, 3, 6}) == reason
    te = 0.5 * (verts[[0, 3, 0]] + verts[[3, 6, 1]])
    toml = '[families.G]\nfactor = 2\nmethod = "grid"\n'
    src = write_source(
        tmp_path / "src", "wing", Composite(verts, {"G": faces}, te, {}), refine_toml=toml
    )
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src)
    text = str(caught.value)
    said = f"{src} family G: method is grid and no grid was recovered: {reason}."
    assert text == f"{said} Nothing was written."
    src.with_name("wing.refine.toml").write_bytes(b"[families.G]\nfactor = 2\n")
    with warnings.catch_warnings():
        # The remesh of a sheet of four cells is judged by its audit (its skewness check
        # fails, a warning); its quality is not what this test asserts.
        warnings.filterwarnings("ignore", "audit check skewness failed", PyflightstreamWarning)
        entry = refine_mesh(src).report["G"]
    assert (entry["method"], entry["reason"]) == ("remesh", f"no grid recovered: {reason}")
