"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import csv
import json
import math
import os
import warnings
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

import pyflightstream._textio as textio
import pyflightstream.post._additional as additional
import pyflightstream.post._sim as sim
import pyflightstream.post.corrections as corrections
import pyflightstream.post.products as _post2_products__products
from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream._errors import ProductError, ProductExistsError
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.corrections import CalibrationError
from pyflightstream.exceptions import IncompleteOutputError, MalformedOutputError
from pyflightstream.post import _sim, inflow_tools, passage_windows, read_timestep_series, series
from pyflightstream.post import products as _post_1_products__products
from pyflightstream.post._additional import _current_extraction
from pyflightstream.post._reduction_stage import (
    _judged_reduction_windows,
    _ReductionProducts,
    _write_point_revolutions,
)
from pyflightstream.post._tables import plots_table_series, read_csv_table, write_csv_table
from pyflightstream.post.glossary import write_input_glossary
from pyflightstream.post.point_tables import write_unsteady_probes_table
from pyflightstream.post.probe_fields import write_recorded_probe_fields
from pyflightstream.post.products import write_campaign_products
from pyflightstream.post.settings_table import (
    FLAG_IDS,
    VALUE_KINDS,
    read_settings_table,
    settings_table,
    write_settings_table,
)
from pyflightstream.post.surfaces import average_surface_exports, write_surface_average
from pyflightstream.post.unsteady import TimestepSeries
from pyflightstream.results import REDUCTION_WINDOW_CODES, SurfaceFrame
from pyflightstream.script import Script, helpers
from pyflightstream.workspace import CampaignWorkspace, ExtractionStatus, RunRecord
from tests.tier1_offline.test_b01_frozen_solve import (
    _post_workspace as _integfix_reduction_label___post_workspace,
)
from tests.tier1_offline.test_g25_surface_time_average import MRP as _POST_1_SURFACES__MRP
from tests.tier1_offline.test_g25_surface_time_average import _exports as _post_1_surfaces___exports
from tests.tier1_offline.test_goal028_rotor_table_average import REFERENCE as _POST_1_SIM__REFERENCE
from tests.tier1_offline.test_goal028_rotor_table_average import _pproc as _post_1_sim___pproc
from tests.tier1_offline.test_post_products import (
    _unsteady_workspace as _post2_products___unsteady_workspace,
)
from tests.tier1_offline.test_post_superfile import _MATRIX as _POST_1_SIM___MATRIX
from tests.tier1_offline.test_post_superfile import _PLOTS as _POST_1_SIM___PLOTS
from tests.tier1_offline.test_post_superfile import _post as _integfix_reduction_label___post
from tests.tier1_offline.test_post_superfile import _post as _post_1_sim___post
from tests.tier1_offline.test_post_superfile import (
    _workspace as _integfix_reduction_label___workspace,
)
from tests.tier1_offline.test_post_superfile import _workspace as _post_1_products___workspace
from tests.tier1_offline.test_post_superfile import _workspace as _post_1_sim___workspace
from tests.tier1_offline.test_settings_codebook import snapshot as _post_1_review__snapshot


def _integfix_post_groupkey___ctx() -> SimpleNamespace:
    point = SimpleNamespace(name="AL-020", loads=SimpleNamespace(surfaces={"W": None}))
    return SimpleNamespace(
        points=[point],
        conditions=[{}],
        aliases={},
        mach=0.2,
        reference=None,
        record_of={"AL-020": SimpleNamespace(run_id="camp/sim_7001/AL-020")},
        skipped={},
    )


class TestIntegfixPostGroupkey:
    """P0400-GROUPKEY: one group's polar failure on a point is keyed under that polar.

    At the 0.40.0 base a group whose polar rows could not be built for one point
    filed the failure under ``runs/<run id>``, the key that means no product holds
    the run. The point is a miss of THAT group's polar, ``polars/<file>#<point>``,
    as the absent-surface case already was; a point failing every group gives one
    such skip per group, never a whole-run refusal (PFS-2088.012).
    """

    @staticmethod
    def test_p0400_groupkey_one_groups_failure_is_keyed_under_its_polar(monkeypatch):
        """P0400-GROUPKEY (PFS-2088.012): the point is a miss of THIS group, not a refused run."""

        def refuse(*_args, **_kwargs):
            raise ProductError("no Reynolds number")

        monkeypatch.setattr(sim, "select_group_members", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(sim, "group_polar_rows", refuse)
        ctx = _integfix_post_groupkey___ctx()
        group_points, _conditions, rows, absent = sim._group_rows(ctx, "1", ["W"])
        assert group_points == [] and rows == []
        assert "no Reynolds number" in absent["AL-020"]
        assert not any(key.startswith("runs/") for key in ctx.skipped)

    @staticmethod
    def test_p0400_groupkey_a_point_failing_every_group_is_skipped_per_group(monkeypatch):
        """P0400-GROUPKEY (PFS-2088.012): each group records its own miss; none overwrites another."""  # noqa: E501

        def refuse(_points, families, **_kwargs):
            raise ProductError(f"group {families[0]} has no Reynolds number")

        monkeypatch.setattr(sim, "select_group_members", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(sim, "group_polar_rows", refuse)
        ctx = _integfix_post_groupkey___ctx()
        reasons = {group: sim._group_rows(ctx, group, [group])[3] for group in ("WING", "TAIL")}
        assert "group WING" in reasons["WING"]["AL-020"]
        assert "group TAIL" in reasons["TAIL"]["AL-020"]
        assert ctx.skipped == {}


_INTEGFIX_POST_INSTALLED___HEADER = (
    "POL,ROTOR,J_PROP,CT_PROP,CQ_PROP,CP_PROP,TORQUE_PROP,RPM_PROP,"
    "YMOM,H1_PHASE_DEG,H2_PHASE_DEG,C_PHASE_DEG,S_PHASE_DEG"
)


def _integfix_post_installed___rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class TestIntegfixPostInstalled:
    """P0400-MIRRORCQ: the installed-frame copy places CQ, YMOM and the harmonic phases.

    At the 0.40.0 base the mirror through y = 0 negated TORQUE and RPM but copied
    CQ as written, so a mirrored rotor table broke ``CP = 2 pi CQ sign(RPM)``
    (PFS-2105.013); it also copied YMOM, the y of the moment point, and the phase
    of a harmonic in azimuth, which maps ``PHI_k -> -PHI_k`` (PFS-2105.014).
    """

    @staticmethod
    def test_p0400_mirrorcq_a_rotor_table_copy_keeps_cp_equal_to_2_pi_cq_sign_rpm(tmp_path):
        """P0400-MIRRORCQ (PFS-2105.013): CQ flips with TORQUE and RPM, so CP still holds."""
        cq, rpm = 0.004, 2400.0
        cp = 2.0 * math.pi * cq * math.copysign(1.0, rpm)
        table = tmp_path / "rotor.csv"
        table.write_text(
            f"{_INTEGFIX_POST_INSTALLED___HEADER}\n7001,PROP,0.5,0.1,{cq},{cp!r},12.0,{rpm},0.75,30.0,350.0,10.0,20.0\n",
            encoding="utf-8",
        )
        classes = inflow_tools.installed_frame_columns(_INTEGFIX_POST_INSTALLED___HEADER.split(","))
        assert {"CQ_PROP", "TORQUE_PROP", "RPM_PROP"} <= set(classes.flipped)
        assert "CP_PROP" not in classes.flipped and "CT_PROP" not in classes.flipped
        (row,) = _integfix_post_installed___rows(inflow_tools.to_installed_frame(table))
        copy_cq, copy_rpm, copy_cp = (float(row[c]) for c in ("CQ_PROP", "RPM_PROP", "CP_PROP"))
        assert copy_cq == -cq and copy_rpm == -rpm and float(row["TORQUE_PROP"]) == -12.0
        assert math.isclose(copy_cp, 2.0 * math.pi * copy_cq * math.copysign(1.0, copy_rpm))

    @staticmethod
    def test_p0400_mirrorcq_ymom_and_the_harmonic_phases_are_mirrored(tmp_path):
        """P0400-MIRRORCQ (PFS-2105.014): YMOM flips, H1/H2 phases map to -PHI mod 360."""
        table = tmp_path / "harmonics.csv"
        table.write_text(
            f"{_INTEGFIX_POST_INSTALLED___HEADER}\n7001,PROP,0.5,0.1,0.004,0.025,12.0,2400.0,0.75,30.0,350.0,10.0,20.0\n",
            encoding="utf-8",
        )
        classes = inflow_tools.installed_frame_columns(_INTEGFIX_POST_INSTALLED___HEADER.split(","))
        assert "YMOM" in classes.flipped
        assert {"H1_PHASE_DEG", "H2_PHASE_DEG"} <= set(classes.mapped)
        # The Theodorsen and Sears phases are functions of the reduced frequency alone.
        assert not {"C_PHASE_DEG", "S_PHASE_DEG"} & {*classes.flipped, *classes.mapped}
        (row,) = _integfix_post_installed___rows(inflow_tools.to_installed_frame(table))
        assert float(row["YMOM"]) == -0.75
        assert float(row["H1_PHASE_DEG"]) == 330.0 and float(row["H2_PHASE_DEG"]) == 10.0
        assert row["C_PHASE_DEG"] == "10.0" and row["S_PHASE_DEG"] == "20.0"
        # A harmonic cos(k psi - PHI_k) read at -psi is cos(k psi + PHI_k): the copy's phase.
        for psi in (0.0, 45.0, 200.0):
            source = math.cos(math.radians(-psi - 30.0))
            mirrored = math.cos(math.radians(psi - float(row["H1_PHASE_DEG"])))
            assert math.isclose(source, mirrored, abs_tol=1e-12)


_INTEGFIX_POST_SECTOR___LOADS = {
    "ALPHA": 0.0,
    "BETA": 0.0,
    "J": 0.5,
    "THRUST": 1.0,
    "TORQUE": 1.0,
    "CT": 0.1,
    "CQ": 0.01,
}


_INTEGFIX_POST_SECTOR___SECTOR = "camp/sim_2/S"


def _integfix_post_sector___workspace(tmp_path, monkeypatch, script: str | None):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    sector = SimpleNamespace(
        run_id=_INTEGFIX_POST_SECTOR___SECTOR, sim_id="2", script_path=None, script_sha256=None
    )
    if script is not None:
        folder = workspace.sim_dir("2")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "S.txt").write_bytes(script.encode("utf-8"))
        sector.script_path, sector.script_sha256 = "S.txt", text_sha256(script)
    runs = [SimpleNamespace(run_id="camp/sim_1/W"), sector]
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda _self: runs)
    out = workspace.products_dir(None)
    out.mkdir(parents=True, exist_ok=True)
    (out / "products.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(corrections, "_rotor_row", lambda *_args: ("t", "PROP", {}))
    monkeypatch.setattr(
        corrections, "_loads_of", lambda *_args: dict(_INTEGFIX_POST_SECTOR___LOADS)
    )
    return workspace


def _integfix_post_sector___call(workspace):
    return corrections.sector_offset_calibration(
        workspace,
        wheel_run_id="camp/sim_1/W",
        sector_run_id=_INTEGFIX_POST_SECTOR___SECTOR,
        calibration_id="c001",
    )


class TestIntegfixPostSector:
    """P0400-SECTORWHOLE: the sector offset helper refuses a sector not proven whole-rotor.

    At the 0.40.0 base sector_offset_calibration subtracted the sector's rotor row
    from the whole wheel's without reading whether the sector's export carried the
    whole rotor (symmetry loads on) or the modelled sector alone, so a sector
    solved with symmetry loads off gave an offset of one sector against a wheel
    (PFS-2093.002, option A: refused, never scaled on a guess).
    """

    @staticmethod
    @pytest.mark.parametrize(
        ("script", "named"),
        [
            ("SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS DISABLE\n", "DISABLE"),
            ("SYMMETRY PERIODIC 6\n", "not stated"),
            (None, "no hashed script"),
        ],
    )
    def test_p0400_sectorwhole_a_sector_not_proven_whole_rotor_is_refused(
        tmp_path, monkeypatch, script, named
    ):
        """P0400-SECTORWHOLE (PFS-2093.002): refused, naming the sector run and what it states."""
        workspace = _integfix_post_sector___workspace(tmp_path, monkeypatch, script)
        with pytest.raises(CalibrationError, match="does not prove whole-rotor loads") as refused:
            _integfix_post_sector___call(workspace)
        assert _INTEGFIX_POST_SECTOR___SECTOR in str(refused.value) and named in str(refused.value)
        assert not (workspace.inputs_dir / "calibrations" / "c001.toml").exists()

    @staticmethod
    @pytest.mark.parametrize(
        "script",
        [
            "SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS ENABLE\n",
            "SYMMETRY NONE\nSET_ANALYSIS_SYMMETRY_LOADS DISABLE\n",
        ],
    )
    def test_p0400_sectorwhole_a_sector_proven_whole_rotor_is_written(
        tmp_path, monkeypatch, script
    ):
        """P0400-SECTORWHOLE control: symmetry loads on, or no symmetry at all, is accepted."""
        workspace = _integfix_post_sector___workspace(tmp_path, monkeypatch, script)
        calibration = corrections.read_calibration(_integfix_post_sector___call(workspace))
        assert calibration.route == "sector_offset" and len(calibration.rows) == 4

    @staticmethod
    def test_p0400_sectorwhole_a_script_edited_after_the_run_is_refused(tmp_path, monkeypatch):
        """P0400-SECTORWHOLE: the script is read only as the record hashed it."""
        workspace = _integfix_post_sector___workspace(
            tmp_path, monkeypatch, "SYMMETRY PERIODIC 6\n"
        )
        (workspace.sim_dir("2") / "S.txt").write_bytes(
            b"SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS ENABLE\n"
        )
        with pytest.raises(CalibrationError, match="no longer hashes as recorded"):
            _integfix_post_sector___call(workspace)


class TestIntegfixPostSetprec:
    """P0400-SETPREC: the settings table writes its values at full precision.

    At the 0.40.0 base every float went through the five-decimal funnel, so a
    convergence threshold of 1e-6 was written 0.00000 and read back as 0
    (PFS-2105.020).
    """

    @staticmethod
    def test_p0400_setprec_small_values_round_trip_equal(tmp_path):
        """P0400-SETPREC (PFS-2105.020): 1e-6 and 2.5e-5 read back equal, every row as written."""
        setup = helpers.solver_settings(
            Script(version="26.120"), velocity=30.0, convergence=1e-6, surface_roughness=2.5e-5
        )
        table, _legend = write_settings_table(tmp_path / "settings.csv", [setup])
        read = read_settings_table(table)
        numbers = {row["flag_id"]: row["value_num"] for row in read}
        stated = {row["flag_id"]: row["value_num"] for row in settings_table([setup])}
        assert 1e-6 in numbers.values() and 2.5e-5 in numbers.values()
        assert numbers == stated
        text = table.read_text(encoding="utf-8")
        assert "1e-06" in text and "2.5e-05" in text

    @staticmethod
    def test_p0400_setprec_the_r10_admission_takes_the_spelling_and_no_value():
        """P0400-SETPREC (PFS-2105.020): FR-1001 admits a 0.38.0 cell's new spelling, never a new value."""  # noqa: E501
        from tests.tier1_offline.test_p0390_r03 import settings_spelling_admitted

        old = "POL,f1_value\n7002,0.00001\n7002,30.00000\n"
        assert settings_spelling_admitted("POL,f1_value\n7002,1e-05\n7002,30.0\n", old)
        assert not settings_spelling_admitted("POL,f1_value\n7002,2e-05\n7002,30.0\n", old)
        assert not settings_spelling_admitted("POL,f1_value\n7002,1e-05\n", old)
        assert not settings_spelling_admitted("POL,f2_value\n7002,1e-05\n7002,30.0\n", old)


def _integfix_reduction_label___rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class TestIntegfixReductionLabel:
    """Tier 1, 0.40.0 integration fixes: an averaged row says it is an average, an instant says so too.

    PFS-2105.043 and PFS-2105.046 relabelled every native unsteady export
    ``last_step`` over ``last_time_step`` (FR-32 as amended at 0.40.0). The
    unsteady polar carries the sweep row's provenance cells in its super content,
    so its averaged row, ``FIRST_STEP`` to ``LAST_STEP`` of the plots history,
    said ``last_step`` as well: a time average labelled as an instant. The
    averaged row is ``time_average`` over ``averaging_window``; the super polar
    of an unsteady simulation, read from the native export, stays ``last_step``.
    """  # noqa: E501

    @staticmethod
    def test_p0400_the_unsteady_polars_averaged_row_says_time_average(tmp_path):
        """P0400-INTEGFIX-REDUCTION-LABEL (FR-32, PFS-2105.043): the row is labelled an average.

        The rotor campaign's ``polars/P7001_AL-020_uns_avg.csv`` averages the plots
        history over steps 60 to 61. Its ``reduction`` and ``reduction_window``
        cells must say ``time_average`` and ``averaging_window``; before the fix
        they carried the sweep row's ``last_step`` and ``last_time_step``.
        """
        workspace = _integfix_reduction_label___post_workspace(tmp_path, 2411, (60, 61), rotor=True)
        write_campaign_products(workspace, matrix_stem="products")
        polars = sorted(
            (Path(workspace.root) / "post" / "products" / "polars").glob("*_uns_avg.csv")
        )
        assert [path.name for path in polars] == ["P7001_AL-020_uns_avg.csv"]
        rows = _integfix_reduction_label___rows(polars[0])
        assert len(rows) == 1
        row = rows[0]
        assert (row["FIRST_STEP"], row["LAST_STEP"], row["STEPS"]) == ("60", "61", "2")
        assert (row["reduction"], row["reduction_window"]) == ("time_average", "averaging_window")
        assert "averaging_window" in REDUCTION_WINDOW_CODES

    @staticmethod
    def test_p0400_an_unsteady_super_polar_row_stays_an_instant(tmp_path):
        """P0400-INTEGFIX-REDUCTION-LABEL (PFS-2105.046): the native-export row is the last step.

        The control: the super polar of the unsteady simulation 6002 is read from
        its loads exports, which state the last time step only, so its rows keep
        ``last_step`` over ``last_time_step`` and never the average's label.
        """
        workspace = _integfix_reduction_label___workspace(tmp_path)
        _integfix_reduction_label___post(workspace)
        polars = Path(workspace.root) / "post" / "matriz" / "polars"
        supers = sorted(polars.glob("SUPER-6002-*.csv"))
        assert supers, "the campaign no longer writes the unsteady simulation's super polar"
        for path in supers:
            rows = _integfix_reduction_label___rows(path)
            assert rows
            for row in rows:
                assert (row["reduction"], row["reduction_window"]) == (
                    "last_step",
                    "last_time_step",
                )
        assert not list(polars.glob("*6002*_uns_avg.csv"))


def _post2_additional___pair(tmp_path):
    saved = tmp_path / "point.fsm"
    saved.write_bytes(b"saved simulation")
    digest = file_sha256(saved)
    workspace = SimpleNamespace(
        sim_dir=lambda _sim: tmp_path, changed_extraction_file=lambda _extraction: None
    )
    extraction = SimpleNamespace(run_id="r", fsm="point.fsm", fsm_sha256=digest, sim_id="1")
    point = SimpleNamespace(outputs_sha256={"point.fsm": digest})
    return saved, workspace, extraction, point


class TestPost2Additional:
    """P0400-DIGEST: the additional post hashes a saved simulation once per post.

    At the 0.40.0 base every extraction re-hashed its point's saved simulation, so
    several extractions of one point hashed the same file again on every post.
    """

    @staticmethod
    def test_p0400_digest_two_extractions_of_one_point_hash_it_once(tmp_path, monkeypatch):
        """P0400-DIGEST: one post's cache answers the second extraction of one file."""
        saved, workspace, extraction, point = _post2_additional___pair(tmp_path)
        calls: list[object] = []
        monkeypatch.setattr(
            additional, "file_sha256", lambda path: calls.append(path) or file_sha256(path)
        )
        digests: dict = {}
        for _ in range(2):
            assert additional._current_extraction(workspace, extraction, point, digests) is None
        assert len(calls) == 1

    @staticmethod
    def test_p0400_digest_a_changed_file_is_hashed_again(tmp_path, monkeypatch):
        """P0400-DIGEST: a file whose size or mtime changed is not answered from the cache."""
        saved, workspace, extraction, point = _post2_additional___pair(tmp_path)
        digests: dict = {}
        assert additional._current_extraction(workspace, extraction, point, digests) is None
        saved.write_bytes(b"another simulation, saved since")
        os.utime(saved, ns=(1, 1))
        reason = additional._current_extraction(workspace, extraction, point, digests)
        assert reason is not None and "stale" in reason

    @staticmethod
    def test_p0400_digest_cache_is_shared_and_scoped_by_the_post(tmp_path, monkeypatch):
        """P0400-DIGEST: the production loop hashes once, and a later post hashes again."""
        saved, workspace, extraction, point = _post2_additional___pair(tmp_path)
        extractions = [
            SimpleNamespace(
                **vars(extraction),
                extraction_id=f"e{index}",
                matrix_stem=None,
                status=ExtractionStatus.EXTRACTED,
                pproc=f"p00{index}",
                outputs=[],
                outputs_sha256={},
                sections_layout=[],
                unsteady=False,
            )
            for index in (1, 2)
        ]
        workspace.read_additional = lambda: extractions
        point.run_id = "r"
        point.outputs = []
        point.model_copy = lambda **_kwargs: point
        calls = []
        built = []
        monkeypatch.setattr(
            additional, "file_sha256", lambda path: calls.append(path) or file_sha256(path)
        )
        monkeypatch.setattr(additional, "_resolve_post_pproc", lambda *_args: None)

        def build(*_args, **_kwargs):
            built.append(True)
            return [], {}, {}

        monkeypatch.setattr(additional, "_sim_products", build)
        for post in (1, 2):
            skipped = {}
            additional._additional_products(
                workspace,
                {"r": point},
                tmp_path,
                [],
                {},
                skipped,
                rows_of_the_matrix={},
                matrix_stem=None,
                overwrite=True,
                archive=False,
                archive_stamp=None,
                check_frozen=False,
            )
            assert skipped == {}
            assert len(built) == 2 * post
            assert calls == [saved] * post


def _post2_products___refusing_writes(monkeypatch, name: str, armed=lambda: True):
    real = textio.write_text

    def write_text(path, *args, **kwargs):
        # The manifest is staged as products.json.tmp and then replaced (PFS-2096.019).
        if str(path).endswith((name, f"{name}.tmp")) and armed():
            raise OSError(f"{name} is locked")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(textio, "write_text", write_text)


class TestPost2Products:
    """P0400-PRIMARY: a failed log or manifest write never replaces the error that stopped the post.

    At the 0.40.0 base the post log was written in a ``finally`` with no guard and
    the interrupted manifest in an ``except`` with none, so an OSError there (a
    locked file, a full disk) replaced the error that stopped the post, and a
    caller catching that error by its type received an OSError.
    """

    @staticmethod
    def test_p0400_primary_a_post_log_write_failure_keeps_the_error(tmp_path, monkeypatch):
        """P0400-PRIMARY: the caller receives the CampaignConfigError, the log failure as a note."""
        workspace = _post2_products___unsteady_workspace(tmp_path, reductions=None)

        def stop(*_args, **_kwargs):
            raise CampaignConfigError("the stated input is wrong")

        monkeypatch.setattr(_post2_products__products, "_campaign_products", stop)
        _post2_products___refusing_writes(monkeypatch, "post.log.json")
        with pytest.raises(CampaignConfigError, match="the stated input is wrong") as caught:
            _post2_products__products.write_campaign_products(workspace)
        assert any("post log could not be written" in note for note in caught.value.__notes__)

    @staticmethod
    def test_p0400_primary_an_interrupted_manifest_write_failure_keeps_the_error(
        tmp_path, monkeypatch
    ):
        """P0400-PRIMARY: the rewrite of products.json failing keeps the rebuild's own error."""
        workspace = _post2_products___unsteady_workspace(tmp_path, reductions=None)
        stopped: list[bool] = []

        def stop(*_args, **_kwargs):
            stopped.append(True)
            raise CampaignConfigError("a product cannot be built")

        monkeypatch.setattr(_post2_products__products, "_write_the_products", stop)
        _post2_products___refusing_writes(monkeypatch, "products.json", armed=lambda: bool(stopped))
        with pytest.raises(CampaignConfigError, match="a product cannot be built") as caught:
            _post2_products__products.write_campaign_products(workspace)
        assert any("interrupted manifest" in note for note in caught.value.__notes__)

    @staticmethod
    def test_p0400_primary_a_clean_post_still_raises_its_log_failure(tmp_path, monkeypatch):
        """P0400-PRIMARY control: with no error in flight, the log failure is the error."""
        workspace = _post2_products___unsteady_workspace(tmp_path, reductions=None)
        monkeypatch.setattr(
            _post2_products__products, "_campaign_products", lambda *_args, **_kwargs: []
        )
        _post2_products___refusing_writes(monkeypatch, "post.log.json")
        with pytest.raises(OSError, match="locked"):
            _post2_products__products.write_campaign_products(workspace)

    @staticmethod
    def test_p0400_primary_a_partial_manifest_write_keeps_the_error(tmp_path, monkeypatch):
        """P0400-PRIMARY: reading a partially written manifest cannot replace the post error."""
        workspace = _post2_products___unsteady_workspace(tmp_path, reductions=None)
        original = CampaignConfigError("a product cannot be built")
        stopped = []
        real = textio.write_text

        def stop(*_args, **_kwargs):
            stopped.append(True)
            raise original

        def partial_write(path, *args, **kwargs):
            if str(path).endswith("products.json.tmp") and stopped:
                real(path, "{")
                raise OSError("manifest write ran out of space")
            return real(path, *args, **kwargs)

        monkeypatch.setattr(_post2_products__products, "_write_the_products", stop)
        monkeypatch.setattr(textio, "write_text", partial_write)
        with pytest.raises(CampaignConfigError) as caught:
            _post2_products__products.write_campaign_products(workspace)
        assert caught.value is original
        assert any("interrupted manifest" in note for note in caught.value.__notes__)
        # The manifest is staged and replaced whole (PFS-2096.019), so the half-written file never
        # stands at its name: the post log reader finds no truncated JSON and adds no note.
        assert not any("post log" in note for note in caught.value.__notes__)

    @staticmethod
    @pytest.mark.parametrize("failure", [CampaignConfigError, KeyboardInterrupt])
    def test_p0400_primary_log_close_failure_keeps_the_primary(tmp_path, monkeypatch, failure):
        """P0400-PRIMARY: a buffered write failing at close preserves the original error."""
        workspace = _post2_products___unsteady_workspace(tmp_path, reductions=None)
        original = failure("the post stopped")

        def stop(*_args, **_kwargs):
            raise original

        @contextmanager
        def broken_close(*_args, **_kwargs):
            try:
                yield StringIO()
            finally:
                raise OSError("post.log close failed")

        monkeypatch.setattr(_post2_products__products, "_campaign_products", stop)
        monkeypatch.setattr(textio, "open_text", broken_close)
        with pytest.raises(failure) as caught:
            _post2_products__products.write_campaign_products(workspace)
        assert caught.value is original
        assert any("post.log close failed" in note for note in caught.value.__notes__)

    @staticmethod
    def test_p0400_primary_clean_post_reports_log_close_failure(tmp_path, monkeypatch):
        """P0400-PRIMARY: a close failure remains visible when the post succeeded."""
        workspace = _post2_products___unsteady_workspace(tmp_path, reductions=None)

        @contextmanager
        def broken_close(*_args, **_kwargs):
            yield StringIO()
            raise OSError("post.log close failed")

        monkeypatch.setattr(
            _post2_products__products, "_campaign_products", lambda *_args, **_kwargs: []
        )
        monkeypatch.setattr(textio, "open_text", broken_close)
        with pytest.raises(OSError, match="post.log close failed"):
            _post2_products__products.write_campaign_products(workspace)


def _post2_reduction_stage___ctx(tmp_path, plan):
    return _ReductionProducts(
        plots_table=tmp_path / "absent_plots.csv",
        plan=plan,
        out=tmp_path,
        runs=[],
        target=lambda path: path,
        written=[],
        written_names={},
        skipped={},
        condition=None,
        reference=None,
        rotor_facts=None,
        names=None,
        frozen=None,
        pol=None,
        stem="P1",
    )


class TestPost2ReductionStage:
    """P0400-REDSKIP: the reduction stage records its skips under the files it would write.

    At the 0.40.0 base a recorded window holding a non-number was cast outside the
    guarded block, so it ended the whole post; and a per-revolution read failure of a
    plan with a rotors block was keyed under the single-rotor file name that plan
    never writes.
    """

    @staticmethod
    def test_p0400_redskip_a_malformed_window_is_a_skip_of_its_reduction(tmp_path):
        """P0400-REDSKIP: a window holding a non-number is a named skip, not an abort."""
        ctx = _post2_reduction_stage___ctx(tmp_path, {})
        relative = "probes/P1_time_average.csv"
        entry = {"windows": [["ten", 20]]}
        assert _judged_reduction_windows(ctx, "time_average", entry, relative, None) is None
        assert "not whole numbers" in ctx.skipped[relative]

    @staticmethod
    @pytest.mark.parametrize("name, window", [("time_average", []), ("per_blade", [1])])
    def test_p0400_redskip_a_window_without_two_bounds_is_a_named_skip(tmp_path, name, window):
        """P0400-REDSKIP: malformed bound counts cannot escape as an IndexError."""
        ctx = _post2_reduction_stage___ctx(tmp_path, {})
        write_csv_table(ctx.plots_table, ["Time-step", "CL"], [[1, 0.1], [2, 0.2]])
        relative = f"probes/P1_{name}.csv"
        assert _judged_reduction_windows(ctx, name, {"windows": [window]}, relative, None) is None
        assert "two bounds" in ctx.skipped[relative]

    @staticmethod
    def test_p0400_redskip_per_revolution_failure_is_keyed_per_rotor(tmp_path):
        """P0400-REDSKIP: a rotors plan records the read failure under each rotor's file."""
        plan = {
            "rotors": {"PROP": {"steps_per_revolution": 36}, "TAIL": {"steps_per_revolution": 24}}
        }
        ctx = _post2_reduction_stage___ctx(tmp_path, plan)
        _write_point_revolutions(ctx, None)
        assert sorted(ctx.skipped) == [
            "probes/P1_per_revolution_PROP.csv",
            "probes/P1_per_revolution_TAIL.csv",
        ]

    @staticmethod
    def test_p0400_redskip_single_rotor_failure_keeps_its_file_name(tmp_path):
        """P0400-REDSKIP control: a phase-locked plan keeps the single-rotor name."""
        ctx = _post2_reduction_stage___ctx(
            tmp_path, {"phase_locked": {}, "steps_per_revolution": 36}
        )
        _write_point_revolutions(ctx, None)
        assert list(ctx.skipped) == ["probes/P1_per_revolution.csv"]


class TestPost2Sim:
    """P0400-GROUPKEY: a rotor integration-group clash writes no group polar.

    At the 0.40.0 base a rotor integration-group clash was recorded as a skip
    while every group polar, the clashing one included, was still written.
    """

    @staticmethod
    def test_p0400_groupkey_a_rotor_group_clash_writes_no_group_polar(monkeypatch):
        """P0400-GROUPKEY: a declared group disagreeing with a rotor stops every group polar."""
        drawn: list[str] = []
        monkeypatch.setattr(
            sim, "_group_polar", lambda _ctx, group, *_rest, **_kw: drawn.append(group)
        )
        ctx = SimpleNamespace(
            pproc=SimpleNamespace(
                products=SimpleNamespace(polars=True), groups={"PORT": ["Wing"], "1": ["all"]}
            ),
            live=SimpleNamespace(rotors={"PORT": SimpleNamespace(members=["Blade1"])}),
            window=None,
            points=[],
            skipped={},
            sim_id="7001",
        )
        sim._group_polars(ctx)
        assert drawn == []
        assert "No group polar of simulation '7001'" in ctx.skipped["polars/7001"]

    @staticmethod
    def test_p0400_groupkey_agreeing_groups_are_all_drawn(monkeypatch):
        """P0400-GROUPKEY control: with no clash every group, the rotor's included, is drawn."""
        from pyflightstream.results import parse_loads
        from tests.tier1_offline.test_post_products import LOADS

        drawn: list[str] = []
        # `instant` is the keyword the instant group polars of PFS-2105.011 pass.
        monkeypatch.setattr(
            sim, "_group_polar", lambda _ctx, group, *_rest, **_kw: drawn.append(group)
        )
        ctx = SimpleNamespace(
            pproc=SimpleNamespace(products=SimpleNamespace(polars=True), groups={"1": ["all"]}),
            live=SimpleNamespace(rotors={"PORT": SimpleNamespace(members=["Blade1"])}),
            window=None,
            points=[],
            skipped={},
            sim_id="7001",
        )
        sim._group_polars(ctx)
        assert drawn == ["1", "PORT"] and ctx.skipped == {}
        instant_groups = {}
        monkeypatch.setattr(
            sim,
            "_group_polar",
            lambda _ctx, group, *_rest, **kw: instant_groups.update({group: kw.get("instant")}),
        )
        ctx.points = [SimpleNamespace(name="P", loads=parse_loads(LOADS), vorticity_selection=None)]
        ctx.record_of = {"P": SimpleNamespace(recipe="unsteady")}
        with pytest.warns(sim.PyflightstreamWarning, match="LAST TIME STEP"):
            sim._group_polars(ctx)
        assert instant_groups == {"1": True, "PORT": True}


_POST2_UNSTEADY___VARIABLES = 'VARIABLES = "X" "Y" "Z" "cp"'


def _post2_unsteady___frame(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _post2_unsteady___vtk(body: str) -> str:
    head = "# vtk DataFile Version 3.0\nt\nASCII\nDATASET POLYDATA\n"
    return head + "POINTS 2 float\n0 0 0\n1 0 0\nVERTICES 2 4\n1 0\n1 1\n" + body


def _post2_unsteady___series(steps):
    steps = np.asarray(steps, dtype=int)
    return TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"cp": np.zeros((len(steps), 1))},
        sources=(),
    )


class TestPost2Unsteady:
    """P0400-FRAMES: the animation frame readers and the passage windows.

    Each case is a frame the readers took wrongly at the 0.40.0 base: a Tecplot
    zone whose keywords are separated by commas, a second zone, an auxiliary data
    record, a truncated or ragged VECTORS block, a CELL_DATA section, and passage
    windows over frames whose stride does not divide the passage.
    """

    @staticmethod
    def test_p0400_frames_comma_separated_solutiontime_orders_the_frames(tmp_path):
        """P0400-FRAMES: SOLUTIONTIME followed by a comma is read as a number."""
        frames = [
            _post2_unsteady___frame(
                tmp_path,
                f"f{i}.dat",
                f'{_POST2_UNSTEADY___VARIABLES}\nZONE T="f", I=1, SOLUTIONTIME={t}, STRANDID=1\n0 0 0 {v}\n',  # noqa: E501
            )
            for i, (t, v) in enumerate([(0.5, 2.0), (0.25, 1.0)])
        ]
        series = read_timestep_series(frames)
        assert series.times_s.tolist() == [0.25, 0.5]
        assert series.fields["cp"][:, 0].tolist() == [1.0, 2.0]

    @staticmethod
    def test_p0400_frames_a_second_zone_is_refused_by_name(tmp_path):
        """P0400-FRAMES: a one-zone-per-sample file is refused as multi-zone, not as truncated."""
        text = (
            f'{_POST2_UNSTEADY___VARIABLES}\nZONE T="Sample 0", I=1, J=1, K=1\n0 0 0 1\n'
            'ZONE T="Sample 1", I=1, J=1, K=1\n1 0 0 2\n'
        )
        path = _post2_unsteady___frame(tmp_path, "zones.dat", text)
        with pytest.raises(MalformedOutputError, match="second ZONE"):
            read_timestep_series([path], order="given")

    @staticmethod
    @pytest.mark.parametrize(
        "record", ['DATASETAUXDATA SOURCE = "a"', 'AUXDATA NOTE = "b"'], ids=["dataset", "zone"]
    )
    def test_p0400_frames_auxiliary_records_are_skipped(tmp_path, record):
        """P0400-FRAMES: an auxiliary name-value record is not read as a row."""
        text = f'{_POST2_UNSTEADY___VARIABLES}\n{record}\nZONE T="f" I=2\n0 0 0 1\n1 0 0 2\n'
        series = read_timestep_series(
            [_post2_unsteady___frame(tmp_path, "aux.dat", text)], order="given"
        )
        assert series.fields["cp"][0].tolist() == [1.0, 2.0]

    @staticmethod
    def test_p0400_frames_a_text_line_is_a_malformed_output_naming_it(tmp_path):
        """P0400-FRAMES: a non-numeric data line raises the catalogued error, naming the line."""
        text = f'{_POST2_UNSTEADY___VARIABLES}\nZONE T="f" I=1\nDT=(SINGLE SINGLE)\n0 0 0 1\n'
        with pytest.raises(MalformedOutputError, match=r"DT=\(SINGLE SINGLE\)"):
            read_timestep_series(
                [_post2_unsteady___frame(tmp_path, "text.dat", text)], order="given"
            )

    @staticmethod
    def test_p0400_frames_a_truncated_vectors_block_is_incomplete(tmp_path):
        """P0400-FRAMES: a VECTORS block cut short is an IncompleteOutputError, not IndexError."""
        path = _post2_unsteady___frame(
            tmp_path, "cut.vtk", _post2_unsteady___vtk("POINT_DATA 2\nVECTORS u float\n1 2 3\n")
        )
        with pytest.raises(IncompleteOutputError, match="'u' block ends"):
            read_timestep_series([path], order="given")

    @staticmethod
    def test_p0400_frames_a_ragged_vectors_line_is_malformed(tmp_path):
        """P0400-FRAMES: a vector line without three values is a MalformedOutputError."""
        path = _post2_unsteady___frame(
            tmp_path,
            "ragged.vtk",
            _post2_unsteady___vtk("POINT_DATA 2\nVECTORS u float\n1 2 3\n4 5\n"),
        )
        with pytest.raises(MalformedOutputError, match="2 value"):
            read_timestep_series([path], order="given")

    @staticmethod
    def test_p0400_frames_a_whole_vectors_block_is_read(tmp_path):
        """P0400-FRAMES control: a complete VECTORS block under POINT_DATA is read."""
        path = _post2_unsteady___frame(
            tmp_path,
            "ok.vtk",
            _post2_unsteady___vtk("POINT_DATA 2\nVECTORS u float\n1 2 3\n4 5 6\n"),
        )
        series = read_timestep_series([path], order="given")
        assert series.fields["u"][0].tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]

    @staticmethod
    def test_p0400_frames_cell_data_is_refused(tmp_path):
        """P0400-FRAMES: CELL_DATA scalars are refused, not read as point samples."""
        body = "CELL_DATA 3\nSCALARS cp float 1\nLOOKUP_TABLE default\n1\n2\n3\n"
        with pytest.raises(MalformedOutputError, match="CELL_DATA"):
            read_timestep_series(
                [_post2_unsteady___frame(tmp_path, "cells.vtk", _post2_unsteady___vtk(body))],
                order="given",
            )

    @staticmethod
    def test_p0400_frames_a_field_without_point_data_is_refused(tmp_path):
        """P0400-FRAMES: a SCALARS block not preceded by POINT_DATA n is refused."""
        body = "SCALARS cp float 1\nLOOKUP_TABLE default\n1\n2\n"
        with pytest.raises(MalformedOutputError, match="POINT_DATA 2"):
            read_timestep_series(
                [_post2_unsteady___frame(tmp_path, "bare.vtk", _post2_unsteady___vtk(body))],
                order="given",
            )

    @staticmethod
    @pytest.mark.parametrize(
        "steps", [[0, 3, 6, 9, 12, 15, 18], [0, 2, 3, 6, 8, 9]], ids=["stride", "uneven"]
    )
    def test_p0400_frames_passages_of_unequal_phases_are_refused(steps):
        """P0400-FRAMES: a stride that does not divide the passage, or uneven frames, is refused."""
        with pytest.raises(MalformedOutputError, match="different phases"):
            passage_windows(_post2_unsteady___series(steps), period_steps=4)

    @staticmethod
    def test_p0400_frames_a_dividing_stride_keeps_its_windows():
        """P0400-FRAMES control: a stride dividing the passage cuts as before."""
        assert passage_windows(_post2_unsteady___series([0, 2, 4, 6, 8, 10]), period_steps=4) == [
            (0, 3),
            (4, 7),
        ]

    @staticmethod
    def test_p0400_frames_a_zero_stride_is_a_catalogued_refusal():
        """P0400-FRAMES: repeated step stamps cannot divide a passage into phases."""
        with pytest.raises(MalformedOutputError, match="stride must be positive"):
            passage_windows(_post2_unsteady___series([0, 0]), period_steps=1)


class TestPost1Additional:
    """P0400-STALEREMEDY (PFS-2100.003): the stale-extraction remedy names the matrix.

    ``pyfs-matrix post --additional-pproc`` without the matrix is refused by the
    CLI (the ADDITIONAL_PPROC key is read from its rows), so a remedy printed
    without it names a command that fails.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-STALEREMEDY")])
    def test_p0400_staleremedy_names_the_matrix() -> None:
        """P0400-STALEREMEDY: a rerun point's remedy names its matrix stem."""
        extraction = SimpleNamespace(
            run_id="R1", fsm="P1.fsm", fsm_sha256="a" * 64, matrix_stem="wing", sim_id="S1"
        )
        point = SimpleNamespace(outputs_sha256={"P1.fsm": "b" * 64})
        reason = _current_extraction(cast(Any, None), cast(Any, extraction), cast(Any, point))
        assert reason is not None
        assert "pyfs-matrix post wing --additional-pproc" in reason


class TestPost1Glossary:
    """P0400-CRLFGLOSSARY (PFS-2105.034): a CRLF checkout of INPUTS.md is not rewritten.

    write_input_glossary compared raw bytes, so a page a checkout turned CRLF never
    equalled the LF block it generates: every plan or post rewrote it, mixed.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-CRLFGLOSSARY")])
    def test_p0400_crlfglossary_a_crlf_page_is_left_alone(tmp_path):
        """P0400-CRLFGLOSSARY: unchanged content in CRLF is not written, and stays CRLF."""
        page = write_input_glossary(tmp_path)
        crlf = page.read_bytes().replace(b"\n", b"\r\n")
        page.write_bytes(b"# Our notes\r\n\r\n" + crlf)
        changed: list = []
        write_input_glossary(tmp_path, changed=changed)
        assert changed == []
        assert page.read_bytes() == b"# Our notes\r\n\r\n" + crlf

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-CRLFGLOSSARY")])
    def test_p0400_crlfglossary_a_refresh_keeps_the_pages_endings(tmp_path):
        """P0400-CRLFGLOSSARY: a stale block in a CRLF page is refreshed in CRLF, not mixed."""
        page = write_input_glossary(tmp_path)
        text = page.read_bytes()
        begin = text.index(b"-->") + len(b"-->")
        end = text.index(b"<!-- pyflightstream:input-glossary:end")
        stale = text[:begin] + b"\nstale\n" + text[end:]
        page.write_bytes(stale.replace(b"\n", b"\r\n"))
        changed: list = []
        write_input_glossary(tmp_path, changed=changed)
        assert changed == [page]
        assert page.read_bytes() == text.replace(b"\n", b"\r\n")


_POST_1_PRODUCTS___SOURCE = ast.parse(
    Path(_post_1_products__products.__file__).read_text(encoding="utf-8")
)


def _post_1_products___posted(workspace) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)


class TestPost1Products:
    """P0400 products-module defects (post-1 lane).

    P0400-NOPRIVATEREEXPORT (PFS-2098.003): post.products re-exports no private
    name through the explicit ``X as X`` idiom.
    P0400-HONESTFANOUT (PFS-2088.015): post.products imports the LF route from its
    defining module, so the fan-out guard counts it.
    P0400-MANIFESTREBUILD (PFS-2096.019): a truncated products.json is refused by
    name, a manifest is still written, and the manifest is replaced whole.
    P0400-UNKNOWNMATRIX (PFS-2096.020): an unknown matrix stem is refused before its
    folder or its log exists.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-NOPRIVATEREEXPORT")])
    def test_p0400_noprivatereexport_in_products():
        """P0400-NOPRIVATEREEXPORT: no ``from m import _x as _x`` and no ``import _x as _x``."""
        reexported = [
            alias.name
            for node in _POST_1_PRODUCTS___SOURCE.body
            if isinstance(node, ast.ImportFrom | ast.Import)
            for alias in node.names
            if alias.asname is not None
            and alias.asname == alias.name
            and alias.asname.startswith("_")
        ]
        assert reexported == [], reexported

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-HONESTFANOUT")])
    def test_p0400_honestfanout_textio_comes_from_its_home():
        """P0400-HONESTFANOUT: _textio is bound from pyflightstream._textio, not through _tables."""
        bound = {
            (node.module if isinstance(node, ast.ImportFrom) else alias.name)
            for node in _POST_1_PRODUCTS___SOURCE.body
            if isinstance(node, ast.ImportFrom | ast.Import)
            for alias in node.names
            if (alias.asname or alias.name) == "_textio"
            or (isinstance(node, ast.Import) and alias.asname == "_textio")
        }
        assert bound == {"pyflightstream._textio"}, bound

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-MANIFESTREBUILD")])
    def test_p0400_manifestrebuild_a_truncated_manifest_is_named_and_replaced(tmp_path):
        """P0400-MANIFESTREBUILD: the refusal names products.json; a parseable manifest follows."""
        workspace = _post_1_products___workspace(tmp_path)
        _post_1_products___posted(workspace)
        manifest = workspace.products_dir("matriz") / "products.json"
        manifest.write_text(manifest.read_text(encoding="utf-8")[:40], encoding="utf-8")
        with pytest.raises(ProductError, match="products.json does not parse"):
            _post_1_products___posted(workspace)
        written = json.loads(manifest.read_text(encoding="utf-8"))
        assert written["complete"] is False and "does not parse" in written["interrupted"]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-MANIFESTREBUILD")])
    def test_p0400_manifestrebuild_a_killed_write_leaves_no_truncated_manifest(
        tmp_path, monkeypatch
    ):
        """P0400-MANIFESTREBUILD: a write killed half way never leaves half a products.json."""
        workspace = _post_1_products___workspace(tmp_path)
        real = textio.write_text

        def killed(path, text, **kwargs):
            if Path(path).name.startswith("products.json"):
                real(path, text[: len(text) // 2], **kwargs)
                raise MemoryError("killed while writing")
            return real(path, text, **kwargs)

        monkeypatch.setattr(textio, "write_text", killed)
        with pytest.raises(MemoryError):
            _post_1_products___posted(workspace)
        manifest = workspace.products_dir("matriz") / "products.json"
        if manifest.exists():
            json.loads(manifest.read_text(encoding="utf-8"))

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-UNKNOWNMATRIX")])
    def test_p0400_unknownmatrix_is_refused_before_anything_is_written(tmp_path):
        """P0400-UNKNOWNMATRIX: a typo in the stem creates no folder and no log."""
        workspace = _post_1_products___workspace(tmp_path)
        with pytest.raises(ProductError, match="no record of matrix 'matirz'"):
            write_campaign_products(workspace, matrix_stem="matirz", overwrite=True)
        assert not workspace.products_dir("matirz").exists()


class TestPost1Review:
    """P0400 review regressions for reported fixes missing at the lane head."""

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-WIDE-KIND")])
    def test_p0400_wide_boundary_values_retain_their_kind():
        setup = _post_1_review__snapshot()
        command = "SET_VORTICITY_DRAG_BOUNDARIES"
        flags = dict(setup.flags)
        variants = []
        for value in ("all", [1]):
            flags[command] = flags[command].model_copy(update={"value": value})
            variants.append(setup.model_copy(update={"flags": dict(flags)}))
        rows = settings_table(variants, wide=True, fill=999)
        prefix = f"f{FLAG_IDS[command]}"
        assert [row[f"{prefix}_value"] for row in rows] == [1, 1]
        assert [row[f"{prefix}_kind"] for row in rows] == [
            VALUE_KINDS["enumerated"],
            VALUE_KINDS["list"],
        ]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-INFLOW-NAME")])
    def test_p0400_inflow_type_has_a_distinct_name_and_deprecated_alias():
        current = getattr(inflow_tools, "InflowStationHarmonics", None)
        assert current is not None
        with pytest.warns(DeprecationWarning, match="1.0.0"):
            old = inflow_tools.StationHarmonics
        assert old is current
        assert current.__name__ == "InflowStationHarmonics"

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-MIRROR")])
    def test_p0400_mirror_transforms_moment_position_and_harmonic_phase(tmp_path):
        table = tmp_path / "harmonics.csv"
        table.write_text("YMOM,H1_PHASE_DEG,H2_PHASE_DEG,OTHER_PHASE_DEG\n2,30,210,90\n")
        mirrored = inflow_tools.to_installed_frame(table)
        _, rows = read_csv_table(mirrored)
        assert [float(value) for value in rows[0].values()] == [-2, 330, 150, 270]
        _, twice = read_csv_table(inflow_tools.to_installed_frame(mirrored))
        assert [float(value) for value in twice[0].values()] == [2, 30, 210, 90]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-SERIES-PATHS")])
    def test_p0400_native_series_paths_use_the_product_folder_consistently(tmp_path, monkeypatch):
        root = tmp_path / "workspace"
        sim = root / "sims" / "sim_1"
        sim.mkdir(parents=True)
        native = sim / "p_iteration=1.dat"
        native.write_text("native")
        out = root / "post" / "matrix"
        monkeypatch.setattr(
            series,
            "stamped_exports",
            lambda *_: {
                ("", "txt"): {1: sim / "p_iteration=1.txt"},
                ("", "dat"): {1: native},
            },
        )
        monkeypatch.setattr(series, "SERIES_KINDS", (("loads", ""),))
        monkeypatch.setitem(series._ROWS, "loads", lambda *_a, **_k: (("STEP",), [(1,)]))
        monkeypatch.setattr(series, "surface_export_metadata", lambda *_a, **_k: {})
        monkeypatch.setattr(series, "translated_surface", lambda *_a, **_k: {})
        monkeypatch.setattr(series, "run_clock", lambda _: (None, None))
        record = SimpleNamespace(
            export_window={"first_step": 1, "time_iterations": 1},
            outputs=["p.txt"],
            run_id="r1",
            sim_id="1",
            sections_layout=None,
        )
        native_entries = {}
        _, entries = series.write_point_series(
            root,
            sim_dir=sim,
            record=record,
            stem="p",
            out=out,
            overwrite=True,
            surface_exports=native_entries,
        )
        (entry,) = entries.values()
        assert entry["tecplot_files"] == list(native_entries)
        assert (out / entry["tecplot_files"][0]).resolve() == native.resolve()

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-REPORTED-UNSTEADY")])
    def test_p0400_group_polars_honor_the_exports_solver_mode(monkeypatch):
        point = SimpleNamespace(
            name="p", loads=SimpleNamespace(solver_mode="Unsteady"), vorticity_selection=None
        )
        ctx = SimpleNamespace(
            pproc=SimpleNamespace(products=SimpleNamespace(polars=True), groups={"g": ["B"]}),
            points=[point],
            window=None,
            record_of={},
            sim_id="1",
            live=None,
        )
        monkeypatch.setattr(_sim, "declined_profile_drag_125", lambda *_: ())
        captured = []
        monkeypatch.setattr(_sim, "_group_polar", lambda *_a, **kw: captured.append(kw["instant"]))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _sim._group_polars(ctx)
        assert captured == [True]
        assert any("LAST TIME STEP" in str(w.message) for w in caught)

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-PUBLIC-IMPORTS")])
    def test_p0400_post_uses_public_lower_layer_contracts():
        from pyflightstream.post import _products_campaign, input_template

        forbidden = {"pyflightstream.cases._setup_keys", "pyflightstream.workspace._missing_log"}
        for module in (input_template, _products_campaign):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            assert not [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module in forbidden
            ]

    @staticmethod
    @pytest.mark.parametrize(
        "hub, radius",
        [((0.0, 0.5, 0.0), "1.00000"), ((0.0, 0.5, 0.3), "NA")],
        ids=["P0400-REVIEW-HARMONIC-HUB", "P0400-REVIEW-HARMONIC-NA"],
    )
    def test_p0400_wheel_harmonic_radii_are_measured_from_the_hub(
        tmp_path, monkeypatch, hub, radius
    ):
        from pyflightstream.post import _rotor_products

        table = tmp_path / "sections.csv"
        table.write_text(
            "CLOCKING,ROTOR,FAMILY,PLANE,AZIMUTH,Offset,Fx\n"
            + "".join(f"{i},PROP,B,XZ,{i * 60},1.5,10\n" for i in range(6))
        )
        quasi = SimpleNamespace(
            case="wheel",
            rotor_alias="PROP",
            families_blades=["B"],
            diameter_m=4.0,
            positions=list(range(6)),
            hub_m=hub,
            axis_vector=(1.0, 0.0, 0.0),
        )
        monkeypatch.setattr(_rotor_products, "read_qsteady_record", lambda _: quasi)
        record = SimpleNamespace(
            recipe="qsteady_rotor",
            sim_id="1",
            sections_layout=[{"families": ["B"], "plane": "XZ", "frame": "MRP"}],
        )
        point = SimpleNamespace(name="p", loads_path=tmp_path / "p.txt")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _rotor_products._wheel_harmonics(
                table, point, record, out=tmp_path, target=lambda p: p, runs=["r1"], skipped={}
            )
        assert result is not None
        _, rows = read_csv_table(result[0])
        assert {row["STATION_R_M"] for row in rows} == {radius}
        assert {row["R_OVER_R"] for row in rows} == {"0.50000" if radius != "NA" else "NA"}
        if radius == "NA":
            assert any("radius" in str(w.message) for w in caught)


def _post_1_sim___without_a_window(
    tmp_path: Path, *, plots: str | None = None
) -> tuple[dict, list[str]]:
    """The superfile fixture's rotor simulation, its record stating a speed and no window."""
    workspace = _post_1_sim___workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        _POST_1_SIM__REFERENCE, encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        '[groups]\n"1" = "all"\n\n'
        + _post_1_sim___pproc("HUB_PUSHER", "MRP", '["B"]').split("\n\n", 1)[1],
        encoding="utf-8",
    )
    (workspace.root / "matriz.fs").write_text(_POST_1_SIM___MATRIX, encoding="utf-8")
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            plan = {"rotors": {"PUSHER": {"blades": 6, "rpm": 2200.0}}}
            record = record.model_copy(update={"reductions": plan})
            if plots is not None:
                export = next(o for o in record.outputs if o.endswith("_plots.txt"))
                (workspace.sim_dir("6002") / export).write_text(plots, encoding="utf-8")
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post_1_sim___post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    return json.loads(manifest.read_text(encoding="utf-8")), [str(w.message) for w in caught]


class TestPost1Sim:
    """P0400 simulation-stage defects (post-1 lane).

    P0400-OBJREMEDY (PFS-2100.011): the FR-348 mesh-faces warning names a remedy
    that works for the geometry's kind; --overwrite is always refused for an OBJ.
    P0400-INSTANTGROUPS (PFS-2105.011): an unsteady simulation with no window gets
    group polars marked kind: instant, as its rotor table is, and a post.log line.
    P0400-EMPTYPLOTS (PFS-2105.031, not a bug): a plots export holding no step is
    refused by the parser, so the post names it as holding no step and replaces the
    pre-recorded "missing plots history" reason; this pins that it stays so.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-OBJREMEDY")])
    @pytest.mark.parametrize(("name", "overwrite"), [("wing.obj", False), ("wing.fsm", True)])
    def test_p0400_objremedy_names_a_remedy_that_runs(tmp_path, monkeypatch, name, overwrite):
        # Verifies FR-348.
        """P0400-OBJREMEDY: an OBJ is never told --overwrite; a saved simulation still is."""
        faces = SimpleNamespace(
            same_bytes=False,
            sidecar=tmp_path / f"{name}.inventory.toml",
            mesh_faces=12,
            counted_sha256="a" * 12,
            recorded_sha256="b" * 12,
            name=name,
        )
        monkeypatch.setattr(_sim, "recorded_mesh_faces", lambda *_args: faces)
        workspace = SimpleNamespace(sim_dir=lambda sim: tmp_path / sim, resolve_geometry=None)
        record = SimpleNamespace(sim_id="1", run_id="r1", inputs_sha256={})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert _sim._mesh_faces_of(cast(Any, workspace), cast(Any, record), "P1") == "12"
        (message,) = [str(warning.message) for warning in caught]
        assert ("--overwrite" in message) is overwrite, message
        if not overwrite:
            assert "docs/mesh-inputs.md" in message, message

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-INSTANTGROUPS")])
    def test_p0400_instantgroups_are_marked_and_said(tmp_path):
        """P0400-INSTANTGROUPS: every group polar of 6002 is kind: instant, and post.log says why."""  # noqa: E501
        manifest, caught = _post_1_sim___without_a_window(tmp_path)
        polars = {
            key: entry
            for key, entry in manifest["products"].items()
            if key.startswith("polars/")
            and "6002" in key
            and entry.get("kind") != "rotor_table"
            and not key.endswith("_rotor.csv")
            and "SUPER" not in key
        }
        assert polars, sorted(manifest["products"])
        assert {entry.get("kind") for entry in polars.values()} == {"instant"}, polars
        assert any("simulation 6002" in m and "LAST TIME STEP" in m for m in caught), caught

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-EMPTYPLOTS")])
    def test_p0400_emptyplots_says_the_export_holds_no_step(tmp_path):
        """P0400-EMPTYPLOTS: the export is on disk; the skip says it holds no time step."""
        # The header and the column line, written before the first step was.
        empty = _POST_1_SIM___PLOTS.partition("1.0000,")[0]
        manifest, _caught = _post_1_sim___without_a_window(tmp_path, plots=empty)
        reasons = {key: why for key, why in manifest["skipped"].items() if "6002" in key}
        plots = [why for key, why in reasons.items() if key.endswith("_plots.csv")]
        assert plots and "holds no time step" in plots[0], reasons
        assert not any("missing plots history export" in why for why in reasons.values()), reasons


#: A clock that goes back: step 3 written before step 2.
_POST_1_STEP_CLOCK___PLOTS = "POL,Time-step,VX1,VY1,VZ1\n1,3,11,3,5\n1,2,12,3,5\n"


class TestPost1StepClock:
    """P0400-ONECLOCK (PFS-2088.014): one reader of the plots table's Time-step clock.

    The reductions, the probe table and the probe fields each read the clock with
    their own fallback, so one non-monotonic clock gave a probe table whose STEP
    disagreed with the steps the reductions used, and fields placed at steps no
    other product names. Fed one non-monotonic clock, the three agree: the
    reductions and the probe table on the ordinal, the fields by refusing.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-ONECLOCK")])
    def test_p0400_oneclock_the_reductions_and_the_probe_table_agree(tmp_path):
        """P0400-ONECLOCK: the probe table's STEP is the step the reductions read, row for row."""
        plots = tmp_path / "plots.csv"
        plots.write_text(_POST_1_STEP_CLOCK___PLOTS, encoding="utf-8")
        _columns, series = plots_table_series(plots)
        table = write_unsteady_probes_table(
            tmp_path / "probes.csv",
            plots,
            positions={1: (0.0, 0.0, 0.0, "REFERENCE")},
            parameters=["VX", "VY", "VZ"],
        )
        assert table is not None
        _names, rows = read_csv_table(table)
        assert [int(row["STEP"]) for row in rows] == [int(step) for step in series.steps] == [1, 2]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-ONECLOCK")])
    def test_p0400_oneclock_the_fields_refuse_a_clock_the_others_read_as_ordinal(tmp_path):
        """P0400-ONECLOCK: a field is never placed on a step the other products do not name."""
        table = tmp_path / "probes.csv"
        table.write_text("PROBE,STEP,X,Y,Z,VX,VY,VZ\n1,3,0,0,0,11,3,5\n1,2,0,0,0,12,3,5\n")
        plots = tmp_path / "plots.csv"
        plots.write_text(_POST_1_STEP_CLOCK___PLOTS, encoding="utf-8")
        record = SimpleNamespace(
            run_id="test",
            campaign=None,
            probe_field_layout=[
                dict(
                    entry=1,
                    probe_ids=[1],
                    frame="REFERENCE",
                    native_to_m=1,
                    formats=["vtk"],
                    reusable_inflow=False,
                )
            ],
            solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                mode="json"
            ),
        )
        with pytest.raises(ValueError, match="strictly increasing"):
            write_recorded_probe_fields(table, record, tmp_path / "out", "P", step_source=plots)
        assert not (tmp_path / "out").exists()


class TestPost1Surfaces:
    """P0400 surface-average defects (post-1 lane).

    P0400-REVERSEDWINDOW (PFS-2095.045): a reversed window is a ProductError,
    never a bare IndexError.
    P0400-HALFPAIR (PFS-2096.022): write_surface_average tests both destinations
    before it writes either, so a refusal leaves nothing behind.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-REVERSEDWINDOW")])
    def test_p0400_reversedwindow_is_refused(tmp_path):
        """P0400-REVERSEDWINDOW: (6, 3) is refused, naming the window."""
        _post_1_surfaces___exports(tmp_path, range(1, 8))
        files = {step: tmp_path / f"p_iteration={step}.vtk" for step in range(1, 8)}
        with pytest.raises(ProductError, match=r"\(6, 3\) ends before it starts"):
            average_surface_exports(
                files, window=(6, 3), frame=SurfaceFrame.from_record(_POST_1_SURFACES__MRP)
            )

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-HALFPAIR")])
    def test_p0400_halfpair_a_refusal_writes_nothing(tmp_path):
        """P0400-HALFPAIR: the VTK exists; the Tecplot is not written either."""
        _post_1_surfaces___exports(tmp_path, range(1, 8))
        files = {step: tmp_path / f"p_iteration={step}.vtk" for step in range(1, 8)}
        average = average_surface_exports(
            files, window=(3, 6), frame=SurfaceFrame.from_record(_POST_1_SURFACES__MRP)
        )
        (tmp_path / "avg.vtk").write_text("earlier", encoding="utf-8")
        with pytest.raises(ProductExistsError):
            write_surface_average(tmp_path / "avg.dat", average, vtk=tmp_path / "avg.vtk")
        assert not (tmp_path / "avg.dat").exists()


# ---------------------------------------------------------------------------
# F3-0203 (pyflightstream 0.43.0): post products of the rotor, noise and structure stages
# ---------------------------------------------------------------------------


def _f3_0203_signal(frequency: float, observer: str = "o1"):
    from pyflightstream.cases.acoustics import AcousticSignal

    times = tuple(0.05 + n / 1000.0 for n in range(200))
    pressure = tuple(math.cos(2 * math.pi * frequency * (t - 0.05)) for t in times)
    return AcousticSignal(observer, 1.0, 0.0, 0.0, times, pressure)


def test_f3_0203_f132_acoustic_harmonics_use_the_recorded_blade_count(tmp_path, monkeypatch):
    """F-132: the blade-passing frequency uses the RECORDED blade count, not the sector's."""
    from pyflightstream.post import _rotor_products
    from pyflightstream.post import harmonics as _harmonics

    monkeypatch.setattr(
        _rotor_products._acoustics, "read_acoustic_signals", lambda _s: [_f3_0203_signal(120.0)]
    )
    record = SimpleNamespace(
        run_id="r1",
        outputs=["P1" + _rotor_products._acoustics.ACOUSTIC_SIGNALS_SUFFIX],
        reductions={"rotors": {"main": {"blades": 6, "rpm": 1200.0}}},
    )
    rotor = _harmonics.HarmonicRotor("main", (("a",), ("b",)), None, False)
    _rotor_products._acoustic_products(
        record,
        sim_dir=tmp_path,
        stem="P1",
        out=tmp_path / "post",
        rotors={"main": (rotor, None)},
        clocks={"main": {"rpm": 1200.0}},
        target=lambda p: p,
        skipped={},
    )
    with (tmp_path / "post" / "acoustics" / "P1_acoustics_bpf.csv").open(encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    assert float(rows[0]["FREQUENCY_HZ"]) == pytest.approx(120.0)


def _f3_0203_structure_ctx(tmp_path, monkeypatch, *, history: bytes | None = None):
    """A coupled point whose recorded displacements decode to two stations, no solver needed."""
    import pyflightstream.post._structure as structure

    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "src.txt").write_text("x", encoding="utf-8")
    if history is not None:
        (folder / "fsi_convergence_log.csv").write_bytes(history)
    monkeypatch.setattr(structure, "file_sha256", lambda _p: "h")
    monkeypatch.setattr(
        structure,
        "load_config",
        lambda _p: SimpleNamespace(blade=SimpleNamespace(station_radii_m=[0.1, 0.2])),
    )
    monkeypatch.setattr(
        structure,
        "generate_node_layout",
        lambda _c: SimpleNamespace(le_offset_m=[0.0, 0.0], te_offset_m=[0.0, 0.0]),
    )
    monkeypatch.setattr(
        structure, "_recorded_displacements", lambda *_a: (folder / "src.txt", None)
    )
    monkeypatch.setattr(structure, "unflatten_translations", lambda *_a: ["t"])
    monkeypatch.setattr(
        structure,
        "decode_station_translations",
        lambda *_a: (np.array([0.001, 0.002]), np.array([0.0, 0.1])),
    )
    point = SimpleNamespace(name="P1")
    record = SimpleNamespace(
        inputs_sha256={"fsi-provenance.json": "p", "config.json": "h"}, cwd=str(folder)
    )
    added: list[tuple[Path, dict]] = []
    ctx = SimpleNamespace(
        points=[point],
        record_of={"P1": record},
        skipped={},
        notes=[],
        out=tmp_path / "out",
        sources={"P1": ["run-1"]},
        structure_tips={},
        sim_id="3207",
        target=lambda p: p,
        add=lambda path, entry: added.append((path, entry)),
        condition=lambda _p: {"alpha": 4.0, "mach": 0.1},
        reference=SimpleNamespace(as_lengths=lambda: {}),
    )
    return structure, ctx, added


def test_f3_0203_f133_the_station_table_leads_with_pol_and_the_condition(tmp_path, monkeypatch):
    """F-133 (X-F-1630): the station CSV opens with POL and the condition block like every table."""
    from pyflightstream._tokens import CONTEXT_COLUMNS

    structure, ctx, _added = _f3_0203_structure_ctx(tmp_path, monkeypatch)
    structure.structure_products(ctx)
    with (tmp_path / "out" / "structure" / "P1_deflection.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0])[: 1 + len(CONTEXT_COLUMNS)] == ["POL", *CONTEXT_COLUMNS]
    assert rows[0]["POL"] == "3207" and rows[0]["ALPHA"] == "4.0"
    assert float(rows[1]["deflection_m"]) == pytest.approx(0.002)


def test_f3_0203_f1377_a_missing_coupling_history_is_a_named_skip(tmp_path, monkeypatch):
    """F-1377: no convergence log in the working folder leaves a skip entry, not silence."""
    structure, ctx, _added = _f3_0203_structure_ctx(tmp_path, monkeypatch)
    structure.structure_products(ctx)
    assert "fsi_convergence_log.csv" in ctx.skipped["structure/P1_history.csv"]
    assert "structure/P1_deflection.csv" not in ctx.skipped


def test_f3_0203_f782_an_unreadable_coupling_history_costs_only_itself(tmp_path, monkeypatch):
    """F-782: a non-UTF-8 history is a skip; the deflection table and later points still write."""
    structure, ctx, added = _f3_0203_structure_ctx(
        tmp_path, monkeypatch, history=b"\xff\xfe\x00bad"
    )
    structure.structure_products(ctx)
    assert "cannot be read" in ctx.skipped["structure/P1_history.csv"]
    assert [entry["kind"] for _path, entry in added] == ["structure"]
