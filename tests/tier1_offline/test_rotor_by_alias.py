"""A row names its rotor by alias and states nothing else about it (FR-61, FR-63).

Her design of 2026-09-10. A motion record carries `MOVING_BC_ALIAS` and
nothing more: the hub, the axis, the sign, the blades and the diameter are
the reference's, stated once in the rotor's own block. What a row keeps is
what a row decides, which is WHICH rotors turn and at what operating point.

Two behaviours are measured here and they are one design:

* the record's alias resolves to the engine block, and the boundaries the
  motion moves are that rotor's own families, general first;
* an advance ratio resolves against THAT ROTOR's diameter, so one ratio
  written once gives two rotors of different sizes two different speeds.

WHY THESE FAIL BEFORE LANE B: a record's rotor identity is
``MOVING_BOUNDARIES`` today and the diameter is one number for the whole
configuration (``case.reference.propeller_diameter``), so the second case
cannot be expressed at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream._fsm import MESH_MARKER
from pyflightstream.cases import BladeDatum, EngineBlock, ReferenceData, SimCase, SweepAxis
from pyflightstream.cases.workflows import WORKFLOW_KEY, build_script, rotor_speed
from pyflightstream.script import Script

#: The two rotors of the use case, cut to what one row needs: a lifter of
#: four blades at 1.20 m and a pusher of three at 1.80 m, which is the pair
#: whose diameters differ.
LIFTER = EngineBlock(
    alias="LIFT_L1",
    axis="Z",
    rpm_sign=1,
    diameter_m=1.2,
    x_m=1.2,
    y_m=2.4,
    z_m=0.3,
    families_general=["LH_L1"],
    families_blades=["LB_L1_1", "LB_L1_2", "LB_L1_3", "LB_L1_4"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="X"),
)
PUSHER = EngineBlock(
    alias="PUSHER",
    axis="X",
    rpm_sign=1,
    diameter_m=1.8,
    x_m=7.2,
    families_general=["Spinner"],
    families_blades=["Blade_1", "Blade_2", "Blade_3"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)
MESH = [
    "LH_L1",
    "LB_L1_1",
    "LB_L1_2",
    "LB_L1_3",
    "LB_L1_4",
    "Spinner",
    "Blade_1",
    "Blade_2",
    "Blade_3",
    "W",
]


def saved_simulation(path: Path, names: list[str]) -> Path:
    """Write the smallest saved simulation the mesh reader accepts."""
    body = [MESH_MARKER, "9999", "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$"]
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


def two_rotor_case(tmp_path, **overrides) -> SimCase:
    """A row that states two rotors by alias and nothing else about them."""
    variables: dict[str, str | float | int | bool] = {
        WORKFLOW_KEY: "unsteady_rotor",
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.0001",
        "TIME_ITERATIONS": "720",
        "SYMMETRY": "NONE",
    }
    variables.update({k: v for k, v in overrides.items() if v is not None})
    return SimCase(
        sim_id="9201",
        aircraft="WORK",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
        geometry=str(saved_simulation(tmp_path / "work.fsm", MESH)),
        engines={"LIFT_L1": LIFTER, "PUSHER": PUSHER},
        aliases={
            "LIFT_L1": [*LIFTER.families_general, *LIFTER.families_blades],
            "PUSHER": [*PUSHER.families_general, *PUSHER.families_blades],
        },
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"},
            {"MOVING_BC_ALIAS": "PUSHER", "ADVANCE_RATIO": "0.85"},
        ],
    )


def rendered(case: SimCase) -> str:
    script = Script(version="26.123")
    build_script(case, script)
    return script.render()


def motion_payloads(text: str) -> list[str]:
    """The boundary list under each SET_MOTION_BOUNDARIES, in the order emitted."""
    lines = text.splitlines()
    return [
        lines[i + 1] for i, line in enumerate(lines) if line.startswith("SET_MOTION_BOUNDARIES")
    ]


def test_a_record_names_its_rotor_by_alias_and_moves_that_rotors_boundaries(tmp_path):
    """The alias is the only rotor identity a row carries, and it resolves to the mesh."""
    text = rendered(two_rotor_case(tmp_path))
    payloads = motion_payloads(text)
    assert len(payloads) == 2, f"one motion per record:\n{text}"
    lifter, pusher = payloads
    for name in LIFTER.families_blades:
        assert name in lifter or str(MESH.index(name) + 1) in lifter, lifter
    for name in PUSHER.families_blades:
        assert name in pusher or str(MESH.index(name) + 1) in pusher, pusher


def test_the_spinner_turns_with_its_blades(tmp_path):
    """Her words of 2026-09-10: the alias prescribes the motion and the spinner turns with it."""
    text = rendered(two_rotor_case(tmp_path))
    _, pusher = motion_payloads(text)
    assert "Spinner" in pusher or str(MESH.index("Spinner") + 1) in pusher, pusher


def test_one_ratio_gives_two_rotors_two_speeds_when_their_diameters_differ(tmp_path):
    """FR-63, and the reason a flight-condition ratio is legitimate over unlike rotors.

    Both records state the same ratio and nothing else. The lifter is
    1.20 m and the pusher 1.80 m, so ``n = V / (J D)`` is two different
    numbers, and a package holding ONE diameter for the configuration
    cannot express it.
    """
    case = two_rotor_case(tmp_path)
    case = case.model_copy(
        update={
            "motions": [
                {"MOVING_BC_ALIAS": "LIFT_L1", "ADVANCE_RATIO": "0.85"},
                {"MOVING_BC_ALIAS": "PUSHER", "ADVANCE_RATIO": "0.85"},
            ]
        }
    )
    from pyflightstream.cases.workflows import _motion_view

    speeds = [rotor_speed(_motion_view(case, record)).rpm for record in case.motions]
    assert speeds[0] != speeds[1], speeds
    # n = V / (J D), rpm = 60 n, and the ratio of the two speeds is the
    # inverse ratio of the diameters: 1.8 / 1.2 = 1.5.
    assert speeds[0] == pytest.approx(speeds[1] * 1.5, rel=1e-9)


def test_the_frames_a_rotor_instantiates_take_its_alias_as_their_radical(tmp_path):
    """FR-62: nine rotors instantiate nine sets rather than colliding on one radical.

    `<ALIAS>_SMRP` at the hub, `<ALIAS>_RMRP` turning with the motion, and
    `<ALIAS>_RMRP<k>` per blade of the block's own list. A family of
    `families_general` gets no frame: its local frame IS the rotor's,
    which is what makes the spinner ride the hub.
    """
    text = rendered(two_rotor_case(tmp_path))
    for name in (
        "LIFT_L1_SMRP",
        "LIFT_L1_RMRP",
        "LIFT_L1_RMRP1",
        "LIFT_L1_RMRP4",
        "PUSHER_SMRP",
        "PUSHER_RMRP",
        "PUSHER_RMRP3",
    ):
        assert name in text, f"{name} is not among the frames:\n{text[:400]}"
    assert "Spinner_SMRP" not in text, "a general family has no frame of its own"
    assert "PUSHER_RMRP4" not in text, "the pusher has three blades"


def test_the_0140_frame_names_survive_a_record_that_names_no_engine(tmp_path):
    """A row written before this release renders the frames it always did.

    The alias radical belongs to a record that CITES a rotor of the
    reference. A record still stating MOVING_BOUNDARIES has no alias to
    take one from, and renaming its frames would rewrite every golden of
    every 0.14.0 rotor row.
    """
    case = two_rotor_case(tmp_path)
    case = case.model_copy(
        update={
            "engines": {},
            "motions": [
                {"MOVING_BOUNDARIES": "LB_L1_1", "RPM": "2200", "ROTOR_AXIS": "Z"},
                {"MOVING_BOUNDARIES": "Blade_1", "RPM": "900", "ROTOR_AXIS": "X"},
            ],
        }
    )
    text = rendered(case)
    assert "PROP_MRP1" in text and "RotorAxis1" in text
    assert "PROP_MRP2" in text and "RotorAxis2" in text
    assert "_SMRP" not in text


def test_a_blade_the_mesh_lacks_gets_no_frame_and_the_count_stays(tmp_path):
    """The sector case: four blades declared, one meshed, one frame, count still four."""
    case = two_rotor_case(tmp_path)
    sector = ["LH_L1", "LB_L1_1", "W"]
    case = case.model_copy(
        update={
            "geometry": str(saved_simulation(tmp_path / "sector.fsm", sector)),
            "motions": [{"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"}],
        }
    )
    text = rendered(case)
    assert "LIFT_L1_RMRP1" in text
    assert "LIFT_L1_RMRP2" not in text, "no frame for a blade the mesh does not carry"
    assert case.engines["LIFT_L1"].blade_count == 4, "the count is the list, not the file"


def test_the_clock_follows_the_named_motion_and_not_the_fastest(tmp_path):
    """FR-64: the owner of the time step is declared, not inferred.

    The lifter turns at 2200 rev/min and the pusher slower. Naming the
    PUSHER as the clock must give a different time step from the one the
    fastest-rotor arithmetic gives, and this asserts the two are not equal
    rather than asserting a number, so it cannot be satisfied by a
    constant.
    """
    from pyflightstream.cases.workflows import _clock_speed, _motion_view

    base = two_rotor_case(tmp_path)
    base = base.model_copy(
        update={
            "motions": [
                {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"},
                {"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"},
            ]
        }
    )
    views = [_motion_view(base, record) for record in base.motions]
    speeds = [rotor_speed(view) for view in views]
    named = base.model_copy(update={"variables": {**base.variables, "CLOCK_MOTION": "PUSHER"}})
    assert _clock_speed(named, views, speeds).rpm == 900
    with pytest.warns(match="CLOCK_MOTION"):
        assert _clock_speed(base, views, speeds).rpm == 2200


def test_a_clock_naming_a_motion_the_row_does_not_state_is_refused(tmp_path):
    from pyflightstream.cases.workflows import _clock_speed, _motion_view

    case = two_rotor_case(tmp_path)
    views = [_motion_view(case, record) for record in case.motions]
    speeds = [rotor_speed(view) for view in views]
    case = case.model_copy(update={"variables": {**case.variables, "CLOCK_MOTION": "LIFT_R4"}})
    with pytest.raises(PyflightstreamError) as refused:
        _clock_speed(case, views, speeds)
    assert "LIFT_R4" in str(refused.value)
    assert "PUSHER" in str(refused.value), "the refusal names the motions the row states"


def test_a_row_stating_symmetry_loads_overrides_the_preset_and_warns(tmp_path):
    """FR-66: one preset serves a sector row and a full-wheel row.

    The value the script carries is the ROW's, and the warning names both
    so the override is not silent. Her first answer that hour was to
    refuse both stating it; she changed it the same hour.
    """
    from pyflightstream.cases.workflows import _row_symmetry_loads

    case = two_rotor_case(tmp_path)
    quiet = case.model_copy(update={"variables": {**case.variables}})
    assert _row_symmetry_loads(quiet, True) is True, "a row stating nothing inherits"
    stated = case.model_copy(update={"variables": {**case.variables, "SYMMETRY_LOADS": "false"}})
    with pytest.warns(match="SYMMETRY_LOADS"):
        assert _row_symmetry_loads(stated, True) is False
    # Agreeing is not an override and warns nothing.
    agreeing = case.model_copy(update={"variables": {**case.variables, "SYMMETRY_LOADS": "true"}})
    assert _row_symmetry_loads(agreeing, True) is True


def test_a_symmetry_loads_that_is_not_a_yes_or_a_no_is_refused(tmp_path):
    from pyflightstream.cases.workflows import _row_symmetry_loads

    case = two_rotor_case(tmp_path)
    case = case.model_copy(update={"variables": {**case.variables, "SYMMETRY_LOADS": "sector"}})
    with pytest.raises(PyflightstreamError) as refused:
        _row_symmetry_loads(case, None)
    assert "sector" in str(refused.value)


def test_an_incidence_the_row_states_reaches_the_solver(tmp_path):
    """FR-69, and the measured defect it closes.

    A row sweeping the advance ratio reached the solver at incidence
    ZERO, and the only record of the incidence was that nobody had
    written one: the point carries the swept axis alone and the builder
    read `case.point.get("alpha", 0.0)`. The row can now state the angle
    it is not sweeping, and it is read.

    THE ANGLE DOES NOT ENTER THE POINT, deliberately: the point's
    coordinates are run IDENTITY, and carrying a held angle there would
    rename runs that already exist to say something they always meant.

    REACHABLE FROM PYTHON AND NOT YET FROM A ROW: the key that puts the
    angle on the case is the FLIGHT_CONDITION cell, and that half is lane
    D, which is the column removal and is on its own branch. This test
    sets the variable directly, so it measures the reader that consumes
    it rather than the writer that will fill it.
    """
    from pyflightstream.cases.workflows import _angle

    # A J SWEEP: the point carries the ratio and no angle, which is the
    # shape the defect was measured in.
    swept_ratio = two_rotor_case(tmp_path).model_copy(
        update={
            "sweep": SweepAxis(type="advance_ratio", values=[0.85]),
            "point": {"advance_ratio": 0.85},
        }
    )
    assert _angle(swept_ratio, "alpha") == 0.0, "a row stating nothing is at zero, as before"
    stated = swept_ratio.model_copy(
        update={"variables": {**swept_ratio.variables, "ALPHA": "4.0", "BETA": "1.5"}}
    )
    assert _angle(stated, "alpha") == 4.0
    assert _angle(stated, "beta") == 1.5
    assert "alpha" not in stated.point, "the row's angle does not become run identity"
    # The POINT still wins, because a swept angle is the point's.
    swept_angle = stated.model_copy(update={"point": {"alpha": 2.0}})
    assert _angle(swept_angle, "alpha") == 2.0
    assert _angle(swept_angle, "beta") == 1.5, "the one it does not sweep is still the row's"


def test_a_record_citing_an_alias_the_reference_does_not_declare_is_refused(tmp_path):
    case = two_rotor_case(tmp_path)
    case = case.model_copy(update={"motions": [{"MOVING_BC_ALIAS": "LIFT_L9"}]})
    with pytest.raises(PyflightstreamError) as refused:
        rendered(case)
    message = str(refused.value)
    assert "LIFT_L9" in message
    assert "PUSHER" in message, "the refusal names the engines the reference does declare"


def test_a_record_still_naming_its_boundaries_warns_from_the_ledger(tmp_path):
    """TW2-15: the promise was registered and never spoken.

    `ROW_MOVING_BOUNDARIES` sat in the deprecation ledger with a removal
    version, and nothing called its `message()`. A record stating
    `MOVING_BOUNDARIES` was accepted in SILENCE, so the deprecation the
    ledger announces was invisible to the user it is for.

    The text is the ledger entry's own, so the release it names is the one
    the deadline guard enforces rather than a second copy nothing keeps
    equal.
    """
    from pyflightstream._deprecations import ROW_MOVING_BOUNDARIES
    from pyflightstream.cases.workflows import _motion_view

    case = two_rotor_case(tmp_path).model_copy(
        update={"engines": {}, "motions": [{"MOVING_BOUNDARIES": "LB_L1_1", "RPM": "2200"}]}
    )
    with pytest.warns(match="MOVING_BOUNDARIES") as caught:
        _motion_view(case, case.motions[0])
    assert ROW_MOVING_BOUNDARIES.message() in str(caught[0].message)
    assert f"removed in v{ROW_MOVING_BOUNDARIES.removal_version}" in str(caught[0].message)


def test_a_record_stating_both_spellings_is_refused(tmp_path):
    """One rotor identity per record: the new spelling and the old cannot both decide."""
    case = two_rotor_case(tmp_path)
    case = case.model_copy(
        update={
            "motions": [
                {"MOVING_BC_ALIAS": "LIFT_L1", "MOVING_BOUNDARIES": "Blade_1", "RPM": "2200"}
            ]
        }
    )
    with pytest.raises(PyflightstreamError) as refused:
        rendered(case)
    assert "MOVING_BC_ALIAS" in str(refused.value)
    assert "MOVING_BOUNDARIES" in str(refused.value)
