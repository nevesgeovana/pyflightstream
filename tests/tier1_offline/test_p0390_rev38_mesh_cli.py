"""P0390-REV38 (NFR-45): the mesh command findings of the 0.38.0 review, API-05 and PUSH-IND-ARCH-6.

API-05: the mesh verbs name the file they write ``--out`` as their sibling
commands do: ``pyfs-matrix refine --out DIR`` and ``pyfs-matrix audit-mesh
--out FILE``. The names of 0.38.0, ``--out-dir`` and ``--csv``, are kept as
deprecated aliases: each gives the byte-identical result and warns once.

PUSH-IND-ARCH-6: the mesh command reads the boundaries file's trailing-edge
points entry through the one reader the refinement and the audit use
(``workspace/_refine/_obj.py``), never its own.

Every source is synthetic (tests/p0380_mesh_fixtures.py).
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run import cli
from pyflightstream.workspace import MeshAudit, refine_mesh
from pyflightstream.workspace.sidecars import read_raw_mesh_conditions
from tests.p0380_mesh_fixtures import sheet_with_strips, write_source

REPO = Path(__file__).resolve().parents[2]
CLI_MESH = REPO / "src" / "pyflightstream" / "run" / "_cli_mesh.py"
GT = (("T", "tri", (0.03, 0.04, 0.05)),)
FACTOR_2 = "[families.G]\nfactor = 2.0\n"


def _source(tmp_path: Path, name: str = "src") -> Path:
    return write_source(tmp_path / name, "wing", sheet_with_strips(GT))


def _run(capsys, *argv: str) -> tuple[int, str, str, list[str]]:
    """Run ``pyfs-matrix`` in-process; return the status, stdout, stderr, deprecation warnings."""
    capsys.readouterr()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        code = cli.main(list(argv))
    out = capsys.readouterr()
    said = [str(w.message) for w in caught if "deprecated" in str(w.message)]
    return code, out.out, out.err, said


def _tree(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def test_refine_out_and_its_deprecated_alias_out_dir_write_the_same_level(tmp_path, capsys):
    """P0390-REV38 (NFR-45 R2, API-05): ``refine --out DIR``; ``--out-dir`` is its alias.

    Both write the level folder under the directory they name, file for file
    byte-identical; the alias warns once that it is deprecated and names
    ``--out``, and ``--out`` warns of nothing. Both together are refused
    naming both, exit 2, with nothing written.
    """
    src = _source(tmp_path)
    code, out, _, said = _run(capsys, "refine", str(src), "2", "--out", str(tmp_path / "new"))
    assert code == 0 and said == []
    level = next((tmp_path / "new").iterdir())
    code, _, _, said = _run(capsys, "refine", str(src), "2", "--out-dir", str(tmp_path / "old"))
    assert code == 0
    assert len(said) == 1 and "--out-dir" in said[0] and "--out " in said[0]
    assert _tree(tmp_path / "old" / level.name) == _tree(level)
    assert str(level / "wing_R2.obj") in out
    code, _, err, _ = _run(
        capsys,
        "refine",
        str(src),
        "2",
        "--out",
        str(tmp_path / "a"),
        "--out-dir",
        str(tmp_path / "b"),
    )
    assert code == 2 and "--out-dir" in err and "--out" in err and "Nothing was written." in err
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


def test_audit_mesh_out_and_its_deprecated_alias_csv_write_the_same_figures(tmp_path, capsys):
    """P0390-REV38 (NFR-45 R2, API-05): ``audit-mesh --out FILE``; ``--csv`` is its alias.

    Both write the CSV of the figures byte for byte the same and print the
    same summary; the alias warns once that it is deprecated and names
    ``--out``. A refusal of the file names the option the user typed: the
    same folder is refused as ``--out`` and as ``--csv``. Both together are
    refused naming both, exit 2.
    """
    src = _source(tmp_path)
    code, out_new, _, said = _run(capsys, "audit-mesh", str(src), "--out", str(tmp_path / "n.csv"))
    assert code == 0 and said == []
    code, out_old, _, said = _run(capsys, "audit-mesh", str(src), "--csv", str(tmp_path / "o.csv"))
    assert code == 0
    assert len(said) == 1 and "--csv" in said[0] and "--out " in said[0]
    assert (tmp_path / "n.csv").read_bytes() == (tmp_path / "o.csv").read_bytes()
    assert out_new.replace("n.csv", "o.csv") == out_old
    for flag in ("--out", "--csv"):
        code, _, err, _ = _run(capsys, "audit-mesh", str(src), flag, str(tmp_path))
        assert code == 2 and f"{flag} names a folder" in err
    code, _, err, _ = _run(
        capsys, "audit-mesh", str(src), "--out", str(tmp_path / "x.csv"), "--csv", "y.csv"
    )
    assert code == 2 and "--csv y.csv and --out" in err and "Nothing was written." in err
    assert not (tmp_path / "x.csv").exists()


def test_the_mesh_command_names_no_key_of_the_boundaries_layout():
    """P0390-REV38 (NFR-45 R3, PUSH-IND-ARCH-6): the boundaries layout has one reader.

    The command module imports no TOML reader and holds no key of the
    boundaries file's ``[trailing_edges]`` table (``trailing_edges``,
    ``file``) as a string: it reaches the points entry only through the
    audit's list of the files it reads. Control: the same walk over a planted
    source that reads the table itself reports both.
    """

    def offences(text: str) -> list[str]:
        tree = ast.parse(text)
        found = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value in ("trailing_edges", "file")
        ]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                found += [n for n in names if n == "tomllib"]
        return found

    assert offences(CLI_MESH.read_text(encoding="utf-8")) == []
    planted = 'import tomllib\ndef f(t):\n    return t.get("trailing_edges").get("file")\n'
    assert sorted(offences(planted)) == ["file", "tomllib", "trailing_edges"]


def test_the_command_reads_the_points_entry_through_the_one_reader(tmp_path, capsys):
    """P0390-REV38 (NFR-45 R3, PUSH-IND-ARCH-6): the command asks the refinement's reader.

    A boundaries file naming its points file in a subfolder: the audit's own
    list of the files it reads (``MeshAudit.files_read``, through the
    refinement's reader) names it, and ``audit-mesh --out`` on that file is
    refused as the points file the audit reads, leaving it unchanged; another
    file is accepted (results unchanged). Control: the subfolder file is
    accepted once the boundaries file no longer names it.
    """
    src = _source(tmp_path)
    folder = src.parent / "pts"
    folder.mkdir()
    (src.parent / "wing.te.txt").rename(folder / "edge.txt")
    sidecar = src.with_name("wing.boundaries.toml")
    text = sidecar.read_text(encoding="utf-8").replace('"wing.te.txt"', '"pts/edge.txt"')
    sidecar.write_text(text, encoding="utf-8")
    named = folder / "edge.txt"
    assert ("its trailing-edge points file", named) in MeshAudit.files_read(src)
    before = named.read_bytes()
    code, _, err, _ = _run(capsys, "audit-mesh", str(src), "--out", str(named))
    assert code == 2 and "its trailing-edge points file" in err and named.read_bytes() == before
    code, _, _, _ = _run(capsys, "audit-mesh", str(src), "--out", str(tmp_path / "ok.csv"))
    assert code == 0
    sidecar.write_text(text.replace('file = "pts/edge.txt"', ""), encoding="utf-8")
    assert named not in [path for _, path in MeshAudit.files_read(src)]
    code, _, _, _ = _run(capsys, "audit-mesh", str(src), "--out", str(named))
    assert code == 0 and named.read_bytes() != before


@pytest.mark.parametrize(
    "detect",
    [
        'detect = "everywhere"',
        "detect = { sweep = 60 }",
        "detect = { surfaces = [] }",
        'file = "wing.te.txt"\ndetect = "auto"',
    ],
    ids=["word", "foreign-key", "no-surface", "file-and-detect"],
)
def test_a_detect_shape_the_workflow_refuses_is_refused_by_the_refinement(tmp_path, detect):
    """P0390-REV38 (NFR-45 R3, PUSH-IND-ARCH-6): the refinement reads detect as the workflow does.

    A ``[trailing_edges]`` routing the trailing edge to detection in a shape
    the workflow's reader (``read_raw_mesh_conditions``) refuses is refused
    by the refinement with the same words, before any work: no level folder
    is written. Control: ``detect = "auto"`` refines.
    """
    src = write_source(tmp_path / "src", "wing", sheet_with_strips(GT), refine_toml=FACTOR_2)
    sidecar = src.with_name("wing.boundaries.toml")
    text = sidecar.read_text(encoding="utf-8")
    sidecar.write_text(text.replace('file = "wing.te.txt"', detect), encoding="utf-8")
    with pytest.raises(InputArtifactError) as workflow:
        read_raw_mesh_conditions(sidecar)
    out = tmp_path / "out"
    with pytest.raises(InputArtifactError) as refused:
        refine_mesh(src, out_dir=out)
    assert str(refused.value) == f"{workflow.value} Nothing was written."
    assert not out.exists()
    sidecar.write_text(text.replace('file = "wing.te.txt"', 'detect = "auto"'), encoding="utf-8")
    assert refine_mesh(src, out_dir=out).obj.is_file()
