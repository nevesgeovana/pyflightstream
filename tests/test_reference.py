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


def _registered_sources() -> set[str]:
    """Every source id the registry declares, derived from the registry.

    A literal list of them went stale the moment a build was registered,
    twice, so the population comes from the same place the pages do.
    """
    import re

    from pyflightstream.versions import manual_editions

    return {
        match.group(1)
        for text in manual_editions().values()
        if (match := re.match(r"\s*(SRC-\d{3})", text))
    }


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
    # Honest about what is NOT recorded, which is the property this test
    # is named for. 26.000 carried evidence for nothing until its own
    # manual edition was read on 2026-08-10; it documents 262 commands
    # now and is silent about the other 126, and the row has to say so
    # rather than leaving the reader to subtract.
    #
    # Derived from the registry rather than pinned as a literal: the
    # first version pinned the whole row, so the day evidence arrived it
    # failed for the right reason and had to be retyped, which is how a
    # pinned row becomes a row nobody reads.
    from pyflightstream.versions import known_versions

    version = next(v for v in known_versions() if v.canonical == "26.000")
    recorded = sum(1 for e in registry.commands.values() if e.evidence_in(version) is not None)
    silent = len(registry.commands) - recorded
    assert recorded and silent, (
        "26.000 either records everything or nothing, so this row cannot show the "
        "honest-absence column this test is about"
    )
    edition_cell = [line for line in page.splitlines() if line.startswith("| 26.000 | 26.0 |")]
    assert len(edition_cell) == 1, edition_cell
    row = edition_cell[0]
    assert f"| {silent} |" in row, (
        f"the matrix does not report {silent} commands as unrecorded for 26.000: {row}"
    )
    assert "| 0 |" in row, "no command is inherited by a base release, and the row must say 0"
    assert "SRC-747" in row, (
        f"26.000's manual edition was registered, so the matrix must name it: {row}"
    )
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
    # EVERY REGISTERED EDITION ANSWERS, derived rather than listed. Two
    # of the then four stopped answering when the February and May
    # editions were registered with prose naming their chapter start and
    # no closed range, and the section printed "no gap listing can be
    # computed for it" for both: the published page went quiet on half
    # the manuals in the same change that added the tool for reading
    # them. The assertion is on the source ids rather than on the
    # absence of that sentence, because absence is what it was asserting
    # before, from the other side.
    #
    # The four were hardcoded until 2026-08-10 and covered half the
    # registered set by then, which is the same staleness the sibling
    # guard in test_command_db.py had already been corrected for.
    for source in _registered_sources():
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

    # The cited-page scan sees every registered manual source, derived
    # rather than listed: the pair that used to be named here covered
    # two of eight editions by 2026-08-10.
    cited = _database_cited_pages()
    missing = _registered_sources() - set(cited)
    assert not missing, (
        f"these registered editions contribute no cited page at all: {sorted(missing)}. "
        "An edition nothing cites is one the coverage section can say nothing about"
    )

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
    # The module docstring is dropped, the imports survive. Matched on
    # the import STATEMENT and not on the symbol list after it: this
    # assertion is about what the renderer keeps, and pinning the names
    # made it fail the day the example imported one more of them, which
    # is a change the renderer has no part in.
    assert "Steady polar example: synthetic wing" not in page
    assert "from pyflightstream.script import" in page


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
        # An empty cell is a command with no record for a build. It used
        # to be reachable with any command on 26.000, which carried
        # evidence for nothing; reading that edition on 2026-08-10 gave
        # it 262 commands, so the witness is now a command that arrived
        # AFTER the build: the aeroelastic toolbox is documented from
        # 26.101 and the 25 series predates it.
        "empty cell": ("ASSIGN_AEROELASTIC_SURFACES", "25.000"),
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

    ONE AXIS IS NOT ENOUGH, and a QA pass proved it: `documented` and
    `removed` are BOTH on the read side, so swapping their prose keeps
    each row on its correct side of this test and passes. The published
    matrix then says that `documented` means the build does not carry
    the command and that `removed` means a manual page describes it,
    which is a straight inversion of the two. The per-state
    expectations below close that, and they live OUTSIDE
    `_STATUS_LEGEND` on purpose: an expectation stored beside the prose
    moves with it and pins nothing.

    THE LIMIT, stated rather than left to be discovered: what is pinned
    is the axis plus one distinguishing phrase per state. Free prose
    after that is not pinned, so inverting a trailing sentence still
    passes. Widening it is
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

    # Per state, one phrase that ONLY that state's row can honestly
    # carry. Written here rather than in the tuple so the expectation
    # cannot move with the prose it checks.
    # "does not carry the command" is NOT usable for `removed`: the
    # `broken` row says it too, legitimately, because a build that does
    # not carry a command lands in `broken` when the harness has no
    # `removed` outcome to write. A phrase that two rows may honestly
    # carry cannot tell them apart.
    distinguishing = {
        "documented": "describes the command and its grammar",
        "verified": "observed its effect",
        "broken": "discrepancy between the manual and the solver",
        "removed": "which of three",
        "empty cell": "No recorded evidence",
    }
    assert set(distinguishing) == {state for state, _r, _e in _STATUS_LEGEND}, (
        "a legend row was added or renamed without a distinguishing phrase; add one "
        "rather than dropping the check, or the new row is unpinned"
    )
    for state, rests_on, _emitter in _STATUS_LEGEND:
        phrase = distinguishing[state]
        assert phrase in rests_on, (
            f"the {state!r} row no longer says {phrase!r}, so its cell can no longer be "
            f"told from another state's: {rests_on!r}"
        )
        others = [s for s in distinguishing if s != state]
        wrong = [s for s in others if distinguishing[s] in rests_on]
        assert not wrong, (
            f"the {state!r} row carries the phrase that identifies {wrong}, so the two "
            "rows can be swapped without this test noticing"
        )


def test_the_srs_data_model_table_agrees_with_the_status_legend():
    """A third home for the five definitions, and it had no guard.

    `_STATUS_LEGEND` exists so the compatibility matrix and the offline
    `help()` page cannot carry different legends. `docs/srs/data-model.md`
    restates the same definitions in its own table and is reached by
    neither, so a QA pass could invert two legend rows and leave that
    page saying the opposite with the SRS consistency suite green.

    What is tied here is the distinguishing phrase per status, the same
    one the legend guard uses, rather than the whole sentence: the two
    documents are written for different readers and should not be
    required to word it identically. What they may not do is disagree
    about which status means what.
    """
    from pathlib import Path

    from pyflightstream.reference import _STATUS_LEGEND

    page = (Path(__file__).resolve().parents[1] / "docs" / "srs" / "data-model.md").read_text(
        encoding="utf-8"
    )
    rows = [line for line in page.splitlines() if line.startswith("| ")]
    assert rows, "the data model page carries no table"

    shared = {
        "documented": "manual says so",
        "verified": "proved it works",
        "broken": "proved it fails",
        "removed": "which of three",
    }
    legend = {state: rests_on for state, rests_on, _emitter in _STATUS_LEGEND}
    for status, phrase in shared.items():
        row = [line for line in rows if line.startswith(f"| {status} |")]
        assert len(row) == 1, f"the data model page has {len(row)} rows for {status!r}"
        assert phrase in row[0], (
            f"the data model page no longer says {phrase!r} for {status!r}, so it can "
            f"no longer be told from another status: {row[0]!r}"
        )
        wrong = [s for s, other in shared.items() if s != status and other in row[0]]
        assert not wrong, f"the {status!r} row carries the phrase identifying {wrong}"

    # And the two documents must still agree on the one claim that is
    # word for word shared: what `removed` says about the build.
    assert "which of three" in legend["removed"]
    assert "does not carry the command" in legend["removed"]
    removed_row = next(line for line in rows if line.startswith("| removed |"))
    assert "does not carry the command" in removed_row


def test_the_build_page_counts_the_shared_release_names_it_actually_shares():
    """A derived number on a published page, which replaced a stale literal.

    Changing the predicate from "more than one" to "at least one" makes
    the page say every registered build shares its printed name, and
    nothing noticed: replacing a hardcoded count with an unchecked
    derivation is the same defect one step along.
    """
    from pyflightstream.reference import _sharing_a_printed_name
    from pyflightstream.versions import known_versions

    versions = known_versions()
    shared = {
        version.prints
        for version in versions
        if version.prints is not None
        and sum(1 for other in versions if other.prints == version.prints) > 1
    }
    expected = sum(1 for version in versions if version.prints in shared)
    assert _sharing_a_printed_name(versions) == expected
    # And the figure itself, so the two computations cannot drift into
    # agreeing on a wrong answer: the five 26.1x builds all print 26.1.
    assert _sharing_a_printed_name(versions) == 5
