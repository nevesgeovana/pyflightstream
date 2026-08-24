"""Tier 1: package front door (version, docstring) and the architecture overview.

Two defects are reproduced and then guarded here.

The first (OPS-2005.12). ``pyflightstream._errors`` imports nothing from
this package and most of the package imports it, and it appeared in none
of the three places the layering is stated: the generated architecture
page, the SRS architecture chapter, and the layout rule in ``CLAUDE.md``.
The shortest reproduction is one line::

    "_errors" in pyflightstream.overview.markdown_overview()   # was False

Worse than the omission, the module that called itself "the lowest layer"
was no longer the lowest, and this file asserted that exact phrase in the
rendered page, so the suite was holding the false sentence in place. The
reword and the assertion could only land together, which is why the
guard below now also asserts the old phrase is ABSENT.

The second (OPS-2006.02.01). The stack is declared as data in
``overview.py`` and restated in prose in four other files with nothing
holding the two equal, so they drift and a reviewer enforces whichever
copy they read. The four guards at the end of this module derive every
restatement from the module data, name the one file that disagrees, and
write out no layer name of their own: a guard that spells the stack a
sixth time would be a fifth copy to drift.
"""

import re
from importlib import metadata
from pathlib import Path

import pyflightstream
from pyflightstream.overview import (
    _BASE_LAYERS,
    _CORE_LAYERS,
    _LAYER_STACK,
    _SECTIONS,
    _SIDE_BRANCHES,
    markdown_overview,
    render_overview_html,
)

REPO = Path(__file__).parents[1]

# The four prose restatements of the layer stack. Module-level and read
# through these names on purpose: the mutation battery that proves these
# guards deny points them at copies in a scratch directory, so nothing
# has to mutate a tracked file in a tree other sessions are working in.
SRS_ARCHITECTURE = REPO / "docs" / "srs" / "architecture-srs.md"
CLAUDE_MD = REPO / "CLAUDE.md"
USER_GUIDE = REPO / "guide" / "pyflightstream_user_guide.tex"

# Markers rather than line numbers, and each is asserted present and
# unique before anything is read from it: an anchor that silently matches
# nothing turns a guard into a green no-op.
FENCE_ANCHOR = "Dependencies flow strictly downward; no module imports upward:"
SIDE_BRANCH_ANCHOR = "Side branches follow the same downward-only rule:"
GUIDE_FRAME_ANCHOR = "\\begin{frame}{The layered architecture}"
GUIDE_LABEL = re.compile(r"\\textbf\{([^}]*)\}")
BACKTICKED = re.compile(r"`([^`]+)`")


def _collapse(text: str) -> str:
    """Collapse every whitespace run to one space.

    Two of the four restatements are wrapped prose, so a comparison that
    respects line breaks would fail on a reflow that changed nothing.
    """
    return " ".join(text.split())


def _after_unique_anchor(text: str, anchor: str, path: Path) -> str:
    """Return the text following an anchor asserted present and unique."""
    found = text.count(anchor)
    assert found == 1, (
        f"{path.name} carries the anchor {anchor!r} {found} times, not once, "
        "so this guard is reading nothing or reading the wrong block; fix the "
        "anchor before trusting the assertion below it"
    )
    return text.split(anchor, 1)[1]


def _declared_table_rows() -> list[str]:
    """Rows of the layer TABLE, derived: names, then the caption."""
    return [_collapse(" ".join(names) + " " + caption) for names, caption in _LAYER_STACK]


def _declared_chain() -> str:
    """The layer CHAIN, derived bottom-up, as the layout rule writes it."""
    return " <- ".join("/".join(names) for names, _ in reversed(_CORE_LAYERS))


def _declared_names() -> set[str]:
    """Every module name the overview declares, core, base and side."""
    names = {name for group, _ in _LAYER_STACK for name in group}
    for group, _ in _SIDE_BRANCHES:
        names.update(part.strip() for part in group.split(","))
    return names


def _srs_fence_rows(text: str) -> list[str]:
    """The rows of the SRS layer fence, whitespace collapsed."""
    fence = _after_unique_anchor(text, FENCE_ANCHOR, SRS_ARCHITECTURE).split("```")[1]
    return [_collapse(line) for line in fence.splitlines() if line.strip()]


def _srs_side_branch_names(text: str) -> set[str]:
    """Every backticked name in the SRS side-branch paragraph."""
    paragraph = _after_unique_anchor(text, SIDE_BRANCH_ANCHOR, SRS_ARCHITECTURE)
    return set(BACKTICKED.findall(paragraph.split("\n\n", 1)[0]))


def _guide_diagram_labels(text: str) -> list[str]:
    """The bold labels of the guide's layer diagram, top row first."""
    frame = _after_unique_anchor(text, GUIDE_FRAME_ANCHOR, USER_GUIDE)
    return GUIDE_LABEL.findall(frame.split("\\draw", 1)[0])


def _page_layer_diagram(page: str) -> str:
    """The layer diagram block of the generated markdown page."""
    return page.split("```text", 1)[1].split("```", 1)[0]


def test_version_comes_from_the_installed_metadata():
    # B1 (PLN-021): the published package must never report the stale
    # hardcoded skeleton version again.
    assert pyflightstream.__version__ != "0.0.1.dev0"
    try:
        installed = metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        assert pyflightstream.__version__ == "0.0.0+uninstalled"
    else:
        assert pyflightstream.__version__ == installed


def test_package_docstring_is_the_didactic_front_door():
    # B2 (PLN-021): no milestone references; the docstring names the
    # pipeline layers and the two offline entry points.
    doc = pyflightstream.__doc__
    assert "ilestone" not in doc
    for layer in (
        "versions",
        "commands",
        "script",
        "results",
        "cases",
        "run",
        "workspace",
    ):
        assert f"``{layer}``" in doc
    assert "help" in doc and "overview" in doc


def test_overview_is_exported_next_to_help():
    # The two offline pages, the pandas-style options quintet
    # (role-review adoption 2026-07-23), and the support-level quartet
    # (FR-49): the question "is my FlightStream version usable here?"
    # is answered at the top of the package rather than by knowing
    # which module to import.
    assert set(pyflightstream.__all__) == {
        "__version__",
        "help",
        "overview",
        "get_option",
        "set_option",
        "reset_option",
        "describe_option",
        "option_context",
        "SupportLevel",
        "support_level",
        "support_table",
        "version_support",
    }
    assert callable(pyflightstream.overview)


def test_render_overview_html_covers_every_subpackage():
    page = render_overview_html()
    assert page.startswith("<!DOCTYPE html>")
    assert "Layer diagram" in page
    for name in _SECTIONS:
        assert f"<code>pyflightstream.{name}</code>" in page
    # Content is the live docstrings, not prose of its own: spot-check
    # one distinctive phrase per end of the pipeline.
    assert "the bottom of the pipeline proper" in page  # versions
    assert "conservation ledgers" in page  # farfield
    # And the phrase this assertion used to pin, which stopped being true
    # the moment the base-exception module was recorded below it
    # (OPS-2005.12). Asserted absent so it cannot come back quietly in a
    # docstring, which is where it lived and where nothing else looks.
    assert "the lowest layer" not in page


def test_overview_sections_match_the_deliverable_list():
    assert _SECTIONS == (
        # First, below the pipeline it supports: the base-exception
        # module imports nothing and every layer may import it
        # (OPS-2005.12). Private, so it is absent from PUBLIC_MODULES
        # below and the comparison there is unaffected.
        "_errors",
        # The second floor module (PFS-2027.03): it imports the base
        # exception and nothing else from the package, and the pipeline
        # imports it. Private, so it is absent from PUBLIC_MODULES too.
        "_atmosphere",
        "versions",
        "commands",
        "script",
        "results",
        "cases",
        "run",
        "workspace",
        "post",
        "qa",
        "fsi",
        "probes",
        "farfield",
        "reference",
        "overview",
        "options",
        "exceptions",
        "extras",
        "testing",
        "support",
        "utils",
    )
    # The literal tuple above enforces "somebody edited this list", not
    # "the list covers the public surface": `extras` landed as a public
    # module and was missing here while this test passed. So the two are
    # compared, and a new public top-level module now fails here.
    from test_public_api import PUBLIC_MODULES

    top_level = {
        name.split(".", 1)[1]
        for name in PUBLIC_MODULES
        if name.count(".") == 1 and not name.endswith(".cli")
    }
    documented = set(_SECTIONS)
    assert top_level - documented == set(), (
        f"public modules {sorted(top_level - documented)} are absent from the "
        "architecture overview, so the published page documents less than the "
        "package offers"
    )


def test_overview_writes_the_page_without_opening_a_browser(tmp_path: Path):
    target = pyflightstream.overview(path=tmp_path / "overview.html", open_browser=False)
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "pyflightstream architecture overview" in text
    assert "downward" in text


def test_markdown_overview_carries_the_diagram_and_sections():
    page = markdown_overview()
    assert page.startswith("# Architecture overview")
    assert "```text" in page
    for name in _SECTIONS:
        assert f"## `pyflightstream.{name}`" in page
    # Sphinx roles are rewritten to plain markdown code spans.
    assert ":mod:" not in page
    assert ":func:" not in page
    assert "`pyflightstream.script.helpers`" in page


def test_the_generated_page_puts_the_base_module_below_the_pipeline():
    # OPS-2005.12: the module every layer imports and that imports none
    # was in no layer authority at all, so the published page described a
    # stack whose floor it never mentioned.
    diagram = _page_layer_diagram(markdown_overview())
    base = _BASE_LAYERS[-1][0][-1]
    lowest_stage = _CORE_LAYERS[-1][0][-1]
    assert base in diagram, (
        f"the generated architecture page never names {base}, which imports "
        "nothing from this package and which most of the package imports, so "
        "the published layer diagram omits its own floor"
    )
    assert diagram.index(base) > diagram.index(lowest_stage), (
        f"the generated architecture page places {base} above {lowest_stage}; "
        "the base exception is below every pipeline stage, not inside them"
    )


def test_the_srs_layer_fence_is_derived_from_the_module_data():
    # OPS-2006.02.01, restatement 1 of 4.
    rows = _srs_fence_rows(SRS_ARCHITECTURE.read_text(encoding="utf-8"))
    assert rows == _declared_table_rows(), (
        f"{SRS_ARCHITECTURE.name} restates the layer stack and disagrees with "
        "the data in pyflightstream/overview.py, which is the single home of "
        "it; edit the module, then this chapter"
    )


def test_the_srs_side_branch_paragraph_names_only_declared_modules():
    # OPS-2006.02.01, restatement 2 of 4. Containment, not equality: the
    # paragraph covers three of the five side rows on purpose, so what
    # this catches is a DEAD name, of the kind the `files` shim left
    # behind when it was removed at v0.4.0.
    mentioned = _srs_side_branch_names(SRS_ARCHITECTURE.read_text(encoding="utf-8"))
    unknown = sorted(mentioned - _declared_names())
    assert not unknown, (
        f"{SRS_ARCHITECTURE.name} names {unknown} as modules of this package "
        "and pyflightstream/overview.py declares no such rows, so the chapter "
        "teaches a module the package does not have"
    )


def test_the_layout_rule_carries_the_derived_layer_chain():
    # OPS-2006.02.01, restatement 3 of 4. Whitespace is collapsed across
    # line wraps first: the rule is wrapped prose and a reflow that
    # changes nothing must not fail here.
    text = _collapse(CLAUDE_MD.read_text(encoding="utf-8"))
    assert _declared_chain() in text, (
        f"{CLAUDE_MD.name} restates the layer chain and disagrees with the "
        "data in pyflightstream/overview.py, which is the single home of it; "
        f"the chain the module declares is: {_declared_chain()}"
    )


def test_the_user_guide_diagram_is_derived_from_the_module_data():
    # OPS-2006.02.01, restatement 4 of 4. Only the bold label is
    # derivable: the guide's captions are written for a reader of the
    # deck and are deliberately not the module's captions.
    labels = _guide_diagram_labels(USER_GUIDE.read_text(encoding="utf-8"))
    assert labels == [" / ".join(names) for names, _ in _CORE_LAYERS], (
        f"{USER_GUIDE.name} draws the layer stack and disagrees with the data "
        "in pyflightstream/overview.py, which is the single home of it; the "
        "guide is not built by CI, so nothing else would have said so"
    )
