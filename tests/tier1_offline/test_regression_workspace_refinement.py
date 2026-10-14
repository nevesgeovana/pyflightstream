"""Regression coverage grouped by subject."""

from __future__ import annotations

import json
import os
import tomllib
import warnings
from pathlib import Path

import numpy
import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace import audit_mesh, refine_mesh
from pyflightstream.workspace._refine import _config
from pyflightstream.workspace._refine._config import RefineRequest, level_tag, resolve_request
from pyflightstream.workspace._refine._geometry import order_like
from pyflightstream.workspace._refine._grid import Grid, recover_grid, refine_grid
from pyflightstream.workspace._refine._obj import read_obj, read_te
from pyflightstream.workspace._refine._periodic import find_cuts, match_level
from pyflightstream.workspace._refine._remesh import refine_group
from pyflightstream.workspace.sidecars import read_raw_mesh_conditions
from tests.p0380_mesh_fixtures import Composite as _Workspace2RefineWingComposite
from tests.p0380_mesh_fixtures import face_coordinates as _workspace_2_refine_wing__face_coordinates
from tests.p0380_mesh_fixtures import read_mesh as _workspace_2_refine_wing__read_mesh
from tests.p0380_mesh_fixtures import (
    sheet_with_strips as _workspace_2_refine_entry__sheet_with_strips,
)
from tests.p0380_mesh_fixtures import (
    sheet_with_strips as _workspace_2_refine_level__sheet_with_strips,
)
from tests.p0380_mesh_fixtures import write_source as _reviews2_refine_te__write_source
from tests.p0380_mesh_fixtures import write_source as _workspace_2_refine_entry__write_source
from tests.p0380_mesh_fixtures import write_source as _workspace_2_refine_level__write_source
from tests.p0380_mesh_fixtures import write_source as _workspace_2_refine_wing__write_source
from tests.tier1_offline.test_p0380_s1_refine import _json as _workspace_1_refine___json
from tests.tier1_offline.test_p0380_s1_refine import _left as _workspace_1_refine___left
from tests.tier1_offline.test_p0380_s1_refine import _refused as _workspace_1_refine___refused
from tests.tier1_offline.test_p0380_s1_refine import _source as _decided_docs_1_refine_tag___source
from tests.tier1_offline.test_p0380_s1_refine import _source as _workspace_1_refine___source
from tests.tier1_offline.test_p0380_s1_refine import _two_tubes as _workspace_1_refine___two_tubes
from tests.tier1_offline.test_p0380_s4_sector import (
    PERIODIC as _WORKSPACE_2_REFINE_SECTOR__PERIODIC,
)
from tests.tier1_offline.test_p0380_s4_sector import SIX as _WORKSPACE_2_REFINE_SECTOR__SIX
from tests.tier1_offline.test_p0380_s4_sector import _cells as _workspace_2_refine_sector___cells
from tests.tier1_offline.test_p0380_s4_sector import _wedge as _workspace_2_refine_sector___wedge
from tests.tier1_offline.test_p0380_s4_sector import _write as _workspace_2_refine_sector___write
from tests.tier1_offline.test_p0390_firstrow import (
    _joined_level as _reviews2_refine_te___joined_level,
)
from tests.tier1_offline.test_p0390_firstrow import (
    _tube_source as _reviews2_refine_te___tube_source,
)

_DECIDED_DOCS_1_REFINE_TAG__PAGE = (
    Path(__file__).resolve().parents[2] / "docs" / "mesh" / "reference.md"
)


def _decided_docs_1_refine_tag___numbers(node: object) -> list[float]:
    """Return every number of a parsed JSON tree."""
    if isinstance(node, dict):
        return [n for value in node.values() for n in _decided_docs_1_refine_tag___numbers(value)]
    if isinstance(node, list):
        return [n for value in node for n in _decided_docs_1_refine_tag___numbers(value)]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return [float(node)]
    return []


class TestDecidedDocs1RefineTag:
    """Tier 1: the short refine tag and two factors it cannot tell apart (P0400-REFINE-TAG).

    Pipeline role: quality gate on the level tag of ``refine`` (FR-433, planning
    node PFS-2081.01). A factor in a built tag shows 6 significant digits, so two
    factors that agree to 6 digits build one tag: the second level is refused as
    an existing one unless overwritten, and ``refine.json`` keeps the exact factor.
    The page docs/mesh/reference.md states all three facts.
    """

    @staticmethod
    def test_p0400_refine_tag_close_factors_collide_and_refine_json_keeps_the_exact_one(tmp_path):
        # Verifies FR-433.
        """P0400-REFINE-TAG: 2.0000001 and 2.0000002 share R2; the second is refused, then replaced."""  # noqa: E501
        src = _decided_docs_1_refine_tag___source(tmp_path)
        first = refine_mesh(src, 2.0000001)
        assert first.folder.name.endswith("_R2"), first.folder
        record = json.loads((first.folder / f"{first.folder.name}.refine.json").read_text("utf-8"))
        assert 2.0000001 in _decided_docs_1_refine_tag___numbers(record["specs"]), record["specs"]
        with pytest.raises(InputArtifactError, match=r"the level exists; give overwrite=True"):
            refine_mesh(src, 2.0000002)
        second = refine_mesh(src, 2.0000002, overwrite=True)
        assert second.folder == first.folder

    @staticmethod
    def test_p0400_refine_tag_page_states_digits_exact_factor_and_collision():
        """P0400-REFINE-TAG: the page gives the 6 digits, the exact factor and the refusal."""
        text = " ".join(_DECIDED_DOCS_1_REFINE_TAG__PAGE.read_text(encoding="utf-8").split())
        assert "at most 6 significant digits" in text
        assert "`refine.json` holds the exact factor under `specs`" in text
        assert "refused as an existing one unless `--overwrite`" in text

    @staticmethod
    def test_p0400_refine_tag_rounding_collision_excludes_summary_hashes():
        """P0400-REFINE-TAG: summary hashes retain digits hidden by the short spelling."""
        names = ["LongFamilyNameAlpha", "LongFamilyNameBeta"]
        requests = [
            _config.RefineRequest(
                specs={
                    names[0]: _config.FamilySpec(factor=factor),
                    names[1]: _config.FamilySpec(factor=5.0),
                }
            )
            for factor in (2.0000001, 2.0000002)
        ]
        assert [_config.spec_tag(request.specs[names[0]]) for request in requests] == ["2", "2"]
        tags = [_config.level_tag(request, names) for request in requests]
        assert all(tag.startswith("R-2fam-") for tag in tags)
        assert tags[0] != tags[1]
        text = " ".join(_DECIDED_DOCS_1_REFINE_TAG__PAGE.read_text(encoding="utf-8").split())
        assert "For a short tag without a hash" in text
        assert "Summary tags hash the exact factors" in text


def _reviews2_refine_te___detected_source(tmp_path, detect: str):
    source = _reviews2_refine_te__write_source(
        tmp_path / "src",
        "wing",
        _reviews2_refine_te___tube_source(),
        refine_toml="[families.Wing]\nspanwise = 2\nkeep_first_row = true\n",
    )
    side = source.with_suffix(".boundaries.toml")
    side.write_text(
        side.read_text("utf-8")
        + '\n[import]\nunits = "METER"\n'
        + f"[trailing_edges]\ndetect = {detect}\n",
        "utf-8",
    )
    return source


def _reviews2_refine_te___drop_last_edge(level) -> None:
    path = level.obj.with_suffix(".te.txt")
    lines = path.read_text("utf-8").splitlines()
    rows = np.array([[float(v) for v in line.split(",")] for line in lines[1:]])
    last = int(np.argmax(rows[:, 1]))
    kept = [row for i, row in enumerate(lines[1:]) if i != last]
    path.write_text("\n".join([lines[0], *kept]) + "\n", "utf-8")


class TestReviews2RefineTe:
    """P0400-TEROUTE (PFS-2088.018) and P0400-TECHAIN (PFS-2099.020): the refined trailing edge.

    TEROUTE: a kept row's trailing edge the refinement detects is written to the
    level's points file, and the level's boundaries file names that file in place
    of ``detect`` when every family the route selects was detected, so the run
    reads the line the refinement kept and the audit checked. When the route also
    covers a family the refinement did not detect on, ``detect`` stays and a
    warning names the points file the run does not read.

    TECHAIN: gate G4 compares the level's trailing-edge length with the source's,
    so a trailing-edge chain shortened by a dropped edge fails it while a refined
    level, whose edges are split but whose line is the same, passes.
    """

    @staticmethod
    def test_p0400_teroute_the_level_names_the_points_file_the_refinement_detected(tmp_path):
        """P0400-TEROUTE: detect on the kept-row family alone becomes file = <stem>.te.txt."""
        source = _reviews2_refine_te___detected_source(tmp_path, '{ surfaces = ["Wing"] }')
        level = refine_mesh(source)
        points = level.obj.with_suffix(".te.txt")
        side = level.obj.with_suffix(".boundaries.toml")
        table = tomllib.loads(side.read_text("utf-8"))["trailing_edges"]
        assert table == {"file": points.name}
        marking = read_raw_mesh_conditions(side).trailing_edges
        assert marking.route == "file"
        assert marking.points_file == str(points)
        assert points.is_file()
        gate = next(g for g in audit_mesh(level.obj, against=source).gates if g.name == "G4")
        assert gate.passed, gate

    @staticmethod
    def test_p0400_teroute_a_route_covering_an_undetected_family_keeps_detect_and_warns(tmp_path):
        """P0400-TEROUTE: detect = "auto" also covers Body; detect stays and a warning says so."""
        source = _reviews2_refine_te___detected_source(tmp_path, '"auto"')
        with pytest.warns(PyflightstreamWarning, match=r"does not name.*Body"):
            level = refine_mesh(source)
        table = tomllib.loads(level.obj.with_suffix(".boundaries.toml").read_text("utf-8"))
        assert table["trailing_edges"] == {"detect": "auto"}

    @staticmethod
    def test_p0400_techain_a_shortened_trailing_edge_chain_fails_g4(tmp_path):
        """P0400-TECHAIN: removing the tip edge of the refined line fails G4, naming the length."""
        source, level = _reviews2_refine_te___joined_level(tmp_path, None)
        before = next(g for g in audit_mesh(level.obj, against=source).gates if g.name == "G4")
        assert before.passed, before
        _reviews2_refine_te___drop_last_edge(level)
        gate = next(g for g in audit_mesh(level.obj, against=source).gates if g.name == "G4")
        assert not gate.passed
        assert gate.values["length"] < gate.values["source_length"]


def _workspace_1_refine___one_row_sheet():
    """A sheet of 2 stations by 4 nodes, written row by row from station 0."""
    verts = numpy.array([[float(x), float(y), 0.0] for y in (0, 1) for x in range(4)])
    faces = [[i, i + 1, i + 5, i + 4] for i in range(3)]
    return verts, faces


class TestWorkspace1Refine:
    """P0400-WSREFINE: the refinement request, the face order and a one-row grid.

    0.40.0 lane workspace-1.

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSREFINE")

    @staticmethod
    @pytest.mark.parametrize("families", [[], ()], ids=["list", "tuple"])
    def test_p0400_wsrefine_an_empty_family_selection_is_refused(tmp_path, families):
        """P0400-WSREFINE (PFS-2099.005): no family selected writes no unchanged R- level."""
        src = _workspace_1_refine___source(tmp_path)
        text = _workspace_1_refine___refused(tmp_path, src, 2.0, families=families)
        assert "no family is selected" in text
        assert _workspace_1_refine___left(tmp_path) == []

    @staticmethod
    @pytest.mark.parametrize("tag", [None, "empty"])
    def test_p0400_wsrefine_level_tags_refuse_an_empty_selection_even_with_a_custom_tag(tag):
        """P0400-WSREFINE (PFS-2099.005): the independent level-tag guard refuses no work."""
        with pytest.raises(InputArtifactError, match="no family is selected"):
            level_tag(RefineRequest(specs={}, tag=tag), ["G"])

    @staticmethod
    def test_p0400_wsrefine_a_refinement_file_that_is_not_utf8_is_refused(tmp_path):
        """P0400-WSREFINE (PFS-2099.004): a cp1252 byte is a refusal naming the file."""
        src = _workspace_1_refine___source(tmp_path)
        src.with_name("wing.refine.toml").write_bytes(b"# caf\xe9\n[families.G]\nfactor = 2\n")
        text = _workspace_1_refine___refused(tmp_path, src)
        assert "wing.refine.toml" in text and "cannot be read" in text

    @staticmethod
    def test_p0400_wsrefine_a_keep_first_row_only_table_names_the_fix(tmp_path):
        """P0400-WSREFINE (PFS-2093.013): the refusal says how to ask keep_first_row instead."""
        src = _workspace_1_refine___source(
            tmp_path, refine_toml="[families.G]\nkeep_first_row = true\n"
        )
        text = _workspace_1_refine___refused(tmp_path, src)
        assert "--keep-first-row" in text and "states no factor, chordwise or spanwise" in text

    @staticmethod
    def test_p0400_wsrefine_a_trailing_edge_file_that_is_not_utf8_is_refused(tmp_path):
        """P0400-WSREFINE (PFS-2099.004): the second reader refuses cp1252 by name."""
        path = tmp_path / "edge.txt"
        path.write_bytes(bytes([233]))
        with pytest.raises(InputArtifactError, match="edge.txt.*UTF-8"):
            read_te(path)

    @staticmethod
    def test_p0400_wsrefine_a_selected_family_without_a_table_warns(tmp_path):
        """P0400-WSREFINE (PFS-2089.003): a copied family names the missing table."""
        src = _workspace_1_refine___source(tmp_path, refine_toml="[families.G]\nfactor = 2\n")
        with pytest.warns(PyflightstreamWarning, match=r"add \[families.tail\].*give FACTOR"):
            request = resolve_request(src, ["G", "tail"])
        assert request.missing == ("tail",)

    @staticmethod
    def test_p0400_wsrefine_missing_family_tables_are_recorded_beside_ignored_tables(tmp_path):
        """P0400-WSREFINE (PFS-2089.003): refine.json names copied selected families."""
        source = _workspace_1_refine___two_tubes(tmp_path, "[families.A]\nfactor = 2\n")
        with pytest.warns(PyflightstreamWarning, match=r"add \[families.B\]"):
            level = refine_mesh(source)
        record = _workspace_1_refine___json(level.files[2])
        assert record["missing_families_tables"] == ["B"]
        assert record["ignored_families_tables"] == []

    @staticmethod
    def test_p0400_wsrefine_the_face_order_does_not_depend_on_the_length_unit():
        """P0400-WSREFINE (PFS-2099.019): faces on one source face follow its vertices, any unit."""
        length = 10000.0
        verts = numpy.array([[0.0, 0.0, 0.0], [length, 0.0, 0.0], [0.0, length, 0.0]])
        source = [[0, 1, 2]]
        near_second = numpy.array([[9850.0, 10.0, 0.0], [9950.0, 10.0, 0.0], [9900.0, 40.0, 0.0]])
        near_first = numpy.array(
            [[1000.0, 1000.0, 0.0], [1150.0, 1000.0, 0.0], [1000.0, 1150.0, 0.0]]
        )
        for scale in (1.0, 1.0e-4):
            pts = numpy.vstack([near_second, near_first]) * scale
            out = order_like(pts, [[0, 1, 2], [3, 4, 5]], verts * scale, source)
            assert sorted(out[0]) == [3, 4, 5], (scale, out)

    @staticmethod
    def test_p0400_wsrefine_a_one_row_grid_is_written_in_its_rows_from_station_0():
        """P0400-WSREFINE (PFS-2099.018): refined spanwise, the sheet keeps its row order."""
        verts, faces = _workspace_1_refine___one_row_sheet()
        grid = recover_grid(verts, faces, (3, 7))
        assert isinstance(grid, Grid), grid
        level = refine_grid(verts, faces, grid, chordwise=1.0, spanwise=2.0)
        centroids = [tuple(numpy.round(level.points[f].mean(axis=0)[:2], 6)) for f in level.faces]
        assert centroids == [
            (0.5, 0.25),
            (1.5, 0.25),
            (2.5, 0.25),
            (0.5, 0.75),
            (1.5, 0.75),
            (2.5, 0.75),
        ], centroids

    @staticmethod
    def test_p0400_wsrefine_a_one_column_grid_keeps_its_forward_grid_column_sweep():
        """P0400-WSREFINE (PFS-2099.018): a missing chordwise neighbour never reverses it."""
        verts = numpy.array([[float(x), float(y), 0.0] for y in range(4) for x in (0, 1)])
        faces = [[2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2] for k in range(3)]
        grid = recover_grid(verts, faces, (1, 3, 5, 7))
        assert isinstance(grid, Grid), grid
        level = refine_grid(verts, faces, grid, chordwise=2.0, spanwise=1.0)
        centroids = [tuple(numpy.round(level.points[f].mean(axis=0)[:2], 6)) for f in level.faces]
        assert centroids == [
            (0.75, 0.5),
            (0.75, 1.5),
            (0.75, 2.5),
            (0.25, 0.5),
            (0.25, 1.5),
            (0.25, 2.5),
        ], centroids

    @staticmethod
    def test_p0400_wsrefine_refine_mesh_takes_no_empty_selection_through_the_library_call(tmp_path):
        """P0400-WSREFINE (PFS-2099.005): the public call refuses before any work, by class."""
        src = _workspace_1_refine___source(tmp_path)
        with pytest.raises(InputArtifactError):
            refine_mesh(src, 2.0, families=[])


_WORKSPACE_2_REFINE_ENTRY__WITH_T = (("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),)


def _workspace_2_refine_entry___source(
    tmp_path: Path, strips=_WORKSPACE_2_REFINE_ENTRY__WITH_T
) -> Path:
    return _workspace_2_refine_entry__write_source(
        tmp_path / "src", "wing", _workspace_2_refine_entry__sheet_with_strips(strips)
    )


class TestWorkspace2RefineEntry:
    """P0400-REFINEENTRY: refine_mesh takes its arguments as the API states them, and refuses alike."""  # noqa: E501

    @staticmethod
    @pytest.fixture(autouse=True, scope="class")
    def _optional_dependencies():
        pytest.importorskip("trimesh")

    @staticmethod
    def test_p0400_refineentry_a_missing_obj_is_an_input_artifact_refusal(tmp_path):
        """P0400-REFINEENTRY (PFS-2085.010): a mesh path that is no file is refused as
        InputArtifactError, as audit_mesh refuses it, never a bare FileNotFoundError."""
        with pytest.raises(InputArtifactError) as caught:
            refine_mesh(tmp_path / "src" / "absent.obj", 2)
        assert "no such OBJ file" in str(caught.value)
        assert str(caught.value).endswith("Nothing was written.")
        assert list(tmp_path.iterdir()) == []

    @staticmethod
    def test_p0400_refineentry_a_bare_family_name_is_one_family(tmp_path):
        """P0400-REFINEENTRY (PFS-2099.010): a string selects one whole family name."""
        src = _workspace_2_refine_entry___source(tmp_path)
        src.write_text(src.read_text("utf-8").replace("g G", "g GRID"), encoding="utf-8")
        level = refine_mesh(src, 2, families="GRID", out_dir=tmp_path / "out")
        assert level.report["GRID"]["method"] == "grid"

    @staticmethod
    def test_p0400_refineentry_a_bare_file_name_goes_beside_its_folder(tmp_path):
        """P0400-REFINEENTRY (PFS-2099.009): a bare file name run in the mesh's own folder writes
        the level into the parent of that folder, the documented default, instead of refusing it
        as inside the source's folder."""
        src = _workspace_2_refine_entry___source(tmp_path)
        here = Path.cwd()
        os.chdir(src.parent)
        try:
            level = refine_mesh("wing.obj", 2, families=["G"])
        finally:
            os.chdir(here)
        assert level.folder.parent.resolve() == tmp_path.resolve()

    @staticmethod
    def test_p0400_refineentry_the_rebuilt_whole_warning_points_at_the_caller(tmp_path):
        """P0400-REFINEENTRY (PFS-2099.015): the FR-431 warning is attributed to the line that
        called refine_mesh, this file, not to a line of the library."""
        src = _workspace_2_refine_entry___source(tmp_path, (("T", "tri", (0.03, 0.04)),))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            refine_mesh(src, 2, families=["G"], out_dir=tmp_path / "out")
        rebuilt = [
            w
            for w in caught
            if issubclass(w.category, PyflightstreamWarning) and "rebuilt whole" in str(w.message)
        ]
        assert len(rebuilt) == 1, [str(w.message) for w in caught]
        assert Path(rebuilt[0].filename).resolve() == Path(__file__).resolve(), rebuilt[0].filename


def _workspace_2_refine_level___record(level) -> dict:
    return json.loads(next(Path(level.folder).glob("*.refine.json")).read_text(encoding="utf-8"))


def _workspace_2_refine_level___te_rows(level) -> list[str]:
    return next(Path(level.folder).glob("*.te.txt")).read_text(encoding="utf-8").splitlines()[1:]


class TestWorkspace2RefineLevel:
    """P0400-REFINELEVEL: what a level records and writes of its families and its trailing edge."""

    @staticmethod
    @pytest.fixture(autouse=True, scope="class")
    def _optional_dependencies():
        pytest.importorskip("trimesh")

    @staticmethod
    def test_p0400_refinelevel_a_selected_family_at_factor_one_is_in_the_specs(tmp_path):
        """P0400-REFINELEVEL (PFS-2099.007): G at 2 and T at 1 are both selected; T is kept
        unchanged, and refine.json's specs still records it with its factor (FR-433 R4)."""
        toml = "[families.G]\nfactor = 2\n[families.T]\nfactor = 1\n"
        mesh = _workspace_2_refine_level__sheet_with_strips(
            (("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),)
        )
        src = _workspace_2_refine_level__write_source(
            tmp_path / "src", "wing", mesh, refine_toml=toml
        )
        level = refine_mesh(src, config=src.with_suffix(".refine.toml"), out_dir=tmp_path / "out")
        record = _workspace_2_refine_level___record(level)
        assert record["specs"]["T"]["factor"] == 1.0, record["specs"]
        assert record["specs"]["G"]["factor"] == 2.0
        assert record["families"]["T"]["method"] == "unchanged"

    @staticmethod
    def test_p0400_refinelevel_a_trailing_edge_between_two_interfaces_keeps_its_point(tmp_path):
        """P0400-REFINELEVEL (PFS-2099.020): T, a one-row quadrilateral strip between the grid G
        and the strip U, is remeshed; its trailing-edge edge joins two interface nodes, and its
        point is still in the level's points file: one row per source trailing-edge edge."""
        strips = (("T", "quad", (0.03,)), ("U", "tri", (0.04, 0.05)))
        mesh = _workspace_2_refine_level__sheet_with_strips(strips)
        toml = '[families.T]\nfactor = 1\nmethod = "remesh"\n'
        src = _workspace_2_refine_level__write_source(
            tmp_path / "src", "wing", mesh, refine_toml=toml
        )
        level = refine_mesh(src, config=src.with_suffix(".refine.toml"), out_dir=tmp_path / "out")
        assert _workspace_2_refine_level___record(level)["families"]["T"]["method"] == "remesh"
        assert len(_workspace_2_refine_level___te_rows(level)) == len(mesh.te)


def _workspace_2_refine_sector___body(axial: float, circumferential: float) -> str:
    return (
        f"[families.W]\naxial = {axial}\ncircumferential = {circumferential}\n"
        "axis = [0.0, 0.0, 1.0]\n"
    )


class TestWorkspace2RefineSector:
    """P0400-REFINESECTOR: a periodic sector's cut is never resampled by an undecided factor."""

    @staticmethod
    @pytest.fixture(autouse=True, scope="class")
    def _optional_dependencies():
        pytest.importorskip("trimesh")

    @staticmethod
    def test_p0400_refinesector_a_body_stretched_unlike_on_a_cut_is_refused(tmp_path):
        """P0400-REFINESECTOR (PFS-2099.023): a sector of a cylinder at axial 1 and
        circumferential 3 is refused before any work, naming both factors, where its cut was
        resampled by max(axial, circumferential) = 3 along the axis."""
        source = _workspace_2_refine_sector___write(
            tmp_path,
            _workspace_2_refine_sector___wedge(na=6, nz=6),
            _WORKSPACE_2_REFINE_SECTOR__PERIODIC + _workspace_2_refine_sector___body(1, 3),
        )
        with pytest.raises(InputArtifactError) as caught:
            refine_mesh(source)
        message = str(caught.value)
        assert "axial 1 and circumferential 3" in message and "[periodic]" in message, message
        assert sorted(p.name for p in tmp_path.iterdir()) == ["src"]

    @staticmethod
    def test_p0400_refinesector_a_body_stretched_alike_still_refines(tmp_path):
        """P0400-REFINESECTOR (PFS-2099.023): equal factors leave one factor for the cut; refined."""  # noqa: E501
        source = _workspace_2_refine_sector___write(
            tmp_path,
            _workspace_2_refine_sector___wedge(na=6, nz=6),
            _WORKSPACE_2_REFINE_SECTOR__PERIODIC + _workspace_2_refine_sector___body(2, 2),
        )
        assert refine_mesh(source).obj.is_file()

    @staticmethod
    def test_p0400_refinesector_a_finely_spaced_open_edge_beside_a_cut_is_not_the_cut():
        """P0400-REFINESECTOR (PFS-2099.022): the wedge's open arcs are spaced 0.3 degrees beside
        each cut, closer to the cut's corner than a quarter of its first segment. The arc's node is
        no cut node: the level (here the source itself) matches its cuts node for node, where the
        distance rule took the arc's node at 0.3 degrees on one cut and at 59.7 on the other and
        refused a sector that matches."""
        theta = numpy.radians([0.0, 0.3, 10.0, 20.0, 30.0, 40.0, 50.0, 59.7, 60.0])
        z = 0.5 * (1.0 - numpy.cos(numpy.pi * numpy.arange(6) / 5))
        t, h = numpy.meshgrid(theta, z)
        verts = numpy.column_stack([numpy.cos(t).ravel(), numpy.sin(t).ravel(), h.ravel()])
        na = len(theta) - 1
        faces = {
            "W": _workspace_2_refine_sector___cells(
                na, [(i, j) for j in range(5) for i in range(na)]
            )
        }
        size = float(numpy.linalg.norm(verts.max(axis=0) - verts.min(axis=0)))
        cuts = find_cuts(verts, faces, _WORKSPACE_2_REFINE_SECTOR__SIX, size=size, where="wedge")
        level, report = match_level(
            verts,
            faces,
            cuts,
            _WORKSPACE_2_REFINE_SECTOR__SIX,
            source=verts,
            size=size,
            where="wedge",
        )
        assert report is not None and report["level_distance"] <= 1e-9 * size, report
        assert report["pairs"][0]["level_nodes"] == [6, 6], report


#: Chordwise positions from the trailing edge (column 0) to the leading edge.
_WORKSPACE_2_REFINE_WING__X = (1.0, 0.995, 0.98, 0.94, 0.8, 0.6, 0.35, 0.12, 0.0)


#: Spanwise stations; the root is y = 0.
_WORKSPACE_2_REFINE_WING__Y = (0.0, 0.25, 0.5, 0.75, 1.0)


def _workspace_2_refine_wing___thickness(x: float) -> float:
    return 0.3 * x**0.5 * (1.0 - x)


def _workspace_2_refine_wing__wing(*, root: bool = True) -> _Workspace2RefineWingComposite:
    """Return the two-sheet wing, with the root band F when ``root``."""
    n, k = len(_WORKSPACE_2_REFINE_WING__X), len(_WORKSPACE_2_REFINE_WING__Y)
    verts: list[tuple[float, float, float]] = []
    upper: dict[tuple[int, int], int] = {}
    lower: dict[tuple[int, int], int] = {}
    for s, y in enumerate(_WORKSPACE_2_REFINE_WING__Y):
        for i, x in enumerate(_WORKSPACE_2_REFINE_WING__X):
            upper[s, i] = len(verts)
            verts.append((x, y, _workspace_2_refine_wing___thickness(x)))
        for i, x in enumerate(_WORKSPACE_2_REFINE_WING__X):
            if i in (0, n - 1):
                lower[s, i] = upper[s, i]
            else:
                lower[s, i] = len(verts)
                verts.append((x, y, -_workspace_2_refine_wing___thickness(x)))
    families: dict[str, list[list[int]]] = {"U": [], "L": []}
    for s in range(k - 1):
        for i in range(n - 1):
            families["U"].append(
                [upper[s, i], upper[s, i + 1], upper[s + 1, i + 1], upper[s + 1, i]]
            )
            families["L"].append(
                [lower[s, i], lower[s + 1, i], lower[s + 1, i + 1], lower[s, i + 1]]
            )
    if root:
        ring = [upper[0, i] for i in range(n)] + [lower[0, i] for i in range(n - 2, 0, -1)]
        below = []
        for v in ring:
            x, _, z = verts[v]
            below.append(len(verts))
            verts.append((x, -0.2, z))
        families["F"] = [
            [ring[j], below[j], below[(j + 1) % len(ring)], ring[(j + 1) % len(ring)]]
            for j in range(len(ring))
        ]
    points = numpy.asarray(verts, dtype=float)
    column = [upper[s, 0] for s in range(k)]
    te = 0.5 * (points[column[:-1]] + points[column[1:]])
    return _Workspace2RefineWingComposite(points, families, te, {})


def _workspace_2_refine_wing___source(tmp_path: Path, mesh: _Workspace2RefineWingComposite) -> Path:
    return _workspace_2_refine_wing__write_source(tmp_path / "src", "wing", mesh)


def _workspace_2_refine_wing___te_rows(level) -> list[tuple[float, ...]]:
    lines = next(Path(level.folder).glob("*.te.txt")).read_text(encoding="utf-8").splitlines()
    return [tuple(round(float(c), 6) for c in row.split(",")) for row in lines[1:]]


def _workspace_2_refine_wing___gate(level, name: str):
    return next(item for item in level.audit.gates if item.name == name)


class TestWorkspace2RefineWing:
    """P0400-REFINEWING: a wing of two sheets sharing their trailing and leading edges, on a root.

    The synthetic source: ``U`` and ``L``, the upper and lower surfaces of a
    wing, each a sheet grid of five stations by nine chordwise nodes clustered
    at the trailing edge (x = 1, column 0); they share the trailing-edge and the
    leading-edge lines node for node. ``F``, a band of another component, closes
    the root station of both. The trailing-edge points file lists the trailing
    edge once, the edges U and L share.
    """

    @staticmethod
    @pytest.fixture(autouse=True, scope="class")
    def _optional_dependencies():
        pytest.importorskip("trimesh")

    @staticmethod
    def test_p0400_refinewing_a_factor_one_grid_leaves_its_neighbour_byte_identical(tmp_path):
        """P0400-REFINEWING (PFS-2099.008): U at factor 1 keeps every node, so L, which shares its
        trailing and leading edges, is copied face for face; a root node of U beside the
        trailing-edge corner is no node of the shared trailing edge."""
        mesh = _workspace_2_refine_wing__wing()
        level = refine_mesh(
            _workspace_2_refine_wing___source(tmp_path, mesh),
            1,
            families=["U"],
            out_dir=tmp_path / "out",
        )
        verts, families = _workspace_2_refine_wing__read_mesh(level.obj)
        assert level.report["L"] == {"method": "copied"}, level.report["L"]
        assert _workspace_2_refine_wing__face_coordinates(
            verts, families["L"]
        ) == _workspace_2_refine_wing__face_coordinates(mesh.verts.round(9), mesh.families["L"])

    @staticmethod
    def test_p0400_refinewing_a_factor_two_grid_welds_to_its_neighbours(tmp_path):
        """P0400-REFINEWING (PFS-2099.008): U at factor 2; L and F take U's new nodes on the curves
        they share and nothing else, so the level passes G1 and G3 (no crack, no edge of three)."""
        level = refine_mesh(
            _workspace_2_refine_wing___source(tmp_path, _workspace_2_refine_wing__wing()),
            2,
            families=["U"],
            out_dir=tmp_path / "out",
        )
        assert _workspace_2_refine_wing___gate(level, "G1").verdict == "pass", (
            _workspace_2_refine_wing___gate(level, "G1")
        )
        assert _workspace_2_refine_wing___gate(level, "G3").verdict == "pass", (
            _workspace_2_refine_wing___gate(level, "G3")
        )

    @staticmethod
    def test_p0400_refinewing_a_trailing_edge_two_families_hold_is_written_once(tmp_path):
        """P0400-REFINEWING (PFS-2099.016, PFS-2099.024): U refined chordwise only keeps its
        trailing-edge nodes and L is copied; both hold the trailing-edge edges, and the level's
        points file names each edge once, one row per source row."""
        mesh = _workspace_2_refine_wing__wing(root=False)
        level = refine_mesh(
            _workspace_2_refine_wing___source(tmp_path, mesh),
            chordwise=2,
            families=["U"],
            out_dir=tmp_path,
        )
        rows = _workspace_2_refine_wing___te_rows(level)
        assert len(rows) == len(set(rows)) == len(mesh.te), rows
        assert json.loads(next(level.folder.glob("*.refine.json")).read_text("utf-8"))

    @staticmethod
    def test_p0400_refinewing_a_sheet_trailing_edge_is_detected_across_its_families(tmp_path):
        """P0400-REFINEWING (PFS-2099.017): no points file; the boundaries file routes U's
        trailing edge to detection and U keeps its root row. U's trailing edge is a boundary of
        U, sharp only with L's faces beside it; measured on every family's faces it is found."""
        mesh = _workspace_2_refine_wing__wing()
        mesh = _Workspace2RefineWingComposite(mesh.verts, mesh.families, numpy.zeros((0, 3)), {})
        toml = (
            "[families.U]\nspanwise = 2.0\nkeep_first_row = true\n"
            "trailing_edge_direction = [1.0, 0.0, 0.0]\n"
        )
        src = _workspace_2_refine_wing__write_source(
            tmp_path / "src", "wing", mesh, refine_toml=toml
        )
        sidecar = src.with_name("wing.boundaries.toml")
        text = sidecar.read_text(encoding="utf-8")
        sidecar.write_text(
            text + '\n[import]\nunits = "METER"\n[trailing_edges]\ndetect = { surfaces = ["U"] }\n',
            "utf-8",
        )
        level = refine_mesh(src, out_dir=tmp_path / "out")
        entry = level.report["U"]
        assert entry["trailing_edge"] == "detected" and entry["kept_rows"] == ["station 0"], entry
        rows = _workspace_2_refine_wing___te_rows(level)
        assert rows and all(row[0] == 1.0 for row in rows), rows

    @staticmethod
    @pytest.mark.requirement("FR-430")
    def test_p0400_bgtests2_detected_trailing_edges_require_mesh_units(tmp_path):
        """PFS-2099.006: detection cannot label unknown mesh coordinates as metres."""
        from pyflightstream.workspace import InputArtifactError

        mesh = _workspace_2_refine_wing__wing()
        mesh = _Workspace2RefineWingComposite(mesh.verts, mesh.families, numpy.zeros((0, 3)), {})
        src = _workspace_2_refine_wing___source(tmp_path, mesh)
        src.with_suffix(".boundaries.toml").write_text(
            '[trailing_edges]\ndetect = { surfaces = ["U"] }\n', encoding="utf-8"
        )
        with pytest.raises(InputArtifactError, match=r"\[import\].*units"):
            refine_mesh(src, spanwise=2, families=["U"], keep_first_row=["U"])

    @staticmethod
    @pytest.mark.requirement("FR-432")
    @pytest.mark.parametrize("unit", ["MILLIMETER", None])
    def test_p0400_bgtests2_shared_edge_targets_state_their_units(tmp_path, unit):
        """PFS-2099.011: native lengths become metres only with a declared conversion."""
        from tests.p0380_mesh_fixtures import sheet_with_strips

        mesh = sheet_with_strips((("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),))
        src = _workspace_2_refine_wing___source(tmp_path, mesh)
        sidecar = src.with_suffix(".boundaries.toml")
        if unit is not None:
            sidecar.write_text(
                sidecar.read_text("utf-8") + f'\n[import]\nunits = "{unit}"\n', encoding="utf-8"
            )
        te = src.with_suffix(".te.txt")
        te.write_text(te.read_text("utf-8").replace("METER", unit or "METER"), encoding="utf-8")
        level = refine_mesh(src, 2, families=["G"])
        entry = level.report["T"]
        if unit is None:
            assert "shared_edge_target_m" not in entry
            assert entry["shared_edge_target_mesh_units"]["max"] > 0
        else:
            assert 0 < entry["shared_edge_target_m"]["max"] < 0.001

    @staticmethod
    @pytest.mark.requirement("FR-426")
    def test_p0400_bgtests2_remesh_preserves_only_listed_trailing_edges(tmp_path):
        """PFS-2099.021: four TE vertices do not make all four sides trailing edges."""
        points = numpy.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
        te = numpy.array([[0.5, 0, 0], [0.5, 1, 0]])
        src = _workspace_2_refine_wing__write_source(
            tmp_path / "src",
            "plate",
            _Workspace2RefineWingComposite(points, {"A": [[0, 1, 2, 3]]}, te, {}),
            refine_toml='[families.A]\nfactor = 1\nmethod = "remesh"\n',
        )
        level = refine_mesh(src)
        assert sorted(_workspace_2_refine_wing___te_rows(level)) == sorted(map(tuple, te.tolist()))

    @staticmethod
    @pytest.mark.requirement("FR-426")
    def test_p0400_bgtests2_assembled_grid_and_copied_family_share_one_trailing_edge(tmp_path):
        """PFS-2099.016 and PFS-2099.024: assembly deduplicates a grid part and its copied neighbour."""  # noqa: E501
        mesh = _workspace_2_refine_wing__wing(root=False)
        # Uniform chord spacing keeps both source and refined corner nodes away
        # from the neighboring spanwise edge on older refinement implementations.
        vertices = mesh.verts.copy()
        vertices[:, 0] = numpy.interp(
            vertices[:, 0],
            _WORKSPACE_2_REFINE_WING__X[::-1],
            numpy.linspace(0, 1, len(_WORKSPACE_2_REFINE_WING__X)),
        )
        mesh = _Workspace2RefineWingComposite(vertices, mesh.families, mesh.te, {})
        level = refine_mesh(
            _workspace_2_refine_wing___source(tmp_path, mesh),
            chordwise=2,
            families=["U"],
            out_dir=tmp_path / "out",
        )
        assert level.report["U"]["method"] == "grid"
        assert level.report["L"]["method"] == "copied"
        midpoints = _workspace_2_refine_wing___te_rows(level)
        assert len(midpoints) == len(mesh.te)
        assert sorted(midpoints) == sorted(map(tuple, mesh.te.tolist()))


class TestWorkspace2Remesh:
    """P0400-REMESHRECORD: a remesh group's record is strict JSON."""

    @staticmethod
    @pytest.fixture(autouse=True, scope="class")
    def _optional_dependencies():
        pytest.importorskip("trimesh")

    @staticmethod
    def test_p0400_remeshrecord_a_group_of_curve_edges_only_records_null(tmp_path):
        """P0400-REMESHRECORD (PFS-2099.014): a group whose every edge is a curve has no edge ratio;
        its record says null, which json.dumps(allow_nan=False) writes, instead of NaN."""
        obj = tmp_path / "one.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng A\nf 1 2 3\n", encoding="utf-8")
        done = refine_group(read_obj(obj), ["A"], set(), 1.0)
        assert done.info["edge_ratio_median"] is None
        json.dumps(done.info, allow_nan=False)
