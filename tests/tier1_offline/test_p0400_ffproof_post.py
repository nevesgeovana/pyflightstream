"""P0400-FFPROOF: the far-field products ``pyfs-matrix post`` writes, read from the files.

Every test posts a synthetic campaign end to end through
``write_campaign_products`` (the body of ``pyfs-matrix post``) and reads what
it wrote: the far-field tables, ``products.json`` and the WARNING lines of
``post.log``. The exports are built in the recorded formats with synthetic
values (an elliptic loading, a wake of straight lines, uniform streams sampled
on a survey lattice); no research data enters. The steady wing point is the
one of ``test_p0400_farfield_products``; the survey points are new here.
"""

from __future__ import annotations

import csv
import json
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases._farfield_spec import LatticeShape
from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.farfield_fields import LEDGER_COLUMNS
from pyflightstream.post.products import write_campaign_products
from pyflightstream.probes.layouts import lattice_points
from pyflightstream.results import sweep_table, write_table
from pyflightstream.run import SWEEP_TABLE_NAME
from pyflightstream.run._pending import _write_probe_points
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline.test_post_products import LOADS, PLOTS_HEADER

_STEM = "POLAR-3207_M20AL-020BE+000"
_RUN = "camp/sim_3207/AL-020"
_RULE = " " + "-" * 100 + "\n"
_FSM = "$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n"
_RHO = 1.225

#: A survey lattice of the MRP frame: two stations, two rings, eight azimuths.
_LATTICE = {"frame": "MRP", "tip_radius_m": 1.0, "stations": [-1.0, 1.0], "n_r": 2, "n_psi": 8}
_SHAPE = LatticeShape.model_validate(_LATTICE)
_POINTS_M = lattice_points(_SHAPE.build(1.0), axis="X")
_LEDGERS = (
    '[farfield]\nfamilies = "all"\n[farfield.ledgers]\nframe = "MRP"\ntip_radius_m = 1.0\n'
    "stations = [-1.0, 1.0]\nn_r = 2\nn_psi = 8\nm_max = 2\n"
)
#: The window an unsteady row of eight steps states with ``LAST_ITERS_AVG: 4``,
#: as the plan records it (steps 5 to 8), flagged as stated by the row.
_WINDOW = {
    "window_stated": True,
    "time_iterations": 8,
    "time_average": {"windows": [[5, 8]], "window_from": "LAST_ITERS_AVG: 4"},
}


def _speed(step: int) -> float:
    """The uniform axial speed of the synthetic unsteady field at one time step, m/s."""
    return 10.0 + step


def _probe_export(points: np.ndarray, speed: float) -> str:
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
    footer = tail.split(_RULE)[-1]
    return head + columns + tail.split("\n", 1)[0] + "\n" + _RULE + rows + _RULE + footer


def _plots_export(count: int, steps: int) -> str:
    """Fluid plots of ``count`` vertices over ``steps`` time steps, a uniform axial stream."""
    names = [f"{p}{n}" for n in range(1, count + 1) for p in ("VX", "VY", "VZ", "CP_REF")]
    table = "Time-step," + ",".join(names) + "\n"
    for step in range(1, steps + 1):
        values = [_speed(step), 0.0, 0.0, 0.0] * count
        table += f"{step}.0000," + ",".join(f"{v:.5f}" for v in values) + ",\n"
    return PLOTS_HEADER + table + "-" * 60 + "\n     Force Units: Coefficients\n"


def _campaign(
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
    exports = {f"{_STEM}.txt": LOADS, f"{_STEM}.fsm": _FSM, **files}
    for name, text in exports.items():
        (raw / name).write_text(text, encoding="utf-8")
    extra: dict[str, Any] = {}
    if reductions is not None:
        extra["reductions"] = reductions
    if positions:
        points = [
            (n, float(x), float(y), float(z), "REFERENCE")
            for n, (x, y, z) in enumerate(_POINTS_M, start=1)
        ]
        extra["probe_points_file"] = _write_probe_points(sim_dir, "3207", points)
    workspace.append_record(
        RunRecord(
            run_id=_RUN,
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
            density_kg_m3=_RHO,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0, "XMOM": 0.0},
            **extra,
        )
    )
    return workspace


def _post(workspace: CampaignWorkspace) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace)


def _one(root: Path, pattern: str) -> Path:
    found = sorted(root.rglob(pattern))
    assert len(found) == 1, (pattern, found)
    return found[0]


def _table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _manifest(root: Path) -> dict:
    return json.loads(_one(root, "products.json").read_text(encoding="utf-8"))


def _entry(manifest: dict, suffix: str) -> dict:
    (entry,) = [v for k, v in manifest["products"].items() if k.endswith(suffix)]
    return entry


def _warnings_of(root: Path) -> list[str]:
    text = _one(root, "post.log").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if "WARNING" in line]


def _set_record(workspace: CampaignWorkspace, **fields: object) -> None:
    """Change fields of the recorded run, as a record of that shape would carry them."""
    data = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    runs = data if isinstance(data, list) else data.get("runs", data.get("records", []))
    for run in runs:
        run.update(fields)
    workspace.manifest_path.write_text(json.dumps(data, indent=1), encoding="utf-8")


# ----------------------------------------------------------------- FR-450 R7


@pytest.mark.requirement("FR-450")
def test_p0400_ffproof_the_sweep_table_keeps_its_bytes(tmp_path):
    """P0400-FFPROOF (FR-450 R7): ``campaign_sweep.csv`` byte-identical with and without it.

    The same point recorded twice: once by a row selecting the three Trefftz
    variants, which the plan gave the sectional loads, wake and probe exports,
    and once by the row without ``[farfield]``, which recorded the loads and
    the saved simulation only. Both are posted, then the sweep table is written
    as the run stage writes it (``results.sweep_table`` through
    ``results.write_table`` to ``post/campaign_sweep.csv``): the two files are
    the same bytes, and the far field wrote its own table.
    """
    far = wing._workspace(tmp_path / "with", farfield=True)
    plain = wing._workspace(tmp_path / "without", farfield=False)
    _set_record(plain, outputs=[f"outputs/{_STEM}.txt", f"outputs/{_STEM}.fsm"])
    tables = []
    for workspace in (far, plain):
        _post(workspace)
        target = workspace.sweep_dir(None) / SWEEP_TABLE_NAME
        write_table(sweep_table(workspace, require_loads=False), target, overwrite=True)
        tables.append(target.read_bytes())
    assert list(Path(far.root).rglob("farfield/*_trefftz.csv")), "the far field was posted"
    assert not list(Path(plain.root).rglob("farfield/*"))
    assert b"-2" in tables[1] and tables[0] == tables[1]


# ----------------------------------------------------------------- FR-451 R10


@pytest.mark.requirement("FR-451")
def test_p0400_ffproof_post_warns_a_family_with_few_stations(tmp_path):
    """P0400-FFPROOF (FR-451 R10): one post WARNING naming the family, its count and the bias.

    The recorded distribution has 160 sections over the full span, 80 per
    side; the table asks for 160 per side. Variant A is still integrated and
    ``post.log`` says so once, with the bias the definitions page measured
    at 80 (0.52 percent).
    """
    workspace = wing._workspace(tmp_path, farfield=True)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n[farfield]\nfamilies = "all"\n[farfield.trefftz]\n'
        'variant = "sections"\nstations = 160\n',
        encoding="utf-8",
    )
    _post(workspace)
    root = Path(workspace.root)
    _columns, rows = _table(_one(root, "farfield/*_trefftz.csv"))
    assert [row["VARIANT"] for row in rows] == ["A"] and rows[0]["E_T"] != "NA"
    few = [line for line in _warnings_of(root) if "stations per side" in line]
    assert len(few) == 1, few
    assert "family W has 80 stations per side, fewer than the 160" in few[0]
    assert "0.52 percent at 80 stations per side" in few[0]


# ----------------------------------------------------------------- FR-452 R3


def _short_wakes(short: int) -> str:
    """The wing's wake with ``short`` lines ending 3 m behind the trailing edge."""
    text = wing._wakes()
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


@pytest.mark.requirement("FR-452")
def test_p0400_ffproof_a_short_wake_posts_the_b_row_na(tmp_path):
    """P0400-FFPROOF (FR-452 R3): the B row is NA, and the WARNING says why and how long.

    Three of the 159 wake lines end 3 m behind the trailing edge and the
    plane stands 0.25 BREF = 5 m behind it: the B row is written with its
    coefficients NA, never dropped and never integrated over the lines that
    reach; ``post.log`` names the three short lines and the wake's length.
    """
    workspace = wing._workspace(tmp_path, farfield=True)
    (workspace.sim_dir("3207") / "outputs" / f"{_STEM}_wakes.vtk").write_text(
        _short_wakes(3), encoding="utf-8"
    )
    _post(workspace)
    root = Path(workspace.root)
    _columns, rows = _table(_one(root, "farfield/*_trefftz.csv"))
    (b,) = [row for row in rows if row["VARIANT"] == "B"]
    assert b["FAMILY"] == "TOTAL"
    assert {b[c] for c in ("CL_T", "CDI_T", "CY_T", "E_T", "GAMMA_SCALE")} == {"NA"}
    assert b["X_T_M"] != "NA"
    said = [line for line in _warnings_of(root) if "wake lines end before the plane" in line]
    # The WARNING of the step and the line of its named skip, each saying it in full.
    assert len(said) == 2, said
    reach = 3.0 * math.cos(math.radians(wing.ALPHA))  # 3 m of wake, along the free stream
    for line in said:
        assert "3 of 159 wake lines end before the plane" in line
        assert f"the recorded wake is {reach:.4g} m long on its shortest line" in line
    skipped = _manifest(root)["skipped"]
    assert any("variant=wake" in key for key in skipped)


# ----------------------------------------------------------------- FR-453 R7


@pytest.mark.requirement("FR-453")
@pytest.mark.parametrize(("mach", "warned"), [(0.5, True), (0.2, False)])
def test_p0400_ffproof_above_mach_0_3_the_c_row_is_warned(tmp_path, mach, warned):
    """P0400-FFPROOF (FR-453 R7): the C row is written, with the incompressible WARNING above 0.3.

    The same recorded point at Mach 0.5 and at Mach 0.2: both write their C
    row; only the first writes the WARNING that the incompressible relations
    of the definitions page are used.
    """
    workspace = wing._workspace(tmp_path, farfield=True)
    _set_record(workspace, mach=mach)
    _post(workspace)
    root = Path(workspace.root)
    _columns, rows = _table(_one(root, "farfield/*_trefftz.csv"))
    (c,) = [row for row in rows if row["VARIANT"] == "C"]
    assert c["CDI_T"] != "NA"
    said = [line for line in _warnings_of(root) if "incompressible relations" in line]
    assert len(said) == (1 if warned else 0), said
    if warned:
        assert "Mach 0.5" in said[0] and "Trefftz C" in said[0]


# ------------------------------------------------- FR-456 R1, R4 and FR-38 R1 to R3


@pytest.mark.requirement("FR-456")
@pytest.mark.requirement("FR-38")
def test_p0400_ffproof_post_writes_the_ledgers_table(tmp_path):
    """P0400-FFPROOF (FR-456 R1, R4; FR-38 R1 to R3): ``farfield/<group>_ledgers.csv``.

    A steady point whose probe export holds the survey lattice in a uniform
    stream: one row per station, the columns of R4 in order, the mass flow
    constant over the stations, the control-volume columns NA on the inlet
    row and zero on the next, the gate columns written; the file sits beside
    the polar by name and its manifest entry names the analysis and the run.
    """
    workspace = _campaign(
        tmp_path,
        pproc=_LEDGERS,
        files={f"{_STEM}_probes.txt": _probe_export(_POINTS_M, 20.0)},
    )
    _post(workspace)
    root = Path(workspace.root)
    path = _one(root, "farfield/*_ledgers.csv")
    polar = _one(root, "polars/P*.csv")
    group = polar.stem.rsplit("_", 1)[0]
    assert path.name == f"{group}_ledgers.csv", "beside the polar, by name (R1)"
    columns, rows = _table(path)
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
    entry = _entry(_manifest(root), "_ledgers.csv")
    assert entry["analysis"] == "ledgers" and entry["runs"] == [_RUN]
    assert "reduction" not in entry, "a steady row's table is neither instant nor average"


# ------------------------------------------------- FR-38 R7 and FR-456 R1


@pytest.mark.requirement("FR-38")
@pytest.mark.requirement("FR-456")
def test_p0400_ffproof_an_unsteady_row_writes_the_instant_and_the_average(tmp_path):
    """P0400-FFPROOF (FR-38 R7, FR-456 R1): two ledgers files, each labelled.

    An ``unsteady`` row of eight steps whose window is ``LAST_ITERS_AVG: 4``
    (steps 5 to 8), its lattice sampled by fluid plots at every step in a
    stream of 10 + step m/s. The instant is step 8; the average is the mean
    of the four steps' balances, so its mass flow is 16.5/18 of the instant's
    (14.5/18 would be the whole run, 18/18 the last step). Each file names its
    reduction in its name and in its manifest entry.
    """
    count = len(_POINTS_M)
    workspace = _campaign(
        tmp_path,
        pproc=_LEDGERS,
        files={f"{_STEM}_plots.txt": _plots_export(count, 8)},
        recipe="unsteady",
        reductions=_WINDOW,
        positions=True,
    )
    _post(workspace)
    root = Path(workspace.root)
    instant = _one(root, "farfield/*_ledgers_instant.csv")
    average = _one(root, "farfield/*_ledgers_average.csv")
    assert not list(root.rglob("farfield/*_ledgers.csv"))
    columns, now = _table(instant)
    assert columns == ["POL", "STEP", *CONTEXT_COLUMNS, *LEDGER_COLUMNS]
    _columns, mean = _table(average)
    assert {row["STEP"] for row in now} == {"8"}
    assert {row["STEP"] for row in mean} == {"AVERAGE"}
    for last, window in zip(now, mean, strict=True):
        ratio = float(window["MDOT_KG_S"]) / float(last["MDOT_KG_S"])
        assert ratio == pytest.approx(16.5 / 18.0, rel=1e-6)
        assert abs(ratio - 14.5 / 18.0) > 0.05, "the whole run is not the window"
    manifest = _manifest(root)
    assert _entry(manifest, "_ledgers_instant.csv")["reduction"] == "instant"
    assert _entry(manifest, "_ledgers_average.csv")["reduction"] == "average"


# ----------------------------------------------------------------- FR-455 R9


@pytest.mark.requirement("FR-455")
def test_p0400_ffproof_a_normal_declaration_gives_the_instant_only(tmp_path):
    """P0400-FFPROOF (FR-455 R9): a reused ``kind = "normal"`` lattice holds the last step.

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
    workspace = _campaign(
        tmp_path,
        pproc=probes + _LEDGERS,
        files={f"{_STEM}_probes.txt": _probe_export(_POINTS_M, _speed(8))},
        recipe="unsteady",
        reductions=_WINDOW,
    )
    _post(workspace)
    root = Path(workspace.root)
    _columns, now = _table(_one(root, "farfield/*_ledgers_instant.csv"))
    assert {row["STEP"] for row in now} == {"8"}
    area = float(now[0]["MDOT_KG_S"]) / (_RHO * _speed(8))
    assert area > 0.0 and now[1]["FX_N"] != "NA"
    assert not list(root.rglob("farfield/*_ledgers_average.csv"))
    skipped = _manifest(root)["skipped"]
    (reason,) = [v for k, v in skipped.items() if k.startswith("farfield/average#point=")]
    assert 'kind = "normal"' in reason and "last time step" in reason
    assert any('kind = "normal"' in line for line in _warnings_of(root))
