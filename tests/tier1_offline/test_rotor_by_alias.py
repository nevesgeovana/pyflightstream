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


def test_a_record_citing_an_alias_the_reference_does_not_declare_is_refused(tmp_path):
    case = two_rotor_case(tmp_path)
    case = case.model_copy(update={"motions": [{"MOVING_BC_ALIAS": "LIFT_L9"}]})
    with pytest.raises(PyflightstreamError) as refused:
        rendered(case)
    message = str(refused.value)
    assert "LIFT_L9" in message
    assert "PUSHER" in message, "the refusal names the engines the reference does declare"


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
