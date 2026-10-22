"""Regression coverage grouped by subject."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import warnings
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.tier1_offline.test_restart_continuation as _run_1_continuation__fr96
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows import unsteady_export_threshold, workflow_registry
from pyflightstream.run import (
    CampaignErrors,
    ExecutionResult,
    ExecutorConfigurationError,
    LocalExecutor,
    SubmittingExecutor,
    SurfaceMeshExportError,
    cli,
    export_surface_mesh,
    reconstruct,
    records,
    render_descriptor,
    run_campaign,
)
from pyflightstream.run import _executors as executors
from pyflightstream.run import matrix as _run_2_matrix__run_matrix
from pyflightstream.run._actions_counter import render_program
from pyflightstream.run._batch_collect import _formatted
from pyflightstream.run._collect_logs import _profile_glob
from pyflightstream.run._continuation import _refuse_a_field_the_stopped_run_did_not_read
from pyflightstream.run._plan import _recorded_costs, estimate_point_cost, plan_campaign
from pyflightstream.run.collect import collect_once
from pyflightstream.run.matrix import run_matrix as _run_1_executors__run_matrix
from pyflightstream.run.matrix import run_matrix as _run_1_ids__run_matrix
from pyflightstream.run.records import mark_converged
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from pyflightstream.workspace.ledger import read_ledger
from pyflightstream.workspace.matrix import resolve_matrix
from pyflightstream.workspace.naming import RunsManifestError
from pyflightstream.workspace.record_document import encode_rows
from pyflightstream.workspace.storage import _compact_sim
from tests.support_helpers import no_sleep as _integfix_run1_review___no_sleep
from tests.support_helpers import no_sleep as _run_2_review__no_sleep
from tests.tier1_offline import test_p0350_run_id_alias as _run_1_plan__alias_tests
from tests.tier1_offline import test_p0350_run_id_alias as _run_1_review__alias_tests
from tests.tier1_offline.test_additional_post import (
    a_recorded_campaign as _run_2_review__a_recorded_campaign,
)
from tests.tier1_offline.test_additional_post import a_stub as _run_2_review__a_stub
from tests.tier1_offline.test_additional_post import extract as _run_2_review__extract
from tests.tier1_offline.test_collect_stage import (
    _submitted_workspace as _integfix_run1_review___submitted_workspace,
)
from tests.tier1_offline.test_g15_custom_freestream import field as _run_1_continuation__field
from tests.tier1_offline.test_g15_custom_freestream import (
    with_field as _run_1_continuation__with_field,
)
from tests.tier1_offline.test_goal024_freestream_rotation import RECIPES as _RUN_1_IDS__RECIPES
from tests.tier1_offline.test_goal024_freestream_rotation import (
    _rate_matrix as _run_1_ids___rate_matrix,
)
from tests.tier1_offline.test_goal024_profile_log import (
    _work_dir as _integfix_run1_review___work_dir,
)
from tests.tier1_offline.test_goal024_profile_log import (
    _write_profile as _integfix_run1_review___write_profile,
)
from tests.tier1_offline.test_goal024_walltime import _case as _run_2_submit___case
from tests.tier1_offline.test_goal024_walltime import _profile as _run_2_submit___profile
from tests.tier1_offline.test_matrix_run import RECIPES as _RUN_1_EXECUTORS__RECIPES
from tests.tier1_offline.test_matrix_run import (
    WRITES_EVERY_EXPORT as _RUN_1_IDS__WRITES_EVERY_EXPORT,
)
from tests.tier1_offline.test_matrix_run import CountingStub as _Run1IdsCountingStub
from tests.tier1_offline.test_matrix_run import (
    _steady_sweep_matrix as _run_1_executors___steady_sweep_matrix,
)
from tests.tier1_offline.test_matrix_run import converged as _run_1_executors__converged
from tests.tier1_offline.test_matrix_run import converged as _run_1_ids__converged
from tests.tier1_offline.test_p0320_b3_post_records import (
    _from_sims_workspace as _run_1_assemble___from_sims_workspace,
)
from tests.tier1_offline.test_p0350_batch_collect import _listing as _run_2_review___listing
from tests.tier1_offline.test_p0350_batch_collect import (
    _workspace as _integfix_run1_review___grouped_workspace,
)
from tests.tier1_offline.test_p0370_s1_mark_converged import REASON as _RUN_1_REVIEW__REASON
from tests.tier1_offline.test_p0370_s1_mark_converged import workspace as _run_1_review__workspace
from tests.tier1_offline.test_p0370_s1_matrix_home import (
    grouped_workspace as _run_2_review__grouped_workspace,
)
from tests.tier1_offline.test_plan_cost import saved_simulation as _run_1_plan__saved_simulation
from tests.tier1_offline.test_plan_cost import steady_case as _run_1_plan__steady_case
from tests.tier1_offline.test_regression_run_records import (
    _run_2_records___job_workspace as _run_2_review___job_workspace,
)
from tests.tier1_offline.test_regression_run_records import (
    _run_2_records___points_of as _run_2_review___points_of,
)
from tests.tier1_offline.test_restart_continuation import SAVED as _LAST6_CONTINUATION__SAVED
from tests.tier1_offline.test_restart_continuation import (
    _continuing_case as _last6_continuation___continuing_case,
)
from tests.tier1_offline.test_run_campaign import WRITES_LOADS as _RUN_1_POINTS__WRITES_LOADS
from tests.tier1_offline.test_run_campaign import StubSolver as _Run1PointsStubSolver
from tests.tier1_offline.test_run_campaign import converged as _run_1_points__converged
from tests.tier1_offline.test_run_campaign import make_campaign as _run_1_points__make_campaign
from tests.tier1_offline.test_run_campaign import steady_recipe as _run_1_points__steady_recipe
from tests.tier1_offline.test_submitted_additional_post import Scheduler as _Run2ReviewScheduler
from tests.tier1_offline.test_workflows import steady_case as _run_1_continuation__steady_case

_INTEGFIX_RUN1_REVIEW__PLACEHOLDERS = ["{sim.missing}", "{sim[bad]}", "{Sim}"]


def _integfix_run1_review___workspace_with_profile(tmp_path, placeholder, grouped):
    if grouped:
        workspace, _job_dir, _staged = _integfix_run1_review___grouped_workspace(
            tmp_path, "batch", written=()
        )
    else:
        workspace, sim = _integfix_run1_review___submitted_workspace(
            tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt")
        )
        (_integfix_run1_review___work_dir(workspace, sim) / "loads.txt").write_text(
            "data", encoding="utf-8"
        )
    _integfix_run1_review___write_profile(
        workspace, '[log]\nexport_log = false\nnative_log = "FTS' + placeholder + '.l*"\n'
    )
    return workspace


class TestIntegfixRun1Review:
    """Tier 1, 0.40.0 integration fix: the run-1 review findings R1-004 and R1-007 on the merged tree.

    R1-007 (PFS-2095.026): an invalid native_log access (``{sim.missing}``, ``{sim[bad]}``) is
    refused by name. In the integrated tree the profile reader refuses it when the profile is
    read (the item's acceptance), so collect stops before any point is touched, and the shared
    per-point formatter still turns any formatting failure into a refusal rather than a
    traceback. No solver runs.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize("placeholder", _INTEGFIX_RUN1_REVIEW__PLACEHOLDERS)
    @pytest.mark.parametrize("grouped", [False, True])
    def test_p0400_invalid_native_log_access_is_refused_before_any_point(
        tmp_path, placeholder, grouped
    ):
        """P0400-NATIVE-LOG-READ-REFUSAL (PFS-2095.026): named, and nothing recorded.

        The profile reader refuses a native_log placeholder outside {work_dir}, {batch}, {sim}
        and {point}; collect, ordinary or grouped, raises that named refusal and leaves the
        manifest as it found it, so a corrected profile collects the same points again.
        """
        workspace = _integfix_run1_review___workspace_with_profile(tmp_path, placeholder, grouped)
        before = workspace.manifest_path.read_bytes()
        with pytest.raises(InputArtifactError) as raised:
            collect_once(workspace, interval=0.0, sleep=_integfix_run1_review___no_sleep)
        assert "native_log" in str(raised.value) and placeholder in str(raised.value)
        assert workspace.manifest_path.read_bytes() == before

    @staticmethod
    @pytest.mark.parametrize("placeholder", ["{sim.missing}", "{sim[bad]}"])
    def test_p0400_invalid_native_log_access_cli_is_a_message_not_a_traceback(
        tmp_path, placeholder, capsys
    ):
        """P0400-NATIVE-LOG-CLI (PFS-2095.026): ``collect`` prints the refusal and exits 2."""
        workspace = _integfix_run1_review___workspace_with_profile(
            tmp_path, placeholder, grouped=False
        )
        status = cli.main(
            ["collect", "--workspace", str(workspace.root), "--interval", "0.001", "--no-post"]
        )
        captured = capsys.readouterr()
        assert status == 2
        assert "native_log" in captured.err and placeholder in captured.err
        # The banner's art says "Traceback"; a real one says "most recent call last".
        assert "most recent call last" not in captured.err + captured.out

    @staticmethod
    @pytest.mark.parametrize("pattern", ["FTS{sim.missing}.l*", "FTS{sim[bad]}.l*", "FTS{nope}.l*"])
    def test_p0400_shared_profile_glob_formatter_refuses_every_failure(pattern):
        """P0400-PROFILE-GLOB-FORMATTER (PFS-2095.026): one formatter, no exception escapes.

        AttributeError and TypeError join KeyError, IndexError and ValueError: the per-record
        formatter returns the refusal naming the profile key, and the grouped one, which calls
        it, returns None, for a pattern that reached collection without the read-time check.
        """
        glob, refusal = _profile_glob("native_log", pattern, {"sim": "9001", "point": "p"})
        assert glob is None and "native_log" in refusal and pattern in refusal
        job = {"values": {"sim": "9001", "batch": "b1"}}
        assert _formatted(pattern, job) is None  # type: ignore[arg-type]

    @staticmethod
    @pytest.mark.parametrize("pattern", ["/scratch/{sim}/log*", "C:/runs/{sim}/log*"])
    def test_x_f_1340_an_absolute_profile_glob_is_a_refusal_not_a_traceback(pattern):
        """A formatted pattern that is absolute would raise NotImplementedError from Path.glob."""
        glob, refusal = _profile_glob("native_log", pattern, {"sim": "9001", "point": "p"})
        assert glob is None and "absolute path" in refusal and "native_log" in refusal
        assert _profile_glob("native_log", "FTS{sim}.l*", {"sim": "9001"}) == ("FTS9001.l*", "")


def _last6_continuation___case(key, value, offset=250, owed=150):
    return _last6_continuation___continuing_case(
        "{FINISH_PENDING}",
        RESTART_FROM=_LAST6_CONTINUATION__SAVED,
        RESTART_ITERATIONS=str(owed),
        RESTART_STEP_OFFSET=str(offset),
        **{key: str(value)},
    )


class TestLast6Continuation:
    """Continuation thresholds must be reached by the continued march's local counter."""

    pytestmark = pytest.mark.requirement("P0400-LAST6-CONTINUATION")

    @staticmethod
    def test_p0400_last6_some_owed_count_reaches_last_iter_threshold(tmp_path):
        threshold = unsteady_export_threshold(
            _last6_continuation___case("EXPORT_UNSTEADY_LAST_ITER", 100), version="26.124"
        )
        scope = {"__file__": str(tmp_path / "counter.py"), "__name__": "counter"}
        exec(compile(render_program(threshold, interpreter="python"), "counter.py", "exec"), scope)
        assert any(scope["state"](count)["exporting"] for count in range(1, 151)), (
            "P0400-LAST6-OWED"
        )
        assert threshold.first_step == 51

    @staticmethod
    @pytest.mark.parametrize(
        "key,value,first",
        [
            ("EXPORT_UNSTEADY_LAST_ITER", 100, 51),
            ("EXPORT_UNSTEADY_AFTER_ITER", 300, 50),
        ],
    )
    def test_p0400_last6_last_and_after_iter_are_rebased(key, value, first):
        threshold = unsteady_export_threshold(
            _last6_continuation___case(key, value), version="26.124"
        )
        assert threshold.first_step == first, "P0400-LAST6-REBASE"
        assert threshold.time_iterations == 150
        assert threshold.program_value == first

    @staticmethod
    def test_p0400_last6_threshold_in_the_completed_span_is_refused():
        with pytest.raises(CampaignConfigError, match="already"):
            unsteady_export_threshold(
                _last6_continuation___case("EXPORT_UNSTEADY_AFTER_ITER", 200), version="26.124"
            )

    @staticmethod
    def test_p0400_last6_additional_run_last_window_ends_at_the_new_end():
        case = _last6_continuation___case("EXPORT_UNSTEADY_LAST_ITER", 50, offset=400, owed=120)
        case.variables["RESTART"] = "{ADDITIONAL_ITERS=120}"
        threshold = unsteady_export_threshold(case, version="26.124")
        assert threshold.first_step == 71, "P0400-LAST6-ADDITIONAL"

    @staticmethod
    def test_p0400_last6_legacy_chain_sums_its_predecessor_steps(tmp_path):
        from pyflightstream.run._continuation import _continued_step_offset
        from pyflightstream.workspace import CampaignWorkspace
        from tests.tier1_offline.test_restart_continuation import _stopped_record

        workspace = CampaignWorkspace.init(tmp_path / "chain")
        root = _stopped_record()
        child = root.model_copy(
            update={
                "run_id": "camp/sim_9001/rfirst/AL+000",
                "continues": root.run_id,
                "stopped_at": {"step": 20},
            }
        )
        workspace.append_record(root)
        workspace.append_record(child)
        assert _continued_step_offset(workspace, child) == 270, "P0400-LAST6-CHAIN"

    @staticmethod
    def test_p0400_last6_resolved_offset_reaches_the_planned_counter(tmp_path):
        from pyflightstream.cases import Campaign
        from pyflightstream.cases.workflows import build_script
        from pyflightstream.run import plan_campaign
        from pyflightstream.workspace import CampaignWorkspace
        from tests.tier1_offline.test_restart_continuation import _stopped_record

        workspace = CampaignWorkspace.init(tmp_path / "camp")
        previous = _stopped_record()
        workspace.append_record(previous)
        saved = workspace.sim_dir("9001") / previous.outputs[0]
        saved.parent.mkdir(parents=True)
        saved.write_bytes(b"saved")
        case = _last6_continuation___continuing_case(
            "{FINISH_PENDING}", EXPORT_UNSTEADY_LAST_ITER="100"
        )
        campaign = Campaign(name="camp", fs_version="26.124", fs_exe="solver.exe", sims=[case])
        seen = []

        def recipe(case, script):
            seen.append(unsteady_export_threshold(case, version=script.version))
            build_script(case, script)

        plan = plan_campaign(campaign, workspace, recipes={"unsteady": recipe}, write_plan=False)
        assert not plan.blocked, "P0400-LAST6-PLAN-OFFSET"
        assert seen[0].step_offset == 250
        assert seen[0].first_step == 51

    @staticmethod
    def test_f1457_an_undecodable_script_is_the_conservative_fallback(tmp_path):
        # Verifies F-1457: UnicodeDecodeError ends in None, as a missing script does.
        from pyflightstream.cases.workflows._rows import RestartRequest
        from pyflightstream.run._continuation_frame import recorded_requests
        from tests.tier1_offline.test_restart_continuation import _stopped_record

        earlier = _stopped_record()
        latest = earlier.model_copy(
            update={"run_id": "camp/sim_9001/r2/AL+000", "continues": earlier.run_id}
        )
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        script = workspace.sim_dir("9001") / str(latest.script_path)
        script.parent.mkdir(parents=True)
        script.write_bytes(b"\xff\xfe\x00 not utf-8")
        answered = recorded_requests(workspace, [earlier, latest])
        # A script that cannot be read answers the request, so it is not continued again.
        assert answered(latest, RestartRequest(form="FINISH_PENDING", value=None)) is True

    @staticmethod
    def test_f840_a_max_iter_reached_run_recovers_its_step_counter(tmp_path):
        # Verifies F-840: MAX_ITER_REACHED is continuable, so it may recover a missing counter.
        from pyflightstream.run._continuation import _continued_step_offset
        from tests.tier1_offline.test_restart_continuation import _stopped_record

        workspace = CampaignWorkspace.init(tmp_path / "camp")
        previous = _stopped_record().model_copy(
            update={"status": RunStatus.MAX_ITER_REACHED, "stopped_at": None}
        )
        workspace.append_record(previous)
        assert _continued_step_offset(workspace, previous) == 400

    @staticmethod
    def test_f601_a_replaced_saved_state_is_not_the_predecessor(tmp_path):
        # Verifies F-601: the saved simulation's bytes are held to the digest the run recorded.
        from pyflightstream.cases import Campaign
        from pyflightstream.cases.workflows import build_script
        from pyflightstream.run import plan_campaign
        from tests.tier1_offline.test_restart_continuation import _stopped_record

        def planned(body):
            workspace = CampaignWorkspace.init(tmp_path / f"camp-{len(body)}")
            previous = _stopped_record()
            previous = previous.model_copy(
                update={"outputs_sha256": {previous.outputs[0]: sha256(b"original").hexdigest()}}
            )
            workspace.append_record(previous)
            saved = workspace.sim_dir("9001") / previous.outputs[0]
            saved.parent.mkdir(parents=True)
            saved.write_bytes(body)
            case = _last6_continuation___continuing_case("{FINISH_PENDING}")
            campaign = Campaign(name="camp", fs_version="26.124", fs_exe="solver.exe", sims=[case])
            return plan_campaign(
                campaign, workspace, recipes={"unsteady": build_script}, write_plan=False
            )

        assert not planned(b"original").blocked
        blocked = planned(b"replaced-bytes").blocked
        assert [entry.error for entry in blocked if "digest" in str(entry.error)], blocked

    @staticmethod
    def test_p0400_last6_rebased_step_is_written_to_the_run_record(tmp_path):
        from pyflightstream.cases.workflows import build_script
        from pyflightstream.run._actions_counter import stage_counter
        from pyflightstream.script import Script

        case = _last6_continuation___case("EXPORT_UNSTEADY_LAST_ITER", 100)
        script = Script("26.124")
        build_script(case, script)
        for name, text in script.pending_action_scripts.items():
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        fields = stage_counter(tmp_path, script, case, "26.124", {})
        assert fields["export_window"]["first_step"] == 51, "P0400-LAST6-PERSISTED-REBASE"
        assert fields["export_window"]["time_iterations"] == 150
        assert fields["export_window"]["step_offset"] == 250


def _run_1_alias___rows(root, rows):
    (root / "runs.json").write_text(json.dumps(encode_rows(rows)), encoding="utf-8")


class TestRun1Alias:
    """Tier 1, 0.40.0 lane run-1: the run id alias ``<sim>_<index>`` (FR-395).

    Every fixture is synthetic: a ``runs.json`` and ``plan.json`` written by hand, or the
    two-simulation steady matrix of the 0.34.0 tests with a stub for the solver.
    """

    @staticmethod
    def test_p0400_a_known_simulation_id_with_an_underscore_is_not_an_alias(tmp_path):
        # Verifies FR-395.
        """P0400-ALIAS-SIM-UNDERSCORE (PFS-2094.028): ``2006_1`` beside ``2006`` names the simulation.

        Simulation ids may hold an underscore; a destroying verb read ``2006_1`` as point 1 of
        simulation 2006, so ``mark-failed --sims 2006_1`` marked the wrong simulation's point.
        """  # noqa: E501
        from pyflightstream.run._alias import read_alias, split_typed_ids

        assert read_alias("2006_1", {"2006", "2006_1"}) is None
        assert read_alias("2006_1", {"2006"}) == ("2006", 1)
        _run_1_alias___rows(
            tmp_path,
            [
                {"run_id": "warm/sim_2006/P1", "sim_id": "2006", "status": "CONVERGED"},
                {"run_id": "warm/sim_2006_1/P1", "sim_id": "2006_1", "status": "CONVERGED"},
            ],
        )
        assert split_typed_ids(["2006_1"], tmp_path) == (["2006_1"], {})
        assert split_typed_ids(["2006_1"], tmp_path, whole_only=True) == (["2006_1"], {})

    @staticmethod
    def test_p0430_a_digit_like_unicode_suffix_is_not_an_alias():
        # Verifies FR-395.
        """F-1561: a suffix that ``str.isdigit`` accepts and ``int`` cannot read is no alias.

        A superscript two passed the digit check and then raised ValueError in ``int``,
        against the documented None return for a text that is not an alias.
        """
        from pyflightstream.run._alias import read_alias

        assert read_alias("2006_²", {"2006"}) is None
        assert read_alias("2006_١", {"2006"}) is None
        assert read_alias("2006_2", {"2006"}) == ("2006", 2)

    @staticmethod
    def test_p0400_the_failure_alias_is_the_one_every_reader_resolves(tmp_path):
        """P0400-ALIAS-ONE-READING (PFS-2094.004, PFS-2089.008): records out of sweep order.

        Alpha 0 and 4 are recorded, the matrix gains alpha 2, and the resumed run fails it. The
        failure line named ``2006_3`` from the record order while ``mark-failed``, ``show`` and
        the plan read ``2006_3`` as alpha 4. Every reader now builds its planned order with
        one function, and the failure line names ``2006_2``, which resolves back to alpha 2.
        """
        from pyflightstream.run._alias import (
            failure_alias_lines,
            planned_in_workspace,
            split_typed_ids,
        )
        from pyflightstream.run._cli_query_point import _aliases

        plan = {
            "points": [
                {"sim_id": "2006", "run_id": f"warm/sim_2006/{tag}"} for tag in ("A0", "A2", "A4")
            ]
        }
        (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        rows = [
            {"run_id": f"warm/sim_2006/{tag}", "sim_id": "2006", "status": status}
            for tag, status in (
                ("A0", "CONVERGED"),
                ("A4", "CONVERGED"),
                ("A2", "FAILED_EXECUTION"),
            )
        ]
        _run_1_alias___rows(tmp_path, rows)
        failed = SimpleNamespace(sim_id="2006", run_id="warm/sim_2006/A2")
        assert failure_alias_lines([failed], rows, tmp_path) == [
            "  alias 2006_2 = warm/sim_2006/A2"
        ]
        assert split_typed_ids(["2006_2"], tmp_path) == ([], {"2006": ["A2"]})
        assert _aliases(read_ledger(tmp_path))["2006_2"] == ("2006", "A2")
        assert planned_in_workspace(tmp_path, rows) == {"2006": ["A0", "A2", "A4"]}

    @staticmethod
    def test_p0400_a_plan_of_a_selection_numbers_aliases_against_the_whole_sweep(
        tmp_path, monkeypatch
    ):
        """P0400-ALIAS-WHOLE-SWEEP (PFS-2094.034, PFS-2094.029): plan the third point alone.

        The plan narrowed to ``--points <third>`` printed ``5002_1`` beside it and wrote only it
        into ``plan.json``, so ``show`` and ``mark-failed`` read ``5002_1`` as the third point
        while ``run --points 5002_1`` ran the first. Given the whole sweep, the plan prints
        ``5002_3`` and ``plan.json`` carries the whole sweep for every later reader.
        """
        from pyflightstream.run._alias import planned_in_workspace, selection_with_aliases
        from pyflightstream.run._cli_print import _alias_block
        from pyflightstream.run._ids import narrow_to_selection, whole_sweeps
        from tests.tier1_offline.test_p0340_run_usability import _names, _two_simulations

        workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
        names = _names(workspace, matrix, "5002")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            resolved = resolve_matrix(
                matrix,
                workspace,
                name="warm",
                fs_version="26.120",
                recipes={},
                ignore_missing_families=True,
            )
            whole = whole_sweeps(resolved)
            narrowed = narrow_to_selection(resolved, ["5002"], [names[2]], workspace)
            plan = plan_campaign(
                narrowed.campaign, workspace, matrix_path=matrix, planned_order=whole
            )
        assert [entry.run_id.rsplit("/", 1)[-1] for entry in plan.points] == [names[2]]
        assert _alias_block(plan, []) == [f"  5002_3  POL 5002 {names[2]}"]
        assert planned_in_workspace(workspace.root, [])["5002"] == names
        run_side = selection_with_aliases(["5002"], ["5002_3"], [], whole)
        assert run_side == (["5002"], [names[2]])


def _run_1_assemble___judged(workspace):
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    steady = sorted(
        (record for record in assembled if record.sim_id == "6001"),
        key=lambda record: record.point["alpha"],
    )
    return [(record.status, record.error) for record in steady], refusals


class TestRun1Assemble:
    """Tier 1, 0.40.0 lane run-1: ``post --from-sims`` assembles records from the simulation folders.

    The from-sims workspace of the 0.32.0 tests: a steady polar run outside the package, its
    exports under ``sims/sim_6001/outputs/`` and no ``runs.json``.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize("folder", ["", "run1"])
    def test_p0400_an_export_outside_the_assessors_folders_is_judged_where_it_was_found(
        tmp_path, folder
    ):
        """P0400-FROM-SIMS-FOLDER (PFS-2103.017): exports in ``sims/sim_X/`` or ``sims/sim_X/run1/``.

        The assessor read only ``datapoints/DP-<name>/``, ``outputs/`` and ``raw/``, so an
        export anywhere else read as no output and the point was FAILED_INCOMPLETE_OUTPUT
        ("no single collected output reads as a loads table"). Each layout is now judged as
        the ``outputs/`` layout is (the control).
        """  # noqa: E501
        control, _ = _run_1_assemble___judged(
            _run_1_assemble___from_sims_workspace(tmp_path / "control")
        )
        assert len(control) == 2
        workspace = _run_1_assemble___from_sims_workspace(tmp_path / "moved")
        sim = workspace.sim_dir("6001")
        target = sim / folder
        target.mkdir(exist_ok=True)
        for path in sorted((sim / "outputs").iterdir()):
            path.replace(target / path.name)
        moved, refusals = _run_1_assemble___judged(workspace)
        assert moved == control, refusals
        assert not any("reads as a loads table" in str(error) for _status, error in moved)

    @staticmethod
    def test_p0400_post_from_sims_restores_a_compacted_simulation(tmp_path):
        """P0400-FROM-SIMS-COMPACTED (PFS-2103.019): ``sims/sim_6001.zip`` is read, not skipped."""
        control, _ = _run_1_assemble___judged(
            _run_1_assemble___from_sims_workspace(tmp_path / "control")
        )
        workspace = _run_1_assemble___from_sims_workspace(tmp_path / "compacted")
        _compact_sim(workspace, "6001")
        assert not workspace.sim_dir("6001").exists()
        compacted, refusals = _run_1_assemble___judged(workspace)
        assert compacted == control, refusals
        assert workspace.sim_dir("6001").is_dir()

    @staticmethod
    def test_p0400_post_from_sims_refuses_a_compacted_simulation_it_cannot_restore(tmp_path):
        """P0400-FROM-SIMS-COMPACTED (PFS-2103.019): a broken archive is a refusal naming it."""
        workspace = _run_1_assemble___from_sims_workspace(tmp_path)
        _compact_sim(workspace, "6001")
        archive = workspace.root / "sims" / "sim_6001.zip"
        archive.write_bytes(b"not a zip")
        assembled, refusals = records.assemble_records(workspace.root, "matriz")
        assert "6001" not in {record.sim_id for record in assembled}
        assert "sims/sim_6001.zip" in refusals["sims/sim_6001"]


class TestRun1Continuation:
    """Tier 1, 0.40.0 lane run-1: continuing a recorded point (RESTART).

    Synthetic cases and records; no solver runs.
    """

    @staticmethod
    def test_p0400_a_changed_units_declaration_is_refused_naming_the_point(tmp_path):
        """P0400-CONTINUATION-UNITS-NAMED (PFS-2100.015): case, point, run, both declarations.

        The refusal named neither the point nor the two declarations, so a person continuing
        a campaign could not tell which row to correct, or to what.
        """
        source = _run_1_continuation__field(tmp_path)
        case = _run_1_continuation__with_field(
            _run_1_continuation__steady_case(), source
        ).model_copy(update={"freestream_units": "SI"})
        previous = SimpleNamespace(
            run_id="c/sim_9001/AL+000",
            inputs_sha256={source.name: sha256(source.read_bytes()).hexdigest()},
            freestream_units="NATIVE",
        )
        with pytest.raises(CampaignConfigError) as refused:
            _refuse_a_field_the_stopped_run_did_not_read(case, "AL+000", previous)
        message = str(refused.value)
        for part in (repr(case.sim_id), "AL+000", "'c/sim_9001/AL+000'", "'SI'", "'NATIVE'"):
            assert part in message, (part, message)
        assert "Restore the declaration" in message and "RESTART" in message

    @staticmethod
    def test_p0400_a_ran_missing_log_march_is_not_continued_as_converged():
        """P0400-RAN-MISSING-LOG-NOT-CONTINUED (PFS-2103.025): ADDITIONAL_REVS on RAN_MISSING_LOG.

        The verdict announced 'continuing a CONVERGED unsteady run' for a run whose log is
        absent, which FR-413 says is never CONVERGED by assumption, and continued it although
        the continuable set excludes it. It is now refused naming its status; the control, a
        CONVERGED march, is continued with the words it had.
        """
        verdict = _run_1_continuation__fr96._fr96_converged_continuation___verdict(
            "ADDITIONAL_REVS=1",
            _run_1_continuation__fr96._fr96_converged_continuation___record(
                RunStatus.RAN_MISSING_LOG
            ),
        )
        assert not verdict.pending
        assert "RAN_MISSING_LOG" in str(verdict.said) and "CONVERGED" not in str(verdict.said)
        control = _run_1_continuation__fr96._fr96_converged_continuation___verdict(
            "ADDITIONAL_REVS=1",
            _run_1_continuation__fr96._fr96_converged_continuation___record(RunStatus.CONVERGED),
        )
        assert control.pending
        assert (
            control.said
            == f"continuing a CONVERGED unsteady run, {_run_1_continuation__fr96._FR96_CONVERGED_CONTINUATION__POINT!r}, by 1 revolution(s)"  # noqa: E501
        )


_RUN_1_EXECUTORS__VALUES = {"sim": "mtx_b1", "ncpus": 8, "fs_build": "26.124", "ratio": 0.5}


def _run_1_executors___fields(fmt: str) -> SimpleNamespace:
    return SimpleNamespace(
        fields={
            "job_name": "FTS{sim}",
            "ncpus": "{ncpus}",
            "ratio": "{ratio}",
            "version": "{fs_build}",
            "driveg": True,
        },
        descriptor_format=fmt,
        path="h.toml",
    )


_RUN_1_EXECUTORS__PROFILE = """\
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
job_name = "FTS{sim}"

[submit]
command = COMMAND
"""


def _run_1_executors___profile(tmp_path: Path, command: str, extra: str = ""):
    path = tmp_path / "inputs" / "hpc" / "h001.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_RUN_1_EXECUTORS__PROFILE.replace("COMMAND", command) + extra, encoding="utf-8")
    return path


class _Run1ExecutorsSaysOnStdout:
    def run_script(self, script_path, working_dir, timeout_s=None) -> ExecutionResult:
        return ExecutionResult(
            return_code=3,
            wall_time_s=0.1,
            timed_out=False,
            log_text=None,
            stdout="unknown argument -scrpt",
            stderr="",
        )


class TestRun1Executors:
    """Tier 1, 0.40.0 lane run-1: the executors (descriptors, submission, the local run's log).

    Synthetic profiles, scripts and stand-in programs; no solver runs.
    """

    @staticmethod
    def test_p0400_json_and_toml_descriptors_write_numbers_and_booleans_bare():
        """P0400-DESCRIPTOR-TYPES (PFS-2094.009): the yaml rule of 0.35.0, in json and toml.

        json wrote ``"driveg": "true"`` and ``"ncpus": "8"``, toml ``ncpus = "8"``: the cluster
        reads a string where it expects the switch or the count. A build identifier, which reads
        as a number and is text, stays quoted (the control).
        """
        payload = json.loads(
            render_descriptor(_run_1_executors___fields("json"), _RUN_1_EXECUTORS__VALUES)
        )
        assert payload == {
            "job_name": "FTSmtx_b1",
            "ncpus": 8,
            "ratio": 0.5,
            "version": "26.124",
            "driveg": True,
        }
        toml = render_descriptor(_run_1_executors___fields("toml"), _RUN_1_EXECUTORS__VALUES)
        assert "ncpus = 8\n" in toml and "ratio = 0.5\n" in toml and "driveg = true\n" in toml
        assert 'version = "26.124"\n' in toml and 'job_name = "FTSmtx_b1"\n' in toml

    @staticmethod
    def test_p0400_a_submit_placeholder_no_run_supplies_is_refused_at_construction(tmp_path):
        """P0400-SUBMIT-PLACEHOLDERS (PFS-2094.010): ``{queue}`` in the submit command.

        It was a KeyError at the first point's submission, after earlier rows were submitted;
        it is now refused when the executor is built, naming the profile and the name.
        """
        profile = read_hpc_profile(
            _run_1_executors___profile(tmp_path, '["esub", "-q", "{queue}", "{descriptor_path}"]')
        )
        with pytest.raises(ExecutorConfigurationError, match=r"\{queue\}"):
            SubmittingExecutor(profile, values={"fs_build": "26.120"})
        # The control: a name the run supplies is accepted.
        good = read_hpc_profile(
            _run_1_executors___profile(tmp_path, '["esub", "{ncpus}", "{descriptor_path}"]')
        )
        SubmittingExecutor(good, values={"fs_build": "26.120"})

    @staticmethod
    def test_p0400_a_point_the_submit_command_cannot_name_is_refused_by_name(tmp_path):
        """P0400-SUBMIT-PLACEHOLDERS (PFS-2094.010): ``{walltime}`` and a row that states none.

        The KeyError of the argv format left the campaign as a traceback; it is now the
        package's refusal naming the profile and what the point can supply, returned as
        this point's failed result (PFS-2094.037) with no descriptor written.
        """
        profile = read_hpc_profile(
            _run_1_executors___profile(tmp_path, '["esub", "--time={walltime}"]')
        )
        executor = SubmittingExecutor(profile, values={"fs_build": "26.120"}, submit=False)
        executor.bind_point({"sim": "5001", "point": "AL+000"}, replace=True)
        script = tmp_path / "s.txt"
        script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
        result = executor.run_script(script, tmp_path / "work")
        assert result.failed and result.return_code == 2, result
        assert "{walltime}" in result.stderr and "h001.toml" in result.stderr, result.stderr
        assert "What it can:" in result.stderr, result.stderr
        assert executor.descriptor_path is None
        assert not (tmp_path / "work" / profile.descriptor_name).exists()

    @staticmethod
    def test_p0400_a_submit_command_that_hangs_is_this_points_failure(tmp_path):
        """P0400-SUBMIT-TIMEOUT (PFS-2094.010): TimeoutExpired was not caught and ended the campaign."""  # noqa: E501
        program = Path(sys.executable).as_posix()
        command = f'["{program}", "-c", "import time; time.sleep(30)", "{{descriptor_path}}"]'
        profile = read_hpc_profile(_run_1_executors___profile(tmp_path, command))
        executor = SubmittingExecutor(profile, values={"fs_build": "26.120"})
        executor.bind_point({"sim": "5001", "point": "AL+000"}, replace=True)
        script = tmp_path / "s.txt"
        script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
        result = executor.run_script(script, tmp_path / "work", timeout_s=1.0)
        assert result.failed and result.timed_out
        assert "did not return within" in result.stderr

    @staticmethod
    def test_p0400_a_refused_submission_is_the_rows_record_and_the_run_returns(tmp_path):
        """P0400-SUBMIT-REFUSAL-RECORDED (PFS-2094.010): a descriptor field this row cannot fill.

        The refusal raised inside run_script left the campaign loop with no record for the row,
        after earlier rows were submitted; the row is now recorded as this point's failed
        submission (FAILED_EXECUTION, PFS-2094.037), naming it, and run_matrix returns.
        """
        workspace, matrix = _run_1_executors___steady_sweep_matrix(tmp_path)
        path = _run_1_executors___profile(tmp_path / "w", '["esub", "{descriptor_path}"]')
        text = path.read_text(encoding="utf-8").replace(
            'job_name = "FTS{sim}"', 'job_name = "FTS{sim}"\nwalltime = "{walltime}"'
        )
        path.write_text(text, encoding="utf-8")
        executor = SubmittingExecutor(read_hpc_profile(path), values={"fs_build": "26.120"})
        # A campaign whose points failed ends as every such campaign does, with its records.
        with pytest.raises(CampaignErrors) as failed:
            _run_1_executors__run_matrix(
                matrix,
                workspace,
                name="cluster",
                default_fs_version="26.120",
                recipes=_RUN_1_EXECUTORS__RECIPES,
                recipe_registry=workflow_registry(),
                assess=_run_1_executors__converged,
                executor=executor,
            )
        records = failed.value.records
        assert records and all(r.status is RunStatus.FAILED_EXECUTION for r in records), records
        assert all("walltime" in (r.error or "") for r in records)
        assert [r.run_id for r in workspace.read_manifest()] == [r.run_id for r in records]

    @staticmethod
    def test_p0400_a_relative_script_is_read_from_the_working_directory(tmp_path, monkeypatch):
        """P0400-LOCAL-RELATIVE-SCRIPT (PFS-2094.011): the steady coupled check reads it as the solver.

        The check opened the relative path against this process's directory, found nothing and
        took the ordinary path, while the solver read the coupled script from its own directory.
        """  # noqa: E501
        work = tmp_path / "work"
        work.mkdir()
        (work / "coupled.txt").write_text("EXECUTE_AEROELASTIC_ANALYSIS\n", encoding="utf-8")
        seen: list[Path] = []
        monkeypatch.setattr(
            executors, "_a_steady_coupled_script", lambda path: seen.append(Path(path)) or False
        )
        monkeypatch.chdir(tmp_path)
        stub = tmp_path / "stub.py"
        stub.write_text("", encoding="utf-8")
        executor = LocalExecutor(sys.executable)
        monkeypatch.setattr(executor, "_argv", lambda script: [sys.executable, str(stub)])
        executor.run_script(Path("coupled.txt"), working_dir=work)
        assert seen == [work / "coupled.txt"]

    @staticmethod
    def test_p0400_a_log_an_earlier_attempt_left_is_not_this_runs_log(tmp_path, monkeypatch):
        """P0400-STALE-SOLVER-LOG (PFS-2103.003): a planted FlightStreamLog.txt is not read.

        The file was read as this run's log whenever it existed, so an earlier attempt's text
        was quoted as this run's evidence. A log the run writes is read (the control).
        """
        work = tmp_path / "work"
        work.mkdir()
        stale = work / "FlightStreamLog.txt"
        stale.write_text("an earlier attempt's log", encoding="utf-8")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        quiet = tmp_path / "quiet.py"
        quiet.write_text("", encoding="utf-8")
        writes = tmp_path / "writes.py"
        writes.write_text(
            "from pathlib import Path\nPath('FlightStreamLog.txt').write_text('this run')\n",
            encoding="utf-8",
        )
        executor = LocalExecutor(sys.executable)
        monkeypatch.setattr(executor, "_argv", lambda script: [sys.executable, str(quiet)])
        script = work / "s.txt"
        script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
        assert executor.run_script(script, working_dir=work).log_text is None
        assert stale.read_text(encoding="utf-8") == "an earlier attempt's log", "evidence kept"
        monkeypatch.setattr(executor, "_argv", lambda script: [sys.executable, str(writes)])
        assert executor.run_script(script, working_dir=work).log_text == "this run"

    @staticmethod
    def test_p0400_a_mesh_export_failure_quotes_what_the_run_printed(tmp_path):
        """P0400-MESH-EXPORT-DIAGNOSIS (PFS-2094.012): a failure before the script is accepted.

        Only stdout carries it, and the refusal quoted the log alone, so it read ``''``. It is
        now the one sentence ExecutionResult.diagnosis composes.
        """
        with pytest.raises(SurfaceMeshExportError) as refused:
            export_surface_mesh(
                tmp_path / "case.fsm",
                tmp_path / "pre",
                version="26.120",
                executor=_Run1ExecutorsSaysOnStdout(),
            )
        message = str(refused.value)
        assert "unknown argument -scrpt" in message and "return code 3" in message, message
        assert "was not written" in message


def _run_1_ids___free_stream_words(text: str) -> list[str]:
    line = next(line.strip() for line in text.splitlines() if line.startswith("SET_FREESTREAM"))
    return line.split()


class TestRun1Ids:
    """Tier 1, 0.40.0 lane run-1: which steady rows run as one warm job (``_ids``).

    The one-row rate matrix of the 0.24.0 rotation tests, run through ``run_matrix`` with a
    stub standing in for the solver.
    """

    @staticmethod
    def test_p0400_a_steady_row_sweeping_a_body_rate_runs_one_point_per_rate(tmp_path):
        """P0400-RATE-SWEEP-ONE-JOB (PFS-2104.044): ``pitch_rate:sweep`` over 2 and 4 deg/s.

        The row ran as one warm job whose free stream was set once, at the first point's rate,
        and every later point was recorded under its own rate. Each point now has its own
        script, whose SET_FREESTREAM ROTATION turns at that point's rate.
        """
        workspace, matrix = _run_1_ids___rate_matrix(
            tmp_path,
            condition="MACH:0.2, REmi:2.3, ALPHA:0.0, pitch_rate:sweep",
            values="2.0,4.0",
        )
        records = _run_1_ids__run_matrix(
            matrix,
            workspace,
            name="turning",
            default_fs_version="26.120",
            recipes=_RUN_1_IDS__RECIPES,
            recipe_registry=workflow_registry(),
            assess=_run_1_ids__converged,
            executor=_Run1IdsCountingStub(_RUN_1_IDS__WRITES_EVERY_EXPORT),
        )
        assert [r.run_id.rsplit("/", 1)[-1] for r in records] == [
            "M200RE230AL+000Q+020",
            "M200RE230AL+000Q+040",
        ]
        scripts = sorted((workspace.sim_dir("3207") / "scripts").glob("*.txt"))
        assert len(scripts) == 2, scripts
        rates = []
        for script in scripts:
            words = _run_1_ids___free_stream_words(script.read_text(encoding="utf-8"))
            assert words[:2] == ["SET_FREESTREAM", "ROTATION"], words
            rates.append(float(words[4]) * 360.0 / 60.0)
        assert sorted(rates) == pytest.approx([2.0, 4.0])


class TestRun1Plan:
    """Tier 1, 0.40.0 lane run-1: the plan's cost estimate (FR-82).

    A fresh workspace with hand-written records; no solver runs.
    """

    @staticmethod
    def test_p0400_the_estimate_learns_nothing_from_a_run_that_did_not_end(tmp_path):
        # Verifies FR-82.
        """P0400-COST-SAMPLES (PFS-2094.014): a fast failure and a run stopped by its clock.

        Every record with a wall time was a sample, so a FAILED_EXECUTION after one second, a
        WALLTIME_REACHED at the clock and a person's FAILED_MARKED moved the estimate, against
        restore-and-rebuild.md. The control is the CONVERGED run alone: 10 s, one sample.
        """
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        for tag, status, seconds in (
            ("A0", RunStatus.CONVERGED, 10.0),
            ("A1", RunStatus.FAILED_EXECUTION, 1.0),
            ("A2", RunStatus.WALLTIME_REACHED, 600.0),
            ("A3", RunStatus.FAILED_MARKED, 5.0),
            ("A4", RunStatus.RAN_MISSING_LOG, 50.0),
        ):
            record = _run_1_plan__alias_tests._record("2006", f"warm/sim_2006/{tag}", status=status)
            workspace.append_record(
                record.model_copy(update={"wall_time_s": seconds, "recipe": "steady"})
            )
        samples = _recorded_costs(workspace)
        assert [row["run_id"] for row in samples] == ["warm/sim_2006/A0"]
        geometry = _run_1_plan__saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
        estimate = estimate_point_cost(
            _run_1_plan__steady_case(geometry), run_id="run/a", recorded=samples, steps_by_run={}
        )
        assert estimate.samples == 1
        assert estimate.seconds == pytest.approx(10.0)


class TestRun1Points:
    """Tier 1, 0.40.0 lane run-1: what a point's record says, and what reconstruct reads back.

    A campaign run with the stub solver of the run tests; no solver runs.
    """

    @staticmethod
    def test_p0400_reconstruct_finds_an_inherited_probe_layout_where_it_lives(tmp_path):
        """P0400-RECONSTRUCT-PROBE-LAYOUT (PFS-2103.027): a key with a folder part.

        A continuation that inherits a probe field layout records it under
        ``profiles/<sim>_probe_points.csv``, relative to the simulation folder; reconstruct
        looked for it in the point's own folder and called it missing while it was on disk.
        """
        campaign = _run_1_points__make_campaign(tmp_path, alphas=(0.0,))
        workspace = CampaignWorkspace(tmp_path / "camp")
        run_campaign(
            campaign,
            _Run1PointsStubSolver(_RUN_1_POINTS__WRITES_LOADS),
            workspace,
            assess=_run_1_points__converged,
            recipes={"steady": _run_1_points__steady_recipe},
        )
        record = workspace.read_manifest()[0]
        layout = workspace.sim_dir("9001") / "profiles" / "9001_probe_points.csv"
        layout.parent.mkdir(parents=True, exist_ok=True)
        layout.write_text("x,y,z\n0,0,0\n", encoding="utf-8")
        key = "profiles/9001_probe_points.csv"
        digest = hashlib.sha256(layout.read_bytes()).hexdigest()
        record = record.model_copy(update={"inputs_sha256": {**record.inputs_sha256, key: digest}})
        rebuilt = reconstruct(record, workspace=workspace)
        assert rebuilt.verified[f"inputs/{key}"] == "match", rebuilt.verified
        assert rebuilt.faithful


def _run_2_matrix___resolved(builds: dict[str, str | None]):
    """A bound matrix of one row per build, each registered as a bare path or with a version."""
    sims = [SimpleNamespace(sim_id=f"700{index}") for index in range(1, len(builds) + 1)]
    return SimpleNamespace(
        campaign=SimpleNamespace(sims=sims),
        row_builds=list(builds),
        builds={build: SimpleNamespace(fs_version=version) for build, version in builds.items()},
    )


class TestRun2Matrix:
    """Tier 1, 0.40.0 lane run-2: the matrix entry points (plan, run, additional post).

    Every fixture is synthetic.
    """

    @staticmethod
    def test_p0400_preflight_versions_follow_the_run_s_fallback_chain():
        """P0400-ROW-VERSIONS (PFS-2094.018): the pre-flight version is the one the run emits under.

        With no default and two bare-path builds, the run emits each row under
        its build id (_bind_row_builds); the pre-flight gave such rows no version
        of their own, so they were pre-flighted under the first row's build.
        """
        resolved = _run_2_matrix___resolved({"26.120": None, "26.124": None})
        assert _run_2_matrix__run_matrix._row_versions(resolved) == {
            "7001": "26.120",
            "7002": "26.124",
        }
        assert _run_2_matrix__run_matrix._row_versions(resolved, "26.123") == {
            "7001": "26.123",
            "7002": "26.123",
        }
        declared = _run_2_matrix___resolved({"26.120": "26.120.1", "26.124": None})
        assert _run_2_matrix__run_matrix._row_versions(declared) == {
            "7001": "26.120.1",
            "7002": "26.124",
        }

    @staticmethod
    def test_p0400_a_local_extraction_with_a_translation_problem_fails_as_a_collected_one(
        tmp_path, monkeypatch
    ):
        """P0400-EXTRACTION-ONE-RULE (PFS-2103.008): the local path refuses a translation problem.

        The collected path fails an extraction whose stamped translation reports a
        problem; the local path judged by file existence alone and recorded it
        EXTRACTED, deleting the private copy first. Both now complete by one rule.
        """
        from pyflightstream.run import _additional
        from tests.tier1_offline.test_additional_post import (
            POST_ADDITIONAL_TOML,
            a_recorded_campaign,
            a_stub,
            extract,
        )

        def refused(folder, translations):
            for entry in translations:
                (folder / str(entry["dat"])).write_text("preserved surface export", "utf-8")
            return [
                {**entry, "written": [], "problems": ["the frame changed"]}
                for entry in translations
            ]

        workspace, matrix = a_recorded_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
        monkeypatch.setattr(_additional, "translate_surface_exports", refused)
        monkeypatch.setattr(
            _run_2_matrix__run_matrix, "translate_surface_exports", refused, raising=False
        )
        _, records = extract(workspace, matrix, a_stub(tmp_path))
        assert records and {record.status for record in records} == {"FAILED_EXECUTION"}, [
            (record.status, record.error) for record in records
        ]
        assert all("the frame changed" in (record.error or "") for record in records)
        for record in records:
            folder = workspace.sim_dir(record.sim_id) / record.working_dir
            assert list(folder.glob("*.reopened.fsm")), "the private copy was deleted"


class TestRun2Review:
    """P0400 regressions for the adversarial review of lane run-2."""

    @staticmethod
    def test_p0400_mark_whole_job_after_marking_one_point(tmp_path):
        workspace = _run_2_review___job_workspace(tmp_path)
        records.mark_failed(
            workspace.root, [], points={"5001": ["AL+005"]}, reason="first", apply=True
        )
        result = records.mark_failed(workspace.root, ["5001"], reason="whole", apply=True)
        assert set(_run_2_review___points_of(workspace, "5001").values()) == {"FAILED_MARKED"}
        assert len(result["marked"]) == 2
        row = next(r for r in workspace.read_raw_manifest() if r.get("sim_id") == "5001")
        assert row["points_ran"][1]["marked"]["reason"] == "first"
        assert not records.mark_failed(workspace.root, ["5001"], apply=True)["applied"]

    @staticmethod
    def test_p0400_ended_batch_moves_only_selected_simulations(tmp_path):
        workspace = _run_2_review__grouped_workspace(tmp_path, mode="batch", collect=False)
        row = next(r for r in workspace.read_manifest() if r.sim_id == "7003")
        batch = workspace.root / row.submission["job"]["dir"]
        other = batch / "sim_7003"
        before = _run_2_review___listing(other)
        collect_once(workspace, sims=["7001"], interval=0, sleep=_run_2_review__no_sleep)
        assert not (batch / "sim_7001").exists()
        assert other.is_dir(), "an unselected simulation was moved"
        assert _run_2_review___listing(other) == before
        assert (
            next(r for r in workspace.read_manifest() if r.sim_id == "7003").status == "SUBMITTED"
        )

    @staticmethod
    def test_p0400_ended_batch_moves_home_after_every_point_completed(tmp_path):
        workspace = _run_2_review__grouped_workspace(
            tmp_path, mode="batch", collect=False, ended=False
        )
        row = workspace.read_manifest()[0]
        job = row.submission["job"]
        batch = workspace.root / job["dir"]
        collect_once(workspace, interval=0, sleep=_run_2_review__no_sleep)
        assert all(r.status != "SUBMITTED" for r in workspace.read_manifest())
        assert (batch / "sim_7001").exists()
        (batch / f"{Path(job['script']).stem}.end.json").write_text('{"return_code": 0}')
        collect_once(workspace, interval=0, sleep=_run_2_review__no_sleep)
        assert not (batch / "sim_7001").exists()
        assert not (batch / "sim_7003").exists()

    @staticmethod
    def test_p0400_pending_extraction_is_skipped_and_not_reported_launched(tmp_path):
        workspace, matrix = _run_2_review__a_recorded_campaign(tmp_path, values="0.0")
        scheduler = _Run2ReviewScheduler()
        _, first = _run_2_review__extract(workspace, matrix, scheduler)
        before = workspace.read_additional()
        plans, repeated = _run_2_review__extract(workspace, matrix, scheduler)
        assert [plan.status for plan in plans] == ["SKIPPED"]
        assert "collect" in plans[0].message
        assert repeated == []
        assert len(scheduler.invocations) == 1
        assert first[0].status == "SUBMITTED" and workspace.read_additional() == before

    @staticmethod
    def test_p0400_local_extraction_cleanup_failure_keeps_completed_result(tmp_path, monkeypatch):
        workspace, matrix = _run_2_review__a_recorded_campaign(tmp_path, values="0.0")
        real = Path.unlink

        def held(path, missing_ok=False):
            if path.name.endswith(".reopened.fsm"):
                raise PermissionError("held by another process")
            return real(path, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", held)
        _, completed = _run_2_review__extract(workspace, matrix, _run_2_review__a_stub(tmp_path))
        assert [record.status for record in completed] == ["EXTRACTED"]
        assert "could not be removed" in (completed[0].note or "")
        assert workspace.read_additional()[-1].status == "EXTRACTED"

    @staticmethod
    @pytest.mark.parametrize("placeholder", ["{walltime.missing}", "{walltime[bad]}"])
    def test_p0400_submit_field_access_refusal_is_a_failed_result(tmp_path, placeholder):
        from dataclasses import replace

        from pyflightstream.run import SubmittingExecutor
        from tests.tier1_offline.test_goal024_walltime import _profile

        profile = replace(_profile(tmp_path), submit=("submit", placeholder))
        executor = SubmittingExecutor(profile, values={"walltime": "4h"}, submit=False)
        script = tmp_path / "point.txt"
        script.write_text("CLOSE_FLIGHTSTREAM" + chr(10), encoding="utf-8")
        result = executor.run_script(script, tmp_path / "work")
        assert result.failed and "nothing was submitted" in result.stderr
        assert not (tmp_path / "work" / profile.descriptor_name).exists()


def _run_2_submit___recipe(case, script):
    script.emit("CLOSE_FLIGHTSTREAM")


def _run_2_submit___converged(case, result, sim_dir):
    from pyflightstream.run import Assessment

    return Assessment(status=RunStatus.CONVERGED)


class TestRun2Submit:
    """Tier 1, 0.40.0 lane run-2: a refusal inside the submitting executor fails its point alone.

    The executor writes its descriptor and calls no scheduler (``submit=False``).
    """

    @staticmethod
    def test_p0400_a_row_the_descriptor_refuses_fails_alone_and_the_campaign_goes_on(tmp_path):
        """P0400-SUBMIT-REFUSAL (PFS-2094.037): the refusal is the point's, not the campaign's.

        The profile's descriptor asks for {walltime}; row 5001 states it, row 5002
        does not. render_descriptor's refusal escaped run_script, the campaign
        ended there, and row 5002 got no record.
        """
        from pyflightstream.cases import Campaign

        first = _run_2_submit___case("4h")
        second = _run_2_submit___case(None).model_copy(update={"sim_id": "5002"})
        campaign = Campaign(
            name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[first, second]
        )
        workspace = CampaignWorkspace(tmp_path / "camp")
        executor = SubmittingExecutor(_run_2_submit___profile(tmp_path), values={}, submit=False)
        try:
            records = run_campaign(
                campaign,
                executor,
                workspace,
                assess=_run_2_submit___converged,
                recipes={"steady": _run_2_submit___recipe},
            )
        except CampaignErrors as error:
            records = error.records
        status = {record.sim_id: record for record in workspace.read_manifest()}
        assert status["5001"].status is RunStatus.SUBMITTED, status["5001"].error
        assert str(status["5002"].status).startswith("FAILED"), status["5002"].status
        assert "walltime" in (status["5002"].error or ""), status["5002"].error
        assert {record.sim_id for record in records} == {"5001", "5002"}

    @staticmethod
    def test_p0400_a_submit_command_naming_an_unresolved_value_writes_no_descriptor(tmp_path):
        """P0400-SUBMIT-REFUSAL (PFS-2094.037): the argv is formatted before the descriptor.

        A KeyError from formatting the submit command escaped run_script after the
        descriptor had been written. A name no run supplies (``{queue}``) is refused when
        the executor is built (PFS-2094.010); a name a grouped job supplies and this point
        does not (``{batch_id}``) is this point's failed result, with no descriptor.
        """
        import pytest

        from pyflightstream.run import ExecutorConfigurationError
        from pyflightstream.workspace.inputs import read_hpc_profile

        source = _run_2_submit___profile(tmp_path).path.read_text(encoding="utf-8")
        unknown = tmp_path / "h002.toml"
        unknown.write_text(source.replace("{descriptor_path}", "{queue}"), encoding="utf-8")
        with pytest.raises(ExecutorConfigurationError, match=r"\{queue\}"):
            SubmittingExecutor(read_hpc_profile(unknown), values={"walltime": "4h"}, submit=False)
        unbound = tmp_path / "h003.toml"
        unbound.write_text(source.replace("{descriptor_path}", "{batch_id}"), encoding="utf-8")
        executor = SubmittingExecutor(
            read_hpc_profile(unbound), values={"walltime": "4h"}, submit=False
        )
        script = tmp_path / "point.txt"
        script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
        result = executor.run_script(script, working_dir=tmp_path / "work")
        assert result.return_code != 0 and "{batch_id}" in result.stderr, result.stderr
        assert not (tmp_path / "work" / "submit.yaml").exists()


class TestRun1Review:
    """Adversarial regressions for the run-1 release lane, without a solver."""

    workspace = staticmethod(_run_1_review__workspace)

    @staticmethod
    @pytest.mark.parametrize("point", ["0", "99"])
    def test_p0400_review_unknown_numeric_point_lists_choices(tmp_path, capsys, point):
        """P0400-REVIEW-SHOW: invalid numeric selections get the same useful refusal."""
        camp = CampaignWorkspace.init(tmp_path / "camp")
        for tag in ("AL+000", "AL+020"):
            camp.append_record(_run_1_review__alias_tests._record("2006", f"warm/sim_2006/{tag}"))
        assert cli.main(["show", "2006", "--point", point, "--workspace", str(camp.root)]) == 1
        said = capsys.readouterr().err
        assert f"{point!r}" in said and "'2006'" in said
        assert "AL+000 (2006_1)" in said and "AL+020 (2006_2)" in said

    @staticmethod
    def test_p0400_review_nested_submit_fields_are_checked(tmp_path):
        """P0400-REVIEW-SUBMIT: a nested unknown is refused before any row runs."""
        path = _run_1_executors___profile(tmp_path, json.dumps(["esub", "{ncpus:{queue}}"]))
        profile = read_hpc_profile(path)
        with pytest.raises(ExecutorConfigurationError, match="submit"):
            SubmittingExecutor(profile, values={"fs_build": "26.120"})

    @staticmethod
    def test_p0400_review_submit_attribute_error_is_a_point_refusal(tmp_path):
        """P0400-REVIEW-SUBMIT: a malformed attribute cannot escape the point handler."""
        path = _run_1_executors___profile(tmp_path, json.dumps(["esub", "{ncpus.missing}"]))
        executor = SubmittingExecutor(
            read_hpc_profile(path),
            values={"fs_build": "26.120", "sim": "1", "ncpus": 8},
            submit=False,
        )
        script = tmp_path / "point.txt"
        script.write_text("CLOSE_FLIGHTSTREAM", encoding="utf-8")
        result = executor.run_script(script, working_dir=tmp_path)
        assert result.return_code == 2
        assert "nothing was submitted" in result.stderr and "submit command" in result.stderr

    @staticmethod
    @pytest.mark.parametrize(
        "broken", ["points_shape", "point_shape", "point_status", "row_status"]
    )
    def test_p0400_review_invalid_manifest_is_refused_before_writes(workspace, broken):  # noqa: F811
        """P0400-REVIEW-MANIFEST: invalid shapes or statuses never become a person's verdict."""
        document = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
        row = next(row for row in document["runs"] if row["details"]["sim_id"] == "7002")
        if broken == "points_shape":
            row["details"]["points_ran"] = "invalid"
        elif broken == "point_shape":
            row["details"]["points_ran"] = [None]
        elif broken == "point_status":
            row["details"]["points_ran"][0]["status"] = "HALF_DONE"
        else:
            row["status"] = "HALF_DONE"
        workspace.manifest_path.write_text(json.dumps(document), encoding="utf-8")
        before = workspace.manifest_path.read_bytes()
        archives = sorted((workspace.root / "archive").glob("runs-*.json"))
        with pytest.raises(RunsManifestError, match="invalid|HALF_DONE|points_ran"):
            mark_converged(workspace.root, ["7002"], reason=_RUN_1_REVIEW__REASON, apply=True)
        assert workspace.manifest_path.read_bytes() == before
        assert sorted((workspace.root / "archive").glob("runs-*.json")) == archives


def test_f6_0102_two_different_points_with_one_run_id_are_both_refused(tmp_path):
    """F-1453: a run id names one point, so a collision keeps neither point."""
    import shutil

    from tests.tier1_offline.test_post_superfile import _loads

    workspace = _run_1_assemble___from_sims_workspace(tmp_path)
    sim = workspace.sim_dir("6001")
    shutil.rmtree(sim / "outputs")
    # Two exports of one name, in folders that are not datapoint folders: one run id, two points.
    for folder, alpha in (("a", -2.0), ("b", 0.0)):
        (sim / folder).mkdir()
        (sim / folder / "loads.txt").write_text(_loads(alpha), encoding="utf-8")
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    assert [item.run_id for item in assembled if item.sim_id == "6001"] == []
    refused = {name: why for name, why in refusals.items() if name.startswith("sims/sim_6001/")}
    assert set(refused) == {"sims/sim_6001/a/loads.txt", "sims/sim_6001/b/loads.txt"}
    assert all("one run id" in why for why in refused.values())


def test_f6_0102_a_stale_surface_mesh_is_not_returned_as_the_fresh_export(tmp_path):
    """F-602: a run that wrote no mesh fails even when an earlier export left one behind."""

    class _Succeeds:
        def run_script(self, script_path, working_dir, timeout_s=None) -> ExecutionResult:
            return ExecutionResult(
                return_code=0, wall_time_s=0.1, timed_out=False, log_text=None, stdout="", stderr=""
            )

    work = tmp_path / "pre"
    work.mkdir()
    (work / "surface_mesh.obj").write_text("v 0 0 0\n", encoding="utf-8")
    with pytest.raises(SurfaceMeshExportError, match="was not written"):
        export_surface_mesh(tmp_path / "case.fsm", work, version="26.120", executor=_Succeeds())


def test_p0430_f261_an_assembled_record_keeps_the_residual_note(tmp_path):
    """F-261: the judged residual_note travels with the recovered residual into the record."""
    from tests.tier1_offline.test_goal028_hpc_log_completeness import _log

    workspace = _run_1_assemble___from_sims_workspace(tmp_path)
    outputs = workspace.sim_dir("6001") / "outputs"
    export = outputs / "POLAR-6001_M20AL+000BE+000.txt"
    counter = "Current solver iteration number:            "
    export.write_text(
        export.read_text(encoding="utf-8").replace(f"{counter}198", f"{counter}500"),
        encoding="utf-8",
    )
    # A log ending at the requested limit with the residual unsettled: MAX_ITER_REACHED.
    (outputs / "POLAR-6001_M20AL+000BE+000_log.txt").write_text(
        _log(ends_at=500, final_velocity="+9.6000000E-2"), encoding="utf-8"
    )
    assembled, _refusals = records.assemble_records(workspace.root, "matriz")
    note = {item.point_name: item.residual_note for item in assembled if item.sim_id == "6001"}
    assert "iteration limit" in str(note["POLAR-6001_M20AL+000BE+000"])
    assert note["POLAR-6001_M20AL-020BE+000"] is None


def test_f611_an_output_of_the_same_name_does_not_stand_in_for_a_missing_input(tmp_path):
    # Verifies F-611: a file the run wrote is not the input it read.
    from pyflightstream.run import reconstruct
    from pyflightstream.workspace import KNOWN_MANIFEST_SCHEMAS
    from tests.tier1_offline.test_restart_continuation import _stopped_record

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    sim = workspace.sim_dir("9001")
    work = sim / "datapoints" / "DP-1"
    work.mkdir(parents=True)
    (work / "probes.csv").write_text("written by the run", encoding="utf-8")
    (sim / "scripts").mkdir()
    (sim / "scripts" / "point.fs").write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    digest = sha256(b"written by the run").hexdigest()

    def read_input(outputs):
        record = _stopped_record().model_copy(
            update={
                "argv": ["solver.exe", "-script", "x"],
                "manifest_schema": sorted(KNOWN_MANIFEST_SCHEMAS)[-1],
                "cwd": str(work),
                "inputs_sha256": {"probes.csv": digest},
                "outputs_sha256": outputs,
            }
        )
        return reconstruct(record, workspace=workspace).verified["inputs/probes.csv"]

    # The run recorded that name among its outputs: the file beside the script is its own.
    assert read_input({"datapoints/DP-1/probes.csv": digest}) == "missing"
    # Without that output recorded, the file beside the script is the input, as before.
    assert read_input({}) == "match"


def test_f831_a_queued_steady_job_is_seen_by_the_point_collision_guard(tmp_path):
    # Verifies F-831: a SUBMITTED job record lists its points, and the guard reads that list.
    from pyflightstream.run import CampaignErrors, run_campaign
    from tests.tier1_offline.test_restart_continuation import _stopped_record
    from tests.tier1_offline.test_run_campaign import (
        WRITES_LOADS,
        StubSolver,
        converged,
        make_campaign,
        steady_recipe,
    )

    solver = {"assess": converged, "recipes": {"steady": steady_recipe}, "quiet": True}

    def run(folder, queued_tag):
        workspace = CampaignWorkspace.init(tmp_path / folder / "camp")
        # Another point of the row first, so its geometry is staged and staging again
        # changes nothing the queued job opens.
        staged = make_campaign(tmp_path / folder, alphas=(5.0,))
        run_campaign(staged, StubSolver(WRITES_LOADS), workspace, **solver)
        job = _stopped_record().model_copy(
            update={
                "run_id": "camp/sim_9001/sweep",
                "status": RunStatus.SUBMITTED,
                "points_ran": [{"tag": queued_tag, "point": {}, "status": "SUBMITTED"}],
            }
        )
        workspace.append_record(job)
        campaign = make_campaign(tmp_path / folder, alphas=(0.0,))
        try:
            run_campaign(campaign, StubSolver(WRITES_LOADS), workspace, **solver)
        except CampaignErrors:
            pass
        return {r.run_id: r for r in workspace.read_manifest()}["camp/sim_9001/AL+000"]

    refused = run("queued", "AL+000")
    assert refused.status is RunStatus.FAILED_SCRIPT
    assert "scheduler's queue as 'camp/sim_9001/sweep'" in str(refused.error)
    assert run("other", "AL+005").status is RunStatus.CONVERGED


def test_pfs_2130_071_reconstruct_expands_a_compacted_simulation(tmp_path):
    # Verifies PFS-2130.071: reconstruct restores sims/sim_<id>.zip before it reads the script.
    from pyflightstream.run import reconstruct
    from tests.tier1_offline.test_restart_continuation import _stopped_record

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    from pyflightstream.workspace import KNOWN_MANIFEST_SCHEMAS

    record = _stopped_record().model_copy(
        update={
            "argv": ["solver.exe", "-script", "x"],
            "manifest_schema": sorted(KNOWN_MANIFEST_SCHEMAS)[-1],
        }
    )
    workspace.append_record(record)
    script = workspace.sim_dir("9001") / str(record.script_path)
    script.parent.mkdir(parents=True)
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    _compact_sim(workspace, "9001")
    assert not workspace.sim_dir("9001").exists()
    rebuilt = reconstruct(record, workspace=workspace)
    assert rebuilt.script_text == "CLOSE_FLIGHTSTREAM\n"


def test_x_f_0399_an_export_at_another_sideslip_is_not_assembled_with_the_row_beta():
    """The angle a sweep holds fixed is compared with the value the row states for it.

    A row that states no BETA flies at sideslip 0.0 (FR-69, RB6-07 decision), so an
    export at another sideslip is not its point either (RB8, RB7-36).
    """
    from pyflightstream.run._assemble import point_of_export
    from pyflightstream.workspace import WorkspaceError

    sweep = SimpleNamespace(
        type="alpha",
        values=[0.0, 2.0, 4.0],
        points=lambda: [{"alpha": 0.0}, {"alpha": 2.0}, {"alpha": 4.0}],
    )
    stated = SimpleNamespace(pol="6001", flight_condition={"BETA": 0.0}, sweep=sweep)
    assert point_of_export(stated, "export", 2.0, 0.0) == {"alpha": 2.0}
    with pytest.raises(WorkspaceError, match="no point of row POL 6001"):
        point_of_export(stated, "export", 2.0, 3.0)
    unstated = SimpleNamespace(pol="6001", flight_condition={}, sweep=sweep)
    assert point_of_export(unstated, "export", 2.0, 0.0) == {"alpha": 2.0}
    with pytest.raises(WorkspaceError, match="no point of row POL 6001"):
        point_of_export(unstated, "export", 2.0, 3.0)


def test_x_f_1293_plan_resolves_a_continuation_without_expanding_a_compacted_simulation(
    tmp_path,
):
    """A preview writes nothing: ``expand=False`` leaves the simulation compacted."""
    from pyflightstream.run import resolve_continuation
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline import test_restart_continuation as restart

    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    saved = workspace.sim_dir("9001") / "datapoints" / "DP-AL+000"
    saved.mkdir(parents=True)
    (saved / "state.fsm").write_text("a stopped march", encoding="utf-8")
    workspace.append_record(restart._stopped_record())
    _compact_sim(workspace, "9001")
    folder = workspace.sim_dir("9001")
    assert not folder.exists()
    case = restart._continuing_case("{FINISH_PENDING}")
    preview = resolve_continuation(
        workspace, case, {"alpha": 0.0}, run_id="camp/sim_9001/AL+000", expand=False
    )
    assert preview is not None and str(preview["saved"]).endswith("state.fsm")
    assert not folder.exists(), "the preview expanded the simulation"
    resolve_continuation(workspace, case, {"alpha": 0.0}, run_id="camp/sim_9001/AL+000")
    assert (folder / "datapoints" / "DP-AL+000" / "state.fsm").is_file()
