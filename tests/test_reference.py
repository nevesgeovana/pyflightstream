"""Tier 1: reference rendering, HTML fallback and markdown docs pages."""

from pathlib import Path

import pyflightstream
from pyflightstream.commands import CommandRegistry
from pyflightstream.reference import (
    markdown_compatibility_matrix,
    markdown_reference_pages,
    percent_script_markdown,
    render_html,
)


def test_render_html_covers_the_whole_database():
    page = render_html()
    assert page.startswith("<!DOCTYPE html>")
    for name in ("INITIALIZE_SOLVER", "CREATE_NEW_ACTUATOR", "SONIC_VELOCITY"):
        assert f"<code>{name}</code>" in page
    assert "manual_ref" in page


def test_render_html_version_scope_keeps_removed_visible():
    page = render_html("26.120")
    assert "Scope: FlightStream 26.120" in page
    assert "<code>SONIC_VELOCITY</code>" in page
    assert "26.120: removed" in page


def test_render_html_formats_typed_arguments():
    page = render_html()
    assert "variables: enum_list in {" in page
    assert "(optional)" in page
    assert "[deg]" in page


def test_help_writes_the_page_without_opening_a_browser(tmp_path: Path):
    target = pyflightstream.help(path=tmp_path / "reference.html", open_browser=False)
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "pyflightstream command reference" in text
    assert "113 commands" in text or "commands." in text


def test_markdown_pages_cover_every_chapter_and_command():
    registry = CommandRegistry.load()
    pages = markdown_reference_pages()
    chapters = {entry.chapter for entry in registry.commands.values()}
    assert set(pages) == {f"{chapter}.md" for chapter in chapters} | {"index.md", "SUMMARY.md"}
    joined = "\n".join(pages.values())
    for name in registry.commands:
        assert f"## {name}" in joined


def test_markdown_pages_carry_the_navigation_and_evidence():
    pages = markdown_reference_pages()
    assert pages["SUMMARY.md"].startswith("* [Overview](index.md)")
    assert "compatibility.md" in pages["index.md"]
    solver = pages["solver_settings.md"]
    assert '<span class="status-verified">verified</span>' in solver
    assert "reports/compat/" in solver
    assert "SRC-725 p.340" in solver


def test_compatibility_matrix_is_honest_about_missing_evidence():
    page = markdown_compatibility_matrix()
    registry = CommandRegistry.load()
    # Every registered version is a column; 26.000 has no evidence yet,
    # so its summary row reports the whole database as unrecorded, and
    # none of that absence can be inherited (it is a base release, and
    # there is nothing below it to inherit from).
    assert (
        f"| 26.000 | 26.0 | 0 | 0 | 0 | 0 | {len(registry.commands)} | 0 | none registered |"
    ) in page
    assert "SRC-725" in page and "SRC-003" in page
    # Commands link back to their reference entry anchors.
    assert "[SET_SOLVER_STEADY](reference/solver_settings.md#set_solver_steady)" in page


def test_html_reference_carries_the_manual_coverage_section():
    page = render_html()
    assert "Manual coverage" in page
    # Chapter rows carry the page citations from the YAML headers.
    assert "SRC-003 pp.341-343" in page
    # A citation wrapped across header comment lines still reassembles.
    assert "SRC-003 pp.344-346" in page
    # The honesty notes: uncited pages are named, never guessed at.
    assert "not yet cited" in page
    assert "not absent from the manual" in page


def test_markdown_index_carries_the_manual_coverage_section():
    pages = markdown_reference_pages()
    index = pages["index.md"]
    assert "| Chapter | Manual pages | Commands drafted |" in index
    assert "SRC-003 pp.341-343" in index
    assert "## Manual coverage" in index
    assert "not yet cited" in index
    # Every registered edition answers. Two of the four stopped answering
    # when the February and May editions were registered with prose that
    # named their chapter start and no closed range, and the section
    # printed "no gap listing can be computed for it" for both: the
    # published page went quiet on half the manuals in the same change
    # that added the tool for reading them. The assertion is on the four
    # source ids rather than on the absence of that sentence, because
    # absence is what it was asserting before, from the other side.
    for source in ("SRC-741", "SRC-725", "SRC-003", "SRC-740"):
        assert f"{source} scripting reference pages not yet cited" in index, (
            f"the manual-coverage section computes no gap listing for {source}; "
            "an edition registered without a closed page range goes silent here"
        )


def test_coverage_gap_analysis_is_derived_not_guessed():
    from pyflightstream.reference import (
        _coverage_notes,
        _coverage_rows,
        _database_cited_pages,
        _page_spans,
    )

    # Every chapter of the database appears exactly once with its count.
    registry = CommandRegistry.load()
    rows = _coverage_rows()
    assert {row[0] for row in rows} == {entry.chapter for entry in registry.commands.values()}
    assert sum(row[3] for row in rows) == len(registry.commands)

    # The cited-page scan sees both registered manual sources.
    cited = _database_cited_pages()
    assert "SRC-003" in cited and "SRC-725" in cited

    # Span collapsing is exact.
    assert _page_spans({300, 301, 302, 310}) == "300-302, 310"

    # Notes never claim knowledge the database lacks: the closing note
    # states out-of-scope areas are not tracked.
    notes = _coverage_notes()
    assert any("out of scope" in note for note in notes)


def test_percent_script_markdown_renders_the_committed_example():
    source = Path("examples/steady_polar.py").read_text(encoding="utf-8")
    page = percent_script_markdown(source)
    assert page.startswith("# Steady polar")
    assert "```python" in page
    # The module docstring is dropped, the imports survive.
    assert "Steady polar example: synthetic wing" not in page
    assert "from pyflightstream.script import Script" in page


def test_percent_script_markdown_splits_cells():
    source = (
        '# %% [markdown]\n# # Title\n# Prose line.\n# %%\n"""Docstring\nspanning lines."""\nx = 1\n'
    )
    page = percent_script_markdown(source)
    assert "# Title\nProse line." in page
    assert "```python\nx = 1\n```" in page
    assert "Docstring" not in page


# --- the evidence legend ------------------------------------------------------
#
# Added because a reader asked what the five cells mean and the pages
# defined only two of them, the empty cell and the inheritance mark. A
# legend is prose about behaviour, which is the kind of documentation
# that goes stale silently, so these pin it against the behaviour rather
# than against itself.


def test_both_rendering_layers_carry_the_same_legend():
    """Two layers, one legend, because this module has form on that.

    `test_no_consumer_of_a_citation_prints_an_empty_one` records the
    time a citation was added and one of the two renderers converted:
    the markdown page was fixed and the HTML fallback printed a probe
    report under a column headed Manual ref. Both layers read one tuple
    now, and this is what keeps that true.
    """
    from pyflightstream.reference import (
        _STATUS_LEGEND,
        markdown_compatibility_matrix,
        render_html,
    )

    matrix = markdown_compatibility_matrix()
    page = render_html()
    assert len(_STATUS_LEGEND) == 5, "the legend should name four statuses and the empty cell"
    for state, rests_on, emitter in _STATUS_LEGEND:
        for surface, text in (("matrix", matrix), ("html", page)):
            assert state in text, f"the {surface} legend does not name {state!r}"
            # A distinctive fragment rather than the whole sentence: the
            # HTML layer escapes its text, so the two are not identical
            # strings even though they are the same content.
            assert rests_on.split(".")[0][:40] in text, (
                f"the {surface} legend names {state!r} without saying what it rests on"
            )
            assert emitter.split(",")[0] in text, (
                f"the {surface} legend does not say what the emitter does with {state!r}"
            )


def test_the_legend_describes_what_the_emitter_actually_does():
    """The half a reader cannot check, checked.

    The legend says two of the five states are refused and three are
    not, and a reader planning a run acts on that. It is prose about
    behaviour, so it is pinned to the behaviour: each claim is made by
    emitting a real command of that status on a real build.
    """
    from pyflightstream.commands import CommandNotInVersionError, CommandRegistry, Status
    from pyflightstream.reference import _STATUS_LEGEND
    from pyflightstream.script import BrokenCommandError, Script

    registry = CommandRegistry.load()

    def one_with(status):
        for name, entry in sorted(registry.commands.items()):
            for canonical, row in entry.versions.items():
                if row.status is status:
                    return name, canonical
        raise AssertionError(f"no {status} row in the database, so this guard walks nothing")

    #: 26.000 carries no evidence for any command, which is what makes it
    #: the population the empty-cell row describes.
    population = {
        "documented": one_with(Status.DOCUMENTED),
        "verified": one_with(Status.VERIFIED),
        "broken": one_with(Status.BROKEN),
        "removed": one_with(Status.REMOVED),
        "empty cell": ("START_SOLVER", "26.000"),
    }

    # THE EXPECTATION IS READ OFF THE LEGEND, not written here beside it.
    # The first version of this test asserted the behaviour and never
    # compared it to the prose, so rewriting the legend to call `broken`
    # emitted left the whole file green: the guard measured the code and
    # certified the sentence, which is the shape this repository keeps
    # finding in its own guards.
    legend = {state: emitter for state, _rests_on, emitter in _STATUS_LEGEND}
    assert set(legend) == set(population), (
        f"the legend and this walk disagree about which states exist: {sorted(legend)} "
        f"versus {sorted(population)}"
    )

    for state, (name, canonical) in population.items():
        says_refused = legend[state].startswith("REFUSED")
        script = Script(version=canonical)
        try:
            script.emit(name)
            refused = False
        except (BrokenCommandError, CommandNotInVersionError):
            refused = True
        except Exception:  # noqa: BLE001 - an argument refusal is a separate gate
            refused = False
        assert refused == says_refused, (
            f"the legend says {state!r} is "
            f"{'refused' if says_refused else 'emitted'} and {name} on {canonical} was "
            f"{'refused' if refused else 'emitted'}. One of the two is wrong, and the "
            "page is the one a reader acts on"
        )


def test_the_legend_names_the_waiver_the_way_a_caller_must_call_it():
    """A legend naming an API that does not exist is worse than no legend.

    The first draft of this one said `Script(allow_broken=True)`, a
    constructor keyword this package does not have; the real waiver is a
    method, per command, and it refuses an empty reason because the
    reason is recorded in the run manifest.
    """
    import inspect

    import pytest as _pytest

    from pyflightstream.reference import _STATUS_LEGEND
    from pyflightstream.script import CommandArgumentError, Script

    broken = next(row for row in _STATUS_LEGEND if row[0] == "broken")
    assert "Script.allow_broken(name, reason=...)" in broken[2], (
        "the legend describes the waiver in a form a caller cannot type"
    )
    signature = inspect.signature(Script.allow_broken)
    assert list(signature.parameters) == ["self", "name", "reason"], signature
    assert signature.parameters["reason"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "allow_broken" not in inspect.signature(Script.__init__).parameters
    with _pytest.raises(CommandArgumentError, match="needs a reason"):
        Script(version="26.100").allow_broken("AIR_ALTITUDE", reason="")
