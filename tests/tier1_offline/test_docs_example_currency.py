"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
from pathlib import Path

from tests.tier1_offline._workflow_docs import WORKFLOW_DOCS

REPO = Path(__file__).resolve().parents[2]


def test_p0440_blade_passage_windows_are_distinct_from_shared_average():
    from pyflightstream.cases.workflows import ReductionPlan

    assert "disjoint passage windows" in ReductionPlan.blade_windows.__doc__
    text = (REPO / "docs/definitions/per_blade.md").read_text(encoding="utf-8")
    assert "ReductionPlan.blade_windows()" in text
    assert "different parts of the history" in text


def test_p0440_alias_contract_states_recorded_first_order():
    import csv

    from pyflightstream.run._alias import alias_order

    with (REPO / "tests/requirements_l3.csv").open(encoding="utf-8", newline="") as stream:
        row = next(row for row in csv.reader(stream) if row[0] == "FR-395")
    assert "recorded points first" in row[3]
    assert "unrecorded planned points" in row[3]
    assert "no longer planned" in alias_order.__doc__


def test_p0440_unemitted_defaults_are_provenance_not_loaded_state():
    import csv

    from pyflightstream.script.solver_setup import FlagRecord

    with (REPO / "tests/requirements_l3.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    row = next(row for row in rows if row[0] == "FR-1216")
    assert "not the effective state of a loaded simulation" in row[3]
    assert "not the effective state of a loaded simulation" in FlagRecord.__doc__


def test_p0440_preview_contract_preserves_invalid_or_old_batches():
    import ast

    tree = ast.parse((REPO / "src/pyflightstream/workspace/excel_bridge.py").read_text())
    contract = next(
        ast.get_docstring(node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_preview_records"
    )
    assert "invalid direction preserves the previous batch" in contract
    assert "older-version batch" in contract
    assert "refused rather than replaced" in contract


def test_p0440_series_contract_keeps_the_moving_grid_refusal():
    from pyflightstream.post.unsteady import read_timestep_series

    assert "stationary sample coordinates only" in read_timestep_series.__doc__
    assert "RB5-30" in read_timestep_series.__doc__


def test_p0440_probe_reference_contract_names_the_unmeasured_placement():
    from pyflightstream.post.point_tables import write_probes_table

    assert "per-export placement probe is still owed in 0.45.0" in write_probes_table.__doc__
    text = (REPO / "docs/definitions/sampled-velocity-fields-and-reusable-inflow.md").read_text(
        encoding="utf-8"
    )
    assert "by the 0.40.0 design" in text and "RB3-04" in text


def test_p0440_custom_inflow_supplement_has_a_dated_erratum():
    text = (REPO / "reports/RPT-082_cad-units-and-custom-inflow-coverage_2026-09-27.md").read_text(
        encoding="utf-8"
    )
    assert "Erratum dated 2026-10-23" in text
    assert "supplement added on 2026-10-21" in text
    assert "original report date remains 2026-09-27" in text


def test_p0440_external_flight_evidence_is_named_as_private():
    text = (REPO / "docs/flight-conditions.md").read_text(encoding="utf-8")
    assert "RPT-052, RPT-060 and RPT-078" in text
    assert "private release records" in text and "not publicly available" in text


def test_p0440_missing_value_definition_names_the_fixed_width_exception():
    text = (REPO / "docs/definitions/the-token-for-a-value-that-does-not-exist.md").read_text(
        encoding="utf-8"
    )
    assert "except the fixed-width custom polar" in text and "`nan`" in text


PAGE = WORKFLOW_DOCS


def test_p0440_executable_report_separates_public_builds_from_byte_identity():
    text = (REPO / "reports/RPT-032_executable-identity-baseline_2026-08-19.md").read_text(
        encoding="utf-8"
    )
    # A dated report is corrected by an erratum; its original text stays readable (VV-2).
    after = text.split("## Erratum dated 2026-10-23", 1)[1]
    erratum, dated = after.split("The licence in use is temporary", 1)
    assert "Build agreement does not establish byte identity" in erratum
    assert "read the nine original rows" in erratum
    assert "a public build-only match does not" in erratum
    assert "Every other row is this report's own measurement of" in dated


def test_p0440_capture_comment_distinguishes_historical_export_grammar():
    text = (REPO / "scripts/capture_export_corpus.py").read_text(encoding="utf-8")
    assert "current entry declares both index and path" in text
    assert "entry declares `index: int` alone" not in text


def test_p0440_walltime_documents_both_clock_origins():
    text = (REPO / "docs/workflow-run-matrix.md").read_text(encoding="utf-8")
    clock = text.split("`WALLTIME` is the wall clock", 1)[1].split("**A COLUMN", 1)[0]
    assert all(term in clock for term in ("job-start", "first-invocation", "walltime_margin_s"))


def test_p0440_g2_documents_closed_shells_across_families():
    text = (REPO / "docs/mesh/reference.md").read_text(encoding="utf-8")
    gate = next(line for line in text.splitlines() if line.startswith("| G2 |"))
    assert "closed shell" in gate and "across families" in gate


def test_p0440_show_documents_the_final_resolved_record():
    text = (REPO / "docs/workspace-queries.md").read_text(encoding="utf-8")
    show = text.split("`show` prints", 1)[1].split("`log` prints", 1)[0]
    assert "ends with the full resolved record" in show


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


def test_p0440_solver_export_claims_cite_their_measured_evidence():
    import ast

    for module, function, report in (
        ("workspace/_layout.py", "with_wake_companions", "RPT-074"),
        ("workspace/__init__.py", "collect_outputs", "RPT-074"),
        ("results/tables.py", "_loads_frame", "RPT-053"),
    ):
        tree = ast.parse((REPO / "src/pyflightstream" / module).read_text(encoding="utf-8"))
        node = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        assert report in (ast.get_docstring(node) or ""), (module, function, report)


def test_the_page_exists_and_is_reachable_from_the_site_nav():
    """A page nobody can navigate to is not published."""
    assert PAGE.is_file(), "the workspace and workflow page does not exist"
    nav = (REPO / "properdocs.yml").read_text(encoding="utf-8")
    assert "workspace-and-workflows.md" in nav, (
        "the page is not in properdocs.yml's nav, which is explicit, so the page would "
        "build and be unreachable"
    )


def test_the_recorded_rotor_block_on_the_page_validates(tmp_path):
    """The documented artifact is refused by nothing.

    This item exists BECAUSE a real campaign's reference artifact was
    refused by the shipped model, so publishing an example of that same
    artifact on the strength of having typed it carefully would be the
    same defect with a smaller blast radius.

    Note what it does NOT prove. There is no executed test this block is
    lifted from, unlike the matrix and the input library above, so this
    checks that the page's artifact is ADMISSIBLE and not that any
    behaviour follows from it.
    """
    import tomllib

    from pyflightstream.workspace.inputs import ReferenceArtifact

    blocks = [
        body
        for info, body in _blocks(PAGE.read_text(encoding="utf-8"))
        if info == "toml" and "[rotor]" in body
    ]
    assert len(blocks) == 1, (
        f"the page carries {len(blocks)} recorded rotor blocks; this guard reads exactly "
        "one, and zero would pass every assertion below vacuously"
    )

    artifact = ReferenceArtifact.model_validate(tomllib.loads(blocks[0]))
    assert artifact.rotor is not None, (
        "the documented artifact parses but carries no recorded rotor block, so the guard "
        "would go on passing over a page that lost the block entirely"
    )


def test_every_key_of_the_documented_rotor_block_is_a_field_of_the_model():
    """A renamed field cannot leave the page quietly documenting the old name.

    ``extra="forbid"`` means validation already refuses an unknown key,
    so this case earns its place only for the OPPOSITE direction: it
    names, in its failure, which key on the page the model no longer has.
    A pydantic refusal names the same key, but as one of a list of
    validation errors on a block a reader then has to find.
    """
    import tomllib

    from pyflightstream.workspace.inputs import RotorReference

    blocks = [
        body
        for info, body in _blocks(PAGE.read_text(encoding="utf-8"))
        if info == "toml" and "[rotor]" in body
    ]
    assert len(blocks) == 1
    documented = set(tomllib.loads(blocks[0])["rotor"])
    assert documented, "the documented recorded rotor block is empty"

    unknown = documented - set(RotorReference.model_fields)
    assert not unknown, (
        f"the page documents {sorted(unknown)} under [rotor] and the model has no "
        f"such field. Its fields are {sorted(RotorReference.model_fields)}"
    )
