"""Tier 1, 0.28.0 item G30: an OBJ's surface names read from its groups (RPT-078).

THE ITEM: a raw mesh's surfaces are named in ``<stem>.boundaries.toml``, and
until 0.28.0 that list was written by hand for an OBJ as for an STL. The
licensed probe of RPT-078 settled how 26.124 numbers an OBJ's surfaces: one
boundary per ``o`` or ``g`` group that holds a face, named by the group, in the
order the groups appear in the file; an empty group makes none.

WHAT THESE TESTS HOLD, each through the workflow a user runs where there is
one:

* the reader, against the four variants the probe imported, and its refusals
  of the three shapes the probe did not settle, each naming its line and the
  route by hand;
* ``pyfs-matrix plan`` over a workspace whose OBJ has no sidecar writes one
  from the groups, says so on stderr, and then blocks the row on the unit the
  user still owes; with the user's tables added beneath the list, it plans;
* a sidecar that exists is never rewritten, and one whose list disagrees with
  the groups is cited as written with a warning naming both lists, measured
  beside an agreeing control that draws none;
* ``pyfs-matrix inventory`` writes the same file for an OBJ and refuses its
  existing sidecar, ``--overwrite`` or not;
* an STL is unchanged: nothing is written beside it, and its refusals are the
  ones it had.

The new names are reached through the module, not imported by name, so each
test fails on its own assertion on a tree without the item.
"""

from __future__ import annotations

import tomllib
import warnings

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import PlanStatus
from pyflightstream.run.cli import main as pyfs_matrix
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import InputArtifactError
from pyflightstream.workspace import inputs as sidecar_reader
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    geometry_matrix,
    make_library,
    resolve_geometry_row,
    stage_geometry,
)

#: Three vertices and the face over them, which every group below reuses.
TRIANGLE = "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
FACE = "f 1 2 3\n"

#: The four variants RPT-078 imported, by the names it gives them. The names
#: are not in alphabetical order, so an order by name and one by file differ.
O_ONE = "o Wing\n" + TRIANGLE + FACE
O_THREE = "o ZETA\n" + TRIANGLE + FACE + "o ALPHA\n" + FACE + "o MID\n" + FACE
O_G = O_THREE.replace("o ", "g ")
O_EMPTY = "o ZETA\n" + TRIANGLE + FACE + "o EMPTY\no ALPHA\n" + FACE + "o MID\n" + FACE

#: The list the three-group variants make, as the solver numbered it.
THREE = ("ZETA", "ALPHA", "MID")

#: The row names the mesh and nothing else a raw mesh needs.
OBJ_ROW = " / VELOCITY: 30.0 / GEOMETRY: wing.obj"

#: What the user adds beneath the written list: the unit and the trailing edge,
#: by the route every build carries.
USER_TABLES = '\n[import]\nunits = "METER"\n\n[trailing_edges]\ndetect = "auto"\n'


def _plan(tmp_path, workspace, tail=OBJ_ROW):
    return plan_matrix(
        geometry_matrix(tmp_path, tail),
        workspace,
        name="matrix",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


def _disagreements(caught) -> list[str]:
    """The warnings of this item among those caught: a sidecar disagreeing with its groups."""
    return [
        str(item.message)
        for item in caught
        if issubclass(item.category, PyflightstreamWarning) and "RPT-078" in str(item.message)
    ]


# --- the reader --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "names"),
    [(O_ONE, ("Wing",)), (O_THREE, THREE), (O_G, THREE), (O_EMPTY, THREE)],
    ids=["O_ONE", "O_THREE", "O_G", "O_EMPTY"],
)
def test_g30_an_objs_names_are_its_groups_holding_a_face_in_file_order(tmp_path, text, names):
    """RPT-078's four imports: one per group with a face, by the group, in file order."""
    mesh = tmp_path / "wing.obj"
    mesh.write_text(text, encoding="utf-8")
    assert sidecar_reader.obj_boundary_names(mesh) == names


@pytest.mark.parametrize(
    ("text", "needles"),
    [
        ("o ZETA\n" + TRIANGLE + FACE + "g ALPHA\n" + FACE, ("line 6", "line 1", "`g`", "`o`")),
        (
            "o A\n" + TRIANGLE + FACE + "o B\n" + FACE + "o A\n" + FACE,
            ("line 8", "line 1", "'A'", "two places"),
        ),
        (TRIANGLE + FACE + "o Wing\n" + FACE, ("line 4", "before the first")),
        ("o\n" + TRIANGLE + FACE, ("line 1", "no group")),
        ("o Left Wing\n" + TRIANGLE + FACE, ("line 1", "several words")),
        ("o Wing\n" + TRIANGLE, ("no face",)),
    ],
    ids=[
        "o-and-g-mixed",
        "a-group-in-two-places",
        "a-face-before-the-first-group",
        "a-group-with-no-name",
        "a-name-of-two-words",
        "no-face",
    ],
)
def test_g30_what_the_probe_did_not_settle_is_refused_naming_the_line(tmp_path, text, needles):
    """Each shape RPT-078 leaves open is refused by name, pointing at the list by hand."""
    mesh = tmp_path / "wing.obj"
    mesh.write_text(text, encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        sidecar_reader.obj_boundary_names(mesh)
    message = str(caught.value)
    for needle in (*needles, "wing.obj", "wing.boundaries.toml", "by hand"):
        assert needle in message, f"the refusal does not name {needle!r}: {message}"


def test_g30_a_comment_on_a_group_line_is_not_part_of_the_name(tmp_path):
    mesh = tmp_path / "wing.obj"
    mesh.write_text("# exported\no Wing # the main wing\n" + TRIANGLE + FACE, encoding="utf-8")
    assert sidecar_reader.obj_boundary_names(mesh) == ("Wing",)


# --- the plan writes the sidecar -----------------------------------------------------


def test_g30_the_plan_writes_an_objs_sidecar_from_its_groups(tmp_path, capsys):
    """THE EXIT OF G30: an OBJ with no sidecar gets one at plan, and then plans with it.

    The written file holds the list and a header naming the OBJ's sha256 and
    the report, and nothing else, so the plan blocks the row on the unit the
    user still owes, naming the table. With the user's tables appended beneath
    the list, the next plan is READY, the list is the case's inventory, and
    the file is not rewritten.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    mesh = stage_geometry(workspace, "wing.obj", O_THREE.encode())
    sidecar = mesh.with_name("wing.boundaries.toml")

    plan = _plan(tmp_path, workspace)
    assert sidecar.is_file(), "the plan wrote no sidecar beside an OBJ that had none"
    text = sidecar.read_text(encoding="utf-8")
    assert tomllib.loads(text) == {"boundaries": list(THREE)}, text
    assert file_sha256(mesh) in text and "RPT-078" in text, text
    err = capsys.readouterr().err
    assert str(sidecar) in err and "ZETA, ALPHA, MID" in err, err
    [point] = plan.points
    assert point.status is PlanStatus.BLOCKED
    assert "[import]" in point.error and "units" in point.error, point.error

    with sidecar.open("a", encoding="utf-8") as handle:
        handle.write(USER_TABLES)
    completed = sidecar.read_bytes()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = _plan(tmp_path, workspace)
        case = resolve_geometry_row(tmp_path, workspace, OBJ_ROW)
    assert [point.status for point in plan.points] == [PlanStatus.READY], plan.points
    assert case.inventory == THREE and case.inventory_source == "sidecar"
    assert sidecar.read_bytes() == completed, "the plan rewrote a sidecar that existed"
    assert not _disagreements(caught), "an agreeing sidecar drew the disagreement warning"
    assert "read from its groups" not in capsys.readouterr().err, (
        "the plan said it wrote a sidecar that existed"
    )


@pytest.mark.parametrize(
    ("stated", "warned"),
    [(THREE, False), (("ALPHA", "MID", "ZETA"), True), (("ZETA", "ALPHA", "TAIL"), True)],
    ids=["agrees", "another-order", "another-name"],
)
def test_g30_an_existing_sidecar_is_kept_and_a_disagreement_is_warned(tmp_path, stated, warned):
    """Never rewritten; the run cites it as written; a list the groups do not make warns.

    The agreeing control is the one that draws no warning, so the warning is
    about the lists and not about the sidecar existing.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    mesh = stage_geometry(workspace, "wing.obj", O_THREE.encode())
    sidecar = mesh.with_name("wing.boundaries.toml")
    listed = ", ".join(f'"{name}"' for name in stated)
    sidecar.write_text(f"boundaries = [{listed}]\n" + USER_TABLES, encoding="utf-8")
    before = sidecar.read_bytes()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        case = resolve_geometry_row(tmp_path, workspace, OBJ_ROW)
    assert sidecar.read_bytes() == before, "the binding rewrote the user's sidecar"
    assert case.inventory == stated, "the run does not cite the sidecar's list as written"
    found = _disagreements(caught)
    if not warned:
        assert not found, found
        return
    assert len(found) == 1, found
    for needle in (", ".join(stated), "ZETA, ALPHA, MID", "wing.boundaries.toml", "wing.obj"):
        assert needle in found[0], f"the warning does not name {needle!r}: {found[0]}"


def test_g30_a_sidecar_stating_no_boundaries_is_refused_naming_the_groups(tmp_path):
    """A sidecar holding only the user's tables is kept, and the refusal gives the list."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    mesh = stage_geometry(workspace, "wing.obj", O_THREE.encode())
    sidecar = mesh.with_name("wing.boundaries.toml")
    sidecar.write_text(USER_TABLES, encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, OBJ_ROW)
    message = str(caught.value)
    for needle in ("POL 7001", "ZETA, ALPHA, MID", 'boundaries = ["ZETA", "ALPHA", "MID"]'):
        assert needle in message, f"the refusal does not name {needle!r}: {message}"
    assert sidecar.read_text(encoding="utf-8") == USER_TABLES, "the refusal rewrote the file"


def test_g30_an_unsettled_obj_without_a_sidecar_is_refused_at_plan_by_row_and_line(tmp_path):
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    mesh = stage_geometry(workspace, "wing.obj", (TRIANGLE + FACE + "o Wing\n" + FACE).encode())
    with pytest.raises(InputArtifactError) as caught:
        _plan(tmp_path, workspace)
    message = str(caught.value)
    for needle in ("POL 7001", "line 4", "wing.boundaries.toml", "by hand"):
        assert needle in message, f"the refusal does not name {needle!r}: {message}"
    assert not mesh.with_name("wing.boundaries.toml").exists(), "a refused OBJ got a sidecar"


# --- pyfs-matrix inventory ---------------------------------------------------------


def test_g30_inventory_writes_an_objs_sidecar_and_never_rewrites_it(tmp_path, capsys):
    mesh = tmp_path / "wing.obj"
    mesh.write_text(O_EMPTY, encoding="utf-8")
    sidecar = tmp_path / "wing.boundaries.toml"
    assert pyfs_matrix(["inventory", str(mesh)]) == 0
    assert capsys.readouterr().out.strip() == str(sidecar)
    assert tomllib.loads(sidecar.read_text(encoding="utf-8")) == {"boundaries": list(THREE)}
    sidecar.write_text('boundaries = ["edited"]\n' + USER_TABLES, encoding="utf-8")
    before = sidecar.read_bytes()
    for flags in ([], ["--overwrite"]):
        assert pyfs_matrix(["inventory", str(mesh), *flags]) == 2, flags
        err = capsys.readouterr().err
        assert "wing.boundaries.toml" in err and "never rewritten" in err, err
        assert sidecar.read_bytes() == before, f"inventory {flags} rewrote an OBJ's sidecar"


# --- an STL is unchanged -----------------------------------------------------------

_STL_WING = (
    b"solid Wing\n facet normal 0 0 1\n  outer loop\n   vertex 0 0 0\n   vertex 1 0 0\n"
    b"   vertex 0 1 0\n  endloop\n endfacet\nendsolid Wing\n"
)


def test_g30_an_stl_gets_no_sidecar_and_keeps_its_refusals(tmp_path, capsys):
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    mesh = stage_geometry(workspace, "wing.stl", _STL_WING)
    sidecar = mesh.with_name("wing.boundaries.toml")
    plan = _plan(tmp_path, workspace, tail=" / VELOCITY: 30.0 / GEOMETRY: wing.stl")
    assert not sidecar.exists(), "the plan wrote a sidecar beside an STL"
    [point] = plan.points
    assert point.status is PlanStatus.BLOCKED and "[import]" in point.error, point.error
    assert pyfs_matrix(["inventory", str(mesh)]) == 2
    err = capsys.readouterr().err
    assert "no mesh block" in err and "write its surface names by hand" in err, err
    assert not sidecar.exists()
