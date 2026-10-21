"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

import pyflightstream.fsi.external as external
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError, fsi_workspace
from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.cases._fsi_external import EXTERNAL_NODES_FILE
from pyflightstream.cases.workflows import build_script, effective_fsi_config
from pyflightstream.cases.workflows._clock import _rotor_clock
from pyflightstream.fsi import beam, centrifugal, cli, driver, nodes
from pyflightstream.fsi.cli import main as fsi_main
from pyflightstream.fsi.config import BladeProperties, FsiConfig, config_sha256, dump_config
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.external import EXTERNAL_MANIFEST, external_step
from pyflightstream.fsi.loads import SectionBlock, to_elastic_axis
from pyflightstream.fsi.materials import SHEAR_MODULUS_DERIVED
from pyflightstream.fsi.sections import blade_properties_from_sections
from pyflightstream.fsi.state import DISPLACEMENT_FILE, LOADS_FILE, TwistIterationError, load_state
from pyflightstream.script import Script
from pyflightstream.workspace import fsi_setup
from pyflightstream.workspace.fsi_external_setup import FsiExternalSetupError, resolve_external_fsi
from pyflightstream.workspace.fsi_setup import FsiSetupError, resolve_fsi_setup, resolve_row_fsi
from tests.tier1_offline.test_aeroelastic_typed_setup import (
    coupled_case as _integfix_fsi__coupled_case,
)
from tests.tier1_offline.test_fsi_driver import CALL2 as _FSI_DRIVER__CALL2
from tests.tier1_offline.test_fsi_driver import driver_config as _fsi_driver__driver_config
from tests.tier1_offline.test_fsi_driver import driver_config as _fsi_review__driver_config
from tests.tier1_offline.test_fsi_driver import run_sequence as _fsi_driver__run_sequence
from tests.tier1_offline.test_fsi_driver import stage_run as _fsi_cli__stage_run
from tests.tier1_offline.test_fsi_driver import stage_run as _fsi_driver__stage_run
from tests.tier1_offline.test_fsi_driver import stage_run as _fsi_review__stage_run
from tests.tier1_offline.test_fsi_driver import write_loads as _fsi_cli__write_loads
from tests.tier1_offline.test_fsi_driver import write_loads as _fsi_driver__write_loads
from tests.tier1_offline.test_fsig_fixed_wing import _wing_update as _gaps_rt_fsiext___wing_update
from tests.tier1_offline.test_g06_actuator_disc import _lines as _gaps_rt_fsiext___lines
from tests.tier1_offline.test_g06_actuator_disc import _lines as _review_r8_fsi___lines
from tests.tier1_offline.test_g06_actuator_disc import _lines as _rfixb_fsi___lines
from tests.tier1_offline.test_g06_actuator_disc import _lines as _rfixr6_fsi___lines
from tests.tier1_offline.test_workflows import steady_case as _gaps_rt_fsiext__steady_case
from tests.tier1_offline.test_workflows import unsteady_case as _gaps_rt_fsiext__unsteady_case
from tests.tier1_offline.test_workspace_fsi_setup import (
    CALCULATED as _WORKSPACE_2_FSI_SETUP__CALCULATED,
)
from tests.tier1_offline.test_workspace_fsi_setup import (
    SUPPLIED as _WORKSPACE_2_FSI_SETUP__SUPPLIED,
)

_FSI_CLI__ROOT = Path(__file__).resolve().parents[2]


class TestFsiCli:
    """Tier 1: the pyfs-fsi items of the FSI lane of 0.40.0.

    P0400-STEPECHO (PFS-2085.003), P0400-FAILARCHIVE (PFS-2085.004),
    P0400-AERONODES (PFS-2085.005) and P0400-NOEXTRA (PFS-2095.014). Each test
    failed on the code before its fix.
    """

    @staticmethod
    def test_p0400_stepecho_an_explicit_step_says_why_it_failed(tmp_path, capsys):
        """P0400-STEPECHO: the console gets the cause and the log's path."""
        _fsi_cli__stage_run(tmp_path)  # no loads file: the coupled call fails
        assert cli.main(["step", "--out", str(tmp_path)]) == 1
        err = capsys.readouterr().err
        assert "pyfs-fsi step failed: FileNotFoundError" in err
        assert str(tmp_path / cli.ERROR_LOG) in err

    @staticmethod
    def test_p0400_stepecho_the_solvers_bare_call_stays_silent(tmp_path, capsys, monkeypatch):
        """P0400-STEPECHO: the control; the bare call's failure goes to the log alone."""
        _fsi_cli__stage_run(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert cli.main([]) == 1
        assert "pyfs-fsi step failed" not in capsys.readouterr().err
        assert "coupled step failed" in (tmp_path / cli.ERROR_LOG).read_text(encoding="utf-8")

    @staticmethod
    def test_p0400_failarchive_a_failed_call_keeps_the_loads_that_broke_it(tmp_path):
        """P0400-FAILARCHIVE: archived under fsi_archive/failed_<stamp>/."""
        _fsi_cli__stage_run(tmp_path)
        _fsi_cli__write_loads(tmp_path, 100)
        (tmp_path / driver.FAMILY_MAP_FILE).unlink()  # the call fails after reading the loads
        assert cli.coupled_step(tmp_path) == 1
        failed = sorted((tmp_path / cli.ARCHIVE_DIR).glob("failed_*"))
        assert len(failed) == 1
        kept = (failed[0] / driver.LOADS_FILE).read_text(encoding="utf-8")
        assert kept == (tmp_path / driver.LOADS_FILE).read_text(encoding="utf-8")

    @staticmethod
    def test_p0400_aeronodes_the_solvers_node_list_is_archived_with_the_call(tmp_path):
        """P0400-AERONODES: FSInodes.txt, when the solver wrote one, is part of the replay."""
        _fsi_cli__stage_run(tmp_path)
        _fsi_cli__write_loads(tmp_path, 100)
        (tmp_path / "FSInodes.txt").write_text("0.0,0.0,0.5\n", encoding="utf-8")
        assert cli.coupled_step(tmp_path) == 0
        archived = tmp_path / cli.ARCHIVE_DIR / "call_0001" / "FSInodes.txt"
        assert archived.read_text(encoding="utf-8") == "0.0,0.0,0.5\n"

    @staticmethod
    def test_p0400_noextra_a_missing_fsi_extra_reaches_the_error_log(tmp_path):
        """P0400-NOEXTRA: PyNite blocked, the coupled call logs the didactic refusal.

        In a fresh interpreter, because the driver and its beam are already
        imported in this one.
        """
        _fsi_cli__stage_run(tmp_path)
        script = (
            "import sys\n"
            "sys.modules['Pynite'] = None\n"
            "from pathlib import Path\n"
            "from pyflightstream.fsi import cli\n"
            "sys.exit(10 + cli.coupled_step(Path(sys.argv[1])))\n"
        )
        env = {**os.environ, "PYTHONPATH": str(_FSI_CLI__ROOT / "src")}
        done = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)],
            cwd=_FSI_CLI__ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert done.returncode == 11, done.stderr
        error = (tmp_path / cli.ERROR_LOG).read_text(encoding="utf-8")
        assert "coupled step failed" in error
        assert "fsi" in error and "Traceback" in error


_FSI_DRIVER__PRINTED_DT = "     Time increment (sec)                        .004\n"


def _fsi_driver___with_printed_dt(run_dir, iteration: int, printed: str) -> None:
    """Stage the fixture loads at an iteration, its header printing another dt."""
    _fsi_driver__write_loads(run_dir, iteration)
    path = run_dir / driver.LOADS_FILE
    text = path.read_text(encoding="utf-8")
    assert _FSI_DRIVER__PRINTED_DT in text
    path.write_text(
        text.replace(_FSI_DRIVER__PRINTED_DT, _FSI_DRIVER__PRINTED_DT.replace(".004", printed)),
        encoding="utf-8",
    )


def _fsi_driver___direct(cfg: FsiConfig) -> FsiConfig:
    return FsiConfig.model_validate({**cfg.model_dump(), "morphing": "direct"})


def _fsi_driver___logged_calls(run_dir) -> list[int]:
    lines = (run_dir / driver.LOG_FILE).read_text(encoding="utf-8").splitlines()
    return [int(line.split(",")[0]) for line in lines if line[:1].isdigit()]


def _fsi_driver___ellipse(chord: float, points: int = 48) -> list[list[float]]:
    """A 20 percent thick ellipse in the section frame, pitch axis at quarter chord."""
    out = []
    for k in range(points):
        angle = 2.0 * math.pi * k / points
        u = 0.5 - 0.5 * math.cos(angle)  # 0 at the leading edge, 1 at the trailing edge
        out.append([(0.25 - u) * chord, 0.1 * chord * math.sin(angle)])
    return out


class TestFsiDriver:
    """Tier 1: the coupling-driver and node-file items of the FSI lane of 0.40.0.

    P0400-DIRECTROUTE (PFS-2085.006, PFS-2085.014), P0400-DTBOUND (PFS-2088.005),
    P0400-NANDT (PFS-2086.004), P0400-COARSEDT (PFS-2088.004), P0400-CONFIGSTAMP
    (PFS-2094.001), P0400-LOGORDER (PFS-2103.016), P0400-UNSTEADYSHAPE
    (PFS-2087.001), P0400-EANODE (PFS-2104.014), P0400-FSIDISPCELL
    (PFS-2095.065) and P0400-LAYOUTRAISE (PFS-2095.015). Each test failed on the code before its fix.
    """  # noqa: E501

    @staticmethod
    def test_p0400_directroute_the_unsteady_route_refuses_direct_morphing(tmp_path):
        """P0400-DIRECTROUTE: the phase machine writes structural-node rows only."""
        _fsi_driver__stage_run(tmp_path, _fsi_driver___direct(_fsi_driver__driver_config()))
        _fsi_driver__write_loads(tmp_path, 100)
        with pytest.raises(FsiInputError, match="unsteady rotor route"):
            driver.coupling_step(tmp_path)
        assert not (tmp_path / driver.DISPLACEMENT_FILE).exists()

    @staticmethod
    def test_p0400_directroute_a_frozen_replay_refuses_direct_morphing(tmp_path):
        """P0400-DIRECTROUTE: the frozen file holds node rows, the solver reads vertex rows."""
        cfg = _fsi_driver__stage_run(tmp_path, _fsi_driver___direct(_fsi_driver__driver_config()))
        layout = nodes.generate_node_layout(cfg)
        nodes.write_fsidisp(tmp_path / driver.FROZEN_FILE, np.zeros((layout.total_nodes, 3)))
        with pytest.raises(FsiInputError, match="frozen replay"):
            driver.coupling_step(tmp_path)
        assert not (tmp_path / driver.DISPLACEMENT_FILE).exists()

    @staticmethod
    @pytest.mark.parametrize(("configured", "printed"), [(0.0045, ".005"), (0.0085, ".008")])
    def test_p0400_dtbound_a_half_thousandth_dt_is_accepted_either_way(
        tmp_path, configured, printed
    ):
        """P0400-DTBOUND: a dt ending in 5 at the fourth decimal is within print precision."""
        cfg = _fsi_driver__driver_config().model_copy(update={"time_increment_s": configured})
        _fsi_driver__stage_run(tmp_path, cfg)
        _fsi_driver___with_printed_dt(tmp_path, 100, printed)
        result = driver.coupling_step(tmp_path)
        assert result.revolutions == pytest.approx(
            driver.revolutions_per_step(cfg.omega_rad_per_s, configured)
        )

    @staticmethod
    @pytest.mark.parametrize("dt", [math.nan, math.inf])
    def test_p0400_nandt_revolutions_per_step_refuses_a_non_finite_dt(dt):
        """P0400-NANDT: `<= 0` let a NaN and an infinity through."""
        with pytest.raises(FsiInputError, match="advancing clock"):
            driver.revolutions_per_step(100.0, dt)
        with pytest.raises(FsiInputError, match="spinning rotor"):
            driver.revolutions_per_step(dt, 0.004)

    @staticmethod
    def test_p0400_nandt_a_header_printing_nan_is_refused_before_scheduling(tmp_path):
        """P0400-NANDT: a printed NaN dt is refused, even under a configured dt."""
        for configured in (None, 0.004):
            run_dir = tmp_path / str(configured)
            _fsi_driver__stage_run(
                run_dir,
                _fsi_driver__driver_config().model_copy(update={"time_increment_s": configured}),
            )
            _fsi_driver___with_printed_dt(run_dir, 100, "nan")
            with pytest.raises(FsiInputError, match="not a finite number"):
                driver.coupling_step(run_dir)
            assert not (run_dir / driver.STATE_FILE).exists()

    @staticmethod
    def test_p0400_coarsedt_an_unconfigured_printed_dt_is_warned_of(tmp_path):
        """P0400-COARSEDT: .004 s printed can be 12.5 percent off; the configured dt is not."""
        _fsi_driver__stage_run(tmp_path / "printed")
        _fsi_driver__write_loads(tmp_path / "printed", 100)
        with pytest.warns(PyflightstreamWarning, match="states no time_increment_s"):
            driver.coupling_step(tmp_path / "printed")
        _fsi_driver__stage_run(
            tmp_path / "set",
            _fsi_driver__driver_config().model_copy(update={"time_increment_s": 0.004}),
        )
        _fsi_driver__write_loads(tmp_path / "set", 100)
        with warnings.catch_warnings():
            warnings.simplefilter("error", PyflightstreamWarning)
            driver.coupling_step(tmp_path / "set")

    @staticmethod
    def test_p0400_configstamp_the_marker_covers_one_change_and_restamps_the_state(tmp_path):
        """P0400-CONFIGSTAMP: after the marker carried a change, the state holds the new digest."""
        cfg = _fsi_driver__stage_run(tmp_path)
        _fsi_driver__run_sequence(tmp_path, 3)
        changed = FsiConfig.model_validate({**cfg.model_dump(), "stiffness_scale_factor": 999.0})
        dump_config(changed, tmp_path / driver.CONFIG_FILE)
        marker = tmp_path / driver.ALLOW_CONFIG_CHANGE_FILE
        marker.write_text("", encoding="utf-8")
        _fsi_driver__write_loads(tmp_path, 500)
        assert driver.coupling_step(tmp_path).call == 4
        state = load_state(tmp_path / driver.STATE_FILE)
        assert state.config_sha256 == config_sha256(changed)
        # The decision is consumed by the stamp: the next call resumes without it.
        marker.unlink()
        _fsi_driver__write_loads(tmp_path, 540)
        assert driver.coupling_step(tmp_path).call == 5

    @staticmethod
    def test_p0400_logorder_a_call_killed_at_the_state_write_leaves_no_orphan_row(tmp_path):
        """P0400-LOGORDER: the retry of a killed call writes its call number once."""
        _fsi_driver__stage_run(tmp_path)
        _fsi_driver__run_sequence(tmp_path, 1)
        # A directory where the state's temporary file goes: the atomic write
        # fails exactly as a call killed at that point would leave it.
        blocker = tmp_path / (driver.STATE_FILE + ".tmp")
        blocker.mkdir()
        _fsi_driver__write_loads(tmp_path, 140)
        with pytest.raises(OSError):
            driver.coupling_step(tmp_path)
        blocker.rmdir()
        driver.coupling_step(tmp_path)  # the retry, from the state of call 1
        assert _fsi_driver___logged_calls(tmp_path) == [1, 2]

    @staticmethod
    def test_p0400_unsteadyshape_the_unsteady_route_refuses_a_changed_node_count(tmp_path):
        """P0400-UNSTEADYSHAPE: the previous-displacement guard is on the unsteady route too."""
        _fsi_driver__stage_run(tmp_path)
        _fsi_driver__run_sequence(tmp_path, 2)  # phase 1 twice
        path = tmp_path / driver.STATE_FILE
        state = json.loads(path.read_text(encoding="utf-8"))
        state["previous_displacements"] = state["previous_displacements"][:-3]
        path.write_text(json.dumps(state), encoding="utf-8")
        _fsi_driver__write_loads(tmp_path, 180)
        with pytest.raises(FsiInputError, match="node list changed between two calls"):
            driver.coupling_step(tmp_path)

    @staticmethod
    def test_p0400_eanode_a_moved_node_moves_with_the_rigid_section(tmp_path):
        """P0400-EANODE: every row is w + theta (p - e_true) about the configured axis.

        The elastic axis is configured at 60 percent chord, outside the node
        window, so the elastic-axis node sits at 30 percent chord; the beam is
        still solved about 60 percent. One quasi-steady rotor call with
        relaxation 1 writes the computed rows, read back along each station's
        section normal.
        """
        base = _fsi_driver__driver_config()
        chords = base.blade.chord_m
        blade = base.blade.model_copy(
            update={
                "elastic_axis_offset_chordwise_m": [(0.25 - 0.6) * c for c in chords],
                "section_contours_m": [_fsi_driver___ellipse(c) for c in chords],
            }
        )
        phases = base.phases.model_copy(update={"coupling_relaxation": 1.0})
        cfg = FsiConfig.model_validate(
            {**base.model_dump(), "blade": blade.model_dump(), "phases": phases.model_dump()}
        )
        _fsi_driver__stage_run(tmp_path, cfg)
        (tmp_path / driver.QUASI_STEADY_ROTOR_FILE).write_text("marker\n", encoding="utf-8")
        _fsi_driver__write_loads(tmp_path, 100)
        result = driver.coupling_step(tmp_path)

        layout = nodes.generate_node_layout(cfg)
        assert layout.ea_configured_chordwise_m is not None
        triads = nodes.station_triads(layout)
        (solution,) = result.solutions
        checked = 0
        for s in range(layout.station_count):
            e_true = (0.25 - 0.6) * chords[s]
            e_node = layout.ea_offset_chordwise_m[s]
            assert abs(e_node - e_true) > 0.05 * chords[s]  # the node did move
            offsets = {
                "elastic_axis": 0.0,
                "leading_edge": layout.le_offset_m[s],
                "trailing_edge": layout.te_offset_m[s],
            }
            for role, offset in offsets.items():
                row = result.displacements[layout.row_index(0, s, role)]
                normal = float(row @ triads[s, 1])
                rigid = solution.flap_deflection_m[s] + solution.elastic_twist_rad[s] * (
                    e_node + offset - e_true
                )
                assert normal == pytest.approx(rigid, rel=1e-9, abs=1e-15), (s, role)
                checked += 1
        assert checked == 3 * layout.station_count
        assert max(abs(t) for t in solution.elastic_twist_rad) > 1e-6  # the test can see theta

    @staticmethod
    def test_p0400_fsidispcell_a_non_numeric_cell_is_refused_naming_the_line(tmp_path):
        """P0400-FSIDISPCELL: a didactic refusal, not float()'s bare ValueError."""
        path = tmp_path / "FSIDisp.txt"
        path.write_text("0,0,0\n1,x,2\n", encoding="utf-8")
        with pytest.raises(FsiInputError, match=r"line 2 of FSIDisp\.txt .*not a number"):
            nodes.read_fsidisp(path)

    @staticmethod
    def test_p0400_layoutraise_a_foreign_node_map_is_an_fsi_input_error(tmp_path):
        """P0400-LAYOUTRAISE (PFS-2095.015): the catalogued class, not a bare ValueError."""
        cfg = _fsi_driver__stage_run(tmp_path)
        _fsi_driver__write_loads(tmp_path, 100)
        driver.coupling_step(tmp_path)  # writes the map from the config
        foreign = cfg.model_copy(update={"node_offset_chord_fraction": 0.1}, deep=True)
        nodes.write_node_map(nodes.generate_node_layout(foreign), tmp_path / cfg.node_map_file)
        _fsi_driver__write_loads(tmp_path, 140)
        with pytest.raises(FsiInputError, match="FSI-R14"):
            driver.coupling_step(tmp_path)

    @staticmethod
    def test_p0400_fixture_prints_the_dt_the_helpers_patch():
        """The helpers above rely on the fixture's header line."""
        assert _FSI_DRIVER__PRINTED_DT in _FSI_DRIVER__CALL2


_FSI_LOADS__STATIONS = [0.2, 0.6, 1.0]


_FSI_LOADS__SECTIONS = np.linspace(0.2, 1.0, 9)


def _fsi_loads___config(ea_chordwise_m: float, ea_normal_m: float = 0.0) -> FsiConfig:
    """A section-frame blade (Omega zero): the export columns are the section axes."""
    n = len(_FSI_LOADS__STATIONS)
    blade = BladeProperties(
        station_radii_m=_FSI_LOADS__STATIONS,
        chord_m=[0.2] * n,
        mass_per_length_kg_per_m=[2.0] * n,
        inertia_major_kg_m=[1.0e-3] * n,
        inertia_minor_kg_m=[1.0e-4] * n,
        bending_stiffness_n_m2=[1.0e4] * n,
        torsion_stiffness_n_m2=[1.0e3] * n,
        elastic_axis_offset_chordwise_m=[ea_chordwise_m] * n,
        elastic_axis_offset_normal_m=[ea_normal_m] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[0.0] * n,
    )
    return FsiConfig(blade_count=1, omega_rad_per_s=0.0, blade=blade)


def _fsi_loads___block(chordwise: float, normal: float, moment: float) -> SectionBlock:
    k = len(_FSI_LOADS__SECTIONS)
    return SectionBlock(
        family="blade_1",
        offset_m=_FSI_LOADS__SECTIONS,
        chord_m=np.full(k, 0.2),
        x_qc_m=np.zeros(k),
        z_qc_m=np.zeros(k),
        fx_n_per_m=np.full(k, chordwise),
        fz_n_per_m=np.full(k, normal),
        moment_qc_nm_per_m=np.full(k, moment),
    )


class TestFsiLoads:
    """Tier 1: P0400-EASIGN (PFS-2104.013), the pitch-axis to elastic-axis moment transfer's sign.

    The aerodynamic forces act at the pitch axis and the configuration's
    ``elastic_axis_offset_*`` runs from the pitch axis to the elastic axis, so
    the moment about the elastic axis is M_PA + (r_PA - r_EA) x F = M_PA - e x F.
    Both tests failed on the code before the fix, which added e x F.
    """

    @staticmethod
    def test_p0400_easign_lift_ahead_of_the_elastic_axis_twists_nose_up():
        """P0400-EASIGN: the physical oracle.

        Lift at the pitch axis with the elastic axis 5 cm aft of it acts ahead of
        the elastic axis and twists the section nose up: +10 N/m x 0.05 m. With
        the elastic axis ahead, the same lift twists it nose down.
        """
        lift = 10.0
        aft = to_elastic_axis(
            _fsi_loads___block(0.0, lift, 0.0), _fsi_loads___config(ea_chordwise_m=-0.05)
        )
        assert aft.moment_ea_nm_per_m == pytest.approx(np.full(len(_FSI_LOADS__SECTIONS), +0.5))
        ahead = to_elastic_axis(
            _fsi_loads___block(0.0, lift, 0.0), _fsi_loads___config(ea_chordwise_m=+0.05)
        )
        assert ahead.moment_ea_nm_per_m == pytest.approx(np.full(len(_FSI_LOADS__SECTIONS), -0.5))

    @staticmethod
    def test_p0400_easign_the_transfer_is_the_cross_product_of_the_lever_from_the_elastic_axis():
        """P0400-EASIGN: an independent check with numpy's cross product.

        In the right-handed triad (chordwise, normal, spanwise) the moment about
        the elastic axis of a force F at the pitch axis is M_PA plus the spanwise
        component of (r_PA - r_EA) x F, with r_PA - r_EA = -e.
        """
        e = np.array([0.031, -0.012, 0.0])
        force = np.array([7.0, -23.0, 0.0])
        moment_pa = 1.7
        loads = to_elastic_axis(
            _fsi_loads___block(force[0], force[1], moment_pa), _fsi_loads___config(e[0], e[1])
        )
        expected = moment_pa + np.cross(-e, force)[2]
        assert loads.moment_ea_nm_per_m == pytest.approx(
            np.full(len(_FSI_LOADS__SECTIONS), expected), rel=1e-12
        )


_FSI_MODAL__PLATE = [(0.02, 0.002), (-0.02, 0.002), (-0.02, -0.002), (0.02, -0.002)]


def _fsi_modal__plate_config(
    pitch_deg: float = 10.0, omega: float = 0.0, **blade_updates
) -> FsiConfig:
    """A flat titanium plate blade on three stations, uniform in every distribution."""
    blade = blade_properties_from_sections(
        [0.1, 0.3, 0.5],
        sections_m=[_FSI_MODAL__PLATE] * 3,
        chord_m=[0.04] * 3,
        geometric_pitch_deg=[pitch_deg] * 3,
        material="ti-6al-4v-grade5-annealed",
        geometry_source="a flat 40 x 4 mm plate",
    )
    data = {**blade.model_dump(), **blade_updates}
    return FsiConfig.model_validate({"blade_count": 2, "omega_rad_per_s": omega, "blade": data})


def _fsi_modal___first_flap(result: beam.ModalResult) -> float:
    return next(
        f for f, k in zip(result.frequencies_rad_per_s, result.kinds, strict=True) if k == "flap"
    )


class TestFsiModal:
    """Tier 1: the modal and rotating-solve items of the FSI lane of 0.40.0.

    P0400-MODALMASS (PFS-2095.010), P0400-FLAPSOFTEN (PFS-2085.002),
    P0400-CAMPBELLCONV (PFS-2088.003), P0400-TORSIONARRAY (PFS-2095.011),
    P0400-CGOFFSET (PFS-2085.013), P0400-FAMILYTRACK (PFS-2095.012) and
    P0400-SOUTHWELL (PFS-2095.013). Each test failed on the code before its fix.
    """

    @staticmethod
    def test_p0400_modalmass_a_station_without_twist_inertia_is_refused_by_name():
        """P0400-MODALMASS: a free station lumping no twist inertia is refused, naming it."""
        cfg = _fsi_modal__plate_config()
        i1 = list(cfg.blade.inertia_major_kg_m)
        i2 = list(cfg.blade.inertia_minor_kg_m)
        i1[1] = i2[1] = 0.0
        bare = _fsi_modal__plate_config(inertia_major_kg_m=i1, inertia_minor_kg_m=i2)
        model = beam.build_beam_model(bare)
        beam.solve_static(model)
        with pytest.raises(FsiInputError, match=r"station 1 .*twist inertia"):
            beam.modal_frequencies(model, bare, n_modes=4)

    @staticmethod
    def test_p0400_flapsoften_the_modal_problem_carries_the_in_plane_softening():
        """P0400-FLAPSOFTEN: omega_flap^2(beta) = omega_flap^2(0) - Omega^2 sin^2(beta).

        The oracle, by hand: with mu uniform, the softening the static solve
        applies, mu Omega^2 sin^2(beta) per unit span lumped over the tributary
        lengths, is Omega^2 sin^2(beta) times the lumped flap mass matrix. A
        stiffness term proportional to the mass matrix shifts every flap
        eigenvalue by exactly that factor, and flap and torsion do not couple in
        this beam, so the pitched blade's flap frequencies are the flat blade's
        lowered by Omega^2 sin^2(beta) in the squares. The geometric stiffness of
        the tension does not depend on the pitch.
        """
        omega = 150.0
        beta = 25.0
        flat = centrifugal.rotating_frequencies(_fsi_modal__plate_config(0.0, omega), n_modes=4)
        pitched = centrifugal.rotating_frequencies(_fsi_modal__plate_config(beta, omega), n_modes=4)
        expected = math.sqrt(
            _fsi_modal___first_flap(flat) ** 2 - omega**2 * math.sin(math.radians(beta)) ** 2
        )
        assert _fsi_modal___first_flap(pitched) == pytest.approx(expected, rel=1e-9)
        assert _fsi_modal___first_flap(pitched) < _fsi_modal___first_flap(flat)

    @staticmethod
    def test_p0400_flapsoften_a_flap_stiffness_entry_count_is_held_to_the_stations():
        """P0400-FLAPSOFTEN: the new modal term is sampled at the configuration stations."""
        cfg = _fsi_modal__plate_config()
        model = beam.build_beam_model(cfg)
        beam.solve_static(model)
        with pytest.raises(FsiInputError, match="flap_stiffness_n_per_m has 2 entries"):
            beam.modal_frequencies(model, cfg, flap_stiffness_n_per_m=[0.0, 0.0])

    @staticmethod
    def test_p0400_campbellconv_an_unsettled_static_solve_is_refused():
        """P0400-CAMPBELLCONV: no modes are linearized about an unconverged twist.

        A plate at a tenth of its torsional stiffness, 30 deg of pitch and
        1000 rad/s: the propeller moment outweighs the stiffness and the inner
        iteration exhausts its solves (measured, residual about 1.6 rad).
        """
        base = _fsi_modal__plate_config(30.0, 1000.0)
        soft = [0.1 * g for g in base.blade.torsion_stiffness_n_m2]
        cfg = _fsi_modal__plate_config(30.0, 1000.0, torsion_stiffness_n_m2=soft)
        assert not centrifugal.solve_rotating_static(cfg).converged
        with pytest.raises(TwistIterationError, match="did not converge"):
            centrifugal.rotating_frequencies(cfg, n_modes=2)

    @staticmethod
    def test_p0400_torsionarray_a_numpy_torsion_distribution_is_accepted():
        """P0400-TORSIONARRAY: an array solves as the same list does."""
        cfg = _fsi_modal__plate_config(10.0, 100.0)
        torsion = np.array([0.5, 0.3, 0.1])
        from_array = centrifugal.solve_rotating_static(cfg, torsion_moment_n_m_per_m=torsion)
        from_list = centrifugal.solve_rotating_static(cfg, torsion_moment_n_m_per_m=list(torsion))
        assert from_array.solution == from_list.solution

    @staticmethod
    def test_p0400_torsionarray_an_empty_torsion_distribution_is_refused():
        """P0400-TORSIONARRAY: empty is a wrong length, not 'no torsion'."""
        with pytest.raises(FsiInputError, match="torsion_moment_n_m_per_m has 0 entries"):
            centrifugal.solve_rotating_static(
                _fsi_modal__plate_config(), torsion_moment_n_m_per_m=[]
            )

    @staticmethod
    def test_p0400_cgoffset_the_twist_inertia_carries_the_parallel_axis_term():
        """P0400-CGOFFSET: (I1 + I2 + mu d^2) l, computed by hand."""
        cfg = _fsi_modal__plate_config(
            cg_offset_chordwise_m=[0.003] * 3, cg_offset_normal_m=[0.004] * 3
        )
        _, twist = beam.lumped_station_masses(cfg)
        blade = cfg.blade
        tributary = [0.1, 0.2, 0.1]
        expected = [
            (blade.inertia_major_kg_m[i] + blade.inertia_minor_kg_m[i])
            + blade.mass_per_length_kg_per_m[i] * 0.005**2
            for i in range(3)
        ]
        assert twist == pytest.approx(
            [e * t for e, t in zip(expected, tributary, strict=True)], rel=1e-12
        )

    @staticmethod
    def test_p0400_cgoffset_a_rotating_blade_with_a_cg_offset_is_warned():
        """P0400-CGOFFSET: the rotating model says it does not carry the offset."""
        cfg = _fsi_modal__plate_config(10.0, 100.0, cg_offset_chordwise_m=[0.003] * 3)
        with pytest.warns(PyflightstreamWarning, match="nonzero cg_offset on a rotating blade"):
            centrifugal.solve_rotating_static(cfg)
        with warnings.catch_warnings():
            warnings.simplefilter("error", PyflightstreamWarning)
            centrifugal.solve_rotating_static(_fsi_modal__plate_config(10.0, 100.0))

    @staticmethod
    def test_p0400_familytrack_a_family_absent_from_the_sweep_is_refused():
        """P0400-FAMILYTRACK: a didactic refusal, not a bare StopIteration."""
        data = centrifugal.campbell_sweep(_fsi_modal__plate_config(), [0.0, 10.0], n_modes=2)
        assert data.modal_results[0].kinds == ("flap", "flap")
        with pytest.raises(FsiInputError, match="larger n_modes"):
            data.family_track("torsion")

    @staticmethod
    @pytest.mark.parametrize("omegas", [[10.0, 10.0, 10.0], [10.0, -10.0, 10.0]])
    def test_p0400_southwell_one_omega_squared_is_refused(omegas):
        """P0400-SOUTHWELL: one distinct Omega^2 leaves the slope undefined."""
        with pytest.raises(FsiInputError, match="two distinct values of Omega"):
            centrifugal.southwell_fit(omegas, [1.0, 2.0, 3.0])


class TestFsiReview:
    """Regressions found in the adversarial review of the FSI release lane."""

    @staticmethod
    def test_p0400_failed_archive_preserves_the_original_failure(tmp_path, capsys):
        """P0400-FAILARCHIVE: archival failure cannot mask the coupling failure."""
        _fsi_review__stage_run(tmp_path)
        (tmp_path / cli.ARCHIVE_DIR).write_text("occupied", encoding="utf-8")

        assert cli.coupled_step(tmp_path, echo_failure=True) == 1

        error = capsys.readouterr().err
        assert "pyfs-fsi step failed: FileNotFoundError" in error
        assert str(tmp_path / cli.ERROR_LOG) in error
        log = (tmp_path / cli.ERROR_LOG).read_text(encoding="utf-8")
        assert "FS_SurfaceSection_Loads.txt" in log
        assert "could not archive the failed call" in log

    @staticmethod
    @pytest.mark.parametrize("configured", [[], [0.0], [0.0] * 100])
    def test_p0400_configured_axis_requires_one_value_per_station(configured):
        """P0400-EANODE: the new axis distribution obeys the map's shape contract."""
        layout = nodes.generate_node_layout(_fsi_review__driver_config())
        payload = {**layout.model_dump(), "ea_configured_chordwise_m": configured}
        with pytest.raises(ValidationError, match="ea_configured_chordwise_m.*entries"):
            nodes.NodeOrderingMap.model_validate(payload)

    @staticmethod
    def test_p0400_all_routes_share_the_section_load_reduction():
        """P0400-SHAREDLOADS: one reduction serves both rotors and the fixed wing."""
        tree = ast.parse(Path(driver.__file__).read_text(encoding="utf-8"))
        reductions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "to_elastic_axis"
        ]
        assert len(reductions) == 1, "all three routes must use the same per-family load reduction"


_GAPS_RT_FSIEXT__NODES = "0.25,0.0,0.0\n0.25,2.0,0.0\n0.25,4.0,0.0\n"


_GAPS_RT_FSIEXT__INPUT = """mode = "external"

[external]
executable = "bin/struct_wrapper.exe"
arguments = ["--quiet"]
structural_nodes = "f010.nodes.txt"
inputs = ["f010.model.dat"]
outputs = ["struct_log.txt"]

[coupling]
families = ["Wing"]
max_iterations = 30
"""


def _gaps_rt_fsiext___inputs(tmp_path: Path, text: str = _GAPS_RT_FSIEXT__INPUT) -> Path:
    folder = tmp_path / "inputs" / "fsi"
    (folder / "bin").mkdir(parents=True, exist_ok=True)
    (folder / "bin" / "struct_wrapper.exe").write_bytes(b"stand-in program bytes")
    (folder / "f010.nodes.txt").write_text(_GAPS_RT_FSIEXT__NODES, encoding="utf-8")
    (folder / "f010.model.dat").write_text("E = 70e9\n", encoding="utf-8")
    (folder / "f010.toml").write_text(text, encoding="utf-8")
    return folder / "f010.toml"


# --------------------------------------------------------------------------- FR-1094, FR-1095
def _gaps_rt_fsiext___external_case(tmp_path: Path, make=_gaps_rt_fsiext__steady_case):
    from pyflightstream.fsi.external import ExternalStructure

    structure = resolve_row_fsi(_gaps_rt_fsiext___inputs(tmp_path).parent.parent, {"FSI": "f010"})
    assert isinstance(structure, ExternalStructure)
    update = _gaps_rt_fsiext___wing_update(tmp_path, None)
    update["fsi"] = None
    update["fsi_external"] = structure
    update["fsi_provenance"] = structure.provenance()
    return make().model_copy(update=update), structure


def _gaps_rt_fsiext___steady_external():
    from pyflightstream.cases._fsi_external import EXTERNAL_NODES_FILE

    return [
        "AEROELASTIC_RBF_TYPE MULTI_QUADRATIC",
        "DELETE_AEROELASTIC_STRUCTURAL_NODES",
        "ASSIGN_AEROELASTIC_SURFACES 1",
        "2",
        "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS 1",
        "2",
        "IMPORT_AEROELASTIC_STRUCTURAL_NODES 2 DISABLE",
        EXTERNAL_NODES_FILE,
        "SET_AEROELASTIC_WORKING_DIRECTORY",
        ".",
        "SET_AEROELASTIC_POST_PROCESSING_SCRIPT",
        "fsi_post.txt",
        "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
    ]


# --------------------------------------------------------------------------- FR-1092, the step
_GAPS_RT_FSIEXT__STAND_IN = """import sys
mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
rows = [line for line in open("fsi_external_nodes.csv").read().splitlines() if line.strip()]
open("struct_log.txt", "w").write("called\\n")
if mode == "fail":
    sys.exit(3)
if mode == "silent":
    sys.exit(0)
count = len(rows) - 1 if mode == "short" else len(rows)
value = "nan" if mode == "nan" else "1.0000000000000000e-03"
with open("FSIDisp.txt", "w") as out:
    for _ in range(count):
        out.write("0.0000000000000000e+00,0.0000000000000000e+00," + value + "\\n")
"""


def _gaps_rt_fsiext___point(tmp_path: Path, mode: str = "ok") -> Path:
    from pyflightstream.cases._fsi_external import EXTERNAL_NODES_FILE
    from pyflightstream.fsi.external import EXTERNAL_MANIFEST, ExternalStructure

    folder = tmp_path / "point"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stand_in.py").write_text(_GAPS_RT_FSIEXT__STAND_IN, encoding="utf-8")
    (folder / EXTERNAL_NODES_FILE).write_text(_GAPS_RT_FSIEXT__NODES, encoding="utf-8")
    (folder / LOADS_FILE).write_text("loads of the call\n", encoding="utf-8")
    exe = Path(sys.executable)
    script = folder / "stand_in.py"
    structure = ExternalStructure(
        source=str(folder / "f010.toml"),
        source_sha256="0" * 64,
        executable=str(exe),
        executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
        arguments=["stand_in.py", mode],
        structural_nodes=str(folder / EXTERNAL_NODES_FILE),
        structural_nodes_sha256=hashlib.sha256(
            (folder / EXTERNAL_NODES_FILE).read_bytes()
        ).hexdigest(),
        node_count=3,
        inputs={"stand_in.py": str(script)},
        inputs_sha256={"stand_in.py": hashlib.sha256(script.read_bytes()).hexdigest()},
        outputs=["struct_log.txt"],
        timeout_s=60.0,
        families=["Wing"],
    )
    (folder / EXTERNAL_MANIFEST).write_text(structure.model_dump_json(), encoding="utf-8")
    return folder


class TestGapsRtFsiext:
    """P0400-FSIEXT (FR-462): an FSI row couples a structural program of the user's own.

    The input is read and refused at reading (FR-1090, FR-1093); the coupling block of a
    steady wing is held to the beam route's shape with the archiving step as the
    execution command and the user's node file imported (FR-1094); the run stages the
    manifest, the node file, the declared inputs and the provenance (FR-1095); and the
    step, run on a stand-in program that writes the PyNite-format displacements,
    archives and validates each call, failing on each defect FR-1092 names (FR-1092).
    """

    @staticmethod
    # --------------------------------------------------------------------------- FR-1090, FR-1093
    def test_p0400_fsiext_resolves_and_hashes(tmp_path):
        """P0400-FSIEXT (FR-1090, FR-1095): the program, nodes and inputs, hashed; three nodes."""
        from pyflightstream.fsi.external import ExternalStructure

        path = _gaps_rt_fsiext___inputs(tmp_path)
        structure = resolve_row_fsi(tmp_path / "inputs", {"FSI": "f010"})
        assert isinstance(structure, ExternalStructure)
        assert structure.node_count == 3
        exe = path.parent / "bin" / "struct_wrapper.exe"
        assert structure.executable_sha256 == hashlib.sha256(exe.read_bytes()).hexdigest()
        assert set(structure.inputs_sha256) == {"f010.model.dat"}
        assert structure.max_iterations == 30
        assert structure.provenance()["route"].startswith("B:")

    @staticmethod
    @pytest.mark.parametrize(
        ("old", "new", "words"),
        [
            ('arguments = ["--quiet"]', "show_console = true", "show_console"),
            ('mode = "external"', 'mode = "external"\nmorphing = "direct"', "morphing"),
            (
                'executable = "bin/struct_wrapper.exe"',
                'executable = "../elsewhere.exe"',
                "executable",
            ),
            ('inputs = ["f010.model.dat"]', 'inputs = ["absent.dat"]', "declared input"),
            ('families = ["Wing"]', 'families = ["Wing", "Tail"]', "one family"),
            ("max_iterations = 30", "max_iterations = 30\nrelaxation = 0.5", "Extra inputs"),
        ],
    )
    def test_p0400_fsiext_refusals_at_reading(tmp_path, old, new, words):
        """P0400-FSIEXT (FR-1093): each refusal names its key."""
        from pyflightstream.workspace.fsi_external_setup import (
            FsiExternalSetupError,
            resolve_external_fsi,
        )

        assert old in _GAPS_RT_FSIEXT__INPUT
        path = _gaps_rt_fsiext___inputs(tmp_path, _GAPS_RT_FSIEXT__INPUT.replace(old, new))
        with pytest.raises(FsiExternalSetupError, match=words):
            resolve_external_fsi(path)

    @staticmethod
    def test_p0400_fsiext_empty_node_file_is_refused(tmp_path):
        """P0400-FSIEXT (FR-1093): a node file with no node."""
        from pyflightstream.workspace.fsi_external_setup import (
            FsiExternalSetupError,
            resolve_external_fsi,
        )

        path = _gaps_rt_fsiext___inputs(tmp_path)
        (path.parent / "f010.nodes.txt").write_text("\n", encoding="utf-8")
        with pytest.raises(FsiExternalSetupError, match="no node"):
            resolve_external_fsi(path)

    @staticmethod
    def test_p0400_fsiext_factor_keys_are_refused(tmp_path):
        """P0400-FSIEXT (FR-1093): a factor key on an external row changes nothing, so refused."""
        _gaps_rt_fsiext___inputs(tmp_path)
        with pytest.raises(FsiSetupError, match="external"):
            resolve_row_fsi(
                tmp_path / "inputs", {"FSI": "f010", "FSI_BENDING_STIFFNESS_N_M2_FACTOR": "1.1"}
            )

    @staticmethod
    def test_p0400_fsiext_steady_block_and_staged_files(tmp_path):
        """P0400-FSIEXT (FR-1094, FR-1095): the beam route's block, the step as the command."""
        from pyflightstream.cases._fsi_external import EXTERNAL_NODES_FILE
        from pyflightstream.fsi.external import EXTERNAL_MANIFEST, ExternalStructure

        STEADY_EXTERNAL = _gaps_rt_fsiext___steady_external()
        case, structure = _gaps_rt_fsiext___external_case(tmp_path)
        lines, script = _gaps_rt_fsiext___lines(case)
        body = [line for line in lines if line.strip()]
        start = body.index("AEROELASTIC_RBF_TYPE MULTI_QUADRATIC")
        assert body[start : start + len(STEADY_EXTERNAL)] == STEADY_EXTERNAL
        assert body[start + len(STEADY_EXTERNAL) + 1] == "SET_AEROELASTIC_ITERATIONS 30"
        assert body[-1] == "EXECUTE_AEROELASTIC_ANALYSIS"
        assert ws.is_steady_aeroelastic_script(script.render())
        for absent in (
            "SET_MOTION_FSI_EXECUTABLE",
            "SET_MOTION_FSI_STRUCTURAL_NODES",
            "START_SOLVER",
        ):
            assert not any(line.startswith(absent) for line in body), absent
        staged = script.pending_input_files
        assert "main(['external', '--out', '.'])" in staged[ws.CALLBACK_FILE]
        assert ExternalStructure.model_validate_json(staged[EXTERNAL_MANIFEST]) == structure
        assert staged[EXTERNAL_NODES_FILE] == Path(structure.structural_nodes).read_bytes()
        assert "f010.model.dat" in staged
        assert json.loads(staged["fsi-provenance.json"])["mode"] == "external"

    @staticmethod
    def test_p0400_fsiext_unsteady_couples_in_the_march(tmp_path):
        """P0400-FSIEXT (FR-1094): one coupling iteration per step inside the march."""
        case, _ = _gaps_rt_fsiext___external_case(tmp_path, _gaps_rt_fsiext__unsteady_case)
        lines, _script = _gaps_rt_fsiext___lines(case)
        assert "SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE" in lines
        assert "SET_AEROELASTIC_ITERATIONS 1" in lines

    @staticmethod
    def test_p0400_fsiext_refuses_symmetry_and_a_second_distribution(tmp_path):
        """P0400-FSIEXT (FR-1093): symmetry copies and a second section distribution."""
        case, _ = _gaps_rt_fsiext___external_case(tmp_path)
        mirrored = case.model_copy(update={"variables": {**case.variables, "SYMMETRY": "MIRROR"}})
        with pytest.raises(CampaignConfigError, match="symmetry"):
            _gaps_rt_fsiext___lines(mirrored)
        assert case.pproc is not None
        doubled = case.pproc.model_copy(deep=True)
        doubled.sections.distributions.append(doubled.sections.distributions[0])
        with pytest.raises(CampaignConfigError, match="one section"):
            _gaps_rt_fsiext___lines(case.model_copy(update={"pproc": doubled}))

    @staticmethod
    def test_p0400_fsiext_step_archives_and_validates_a_call(tmp_path):
        """P0400-FSIEXT (FR-1091, FR-1092): the call archived with its record, through the CLI."""
        from pyflightstream.fsi.external import EXTERNAL_CALLS_LOG, external_step

        folder = _gaps_rt_fsiext___point(tmp_path)
        assert fsi_main(["external", "--out", str(folder)]) == 0
        archive = folder / "fsi_archive" / "call_0001"
        record = json.loads((archive / "call.json").read_text(encoding="utf-8"))
        assert record["verdict"] == "passed" and record["return_code"] == 0
        assert record["rows_written"] == 3 and record["node_count"] == 3
        assert {LOADS_FILE, "stand_in.py"} <= set(record["read_sha256"])
        assert set(record["written_sha256"]) == {DISPLACEMENT_FILE, "struct_log.txt"}
        for name in (LOADS_FILE, DISPLACEMENT_FILE, "struct_log.txt"):
            assert (archive / name).is_file(), name
        assert external_step(folder) == 0
        log = (folder / EXTERNAL_CALLS_LOG).read_text(encoding="utf-8").splitlines()
        assert log[0].startswith("call,") and len(log) == 3

    @staticmethod
    @pytest.mark.parametrize(
        ("mode", "words"),
        [
            ("fail", "returned 3"),
            ("silent", "wrote no FSIDisp.txt"),
            ("short", "2 rows for 3"),
            ("nan", "not finite"),
        ],
    )
    def test_p0400_fsiext_step_fails_each_defect(tmp_path, mode, words):
        """P0400-FSIEXT (FR-1092): a nonzero code, no file, a wrong count, a non-finite value."""
        from pyflightstream.fsi.external import external_step

        folder = _gaps_rt_fsiext___point(tmp_path, mode)
        assert external_step(folder) == 1
        error = (folder / "pyfs_fsi_error.log").read_text(encoding="utf-8")
        assert words in error
        record = json.loads(
            (folder / "fsi_archive" / "call_0001" / "call.json").read_text(encoding="utf-8")
        )
        assert record["verdict"] == "failed"

    @staticmethod
    def test_p0400_fsiext_step_refuses_a_changed_input(tmp_path):
        """P0400-FSIEXT (FR-1092): a declared input changed after the plan hashed it."""
        from pyflightstream.fsi.external import external_step

        folder = _gaps_rt_fsiext___point(tmp_path)
        (folder / "stand_in.py").write_text(
            _GAPS_RT_FSIEXT__STAND_IN + "\n# edited\n", encoding="utf-8"
        )
        assert external_step(folder) == 1
        assert "changed after the plan" in (folder / "pyfs_fsi_error.log").read_text(
            encoding="utf-8"
        )
        assert not (folder / DISPLACEMENT_FILE).exists()

    @staticmethod
    def test_p0400_fsiext_a_previous_answer_is_not_passed_on(tmp_path):
        """P0400-FSIEXT (FR-1092): the last call's FSIDisp.txt does not survive a silent call."""
        from pyflightstream.fsi.external import EXTERNAL_MANIFEST, external_step

        folder = _gaps_rt_fsiext___point(tmp_path)
        assert external_step(folder) == 0
        manifest = json.loads((folder / EXTERNAL_MANIFEST).read_text(encoding="utf-8"))
        manifest["arguments"] = ["stand_in.py", "silent"]
        (folder / EXTERNAL_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        assert external_step(folder) == 1


def test_p0430_f6_04_external_archives_invalid_encoding(tmp_path):
    import hashlib

    folder = _gaps_rt_fsiext___point(tmp_path)
    program = folder / "stand_in.py"
    program.write_text(
        "from pathlib import Path\nPath('FSIDisp.txt').write_bytes('0,0,0'.encode('utf-16'))\n",
        encoding="utf-8",
    )
    manifest_path = folder / EXTERNAL_MANIFEST
    manifest = json.loads(manifest_path.read_text())
    manifest["inputs_sha256"]["stand_in.py"] = hashlib.sha256(program.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert external_step(folder) == 1
    record = json.loads((folder / "fsi_archive/call_0001/call.json").read_text())
    assert record["verdict"] == "failed"
    assert "UTF-8" in record["reason"]


class TestIntegfixFsi:
    """Tier 1, 0.40.0 integration fixes of the FSI lane."""

    @staticmethod
    @pytest.fixture(autouse=True)
    def rotor_route_open(monkeypatch):
        """Open the unsteady_rotor FSI route, as the typed-setup wiring tests do."""
        guard = fsi_workspace.fsi_workflow_refusal
        monkeypatch.setattr(
            fsi_workspace,
            "fsi_workflow_refusal",
            lambda workflow: None if workflow == "unsteady_rotor" else guard(workflow),
        )

    @staticmethod
    def test_p0400_unsteady_route_stages_the_resolved_time_increment(tmp_path):
        """P0400-FSI-DT (PFS-2088.004): an unset time_increment_s is staged as the solver clock's dt.

        Without it the structural callback schedules on the loads header's
        three-decimal print of dt, off by up to 13 percent at 0.0035 s.
        """  # noqa: E501
        case = _integfix_fsi__coupled_case(tmp_path)
        assert case.fsi is not None
        unset = case.model_copy(
            update={"fsi": case.fsi.model_copy(update={"time_increment_s": None})}
        )
        resolved = _rotor_clock(unset).delta_time_s
        build_script(unset, Script("26.124"))  # the wiring accepts the unset field
        staged = effective_fsi_config(unset)
        assert staged is not None
        assert staged.time_increment_s == resolved
        assert '"time_increment_s": ' in staged.model_dump_json(indent=2)
        # a stated value is left as the row wrote it
        stated = effective_fsi_config(case)
        assert stated is not None and stated.time_increment_s == case.fsi.time_increment_s


class TestWorkspace2FsiSetup:
    """P0400-FSIROW: a row's FSI input is refused by name, and unity calibration changes nothing."""

    @staticmethod
    def test_p0400_fsirow_a_missing_input_lists_the_inputs_there(tmp_path: Path) -> None:
        """P0400-FSIROW (PFS-2095.031): FSI: f002 with only f001 present is an FsiSetupError naming
        the missing file and the inputs that exist, never a bare FileNotFoundError."""
        (tmp_path / "fsi").mkdir()
        (tmp_path / "fsi" / "f001.toml").write_text(
            _WORKSPACE_2_FSI_SETUP__SUPPLIED, encoding="utf-8"
        )
        with pytest.raises(FsiSetupError, match=r"f002\.toml.*f001"):
            resolve_row_fsi(tmp_path, {"FSI": "f002"})

    @staticmethod
    def test_p0400_fsirow_an_unknown_material_is_wrapped_naming_the_file(tmp_path: Path) -> None:
        """P0400-FSIROW (PFS-2095.031): the FSI package's refusal of an unknown material arrives as
        an FsiSetupError naming the source file."""
        path = tmp_path / "f002.toml"
        path.write_text(
            _WORKSPACE_2_FSI_SETUP__CALCULATED.replace("ti-6al-4v-grade5-annealed", "no-such-alloy")
        )
        with pytest.raises(FsiSetupError, match="f002.toml"):
            resolve_fsi_setup(path)

    @staticmethod
    def test_p0400_fsirow_placeholder_factor_cells_beside_no_fsi_are_blank(tmp_path: Path) -> None:
        """P0400-FSIROW (PFS-2100.021): FSI: - with FSI_* factor cells of '-' states no FSI, as the
        factor loop already reads '-', and is not refused with the add-an-input remedy."""
        row = {"FSI": "-", "FSI_BENDING_STIFFNESS_N_M2_FACTOR": "-"}
        assert resolve_row_fsi(tmp_path, row) is None

    @staticmethod
    def test_p0400_fsirow_a_derived_shear_modulus_stands_at_unity(tmp_path, monkeypatch) -> None:
        """P0400-FSIROW (PFS-2104.048): a derived-basis material whose stated G is rounded keeps it
        when no factor moves E or nu, so the effective beam is the base one with every origin unity;
        calibrating E re-derives G and says so in the origins."""
        titanium = fsi_setup.material("ti-6al-4v-grade5-annealed")
        rounded = replace(
            titanium,
            shear_modulus_basis=SHEAR_MODULUS_DERIVED,
            shear_modulus_pa=round(
                titanium.youngs_modulus_pa / (2 * (1 + titanium.poisson_ratio)), -9
            ),
        )
        monkeypatch.setattr(fsi_setup, "material", lambda key: rounded)
        path = tmp_path / "f002.toml"
        path.write_text(_WORKSPACE_2_FSI_SETUP__CALCULATED)
        result = resolve_fsi_setup(path)
        assert set(result.origins.values()) == {"unity"}
        assert result.material_effective == result.material_base
        assert result.effective.blade == result.base.blade
        scaled = resolve_fsi_setup(path, matrix_calibration={"youngs_modulus_pa": 2.0})
        assert scaled.origins["shear_modulus_pa"].startswith("derived")


class TestReviewR8Fsi:
    """REL8-001: outputs=['call.json.'] must never replace the call's archive record.

    REL9-001: the integration retained these tests but omitted the source fix.
    The invariant is checked at input resolution, planning and execution, including
    an actual two-call program whose distinct output bytes would otherwise be lost.
    """

    pytestmark = pytest.mark.requirement("FR-462")

    @staticmethod
    @pytest.mark.parametrize("name", ["call.json.", "call.json "])
    def test_rel8_001_resolve_refuses_archive_alias(tmp_path, name):
        path = _gaps_rt_fsiext___inputs(
            tmp_path,
            _GAPS_RT_FSIEXT__INPUT.replace('outputs = ["struct_log.txt"]', f'outputs = ["{name}"]'),
        )
        with pytest.raises(FsiExternalSetupError, match="archiving step"):
            resolve_external_fsi(path)

    @staticmethod
    @pytest.mark.parametrize("name", ["call.json.", "call.json "])
    def test_rel8_001_plan_refuses_archive_alias(tmp_path, name):
        case, structure = _gaps_rt_fsiext___external_case(tmp_path)
        changed = structure.model_copy(update={"outputs": [name]})
        with pytest.raises(CampaignConfigError, match="reserved-name collision"):
            _review_r8_fsi___lines(case.model_copy(update={"fsi_external": changed}))

    @staticmethod
    @pytest.mark.parametrize("name", ["call.json.", "call.json "])
    def test_rel8_001_two_calls_cannot_overwrite_archive_metadata(tmp_path, name):
        folder = _gaps_rt_fsiext___point(tmp_path)
        program = folder / "stand_in.py"
        program.write_text(
            _GAPS_RT_FSIEXT__STAND_IN
            + "\nfrom pathlib import Path\n"
            + "counter = Path('counter.txt')\n"
            + "count = int(counter.read_text()) + 1 if counter.exists() else 1\n"
            + "counter.write_text(str(count))\n"
            + f"Path({name!r}).write_text(str(count))\n",
            encoding="utf-8",
        )
        path = folder / EXTERNAL_MANIFEST
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["inputs_sha256"]["stand_in.py"] = hashlib.sha256(program.read_bytes()).hexdigest()
        manifest["outputs"] = [name]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        results = [external_step(folder), external_step(folder)]
        mismatches = []
        for record_path in (folder / "fsi_archive").glob("call_*/call.json"):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            for output, digest in record["written_sha256"].items():
                if hashlib.sha256((record_path.parent / output).read_bytes()).hexdigest() != digest:
                    mismatches.append((record["call"], output))
        assert results == [1, 1], (
            f"accepted alias: {results}; archive digest mismatches: {mismatches}"
        )
        assert not (folder / "counter.txt").exists(), "the structural program ran"
        assert not (folder / "fsi_archive").exists()
        assert "archiving step" in (folder / "pyfs_fsi_error.log").read_text(encoding="utf-8")


class TestRfixBFsi:
    """External FSI refuses coupling-file collisions and checks structural node bytes."""

    @staticmethod
    @pytest.mark.requirement("FR-462")
    @pytest.mark.parametrize(
        "name",
        [
            EXTERNAL_NODES_FILE,
            "fsi_callback.py",
            "fsi_external.json",
            "fsi_post.txt",
            "FSI_CALLBACK.PY",
        ],
    )
    @pytest.mark.parametrize("kind", ["inputs", "outputs"])
    def test_p0400_rfixb_reserved_fsi_names_are_refused_before_staging(tmp_path, name, kind):
        """P0400-RFIXB-FSI-COLLISION: user files cannot replace the coupling payloads."""
        case, structure = _gaps_rt_fsiext___external_case(tmp_path)
        value = {name: structure.structural_nodes} if kind == "inputs" else [name]
        changed = structure.model_copy(update={kind: value})
        with pytest.raises(CampaignConfigError, match="reserved-name collision"):
            _rfixb_fsi___lines(case.model_copy(update={"fsi_external": changed}))

    @staticmethod
    @pytest.mark.requirement("FR-462")
    @pytest.mark.parametrize("name", ["f010.toml", "f010.model.dat"])
    def test_p0400_rfixb_output_cannot_clobber_an_input(tmp_path, name):
        """P0400-RFIXB-FSI-COLLISION: the program's outputs cannot overwrite provenance or inputs."""  # noqa: E501
        case, structure = _gaps_rt_fsiext___external_case(tmp_path)
        changed = structure.model_copy(update={"outputs": [name]})
        with pytest.raises(CampaignConfigError, match="reserved-name collision"):
            _rfixb_fsi___lines(case.model_copy(update={"fsi_external": changed}))

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_rfixb_changed_same_count_nodes_are_not_staged(tmp_path):
        """P0400-RFIXB-FSI-NODES: three different nodes still violate the planned digest."""
        case, structure = _gaps_rt_fsiext___external_case(tmp_path)
        Path(structure.structural_nodes).write_text("0,0,0\n1,1,1\n2,2,2\n", encoding="utf-8")
        with pytest.raises(CampaignConfigError, match="node file changed"):
            _rfixb_fsi___lines(case)

    @staticmethod
    @pytest.mark.requirement("FR-462")
    @pytest.mark.parametrize("changed", ["missing", "changed"])
    def test_p0400_rfixb_step_checks_nodes_before_starting_program(tmp_path, changed):
        """P0400-RFIXB-FSI-DIGEST: missing or changed nodes refuse before any program call."""
        folder = _gaps_rt_fsiext___point(tmp_path)
        nodes = folder / EXTERNAL_NODES_FILE
        if changed == "missing":
            nodes.unlink()
        else:
            nodes.write_text("0,0,0\n1,1,1\n2,2,2\n", encoding="utf-8")
        assert external_step(folder) == 1
        assert not (folder / "struct_log.txt").exists()
        assert "structural node file" in (folder / "pyfs_fsi_error.log").read_text()

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_rfixb_call_records_the_verified_node_digest(tmp_path):
        """P0400-RFIXB-FSI-DIGEST: the call records the staged node bytes actually read."""
        folder = _gaps_rt_fsiext___point(tmp_path)
        assert external_step(folder) == 0
        record = json.loads((folder / "fsi_archive" / "call_0001" / "call.json").read_text())
        assert (
            record["read_sha256"][EXTERNAL_NODES_FILE]
            == hashlib.sha256((folder / EXTERNAL_NODES_FILE).read_bytes()).hexdigest()
        )


class TestRfixR6Fsi:
    """No declared external FSI file can land on a name the archiving step owns (FR-1092, FR-1093).

    P0400-RFIXR6-FSI (PFS-2081.121, REL6-001). The step writes ``call.json`` into
    every per-call archive beside the loads file, the displacement file and the
    declared outputs, and reads or writes a handful of files in the point folder.
    A declared input or output under one of those names would be overwritten, or
    would overwrite the step's own file, while the call reports success; each layer
    that reads the declaration refuses it instead, and no user byte is lost.
    """

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_rfixr6_the_step_names_its_archive_record_and_point_files():
        """P0400-RFIXR6-FSI: one home names every file the step owns, the record among them."""
        assert external.ARCHIVE_RECORD == "call.json"
        for name in (
            "call.json",
            EXTERNAL_MANIFEST,
            LOADS_FILE,
            DISPLACEMENT_FILE,
            "fsi_external_nodes.csv",
            "fsi_external_calls.csv",
            "pyfs_fsi_error.log",
            "fsi_external_stdout.txt",
            "fsi_archive",
        ):
            assert name in external.STEP_NAMES, name

    @staticmethod
    @pytest.mark.requirement("FR-462")
    @pytest.mark.parametrize("name", ["call.json", "Call.JSON", "fsi_external_stdout.txt"])
    def test_p0400_rfixr6_a_step_name_as_output_is_refused_at_reading(tmp_path, name):
        """P0400-RFIXR6-FSI: resolve refuses the output, naming it, before any plan."""
        path = _gaps_rt_fsiext___inputs(
            tmp_path,
            _GAPS_RT_FSIEXT__INPUT.replace('outputs = ["struct_log.txt"]', f'outputs = ["{name}"]'),
        )
        with pytest.raises(FsiExternalSetupError, match="the archiving step") as raised:
            resolve_external_fsi(path)
        assert repr(name) in str(raised.value)

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_rfixr6_a_step_name_as_input_is_refused_at_reading(tmp_path):
        """P0400-RFIXR6-FSI: an input staged as call.json is refused the same way."""
        path = _gaps_rt_fsiext___inputs(
            tmp_path,
            _GAPS_RT_FSIEXT__INPUT.replace('inputs = ["f010.model.dat"]', 'inputs = ["call.json"]'),
        )
        (path.parent / "call.json").write_text("{}\n", encoding="utf-8")
        with pytest.raises(FsiExternalSetupError, match="'call.json'"):
            resolve_external_fsi(path)

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_rfixr6_the_archive_record_name_is_refused_at_plan(tmp_path):
        """P0400-RFIXR6-FSI: a structure carrying call.json as output never reaches a script."""
        case, structure = _gaps_rt_fsiext___external_case(tmp_path)
        changed = structure.model_copy(update={"outputs": ["struct_log.txt", "CALL.json"]})
        with pytest.raises(CampaignConfigError, match="reserved-name collision") as raised:
            _rfixr6_fsi___lines(case.model_copy(update={"fsi_external": changed}))
        assert "call.json" in str(raised.value).casefold()

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_rfixr6_the_step_refuses_a_manifest_that_would_overwrite_its_record(tmp_path):
        """P0400-RFIXR6-FSI: the program is not run, nothing is archived, the user's file stays."""
        folder = _gaps_rt_fsiext___point(tmp_path)
        users = folder / "call.json"
        users.write_bytes(b"the structural program's own call.json\n")
        manifest = json.loads((folder / EXTERNAL_MANIFEST).read_text(encoding="utf-8"))
        manifest["outputs"] = ["struct_log.txt", "call.json"]
        (folder / EXTERNAL_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        assert external_step(folder) == 1
        error = (folder / "pyfs_fsi_error.log").read_text(encoding="utf-8")
        assert "'call.json'" in error and "the archiving step" in error
        assert not (folder / "struct_log.txt").exists(), "the program ran"
        assert not (folder / DISPLACEMENT_FILE).exists()
        assert not (folder / "fsi_archive").exists()
        assert users.read_bytes() == b"the structural program's own call.json\n"

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_rfixr6_every_archived_byte_matches_its_recorded_digest(tmp_path):
        """P0400-RFIXR6-FSI: across two calls, each archive holds what its record says it holds."""
        folder = _gaps_rt_fsiext___point(tmp_path)
        assert external_step(folder) == 0
        (folder / LOADS_FILE).write_text("loads of the second call\n", encoding="utf-8")
        assert external_step(folder) == 0
        for call in ("call_0001", "call_0002"):
            archive = folder / "fsi_archive" / call
            record = json.loads((archive / "call.json").read_text(encoding="utf-8"))
            assert set(record["written_sha256"]) == {DISPLACEMENT_FILE, "struct_log.txt"}
            for name, digest in record["written_sha256"].items():
                assert hashlib.sha256((archive / name).read_bytes()).hexdigest() == digest, name
            assert (
                hashlib.sha256((archive / LOADS_FILE).read_bytes()).hexdigest()
                == record["read_sha256"][LOADS_FILE]
            )
        first = folder / "fsi_archive" / "call_0001" / LOADS_FILE
        assert first.read_text(encoding="utf-8") == "loads of the call\n"
