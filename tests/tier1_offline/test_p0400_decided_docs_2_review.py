"""P0400 review controls for the archive guard and the licensed result readers.

The synthetic CSVs exercise the rotation reader, not a licensed solver.
"""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

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


def _write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_p0400_rotation_main_scores_both_turned_points(tmp_path, monkeypatch, capsys):
    """PFS-2135.080: main must use the leading simulation id for both angle signs."""
    from tests.tier3_licensed import rotation_null as reader

    monkeypatch.setattr(reader, "PRODUCTS", tmp_path)
    control = dict(CL=1.0, CDi=0.2, CDo=0.3, Cx=1.0, Cy=0.0, Cz=0.0, CMx=2.0, CMy=0.0, CMz=0.0)
    turned = dict(control)
    turned["Cx"], turned["Cz"] = reader.rotate_y(1.0, 0.0, reader.MESH_ANGLE_DEG)
    turned["CMx"], turned["CMz"] = reader.rotate_y(2.0, 0.0, reader.MESH_ANGLE_DEG)
    wrong = {key: value + 1.0 for key, value in turned.items()}
    sweep = []
    for point, sim, alpha, values, section_value in (
        (reader.CONTROL, "9001", 0, control, 1.0),
        (reader.TURNED[0], "9002", 6, wrong, 2.0),
        (reader.TURNED[1], "9003", -6, turned, 1.0),
    ):
        sweep.append({"sim_id": sim, "alpha": alpha, **values})
        _write_rows(
            tmp_path / "series" / f"{point}_loads_series.csv",
            [
                {"STEP": step, **{f"Body_{key}": value for key, value in values.items()}}
                for step in range(28)
            ],
        )
        _write_rows(
            tmp_path / "sections" / f"{point}_sections.csv",
            [dict(Fx=section_value, Fz=section_value, Moment=section_value) for _ in range(20)],
        )
    _write_rows(tmp_path / "campaign_sweep.csv", sweep)
    assert reader.main([]) == 0
    text = capsys.readouterr().out
    assert "9003 (alpha -6.0)" in text
    assert "row 9002 at alpha +6.0, DIFFERS on 4 of 4 checks" in text
    assert "209 comparisons of four kinds" in text


@pytest.mark.parametrize(
    "prefix",
    ["", "16 trailing edges marked on surface Wing\n", "0 trailing edges marked on surface Wing\n"],
)
def test_p0400_detection_reader_counts_every_marking(prefix, monkeypatch):
    """PFS-2135.031: call the licensed assertion with a synthetic log, without a solver."""
    from tests.tier3_licensed import test_mesh

    runs = SimpleNamespace(one=lambda *args, **kwargs: object())
    log = prefix + "16 trailing edges marked on surface Wing\n"
    monkeypatch.setattr(test_mesh, "_log", lambda runs, record: log)
    check = test_mesh.test_the_detection_route_marked_the_edges_the_saved_file_carries
    if prefix:
        with pytest.raises(AssertionError):
            check(runs, "4103", "Wing", 16)
    else:
        check(runs, "4103", "Wing", 16)
