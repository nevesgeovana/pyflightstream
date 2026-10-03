"""The workflows section of the docs site, read as one text.

Until 0.32.0 the whole workspace and workflow guide was one page,
``docs/workspace-and-workflows.md``. The site is organized by task now: that
page is the index of the workflows section and each run type and topic it held
has a page of its own (GEO-066 2.1). A test that guards a sentence of the guide
guards it wherever the sentence lives, so it reads :data:`WORKFLOW_DOCS`, which
stands where the single page stood: ``read_text`` returns every page of the
section, joined, and ``is_file`` is true only when every page exists.
"""

from __future__ import annotations

import json
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"

#: Every page the old single page was split into, and the page it left behind.
WORKFLOW_PAGE_NAMES: tuple[str, ...] = (
    "workspace-and-workflows.md",
    "workflow-run-matrix.md",
    "workflow-steady.md",
    "workflow-unsteady.md",
    "workflow-unsteady-rotor.md",
    "workflow-qsteady-rotor.md",
    "workflow-additional-post.md",
    "workflow-plan-and-cost.md",
    "workflow-input-library.md",
    "workflow-reference-artifact.md",
    "pproc-artifact.md",
    "workflow-row-flow-inputs.md",
    "workflow-row-geometry-motion.md",
    "workflow-builds-and-hpc.md",
)


class WorkflowDocs:
    """A read-only stand-in for the one page the guide used to be."""

    stem = "workspace-and-workflows"
    name = "workspace-and-workflows (all pages of the workflows section)"

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(DOCS / page for page in WORKFLOW_PAGE_NAMES)

    def is_file(self) -> bool:
        return all(path.is_file() for path in self.paths)

    def read_text(self, encoding: str = "utf-8") -> str:
        return "\n\n".join(path.read_text(encoding=encoding) for path in self.paths)


WORKFLOW_DOCS = WorkflowDocs()


def workflow_docs_text() -> str:
    """The text of every page of the workflows section, joined."""
    return WORKFLOW_DOCS.read_text(encoding="utf-8")


class SplitDocs:
    """Read the actual split pages for existing cross-family content guards.

    The frozen heading fixture determines the family inventory; an absent
    page raises rather than silently shrinking the text a guard examines.
    Anchor and individual-page checks live in test_p0360_doc.
    """

    def __init__(self, name: str, pages: tuple[str, ...]):
        self.name = name
        self.stem = name.removesuffix(".md")
        self.paths = tuple(DOCS / page for page in pages)

    def read_text(self, encoding: str = "utf-8") -> str:
        return "\n\n".join(path.read_text(encoding=encoding) for path in self.paths)

    def is_file(self) -> bool:
        return all(path.is_file() for path in self.paths)


_SLUGS = json.loads((Path(__file__).parent / "data/p0360_doc_slugs.json").read_text("utf-8"))
DEFINITION_DOCS = SplitDocs(
    "post-processing definitions (index and families)",
    ("post-processing-definitions.md",)
    + tuple(
        f"definitions/{heading['slug']}.md"
        for heading in _SLUGS["definitions"]
        if heading["level"] == 2 and heading["slug"] != "contents"
    ),
)
MESH_DOCS = SplitDocs(
    "mesh inputs (how-to, reference and example)",
    ("mesh/how-to.md", "mesh/reference.md", "mesh/example.md"),
)
