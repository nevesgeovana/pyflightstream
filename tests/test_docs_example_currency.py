"""Tier 1: the newcomer's page shows what the suite actually executes.

Pipeline role: quality gate on PFS-2025.21. The page it guards,
``docs/workspace-and-workflows.md``, is what a reader who has only
installed the package reads to find out what a workspace is and how a
run matrix becomes results.

WHY A GUARD AND NOT A REVIEW. An example written for a page is true the
day it is written and silently false afterwards. The page's example is
therefore LIFTED from an executed test, and this module holds the two
halves of that lift mechanically: the artefacts on the page are the
repository's own fixture bytes, and the outcome on the page is the one
the named test asserts. Change the behaviour and
``test_run_matrix_executes_and_records_every_point`` goes red; change
the fixture or the run identifiers without moving the page and this
module goes red.

WHY THE BLOCKS DO NOT RUN, stated because a reader will ask. The docs
Sybil executes every ``python`` block that is not marked
``<!-- skip: next -->`` (``conftest.py``), and this example needs a
temporary directory, a synthetic input library and a stub solver
standing in for FlightStream. Marking them keeps them highlighted and
uncollected, and the guarantee the acceptance asks for is carried by the
lift rather than by the block: the SOURCE is an executed test.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "workspace-and-workflows.md"
FIXTURE = REPO / "tests" / "fixtures" / "matrix_registry.fs"
LIFTED_FROM = "test_run_matrix_executes_and_records_every_point"
SOURCE_TEST = REPO / "tests" / "test_matrix_run.py"


def _blocks(text: str) -> list[tuple[str, str]]:
    """Return every fenced block as ``(info string, body)``."""
    found = []
    fence = re.compile(r"^```(.*)$")
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opened = fence.match(lines[index])
        if not opened:
            index += 1
            continue
        info = opened.group(1).strip()
        body: list[str] = []
        index += 1
        while index < len(lines) and not lines[index].startswith("```"):
            body.append(lines[index])
            index += 1
        found.append((info, "\n".join(body)))
        index += 1
    return found


def _normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


def test_the_page_exists_and_is_reachable_from_the_site_nav():
    """A page nobody can navigate to is not published."""
    assert PAGE.is_file(), "the workspace and workflow page does not exist"
    nav = (REPO / "properdocs.yml").read_text(encoding="utf-8")
    assert "workspace-and-workflows.md" in nav, (
        "the page is not in properdocs.yml's nav, which is explicit, so the page would "
        "build and be unreachable"
    )


def test_the_page_explains_the_workspace_before_it_shows_a_signature():
    """Plain language first: the acceptance is about the ORDER.

    A newcomer meets `CampaignWorkspace.init` on the getting-started
    page with no sentence anywhere saying what a workspace is.
    """
    text = PAGE.read_text(encoding="utf-8")
    prose_end = min(
        (text.index(marker) for marker in ("```", "CampaignWorkspace.init") if marker in text),
        default=len(text),
    )
    opening = text[:prose_end]
    assert "workspace" in opening.lower()
    assert len(opening.split()) > 120, (
        "the page reaches a signature or a code block before it has explained, in plain "
        "language, what a workspace is and what it is for"
    )


def test_the_page_cites_the_executed_test_its_example_comes_from():
    """The citation is load-bearing: it is what makes the example rot-proof."""
    text = PAGE.read_text(encoding="utf-8")
    assert LIFTED_FROM in text, "the page does not name the test its example is lifted from"
    assert "tests/test_matrix_run.py" in text
    source = SOURCE_TEST.read_text(encoding="utf-8")
    assert f"def {LIFTED_FROM}(" in source, (
        f"the page cites {LIFTED_FROM}, which no longer exists in tests/test_matrix_run.py; "
        "a citation to a deleted test is worse than no citation, because it reads as "
        "evidence"
    )


def test_the_matrix_on_the_page_is_the_fixture_the_suite_runs():
    """Byte for byte, once line endings are normalized.

    The fixture is stored with CRLF endings and the page is LF, which is
    a difference in how the two files are stored and not in what the
    matrix says, so the comparison normalizes and nothing else.
    """
    blocks = _blocks(PAGE.read_text(encoding="utf-8"))
    matrix_blocks = [body for info, body in blocks if info == 'text title="matrix_registry.fs"']
    assert len(matrix_blocks) == 1, (
        "the page must carry exactly one block titled matrix_registry.fs; found "
        f"{len(matrix_blocks)}"
    )
    assert _normalized(matrix_blocks[0]) == _normalized(FIXTURE.read_text(encoding="utf-8")), (
        "the matrix on the page is not the fixture the suite runs, so a reader copying it "
        "is copying something nothing executes"
    )


def test_the_run_identifiers_on_the_page_are_the_ones_the_test_asserts():
    """The outcome is lifted too, not only the input.

    Extracted from the test's own source rather than restated here, so
    this guard cannot drift from the test either.
    """
    source = SOURCE_TEST.read_text(encoding="utf-8")
    body = source.split(f"def {LIFTED_FROM}(", 1)[1].split("\ndef ", 1)[0]
    identifiers = re.findall(r'"(matrix/sim_\d+/[^"]+)"', body)
    assert identifiers, "the source test asserts no run identifiers; this guard has nothing to lift"
    text = PAGE.read_text(encoding="utf-8")
    missing = [item for item in identifiers if item not in text]
    assert not missing, (
        f"{missing} are asserted by {LIFTED_FROM} and do not appear on the page, so the "
        "page shows a result the suite does not produce"
    )


def test_the_input_library_the_page_shows_is_the_one_the_test_builds(tmp_path):
    """Every artefact the page names is one `make_library` really writes.

    IT RUNS THE BUILDER rather than reading its source, and the change of
    method is the finding. The first version matched the literal
    ``inputs / "references" / "R001.toml"`` spelling out of the source
    text. On 2026-08-19 the ids gained a kind letter and `make_library`
    became a loop writing ``inputs / subdir / f"{code}.toml"``, so the
    pattern matched NOTHING while every artefact was still staged; the
    guard's own non-empty assertion is what refused, which is why it is
    written before the comparison rather than after it.

    Running it measures what lands on disk, so the guard survives any
    rewriting of how the paths are spelled, which is the only thing that
    ever broke it.
    """
    from test_matrix_run import make_library

    workspace = make_library(tmp_path)
    staged = sorted(
        (path.parent.name, path.name)
        for path in workspace.inputs_dir.rglob("*")
        if path.is_file() and path.parent != workspace.inputs_dir
    )
    assert len(staged) >= 5, (
        f"make_library staged only {staged}; a guard that collects nothing passes for "
        "the wrong reason, so the count is asserted before the comparison"
    )
    text = PAGE.read_text(encoding="utf-8")
    for folder, name in staged:
        assert f"{folder}/{name}" in text, (
            f"inputs/{folder}/{name} is staged by make_library and is missing from the "
            "page's picture of the input library"
        )


def test_every_python_block_on_the_page_is_marked_skip():
    """Marked, because none of them can run without a stub solver.

    An unmarked block is EXECUTED by the docs Sybil with the repository
    as the working directory, which would both fail and leave an
    artefact in the repository root.
    """
    text = PAGE.read_text(encoding="utf-8")
    lines = text.splitlines()
    seen = 0
    for index, line in enumerate(lines):
        if line.strip().startswith("```python"):
            seen += 1
            preceding = [item.strip() for item in lines[max(0, index - 3) : index] if item.strip()]
            assert preceding and preceding[-1] == "<!-- skip: next -->", (
                f"the python block opening at line {index + 1} is not marked "
                "<!-- skip: next -->, so Sybil will execute it"
            )
    assert seen >= 2, (
        f"only {seen} python blocks on the page; a page with none would pass this check "
        "for the wrong reason, and the acceptance asks for a worked example"
    )


def test_the_page_says_plainly_what_is_not_built():
    """A page that documents an unbuilt capability is worse than no page.

    There is no workflow OBJECT in this package: what exists is a run
    matrix, a recipe and one call. The page has to say so, because the
    word workflow is used throughout the plan tree for something that
    does not ship.
    """
    text = PAGE.read_text(encoding="utf-8")
    assert "## What does not exist yet" in text, (
        "the page carries no section stating what is not built, so a reader takes every "
        "capability named anywhere near it as shipping"
    )
    tail = text.split("## What does not exist yet", 1)[1]
    assert "workflow" in tail.lower()
    assert "does not" in tail.lower() or "no " in tail.lower()


def test_the_index_no_longer_promises_this_page_as_planned():
    """The bullet that promised exactly this walkthrough is retired."""
    index = (REPO / "docs" / "index.md").read_text(encoding="utf-8")
    assert "workspace-and-workflows.md" in index, (
        "the home page does not link the page a newcomer is supposed to read"
    )
    assert "Campaign tutorial page" not in index, (
        "the Planned next bullet still promises the walkthrough this page delivers"
    )
