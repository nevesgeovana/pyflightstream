"""Recorded private-ledger-id citations per counted unit (OPS-2010.15).

Data only, read by ``test_no_new_private_ledger_citation_in_a_walked_file``
in ``tests/test_house_style.py``. That module owns the meaning of a counted
unit; this file owns nothing but the numbers.

Paths and counts, and deliberately nothing else. This file is inside the
style walk it feeds, so a row carrying the cited id itself would make the
record its own offender; no walked path carries such an id in its own name.

To lower a row: run the sweep, then set the number to what the tree now
holds. The ratchet fails on a count that dropped as well as on one that
grew, so the record cannot quietly stop describing the tree. The failure
message names the unit and both numbers, so no tool is needed to find them;
there is deliberately no regenerate command here, because a one-command
rewrite would absorb a new citation as easily as a removed one, which is the
whole thing this record exists to prevent.

Re-measured 2026-08-23, and the rows below are that measurement: 325
citations across 99 counted units, over 407 walked files.

EVERY WALKED FILE IS COUNTED END TO END, and that is the change of
2026-08-23 rather than a simplification of the sentence. There used to be an
exempt region: a population of files whose bodies were byte-pinned outside
this repository, counted only above a marker line, because a citation below
it could not be corrected here at all. Those files have left the tree, so no
walked file has a region this repository cannot correct, and the two totals
that used to differ are one number.

FIFTY-FIVE ROWS WENT WITH THEM in the same measurement, and the drop from
609 citations to 325 is that removal rather than a sweep: the departing
tree was where more than half of the recorded citations lived. Three
surviving rows also fell, each because the sentence carrying the citation
was rewritten in the same change. Nothing was added anywhere, which is what
the ratchet's upward arm was asked and what it answered.

Read those totals as a snapshot rather than as a contract. The rows are the
contract; the totals move whenever a page is edited, and the guard reports
the live ones in its failure message.
"""

PRIVATE_ID_COUNTS: dict[str, int] = {
    "CHANGELOG.md": 48,
    "CLAUDE.md": 14,
    "CONTRIBUTING.md": 4,
    "README.md": 1,
    "docs/mesh-inputs.md": 1,
    "docs/srs/data-model.md": 2,
    "docs/srs/functional-requirements.md": 39,
    "docs/srs/index.md": 4,
    "docs/srs/introduction.md": 20,
    "docs/srs/nonfunctional-requirements.md": 7,
    "docs/srs/roadmap.md": 2,
    "reports/RPT-004_probe-roundtrip-order_2026-07-21.md": 3,
    "reports/RPT-005_fsi-dry-run_2026-07-21.md": 2,
    "reports/RPT-006_wp7-nearrigid-pilot_2026-07-21.md": 2,
    "reports/RPT-007_soft-pilot-morphing-investigation_2026-07-21.md": 3,
    "reports/RPT-010_obj-group-names_2026-07-23.md": 2,
    "reports/RPT-011_solver-defaults_2026-07-23.md": 2,
    "reports/RPT-012_bulk-separation-spelling_2026-07-23.md": 2,
    "reports/RPT-014_26121-manual-diff-and-probe_2026-08-02.md": 3,
    "reports/RPT-016_runtime-and-plot-licenses_2026-08-03.md": 2,
    "reports/RPT-018_separation-family-across-builds_2026-08-05.md": 2,
    "reports/RPT-019_keyword-block-order_2026-08-08.md": 1,
    "reports/RPT-021_chapter-questions-measured_2026-08-08.md": 6,
    "reports/RPT-023_the-script-argument-across-builds_2026-08-09.md": 1,
    "reports/RPT-024_the-scripting-surface-of-every-build_2026-08-09.md": 2,
    "reports/RPT-025_rotor-morphing-across-three-builds_2026-08-11.md": 1,
    "reports/RPT-026_what-the-solver-says-when-it-refuses-a-name_2026-08-11.md": 3,
    "reports/compat/CMP-26122_2026-08-11_full_erratum_2026-08-11.md": 1,
    "reports/compat/CMP-26123_2026-08-17_full-sim_erratum_2026-08-17.md": 1,
    "reports/physics/TRI-26123-CDo_2026-08-18.md": 1,
    "reports/physics/TRI-SMI01-CMy_2026-07-21.md": 2,
    "scripts/_mutation_harness.py": 1,
    "scripts/prove_evidence_guards.py": 1,
    "scripts/prove_flow_mapping_guard.py": 1,
    "scripts/prove_published_invocation_guards.py": 1,
    "scripts/prove_report_date_guards.py": 1,
    "src/pyflightstream/_yamlflow.py": 1,
    "src/pyflightstream/cases/matrix.py": 1,
    "src/pyflightstream/commands/__init__.py": 2,
    "src/pyflightstream/commands/_meta.yaml": 2,
    "src/pyflightstream/commands/advanced_settings.yaml": 2,
    "src/pyflightstream/commands/aeroelastic_coupling.yaml": 2,
    "src/pyflightstream/commands/boundary_conditions.yaml": 1,
    "src/pyflightstream/commands/cad.yaml": 3,
    "src/pyflightstream/commands/cad_create.yaml": 8,
    "src/pyflightstream/commands/ccs_fuselage_mesh.yaml": 1,
    "src/pyflightstream/commands/ccs_revolve_mesh.yaml": 1,
    "src/pyflightstream/commands/ccs_wing_mesh.yaml": 5,
    "src/pyflightstream/commands/coordinate_systems.yaml": 2,
    "src/pyflightstream/commands/mesh_operations.yaml": 3,
    "src/pyflightstream/commands/mesh_wrapper.yaml": 1,
    "src/pyflightstream/commands/motion_definitions.yaml": 3,
    "src/pyflightstream/commands/scene_settings.yaml": 1,
    "src/pyflightstream/commands/solver_contours.yaml": 1,
    "src/pyflightstream/commands/solver_settings.yaml": 5,
    "src/pyflightstream/commands/streamlines.yaml": 1,
    "src/pyflightstream/commands/sweeper.yaml": 1,
    "src/pyflightstream/fsi/README.md": 1,
    "src/pyflightstream/qa/compat.py": 3,
    "src/pyflightstream/qa/probes.py": 2,
    "src/pyflightstream/qa/reports.py": 2,
    "src/pyflightstream/qa/specs.py": 1,
    "src/pyflightstream/reference.py": 2,
    "src/pyflightstream/run/__init__.py": 6,
    "src/pyflightstream/script/__init__.py": 1,
    "src/pyflightstream/script/helpers.py": 1,
    "src/pyflightstream/script/toggles.py": 1,
    "src/pyflightstream/support.py": 1,
    "src/pyflightstream/utils/manual.py": 2,
    "src/pyflightstream/workspace/__init__.py": 1,
    "tests/test_build_table.py": 1,
    "tests/test_clean_room.py": 1,
    "tests/test_command_db.py": 5,
    "tests/test_conventions.py": 1,
    "tests/test_digest.py": 1,
    "tests/test_error_messages.py": 2,
    "tests/test_evidence_provenance.py": 3,
    "tests/test_exceptions_catalog.py": 4,
    "tests/test_extras_isolation.py": 6,
    "tests/test_guide_api_names.py": 1,
    "tests/test_guide_currency.py": 2,
    "tests/test_house_style.py": 3,
    "tests/test_mutation_harness.py": 1,
    "tests/test_overview.py": 2,
    "tests/test_qa_cli.py": 1,
    "tests/test_qa_compat.py": 5,
    "tests/test_qa_physics.py": 1,
    "tests/test_qa_probes.py": 1,
    "tests/test_reference.py": 1,
    "tests/test_results.py": 1,
    "tests/test_run.py": 1,
    "tests/test_run_campaign.py": 3,
    "tests/test_run_preproc.py": 1,
    "tests/test_script.py": 7,
    "tests/test_solver_setup.py": 2,
    "tests/test_traceability.py": 2,
    "tests/test_utils_manual.py": 3,
    "tests/test_version_identity.py": 1,
    "tests/test_yamlflow.py": 2,
}
