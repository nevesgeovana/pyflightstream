"""Regression coverage grouped by subject."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream import reference
from pyflightstream._errors import InputArtifactError, PyflightstreamError
from pyflightstream.testing import assert_records_close
from pyflightstream.workspace.inputs import PprocArtifact, resolve_pproc
from tests import support_program_checks as _decided_docs_2_tier3__support_program_checks
from tests.tier1_offline.test_metadata_currency import (
    _owed_claim_names_the_debt as _decided_docs_2_review___owed_claim_names_the_debt,
)


class TestDecidedDocs1Reference:
    """Tier 1: reference.help opens a page at a relative path (P0400-HELP-RELPATH).

    Pipeline role: quality gate on :func:`pyflightstream.reference.help`. The
    page was written and then ``Path.as_uri`` raised on the relative path before
    the browser was asked to open it. The browser is replaced by a recorder, so
    nothing opens. Planning node PFS-2095.036.
    """

    @staticmethod
    def test_p0400_help_relpath_opens_the_resolved_page(tmp_path, monkeypatch):
        """P0400-HELP-RELPATH: a relative path is written and opened as an absolute file URI."""
        opened: list[str] = []
        monkeypatch.setattr(reference.webbrowser, "open", opened.append)
        monkeypatch.chdir(tmp_path)

        page = reference.help("26.124", path="commands.html")

        assert page == Path("commands.html")
        assert (tmp_path / "commands.html").is_file()
        assert opened == [(tmp_path / "commands.html").resolve().as_uri()]


_DECIDED_DOCS_1_TESTING__INF = math.inf


class TestDecidedDocs1Testing:
    """Tier 1: assert_records_close and infinite values (P0400-RECORDS-INF, PFS-2102.016).

    Pipeline role: quality gate on :mod:`pyflightstream.testing`. An infinite
    expected value made the tolerance band infinite (or nan when rtol is 0), so
    ``inf > inf`` let a finite or wrong-signed actual through. Only the same
    infinity agrees with an infinity.
    """

    @staticmethod
    @pytest.mark.parametrize("rtol", [1.0e-6, 0.0])
    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            (1.0, _DECIDED_DOCS_1_TESTING__INF),
            (-_DECIDED_DOCS_1_TESTING__INF, _DECIDED_DOCS_1_TESTING__INF),
            (_DECIDED_DOCS_1_TESTING__INF, -_DECIDED_DOCS_1_TESTING__INF),
            (_DECIDED_DOCS_1_TESTING__INF, 1.0),
            (0.0, -_DECIDED_DOCS_1_TESTING__INF),
        ],
    )
    def test_p0400_records_inf_refuses_a_different_value(actual, expected, rtol):
        """P0400-RECORDS-INF: a finite or opposite-signed value never matches an infinity."""
        with pytest.raises(AssertionError, match=r"1 of 1 values violate"):
            assert_records_close({"CL": actual}, {"CL": expected}, rtol=rtol)

    @staticmethod
    @pytest.mark.parametrize("rtol", [1.0e-6, 0.0])
    @pytest.mark.parametrize("value", [_DECIDED_DOCS_1_TESTING__INF, -_DECIDED_DOCS_1_TESTING__INF])
    def test_p0400_records_inf_accepts_the_same_infinity(value, rtol):
        """P0400-RECORDS-INF: the same infinity on both sides agrees."""
        assert_records_close({"CL": value}, {"CL": value}, rtol=rtol)


class TestDecidedDocs2Review:
    """P0400 review controls for the archive guard and the licensed result readers.

    The synthetic CSVs exercise the rotation reader, not a licensed solver.
    """

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def test_p0400_export_refusal_documents_the_information_it_records():
        """PFS-2135.071: a helper-name register does not promise file and line call sites."""
        import inspect

        from pyflightstream.script.helpers import export_probes

        doc = " ".join((inspect.getdoc(export_probes) or "").split())
        assert "helper name" in doc
        assert "BOTH call sites" not in doc

    @staticmethod
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

    @staticmethod
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
        assert not _decided_docs_2_review___owed_claim_names_the_debt(claim, "9.9.9")

    @staticmethod
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
        assert _decided_docs_2_review___owed_claim_names_the_debt(claim, "9.9.9")


_DECIDED_DOCS_2_TIER3__REPO = Path(__file__).resolve().parents[2]


_DECIDED_DOCS_2_TIER3__TIER3 = _DECIDED_DOCS_2_TIER3__REPO / "tests" / "tier3_licensed"


def _decided_docs_2_tier3___isolated_program(tmp_path: Path, name: str) -> Path:
    """Copy the real entrypoint and its support into a tree holding no run artifacts."""
    tests = tmp_path / "program-tree" / "tests"
    scripts = tests / "tier3_licensed"
    scripts.mkdir(parents=True)
    for filename in ("__init__.py", "support_tier3.py"):
        shutil.copyfile(_DECIDED_DOCS_2_TIER3__REPO / "tests" / filename, tests / filename)
    target = scripts / f"{name}.py"
    shutil.copyfile(_DECIDED_DOCS_2_TIER3__TIER3 / target.name, target)
    return target


def _decided_docs_2_tier3___clean_environment() -> dict[str, str]:
    """The environment of a solver-started action: no PYTHONPATH to hide a missing root."""
    return {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}


class TestDecidedDocs2Tier3:
    """P0400-DECIDED-DOCS-2: the tier-3 programs a tier-1 run can hold to what they promise.

    Four programs of ``tests/tier3_licensed`` are started by people or by the solver, never by
    pytest, so nothing offline ever ran them as they are run (PFS-2135.004, .047, .057, .080).
    """

    @staticmethod
    def test_p0400_offline_program_checks_import_no_licensed_modules(monkeypatch):
        """The pure checks must work when the licensed tier cannot be imported."""
        import builtins
        import importlib

        original = builtins.__import__

        def offline_import(name, *args, **kwargs):
            licensed = name == "tests.tier3_licensed" or name.startswith("tests.tier3_licensed.")
            assert not licensed, name
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", offline_import)
        importlib.reload(_decided_docs_2_tier3__support_program_checks)
        TestDecidedDocs2Tier3.test_p0400_a_gap_of_exactly_one_printed_unit_is_inside_the_band_for_the_unit_answer()
        TestDecidedDocs2Tier3.test_p0400_the_rotation_null_reads_the_simulation_id_a_point_name_leads_with()

    @staticmethod
    def test_p0400_the_actions_probe_starts_as_the_solvers_command_line_action(tmp_path):
        """P0400-TIER3-PROBE-START: ``python actions_probe.py --verdict`` from another folder.

        The action's ``.cmd`` runs the file as a script, so ``sys.path[0]`` is its own folder and
        the repository root is absent; the program must find ``tests`` from its own location.
        """
        program = _decided_docs_2_tier3___isolated_program(tmp_path, "actions_probe")
        done = subprocess.run(
            [sys.executable, str(program), "--verdict"],
            cwd=tmp_path,
            env=_decided_docs_2_tier3___clean_environment(),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert done.returncode == 0, done.stderr[-600:]
        assert json.loads(done.stdout)["verdict"] == "NOT_RUN", done.stdout
        assert not (program.parent / "sims").exists()

    @staticmethod
    def test_p0400_the_duct_generator_runs_as_the_script_the_docs_name(tmp_path):
        """P0400-TIER3-DUCT-START: ``python tests/tier3_licensed/duct.py out.obj`` writes the duct."""  # noqa: E501
        from tests.support_tier3 import write_duct_obj

        target = tmp_path / "duct.obj"
        program = _decided_docs_2_tier3___isolated_program(tmp_path, "duct")
        done = subprocess.run(
            [sys.executable, str(program), str(target)],
            cwd=tmp_path,
            env=_decided_docs_2_tier3___clean_environment(),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert done.returncode == 0, done.stderr[-600:]
        expected = write_duct_obj(tmp_path / "expected.obj")
        assert target.read_bytes() == Path(expected).read_bytes()

    @staticmethod
    def test_p0400_a_gap_of_exactly_one_printed_unit_is_inside_the_band_for_the_unit_answer():
        """P0400-TIER3-MESH-BAND: ``unit_answer`` shares the slack ``outside`` applies."""
        mesh_routes = _decided_docs_2_tier3__support_program_checks

        band = 1.0e-4
        one_unit = 1.0000000000000085e-4  # the binary quotient of a one-unit gap over the floor
        assert one_unit > band
        table = {"units": {"gaps": {"CL": one_unit, "CD": 0.5e-4}}}
        assert mesh_routes.unit_answer(table, band).startswith("IMPORT CONVERTS")
        banded = {"routes": {"4101": {"banded": True, "gaps": {"CL": one_unit}}}}
        assert mesh_routes.outside(banded, band) == {}
        table["units"]["gaps"]["CL"] = 1.01e-4
        assert mesh_routes.unit_answer(table, band).startswith("IMPORT DOES NOT CONVERT")
        assert mesh_routes.outside(
            {"routes": {"4101": {"banded": True, "gaps": {"CL": 1.01e-4}}}}, band
        )

    @staticmethod
    def test_p0400_the_rotation_null_reads_the_simulation_id_a_point_name_leads_with():
        """P0400-TIER3-ROTATION-NULL-SIM: both turned points resolve to a row of the sweep table."""
        rotation_null = _decided_docs_2_tier3__support_program_checks

        assert [rotation_null.sim_id_of(point) for point in rotation_null.TURNED] == [
            "9002",
            "9003",
        ]
        assert rotation_null.sim_id_of(rotation_null.CONTROL) == "9001"
        sweep = {sim: {"sim_id": sim} for sim in ("9001", "9002", "9003")}
        for point in rotation_null.TURNED:
            assert rotation_null.sim_id_of(point) in sweep


class TestDocfixHistory:
    """Run the published history example against its recorded export."""

    @staticmethod
    def test_p0400_getting_started_history_example(monkeypatch):
        root = Path(__file__).resolve().parents[2]
        page = (root / "docs" / "getting-started.md").read_text(encoding="utf-8")
        section = page.split("### Time-resolved history", 1)[1]
        example = section.split("```python\n", 1)[1].split("```", 1)[0]
        monkeypatch.chdir(root)
        exec(compile(example, "getting-started history example", "exec"), {})


class TestDocfixRefusals:
    """Regression coverage for the documented pproc artifact refusal boundary."""

    @staticmethod
    @pytest.mark.parametrize("entry", ["constructor", "mapping", "json"])
    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            (
                {"groups": {"Blade": ["Blade1"]}},
                "pproc [groups] entry 'Blade': member lists were removed in 0.26.0. "
                'Write Blade = "Blade1" instead.',
            ),
            (
                {"vtk_variables": ["NOT_A_VARIABLE"]},
                "vtk_variables: unknown variable(s) NOT_A_VARIABLE",
            ),
            ({"unexpected": True}, "unexpected: Extra inputs are not permitted"),
            (
                {"probes": [{"points": 1}]},
                "probes.0.points: Input should be greater than or equal to 2",
            ),
        ],
        ids=["P0400-MEMBER-LIST", "P0400-VTK", "P0400-EXTRA", "P0400-NESTED"],
    )
    def test_p0400_artifact_refusals_keep_the_public_class_and_message(entry, payload, message):
        with pytest.raises(InputArtifactError) as caught:
            if entry == "constructor":
                PprocArtifact(**payload)
            elif entry == "mapping":
                PprocArtifact.model_validate(payload)
            else:
                PprocArtifact.model_validate_json(json.dumps(payload))
        assert type(caught.value) is InputArtifactError
        assert isinstance(caught.value, PyflightstreamError)
        assert str(caught.value) == message
        assert caught.value.kind == "pproc"

    @staticmethod
    def test_p0400_artifact_loader_keeps_the_path_with_the_public_refusal(tmp_path):
        path = tmp_path / "pproc" / "p001.toml"
        path.parent.mkdir()
        path.write_text('[groups]\nBlade = ["Blade1"]\n', encoding="utf-8")
        with pytest.raises(InputArtifactError) as caught:
            resolve_pproc(tmp_path, "p001")
        assert str(path) in str(caught.value)
        assert 'Write Blade = "Blade1" instead.' in str(caught.value)
