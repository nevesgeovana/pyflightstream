"""Tier 1: the face count of a geometry is taken with its inventory and carried by the post.

P0340-MESH-FACES (FR-348). The inventory ``<stem>.boundaries.toml`` states
``mesh_faces`` (and ``boundary_faces`` where the reader gives it, and the
``mesh_sha256`` of the file counted) when it is taken, from a saved
simulation or an OBJ; the super file and the unsteady polar carry it as their
LAST column ``MESH_FACES`` for a row whose run recorded that very sha256 for
the geometry, and ``NA`` otherwise. The post never counts a face.

Every fixture is synthetic: a mesh block and an OBJ built here, and the
recorded campaigns the products snapshot already posts.
"""

from __future__ import annotations

import csv
import importlib.util
import tomllib
import warnings
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream._fsm import MESH_MARKER

REPO = Path(__file__).resolve().parents[2]


def _row(values) -> str:
    return ",".join(str(value) for value in values) + ","


def _saved_simulation(path: Path, boundaries, owners, *, corners: int = 3) -> Path:
    """A saved simulation whose mesh block holds one face per entry of ``owners``.

    The layout the reader knows: two header lines, the boundary count and its
    records, the face count, the face ids, the vertices per face, three
    vertex-index rows, seven 0/1 rows of which the seventh names each face's
    boundary, five T/F rows, a 0, and the vertices.
    """
    faces = len(owners)
    body = [MESH_MARKER, "9999", "99", str(len(boundaries))]
    for number, name in enumerate(boundaries, start=2):
        body += [f"{number}, T, T, F", name, ".500,.500,.500"]
    body += [str(faces), _row(range(1, faces + 1)), _row([corners] * faces)]
    body += [_row([slot] * faces) for slot in (1, 2, 3)]
    body += [_row([0] * faces) for _ in range(6)] + [_row(owners)]
    body += [_row(["T"] * faces) for _ in range(5)]
    body += ["0", "3", "0.,1.,0.,", "0.,0.,1.,", "0.,0.,0.,", "$MESH_END$"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


def _records_only(path: Path, boundaries) -> Path:
    """A saved simulation whose block ends after its boundary records."""
    body = [MESH_MARKER, "9999", "99", str(len(boundaries))]
    for number, name in enumerate(boundaries, start=2):
        body += [f"{number}, T, T, F", name, ".500,.500,.500"]
    path.write_text("\r\n".join([*body, "$MESH_END$"]) + "\r\n", encoding="utf-8", newline="")
    return path


def _sidecar(geometry: Path) -> dict:
    return tomllib.loads(geometry.with_name(geometry.stem + ".boundaries.toml").read_text("utf-8"))


def test_the_inventory_of_a_saved_simulation_states_its_faces_and_each_boundarys_fr_348(
    tmp_path,
):
    """P0340-MESH-FACES, FR-348: the count, the count per boundary and the digest are written.

    Controls: a block holding a face that is not a triangle states the total
    alone, and a block that ends after its records is inventoried as before,
    with no count at all.
    """
    requirement = "FR-348"
    from pyflightstream.workspace.inputs import write_inventory

    wing = _saved_simulation(tmp_path / "wing.fsm", ["Body", "Base"], [1, 1, 2, 1, 2])
    write_inventory(wing)
    assert _sidecar(wing) == {
        "file": "wing.fsm",
        "boundaries": ["Body", "Base"],
        "mesh_faces": 5,
        "boundary_faces": [3, 2],
        "mesh_sha256": file_sha256(wing),
    }, requirement

    quads = _saved_simulation(tmp_path / "quads.fsm", ["Body"], [1, 1], corners=4)
    write_inventory(quads)
    stated = _sidecar(quads)
    assert stated["mesh_faces"] == 2 and "boundary_faces" not in stated, requirement

    bare = _records_only(tmp_path / "bare.fsm", ["Body"])
    write_inventory(bare)
    assert _sidecar(bare) == {"file": "bare.fsm", "boundaries": ["Body"]}, requirement


def test_the_inventory_command_counts_each_group_of_an_obj_fr_348(tmp_path, capsys):
    """P0340-MESH-FACES, FR-348: ``pyfs-matrix inventory`` counts an OBJ's faces by group.

    The faces before the first group are a boundary of their own, an empty
    group is none, and each count stands beside the boundary its group makes.
    """
    requirement = "FR-348"
    from pyflightstream.run.cli import main

    mesh = tmp_path / "rotor.obj"
    vertices = "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
    face = "f 1 2 3\n"
    mesh.write_text(
        vertices + face + "g Hub\n" + face * 2 + "g Empty\ng Blade\n" + face, encoding="utf-8"
    )
    assert main(["inventory", str(mesh)]) == 0, capsys.readouterr().err
    stated = _sidecar(mesh)
    assert stated["boundaries"] == ["Boundary-1", "Hub", "Blade"], requirement
    assert stated["mesh_faces"] == 4, requirement
    assert stated["boundary_faces"] == [1, 2, 1], requirement
    assert stated["mesh_sha256"] == file_sha256(mesh), requirement


def test_a_count_whose_file_moved_under_it_is_not_written_fr_348(tmp_path):
    """P0340-MESH-FACES, FR-348: the digests before and after the count must agree.

    The file reads one sha256 before the count and another after it, so no
    line is written: no count, no count per boundary and no digest, which
    leaves the inventory the one written before this requirement (as the
    block that cannot be counted shows in the first test). A count per
    boundary that does not stand one for one beside the listed boundaries is
    left out, the total and the digest kept; the control lists as many as
    were counted, and a steady digest writes the count.
    """
    requirement = "FR-348"
    from pyflightstream.workspace.sidecars import BOUNDARY_FACES_KEY, face_count_lines

    wing = _saved_simulation(tmp_path / "wing.fsm", ["Body", "Base"], [1, 1, 2, 1, 2])
    lines = face_count_lines(wing, 3, obj=False)
    assert lines and not any(BOUNDARY_FACES_KEY in line for line in lines), lines
    assert "mesh_faces = 5" in lines, (requirement, lines)
    assert f'mesh_sha256 = "{file_sha256(wing)}"' in lines, (requirement, lines)
    control = face_count_lines(wing, 2, obj=False)
    assert "boundary_faces = [3, 2]" in control, (requirement, control)

    digests = iter(["a" * 64, "b" * 64])
    assert face_count_lines(wing, 2, obj=False, digest=lambda _path: next(digests)) == []
    steady = face_count_lines(wing, 2, obj=False, digest=lambda _path: "a" * 64)
    assert steady == [*control[:-1], f'mesh_sha256 = "{"a" * 64}"'], (requirement, steady)


def _stamped(monkeypatch, digest: str) -> None:
    """Record every run of a campaign built after this as staging ``wing.fsm`` at ``digest``."""
    from pyflightstream.workspace import CampaignWorkspace

    original = CampaignWorkspace.append_record

    def append(self, record, *args, **kwargs):
        record = record.model_copy(update={"inputs_sha256": {"wing.fsm": digest}})
        return original(self, record, *args, **kwargs)

    monkeypatch.setattr(CampaignWorkspace, "append_record", append)


#: How the products snapshot posts each campaign this module reuses.
_POST_OPTIONS: dict[str, dict] = {
    "superfile": {"matrix_stem": "matriz", "overwrite": True},
    "unsteady_rotor": {},
}


def _posted(workspace, builder: str) -> dict[str, list[list[str]]]:
    """Post a campaign and return its super files and unsteady polars, read as CSV."""
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.post.products import write_campaign_products

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace, **_POST_OPTIONS[builder])
    post = Path(workspace.root) / "post"
    tables = {}
    for path in sorted([*post.rglob("SUPER-*.csv"), *post.rglob("*_uns_avg.csv")]):
        if "archive" in path.relative_to(post).parts:
            continue  # a post again archives the products of the post before it
        with path.open(encoding="utf-8", newline="") as handle:
            tables[path.relative_to(post).as_posix()] = list(csv.reader(handle))
    return tables


def _campaign(tmp_path: Path, monkeypatch, *, digest_of_the_run: str | None, builder: str):
    """One recorded campaign whose geometry ``wing.fsm`` is inventoried with a face count."""
    geometry_bytes = _saved_simulation(
        tmp_path / "source" / "wing.fsm", ["Body", "Base"], [1, 2, 1, 1, 2, 1, 1]
    ).read_bytes()
    _stamped(monkeypatch, digest_of_the_run or file_sha256(tmp_path / "source" / "wing.fsm"))
    if builder == "superfile":
        from tests.tier1_offline.test_post_superfile import _workspace

        workspace = _workspace(tmp_path / "w")
    else:
        from tests.tier1_offline.test_post_products import ROTOR_PLAN, _unsteady_workspace

        workspace = _unsteady_workspace(tmp_path / "w", reductions=ROTOR_PLAN)
    from pyflightstream.workspace.inputs import write_inventory

    geometry = workspace.inputs_dir / "geometries" / "wing.fsm"
    geometry.parent.mkdir(parents=True, exist_ok=True)
    geometry.write_bytes(geometry_bytes)
    write_inventory(geometry)
    return workspace


@pytest.mark.parametrize("builder", ["superfile", "unsteady_rotor"])
def test_the_post_carries_the_inventorys_count_as_the_last_column_fr_348(
    tmp_path, monkeypatch, builder
):
    """P0340-MESH-FACES, FR-348: the count reaches the super file and the unsteady polar, last.

    The run recorded the sha256 the inventory states, so every row carries 7.
    The control is the same campaign whose run recorded another sha256: every
    row carries NA, and every other column and cell of both posts is the same.
    """
    requirement = "FR-348"
    workspace = _campaign(tmp_path / "a", monkeypatch, digest_of_the_run=None, builder=builder)
    carried = _posted(workspace, builder)
    monkeypatch.undo()
    other = _campaign(tmp_path / "b", monkeypatch, digest_of_the_run="0" * 64, builder=builder)
    replaced = _posted(other, builder)
    kinds = {"SUPER" if "SUPER-" in name else "uns_avg" for name in carried}
    assert kinds == ({"SUPER"} if builder == "superfile" else {"uns_avg"}), (requirement, carried)
    assert set(carried) == set(replaced), requirement
    for name, table in carried.items():
        header, *rows = table
        assert header[-1] == "MESH_FACES" and header.count("MESH_FACES") == 1, (name, header)
        assert rows and all(row[-1] == "7" for row in rows), (requirement, name, rows)
        control_header, *control_rows = replaced[name]
        assert control_header == header, (requirement, name)
        assert all(row[-1] == "NA" for row in control_rows), (requirement, name, control_rows)
        assert [row[:-1] for row in control_rows] == [row[:-1] for row in rows], (requirement, name)


def test_the_super_file_keeps_the_column_last_when_a_later_row_brings_one_fr_348(tmp_path):
    """P0340-MESH-FACES, FR-348: the campaign's union of columns still ends with MESH_FACES.

    The second draft's row brings a column the first does not have, after its
    own MESH_FACES; the files carry it before MESH_FACES, and a row without a
    count reads NA.
    """
    requirement = "FR-348"
    from pyflightstream.post.superfile import SuperfileDraft, write_superfiles

    drafts = [
        SuperfileDraft(tmp_path / "SUPER-1_g01.csv", ({"POL": "1", "MESH_FACES": "7"},), {}),
        SuperfileDraft(
            tmp_path / "SUPER-2_g01.csv", ({"POL": "2", "MESH_FACES": "", "CT": "0.1"},), {}
        ),
    ]
    written, _entries, columns = write_superfiles(drafts, target=lambda path: path)
    assert columns == ("POL", "CT", "MESH_FACES"), (requirement, columns)
    first, second = (path.read_text(encoding="utf-8").splitlines() for path in written)
    assert first == ["POL,CT,MESH_FACES", "1,NA,7"], (requirement, first)
    assert second == ["POL,CT,MESH_FACES", "2,0.1,NA"], (requirement, second)


def test_the_post_never_counts_and_a_missing_count_is_na_fr_348(tmp_path, monkeypatch):
    """P0340-MESH-FACES, FR-348: the post reads the count and never counts; no count is NA.

    First the inventory, beside the very bytes the run recorded, its seven
    faces readable, keeps its boundaries and its digest and states no count:
    a post that counted would write 7, and the post writes NA. Then the
    inventory states its count again and the geometry on disk is replaced by
    bytes no face reader can count: a post that counted would fail or write
    NA, and the post writes the inventory's 7 in every row.
    """
    requirement = "FR-348"
    workspace = _campaign(tmp_path, monkeypatch, digest_of_the_run=None, builder="superfile")
    geometry = workspace.inputs_dir / "geometries" / "wing.fsm"
    sidecar = geometry.with_name("wing.boundaries.toml")
    stated, inventory = _sidecar(geometry), sidecar.read_bytes()
    assert stated["mesh_faces"] == 7 and stated["mesh_sha256"] == file_sha256(geometry)
    sidecar.write_text(
        'file = "wing.fsm"\nboundaries = ["Body", "Base"]\n'
        f'mesh_sha256 = "{stated["mesh_sha256"]}"\n',
        encoding="utf-8",
    )
    for cell, mesh in (("NA", geometry.read_bytes()), ("7", b"no mesh block here\n")):
        geometry.write_bytes(mesh)
        tables = _posted(workspace, "superfile")
        assert tables, requirement
        for name, (header, *rows) in tables.items():
            assert header[-1] == "MESH_FACES", (requirement, name)
            assert rows and all(row[-1] == cell for row in rows), (requirement, name, rows)
        sidecar.write_bytes(inventory)


def _parity():
    spec = importlib.util.spec_from_file_location(
        "check_parity_mesh_faces", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_OLD = "POL,ALPHA,CL\n6001,-2.00000,0.10000\n6001,0.00000,0.30000\n"
_NEW = "POL,ALPHA,CL,MESH_FACES\n6001,-2.00000,0.10000,1056\n6001,0.00000,0.30000,NA\n"


def test_the_parity_names_the_column_whole_and_alone_fr_348():
    """P0340-MESH-FACES, FR-348: the parity script names only the appended last column.

    Controls: a second changed cell, the column placed before another, a cell
    that is not NA or a whole number, a line added, and the same column on a
    product the requirement does not name each stay unnamed.
    """
    requirement = "FR-348"
    parity = _parity()
    defined = {requirement}
    entries = [n for n in parity.NAMED_DIFFERENCES if n["requirement"] == requirement]
    assert {n["pattern"] for n in entries} == {"*/SUPER-*.csv", "*_uns_avg.csv"}, entries
    for name in ("matriz/polars/SUPER-6001-M200_g01.csv", "matriz/polars/P7001_AL-020_uns_avg.csv"):
        named = parity.name_difference("post", name, _OLD, _NEW, defined)
        assert named.get("requirement") == requirement, (name, named)
    unnamed = {
        "a second change": _NEW.replace("0.30000,NA", "0.30001,NA"),
        "not last": (
            "POL,ALPHA,MESH_FACES,CL\n6001,-2.00000,1056,0.10000\n6001,0.00000,NA,0.30000\n"
        ),
        "a cell not a count": _NEW.replace(",1056", ",1056.5"),
        "a line added": _NEW + "6001,2.00000,0.50000,NA\n",
        "a legacy field under a comma header": _NEW.replace(",NA\n", "              NA\n"),
    }
    for label, new in unnamed.items():
        named = parity.name_difference(
            "post", "matriz/polars/SUPER-6001_g01.csv", _OLD, new, defined
        )
        assert "requirement" not in named, (requirement, label, named)
    other = parity.name_difference("post", "matriz/polars/P6001_g01.csv", _OLD, _NEW, defined)
    assert "requirement" not in other, (requirement, other)

    # The legacy_polar form of the super file: 16-wide fields, no commas.
    legacy_lines = [
        "".join(cell.rjust(16) for cell in row)
        for row in (("POL", "ALPHA", "CL"), ("6001", "-2.00000", "0.10000"))
    ]
    legacy_old = "\n".join(legacy_lines) + "\n"
    legacy = {
        "the legacy_polar form": ("1056", 16, True),
        "a legacy field not a count": ("1056.5", 16, False),
        "a legacy field of another width": ("1056", 15, False),
    }
    for label, (cell, width, admitted) in legacy.items():
        new = "".join(
            line + extra.rjust(width) + "\n"
            for line, extra in zip(legacy_lines, ("MESH_FACES", cell), strict=True)
        )
        named = parity.name_difference(
            "post", "matriz/polars/SUPER-6001_g01.csv", legacy_old, new, defined
        )
        assert (named.get("requirement") == requirement) is admitted, (label, named)


def test_the_snapshot_admits_the_column_whole_and_alone_fr_348():
    """P0340-MESH-FACES, FR-348: the products snapshot takes off the one column, and only it.

    The stored digests are of the 0.33 products; a super file or unsteady
    polar is compared with the column taken off, and one without the column,
    with a second change, or with a cell that is not a count, is a difference.
    """
    requirement = "FR-348"
    from tests.tier1_offline import test_products_snapshot as snapshot

    old, new = _OLD.encode(), _NEW.encode()
    assert snapshot.without_the_fr348_column(new) == old, requirement
    assert snapshot.without_the_fr348_column(old) is None, requirement
    assert snapshot.without_the_fr348_column(new.replace(b",1056", b",x")) is None, requirement
    index = {
        "m/polars/SUPER-1_g01.csv": snapshot.digests({"x": old})["x"],
        "m/polars/P1_uns_avg.csv": snapshot.digests({"x": old})["x"],
        "m/polars/P1_g01.csv": snapshot.digests({"x": old})["x"],
    }
    files = {
        "m/polars/SUPER-1_g01.csv": new,
        "m/polars/P1_uns_avg.csv": new,
        "m/polars/P1_g01.csv": old,
    }
    assert snapshot.differences(index, files) == [], requirement
    lacking = dict(files, **{"m/polars/SUPER-1_g01.csv": old})
    assert snapshot.differences(index, lacking) == [
        "m/polars/SUPER-1_g01.csv: lacks the MESH_FACES column FR-348 appends"
    ], requirement
    second = dict(files, **{"m/polars/P1_uns_avg.csv": new.replace(b"0.10000", b"0.10001")})
    assert snapshot.differences(index, second) == ["m/polars/P1_uns_avg.csv: bytes differ"]
    unnamed = dict(files, **{"m/polars/P1_g01.csv": new})
    assert snapshot.differences(index, unnamed) == ["m/polars/P1_g01.csv: bytes differ"]


def test_the_definitions_page_and_the_glossary_state_the_column_fr_348():
    """P0340-MESH-FACES, FR-348: the page defines the column; the glossary states the keys.

    The page says where the count comes from (the inventory), that a row
    without it is NA, that the post never counts, and that the column is last
    in both products; the sidecar glossary carries the three inventory keys.
    """
    requirement = "FR-348"
    from pyflightstream.workspace.sidecars import GEOMETRY_SIDECAR_KEYS

    page = (REPO / "docs" / "post-processing-definitions.md").read_text(encoding="utf-8")
    start = page.index("## The mesh face count")
    section = page[start : page.index("\n## ", start + 1)]
    for fact in ("`MESH_FACES`", "`mesh_faces`", "`NA`", "last column", "never", "`mesh_sha256`"):
        assert fact in section, (requirement, fact)
    assert "uns_avg" in section and "super file" in section, requirement
    assert "(#the-mesh-face-count-since-0340)" in page, requirement
    assert {"mesh_faces", "boundary_faces", "mesh_sha256"} <= set(GEOMETRY_SIDECAR_KEYS)
