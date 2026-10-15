"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


GENERATOR = REPO / "scripts" / "gen_requirements_index.py"


def test_p0410_pa2_owned_citations_use_stable_uids() -> None:
    """P0410-PA2: source, tests and authored SRS reject former child citations."""
    paths = subprocess.check_output(
        [
            "git",
            "ls-files",
            "src",
            "tests",
            "docs/srs",
            "docs/unpublished/requirements",
        ],
        cwd=REPO,
        text=True,
    ).splitlines()
    old = re.compile(r"\b(?:FR|NFR)-\d+[a-z]?(?:[ .]+|\s*\)\s*:?\s*)" + r"R\d+\b")
    broken = []
    for relative in paths:
        path = REPO / relative
        if path.suffix not in {".py", ".md", ".json", ".toml", ".yaml", ".yml"}:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if old.search(line):
                broken.append(f"{relative}:{number}")
    assert not broken, broken


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


def test_p0410_pa2_generated_requirement_page_links_resolve() -> None:
    """P0410-PA2: generated pages contain no dangling local Markdown links."""
    generator = _generator()
    pages = generator.requirement_pages(generator.collect(generator.SRS))
    broken = []
    for name, body in pages.items():
        for target in re.findall(r"\]\(([^)]+\.md)(?:#[^)]*)?\)", body):
            if "://" not in target and target not in pages:
                broken.append(f"{name}: {target}")
    assert not broken, broken


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


def test_p0410_srs_uids_survive_reordering_while_hids_follow_the_tree(tmp_path):
    """PFS-2081.37: stable identity is independent of generated placement."""
    page = tmp_path / "functional-requirements.md"
    header = "| UID | Parent | Area | Status | Statement | Code | Test |\n"
    rows = [
        "| FR-1 | - | MESH | implemented | Refine a mesh. | m:refine | t.py::test_refine |\n",
        "| FR-2 | FR-1 | MESH | implemented | Preserve the interface. "
        "| m:join | t.py::test_join |\n",
        "| NFR-1 | - | MESH | implemented | Refuse invalid input. | m:read | t.py::test_read |\n",
        "| FR-3 | - | MESH | retired | Removed route. | - | - |\n",
    ]
    page.write_text(header + "".join(rows), encoding="utf-8")
    generator = _generator()
    first = {r["id"]: r for r in generator.collect(tmp_path)}
    assert set(first) == {"FR-1", "FR-2", "NFR-1", "FR-3"}
    assert first["FR-1"]["hid"] == "MESH-1"
    assert first["FR-2"]["hid"] == "MESH-1.1"
    assert first["NFR-1"]["hid"] == "MESH-2"
    assert first["FR-3"]["hid"] == ""
    pages = generator.requirement_pages(list(first.values()))
    assert '<a id="FR-2"></a>' in pages["mesh.md"]
    assert "FR-2 / MESH-1.1" in pages["mesh.md"]
    assert "FR-3" not in pages["mesh.md"]
    assert "FR-3" in pages["index.md"]
    page.write_text(header + "".join([rows[2], *rows[:2], rows[3]]), encoding="utf-8")
    second = {r["id"]: r for r in generator.collect(tmp_path)}
    assert second["FR-1"]["hid"] == "MESH-2"
    assert second["FR-2"]["hid"] == "MESH-2.1"
    assert {uid: r["text"] for uid, r in first.items()} == {
        uid: r["text"] for uid, r in second.items()
    }


@pytest.mark.parametrize(
    "bad_row",
    [
        "| FR-1 | - | MESH | implemented | Duplicate. | m:f | t.py::test_f |",
        "| FR-2 | FR-99 | MESH | implemented | Missing parent. | m:f | t.py::test_f |",
        "| FR-2 | FR-2 | MESH | implemented | Cycle. | m:f | t.py::test_f |",
        "| FR-2 | - | MESH | implemented | Missing code. | - | t.py::test_f |",
        "| FR-2 | - | MESH | implemented | Missing test. | m:f | - |",
    ],
)
def test_p0410_srs_refuses_ambiguous_or_unanchored_rows(tmp_path, bad_row):
    """PFS-2081.37: incomplete trace links cannot publish as verified claims."""
    (tmp_path / "functional-requirements.md").write_text(
        "| UID | Parent | Area | Status | Statement | Code | Test |\n"
        "| FR-1 | - | MESH | implemented | Refine. | m:f | t.py::test_f |\n" + bad_row + "\n",
        encoding="utf-8",
    )
    generator = _generator()
    with pytest.raises(generator.MalformedRequirementPageError):
        generator.collect(tmp_path)


@pytest.mark.parametrize("broken", ["code", "test", "none"])
def test_p0410_srs_resolves_anchors_before_publishing(tmp_path, monkeypatch, broken):
    """An invented symbol or test must not become a published trace link."""
    srs = tmp_path / "srs"
    srs.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    (src / "sample.py").write_text("def refine():\n    pass\n", encoding="utf-8")
    (tests / "test_sample.py").write_text("def test_refine():\n    assert True\n", encoding="utf-8")
    symbol = "missing" if broken == "code" else "refine"
    test = "test_missing" if broken == "test" else "test_refine"
    (srs / "functional-requirements.md").write_text(
        "| UID | Parent | Area | Status | Statement | Code | Test |\n"
        f"| FR-1 | - | MESH | implemented | Refine. | sample:{symbol} "
        f"| tests/test_sample.py::{test} |\n",
        encoding="utf-8",
    )
    generator = _generator()
    monkeypatch.setattr(generator, "REPO", tmp_path)
    if broken == "none":
        assert generator.build(srs, tests)["requirements"][0]["id"] == "FR-1"
    else:
        with pytest.raises(generator.MalformedRequirementPageError, match="FR-1"):
            generator.build(srs, tests)


def test_p0410_srs_main_writes_and_checks_the_generated_pages(tmp_path, monkeypatch):
    """The command must deliver its pages and detect edits to a generated page."""
    code, err, out = _run_on(GOOD_BOX, monkeypatch, tmp_path)
    assert code == 0, err
    index = out.parent / "requirements" / "index.md"
    assert index.is_file(), "the generator published its JSON but omitted the pages"
    index.write_text("stale\n", encoding="utf-8")
    generator = _generator()
    monkeypatch.setattr(generator, "SRS", tmp_path / "srs")
    monkeypatch.setattr(generator, "OUT", out)
    monkeypatch.setattr(generator, "TESTS", tmp_path / "tests")
    monkeypatch.setattr(generator, "REPO", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gen_requirements_index.py", "--check"])
    assert generator.main() == 1


def test_p0410_pa2_unreadable_saved_actions_warn_with_the_file(tmp_path):
    """P0410-PA2 (FR-538): an unreadable file is named without raising."""
    from pyflightstream.workspace._geometry_clean import saved_action_warning

    source = tmp_path / "unreadable.fsm"
    message = saved_action_warning(source, source.name, ["P7"])
    assert message is not None
    assert source.name in message and "P7" in message
    assert "cannot be read" in message
    assert not source.exists()


@pytest.mark.parametrize("sideslip", [-2.0, 2.0])
def test_p0410_pa2_section_trefftz_names_a_sideslip_skip(sideslip):
    """P0410-PA2 (FR-1018): an inapplicable section analysis writes no result."""
    from types import SimpleNamespace

    from pyflightstream.exceptions import PyflightstreamWarning
    from pyflightstream.post.farfield_products import _variant_a

    context = SimpleNamespace(pproc=SimpleNamespace(farfield=None), skipped={})
    point = SimpleNamespace(
        name="P7",
        state=SimpleNamespace(density_kg_m3=1.2),
        loads=SimpleNamespace(
            freestream_velocity_m_s=30.0, angle_of_attack_deg=0.0, sideslip_deg=sideslip
        ),
    )
    with pytest.warns(PyflightstreamWarning, match="point=P7.*sideslip"):
        assert _variant_a(context, point) == []
    assert len(context.skipped) == 1
    reason = next(iter(context.skipped.values()))
    assert "sideslip" in reason and "variants B and C" in reason
