"""P0530-LOWS (PFS-2185.10): the low findings of the 0.50.0 push lenses and the 0.50.1 API review.

PUSH-003: the pyproject comment on the pydantic floor says why it is a patch release.
PUSH-004: the importorskip reasons of two tests name the extra they need.
PUSH-005: the extras import names the test conftest skips on are pinned to the ones the
import-isolation test tolerates.
0.50.1 API review: a list variable written alone as an item of an array is spliced into it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pyflightstream.workspace._refine import _config
from tests.tier1_offline.test_import_isolation import _EXTRA_IMPORT_ROOTS

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def test_p0530_push003_the_pydantic_floor_comment_says_why_it_is_a_patch_release():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    comments = "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#"))
    assert "2.10.4" in comments and "ModelWrapValidatorHandler" in comments
    assert '"pydantic>=2.10.4,<3"' in text


@pytest.mark.parametrize("name", ["test_p0340_lf_products.py", "test_excel_file.py"])
def test_p0530_push004_an_importorskip_of_an_extra_names_the_extra(name):
    tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "importorskip"
    ]
    assert calls, name
    for call in calls:
        reasons = [kw.value for kw in call.keywords if kw.arg == "reason"]
        assert reasons and isinstance(reasons[0], ast.Constant), ast.unparse(call)
        assert "optional extra" in str(reasons[0].value), ast.unparse(call)


def test_p0530_push005_the_conftest_extra_modules_are_the_tolerated_extra_roots():
    tree = ast.parse((HERE / "conftest.py").read_text(encoding="utf-8"))
    pinned = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_EXTRA_MODULES"
            for target in node.targets
        ):
            pinned = ast.literal_eval(node.value)
    assert pinned is not None, "conftest.py holds no _EXTRA_MODULES map"
    assert set(pinned.values()) == set(_EXTRA_IMPORT_ROOTS.values())


def _read(tmp_path: Path, text: str, names=("G", "T", "U")) -> dict:
    path = tmp_path / "w.refine.toml"
    path.write_text(text, encoding="utf-8")
    return _config.read_refine_file(path, list(names))


@pytest.mark.requirement("FR-3396")
def test_p0530_api_a_list_variable_alone_in_an_array_is_spliced_in(tmp_path):
    text = (
        "[vars]\nmembers = ['G', 'T']\n"
        "[families.G]\nfactor = 1\n[families.T]\nfactor = 2\n[families.U]\nfactor = 3\n"
        "[components]\nWing = ['${members}', 'U']\n"
    )
    assert _read(tmp_path, text)["components"] == {"Wing": ["G", "T", "U"]}


@pytest.mark.requirement("FR-3396")
def test_p0530_api_a_list_variable_inside_a_list_variable_is_spliced_in(tmp_path):
    text = (
        "[vars]\nhead = ['G']\nmembers = ['${head}', 'T']\n"
        "[families.G]\nfactor = 1\n[families.T]\nfactor = 2\n"
        "[components]\nWing = '${members}'\n"
    )
    assert _read(tmp_path, text)["components"] == {"Wing": ["G", "T"]}
