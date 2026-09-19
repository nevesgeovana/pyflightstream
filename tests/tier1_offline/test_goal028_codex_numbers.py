"""Independent release regressions for row, frame, group and reference identity."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pyflightstream.cases import ForcePlotGroup
from pyflightstream.post.products import (
    PolarPoint,
    ProductError,
    ReferenceValues,
    _rotor_tables,
    global_frame_plot_groups,
    read_csv_table,
    rotor_plot_source,
    write_recorded_polar,
    write_rotor_table,
    write_unsteady_polar,
)
from pyflightstream.results import parse_loads
from tests.tier1_offline.test_post_products import LOADS


def test_a_point_override_does_not_replace_the_default_window(tmp_path):
    plots = tmp_path / "history.csv"
    plots.write_text("Time-step,CL_TOTAL\n1,10\n2,20\n3,100\n4,200\n", encoding="utf-8")
    path = write_unsteady_polar(
        tmp_path / "polar.csv",
        points=[SimpleNamespace(name="A"), SimpleNamespace(name="B")],
        plots={"A": plots, "B": plots},
        window=(3, 4),
        windows={"A": (1, 2)},
        conditions=[{}, {}],
        reference=None,
    )
    _, rows = read_csv_table(path)
    assert float(rows[1]["CL_TOTAL"]) == 150.0, (
        "point B must average its default steps 3..4 to 150, not point A's steps 1..2"
    )


@pytest.mark.parametrize(
    "name,frame,families",
    [
        ("ROTOR_PROP", "MRP", ["Wing"]),
        ("ROTOR_PROP", "PROP_SMRP", ["Blade1"]),
        ("ROTOR_{family}", "SMRP", ["PROP"]),
    ],
)
def test_a_declared_generated_name_is_not_proof_of_rotor_membership(name, frame, families):
    pproc = SimpleNamespace(
        plots=SimpleNamespace(
            groups=[ForcePlotGroup(name=name, frame=frame, families=families)],
            parameters=["FX", "FY", "FZ", "MX", "MY", "MZ"],
        )
    )
    candidates, _ = rotor_plot_source(
        pproc, "PROP", rotor_families=["Blade1"], inventory=["Wing", "Blade1"]
    )
    assert "ROTOR_PROP" not in candidates, (
        f"ROTOR_PROP is explicitly {frame} over {families}, not the rotor's global loads"
    )
    # A lift-only declaration occupies none of the automatic six components.
    pproc.plots.parameters = ["CL"]
    candidates, _ = rotor_plot_source(
        pproc, "PROP", rotor_families=["Blade1"], inventory=["Wing", "Blade1"]
    )
    assert "ROTOR_PROP" in candidates


def _recorded(tmp_path, text):
    polar = tmp_path / "POLAR-1"
    point = polar / "P"
    point.mkdir(parents=True)
    (point / "P.txt").write_text(text, encoding="utf-8")
    return polar


@pytest.mark.parametrize("name,frame", [("MRP_TOTAL", "PROP_SMRP"), ("MRP_{family}", "SMRP")])
def test_a_rotor_frame_named_mrp_total_is_not_a_global_axes_source(name, frame):
    pproc = SimpleNamespace(
        plots=SimpleNamespace(
            parameters=["FX", "FY", "FZ", "MX", "MY", "MZ"],
            groups=[ForcePlotGroup(name=name, frame=frame, families=["TOTAL"])],
        )
    )
    assert "MRP_TOTAL" not in global_frame_plot_groups(pproc), (
        "MRP_TOTAL explicitly names a rotor frame; its label cannot establish global axes"
    )
    pproc.plots.parameters = ["CL"]
    assert "MRP_TOTAL" in global_frame_plot_groups(pproc)


@pytest.mark.parametrize("automatic", ["ROTOR_PROP", "MRP_TOTAL"])
def test_a_family_template_that_could_emit_the_automatic_name_is_never_read_as_it(automatic):
    """THE REQUIREMENT MOVED, and this is the test's second expectation.

    Round 2 of the release review (R2-API-1) asked that a `{family}` group over the
    blades never cost the rotor table, and this test first asserted the automatic
    name stayed a source. Meeting that needs the label the builder puts in each
    name, which the post stage cannot derive: three attempts each let a rotor-frame
    or custom-frame history pass as GLOBAL loads, which the independent review
    measured. The rule is now conservative: a template that could produce the name
    makes the source ambiguous, and an ambiguous source costs its table, with a
    reason, and never publishes a number. The exact rule, from the names the run
    records it emitted, is registered for 0.25.0.
    """
    pproc = SimpleNamespace(
        plots=SimpleNamespace(
            parameters=["FX", "FY", "FZ", "MX", "MY", "MZ"],
            groups=[
                ForcePlotGroup(
                    name="ROTOR_{family}", frame="LOCAL_AXIS", families=["Blade1", "Blade2"]
                ),
                ForcePlotGroup(
                    name="MRP_{family}", frame="LOCAL_AXIS", families=["Blade1", "Blade2"]
                ),
            ],
        )
    )
    candidates, _ = rotor_plot_source(
        pproc, "PROP", rotor_families=["Blade1", "Blade2"], inventory=["Blade1", "Blade2"]
    )
    actual = candidates if automatic == "ROTOR_PROP" else global_frame_plot_groups(pproc)
    assert automatic not in actual, f"an ambiguous {automatic} was read as a source"


def test_recorded_polar_refuses_an_area_the_export_did_not_use(tmp_path):
    polar = _recorded(tmp_path, LOADS)
    with pytest.raises(ProductError, match="SREF"):
        write_recorded_polar(
            polar,
            tmp_path / "out",
            groups={"1": ["W", "B"]},
            reference=ReferenceValues(40.0, 2.526, 20.0),
            description="test",
            mach=0.2,
        )


def test_recorded_polar_refuses_vectors_in_a_rotated_analysis_frame(tmp_path):
    polar = _recorded(
        tmp_path,
        LOADS.replace(
            "Coordinate frame for analysis:              MRP",
            "Coordinate frame for analysis:              PROP_SMRP",
        ),
    )
    with pytest.raises(ProductError, match="PROP_SMRP"):
        write_recorded_polar(
            polar,
            tmp_path / "out",
            groups={"1": ["W", "B"]},
            reference=ReferenceValues(50.0, 2.526, 20.0),
            description="test",
            mach=0.2,
        )


def test_rotor_table_keeps_the_reference_aliases_when_summing_loads(tmp_path, monkeypatch):
    from pyflightstream.post import products

    rotor = SimpleNamespace(
        alias="PROP",
        members=["hub", "Blade1"],
        families_general=["hub"],
        families_blades=["Blade1"],
        diameter_m=1.0,
        axis_vector=(1.0, 0.0, 0.0),
        x_m=0.0,
        y_m=0.0,
        z_m=0.0,
    )
    monkeypatch.setattr(
        products, "resolve_reference", lambda *args: SimpleNamespace(rotors={"PROP": rotor})
    )
    zero = dict.fromkeys(("Cx", "Cy", "Cz", "CMx", "CMy", "CMz"), 0.0)
    loads = replace(
        parse_loads(LOADS),
        reference_velocity_m_s=1.0,
        freestream_velocity_m_s=1.0,
        surfaces={"Blade1": {**zero, "Cx": 1.0}, "Spinner": {**zero, "Cx": 2.0}},
    )
    point = PolarPoint("P", loads, tmp_path / "loads.txt")
    record = SimpleNamespace(
        run_id="run",
        reductions={"rotors": {"PROP": {"rpm": 600.0}}},
        density_kg_m3=2.0,
        mach=0.2,
    )
    reference = ReferenceValues(1.0, 1.0, 1.0)
    ((destination, _, plan),) = _rotor_tables(
        SimpleNamespace(inputs_dir=tmp_path),
        "1",
        [point],
        [record],
        {"P": ["run"]},
        reference,
        SimpleNamespace(ref_code="r001", variables={}),
        tmp_path,
        aliases={"hub": ["Spinner"]},
    )
    write_rotor_table(destination, rotor=rotor, rows=plan["rows"], reference=reference)
    _, rows = read_csv_table(destination, skip=1)
    # q S = 1 N; the rotor owns 1 + 2 N. rho n^2 D^4 = 200 N.
    assert float(rows[0]["CT_PROP"]) == 0.015, "the spinner alias lost 2 N of rotor thrust"
