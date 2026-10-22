"""Regression coverage grouped by subject."""

from __future__ import annotations

import csv
import json
import math
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import pyflightstream.post.corrections as corrections
from pyflightstream._digest import text_sha256
from pyflightstream._errors import ProductError
from pyflightstream.cases.acoustics import AcousticSignal
from pyflightstream.cases.corrections import (
    CalibrationError,
    CalibrationRow,
    QsteadyCorrectionSpec,
    calibration_path,
    calibration_text,
)
from pyflightstream.cases.qsteady import reduced_frequency
from pyflightstream.post import _rotor_plan
from pyflightstream.post._rotor_products import _acoustic_products
from pyflightstream.post.acoustics import write_acoustic_products
from pyflightstream.post.harmonics import fit_harmonics
from pyflightstream.post.inflow_tools import blade_view_harmonics
from pyflightstream.post.products import read_csv_table, write_rotor_table
from pyflightstream.post.qsteady import add_reduced_frequency_to_sections
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_goal026_item06_rotor_loads import (
    _reference as _post_1_rotor_table___reference,
)
from tests.tier1_offline.test_goal026_item06_rotor_loads import (
    _rotor as _post_1_rotor_table___rotor,
)
from tests.tier1_offline.test_goal026_item06_rotor_loads import (
    _surfaces as _post_1_rotor_table___surfaces,
)
from tests.tier1_offline.test_goal028_rotor_table_average import (
    REFERENCE as _POST_1_ROTOR_PLAN__REFERENCE,
)
from tests.tier1_offline.test_goal028_rotor_table_average import (
    SHAFT_FORCE as _POST_1_ROTOR_PLAN__SHAFT_FORCE,
)
from tests.tier1_offline.test_goal028_rotor_table_average import (
    _pproc as _post_1_rotor_plan___pproc,
)
from tests.tier1_offline.test_goal036_harmonics import _post as _post_1_rotor_products___post
from tests.tier1_offline.test_goal036_harmonics import (
    _unsteady as _post_1_rotor_products___unsteady,
)
from tests.tier1_offline.test_goal036_qsteady_corrections import (
    _post_recorded as _post_1_corrections___post_recorded,
)
from tests.tier1_offline.test_goal036_qsteady_corrections import (
    _post_recorded as _post_1_qsteady___post_recorded,
)
from tests.tier1_offline.test_goal036_qsteady_corrections import (
    _recorded_wheel as _post_1_corrections___recorded_wheel,
)
from tests.tier1_offline.test_goal036_qsteady_corrections import (
    _recorded_wheel as _post_1_qsteady___recorded_wheel,
)
from tests.tier1_offline.test_goal036_qsteady_corrections import _row as _post_1_corrections___row
from tests.tier1_offline.test_goal036_qsteady_corrections import (
    _table as _post_1_corrections___table,
)
from tests.tier1_offline.test_p0320_d_inflow_tools import OMEGA as _POST_1_INFLOW__OMEGA
from tests.tier1_offline.test_p0320_d_inflow_tools import RADIUS as _POST_1_INFLOW__RADIUS
from tests.tier1_offline.test_p0320_d_inflow_tools import (
    _uniform_at_aoa as _post_1_inflow___uniform_at_aoa,
)
from tests.tier1_offline.test_post_products import PLOTS_HEADER as _POST_1_ROTOR_PLAN__PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX as _POST_1_ROTOR_PLAN___MATRIX
from tests.tier1_offline.test_post_superfile import _post as _post_1_rotor_plan___post
from tests.tier1_offline.test_post_superfile import _workspace as _post_1_rotor_plan___workspace

_INTEGFIX_POST_HARMONICS_PAGE__PAGE = (
    Path(__file__).resolve().parents[2] / "docs" / "definitions" / "the-per-station-harmonics.md"
)


class TestIntegfixPostHarmonicsPage:
    """P0400-COVERAGEPAGE: the per-station harmonics page states the coverage criterion.

    The fit leaves a harmonic out where the samples' azimuths do not go round the
    circle (PFS-2086.007), and the definitions page, the record, stated only the
    count of distinct azimuths.
    """

    @staticmethod
    def test_p0400_coveragepage_the_page_states_the_criterion_the_fit_applies():
        """P0400-COVERAGEPAGE (PFS-2086.007): the 180 deg gap rule, on the page and in the fit."""
        crowded = fit_harmonics([0.0, 0.1, 0.2, 0.3, 0.4], [1.0, 1.0, 1.0, 1.0, 1.0])
        assert crowded.h1_amp is None and crowded.h2_amp is None
        assert "no gap over 180 deg" in str(crowded.reason)
        text = " ".join(_INTEGFIX_POST_HARMONICS_PAGE__PAGE.read_text(encoding="utf-8").split())
        assert "leave no gap larger than 180 deg around the circle" in text
        assert (
            "do not go round the circle: a 1P fit needs the angles 1 psi with no gap over" in text
        )


#: Clock rotor PUSH at 100 steps a turn, LIFT at 150; the run ends at step 1000.
_INTEGFIX_POST_ROTOR_WINDOW___PLAN = {
    "time_iterations": 1000,
    "steps_per_revolution": 100,
    "rotors": {"PUSH": {"steps_per_revolution": 100}, "LIFT": {"steps_per_revolution": 150}},
}


def _integfix_post_rotor_window___ctx(tmp_path, variables, row_span=(801, 1000)):
    return SimpleNamespace(
        windows={"AL-000": row_span},
        window=row_span,
        by_run={"r1": SimpleNamespace(reductions=_INTEGFIX_POST_ROTOR_WINDOW___PLAN)},
        sources={"AL-000": ["r1"]},
        matrix_row=SimpleNamespace(variables=variables),
        plots={"AL-000": tmp_path / "no_plots_table.csv"},
    )


def _integfix_post_rotor_window___span_used(ctx, alias):
    """The window the averaging reads, as its refusal names it (no plots table here)."""
    point = SimpleNamespace(name="AL-000")
    newtons, reason, _group = _rotor_plan._averaged_rotor_newtons(ctx, point, alias, [])
    assert newtons is None
    return reason.rsplit("over steps ", 1)[1]


class TestIntegfixPostRotorWindow:
    """P0400-ROTORWINDOW: each rotor of a rotor table is averaged over its own turns.

    At the 0.40.0 base the rotor table averaged every rotor of a row over the row's
    window, which is counted on the clock rotor, so a second rotor at another speed
    was averaged over a non-integer number of its own revolutions while its
    per-blade and per-revolution reductions were cut on its own clock (FR-68;
    PFS-2088.013, PFS-2081.30).
    """

    @staticmethod
    @pytest.mark.parametrize(("alias", "span"), [("PUSH", "801 to 1000"), ("LIFT", "701 to 1000")])
    def test_p0400_rotorwindow_last_revs_avg_counts_each_rotors_own_turns(tmp_path, alias, span):
        # Verifies FR-68.
        """P0400-ROTORWINDOW (PFS-2088.013): 2 turns are 200 steps of PUSH and 300 of LIFT."""
        assert (
            _integfix_post_rotor_window___span_used(
                _integfix_post_rotor_window___ctx(tmp_path, {"LAST_REVS_AVG": "2"}), alias
            )
            == span
        )

    @staticmethod
    def test_p0400_rotorwindow_last_iters_avg_is_the_same_steps_for_every_rotor(tmp_path):
        """P0400-ROTORWINDOW control: a count of iterations does not depend on the rotor."""
        ctx = _integfix_post_rotor_window___ctx(tmp_path, {"LAST_ITERS_AVG": "200"})
        assert {
            _integfix_post_rotor_window___span_used(ctx, alias) for alias in ("PUSH", "LIFT")
        } == {"801 to 1000"}

    @staticmethod
    def test_p0400_rotorwindow_the_entry_states_each_points_window_of_the_rotor(tmp_path):
        """P0400-ROTORWINDOW (PFS-2088.013): the manifest's windows are this rotor's own."""
        ctx = _integfix_post_rotor_window___ctx(tmp_path, {"LAST_REVS_AVG": "2"})
        assert _rotor_plan._rotor_windows(ctx, "LIFT") == {"AL-000": (701, 1000)}
        assert _rotor_plan._rotor_windows(ctx, "PUSH") == {"AL-000": (801, 1000)}


_POST2_CORRECTIONS___LOADS = {
    "ALPHA": 0.0,
    "BETA": 0.0,
    "J": 0.5,
    "THRUST": 1.0,
    "TORQUE": 1.0,
    "CT": 0.1,
    "CQ": 0.01,
}


def _post2_corrections___workspace(tmp_path, monkeypatch):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    # The sector's script proves whole-rotor loads (PFS-2093.002).
    script = "SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS ENABLE\n"
    (workspace.sim_dir("2") / "S.txt").parent.mkdir(parents=True, exist_ok=True)
    (workspace.sim_dir("2") / "S.txt").write_bytes(script.encode("utf-8"))
    sector = SimpleNamespace(
        run_id="camp/sim_2/S", sim_id="2", script_path="S.txt", script_sha256=text_sha256(script)
    )
    runs = [SimpleNamespace(run_id="camp/sim_1/W"), sector]
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda _self: runs)
    out = workspace.products_dir(None)
    out.mkdir(parents=True, exist_ok=True)
    (out / "products.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(corrections, "_rotor_row", lambda *_args: ("t", "PROP", {}))
    monkeypatch.setattr(corrections, "_loads_of", lambda *_args: dict(_POST2_CORRECTIONS___LOADS))
    return workspace


def _post2_corrections___call(workspace, **kwargs):
    return corrections.sector_offset_calibration(
        workspace,
        wheel_run_id="camp/sim_1/W",
        sector_run_id="camp/sim_2/S",
        calibration_id="c001",
        **kwargs,
    )


class TestPost2Corrections:
    """P0400-CALWRITE: the sector offset calibration is validated before it is written.

    At the 0.40.0 base sector_offset_calibration wrote the file first and read it
    back after, so a refused text stayed in the calibrations folder and, with
    overwrite, the calibration it replaced was already gone.
    """

    @staticmethod
    def test_p0400_calwrite_a_refused_text_never_replaces_the_calibration(tmp_path, monkeypatch):
        """P0400-CALWRITE: with overwrite, a text the reader refuses leaves the old file whole."""
        workspace = _post2_corrections___workspace(tmp_path, monkeypatch)
        path = calibration_path(workspace.inputs_dir, "c001")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("the calibration that was there\n", encoding="utf-8")
        monkeypatch.setattr(corrections, "calibration_text", lambda *_a, **_k: "route = [[[\n")
        with pytest.raises(CalibrationError):
            _post2_corrections___call(workspace, overwrite=True)
        assert path.read_text(encoding="utf-8") == "the calibration that was there\n"

    @staticmethod
    def test_p0400_calwrite_a_refused_text_leaves_no_file(tmp_path, monkeypatch):
        """P0400-CALWRITE: with no file before, a refused text writes none."""
        workspace = _post2_corrections___workspace(tmp_path, monkeypatch)
        monkeypatch.setattr(corrections, "calibration_text", lambda *_a, **_k: "route = [[[\n")
        with pytest.raises(CalibrationError):
            _post2_corrections___call(workspace)
        assert not calibration_path(workspace.inputs_dir, "c001").exists()

    @staticmethod
    def test_p0400_calwrite_a_valid_text_is_written(tmp_path, monkeypatch):
        """P0400-CALWRITE control: the helper's own text is written and reads back."""
        workspace = _post2_corrections___workspace(tmp_path, monkeypatch)
        path = _post2_corrections___call(workspace)
        calibration = corrections.read_calibration(path)
        assert calibration.route == "sector_offset" and len(calibration.rows) == 4


class TestPost2Harmonics:
    """P0400-COVERAGE: a harmonic is fitted only where the azimuths go round the circle.

    At the 0.40.0 base fit_harmonics chose 1P and 2P from the count of distinct
    azimuths alone, so five samples 0.1 deg apart on a constant load returned finite
    amplitudes of order 1e5.
    """

    @staticmethod
    def test_p0400_coverage_crowded_azimuths_leave_both_harmonics_none():
        """P0400-COVERAGE: five samples 0.1 deg apart fit H0 alone and say why."""
        psi = [0.0, 0.1, 0.2, 0.3, 0.4]
        noise = [0.0, 1e-6, -1e-6, 2e-6, 0.0]
        fit = fit_harmonics(psi, [1.0 + e for e in noise])
        assert fit.distinct == 5
        assert (fit.h1_amp, fit.h1_phase_deg, fit.h2_amp, fit.h2_phase_deg) == (None,) * 4
        assert fit.h0 == pytest.approx(1.0, abs=1e-5)
        assert fit.reason is not None and "1P term and above" in fit.reason

    @staticmethod
    def test_p0400_coverage_a_full_circle_five_point_fit_is_unchanged():
        """P0400-COVERAGE control: five azimuths round the circle still fit 1P and 2P."""
        psi = [0.0, 72.0, 144.0, 216.0, 288.0]
        load = [
            2.0
            + 0.5 * math.cos(math.radians(p - 30.0))
            + 0.25 * math.cos(math.radians(2 * p - 40.0))
            for p in psi
        ]
        fit = fit_harmonics(psi, load)
        assert fit.h0 == pytest.approx(2.0)
        assert (fit.h1_amp, fit.h1_phase_deg) == (pytest.approx(0.5), pytest.approx(30.0))
        assert (fit.h2_amp, fit.h2_phase_deg) == (pytest.approx(0.25), pytest.approx(40.0))
        assert getattr(fit, "reason", None) is None

    @staticmethod
    def test_p0400_coverage_a_resolved_first_harmonic_survives_a_narrow_second():
        """P0400-COVERAGE: the definition's five-point example fits 1P and omits 2P."""
        psi = [0.0, 10.0, 180.0, 190.0, 350.0]
        load = [2.0 + 0.5 * math.cos(math.radians(p - 30.0)) for p in psi]
        fit = fit_harmonics(psi, load)
        assert fit.h0 == pytest.approx(2.0)
        assert fit.h1_amp == pytest.approx(0.5)
        assert fit.h1_phase_deg == pytest.approx(30.0)
        assert fit.h2_amp is None and fit.h2_phase_deg is None
        assert fit.reason is not None and "2P term and above" in fit.reason


class TestPost2RotorProducts:
    """P0400-QSRECORD: an unreadable quasi-steady record is keyed under its point.

    At the 0.40.0 base the omission was filed under the made-up alias '?', which the
    file-name rule turned into ``polars/P<sim>-rotor_qs_positions.csv``, a file of a
    rotor no plan names.
    """

    @staticmethod
    def test_p0400_qsrecord_an_unreadable_record_is_keyed_under_the_run(tmp_path):
        """P0400-QSRECORD: the skip names runs/<run id>#qsteady_record and no rotor file."""
        workspace = _post_1_qsteady___recorded_wheel(tmp_path)
        (record,) = [
            r for r in workspace.read_manifest() if r.sim_id == "6001" and "AL+000" in r.run_id
        ]
        broken = workspace.sim_dir("6001") / "outputs" / "POLAR-6001_M20AL+000BE+000_qsteady.json"
        broken.write_text("{broken", encoding="utf-8")
        manifest, _folder, _log = _post_1_qsteady___post_recorded(workspace)
        key = f"runs/{record.run_id}#qsteady_record"
        assert key in manifest["skipped"]
        assert "POLAR-6001_M20AL+000BE+000" in manifest["skipped"][key]
        assert not [name for name in manifest["skipped"] if "?" in name]
        assert not [name for name in manifest["products"] if "?" in name]

    @staticmethod
    def test_p0430_rb3_inconsistent_load_columns_skip_only_the_rotor_tables(tmp_path):
        """RB3-02 (F-1370): the refusal is a named skip of the rotor's tables, never a lost sim.

        At d1d08f51 write_qsteady_tables raised ProductError out of this stage, and the
        campaign dropped every product of the simulation under one key naming no product.
        """
        workspace = _post_1_qsteady___recorded_wheel(tmp_path)
        records = [r for r in workspace.read_manifest() if r.sim_id == "6001"]
        second = workspace.sim_dir("6001") / "outputs" / "POLAR-6001_M20AL-020BE+000_qsteady.json"
        data = json.loads(second.read_text(encoding="utf-8"))
        data["families_blades"] = list(reversed(data["families_blades"]))
        second.write_text(json.dumps(data), encoding="utf-8")
        manifest, _folder, _log = _post_1_qsteady___post_recorded(workspace)
        (key,) = [name for name in manifest["skipped"] if name.endswith("_qs_positions.csv")]
        assert "inconsistent load columns" in manifest["skipped"][key]
        assert all(record.run_id in manifest["skipped"][key] for record in records)
        assert not [name for name in manifest["products"] if name.endswith("_qs_positions.csv")]
        assert any(name.endswith("_rotor.csv") for name in manifest["products"]), (
            "the rotor table of the simulation is still written"
        )


class TestPost1Acoustics:
    """P0400-ACOUSTICPRECISION (PFS-2105.032): the acoustic tables round-trip their numbers.

    Written at five fixed decimals, a 30 kHz clock alternated between 3e-5 and
    4e-5 s steps and a 4e-6 Pa harmonic was written as 0.00000.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-ACOUSTICPRECISION")])
    def test_p0400_acousticprecision_time_and_micro_pascals_survive(tmp_path):
        """P0400-ACOUSTICPRECISION: TIME_S at a 1e-5 s step and a 1e-6 Pa amplitude read back."""
        rate, samples = 100_000.0, 200
        times = tuple(n / rate for n in range(samples))
        pressure = tuple(1e-6 * math.cos(2 * math.pi * 5000.0 * t) for t in times)
        signal = AcousticSignal("m", 1.0, 0.0, 0.0, times, pressure)
        write_acoustic_products([signal], tmp_path, stem="P1", rotors={})
        (table,) = tmp_path.glob("P1_01_*_pressure.csv")
        with table.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert [float(row["TIME_S"]) for row in rows] == list(times)
        assert [float(row["PRESSURE_PA"]) for row in rows] == list(pressure)
        (spectrum,) = tmp_path.glob("P1_01_*_spectrum.csv")
        with spectrum.open(encoding="utf-8", newline="") as handle:
            peak = max(float(row["AMPLITUDE_PA"]) for row in csv.DictReader(handle))
        assert abs(peak - 1e-6) < 1e-9, peak


def _post_1_corrections___calibration(component: str) -> str:
    text = 'route = "table"\n'
    for alpha in (-4.0, 4.0):
        text += _post_1_corrections___row(component, 1.7, alpha, 0.0, 0.001, 1.1, 1.0, 0.0)
    return text


class TestPost1Corrections:
    """P0400-DERIVEDNA (PFS-2105.033): a column derived from a corrected component is NA.

    ETAW turns the whole force into wind axes, so a calibration of CN alone left
    it raw beside the corrected CN; THRUST is the shaft projection of FX to FZ, so
    a calibration of FX alone left THRUST and the rotor state derived from it raw.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-DERIVEDNA")])
    def test_p0400_derivedna_cn_alone_makes_etaw_na(tmp_path):
        """P0400-DERIVEDNA: a CN calibration leaves ETAW NA in the corrected rotor table."""
        extra = '\n[qsteady_correction]\nroute = "table"\nfile = "c001"\n'
        workspace = _post_1_corrections___recorded_wheel(
            tmp_path,
            pproc_extra=extra,
            files={"c001.toml": _post_1_corrections___calibration("CN")},
        )
        products, folder, _ = _post_1_corrections___post_recorded(workspace)
        (rotor,) = [
            name for name in products["products"] if name.endswith("PROP_rotor_corrected.csv")
        ]
        assert {row["ETAW_PROP"] for row in _post_1_corrections___table(folder, rotor)} == {"NA"}
        assert "ETAW_PROP" in products["products"][rotor]["derived_na"]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-DERIVEDNA")])
    def test_p0400_derivedna_fx_alone_makes_thrust_na(tmp_path):
        """P0400-DERIVEDNA: an FX calibration leaves THRUST, TORQUE and CT_ROTOR NA."""
        extra = '\n[qsteady_correction]\nroute = "table"\nfile = "c001"\n'
        workspace = _post_1_corrections___recorded_wheel(
            tmp_path,
            pproc_extra=extra,
            files={"c001.toml": _post_1_corrections___calibration("FX")},
        )
        products, folder, _ = _post_1_corrections___post_recorded(workspace)
        (average,) = [
            name for name in products["products"] if name.endswith("PROP_qs_avg_corrected.csv")
        ]
        rows = _post_1_corrections___table(folder, average)
        for column in ("THRUST_PROP", "TORQUE_PROP", "CT_ROTOR", "LAMBDA_I"):
            assert {row[column] for row in rows} == {"NA"}, column


class TestPost1Inflow:
    """P0400-MINUSXAXIS (PFS-2105.037): blade-view harmonics refuse a -X axis.

    omega's sign is its hand about +X; with a -X axis a positive omega turned
    left-handed about +X while every column of the product says right-handed.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-MINUSXAXIS")])
    def test_p0400_minusxaxis_is_refused():
        """P0400-MINUSXAXIS: (-1, 0, 0) is refused, naming +X and the sign of omega."""
        with pytest.raises(ProductError, match=r"\+X and a negative omega"):
            blade_view_harmonics(
                _post_1_inflow___uniform_at_aoa(5.0),
                hub=(0.0, 0.0, 0.0),
                axis=(-1.0, 0.0, 0.0),
                omega_rad_s=_POST_1_INFLOW__OMEGA,
                radii_m=[_POST_1_INFLOW__RADIUS],
            )
        assert blade_view_harmonics(
            _post_1_inflow___uniform_at_aoa(5.0),
            hub=(0.0, 0.0, 0.0),
            axis=(2.0, 0.0, 0.0),
            omega_rad_s=_POST_1_INFLOW__OMEGA,
            radii_m=[_POST_1_INFLOW__RADIUS],
        )


def _post_1_qsteady___sections(tmp_path, hub):
    path = tmp_path / "sections.csv"
    path.write_text(
        "ROTOR,FAMILY,PLANE,Offset,Chord,Fx,Fz\n"
        "PROP,B,XZ,1.5,0.2,10.0,2.0\n"
        "PROP,B,XZ,2.0,0.2,12.0,3.0\n"
        "PROP,C,XZ,1.0,0.2,8.0,1.0\n",
        encoding="utf-8",
    )
    record = SimpleNamespace(
        rotor_alias="PROP",
        rpm=1200.0,
        families_blades=["B", "C"],
        hub_m=hub,
        axis_vector=(1.0, 0.0, 0.0),
        shaft_frame_axis="X",
    )
    layout = [
        {"families": ["B"], "plane": "XZ", "frame": "MRP"},
        {"families": ["C"], "plane": "XZ", "frame": "PROP_RMRP"},
    ]
    validity = add_reduced_frequency_to_sections(
        path, cast(Any, record), velocity_m_per_s=30.0, layout=layout
    )
    rows = path.read_text(encoding="utf-8").splitlines()
    return validity, rows


class TestPost1Qsteady:
    """P0400 quasi-steady defects (post-1 lane).

    P0400-CLOCKINGSPEED (PFS-2105.036): a clocking whose export states no reference
    velocity is named in the clockings and average tables, as the rotor table names
    it, never read at the free-stream speed.
    P0400-MRPRADIUS (PFS-2105.035): a cut in the MRP frame places its station at
    Offset minus the hub's coordinate along the cut normal, and is NA where the hub
    sits off the plane's radial line.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-CLOCKINGSPEED")])
    def test_p0400_clockingspeed_a_clocking_without_reference_velocity_is_named(tmp_path):
        """P0400-CLOCKINGSPEED: clocking 1 states no reference velocity; its point is left out."""
        workspace = _post_1_qsteady___recorded_wheel(tmp_path)
        record = next(record for record in workspace.read_manifest() if record.sim_id == "6001")
        loads = workspace.sim_dir("6001") / record.outputs[0]
        second = loads.with_name(f"{loads.stem}_qs01.txt")
        lines = second.read_text(encoding="utf-8").splitlines(keepends=True)
        second.write_text(
            "".join(line for line in lines if "Reference velocity" not in line), encoding="utf-8"
        )
        products, _folder, _log = _post_1_qsteady___post_recorded(workspace)
        named = {
            key: why
            for key, why in products["skipped"].items()
            if key.split("#", 1)[0].endswith("_qs_positions.csv")
        }
        assert any(
            "clocking 1" in why and "states no reference velocity" in why for why in named.values()
        ), products["skipped"]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-MRPRADIUS")])
    def test_p0400_mrpradius_the_station_is_measured_from_the_hub(tmp_path):
        """P0400-MRPRADIUS: hub at y = 0.5; the station at Offset 1.5 is at r = 1.0."""
        validity, rows = _post_1_qsteady___sections(tmp_path, (0.0, 0.5, 0.0))
        header = rows[0].split(",")
        first = dict(zip(header, rows[1].split(","), strict=True))
        omega = 1200.0 * 2.0 * 3.141592653589793 / 60.0
        expected = reduced_frequency(
            omega_rad_s=omega, chord_m=0.2, radius_m=1.0, velocity_m_per_s=30.0
        )
        assert float(first["K_1P"]) == pytest.approx(expected, rel=1e-4)
        assert validity is not None

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-MRPRADIUS")])
    def test_p0400_mrpradius_a_hub_off_the_radial_line_is_na(tmp_path):
        """P0400-MRPRADIUS: hub at z = 0.3 (off the XZ cut's radial line): K_1P NA, said."""
        validity, rows = _post_1_qsteady___sections(tmp_path, (0.0, 0.0, 0.3))
        header = rows[0].split(",")
        first = dict(zip(header, rows[1].split(","), strict=True))
        assert first["K_1P"] == "NA"
        assert validity is not None
        assert any("K_1P of rotor PROP reads NA" in note for note in validity.notes), validity.notes
        assert validity.values["THRUST_PCT_K_GT_0_1"] is None


_POST_1_ROTOR_PLAN___TRACTOR = """
[rotors.TRACTOR]
alias = "TRACTOR"
x_m = 5.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 2.0
families_blades = ["T"]
blade1 = { azimuth_deg = 0.0, zero = "Y" }
"""


def _post_1_rotor_plan___plots_export(columns: str) -> str:
    names = [f"{part}_{columns}" for part in ("FX", "FY", "FZ", "MX", "MY", "MZ")]
    table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
    for step, force in enumerate(_POST_1_ROTOR_PLAN__SHAFT_FORCE, start=1):
        table += f"{step}.0000,{force:.4f},0.0000,0.0000,0.0000,0.0000,0.0000,\n"
    return (
        _POST_1_ROTOR_PLAN__PLOTS_HEADER + table + "-" * 70 + "\n     Force Units: Coefficients\n"
    )


def _post_1_rotor_plan___campaign(
    tmp_path: Path,
    *,
    alias: str = "PUSHER",
    reference: str = _POST_1_ROTOR_PLAN__REFERENCE,
    window: bool = True,
    clock: str = "PUSHER",
    second_point_without_mach: bool = False,
) -> tuple[list[Path], dict, list[str]]:
    """Post the superfile fixture's rotor simulation 6002 with the rotor as asked."""
    workspace = _post_1_rotor_plan___workspace(tmp_path)
    text = reference.replace(
        '[rotors.PUSHER]\nalias = "PUSHER"', f'[rotors."{alias}"]\nalias = "{alias}"'
    )
    (workspace.inputs_dir / "references" / "r002.toml").write_text(text, encoding="utf-8")
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        _post_1_rotor_plan___pproc("HUB_PUSHER", "MRP", '["B"]'), encoding="utf-8"
    )
    row = next(line for line in _POST_1_ROTOR_PLAN___MATRIX.splitlines() if line.startswith("6002"))
    stated = row.rstrip().replace("CLOCK_MOTION: PUSHER", f"CLOCK_MOTION: {clock}")
    if window:
        stated += " / LAST_REVS_AVG: 0.5"
    (workspace.root / "matriz.fs").write_text(
        _POST_1_ROTOR_PLAN___MATRIX.replace(row, stated), encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            plots = next(o for o in record.outputs if o.endswith("_plots.txt"))
            (workspace.sim_dir("6002") / plots).write_text(
                _post_1_rotor_plan___plots_export("HUB_PUSHER"), encoding="utf-8"
            )
            plan = dict(record.reductions or {})
            plan.update(time_iterations=4, steps_per_revolution=4.0)
            plan["rotors"] = {
                alias: {"blades": 6, "rpm": 2200.0, "steps_per_revolution": 4.0, "period_steps": 1}
            }
            record = record.model_copy(update={"reductions": plan})
            workspace.append_record(RunRecord(**record.model_dump()))
            if second_point_without_mach:
                folder = workspace.sim_dir("6002")
                outputs = []
                for name in record.outputs:
                    other = name.replace("J+170", "J+200")
                    (folder / other).write_text(
                        (folder / name).read_text(encoding="utf-8"), encoding="utf-8"
                    )
                    outputs.append(other)
                second = record.model_copy(
                    update={
                        "run_id": record.run_id.replace("J+170", "J+200"),
                        "point_name": record.point_name.replace("J+170", "J+200"),
                        "point": {"alpha": 0.0, "beta": 0.0, "advance_ratio": 2.0},
                        "outputs": outputs,
                        "mach": None,
                        "flight_condition": {"REmi": 4.38},
                    }
                )
                workspace.append_record(RunRecord(**second.model_dump()))
            continue
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = [Path(path) for path in _post_1_rotor_plan___post(workspace)]
    (manifest,) = workspace.root.rglob("products.json")
    return (
        written,
        json.loads(manifest.read_text(encoding="utf-8")),
        [str(warning.message) for warning in caught],
    )


class TestPost1RotorPlan:
    """P0400 rotor-table plan defects (post-1 lane), each measured through the post stage.

    P0400-ROTORPRODUCT (PFS-2100.012): the frozen-window judgement names the
    rotor table's real, sanitised path.
    P0400-CLOCKFOLD (PFS-2105.005): the J-mismatch warning finds the clock rotor
    case-folded, as clock_rotor_facts resolves it.
    P0400-NOCOEFFINSTANT (PFS-2105.006): a windowed row whose average cannot be
    made coefficients is left out and named, never written as the last step.
    P0400-ROTORMACH (PFS-2105.030): a record stating no Mach gets the
    simulation's Mach in the rotor table, not 0.0.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-ROTORPRODUCT")])
    def test_p0400_rotorproduct_judgement_names_the_sanitised_path(tmp_path, monkeypatch):
        """P0400-ROTORPRODUCT: the product a frozen-window warning names is the file written."""
        judged: list[str] = []

        def _recording(frozen, steps, *, point, product):
            judged.append(product)
            return None

        monkeypatch.setattr(_rotor_plan, "_judge_average", _recording)
        _written, manifest, _caught = _post_1_rotor_plan___campaign(tmp_path, alias="PUSH/ER")
        assert judged, "the averaging path was not reached"
        tables = [key for key in manifest["products"] if key.endswith("_rotor.csv")]
        assert tables == ["polars/P6002-PUSH_ER_rotor.csv"], tables
        assert set(judged) == set(tables), (judged, tables)

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-CLOCKFOLD")])
    def test_p0400_clockfold_mismatch_warns_for_a_case_folded_clock(tmp_path):
        """P0400-CLOCKFOLD: CLOCK_MOTION 'pusher' names rotor PUSHER of a two-rotor reference."""
        _written, _manifest, caught = _post_1_rotor_plan___campaign(
            tmp_path,
            reference=_POST_1_ROTOR_PLAN__REFERENCE + _POST_1_ROTOR_PLAN___TRACTOR,
            window=False,
            clock="pusher",
        )
        assert any("ran at J_PUSHER" in message for message in caught), caught

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-NOCOEFFINSTANT")])
    def test_p0400_nocoeffinstant_leaves_the_point_out(tmp_path, monkeypatch):
        """P0400-NOCOEFFINSTANT: no coefficients from the average means no row, and a reason."""
        monkeypatch.setattr(_rotor_plan, "_rotor_coefficients_from_newtons", lambda *a, **k: {})
        written, manifest, _caught = _post_1_rotor_plan___campaign(tmp_path)
        assert not [path for path in written if path.name.endswith("_rotor.csv")], written
        reasons = [why for key, why in manifest["skipped"].items() if key.endswith("_rotor.csv")]
        assert reasons and "cannot be made coefficients" in reasons[0], manifest["skipped"]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-ROTORMACH")])
    def test_p0400_rotormach_a_record_without_mach_takes_the_simulations(tmp_path):
        """P0400-ROTORMACH: the second point states no Mach; its row carries 0.1441, never 0."""
        written, _manifest, _caught = _post_1_rotor_plan___campaign(
            tmp_path, window=False, second_point_without_mach=True
        )
        (table,) = [path for path in written if path.name.endswith("-PUSHER_rotor.csv")]
        _columns, rows = read_csv_table(table)
        assert len(rows) == 2, rows
        assert [float(row["MACH"]) for row in rows] == [0.1441, 0.1441], rows


class TestPost1RotorProducts:
    """P0400 rotor-products defects (post-1 lane).

    P0400-ACOUSTICSKIP (PFS-2105.007): an unreadable acoustic export is a skip of
    its own point, so two points' reasons both survive in products.json.
    P0400-WALLTIMEREV (PFS-2105.008): the unsteady harmonics of a run a wall clock
    stopped are fitted over the last revolution the series holds, not one counted
    to the planned last step.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-ACOUSTICSKIP")])
    def test_p0400_acousticskip_each_point_keeps_its_own_reason(tmp_path):
        """P0400-ACOUSTICSKIP: two unreadable exports leave two named skips."""
        skipped: dict[str, str] = {}
        for stem in ("P1", "P2"):
            record = SimpleNamespace(run_id=f"run-{stem}", outputs=[f"{stem}_acoustic_signals.txt"])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _acoustic_products(
                    cast(Any, record),
                    sim_dir=tmp_path,
                    stem=stem,
                    out=tmp_path / "post",
                    rotors={},
                    clocks={},
                    target=lambda path: path,
                    skipped=skipped,
                )
        assert set(skipped) == {
            "acoustics/P1_acoustics_summary.csv",
            "acoustics/P2_acoustics_summary.csv",
        }, skipped
        assert "P1_acoustic_signals" in skipped["acoustics/P1_acoustics_summary.csv"]
        assert "P2_acoustic_signals" in skipped["acoustics/P2_acoustics_summary.csv"]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-WALLTIMEREV")])
    def test_p0400_walltimerev_the_fit_ends_where_the_series_ends(tmp_path, monkeypatch):
        """P0400-WALLTIMEREV: planned 20 steps, stopped at 14: the fit reads 7 to 12, not 13 to 18."""  # noqa: E501
        workspace = _post_1_rotor_products___unsteady(tmp_path, monkeypatch, blades=3, rpm=1200.0)
        (record,) = workspace.read_manifest()
        plan = dict(record.reductions or {})
        plan["time_iterations"] = 20
        stopped = record.model_copy(
            update={
                "status": RunStatus.WALLTIME_REACHED,
                "stopped_at": {"step": 14},
                "export_window": {**(record.export_window or {}), "time_iterations": 20},
                "reductions": plan,
            }
        )
        monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [stopped])
        _out, manifest, _log = _post_1_rotor_products___post(workspace)
        entry = manifest["products"]["sections/AL-020_harmonics.csv"]  # type: ignore[index]
        assert entry["revolution"] == {"PROP": [7, 12]}, entry
        assert entry["samples"] == 18, entry


def _post_1_rotor_table___row(run_id: str = "camp/sim_1/P1", **update):
    row = {
        "run_id": run_id,
        "surfaces": _post_1_rotor_table___surfaces(Blade1={"Cz": 0.5, "Cx": 0.2, "CMz": 0.1}),
        "condition": {"MACH": 0.15, "ALPHA": 0.0, "BETA": 0.0, "VINF": 40.0, "J": 0.5},
        "rpm": 3000.0,
        "density": 1.225,
        "speed": 40.0,
        "free_stream": 40.0,
    }
    row.update(update)
    return row


def _post_1_rotor_table___etaw(tmp_path, rows, **kwargs):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = write_rotor_table(
            tmp_path / "P1-PUSHER_rotor.csv",
            rotor=_post_1_rotor_table___rotor("Z"),
            rows=rows,
            reference=_post_1_rotor_table___reference(),
            **kwargs,
        )
    assert written is not None
    _columns, table = read_csv_table(written)
    return [row["ETAW_PUSHER"] for row in table], [str(w.message) for w in caught]


def _post_1_rotor_table___at(alpha: float, run_id: str, **condition):
    stated = {"MACH": 0.15, "ALPHA": alpha, "BETA": 0.0, "VINF": 40.0, "J": 0.5, **condition}
    return _post_1_rotor_table___row(run_id, condition=stated)


class TestPost1RotorTable:
    """P0400 rotor-table defects (post-1 lane).

    P0400-ETAWSENSE (PFS-2105.017): ETAW's sense is fixed once per rotor, so a lift
    rotor swept through alpha 0 keeps the sign of its ETAW.
    P0400-NOATTITUDE (PFS-2105.018): a row stating no ALPHA or BETA gets ETAW NA and a
    warning, never level flight; the keys are read case-folded.
    P0400-NAROWSAID (PFS-2105.040): a loads export in another frame is a refused row
    with its reason; a static row stays and is said once.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-ETAWSENSE")])
    def test_p0400_etawsense_a_lift_rotor_keeps_its_sign_through_alpha_zero(tmp_path):
        """P0400-ETAWSENSE: alpha -2 and +2 on a +Z rotor give ETAW of one sign."""
        etaw, _ = _post_1_rotor_table___etaw(
            tmp_path, [_post_1_rotor_table___at(-2.0, "r1"), _post_1_rotor_table___at(2.0, "r2")]
        )
        signs = {math.copysign(1.0, float(value)) for value in etaw}
        assert len(signs) == 1, etaw

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-NOATTITUDE")])
    def test_p0400_noattitude_is_na_and_said(tmp_path):
        """P0400-NOATTITUDE: no BETA gives NA and a line; lower-case keys are read."""
        no_beta = _post_1_rotor_table___row(
            "r1", condition={"MACH": 0.15, "ALPHA": 2.0, "VINF": 40.0, "J": 0.5}
        )
        lower = _post_1_rotor_table___row(
            "r2", condition={"MACH": 0.15, "alpha": 2.0, "beta": 0.0, "J": 0.5}
        )
        stated = _post_1_rotor_table___at(2.0, "r3")
        etaw, caught = _post_1_rotor_table___etaw(tmp_path, [no_beta, lower, stated])
        assert etaw[0] == "NA", etaw
        assert etaw[1] == etaw[2] != "NA", etaw
        assert any("state no ALPHA or BETA (r1)" in message for message in caught), caught

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-NAROWSAID")])
    def test_p0400_narowsaid_frame_refused_and_static_said(tmp_path):
        """P0400-NAROWSAID: frame BODY is left out with its reason; the static row is warned."""
        left_out: list[tuple[str, str]] = []
        written_runs: list[str] = []
        rows = [
            _post_1_rotor_table___row("r1", frame="BODY"),
            _post_1_rotor_table___row("r2", speed=0.0),
            _post_1_rotor_table___row("r3"),
        ]
        _etaw_values, caught = _post_1_rotor_table___etaw(
            tmp_path, rows, left_out=left_out, written_runs=written_runs
        )
        assert [run for run, _why in left_out] == ["r1"], left_out
        assert "analysis frame 'BODY'" in left_out[0][1]
        assert written_runs == ["r2", "r3"]
        assert any("static points (r2)" in message for message in caught), caught


def test_f139_a_harmonic_row_outside_the_grid_is_carried_as_na(tmp_path, monkeypatch):
    """F-139: the log promises NA in both corrected files; the harmonic row stays, NA."""
    from tests.tier1_offline.test_goal036_qsteady_corrections import (
        _section_calibration,
        _wheel_posted,
    )

    _, out, _, _ = _wheel_posted(
        tmp_path,
        monkeypatch,
        correction={"route": "table", "file": "c001"},
        calibration=_section_calibration(low=0.12),
    )
    _, raw = read_csv_table(out / "sections" / "DP_harmonics.csv")
    _, corrected = read_csv_table(out / "sections" / "DP_harmonics_corrected.csv")
    assert len(corrected) == len(raw)
    na = [row for row in corrected if row["H0"] == "NA" and row["H1_AMP"] == "NA"]
    assert na and len(na) < len(corrected)


def test_f175_the_theodorsen_function_is_right_where_float_phases_coincide():
    """F-175: C(k) tends to 1/2; a float phase gave 0.5 - 0.5j at k = 1e17."""
    from pyflightstream.post.corrections import theodorsen

    for k in (1e8, 1e12, 1e17, 1e30):
        assert abs(theodorsen(k) - 0.5) < 1e-8, k
    with pytest.raises(ProductError, match="beyond"):
        theodorsen(1e41)


def test_f4_0304_transfer_functions_survive_the_float_extremes():
    """F-176, F-177: a huge argument keeps its Bessel scale; a subnormal one the limit."""
    from pyflightstream.post._transfer_functions import bessel_j, sears, theodorsen

    # The phase of the expansion cannot be held beyond 1e40 (F-175): the largest arguments are
    # refused by name instead of answered with a wrong finite number, and the largest held one
    # keeps its Bessel scale (F-176: the amplitude does not overflow through pi * x).
    for x in (1e40,):
        assert math.isfinite(bessel_j(0, x))
        assert theodorsen(x) == pytest.approx(complex(0.5, 0.0), abs=1e-8)
        assert math.isfinite(abs(sears(x)))
    for x in (1e308, 1.7e308):
        with pytest.raises(ProductError, match="beyond"):
            bessel_j(0, x)
    for k in (5e-324, 1e-310, 1e-200):
        value = theodorsen(k)
        assert value.real == 1.0
        assert math.isfinite(value.imag) and abs(value.imag) < 1e-100
        assert math.isfinite(abs(sears(k)))


def test_f4_0304_a_harmonic_product_without_a_phase_column_is_a_named_skip(tmp_path):
    """F-1380: a missing H1_PHASE_DEG column is a nonblocking skip, not a ValueError."""
    folder = tmp_path / "sections"
    folder.mkdir()
    (folder / "p_sections.csv").write_text("ROTOR,Offset\nP,0.5\n", encoding="utf-8")
    (folder / "p_harmonics.csv").write_text(
        "ROTOR,QUANTITY,H0,H1_AMP\nP,CT,1,1\n", encoding="utf-8"
    )
    component = corrections.SECTION_COMPONENTS[0]
    rows = [CalibrationRow(component, 0.6, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0)]
    path = calibration_path(tmp_path, "c001")
    path.parent.mkdir(parents=True)
    path.write_text(calibration_text("sector_offset", rows, source_run_id="r"), encoding="utf-8")
    skipped: dict[str, str] = {}
    with pytest.warns(Warning, match="H1_PHASE_DEG"):
        written = corrections.write_qsteady_corrections(
            QsteadyCorrectionSpec(route="sector_offset", file="c001"),
            sim_id="1",
            inputs_dir=tmp_path,
            out=tmp_path,
            wheel_points=[corrections.WheelPointRef("p", "r", "P")],
            written_names={"sections/p_sections.csv": {}, "sections/p_harmonics.csv": {}},
            known_runs=None,
            target=lambda path: path,
            skipped=skipped,
        )
    assert written == [] and any("H1_PHASE_DEG" in why for why in skipped.values())


def test_f4_0304_a_nan_j_tolerance_is_refused(tmp_path, monkeypatch):
    """F-181: NaN would pass every J comparison, so offsets at different J were written."""
    workspace = _post2_corrections___workspace(tmp_path, monkeypatch)
    calls = iter([{**_POST2_CORRECTIONS___LOADS, "J": 0.9}, dict(_POST2_CORRECTIONS___LOADS)])
    monkeypatch.setattr(corrections, "_loads_of", lambda *_args: next(calls))
    with pytest.raises(CalibrationError, match="j_tolerance"):
        _post2_corrections___call(workspace, j_tolerance=float("nan"))
