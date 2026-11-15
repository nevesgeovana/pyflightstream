"""The unsteady polar states the axis coefficients, from the plots of the global MRP frame.

THE REQUIREMENT (answer 8b, 2026-09-18). For an unsteady point the axis columns
come from the plot variables exported in the GLOBAL MRP frame: the six components
`FX, FY, FZ, MX, MY, MZ` of a plot group declared in that frame, in Newtons and
Newton metres, AVERAGED over the row's window, made coefficients with the row's own
`RHO`, `VINF`, `SREF` and `CREF`, and turned by the chain the steady polar uses.
Never a rotor's own frame: a force in a rotor frame is not in the geometry's axes.

Since 0.58.0 the unsteady polar is the family and group files of ``polars/`` (design
of the post outputs, 2.2 and 4.8): the axis coefficients are the bare names
`CDW .. CnB` of the group's ACOEF file, no column carries a group suffix, and a row
without what it needs is ``NA`` and said, never a column dropped.

EXPECTED VALUES are the definition, computed here: `C = F / (1/2 rho V^2 S)`, turned
through scipy. Nothing is taken from the module under test.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest

from pyflightstream.post.products import ReferenceValues, read_csv_table, write_plots_table
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _loads, _workspace

REFERENCE = ReferenceValues(sref_m2=50.0, cref_m=2.526, bref_m=20.0)
RHO, VINF = 1.1, 60.0
#: The names the axis coefficients carry in a group's ACOEF file, wind, stability, body.
AXES = ("CDW CYW CLW ClW CmW CnW CDS CYS CLS ClS CmS CnS CDB CYB CLB ClB CmB CnB").split()
#: The oracle's keys (`CR` is the rolling moment, `CM` pitching, `CN` yawing) and the file's.
_KEY_TO_COLUMN = {"CR": "Cl", "CM": "Cm", "CN": "Cn"}

#: Step 1 is outside the window; steps 2 and 3 average to the second tuple.
HISTORY = {
    1: (9000.0, 9000.0, 9000.0, 9000.0, 9000.0, 9000.0),
    2: (110.0, -30.0, 1000.0, 12.0, -28.0, 1.0),
    3: (130.0, -50.0, 1200.0, 16.0, -32.0, 3.0),
}
MEAN = (120.0, -40.0, 1100.0, 14.0, -30.0, 2.0)
SIX = ("FX", "FY", "FZ", "MX", "MY", "MZ")


CONDITION = {"ALPHA": 4.0, "BETA": 6.0, "MACH": 0.18, "RHO": RHO, "VINF": VINF, "VREF": VINF}


class _Point:
    name = "P"


def _plots(tmp_path, groups: tuple[str, ...]) -> Path:
    """A written plots table of ``groups`` over `HISTORY` (other test modules borrow it)."""
    names = [f"{part}_{group}" for group in groups for part in SIX]
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
    export = (
        text
        + "\n".join(lines)
        + "\n"
        + "-" * 60
        + "\n     Force Units: Coefficients\nSoftware : Flightstream version 26.1, build #7012026\n"
    )
    table = write_plots_table(tmp_path / "P_plots.csv", export)
    assert table is not None
    return table


def _column(key: str) -> str:
    """The column an oracle key is published under: `CMW` is `CmW`."""
    return _KEY_TO_COLUMN.get(key[:2], key[:2]) + key[2:]


def six_history(group: str = "MRP_TOTAL") -> dict[str, list[float]]:
    """The plots of one group over `HISTORY`'s three steps, step 1 outside the window."""
    columns: dict[str, list[float]] = {"steps": list(HISTORY)}
    for index, part in enumerate(SIX):
        columns[f"{part}_{group}"] = [six[index] for six in HISTORY.values()]
    return columns


def _export(history: dict[str, list[float]]) -> str:
    """A raw unsteady plots export of ``history``: ``steps`` is its clock, the rest its columns."""
    columns = {name: values for name, values in history.items() if name != "steps"}
    count = len(next(iter(columns.values())))
    steps = history.get("steps") or list(range(1, count + 1))
    table = "Time-step," + ",".join(columns) + "\n" + "-" * 70 + "\n"
    for index, step in enumerate(steps):
        cells = ",".join(f"{values[index]:.4f}" for values in columns.values())
        table += f"{step}.0000,{cells},\n"
    return (
        PLOTS_HEADER
        + table
        + "-" * 70
        + "\n     Force Units: Coefficients\nSoftware : Flightstream version 26.1, build #7012026\n"
    )


def posted_unsteady(
    tmp_path,
    histories,
    *,
    window,
    velocity=VINF,
    density=RHO,
    alpha=4.0,
    beta=6.0,
    drop_attitude=False,
):
    """Post a campaign whose unsteady simulation 6002 has one point per entry of ``histories``.

    Each entry is the plots history of one point (see `_export`), or None for a point that
    exported no plots. The row's window is ``window``: its last step is the run's length and
    its length one revolution, ``LAST_REVS_AVG: 1.0``. Returns the workspace, its ``polars/``
    folder and the warnings the post said.
    """
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import RunRecord

    workspace = _workspace(tmp_path)
    first, last = window
    span = last - first + 1
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 1.0"), encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    base = next(record for record in records if record.sim_id == "6002")
    for record in records:
        if record.sim_id != "6002":
            workspace.append_record(RunRecord(**record.model_dump()))
    outputs_dir = workspace.sim_dir("6002") / "outputs"
    for index, history in enumerate(histories):
        stem = f"POLAR-6002_M14AL+000BE+000J+{170 + index}"
        name = f"M144RE438AL+000BE+000J+{170 + index}"
        plan = dict(base.reductions or {})
        plan.update(time_iterations=last, steps_per_revolution=float(span))
        plan["rotors"] = {
            "PUSHER": {**plan["rotors"]["PUSHER"], "steps_per_revolution": float(span)}
        }
        text = _loads(alpha, velocity=f"{velocity:.3f}", mode="Unsteady").replace(
            "Side-slip angle (Deg)                       .000",
            f"Side-slip angle (Deg)                       {beta:.3f}",
        )
        if drop_attitude:
            text = "\n".join(
                line
                for line in text.splitlines()
                if "Angle of attack" not in line and "Side-slip" not in line
            )
        (outputs_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
        outputs = [f"outputs/{stem}.txt"]
        if history is not None:
            (outputs_dir / f"{stem}_plots.txt").write_text(_export(history), encoding="utf-8")
            outputs.append(f"outputs/{stem}_plots.txt")
        workspace.append_record(
            RunRecord(
                **{
                    **base.model_dump(),
                    "run_id": f"camp/sim_6002/{name}",
                    "point_name": name,
                    "point": {"alpha": alpha, "beta": beta, "advance_ratio": 1.7 + 0.01 * index},
                    "density_kg_m3": density,
                    "velocity_requested_m_s": velocity,
                    "outputs": outputs,
                    "reductions": plan,
                }
            )
        )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    polars = workspace.root / "post" / "matriz" / "polars"
    return workspace, polars, [str(w.message) for w in caught]


def skipped_by_the_post(workspace) -> dict[str, str]:
    """What the post said it did not write, from the manifest's `skipped` section."""
    manifest = json.loads(
        (workspace.root / "post" / "matriz" / "products.json").read_text(encoding="utf-8")
    )
    return dict(manifest.get("skipped", {}))


def _written(tmp_path, group="MRP_TOTAL", name="P6002-TOTAL-ACOEF.csv", **options):
    """The first row of one polar file of a one-point unsteady simulation over `HISTORY`."""
    _workspace_, polars, said = posted_unsteady(
        tmp_path, [six_history(group)], window=(2, 3), **options
    )
    columns, rows = read_csv_table(polars / name)
    return list(columns), rows[0], said


def _expected() -> dict[str, float]:
    force_unit = 0.5 * RHO * VINF**2 * REFERENCE.sref_m2
    force = [value / force_unit for value in MEAN[:3]]
    # The oracle normalises the moment by the span or the chord itself (the airframe
    # coefficients of the ACOEF files take N and N m), so it is given over q S only.
    moment = [value / force_unit for value in MEAN[3:]]
    # imported here: that module skips itself without scipy, and an import at the top
    # would skip every scipy-free test of every module that borrows this one's helpers
    from tests.tier1_offline.test_goal028_polar_from_the_vector import _oracle

    return _oracle(force, moment, 4.0, 6.0)


def test_the_axes_are_the_averaged_newtons_made_coefficients_and_turned(tmp_path):
    columns, row, _said = _written(tmp_path)
    at = columns.index("CDW")
    assert columns[at : at + 18] == AXES, columns[at : at + 18]
    for name, expected in _expected().items():
        assert float(row[_column(name)]) == pytest.approx(expected, abs=5e-6), name
    # The body-axis force IS the averaged force over the dynamic pressure and the area.
    unit = 0.5 * RHO * VINF**2 * REFERENCE.sref_m2
    assert float(row["CDB"]) == pytest.approx(MEAN[0] / unit, abs=5e-6)
    assert math.isfinite(float(row["CLW"]))
    # The group is the file's, not the column's: no name carries the plot group's.
    assert not [name for name in columns if name.endswith(("_MRP_TOTAL", "_TOTAL"))], columns


def test_two_groups_in_the_global_frame_take_their_groups_file_and_no_suffix(tmp_path):
    """Design 2.3: `CLW_<GROUP>` is `CLW` in the group file of `<GROUP>`."""
    parts = {}
    for group in ("MRP_TOTAL", "MRP_W", "MRP_B"):
        for name, values in six_history(group).items():
            parts[name] = values
    _workspace_, polars, _said = posted_unsteady(tmp_path, [parts], window=(2, 3))
    total_columns, total = read_csv_table(polars / "P6002-TOTAL-ACOEF.csv")
    air_columns, air = read_csv_table(polars / "P6002-AIRFRAME-ACOEF.csv")
    for columns in (total_columns, air_columns):
        assert "CLW" in columns and "CLW_MRP_TOTAL" not in columns, columns
        assert not [name for name in columns if name.startswith("CLW_")], columns
    assert {row["GROUP"] for row in total} == {"TOTAL"}
    assert {row["GROUP"] for row in air} == {"AIRFRAME"}
    assert total[0]["CLW"] == air[0]["CLW"]


@pytest.mark.parametrize("axes,suffix", [("wind", "W"), ("stability", "S")])
def test_p0410_rv2_selected_axes_preserve_unsteady_plot_groups(tmp_path, axes, suffix):
    from pyflightstream.post.polar import selected_axes

    _written(tmp_path)
    path = tmp_path / "camp" / "post" / "matriz" / "polars" / "P6002-TOTAL-ACOEF.csv"
    original_columns, original = read_csv_table(path)
    original = dict(original[0])
    selected_axes(path, axes)
    columns, rows = read_csv_table(path)
    assert len(columns) == len(set(columns))
    assert {key: rows[0][key] for key in original_columns} == original
    # The group is the file's, so the selected quantities are the bare names.
    for quantity in ("CD", "CY", "CL"):
        assert rows[0][quantity] == rows[0][f"{quantity}{suffix}"]
    assert rows[0]["polar_axes"] == axes


def test_p0410_rv2_selected_axes_keep_existing_solver_plot_coefficients(tmp_path):
    import csv

    from pyflightstream.post.polar import selected_axes

    columns, row, _said = _written(tmp_path)
    path = tmp_path / "camp" / "post" / "matriz" / "polars" / "P6002-TOTAL-ACOEF.csv"
    row["CL"] = "7.25"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*columns, "CL"])
        writer.writeheader()
        writer.writerow(row)
    before = path.read_bytes()
    # The solver's own `CL` is never replaced: the selection refuses and leaves the table.
    with pytest.raises(ValueError, match="polar axes"):
        selected_axes(path, "wind")
    assert path.read_bytes() == before
    _, rows = read_csv_table(path)
    assert rows[0]["CL"] == "7.25"


@pytest.mark.parametrize("damage", ["missing_component", "collision"])
def test_p0410_rv2_selected_axes_refuse_before_replacing_the_table(tmp_path, damage):
    from pyflightstream.post.polar import selected_axes

    _written(tmp_path)
    path = tmp_path / "camp" / "post" / "matriz" / "polars" / "P6002-TOTAL-ACOEF.csv"
    content = path.read_text(encoding="utf-8")
    if damage == "missing_component":
        content = content.replace(",CYW,", ",other_side_force,")
    else:
        content = content.replace(",CDI,", ",CD,")
    assert content != path.read_text(encoding="utf-8")
    path.write_text(content, encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="polar axes"):
        selected_axes(path, "wind")
    assert path.read_bytes() == before


def test_a_rotors_own_frame_is_never_the_source_and_the_post_says_why_the_axes_are_na(tmp_path):
    # The plots hold the six of a group in the ROTOR's frame only: no group of the global
    # frame, so the axes are NA and the warning names the plot groups that were looked for.
    columns, row, said = _written(tmp_path, group="PUSHER_SMRP")
    assert {row[name] for name in AXES} == {"NA"}, row
    (reason,) = [text for text in said if "the plots hold no FX to MZ of plot group" in text]
    assert "MRP" in reason and "FX" in reason and "NA" in reason, reason


def test_a_row_stating_no_density_gets_na_axes_and_says_so(tmp_path):
    columns, row, said = _written(tmp_path, density=None)
    assert {row[name] for name in AXES} == {"NA"}, row
    assert any("RHO" in text for text in said), said


def test_p0440_rb6_07_missing_attitude_refuses_axis_coefficients(tmp_path):
    """Missing attitude refuses axis coefficients; explicitly stated zero is computable."""
    folder = tmp_path / "bare"
    folder.mkdir()
    workspace, polars, _said = posted_unsteady(
        folder, [six_history()], window=(2, 3), drop_attitude=True
    )
    # A loads export that does not state its attitude is refused for the point, by name,
    # and the point is no row of any polar file of the simulation.
    refusals = [text for key, text in skipped_by_the_post(workspace).items() if "6002" in key]
    assert any("Angle of attack" in text for text in refusals), refusals
    assert not (polars / "P6002-TOTAL-ACOEF.csv").exists()
    zero = tmp_path / "zero"
    zero.mkdir()
    columns, row, _said = _written(zero, alpha=0.0, beta=0.0)
    assert math.isfinite(float(row["CLW"])), row
    assert row["ALPHA"] == "0.00000" and row["BETA"] == "0.00000", row


def test_the_stage_records_why_an_unsteady_polar_carries_no_axes(tmp_path):
    """The recorded campaign plots no six components in the global frame, and says so.

    Since 0.58.0 the unsteady polar is the family and group files: a record whose plots
    hold no FX to MZ of a plot group gives ``NA`` axis coefficients for that group and
    one warning naming the plot groups it lacks (design of the post outputs, 4.8).
    """
    import warnings

    from tests.tier1_offline.test_post_superfile import _MATRIX, _post, _workspace

    workspace = _workspace(tmp_path)
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    stated = _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5")
    (workspace.root / "matriz.fs").write_text(stated, encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = [Path(path) for path in _post(workspace)]
    names = {path.name for path in written}
    assert not [name for name in names if name.endswith("_uns_avg.csv")], names
    for name in ("FAM-ACOEF-P6002.csv", "P6002-TOTAL-ACOEF.csv"):
        (path,) = [path for path in written if path.name == name]
        columns, rows = read_csv_table(path)
        assert "CLW" in columns and rows, (name, columns)
        assert {row["CLW"] for row in rows} == {"NA"}, name
    (reason,) = [
        str(w.message)
        for w in caught
        if "the plots hold no FX to MZ of plot group" in str(w.message)
    ]
    assert "MRP_B" in reason and "MRP_W" in reason and "NA" in reason, reason


def _script_of(tmp_path, plots: dict) -> list[str]:
    from tests.tier1_offline.test_workflows import (
        _her_pproc,
        _wb_geometry,
        _with_pproc,
        rendered,
        unsteady_case,
    )

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
    from tests.tier1_offline.test_workflows import _her_pproc

    lines = _script_of(tmp_path, _her_pproc().plots.model_dump())
    names = _plot_names(lines)
    assert names.count("FX_MRP_TOTAL") == 1, [n for n in names if n.startswith("FX_")]


def test_the_stage_looks_for_the_groups_the_artifact_puts_in_the_global_frame():
    from pyflightstream.post.products import global_frame_plot_groups
    from tests.tier1_offline.test_workflows import _her_pproc

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
    from pyflightstream.post.products import global_frame_plot_groups
    from tests.tier1_offline.test_workflows import _her_pproc

    plots = type(_her_pproc().plots).model_validate(
        {
            "parameters": ["CL"],
            "groups": [{"name": "MRP_AIRFRAME", "frame": "MRP", "families": ["W", "B"]}],
        }
    )
    partial = _her_pproc().model_copy(update={"plots": plots})
    assert global_frame_plot_groups(partial) == ("MRP_TOTAL",)
