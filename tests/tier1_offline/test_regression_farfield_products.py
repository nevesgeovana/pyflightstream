"""Regression coverage grouped by subject."""

from __future__ import annotations

import csv
import json
import lzma
import math
import re
import shutil
import warnings
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest

import tests.tier1_offline.test_regression_farfield_interfaces as _rfixa_products__plan
import tests.tier1_offline.test_regression_farfield_products as _ffproof_post__wing

# P0460 fixtures use the public export parser and the existing product harness.
import tests.tier1_offline.test_regression_farfield_products as _p0460_fixtures
import tests.tier1_offline.test_regression_farfield_products as _rfixa_products__post
import tests.tier1_offline.test_regression_farfield_products as _rfixa_products__wing
import tests.tier1_offline.test_regression_farfield_products as _rfixf_drag_split__ffpost
import tests.tier1_offline.test_regression_farfield_products as _rfixf_drag_split__wing
import tests.tier1_offline.test_regression_farfield_products as _rfixf_layout__ffpost
import tests.tier1_offline.test_regression_farfield_products as _rfixf_plane_lift__ffpost
import tests.tier1_offline.test_regression_farfield_products as _rfixf_qsteady__ffpost
import tests.tier1_offline.test_regression_farfield_products as _rfixf_status__ffpost
import tests.tier1_offline.test_regression_farfield_products as _rfixf_status__wing
import tests.tier1_offline.test_regression_farfield_products as _rfixf_traced_lift__ffpost
import tests.tier1_offline.test_regression_farfield_products as _rfixf_traced_lift__wing
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import PprocSpec
from pyflightstream.cases._farfield_spec import FarfieldSpec, LatticeShape
from pyflightstream.cases.farfield_inputs import resolve_farfield
from pyflightstream.cases.qsteady import QsteadyClocking, QsteadyRecord
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._farfield import plan_record
from pyflightstream.farfield import bernoulli_residual
from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.farfield_fields import (
    LEDGER_COLUMNS,
    ProbeSamples,
    far_samples,
    plane_values,
    recorded_layout,
)
from pyflightstream.post.farfield_products import farfield_axes, farfield_products
from pyflightstream.post.products import ReferenceValues, write_campaign_products
from pyflightstream.probes.layouts import farfield_plane, lattice_points
from pyflightstream.results import parse_loads, sweep_table, write_table
from pyflightstream.run import SWEEP_TABLE_NAME
from pyflightstream.run._pending import _write_probe_points
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace import RunRecord as _FarfieldProductsRunRecord
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.tier1_offline.test_post_products import LOADS as _FARFIELD_PRODUCTS__LOADS
from tests.tier1_offline.test_post_products import LOADS as _FFPROOF_POST__LOADS
from tests.tier1_offline.test_post_products import LOADS as _LITB_POST__LOADS
from tests.tier1_offline.test_post_products import PLOTS_HEADER as _FFPROOF_POST__PLOTS_HEADER
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _FFPROOF_PLAN___LATTICE as _RFIXF2_PLOTS___LATTICE,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _FFPROOF_PLAN___POINTS as _RFIXF2_PLOTS___POINTS,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___case as _rfixf2_plan_states___case,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___case as _rfixf_layout___case,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___script as _rfixf2_plan_states___script,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___script as _rfixf_layout___script,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _ffproof_plan___unsteady as _rfixf2_plots___unsteady,
)

# Transcribed numeric and header lines from the alpha-zero loads export.
LOADS = """Aerodynamic loads
     Angle of attack (Deg)                       .000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   30.000
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Solver mode:                                Steady
     Current solver iteration number:            51
     Reference velocity (m/s)                    30.000
     Reference length (m)                        1.000
     Reference area (m^2)                        8.000
     Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz
     ----------------------------------------------------------------------------------------------------
     Total,+0.0066,-0.0000,+0.0023,+0.0023,+0.0000,+0.0066,+0.0011,-0.0014,+0.0000
     ----------------------------------------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #8172026
"""


@pytest.mark.requirement("FR-38")
@pytest.mark.parametrize("recipe", ["steady", "unsteady", "unsteady_rotor", "qsteady_rotor"])
@pytest.mark.parametrize("named_rotor", [False, True])
def test_p0460_g4_rotor_is_not_a_thrust_balance(tmp_path, recipe, named_rotor):
    """Post identical probe fields: rotor G4 is NA; every other ledger value stays."""
    unsteady = recipe in ("unsteady", "unsteady_rotor")
    files = _p0450_probe_series(_FFPROOF_POST___POINTS_M)
    files[f"{_FFPROOF_POST___STEM}_plots.txt"] = (
        _FFPROOF_POST__PLOTS_HEADER
        + "Time-step,FX_MRP_TOTAL,CDO_MRP_TOTAL\n7,-10,0,\n8,-30,0,\n"
        + "-" * 60
        + "\n     Force Units: Newtons\nSoftware : Flightstream version 26.1, build #10052026\n"
    )
    results = []
    for control in (True, False):
        pproc = _FFPROOF_POST___LEDGERS + 'export_type = "avg_window"\nlast_steps = 2\n'
        if named_rotor and not control:
            pproc = pproc.replace('frame = "MRP"\ntip_radius_m = 1.0', 'rotor = "R"')
        workspace = _ffproof_post___campaign(
            tmp_path / ("control" if control else "subject"),
            pproc=pproc,
            files=files,
            recipe=("unsteady" if unsteady else "steady") if control else recipe,
            reductions={
                **_FFPROOF_POST___WINDOW,
                "rotors": {"R" if named_rotor and not control else "None": {"rpm": 0.0}},
            },
        )
        _ffproof_post___set_record(
            workspace,
            farfield_layout={
                "shapes": [
                    {
                        "kind": "lattice",
                        "source": "added",
                        "entry": None,
                        "count": len(_FFPROOF_POST___POINTS_M),
                        "axis": "X",
                        "origin_m": [0.0, 0.0, 0.0],
                        "positions_frame": "REFERENCE",
                        "lattice": _FFPROOF_POST___SHAPE.build(1.0).model_dump(mode="json"),
                    }
                ]
            },
        )
        _ffproof_post___post(workspace)
        suffixes = ("_instant", "_average") if unsteady else ("",)
        results.append(
            [
                row
                for suffix in suffixes
                for row in _rfixf_layout___rows(workspace.root, f"farfield/*_ledgers{suffix}.csv")
            ]
        )
    control_rows, rows = results
    assert rows and len(rows) == len(control_rows)
    rotor = named_rotor or recipe in ("unsteady_rotor", "qsteady_rotor")
    for baseline, row in zip(control_rows, rows, strict=True):
        for column in LEDGER_COLUMNS:
            if column in ("LATTICE", "SPURIOUS_COUNTS", "F_NEAR_N"):
                continue
            assert row[column] == baseline[column], column
        for column in ("SPURIOUS_COUNTS", "F_NEAR_N"):
            assert baseline[column] != "NA"
            assert row[column] == ("NA" if rotor else baseline[column])
    skips = _ffproof_post___manifest(workspace.root)["skipped"]
    reasons = [reason for key, reason in skips.items() if "SPURIOUS_COUNTS" in key]
    assert bool(reasons) is rotor
    if rotor:
        assert all("free-stream Bernoulli pressure" in reason for reason in reasons)
        assert all("no disk total-pressure jump" in reason for reason in reasons)


@pytest.mark.requirement("FR-38")
@pytest.mark.parametrize("axis", ["X", (0.6, 0.0, 0.8)])
@pytest.mark.parametrize("split", ["CDo", "CDv"])
def test_p0460_g4_export_split(tmp_path, axis, split):
    """Post export lines: -18 counts on X and the same projection on a tilted axis."""
    loads = LOADS.replace("CDi, CDo", "CDp, CDv") if split == "CDv" else LOADS
    lattice = _FFPROOF_POST___SHAPE.build(1.0)
    positions = lattice_points(lattice, axis=axis)
    export = _ffproof_post___probe_export(positions, 30.0)
    lines = export.splitlines()
    direction = np.array([1.0, 0.0, 0.0]) if axis == "X" else np.array(axis)
    # Uniform velocity on both planes cancels; uniform outlet pressure adds 7.938 N.
    area = np.pi * (lattice.ring_edges[-1] ** 2 - lattice.ring_edges[0] ** 2)
    for index, line in enumerate(lines):
        cells = line.split(",")
        if len(cells) > 10 and cells[0].strip() not in ("X", ""):
            xyz = np.array([float(c) for c in cells[:3]])
            cells[4] = str(7.938 / (551.25 * area) if xyz @ direction > 0 else 0)
            lines[index] = ",".join(cells)
    workspace = _ffproof_post___campaign(
        tmp_path,
        pproc=_FFPROOF_POST___LEDGERS,
        files={
            f"{_FFPROOF_POST___STEM}.txt": loads,
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": "\n".join(lines),
        },
    )
    _ffproof_post___set_record(
        workspace,
        point={"alpha": 0.0},
        reference={"SREF": 8.0, "CREF": 1.0, "BREF": 8.0},
        farfield_layout={
            "shapes": [
                {
                    "kind": "lattice",
                    "source": "added",
                    "entry": None,
                    "count": len(positions),
                    "axis": axis,
                    "origin_m": [0.0, 0.0, 0.0],
                    "positions_frame": "REFERENCE",
                    "lattice": lattice.model_dump(mode="json"),
                }
            ]
        },
    )
    _ffproof_post___post(workspace)
    rows = _rfixf_layout___rows(workspace.root, "farfield/*_ledgers.csv")
    assert rows
    near = 0.0 if axis == "X" else -0.0023 * 0.8 * 4410
    viscous = -29.106 * (1.0 if axis == "X" else 0.6)
    assert float(rows[-1]["FX_N"]) == pytest.approx(7.938, abs=0.001)
    assert float(rows[-1]["SPURIOUS_COUNTS"]) == pytest.approx((near - 7.938) / 4410 * 1e4, abs=0.1)
    assert float(rows[-1]["F_NEAR_N"]) == pytest.approx(near, abs=1e-5)
    assert float(rows[-1]["F_NEAR_VISCOUS_N"]) == pytest.approx(viscous, abs=1e-5)


@pytest.mark.requirement("FR-38")
@pytest.mark.parametrize("viscous", [False, True])
@pytest.mark.parametrize("group", ["MRP_TOTAL", "G1"])
def test_p0460_g4_history_split(tmp_path, viscous, group):
    """The window uses its own CDO, or names its absence and leaves near/G4 NA."""
    files = _p0460_fixtures._p0450_probe_series(_p0460_fixtures._FFPROOF_POST___POINTS_M)
    columns = "Time-step,FX_MRP_TOTAL" + (f",CDO_{group}" if viscous else "")
    rows = (
        "7,-10" + (",0.001" if viscous else "") + ",\n8,-30" + (",0.003" if viscous else "") + ","
    )
    files[f"{_p0460_fixtures._FFPROOF_POST___STEM}_plots.txt"] = (
        _p0460_fixtures._FFPROOF_POST__PLOTS_HEADER
        + columns
        + "\n"
        + rows
        + "\n"
        + "-" * 60
        + "\n     Force Units: Newtons\nSoftware : Flightstream version 26.1, build #10052026\n"
    )
    workspace = _p0460_fixtures._ffproof_post___campaign(
        tmp_path,
        pproc=_p0460_fixtures._FFPROOF_POST___LEDGERS
        + 'export_type = "avg_window"\nlast_steps = 2\n',
        files=files,
        recipe="unsteady",
        reductions=_p0460_fixtures._FFPROOF_POST___WINDOW,
        positions=True,
    )
    if group == "G1":
        _ffproof_post___set_record(
            workspace,
            inventory=["Wing"],
            reductions={
                **_FFPROOF_POST___WINDOW,
                "plot_groups": [
                    {
                        "name": "MRP_TOTAL",
                        "parameters": ["FX"],
                        "frame": "MRP",
                        "families": ["Wing"],
                    },
                    {"name": "G1", "parameters": ["CDO"], "frame": "MRP", "families": ["Wing"]},
                ],
            },
        )
    _p0460_fixtures._ffproof_post___post(workspace)
    root = workspace.root
    _, rows = _p0460_fixtures._ffproof_post___table(
        _p0460_fixtures._ffproof_post___one(root, "farfield/*_ledgers_average.csv")
    )
    if not viscous:
        assert all(row["SPURIOUS_COUNTS"] == "NA" for row in rows)
        assert all(row.get("F_NEAR_N") == "NA" for row in rows)
        assert "history has no viscous drag" in str(
            _p0460_fixtures._ffproof_post___manifest(root)["skipped"]
        )
    else:
        qs = 0.5 * _p0460_fixtures._FFPROOF_POST___RHO * 68.058**2 * 50
        # The history banner states VREF = 2 VINF; written CDO is scaled by four.
        drag = -0.002 * 4 * qs * np.cos(np.deg2rad(-2))
        for row in rows:
            assert float(row["SPURIOUS_COUNTS"]) == pytest.approx((20 - drag) / qs * 1e4, rel=1e-5)
            assert float(row["F_NEAR_N"]) == pytest.approx(20 - drag, rel=1e-5)
            assert float(row["F_NEAR_VISCOUS_N"]) == pytest.approx(drag, rel=1e-5)


@pytest.mark.requirement("FR-38")
@pytest.mark.parametrize("rotor", [False, True])
@pytest.mark.parametrize("averaged", [False, True])
def test_p0460_g3_blade_passage(tmp_path, rotor, averaged):
    """A six-blade passage of .4828 leaves the 3.47e-5 m/s m=1 floor."""
    points = _FFPROOF_POST___POINTS_M
    export = _ffproof_post___probe_export(points, 68.058)
    lines = export.splitlines()
    for index, line in enumerate(lines):
        cells = line.split(",")
        if len(cells) > 10 and cells[0].strip() not in ("X", ""):
            psi = math.atan2(float(cells[1]), float(cells[2]))
            u = 68.058 + 2 * 0.4828 * math.cos(6 * psi) + 2 * 3.47e-5 * math.cos(psi)
            cells[5] = cells[8] = f"{u:.12e}"
            lines[index] = ",".join(cells)
    export = "\n".join(lines)
    files = {f"{_FFPROOF_POST___STEM}_farfield_survey.txt": export}
    if averaged:
        files.update(
            {
                f"{_FFPROOF_POST___STEM}_farfield_survey_iteration={step}.txt": export
                for step in (7, 8)
            }
        )
    pproc = _FFPROOF_POST___LEDGERS.replace("m_max = 2", "m_max = 6")
    if rotor:
        pproc = pproc.replace('frame = "MRP"\ntip_radius_m = 1.0', 'rotor = "R"')
    workspace = _ffproof_post___campaign(
        tmp_path,
        pproc=pproc + 'export_type = "avg_window"\nlast_steps = 2\n',
        files=files,
        recipe="unsteady_rotor" if averaged else "steady",
        reductions={**_FFPROOF_POST___WINDOW, "rotors": {"R": {"blades": 6}}},
    )
    _ffproof_post___set_record(
        workspace,
        farfield_layout={
            "shapes": [
                {
                    "kind": "lattice",
                    "source": "added",
                    "entry": None,
                    "count": len(points),
                    "axis": "X",
                    "origin_m": [0.0, 0.0, 0.0],
                    "positions_frame": "REFERENCE",
                    "lattice": _FFPROOF_POST___SHAPE.build(1.0).model_dump(mode="json"),
                }
            ]
        },
    )
    _ffproof_post___post(workspace)
    suffix = "_average" if averaged else ""
    rows = _rfixf_layout___rows(workspace.root, f"farfield/*_ledgers{suffix}.csv")
    assert rows
    expected = 3.47e-5 if rotor else 0.4828
    assert all(float(row["SYMMETRY_FLOOR"]) == pytest.approx(expected, abs=1e-8) for row in rows)
    entry = _ffproof_post___entry(_ffproof_post___manifest(workspace.root), f"_ledgers{suffix}.csv")
    assert entry.get("symmetry_excluded_orders", {}).get(_FFPROOF_POST___STEM, {}).get("power") == (
        [6] if rotor else []
    )


_FARFIELD_PRODUCTS__ALPHA = -2.0


_FARFIELD_PRODUCTS__SPEED = 68.058


_FARFIELD_PRODUCTS__RHO = 1.225


_FARFIELD_PRODUCTS__BREF = 20.0


_FARFIELD_PRODUCTS__SREF = 50.0


_FARFIELD_PRODUCTS__CL = 0.1882829


_FARFIELD_PRODUCTS__STATIONS = 160


_FARFIELD_PRODUCTS___RULE = " " + "-" * 100 + "\n"


@pytest.mark.parametrize(
    "cl_plane,cl_near,flagged",
    [
        (-5.4e-15, -7.4e-5, False),
        (0.0034, 0.0023, True),
        (0.334, 0.3342, False),
        (0.002, 0.0, True),
    ],
)
def test_p0450_ff6_plane_lift_near_zero(tmp_path, cl_plane, cl_near, flagged):
    """LIC-05: compare absolute lift below 1e-3, relative lift above it."""
    row, flags = _rfixf_plane_lift___post(
        tmp_path, cl_plane / _RFIXF_PLANE_LIFT___CL, near_cl=cl_near
    )
    assert float(row["CL_T"]) == pytest.approx(cl_plane, rel=0.02, abs=1e-8)
    assert bool(flags) is flagged


@pytest.mark.parametrize("history", ["complete", "absent", "gap"])
def test_p0450_ff6_g4_uses_same_window_loads(tmp_path, history):
    """LIC-04: post a two-step window; G4 compares the two means, never final loads."""
    files = _p0450_probe_series(_FFPROOF_POST___POINTS_M)
    if history != "absent":
        rows = "Time-step,FX_MRP_TOTAL,CDO_MRP_TOTAL\n1,-9000,0,\n7,-10,0,\n"
        if history != "gap":
            rows += "8,-30,0,\n"
        files[f"{_FFPROOF_POST___STEM}_plots.txt"] = (
            _FFPROOF_POST__PLOTS_HEADER
            + rows
            + "-" * 60
            + "\n     Force Units: Newtons\nSoftware : Flightstream version 26.1, build #7012026\n"
        )
    workspace = _ffproof_post___campaign(
        tmp_path,
        pproc=_FFPROOF_POST___LEDGERS + 'export_type = "avg_window"\nlast_steps = 2\n',
        files=files,
        recipe="unsteady",
        reductions=_FFPROOF_POST___WINDOW,
        positions=True,
    )
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    _, mean = _ffproof_post___table(_ffproof_post___one(root, "farfield/*_ledgers_average.csv"))
    _, instant = _ffproof_post___table(_ffproof_post___one(root, "farfield/*_ledgers_instant.csv"))
    assert all(row["SPURIOUS_COUNTS"] != "NA" for row in instant)
    if history == "complete":
        # Uniform axial speed on both planes: each step's downstream-minus-upstream
        # flux is zero. The near mean is -( -10 -30 ) / 2 = 20 N, not 30 or 9000.
        expected = 20.0 / (0.5 * _FFPROOF_POST___RHO * 68.058**2 * 50.0) * 1e4
        assert all(row["SPURIOUS_COUNTS"] != "NA" for row in mean)
        assert all(
            float(row["SPURIOUS_COUNTS"]) == pytest.approx(expected, rel=1e-5) for row in mean
        )
    else:
        assert all(row["SPURIOUS_COUNTS"] == "NA" for row in mean)
        skipped = _ffproof_post___manifest(root)["skipped"]
        assert any(
            "SPURIOUS_COUNTS" in key and "loads history" in reason
            for key, reason in skipped.items()
        )


@pytest.mark.parametrize("parameters", ['"FX"', '"FX", "FY", "FZ", "MX", "MY", "MZ"'])
@pytest.mark.parametrize("families", ['["Wing"]', '"all"', '["Wing", "Tail"]'])
@pytest.mark.parametrize("recorded", [False, True])
def test_p0450_rv2_g4_requires_whole_configuration(tmp_path, parameters, families, recorded):
    """RV2-02: a user-defined MRP_TOTAL may hold only one part of the configuration."""
    files = _p0450_probe_series(_FFPROOF_POST___POINTS_M)
    files[f"{_FFPROOF_POST___STEM}_plots.txt"] = (
        _FFPROOF_POST__PLOTS_HEADER
        + "Time-step,FX_MRP_TOTAL,CDO_MRP_TOTAL\n7,-10,0,\n8,-30,0,\n"
        + "-" * 60
        + "\n     Force Units: Newtons\nSoftware : Flightstream version 26.1, build #7012026\n"
    )
    workspace = _ffproof_post___campaign(
        tmp_path,
        pproc=_FFPROOF_POST___LEDGERS
        + 'export_type = "avg_window"\nlast_steps = 2\n'
        + f'[plots]\nparameters = [{parameters}]\n[[plots.groups]]\nname = "MRP_TOTAL"\n'
        + f'frame = "MRP"\nfamilies = {families}\n',
        files=files,
        recipe="unsteady",
        reductions=_FFPROOF_POST___WINDOW,
    )
    reductions = dict(_FFPROOF_POST___WINDOW)
    if recorded:
        reductions["plot_groups"] = [
            {
                "name": "MRP_TOTAL",
                "frame": "MRP",
                "parameters": ["FX", "CDO"],
                "families": ["Wing"] if families == '["Wing"]' else ["Wing", "Tail"],
            }
        ]
        # Current declarations cannot turn a recorded subset into a total.
        path = workspace.inputs_dir / "pproc" / "p001.toml"
        path.write_text(path.read_text().replace(f"families = {families}", 'families = "all"'))
    _ffproof_post___set_record(workspace, inventory=["Wing", "Tail"], reductions=reductions)
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    rows = _rfixf_layout___rows(root, "farfield/*_ledgers_average.csv")
    assert rows
    if families == '["Wing"]':
        assert all(row["SPURIOUS_COUNTS"] == "NA" for row in rows)
        assert "whole-configuration" in str(_ffproof_post___manifest(root)["skipped"])
    else:
        expected = 20.0 / (0.5 * _FFPROOF_POST___RHO * 68.058**2 * 50.0) * 1e4
        assert all(
            float(row["SPURIOUS_COUNTS"]) == pytest.approx(expected, rel=1e-5) for row in rows
        )


@pytest.mark.parametrize("variant", ["plane", "power"])
@pytest.mark.requirement("FR-1052")
def test_p0450_rv2_wrong_geometry_cannot_shorten_average(tmp_path, variant):
    """RV2-01: a readable snapshot missing its point set cannot become a partial mean."""
    if variant == "plane":
        workspace = _p0450_plane_series(tmp_path)
    else:
        workspace = _ffproof_post___campaign(
            tmp_path,
            pproc=_FFPROOF_POST___LEDGERS + 'export_type = "avg_window"\n',
            files=_p0450_probe_series(_FFPROOF_POST___POINTS_M),
            recipe="unsteady",
            reductions=_FFPROOF_POST___WINDOW,
        )
    source = next(workspace.sim_dir("3207").rglob("*_farfield_survey_iteration=7.txt"))
    source.write_text(_ffproof_post___probe_export(np.array([[99.0, 0.0, 0.0]]), 17.0))
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    assert _rfixf_layout___rows(root, "farfield/*_trefftz_instant.csv")
    assert not _rfixf_layout___rows(root, "farfield/*_trefftz_average.csv")
    assert not _rfixf_layout___rows(root, "farfield/*_ledgers_average.csv")
    skipped = str(_ffproof_post___manifest(root)["skipped"])
    assert f"absent={'plane' if variant == 'plane' else 'lattice'}" in skipped
    assert "average" in skipped and "restore" in skipped


def _ff5_printed_samples(points: np.ndarray, velocity: np.ndarray) -> ProbeSamples:
    """Read coordinates printed in the solver's four-digit 0.xxxxE form."""
    from pyflightstream.post.farfield_fields import steady_samples

    lines = _rfixf_layout___export(points, velocity).splitlines(keepends=True)
    index = 0
    for i, line in enumerate(lines):
        if re.match(r"\s*[-+]?\d\.\d+E", line):
            cells = line.split(",")
            for j, value in enumerate(points[index]):
                mantissa, exponent = f"{value:.3E}".split("E")
                cells[j] = f" {float(mantissa) / 10:.4f}E{int(exponent) + 1:+03d}"
            lines[i] = ",".join(cells)
            index += 1
    assert index == len(points)
    return steady_samples("".join(lines))


@pytest.mark.parametrize("alpha,beta", [(4.0, 0.0), (0.0, 3.0)], ids=["P0450-alpha", "P0450-beta"])
@pytest.mark.parametrize("per_m", [1.0, 1000.0])
def test_p0450_ff5_rounded_plane_keeps_drag_and_refuses_wrong_plane(alpha, beta, per_m):
    """LIC-01: reading a four-digit tilted plane preserves CDI_T; a shifted plane fails."""
    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.post.farfield_fields import FarLayout

    a, b = math.radians(alpha), math.radians(beta)
    direction = (math.cos(a) * math.cos(b), -math.cos(a) * math.sin(b), math.sin(a))
    grid = (0.4, 0.4, 0.08)
    laid = farfield_plane(
        (0.0, 0.0, 0.0),
        direction=direction,
        distance=2.27415,
        half_width=grid[0],
        half_height=grid[1],
        spacing=grid[2],
    )
    velocity = np.tile([30.0, 1.0, 0.5], (len(laid.points), 1))
    samples = _ff5_printed_samples(laid.points * per_m, velocity)
    assert samples.digits == 4
    layout = FarLayout(plane_m=laid.points, plane_grid=grid, plane_placed=True)
    _, block, why = far_samples(samples, layout, per_m=per_m)
    assert block is not None, why
    args = dict(flow=(1.2, 30.0, alpha, beta), grid=grid, per_m=per_m, q_ref=540.0)
    exact = replace(samples, positions=laid.points * per_m, digits=None)
    expected = plane_values(exact, block, **args)["D"] / (540.0 * 2.0)
    actual = plane_values(samples, block, **args)["D"] / (540.0 * 2.0)
    assert actual > 0.0
    assert actual == pytest.approx(expected, rel=1e-6)
    shifted = _ff5_printed_samples((laid.points + 0.04 * laid.axes[0]) * per_m, velocity)
    assert far_samples(shifted, layout, per_m=per_m)[1] is None
    warped = samples.positions.copy()
    warped[-1] += 0.04 * per_m * laid.axes[0]
    with pytest.raises(PyflightstreamError, match="not the plane"):
        plane_values(replace(samples, positions=warped), block, **args)


def test_p0450_ff6_captured_lattice_four_digits_is_read():
    """PFS-2139.015: the captured lattice fits the corrected printed-precision guard."""
    from pyflightstream.post.farfield_fields import FarLayout
    from pyflightstream.probes import build_lattice

    lattice = build_lattice(tip_radius=8.0, stations=[-2, 4, 8], n_r=8, n_psi=24)
    points = lattice_points(lattice, axis="X")
    assert points.shape == (648, 3)
    np.testing.assert_allclose(
        points[:2], [[-16.0, 0.0, 1.07758], [-16.0, 0.2789, 1.04086]], atol=1e-4, rtol=0
    )
    assert points[:, 0].min() == -16.0 and points[:, 0].max() == 64.0
    samples = _ff5_printed_samples(points, np.tile([30.0, 0.0, 0.0], (len(points), 1)))
    assert samples.digits == 4
    block, _, why = far_samples(samples, FarLayout(lattice_m=points), per_m=1.0)
    assert block == slice(0, 648), why


def test_p0450_ff5_lattice_precision_names_spacing_and_configuration():
    """LIC-03: an ambiguous lattice names the required native spacing and its controls."""
    from pyflightstream.post.farfield_fields import FarLayout
    from pyflightstream.probes import build_lattice

    for stations, inner, outer, origin, refused in [
        ((-2.0, 4.0, 8.0), 0.05, 2.5, 100.0, True),
        ((-1.0, 1.0), 0.2, 1.5, 0.0, False),
    ]:
        lattice = build_lattice(
            tip_radius=8.0,
            stations=stations,
            n_r=8,
            n_psi=24,
            r_inner=inner,
            r_outer=outer,
        )
        points = lattice_points(lattice, axis="X") + np.array([origin, 0.0, 0.0])
        samples = _ff5_printed_samples(points, np.tile([30.0, 0.0, 0.0], (len(points), 1)))
        assert samples.digits == 4
        block, _, why = far_samples(samples, FarLayout(lattice_m=points), per_m=1.0)
        if refused:
            assert block is None
            assert "printed precision" in why
            assert "at least 0.80008 native units" in why
            for key in ("r_inner", "n_psi", "n_r", "r_outer", "stations"):
                assert key in why
        else:
            assert block is not None, why


def test_p0450_ff5_wake_entries_keep_their_own_spanwise_files(tmp_path):
    """RV1-06: two B entries preserve the rows each would write in isolation."""
    entries = {"near": 0.1, "far": 0.2}
    expected = {}
    for selected in (["near", "far"], ["near"], ["far"]):
        workspace = _farfield_products___workspace(tmp_path / "_".join(selected), farfield=True)
        (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
            '[groups]\n"1" = "all"\n'
            + "".join(
                f'[[farfields]]\nvariant = "wake"\nname = "{name}"\n'
                f"distance_bref = {entries[name]}\n"
                for name in selected
            ),
            encoding="utf-8",
        )
        _farfield_products___post(workspace)
        root = workspace.root / "post"
        files = sorted(root.rglob("sections/*_trefftz_net_*.csv"))
        assert len(files) == len(selected)
        manifest = _farfield_products___one(root, "products.json").read_text(encoding="utf-8")
        for name in selected:
            path = next(path for path in files if path.name.endswith(f"_net_{name}.csv"))
            rows = _farfield_products___table(path)
            assert rows and {row["VARIANT"] for row in rows} == {"B"}
            assert {row["FAMILY"] for row in rows} == {"net"}
            assert path.name in manifest
            if len(selected) == 2:
                expected[name] = rows
            else:
                assert rows == expected[name]
    assert expected["near"] != expected["far"]


def _farfield_products___sloads() -> str:
    q = 0.5 * _FARFIELD_PRODUCTS__RHO * _FARFIELD_PRODUCTS__SPEED * _FARFIELD_PRODUCTS__SPEED
    peak = (
        _FARFIELD_PRODUCTS__CL
        * q
        * _FARFIELD_PRODUCTS__SREF
        * 4.0
        / (math.pi * _FARFIELD_PRODUCTS__BREF)
    )
    y = (
        -_FARFIELD_PRODUCTS__BREF / 2
        + (np.arange(_FARFIELD_PRODUCTS__STATIONS) + 0.5)
        * _FARFIELD_PRODUCTS__BREF
        / _FARFIELD_PRODUCTS__STATIONS
    )
    lift = peak * np.sqrt(1.0 - (2.0 * y / _FARFIELD_PRODUCTS__BREF) ** 2)
    fz = lift / math.cos(math.radians(_FARFIELD_PRODUCTS__ALPHA))
    head = _FARFIELD_PRODUCTS__LOADS.split("     Surface,")[0].replace(
        "Aerodynamic loads", "Surface Sectional Loads"
    )
    rows = "".join(
        f"     {a: .4E}, 0.1000E+01, 0.0000E+00, 0.0000E+00, 0.0000E+00, {b: .4E}, 0.0000E+00,\n"
        for a, b in zip(y, fz, strict=True)
    )
    return (
        head.rsplit(_FARFIELD_PRODUCTS___RULE, 1)[0]
        + f"     Number of Surface Sections:                 {_FARFIELD_PRODUCTS__STATIONS}\n"
        + _FARFIELD_PRODUCTS___RULE
        + "     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n"
        + rows
        + _FARFIELD_PRODUCTS___RULE
        + "     Force Units: Newtons\n     Moment Units: Newton-Meter\n"
        + "     Software : Flightstream\n"
    )


def _farfield_products___wakes(*, half: bool = False) -> str:
    nodes = np.linspace(
        -_FARFIELD_PRODUCTS__BREF / 2,
        _FARFIELD_PRODUCTS__BREF / 2,
        _FARFIELD_PRODUCTS__STATIONS + 1,
    )
    centres = 0.5 * (nodes[:-1] + nodes[1:])
    gamma = np.sqrt(1.0 - (2.0 * centres / _FARFIELD_PRODUCTS__BREF) ** 2)
    shed = -np.diff(np.concatenate([[0.0], gamma, [0.0]]))
    if half:
        shed = -shed[nodes > 0.0]
        nodes = nodes[nodes > 0.0]
    points, lines = [], []
    for index, y in enumerate(nodes):
        points += [(1.0, y, 0.0), (15.0, y, 0.0), (30.0, y, 0.0)]
        lines += [(3 * index, 3 * index + 1), (3 * index + 1, 3 * index + 2)]
    values = np.repeat(shed, 2)
    return (
        "# vtk DataFile Version 3.0\nwake\nASCII\nDATASET POLYDATA\n"
        + f"POINTS {len(points)} float\n"
        + "".join(f"{x} {y} {z}\n" for x, y, z in points)
        + f"LINES {len(lines)} {3 * len(lines)}\n"
        + "".join(f"2 {a} {b}\n" for a, b in lines)
        + f"CELL_DATA {len(lines)}\nSCALARS Normalized_Vorticity float 1\nLOOKUP_TABLE default\n"
        + "".join(f"{v}\n" for v in values)
    )


def _farfield_products___probes() -> str:
    a = math.radians(_FARFIELD_PRODUCTS__ALPHA)
    direction = (math.cos(a), 0.0, math.sin(a))
    laid = farfield_plane(
        (20.0, 0.0, 0.0),
        direction=direction,
        distance=5.0,
        half_width=0.75 * _FARFIELD_PRODUCTS__BREF,
        half_height=0.5 * _FARFIELD_PRODUCTS__BREF,
        spacing=0.05 * _FARFIELD_PRODUCTS__BREF,
    )
    velocity = _FARFIELD_PRODUCTS__SPEED * np.array(direction)
    rows = "".join(
        "     "
        + ", ".join(f"{v: .4E}" for v in (*p, 0.2, 0.0, *velocity, _FARFIELD_PRODUCTS__SPEED, 0.0))
        + ", 0.0000E+00" * 6
        + ",\n"
        for p in laid.points
    )
    fixture = Path(__file__).parent / "fixtures" / "probe_points_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    head, _, tail = text.partition(
        "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp, s_len, momentum_thickness, disp_thick,"
    )
    head = head.replace(
        "Number of Probe Points:                     12",
        f"Number of Probe Points:                     {len(laid.points)}",
    )
    footer = tail.split(_FARFIELD_PRODUCTS___RULE)[-2:]
    return (
        head
        + "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp, s_len, momentum_thickness, disp_thick,"
        + tail.split("\n", 1)[0]
        + "\n"
        + _FARFIELD_PRODUCTS___RULE
        + rows
        + _FARFIELD_PRODUCTS___RULE
        + footer[-1]
    )


_FARFIELD_PRODUCTS___FARFIELD = (
    "[[farfields]]\n"
    'variant = "sections"\n'
    'families = "all"\n'
    "[[farfields]]\n"
    'variant = "wake"\n'
    "[[farfields]]\n"
    'variant = "plane"\n'
    "spacing_bref = 0.05\n"
)


def _farfield_products___workspace(root: Path, *, farfield: bool) -> CampaignWorkspace:
    workspace = CampaignWorkspace.init(root / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n' + (_FARFIELD_PRODUCTS___FARFIELD if farfield else ""),
        encoding="utf-8",
    )
    raw = workspace.sim_dir("3207") / "outputs"
    raw.mkdir(parents=True)
    stem = "POLAR-3207_M20AL-020BE+000"
    files = {
        f"{stem}.txt": _FARFIELD_PRODUCTS__LOADS,
        f"{stem}.fsm": "$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n",
        f"{stem}_sloads.txt": _farfield_products___sloads(),
        f"{stem}.vtk": "# vtk DataFile Version 3.0\n",
        f"{stem}_wakes.vtk": _farfield_products___wakes(),
        f"{stem}_farfield_survey.txt": _farfield_products___probes(),
    }
    for name, text in files.items():
        (raw / name).write_text(text, encoding="utf-8")
    workspace.append_record(
        _FarfieldProductsRunRecord(
            run_id="camp/sim_3207/AL-020",
            point_name="AL-020",
            sweep_name="AL-020",
            point={"alpha": _FARFIELD_PRODUCTS__ALPHA},
            sim_id="3207",
            status=RunStatus.CONVERGED,
            recipe="steady",
            outputs=[f"outputs/{name}" for name in files if not name.endswith("_wakes.vtk")],
            fs_version_requested="26.120",
            script_sha256="",
            package_version="0.40.0",
            raw_flag=False,
            pproc="p001",
            mach=0.2,
            density_kg_m3=_FARFIELD_PRODUCTS__RHO,
            reference={
                "SREF": _FARFIELD_PRODUCTS__SREF,
                "CREF": 2.526,
                "BREF": _FARFIELD_PRODUCTS__BREF,
                "XMOM": 0.0,
            },
            sections_layout=[
                {
                    "distribution": 1,
                    "distribution_families": ["W"],
                    "families": ["W"],
                    "plane": "XZ",
                    "frame": "MRP",
                    "count": _FARFIELD_PRODUCTS__STATIONS,
                }
            ],
        )
    )
    return workspace


def _farfield_products___post(workspace: CampaignWorkspace) -> list[str]:
    from pyflightstream.post.products import write_campaign_products

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", PyflightstreamWarning)
        write_campaign_products(workspace)
    return [str(w.message) for w in caught]


def _farfield_products___table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_p0440_nonmetre_steady_probe_velocity_is_a_named_skip(tmp_path):
    workspace = _farfield_products___workspace(tmp_path, farfield=True)
    saved = next(workspace.sim_dir("3207").glob("outputs/*.fsm"))
    saved.write_text("$GLOBAL_START$\n.001\n2\n$GLOBAL_END$\n", encoding="utf-8")
    messages = _farfield_products___post(workspace)
    assert any("conventional probe velocity units" in message for message in messages)
    assert any("1000" in message and "unmeasured" in message for message in messages)


def _farfield_products___one(root: Path, pattern: str) -> Path:
    found = sorted(root.rglob(pattern))
    assert len(found) == 1, (pattern, found)
    return found[0]


def _farfield_products___items(entries):
    if isinstance(entries, dict):
        return entries.items()
    return [(str(entry.get("path", "")), entry) for entry in entries]


def _farfield_products___add_outputs(
    manifest: Path, sim_id: str, suffixes: tuple[str, ...]
) -> None:
    """Add exports to the recorded outputs of one simulation's runs, as a run records them."""
    from pyflightstream.workspace.record_document import encode_rows, read_rows

    runs = read_rows(manifest)
    for run in runs:
        if run.get("sim_id") == sim_id:
            loads = run["outputs"][0]
            run["outputs"] = [loads] + [loads[: -len(".txt")] + suffix for suffix in suffixes]
    manifest.write_text(json.dumps(encode_rows(runs), indent=1), encoding="utf-8")


class TestFarfieldProducts:
    """P0400-FFOUT: the far-field products of a posted simulation (FR-456).

    One synthetic steady point is posted end to end: an elliptic loading of a
    wing alone exported as sectional loads, its wake as the solver writes it, and
    a uniform stream sampled on the C plane. Every export is built here in the
    recorded formats with synthetic values; no research data enters.
    """

    @staticmethod
    @pytest.fixture(scope="class")
    def posted(tmp_path_factory):
        root = tmp_path_factory.mktemp("ff")
        workspace = _farfield_products___workspace(root / "with", farfield=True)
        messages = _farfield_products___post(workspace)
        plain = _farfield_products___workspace(root / "without", farfield=False)
        _farfield_products___post(plain)
        return Path(workspace.root), Path(plain.root), messages

    @staticmethod
    @pytest.mark.requirement("FR-456")
    @pytest.mark.requirement("FR-3263")
    def test_p0450_d0_trefftz_table_identifies_entries(posted):
        """P0400-FFOUT (FR-1053, FR-1054): one file beside the polar, A, B and C rows, NA per
        rule.
        """
        root, _plain, _messages = posted
        path = _farfield_products___one(root, "farfield/*_trefftz.csv")
        rows = {row["VARIANT"]: row for row in _farfield_products___table(path)}
        assert set(rows) == {"A", "B", "C"}
        header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
        # PFS-2081.97: the point's status closes every far-field row, after ETA_FF.
        assert header[:3] == ["POL", "ENTRY", "STEP"] and header[-2:] == ["ETA_FF", "STATUS"]
        a, b, c = rows["A"], rows["B"], rows["C"]
        assert [a["FAMILY"], b["FAMILY"], c["FAMILY"]] == ["TOTAL", "net", "net"]
        assert [a["ENTRY"], b["ENTRY"], c["ENTRY"]] == ["sections", "wake", "plane"]
        assert float(a["CL_T"]) == pytest.approx(_FARFIELD_PRODUCTS__CL, rel=2e-3)
        assert 1.0 < float(a["E_T"]) < 1.012, "the elliptic bias of 80 stations per side"
        assert float(b["CL_T"]) == pytest.approx(_FARFIELD_PRODUCTS__CL, abs=1e-5), (
            "B is calibrated on the near CL"
        )
        assert 0.97 < float(b["E_T"]) < 1.03
        upstream = float(
            (farfield_axes(_FARFIELD_PRODUCTS__ALPHA, 0.0) @ np.array([1.0, 0.0, 0.0]))[0]
        )
        assert float(b["X_T_M"]) == pytest.approx(
            upstream + 0.25 * _FARFIELD_PRODUCTS__BREF, abs=1e-5
        )
        assert a["X_T_M"] == "NA"
        assert float(c["CDI_T"]) == pytest.approx(0.0, abs=1e-9), "a uniform stream has no drag"
        # FR-1038 (PFS-2081.95): C states the lift of its own vorticity; this
        # fixture's plane holds none, so it is zero (and post flags it).
        assert float(c["COVERAGE"]) == 1.0 and float(c["CL_T"]) == pytest.approx(0.0, abs=1e-9)
        assert a["P_AXIAL_W"] == "NA" and a["CDI_NEAR_PRESSURE"] == "0.0012418"

    @staticmethod
    @pytest.mark.requirement("FR-456")
    def test_p0400_ffout_the_spanwise_files(posted):
        """P0450-D5 (FR-1055): A per family, B as net, downwash and local drag."""
        root, _plain, _messages = posted
        family = _farfield_products___table(
            _farfield_products___one(root, "sections/*_trefftz_W.csv")
        )
        total = _farfield_products___table(
            _farfield_products___one(root, "sections/*_trefftz_net_wake.csv")
        )
        assert len(family) == _FARFIELD_PRODUCTS__STATIONS and {
            row["VARIANT"] for row in family
        } == {"A"}
        assert {row["CDI_LOCAL"] for row in total} == {"NA"}
        assert {row["FAMILY"] for row in total} == {"net"}
        manifest = _farfield_products___one(root, "products.json").read_text()
        log = _farfield_products___one(root, "post.log").read_text()
        assert "_trefftz_net_wake.csv" in manifest
        assert "_trefftz_TOTAL.csv" not in manifest + log
        downwash = [float(row["W_M_S"]) for row in family[10:-10]]
        assert max(downwash) - min(downwash) < 0.05 * abs(np.mean(downwash)), "elliptic: uniform"

    @staticmethod
    @pytest.mark.requirement("FR-456")
    def test_p0400_ffout_the_manifest(posted):
        """P0400-FFOUT (FR-1058): runs held, analysis, variants, inputs and the strip rule."""
        root, _plain, _messages = posted
        manifest = json.loads(
            _farfield_products___one(root, "products.json").read_text(encoding="utf-8")
        )
        entries = manifest.get("products", manifest)
        (entry,) = [
            value
            for key, value in _farfield_products___items(entries)
            if key.endswith("_trefftz.csv")
        ]
        assert entry["runs"] == ["camp/sim_3207/AL-020"]
        assert entry["analysis"] == "trefftz" and entry["strip_rule"] == "extended"
        assert entry["variants"] == ["sections", "wake", "plane"]

    @staticmethod
    @pytest.mark.requirement("FR-456")
    def test_p0400_ffout_the_polar_keeps_its_bytes(posted):
        """P0400-FFOUT (FR-1060, FR-450): the polar is byte-identical with and without [farfield].

        The super file beside it gains its far-field block (FR-1062), so it is the one
        file of the folder left out here.
        """
        root, plain, _messages = posted
        for path in sorted(p for p in plain.rglob("polars/*") if not p.name.startswith("SUPER-")):
            twin = root / path.relative_to(plain)
            assert twin.read_bytes() == path.read_bytes(), path.name
        assert not list(plain.rglob("farfield/*")), "no [farfield], no far-field file"

    @staticmethod
    @pytest.mark.requirement("FR-456")
    def test_p0400_ffout_the_super_file_block(tmp_path):
        """P0400-FFOUT (FR-1062, NFR-19): the three columns append without renaming others."""
        from tests.tier1_offline.test_post_superfile import _post as post_matrix
        from tests.tier1_offline.test_post_superfile import _superfiles
        from tests.tier1_offline.test_post_superfile import _workspace as matrix_workspace

        plain = matrix_workspace(tmp_path / "plain")
        post_matrix(plain)
        name = "SUPER-6001-M200RE1177AL+sweepBE+000_g01.csv"
        before = _superfiles(plain)[name][0]
        workspace = matrix_workspace(tmp_path / "far")
        (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
            '[groups]\n"1" = "all"\n"2" = "W"\n[[farfields]]\nvariant = "wake"\n',
            encoding="utf-8",
        )
        outputs = workspace.sim_dir("6001") / "outputs"
        for tag in ("AL-020", "AL+000"):
            stem = f"POLAR-6001_M20{tag}BE+000"
            (outputs / f"{stem}.fsm").write_text("$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n")
            (outputs / f"{stem}.vtk").write_text("# vtk DataFile Version 3.0\n")
            (outputs / f"{stem}_wakes.vtk").write_text(
                _farfield_products___wakes(half=True), encoding="utf-8"
            )
        _farfield_products___add_outputs(workspace.manifest_path, "6001", (".fsm", ".vtk"))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            post_matrix(workspace)
        columns, rows = _superfiles(workspace)[name]
        added = [column for column in columns if column not in before]
        assert added == ["CL_T_B_wake", "CDI_T_B_wake", "E_T_B_wake"]
        kept = [column for column in before if column != "MESH_FACES"]
        assert columns.index("CL_T_B_wake") > max(columns.index(column) for column in kept)
        assert all(row["E_T_B_wake"] not in ("", None) for row in rows)


_FFPROOF_POST___STEM = "POLAR-3207_M20AL-020BE+000"


_FFPROOF_POST___RUN = "camp/sim_3207/AL-020"


_FFPROOF_POST___RULE = " " + "-" * 100 + "\n"


_FFPROOF_POST___FSM = "$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n"


_FFPROOF_POST___RHO = 1.225


#: A survey lattice of the MRP frame: two stations, two rings, eight azimuths.
_FFPROOF_POST___LATTICE = {
    "frame": "MRP",
    "tip_radius_m": 1.0,
    "stations": [-1.0, 1.0],
    "n_r": 2,
    "n_psi": 16,
}


_FFPROOF_POST___SHAPE = LatticeShape.model_validate(_FFPROOF_POST___LATTICE)


_FFPROOF_POST___POINTS_M = lattice_points(_FFPROOF_POST___SHAPE.build(1.0), axis="X")


_FFPROOF_POST___LEDGERS = (
    "[[farfields]]\n"
    'variant = "power"\n'
    'balances = ["mass", "axial", "transverse", "torque", "in_plane_mo'
    'ment", "crossflow_energy"]\n'
    'frame = "MRP"\n'
    "tip_radius_m = 1.0\n"
    "stations = [-1.0, 1.0]\n"
    "n_r = 2\n"
    "n_psi = 16\n"
    "m_max = 2\n"
)


#: The window an unsteady row of eight steps states with ``LAST_ITERS_AVG: 4``,
#: as the plan records it (steps 5 to 8), flagged as stated by the row.
_FFPROOF_POST___WINDOW = {
    "window_stated": True,
    "time_iterations": 8,
    "time_average": {"windows": [[5, 8]], "window_from": "LAST_ITERS_AVG: 4"},
}


def _ffproof_post___speed(step: int) -> float:
    """The uniform axial speed of the synthetic unsteady field at one time step, m/s."""
    return 10.0 + step


def _ffproof_post___probe_export(points: np.ndarray, speed: float) -> str:
    """A steady probe-points export of ``points`` (m) in a uniform axial stream of ``speed``."""
    rows = "".join(
        "     "
        + ", ".join(f"{v: .6E}" for v in (*p, 0.1, 0.0, speed, 0.0, 0.0, speed, 0.0))
        + ", 0.0000E+00" * 6
        + ",\n"
        for p in points
    )
    fixture = Path(__file__).parent / "fixtures" / "probe_points_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    columns = (
        "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp, s_len, momentum_thickness, disp_thick,"
    )
    head, _, tail = text.partition(columns)
    head = head.replace(
        "Number of Probe Points:                     12",
        f"Number of Probe Points:                     {len(points)}",
    )
    footer = tail.split(_FFPROOF_POST___RULE)[-1]
    return (
        head
        + columns
        + tail.split("\n", 1)[0]
        + "\n"
        + _FFPROOF_POST___RULE
        + rows
        + _FFPROOF_POST___RULE
        + footer
    )


def _ffproof_post___plots_export(count: int, steps: int) -> str:
    """Fluid plots of ``count`` vertices over ``steps`` time steps, a uniform axial stream."""
    names = [f"{p}{n}" for n in range(1, count + 1) for p in ("VX", "VY", "VZ", "CP_REF")]
    table = "Time-step," + ",".join(names) + "\n"
    for step in range(1, steps + 1):
        values = [_ffproof_post___speed(step), 0.0, 0.0, 0.0] * count
        table += f"{step}.0000," + ",".join(f"{v:.5f}" for v in values) + ",\n"
    return (
        _FFPROOF_POST__PLOTS_HEADER
        + table
        + "-" * 60
        + "\n     Force Units: Coefficients\nSoftware : Flightstream version 26.1, build #7012026\n"
    )


def _ffproof_post___campaign(
    root: Path,
    *,
    pproc: str,
    files: dict[str, str],
    recipe: str = "steady",
    reductions: dict | None = None,
    positions: bool = False,
) -> CampaignWorkspace:
    """One converged point of simulation 3207 with the named exports under ``outputs/``."""
    workspace = CampaignWorkspace.init(root / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n' + pproc, encoding="utf-8"
    )
    sim_dir = workspace.sim_dir("3207")
    raw = sim_dir / "outputs"
    raw.mkdir(parents=True)
    exports = {
        f"{_FFPROOF_POST___STEM}.txt": _FFPROOF_POST__LOADS,
        f"{_FFPROOF_POST___STEM}.fsm": _FFPROOF_POST___FSM,
        **files,
    }
    for name, text in exports.items():
        (raw / name).write_text(text, encoding="utf-8")
    extra: dict[str, Any] = {}
    if reductions is not None:
        extra["reductions"] = reductions
    if positions:
        points = [
            (n, float(x), float(y), float(z), "REFERENCE")
            for n, (x, y, z) in enumerate(_FFPROOF_POST___POINTS_M, start=1)
        ]
        extra["probe_points_file"] = _write_probe_points(sim_dir, "3207", points)
    workspace.append_record(
        RunRecord(
            run_id=_FFPROOF_POST___RUN,
            point_name="AL-020",
            sweep_name="AL-020",
            point={"alpha": -2.0},
            sim_id="3207",
            status=RunStatus.CONVERGED,
            recipe=recipe,
            outputs=[f"outputs/{name}" for name in exports],
            fs_version_requested="26.120",
            script_sha256="",
            package_version="0.40.0",
            raw_flag=False,
            pproc="p001",
            mach=0.2,
            density_kg_m3=_FFPROOF_POST___RHO,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0, "XMOM": 0.0},
            **extra,
        )
    )
    return workspace


def _ffproof_post___post(workspace: CampaignWorkspace) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace)


def _ffproof_post___one(root: Path, pattern: str) -> Path:
    found = sorted(root.rglob(pattern))
    assert len(found) == 1, (pattern, found)
    return found[0]


def _ffproof_post___table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _ffproof_post___manifest(root: Path) -> dict:
    return json.loads(_ffproof_post___one(root, "products.json").read_text(encoding="utf-8"))


def _ffproof_post___entry(manifest: dict, suffix: str) -> dict:
    (entry,) = [v for k, v in manifest["products"].items() if k.endswith(suffix)]
    return entry


def _ffproof_post___warnings_of(root: Path) -> list[str]:
    text = _ffproof_post___one(root, "post.log").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if "WARNING" in line]


def _ffproof_post___set_record(workspace: CampaignWorkspace, **fields: object) -> None:
    """Change fields of the recorded run, as a record of that shape would carry them."""
    data = _read_record_rows(workspace.manifest_path)
    runs = data if isinstance(data, list) else data.get("runs", data.get("records", []))
    for run in runs:
        run.update(fields)
    workspace._replace_manifest(data)


# ----------------------------------------------------------------- FR-1025
def _ffproof_post___short_wakes(short: int) -> str:
    """The wing's wake with ``short`` lines ending 3 m behind the trailing edge."""
    text = _ffproof_post__wing._farfield_products___wakes()
    lines = text.splitlines()
    first = lines.index(next(line for line in lines if line.startswith("POINTS"))) + 1
    for index in range(short):
        # The third node of a line is its end: put it 3 m behind its start.
        row = first + 3 * index + 2
        x, y, z = lines[row].split()
        lines[row] = f"4.0 {y} {z}"
        middle = first + 3 * index + 1
        _x, y, z = lines[middle].split()
        lines[middle] = f"2.5 {y} {z}"
    return "\n".join(lines) + "\n"


class TestFfproofPost:
    """P0400-FFPROOF: the far-field products ``pyfs-matrix post`` writes, read from the files.

    Every test posts a synthetic campaign end to end through
    ``write_campaign_products`` (the body of ``pyfs-matrix post``) and reads what
    it wrote: the far-field tables, ``products.json`` and the WARNING lines of
    ``post.log``. The exports are built in the recorded formats with synthetic
    values (an elliptic loading, a wake of straight lines, uniform streams sampled
    on a survey lattice); no research data enters. The steady wing point is the
    one of ``test_p0400_farfield_products``; the survey points are new here.
    """

    @staticmethod
    # ----------------------------------------------------------------- FR-1009
    @pytest.mark.requirement("FR-450")
    def test_p0400_ffproof_the_sweep_table_keeps_its_bytes(tmp_path):
        """P0400-FFPROOF (FR-1009): ``campaign_sweep.csv`` byte-identical with and without it.

        The same point recorded twice: once by a row selecting the three Trefftz
        variants, which the plan gave the sectional loads, wake and probe exports,
        and once by the row without ``[farfield]``, which recorded the loads and
        the saved simulation only. Both are posted, then the sweep table is written
        as the run stage writes it (``results.sweep_table`` through
        ``results.write_table`` to ``post/campaign_sweep.csv``): the two files are
        the same bytes, and the far field wrote its own table.
        """
        far = _ffproof_post__wing._farfield_products___workspace(tmp_path / "with", farfield=True)
        plain = _ffproof_post__wing._farfield_products___workspace(
            tmp_path / "without", farfield=False
        )
        _ffproof_post___set_record(
            plain,
            outputs=[f"outputs/{_FFPROOF_POST___STEM}.txt", f"outputs/{_FFPROOF_POST___STEM}.fsm"],
        )
        tables = []
        for workspace in (far, plain):
            _ffproof_post___post(workspace)
            target = workspace.sweep_dir(None) / SWEEP_TABLE_NAME
            write_table(sweep_table(workspace, require_loads=False), target, overwrite=True)
            tables.append(target.read_bytes())
        assert list(Path(far.root).rglob("farfield/*_trefftz.csv")), "the far field was posted"
        assert not list(Path(plain.root).rglob("farfield/*"))
        assert b"-2" in tables[1] and tables[0] == tables[1]

    @staticmethod
    # ----------------------------------------------------------------- FR-1019
    @pytest.mark.requirement("FR-451")
    def test_p0400_ffproof_post_warns_a_family_with_few_stations(tmp_path):
        """P0400-FFPROOF (FR-1019): one post WARNING naming the family, its count and the bias.

        The recorded distribution has 160 sections over the full span, 80 per
        side; the table asks for 160 per side. Variant A is still integrated and
        ``post.log`` says so once, with the bias the definitions page measured
        at 80 (0.52 percent).
        """
        workspace = _ffproof_post__wing._farfield_products___workspace(tmp_path, farfield=True)
        (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
            (
                "[groups]\n"
                '"1" = "all"\n'
                "[[farfields]]\n"
                'variant = "sections"\n'
                'families = "all"\n'
                "stations = 160\n"
            ),
            encoding="utf-8",
        )
        _ffproof_post___post(workspace)
        root = Path(workspace.root)
        _columns, rows = _ffproof_post___table(_ffproof_post___one(root, "farfield/*_trefftz.csv"))
        assert [row["VARIANT"] for row in rows] == ["A"] and rows[0]["E_T"] != "NA"
        few = [line for line in _ffproof_post___warnings_of(root) if "stations per side" in line]
        assert len(few) == 1, few
        assert "family W has 80 stations per side, fewer than the 160" in few[0]
        assert "0.52 percent at 80 stations per side" in few[0]

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_ffproof_a_short_wake_posts_the_b_row_na(tmp_path):
        """P0400-FFPROOF (FR-1025): the B row is NA, and the WARNING says why and how long.

        Three of the 161 wake lines end 3 m behind the trailing edge and the
        plane stands 0.25 BREF = 5 m behind it: the B row is written with its
        coefficients NA, never dropped and never integrated over the lines that
        reach; ``post.log`` names the three short lines and the wake's length.
        """
        workspace = _ffproof_post__wing._farfield_products___workspace(tmp_path, farfield=True)
        topology = _ffproof_post___short_wakes(3)
        assert "POINTS 483 float" in topology
        assert "LINES 322 966" in topology  # 161 strands, two connected segments each.
        (workspace.sim_dir("3207") / "outputs" / f"{_FFPROOF_POST___STEM}_wakes.vtk").write_text(
            topology, encoding="utf-8"
        )
        _ffproof_post___post(workspace)
        root = Path(workspace.root)
        _columns, rows = _ffproof_post___table(_ffproof_post___one(root, "farfield/*_trefftz.csv"))
        (b,) = [row for row in rows if row["VARIANT"] == "B"]
        assert b["FAMILY"] == "net"
        assert {b[c] for c in ("CL_T", "CDI_T", "CY_T", "E_T", "GAMMA_SCALE")} == {"NA"}
        assert b["X_T_M"] != "NA"
        said = [
            line
            for line in _ffproof_post___warnings_of(root)
            if "wake lines end before the plane" in line
        ]
        # The WARNING of the step and the line of its named skip, each saying it in full.
        assert len(said) == 2, said
        reach = 3.0 * math.cos(
            math.radians(_ffproof_post__wing._FARFIELD_PRODUCTS__ALPHA)
        )  # 3 m of wake, along the free stream
        for line in said:
            assert "3 of 161 wake lines end before the plane" in line
            assert f"the recorded wake is {reach:.4g} m long on its shortest line" in line
        skipped = _ffproof_post___manifest(root)["skipped"]
        assert any("variant=wake" in key for key in skipped)

    @staticmethod
    # ----------------------------------------------------------------- FR-1036
    @pytest.mark.requirement("FR-453")
    @pytest.mark.parametrize(("mach", "warned"), [(0.5, True), (0.2, False)])
    def test_p0400_ffproof_above_mach_0_3_the_c_row_is_warned(tmp_path, mach, warned):
        """P0400-FFPROOF (FR-1036): the C row is written, with the incompressible WARNING above 0.3.

        The same recorded point at Mach 0.5 and at Mach 0.2: both write their C
        row; only the first writes the WARNING that the incompressible relations
        of the definitions page are used.
        """  # noqa: E501
        workspace = _ffproof_post__wing._farfield_products___workspace(tmp_path, farfield=True)
        _ffproof_post___set_record(workspace, mach=mach)
        _ffproof_post___post(workspace)
        root = Path(workspace.root)
        _columns, rows = _ffproof_post___table(_ffproof_post___one(root, "farfield/*_trefftz.csv"))
        (c,) = [row for row in rows if row["VARIANT"] == "C"]
        assert c["CDI_T"] != "NA"
        said = [
            line for line in _ffproof_post___warnings_of(root) if "incompressible relations" in line
        ]
        assert len(said) == (1 if warned else 0), said
        if warned:
            assert "Mach 0.5" in said[0] and "Trefftz C" in said[0]

    @staticmethod
    # ------------------------------------------------- FR-1053, FR-1056 and FR-478 to FR-480
    @pytest.mark.requirement("FR-456")
    @pytest.mark.requirement("FR-38")
    def test_p0450_d0_ledgers_table_identifies_entries(tmp_path):
        """P0400-FFPROOF (FR-1053, FR-1056; FR-478 to FR-480): ``farfield/<group>_ledgers.csv``.

        A steady point whose probe export holds the survey lattice in a uniform
        stream: one row per station, the columns of FR-1056 in order, the mass flow
        constant over the stations, the control-volume columns NA on the inlet
        row and zero on the next, the gate columns written; the file sits beside
        the polar by name and its manifest entry names the analysis and the run.
        """
        workspace = _ffproof_post___campaign(
            tmp_path,
            pproc=_FFPROOF_POST___LEDGERS,
            files={
                f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _ffproof_post___probe_export(
                    _FFPROOF_POST___POINTS_M, 20.0
                )
            },
        )
        _ffproof_post___post(workspace)
        root = Path(workspace.root)
        path = _ffproof_post___one(root, "farfield/*_ledgers.csv")
        polar = _ffproof_post___one(root, "polars/P*.csv")
        group = polar.stem.rsplit("_", 1)[0]
        assert path.name == f"{group}_ledgers.csv", "beside the polar, by name (R1)"
        columns, rows = _ffproof_post___table(path)
        assert columns == ["POL", "ENTRY", "STEP", *CONTEXT_COLUMNS, *LEDGER_COLUMNS]
        assert [float(row["STATION_X_R"]) for row in rows] == [-1.0, 1.0]
        assert {row["LATTICE"] for row in rows} == {"MRP"}
        inlet, outlet = rows
        assert float(inlet["MDOT_KG_S"]) > 0.0
        assert float(outlet["MDOT_KG_S"]) == pytest.approx(float(inlet["MDOT_KG_S"]), rel=1e-12)
        assert float(inlet["MASS_SPREAD"]) == pytest.approx(0.0, abs=1e-12)
        for column in ("FX_N", "FY_PLANE_N", "FZ_PLANE_N", "MY_LOADING_NM", "MZ_ARM_NM"):
            assert inlet[column] == "NA", column
            assert float(outlet[column]) == pytest.approx(0.0, abs=1e-9), column
        assert outlet["FY_PLANE_N"] != "" and outlet["FY_PLANE_HARMONIC_N"] != "NA"
        assert all(row[g] != "" for row in rows for g in ("SYMMETRY_FLOOR", "SPURIOUS_COUNTS"))
        entry = _ffproof_post___entry(_ffproof_post___manifest(root), "_ledgers.csv")
        assert entry["analysis"] == "ledgers" and entry["runs"] == [_FFPROOF_POST___RUN]
        assert "reduction" not in entry, "a steady row's table is neither instant nor average"

    @staticmethod
    # ------------------------------------------------- FR-484 and FR-1053
    @pytest.mark.requirement("FR-38")
    @pytest.mark.requirement("FR-456")
    def test_p0400_ffproof_an_unsteady_row_writes_the_instant_and_the_average(tmp_path):
        """P0400-FFPROOF (FR-484, FR-1053): two ledgers files, each labelled.

        An ``unsteady`` row of eight steps whose window is ``LAST_ITERS_AVG: 4``
        (steps 5 to 8), its lattice sampled by fluid plots at every step in a
        stream of 10 + step m/s. The instant is step 8; the average is the mean
        of the four steps' balances, so its mass flow is 16.5/18 of the instant's
        (14.5/18 would be the whole run, 18/18 the last step). Each file names its
        reduction in its name and in its manifest entry.
        """
        workspace = _ffproof_post___campaign(
            tmp_path,
            pproc=_FFPROOF_POST___LEDGERS + 'export_type = "avg_window"\n',
            files=_p0450_probe_series(_FFPROOF_POST___POINTS_M),
            recipe="unsteady",
            reductions=_FFPROOF_POST___WINDOW,
            positions=True,
        )
        _ffproof_post___post(workspace)
        root = Path(workspace.root)
        instant = _ffproof_post___one(root, "farfield/*_ledgers_instant.csv")
        average = _ffproof_post___one(root, "farfield/*_ledgers_average.csv")
        assert not list(root.rglob("farfield/*_ledgers.csv"))
        columns, now = _ffproof_post___table(instant)
        assert columns == ["POL", "ENTRY", "STEP", *CONTEXT_COLUMNS, *LEDGER_COLUMNS]
        _columns, mean = _ffproof_post___table(average)
        assert {row["STEP"] for row in now} == {"8"}
        assert {row["STEP"] for row in mean} == {"AVERAGE"}
        for last, window in zip(now, mean, strict=True):
            ratio = float(window["MDOT_KG_S"]) / float(last["MDOT_KG_S"])
            assert ratio == pytest.approx(16.5 / 18.0, rel=1e-6)
            assert abs(ratio - 14.5 / 18.0) > 0.05, "the whole run is not the window"
        manifest = _ffproof_post___manifest(root)
        assert _ffproof_post___entry(manifest, "_ledgers_instant.csv")["reduction"] == "instant"
        assert _ffproof_post___entry(manifest, "_ledgers_average.csv")["reduction"] == "average"

    @staticmethod
    # ----------------------------------------------------------------- FR-1052
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffproof_a_normal_declaration_gives_the_instant_only(tmp_path):
        """P0400-FFPROOF (FR-1052): a reused ``kind = "default"`` lattice holds the last step.

        The far field reuses a ``[[probes]]`` lattice of kind normal on an
        unsteady row: the probe export of the last step (18 m/s) gives the
        instant, written with the run's last step; the average is not written,
        and it is a named skip in ``products.json`` and a WARNING in ``post.log``.
        """
        probes = (
            '[[probes]]\nframe = "MRP"\nkind = "default"\nparameters = ["VX"]\n'
            '[[probes.lattices]]\nframe = "MRP"\ntip_radius_m = 1.0\nstations = [-1.0, 1.0]\n'
            "n_r = 2\nn_psi = 16\n"
        )
        workspace = _ffproof_post___campaign(
            tmp_path,
            pproc=probes + _FFPROOF_POST___LEDGERS,
            files={
                f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _ffproof_post___probe_export(
                    _FFPROOF_POST___POINTS_M, _ffproof_post___speed(8)
                )
            },
            recipe="unsteady",
            reductions=_FFPROOF_POST___WINDOW,
        )
        _ffproof_post___post(workspace)
        root = Path(workspace.root)
        _columns, now = _ffproof_post___table(
            _ffproof_post___one(root, "farfield/*_ledgers_instant.csv")
        )
        assert {row["STEP"] for row in now} == {"8"}
        area = float(now[0]["MDOT_KG_S"]) / (_FFPROOF_POST___RHO * _ffproof_post___speed(8))
        assert area > 0.0 and now[1]["FX_N"] != "NA"
        assert not list(root.rglob("farfield/*_ledgers_average.csv"))
        skipped = _ffproof_post___manifest(root)["skipped"]
        (reason,) = [v for k, v in skipped.items() if k.startswith("farfield/average#point=")]
        assert "export_type = 'default'" in reason and "last step" in reason
        assert any("export_type" in line for line in _ffproof_post___warnings_of(root))


_LITB_POST__FIXTURES = Path(__file__).parent / "fixtures"


def _litb_post__post_wake(root, fixture, *, cl=0.3400367, vref=None):
    root.mkdir(exist_ok=True)
    if fixture.endswith(
        ".xz"
    ):  # recorded exports over the repository size limit are stored xz-compressed
        (root / "point_wakes.vtk").write_bytes(
            lzma.decompress((_LITB_POST__FIXTURES / fixture).read_bytes())
        )
    else:
        shutil.copyfile(_LITB_POST__FIXTURES / fixture, root / "point_wakes.vtk")
    (root / "point.fsm").write_text("$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n", "utf-8")
    loads = replace(
        parse_loads(_LITB_POST__LOADS),
        freestream_velocity_m_s=34.03,
        angle_of_attack_deg=4.0,
    )
    if vref is not None:
        loads = replace(loads, reference_velocity_m_s=vref)
    loads.total["CL"] = cl
    point = SimpleNamespace(
        name="point",
        loads=loads,
        state=SimpleNamespace(density_kg_m3=1.2250122659906946),
        vorticity_selection=None,
    )
    products = {}

    def target(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    ctx = SimpleNamespace(
        pproc=PprocSpec.model_validate({"farfields": [{"variant": "wake"}]}),
        workspace=SimpleNamespace(sim_dir=lambda sim: root),
        record_of={
            "point": SimpleNamespace(
                outputs=["point.vtk", "point.fsm"],
                package_version="0.40.0",
                recipe="steady",
            )
        },
        sim_id="1",
        points=[point],
        reference=ReferenceValues(4.934802200544679, 1.0, 6.283185307179586),
        matrix_row=SimpleNamespace(variables={"SYMMETRY": "MIRROR"}),
        sources={"point": ["recorded"]},
        skipped={},
        out=root / "post",
        table_name="point",
        condition=lambda point: {},
        target=target,
        add=lambda path, entry: products.update(
            {
                str(path): entry,
            }
        ),
        farfield_super={},
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        farfield_products(ctx)
    paths = list((root / "post" / "farfield").glob("*_trefftz.csv"))
    assert len(paths) == 1, ctx.skipped
    with paths[0].open(encoding="utf-8", newline="") as handle:
        (row,) = list(csv.DictReader(handle))
    return row, [str(w.message) for w in caught], ctx.skipped


class TestLitBPost:
    """Post the untouched wake exports through the public far-field product stage."""

    @staticmethod
    @pytest.mark.parametrize("build", ["26124", "26125"])
    def test_p0400_litb_real_mirror_wake_reaches_post(tmp_path, build):
        row, messages, skipped = _litb_post__post_wake(tmp_path, f"p0400_litB_wake_{build}.vtk")
        assert row["VARIANT"] == "B" and row["E_T"] != "NA", skipped
        # The native CL stands on the reference velocity (68.058 m/s) and CL_T on the free
        # stream's (34.03 m/s): the calibrated lift is CL q_ref SREF.
        assert float(row["CL_T"]) == pytest.approx(0.3400367 * (68.058 / 34.03) ** 2, rel=1e-4)
        assert any("collapsed wake lines" in message for message in messages) == (build == "26124")


class TestRfixAProducts:
    """Regressions through planned section layouts and the public post stage."""

    @staticmethod
    @pytest.mark.parametrize("selection", ['"Wing"', '"each"', '["Wing"]', '"outer"'])
    def test_p0400_rfixa_family_selectors_reach_post(tmp_path, selection):
        """FR-454, FR-451: stems, lists, selector words and nested aliases select both wings."""
        workspace = _rfixa_products__wing._farfield_products___workspace(tmp_path, farfield=True)
        artifact = workspace.inputs_dir / "pproc" / "p001.toml"
        artifact.write_text(
            artifact.read_text().replace('families = "all"', f"families = {selection}")
        )
        raw = workspace.sim_dir("3207") / "outputs"
        path = next(raw.glob("*_sloads.txt"))
        text = _rfixa_products__wing._farfield_products___sloads()
        rows = text.split("     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n")[1].split(
            _rfixa_products__wing._FARFIELD_PRODUCTS___RULE
        )[0]
        text = text.replace(
            f"{_rfixa_products__wing._FARFIELD_PRODUCTS__STATIONS}\n",
            f"{2 * _rfixa_products__wing._FARFIELD_PRODUCTS__STATIONS}\n",
        )
        path.write_text(text.replace(rows, rows + rows))
        layout = [
            {
                "distribution": n,
                "families": [name],
                "distribution_families": [name],
                "count": _rfixa_products__wing._FARFIELD_PRODUCTS__STATIONS,
                "plane": "XZ",
                "frame": "MRP",
            }
            for n, name in enumerate(("Wing1", "Wing2"), 1)
        ]
        _rfixa_products__post._ffproof_post___set_record(
            workspace,
            sections_layout=layout,
            inventory=["Wing1", "Wing2"],
            aliases={"outer": ["inner"], "inner": ["Wing"]},
        )
        _rfixa_products__post._ffproof_post___post(workspace)
        _, result = _rfixa_products__post._ffproof_post___table(
            _rfixa_products__post._ffproof_post___one(
                Path(workspace.root), "farfield/*_trefftz.csv"
            )
        )
        assert {r["FAMILY"] for r in result if r["VARIANT"] == "A"} == {"Wing1", "Wing2", "TOTAL"}

    @staticmethod
    def test_p0400_rfixa_missing_families_get_individual_distributions(tmp_path):
        """FR-1046: both auto-added distributions have ownership post can interpret."""
        case = _rfixa_products__plan._farfield_plan___case(
            tmp_path, [{"variant": "sections", "families": "all", "stations": 80}]
        )
        _rfixa_products__plan._farfield_plan___box(tmp_path, ("Wing1", "Wing2"))
        case = case.model_copy(update={"inventory": ("Wing1", "Wing2")})
        script = _rfixa_products__plan._farfield_plan___script(case)
        assert [block["families"] for block in script.section_blocks] == [["Wing1"], ["Wing2"]]
        assert script.render().splitlines().count("NEW_SURFACE_SECTION_DISTRIBUTION") == 2
        workspace = _rfixa_products__wing._farfield_products___workspace(tmp_path, farfield=True)
        path = next((workspace.sim_dir("3207") / "outputs").glob("*_sloads.txt"))
        text = _rfixa_products__wing._farfield_products___sloads()
        rows = text.split("     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n")[1].split(
            _rfixa_products__wing._FARFIELD_PRODUCTS___RULE
        )[0]
        path.write_text(
            text.replace(
                f"{_rfixa_products__wing._FARFIELD_PRODUCTS__STATIONS}\n",
                f"{2 * _rfixa_products__wing._FARFIELD_PRODUCTS__STATIONS}\n",
            ).replace(rows, rows + rows)
        )
        _rfixa_products__post._ffproof_post___set_record(
            workspace, sections_layout=script.section_blocks, inventory=["Wing1", "Wing2"]
        )
        _rfixa_products__post._ffproof_post___post(workspace)
        _, result = _rfixa_products__post._ffproof_post___table(
            _rfixa_products__post._ffproof_post___one(
                Path(workspace.root), "farfield/*_trefftz.csv"
            )
        )
        assert {r["FAMILY"] for r in result if r["VARIANT"] == "A"} == {"Wing1", "Wing2", "TOTAL"}

    @staticmethod
    def test_p0400_rfixa_plane_uses_reference_dynamic_pressure(tmp_path):
        """FR-1031: Cp_ref=-0.1, rho=1, V=10, Vref=20 gives p'=-20 Pa."""
        case = _rfixa_products__plan._farfield_plan___case(
            tmp_path,
            [
                {
                    "variant": "plane",
                    "half_width_bref": 0.25,
                    "half_height_bref": 0.25,
                    "spacing_bref": 0.25,
                }
            ],
        )
        # The row's VELOCITY cell follows the velocity it resolves: two different speeds
        # are refused (X-F-1157).
        case = case.model_copy(
            update={
                "velocity": 10.0,
                "variables": {**case.variables, "VELOCITY": "10.0"},
                "reference": case.reference.model_copy(update={"velocity": 20.0}),
            }
        )
        script = _rfixa_products__plan._farfield_plan___script(case)
        points = np.array([p[1:4] for p in script.probe_points])
        assert points.shape == (9, 3)
        velocity = np.tile([10.0, 0.0, 0.0], (len(points), 1))
        samples = ProbeSamples(points, velocity, np.full(len(points), -0.1))
        # Check the recorded-reference path through post, in addition to the adapter.
        workspace = _rfixa_products__post._ffproof_post___campaign(
            tmp_path,
            pproc=(
                "[[farfields]]\n"
                'variant = "plane"\n'
                "half_width_bref = 0.05\n"
                "half_height_bref = 0.05\n"
                "spacing_bref = 0.05\n"
            ),
            files={
                f"{_rfixa_products__post._FFPROOF_POST___STEM}_farfield_survey.txt": _rfixa_products__post._ffproof_post___probe_export(  # noqa: E501
                    points, 10.0
                )
            },
        )
        raw = workspace.sim_dir("3207") / "outputs"
        loads = next(raw.glob(f"{_rfixa_products__post._FFPROOF_POST___STEM}.txt"))
        text = loads.read_text()
        # The fixture prints these speeds on explicit header lines.
        lines = text.splitlines()
        for n, line in enumerate(lines):
            if "Freestream velocity (m/s)" in line:
                lines[n] = "     Freestream velocity (m/s)                   10.0"
            if "Reference velocity (m/s)" in line:
                lines[n] = "     Reference velocity (m/s)                    20.0"
            if "Angle of attack (Deg)" in line:
                lines[n] = "     Angle of attack (Deg)                       0.0"
        loads.write_text("\n".join(lines) + "\n")
        probes = next(raw.glob("*_farfield_survey.txt"))
        probes.write_text(
            probes.read_text().replace(
                " 0.000000E+00,  1.000000E+01", "-1.000000E-01,  1.000000E+01"
            )
        )
        _rfixa_products__post._ffproof_post___set_record(
            workspace, density_kg_m3=1.0, point={"alpha": 0.0}
        )
        _rfixa_products__post._ffproof_post___post(workspace)
        _, rows = _rfixa_products__post._ffproof_post___table(
            _rfixa_products__post._ffproof_post___one(
                Path(workspace.root), "farfield/*_trefftz.csv"
            )
        )
        deficit = 20.0
        star = math.sqrt(100.0 + 2.0 * deficit)
        expected = 4.0 * (deficit + 0.5 * (star - 10.0) ** 2)
        assert float(rows[0]["BERNOULLI_RESIDUAL"]) * (50.0 * 50.0) == pytest.approx(
            expected, rel=3e-4
        )
        values = plane_values(
            samples,
            slice(None),
            flow=(1.0, 10.0, 0.0, 0.0),
            grid=(1.0, 1.0, 1.0),
            per_m=1.0,
            q_ref=200.0,
        )
        assert values["RESIDUAL"] == pytest.approx(expected)

    @staticmethod
    def test_p0400_rfixa_residual_documents_the_integrated_force():
        """FR-1031: generated API Returns describes the integrated diagnostic in N."""
        returns = bernoulli_residual.__doc__.split("Returns", 1)[1]
        assert "integrated" in returns.lower() and "N" in returns
        assert "divided by dynamic pressure" not in returns


_RFIXF2_DISTRIBUTIONS___TREFFTZ_A = [{"variant": "sections", "families": "all", "stations": 80}]


def _rfixf2_distributions___sections(families: object) -> dict:
    import tests.tier1_offline.test_regression_farfield_products as wing

    return {
        "sections": {
            "count": wing._FARFIELD_PRODUCTS__STATIONS,
            "distributions": [{"families": families, "frame": "MRP", "planes": ["XZ"]}],
        }
    }


def _rfixf2_distributions___states(record: dict) -> set[str]:
    return {
        item["state"]
        for item in record["inputs"]
        if item["analysis"] == "trefftz:sections" and item["input"] == "section_distribution"
    }


class TestRfixF2Distributions:
    """P0400-RFIXF2-DISTRIBUTIONS: plan and post share one rule for a declared distribution.

    PFS-2081.100 (REL2-004): the sectional-loads export holds one block per
    distribution and plane, summed over its families, so Trefftz A traces a block
    of exactly one family. A declared ``families = "all"`` distribution on a
    geometry of one family is that family's block, and post now traces it as the
    plan reused it; a declared aggregate of several families covers none of them,
    so the plan adds their own blocks rather than reusing what post cannot read.
    """

    pytestmark = pytest.mark.requirement("FR-455")

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_an_all_distribution_of_one_family_is_traced(tmp_path, monkeypatch):
        """P0400-RFIXF2-DISTRIBUTIONS (FR-1045, FR-1047): plan reuses it, post traces it (row A)."""
        import tests.tier1_offline.test_regression_farfield_products as wing
        from pyflightstream.cases.workflows._farfield import plan_record
        from tests.tier1_offline.test_regression_farfield_interfaces import (
            _farfield_plan___case as _case,
        )
        from tests.tier1_offline.test_regression_farfield_interfaces import (
            _farfield_plan___script as _script,
        )

        (tmp_path / "plan").mkdir()
        case = _case(
            tmp_path / "plan",
            _RFIXF2_DISTRIBUTIONS___TREFFTZ_A,
            **_rfixf2_distributions___sections("all"),
        )
        script = _script(case)
        assert _rfixf2_distributions___states(plan_record(case, "26.124", script)) == {"reused"}
        (block,) = script.section_blocks
        assert block["families"] == [], "the every-boundary form, as the script records it"

        def record(**fields: Any) -> RunRecord:
            return RunRecord(**{**fields, "sections_layout": [block], "inventory": ["W"]})

        monkeypatch.setattr(wing, "_FarfieldProductsRunRecord", record)
        workspace = wing._farfield_products___workspace(tmp_path / "post", farfield=True)
        wing._farfield_products___post(workspace)
        root = Path(workspace.root)
        with wing._farfield_products___one(root, "farfield/*_trefftz.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = {row["VARIANT"]: row for row in csv.DictReader(handle)}
        assert "A" in rows and float(rows["A"]["CL_T"]) == pytest.approx(
            wing._FARFIELD_PRODUCTS__CL, rel=2e-3
        )
        skipped = json.loads(
            wing._farfield_products___one(root, "products.json").read_text(encoding="utf-8")
        )
        assert not [why for why in skipped.get("skipped", {}).values() if "distribution" in why]

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_multi_family_aggregate_covers_none(tmp_path):
        """P0400-RFIXF2-DISTRIBUTIONS (FR-1045, FR-1046): a block over W and T is no family's block.

        The plan's coverage, the rule post reads by, leaves both families
        uncovered, so the plan adds a block of each instead of reusing the
        aggregate.
        """
        from pyflightstream.cases.farfield_inputs import traced_family
        from pyflightstream.script import Script
        from tests.tier1_offline.test_regression_farfield_interfaces import (
            _farfield_plan___case as _case,
        )

        case = _case(
            tmp_path,
            _RFIXF2_DISTRIBUTIONS___TREFFTZ_A,
            **_rfixf2_distributions___sections(["W", "T"]),
        )
        script = Script("26.124")
        script.declare_existing(boundaries={"W": 1, "T": 2})
        # Neither family is covered by the block, so the plan adds its own: nothing is reused.
        assert _rfixf2_distributions___states(plan_record(case, "26.124", script)) == {"added"}
        assert traced_family(["W", "T"], ["W", "T"]) is None
        assert traced_family([], ["W"]) == "W"
        assert traced_family([], ["W", "T"]) is None


if TYPE_CHECKING:
    from pyflightstream.post.farfield_fields import ProbeSamples


def _rfixf2_matching___plane(center: tuple[float, float, float], grid: float) -> np.ndarray:
    from pyflightstream.probes.layouts import farfield_plane

    return farfield_plane(
        center,
        direction=(1.0, 0.0, 0.0),
        distance=0.0,
        half_width=grid,
        half_height=grid,
        spacing=grid,
    ).points


def _rfixf2_matching___plane_shape(center: tuple[float, float, float], grid: float) -> dict:
    return {
        "kind": "plane",
        "source": "added",
        "entry": None,
        "count": 9,
        "center_m": list(center),
        "direction": [1.0, 0.0, 0.0],
        "half_width_m": grid,
        "half_height_m": grid,
        "spacing_m": grid,
    }


def _rfixf2_matching___crossflow(points: np.ndarray) -> ProbeSamples:
    """A steady export of ``points`` in a 10 m/s stream with a 1 m/s crossflow."""
    from pyflightstream.post.farfield_fields import steady_samples
    from tests.tier1_offline.test_regression_farfield_products import (
        _rfixf_layout___export as _export,
    )

    velocity = np.tile([10.0, 1.0, 0.0], (len(points), 1))
    return steady_samples(_export(points, velocity))


class TestRfixF2Matching:
    """P0400-RFIXF2-MATCHING: far-field sets are matched to the export's precision.

    PFS-2081.103 (REL2-002): the matching tolerance is the export's printed
    precision of each coordinate, never a fraction of the distance from the origin;
    a plane of another grid at large coordinates, or a legacy export holding a
    distant unrelated point, is refused rather than integrated with the wrong area.
    Every fixture is synthetic: a uniform stream, a uniform crossflow.
    """  # noqa: E501

    pytestmark = pytest.mark.requirement("FR-455")

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_distant_plane_of_another_grid_is_refused():
        """P0400-RFIXF2-MATCHING (FR-1045, PFS-2081.103): 4 m2 laid, 16 m2 recorded, at x = 30 km.

        The control is the recorded 4 m2 plane at the same place: matched, and its
        induced drag is the crossflow's 0.5 rho v^2 S = 2 N.
        """
        from pyflightstream.post.farfield_fields import plane_values

        center = (30000.0, 0.0, 0.0)
        samples = _rfixf2_matching___crossflow(_rfixf2_matching___plane(center, 1.0))
        _, plane, why = far_samples(
            samples, recorded_layout([_rfixf2_matching___plane_shape(center, 2.0)]), per_m=1.0
        )
        assert plane is None and "no point set" in why
        _, plane, why = far_samples(
            samples, recorded_layout([_rfixf2_matching___plane_shape(center, 1.0)]), per_m=1.0
        )
        assert why == "" and plane == slice(0, 9)
        flow = (1.0, 10.0, 0.0, 0.0)
        values = plane_values(
            samples, plane, flow=flow, grid=(1.0, 1.0, 1.0), per_m=1.0, q_ref=50.0
        )
        assert values["D"] == pytest.approx(2.0, rel=1e-6)

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_legacy_export_with_a_distant_point_keeps_a_tight_tolerance():
        """P0400-RFIXF2-MATCHING (FR-1045, PFS-2081.103): one far point does not loosen matching.

        A record without a layout matches the plane by shape. A distant unrelated
        point before a 1 m grid must not make a 2 m grid's shape match it.
        """
        from pyflightstream.post.farfield_fields import FarLayout

        points = np.vstack([[[1.0e6, 0.0, 0.0]], _rfixf2_matching___plane((5.0, 0.0, 0.0), 1.0)])
        samples = _rfixf2_matching___crossflow(points)
        wider = FarLayout(
            plane_m=_rfixf2_matching___plane((0.0, 0.0, 0.0), 2.0),
            plane_grid=(2.0, 2.0, 2.0),
            plane_placed=False,
        )
        _, plane, why = far_samples(samples, wider, per_m=1.0)
        assert plane is None and "no point set" in why
        same = FarLayout(
            plane_m=_rfixf2_matching___plane((0.0, 0.0, 0.0), 1.0),
            plane_grid=(1.0, 1.0, 1.0),
            plane_placed=False,
        )
        _, plane, why = far_samples(samples, same, per_m=1.0)
        assert why == "" and plane == slice(1, 10)

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_layout_finer_than_the_printed_digits_is_refused():
        """P0400-RFIXF2-MATCHING (FR-1045, PFS-2081.103): seven digits cannot place 1 m at 3e7 m."""  # noqa: E501

        center = (3.0e7, 0.0, 0.0)
        samples = _rfixf2_matching___crossflow(_rfixf2_matching___plane(center, 1.0))
        _, plane, why = far_samples(
            samples, recorded_layout([_rfixf2_matching___plane_shape(center, 1.0)]), per_m=1.0
        )
        assert plane is None and "printed precision" in why

    @staticmethod
    @pytest.mark.parametrize("tag", ["080", "0390", "01000", "123456"])
    def test_p0400_bgtests2_parity_normalizes_any_report_tag_length(tag):
        """PFS-2081.10: the report tag is a digit run, not a four-digit field."""
        from tests.tier1_offline.test_regression_maintainer_tools import (
            _core_small_parity___load as _load,
        )

        normalize = _load().normalize
        report = f'{{"superfile_report": "reports/superfile-{tag}.json"}}'.encode()
        assert normalize("m/products.json", report) == (
            b'{"superfile_report": "reports/superfile-<VERSION>.json"}'
        )
        unrelated = b'{"path": "elsewhere/superfile-080.json", "x": "reports/superfile-a1.json"}'
        assert normalize("m/products.json", unrelated) == unrelated


def _rfixf2_plan_states___probe_states(record: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for item in record["inputs"]:
        if item["input"] == "probe_points":
            out.setdefault(item["analysis"], set()).add(item["state"])
    return out


class TestRfixF2PlanStates:
    """P0400-RFIXF2-PLANSTATES: the plan states the reuse the script makes (PFS-2081.101).

    A rotor's Trefftz C reads a station of the survey lattice. When the ledgers and
    the rotor's Trefftz C reuse one declared ``[[probes]]`` lattice, both analyses
    must say ``reused``; before the fix ``trefftz:plane`` said the lattice was added.
    """

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_rotor_trefftz_c_reads_the_declared_lattice_flag():
        """P0400-RFIXF2-PLANSTATES (FR-1047): the resolver uses the lattice flag for a rotor's C."""  # noqa: E501
        spec = FarfieldSpec.model_validate(
            {"variant": "power", "rotor": "ROTOR", "balances": ["mass"]}
        )
        resolution = resolve_farfield(
            spec,
            run_type="qsteady_rotor",
            covered_families=(),
            selected_families=["Blade"],
            exports={},
            declares_lattice=True,
            declares_plane=False,
            coupled=False,
            admits_probes=True,
            has_command=lambda command: True,
            rotor=True,
        )
        assert _rfixf2_plan_states___probe_states(resolution.as_record()) == {
            "trefftz:power": {"reused"},
            "ledgers": {"reused"},
        }

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_the_rotor_plan_matches_the_selected_shapes(tmp_path):
        """P0400-RFIXF2-PLANSTATES (FR-1045, FR-1047): a steady rotor row reusing one lattice twice.

        The script lays the declared lattice once and records it as the entry
        reused; the plan says reused for the ledgers and for the rotor's Trefftz C.
        """
        lattice = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16}
        case = _rfixf2_plan_states___case(
            tmp_path,
            [{"variant": "power", "rotor": "ROTOR", "m_max": 2, "balances": ["mass"]}],
            probes=[
                {
                    "kind": "instantaneous",
                    "frame": "REFERENCE",
                    "parameters": ["VX"],
                    "lattices": [lattice],
                }
            ],
        )
        case = case.model_copy(update={"point": {**case.point, "RPM": 1000.0}})
        script = _rfixf2_plan_states___script(case)
        count = LatticeShape.model_validate(lattice).build(1.0).point_count
        assert len(script.probe_points) == count
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert (shape["kind"], shape["source"]) == ("lattice", "declared")
        states = _rfixf2_plan_states___probe_states(plan_record(case, "26.124", script))
        assert states == {"trefftz:power": {"reused"}, "ledgers": {"reused"}}


_RFIXF2_PLOTS___PLOT = "UNSTEADY_SOLVER_NEW_FLUID_PLOT"


def _rfixf2_plots___plot_names(text: str) -> list[str]:
    """The names of the fluid plots a rendered script creates, in order."""
    lines = text.splitlines()
    named = re.compile(r"^\s*NAME\s+(\w+)\s*$")
    names = []
    for at, line in enumerate(lines):
        if line.strip() == _RFIXF2_PLOTS___PLOT:
            names += [m.group(1) for m in map(named.match, lines[at + 1 : at + 6]) if m]
    return names


class TestRfixF2Plots:
    """P0400-RFIXF2-PLOTS: a reused declared lattice on an unsteady row gets the histories it lacks.

    PFS-2081.99 (REL2-003): the far field reads ``VX``, ``VY``, ``VZ`` and
    ``CP_REF`` at every step. A declared ``[[probes]]`` lattice reused by identity
    keeps its points and its own histories, and the plan adds the missing ones at
    the same vertices, in the entry's frame, and states their count; before the fix
    a ``VX``-only declaration left the other three absent and post read NaN.
    """

    pytestmark = pytest.mark.requirement("FR-455")

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_vx_only_lattice_gets_the_other_histories(tmp_path):
        """P0400-RFIXF2-PLOTS (FR-1045, FR-1052): VX declared; VY, VZ and CP_REF added at its
         vertices.

        No probe point is laid twice; every vertex of the lattice carries the four
        histories post reads, so one step of synthetic plots under those names
        leaves no NaN in the matched lattice.
        """
        entry = {
            "kind": "instantaneous",
            "frame": "MRP",
            "parameters": ["VX"],
            "lattices": [_RFIXF2_PLOTS___LATTICE],
        }
        case = _rfixf2_plots___unsteady(
            tmp_path,
            [{"variant": "power", **dict(_RFIXF2_PLOTS___LATTICE, m_max=2)}],
            probes=[entry],
        )
        script = Script("26.124")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            build_script(case, script)
        messages = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
        text = script.render()
        assert len(script.probe_points) == _RFIXF2_PLOTS___POINTS, "the declared lattice, laid once"
        assert text.count(_RFIXF2_PLOTS___PLOT) == _RFIXF2_PLOTS___POINTS
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert shape["source"] == "declared" and "plots_added" not in shape
        assert any("per exported step" in message for message in messages)
        names = _rfixf2_plots___plot_names(text)
        assert names == [f"VX{point[0]}" for point in script.probe_points]
        assert "PROBE_POINTS_IMPORT" in text and "_farfield_survey.txt" in text

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_lattice_stating_every_history_adds_none(tmp_path):
        """P0400-RFIXF2-PLOTS (FR-1045): nothing is added to an entry that states all four."""
        entry = {
            "kind": "instantaneous",
            "frame": "MRP",
            "parameters": ["VX", "VY", "VZ", "CP_REF"],
            "lattices": [_RFIXF2_PLOTS___LATTICE],
        }
        case = _rfixf2_plots___unsteady(
            tmp_path,
            [{"variant": "power", **dict(_RFIXF2_PLOTS___LATTICE, m_max=2)}],
            probes=[entry],
        )
        script = Script("26.124")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            build_script(case, script)
        assert script.render().count(_RFIXF2_PLOTS___PLOT) == 4 * _RFIXF2_PLOTS___POINTS
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert "plots_added" not in shape


_RFIXF_LAYOUT___RHO = _rfixf_layout__ffpost._FFPROOF_POST___RHO


_RFIXF_LAYOUT___SPEED = 68.058  # the free stream of the loads fixture, m/s


_RFIXF_LAYOUT___ALPHA = -2.0  # its incidence, deg


_RFIXF_LAYOUT___SREF = 50.0


_RFIXF_LAYOUT___Q = 0.5 * _RFIXF_LAYOUT___RHO * _RFIXF_LAYOUT___SPEED**2


def _rfixf_layout___export(points: np.ndarray, velocity: np.ndarray, *, digits: int = 6) -> str:
    """A steady probe-points export of ``points`` (native) with ``velocity`` (m/s) at each."""
    rows = "".join(
        "     "
        + ", ".join(
            f"{v: .{digits}E}"
            for v in (*p, 0.1, 0.0, *u, float(np.linalg.norm(u)), 0.0)  # X Y Z Mach Cp_ref vxyz
        )
        + ", 0.0000E+00" * 6
        + ",\n"
        for p, u in zip(points, velocity, strict=True)
    )
    fixture = Path(_rfixf_layout__ffpost.__file__).parent / "fixtures" / "probe_points_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    columns = (
        "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp, s_len, momentum_thickness, disp_thick,"
    )
    head, _, tail = text.partition(columns)
    head = head.replace(
        "Number of Probe Points:                     12",
        f"Number of Probe Points:                     {len(points)}",
    )
    footer = tail.split(_rfixf_layout__ffpost._FFPROOF_POST___RULE)[-1]
    rule = _rfixf_layout__ffpost._FFPROOF_POST___RULE
    return head + columns + tail.split("\n", 1)[0] + "\n" + rule + rows + rule + footer


def _rfixf_layout___rows(root: Path, pattern: str) -> list[dict[str, str]]:
    found = sorted(root.rglob(pattern))
    if not found:
        return []
    with found[0].open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rfixf_layout___skipped(root: Path) -> dict[str, str]:
    manifest = json.loads(
        _rfixf_layout__ffpost._ffproof_post___one(root, "products.json").read_text(encoding="utf-8")
    )
    return {k: v for k, v in manifest.get("skipped", {}).items() if k.startswith("farfield/")}


# ------------------------------------------------------------- the plane (PFS-2081.58)
_RFIXF_LAYOUT___DIRECTION = (
    math.cos(math.radians(_RFIXF_LAYOUT___ALPHA)),
    0.0,
    math.sin(math.radians(_RFIXF_LAYOUT___ALPHA)),
)


#: The plane the run laid: 3 by 3 points 1 m apart, 4 m^2 by the trapezoid rule.
_RFIXF_LAYOUT___LAID = farfield_plane(
    (30.0, 0.0, 1.0),
    direction=_RFIXF_LAYOUT___DIRECTION,
    distance=0.0,
    half_width=1.0,
    half_height=1.0,
    spacing=1.0,
)


#: The table as it stands at post states another 3 by 3 grid, 2 m apart (16 m^2).
_RFIXF_LAYOUT___TABLE_2M = (
    "[[farfields]]\n"
    'variant = "plane"\n'
    "half_width_bref = 0.1\n"
    "half_height_bref = 0.1\n"
    "spacing_bref = 0.1\n"
)


_RFIXF_LAYOUT___TABLE_1M = _RFIXF_LAYOUT___TABLE_2M.replace("0.1", "0.05")


_RFIXF_LAYOUT___PLANE_RECORD = {
    "shapes": [
        {
            "kind": "plane",
            "source": "added",
            "entry": None,
            "count": 9,
            "center_m": [30.0, 0.0, 1.0],
            "direction": list(_RFIXF_LAYOUT___DIRECTION),
            "half_width_m": 1.0,
            "half_height_m": 1.0,
            "spacing_m": 1.0,
        }
    ]
}


@pytest.mark.requirement("FR-1062")
@pytest.mark.parametrize("plane_name", ["net", "plane"])
def test_p0450_d7_super_cells_belong_to_each_entry(tmp_path, plane_name):
    """P0450-D7: two A entries and C retain separate aggregate cells."""
    workspace = _farfield_products___workspace(tmp_path, farfield=True)
    pproc = workspace.inputs_dir / "pproc" / "p001.toml"
    text = pproc.read_text(encoding="utf-8")
    text = text.replace('variant = "sections"', 'name = "wing"\nvariant = "sections"')
    text += '\n[[farfields]]\nname = "tail"\nvariant = "sections"\nfamilies = "all"\n'
    if plane_name == "net":
        text = text.replace('variant = "plane"', 'name = "net"\nvariant = "plane"')
    pproc.write_text(text, encoding="utf-8")
    _farfield_products___post(workspace)
    root = Path(workspace.root)
    rows = _farfield_products___table(_farfield_products___one(root, "farfield/*_trefftz.csv"))
    (super_row,) = _farfield_products___table(_farfield_products___one(root, "polars/SUPER-*.csv"))
    assert {r["ENTRY"] for r in rows} == {"wing", "tail", "wake", plane_name}
    for row in rows:
        for column in ("CL_T", "CDI_T", "E_T"):
            key = f"{column}_{row['VARIANT']}_{row['ENTRY']}"
            assert key in super_row
            actual = super_row[key]
            assert (
                actual == "NA"
                if row[column] == "NA"
                else float(actual) == pytest.approx(float(row[column]), abs=1e-5)
            )


@pytest.mark.requirement("FR-1062")
def test_p0450_d5_super_reads_net_and_preserves_a_total(tmp_path):
    """P0450-D5: every variant keeps its columns and selects its aggregate row."""
    workspace = _farfield_products___workspace(tmp_path, farfield=True)
    _farfield_products___post(workspace)
    root = Path(workspace.root)
    rows = _farfield_products___table(_farfield_products___one(root, "farfield/*_trefftz.csv"))
    (super_row,) = _farfield_products___table(_farfield_products___one(root, "polars/SUPER-*.csv"))
    assert {(r["VARIANT"], r["FAMILY"]) for r in rows} == {
        ("A", "TOTAL"),
        ("B", "net"),
        ("C", "net"),
    }
    for row in rows:
        for column in ("CL_T", "CDI_T", "E_T"):
            actual = super_row[f"{column}_{row['VARIANT']}_{row['ENTRY']}"]
            if row[column] == "NA":
                assert actual == "NA"
            else:
                assert float(actual) == pytest.approx(float(row[column]), abs=1e-5)


def _p0450_plane_series(tmp_path, extra=""):
    workspace = _ffproof_post___campaign(
        tmp_path,
        pproc=(_RFIXF_LAYOUT___TABLE_1M + extra).replace(
            "[[farfields]]", '[[farfields]]\nexport_type = "avg_window"'
        ),
        files=_p0450_probe_series(_RFIXF_LAYOUT___LAID.points),
        recipe="unsteady_rotor",
        reductions=_FFPROOF_POST___WINDOW,
    )
    positions = [
        (i, *map(float, point), "REFERENCE")
        for i, point in enumerate(_RFIXF_LAYOUT___LAID.points, 1)
    ]
    path = _write_probe_points(workspace.sim_dir("3207"), "3207", positions)
    _ffproof_post___set_record(
        workspace, probe_points_file=path, farfield_layout=_RFIXF_LAYOUT___PLANE_RECORD
    )
    return workspace


@pytest.mark.parametrize("recipe", ["steady", "unsteady_rotor"])
@pytest.mark.parametrize("balances", [False, True])
def test_p0450_d2_power_writes_d_and_optional_ledgers(tmp_path, recipe, balances):
    table = _FFPROOF_POST___LEDGERS + "station = 1.0\n"
    if not balances:
        table = table[: table.index("balances =")] + table[table.index("frame =") :]
    unsteady = recipe == "unsteady_rotor"
    files = (
        _p0450_probe_series(_FFPROOF_POST___POINTS_M)
        if unsteady
        else {
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _ffproof_post___probe_export(
                _FFPROOF_POST___POINTS_M, 20.0
            )
        }
    )
    workspace = _ffproof_post___campaign(
        tmp_path,
        pproc=table,
        files=files,
        recipe=recipe,
        reductions=_FFPROOF_POST___WINDOW if unsteady else None,
        positions=unsteady,
    )
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    suffix = "_instant" if unsteady else ""
    rows = _rfixf_layout___rows(root, f"farfield/*_trefftz{suffix}.csv")
    assert len(rows) == 1
    row = rows[0]
    assert (row["VARIANT"], row["FAMILY"], row["ENTRY"]) == ("D", "net", "power")
    assert float(row["X_T_M"]) == 1.0
    assert row["P_AXIAL_W"] != "NA" and row["ETA_FF"] == "NA"
    assert bool(_rfixf_layout___rows(root, f"farfield/*_ledgers{suffix}.csv")) is balances


def test_p0450_d1_rotor_plane_posts_instant_and_average(tmp_path):
    workspace = _p0450_plane_series(tmp_path)
    _ffproof_post___post(workspace)
    for suffix, step in (("instant", "8"), ("average", "AVERAGE")):
        rows = _rfixf_layout___rows(Path(workspace.root), f"farfield/*_trefftz_{suffix}.csv")
        assert len(rows) == 1, "C must read the plane on an unsteady rotor row"
        assert (rows[0]["VARIANT"], rows[0]["FAMILY"], rows[0]["STEP"]) == ("C", "net", step)


@pytest.mark.parametrize("broken_step", [1, 7])
@pytest.mark.requirement("FR-1052")
def test_p0450_rv1_bad_snapshot_preserves_valid_instant(tmp_path, broken_step):
    """P0450-RV1-03: only the average needing a broken snapshot is lost."""
    workspace = _p0450_plane_series(tmp_path)
    path = next(workspace.sim_dir("3207").rglob(f"*_farfield_survey_iteration={broken_step}.txt"))
    path.write_text("truncated export", encoding="utf-8")
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    instant = _rfixf_layout___rows(root, "farfield/*_trefftz_instant.csv")
    assert len(instant) == 1 and instant[0]["STEP"] == "8"
    assert float(instant[0]["CDI_T"]) > 0
    average = _rfixf_layout___rows(root, "farfield/*_trefftz_average.csv")
    assert bool(average) is (broken_step == 1)
    if broken_step == 7:
        skipped = str(_ffproof_post___manifest(root)["skipped"])
        assert "step=7" in skipped and "restore" in skipped.lower()


def test_p0450_d2_rotor_lattice_and_plane_write_both(tmp_path):
    table = _FFPROOF_POST___LEDGERS.replace('frame = "MRP"\ntip_radius_m = 1.0', 'rotor = "ROTOR"')
    workspace = _p0450_plane_series(tmp_path, "\n" + table)
    points = np.vstack([_RFIXF_LAYOUT___LAID.points, _FFPROOF_POST___POINTS_M])
    path = _write_probe_points(
        workspace.sim_dir("3207"),
        "3207",
        [(i, *map(float, p), "REFERENCE") for i, p in enumerate(points, 1)],
    )
    shape = {
        "kind": "lattice",
        "source": "added",
        "entry": None,
        "count": len(_FFPROOF_POST___POINTS_M),
        "farfield_entry": "power",
        "axis": "X",
        "origin_m": [0.0, 0.0, 0.0],
        "positions_frame": "REFERENCE",
        "lattice": _FFPROOF_POST___SHAPE.build(1.0).model_dump(mode="json"),
    }
    plane = dict(_RFIXF_LAYOUT___PLANE_RECORD["shapes"][0], farfield_entry="plane")
    _ffproof_post___set_record(
        workspace,
        probe_points_file=path,
        farfield_layout={"shapes": [plane, shape]},
    )
    for name, text in _p0450_probe_series(points).items():
        (workspace.sim_dir("3207") / "outputs" / name).write_text(text, encoding="utf-8")
    _ffproof_post___post(workspace)
    for suffix in ("instant", "average"):
        rows = _rfixf_layout___rows(Path(workspace.root), f"farfield/*_trefftz_{suffix}.csv")
        assert {(row["ENTRY"], row["VARIANT"]) for row in rows} == {("plane", "C"), ("power", "D")}


@pytest.mark.parametrize("series", [False, True])
def test_p0450_d3_unsteady_sections_instant_and_window(tmp_path, series):
    workspace = _farfield_products___workspace(tmp_path, farfield=True)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[[farfields]]\nvariant = "sections"\nexport_type = "avg_window"\nfamilies = ["W"]\n',
        encoding="utf-8",
    )
    _ffproof_post___set_record(
        workspace, recipe="unsteady_rotor", reductions=_FFPROOF_POST___WINDOW
    )
    source = next(workspace.sim_dir("3207").rglob("*_sloads.txt"))
    if series:
        for step in range(5, 9):
            lines = []
            for line in source.read_text().splitlines():
                cells = line.split(",")
                if len(cells) == 8:
                    cells[5] = str(float(cells[5]) * step / 8)
                lines.append(",".join(cells))
            source.with_name(f"{source.stem}_iteration={step}.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
    _farfield_products___post(workspace)
    root = Path(workspace.root)
    instant = _rfixf_layout___rows(root, "farfield/*_trefftz_instant.csv")
    assert instant and {row["VARIANT"] for row in instant} == {"A"}
    assert {row["STEP"] for row in instant} == {"8"}
    average = _rfixf_layout___rows(root, "farfield/*_trefftz_average.csv")
    assert bool(average) is series
    if series:
        ratio = np.mean([(step / 8) ** 2 for step in range(5, 9)])
        assert float(average[-1]["CDI_T"]) == pytest.approx(
            float(instant[-1]["CDI_T"]) * ratio, rel=1e-5
        )
    else:
        manifest = str(_ffproof_post___manifest(root))
        assert "per-step sectional" in manifest
        assert "per-step sectional" in next(root.rglob("post.log")).read_text()


@pytest.mark.parametrize(
    "key,value,first", [("last_steps", 2, 7), ("last_revs", 0.5, 7), ("last_steps", 20, 1)]
)
def test_p0450_d4_entry_window_preserves_instant(tmp_path, key, value, first):
    workspace = _p0450_plane_series(tmp_path, f"{key} = {value}\n")
    _ffproof_post___set_record(
        workspace, reductions={**_FFPROOF_POST___WINDOW, "steps_per_revolution": 4}
    )
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    instant = _rfixf_layout___rows(root, "farfield/*_trefftz_instant.csv")[0]
    average = _rfixf_layout___rows(root, "farfield/*_trefftz_average.csv")[0]
    assert instant["STEP"] == "8"
    ratio = np.mean([(10 + step) ** 2 for step in range(first, 9)]) / 18**2
    assert float(average["CDI_T"]) / float(instant["CDI_T"]) == pytest.approx(ratio, rel=1e-5)
    manifest = _ffproof_post___entry(_ffproof_post___manifest(root), "_trefftz_average.csv")
    reduced = next(iter(manifest["reduced_from"].values()))
    entry = reduced["entries"]["plane"]
    assert entry["window"] == [first, 8]
    assert entry["source"] == f"{key} = {value:g}"


def test_p0450_d4_two_entries_keep_separate_windows(tmp_path):
    extra = "last_steps = 2\n" + _RFIXF_LAYOUT___TABLE_1M + 'name = "long"\nlast_steps = 4\n'
    workspace = _p0450_plane_series(tmp_path, extra)
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    rows = _rfixf_layout___rows(root, "farfield/*_trefftz_average.csv")
    assert {row["ENTRY"] for row in rows} == {"plane", "long"}
    assert rows[0]["CDI_T"] != rows[1]["CDI_T"]
    manifest = _ffproof_post___entry(_ffproof_post___manifest(root), "_trefftz_average.csv")
    entries = next(iter(manifest["reduced_from"].values()))["entries"]
    assert entries["plane"]["window"] == [7, 8]
    assert entries["long"]["window"] == [5, 8]


def _rfixf_layout___crossflow_plane(tmp_path: Path, table: str, **record: object):
    """A point whose export holds the laid plane in the free stream plus 1 m/s along its y."""
    velocity = np.tile(
        np.asarray(_RFIXF_LAYOUT___DIRECTION) * _RFIXF_LAYOUT___SPEED
        + _RFIXF_LAYOUT___LAID.axes[1],
        (len(_RFIXF_LAYOUT___LAID.points), 1),
    )
    workspace = _rfixf_layout__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=table,
        files={
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_layout___export(
                _RFIXF_LAYOUT___LAID.points, velocity
            )
        },
    )
    if record:
        _rfixf_layout__ffpost._ffproof_post___set_record(workspace, **record)
    _rfixf_layout__ffpost._ffproof_post___post(workspace)
    return Path(workspace.root)


# ----------------------------------------------- a frame's lattice (PFS-2081.58)
_RFIXF_LAYOUT___POINTS = _rfixf_layout__ffpost._FFPROOF_POST___POINTS_M


_RFIXF_LAYOUT___LATTICE = _rfixf_layout__ffpost._FFPROOF_POST___SHAPE.build(1.0)


_RFIXF_LAYOUT___OTHER = 20


def _rfixf_layout___lattice_then_another_entry(tmp_path: Path, **record: object):
    """The MRP lattice in a 20 m/s stream, then twenty probes of another entry at 50 m/s."""
    other = np.array([[5.0, float(k), 0.0] for k in range(_RFIXF_LAYOUT___OTHER)])
    positions = np.vstack([_RFIXF_LAYOUT___POINTS, other])
    stream = np.tile([20.0, 0.0, 0.0], (len(_RFIXF_LAYOUT___POINTS), 1))
    velocity = np.vstack([stream, np.tile([50.0, 0.0, 0.0], (_RFIXF_LAYOUT___OTHER, 1))])
    workspace = _rfixf_layout__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=_rfixf_layout__ffpost._FFPROOF_POST___LEDGERS,
        files={
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_layout___export(
                positions, velocity
            )
        },
    )
    if record:
        _rfixf_layout__ffpost._ffproof_post___set_record(workspace, **record)
    _rfixf_layout__ffpost._ffproof_post___post(workspace)
    return _rfixf_layout___rows(Path(workspace.root), "farfield/*_ledgers.csv")


def _rfixf_layout___annulus() -> float:
    edges = _RFIXF_LAYOUT___LATTICE.ring_edges
    return math.pi * (edges[-1] ** 2 - edges[0] ** 2) * _RFIXF_LAYOUT___LATTICE.tip_radius**2


# ---------------------------------------------------- planning (PFS-2081.56)
def _rfixf_layout___states(record: dict, analysis: str) -> set[str]:
    return {
        item["state"]
        for item in record["inputs"]
        if item["analysis"] == analysis and item["input"] == "probe_points"
    }


class TestRfixFLayout:
    """P0400-RFIXF-LAYOUT: the far field integrates exactly the probes the run laid (PFS-2081.56, .58).

    The plan chooses the far-field plane and lattice once, by frame and by the
    exact laid-out points (a declared ``[[probes]]`` shape reused, or the far
    field's own added), records the choice on the script, the run carries it in
    its record, and post matches every exported position to it before it
    integrates; what it cannot match exactly once is a named skip. Every fixture is
    synthetic: a box mesh, a uniform stream, a uniform crossflow.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.requirement("FR-453")
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf_the_recorded_plane_is_integrated_with_its_own_grid(tmp_path):
        """P0400-RFIXF-LAYOUT (PFS-2081.58): the table changed to a grid of the same count.

        The run laid 3 by 3 points 1 m apart; the table now states 3 by 3 points
        2 m apart. Before the fix post took the plane by its count and gave it the
        table's grid, 16 m^2 for 4, so the crossflow energy of a 1 m/s crossflow
        was 4 times too large; it integrates the recorded grid now.
        """
        root = _rfixf_layout___crossflow_plane(
            tmp_path, _RFIXF_LAYOUT___TABLE_2M, farfield_layout=_RFIXF_LAYOUT___PLANE_RECORD
        )
        (row,) = [
            r for r in _rfixf_layout___rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"
        ]
        drag = 0.5 * _RFIXF_LAYOUT___RHO * 1.0 * 4.0  # rho/2 * v^2 * the laid plane's area, N
        assert float(row["CDI_T"]) == pytest.approx(
            drag / (_RFIXF_LAYOUT___Q * _RFIXF_LAYOUT___SREF), rel=1e-5
        )
        assert float(row["N_TRACE"]) == 9

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_rfixf_a_record_without_a_layout_matches_the_plane_by_shape(tmp_path):
        """P0400-RFIXF-LAYOUT (PFS-2081.58): no layout recorded, the table's grid is matched.

        The same export posted against a table stating the laid grid gives the
        4 m^2 value; against a table stating another grid of the same count it is
        a named skip and no C row, never the 16 m^2 value.
        """
        (tmp_path / "same").mkdir()
        root = _rfixf_layout___crossflow_plane(tmp_path / "same", _RFIXF_LAYOUT___TABLE_1M)
        (row,) = [
            r for r in _rfixf_layout___rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"
        ]
        assert float(row["CDI_T"]) == pytest.approx(
            0.5 * _RFIXF_LAYOUT___RHO * 4.0 / (_RFIXF_LAYOUT___Q * _RFIXF_LAYOUT___SREF), rel=1e-5
        )
        (tmp_path / "other").mkdir()
        root = _rfixf_layout___crossflow_plane(tmp_path / "other", _RFIXF_LAYOUT___TABLE_2M)
        assert not [
            r for r in _rfixf_layout___rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"
        ]
        (reason,) = _rfixf_layout___skipped(root).values()
        assert "shape of the plane" in reason

    @staticmethod
    @pytest.mark.requirement("FR-38")
    @pytest.mark.parametrize("recorded", [False, True], ids=["legacy-record", "recorded-layout"])
    def test_p0400_rfixf_a_frame_lattice_before_another_entry_is_found(tmp_path, recorded):
        """P0400-RFIXF-LAYOUT (PFS-2081.58): the lattice, not the last points of the export.

        Before the fix post took a frame's lattice as the last points of the
        export, here the last 48: 28 lattice points and the 20 probes of the next
        entry at 50 m/s, which landed on the lateral rings and the outlet
        station, so the outlet's mass flow was not the lattice's. It is the
        uniform stream's ``rho V A`` at every station now, with the layout
        recorded and without it.
        """
        record = {}
        if recorded:
            shape = {
                "kind": "lattice",
                "source": "declared",
                "entry": 1,
                "count": len(_RFIXF_LAYOUT___POINTS),
                "lattice": _RFIXF_LAYOUT___LATTICE.model_dump(mode="json"),
                "axis": "X",
                "origin_m": [0.0, 0.0, 0.0],
                "positions_frame": "MRP",
            }
            record = {"farfield_layout": {"shapes": [shape]}}
        rows = _rfixf_layout___lattice_then_another_entry(tmp_path, **record)
        assert [float(row["STATION_X_R"]) for row in rows] == [-1.0, 1.0]
        for row in rows:
            assert float(row["MDOT_KG_S"]) == pytest.approx(
                _RFIXF_LAYOUT___RHO * 20.0 * _rfixf_layout___annulus(), rel=1e-6
            )

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf_a_unique_nondefault_lattice_is_reused(tmp_path):
        """P0400-RFIXF-LAYOUT (FR-1045): a table stating no geometry reuses the one declared.

        The ledgers name the rotor and state no lattice key; one ``[[probes]]``
        lattice is declared on that rotor with its own stations and rings. It is
        reused: the script lays its points once, adds none, records it as the
        declared entry, and the plan says reused. Before the fix the raw fields
        differed, the plan said added and the default lattice was laid beside it.
        """
        declared = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16}
        case = _rfixf_layout___case(
            tmp_path,
            [{"variant": "power", **{"rotor": "ROTOR", "m_max": 2}}],
            probes=[
                {
                    "kind": "instantaneous",
                    "frame": "REFERENCE",
                    "parameters": ["VX"],
                    "lattices": [declared],
                }
            ],
        )
        script = _rfixf_layout___script(case)
        count = LatticeShape.model_validate(declared).build(1.0).point_count
        assert len(script.probe_points) == count, "laid once, the declared entry"
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert (shape["kind"], shape["source"], shape["entry"]) == ("lattice", "declared", 1)
        assert shape["lattice"]["stations"] == [2.0]
        assert _rfixf_layout___states(plan_record(case, "26.124", script), "trefftz:power") == {
            "reused"
        }

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf_a_default_equivalent_geometry_is_reused(tmp_path):
        """P0400-RFIXF-LAYOUT (FR-1045): a stated key equal to its default is the same lattice.

        The ledgers state ``r_inner = 0.05``, the default the declared lattice
        takes by leaving it unstated: the same points after layout, so the
        declaration is reused; the raw fields differed before the fix.
        """
        shape = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16}
        case = _rfixf_layout___case(
            tmp_path,
            [{"variant": "power", **dict(shape, r_inner=0.05, m_max=2)}],
            probes=[
                {
                    "kind": "instantaneous",
                    "frame": "REFERENCE",
                    "parameters": ["VX"],
                    "lattices": [shape],
                }
            ],
        )
        script = _rfixf_layout___script(case)
        assert len(script.probe_points) == LatticeShape.model_validate(shape).build(1.0).point_count
        assert script.farfield_layout[-1]["shapes"][0]["source"] == "declared"
        assert _rfixf_layout___states(plan_record(case, "26.124", script), "trefftz:power") == {
            "reused"
        }

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf_a_declared_plane_is_reused(tmp_path):
        """P0400-RFIXF-LAYOUT (FR-1045): the one rectangle that is a Trefftz plane is reused.

        No plane key is stated; one rectangle is declared behind the box, normal
        to the free stream, 5 by 3 points 0.5 m apart. It is the far field's
        plane: no plane is added, the layout names the entry with the
        rectangle's center and grid, and the plan says reused. Before the fix the
        plan always added its own plane.
        """
        rectangle = {
            "origin": [3.0, -1.0, -0.5],
            "along_u": [3.0, 1.0, -0.5],
            "along_v": [3.0, -1.0, 0.5],
            "points_u": 5,
            "points_v": 3,
        }
        case = _rfixf_layout___case(
            tmp_path,
            [{"variant": "plane"}],
            probes=[
                {
                    "kind": "instantaneous",
                    "frame": "REFERENCE",
                    "parameters": ["VX"],
                    "rectangles": [rectangle],
                }
            ],
        )
        script = _rfixf_layout___script(case)
        assert len(script.probe_points) == 15, "the declared rectangle alone"
        assert "PROBE_POINTS_IMPORT" not in script.render(), "no far-field plane added"
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert (shape["kind"], shape["source"], shape["entry"]) == ("plane", "declared", 1)
        assert shape["center_m"] == pytest.approx([3.0, 0.0, 0.0])
        assert (shape["half_width_m"], shape["half_height_m"], shape["spacing_m"]) == pytest.approx(
            (1.0, 0.5, 0.5)
        )
        record = plan_record(case, "26.124", script)
        assert _rfixf_layout___states(record, "trefftz:plane") == {"reused"}
        assert record["probes"][0]["entry"] == 1

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf_a_rectangle_that_is_no_trefftz_plane_is_not_reused(tmp_path):
        """P0400-RFIXF-LAYOUT (FR-1045): a rectangle in front of the body is not the plane."""
        rectangle = {
            "origin": [-3.0, -1.0, -0.5],
            "along_u": [-3.0, 1.0, -0.5],
            "along_v": [-3.0, -1.0, 0.5],
            "points_u": 5,
            "points_v": 3,
        }
        case = _rfixf_layout___case(
            tmp_path,
            [{"variant": "plane", "spacing_bref": 0.25}],
            probes=[
                {
                    "kind": "instantaneous",
                    "frame": "REFERENCE",
                    "parameters": ["VX"],
                    "rectangles": [rectangle],
                }
            ],
        )
        script = _rfixf_layout___script(case)
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert shape["source"] == "added"
        assert len(script.probe_points) == 15 + 7 * 5

    @staticmethod
    # ------------------------------------------------- the record (FR-1047)
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf_a_job_hands_each_point_its_own_layout():
        """P0400-RFIXF-LAYOUT (FR-1047): a steady job keys the layouts by point; absent unset."""
        common = dict(
            sim_id="1",
            status=RunStatus.CONVERGED,
            script_sha256="",
            raw_flag=False,
            fs_version_requested="26.124",
            package_version="0.40.0",
        )
        plain = RunRecord(run_id="c/sim_1/AL+000", **common)
        assert "farfield_layout" not in plain.model_dump(mode="json")
        layouts = {"AL+000": {"shapes": [{"kind": "plane"}]}, "AL+040": {"shapes": [{"kind": "x"}]}}
        job = RunRecord(
            run_id="c/sim_1/sweep",
            farfield_layout={"by_point": layouts},
            points_ran=[{"tag": tag, "point": {}, "status": "CONVERGED"} for tag in layouts],
            **common,
        )
        again = RunRecord.model_validate(json.loads(json.dumps(job.model_dump(mode="json"))))
        points = {p.point_name: p.farfield_layout for p in again.as_points()}
        assert points == layouts

    @staticmethod
    def test_p0400_rfixf_layout_points_rebuild_bit_for_bit():
        """P0400-RFIXF-LAYOUT: a recorded lattice and plane lay again to the same bits after JSON."""  # noqa: E501

        lattice = _rfixf_layout__ffpost._FFPROOF_POST___SHAPE.build(1.0)
        shapes = [
            json.loads(json.dumps(_RFIXF_LAYOUT___PLANE_RECORD["shapes"][0])),
            json.loads(
                json.dumps(
                    {
                        "kind": "lattice",
                        "count": lattice.point_count,
                        "lattice": lattice.model_dump(mode="json"),
                        "axis": "X",
                        "origin_m": [0.25, 0.0, 0.1],
                    }
                )
            ),
        ]
        layout = recorded_layout(shapes)
        assert np.array_equal(layout.plane_m, _RFIXF_LAYOUT___LAID.points)
        assert np.array_equal(
            layout.lattice_m, lattice_points(lattice, axis="X") + [0.25, 0.0, 0.1]
        )


_RFIXF_DRAG_SPLIT___STEM = "POLAR-3207_M20AL-020BE+000"


_RFIXF_DRAG_SPLIT___RECORDED = Path(__file__).parent / "fixtures" / "s10_26125" / "loads_26.125.txt"


def _rfixf_drag_split___header(text: str) -> str:
    (line,) = [line for line in text.splitlines() if line.strip().startswith("Surface,")]
    return line


class TestRfixFDragSplit:
    """P0400-RFIXF-DRAGSPLIT: the far field reads the solver's induced drag on 26.125 (PFS-2081.98).

    26.125 prints its loads split as ``CDp, CDv`` where earlier builds print
    ``CDi, CDo`` (FR-423). The far-field rows read the solver's induced drag for
    direct comparison (``CDI_NEAR_PRESSURE``, ``CDI_NEAR_VORTICITY``) and read
    ``CDi`` only, so on 26.125 they wrote ``NA``. They now read the first column of
    whichever split the table prints. The 26.125 header is the recorded one of
    ``fixtures/s10_26125/loads_26.125.txt``.
    """

    @staticmethod
    @pytest.mark.requirement("FR-456")
    @pytest.mark.parametrize("build", ["26.124", "26.125"])
    def test_p0400_rfixf_the_near_field_induced_drag_is_read_on_both_builds(tmp_path, build):
        """P0400-RFIXF-DRAGSPLIT (FR-1054, FR-423): ``CDI_NEAR_PRESSURE`` is the split's first column.

        The same loads table with the 26.124 header and with the recorded 26.125
        header (``CDp, CDv`` in the same places): both rows state 0.0012418, the
        total's induced or pressure drag. Before the fix the 26.125 rows read NA.
        """  # noqa: E501
        workspace = _rfixf_drag_split__wing._farfield_products___workspace(tmp_path, farfield=True)
        if build == "26.125":
            loads = workspace.sim_dir("3207") / "outputs" / f"{_RFIXF_DRAG_SPLIT___STEM}.txt"
            text = loads.read_text(encoding="utf-8")
            recorded = _rfixf_drag_split___header(
                _RFIXF_DRAG_SPLIT___RECORDED.read_text(encoding="utf-8")
            )
            assert "CDp, CDv" in recorded
            loads.write_text(
                text.replace(_rfixf_drag_split___header(text), recorded), encoding="utf-8"
            )
        _rfixf_drag_split__ffpost._ffproof_post___post(workspace)
        rows = _rfixf_layout___rows(Path(workspace.root), "farfield/*_trefftz.csv")
        assert rows
        assert {row["CDI_NEAR_PRESSURE"] for row in rows} == {"0.0012418"}
        assert {row["CDI_NEAR_VORTICITY"] for row in rows} == {"NA"}


_RFIXF_PLANE_LIFT___RHO, _RFIXF_PLANE_LIFT___SPEED, _RFIXF_PLANE_LIFT___SREF = (
    _rfixf_plane_lift__ffpost._FFPROOF_POST___RHO,
    68.058,
    50.0,
)


_RFIXF_PLANE_LIFT___CL = 0.1882829  # the loads fixture's total CL


_RFIXF_PLANE_LIFT___ALPHA = math.radians(-2.0)


_RFIXF_PLANE_LIFT___DIRECTION = (
    math.cos(_RFIXF_PLANE_LIFT___ALPHA),
    0.0,
    math.sin(_RFIXF_PLANE_LIFT___ALPHA),
)


_RFIXF_PLANE_LIFT___PLANE = farfield_plane(
    (30.0, 0.0, 0.0),
    direction=_RFIXF_PLANE_LIFT___DIRECTION,
    distance=0.0,
    half_width=10.0,
    half_height=5.0,
    spacing=0.25,
)


_RFIXF_PLANE_LIFT___LAYOUT = {
    "shapes": [
        {
            "kind": "plane",
            "source": "added",
            "entry": None,
            "count": len(_RFIXF_PLANE_LIFT___PLANE.points),
            "center_m": [30.0, 0.0, 0.0],
            "direction": list(_RFIXF_PLANE_LIFT___DIRECTION),
            "half_width_m": 10.0,
            "half_height_m": 5.0,
            "spacing_m": 0.25,
        }
    ]
}


_RFIXF_PLANE_LIFT___TABLE = (
    "[[farfields]]\n"
    'variant = "plane"\n'
    "half_width_bref = 0.5\n"
    "half_height_bref = 0.25\n"
    "spacing_bref = 0.0125\n"
)


_RFIXF_PLANE_LIFT___SPAN = 6.0  # half the distance between the two vortices, m


_RFIXF_PLANE_LIFT___CORE = 0.6  # Lamb-Oseen core radius, m


def _rfixf_plane_lift___gamma() -> float:
    """The circulation whose pair lifts the fixture's CL: L = rho V Gamma 2 s."""
    lift = (
        _RFIXF_PLANE_LIFT___CL
        * 0.5
        * _RFIXF_PLANE_LIFT___RHO
        * _RFIXF_PLANE_LIFT___SPEED**2
        * _RFIXF_PLANE_LIFT___SREF
    )
    return lift / (
        _RFIXF_PLANE_LIFT___RHO * _RFIXF_PLANE_LIFT___SPEED * 2.0 * _RFIXF_PLANE_LIFT___SPAN
    )


def _rfixf_plane_lift___crossflow(scale: float) -> np.ndarray:
    """Velocities at the plane's points: the free stream plus the pair's crossflow, times scale."""
    yy, zz = np.meshgrid(_RFIXF_PLANE_LIFT___PLANE.y, _RFIXF_PLANE_LIFT___PLANE.z, indexing="ij")
    v = np.zeros_like(yy)
    w = np.zeros_like(yy)
    for y0, gamma in (
        (_RFIXF_PLANE_LIFT___SPAN, _rfixf_plane_lift___gamma()),
        (-_RFIXF_PLANE_LIFT___SPAN, -_rfixf_plane_lift___gamma()),
    ):
        dy, dz = yy - y0, zz
        r2 = dy * dy + dz * dz
        safe = np.where(r2 > 0.0, r2, 1.0)
        # (1 - exp(-r^2 / c^2)) / r^2, whose limit on the axis is 1 / c^2
        shape = np.where(
            r2 > 0.0,
            (1.0 - np.exp(-r2 / _RFIXF_PLANE_LIFT___CORE**2)) / safe,
            1.0 / _RFIXF_PLANE_LIFT___CORE**2,
        )
        swirl = gamma / (2.0 * math.pi) * shape
        v += -swirl * dz
        w += swirl * dy
    cross = scale * (
        v.ravel()[:, None] * _RFIXF_PLANE_LIFT___PLANE.axes[1]
        + w.ravel()[:, None] * _RFIXF_PLANE_LIFT___PLANE.axes[2]
    )
    return np.asarray(_RFIXF_PLANE_LIFT___DIRECTION) * _RFIXF_PLANE_LIFT___SPEED + cross


def _rfixf_plane_lift___post(
    tmp_path: Path, scale: float, *, near_cl: float = _RFIXF_PLANE_LIFT___CL
) -> tuple[dict[str, str], list[str]]:
    workspace = _rfixf_plane_lift__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=_RFIXF_PLANE_LIFT___TABLE,
        files={
            f"{_FFPROOF_POST___STEM}.txt": _FFPROOF_POST__LOADS.replace(
                "+0.1882829", f"{near_cl:+.7f}"
            ),
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_layout___export(
                _RFIXF_PLANE_LIFT___PLANE.points, _rfixf_plane_lift___crossflow(scale)
            ),
        },
    )
    _rfixf_plane_lift__ffpost._ffproof_post___set_record(
        workspace, farfield_layout=_RFIXF_PLANE_LIFT___LAYOUT
    )
    _rfixf_plane_lift__ffpost._ffproof_post___post(workspace)
    root = Path(workspace.root)
    (row,) = [
        r for r in _rfixf_layout___rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"
    ]
    flags = [
        line
        for line in _rfixf_plane_lift__ffpost._ffproof_post___warnings_of(root)
        if "carries a lift of its own" in line
    ]
    return row, flags


class TestRfixFPlaneLift:
    """P0400-RFIXF-PLANELIFT: the Trefftz C plane states its own lift, and is flagged short of it.

    PFS-2081.95: a plane whose probe field does not hold the circulation the
    loads shed gives a crossflow energy that is not their induced drag (RPT-171:
    one build's probe field carried 0.74 of a wing's lift). The C row now states
    ``CL_T``, the Kutta-Joukowski lift of the plane's own streamwise vorticity
    (FR-1038), and post warns where it departs from the solver's CL by more
    than 10 percent. Synthetic: a pair of Lamb-Oseen vortices of known
    circulation behind the loads fixture's wing.
    """

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_rfixf_the_plane_states_the_lift_of_its_vorticity(tmp_path):
        """P0400-RFIXF-PLANELIFT (FR-1038): CL_T of C is rho V Gamma 2 s, and no flag.

        Before the fix the C row's CL_T was NA, so a plane holding a fraction of
        the shed circulation could not be told from one holding all of it.
        """
        row, flags = _rfixf_plane_lift___post(tmp_path, 1.0)
        assert float(row["CL_T"]) == pytest.approx(_RFIXF_PLANE_LIFT___CL, rel=0.02)
        assert not flags

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_rfixf_a_plane_short_of_the_lift_is_flagged(tmp_path):
        """P0400-RFIXF-PLANELIFT (FR-1038, PFS-2081.95): 0.74 of the circulation is flagged.

        The field of one build's probes on a wing carried 0.74 of the lift
        (RPT-171). The row is written, its CL_T says 0.74 CL, and post.log names
        the point, both values and the ratio.
        """
        row, flags = _rfixf_plane_lift___post(tmp_path, 0.74)
        assert float(row["CL_T"]) == pytest.approx(0.74 * _RFIXF_PLANE_LIFT___CL, rel=0.02)
        assert float(row["CDI_T"]) > 0.0, "the row is written"
        (flag,) = flags
        assert "0.74" in flag and "RPT-171" in flag


_RFIXF_QSTEADY___SHAPE = {"rotor": "ROTOR", "stations": [-1.0, 1.0], "n_r": 2, "n_psi": 16}


_RFIXF_QSTEADY___LEDGERS = (
    "[[farfields]]\n"
    'variant = "power"\n'
    'balances = ["mass", "axial", "transverse", "torque", "in_plane_mo'
    'ment", "crossflow_energy"]\n'
    'rotor = "ROTOR"\n'
    "stations = [-1.0, 1.0]\n"
    "n_r = 2\n"
    "n_psi = 16\n"
    "m_max = 2\n"
)


_RFIXF_QSTEADY___HUB = np.array([0.5, 0.0, 0.0])


_RFIXF_QSTEADY___LATTICE = LatticeShape.model_validate(_RFIXF_QSTEADY___SHAPE).build(1.0)


_RFIXF_QSTEADY___POINTS = lattice_points(_RFIXF_QSTEADY___LATTICE, axis="X") + _RFIXF_QSTEADY___HUB


def _rfixf_qsteady___quasi(rpm: float) -> str:
    """The quasi-steady record of the row, its speed signed by the rotor's hand."""
    return QsteadyRecord(
        case="wheel",
        rotor_alias="ROTOR",
        blades=2,
        rpm=rpm,
        shaft_frame_axis="X",
        hub_m=(0.5, 0.0, 0.0),
        axis_vector=(1.0, 0.0, 0.0),
        diameter_m=2.0,
        families_general=(),
        families_blades=("B1", "B2"),
        blade1_azimuth_deg=0.0,
        positions=(QsteadyClocking(0, 0.0, 0.0, f"{_FFPROOF_POST___STEM}.txt"),),
        validity=None,
    ).to_text()


def _rfixf_qsteady___ledgers(tmp_path: Path, rpm: float) -> list[dict[str, str]]:
    """Post a qsteady point whose probes read a 12 m/s still stream in the turning frame."""
    omega = np.array([1.0, 0.0, 0.0]) * 2.0 * math.pi * rpm / 60.0
    turning = np.tile([12.0, 0.0, 0.0], (len(_RFIXF_QSTEADY___POINTS), 1)) - np.cross(
        omega, _RFIXF_QSTEADY___POINTS - _RFIXF_QSTEADY___HUB
    )
    workspace = _rfixf_qsteady__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=_RFIXF_QSTEADY___LEDGERS,
        recipe="qsteady_rotor",
        files={
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_layout___export(
                _RFIXF_QSTEADY___POINTS, turning
            ),
            f"{_FFPROOF_POST___STEM}_qsteady.json": _rfixf_qsteady___quasi(rpm),
        },
    )
    shape = {
        "kind": "lattice",
        "source": "added",
        "entry": None,
        "count": len(_RFIXF_QSTEADY___POINTS),
        "lattice": _RFIXF_QSTEADY___LATTICE.model_dump(mode="json"),
        "axis": "X",
        "origin_m": list(_RFIXF_QSTEADY___HUB),
        "positions_frame": "REFERENCE",
    }
    _rfixf_qsteady__ffpost._ffproof_post___set_record(
        workspace, farfield_layout={"shapes": [shape]}
    )
    _rfixf_qsteady__ffpost._ffproof_post___post(workspace)
    return _rfixf_layout___rows(Path(workspace.root), "farfield/*_ledgers.csv")


class TestRfixFQsteady:
    """P0400-RFIXF-QSTEADY: the quasi-steady rotor's far field reads the row's own speed (PFS-2081.93).

    A ``qsteady_rotor`` run plans no reductions, so its record states no rotor
    speed; the builder writes the row's speed, signed by the rotor's hand, in the
    quasi-steady record beside the loads export, which every other product reads.
    The far-field balances read it there too, and turn the probes to the hub frame
    by that signed speed alone. Synthetic: a still stream of 12 m/s sampled in the
    frame that turns with the blades.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.requirement("FR-453")
    @pytest.mark.requirement("FR-38")
    @pytest.mark.parametrize("rpm", [600.0, -600.0], ids=["right-hand", "left-hand"])
    def test_p0400_rfixf_the_qsteady_balances_read_the_rows_own_speed(tmp_path, rpm):
        """P0400-RFIXF-QSTEADY (FR-1037, PFS-2081.93): the ledgers are written, swirl-free.

        Before the fix the far field asked the record's plan for the speed, which a
        quasi-steady run never writes, and skipped the point ("states no speed").
        Converted by the row's own signed speed, the still stream has no swirl:
        torque flux and crossflow energy zero at every station, mass flow
        ``rho V A``. A left-handed rotor, whose recorded speed is negative, is
        converted by that sign once; the hand applied a second time would leave a
        swirl of twice the frame's.
        """
        rows = _rfixf_qsteady___ledgers(tmp_path, rpm)
        assert [float(row["STATION_X_R"]) for row in rows] == [-1.0, 1.0]
        edges = _RFIXF_QSTEADY___LATTICE.ring_edges
        area = math.pi * (edges[-1] ** 2 - edges[0] ** 2)
        for row in rows:
            assert float(row["MDOT_KG_S"]) == pytest.approx(
                _rfixf_qsteady__ffpost._FFPROOF_POST___RHO * 12.0 * area, rel=1e-5
            )
            assert float(row["TORQUE_NM"]) == pytest.approx(0.0, abs=0.1)  # printed digits
            assert float(row["E_TOTAL_W"]) == pytest.approx(0.0, abs=1.0)


class TestRfixFStatus:
    """P0400-RFIXF-STATUS: every far-field row carries the point's solver status (PFS-2081.97).

    A point that stopped at its iteration limit wrote far-field rows that said
    nothing of it; its status was only in the sweep table and the run record.
    Every row of the Trefftz table, the spanwise files and the ledgers now ends
    with ``STATUS``, the token the sweep table writes, so a row of a point that is
    not converged is marked as the near-field products mark it.
    """

    @staticmethod
    @pytest.mark.requirement("FR-456")
    @pytest.mark.parametrize("status", ["MAX_ITER_REACHED", "CONVERGED"])
    def test_p0400_rfixf_every_trefftz_row_carries_the_status(tmp_path, status):
        """P0400-RFIXF-STATUS (FR-1061): A, B and C rows and the spanwise files say the status."""  # noqa: E501
        workspace = _rfixf_status__wing._farfield_products___workspace(tmp_path, farfield=True)
        extra = {"iterations": 1500, "iterations_requested": 1500} if status != "CONVERGED" else {}
        _rfixf_status__ffpost._ffproof_post___set_record(workspace, status=status, **extra)
        _rfixf_status__ffpost._ffproof_post___post(workspace)
        root = Path(workspace.root)
        rows = _rfixf_layout___rows(root, "farfield/*_trefftz.csv")
        assert {row["VARIANT"] for row in rows} == {"A", "B", "C"}
        assert {row["STATUS"] for row in rows} == {status}
        spanwise = sorted(root.rglob("sections/*_trefftz_*.csv"))
        assert spanwise
        for path in spanwise:
            assert {row["STATUS"] for row in _rfixf_layout___rows(path.parent, path.name)} == {
                status
            }

    @staticmethod
    @pytest.mark.requirement("FR-456")
    def test_p0400_rfixf_every_ledger_row_carries_the_status(tmp_path):
        """P0400-RFIXF-STATUS (FR-1061): the ledgers of a point at its iteration limit say so."""
        workspace = _rfixf_status__ffpost._ffproof_post___campaign(
            tmp_path,
            pproc=_rfixf_status__ffpost._FFPROOF_POST___LEDGERS,
            files={
                f"{_rfixf_status__ffpost._FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_status__ffpost._ffproof_post___probe_export(  # noqa: E501
                    _rfixf_status__ffpost._FFPROOF_POST___POINTS_M, 20.0
                )
            },
        )
        _rfixf_status__ffpost._ffproof_post___set_record(
            workspace, status="MAX_ITER_REACHED", iterations=900, iterations_requested=900
        )
        _rfixf_status__ffpost._ffproof_post___post(workspace)
        rows = _rfixf_layout___rows(Path(workspace.root), "farfield/*_ledgers.csv")
        assert len(rows) == 2 and {row["STATUS"] for row in rows} == {"MAX_ITER_REACHED"}


_RFIXF_TRACED_LIFT___STEM = "POLAR-3207_M20AL-020BE+000"


def _rfixf_traced_lift___post(
    tmp_path: Path, total_cl: str | None
) -> tuple[list[dict[str, str]], list[str]]:
    """Post the wing fixture; ``total_cl`` replaces the loads export's total CL."""
    workspace = _rfixf_traced_lift__wing._farfield_products___workspace(tmp_path, farfield=True)
    if total_cl is not None:
        loads = workspace.sim_dir("3207") / "outputs" / f"{_RFIXF_TRACED_LIFT___STEM}.txt"
        text = loads.read_text(encoding="utf-8")
        assert text.count("+0.1882829") == 1
        loads.write_text(text.replace("+0.1882829", total_cl), encoding="utf-8")
    _rfixf_traced_lift__ffpost._ffproof_post___post(workspace)
    root = Path(workspace.root)
    rows = [r for r in _rfixf_layout___rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "A"]
    said = [
        line
        for line in _rfixf_traced_lift__ffpost._ffproof_post___warnings_of(root)
        if "Trefftz A traces" in line
    ]
    return rows, said


class TestRfixFTracedLift:
    """P0400-RFIXF-TRACEDLIFT: Trefftz A says so when its families do not carry the lift (PFS-2081.96).

    A trace over a subset of the lifting surfaces (a wing selected without its
    body) holds those surfaces' lift alone, and its span efficiency is theirs: a
    wing-body traced over the wing gave e = 0.25 with no warning. Post now writes a
    WARNING naming the families, both lifts and their ratio where the traced lift
    departs from the solver's CL by more than 5 percent (FR-1021).
    """  # noqa: E501

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_rfixf_a_trace_short_of_the_configurations_lift_is_warned(tmp_path):
        """P0400-RFIXF-TRACEDLIFT (FR-1021): the traced wing carries 0.75 of the solver's CL.

        The configuration's CL is raised to 0.2510 (a body lifting the rest); the
        traced wing still lifts 0.1883. The A rows are written and post.log names
        the family, both values and the ratio. Before the fix nothing was said.
        """
        rows, said = _rfixf_traced_lift___post(tmp_path, "+0.2510439")
        assert rows and float(rows[-1]["CL_T"]) == pytest.approx(0.1883, rel=3e-3)
        (line,) = said
        assert "W" in line and "0.75" in line and "0.251" in line and "FR-1021" in line

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_rfixf_a_trace_carrying_the_lift_is_not_warned(tmp_path):
        """P0400-RFIXF-TRACEDLIFT (FR-1021): the wing traced alone, at its own CL, is silent."""
        rows, said = _rfixf_traced_lift___post(tmp_path, None)
        assert rows and not said


def test_p0430_f3_an_empty_plane_selection_is_the_documented_refusal():
    """F-1383: no selected probe raises PyflightstreamError, not IndexError."""
    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.post.farfield_fields import ProbeSamples, plane_values

    samples = ProbeSamples(np.zeros((4, 3)), np.zeros((4, 3)), np.zeros(4), ("REFERENCE",) * 4)
    with pytest.raises(PyflightstreamError, match="no probe"):
        plane_values(
            samples,
            slice(0, 0),
            flow=(1.2, 30.0, 0.0, 0.0),
            grid=(1.0, 1.0, 0.5),
            per_m=1.0,
            q_ref=100.0,
        )


def test_p0430_f3_the_matching_tolerance_is_one_unit_of_the_last_printed_digit():
    """F-142: a coordinate just below a power of ten is not given ten units of slack."""
    from pyflightstream.post.farfield_fields import coordinate_tolerance

    tolerance = coordinate_tolerance(np.array([9.99, 10.01, 0.0]), 7)
    assert tolerance[0] == pytest.approx(1e-6 + 1e-5)
    assert tolerance[1] == pytest.approx(1e-5 + 1e-5)
    assert tolerance[2] == pytest.approx(1e-5)


def test_p0430_f3_a_number_mixed_with_na_averages_to_na():
    """F-182: a step that could not state a value makes the average NA, not the first value."""
    from pyflightstream.post.farfield_fields import average_rows

    first = [("POL", "1", 2.0, "label")]
    second = [("POL", "2", "NA", "label")]
    (row,) = average_rows([first, second], 2)
    assert row[:2] == ("POL", "AVERAGE") and row[2] == "NA" and row[3] == "label"


def _p0450_probe_series(points):
    """Independent uniform-flow exports: velocity at step n is 10 + n m/s."""
    name = f"{_FFPROOF_POST___STEM}_farfield_survey"
    return {
        f"{name}.txt": _ffproof_post___probe_export(points, 18.0),
        **{
            f"{name}_iteration={step}.txt": _ffproof_post___probe_export(points, 10.0 + step)
            for step in range(1, 9)
        },
    }


@pytest.mark.parametrize("policy", ["default", "last_step"])
@pytest.mark.parametrize("variant", ["sections", "plane", "power"])
@pytest.mark.requirement("FR-1052")
def test_p0450_d8_last_step_products_and_manifest(tmp_path, policy, variant):
    """P0450-D8: even with history present, last-step policies write only the instant."""
    if variant == "sections":
        workspace = _farfield_products___workspace(tmp_path, farfield=True)
        table = '[[farfields]]\nvariant = "sections"\nfamilies = ["W"]\n'
        _ffproof_post___set_record(
            workspace, recipe="unsteady_rotor", reductions=_FFPROOF_POST___WINDOW
        )
        source = next(workspace.sim_dir("3207").rglob("*_sloads.txt"))
        for step in range(5, 9):
            source.with_name(f"{source.stem}_iteration={step}.txt").write_bytes(source.read_bytes())
    elif variant == "plane":
        workspace = _p0450_plane_series(tmp_path)
        table = _RFIXF_LAYOUT___TABLE_1M
    else:
        table = _FFPROOF_POST___LEDGERS
        workspace = _ffproof_post___campaign(
            tmp_path,
            pproc=table,
            files=_p0450_probe_series(_FFPROOF_POST___POINTS_M),
            recipe="unsteady_rotor",
            reductions=_FFPROOF_POST___WINDOW,
        )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        table + f'export_type = "{policy}"\n', encoding="utf-8"
    )
    _ffproof_post___post(workspace)
    root = Path(workspace.root)
    assert _rfixf_layout___rows(root, "farfield/*_trefftz_instant.csv")
    assert not _rfixf_layout___rows(root, "farfield/*_trefftz_average.csv")
    manifest = _ffproof_post___manifest(root)
    entry = _ffproof_post___entry(manifest, "_trefftz_instant.csv")
    assert entry["entries"][variant]["export_type"] == policy
    assert any(
        "export_type" in reason and policy in reason for reason in manifest["skipped"].values()
    )


# ----------------------------------------------------------------- P0470-FFR option 1a
_P0470_FFR_LEDGERS = (
    "[[farfields]]\n"
    'variant = "power"\n'
    'rotor = "R"\n'
    'balances = ["mass", "axial"]\n'
    "stations = [-2.0, 0.0, 0.25, 2.0, 4.0]\n"
    "n_r = 60\n"
    "r_inner = 0.02\n"
    "r_outer = 2.0\n"
    "n_psi = 16\n"
    "m_max = 2\n"
)


def _p0470_ffr_probe_export(points: np.ndarray, u: np.ndarray, cp_ref: np.ndarray) -> str:
    """A steady probe-points export of ``points`` (m) with axial ``u`` and ``Cp_ref`` each."""
    rows = "".join(
        "     "
        + ", ".join(f"{v: .9E}" for v in (*p, 0.1, c, s, 0.0, 0.0, s, 0.0))
        + ", 0.0000E+00" * 6
        + ",\n"
        for p, s, c in zip(points, u, cp_ref, strict=True)
    )
    parts = _ffproof_post___probe_export(points, 1.0).split(_FFPROOF_POST___RULE)
    parts[-2] = rows
    return _FFPROOF_POST___RULE.join(parts)


def _p0470_ffr_sloads(radius: np.ndarray, axial: np.ndarray) -> str:
    """One blade's sectional loads cut in planes XZ of its frame: offsets along Y."""
    head = _FFPROOF_POST__LOADS.split("     Surface,")[0].replace(
        "Aerodynamic loads", "Surface Sectional Loads"
    )
    rows = "".join(
        f"     {r: .9E}, 0.2000E-01, 0.0000E+00, 0.0000E+00, {f: .9E}, 0.0000E+00, 0.0000E+00,\n"
        for r, f in zip(radius, axial, strict=True)
    )
    return (
        head.rsplit(_FFPROOF_POST___RULE, 1)[0]
        + f"     Number of Surface Sections:                 {len(radius)}\n"
        + _FFPROOF_POST___RULE
        + "     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n"
        + rows
        + _FFPROOF_POST___RULE
        + "     Force Units: Newtons\n     Moment Units: Newton-Meter\n"
        + "     Software : Flightstream\n"
    )


@pytest.mark.requirement("FR-38")
@pytest.mark.parametrize("loads", [True, False])
def test_p0470_ffr_rotor_g4_reads_the_corrected_pressure(tmp_path, loads):
    """P0470-FFR 1a: a rotor row with blade loads closes its axial balance and keeps G4."""
    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_ffr_actuator

    rho, speed, blades = _FFPROOF_POST___RHO, 68.058, 2
    shape = LatticeShape.model_validate(
        {
            "frame": "MRP",
            "tip_radius_m": 1.0,
            "stations": [-2.0, 0.0, 0.25, 2.0, 4.0],
            "n_r": 60,
            "r_inner": 0.02,
            "r_outer": 2.0,
            "n_psi": 16,
        }
    )
    lattice = shape.build(1.0)
    fields, loading, thrust, _added = _p0470_ffr_actuator(v=speed, rho=rho, lattice=lattice)
    points = lattice_points(lattice, axis="X")
    # The synthetic field on the lattice's own sampling order: planes, then lateral rings.
    planes = fields["u"].reshape(-1)
    u = np.concatenate([planes, np.full(len(points) - len(planes), speed)])
    p_prime = -0.5 * rho * (u * u - speed * speed)
    q_ref = 0.5 * rho * speed * speed
    files = {
        f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _p0470_ffr_probe_export(
            points, u, p_prime / q_ref
        )
    }
    layout: list[dict[str, object]] = []
    if loads:
        files[f"{_FFPROOF_POST___STEM}_sloads.txt"] = _p0470_ffr_sloads(
            loading.radius_m, -loading.thrust_per_m / blades
        )
        layout = [
            {
                "distribution": 1,
                "distribution_families": ["Blade1"],
                "families": ["Blade1"],
                "plane": "XZ",
                "frame": "R_RMRP1",
                "count": len(loading.radius_m),
            }
        ]
    workspace = _ffproof_post___campaign(
        tmp_path,
        pproc=_P0470_FFR_LEDGERS,
        files=files,
        reductions={"rotors": {"R": {"rpm": 2000.0, "blades": blades}}},
    )
    _ffproof_post___set_record(
        workspace,
        sections_layout=layout or None,
        farfield_layout={
            "shapes": [
                {
                    "kind": "lattice",
                    "source": "added",
                    "entry": None,
                    "count": len(points),
                    "axis": "X",
                    "origin_m": [0.0, 0.0, 0.0],
                    "positions_frame": "REFERENCE",
                    "lattice": lattice.model_dump(mode="json"),
                }
            ]
        },
    )
    _ffproof_post___post(workspace)
    columns, rows = _ffproof_post___table(
        _ffproof_post___one(workspace.root, "farfield/*_ledgers.csv")
    )
    skips = _ffproof_post___manifest(workspace.root)["skipped"]
    named = [reason for key, reason in skips.items() if "SPURIOUS_COUNTS" in key]
    if not loads:
        # Without the blade loads the 0.46.0 table and its named skip stay.
        assert columns == ["POL", "ENTRY", "STEP", *CONTEXT_COLUMNS, *LEDGER_COLUMNS]
        assert all(row["SPURIOUS_COUNTS"] == "NA" for row in rows)
        assert named and "no disk total-pressure jump" in named[0]
        return
    assert "FX_CORRECTED_N" in columns, columns
    assert columns[-1] == "STATUS"
    assert not named
    by_station = {float(row["STATION_X_R"]): row for row in rows}
    assert by_station[0.0]["FX_CORRECTED_N"] == "NA"
    for station in (2.0, 4.0):
        row = by_station[station]
        assert float(row["FX_CORRECTED_N"]) == pytest.approx(thrust, rel=5e-3)
        assert abs(float(row["FX_N"]) - thrust) > 0.2 * thrust
        assert float(row["P_PRIME_CORRECTION_N"]) > 0.0
    near = float(rows[-1]["F_NEAR_N"])
    far = float(rows[-1]["FX_CORRECTED_N"])
    expected = 2.0 * (near - far) / (rho * speed * speed * 50.0) * 1e4
    assert float(rows[-1]["SPURIOUS_COUNTS"]) == pytest.approx(expected, rel=1e-6)


_P0470_FFR_Q___RPM = 60.0


def _p0470_ffr_q___turning(rpm: float) -> np.ndarray:
    """The vortex-pair plane of the plane-lift fixture, sampled in a frame turning about X."""
    omega = np.array([1.0, 0.0, 0.0]) * 2.0 * math.pi * rpm / 60.0
    points = _RFIXF_PLANE_LIFT___PLANE.points
    return _rfixf_plane_lift___crossflow(1.0) - np.cross(omega, points - _RFIXF_QSTEADY___HUB)


def _p0470_ffr_q___post(tmp_path: Path, rpm: float) -> tuple[dict[str, str], Path]:
    """Post a qsteady_rotor point whose C plane reads the turning frame."""
    workspace = _rfixf_plane_lift__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=_RFIXF_PLANE_LIFT___TABLE,
        recipe="qsteady_rotor",
        files={
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_layout___export(
                _RFIXF_PLANE_LIFT___PLANE.points, _p0470_ffr_q___turning(rpm)
            ),
            f"{_FFPROOF_POST___STEM}_qsteady.json": _rfixf_qsteady___quasi(rpm),
        },
    )
    _rfixf_plane_lift__ffpost._ffproof_post___set_record(
        workspace, farfield_layout=_RFIXF_PLANE_LIFT___LAYOUT
    )
    _rfixf_plane_lift__ffpost._ffproof_post___post(workspace)
    root = Path(workspace.root)
    rows = [r for r in _rfixf_layout___rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"]
    assert len(rows) == 1, rows
    return rows[0], root


@pytest.mark.requirement("FR-1037")
@pytest.mark.parametrize("rpm", [_P0470_FFR_Q___RPM, -_P0470_FFR_Q___RPM], ids=["right", "left"])
def test_p0470_ffr_qsteady_plane_reads_the_hub_frame(tmp_path, rpm):
    """P0470-FFR-Q3: a qsteady_rotor C plane is converted to the hub frame before Munk.

    The plane samples a vortex pair whose crossflow energy and lift are known, read
    in the frame that turns with the blades. Converted as D converts its lattice
    (v_hub = v + Omega x (x - x_hub), the row's signed speed), the C row returns the
    pair's own CDI_T and CL_T, those of the same field posted on a steady row; read
    as sampled, the frame's swirl would dominate the crossflow energy.
    """
    expected, _ = _rfixf_plane_lift___post(tmp_path / "steady", 1.0)
    row, _root = _p0470_ffr_q___post(tmp_path / "qsteady", rpm)
    assert float(row["CDI_T"]) == pytest.approx(float(expected["CDI_T"]), rel=1e-3)
    assert float(row["CL_T"]) == pytest.approx(float(expected["CL_T"]), rel=1e-3)
    assert float(row["CDI_T_VORT"]) == pytest.approx(float(expected["CDI_T_VORT"]), rel=1e-3)
    sampled = _rfixf_layout___export(_RFIXF_PLANE_LIFT___PLANE.points, _p0470_ffr_q___turning(rpm))
    from pyflightstream.post.farfield_fields import steady_samples

    raw = plane_values(
        steady_samples(sampled),
        slice(None),
        flow=(_RFIXF_PLANE_LIFT___RHO, _RFIXF_PLANE_LIFT___SPEED, -2.0, 0.0),
        grid=(10.0, 5.0, 0.25),
        per_m=1.0,
        q_ref=0.5 * _RFIXF_PLANE_LIFT___RHO * _RFIXF_PLANE_LIFT___SPEED**2,
    )
    q_s = 0.5 * _RFIXF_PLANE_LIFT___RHO * _RFIXF_PLANE_LIFT___SPEED**2 * _RFIXF_PLANE_LIFT___SREF
    assert raw["D"] / q_s > 2.0 * float(expected["CDI_T"])


@pytest.mark.requirement("FR-1059")
def test_p0470_ffr_qsteady_sections_and_wake_are_named_skips(tmp_path):
    """P0470-FFR-Q2: post names A and B as skips on a qsteady_rotor row and writes its C row."""
    workspace = _rfixf_plane_lift__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=(
            "[[farfields]]\n"
            'name = "wing"\n'
            'variant = "sections"\n'
            'families = ["Wing"]\n'
            "[[farfields]]\n"
            'name = "wake"\n'
            'variant = "wake"\n' + _RFIXF_PLANE_LIFT___TABLE
        ),
        recipe="qsteady_rotor",
        files={
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_layout___export(
                _RFIXF_PLANE_LIFT___PLANE.points, _p0470_ffr_q___turning(_P0470_FFR_Q___RPM)
            ),
            f"{_FFPROOF_POST___STEM}_qsteady.json": _rfixf_qsteady___quasi(_P0470_FFR_Q___RPM),
        },
    )
    _rfixf_plane_lift__ffpost._ffproof_post___set_record(
        workspace, farfield_layout=_RFIXF_PLANE_LIFT___LAYOUT
    )
    _rfixf_plane_lift__ffpost._ffproof_post___post(workspace)
    root = Path(workspace.root)
    skipped = str(_ffproof_post___manifest(root)["skipped"])
    assert "trefftz:sections does not apply" in skipped and "Trefftz A" in skipped
    assert "trefftz:wake does not apply" in skipped and "Trefftz B" in skipped
    rows = _rfixf_layout___rows(root, "farfield/*_trefftz.csv")
    assert [row["VARIANT"] for row in rows] == ["C"]


@pytest.mark.requirement("FR-1037")
def test_p0470_ffr_qsteady_wheel_plane_names_its_one_clocking(tmp_path):
    """P0470-FFR-Q3: a wheel solved at several clockings says its C row is clocking 0's.

    The plane is laid and exported with the point's full export set, at clocking 0
    alone; the clocking average is not formed, so post writes the row and names
    the limitation as a skip, never presenting one clocking as the average.
    """
    quasi = QsteadyRecord(
        case="wheel",
        rotor_alias="ROTOR",
        blades=2,
        rpm=_P0470_FFR_Q___RPM,
        shaft_frame_axis="X",
        hub_m=(0.5, 0.0, 0.0),
        axis_vector=(1.0, 0.0, 0.0),
        diameter_m=2.0,
        families_general=(),
        families_blades=("B1", "B2"),
        blade1_azimuth_deg=0.0,
        positions=(
            QsteadyClocking(0, 0.0, 0.0, f"{_FFPROOF_POST___STEM}.txt"),
            QsteadyClocking(1, 90.0, 90.0, f"{_FFPROOF_POST___STEM}_qs01.txt"),
        ),
        validity=None,
    ).to_text()
    workspace = _rfixf_plane_lift__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=_RFIXF_PLANE_LIFT___TABLE,
        recipe="qsteady_rotor",
        files={
            f"{_FFPROOF_POST___STEM}_farfield_survey.txt": _rfixf_layout___export(
                _RFIXF_PLANE_LIFT___PLANE.points, _p0470_ffr_q___turning(_P0470_FFR_Q___RPM)
            ),
            f"{_FFPROOF_POST___STEM}_qsteady.json": quasi,
        },
    )
    _rfixf_plane_lift__ffpost._ffproof_post___set_record(
        workspace, farfield_layout=_RFIXF_PLANE_LIFT___LAYOUT
    )
    _rfixf_plane_lift__ffpost._ffproof_post___post(workspace)
    root = Path(workspace.root)
    skipped = str(_ffproof_post___manifest(root)["skipped"])
    assert "clocking 0" in skipped and "2 clockings" in skipped
    rows = _rfixf_layout___rows(root, "farfield/*_trefftz.csv")
    assert [row["VARIANT"] for row in rows] == ["C"]


def _p0470_wake_vtk(lines: list[np.ndarray], values: np.ndarray) -> str:
    """A wake export of chained two-point segments, one constant value per line."""
    points: list[tuple[float, ...]] = []
    segments: list[tuple[int, int]] = []
    cells: list[float] = []
    for line, value in zip(lines, values, strict=True):
        start = len(points)
        points += [tuple(node) for node in line]
        segments += [(start + k, start + k + 1) for k in range(len(line) - 1)]
        cells += [value] * (len(line) - 1)
    return (
        "# vtk DataFile Version 3.0\nwake\nASCII\nDATASET POLYDATA\n"
        + f"POINTS {len(points)} float\n"
        + "".join(f"{x:.9f} {y:.9f} {z:.9f}\n" for x, y, z in points)
        + f"LINES {len(segments)} {3 * len(segments)}\n"
        + "".join(f"2 {a} {b}\n" for a, b in segments)
        + f"CELL_DATA {len(segments)}\nSCALARS Normalized_Vorticity float 1\n"
        + "LOOKUP_TABLE default\n"
        + "".join(f"{v:.9f}\n" for v in cells)
    )


def _p0470_wing_lines() -> tuple[list[np.ndarray], np.ndarray]:
    nodes = np.linspace(-2.0, 2.0, 17)
    centres = 0.5 * (nodes[:-1] + nodes[1:])
    gamma = np.sqrt(1.0 - (centres / 2.0) ** 2)
    shed = -np.diff(np.concatenate([[0.0], gamma, [0.0]]))
    lines = [np.array([(1.0, y, 0.0), (15.0, y, 0.0), (30.0, y, 0.0)]) for y in nodes]
    return lines, shed


def _p0470_post_rotor_wake(root: Path, lines, values, *, rotor: bool):
    """Post one steady point through the public far-field stage, a rotor row or a wing row."""
    from pyflightstream.cases.reference_blocks import BladeDatum, RotorBlock

    root.mkdir(exist_ok=True)
    (root / "point_wakes.vtk").write_text(_p0470_wake_vtk(lines, values), encoding="utf-8")
    (root / "point.fsm").write_text("$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n", "utf-8")
    loads = replace(
        parse_loads(_LITB_POST__LOADS), freestream_velocity_m_s=30.0, angle_of_attack_deg=0.0
    )
    loads.total["CL"] = 0.3
    point = SimpleNamespace(
        name="point",
        loads=loads,
        state=SimpleNamespace(density_kg_m3=1.225),
        vorticity_selection=None,
    )
    block = RotorBlock(
        alias="ROTOR",
        x_m=3.0,
        y_m=0.0,
        z_m=2.0,
        axis="X",
        rpm_sign=1,
        diameter_m=2.0,
        families_general=[],
        families_blades=["Blade1", "Blade2"],
        blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
    )
    products: dict = {}

    def target(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    ctx = SimpleNamespace(
        pproc=PprocSpec.model_validate({"farfields": [{"variant": "wake"}]}),
        workspace=SimpleNamespace(sim_dir=lambda sim: root),
        record_of={
            "point": SimpleNamespace(
                outputs=["point.vtk", "point.fsm"],
                package_version="0.47.0",
                recipe="steady",
                reductions={"rotors": {"ROTOR": {"rpm": 1000.0, "blades": 2}}},
            )
        },
        sim_id="1",
        points=[point],
        reference=ReferenceValues(4.0, 1.0, 4.0),
        matrix_row=SimpleNamespace(variables={"RPM": "1000"} if rotor else {}),
        live=SimpleNamespace(rotors={"ROTOR": block} if rotor else {}),
        sources={"point": ["recorded"]},
        skipped={},
        out=root / "post",
        table_name="point",
        condition=lambda point: {},
        target=target,
        add=lambda path, entry: products.update({str(path): entry}),
        farfield_super={},
    )
    farfield_products(cast("Any", ctx))
    (path,) = list((root / "post" / "farfield").glob("*_trefftz.csv"))
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader), ctx


@pytest.mark.requirement("FR-452")
def test_p0470_ffr_a_rotor_row_writes_the_wake_loads_of_its_rotor(tmp_path):
    """P0470-FFR option 3: VARIANT W carries T_WAKE_N and Q_WAKE_NM from the rotor's lines."""
    from pyflightstream.farfield import wake_rotor_loads
    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_helical_wake

    radii = np.linspace(0.2, 1.0, 9)
    gamma = 1.5 * np.sin(math.pi * (0.5 * (radii[:-1] + radii[1:]) - 0.2) / 0.8)
    omega = 2.0 * math.pi * 1000.0 / 60.0
    blade_lines, blade_values = _p0470_helical_wake(
        2, gamma=gamma, radii=radii, v=30.0, omega=omega, turns=3.0
    )
    hub = np.array([3.0, 0.0, 2.0])
    blade_lines = [line + hub for line in blade_lines]
    wing, shed = _p0470_wing_lines()
    columns, rows, ctx = _p0470_post_rotor_wake(
        tmp_path, wing + blade_lines, np.concatenate([shed, blade_values]), rotor=True
    )
    (w_row,) = [row for row in rows if row["VARIANT"] == "W"]
    expected = wake_rotor_loads(
        blade_lines,
        values=blade_values,
        hub=hub,
        axis=(1.0, 0.0, 0.0),
        omega=omega,
        v_axial=30.0,
        rho=1.225,
        blades=2,
    )
    assert w_row["FAMILY"] == "ROTOR"
    assert float(w_row["T_WAKE_N"]) == pytest.approx(expected.thrust, rel=1e-6)
    assert float(w_row["Q_WAKE_NM"]) == pytest.approx(expected.torque, rel=1e-6)
    assert float(w_row["GAMMA_SCALE"]) == 1.0
    assert int(float(w_row["N_TRACE"])) == len(blade_lines)
    assert columns.index("T_WAKE_N") < columns.index("STATUS") == len(columns) - 1


@pytest.mark.requirement("FR-452")
def test_p0470_ffr_b_on_a_wing_and_rotor_row_traces_the_wing_lines_alone(tmp_path):
    """P0470-FFR B by family: the B row of a wing beside a rotor is the wing's own trace."""
    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_helical_wake

    radii = np.linspace(0.2, 1.0, 9)
    gamma = np.ones(8)
    blade_lines, blade_values = _p0470_helical_wake(
        2, gamma=gamma, radii=radii, v=30.0, omega=100.0, turns=3.0
    )
    blade_lines = [line + np.array([3.0, 0.0, 2.0]) for line in blade_lines]
    wing, shed = _p0470_wing_lines()
    _, mixed, _ = _p0470_post_rotor_wake(
        tmp_path / "mixed", wing + blade_lines, np.concatenate([shed, blade_values]), rotor=True
    )
    columns, alone, _ = _p0470_post_rotor_wake(tmp_path / "alone", wing, shed, rotor=False)
    (b_mixed,) = [row for row in mixed if row["VARIANT"] == "B"]
    (b_alone,) = [row for row in alone if row["VARIANT"] == "B"]
    for column in ("CL_T", "CDI_T", "E_T", "N_TRACE", "GAMMA_SCALE", "X_T_M"):
        assert b_mixed[column] == b_alone[column], column
    assert "T_WAKE_N" not in columns, "a table of rows without a rotor keeps its columns"


def test_p0470_r1_wake_loads_at_hover_keep_dimensional_loads(tmp_path):
    """A zero free-stream normalization leaves counts NA without losing wake loads."""
    from pyflightstream.post.farfield_products import _TREFFTZ_CELLS, _variant_w
    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_helical_wake

    lines, values = _p0470_helical_wake(
        2, gamma=np.ones(4), radii=np.linspace(0.2, 1.0, 5), v=10, omega=100, turns=2
    )
    lines = [line + np.array([3.0, 0.0, 2.0]) for line in lines]
    _, _, ctx = _p0470_post_rotor_wake(tmp_path, lines, values, rotor=True)
    point = ctx.points[0]
    point.loads = replace(point.loads, freestream_velocity_m_s=0.0)
    try:
        rows = _variant_w(ctx, point, tmp_path / "point_wakes.vtk")
    except ZeroDivisionError:
        rows = []
    assert len(rows) == 1, "hover must retain its dimensional wake loads"
    row = dict(zip(_TREFFTZ_CELLS, rows[0][3 + len(CONTEXT_COLUMNS) :], strict=True))
    assert math.isfinite(row["T_WAKE_N"]) and math.isfinite(row["Q_WAKE_NM"])
    assert math.isnan(row["DT_WAKE_COUNTS"]) and math.isnan(row["DQ_WAKE_COUNTS"])
