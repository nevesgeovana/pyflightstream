"""Tier 1: reference rendering, HTML fallback and markdown docs pages."""

from pathlib import Path

import pytest

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
# defined only two of them, the empty cell and the inheritance mark.
#
# THE FIRST VERSION OF THESE THREE TESTS LET EIGHT OF NINE MUTANTS
# THROUGH, and the shape of the failure is worth keeping in view because
# it is subtle and it looks like coverage. Every check was a
# bag-of-fragments search over the WHOLE page: does this word appear
# anywhere, does the first forty characters of that sentence appear
# anywhere. Nothing tied a fragment to its own ROW, so the two columns
# could be swapped between `documented` and `verified` and the page
# would say that verified rests on a manual reading; nothing checked
# past the first sentence, so the rest of a cell could be inverted;
# nothing checked the exception CLASS, so the page could tell a reader
# to catch the wrong one; and the two non-refusing rows were proven by
# an `except Exception` that read an argument refusal as a successful
# emission, so an emitter that could emit NOTHING AT ALL left the file
# green.
#
# The rule these now follow: locate the row, then assert inside it, and
# assert the behaviour positively rather than by the absence of two
# named exceptions.


def _legend_row_markdown(page: str, state: str) -> str:
    """Return the one markdown table row for ``state``."""
    prefix = f"| {state} |"
    rows = [line for line in page.splitlines() if line.startswith(prefix)]
    assert len(rows) == 1, (
        f"expected exactly one markdown legend row for {state!r}, got {len(rows)}"
    )
    return rows[0]


def _legend_row_html(page: str, state: str) -> str:
    """Return the one HTML table row for ``state``, unescaped."""
    import html as _html

    rows = [
        chunk for chunk in page.split("<tr>") if chunk.startswith(f"<td>{_html.escape(state)}</td>")
    ]
    assert len(rows) == 1, f"expected exactly one HTML legend row for {state!r}, got {len(rows)}"
    return _html.unescape(rows[0])


def test_the_legend_names_every_state_the_matrix_can_print():
    """The legend and the Status enum cannot drift apart.

    Two restatements of one list compare only to each other. A sixth
    Status member would previously have shipped with both published
    pages carrying a legend that omits a state the matrix can print, so
    the set is derived from the enum rather than counted.
    """
    from pyflightstream.commands import Status
    from pyflightstream.reference import _STATUS_LEGEND

    named = {state for state, _rests_on, _emitter in _STATUS_LEGEND}
    assert named == {str(member) for member in Status} | {"empty cell"}, (
        "the legend and Status disagree about which states exist; a state the matrix "
        "can print and the legend does not define is a cell a reader cannot read"
    )


def test_both_rendering_layers_carry_the_same_legend_row_by_row():
    """Two layers, one tuple, and each cell asserted inside its own row.

    `test_no_consumer_of_a_citation_prints_an_empty_one` records the
    time a citation was added and one of the two renderers converted:
    the markdown page was fixed and the HTML fallback printed a probe
    report under a column headed Manual ref.

    Row-scoped and order-checked, because a page-wide search passes just
    as happily when the two columns are swapped between rows, which
    inverts the one claim the second column exists to make.
    """
    from pyflightstream.reference import (
        _STATUS_LEGEND,
        markdown_compatibility_matrix,
        render_html,
    )

    matrix = markdown_compatibility_matrix()
    page = render_html()
    assert "| Cell | What it rests on | What `Script.emit` does |" in matrix, (
        "the markdown legend header changed; the column ORDER is what makes every row "
        "assertion below mean anything"
    )
    assert "<th>Cell</th><th>What it rests on</th><th>What Script.emit does</th>" in page, (
        "the HTML legend header changed or disagrees with the markdown one"
    )
    for state, rests_on, emitter in _STATUS_LEGEND:
        for surface, row in (
            ("markdown", _legend_row_markdown(matrix, state)),
            ("html", _legend_row_html(page, state)),
        ):
            assert rests_on in row, (
                f"the {surface} row for {state!r} does not carry its own 'rests on' text"
            )
            assert emitter in row, (
                f"the {surface} row for {state!r} does not carry its own emitter text"
            )
            assert row.index(rests_on) < row.index(emitter), (
                f"the {surface} row for {state!r} prints its columns in the wrong order, so "
                "the header above it describes the other cell"
            )


def test_the_legend_describes_what_the_emitter_actually_does():
    """The half a reader cannot check, checked against the emitter.

    The expectation is READ OFF THE LEGEND rather than written here
    beside it: an earlier version asserted the behaviour and never
    compared it to the prose, so rewriting the legend to call `broken`
    emitted left the file green. The guard measured the code and
    certified the sentence.

    Both directions are asserted positively. A refusing row must raise
    the class the legend NAMES, since a page telling a reader to catch
    `CommandNotInVersionError` around a broken command is worse than
    silence. A non-refusing row must actually put a line in the script,
    because the absence of two named exceptions is not emission: an
    argument refusal is a different gate and reads the same from
    outside.
    """
    from pyflightstream.commands import CommandNotInVersionError, CommandRegistry, Status
    from pyflightstream.reference import _STATUS_LEGEND
    from pyflightstream.script import BrokenCommandError, CommandArgumentError, Script
    from pyflightstream.versions import known_versions

    registry = CommandRegistry.load()
    versions = {version.canonical: version for version in known_versions()}

    def witness(status, *, argless=False):
        """The alphabetically first (command, build) recording ``status``.

        ``argless`` narrows it to commands that take no required
        argument on that build, which is what lets the non-refusing
        rows be proven by an emission rather than by an absence. The
        refusing rows need no such care: the availability and broken
        gates both run before argument binding, so any witness of those
        statuses refuses whatever its grammar.
        """
        for name, entry in sorted(registry.commands.items()):
            for canonical, row in entry.versions.items():
                if row.status is not status:
                    continue
                if argless:
                    evidence = entry.evidence_in(versions[canonical])
                    args = evidence.record.args or entry.args
                    if any(arg.required for arg in args):
                        continue
                return name, canonical
        raise AssertionError(f"no {status} witness in the database, so this guard walks nothing")

    population = {
        str(Status.DOCUMENTED): witness(Status.DOCUMENTED, argless=True),
        str(Status.VERIFIED): witness(Status.VERIFIED, argless=True),
        str(Status.BROKEN): witness(Status.BROKEN),
        str(Status.REMOVED): witness(Status.REMOVED),
        # 26.000 is registered and carries evidence for no command at
        # all, which is what makes it the population of the empty cell.
        "empty cell": ("START_SOLVER", "26.000"),
    }
    legend = {state: emitter for state, _rests_on, emitter in _STATUS_LEGEND}
    assert set(legend) == set(population), (
        f"the legend and this walk disagree about which states exist: {sorted(legend)} "
        f"versus {sorted(population)}"
    )

    for state, (name, canonical) in population.items():
        emitter_text = legend[state]
        says_refused = emitter_text.startswith("REFUSED")
        script = Script(version=canonical)
        before = script.render()
        raised: type[Exception] | None = None
        try:
            script.emit(name)
        except (BrokenCommandError, CommandNotInVersionError, CommandArgumentError) as error:
            raised = type(error)

        if says_refused:
            assert raised in (BrokenCommandError, CommandNotInVersionError), (
                f"the legend says {state!r} is refused and {name} on {canonical} raised "
                f"{raised.__name__ if raised else 'nothing'}"
            )
            assert raised.__name__ in emitter_text, (
                f"the legend tells a reader to expect a different class than {name} on "
                f"{canonical} raises, which is {raised.__name__}. A caller catching the "
                "class the page names would not catch this"
            )
        else:
            assert raised is None, (
                f"the legend says {state!r} is emitted and {name} on {canonical} raised "
                f"{raised.__name__}"
            )
            assert script.render() != before, (
                f"the legend says {state!r} is emitted and {name} on {canonical} put no "
                "line in the script. Not raising is not emitting"
            )


def test_the_legend_names_the_waiver_the_way_a_caller_must_call_it():
    """A legend naming an API that does not exist is worse than no legend.

    The first draft of this one said `Script(allow_broken=True)`, a
    constructor keyword this package does not have; the real waiver is a
    method, per command, and it refuses an empty reason because the
    reason is recorded in the run manifest.
    """
    import inspect

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
    with pytest.raises(CommandArgumentError, match="needs a reason"):
        Script(version="26.100").allow_broken("AIR_ALTITUDE", reason="")


def test_a_state_that_rests_on_a_run_says_so_and_one_that_reads_a_page_says_that():
    """The claim the second column exists to make, tied to the validators.

    The two tests above compare the rendered page against the tuple and
    the tuple's emitter column against the emitter. Neither can see the
    tuple's own prose being WRONG, because both sides move together: a
    mutation swapping the `rests_on` text between `documented` and
    `verified` changes the page and the expectation at once and leaves
    them agreeing. The published page would then say that verified rests
    on a manual reading and documented on a solver probe, which is the
    exact inversion this column was added to prevent.

    So the axis is tied to something outside the prose. `VersionStatus`
    REFUSES `verified` and `broken` without a committed report and
    accepts `documented` and a page-read `removed` without one, and that
    refusal is the model's own statement of which states rest on a run.

    THE LIMIT, stated rather than left to be discovered: this pins ONE
    axis by keyword. Free prose after the load-bearing clause is not
    pinned, so inverting a trailing sentence still passes, and the
    keyword list is a heuristic in the same way the database's own
    measured-claim pattern is. Widening it is
    `PLN-20260809-0700-the-legend-prose-is-pinned-on-one-axis`.
    """
    from pydantic import ValidationError

    from pyflightstream.commands import Status, VersionStatus
    from pyflightstream.reference import _STATUS_LEGEND

    def requires_a_run(status: Status) -> bool:
        """Whether the model refuses this status with no committed report."""
        try:
            VersionStatus(status=status, note="an edition states the withdrawal, SRC-003 p.1")
        except ValidationError:
            return True
        return False

    measured = ("probe", "run ", " ran ", "measured", "observed")
    read = ("manual page", "edition", "documents")

    for state, rests_on, _emitter in _STATUS_LEGEND:
        if state == "empty cell":
            assert "No recorded evidence" in rests_on, (
                "the empty cell must say it is an absence of evidence and not an absence "
                "of the command"
            )
            continue
        # THE FIRST SENTENCE, not the whole cell. Every one of these
        # rows goes on to mention the other kind of evidence somewhere
        # (verified names the states that also rest on a run, documented
        # names the report path), so a search over the whole string is
        # satisfied by that mention and lets the opening clause say the
        # opposite of what the model enforces. Measured: the swap of the
        # two opening clauses passed a whole-string check.
        opening = rests_on.split(". ")[0].lower()
        if requires_a_run(Status(state)):
            assert any(word in opening for word in measured), (
                f"the model refuses {state!r} without a committed report, so it rests on a "
                f"RUN, and the legend opens by saying: {rests_on.split('. ')[0]!r}"
            )
        else:
            assert any(word in opening for word in read), (
                f"the model accepts {state!r} with no report, so it rests on a READING, "
                f"and the legend opens by saying: {rests_on.split('. ')[0]!r}"
            )
