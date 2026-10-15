"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


GENERATOR = REPO / "scripts" / "gen_requirements_index.py"


GOOD_BOX = (
    "!!! requirement \"FR-901 A title <span class='srs-implemented'>implemented</span>\"\n"
    "    *Origin: a fixture. Evidence: tests/tier1_offline/test_requirements_index.py.*\n"
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
