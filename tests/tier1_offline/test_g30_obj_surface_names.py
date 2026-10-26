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

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.cli import main as pyfs_matrix
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import InputArtifactError
from pyflightstream.workspace import inputs as sidecar_reader
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    geometry_matrix,
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
OBJ_ROW = " / GEOMETRY: wing.obj"

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
        ("g ZETA\n" + TRIANGLE + FACE + "o ALPHA\n" + FACE, ("line 6", "line 1", "`g`", "`o`")),
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


# --- pyfs-matrix inventory ---------------------------------------------------------


def test_g30_inventory_writes_an_objs_sidecar_and_never_rewrites_it(tmp_path, capsys):
    mesh = tmp_path / "wing.obj"
    mesh.write_text(O_EMPTY, encoding="utf-8")
    sidecar = tmp_path / "wing.obj.boundaries.toml"
    assert pyfs_matrix(["inventory", str(mesh)]) == 0
    assert capsys.readouterr().out.strip() == str(sidecar)
    # The face counts of FR-348 (0.34.0): the empty group holds none and is no boundary.
    assert tomllib.loads(sidecar.read_text(encoding="utf-8")) == {
        "boundaries": list(THREE),
        "mesh_faces": 3,
        "boundary_faces": [1, 1, 1],
        "mesh_sha256": file_sha256(mesh),
    }
    sidecar.write_text('boundaries = ["edited"]\n' + USER_TABLES, encoding="utf-8")
    before = sidecar.read_bytes()
    for flags in ([], ["--overwrite"]):
        assert pyfs_matrix(["inventory", str(mesh), *flags]) == 2, flags
        err = capsys.readouterr().err
        assert "wing.obj.boundaries.toml" in err and "never rewritten" in err, err
        assert sidecar.read_bytes() == before, f"inventory {flags} rewrote an OBJ's sidecar"


# --- an STL is unchanged -----------------------------------------------------------

_STL_WING = (
    b"solid Wing\n facet normal 0 0 1\n  outer loop\n   vertex 0 0 0\n   vertex 1 0 0\n"
    b"   vertex 0 1 0\n  endloop\n endfacet\nendsolid Wing\n"
)
