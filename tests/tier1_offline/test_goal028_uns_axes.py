"""The unsteady polar states the axis coefficients, from the plots of the global MRP frame.

THE REQUIREMENT (answer 8b, 2026-09-18). For an unsteady point the axis columns
come from the plot variables exported in the GLOBAL MRP frame: the six components
`FX, FY, FZ, MX, MY, MZ` of a plot group declared in that frame, in Newtons and
Newton metres, AVERAGED over the row's window, made coefficients with the row's own
`RHO`, `VINF`, `SREF` and `CREF`, and turned by the chain the steady polar uses.
Never a rotor's own frame: a force in a rotor frame is not in the geometry's axes.

Without such a group the block is NOT written and the reason is said; a column of
`NA` down a whole table is what this package does not write.

EXPECTED VALUES are the definition, computed here: `C = F / (1/2 rho V^2 S)`, turned
through scipy. Nothing is taken from the module under test.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_goal028_polar_from_the_vector import _oracle  # noqa: E402
from test_post_products import PLOTS_HEADER  # noqa: E402

from pyflightstream.post.products import (  # noqa: E402
    ReferenceValues,
    read_csv_table,
    write_plots_table,
    write_unsteady_polar,
)

REFERENCE = ReferenceValues(sref_m2=50.0, cref_m=2.526, bref_m=20.0)
RHO, VINF = 1.1, 60.0
CONDITION = {"ALPHA": 4.0, "BETA": 6.0, "MACH": 0.18, "RHO": RHO, "VINF": VINF, "VREF": VINF}
AXES = ("CDW CYW CLW CRW CMW CNW CDS CYS CLS CRS CMS CNS CDB CYB CLB CRB CMB CNB").split()
#: Step 1 is outside the window; steps 2 and 3 average to the second tuple.
HISTORY = {
    1: (9000.0, 9000.0, 9000.0, 9000.0, 9000.0, 9000.0),
    2: (110.0, -30.0, 1000.0, 12.0, -28.0, 1.0),
    3: (130.0, -50.0, 1200.0, 16.0, -32.0, 3.0),
}
MEAN = (120.0, -40.0, 1100.0, 14.0, -30.0, 2.0)


class _Point:
    name = "P"


def _plots(tmp_path, groups: tuple[str, ...]) -> Path:
    names = [f"{part}_{group}" for group in groups for part in ("FX", "FY", "FZ", "MX", "MY", "MZ")]
    lines = ["Time-step," + ",".join(names)]
    for step, six in HISTORY.items():
        cells = [f"{value:.4f}" for _group in groups for value in six]
        lines.append(f"{step}.0000," + ",".join(cells) + ",")
    text = PLOTS_HEADER.replace(
        "Reference velocity (m/s)                    100.000",
        "Reference velocity (m/s)                    60.000",
    )  # noqa: E501
    text = text.replace(
        "Freestream velocity (m/s)                   50.000",
        "Freestream velocity (m/s)                   60.000",
    )  # noqa: E501
    export = text + "\n".join(lines) + "\n" + "-" * 60 + "\n     Force Units: Coefficients\n"
    table = write_plots_table(tmp_path / "P_plots.csv", export)
    assert table is not None
    return table


def _written(tmp_path, groups, notes=None, declared=None):
    path = write_unsteady_polar(
        tmp_path / "P0001_x_uns_avg.csv",
        points=[_Point()],
        plots={"P": _plots(tmp_path, groups)},
        window=(2, 3),
        conditions=[CONDITION],
        reference=REFERENCE,
        notes=notes,
        axes_groups=groups if declared is None else declared,
    )
    assert path is not None
    columns, rows = read_csv_table(path)
    return list(columns), rows[0]


def _expected() -> dict[str, float]:
    force_unit = 0.5 * RHO * VINF**2 * REFERENCE.sref_m2
    force = [value / force_unit for value in MEAN[:3]]
    moment = [value / (force_unit * REFERENCE.cref_m) for value in MEAN[3:]]
    return _oracle(force, moment, 4.0, 6.0)


def test_the_axes_are_the_averaged_newtons_made_coefficients_and_turned(tmp_path):
    columns, row = _written(tmp_path, ("MRP_TOTAL",))
    at = columns.index("CDW")
    assert columns[at : at + 18] == AXES, columns[at : at + 18]
    for name, expected in _expected().items():
        assert float(row[name]) == pytest.approx(expected, abs=5e-6), name
    # The body-axis force IS the averaged force over the dynamic pressure and the area.
    unit = 0.5 * RHO * VINF**2 * REFERENCE.sref_m2
    assert float(row["CDB"]) == pytest.approx(MEAN[0] / unit, abs=5e-6)
    assert math.isfinite(float(row["CLW"]))


def test_two_groups_in_the_global_frame_take_their_groups_name(tmp_path):
    columns, row = _written(tmp_path, ("MRP_TOTAL", "MRP_AIRFRAME"))
    assert "CLW" not in columns
    assert "CLW_TOTAL" in columns and "CLW_AIRFRAME" in columns, columns
    assert row["CLW_TOTAL"] == row["CLW_AIRFRAME"]


def test_a_rotors_own_frame_is_never_the_source_and_the_block_says_why_it_is_absent(tmp_path):
    notes: list[str] = []
    # The pproc declares that group in the ROTOR's frame, so the stage does not name it.
    columns, _row = _written(tmp_path, ("PUSHER_SMRP",), notes, declared=())
    assert not [name for name in columns if name.startswith(("CLW", "CDB"))], columns
    assert len(notes) == 1 and "MRP" in notes[0] and "FX" in notes[0], notes


def test_a_row_stating_no_density_gets_no_axes_and_says_so(tmp_path):
    notes: list[str] = []
    bare = {key: value for key, value in CONDITION.items() if key != "RHO"}
    path = write_unsteady_polar(
        tmp_path / "P0001_x_uns_avg.csv",
        points=[_Point()],
        plots={"P": _plots(tmp_path, ("MRP_TOTAL",))},
        window=(2, 3),
        conditions=[bare],
        reference=REFERENCE,
        notes=notes,
        axes_groups=("MRP_TOTAL",),
    )
    columns, _rows = read_csv_table(path)
    assert "CLW" not in columns
    assert any("RHO" in note for note in notes), notes


def test_the_stage_records_why_an_unsteady_polar_carries_no_axes(tmp_path):
    """The recorded campaign plots no six components in the global frame, and says so."""
    import json

    from test_post_superfile import _MATRIX, _post, _workspace

    workspace = _workspace(tmp_path)
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    stated = _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5")
    (workspace.root / "matriz.fs").write_text(stated, encoding="utf-8")
    written = [Path(path) for path in _post(workspace)]
    (polar,) = [path for path in written if path.name.endswith("_uns_avg.csv")]
    columns, _rows = read_csv_table(polar)
    assert "CLW" not in columns
    (manifest,) = workspace.root.rglob("products.json")
    skipped = json.loads(manifest.read_text(encoding="utf-8"))["skipped"]
    reason = skipped[f"polars/{polar.name}#axes"]
    assert "MRP" in reason and "FX" in reason, reason


def _script_of(tmp_path, plots: dict) -> list[str]:
    from test_workflows import _her_pproc, _wb_geometry, _with_pproc, rendered, unsteady_case

    stated = type(_her_pproc().plots).model_validate(plots)
    pproc = _her_pproc().model_copy(update={"plots": stated})
    case = _with_pproc(unsteady_case(), _wb_geometry(tmp_path), pproc)
    return rendered(case).splitlines()


def _plot_names(lines: list[str]) -> list[str]:
    return [line.split(" ", 1)[1] for line in lines if line.startswith("NAME ")]


def test_a_run_whose_pproc_plots_no_global_frame_six_gets_the_group_added(tmp_path):
    """Without it the unsteady polar of that run could never state its axes."""
    lines = _script_of(
        tmp_path,
        {
            "parameters": ["CL"],
            "groups": [{"name": "MRP_TOTAL", "frame": "MRP", "families": "all"}],
        },
    )
    names = _plot_names(lines)
    for part in ("FX", "FY", "FZ", "MX", "MY", "MZ"):
        assert names.count(f"{part}_MRP_TOTAL") == 1, names
    assert names.count("CL_MRP_TOTAL") == 1, "what the artifact asked for is still there, once"


def test_a_pproc_that_already_plots_them_gets_nothing_added(tmp_path):
    from test_workflows import _her_pproc

    lines = _script_of(tmp_path, _her_pproc().plots.model_dump())
    names = _plot_names(lines)
    assert names.count("FX_MRP_TOTAL") == 1, [n for n in names if n.startswith("FX_")]


def test_the_stage_looks_for_the_groups_the_artifact_puts_in_the_global_frame():
    from test_workflows import _her_pproc

    from pyflightstream.post.products import global_frame_plot_groups

    assert global_frame_plot_groups(_her_pproc()) == ("MRP_TOTAL", "MRP_AIRFRAME")
    bare = _her_pproc().model_copy(
        update={"plots": type(_her_pproc().plots).model_validate({"parameters": ["CL"]})}
    )
    assert global_frame_plot_groups(bare) == ("MRP_TOTAL",), "the group the run adds"


def test_a_component_the_artifact_already_plots_in_that_group_is_not_plotted_twice(tmp_path):
    """Two plots under one name are one plot to the solver, and the second would win."""
    lines = _script_of(
        tmp_path,
        {
            "parameters": ["CL", "FX"],
            "groups": [{"name": "MRP_TOTAL", "frame": "MRP", "families": "all"}],
        },
    )
    names = _plot_names(lines)
    for part in ("FX", "FY", "FZ", "MX", "MY", "MZ"):
        assert names.count(f"{part}_MRP_TOTAL") == 1, (part, names)


def test_a_global_frame_group_that_lacks_the_six_is_not_what_the_stage_looks_for():
    from test_workflows import _her_pproc

    from pyflightstream.post.products import global_frame_plot_groups

    plots = type(_her_pproc().plots).model_validate(
        {
            "parameters": ["CL"],
            "groups": [{"name": "MRP_AIRFRAME", "frame": "MRP", "families": ["W", "B"]}],
        }
    )
    partial = _her_pproc().model_copy(update={"plots": plots})
    assert global_frame_plot_groups(partial) == ("MRP_TOTAL",)
