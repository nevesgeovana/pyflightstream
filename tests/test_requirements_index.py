"""Tier 1: the published requirement index matches the SRS.

Pipeline role: quality gate over an evidence artifact. The SRS is the
single source of the requirement set; `reports/requirements-index.json`
is its machine-readable rendering, committed because a consumer outside
this repository reads it and cannot run a generator here.

A committed generated file is the exact shape that goes stale quietly,
so it gets the same treatment as the version-bearing metadata: a test
regenerates and compares. The failure this prevents is not
hypothetical. The dashboard that consumes the index carried 32
hand-assembled entries while the SRS held far more, and the gap widened
on the day the Phase 5 batch landed, because a hand-maintained list has
no way to notice that requirements were added.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "scripts" / "gen_requirements_index.py"
INDEX = REPO / "reports" / "requirements-index.json"

#: One well-formed requirement box, as the SRS writes them. The hostile
#: pages below are this shape with ONE thing wrong, so what a refusal
#: reacts to is the defect and not the fixture.
GOOD_BOX = (
    "!!! requirement \"FR-901 A title <span class='srs-implemented'>implemented</span>\"\n"
    "    *Origin: a fixture. Evidence: tests/test_requirements_index.py.*\n"
    "\n"
    "    The statement.\n"
)


def _generator() -> ModuleType:
    """Import the generator by path, since ``scripts`` is not a package."""
    spec = importlib.util.spec_from_file_location("pyflightstream_gen_index", GENERATOR)
    assert spec is not None and spec.loader is not None, f"cannot load {GENERATOR}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_on(page_text: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Run the generator over one hostile page, writing inside ``tmp_path``.

    Returns
    -------
    tuple of (int, str, pathlib.Path)
        The process return code, everything the run wrote to stderr, and
        the output path it was pointed at. The path is inside
        ``tmp_path``, so a run that writes when it should refuse is
        visible here and cannot touch the committed index.
    """
    srs = tmp_path / "srs"
    srs.mkdir()
    (srs / "functional-requirements.md").write_text(page_text, encoding="utf-8")
    out = tmp_path / "requirements-index.json"

    module = _generator()
    monkeypatch.setattr(module, "SRS", srs)
    monkeypatch.setattr(module, "OUT", out)
    monkeypatch.setattr(module, "TESTS", tmp_path / "tests")
    # REPO travels with them: the success message reports the output path
    # relative to it, and leaving it pointing at the real repository makes
    # a green run raise instead of printing.
    monkeypatch.setattr(module, "REPO", tmp_path)
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(sys, "argv", ["gen_requirements_index.py"])

    err = io.StringIO()
    with redirect_stderr(err), redirect_stdout(io.StringIO()):
        code = module.main()
    return code, err.getvalue(), out


def test_the_committed_index_is_what_the_srs_generates() -> None:
    """Regenerating from the SRS reproduces the committed file exactly."""
    done = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
        # Explicit, and identical to the inherited default. The generator
        # needs the ambient environment to find its own interpreter, and
        # the spawn-environment rule is that the call SAYS so rather than
        # letting a runner-injected variable arrive unnoticed.
        env=os.environ.copy(),
    )
    assert done.returncode == 0, (
        "reports/requirements-index.json no longer matches docs/srs. Run "
        "`python scripts/gen_requirements_index.py` and commit the result, "
        f"in the same change that moved the SRS.\n{done.stdout}\n{done.stderr}"
    )


def test_the_index_holds_every_requirement_box_the_srs_declares() -> None:
    """An independent sweep of the SRS finds no requirement the index lost.

    The staleness test above grades the tool with the tool: it asks the
    generator whether its own output is current, so a parsing regression
    is invisible to it. An id shape the generator's regex does not
    expect produces no entry at all, and the box's body is absorbed into
    the previous entry, whose own statement still looks right. Nothing
    goes red; a requirement simply stops existing for the dashboard.

    This sweep uses a different expression and a different reading of
    the same pages, so the two have to agree. Decisions, non-
    requirements and deprecated requirements are excluded here for the
    same reason the generator excludes them.
    """
    declared: set[str] = set()
    for page in sorted((REPO / "docs" / "srs").glob("*.md")):
        for line in page.read_text(encoding="utf-8").splitlines():
            if not line.startswith('!!! requirement "'):
                continue
            if "srs-deprecated" in line:
                continue
            declared.add(line.split('"')[1].split(" ")[0])

    published = {e["id"] for e in json.loads(INDEX.read_text(encoding="utf-8"))["requirements"]}
    assert published == declared, (
        "the index and the SRS disagree about which requirements exist. "
        f"Missing from the index: {sorted(declared - published)}. "
        f"In the index but not the SRS: {sorted(published - declared)}."
    )
    assert len(declared) >= 85, (
        f"the sweep found only {len(declared)} requirement boxes, which is "
        "too few to be the real set; the sweep or the SRS changed shape"
    )


def test_the_index_carries_the_fields_its_consumer_reads() -> None:
    """The three fields are a contract with an external dashboard.

    Renaming one is not a refactor here: it silently empties a column on
    a board this repository cannot see.
    """
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    entries = payload["requirements"]
    assert entries, "the index is empty"
    for entry in entries:
        # A SUPERSET, not an exact match. The three below are the
        # contract and removing one empties a column the dashboard
        # reads; a JSON consumer ignores a key it does not know, so an
        # ADDITION breaks nobody. Pinned as equality until 2026-08-03,
        # when NFR-13 required status, evidence and a verification
        # method to join them (review finding PYFS-020) and the
        # equality would have made the requirement unimplementable.
        assert set(entry) >= {"id", "text", "priority"}, (
            f"{entry.get('id')} carries fields {sorted(entry)}; the consumer "
            "reads at least id, text and priority"
        )
        assert entry["text"], f"{entry['id']} has no statement text"
        assert entry["priority"] in ("M", "D"), (
            f"{entry['id']} has priority {entry['priority']!r}; M is mandatory and D is deferred"
        )

    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "the index repeats an identifier"

    trace = payload["traceability"]
    assert trace["total"] == len(entries)
    assert 0 <= trace["cited_by_a_test"] <= trace["total"]


def test_no_statement_leaks_markup_into_the_index() -> None:
    """The text field is prose, not Markdown.

    A consumer renders it as-is, so a stray link or bold marker shows up
    as literal punctuation on someone else's page.
    """
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    offenders = {
        e["id"]: e["text"]
        for e in payload["requirements"]
        if "](" in e["text"] or "**" in e["text"] or "<span" in e["text"]
    }
    assert not offenders, f"Markdown leaked into the index text: {offenders}"


# --- what a MALFORMED page does, which is the half the tests above miss ---
#
# Every test above reads the committed index or asks the generator whether
# it is current, so all four measure a HEALTHY page. The failure shapes that
# matter to an outside reader do not change which identifiers exist: a lost
# badge published a deferred requirement as mandatory, an unknown token fell
# through to "implemented", and neither moves the id set the completeness
# sweep compares. These four say what the generator does instead: refuse,
# name the page and the id, and write nothing (OPS-2005.09).


def test_a_requirement_box_with_no_badge_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A box with no ``srs-`` badge refuses, naming the page and the id.

    This is the shape with the worst consequence. Until this refusal, a
    box whose badge was lost in an edit defaulted to ``implemented``, so
    a requirement nobody has built was published to an external
    dashboard as done, with a priority of ``M``.
    """
    page = '!!! requirement "FR-901 A title"\n\n    The statement.\n'
    code, err, out = _run_on(page, monkeypatch, tmp_path)
    assert code != 0, f"the generator published a badgeless box and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert "FR-901" in err, err
    assert "badge" in err.lower(), err


def test_a_badge_token_outside_the_known_set_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unknown badge token refuses rather than being published as-is.

    ``srs-implemnted`` is a typo, not a status. Published unread it
    reaches the consumer as a status string no dashboard column knows,
    and priority ``M``, which is the deferred-published-as-mandatory
    failure with an extra step.
    """
    page = GOOD_BOX.replace("srs-implemented", "srs-implemnted")
    code, err, out = _run_on(page, monkeypatch, tmp_path)
    assert code != 0, f"the generator published an unknown badge token and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert "FR-901" in err, err
    assert "implemnted" in err, err


def test_a_repeated_requirement_id_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two boxes with one id refuse, naming the page and the id.

    The index is keyed by id for its consumer. Two boxes sharing one id
    publish two entries a reader cannot tell apart, and whichever sorts
    last silently answers for both.
    """
    second = GOOD_BOX.replace("A title", "The same id, said twice")
    code, err, out = _run_on(GOOD_BOX + "\n" + second, monkeypatch, tmp_path)
    assert code != 0, f"the generator published a repeated id and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert "FR-901" in err, err


def test_a_requirement_header_the_parser_cannot_read_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A header the box pattern misses refuses, naming the line number.

    This is the silent one. A header the pattern does not match produces
    no entry at all, and its body is absorbed into the PREVIOUS box,
    whose own statement still looks right, so the run is green and one
    requirement has simply stopped existing. The id is what failed to
    parse, so the message names the line rather than an id it does not
    have.
    """
    broken = '!!! requirement "FR902 No hyphen in the id"\n\n    The statement.\n'
    code, err, out = _run_on(GOOD_BOX + "\n" + broken, monkeypatch, tmp_path)
    assert code != 0, f"the generator published an unreadable header and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert ":6" in err, f"the message must name the line the header is on: {err}"
    assert "id" in err.lower() and "pars" in err.lower(), err


def test_a_header_whose_identifier_parses_is_refused_without_blaming_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other half of an unreadable header, and it names the right half.

    A header can be unreadable with a perfectly good identifier: no
    title, no closing quote, or no line after it. The refusal still
    fires, because the consequence is the same silent absorption, but
    the message names the identifier as parsed rather than sending the
    author to look at the one part of the line that is correct.
    """
    broken = '!!! requirement "FR-903"\n\n    The statement.\n'
    code, err, out = _run_on(GOOD_BOX + "\n" + broken, monkeypatch, tmp_path)
    assert code != 0, f"the generator published a titleless header and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert ":6" in err, f"the message must name the line the header is on: {err}"
    assert "FR-903" in err, err
    assert "parses" in err, f"the message must not blame the identifier that parsed: {err}"


def test_a_well_formed_page_still_publishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The strict form is not strict about the shape the SRS actually uses.

    A refusal battery that also refuses the healthy page would pass every
    test above and stop the build, so the well-formed fixture is asserted
    to publish rather than assumed to.
    """
    code, err, out = _run_on(GOOD_BOX, monkeypatch, tmp_path)
    assert code == 0, err
    published = json.loads(out.read_text(encoding="utf-8"))["requirements"]
    assert [e["id"] for e in published] == ["FR-901"], published
    assert published[0]["status"] == "implemented"


def test_the_whole_srs_still_publishes_every_requirement_it_did() -> None:
    """The strict generator publishes the live SRS unchanged.

    96 entries on 2026-08-18, from 97 requirement boxes: the deprecated
    one is dropped, as it was before. A floor rather than an equality,
    because the set grows.
    """
    module = _generator()
    entries = module.collect(module.SRS)
    assert len(entries) >= 96, (
        f"the strict generator publishes {len(entries)} requirements, fewer than the "
        "96 measured when the refusals landed; a refusal is dropping a healthy box"
    )
    committed = json.loads(INDEX.read_text(encoding="utf-8"))["requirements"]
    assert [e["id"] for e in entries] == [e["id"] for e in committed], (
        "the strict generator no longer reproduces the committed index"
    )
