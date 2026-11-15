"""Every product folder the post names is in the manifest tree and the catalogue (DOC-058-04)."""

from __future__ import annotations

import re
from pathlib import Path

from pyflightstream.post._manifest_schema import TREE

REPO = Path(__file__).resolve().parents[2]
_CONSTANT = re.compile(r'^([A-Z_]*_DIR)\s*=\s*"([^"]+)"', re.MULTILINE)
#: Folder constants that are not a folder of products: ``TABLES_DIR`` has no user
#: and ``REPORTS_DIR`` holds the measurement reports of a post, not a product table.
NOT_PRODUCT_FOLDERS = {"TABLES_DIR", "REPORTS_DIR"}


def _folders() -> dict[str, str]:
    found: dict[str, str] = {}
    for module in sorted((REPO / "src" / "pyflightstream" / "post").glob("*.py")):
        for name, value in _CONSTANT.findall(module.read_text(encoding="utf-8")):
            if name not in NOT_PRODUCT_FOLDERS:
                found[name] = value
    return found


def test_the_scan_finds_the_product_folders():
    assert {"POLARS_DIR", "SERIES_DIR", "FARFIELD_DIR"} <= set(_folders())


def test_every_product_folder_is_in_the_tree_and_the_catalogue():
    index = (REPO / "docs" / "pproc" / "index.md").read_text(encoding="utf-8")
    missing_tree = sorted(name for name, folder in _folders().items() if folder not in TREE)
    missing_index = sorted(name for name, folder in _folders().items() if f"{folder}/" not in index)
    assert (missing_tree, missing_index) == ([], [])
