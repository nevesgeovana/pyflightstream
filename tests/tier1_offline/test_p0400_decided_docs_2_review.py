"""P0400 review controls for the archive guard and the licensed result readers.

The synthetic CSVs exercise the rotation reader, not a licensed solver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tier1_offline.test_metadata_currency import _owed_claim_names_the_debt


def test_p0400_upgrade_notes_name_the_changed_tier3_programs():
    """The script behavior changes must be visible when adopting this release."""
    text = (Path(__file__).resolve().parents[2] / "docs" / "upgrading.md").read_text(
        encoding="utf-8"
    )
    section = text.split("## 0.40.0", 1)[-1].split("\n## ", 1)[0]
    assert "## 0.40.0" in text
    for program in ("actions_probe.py", "duct.py", "mesh_routes.py", "rotation_null.py"):
        assert program in section
    assert "1e-9" in section


@pytest.mark.parametrize("gate", ["build_support", "release_receipt"])
@pytest.mark.parametrize("missing", [False, True], ids=["failed-replay", "missing-receipt"])
def test_p0400_operational_gate_cannot_pass_without_replaying_evidence(
    gate, missing, tmp_path, monkeypatch
):
    """PFS-2135.003: neither gate may substitute a comment tag for a passing replay."""
    from tests.tier1_offline import test_fsi_native_interface_evidence as native
    from tests.tier1_offline import test_goal033_release_receipts as release
    from tests.tier1_offline import test_goal034_setup_operational_commands as setup

    def replay(_name):
        if missing:
            pytest.skip("P0400 receipt unavailable")
        raise AssertionError("P0400 replay assertion failed")

    monkeypatch.setattr(native, "_case", replay)
    expected = pytest.skip.Exception if missing else AssertionError
    message = "unproven" if missing else "P0400 replay assertion failed"
    with pytest.raises(expected, match=message):
        if gate == "build_support":
            setup.test_every_in_scope_setup_command_is_in_the_26124_database_and_the_rest_refused()
        else:
            release.test_setup_bc_is_complete_every_in_scope_command_operational_the_rest_refused(
                tmp_path
            )


def test_p0400_export_refusal_documents_the_information_it_records():
    """PFS-2135.071: a helper-name register does not promise file and line call sites."""
    import inspect

    from pyflightstream.script.helpers import export_probes

    doc = " ".join((inspect.getdoc(export_probes) or "").split())
    assert "helper name" in doc
    assert "BOTH call sites" not in doc


def test_p0400_missing_native_receipts_do_not_hide_a_broken_script_route(tmp_path, monkeypatch):
    """Offline failures are judged before a missing native receipt can skip the gate."""
    from tests.tier1_offline import test_goal033_release_receipts as release
    from tests.tier1_offline import test_goal034_setup_operational_commands as setup

    def missing(*args):
        pytest.skip("P0400 private receipt unavailable")

    monkeypatch.setattr(setup, "_prove_elsewhere", missing)
    monkeypatch.setattr(setup, "_carries", lambda *args: False)
    try:
        with pytest.raises(AssertionError, match="in scope and not operational"):
            release.test_setup_bc_is_complete_every_in_scope_command_operational_the_rest_refused(
                tmp_path
            )
    except pytest.skip.Exception:
        pytest.fail("missing evidence hid a broken offline script route")


@pytest.mark.parametrize(
    "claim",
    [
        "The v9.9.9 archive is lower on the page.",
        "The v9.9.90 archive DOI is owed.",
        "The v9.9.9rc1 archive DOI is owed.",
        "The v9.9.9 code is missing a doing flag.",
    ],
)
def test_p0400_archive_debt_requires_whole_words_and_the_exact_release(claim):
    assert not _owed_claim_names_the_debt(claim, "9.9.9")


@pytest.mark.parametrize(
    "claim",
    [
        "The v9.9.9 archive DOI is owed.",
        "We owe the archive identifier for v9.9.9.",
        "The archive for v9.9.9 does not exist yet.",
        "The v9.9.9 DOI is missing.",
        "We owe DOIs for v9.9.9 and v9.9.8.",
        "v9.9.9 still owes its archive.",
    ],
)
def test_p0400_archive_debt_keeps_the_supported_declarations(claim):
    assert _owed_claim_names_the_debt(claim, "9.9.9")
