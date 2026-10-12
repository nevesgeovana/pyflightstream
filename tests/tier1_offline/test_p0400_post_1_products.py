"""P0400 products-module defects (post-1 lane).

P0400-NOPRIVATEREEXPORT (PFS-2098.003): post.products re-exports no private
name through the explicit ``X as X`` idiom.
P0400-HONESTFANOUT (PFS-2088.015): post.products imports the LF route from its
defining module, so the fan-out guard counts it.
P0400-MANIFESTREBUILD (PFS-2096.019): a truncated products.json is refused by
name, a manifest is still written, and the manifest is replaced whole.
P0400-UNKNOWNMATRIX (PFS-2096.020): an unknown matrix stem is refused before its
folder or its log exists.
"""

from __future__ import annotations

import ast
import json
import warnings
from pathlib import Path

import pytest

import pyflightstream._textio as textio
from pyflightstream._errors import ProductError
from pyflightstream.post import products
from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_post_superfile import _workspace

_SOURCE = ast.parse(Path(products.__file__).read_text(encoding="utf-8"))


@pytest.mark.parametrize((), [pytest.param(id="P0400-NOPRIVATEREEXPORT")])
def test_p0400_noprivatereexport_in_products():
    """P0400-NOPRIVATEREEXPORT: no ``from m import _x as _x`` and no ``import _x as _x``."""
    reexported = [
        alias.name
        for node in _SOURCE.body
        if isinstance(node, ast.ImportFrom | ast.Import)
        for alias in node.names
        if alias.asname is not None and alias.asname == alias.name and alias.asname.startswith("_")
    ]
    assert reexported == [], reexported


@pytest.mark.parametrize((), [pytest.param(id="P0400-HONESTFANOUT")])
def test_p0400_honestfanout_textio_comes_from_its_home():
    """P0400-HONESTFANOUT: _textio is bound from pyflightstream._textio, not through _tables."""
    bound = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name)
        for node in _SOURCE.body
        if isinstance(node, ast.ImportFrom | ast.Import)
        for alias in node.names
        if (alias.asname or alias.name) == "_textio"
        or (isinstance(node, ast.Import) and alias.asname == "_textio")
    }
    assert bound == {"pyflightstream._textio"}, bound


def _posted(workspace) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)


@pytest.mark.parametrize((), [pytest.param(id="P0400-MANIFESTREBUILD")])
def test_p0400_manifestrebuild_a_truncated_manifest_is_named_and_replaced(tmp_path):
    """P0400-MANIFESTREBUILD: the refusal names products.json; a parseable manifest follows."""
    workspace = _workspace(tmp_path)
    _posted(workspace)
    manifest = workspace.products_dir("matriz") / "products.json"
    manifest.write_text(manifest.read_text(encoding="utf-8")[:40], encoding="utf-8")
    with pytest.raises(ProductError, match="products.json does not parse"):
        _posted(workspace)
    written = json.loads(manifest.read_text(encoding="utf-8"))
    assert written["complete"] is False and "does not parse" in written["interrupted"]


@pytest.mark.parametrize((), [pytest.param(id="P0400-MANIFESTREBUILD")])
def test_p0400_manifestrebuild_a_killed_write_leaves_no_truncated_manifest(tmp_path, monkeypatch):
    """P0400-MANIFESTREBUILD: a write killed half way never leaves half a products.json."""
    workspace = _workspace(tmp_path)
    real = textio.write_text

    def killed(path, text, **kwargs):
        if Path(path).name.startswith("products.json"):
            real(path, text[: len(text) // 2], **kwargs)
            raise MemoryError("killed while writing")
        return real(path, text, **kwargs)

    monkeypatch.setattr(textio, "write_text", killed)
    with pytest.raises(MemoryError):
        _posted(workspace)
    manifest = workspace.products_dir("matriz") / "products.json"
    if manifest.exists():
        json.loads(manifest.read_text(encoding="utf-8"))


@pytest.mark.parametrize((), [pytest.param(id="P0400-UNKNOWNMATRIX")])
def test_p0400_unknownmatrix_is_refused_before_anything_is_written(tmp_path):
    """P0400-UNKNOWNMATRIX: a typo in the stem creates no folder and no log."""
    workspace = _workspace(tmp_path)
    with pytest.raises(ProductError, match="no record of matrix 'matirz'"):
        write_campaign_products(workspace, matrix_stem="matirz", overwrite=True)
    assert not workspace.products_dir("matirz").exists()
