"""P0400-FFOUT: the far-field products of a posted simulation (FR-456).

One synthetic steady point is posted end to end: an elliptic loading of a
wing alone exported as sectional loads, its wake as the solver writes it, and
a uniform stream sampled on the C plane. Every export is built here in the
recorded formats with synthetic values; no research data enters.
"""

from __future__ import annotations

import csv
import json
import math
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.farfield_products import farfield_axes
from pyflightstream.probes.layouts import farfield_plane
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_post_products import LOADS

ALPHA = -2.0
SPEED = 68.058
RHO = 1.225
BREF = 20.0
SREF = 50.0
CL = 0.1882829
STATIONS = 160
_RULE = " " + "-" * 100 + "\n"


def _sloads() -> str:
    q = 0.5 * RHO * SPEED * SPEED
    peak = CL * q * SREF * 4.0 / (math.pi * BREF)
    y = -BREF / 2 + (np.arange(STATIONS) + 0.5) * BREF / STATIONS
    lift = peak * np.sqrt(1.0 - (2.0 * y / BREF) ** 2)
    fz = lift / math.cos(math.radians(ALPHA))
    head = LOADS.split("     Surface,")[0].replace("Aerodynamic loads", "Surface Sectional Loads")
    rows = "".join(
        f"     {a: .4E}, 0.1000E+01, 0.0000E+00, 0.0000E+00, 0.0000E+00, {b: .4E}, 0.0000E+00,\n"
        for a, b in zip(y, fz, strict=True)
    )
    return (
        head.rsplit(_RULE, 1)[0]
        + f"     Number of Surface Sections:                 {STATIONS}\n"
        + _RULE
        + "     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n"
        + rows
        + _RULE
        + "     Force Units: Newtons\n     Moment Units: Newton-Meter\n"
        + "     Software : Flightstream\n"
    )


def _wakes(*, half: bool = False) -> str:
    nodes = -BREF / 2 + np.arange(1, STATIONS) * BREF / STATIONS
    if half:
        nodes = nodes[nodes > 0.0]
    gamma = np.sqrt(1.0 - (2.0 * nodes / BREF) ** 2)
    points, lines = [], []
    for index, y in enumerate(nodes):
        points += [(1.0, y, 0.0), (15.0, y, 0.0), (30.0, y, 0.0)]
        lines += [(3 * index, 3 * index + 1), (3 * index + 1, 3 * index + 2)]
    values = np.repeat(gamma, 2)
    return (
        "# vtk DataFile Version 3.0\nwake\nASCII\nDATASET POLYDATA\n"
        + f"POINTS {len(points)} float\n"
        + "".join(f"{x} {y} {z}\n" for x, y, z in points)
        + f"LINES {len(lines)} {3 * len(lines)}\n"
        + "".join(f"2 {a} {b}\n" for a, b in lines)
        + f"CELL_DATA {len(lines)}\nSCALARS Normalized_Vorticity float 1\nLOOKUP_TABLE default\n"
        + "".join(f"{v}\n" for v in values)
    )


def _probes() -> str:
    a = math.radians(ALPHA)
    direction = (math.cos(a), 0.0, math.sin(a))
    laid = farfield_plane(
        (20.0, 0.0, 0.0),
        direction,
        distance=5.0,
        half_width=0.75 * BREF,
        half_height=0.5 * BREF,
        spacing=0.05 * BREF,
    )
    velocity = SPEED * np.array(direction)
    rows = "".join(
        "     "
        + ", ".join(f"{v: .4E}" for v in (*p, 0.2, 0.0, *velocity, SPEED, 0.0))
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
    footer = tail.split(_RULE)[-2:]
    return (
        head
        + "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp, s_len, momentum_thickness, disp_thick,"
        + tail.split("\n", 1)[0]
        + "\n"
        + _RULE
        + rows
        + _RULE
        + footer[-1]
    )


_FARFIELD = (
    '[farfield]\nfamilies = "all"\n[farfield.trefftz]\n'
    'variant = ["sections", "wake", "plane"]\nspacing_bref = 0.05\n'
)


def _workspace(root: Path, *, farfield: bool) -> CampaignWorkspace:
    workspace = CampaignWorkspace.init(root / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n' + (_FARFIELD if farfield else ""), encoding="utf-8"
    )
    raw = workspace.sim_dir("3207") / "outputs"
    raw.mkdir(parents=True)
    stem = "POLAR-3207_M20AL-020BE+000"
    files = {
        f"{stem}.txt": LOADS,
        f"{stem}.fsm": "$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n",
        f"{stem}_sloads.txt": _sloads(),
        f"{stem}.vtk": "# vtk DataFile Version 3.0\n",
        f"{stem}_wakes.vtk": _wakes(),
        f"{stem}_probes.txt": _probes(),
    }
    for name, text in files.items():
        (raw / name).write_text(text, encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3207/AL-020",
            point_name="AL-020",
            sweep_name="AL-020",
            point={"alpha": ALPHA},
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
            density_kg_m3=RHO,
            reference={"SREF": SREF, "CREF": 2.526, "BREF": BREF, "XMOM": 0.0},
            sections_layout=[
                {
                    "distribution": 1,
                    "distribution_families": ["W"],
                    "families": ["W"],
                    "plane": "XZ",
                    "frame": "MRP",
                    "count": STATIONS,
                }
            ],
        )
    )
    return workspace


def _post(workspace: CampaignWorkspace) -> list[str]:
    from pyflightstream.post.products import write_campaign_products

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", PyflightstreamWarning)
        write_campaign_products(workspace)
    return [str(w.message) for w in caught]


def _table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def posted(tmp_path_factory):
    root = tmp_path_factory.mktemp("ff")
    workspace = _workspace(root / "with", farfield=True)
    messages = _post(workspace)
    plain = _workspace(root / "without", farfield=False)
    _post(plain)
    return Path(workspace.root), Path(plain.root), messages


def _one(root: Path, pattern: str) -> Path:
    found = sorted(root.rglob(pattern))
    assert len(found) == 1, (pattern, found)
    return found[0]


@pytest.mark.requirement("FR-456")
def test_p0400_ffout_the_trefftz_table(posted):
    """P0400-FFOUT (FR-456 R1, R2): one file beside the polar, A, B and C rows, NA per rule."""
    root, _plain, _messages = posted
    path = _one(root, "farfield/*_trefftz.csv")
    rows = {row["VARIANT"]: row for row in _table(path)}
    assert set(rows) == {"A", "B", "C"}
    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:2] == ["POL", "STEP"] and header[-1] == "ETA_FF"
    a, b, c = rows["A"], rows["B"], rows["C"]
    assert float(a["CL_T"]) == pytest.approx(CL, rel=2e-3)
    assert 1.0 < float(a["E_T"]) < 1.012, "the elliptic bias of 80 stations per side"
    assert float(b["CL_T"]) == pytest.approx(CL, abs=1e-5), "B is calibrated on the near CL"
    assert 0.97 < float(b["E_T"]) < 1.03
    upstream = float((farfield_axes(ALPHA, 0.0) @ np.array([1.0, 0.0, 0.0]))[0])
    assert float(b["X_T_M"]) == pytest.approx(upstream + 0.25 * BREF, abs=1e-5)
    assert a["X_T_M"] == "NA"
    assert float(c["CDI_T"]) == pytest.approx(0.0, abs=1e-9), "a uniform stream has no drag"
    assert float(c["COVERAGE"]) == 1.0 and c["CL_T"] == "NA"
    assert a["P_AXIAL_W"] == "NA" and a["CDI_NEAR_PRESSURE"] == "0.00124"


@pytest.mark.requirement("FR-456")
def test_p0400_ffout_the_spanwise_files(posted):
    """P0400-FFOUT (FR-456 R3): A per family, B as TOTAL, downwash and local drag."""
    root, _plain, _messages = posted
    family = _table(_one(root, "sections/*_trefftz_W.csv"))
    total = _table(_one(root, "sections/*_trefftz_TOTAL.csv"))
    assert len(family) == STATIONS and {row["VARIANT"] for row in family} == {"A"}
    assert {row["CDI_LOCAL"] for row in total} == {"NA"}
    downwash = [float(row["W_M_S"]) for row in family[10:-10]]
    assert max(downwash) - min(downwash) < 0.05 * abs(np.mean(downwash)), "elliptic: uniform"


@pytest.mark.requirement("FR-456")
def test_p0400_ffout_the_manifest(posted):
    """P0400-FFOUT (FR-456 R6): runs held, analysis, variants, inputs and the strip rule."""
    root, _plain, _messages = posted
    manifest = json.loads(_one(root, "products.json").read_text(encoding="utf-8"))
    entries = manifest.get("products", manifest)
    (entry,) = [value for key, value in _items(entries) if key.endswith("_trefftz.csv")]
    assert entry["runs"] == ["camp/sim_3207/AL-020"]
    assert entry["analysis"] == "trefftz" and entry["strip_rule"] == "extended"
    assert entry["variants"] == ["sections", "wake", "plane"]


def _items(entries):
    if isinstance(entries, dict):
        return entries.items()
    return [(str(entry.get("path", "")), entry) for entry in entries]


@pytest.mark.requirement("FR-456")
def test_p0400_ffout_the_polar_keeps_its_bytes(posted):
    """P0400-FFOUT (FR-456 R8, FR-450): the polar is byte-identical with and without [farfield].

    The super file beside it gains its far-field block (R9), so it is the one
    file of the folder left out here.
    """
    root, plain, _messages = posted
    for path in sorted(p for p in plain.rglob("polars/*") if not p.name.startswith("SUPER-")):
        twin = root / path.relative_to(plain)
        assert twin.read_bytes() == path.read_bytes(), path.name
    assert not list(plain.rglob("farfield/*")), "no [farfield], no far-field file"


def _add_outputs(manifest: Path, sim_id: str, suffixes: tuple[str, ...]) -> None:
    """Add exports to the recorded outputs of one simulation's runs, as a run records them."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    runs = data if isinstance(data, list) else data.get("runs", data.get("records", []))
    for run in runs:
        if run.get("sim_id") == sim_id:
            loads = run["outputs"][0]
            run["outputs"] = [loads] + [loads[: -len(".txt")] + suffix for suffix in suffixes]
    manifest.write_text(json.dumps(data, indent=1), encoding="utf-8")


@pytest.mark.requirement("FR-456")
def test_p0400_ffout_the_super_file_block(tmp_path):
    """P0400-FFOUT (FR-456 R9): TOTAL rows only, as CL_T_B, CDI_T_B, E_T_B, after every column."""
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
        (outputs / f"{stem}_wakes.vtk").write_text(_wakes(half=True), encoding="utf-8")
    _add_outputs(workspace.manifest_path, "6001", (".fsm", ".vtk"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        post_matrix(workspace)
    columns, rows = _superfiles(workspace)[name]
    added = [column for column in columns if column not in before]
    assert added == ["CL_T_B", "CDI_T_B", "E_T_B"]
    kept = [column for column in before if column != "MESH_FACES"]
    assert columns.index("CL_T_B") > max(columns.index(column) for column in kept)
    assert all(row["E_T_B"] not in ("", None) for row in rows)
