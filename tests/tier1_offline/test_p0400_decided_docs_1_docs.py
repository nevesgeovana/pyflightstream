"""Tier 1: pages of the docs site that fell behind the package (decided-docs-1 of 0.40.0).

Pipeline role: documentation currency. Each test reads one page and the
package fact it states, so a page that falls behind again fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

from pyflightstream.versions import known_versions

DOCS = Path(__file__).resolve().parents[2] / "docs"


def _page(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def test_p0400_storage_status_examples_list_max_iter_reached():
    """P0400-STORAGE-STATUS (PFS-2081.05): both status examples name the FR-434 status."""
    text = _page("storage-and-sync.md")
    examples = re.findall(r"^status = \[.*\]$", text, flags=re.MULTILINE)
    assert len(examples) == 2, examples
    for line in examples:
        assert line == 'status = ["CONVERGED", "COMPLETED_MAX_ITER", "MAX_ITER_REACHED"]', line
    assert "unsettled runs" in text


def test_p0400_scope_nreq02_names_the_mesh_commands():
    """P0400-NREQ02 (PFS-2091.001): the narrowing names refine, degenerate and audit-mesh."""
    text = " ".join(_page("srs/scope.md").split())
    assert '"NREQ-02 No geometry generation or meshing (narrowed 2026-10-12)"' in text
    for command in ("pyfs-matrix refine", "pyfs-matrix degenerate", "pyfs-matrix audit-mesh"):
        assert command in text, command
    assert "What stays excluded:" in text


def test_p0400_refine_out_names_the_python_keyword():
    """P0400-REFINE-OUT (PFS-2081.06): the page maps refine --out to out_dir of refine_mesh."""
    text = _page("mesh/reference.md")
    (row,) = [line for line in text.splitlines() if line.startswith("| `--out DIR` | `refine` |")]
    assert "the `out_dir` keyword of `refine_mesh` in Python" in row, row


def test_p0400_architecture_srs_places_the_0390_modules():
    """P0400-ARCH-0390 (PFS-2084.001): the 0.39.0 section places its three modules."""
    text = _page("srs/architecture-srs.md")
    assert "\n## The 0.39.0 additions and their limits\n" in text.replace("\r\n", "\n")
    section = text.split("## The 0.39.0 additions and their limits", 1)[1]
    for module in ("workspace/_settings_file.py", "_remesh_group.py", "_remesh_pairs.py"):
        assert module in section, module
    for imported in ("`_cli`", "`_console`", "`_errors`", "`workspace.builds`"):
        assert imported in section, imported


def test_p0400_builds_table_covers_every_registered_build():
    """P0400-BUILDS-TABLE (PFS-2081.12): the run type by build table names every build."""
    text = _page("workflow-builds-and-hpc.md")
    (header,) = [line for line in text.splitlines() if line.startswith("| run type |")]
    named = set(re.findall(r"\d{2}\.\d{3}", header))
    assert named == {version.canonical for version in known_versions()}, header
