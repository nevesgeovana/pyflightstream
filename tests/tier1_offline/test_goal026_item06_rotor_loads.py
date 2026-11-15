"""Tier 1, v0.23.0 item 6: the THRUST and TORQUE of one rotor, from what ran.

`rotor_coefficients` has taken `thrust_n` and `torque_nm` since the first commit
of this release and NOTHING computed them. A release round measured it: the
function had zero callers, its tests passed literals, and the socket was empty.

WHAT THE RUN ACTUALLY LEFT, which is what makes this derivable without a re-run
and therefore inside the owner's acceptance rule. The loads export carries, PER
SURFACE, six dimensionless coefficients in the moment-reference frame --
`Cx, Cy, Cz, CMx, CMy, CMz` -- beside the free-stream velocity, the reference
area and the reference length. The reference block carries the moment point; the
rotor block carries its hub, its diameter and, since item 19, its shaft.

THE ONE STEP THAT IS NOT ARITHMETIC IS THE MOMENT TRANSFER, and it is stated
here because a reader will ask. The export's moments are about the MOMENT
REFERENCE POINT. A rotor's torque is about ITS OWN SHAFT, through its hub. The
two differ by the moment of the force about the offset between them:

    M_hub = M_mrp + (r_mrp - r_hub) x F

That is elementary statics rather than a convention, so it is implemented rather
than asked: there is one right answer and choosing the other would report a
torque no rotor produces. What remains the owner's is the DEFINITION of `ETAW`,
which the coefficient function already flags, and physical validation, which
needs a licensed run.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.post.products import ReferenceValues, rotor_shaft_loads


def _reference(**values) -> ReferenceValues:
    """A reference whose moment point is the origin unless a test moves it."""
    base = {"SREF": 10.0, "CREF": 1.0, "BREF": 4.0, "XMOM": 0.0, "YMOM": 0.0, "ZMOM": 0.0}
    base.update(values)
    return ReferenceValues.from_mapping(base)


def _rotor(axis, *, hub=(0.0, 0.0, 0.0)):
    from pyflightstream.cases import BladeDatum, RotorBlock

    return RotorBlock(
        alias="PUSHER",
        axis=axis if isinstance(axis, str) else {"shaft": "Z", "vector_wrt_global": axis},
        x_m=hub[0],
        y_m=hub[1],
        z_m=hub[2],
        diameter_m=2.0,
        families_blades=["Blade1", "Blade2"],
        blade1=BladeDatum(zero="X" if axis != "X" else "Y"),
    )


def _surfaces(**rows):
    """One loads table, keyed by surface, in the export's own column names."""
    empty = {"Cx": 0.0, "Cy": 0.0, "Cz": 0.0, "CMx": 0.0, "CMy": 0.0, "CMz": 0.0}
    return {name: {**empty, **values} for name, values in rows.items()}


_REFERENCE_TOML = """area_m2 = 10.0
chord_m = 1.0
span_m = 4.0

[rotors.PUSHER]
alias = "PUSHER"
x_m = {x}
y_m = 0.0
z_m = 0.0
axis = "{axis}"
rpm_sign = 1
diameter_m = {diameter}
families_blades = ["Blade1"]
blade1 = {{ azimuth_deg = 0.0, zero = "{zero}" }}
"""
_AXES = {"X": [1.0, 0.0, 0.0], "Z": [0.0, 0.0, 1.0]}


def _stage_rotor(
    tmp_path,
    surfaces,
    *,
    axis="Z",
    hub_x=0.0,
    rpm=3000.0,
    velocity=40.0,
    free_stream=None,
    diameter=2.0,
    density=None,
    skipped=None,
):
    """Post polar 6001 as a quasi-steady sector of the rotor PUSHER and read its RCOEF file.

    The export states ``surfaces`` (coefficients in the export's own columns, in a
    reference of area 10, chord 1 and span 4), the reference velocity ``velocity``
    and, when given, the free-stream velocity ``free_stream``; the rotor turns at
    ``rpm`` rev/min (signed). Since 0.58.0 the rotor table is the rotor group's RCOEF
    file of the post stage, so the rows come from the stage and not from a writer.
    ``diameter`` and ``density`` replace the rotor's 2 m and the record's air density.
    A dict passed as ``skipped`` is filled with the `skipped` entries of the manifest
    (the products the stage left out, each with its reason).
    Returns ``(columns, rows, said)``: the file's header, its rows (one per point of the
    polar) and the warnings the stage raised.
    """
    import json
    import warnings

    from pyflightstream.post.products import read_csv_table
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_superfile import _loads, _post, _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _REFERENCE_TOML.format(
            axis=axis, x=hub_x, diameter=diameter, zero="Y" if axis == "X" else "X"
        ),
        encoding="utf-8",
    )
    order = ("Cx", "Cy", "Cz", "CMx", "CMy", "CMz")
    lines = []
    total = dict.fromkeys(order, 0.0)
    for name, values in surfaces.items():
        row = {key: values.get(key, 0.0) for key in order}
        for key in order:
            total[key] += row[key]
        lines.append(_surface_line(name, row))
    lines.append(_surface_line("Total", total))
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            outputs = [workspace.sim_dir("6001") / name for name in record.outputs]
            for path in outputs:
                text = _loads(0.0, velocity=f"{velocity:.3f}")
                text = text.replace("50.000", "10.000").replace("2.526", "1.000")
                kept = [
                    line
                    for line in text.splitlines()
                    if not line.startswith(("     W,", "     B,", "     Total,"))
                ]
                at = next(i for i, line in enumerate(kept) if "Surface, Cx" in line) + 2
                kept[at:at] = lines
                text = "\n".join(kept) + "\n"
                if free_stream is not None:
                    text = text.replace(
                        f"Freestream velocity (m/s)                   {velocity:.3f}",
                        f"Freestream velocity (m/s)                   {free_stream:.3f}",
                    )
                path.write_text(text, encoding="utf-8")
            loads = outputs[0]
            quasi = {
                "schema_version": 1,
                "run_type": "qsteady_rotor",
                "case": "sector",
                "rotor": "PUSHER",
                "blades": 2,
                "rpm": rpm,
                "shaft_frame_axis": axis,
                "hub_m": [hub_x, 0.0, 0.0],
                "axis_vector": _AXES[axis],
                "diameter_m": diameter,
                "families_general": [],
                "families_blades": ["Blade1"],
                "blade1_azimuth_deg": 0.0,
                "positions": [
                    {"index": 0, "clocking_deg": 0.0, "rotated_deg": 0.0, "loads": loads.name}
                ],
                "validity": None,
            }
            loads.with_name(loads.stem + "_qsteady.json").write_text(json.dumps(quasi))
            update = {
                "recipe": "qsteady_rotor",
                "reference": {"SREF": 10.0, "CREF": 1.0, "BREF": 4.0},
            }
            if density is not None:
                update["density_kg_m3"] = density
            record = record.model_copy(update=update)
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post(workspace)
    table = workspace.products_dir("matriz") / "polars" / "P6001-PUSHER-RCOEF.csv"
    said = [str(w.message) for w in caught]
    if skipped is not None:
        manifest = workspace.products_dir("matriz") / "products.json"
        skipped.update(json.loads(manifest.read_text(encoding="utf-8")).get("skipped", {}))
    if not table.is_file():
        return [], [], said
    columns, rows = read_csv_table(table)
    return list(columns), rows, said


def _surface_line(name, values):
    cells = ",".join(f"{values[key]:+.7f}" for key in ("Cx", "Cy", "Cz"))
    cells += ",+0.0000000,+0.0000000,+0.0000000"
    cells += "," + ",".join(f"{values[key]:+.7f}" for key in ("CMx", "CMy", "CMz"))
    return f"     {name},{cells}"


def test_the_thrust_is_the_force_along_the_shaft_and_nothing_else():
    """A rotor on Z, pushing along Z. Hand-checkable and the whole of the rule.

    q = 0.5 * 1.225 * 40^2 = 980.0; Sref = 10; Cz = 0.5
    => T = 0.5 * 980 * 10 = 4900 N, and the X force does not reach it.
    """
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5, "Cx": 0.3}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(4900.0), loads


def test_a_force_square_to_the_shaft_produces_no_thrust():
    """Without this the rule is satisfied by summing the magnitude."""
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cx": 0.9, "Cy": 0.9}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(0.0, abs=1e-9), loads


def test_only_the_rotors_own_families_are_summed():
    """A rotor's thrust is its OWN. The airframe is in the same table."""
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5}, Wing={"Cz": 99.0}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(4900.0), loads


def test_the_torque_is_taken_about_the_hub_and_not_about_the_moment_point():
    """THE MOMENT TRANSFER, which is the one step that is not arithmetic.

    The rotor sits at x = 2 and the moment point is the origin. A force of
    +Cy at the blade makes a moment about the ORIGIN that a torque about the
    HUB does not have: M_z = x * F_y, which is exactly the term the transfer
    removes.

    q = 980, Sref = 10, Cy = 0.25 => F_y = 2450 N
    the offset is 2 m in x, so the spurious M_z about the origin is 4900 N m
    and the torque about the hub is 0.
    """
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cy": 0.25, "CMz": 0.5}),
        rotor=_rotor("Z", hub=(2.0, 0.0, 0.0)),
        reference=_reference(CREF=1.0),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    # CMz = 0.5 about the origin is 0.5 * 980 * 10 * 1.0 = 4900 N m, and the
    # transfer removes exactly 4900, so the shaft torque is zero.
    assert loads.torque_nm == pytest.approx(0.0, abs=1e-6), loads


def test_a_hub_on_the_moment_point_needs_no_transfer():
    """The other half: with no offset the two are the same number.

    Without this the transfer is satisfied by subtracting the whole moment.
    """
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cy": 0.25, "CMz": 0.5}),
        rotor=_rotor("Z", hub=(0.0, 0.0, 0.0)),
        reference=_reference(CREF=1.0),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.torque_nm == pytest.approx(4900.0), loads


def test_a_tilted_shaft_takes_the_component_along_itself():
    """Item 19 is what makes this answerable for an installed rotor.

    A shaft at 30 degrees from Z in the x-z plane, with a force along Z: the
    thrust is the projection, T = F_z * cos(30).
    """
    angle = math.radians(30.0)
    shaft = [math.sin(angle), 0.0, math.cos(angle)]
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5}),
        rotor=_rotor(shaft),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(4900.0 * math.cos(angle)), loads


def test_the_shaft_angle_to_the_free_stream_is_reported_for_etaw():
    """The retired rotor table took `shaft_angle_deg` and nothing produced it.

    Without a producer a wired rotor table would report the ALIGNED-rotor
    `ETAW` by omission, which is the defect the coefficient function's own
    docstring warns about. The free stream is along +X by the package's own
    convention, so a shaft on Z is 90 degrees from it and a shaft on X is 0.
    """
    on_x = rotor_shaft_loads(
        _surfaces(Blade1={"Cx": 0.5}),
        rotor=_rotor("X"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert on_x.shaft_angle_deg == pytest.approx(0.0, abs=1e-9), on_x

    on_z = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert on_z.shaft_angle_deg == pytest.approx(90.0), on_z


def test_the_rotor_table_is_written_with_its_alias_in_every_row(tmp_path):
    """THE PRODUCT, which is what item 6 asks for and what nothing wrote.

    `rotor_coefficients` and `rotor_coefficient_columns` existed with no
    caller: pieces of a table and no table. The post stage writes one and this
    reads it back.

    THE ALIAS IS INSIDE THE BYTES, which is item 18: a script that has
    already LOADED the file no longer has its name. Since 0.58.0 the rotor's table
    is the RCOEF file of the rotor's own group: its first line is the header, which
    opens with the run block (`POL` first), and its `GROUP` column names the rotor.
    """
    columns, rows, _said = _stage_rotor(
        tmp_path, _surfaces(Blade1={"Cz": 0.5}), rpm=3000.0, velocity=40.0
    )
    assert rows, "the stage wrote no RCOEF file for the rotor group"

    assert columns[0] == "POL", columns
    assert rows[0]["GROUP"] == "PUSHER", rows[0]
    assert "CT" in columns, columns
    assert "ETAW" in columns, columns
    # One row per point of the polar (the fixture's polar has two).
    assert len(rows) == 2, rows
    assert float(rows[0]["CT"]) > 0.0, rows[0]


def test_a_static_point_reads_not_applicable_because_nothing_is_recoverable(tmp_path):
    """A zero reference velocity cannot recover dimensional loads.

    This fixture sets both reference and free-stream velocities to zero. It
    does not describe hover with positive VREF. The owner's batch-9 judgment
    retains reference-speed reconstruction; see the PFS-2127.001 report.

    So every coefficient reads `NA` EXCEPT `J`: visibly absent, rather than a
    zero a reader would believe of a rotor that is plainly pushing.

    THE EXCEPTION IS NAMED BECAUSE THE SENTENCE WITHOUT IT WAS WRONG, and a V&V
    round caught it against the assertion two lines below, which checked four
    columns of six. `J = V / (n D)` is `0.0 / (50.0 * 2.0)`, a clean float, so
    the rotor's `J0` of the run block writes `0.00000` -- and that is PHYSICALLY
    RIGHT: a turning rotor at rest genuinely has an advance ratio of zero. It is
    the one number on the row a reader may believe. `CP` is `2 pi * nan` and
    does read `NA`.

    A wrong sentence and a right number, which is the harder of the two to see:
    this docstring is what a reader takes for the column set's contract.
    """
    from pyflightstream.post.products import NOT_APPLICABLE

    _, rows, _said = _stage_rotor(tmp_path, _surfaces(Blade1={"Cz": 0.5}), velocity=0.0)
    assert rows, "the stage wrote no RCOEF file for the rotor group"
    # ALL FIVE, not the four this asserted. `CP` was the column the docstring
    # covered and the assertion did not, which is how "every coefficient" stayed
    # unchallenged while one of them wrote a number.
    for name in ("CT", "CQ", "CP", "ETA", "ETAW"):
        assert rows[0][name] == NOT_APPLICABLE, (name, rows[0])
    # AND THE ONE THAT IS A REAL ZERO, pinned with its reason so nobody "fixes"
    # it into `NA` for consistency with the five above.
    assert rows[0]["J0"] == "0.00000", (
        "J is V / (n D) and a turning rotor at rest has an advance ratio of "
        f"exactly zero, which is a measurement and not a missing value: {rows[0]}"
    )


def test_p0420_hover_with_positive_vref_pins_current_reconstruction(tmp_path):
    """Pin the reference-speed reconstruction retained by the batch-9 judgment.

    qref=980 Pa, S=10 m2, Cz=.5 gives 4900 N. CMz=.25 and Cref=1 m
    give 2450 Nm. At n=50 Hz, D=2 m these imply CT=.1 and CQ=.025.
    The independent free stream is zero, so J=0 and efficiencies are NA.
    """
    from pyflightstream.post.products import NOT_APPLICABLE

    _, rows, _said = _stage_rotor(
        tmp_path,
        _surfaces(Blade1={"Cz": 0.5, "CMz": 0.25}),
        velocity=40.0,
        free_stream=0.0,
    )
    assert rows, "the stage wrote no RCOEF file for the rotor group"
    assert rows[0]["CT"] != NOT_APPLICABLE
    assert float(rows[0]["CT"]) == pytest.approx(0.1)
    assert float(rows[0]["CQ"]) == pytest.approx(0.025)
    assert float(rows[0]["CP"]) == pytest.approx(0.15708, abs=0.000005)
    assert float(rows[0]["J0"]) == 0.0
    assert rows[0]["ETA"] == rows[0]["ETAW"] == NOT_APPLICABLE


@pytest.mark.requirement("FR-3217")
@pytest.mark.parametrize("vref", [40.0, 0.0])
def test_p0430_a_static_point_follows_its_definition_of_the_reference_speed(tmp_path, vref):
    """The definition of record and the table agree: VREF > 0 recovers, VREF = 0 cannot."""
    from pathlib import Path

    from pyflightstream.post.products import NOT_APPLICABLE

    page = (
        Path(__file__).resolve().parents[2] / "docs" / "definitions" / "rotor-coefficients.md"
    ).read_text(encoding="utf-8")
    static = page.split("### A static point", 1)[1].split("\n### ", 1)[0]
    assert "qref = rho VREF^2 / 2" in static
    assert "Reynolds number" in static and "reports/" in static
    assert "No rotor coefficient is recoverable" not in page
    _, rows, _said = _stage_rotor(
        tmp_path,
        _surfaces(Blade1={"Cz": 0.5, "CMz": 0.25}),
        velocity=vref,
        free_stream=0.0,
    )
    assert rows, "the stage wrote no RCOEF file for the rotor group"
    assert float(rows[0]["J0"]) == 0.0
    assert rows[0]["ETA"] == NOT_APPLICABLE
    if vref > 0.0:
        assert float(rows[0]["CT"]) == pytest.approx(0.1)
    else:
        assert rows[0]["CT"] == rows[0]["CQ"] == NOT_APPLICABLE


def test_a_rotor_that_is_not_turning_has_no_coefficient_to_state(tmp_path):
    """Every coefficient divides by the speed, so a stopped rotor states none.

    0.58.0 (design of the post outputs, section 4.3): the rotor's file is written for
    a rotor not turning, its `T` and `Q` stay (they need no speed) and every
    coefficient over `n^2` and `ETA` read `NA`; `P` is zero at zero speed. The 0.57.0
    writer wrote no table at all.
    """
    from pyflightstream.post.products import NOT_APPLICABLE

    _, rows, _said = _stage_rotor(tmp_path, _surfaces(Blade1={"Cz": 0.5}), rpm=0.0)
    assert rows, "the stage wrote no RCOEF file for the rotor group"
    for name in ("CT", "CQ", "CP", "ETA", "ETAW"):
        assert rows[0][name] == NOT_APPLICABLE, (name, rows[0])
    assert float(rows[0]["T"]) == pytest.approx(4900.0), rows[0]
    assert float(rows[0]["P"]) == 0.0, rows[0]


def test_a_counter_rotating_rotor_keeps_its_table(tmp_path):
    """A NEGATIVE RPM IS A DIRECTION AND NOT A STOPPED ROTOR.

    The plan records the speed SIGNED -- `rpm=_rpm_sign(case) * stated` in
    `cases.workflows` -- so that the sense of rotation survives into the
    record, and that module divides by `abs(self.rpm)` wherever it needs a
    rate. The writer's guard read `rpm <= 0.0` and discarded EVERY row of such
    a rotor: no table, no skip line, nothing saying the product was absent. On
    a contra-rotating pair that is half the aircraft, silently.

    Found by the independent review of `main` at 0.23.0, 2026-09-18. The two
    in-house rounds over this code did not, because every fixture spun forward.

    THE TORQUE IS NON-ZERO HERE AND THE FIRST WRITING OF THIS TEST HAD IT AT
    ZERO, which is why it could not see the defect the fix then introduced. With
    `CQ = CP = 0` the two tables agree under ANY sign rule, including taking the
    magnitude of the torque, so the case proved only that a file existed. The
    independent lens said so in those words. A reversed rotor with a real torque
    is the only fixture that discriminates.

    THE THREE PROPERTIES, each derived from physics rather than read off the
    implementation:

    1. `J` and `CT` are UNCHANGED. `CT = T/(rho n^2 D^4)` is quadratic in the
       rate, and `J = V/(n D)` would go NEGATIVE for a rotor flying forwards, so
       the rate that normalises them is the MAGNITUDE.
    2. `CQ` FLIPS. It is the torque about the rotor's fixed axis, and reversing
       the rotor reverses that projection. Taking its magnitude would erase the
       difference between a rotor driving and one braking, which is real.
    3. `CP`, `ETA` and `ETAW` are UNCHANGED, and this is the one the fix got
       wrong. `CP` is a normalised POWER and `P = Q * omega`: reverse the rotor
       AND its torque and the shaft power is the same number, because both
       factors flipped. Normalising with a magnitude rate while `CQ` keeps its
       sign made `CP` flip, and `ETA` with it.
    """

    def _write(where, rpm, swirl):
        # A REAL TORQUE: `Cy` at a hub offset in x gives a moment about the
        # shaft on Z, so `CQ` is non-zero and the sign rules are separable.
        return _stage_rotor(
            tmp_path / where,
            _surfaces(Blade1={"Cz": 0.5, "Cy": swirl}),
            axis="Z",
            hub_x=2.0,
            rpm=rpm,
            velocity=40.0,
        )

    # THE MIRRORED ROTOR, which is the physical case: reverse the rotation AND
    # the swirl it imparts, so the torque about the fixed axis reverses with it.
    # Reversing the rpm ALONE while holding the loads is a different situation
    # entirely -- a rotor being driven BY the flow -- and there `CP` SHOULD go
    # negative. The first writing of this test reversed only the rpm and then
    # asserted the power was unchanged, which asked for the wrong answer.
    _, fwd, _ = _write("fwd", 3000.0, 0.25)
    _, rev, _ = _write("rev", -3000.0, -0.25)
    assert rev, (
        "a counter-rotating rotor lost its entire table; a negative rpm is a "
        "direction, not a stopped rotor"
    )

    # THE FIXTURE MUST DISCRIMINATE, asserted before the comparisons that rest
    # on it. With a zero torque every check below passes under a wrong fix.
    assert float(fwd[0]["CQ"]) != 0.0, (
        f"this fixture states no torque, so it cannot tell the sign rules apart: {fwd[0]}"
    )

    for name in ("J0", "CT"):
        assert rev[0][name] == fwd[0][name], (
            f"{name} normalises by the RATE, which has no sign: "
            f"{rev[0][name]} against {fwd[0][name]}"
        )
    assert float(rev[0]["CQ"]) == pytest.approx(-float(fwd[0]["CQ"])), (
        "CQ is the torque about the rotor's fixed axis, and a mirrored rotor "
        f"imparts the opposite swirl: {rev[0]['CQ']} against {fwd[0]['CQ']}"
    )
    for name in ("CP", "ETA", "ETAW"):
        assert rev[0][name] == fwd[0][name], (
            f"{name} rests on P = Q * omega, and reversing BOTH the torque and "
            f"the rotation leaves the power unchanged: {rev[0][name]} against {fwd[0][name]}"
        )
    assert float(rev[0]["J0"]) > 0.0, (
        "J is V/(n D) and a rotor flying forwards has a positive advance "
        f"ratio whichever way it turns: {rev[0]}"
    )


def test_every_row_is_dimensionalised_from_its_own_points_record(tmp_path):
    """A SWEEP IS A TABLE OF ITS POINTS, AND EACH POINT HAS ITS OWN AIR.

    `_rotor_tables` read the rotor speed, the density, the velocity and the
    Mach once off `records[0]`, and it HOISTED THE SPEED OUT OF THE POINT LOOP.
    Every row of a sweep was therefore normalised by the FIRST point's state.
    On an advance-ratio sweep -- the one shape this table exists for, where the
    rotor speed is what MOVES -- the second point came out a factor of four
    wrong in `CT`, `CQ` and `CP`, and `J` came out at the first point's value.

    THE ROW STILL LOOKED RIGHT: the condition columns are per point, so `ALPHA`
    and `MACH` in the same row were that point's own and correct, sitting beside
    coefficients computed from a different point entirely.

    Found by the independent review of `main` at 0.23.0, 2026-09-18.

    0.58.0: the rotor table is the rotor group's RCOEF file, written by the post
    stage (the planner `_rotor_tables` is removed with it). Each row states its
    own speed `RPM0` and its own density `RHO` in its run block, and its `CT` is
    `T / (RHO n^2 D^4)` of THOSE cells: a borrowed speed shows as one `RPM0` on
    both rows, a borrowed density as a `CT` that its own row's cells do not give.
    """
    import warnings

    from pyflightstream.post.products import read_csv_table, write_campaign_products
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_p0580_l2_polar_files import _reference as _rotor_reference
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _rotor_reference(("PUSHER", None, "B")), encoding="utf-8"
    )
    # TWO POINTS OF ONE SWEEP: the rotor slows and the air thins.
    own = {"AL-020": (2400.0, 1.225), "AL+000": (1200.0, 1.100)}
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            ((rpm, density),) = [v for k, v in own.items() if k in record.run_id]
            record = record.model_copy(
                update={
                    "density_kg_m3": density,
                    "reductions": {"rotors": {"PUSHER": {"rpm": rpm, "blades": 2}}},
                }
            )
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    path = workspace.root / "post" / "matriz" / "polars" / "P6001-PUSHER-RCOEF.csv"
    _columns, rows = read_csv_table(path)
    assert len(rows) == 2, rows
    speeds = {key: float(row["RPM0"]) for row in rows for key in own if key in row["POINT"]}
    assert speeds == {key: value[0] for key, value in own.items()}, (
        "a sweep's second point turns at its own rate, not the first point's: "
        f"{[row['RPM0'] for row in rows]}"
    )
    for row in rows:
        rho, n, d = float(row["RHO"]), float(row["RPM0"]) / 60.0, float(row["D0"])
        assert float(row["CT"]) == pytest.approx(float(row["T"]) / (rho * n**2 * d**4), rel=1e-4)
    assert len({row["RHO"] for row in rows}) == 2, (
        f"both rows carry one point's air -- {[row['RHO'] for row in rows]}"
    )


def test_the_post_stage_writes_a_rotor_table_from_a_recorded_workspace(tmp_path):
    """ITEM 6 THROUGH THE STAGE, and it needed a route the record does not carry.

    THE ROTOR'S GEOMETRY IS NOT IN THE RECORD. A run leaves its reference BLOCK
    -- areas, lengths and the moment point -- and, under `reductions`, a rotors
    block with blades, rpm and steps per revolution. Neither carries the shaft,
    the hub or the diameter, and the record does not even name its reference. So
    the coefficients of item 6 cannot be derived from a record alone.

    They can be derived without a RE-RUN, which is the test the owner's rule
    sets. The stage already reads the campaign's matrix -- the super file
    depends on it -- the matrix row names its REF, and the reference file is
    still in the workspace. That is the route, and it costs nothing she has.

    This asserts the product: a recorded campaign whose reference declares a
    rotor gets the rotor's group RCOEF file (0.58.0: the rotor table is retired),
    its rows the rotor's own, its group the alias and its `ROTOR_ID` its id.
    """
    from pathlib import Path

    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)

    # THE FIXTURE'S ROTOR ROW names REF `r002` and turns the alias `PUSHER`.
    # The reference FILE is what carries the shaft, the hub and the diameter,
    # and it is the half a record does not keep -- so the test writes the file
    # a real workspace would already hold rather than skipping.
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        "\n".join(
            [
                "area_m2 = 50.0",
                "chord_m = 2.526",
                "span_m = 20.0",
                "",
                "[rotors.PUSHER]",
                'alias = "PUSHER"',
                "x_m = 0.0",
                "y_m = 0.0",
                "z_m = 0.0",
                'axis = "X"',
                "rpm_sign = 1",
                "diameter_m = 1.2",
                # A FAMILY THE EXPORT CARRIES (0.24.0, WT-02). This said Blade1 and
                # Blade2, which the fixture's loads table does not hold (it holds W,
                # B and Total), so the table this test celebrated was CT 0.00000 on
                # every row and the only assertion was the alias line. The rotor is
                # now refused where it selects nothing, and this fixture selects.
                'families_blades = ["B"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )

    written = _post(workspace)
    tables = [Path(p) for p in written if Path(p).name == "P6002-PUSHER-RCOEF.csv"]
    assert tables, (
        "the campaign turns a rotor and the stage wrote no rotor group file; "
        f"it wrote {sorted(Path(p).name for p in written)}"
    )

    # AND A VALUE, DERIVED HERE FROM THE EXPORT AND THE DEFINITION, which is what
    # the header line alone never proves. The shaft is X, so the thrust is the X
    # force of family B: `Cx * q * S`, and `CT = T / (rho n^2 D^4)`. 0.58.0 counts thrust
    # positive forward (D12, design 5.3) and the solver's x is aft, so CT is that
    # quotient with the sign reversed.
    from pyflightstream.post.products import read_csv_table
    from pyflightstream.results import parse_loads

    (record,) = [r for r in workspace.read_manifest() if r.sim_id == "6002"]
    loads_file = next(o for o in record.outputs if o.endswith("J+170.txt"))
    report = parse_loads((workspace.sim_dir("6002") / loads_file).read_text(encoding="utf-8"))
    rho, speed = record.density_kg_m3, report.reference_velocity_m_s
    rps = 2200.0 / 60.0
    thrust = report.surfaces["B"]["Cx"] * 0.5 * rho * speed**2 * 50.0
    expected = -thrust / (rho * rps**2 * 1.2**4)
    _columns, rows = read_csv_table(tables[0])
    assert (rows[0]["POL"], rows[0]["GROUP"]) == ("6002", "PUSHER"), rows[0]
    assert expected != 0.0, "the fixture's family carries no X force, so nothing is proved"
    assert float(rows[0]["CT"]) == pytest.approx(expected, rel=1e-4), rows[0]


def test_a_rotor_declaring_a_family_sums_that_familys_surfaces():
    """THE FALSE ZERO, and no fixture in this file could see it.

    A rotor's `members` are FAMILIES -- the field is `families_blades` -- and
    the package has ONE rule for turning a member token into surface names:
    `select_group_members`, which takes an exact name, an alias of the row's
    setup, or a FAMILY, the label without its trailing number, so `Blade`
    selects `Blade1` to `Blade6`. `group_coefficients` calls it forty lines
    above `rotor_shaft_loads`, which matched by exact name instead.

    So a rotor declared the way the resolver EXISTS TO SERVE summed nothing:
    thrust exactly 0.0, written `0.00000` by the funnel -- not `NA` -- and
    `ETA`/`ETAW` routed to `NA` by the zero power, which makes the row look
    like the documented static case rather than like a defect.

    Every fixture in this file used exact surface names, so nothing here could
    fail on it. A V&V round read it instead. This is the case that would have.
    """
    from pyflightstream.cases import BladeDatum, RotorBlock

    family = RotorBlock(
        alias="PUSHER",
        axis="Z",
        diameter_m=2.0,
        families_blades=["Blade"],
        blade1=BladeDatum(zero="X"),
    )
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.25}, Blade2={"Cz": 0.25}, Wing={"Cz": 99.0}),
        rotor=family,
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    # The two blades sum to Cz = 0.5, which is 4900 N; the wing is not the rotor.
    assert loads.thrust_n == pytest.approx(4900.0), loads
    assert set(loads.families_used) == {"Blade1", "Blade2"}, loads.families_used


def test_the_shaft_angle_follows_the_free_stream_and_not_the_body_axis():
    """THE AIRCRAFT'S PITCH, reintroduced as an omission.

    `shaft_angle_deg` read `acos(shaft[0])` -- the angle to body +X -- under a
    comment calling +X "this package's convention everywhere". The same module
    says otherwise: `polar_row` turns stability-axis forces into body axes
    THROUGH ALPHA, and the wind and stability axes coincide only at BETA 0.

    So on an alpha sweep, which is the ordinary shape of a polar, the angle was
    off by alpha on EVERY row and `ETAW = ETA * cos(theta)` with it. That is the
    defect item 19 exists to remove, one level up, and `rotor_coefficients`
    warns about it in its own docstring.

    THE OLD TEST COULD NOT FAIL ON THIS: it used no alpha at all, asserting 0
    and 90 degrees for shafts on X and Z with the aircraft level. A V&V round
    read the arithmetic instead.
    """
    level = rotor_shaft_loads(
        _surfaces(Blade1={"Cx": 0.5}),
        rotor=_rotor("X"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert level.shaft_angle_deg == pytest.approx(0.0, abs=1e-9), level

    # THE SAME SHAFT, the aircraft at ten degrees: the free stream has moved and
    # the shaft has not, so the angle between them is ten.
    pitched = rotor_shaft_loads(
        _surfaces(Blade1={"Cx": 0.5}),
        rotor=_rotor("X"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
        alpha_deg=10.0,
    )
    assert pitched.shaft_angle_deg == pytest.approx(10.0), pitched

    # AND SIDESLIP COUNTS TOO, which the body-axis reading also missed.
    yawed = rotor_shaft_loads(
        _surfaces(Blade1={"Cx": 0.5}),
        rotor=_rotor("X"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
        beta_deg=5.0,
    )
    assert yawed.shaft_angle_deg == pytest.approx(5.0), yawed


def test_a_refused_row_leaves_nothing_behind_in_the_products_folder(tmp_path):
    """THE SCRATCH FILE SURVIVED EVERY FAILURE, in her products folder.

    The rows were written to `<product>.rows` beside the destination and
    unlinked after. `write_csv_table` refuses a malformed row, and that refusal
    left the scratch behind: a HEADED TABLE WITH NO ALIAS LINE, in `polars/`,
    which is exactly what the write order claims to prevent -- and nothing on
    any later run cleans it up. A QA round reproduced it by shrinking the
    column tuple.

    It is a temporary directory now, so a process killed mid-write leaves
    nothing in the workspace at all. This machine killed three runs for memory
    in one session; that is not hypothetical.
    """
    polars = tmp_path / "polars"
    polars.mkdir()
    target = polars / "P0001-PUSHER-RCOEF.csv"

    from pyflightstream._errors import ProductError
    from pyflightstream.post._tables import write_csv_table

    # A row narrower than the header is what the funnel refuses. Every table of the
    # 0.58.0 post (the rotor group's RCOEF file among them) is written through it; the
    # rotor writer that used to call it is retired.
    # NAMED, not blind: a bare `Exception` here would pass on an unrelated error and
    # prove nothing about the funnel's refusal, which is what this test is about.
    with pytest.raises(ProductError):
        write_csv_table(target, ["ROTOR_ID", "CT", "CQ"], [[0, 0.1]])

    left = sorted(p.name for p in polars.iterdir())
    assert left == [], f"the refusal left files in the products folder: {left}"


@pytest.mark.parametrize("column", ["CDi", "CT_PUSHER", "CQ_PUSHER"])
def test_p0400_bgtests2_small_coefficients_keep_six_significant_figures(tmp_path, column):
    """PFS-2081.53: a small coefficient survives the writer without five-decimal truncation."""
    from pyflightstream.post.products import read_csv_table, write_csv_table

    path = tmp_path / "coefficients.csv"
    value = 0.000123456
    write_csv_table(
        path, [column, column + "_DRIFT_PCT", "SETTING"], [[value, value, "7.123456789"]]
    )
    _, rows = read_csv_table(path)
    assert float(rows[0][column]) == pytest.approx(value, rel=5e-6, abs=0)
    assert rows[0][column + "_DRIFT_PCT"] == "0.00012"
    assert rows[0]["SETTING"] == "7.123456789"


def test_f159_a_missing_surface_coefficient_is_not_a_zero():
    """F-159: a surface that states no Cz leaves the thrust a NaN, not a finite 0.5 * ..."""
    surfaces = {
        "Blade1": {"Cx": 0.0, "Cy": 0.0, "CMx": 0.0, "CMy": 0.0, "CMz": 0.0},
        "Blade2": {"Cx": 0.0, "Cy": 0.0, "Cz": 0.5, "CMx": 0.0, "CMy": 0.0, "CMz": 0.0},
    }
    loads = rotor_shaft_loads(
        surfaces,
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert math.isnan(loads.thrust_n), loads


def test_f4_0506_rotor_loads_refuse_what_they_cannot_define():
    from types import SimpleNamespace

    common = dict(reference=_reference(), density_kg_m3=1.225)
    surfaces = _surfaces(Blade1={"Cz": 0.5})
    # F-1395: a negative speed has no dynamic pressure; it is NaN, not squared
    loads = rotor_shaft_loads(surfaces, rotor=_rotor("Z"), speed_m_s=-40.0, **common)
    assert math.isnan(loads.thrust_n) and math.isnan(loads.torque_nm)
    # F-205: a zero shaft axis is no +Z; the loads read NaN, they are not invented
    bare = SimpleNamespace(
        axis_vector=(0.0, 0.0, 0.0), members=["Blade1"], x_m=0.0, y_m=0.0, z_m=0.0
    )
    loads = rotor_shaft_loads(surfaces, rotor=bare, speed_m_s=40.0, **common)
    assert math.isnan(loads.thrust_n) and loads.families_used == ("Blade1",)


@pytest.mark.parametrize("shaft", [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)])
def test_f4_0506_f_128_the_wind_force_follows_the_shafts_sense(shaft):
    """ETAW equals ETA along the stream for either direction the shaft is declared."""
    from types import SimpleNamespace

    # q * Sref = 0.5 * 1.25 * 40**2 * 10 = 10000, so the coefficients are the newtons / 10000
    newtons = (120.0, 7.0, -3.0)
    thrust = sum(f * s for f, s in zip(newtons, shaft, strict=True))
    surfaces = _surfaces(Blade1={"Cx": 0.012, "Cy": 0.0007, "Cz": -0.0003})
    rotor = SimpleNamespace(axis_vector=shaft, members=["Blade1"], x_m=0.0, y_m=0.0, z_m=0.0)
    loads = rotor_shaft_loads(
        surfaces, rotor=rotor, reference=_reference(), density_kg_m3=1.25, speed_m_s=40.0
    )
    assert loads.thrust_n == pytest.approx(thrust)
    assert loads.wind_force_n == pytest.approx(thrust)
