"""A sections row says WHICH distribution it belongs to, and where that rotor's blade is.

THE DEFECT (scope 4d(1), RI-04, RI-05, NL-02). A pproc declares several
distributions, the wing in XZ and each blade in its own frame, and every one of
them landed in ONE table whose rows carried a condition and no identity: no
family, no plane, no rotor. With `Offset` the only coordinate, two distributions
of similar span were indistinguishable. `AZIMUTH` was one number for the whole
file, the row's CLOCK rotor turned from zero, unsigned, on wing rows too.

The requirement, as answered: each block states its family, its plane and its
rotor, and `AZIMUTH` is where BLADE ONE OF THAT BLOCK'S OWN ROTOR is,

    AZIMUTH = (blade1_azimuth_deg + rpm_sign * STEP * 360 / steps_per_revolution) mod 360

with all three taken from that rotor. `NA` on a block no rotor owns, and on every
record written before the run recorded the layout: the script states surfaces by
INDEX, so nothing at post can name them.

THE LAYOUT IS RECORDED BY THE LOOP THAT EMITS THE DISTRIBUTIONS, for the reason
`Script.probe_points` is: what is recorded cannot drift from what was emitted.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.workflows import build_script
from pyflightstream.post.products import (
    NOT_APPLICABLE,
    read_csv_table,
    write_sections_table,
)
from pyflightstream.script import Script
from tests.tier1_offline.test_post_products import SLOADS
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case


def test_the_builder_records_each_block_it_emits_in_the_order_it_emits_them(tmp_path):
    case = _with_pproc(unsteady_case(LAST_ITERS_AVG="480"), _wb_geometry(tmp_path))
    script = Script("26.120")
    build_script(case, script)
    text = script.render().splitlines()
    emitted = [i for i, line in enumerate(text) if line == "NEW_SURFACE_SECTION_DISTRIBUTION"]
    blocks = script.section_blocks
    assert len(blocks) == len(emitted) == 3, (blocks, len(emitted))
    # W in XZ, B in XZ, B in YZ, as the fixture's pproc declares and the script shows.
    assert [(block["families"], block["plane"]) for block in blocks] == [
        (["W"], "XZ"),
        (["B"], "XZ"),
        (["B"], "YZ"),
    ]
    for block, at in zip(blocks, emitted, strict=True):
        assert text[at + 2] == f"PLANE {block['plane']}"
        assert text[at + 3] == f"NUM_SECTIONS {block['count']}"


LAYOUT = [
    {"families": ["Wing"], "plane": "XZ", "count": 1, "frame": "MRP"},
    {"families": ["Blade1"], "plane": "XY", "count": 1, "frame": "PUSHER_B1"},
]
ROTORS = {
    "PUSHER": {
        "families": ["Blade1", "Blade2"],
        "steps_per_revolution": 72.0,
        "blade1_azimuth_deg": 90.0,
        "rpm": -1200.0,
    }
}


def test_each_row_states_its_family_plane_and_rotor_and_the_step(tmp_path):
    written = write_sections_table(
        tmp_path / "p_sections.csv", SLOADS, mach=0.2, layout=LAYOUT, rotors=ROTORS
    )
    columns, rows = read_csv_table(written)
    # BEHIND THE POLAR since 0.27.0 (G16).
    assert list(columns[:6]) == ["POL", "STEP", "FAMILY", "PLANE", "ROTOR", "AZIMUTH"], columns[:7]
    assert "ITERATION" not in columns
    assert [(r["FAMILY"], r["PLANE"], r["ROTOR"]) for r in rows] == [
        ("Wing", "XZ", NOT_APPLICABLE),
        ("Blade1", "XY", "PUSHER"),
    ]
    assert {row["STEP"] for row in rows} == {"3134"}, "the export states iteration 3134"


def test_the_azimuth_is_blade_one_of_the_blocks_own_rotor_signed_and_offset(tmp_path):
    written = write_sections_table(
        tmp_path / "p_sections.csv", SLOADS, mach=0.2, layout=LAYOUT, rotors=ROTORS
    )
    _columns, rows = read_csv_table(written)
    assert rows[0]["AZIMUTH"] == NOT_APPLICABLE, "a wing has no azimuth, and zero is an azimuth"
    # 3134 steps of 5 degrees, turning the NEGATIVE way, from a datum of 90 degrees:
    # 90 - 3134 * 5 = -15580, and -15580 mod 360 = 260.
    expected = (90.0 - 3134 * 360.0 / 72.0) % 360.0
    assert expected == pytest.approx(260.0)
    assert float(rows[1]["AZIMUTH"]) == pytest.approx(expected)


def test_a_record_with_no_layout_states_not_applicable_rather_than_a_guess(tmp_path):
    written = write_sections_table(tmp_path / "p_sections.csv", SLOADS, mach=0.2)
    _columns, rows = read_csv_table(written)
    for row in rows:
        assert (row["FAMILY"], row["PLANE"], row["ROTOR"], row["AZIMUTH"]) == (NOT_APPLICABLE,) * 4


def test_a_layout_that_does_not_add_up_to_the_export_is_not_applied(tmp_path):
    short = [dict(LAYOUT[0], count=5)]
    written = write_sections_table(
        tmp_path / "p_sections.csv", SLOADS, mach=0.2, layout=short, rotors=ROTORS
    )
    _columns, rows = read_csv_table(written)
    assert {row["FAMILY"] for row in rows} == {NOT_APPLICABLE}


def test_the_stage_takes_a_rotors_families_from_the_reference_and_its_clock_from_the_record():
    """The families are the reference's, through the aliases; the clock is the record's.

    A section block states GEOMETRY families, and a rotor block may state an alias,
    so the two only meet after the alias is expanded. The speed is per point: an RPM
    sweep turns a different angle per step at each one.
    """
    from types import SimpleNamespace

    from pyflightstream.post.products import _section_rotors

    live = SimpleNamespace(
        rotors={
            "PUSHER": SimpleNamespace(families_blades=["blades"]),
            "LIFTER": SimpleNamespace(families_blades=["L1"]),
        }
    )
    record = SimpleNamespace(
        reductions={
            "steps_per_revolution": 999.0,
            "rotors": {
                "PUSHER": {
                    "steps_per_revolution": 72.0,
                    "blade1_azimuth_deg": 90.0,
                    "rpm": -1200.0,
                },
            },
        }
    )
    table = _section_rotors(live, {"blades": ["Blade1", "Blade2"]}, record)
    assert table["PUSHER"] == {
        "families": ["Blade1", "Blade2"],
        "steps_per_revolution": 72.0,
        "blade1_azimuth_deg": 90.0,
        "rpm": -1200.0,
    }
    # A rotor the record says nothing of is NAMED and has no clock: with two rotors
    # the row-level clock belongs to one of them and is not lent to the other.
    assert table["LIFTER"] == {"families": ["L1"]}


def test_the_stage_reads_the_layout_off_the_points_own_record_and_says_it_is_one_instant(tmp_path):
    """The wiring, end to end: the record states the blocks and the table names them.

    And the manifest says what KIND of table it is. On an unsteady point the sections
    table is the distribution at ONE step, not an average over the window, and
    nothing said so.
    """
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_goal028_explained_products import _give
    from tests.tier1_offline.test_post_products import _products_manifest, _unsteady_workspace

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_sloads.txt").write_text(SLOADS, encoding="utf-8")
    _give(
        workspace,
        outputs=["outputs/AL-020.txt", "outputs/AL-020_plots.txt", "outputs/AL-020_sloads.txt"],
        sections_layout=LAYOUT,
    )
    write_campaign_products(workspace)
    table = workspace.root / "post" / "products" / "sections" / "AL-020_sections.csv"
    _columns, rows = read_csv_table(table)
    assert [(r["FAMILY"], r["PLANE"]) for r in rows] == [("Wing", "XZ"), ("Blade1", "XY")]
    entry = _products_manifest(workspace)["products"]["sections/AL-020_sections.csv"]
    assert entry["kind"] == "instant", entry


def test_an_unsteady_points_step_is_its_time_step_and_not_the_solvers_iteration_count(tmp_path):
    """MEASURED ON A LICENSED RUN: 144 time steps, and the export's header said 2813
    (reports/RPT-053, campaign pfs0240 row 2411).

    On an unsteady run the header line `Current solver iteration number` counts the
    solver's INNER iterations, summed over every time step. The table took it for the
    step, so `STEP` read 2813 on a run of 144 steps and `AZIMUTH` was computed from it:
    25 degrees for a blade that, at step 144 of a 72-step turn from a datum of zero,
    is back at 0. The sections export of an unsteady point is written at the END of
    the run, so its step is the run's last time step, which the record states.

    This fixture's export says 3134; the record says the run marched 144 steps.
    """
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_goal028_explained_products import _give
    from tests.tier1_offline.test_post_products import _unsteady_workspace

    plan = {
        "time_iterations": 144,
        "steps_per_revolution": 72.0,
        "rotors": {
            "PUSHER": {
                "blades": 1,
                "blade_families": ["Blade1"],
                "steps_per_revolution": 72.0,
                "blade1_azimuth_deg": 0.0,
                "rpm": 1200.0,
            }
        },
    }
    workspace = _unsteady_workspace(tmp_path, reductions=plan)
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_sloads.txt").write_text(SLOADS, encoding="utf-8")
    _give(
        workspace,
        outputs=["outputs/AL-020.txt", "outputs/AL-020_plots.txt", "outputs/AL-020_sloads.txt"],
        sections_layout=LAYOUT,
    )
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    table = workspace.root / "post" / "products" / "sections" / "AL-020_sections.csv"
    _columns, rows = read_csv_table(table)
    assert {row["STEP"] for row in rows} == {"144"}, "the time step, not the 3134 of the header"
    blade = next(row for row in rows if row["FAMILY"] == "Blade1")
    assert blade["ROTOR"] == "PUSHER"
    # 144 steps of 5 degrees is two whole turns from a datum of zero.
    assert float(blade["AZIMUTH"]) == pytest.approx(0.0)
