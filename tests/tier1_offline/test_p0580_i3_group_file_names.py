"""Two groups of one file name, after the rule of the group files (PFS-2231, lane I3).

THE REQUIREMENT (design of the post outputs, section 7.2; ``docs/pproc/group-files.md``).
A group's name reaches ``P<POL>-<GROUP>-<KIND>.csv`` through the one rule of the alias and
group files (``pyflightstream._tokens.file_name_part``), a numbered key is written
``g<NN>``, and a Windows file system does not tell two spellings apart by case. Two
``[groups]`` keys that reach one file are refused when the pproc is read, naming both, and
a key that reaches the file of a rotor alias is refused at the post with the rotor's group
standing, naming both.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I3-GROUPFILES")])


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Wing", "WING"),
        ("1", "g01"),
        ("1", "01"),
        ("Left/Right", "left_right"),
    ],
    ids=["case", "numbered-twin", "numbered-zero", "rule-and-case"],
)
def test_two_keys_of_one_file_are_refused_when_the_pproc_is_read(first, second):
    from pydantic import ValidationError

    from pyflightstream.cases.pproc import PprocSpec

    with pytest.raises(ValidationError) as refused:
        PprocSpec(groups={first: "W", second: "B"})
    said = str(refused.value)
    assert f"declares {first} and {second}" in said, said
    assert "one file name" in said, said


def test_keys_of_different_files_are_read():
    from pyflightstream.cases.pproc import PprocSpec

    spec = PprocSpec(groups={"Wing": "W", "Wings": "B", "1": "W", "2": "B"})
    assert list(spec.groups) == ["Wing", "Wings", "1", "2"]


@pytest.mark.parametrize("key", ["pusher/", "Pusher.", "PUSHER"])
def test_a_key_of_a_rotor_alias_file_is_refused_and_the_rotor_group_stands(key):
    from pyflightstream.post._family_polar import Family, PolarRotor, polar_groups
    from pyflightstream.post.axes import rotor_frame

    rotor = PolarRotor("PUSHER", 3, rotor_frame((-1.0, 0.0, 0.0), 3), 1.0, (0, 0, 0), ("B",))
    families = [Family("W", 1), Family("B", 2, 3)]
    refused: dict[str, str] = {}
    groups = polar_groups(families, [rotor], {key: ["B"], "WING": ["W"]}, refused=refused)
    assert [g.name for g in groups] == ["TOTAL", "AIRFRAME", "PUSHER", "WING"]
    assert f"[groups] declares {key}," in refused[key]
    assert "PUSHER: the rotor's own group" in refused[key]
