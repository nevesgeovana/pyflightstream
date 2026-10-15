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
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

import tests.tier1_offline.test_regression_farfield_interfaces as _rfixa_products__plan
import tests.tier1_offline.test_regression_farfield_products as _ffproof_post__wing
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
from pyflightstream.farfield import bernoulli_residual, mass_closure
from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.farfield_fields import (
    LEDGER_COLUMNS,
    ProbeSamples,
    far_samples,
    plane_values,
    recorded_layout,
    unsteady_samples,
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

_FARFIELD_PRODUCTS__ALPHA = -2.0


_FARFIELD_PRODUCTS__SPEED = 68.058


_FARFIELD_PRODUCTS__RHO = 1.225


_FARFIELD_PRODUCTS__BREF = 20.0


_FARFIELD_PRODUCTS__SREF = 50.0


_FARFIELD_PRODUCTS__CL = 0.1882829


_FARFIELD_PRODUCTS__STATIONS = 160


_FARFIELD_PRODUCTS___RULE = " " + "-" * 100 + "\n"


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
    '[farfield]\nfamilies = "all"\n[farfield.trefftz]\n'
    'variant = ["sections", "wake", "plane"]\nspacing_bref = 0.05\n'
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
        f"{stem}_probes.txt": _farfield_products___probes(),
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
    def test_p0400_ffout_the_trefftz_table(posted):
        """P0400-FFOUT (FR-1053, FR-1054): one file beside the polar, A, B and C rows, NA per
        rule.
        """
        root, _plain, _messages = posted
        path = _farfield_products___one(root, "farfield/*_trefftz.csv")
        rows = {row["VARIANT"]: row for row in _farfield_products___table(path)}
        assert set(rows) == {"A", "B", "C"}
        header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
        # PFS-2081.97: the point's status closes every far-field row, after ETA_FF.
        assert header[:2] == ["POL", "STEP"] and header[-2:] == ["ETA_FF", "STATUS"]
        a, b, c = rows["A"], rows["B"], rows["C"]
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
        """P0400-FFOUT (FR-1055): A per family, B as TOTAL, downwash and local drag."""
        root, _plain, _messages = posted
        family = _farfield_products___table(
            _farfield_products___one(root, "sections/*_trefftz_W.csv")
        )
        total = _farfield_products___table(
            _farfield_products___one(root, "sections/*_trefftz_TOTAL.csv")
        )
        assert len(family) == _FARFIELD_PRODUCTS__STATIONS and {
            row["VARIANT"] for row in family
        } == {"A"}
        assert {row["CDI_LOCAL"] for row in total} == {"NA"}
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
            '[groups]\n"1" = "all"\n"2" = "W"\n[farfield]\nfamilies = "all"\n'
            '[farfield.trefftz]\nvariant = "wake"\n',
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
        assert added == ["CL_T_B", "CDI_T_B", "E_T_B"]
        kept = [column for column in before if column != "MESH_FACES"]
        assert columns.index("CL_T_B") > max(columns.index(column) for column in kept)
        assert all(row["E_T_B"] not in ("", None) for row in rows)


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
    "n_psi": 8,
}


_FFPROOF_POST___SHAPE = LatticeShape.model_validate(_FFPROOF_POST___LATTICE)


_FFPROOF_POST___POINTS_M = lattice_points(_FFPROOF_POST___SHAPE.build(1.0), axis="X")


_FFPROOF_POST___LEDGERS = (
    '[farfield]\nfamilies = "all"\n[farfield.ledgers]\nframe = "MRP"\ntip_radius_m = 1.0\n'
    "stations = [-1.0, 1.0]\nn_r = 2\nn_psi = 8\nm_max = 2\n"
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
    return _FFPROOF_POST__PLOTS_HEADER + table + "-" * 60 + "\n     Force Units: Coefficients\n"


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
            '[groups]\n"1" = "all"\n[farfield]\nfamilies = "all"\n[farfield.trefftz]\n'
            'variant = "sections"\nstations = 160\n',
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
        assert b["FAMILY"] == "TOTAL"
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
    def test_p0400_ffproof_post_writes_the_ledgers_table(tmp_path):
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
                f"{_FFPROOF_POST___STEM}_probes.txt": _ffproof_post___probe_export(
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
        assert columns == ["POL", "STEP", *CONTEXT_COLUMNS, *LEDGER_COLUMNS]
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
        count = len(_FFPROOF_POST___POINTS_M)
        workspace = _ffproof_post___campaign(
            tmp_path,
            pproc=_FFPROOF_POST___LEDGERS,
            files={f"{_FFPROOF_POST___STEM}_plots.txt": _ffproof_post___plots_export(count, 8)},
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
        assert columns == ["POL", "STEP", *CONTEXT_COLUMNS, *LEDGER_COLUMNS]
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
        """P0400-FFPROOF (FR-1052): a reused ``kind = "normal"`` lattice holds the last step.

        The far field reuses a ``[[probes]]`` lattice of kind normal on an
        unsteady row: the probe export of the last step (18 m/s) gives the
        instant, written with the run's last step; the average is not written,
        and it is a named skip in ``products.json`` and a WARNING in ``post.log``.
        """
        probes = (
            '[[probes]]\nframe = "MRP"\nkind = "normal"\nparameters = ["VX"]\n'
            '[[probes.lattices]]\nframe = "MRP"\ntip_radius_m = 1.0\nstations = [-1.0, 1.0]\n'
            "n_r = 2\nn_psi = 8\n"
        )
        workspace = _ffproof_post___campaign(
            tmp_path,
            pproc=probes + _FFPROOF_POST___LEDGERS,
            files={
                f"{_FFPROOF_POST___STEM}_probes.txt": _ffproof_post___probe_export(
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
        assert 'kind = "normal"' in reason and "last time step" in reason
        assert any('kind = "normal"' in line for line in _ffproof_post___warnings_of(root))


_LITB_POST__FIXTURES = Path(__file__).parent / "fixtures"


def _litb_post__post_wake(root, fixture, *, cl=0.3400367):
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
        parse_loads(_LITB_POST__LOADS), freestream_velocity_m_s=34.03, angle_of_attack_deg=4.0
    )
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
        pproc=PprocSpec.model_validate(
            {
                "farfield": {"families": "all", "trefftz": {"variant": "wake"}},
            }
        ),
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

    pytestmark = pytest.mark.requirement("P0400-LITB-POST")

    @staticmethod
    @pytest.mark.parametrize("build", ["26124", "26125"])
    def test_p0400_litb_real_mirror_wake_reaches_post(tmp_path, build):
        row, messages, skipped = _litb_post__post_wake(tmp_path, f"p0400_litB_wake_{build}.vtk")
        assert row["VARIANT"] == "B" and row["E_T"] != "NA", skipped
        assert float(row["CL_T"]) == pytest.approx(0.3400367, abs=1e-5)
        assert any("collapsed wake lines" in message for message in messages) == (build == "26124")


class TestRfixAProducts:
    """Regressions through planned section layouts and the public post stage."""

    pytestmark = pytest.mark.requirement("P0400-RFIXA-PRODUCTS")

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
            tmp_path, {"families": "all", "trefftz": {"variant": "sections", "stations": 80}}
        )
        mesh = Path(case.geometry)
        mesh.write_text(mesh.read_text().replace("g W", "g Wing1") + "g Wing2\nf 1 2 4 3\n")
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
            {
                "families": "all",
                "trefftz": {
                    "variant": "plane",
                    "half_width_bref": 0.25,
                    "half_height_bref": 0.25,
                    "spacing_bref": 0.25,
                },
            },
        )
        case = case.model_copy(
            update={
                "velocity": 10.0,
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
            pproc='[farfield]\nfamilies="all"\n'
            '[farfield.trefftz]\nvariant="plane"\nhalf_width_bref=0.05\n'
            "half_height_bref=0.05\nspacing_bref=0.05\n",
            files={
                f"{_rfixa_products__post._FFPROOF_POST___STEM}_probes.txt": _rfixa_products__post._ffproof_post___probe_export(  # noqa: E501
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
        probes = next(raw.glob("*_probes.txt"))
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


_RFIXF2_DISTRIBUTIONS___TREFFTZ_A = {
    "families": "all",
    "trefftz": {"variant": "sections", "stations": 80},
}


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
        from pyflightstream.cases.workflows._farfield import _covered
        from tests.tier1_offline.test_regression_farfield_interfaces import (
            _farfield_plan___case as _case,
        )

        case = _case(
            tmp_path,
            _RFIXF2_DISTRIBUTIONS___TREFFTZ_A,
            **_rfixf2_distributions___sections(["W", "T"]),
        )
        assert _covered(case, ["W", "T"]) == set()
        assert traced_family(["W", "T"], ["W", "T"]) is None
        assert traced_family([], ["W"]) == "W"
        assert traced_family([], ["W", "T"]) is None


if TYPE_CHECKING:
    from pyflightstream.post.farfield_fields import ProbeSamples


_RFIXF2_MATCHING___ORIGIN = np.array([0.25, 0.0, 0.0])


def _rfixf2_matching___lattice_case():
    from pyflightstream.cases._farfield_spec import LatticeShape
    from pyflightstream.probes.layouts import lattice_points

    lattice = LatticeShape.model_validate(
        {"frame": "MRP", "tip_radius_m": 0.5, "stations": [2.0], "n_r": 2, "n_psi": 8}
    ).build(1.0)
    local = lattice_points(lattice, axis="X")
    shape = {
        "kind": "lattice",
        "source": "declared",
        "entry": 1,
        "count": len(local),
        "lattice": lattice.model_dump(mode="json"),
        "axis": "X",
        "origin_m": [float(v) for v in _RFIXF2_MATCHING___ORIGIN],
        "positions_frame": "MRP",
    }
    return lattice, local, shape


def _rfixf2_matching___unsteady(entries: list[tuple[np.ndarray, str, float]]) -> ProbeSamples:
    """One step of fluid plots: each entry's points (native = m), frame label and axial speed."""
    from pyflightstream.post.farfield_fields import unsteady_samples

    positions: dict[int, tuple[float, float, float, str]] = {}
    series: dict[str, np.ndarray] = {}
    vertex = 0
    for points, frame, speed in entries:
        for point in points:
            vertex += 1
            positions[vertex] = (*(float(v) for v in point), frame)  # type: ignore[assignment]
            series[f"VX{vertex}"] = np.array([speed])
            series[f"VY{vertex}"] = np.array([0.0])
            series[f"VZ{vertex}"] = np.array([0.0])
            series[f"CP_REF{vertex}"] = np.array([0.0])
    return unsteady_samples(series, positions, 0)


def _rfixf2_matching___mdot(samples: ProbeSamples, block: slice | np.ndarray) -> float:
    from pyflightstream.post.farfield_fields import lattice_samples

    _LATTICE, _, _ = _rfixf2_matching___lattice_case()
    fields = lattice_samples(samples, block, _LATTICE, "X", q=0.5 * 1.225 * 20.0**2)
    return float(mass_closure(fields, 1.225).mdot[0])


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
    """P0400-RFIXF2-MATCHING: each far-field set is matched in its own frame, to the export's precision.

    PFS-2081.102 (REL2-001): a declared lattice recorded in a translated frame (MRP)
    is matched among that frame's points only, in its local coordinates, so a later
    reference-frame entry whose positions coincide with the lattice's reference
    positions never lends it its velocities.

    PFS-2081.103 (REL2-002): the matching tolerance is the export's printed
    precision of each coordinate, never a fraction of the distance from the origin;
    a plane of another grid at large coordinates, or a legacy export holding a
    distant unrelated point, is refused rather than integrated with the wrong area.
    Every fixture is synthetic: a uniform stream, a uniform crossflow.
    """  # noqa: E501

    pytestmark = pytest.mark.requirement("FR-455")

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_translated_frame_lattice_reads_its_own_samples():
        """P0400-RFIXF2-MATCHING (FR-1045, PFS-2081.102): MRP lattice before a REFERENCE entry.

        The lattice's 24 points are recorded in MRP at their local positions with
        20 m/s; the next entry, in REFERENCE, stands at the lattice's reference
        positions (local plus the frame origin) with 50 m/s. Post must read the
        20 m/s, and the balance must be the lattice's own mass flow.
        """
        from pyflightstream.post.farfield_fields import far_samples, recorded_layout

        _, _LOCAL, _SHAPE = _rfixf2_matching___lattice_case()
        samples = _rfixf2_matching___unsteady(
            [(_LOCAL, "MRP", 20.0), (_LOCAL + _RFIXF2_MATCHING___ORIGIN, "REFERENCE", 50.0)]
        )
        lattice, plane, why = far_samples(samples, recorded_layout([_SHAPE]), per_m=1.0)
        assert why == "" and plane is None
        assert np.allclose(samples.velocity[lattice], [20.0, 0.0, 0.0])
        alone = _rfixf2_matching___unsteady([(_LOCAL, "MRP", 20.0)])
        assert _rfixf2_matching___mdot(samples, lattice) == pytest.approx(
            _rfixf2_matching___mdot(alone, slice(0, len(_LOCAL)))
        )

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_frame_lattice_found_twice_in_its_frame_is_refused():
        """P0400-RFIXF2-MATCHING (FR-1045): two MRP entries at the same points are refused."""
        from pyflightstream.post.farfield_fields import far_samples, recorded_layout

        _, _LOCAL, _SHAPE = _rfixf2_matching___lattice_case()
        samples = _rfixf2_matching___unsteady([(_LOCAL, "MRP", 20.0), (_LOCAL, "MRP", 50.0)])
        lattice, _, why = far_samples(samples, recorded_layout([_SHAPE]), per_m=1.0)
        assert lattice is None and "2 times" in why

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_distant_plane_of_another_grid_is_refused():
        """P0400-RFIXF2-MATCHING (FR-1045, PFS-2081.103): 4 m2 laid, 16 m2 recorded, at x = 30 km.

        The control is the recorded 4 m2 plane at the same place: matched, and its
        induced drag is the crossflow's 0.5 rho v^2 S = 2 N.
        """
        from pyflightstream.post.farfield_fields import far_samples, plane_values, recorded_layout

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
        from pyflightstream.post.farfield_fields import FarLayout, far_samples

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
        from pyflightstream.post.farfield_fields import far_samples, recorded_layout

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
            {"families": "all", "trefftz": {"variant": "plane"}, "ledgers": {"rotor": "R"}}
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
            "trefftz:plane": {"reused"},
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
            {
                "families": "all",
                "trefftz": {"variant": "plane"},
                "ledgers": {"rotor": "ROTOR", "m_max": 2},
            },
            probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [lattice]}],
        )
        case = case.model_copy(update={"point": {**case.point, "RPM": 1000.0}})
        script = _rfixf2_plan_states___script(case)
        count = LatticeShape.model_validate(lattice).build(1.0).point_count
        assert len(script.probe_points) == count
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert (shape["kind"], shape["source"]) == ("lattice", "declared")
        states = _rfixf2_plan_states___probe_states(plan_record(case, "26.124", script))
        assert states == {"trefftz:plane": {"reused"}, "ledgers": {"reused"}}


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
        entry = {"frame": "MRP", "parameters": ["VX"], "lattices": [_RFIXF2_PLOTS___LATTICE]}
        case = _rfixf2_plots___unsteady(
            tmp_path,
            {"families": "all", "ledgers": dict(_RFIXF2_PLOTS___LATTICE, m_max=2)},
            probes=[entry],
        )
        script = Script("26.124")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            build_script(case, script)
        messages = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
        text = script.render()
        assert len(script.probe_points) == _RFIXF2_PLOTS___POINTS, "the declared lattice, laid once"
        assert text.count(_RFIXF2_PLOTS___PLOT) == 4 * _RFIXF2_PLOTS___POINTS
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert (shape["source"], shape["plots_added"]) == ("declared", ["VY", "VZ", "CP_REF"])
        assert any(
            f"{3 * _RFIXF2_PLOTS___POINTS} fluid plots at every time step (FR-1052)" in m
            for m in messages
        )
        names = _rfixf2_plots___plot_names(text)
        vertices = [point[0] for point in script.probe_points]
        for parameter in ("VX", "VY", "VZ", "CP_REF"):
            assert sorted(n for n in names if re.fullmatch(f"{parameter}\\d+", n)) == sorted(
                f"{parameter}{v}" for v in vertices
            )
        series = {name: np.array([1.0]) for name in names}
        positions = {p[0]: (p[1], p[2], p[3], p[4]) for p in script.probe_points}
        samples = unsteady_samples(series, positions, 0)
        lattice, _, why = far_samples(samples, recorded_layout([shape]), per_m=1.0)
        assert why == ""
        assert (
            np.isfinite(samples.velocity[lattice]).all() and np.isfinite(samples.cp[lattice]).all()
        )

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixf2_a_lattice_stating_every_history_adds_none(tmp_path):
        """P0400-RFIXF2-PLOTS (FR-1045): nothing is added to an entry that states all four."""
        entry = {
            "frame": "MRP",
            "parameters": ["VX", "VY", "VZ", "CP_REF"],
            "lattices": [_RFIXF2_PLOTS___LATTICE],
        }
        case = _rfixf2_plots___unsteady(
            tmp_path,
            {"families": "all", "ledgers": dict(_RFIXF2_PLOTS___LATTICE, m_max=2)},
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


def _rfixf_layout___export(points: np.ndarray, velocity: np.ndarray) -> str:
    """A steady probe-points export of ``points`` (native) with ``velocity`` (m/s) at each."""
    rows = "".join(
        "     "
        + ", ".join(
            f"{v: .6E}"
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
    '[farfield]\nfamilies = "all"\n[farfield.trefftz]\nvariant = "plane"\n'
    "half_width_bref = 0.1\nhalf_height_bref = 0.1\nspacing_bref = 0.1\n"
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
            f"{_rfixf_layout__ffpost._FFPROOF_POST___STEM}_probes.txt": _rfixf_layout___export(
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
            f"{_rfixf_layout__ffpost._FFPROOF_POST___STEM}_probes.txt": _rfixf_layout___export(
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
            {"families": "all", "ledgers": {"rotor": "ROTOR", "m_max": 2}},
            probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [declared]}],
        )
        script = _rfixf_layout___script(case)
        count = LatticeShape.model_validate(declared).build(1.0).point_count
        assert len(script.probe_points) == count, "laid once, the declared entry"
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert (shape["kind"], shape["source"], shape["entry"]) == ("lattice", "declared", 1)
        assert shape["lattice"]["stations"] == [2.0]
        assert _rfixf_layout___states(plan_record(case, "26.124", script), "ledgers") == {"reused"}

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
            {"families": "all", "ledgers": dict(shape, r_inner=0.05, m_max=2)},
            probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [shape]}],
        )
        script = _rfixf_layout___script(case)
        assert len(script.probe_points) == LatticeShape.model_validate(shape).build(1.0).point_count
        assert script.farfield_layout[-1]["shapes"][0]["source"] == "declared"
        assert _rfixf_layout___states(plan_record(case, "26.124", script), "ledgers") == {"reused"}

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
            {"families": "all", "trefftz": {"variant": "plane"}},
            probes=[{"frame": "REFERENCE", "parameters": ["VX"], "rectangles": [rectangle]}],
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
            {"families": "all", "trefftz": {"variant": "plane", "spacing_bref": 0.25}},
            probes=[{"frame": "REFERENCE", "parameters": ["VX"], "rectangles": [rectangle]}],
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
        from pyflightstream.post.farfield_fields import recorded_layout

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
    '[farfield]\nfamilies = "all"\n[farfield.trefftz]\nvariant = "plane"\n'
    "half_width_bref = 0.5\nhalf_height_bref = 0.25\nspacing_bref = 0.0125\n"
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


def _rfixf_plane_lift___post(tmp_path: Path, scale: float) -> tuple[dict[str, str], list[str]]:
    workspace = _rfixf_plane_lift__ffpost._ffproof_post___campaign(
        tmp_path,
        pproc=_RFIXF_PLANE_LIFT___TABLE,
        files={
            f"{_rfixf_plane_lift__ffpost._FFPROOF_POST___STEM}_probes.txt": _rfixf_layout___export(
                _RFIXF_PLANE_LIFT___PLANE.points, _rfixf_plane_lift___crossflow(scale)
            )
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


_RFIXF_QSTEADY___SHAPE = {"rotor": "ROTOR", "stations": [-1.0, 1.0], "n_r": 2, "n_psi": 8}


_RFIXF_QSTEADY___LEDGERS = (
    '[farfield]\nfamilies = "all"\n[farfield.ledgers]\nrotor = "ROTOR"\n'
    "stations = [-1.0, 1.0]\nn_r = 2\nn_psi = 8\nm_max = 2\n"
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
        positions=(
            QsteadyClocking(0, 0.0, 0.0, f"{_rfixf_qsteady__ffpost._FFPROOF_POST___STEM}.txt"),
        ),
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
            f"{_rfixf_qsteady__ffpost._FFPROOF_POST___STEM}_probes.txt": _rfixf_layout___export(
                _RFIXF_QSTEADY___POINTS, turning
            ),
            f"{_rfixf_qsteady__ffpost._FFPROOF_POST___STEM}_qsteady.json": _rfixf_qsteady___quasi(
                rpm
            ),
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
                f"{_rfixf_status__ffpost._FFPROOF_POST___STEM}_probes.txt": _rfixf_status__ffpost._ffproof_post___probe_export(  # noqa: E501
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
