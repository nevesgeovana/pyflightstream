"""Tier 1, 0.58.0 PFS-2235 (FR-3795): an averaging window spans whole blade passages.

Written from the approved design page (section 7.3). The rotor fixture turns at
1200 rev/min with a 0.0001 s step: 500 steps per revolution, four blades, so a
passage is 125 steps.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows._reductions import require_whole_passages
from tests.tier1_offline.test_reduce_by_rotor import LIFTER, PUSHER, transition_case
from tests.tier1_offline.test_workflows import rendered, rotor_case


@pytest.mark.parametrize(("revs", "passages"), [("0.125", "0.496"), ("0.625", "2.496")])
def test_p0580_l4_a_window_of_a_fractional_number_of_passages_is_refused(revs, passages):
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG=revs))
    text = str(refused.value)
    assert f"POL `7001`: the averaging window `LAST_REVS_AVG = {revs[:5].rstrip('0')}`" in text
    assert f"spans `{passages}` blade passages" in text
    assert "whole number of passages, at least one" in text
    assert "`4` blades" in text and "`125` steps per passage" in text


def test_p0580_l4_the_message_names_the_nearest_valid_window():
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG="0.625"))
    assert "The nearest valid window is `LAST_REVS_AVG = 0.5` (`2` passages, `250` steps)." in str(
        refused.value
    )
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG=None, LAST_ITERS_AVG="312"))
    assert "The nearest valid window is `LAST_ITERS_AVG = 250` (`2` passages, `250` steps)." in str(
        refused.value
    )


def test_p0580_l4_under_one_passage_is_refused_with_one_passage_as_the_nearest():
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG="0.125"))
    assert "`LAST_REVS_AVG = 0.25` (`1` passages, `125` steps)" in str(refused.value)


@pytest.mark.parametrize("revs", ["0.25", "0.75"])
def test_p0580_l4_one_and_three_passages_are_accepted(revs):
    require_whole_passages(rotor_case(LAST_REVS_AVG=revs))


def test_p0580_l4_the_plan_refuses_the_row_when_its_script_is_built():
    with pytest.raises(CampaignConfigError, match="whole number of passages"):
        rendered(rotor_case(LAST_REVS_AVG="0.625"))
    assert "SOLVER" in rendered(rotor_case(LAST_REVS_AVG="0.75")).upper()


def test_p0580_l4_a_row_with_no_window_key_is_not_judged_here():
    require_whole_passages(rotor_case(LAST_REVS_AVG=None))


def test_p0580_l4_a_row_with_two_rotors_names_only_the_rotor_that_fails():
    """Both rotors turn 500 steps a revolution: four blades give 125, three give 166.67."""
    pusher = PUSHER.model_copy(update={"families_blades": ["PH1", "PH2", "PH3"]})
    lifter = LIFTER.model_copy(update={"families_blades": ["L1", "L2", "L3", "L4"]})
    case = transition_case(
        rotors={"LIFT_L1": lifter, "PUSHER": pusher},
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "1200"},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "1200"},
        ],
    )
    quarter = case.model_copy(update={"variables": {**case.variables, "LAST_REVS_AVG": "0.25"}})
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(quarter)
    text = str(refused.value)
    assert "rotor `PUSHER`" in text and "LIFT_L1" not in text
    assert "`3` blades" in text
    assert "`LAST_REVS_AVG = 0.333333` (`1` passages, `167` steps)" in text
    # THE CONTROL: a whole revolution is whole passages of both rotors.
    whole = case.model_copy(update={"variables": {**case.variables, "LAST_REVS_AVG": "1.0"}})
    require_whole_passages(whole)


def _sector_case(**variables):
    """One meshed blade of a six-bladed wheel: SYMMETRY PERIODIC, PERIODIC_COPIES 6."""
    from tests.tier1_offline.test_workflows import FIXTURE_ROTOR

    sector = FIXTURE_ROTOR.model_copy(update={"families_blades": ["Blade1"]})
    variables = {"SYMMETRY": "PERIODIC", **variables}
    case = rotor_case(BLADES=None, PERIODIC_COPIES="6", **variables)
    return case.model_copy(update={"rotors": {sector.alias: sector}})


def test_p0580_l4_a_periodic_sector_counts_the_wheels_blades_as_passages():
    """500 steps a revolution over six blades is a passage of 83.33 steps."""
    require_whole_passages(_sector_case(LAST_REVS_AVG="0.166667"))
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(_sector_case(LAST_REVS_AVG="0.083333"))
    text = str(refused.value)
    assert "`6` blades" in text
    assert (
        "The nearest valid window is `LAST_REVS_AVG = 0.166667` (`1` passages, `83` steps)." in text
    )


def test_p0580_l4_a_window_the_gate_accepts_is_cut_into_the_passages_it_was_accepted_for():
    """VV-F1: a six-blade block at 500 steps a revolution, a passage of 83.33 steps.

    The gate accepts ``LAST_REVS_AVG = 0.166667`` (83 steps, one passage on the
    steps the solver takes); the phase-locked cut must give that one passage
    rather than skip the window as shorter than 83.33 steps.
    """
    from pyflightstream.cases.workflows._reductions import reduction_windows
    from tests.tier1_offline.test_workflows import FIXTURE_ROTOR

    six = FIXTURE_ROTOR.model_copy(update={"families_blades": [f"Blade{n}" for n in range(1, 7)]})
    case = rotor_case(BLADES=None, LAST_REVS_AVG="0.166667")
    case = case.model_copy(update={"rotors": {six.alias: six}})
    require_whole_passages(case)
    plan = reduction_windows(case)
    assert plan is not None and plan["blades"] == 6
    phase_locked = plan["phase_locked"]
    assert isinstance(phase_locked, dict)
    assert "skipped" not in phase_locked, phase_locked
    assert phase_locked["period_steps"] == pytest.approx(500 / 6)
    assert phase_locked["windows"] == [[638, 720]]


def test_p0580_l4_without_periodic_symmetry_the_copies_are_not_blades():
    case = _sector_case(LAST_REVS_AVG="0.166667", SYMMETRY="NONE")
    with pytest.raises(CampaignConfigError, match="`1` blades"):
        require_whole_passages(case)


def test_p0580_l4_the_window_the_gate_accepts_is_cut_into_the_wheels_passages():
    """VV-F1: the gate and the passage cut read one count, the whole wheel's."""
    from pyflightstream.cases.workflows._reductions import reduction_windows

    case = _sector_case(LAST_REVS_AVG="0.166667")
    require_whole_passages(case)
    plan = reduction_windows(case)
    assert plan is not None
    assert plan["blades"] == 6
    phase_locked = plan["phase_locked"]
    assert isinstance(phase_locked, dict)
    assert "skipped" not in phase_locked, phase_locked
    assert phase_locked["period_steps"] == pytest.approx(500 / 6)
    assert len(phase_locked["windows"]) == 1


def _two_of_four(**variables):
    """Two meshed blades of a four-blade wheel: the block lists the meshed families only."""
    from tests.tier1_offline.test_workflows import FIXTURE_ROTOR

    half = FIXTURE_ROTOR.model_copy(update={"families_blades": ["Blade1", "Blade2"]})
    variables = {"SYMMETRY": "PERIODIC", "PERIODIC_COPIES": "2", **variables}
    case = rotor_case(**{"BLADES": None, **variables})
    return case.model_copy(update={"rotors": {half.alias: half}})


@pytest.mark.parametrize("blades", [None, "2", "4"])
def test_p0580_l4_a_two_family_sector_of_two_copies_is_a_four_blade_wheel(blades):
    """FR-68: a sector's block lists the meshed families; the wheel is them times the copies.

    ``BLADES`` unstated, stated as the meshed families' count (what a motion
    view fills in), or as the wheel's, is the same four-blade wheel.
    """
    from pyflightstream.cases.workflows._reductions import _blade_count, reduction_windows

    case = _two_of_four(BLADES=blades, LAST_REVS_AVG="0.25")
    assert _blade_count(case) == 4
    require_whole_passages(case)
    plan = reduction_windows(case)
    assert plan is not None and plan["blades"] == 4
    assert plan["per_blade"]["period_steps"] == pytest.approx(125)
    assert plan["blade_families"] == ["Blade1", "Blade2"]


def test_p0580_l4_a_two_family_sector_refuses_a_count_that_is_neither():
    from pyflightstream.cases.workflows._reductions import _blade_count

    with pytest.raises(CampaignConfigError, match="BLADES: 3 .* 2 blade"):
        _blade_count(_two_of_four(BLADES="3"))


def test_p0580_l4_a_sector_window_of_a_meshed_half_turn_is_two_passages_of_the_wheel():
    """Half a turn is two passages of the four-blade wheel, not one of the meshed pair."""
    require_whole_passages(_two_of_four(LAST_REVS_AVG="0.5"))
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(_two_of_four(LAST_REVS_AVG="0.375"))
    assert "`4` blades" in str(refused.value)


def test_p0580_l4_a_sector_places_its_second_blade_frame_by_the_wheels_count():
    """The blade frames read the same count: blade two of a 2-of-4 sector sits at 90 degrees."""
    from pyflightstream.cases.workflows._frames import _hub_basis, _rotor_blade_frames
    from pyflightstream.script import Script, helpers

    case = _two_of_four()
    rotor = case.rotors["ROTOR"]
    script = Script("26.127")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.entities.declare_boundaries({"Blade1": 1, "Blade2": 2})
    x_axis, y_axis = _hub_basis(rotor)
    hub = helpers.coordinate_frame(
        script, name="ROTOR_SMRP", origin=rotor.origin, x_axis=x_axis, y_axis=y_axis
    )
    before = script.render()
    _rotor_blade_frames(script, rotor, hub=hub, radical="ROTOR", view=case)
    turns = [
        float(line.split()[-1])
        for line in script.render()[len(before) :].splitlines()
        if line.startswith("ANGLE ")
    ]
    assert turns == [0.0, 90.0]


def test_p0580_l4_a_sector_block_listing_the_whole_wheel_skips_absent_families_at_plan(tmp_path):
    """FR-68: one meshed blade of a three-copy sector is three blades, not nine."""
    import warnings

    from pyflightstream._errors import PyflightstreamWarning
    from tests.tier1_offline.test_goal024_point_name import _plan
    from tests.tier1_offline.test_p0551_blade_order import fixture

    workspace, matrix, reference, _mesh, _names = fixture(tmp_path, count=3, sector=True)
    matrix.write_text(matrix.read_text().replace("PERIODIC_COPIES:6", "PERIODIC_COPIES:3"))
    meshed = reference.read_text(encoding="utf-8")
    reference.write_text(
        meshed.replace('["Blade1"]', '["Blade1", "Blade2", "Blade3"]'), encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", PyflightstreamWarning)
        accepted = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in accepted.points), accepted.summary()
    skipped = [str(w.message) for w in caught if "families_blades" in str(w.message)]
    assert len(skipped) == 2
    assert any("Blade2" in text for text in skipped)
    assert any("Blade3" in text for text in skipped)
    assert all("a family the geometry does not carry is skipped" in text for text in skipped)
    reference.write_text(meshed, encoding="utf-8")
    accepted = _plan(workspace, matrix)
    assert all(p.status.value == "READY" for p in accepted.points), accepted.summary()


def _qsteady_sector(tmp_path, families):
    from tests.tier1_offline.test_goal035_qsteady_rotor import (
        ROTOR,
        _blade_obj,
        _case,
        _with_obj,
    )

    rotor = ROTOR.model_copy(update={"families_blades": families})
    case = _case(rotor=rotor, SYMMETRY="PERIODIC", PERIODIC_COPIES="3")
    return _with_obj(case, _blade_obj(tmp_path / "sector.obj", blades=1), ("Blade1",))


def test_p0580_l4_a_qsteady_sector_records_the_wheels_blades(tmp_path):
    """FR-68 on qsteady_rotor: a block of the meshed Blade1 and three copies is a 3-blade wheel."""
    import json

    from tests.tier1_offline.test_goal035_qsteady_rotor import _lines

    _lines_, script = _lines(_qsteady_sector(tmp_path, ["Blade1"]))
    (record,) = [
        json.loads(text)
        for name, text in script.pending_input_files.items()
        if name.endswith("_qsteady.json")
    ]
    assert record["blades"] == 3
    assert record["families_blades"] == ["Blade1"]


def test_p0580_l4_a_qsteady_sector_block_ignores_absent_blades_and_records_three(tmp_path):
    import json

    from tests.tier1_offline.test_goal035_qsteady_rotor import _lines

    _text, script = _lines(_qsteady_sector(tmp_path, ["Blade1", "Blade2", "Blade3"]))
    (record,) = [
        json.loads(text)
        for name, text in script.pending_input_files.items()
        if name.endswith("_qsteady.json")
    ]
    assert record["blades"] == 3
    assert record["families_blades"] == ["Blade1"]


def test_p0580_l4_the_gate_and_cut_count_only_the_blades_the_bound_mesh_carries():
    from pyflightstream.cases.workflows._reductions import reduction_windows
    from tests.tier1_offline.test_workflows import FIXTURE_ROTOR

    full = FIXTURE_ROTOR.model_copy(update={"families_blades": [f"Blade{i}" for i in range(1, 7)]})
    case = _sector_case(LAST_REVS_AVG="0.166667").model_copy(
        update={"rotors": {full.alias: full}, "inventory": ("Blade1",)}
    )
    require_whole_passages(case)
    plan = reduction_windows(case)
    assert plan is not None and plan["blades"] == 6
    assert plan["blade_families"] == ["Blade1"]
    assert plan["phase_locked"]["period_steps"] == pytest.approx(500 / 6)


def test_p0580_l4_named_motion_views_use_each_rotors_present_families():
    from pyflightstream.cases.workflows._reductions import reduction_windows

    case = transition_case().model_copy(
        update={
            "inventory": ("LIFT_L1_B1", "PUSHER_B1"),
            "variables": {
                **transition_case().variables,
                "SYMMETRY": "PERIODIC",
                "PERIODIC_COPIES": "3",
                "LAST_REVS_AVG": "1",
            },
        }
    )
    require_whole_passages(case)
    plan = reduction_windows(case)
    assert plan is not None
    for alias, family in (("LIFT_L1", "LIFT_L1_B1"), ("PUSHER", "PUSHER_B1")):
        rotor = plan["rotors"][alias]
        assert rotor["blades"] == 3
        assert rotor["blade_families"] == [family]
