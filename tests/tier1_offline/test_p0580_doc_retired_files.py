"""The definitions pages name no retired polar file as a current one (DOC-058-02, 03)."""

from __future__ import annotations

import re
from pathlib import Path

DEFINITIONS = Path(__file__).resolve().parents[2] / "docs" / "definitions"
RETIRED = re.compile(r"_rotor\.csv|_uns_avg\.csv|SUPER-")


def test_retired_polar_files_are_named_only_as_retired():
    bad = []
    for page in sorted(DEFINITIONS.rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        for sentence in re.split(r"(?<=[.;:])\s+|\n\s*\n", text):
            if RETIRED.search(sentence) and "retired" not in sentence:
                bad.append((page.name, " ".join(sentence.split())[:90]))
    assert bad == []


def test_changelog_and_upgrading_give_the_renamed_keys_the_same_life():
    root = DEFINITIONS.parents[1]
    for name in ("CHANGELOG.md", "docs/upgrading.md"):
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        stated = [line for line in lines if "superfile_format" in line and "polar_format" in line]
        assert stated, name
        assert all("for one release" in line for line in stated), name


def test_the_index_of_definitions_marks_the_retired_entries():
    index = (DEFINITIONS.parent / "post-processing-definitions.md").read_text(encoding="utf-8")
    for anchor in ("time_average", "per_blade", "the-unsteady-polar"):
        entry = re.search(rf'<a id="{anchor}"></a>\s+(.*)', index)
        assert entry is not None and "(retired" in entry.group(1), anchor


def test_the_mesh_reference_says_why_build_accept_and_from_sidecar_sit_in_pyfs_mesh():
    reference = DEFINITIONS.parent / "mesh" / "reference.md"
    text = " ".join(reference.read_text(encoding="utf-8").split())
    assert (
        "`build`, `accept` and `from-sidecar` sit in `pyfs-mesh` because their output is the mesh "
        "the run uses, though `from-sidecar` reads CAD."
    ) in text
