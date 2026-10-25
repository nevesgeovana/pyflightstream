"""P0451: axis='X', blade1.zero='Y' retains the user's coordinate labels."""

import numpy as np
import pytest
from pydantic import ValidationError

from pyflightstream.cases import RotorBlock
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._frames import _hub_basis
from pyflightstream.script import Script
from tests.tier1_offline.test_p0451_probe_phases import _build, _case, _entry, _power
from tests.tier1_offline.test_rotor_by_alias import two_rotor_case


def _rotor(axis="X", zero="Y"):
    try:
        return RotorBlock(
            alias="PUSHER",
            axis=axis,
            diameter_m=2,
            families_blades=["Blade1", "Blade2", "Blade3", "Blade4"],
            x_m=9.35791,
            z_m=1.14813,
            blade1={"azimuth_deg": 0, "zero": zero},
        )
    except ValidationError as error:
        pytest.fail(f"P0451 specified rotor must load: {error}")


@pytest.mark.parametrize("zero", ["Y", "Z", "-Y"], ids=["P0451-Y", "P0451-Z", "P0451-minusY"])
def test_p0451_labels_remain_on_the_declared_axes(zero):
    rotor = _rotor(zero=zero)
    x, y = _hub_basis(rotor)
    expected = np.diag([1, -1, -1] if zero == "-Y" else [1, 1, 1])
    np.testing.assert_allclose([x, y, np.cross(x, y)], expected)
    if zero == "Y":
        np.testing.assert_allclose(
            np.array(rotor.origin) + np.array([-0.25, -1, 0]) @ np.array([x, y, np.cross(x, y)]),
            [9.10791, -1, 1.14813],
        )


def test_p0451_tilted_table_keeps_shaft_x(tmp_path):
    rotor = _rotor({"shaft": "X", "vector_wrt_global": [0.996, 0, 0.087]})
    x, y = _hub_basis(rotor)
    np.testing.assert_allclose(x, np.array([0.996, 0, 0.087]) / np.linalg.norm([0.996, 0, 0.087]))
    np.testing.assert_allclose(y, [0, 1, 0])
    case = _case(tmp_path, [])
    installed = rotor.model_copy(update={"alias": "ROTOR", "families_blades": ["W"]})
    script = _build(case.model_copy(update={"rotors": {"ROTOR": installed}}))
    lines = script.render().splitlines()
    for name, expected in (
        ("ROTOR_SMRP", [x, y, np.cross(x, y)]),
        ("ROTOR_BMRP", np.eye(3)),
    ):
        at = lines.index(f"NAME {name}")
        fields = dict(line.split(maxsplit=1) for line in lines[at + 1 : at + 13])
        actual = [[float(fields[f"VECTOR_{a}_{b}"]) for b in "XYZ"] for a in "XYZ"]
        np.testing.assert_allclose(actual, expected)
    assert "SET_MOTION_ROTOR_AXIS 1 X" in script.render()


def test_p0451_owner_probe_is_ahead_of_the_disk(tmp_path):
    probe = dict(
        _entry("default"),
        frame="ROTOR_SMRP",
        scale="rotor_radius",
        lines=[dict(start=[-0.25, -1, 0], end=[-0.25, 1, 0])],
    )
    case = _case(tmp_path, [], [probe])
    rotor = _rotor().model_copy(update={"alias": "ROTOR", "families_blades": ["W"]})
    script = _build(case.model_copy(update={"rotors": {"ROTOR": rotor}}))
    assert len(script.pending_input_files) == 1
    payload = next(iter(script.pending_input_files.values()))
    first = [float(value) for value in payload.splitlines()[1].split(",")[:3]]
    np.testing.assert_allclose(first, [9.10791, -1, 1.14813], atol=1e-5)


@pytest.mark.parametrize(
    "axis,zero,match",
    [
        ([1, 0, 0], "Y", "vector_wrt_global"),
        ("X", "-X", "shaft X"),
        ({"shaft": "X", "vector_wrt_global": [0, 0, 0]}, "Y", "length"),
        ({"shaft": "X", "vector_wrt_global": [float("inf"), 0, 0]}, "Y", "finite"),
        ({"shaft": "X", "vector_wrt_global": [0, 0, 1]}, "Y", "90.00"),
        ({"shaft": "X", "vector_wrt_global": [1, 0, 0], "typo": 1}, "Y", "typo"),
    ],
    ids=["P0451-vector", "P0451-datum", "P0451-length", "P0451-finite", "P0451-angle", "P0451-key"],
)
def test_p0451_refusals_explain_the_translation(axis, zero, match):
    with pytest.raises(ValidationError, match=match) as caught:
        RotorBlock(alias="R", axis=axis, diameter_m=2, families_blades=["B"], blade1={"zero": zero})
    if match == "typo":
        assert any(
            error["type"] == "extra_forbidden" and error["loc"][-1] == "typo"
            for error in caught.value.errors()
        )


@pytest.mark.parametrize("power", [False, True], ids=["P0451-probe", "P0451-power"])
def test_p0451_table_and_letter_emit_identical_scripts_and_body_probe(tmp_path, power):
    case = _case(
        tmp_path, [_power()] if power else [], [dict(_entry("default"), frame="ROTOR_BMRP")]
    )
    rotor = case.rotors["ROTOR"]
    letter = RotorBlock.model_validate(dict(rotor.model_dump(), axis="X", blade1={"zero": "Y"}))
    table = RotorBlock.model_validate(
        dict(
            rotor.model_dump(),
            axis={"shaft": "X", "vector_wrt_global": [1, 0, 0]},
            blade1={"zero": "Y"},
        )
    )
    first = _build(case.model_copy(update={"rotors": {"ROTOR": letter}}))
    second = _build(case.model_copy(update={"rotors": {"ROTOR": table}}))
    assert first.render() == second.render()
    assert "ROTOR_BMRP" in first.render()
    assert "SET_MOTION_ROTOR_AXIS 1 X" in first.render()


def test_p0451_owner_emitted_frames_and_rotations(tmp_path):
    case = two_rotor_case(tmp_path)
    rotor = _rotor().model_copy(update={"families_blades": case.rotors["LIFT_L1"].families_blades})
    variables = dict(case.variables, CLOCK_MOTION="PUSHER")
    case = case.model_copy(
        update={
            "rotors": {"PUSHER": rotor},
            "variables": variables,
            "motions": [{"MOVING_BC_ALIAS": "PUSHER", "RPM": "1200"}],
            "aliases": {"PUSHER": rotor.members},
        }
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    for name in [
        "PUSHER_SMRP",
        "PUSHER_RMRP",
        "PUSHER_BMRP",
        *[f"PUSHER_RMRP{k}" for k in range(1, 5)],
    ]:
        start = lines.index(f"NAME {name}")
        values = dict(line.split(maxsplit=1) for line in lines[start + 1 : start + 13])
        basis = [[float(values[f"VECTOR_{a}_{b}"]) for b in "XYZ"] for a in "XYZ"]
        np.testing.assert_allclose(basis, np.eye(3))
        np.testing.assert_allclose([float(values[f"ORIGIN_{a}"]) for a in "XYZ"], rotor.origin)
    for angle in (0, 90, 180, 270):
        assert f"ROTATION_AXIS X\nANGLE {float(angle)}" in script.render()
    assert "SET_MOTION_ROTOR_AXIS 1 X" in script.render()


def test_p0451_plan_resolves_body_probes_for_every_rotor(tmp_path):
    from tests.tier1_offline.test_tier3_offline import (
        TOUR,
        _one_row_matrix,
        _rendered,
        _tier3_copy,
    )

    root = _tier3_copy(tmp_path)
    probes = "".join(
        f'[[probes]]\nkind = "instantaneous"\nframe = "{alias}_BMRP"\n'
        'parameters = ["VX"]\npoints = 2\nscale = "rotor_radius"\n'
        "[[probes.lines]]\nstart = [0, 0, 0]\nend = [0, 1, 0]\n"
        for alias in ("PORT", "STARBOARD")
    )
    (root / "inputs/pproc/p005.toml").write_text(probes)
    row = next(line for line in TOUR.read_text().splitlines() if line.startswith("1022 "))
    plan, rendered = _rendered(root, _one_row_matrix(root, "body.fs", row))
    assert not plan.blocked, plan.summary()
    text = next(iter(rendered.values()))
    for alias in ("PORT", "STARBOARD"):
        assert text.count(f"NAME {alias}_BMRP\n") == 1


def test_p0451_tilted_lattice_stations_follow_global_shaft(tmp_path):
    from pyflightstream.post.farfield_fields import recorded_layout
    from tests.tier1_offline.test_p0451_probe_phases import _power

    case = _case(tmp_path, [_power()])
    original = case.rotors["ROTOR"]
    rotor = RotorBlock.model_validate(
        dict(
            original.model_dump(),
            axis={"shaft": "X", "vector_wrt_global": [0.996, 0, 0.087]},
            blade1={"zero": "Y"},
        )
    )
    script = _build(case.model_copy(update={"rotors": {"ROTOR": rotor}}))
    shape = next(s for s in script.farfield_layout[-1]["shapes"] if s["kind"] == "lattice")
    layout = recorded_layout([shape])
    axial = (layout.lattice_m - np.array(rotor.origin)) @ np.array(rotor.axis_vector)
    expected = layout.lattice.dimensional_points()[:, 0]
    np.testing.assert_allclose(axial, expected, atol=1e-12)
