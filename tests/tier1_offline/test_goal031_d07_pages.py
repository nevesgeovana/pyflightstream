"""Tier 1, 0.27.0 item D07: the definition and workflow pages, each guarantee held by a test.

THE OWNER'S SCOPE OF 2026-09-23, item D07: "the definition and workflow pages:
the final .fsm as a guarantee (G11), the additional post and what a reopened
.fsm gives (G12, with the T09 result), the rates with the measured sense of all
three (G13, with the T11 result). Proof: each sentence of guarantee resolves to
a test."

Three pages carry those guarantees: ``docs/workspace-and-workflows.md`` (G11's
paragraph and G12's section), ``docs/post-processing-definitions.md`` (the
additional post, the definition of record) and ``docs/flight-conditions.md``
(a rotating free stream). This module holds them in four ways:

* :data:`GUARANTEES` names every sentence of guarantee of those sections by a
  phrase of it, with the tests that hold it. The SENTENCE the phrase sits in
  must cite each of those tests by name, in backticks, so a sentence that loses
  its citation, or a citation moved to another sentence, fails here by name;
* every test any of the three pages cites is a test function of the suite, so
  a citation cannot outlive its test;
* the two measured results are stated where the guarantee is: T09 (RPT-062) on
  the workflows page and the definition of record, T11 (RPT-060) with the sense
  of all three rates on the flight-conditions page;
* the documentation site renders each hand-written page AS WRITTEN: every
  fenced block as code, every heading as a heading, every table row inside its
  table. Until D07 it did not. The site's Markdown read a fence whose info
  string carried a title (```` ```text title="matrix_registry.fs" ````) as prose,
  so the fence that closed it OPENED a block, and 286 lines of the workflows
  page, a heading and the reserved-names table among them, rendered as one code
  block; the same shape cut the complete example of the mesh page. A blank line
  inside the reserved-names table cut it in two as well, which the code block
  had hidden. The pages are rendered here with the extensions the site's own
  configuration names, so a page or a configuration that brings either back
  fails here, and not on the published site.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import markdown
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
WORKFLOWS = DOCS / "workspace-and-workflows.md"
DEFINITIONS = DOCS / "post-processing-definitions.md"
FLIGHT = DOCS / "flight-conditions.md"
PAGES = (WORKFLOWS, DEFINITIONS, FLIGHT)

#: EVERY SENTENCE OF GUARANTEE of the D07 sections, by a phrase that sits in it
#: once on its page, and the tests its sentence must cite. A phrase is matched
#: on the page with its whitespace collapsed, as a reader sees it.
GUARANTEES: dict[Path, tuple[tuple[str, tuple[str, ...]], ...]] = {
    WORKFLOWS: (
        # G11, the matrix section's first mention.
        (
            "no final saved simulation of theirs is collected, and plans them as before",
            ("test_g11_a_legacy_row_without_a_saved_simulation_is_warned_at_plan",),
        ),
        # G11, its paragraph.
        (
            "the script saves the solver's state with `SAVEAS`",
            (
                "test_g11_every_workflow_script_saves_its_final_simulation",
                "test_g11_the_save_comes_first_among_the_points_exports",
            ),
        ),
        (
            "hashed in its `outputs_sha256`",
            (
                "test_g11_the_saved_simulation_is_collected_and_hashed",
                "test_g11_a_point_whose_saved_simulation_is_missing_is_recorded_incomplete",
            ),
        ),
        (
            "where each point of a steady sweep saves its own",
            (
                "test_g11_every_point_of_a_steady_sweep_saves_its_own",
                "test_g11_every_workflow_script_saves_its_final_simulation",
                "test_g11_the_saved_simulation_is_collected_and_hashed",
            ),
        ),
        (
            "`[exports] simulation = false` is refused",
            ("test_g11_a_pproc_cannot_switch_the_saved_simulation_off",),
        ),
        (
            "`pyfs-matrix plan` warns naming every `LEGACY` row",
            ("test_g11_a_legacy_row_without_a_saved_simulation_is_warned_at_plan",),
        ),
        (
            "declares its own `outputs` exports exactly those",
            ("test_a_row_declaring_a_loads_table_and_a_log_gets_exactly_those",),
        ),
        # G12, its section.
        (
            "The row runs exactly as it would without it",
            (
                "test_g12_a_row_stating_additional_pproc_plans_ready",
                "test_g12_the_key_changes_no_byte_of_the_run_script",
                "test_g12_the_run_record_never_carries_the_key",
            ),
        ),
        (
            "checks that the copy hashes as the run record says",
            (
                "test_g12_a_copy_that_does_not_hash_as_recorded_fails_and_launches_nothing",
                "test_g12_the_extraction_lands_in_additional_and_is_hashed",
            ),
        ),
        (
            "creates the artifact's section distributions in the frames the run created",
            (
                "test_g12_the_distributions_cite_the_frames_the_run_created",
                "test_g12_the_additional_script_renders_its_committed_bytes",
            ),
        ),
        (
            "never solves, never saves and never writes a probe",
            ("test_g12_the_additional_script_never_solves_and_never_saves",),
        ),
        (
            "an extraction that finds the original changed is recorded failed",
            ("test_g12_an_original_that_changes_during_the_extraction_fails_it",),
        ),
        (
            "Each extraction is recorded in `additional.json`",
            ("test_g12_the_extraction_lands_in_additional_and_is_hashed",),
        ),
        (
            "`runs.json` is never written",
            ("test_g12_the_original_run_record_and_manifest_are_untouched",),
        ),
        (
            "writes the products of every current extraction under",
            ("test_g12_additional_products_are_marked_with_the_pproc",),
        ),
        (
            "(`NO_KEY`",
            ("test_g12_a_row_without_the_key_is_skipped_naming_why",),
        ),
        (
            "(`NO_SAVED_SIMULATION`",
            ("test_g12_a_point_whose_saved_simulation_is_absent_is_skipped_naming_the_path",),
        ),
        (
            "(`HASH_MISMATCH`",
            (
                "test_g12_a_point_whose_saved_simulation_does_not_match_its_record_is_"
                "skipped_naming_both_hashes",
            ),
        ),
        (
            "(`ALREADY_EXTRACTED`",
            ("test_g12_an_extracted_point_is_not_extracted_twice",),
        ),
        (
            "(`BUILD_CHANGED`",
            ("test_g12_a_point_whose_build_changed_is_skipped",),
        ),
        (
            "(`SURFACE_AVERAGED`",
            ("test_g12_a_run_that_averaged_its_surface_in_time_is_skipped",),
        ),
        (
            "(`SCRIPT_DRIFT`",
            (
                "test_g12_a_row_whose_frames_changed_since_the_run_is_skipped",
                "test_g12_a_point_whose_boundaries_moved_since_the_run_is_skipped",
            ),
        ),
        (
            "(`NOT_FINISHED`",
            (
                "test_g12_a_point_still_in_a_queue_is_skipped",
                "test_g12_a_run_a_continuation_replaced_is_skipped_and_the_continuation_extracted",
                "test_g12_a_point_whose_row_is_no_longer_active_is_skipped",
            ),
        ),
        (
            "An id the input library lacks",
            ("test_g12_an_additional_pproc_the_library_lacks_is_refused_at_plan_naming_the_key",),
        ),
        (
            "An additional artifact declaring `[[probes]]` or a `[volume_section]`",
            ("test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062",),
        ),
        (
            "turning on the probe points, the force distribution or a solver plot",
            ("test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_refused",),
        ),
        (
            "The key on a `LEGACY` row",
            ("test_g12_the_key_on_a_legacy_row_is_refused",),
        ),
        (
            "And a row on a build other than 26.124",
            ("test_g12_a_row_on_another_build_is_refused_naming_rpt062",),
        ),
        (
            "`pyfs-matrix plan` warns naming such rows",
            (
                "test_g12_plan_warns_that_an_unsteady_rows_additional_post_is_one_instant",
                "test_g12_an_unsteady_point_is_one_instant_and_says_so",
            ),
        ),
        (
            "`--additional-pproc` needs the matrix",
            (
                "test_g12_the_additional_post_needs_the_matrix",
                "test_g12_a_flag_of_the_additional_post_without_it_is_refused",
            ),
        ),
        (
            "It prints one line per point",
            ("test_g12_the_cli_post_additional_pproc_prints_each_point_and_exits",),
        ),
        (
            "A failed extraction exits 2",
            (
                "test_g12_the_cli_exits_2_on_a_failed_extraction_and_counts_under_strict_"
                "a_skip_that_asks",
            ),
        ),
        (
            "the additional post is refused before anything is written",
            ("test_g12_a_workspace_that_submits_is_refused_naming_local",),
        ),
        (
            "the next `--additional-pproc` extracts the new run",
            ("test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product",),
        ),
    ),
    DEFINITIONS: (
        (
            "extracted from each recorded point's final saved simulation by",
            (
                "test_g12_the_extraction_lands_in_additional_and_is_hashed",
                "test_g12_the_additional_script_never_solves_and_never_saves",
            ),
        ),
        (
            "a row on another build stating the key is refused at plan",
            ("test_g12_a_row_on_another_build_is_refused_naming_rpt062",),
        ),
        (
            "are refused in an additional pproc for the same reason",
            (
                "test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062",
                "test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_"
                "refused",
            ),
        ),
        (
            "the sections table's `STEP` is the run's last time step",
            (
                "test_g12_an_unsteady_extractions_sections_table_is_the_last_instant",
                "test_g12_an_unsteady_extraction_is_one_instant_in_the_post_log",
            ),
        ),
        (
            "Every entry of `products.json` for them carries",
            ("test_g12_additional_products_are_marked_with_the_pproc",),
        ),
        (
            "counts the run's rows at the head",
            ("test_g12_the_additional_sections_table_holds_the_run_rows_then_the_additional_ones",),
        ),
        (
            "Only a CURRENT extraction has products",
            ("test_g12_an_extraction_of_another_state_of_the_point_is_stale",),
        ),
        (
            "The next `--additional-pproc` extracts the point again",
            ("test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product",),
        ),
    ),
    FLIGHT: (
        (
            "at the rate the row wrote",
            ("test_goal024_freestream_rotation_a_pitch_rate_turns_the_free_stream",),
        ),
        (
            "so a row can sweep it",
            ("test_goal024_freestream_rotation_a_rate_sweeps_like_any_other_variable",),
        ),
        (
            "A row stating a rate against a reference that declares none",
            (
                "test_goal024_freestream_rotation_a_reference_declaring_no_axes_is_refused_by_name",
                "test_goal024_freestream_rotation_two_non_zero_rates_are_refused_by_name",
                "test_goal024_freestream_rotation_a_case_authored_in_python_is_refused_too",
            ),
        ),
        (
            "Every rate zero, or no rate at all, writes `CONSTANT`",
            (
                "test_goal024_freestream_rotation_every_rate_zero_writes_constant",
                "test_goal024_freestream_rotation_a_row_with_no_rate_at_all_writes_constant",
            ),
        ),
        (
            "a row stating `roll_rate:40` writes",
            (
                "test_goal024_freestream_rotation_each_rate_turns_in_the_flight_mechanics_sense",
                "test_goal024_freestream_rotation_each_rate_takes_its_own_axis",
            ),
        ),
        (
            "The sign per axis is the diagonal of the turn",
            ("test_goal024_freestream_rotation_the_sign_per_rate_is_the_export_to_body_turn",),
        ),
        (
            "The measured sense of all three",
            ("test_the_emitted_rotation_is_the_one_the_probe_recorded_producing_that_rate",),
        ),
        (
            "A `[body_axes]` table that permutes the axes",
            ("test_goal024_freestream_rotation_a_permuted_axis_turns_with_its_rates_sign",),
        ),
    ),
}

#: A cited test: a test name alone in backticks.
_CITED = re.compile(r"`(test_\w+)`")
#: A sentence ends at a full stop followed by a space and a capital, a bold
#: lead, a code span or a bracket; a list item or a table row ends one too.
_SENTENCE_END = re.compile(r"(?<=\.)\s+(?=[A-Z*`(\[])")


def _units(text: str) -> list[str]:
    """Split a page into its sentences, a list item or a table row never crossing another.

    Blocks first (a blank line, a list item and a table row each start one),
    then sentences inside a block, each with its whitespace collapsed.
    """
    blocks: list[list[str]] = [[]]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            blocks.append([])
        elif re.match(r"^(?:[-*] |\d+\. |\|)", stripped):
            blocks.append([stripped])
        else:
            blocks[-1].append(stripped)
    units: list[str] = []
    for block in blocks:
        joined = " ".join(block)
        if joined:
            units += [part for part in _SENTENCE_END.split(joined) if part]
    return units


def uncited(text: str, guarantees: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    """Every guarantee whose phrase is not on the page once, or whose sentence cites too little."""
    units = _units(text)
    problems = []
    for phrase, tests in guarantees:
        holding = [unit for unit in units if phrase in unit]
        if len(holding) != 1:
            problems.append(f"{phrase!r} sits in {len(holding)} sentences, not one")
            continue
        (sentence,) = holding
        missing = [test for test in tests if f"`{test}`" not in sentence]
        if missing:
            problems.append(f"{phrase!r}: its sentence cites none of {missing}: {sentence!r}")
    return problems


def _defined_tests() -> set[str]:
    """Every test function the suite defines, read from the source of every test module."""
    names: set[str] = set()
    for module in (REPO / "tests").rglob("test_*.py"):
        names.update(re.findall(r"^\s*def (test_\w+)\(", module.read_text(encoding="utf-8"), re.M))
    return names


@pytest.mark.parametrize("page", PAGES, ids=[page.stem for page in PAGES])
def test_d07_every_sentence_of_guarantee_cites_the_tests_that_hold_it(page):
    """THE PROOF OF D07: each sentence of guarantee resolves to a test, named in it."""
    problems = uncited(page.read_text(encoding="utf-8"), GUARANTEES[page])
    assert not problems, f"{page.name}:\n  " + "\n  ".join(problems)


def test_d07_every_test_the_pages_cite_is_a_test_of_the_suite():
    """A citation that outlived its test is a guarantee held by nothing."""
    defined = _defined_tests()
    assert len(defined) > 1000, f"only {len(defined)} tests were read; the walk is broken"
    stray = {
        page.name: sorted(set(_CITED.findall(page.read_text(encoding="utf-8"))) - defined)
        for page in PAGES
    }
    stray = {name: tests for name, tests in stray.items() if tests}
    assert not stray, f"the pages cite tests the suite does not define: {stray}"
    cited = {name for page in PAGES for name in _CITED.findall(page.read_text(encoding="utf-8"))}
    registered = {test for entries in GUARANTEES.values() for _, tests in entries for test in tests}
    assert registered <= cited, sorted(registered - cited)


def test_d07_the_citation_check_can_see_a_citation_lost():
    """The witness: the workflows page with one citation removed fails the check, by its phrase."""
    text = WORKFLOWS.read_text(encoding="utf-8")
    assert not uncited(text, GUARANTEES[WORKFLOWS]), "the control is not clean"
    lost = re.sub(
        r"\s\(`test_g12_an_original_that_changes_during_the_extraction_fails_it`\)", "", text
    )
    assert lost != text, "the page no longer reads as expected"
    problems = uncited(lost, GUARANTEES[WORKFLOWS])
    assert len(problems) == 1 and "the original changed" in problems[0], problems
    # And a citation moved into the NEXT sentence is not the sentence's own.
    moved = re.sub(
        r"never writes a probe\s+\((`test_g12_the_additional_script_never_solves_and_never_saves`)"
        r"\)\. The copy is",
        r"never writes a probe. The copy is (\1)",
        text,
    )
    assert moved != text, "the page no longer reads as expected"
    problems = uncited(moved, GUARANTEES[WORKFLOWS])
    assert len(problems) == 1 and "never writes a probe" in problems[0], problems


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_d07_the_workflows_page_and_the_definition_state_the_t09_result():
    """G12 with T09: what a reopened .fsm reproduces, and what it does not, where the post is."""
    workflows = _flat(WORKFLOWS)
    for phrase in (
        "The licensed probe T09 reopened two saved points on 26.124",
        "came back identical",
        "zero until computed again",
        "The probe points off the body did not come back",
        "by up to 4 percent in speed",
        "holds its last instant",
    ):
        assert phrase in workflows, phrase
    definitions = _flat(DEFINITIONS)
    for phrase in ("the licensed probe T09 on 26.124", "by up to 4 percent in speed", "RPT-062"):
        assert phrase in definitions, phrase


def test_d07_the_flight_conditions_page_states_the_measured_sense_of_all_three_rates():
    """G13 with T11: one row per rate, its emitted line for +40 deg/s and the solver's answer."""
    rows = {
        cells[0]: cells
        for line in FLIGHT.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `")
        for cells in [[cell.strip() for cell in line.strip("|").split("|")]]
    }
    expected = {
        "`roll_rate`": ("`ROTATION <frame> X -6.667`", "T11, RPT-060"),
        "`pitch_rate`": ("`ROTATION <frame> Y 6.667`", "RPT-052"),
        "`yaw_rate`": ("`ROTATION <frame> Z -6.667`", "T11, RPT-060"),
    }
    for rate, (line, source) in expected.items():
        assert rate in rows, f"the page's table has no row for {rate}"
        assert rows[rate][2] == line and rows[rate][4] == source, rows[rate]
        assert "positive" in rows[rate][3], rows[rate]


# ------------------------------------------------------------ the rendering --


def site_markdown() -> tuple[list[str], dict[str, dict]]:
    """The Markdown extensions the site builds with, as the builder assembles them.

    Read from ``properdocs.yml``. The builder puts its three built-ins AHEAD of
    the configured ones, and the order matters: a configured fence extension
    replaces the built-in fence reader only when it registers after it.
    """
    config = yaml.safe_load((REPO / "properdocs.yml").read_text(encoding="utf-8"))
    names: list[str] = []
    configs: dict[str, dict] = {}
    for entry in config["markdown_extensions"]:
        if isinstance(entry, dict):
            ((name, options),) = entry.items()
            configs[name] = dict(options or {})
        else:
            name = entry
        names.append(name)
    builtins = [name for name in ("toc", "tables", "fenced_code") if name not in names]
    return builtins + names, configs


_FENCE_OPEN = re.compile(r"^(?P<indent> *)(?P<fence>`{3,}|~{3,})(?P<info>[^`]*)$")


def fenced_blocks(text: str) -> list[tuple[int, str]]:
    """Every fenced block of a page as a reader reads it: (its first line, its content).

    A fence opens at any indentation and closes at the same fence alone on a
    line; the content is dedented by the opening fence's indentation.
    """
    lines = text.splitlines()
    blocks: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        opened = _FENCE_OPEN.match(lines[index])
        if not opened:
            index += 1
            continue
        width, fence = len(opened.group("indent")), opened.group("fence")
        body: list[str] = []
        end = index + 1
        while end < len(lines) and lines[end].strip() != fence:
            line = lines[end]
            body.append(line[width:] if not line[:width].strip() else line)
            end += 1
        blocks.append((index + 1, "\n".join(body)))
        index = end + 1
    return blocks


def _collapsed(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def rendering_problems(text: str, names: list[str], configs: dict[str, dict]) -> list[str]:
    """What the site's Markdown makes of a page that its author did not write."""
    body = markdown.Markdown(extensions=names, extension_configs=configs).convert(text)
    code = [_collapsed(block) for block in re.findall(r"<pre[^>]*>(.*?)</pre>", body, re.S)]
    problems = [
        f"the fenced block at line {line} is not rendered as code"
        for line, content in fenced_blocks(text)
        if " ".join(content.split())
        and not any(" ".join(content.split()) in block for block in code)
    ]
    inside = {
        number
        for line, content in fenced_blocks(text)
        for number in range(line, line + content.count("\n") + 3)
    }
    rendered = {
        _collapsed(heading).replace("¶", "").strip()
        for heading in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", body, re.S)
    }
    for number, line in enumerate(text.splitlines(), 1):
        heading = re.match(r"^#{1,6} (.+?)\s*$", line)
        if heading and number not in inside:
            words = " ".join(re.sub(r"[`*]", "", heading.group(1)).split())
            if words not in rendered:
                problems.append(f"the heading at line {number} ({words!r}) is not rendered as one")
    problems += [
        f"a table row is rendered as prose: {_collapsed(row)[:80]!r}"
        for row in re.findall(r"<p>(\|.*?)</p>", body, re.S)
    ]
    return problems


HAND_WRITTEN = sorted(DOCS.rglob("*.md"))


@pytest.mark.parametrize("page", HAND_WRITTEN, ids=[page.stem for page in HAND_WRITTEN])
def test_d07_the_site_renders_every_page_as_written(page):
    """Every fence as code, every heading as a heading, every table row in its table."""
    names, configs = site_markdown()
    problems = rendering_problems(page.read_text(encoding="utf-8"), names, configs)
    assert not problems, f"{page.relative_to(REPO).as_posix()}:\n  " + "\n  ".join(problems)


def test_d07_the_rendering_check_can_see_what_it_looks_for():
    """The witness, on the three shapes that cut the pages before D07.

    A titled fence under the built-in fence reader alone, which is the site's
    configuration before D07, loses its block and the heading after the next
    fence; a blank line inside a table leaves its tail as prose. The site's
    configuration of today renders the first as written and still refuses the
    second, which is a fault of the page and not of the reader.
    """
    titled = (
        '```text title="a.fs"\nPOL | RUN\n8001 | 1\n```\n\nRead it.\n\n'
        "## After the fence\n\nProse.\n\n```text\nlast\n```\n"
    )
    split = "| a | b |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n"
    before = (["toc", "tables", "fenced_code", "admonition", "attr_list"], {})
    problems = rendering_problems(titled, *before)
    assert any("line 1" in problem for problem in problems), problems
    assert any("After the fence" in problem for problem in problems), problems
    names, configs = site_markdown()
    assert rendering_problems(titled, names, configs) == []
    assert any("prose" in problem for problem in rendering_problems(split, names, configs))
    assert rendering_problems(split.replace("\n\n|", "\n|"), names, configs) == []
