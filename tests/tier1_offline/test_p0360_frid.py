"""Placement of requirement evidence and the single home of shared test helpers."""

from __future__ import annotations

import ast
import copy
import io
import re
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TIER1 = REPO / "tests" / "tier1_offline"
IDS = re.compile(r"\b(?:FR|NFR)-\d+[a-z]?\b")

# Contextual citations with no behavioural proof in the citing module.
# Each exception names one module and one id; stale exceptions fail below.
LEFTOVERS = {
    ("_p0340_probe_support.py", "FR-333"): "Fixture support only; the probe tests consuming these "
    "builders carry their own evidence.",
    ("_p0340_probe_support.py", "FR-334"): "Fixture support only; the probe tests consuming these "
    "builders carry their own evidence.",
    ("_p0340_probe_support.py", "FR-335"): "Fixture support only; the probe tests consuming these "
    "builders carry their own evidence.",
    ("_p0340_probe_support.py", "FR-342"): "Fixture support only; the probe tests consuming these "
    "builders carry their own evidence.",
    ("conftest.py", "NFR-08"): "Fixture-only module; it supplies synthetic inputs but contains no "
    "test function enforcing the content policy.",
    ("test_approved_capabilities_029.py", "FR-152"): "The header overstates this module: its "
    "tests cover trailing edges, unit origins, "
    "section recovery, FSI inputs and reusable "
    "inflow, not ports, cold-start policy or the "
    "three refused keys.",
    ("test_approved_capabilities_029.py", "FR-158"): "The header overstates this module: its "
    "tests cover trailing edges, unit origins, "
    "section recovery, FSI inputs and reusable "
    "inflow, not ports, cold-start policy or the "
    "three refused keys.",
    ("test_approved_capabilities_029.py", "FR-164"): "The header overstates this module: its "
    "tests cover trailing edges, unit origins, "
    "section recovery, FSI inputs and reusable "
    "inflow, not ports, cold-start policy or the "
    "three refused keys.",
    ("test_clean_log.py", "FR-178"): "Tests warning format, path shortening and verbose progress; "
    "the signature box requirement is proved in "
    "test_cli_signature.py.",
    ("test_cli_options_registry.py", "FR-250"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-253"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-306"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-307"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-308"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-309"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-326"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-330"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-347"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-379"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-385"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-390"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-391"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-397"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-398"): "Citation explains an option allowlist entry; "
    "this module checks registry membership and "
    "defaults, not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-82"): "Citation explains an option allowlist entry; this "
    "module checks registry membership and defaults, "
    "not the cited feature behaviour.",
    ("test_cli_options_registry.py", "FR-99"): "Citation explains an option allowlist entry; this "
    "module checks registry membership and defaults, "
    "not the cited feature behaviour.",
    ("test_collect_stage.py", "FR-309"): "Historical status-count note names mark-failed; these "
    "tests do not invoke or verify mark-failed.",
    ("test_command_db_census.py", "FR-342"): "Comment explains a promoted-command census change; "
    "no test here checks probe specifications or tier-2 "
    "verdicts.",
    ("test_conventions.py", "FR-100"): "Citation explains a unit or layer exemption; the tests "
    "enforce metadata and layering, not this cited behavioural "
    "requirement.",
    ("test_conventions.py", "FR-321"): "Citation explains a unit or layer exemption; the tests "
    "enforce metadata and layering, not this cited behavioural "
    "requirement.",
    ("test_conventions.py", "FR-323"): "Citation explains a unit or layer exemption; the tests "
    "enforce metadata and layering, not this cited behavioural "
    "requirement.",
    ("test_conventions.py", "FR-79"): "Citation explains a unit or layer exemption; the tests "
    "enforce metadata and layering, not this cited behavioural "
    "requirement.",
    ("test_conventions.py", "NFR-20"): "Citation explains a unit or layer exemption; the tests "
    "enforce metadata and layering, not this cited behavioural "
    "requirement.",
    ("test_conventions.py", "NFR-32"): "Citation explains a unit or layer exemption; the tests "
    "enforce metadata and layering, not this cited behavioural "
    "requirement.",
    ("test_fsi_state_migration.py", "NFR-18"): "Tests the FSI state key migration, not the "
    "runs.json manifest schema named by this "
    "requirement.",
    ("test_g25_surface_time_average.py", "FR-160"): "Historical fixture note; tests averaged VTK "
    "surfaces, not requested native "
    "singularity-strength merging.",
    ("test_g45_tecplot_from_vtk.py", "FR-160"): "Historical fixture/context citation; these tests "
    "verify VTK translation, not native strength "
    "attachment or the tracked-geometry guard.",
    ("test_g45_tecplot_from_vtk.py", "NFR-14"): "Historical fixture/context citation; these tests "
    "verify VTK translation, not native strength "
    "attachment or the tracked-geometry guard.",
    ("test_goal021_future_version.py", "FR-84"): "Historical reference to the outputs rename; "
    "these tests check expired deprecation promises, "
    "not directory layout.",
    ("test_goal033_delivery.py", "FR-329"): "Comment explains excluded guide PDF targets; the "
    "delivery tests do not enforce guide numbering or the "
    "cover title.",
    ("test_goal034_setup_operational_commands.py", "FR-152"): "Comments explain exclusions from "
    "the command-route table; no "
    "assertion here proves ports, "
    "counter registration or actuator "
    "swirl sign.",
    ("test_goal034_setup_operational_commands.py", "FR-314"): "Comments explain exclusions from "
    "the command-route table; no "
    "assertion here proves ports, "
    "counter registration or actuator "
    "swirl sign.",
    ("test_goal034_setup_operational_commands.py", "FR-331"): "Comments explain exclusions from "
    "the command-route table; no "
    "assertion here proves ports, "
    "counter registration or actuator "
    "swirl sign.",
    ("test_house_style.py", "FR-329"): "Comment explains the guide PDF exemption; no test here "
    "checks the numbered guide names or cover title.",
    ("test_p0320_rigor.py", "FR-289"): "Retired identifier in the original header, absent from "
    "the live requirements index; no live requirement marker "
    "may claim it.",
    ("test_p0320_setup_surfaces.py", "FR-279"): "Tests emitted surface and wake commands, not "
    "their database probe citations and promotion "
    "status.",
    ("test_p0340_fsi.py", "FR-338"): "The introduction names the broader FSI package; every test "
    "here verifies the convergence-log tip column only.",
    ("test_p0340_fsi.py", "FR-340"): "The introduction names the broader FSI package; every test "
    "here verifies the convergence-log tip column only.",
    ("test_p0340_fsi.py", "FR-341"): "The introduction names the broader FSI package; every test "
    "here verifies the convergence-log tip column only.",
    ("test_p0340_probe_effects.py", "FR-342"): "The module cites shared probe work; its "
    "assertions judge acoustic and CCS effects, not "
    "the missing-specification census.",
    ("test_p0340_qa_promote.py", "FR-334"): "The introduction names the neighbouring "
    "three-command probe package; those specific "
    "assertions live in test_p0340_probe_2001_05.py.",
    ("test_p0340_qsnoise_sign.py", "FR-300"): "Context for the exploratory sign report; these "
    "tests inspect that report rather than the acoustic "
    "prediction model.",
    ("test_p0351_batch_tavg.py", "FR-368"): "Citation labels synthetic log separators; assertions "
    "compare averaged surfaces and stamped exports, not "
    "per-point log slices.",
    ("test_p0351_batch_user_actions.py", "FR-319"): "Context for the native action setup keys; "
    "tests grouped registration, not the complete "
    "solver-chapter setup-key audit.",
    ("test_products_layout.py", "FR-90"): "Context cites the duplicate-output rule; layout "
    "assertions do not compare all output bytes for "
    "duplicates.",
    ("test_public_api.py", "FR-347"): "Comments explain public-module classification; "
    "importability checks do not prove these feature contracts.",
    ("test_public_api.py", "FR-388"): "Comments explain public-module classification; "
    "importability checks do not prove these feature contracts.",
    ("test_public_api.py", "FR-398"): "Comments explain public-module classification; "
    "importability checks do not prove these feature contracts.",
    ("test_public_api.py", "FR-99"): "Comments explain public-module classification; "
    "importability checks do not prove these feature contracts.",
    ("test_raw_on_the_row.py", "FR-31"): "Historical reference to preset-level provenance; these "
    "tests exercise row raw commands rather than the "
    "solver-setting snapshot contract.",
    ("test_run_cli.py", "FR-151"): "Comment explains the summary change accompanying setup "
    "inspection; no test in this module exercises inspect-setups.",
    ("test_sweep_job_volume_section.py", "NFR-31"): "Fixture comment withholds an executable "
    "digest; the tests verify job exports and "
    "build identity, not the public-tree digest "
    "policy.",
    ("test_traceability.py", "FR-111"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-30b"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-320"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-33d"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-33e"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-33f"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-40"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-59"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-73"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "FR-74"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
    ("test_traceability.py", "NFR-03"): "Historical marker-floor changelog; this module checks "
    "traceability bookkeeping, not the feature cited by that "
    "history.",
}


def _module_only_ids(source: str) -> set[str]:
    """Read module comments/docstrings and each test's decorated source with AST spans."""
    tree = ast.parse(source)
    lines = source.splitlines()
    functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    occupied = set()
    carried = set()
    for node in functions:
        start = min([node.lineno] + [item.lineno for item in node.decorator_list])
        occupied.update(range(start, node.end_lineno + 1))
        if node.name.startswith("test_"):
            carried.update(IDS.findall("\n".join(lines[start - 1 : node.end_lineno])))
    comments = "\n".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT and token.start[0] not in occupied
    )
    claimed = set(IDS.findall((ast.get_docstring(tree) or "") + "\n" + comments))
    return claimed - carried


def test_requirement_ids_belong_to_the_test_functions():
    """P0360-FR-IN-FUNCTIONS (NFR-38): presence check, not proof of behaviour.

    An id anywhere in a test's decorated source counts; module-only citations
    fail, with explicit leftovers.
    """
    paths = sorted(TIER1.rglob("*.py"))
    assert len(paths) > 100
    found = {
        (path.relative_to(TIER1).as_posix(), rid)
        for path in paths
        for rid in _module_only_ids(path.read_text(encoding="utf-8"))
    }
    assert found == set(LEFTOVERS), {
        "unassigned": sorted(found - LEFTOVERS.keys()),
        "stale_exceptions": sorted(LEFTOVERS.keys() - found),
    }
    assert all(reason.strip() for reason in LEFTOVERS.values())


@pytest.mark.parametrize("heading", ["# FR-987654\n", '"""FR-987654"""\n'])
def test_module_only_control_is_refused(heading):
    """NFR-38: planted comment-only and docstring-only claims fail the same scanner."""
    source = heading + "def test_control():\n    assert 2 + 2 == 4\n"
    assert _module_only_ids(source) == {"FR-987654"}
    with pytest.raises(AssertionError):
        assert not _module_only_ids(source)


@pytest.mark.parametrize(
    "function",
    [
        'def test_control():\n    """FR-987654"""\n    assert 2 + 2 == 4\n',
        '@pytest.mark.requirement("FR-987654")\ndef test_control():\n    assert True\n',
        "class TestControl:\n    def test_control(self):\n"
        '        """FR-987654"""\n        assert True\n',
    ],
)
def test_function_local_control_satisfies_placement(function):
    """NFR-38: function docstrings, methods and requirement decorators carry evidence."""
    assert not _module_only_ids("# FR-987654\n" + function)
    assert _module_only_ids('# FR-987654\ndef helper():\n    """FR-987654"""\n') == {"FR-987654"}


def _helper_shape(node: ast.FunctionDef) -> str:
    node = copy.deepcopy(node)
    node.name = "helper"
    node.returns = None
    if ast.get_docstring(node) is not None:
        node.body = node.body[1:]
    for child in ast.walk(node):
        if isinstance(child, ast.arg):
            child.annotation = None
    return ast.dump(node, include_attributes=False)


def _helper_duplicates(source: str, support: str) -> list[str]:
    helpers = {
        node.name: _helper_shape(node)
        for node in ast.parse(support).body
        if isinstance(node, ast.FunctionDef)
    }
    return [
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef)
        and (node.name in helpers or _helper_shape(node) in helpers.values())
    ]


def test_shared_helpers_have_one_definition():
    """P0360-RV-A1 (NFR-39): renamed or identically named local copies are refused."""
    support = (REPO / "tests/support_helpers.py").read_text(encoding="utf-8")
    # 11 at 0.38.0: fold_separators joined the shared home (NFR-44 R2).
    assert len([n for n in ast.parse(support).body if isinstance(n, ast.FunctionDef)]) == 11
    duplicates = {
        path.name: found
        for path in TIER1.rglob("*.py")
        if (found := _helper_duplicates(path.read_text(encoding="utf-8"), support))
    }
    assert not duplicates
    control = "def file_sha256(path):\n    return 'wrong'\n"
    assert _helper_duplicates(control, support) == ["file_sha256"]
    copied = next(n for n in ast.parse(support).body if isinstance(n, ast.FunctionDef))
    copied.name = "_planted_copy"
    assert _helper_duplicates(ast.unparse(copied), support) == ["_planted_copy"]
    with pytest.raises(AssertionError):
        assert not _helper_duplicates(control, support)


def test_shared_helpers_are_imported_by_their_consumers():
    """P0360-RV-A2 (NFR-39): every former copy imports its helper from the shared home."""
    for helper, consumers in HELPER_CONSUMERS.items():
        for module, alias in consumers:
            tree = ast.parse((TIER1 / module).read_text(encoding="utf-8"))
            assert any(
                isinstance(node, ast.ImportFrom)
                and node.module == "tests.support_helpers"
                and any(
                    item.name == helper and (item.asname or item.name) == alias
                    for item in node.names
                )
                for node in tree.body
            ), (module, helper, alias)


HELPER_CONSUMERS = {
    "file_sha256": [
        ["test_goal033_release_receipts.py", "_sha256"],
        ["test_goal036_qsteady_corrections.py", "_sha"],
        ["test_p0320_records.py", "_sha"],
        ["test_p0340_thin_blade.py", "_sha"],
        ["test_unsteady_actions.py", "_sha256"],
    ],
    "no_sleep": [
        ["test_collect_stage.py", "_no_sleep"],
        ["test_goal031_machine_log_paths.py", "_no_sleep"],
        ["test_p0350_batch_collect.py", "_no_sleep"],
        ["test_sims_selection.py", "_no_sleep"],
    ],
    "saved_mesh_fixture": [
        ["test_inventory_cli.py", "_saved_simulation"],
        ["test_matrix_run.py", "_saved_simulation_with"],
        ["test_workflows.py", "_saved_simulation"],
        ["test_rotor_by_alias.py", "saved_simulation"],
    ],
    "script_lines": [
        ["test_g05_volume_section.py", "_lines"],
        ["test_g09_loads_selection.py", "_render"],
        ["test_p0320_e2_noise_emission.py", "_lines"],
        ["test_g15_custom_freestream.py", "lines_of"],
    ],
}
