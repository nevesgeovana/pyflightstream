"""Tier 1: the 0.36.0 review ratchets and parity comparison inventory."""

from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
#: Measured on 2026-10-03, opening 0.36.0 development from v0.35.1.
MYPY_EXEMPT_MODULE_LIMIT = 16


def test_mypy_exempt_module_count_cannot_grow() -> None:
    """P0360-RV-ARCH-1 (NFR-27): the named exemption count may only fall."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    count = 0
    for override in config["tool"]["mypy"]["overrides"]:
        if override.get("ignore_errors") is True:
            modules = override["module"]
            count += 1 if isinstance(modules, str) else len(modules)
    assert count <= MYPY_EXEMPT_MODULE_LIMIT, (
        f"{count} mypy-exempt modules exceed the {MYPY_EXEMPT_MODULE_LIMIT} "
        "measured on 2026-10-03; NFR-27 allows the exemption set only to shrink"
    )


def test_fr180_evidence_cites_the_per_revolution_test() -> None:
    """P0360-RV-VV-3 (FR-180): its evidence names the existing scale-rule test."""
    text = (REPO / "docs/srs/functional-requirements.md").read_text(encoding="utf-8")
    entry = re.search(r'^!!! requirement "FR-180\b.*?(?=^!!! |\Z)', text, re.M | re.S)
    assert entry, "FR-180 is absent from the functional requirements"
    evidence = re.search(r"\bEvidence:\s*(.*?)(?:\n\s*\n|\Z)", entry[0], re.S)
    assert evidence, "FR-180 has no Evidence line"
    path = "tests/tier1_offline/test_goal036_per_revolution.py"
    assert f"`{path}`" in evidence[1], f"FR-180 Evidence must cite {path}"
    assert (REPO / path).is_file(), f"FR-180 evidence file does not exist: {path}"


def test_parity_comparison_lists_the_sorted_base_names() -> None:
    """The comparison inventory includes every base name in sorted order."""
    spec = importlib.util.spec_from_file_location(
        "check_parity_under_test", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = {"zeta.txt": "old\n", "alpha.txt": "same\n"}
    release = {"alpha.txt": "same\n", "zeta.txt": "new\n", "added.txt": "extra\n"}
    block = module.compare_texts("scripts", "script", base, release, set())
    assert block.get("compared") == ["alpha.txt", "zeta.txt"]
