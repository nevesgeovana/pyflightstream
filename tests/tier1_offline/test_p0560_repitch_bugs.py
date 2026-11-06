"""P0560-REPITCH-BUGS: repitch keeps the face order, refuses a rotor with no axis in words.

Usage: pyfs-workspace geometry repitch sector.obj --morphing morphing.toml --out pitched.obj
"""

from pathlib import Path

import pytest

from pyflightstream.workspace._refine._obj import read_obj
from tests.tier1_offline.test_p0551_repitch import control, invoke, source_mesh


def face_lines(path: Path) -> list[str]:
    """Return the group and face lines of an OBJ, in file order, as written."""
    return [
        " ".join(line.split())
        for line in path.read_text().splitlines()
        if line.split()[:1] in (["g"], ["f"], ["o"])
    ]


@pytest.mark.requirement("FR-3760")
def test_p0560_repitch_keeps_the_face_order_of_an_obj_that_returns_to_a_family(tmp_path):
    source = source_mesh(tmp_path)
    lines = source.read_text().splitlines()
    first = lines.index("g Blade1")
    # Blade1's last face moves behind the Spinner block, under a second "g Blade1".
    moved = lines.pop(lines.index("g Spinner") - 1)
    assert lines[first] == "g Blade1"
    lines += ["g Blade1", moved]
    source.write_text("\n".join(lines) + "\n")
    out = tmp_path / "pitched.obj"
    assert invoke(source, control(tmp_path, 1.0, 'hub_method = "rings"'), out) == 0
    assert face_lines(out) == face_lines(source)
    assert read_obj(out).families == read_obj(source).families


@pytest.mark.requirement("FR-3760")
def test_p0560_repitch_of_one_block_per_family_is_written_as_before(tmp_path):
    source = source_mesh(tmp_path)
    out = tmp_path / "pitched.obj"
    assert invoke(source, control(tmp_path, 1.0, 'hub_method = "rings"'), out) == 0
    assert face_lines(out) == face_lines(source)


@pytest.mark.requirement("FR-3761")
def test_p0560_repitch_refuses_a_rotor_with_no_axis_in_words(tmp_path, capsys):
    source = source_mesh(tmp_path)
    (tmp_path / "rotor.toml").write_text('[R]\nkind = "rotor"\n')
    config = control(tmp_path, 1.0, 'reference = "rotor.toml"')
    out = tmp_path / "bad.obj"
    assert invoke(source, config, out) == 2
    err = capsys.readouterr().err
    assert "states no 'axis'" in err and "Traceback" not in err
    assert not list(tmp_path.glob("bad.*"))
