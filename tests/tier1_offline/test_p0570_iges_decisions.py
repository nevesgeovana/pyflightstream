"""R1-IGES-010 (0.57.0): IGES names are read byte for byte and decoded with a stated encoding."""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from tests.tier1_offline.test_p0560_iges import Iges, square


def _raw(tmp_path, payload: bytes):
    """A two-face file whose first level carries a NAME with the exact ``payload`` bytes."""
    iges = Iges()
    iges.patch(square(0, 0, 1, 1), level=1)
    iges.patch(square(0, 0, 1, 1, z=1), level=2)
    iges.name(1, payload.decode("latin-1"))
    iges.name(2, "Plain")
    return iges.write(tmp_path / "raw.igs")


@pytest.mark.requirement("FR-3705")
def test_p0570_utf8_name_decodes_with_the_stated_encoding(tmp_path):
    from pyflightstream.workspace._iges_names import read_iges_names

    path = _raw(tmp_path, "Asa_ção".encode())
    assert read_iges_names(path, name_encoding="utf-8").faces == ("Asa_ção", "Plain")


@pytest.mark.requirement("FR-3705")
def test_p0570_default_encoding_is_latin1_and_never_guesses(tmp_path):
    from pyflightstream.workspace._iges_names import read_iges_names

    payload = "Asa_ção".encode()
    path = _raw(tmp_path, payload)
    assert read_iges_names(path).faces[0] == payload.decode("latin-1")


@pytest.mark.requirement("FR-3705")
def test_p0570_invalid_bytes_for_the_encoding_are_refused_not_replaced(tmp_path):
    from pyflightstream.workspace._iges_names import read_iges_names

    path = _raw(tmp_path, b"Asa_\xe7")
    with pytest.raises(InputArtifactError, match="utf-8"):
        read_iges_names(path, name_encoding="utf-8")


@pytest.mark.requirement("FR-3705")
def test_p0570_unknown_encoding_is_refused(tmp_path):
    from pyflightstream.workspace._iges_names import read_iges_names

    with pytest.raises(InputArtifactError, match="not a known"):
        read_iges_names(_raw(tmp_path, b"Asa"), name_encoding="no-such-codec")


@pytest.mark.requirement("FR-3705")
def test_p0570_written_names_round_trip_in_utf8_with_byte_counts(tmp_path):
    from pyflightstream.workspace._iges_names import (
        flag_curves_on_surfaces,
        name_faces,
        read_iges_names,
    )

    iges = Iges()
    iges.patch(square(0, 0, 1, 1), level=0)
    iges.patch(square(0, 0, 1, 1, z=1), level=0)
    source = iges.write(tmp_path / "raw.igs")
    names = ["Asa_ção", "Leme_€"]
    named = name_faces(source, tmp_path / "named.igs", names, name_encoding="utf-8")
    flagged = flag_curves_on_surfaces(named, tmp_path / "flagged.igs")
    for path in (named, flagged):
        assert read_iges_names(path, name_encoding="utf-8").faces == tuple(names)
        assert {len(line) for line in path.read_bytes().splitlines()} == {80}
    assert b"9HAsa_" in named.read_bytes()  # 9 bytes in UTF-8, 7 characters


@pytest.mark.requirement("FR-3705")
def test_p0570_a_name_the_encoding_cannot_hold_is_refused_before_writing(tmp_path):
    from pyflightstream.workspace._iges_names import name_faces

    iges = Iges()
    iges.patch(square(0, 0, 1, 1), level=0)
    source = iges.write(tmp_path / "raw.igs")
    with pytest.raises(InputArtifactError, match="cannot be written"):
        name_faces(source, tmp_path / "n.igs", ["Asa_€"], name_encoding="latin-1")
    assert not (tmp_path / "n.igs").exists()


def _symmetry_grid(tmp_path, line):
    path = tmp_path / "grid.toml"
    path.write_text(f"[defaults]\n{line}\n", encoding="utf-8")
    return path


@pytest.mark.requirement("FR-3705")
def test_p0570_symmetry_is_none_unless_the_grid_states_a_plane(tmp_path):
    """R3-006: no half-model mirroring is inferred; the plane is stated."""
    from pyflightstream.workspace._iges_grid_config import read_grid

    assert read_grid(_symmetry_grid(tmp_path, "size = 1.0")).symmetry == "none"
    assert read_grid(_symmetry_grid(tmp_path, 'symmetry = "y"')).symmetry == "y"


@pytest.mark.requirement("FR-3705")
def test_p0570_an_unknown_symmetry_is_refused(tmp_path):
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace._iges_grid_config import read_grid

    with pytest.raises(InputValueError, match="symmetry"):
        read_grid(_symmetry_grid(tmp_path, 'symmetry = "auto"'))


def _crossing():
    """Three quads of three components that meet along one edge, open elsewhere."""
    import numpy as np

    verts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, -1, 0], [1, -1, 0], [0, 0, 1], [1, 0, 1]],
        dtype=float,
    )
    return verts, {"A": [[0, 1, 3, 2]], "B": [[0, 1, 5, 4]], "C": [[0, 1, 7, 6]]}


@pytest.mark.requirement("FR-3705")
@pytest.mark.parametrize(("symmetry", "expected"), [(None, None), ("none", None), ("y", 1)])
def test_p0570_the_skin_mirrors_only_across_the_stated_plane(monkeypatch, symmetry, expected):
    from pyflightstream.workspace import _iges_skin

    seen = []
    real = _iges_skin._Assembly.oriented

    def spy(self, mirror):
        seen.append(mirror)
        return real(self, mirror)

    monkeypatch.setattr(_iges_skin._Assembly, "oriented", spy)
    verts, families = _crossing()
    if symmetry is None:
        _iges_skin.outer_skin(verts, families)
    else:
        _iges_skin.outer_skin(verts, families, symmetry=symmetry)
    assert seen == [expected]
