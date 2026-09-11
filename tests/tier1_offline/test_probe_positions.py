"""Tier 1: a probe table says where each point IS, beside what the flow did (FR-91).

Her instruction of 2026-09-11: "eu quero que tenha uma arquivo csv com o
resultado das probes e a posicao xyz delas + frame de referencia junto ao
resultado do fluido (velocidade, mach, etc). Isso vai ficar transparente se foi
gerado com steady ou unsteady, e pro unsteady, e importante ter o arquivo de
posicao porque nao vem escrito no unsteady plots."

THE DEFECT IS VISIBLE IN A REAL EXPORT'S HEADER. A recorded unsteady plots
table of this estate opens::

    Time-step,CL_MRP_TOTAL,...,MACH1,VELOCITY1,VX1,VY1,VZ1,STATIC_PRESSURE_RATIO1,MACH2,...

One numbered group per probe point, and nothing anywhere in the file says where
point 7 is. A reader holding that table cannot place a single sample, which is
what makes it a table of numbers about nowhere.

WHAT IS ASSERTED HERE is that the position recorded is the position EMITTED --
the same loop writes both, so they cannot drift -- and that the SPINE of the
written table is identical whichever run type filled it. The fluid columns are
deliberately not identical, and that is her decision: "leva todas as fluid
properties e tudo o que steady probes devolve, isso inclui ate informacao de
boundary layer". A steady export carries the boundary layer and an unsteady one
carries a static pressure ratio; forcing one column set would mean dropping what
she asked to keep.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases import ProbeLine, ProbesSpec
from pyflightstream.post.products import (
    PROBE_SPINE,
    read_csv_table,
    read_probe_positions,
    write_probes_table,
    write_unsteady_probes_table,
)
from pyflightstream.run import _write_probe_points

FIXTURES = Path(__file__).parent / "fixtures"


def positions_file(tmp_path: Path, rows: list[tuple[int, float, float, float, str]]) -> Path:
    """A probe positions file as the run stage writes it."""
    sim_dir = tmp_path / "sim_1"
    relative = _write_probe_points(sim_dir, "1", rows)
    assert relative is not None
    return sim_dir / relative


# --------------------------------------------------------------------------
# The file the run writes
# --------------------------------------------------------------------------


def test_a_row_that_places_no_probe_point_writes_no_file(tmp_path):
    """Every row that declares none, and every row citing a user's points file.

    The package does not parse a survey she wrote in order to re-state it,
    so it has nothing to record, and an empty file promising positions is
    worse than no file.
    """
    assert _write_probe_points(tmp_path / "sim_1", "1", []) is None
    assert not (tmp_path / "sim_1" / "profiles").exists()


def test_the_positions_go_under_profiles_per_sim(tmp_path):
    """Her answer: "o probe txt ... por sim ... vai para dentro da pasta sim/profiles"."""
    relative = _write_probe_points(tmp_path / "sim_1", "6002", [(1, 0.0, 1.0, 2.0, "PUSHER_SMRP")])
    assert relative == "profiles/6002_probe_points.csv"


def test_the_positions_read_back_keyed_by_the_vertex_number(tmp_path):
    """The key is the suffix the unsteady fluid plot carries in its own name."""
    path = positions_file(
        tmp_path,
        [(1, 0.0, 1.0, 2.0, "PUSHER_SMRP"), (2, 0.5, 1.0, 2.0, "PUSHER_SMRP")],
    )
    assert read_probe_positions(path) == {
        1: (0.0, 1.0, 2.0, "PUSHER_SMRP"),
        2: (0.5, 1.0, 2.0, "PUSHER_SMRP"),
    }


def test_a_run_recorded_before_this_release_reads_as_no_positions(tmp_path):
    """An absent file is an EMPTY MAPPING and never a refusal.

    Every run recorded before 0.16.0 has none, and refusing them would take
    a product away from a campaign that already happened.
    """
    assert read_probe_positions(tmp_path / "nothing-here.csv") == {}


def test_a_file_that_is_not_a_positions_table_reads_as_none_of_them(tmp_path):
    """A reader that guessed at a stranger's columns would place points wrongly."""
    stranger = tmp_path / "stranger.csv"
    stranger.write_text("A,B\n1,2\n", encoding="utf-8")
    assert read_probe_positions(stranger) == {}


# --------------------------------------------------------------------------
# The steady table
# --------------------------------------------------------------------------


def test_the_steady_table_keeps_the_export_coordinates_and_gains_the_frame(tmp_path):
    """A steady export states X, Y and Z and never states WHICH FRAME.

    So the export's own coordinates are kept -- they are the solver's
    answer about the point it sampled -- and the recorded positions supply
    the frame name, which no export carries at all.

    THE FIXTURE'S POSITIONS DISAGREE WITH THE EXPORT ON PURPOSE: the
    recorded first point is at the origin and the export's is not, so a
    writer that preferred the record over the export fails here.
    """
    export = (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8")
    recorded = read_probe_positions(positions_file(tmp_path, [(1, 0.0, 0.0, 0.0, "PUSHER_SMRP")]))
    written = write_probes_table(tmp_path / "p_probes.csv", export, positions=recorded)
    assert written is not None
    columns, rows = read_csv_table(written)
    assert tuple(columns[: len(PROBE_SPINE)]) == PROBE_SPINE
    first = rows[0]
    assert float(first["X"]) == pytest.approx(-0.5)
    assert float(first["Y"]) == pytest.approx(2.0)
    assert float(first["Z"]) == pytest.approx(-0.6)
    assert first["FRAME"] == "PUSHER_SMRP"
    assert first["STEP"] == ""
    assert int(float(first["PROBE"])) == 1


def test_the_steady_table_carries_the_boundary_layer_columns_she_asked_for(tmp_path):
    """Her answer on which quantities: everything the steady probe returns."""
    export = (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8")
    written = write_probes_table(tmp_path / "p_probes.csv", export, positions={})
    assert written is not None
    columns, _ = read_csv_table(written)
    for column in ("Mach", "Cp", "vtot", "momentum_thickness", "disp_thick", "CF", "Transition"):
        assert column in columns, column


def test_the_coordinate_columns_appear_once(tmp_path):
    """Two pairs of X, Y, Z would invite the question of which to trust.

    The answer would have to be "they are the same", which is a thing to
    assert rather than a thing to ship twice.
    """
    export = (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8")
    written = write_probes_table(tmp_path / "p_probes.csv", export, positions={})
    assert written is not None
    columns, _ = read_csv_table(written)
    for axis in ("X", "Y", "Z"):
        assert list(columns).count(axis) == 1, (axis, columns)


def test_a_steady_table_of_a_run_with_no_recorded_positions_still_writes(tmp_path):
    """The position columns come from the export; only the frame goes blank."""
    export = (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8")
    written = write_probes_table(tmp_path / "p_probes.csv", export, positions={})
    assert written is not None
    _, rows = read_csv_table(written)
    assert rows[0]["FRAME"] == ""
    assert float(rows[0]["X"]) == pytest.approx(-0.5)


# --------------------------------------------------------------------------
# The unsteady table, which is the half that could not be read at all
# --------------------------------------------------------------------------


def plots_table(path: Path, extra: dict[str, float] | None = None) -> Path:
    """An unsteady plots table shaped like a recorded one: forces, then groups."""
    columns = ["Time-step", "CL_MRP_TOTAL", *sorted(extra or {}), "MACH1", "VX1", "MACH2", "VX2"]
    rows = []
    for step in (1, 2):
        values = {
            "Time-step": float(step),
            "CL_MRP_TOTAL": 0.2 + step,
            "MACH1": 0.10 + step,
            "VX1": 70.0 + step,
            "MACH2": 0.20 + step,
            "VX2": 80.0 + step,
            **(extra or {}),
        }
        rows.append(",".join(f"{values[name]:.5f}" for name in columns))
    path.write_text(",".join(columns) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_the_unsteady_table_places_every_sample_it_carries(tmp_path):
    """The whole requirement, in one assertion set.

    Two probe points over two steps is four rows, each carrying the
    position of ITS point and the step it came from, which is exactly what
    the plots export cannot say.
    """
    recorded = read_probe_positions(
        positions_file(
            tmp_path,
            [(1, 0.0, 1.0, 2.0, "PUSHER_SMRP"), (2, 0.5, 1.0, 2.0, "PUSHER_SMRP")],
        )
    )
    written = write_unsteady_probes_table(
        tmp_path / "p_probes.csv",
        plots_table(tmp_path / "p_plots.csv"),
        positions=recorded,
        parameters=["MACH", "VX"],
    )
    assert written is not None
    columns, rows = read_csv_table(written)
    assert tuple(columns) == (*PROBE_SPINE, "MACH", "VX")
    assert len(rows) == 4
    placed = {
        (int(float(row["PROBE"])), int(float(row["STEP"]))): (
            float(row["X"]),
            float(row["MACH"]),
        )
        for row in rows
    }
    assert placed[(1, 1)] == (pytest.approx(0.0), pytest.approx(1.10))
    assert placed[(2, 1)] == (pytest.approx(0.5), pytest.approx(1.20))
    assert placed[(1, 2)] == (pytest.approx(0.0), pytest.approx(2.10))
    assert placed[(2, 2)] == (pytest.approx(0.5), pytest.approx(2.20))
    assert {row["FRAME"] for row in rows} == {"PUSHER_SMRP"}


def test_a_force_column_of_a_family_whose_name_ends_in_a_digit_is_not_a_probe(tmp_path):
    """The column set is composed FORWARD and never read backward off the header.

    A geometry with a family called `Blade1` writes `CL_MRP_Blade1`, which
    a pattern reads as parameter `CL_MRP_Blade` of vertex 1 and joins to
    the survey. The declared parameters are `MACH` and `VX`, so the
    forward construction never asks for it.
    """
    recorded = read_probe_positions(positions_file(tmp_path, [(1, 0.0, 1.0, 2.0, "MRP")]))
    written = write_unsteady_probes_table(
        tmp_path / "p_probes.csv",
        plots_table(tmp_path / "p_plots.csv", extra={"CL_MRP_Blade1": 0.33}),
        positions=recorded,
        parameters=["MACH", "VX"],
    )
    assert written is not None
    columns, _ = read_csv_table(written)
    assert "CL_MRP_Blade" not in columns
    assert tuple(columns) == (*PROBE_SPINE, "MACH", "VX")


def test_a_plots_table_carrying_no_group_of_the_declared_parameters_writes_nothing(tmp_path):
    """A file of a spine and nothing else promises content that is not there."""
    recorded = read_probe_positions(positions_file(tmp_path, [(1, 0.0, 1.0, 2.0, "MRP")]))
    assert (
        write_unsteady_probes_table(
            tmp_path / "p_probes.csv",
            plots_table(tmp_path / "p_plots.csv"),
            positions=recorded,
            parameters=["PRESSURE"],
        )
        is None
    )


def test_a_run_with_no_recorded_positions_writes_no_unsteady_probe_table(tmp_path):
    """Without the positions there is nothing this table adds to the plots table."""
    assert (
        write_unsteady_probes_table(
            tmp_path / "p_probes.csv",
            plots_table(tmp_path / "p_plots.csv"),
            positions={},
            parameters=["MACH", "VX"],
        )
        is None
    )


# --------------------------------------------------------------------------
# The transparency the requirement is actually about
# --------------------------------------------------------------------------


def test_a_steady_table_and_an_unsteady_one_open_with_the_same_spine(tmp_path):
    """A reader must not have to know the run type to place the data.

    THE SPINE IS WHAT IS IDENTICAL and the fluid columns are not, which is
    her decision rather than a shortfall: a steady export returns the
    boundary layer and an unsteady one returns a static pressure ratio, and
    "leva todas as fluid properties e tudo o que steady probes devolve"
    means keeping both sets rather than intersecting them.
    """
    recorded = read_probe_positions(
        positions_file(
            tmp_path,
            [(1, 0.0, 1.0, 2.0, "PUSHER_SMRP"), (2, 0.5, 1.0, 2.0, "PUSHER_SMRP")],
        )
    )
    steady = write_probes_table(
        tmp_path / "steady_probes.csv",
        (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8"),
        positions=recorded,
    )
    unsteady = write_unsteady_probes_table(
        tmp_path / "unsteady_probes.csv",
        plots_table(tmp_path / "p_plots.csv"),
        positions=recorded,
        parameters=["MACH", "VX"],
    )
    assert steady is not None and unsteady is not None
    steady_columns, _ = read_csv_table(steady)
    unsteady_columns, _ = read_csv_table(unsteady)
    assert tuple(steady_columns[: len(PROBE_SPINE)]) == PROBE_SPINE
    assert tuple(unsteady_columns[: len(PROBE_SPINE)]) == PROBE_SPINE


# --------------------------------------------------------------------------
# The register the builder fills, which is what makes all of the above true
# --------------------------------------------------------------------------


def test_the_recorded_position_is_the_emitted_position(tmp_path):
    """One loop, two consumers, so they cannot drift.

    The alternative was to re-derive the coordinates in the post stage from
    the same artifact, through the same line, rectangle and circle layouts:
    a second author of one fact, which disagrees with the first the week
    either is touched.

    Asserted by reading the EMITTED vertex out of the script text and
    comparing it against what the register recorded for the same number.
    """
    from pyflightstream.cases import PprocSpec, ReferenceData, SimCase, SweepAxis
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script

    geometry = tmp_path / "g.fsm"
    geometry.write_text("nothing\n", encoding="utf-8")
    case = SimCase(
        sim_id="7001",
        aircraft="WB",
        recipe="unsteady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={
            "WORKFLOW": "unsteady",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.001",
            "TIME_ITERATIONS": "3",
        },
        geometry=str(geometry),
        outputs=["loads_a+00.0.txt"],
        # The MRP frame is created from the reference, so the entry can cite it.
        reference=ReferenceData(area=8.0, length=1.0, span_m=4.0, moment_point_m=(0.0, 0.0, 0.0)),
        pproc=PprocSpec(
            probes=[
                ProbesSpec(
                    frame="MRP",
                    parameters=["MACH"],
                    points=3,
                    lines=[ProbeLine(start=[0.0, 0.0, 0.0], end=[1.0, 0.0, 0.0])],
                )
            ]
        ),
        point={"alpha": 0.0},
    )
    script = Script("26.123")
    build_script(case, script)
    text = script.render()

    # WHAT THE SCRIPT ACTUALLY SAYS, read back out of the rendered text: the
    # plot named `MACH<k>` is followed by the `VERTEX` line that places it.
    lines = text.splitlines()
    emitted = {
        lines[index][len("NAME MACH") :]: lines[index + 1]
        for index, line in enumerate(lines)
        if line.startswith("NAME MACH")
    }
    assert len(script.probe_points) == 3
    assert set(emitted) == {"1", "2", "3"}
    for vertex, x, y, z, frame in script.probe_points:
        assert frame == "MRP"
        assert emitted[str(vertex)] == f"VERTEX {x} {y} {z}", (vertex, emitted[str(vertex)])
    # The three points of one line with both ends included, which is also
    # what makes the assertion above discriminate: the three positions are
    # different, so a register that recorded one point three times, or that
    # paired the numbers with the wrong coordinates, fails here.
    assert [entry[1] for entry in script.probe_points] == [0.0, 0.5, 1.0]


def test_a_point_whose_group_is_only_half_present_is_left_out(tmp_path):
    """A group is all of its columns or none of it.

    A point that reached the plots table with `MACH2` and no `VX2` has a
    sample of one quantity and not of the other, and a row carrying the
    first with a blank where the second belongs reads as a measured
    absence. The point is left out and the ones that are whole are kept.
    """
    recorded = read_probe_positions(
        positions_file(
            tmp_path,
            [(1, 0.0, 1.0, 2.0, "MRP"), (2, 0.5, 1.0, 2.0, "MRP")],
        )
    )
    # A plots table that lost one column of point 2's group.
    plots = tmp_path / "p_plots.csv"
    plots.write_text(
        "Time-step,MACH1,VX1,MACH2\n1.00000,0.10000,70.00000,0.20000\n",
        encoding="utf-8",
    )
    written = write_unsteady_probes_table(
        tmp_path / "p_probes.csv", plots, positions=recorded, parameters=["MACH", "VX"]
    )
    assert written is not None
    _, rows = read_csv_table(written)
    assert [int(float(row["PROBE"])) for row in rows] == [1]


def test_a_positions_table_whose_columns_are_in_another_order_still_reads(tmp_path):
    """Read by NAME, never by position, so a reordered header is not a stranger."""
    path = tmp_path / "reordered.csv"
    path.write_text("FRAME,Z,Y,X,PROBE\nMRP,2.0,1.0,0.0,1\n", encoding="utf-8")
    assert read_probe_positions(path) == {1: (0.0, 1.0, 2.0, "MRP")}
