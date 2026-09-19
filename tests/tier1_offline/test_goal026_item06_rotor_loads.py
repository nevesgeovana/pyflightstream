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
        axis=axis,
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
    """`rotor_coefficients` takes `shaft_angle_deg` and nothing produced it.

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


def test_the_rotor_table_is_written_with_its_alias_on_the_first_line(tmp_path):
    """THE PRODUCT, which is what item 6 asks for and what nothing wrote.

    `rotor_coefficients`, `rotor_coefficient_columns` and
    `rotor_table_alias_line` all existed with no caller: three pieces of a
    table and no table. This writes one and reads it back.

    THE ALIAS LEADS THE FILE, alone on its first line, which is item 18: a
    script that has already LOADED the file no longer has its name, so the
    alias has to be inside the bytes.
    """
    from pyflightstream.post.products import read_csv_table, write_rotor_table

    rotor = _rotor("Z")
    written = write_rotor_table(
        tmp_path / "polars" / "P0001-M150_PUSHER_rotor.csv",
        rotor=rotor,
        rows=[
            {
                "surfaces": _surfaces(Blade1={"Cz": 0.5}),
                "condition": {"MACH": 0.15, "ALPHA": 0.0},
                "rpm": 3000.0,
                # THE ROW'S OWN AIR AND VELOCITY. These were arguments of the
                # WHOLE call until 2026-09-18, so every row of a sweep divided
                # by the first point's state.
                "density": 1.225,
                "speed": 40.0,
            }
        ],
        reference=_reference(),
    )
    assert written is not None and written.is_file(), written

    first = written.read_text(encoding="utf-8").splitlines()[0]
    assert first.strip() == "PUSHER", first

    columns, rows = read_csv_table(written, skip=1)
    assert "CT_PUSHER" in columns, columns
    assert "ETAW_PUSHER" in columns, columns
    assert len(rows) == 1, rows
    assert float(rows[0]["CT_PUSHER"]) > 0.0, rows[0]


def test_a_static_point_reads_not_applicable_because_nothing_is_recoverable(tmp_path):
    """A FINDING RATHER THAN A DESIGN, and it is worth the owner's attention.

    The loads export states DIMENSIONLESS coefficients, normalised by the run's
    own dynamic pressure. At V = 0 that pressure is zero and a hovering rotor's
    real thrust has been divided away -- so item 6's coefficients cannot be
    derived from this export for a static point AT ALL, whatever is wired.

    This test asserted `CT > 0` when it was written, on the assumption that
    only the two efficiencies were 0/0. Running it showed the whole row is
    unrecoverable, which is a fact about the export rather than about the code.
    A hover figure of merit needs the run to state a FORCE.

    So every coefficient reads `NA` EXCEPT `J`: visibly absent, rather than a
    zero a reader would believe of a rotor that is plainly pushing.

    THE EXCEPTION IS NAMED BECAUSE THE SENTENCE WITHOUT IT WAS WRONG, and a V&V
    round caught it against the assertion two lines below, which checked four
    columns of six. `J = V / (n D)` is `0.0 / (50.0 * 2.0)`, a clean float, so
    `J_PUSHER` writes `0.00000` -- and that is PHYSICALLY RIGHT: a turning rotor
    at rest genuinely has an advance ratio of zero. It is the one number on the
    row a reader may believe. `CP` is `2 pi * nan` and does read `NA`.

    A wrong sentence and a right number, which is the harder of the two to see:
    this docstring is what a reader takes for the column set's contract.
    """
    from pyflightstream.post.products import NOT_APPLICABLE, read_csv_table, write_rotor_table

    written = write_rotor_table(
        tmp_path / "polars" / "P0001-M000_PUSHER_rotor.csv",
        rotor=_rotor("Z"),
        rows=[
            {
                "surfaces": _surfaces(Blade1={"Cz": 0.5}),
                "condition": {"MACH": 0.0},
                "rpm": 3000.0,
                "density": 1.225,
                "speed": 0.0,
            }
        ],
        reference=_reference(),
    )
    _, rows = read_csv_table(written, skip=1)
    # ALL FIVE, not the four this asserted. `CP` was the column the docstring
    # covered and the assertion did not, which is how "every coefficient" stayed
    # unchallenged while one of them wrote a number.
    for name in ("CT_PUSHER", "CQ_PUSHER", "CP_PUSHER", "ETA_PUSHER", "ETAW_PUSHER"):
        assert rows[0][name] == NOT_APPLICABLE, (name, rows[0])
    # AND THE ONE THAT IS A REAL ZERO, pinned with its reason so nobody "fixes"
    # it into `NA` for consistency with the five above.
    assert rows[0]["J_PUSHER"] == "0.00000", (
        "J is V / (n D) and a turning rotor at rest has an advance ratio of "
        f"exactly zero, which is a measurement and not a missing value: {rows[0]}"
    )


def test_a_rotor_that_is_not_turning_writes_no_table(tmp_path):
    """Every coefficient divides by the speed, so there is no table to write."""
    from pyflightstream.post.products import write_rotor_table

    written = write_rotor_table(
        tmp_path / "polars" / "P0001_PUSHER_rotor.csv",
        rotor=_rotor("Z"),
        rows=[
            {
                "surfaces": _surfaces(Blade1={"Cz": 0.5}),
                "condition": {},
                "rpm": 0.0,
                "density": 1.225,
                "speed": 40.0,
            }
        ],
        reference=_reference(),
    )
    assert written is None, written


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
    from pyflightstream.post.products import read_csv_table, write_rotor_table

    def _row(rpm, swirl):
        return {
            # A REAL TORQUE: `Cy` at a hub offset in x gives a moment about the
            # shaft on Z, so `CQ` is non-zero and the sign rules are separable.
            "surfaces": _surfaces(Blade1={"Cz": 0.5, "Cy": swirl}),
            "condition": {"MACH": 0.15, "ALPHA": 0.0},
            "rpm": rpm,
            "density": 1.225,
            "speed": 40.0,
        }

    def _write(where, rpm, swirl):
        return write_rotor_table(
            tmp_path / where / "P0001_PUSHER_rotor.csv",
            rotor=_rotor("Z", hub=(2.0, 0.0, 0.0)),
            rows=[_row(rpm, swirl)],
            reference=_reference(CREF=1.0),
        )

    # THE MIRRORED ROTOR, which is the physical case: reverse the rotation AND
    # the swirl it imparts, so the torque about the fixed axis reverses with it.
    # Reversing the rpm ALONE while holding the loads is a different situation
    # entirely -- a rotor being driven BY the flow -- and there `CP` SHOULD go
    # negative. The first writing of this test reversed only the rpm and then
    # asserted the power was unchanged, which asked for the wrong answer.
    forward = _write("fwd", 3000.0, 0.25)
    reverse = _write("rev", -3000.0, -0.25)
    assert reverse is not None, (
        "a counter-rotating rotor lost its entire table; a negative rpm is a "
        "direction, not a stopped rotor"
    )
    _, fwd = read_csv_table(forward, skip=1)
    _, rev = read_csv_table(reverse, skip=1)

    # THE FIXTURE MUST DISCRIMINATE, asserted before the comparisons that rest
    # on it. With a zero torque every check below passes under a wrong fix.
    assert float(fwd[0]["CQ_PUSHER"]) != 0.0, (
        f"this fixture states no torque, so it cannot tell the sign rules apart: {fwd[0]}"
    )

    for name in ("J_PUSHER", "CT_PUSHER"):
        assert rev[0][name] == fwd[0][name], (
            f"{name} normalises by the RATE, which has no sign: "
            f"{rev[0][name]} against {fwd[0][name]}"
        )
    assert float(rev[0]["CQ_PUSHER"]) == pytest.approx(-float(fwd[0]["CQ_PUSHER"])), (
        "CQ is the torque about the rotor's fixed axis, and a mirrored rotor "
        f"imparts the opposite swirl: {rev[0]['CQ_PUSHER']} against {fwd[0]['CQ_PUSHER']}"
    )
    for name in ("CP_PUSHER", "ETA_PUSHER", "ETAW_PUSHER"):
        assert rev[0][name] == fwd[0][name], (
            f"{name} rests on P = Q * omega, and reversing BOTH the torque and "
            f"the rotation leaves the power unchanged: {rev[0][name]} against {fwd[0][name]}"
        )
    assert float(rev[0]["J_PUSHER"]) > 0.0, (
        "J is V/(n D) and a rotor flying forwards has a positive advance "
        f"ratio whichever way it turns: {rev[0]}"
    )


def test_an_unsteady_rotor_table_is_the_window_average_and_not_the_last_step(tmp_path):
    """ITEM 16'S WINDOW REACHES THE LAST PRODUCT THAT DID NOT HAVE IT.

    The rotor table was built from `point.loads`, the NATIVE export, which
    states the last time step -- the owner's own answer of 2026-09-18. So an
    unsteady rotor table published one instant of a cycle beside a polar that
    averaged correctly, in the same folder, with neither file saying which it
    was. The independent review of `main` found it (L6-04).

    THE HISTORY IS ALREADY ON DISK. A plots table states `FX_<GROUP>` through
    `MZ_<GROUP>` per plot group, in NEWTONS -- measured on a licensed run. Item
    15 names a rotor's integration group after its alias, so the columns are
    `FX_PUSHER` and its five siblings.

    THE ARITHMETIC IS CHECKABLE BY HAND, which is the point of these numbers:
    `FZ_PUSHER` runs 100, 200, 300, 400 over steps 1 to 4. Over the window 3-4
    the mean is 350 and the LAST STEP is 400. A table built from the native
    export would carry the 400-equivalent and look identical.

    THIS TEST EXISTS BECAUSE THE TYPE CHECKER FOUND WHAT IT SHOULD HAVE. The
    first writing of the averaging path read `reference.sref` and
    `reference.cref`, which are not attributes of `ReferenceValues` -- an
    AttributeError the moment the path ran. The whole suite was green because
    NOTHING REACHED IT: no fixture carried a plots table with these columns.
    `mypy` caught it in CI. A path no case exercises is a path that is not
    delivered, which is this release's own recurring finding.
    """

    from pyflightstream.post.products import PolarPoint, matrix_rows, write_rotor_table
    from pyflightstream.post.products import _rotor_tables as rotor_tables
    from pyflightstream.results import parse_loads
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_products import LOADS
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
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
                'axis = "Z"',
                "rpm_sign = 1",
                "diameter_m = 1.2",
                'families_blades = ["Blade1"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )

    # THE PLOTS TABLE, in the export's own spelling: `{PARAM}_{GROUP}`, in
    # Newtons, with the group named for the rotor's alias.
    history = tmp_path / "plots.csv"
    lines = ["Time-step,FX_PUSHER,FY_PUSHER,FZ_PUSHER,MX_PUSHER,MY_PUSHER,MZ_PUSHER"]
    for step in range(1, 5):
        thrust = 100.0 * step
        lines.append(f"{step},0.0,0.0,{thrust:.5f},0.0,0.0,0.0")
    history.write_text("\n".join(lines) + "\n", encoding="utf-8")

    path = tmp_path / "P.txt"
    path.write_text(LOADS, encoding="utf-8")
    point = PolarPoint(name="P", loads=parse_loads(LOADS), loads_path=path)
    run_id = "camp/sim_0001/P"
    record = RunRecord(
        run_id=run_id,
        sim_id="0001",
        fs_version_requested="26.123",
        package_version="0.23.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status="CONVERGED",
        density_kg_m3=1.225,
        velocity_requested_m_s=40.0,
        mach=0.12,
        reductions={"rotors": {"PUSHER": {"rpm": 1200.0, "blades": 2}}},
    )

    matrix_row = next(
        (
            row
            for row in matrix_rows(workspace.root, "matriz").values()
            if str(getattr(row, "ref_code", "")) == "r002"
        ),
        None,
    )
    assert matrix_row is not None

    reference = _reference(area_m2=50.0, span_m=20.0, chord_m=2.526)

    def _thrust(window):
        tables = rotor_tables(
            workspace,
            "0001",
            [point],
            [record],
            {"P": [run_id]},
            reference,
            matrix_row,
            tmp_path / "out",
            plots={"P": history} if window else None,
            window=window,
        )
        assert tables, "the reference declares a rotor and no table was planned"
        target, _alias, plan = tables[0]
        written = write_rotor_table(
            target, rotor=plan["rotor"], rows=plan["rows"], reference=reference
        )
        assert written is not None, written
        from pyflightstream.post.products import read_csv_table

        _, rows = read_csv_table(written, skip=1)
        return float(rows[0]["CT_PUSHER"])

    early = _thrust((1, 2))
    late = _thrust((3, 4))

    # THE WINDOW IS WHAT MOVED and nothing else did, so the ratio is the ratio
    # of the two means: 350 over 150. Derived from the fixture, never read off
    # the implementation.
    assert late == pytest.approx(early * (350.0 / 150.0), rel=1e-6), (
        "the rotor table is not averaging over the row's window; "
        f"steps 1-2 mean 150 N and steps 3-4 mean 350 N: {early} and {late}"
    )


def test_every_row_is_dimensionalised_from_its_own_points_record(tmp_path):
    """A SWEEP IS A TABLE OF ITS POINTS, AND EACH POINT HAS ITS OWN AIR.

    `_rotor_tables` read the rotor speed, the density, the velocity and the
    Mach once off `records[0]`, and it HOISTED THE SPEED OUT OF THE POINT LOOP.
    Every row of a sweep was therefore normalised by the FIRST point's state.
    On an advance-ratio sweep -- the one shape this table exists for, where the
    rotor speed is what MOVES -- the second point came out a factor of four
    wrong in `CT`, `CQ` and `CP`, and `J` came out at the first point's value.

    THE ROW STILL LOOKED RIGHT, which is why four in-house rounds walked past
    it: `point_condition` is per point, so `ALPHA` and `MACH` in the same row
    were that point's own and correct, sitting beside coefficients computed
    from a different point entirely.

    Found by the independent review of `main` at 0.23.0, 2026-09-18.

    IT ASSERTS THE PLAN AND NOT A COEFFICIENT, deliberately. The plan row is
    where the borrowed value entered, so that is where a mutant has to show;
    a coefficient asserted at a value computed HERE would pass under the
    defect, which is the exact failure this release already shipped once in
    the ETAW sign.
    """

    from pyflightstream.post.products import PolarPoint
    from pyflightstream.post.products import _rotor_tables as rotor_tables
    from pyflightstream.results import parse_loads
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_products import LOADS
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
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
                'families_blades = ["Blade1"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )

    # TWO POINTS OF ONE ADVANCE-RATIO SWEEP: the rotor slows and the air does
    # not. Different densities too, so a borrowed density is visible as well.
    plan_rows = [("J050", 2400.0, 1.225), ("J100", 1200.0, 1.100)]

    points = []
    records = []
    sources = {}
    for name, rpm, density in plan_rows:
        path = tmp_path / f"{name}.txt"
        path.write_text(LOADS, encoding="utf-8")
        points.append(PolarPoint(name=name, loads=parse_loads(LOADS), loads_path=path))
        run_id = f"camp/sim_0001/{name}"
        sources[name] = [run_id]
        records.append(
            RunRecord(
                run_id=run_id,
                sim_id="0001",
                fs_version_requested="26.123",
                package_version="0.23.0",
                script_sha256="0" * 64,
                raw_flag=False,
                status="CONVERGED",
                density_kg_m3=density,
                velocity_requested_m_s=40.0,
                mach=0.12,
                reductions={"rotors": {"PUSHER": {"rpm": rpm, "blades": 2}}},
            )
        )

    # THE STAGE'S OWN ROUTE to the row, not a hand-built one: `matrix_rows` is
    # what `write_products` calls, so a change to that resolution reaches this
    # test instead of passing beside it.
    from pyflightstream.post.products import matrix_rows

    rows_of_the_matrix = matrix_rows(workspace.root, "matriz")
    matrix_row = next(
        (row for row in rows_of_the_matrix.values() if str(getattr(row, "ref_code", "")) == "r002"),
        None,
    )
    assert matrix_row is not None, (
        "the fixture no longer carries a row naming r002: "
        f"{[getattr(r, 'ref_code', None) for r in rows_of_the_matrix.values()]}"
    )

    tables = rotor_tables(
        workspace,
        "0001",
        points,
        records,
        sources,
        _reference(area_m2=50.0, span_m=20.0, chord_m=2.526),
        matrix_row,
        tmp_path / "out",
    )
    assert tables, "the reference declares a rotor and no table was planned"

    _target, _alias, plan = tables[0]
    rows = plan["rows"]
    assert len(rows) == 2, rows
    assert [row["rpm"] for row in rows] == [2400.0, 1200.0], (
        "both rows carry the first point's rotor speed; a sweep's second point "
        f"turns at its own rate -- {[row['rpm'] for row in rows]}"
    )
    assert [row["density"] for row in rows] == [1.225, 1.100], (
        f"both rows carry the first point's air -- {[row['density'] for row in rows]}"
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
    rotor gets a rotor table, with the alias on its first line.
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
    tables = [Path(p) for p in written if str(p).endswith("_rotor.csv")]
    assert tables, (
        "the campaign turns a rotor and the stage wrote no rotor table; "
        f"it wrote {sorted(Path(p).name for p in written)}"
    )
    first = tables[0].read_text(encoding="utf-8").splitlines()[0]
    assert first.strip() == "PUSHER", first

    # AND A VALUE, DERIVED HERE FROM THE EXPORT AND THE DEFINITION, which is what
    # the alias line alone never proved. The shaft is X, so the thrust is the X
    # force of family B: `Cx * q * S`, and `CT = T / (rho n^2 D^4)`.
    from pyflightstream.post.products import read_csv_table
    from pyflightstream.results import parse_loads

    (record,) = [r for r in workspace.read_manifest() if r.sim_id == "6002"]
    loads_file = next(o for o in record.outputs if o.endswith("J+170.txt"))
    report = parse_loads((workspace.sim_dir("6002") / loads_file).read_text(encoding="utf-8"))
    rho, speed = record.density_kg_m3, report.reference_velocity_m_s
    rps = 2200.0 / 60.0
    thrust = report.surfaces["B"]["Cx"] * 0.5 * rho * speed**2 * 50.0
    expected = thrust / (rho * rps**2 * 1.2**4)
    _columns, rows = read_csv_table(tables[0], skip=1)
    assert expected != 0.0, "the fixture's family carries no X force, so nothing is proved"
    assert float(rows[0]["CT_PUSHER"]) == pytest.approx(expected, rel=1e-4), rows[0]


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
    target = polars / "P0001-M150_PUSHER_rotor.csv"

    from pyflightstream.post import products as module

    # A row narrower than the header is what the funnel refuses.
    original = module.rotor_coefficient_columns
    try:
        module.rotor_coefficient_columns = lambda alias: ("ONLY_ONE",)
        # NAMED, not blind: a bare `Exception` here would pass on an
        # AttributeError from the patch itself and prove nothing about the
        # funnel's refusal, which is what this test is about.
        with pytest.raises(module.ProductError):
            module.write_rotor_table(
                target,
                rotor=_rotor("Z"),
                rows=[
                    {
                        "surfaces": _surfaces(Blade1={"Cz": 0.5}),
                        "condition": {"MACH": 0.15},
                        "rpm": 3000.0,
                        "density": 1.225,
                        "speed": 40.0,
                    }
                ],
                reference=_reference(),
            )
    finally:
        module.rotor_coefficient_columns = original

    left = sorted(p.name for p in polars.iterdir())
    assert left == [], f"the refusal left files in the products folder: {left}"
