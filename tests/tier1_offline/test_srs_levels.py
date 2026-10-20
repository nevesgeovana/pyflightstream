"""The SRS level checker: ceilings, fan-out and the L3 traceability (0.43.0 trim).

``scripts/srs_levels.py --json`` is the contract the release goal reads. These tests run it on
the repository and on planted trees, where each planted defect must flip ``ok`` and an
unmutated control must stay ``ok``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "srs_levels.py"
STAGES = "inst dexp spcm phys proc exec recs dred trst wksp oper".split()
HEADER = (
    "| UID | Parent | HID | Level | Status | Verification method | Statement | Rationale "
    "| Derives from | Code | Test |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- "
    "| --- | --- |\n"
)
METHOD = (
    "# Method\n\n| UID | Level | Statement | Rationale | Analogy | Verification | Source |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| NL-INST | L0 | A driver shall know the instrument. | - | - | analysis | - |\n"
    "| NL-INST-1 | L1 | A driver shall bind an identity. | - | - | test | - |\n"
)
TEST_FILE = "def test_one():\n    pass\n"


def _run(root: Path, *extra: str) -> tuple[int, dict]:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--root", str(root), *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, json.loads(done.stdout)


def _row(uid, parent, hid, level, test="tests/test_x.py::test_one"):
    code, test = ("-", "-") if level == "L1" else ("pyflightstream:Thing", test)
    method = "analysis" if level == "L1" else "test"
    statement = "pyflightstream shall record the run identifier."
    return (
        f"| {uid} | {parent} | {hid} | {level} | implemented | {method} | {statement} | - "
        f"| NL-INST | {code} | {test} |\n"
    )


def _tree(
    tmp_path: Path,
    children: int = 3,
    l3_test: str = "tests/test_x.py::test_one",
    uncovered: str = "",
    l3_status: str = "implemented",
) -> Path:
    req = tmp_path / "docs/unpublished/requirements"
    req.mkdir(parents=True)
    for name in [*STAGES, "quality", "retired"]:
        (req / f"{name}.md").write_text(f"# {name}\n\n{HEADER}", encoding="utf-8")
    rows = _row("FR-3000", "-", "INST-1", "L1")
    for i in range(1, children + 1):
        uid = f"FR-{10 + i}"
        test = "-" if uid == uncovered else "tests/test_x.py::test_one"
        rows += _row(uid, "FR-3000", f"INST-1.{i}", "L2", test)
    (req / "inst.md").write_text(f"# Inst\n\n{HEADER}{rows}", encoding="utf-8")
    (tmp_path / "docs/srs").mkdir(parents=True)
    (tmp_path / "docs/srs/numerical-laboratory-method.md").write_text(METHOD, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_x.py").write_text(TEST_FILE, encoding="utf-8")
    (tmp_path / "tests/requirements_l3.csv").write_text(
        "uid,parent,status,statement,code,test,node,rationale\n"
        f"FR-900,FR-11,{l3_status},pyflightstream shall name the key.,,{l3_test},PFS-1.1,\n",
        encoding="utf-8",
    )
    return tmp_path


def test_p0430_levels_contract_on_the_repository():
    """The JSON object carries every contracted key, and the exit status follows ``ok``."""
    status, result = _run(REPO)
    assert set(result) >= {"head", "rows", "counts", "ceilings", "children", "l3", "ok"}
    assert result["ceilings"] == {
        "method_L0": 12,
        "method_L1": 60,
        "inst_L1": 120,
        "inst_L2": 600,
        "total_L0_L2": 800,
        "max_children": 9,
        "mean_children": 5,
    }
    assert set(result["counts"]) == {
        "method_L0",
        "method_L1",
        "inst_L1",
        "inst_L2",
        "quality_L1",
        "quality_L2",
        "total_L0_L2",
    }
    assert set(result["children"]) == {"max", "mean", "over_9"}
    assert set(result["l3"]) >= {"file", "rows", "unresolved", "l2_uncovered"}
    for row in result["rows"]:
        assert set(row) == {"uid", "layer", "level", "parent", "statement", "verification"}
        assert row["layer"] in {"method", "instantiation", "quality"}
        assert row["level"] in {"L0", "L1", "L2"}
    assert len(result["rows"]) == result["counts"]["total_L0_L2"]
    assert status == (0 if result["ok"] else 1)


def test_p0430_the_trimmed_srs_holds_its_ceilings():
    """The approved ceilings hold now; the traceability arms close as 0.43.0 implements."""
    _, result = _run(REPO)
    checks = result["checks"]
    for name in (
        "inst_L1",
        "inst_L2",
        "total_L0_L2",
        "max_children",
        "mean_children",
        "quality_per_characteristic",
        "unique_uids",
    ):
        assert checks[name], name
    assert not result["l3"]["orphans"]
    # every unresolved L3 row and every uncovered L2 is owed work with a planning node
    owed = set(result["l3"]["unresolved"]) | set(result["l3"]["l2_uncovered"])
    assert owed <= set(result["l2_not_implemented"]) | _pending_l3()


def _pending_l3() -> set[str]:
    sys.path.insert(0, str(REPO / "scripts"))
    from _requirements_paths import read_l3

    return {r["uid"] for r in read_l3(REPO) if r["status"] == "pending" and r["node"]}


def test_p0430_levels_checker_imports_only_the_standard_library():
    """The goal checker runs it with no project install: stdlib and repo scripts only."""
    probe = (
        "import sys, runpy; sys.argv = ['srs_levels.py', '--json']; "
        "before = set(sys.modules)\n"
        f"try:\n    runpy.run_path(r'{SCRIPT}', run_name='__main__')\n"
        "except SystemExit:\n    pass\n"
        "extra = {m.split('.')[0] for m in set(sys.modules) - before}\n"
        "local = {'_requirements_paths', 'gen_requirements_index'}\n"
        "bad = sorted(m for m in extra if m not in sys.stdlib_module_names and m not in local)\n"
        "sys.stderr.write('BAD=' + ','.join(bad))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=REPO, check=False
    )
    assert "BAD=" in done.stderr
    assert done.stderr.rsplit("BAD=", 1)[1].strip() == ""


def test_p0430_levels_control_tree_is_ok(tmp_path):
    status, result = _run(_tree(tmp_path))
    assert result["ok"] and status == 0, result["checks"]
    assert result["counts"]["method_L0"] == 1 and result["counts"]["method_L1"] == 1
    assert result["counts"]["inst_L1"] == 1 and result["counts"]["inst_L2"] == 3


@pytest.mark.parametrize("defect", ["missing-test", "uncovered-l2", "ten-children"])
def test_p0430_levels_planted_defects_flip_ok(tmp_path, defect):
    if defect == "missing-test":
        root = _tree(tmp_path, l3_test="tests/test_x.py::test_absent")
        key = "l3_resolved"
    elif defect == "uncovered-l2":
        # FR-11 is the only L2 with an L3 row; without its direct test it stays covered,
        # so the planted gap is FR-12: no direct test and no L3 row.
        root = _tree(tmp_path, uncovered="FR-12")
        key = "l2_covered"
    else:
        root = _tree(tmp_path, children=10)
        key = "max_children"
    status, result = _run(root)
    assert not result["checks"][key] and not result["ok"] and status == 1, result["checks"]


def test_p0430_pending_row_without_test_is_owed_until_the_tag(tmp_path):
    """A pending L3 row whose test does not exist yet is owed work: listed, not failing, until
    ``--release`` (the tag check), where the same row fails the trace."""
    root = _tree(tmp_path, l3_test="tests/test_x.py::test_absent", l3_status="pending")
    status, result = _run(root)
    assert result["l3"]["owed_l3"] == ["FR-900"] and not result["l3"]["unresolved"]
    assert result["ok"] and status == 0, result["checks"]
    status, result = _run(root, "--release")
    assert result["l3"]["unresolved"] == ["FR-900"]
    assert not result["checks"]["l3_resolved"] and status == 1
