"""Independent release regressions for row, frame, group and reference identity."""

import re
import warnings
from types import SimpleNamespace

import pytest

from pyflightstream.cases import ForcePlotGroup
from pyflightstream.post.products import (
    ProductError,
    ReferenceValues,
    global_frame_plot_groups,
    read_csv_table,
    rotor_plot_source,
    write_campaign_products,
    write_recorded_polar,
)
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_post_products import LOADS, PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _workspace


def _two_points(tmp_path, windows):
    """Sim 6002 recorded as two points, each stating its own window, over one plots history.

    The history is the total's FX over four steps, 10, 20, 100 and 200; ``windows`` is the
    window each point's record states, keyed by its J.
    """
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text("[groups]\n", encoding="utf-8")
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    history = (
        PLOTS_HEADER
        + "Time-step,FX_MRP_TOTAL,FY_MRP_TOTAL,FZ_MRP_TOTAL,"
        + "MX_MRP_TOTAL,MY_MRP_TOTAL,MZ_MRP_TOTAL\n"
        + "-" * 70
        + "\n"
        + "".join(f"{i + 1}.0000,{x:.4f},0,0,0,0,0,\n" for i, x in enumerate((10, 20, 100, 200)))
        + "-" * 70
        + "\n     Force Units: Coefficients\nSoftware : Flightstream version 26.1, build #7012026\n"
    )
    outputs = workspace.sim_dir("6002") / "outputs"
    for record in records:
        if record.sim_id != "6002":
            workspace.append_record(RunRecord(**record.model_dump()))
            continue
        loads_text = (workspace.sim_dir("6002") / record.outputs[0]).read_text(encoding="utf-8")
        for advance, window in windows.items():
            stem = f"POLAR-6002_M14AL+000BE+000J+{advance}"
            (outputs / f"{stem}.txt").write_text(loads_text, encoding="utf-8")
            (outputs / f"{stem}_plots.txt").write_text(history, encoding="utf-8")
            plan = {
                "window_stated": True,
                "time_iterations": 4,
                "steps_per_revolution": 4.0,
                "rotors": {},
                "time_average": {"windows": [list(window)], "window_from": "the record"},
            }
            update = {
                "run_id": f"camp/sim_6002/M144RE438AL+000BE+000J+{advance}",
                "point_name": f"M144RE438AL+000BE+000J+{advance}",
                "outputs": [f"outputs/{stem}.txt", f"outputs/{stem}_plots.txt"],
                "reductions": plan,
            }
            workspace.append_record(RunRecord(**{**record.model_dump(), **update}))
    row = next(
        line
        for line in (workspace.root / "matriz.fs").read_text().splitlines()
        if line.startswith("6002")
    )
    sweep = ",".join(f"{int(a) / 100:g}" for a in windows)
    (workspace.root / "matriz.fs").write_text(
        (workspace.root / "matriz.fs")
        .read_text(encoding="utf-8")
        .replace(row, row.replace("| 1.7 |", f"| {sweep} |")),
        encoding="utf-8",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    return workspace.root / "post" / "matriz" / "polars"


def test_a_point_override_does_not_replace_the_default_window(tmp_path):
    polars = _two_points(tmp_path, {"170": (1, 2), "180": (3, 4)})
    rows = read_csv_table(polars / "P6002-TOTAL-DIM.csv")[1]
    by_point = {row["POINT"].rsplit("J+", 1)[1]: row for row in rows}
    assert float(by_point["170"]["FX_MRP"]) == 15.0, "point A averages its own steps 1..2"
    assert float(by_point["180"]["FX_MRP"]) == 150.0, (
        "point B must average its default steps 3..4 to 150, not point A's steps 1..2"
    )
    assert (by_point["170"]["FIRST_STEP"], by_point["180"]["FIRST_STEP"]) == ("1", "3")


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


def test_recorded_polar_warns_of_an_area_the_export_did_not_use(tmp_path):
    """Outside a post the writer follows the documented default: warn, name SREF, write.

    The export divided by 50 m2 and the reference states 40: the warning names both,
    and the table states the reference's SREF (what-every-product-states.md).
    """
    polar = _recorded(tmp_path, LOADS)
    with pytest.warns(Warning, match=r"states a reference area of 50.*SREF 40"):
        written = write_recorded_polar(
            polar,
            tmp_path / "out",
            groups={"1": ["W", "B"]},
            reference=ReferenceValues(40.0, 2.526, 20.0),
            description="test",
            mach=0.2,
        )
    assert written, "the default policy writes every computable product"
    rows = read_csv_table(written[0])[1]
    assert rows and float(rows[0]["SREF"]) == 40.0


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


def test_rotor_table_keeps_the_reference_aliases_when_summing_loads(tmp_path):
    """The rotor's loads are its blades' and its hub's: an alias the reference declares counts.

    Polar 6001 is posted with a rotor PROP whose blade is `Blade1` and whose hub is `hub`, an
    alias of the reference standing for the surface `Spinner`. The thrust of its group file
    holds the spinner's load too.
    """
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        "area_m2 = 50.0\nchord_m = 2.526\nspan_m = 20.0\n"
        '\n[aliases]\nhub = ["Spinner"]\n'
        '\n[rotors.PROP]\nalias = "PROP"\nx_m = 0.0\ny_m = 0.0\nz_m = 0.0\n'
        'axis = "X"\nrpm_sign = 1\ndiameter_m = 1.0\n'
        'families_general = ["hub"]\nfamilies_blades = ["Blade1"]\n'
        'blade1 = { azimuth_deg = 0.0, zero = "Y" }\n',
        encoding="utf-8",
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text("[groups]\n", encoding="utf-8")
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            for output in record.outputs:
                path = workspace.sim_dir("6001") / output
                text = path.read_text(encoding="utf-8")
                # Forward thrust is a force along -x of the mesh: Blade1 -0.001, Spinner -0.002.
                text = re.sub(r"^     W,\+[0-9.]+", "     Blade1,-0.0010000", text, flags=re.M)
                text = re.sub(r"^     B,\+[0-9.]+", "     Spinner,-0.0020000", text, flags=re.M)
                path.write_text(text, encoding="utf-8")
            record = record.model_copy(
                update={"density_kg_m3": 2.0, "reductions": {"rotors": {"PROP": {"rpm": 600.0}}}}
            )
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    polars = workspace.root / "post" / "matriz" / "polars"
    rows = read_csv_table(polars / "P6001-PROP-RCOEF.csv")[1]
    surfaces = {name: row["Cx"] for name, row in _surfaces_of(workspace).items()}
    assert set(surfaces) >= {"Blade1", "Spinner"}, surfaces
    # q S of the export's own reference velocity at the record's density 2 kg/m3; the rotor
    # owns 0.001 + 0.002 of it, and rho n^2 D^4 = 2 * 10^2 * 1 = 200 N.
    pressure_area = 0.5 * 2.0 * 68.058**2 * 50.0
    assert float(rows[0]["CT"]) == pytest.approx(0.003 * pressure_area / 200.0, rel=1e-4), (
        "the spinner alias lost its share of the rotor's thrust"
    )


def _surfaces_of(workspace):
    """The first steady point's loads table, by surface, as the post reads it."""
    from pyflightstream.results import parse_loads

    record = next(r for r in workspace.read_manifest() if r.sim_id == "6001")
    loads = parse_loads((workspace.sim_dir("6001") / record.outputs[0]).read_text(encoding="utf-8"))
    return loads.surfaces
