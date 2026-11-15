"""The groups of a polar and their ids (PFS-2231, lane L2).

THE REQUIREMENT (design of the post outputs, sections 4.4 and 7.2). TOTAL and
AIRFRAME are written for every polar, every rotor is a group by itself, a declared
group is numbered 100 + k; a declared group equal to a rotor alias is refused and
the rotor's own group stands; a group of one rotor's families carries its id (the
condition of an RCOEF file); a numbered group is written g<NN>.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-L2-GROUPS")])


def test_a_declared_group_equal_to_a_rotor_alias_is_refused_and_the_rotor_group_stands():
    from pyflightstream.post._family_polar import Family, PolarRotor, polar_groups
    from pyflightstream.post.axes import rotor_frame

    rotor = PolarRotor("PUSHER", 3, rotor_frame((-1.0, 0.0, 0.0), 3), 1.0, (0, 0, 0), ("B",))
    families = [Family("W", 1), Family("B", 2, 3)]
    refused: dict[str, str] = {}
    groups = polar_groups(families, [rotor], {"pusher": ["B"], "WING": ["W"]}, refused=refused)
    assert [(g.name, g.group_id, g.rotor_id) for g in groups] == [
        ("TOTAL", 0, None),
        ("AIRFRAME", 1, None),
        ("PUSHER", 13, 3),
        ("WING", 102, None),
    ]
    assert "[groups] declares pusher, a default group" in refused["pusher"]
    assert "PUSHER: the rotor's own group" in refused["pusher"]


def test_a_declared_group_of_one_rotors_families_carries_its_id_for_rcoef():
    from pyflightstream.post._family_polar import Family, PolarRotor, polar_groups
    from pyflightstream.post.axes import rotor_frame

    rotor = PolarRotor("PUSHER", 0, rotor_frame((-1.0, 0.0, 0.0)), 1.0, (0, 0, 0), ("B1", "B2"))
    families = [Family("W", 1), Family("B1", 2, 0), Family("B2", 3, 0)]
    groups = polar_groups(families, [rotor], {"BLADE1": ["B1"], "MIXED": ["all"]})
    by_name = {g.name: g for g in groups}
    assert by_name["BLADE1"].rotor_id == 0
    assert by_name["MIXED"].rotor_id is None
    assert by_name["AIRFRAME"].members == ("W",)


def test_a_numbered_group_is_written_g_nn():
    from pyflightstream.post._family_polar import Family, polar_groups

    groups = polar_groups([Family("W", 1)], [], {"1": ["W"]})
    assert groups[-1].name == "g01"


def test_two_groups_of_one_file_name_are_refused_at_the_pproc_naming_both():
    """Lane F1: ``Left/Right`` and ``Left_Right`` are one file after the rule of the files.

    A group's name reaches ``P<POL>-<GROUP>-<KIND>.csv`` through the one rule of the
    alias and group files (``docs/pproc/group-files.md``), so the second group's files
    would overwrite the first's; the pproc refuses the pair when it is read and names both.
    """
    from pydantic import ValidationError

    from pyflightstream.cases.pproc import PprocSpec

    with pytest.raises(ValidationError) as refused:
        PprocSpec(groups={"Left/Right": "W", "Left_Right": "B"})
    said = str(refused.value)
    assert "Left/Right" in said and "Left_Right" in said, said
    spec = PprocSpec(groups={"Left/Right": "W", "Left": "B"})
    assert list(spec.groups) == ["Left/Right", "Left"]
