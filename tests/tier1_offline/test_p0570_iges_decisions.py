"""R1-IGES-010 (0.57.0): IGES names are read byte for byte and decoded with a stated encoding."""

from __future__ import annotations

import os
import signal

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
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


@pytest.mark.requirement("FR-3705")
def test_p0570_the_skin_takes_its_plane_of_symmetry_only_from_the_caller():
    import inspect

    from pyflightstream.workspace._iges_skin import outer_skin

    assert inspect.signature(outer_skin).parameters["symmetry"].default == "none"


@pytest.mark.requirement("FR-3705")
def test_p0570_a_label_and_a_base_family_with_one_name_are_two_declarations(tmp_path):
    """R2-006: an entry and a base rim of one name both survive and the overlap is warned."""
    from pyflightstream.workspace import plan_mark_boundaries
    from tests.tier1_offline.test_p0540_mark_26100 import _capped_strip

    mesh = _capped_strip(
        tmp_path,
        '[trailing_edges.wing]\nfile = "top.te.txt"\ntype = "STANDARD"\n'
        '[base_regions.wing]\ntrailing_edges = {file = "top.te.txt", type = "STANDARD"}\n',
    )
    with pytest.warns(PyflightstreamWarning, match="trailing edge wing and base wing"):
        plan = plan_mark_boundaries(mesh)
    assert [entry["label"] for entry in plan.sets] == ["wing", "wing"]


@pytest.mark.requirement("FR-3705")
def test_p0570_generated_paths_are_role_qualified_and_case_safe(tmp_path):
    """R2-006: equal or case-only equal names never replace one another's point file."""
    from pyflightstream.workspace._wheel import reserve_name

    taken: set[str] = set()
    stem = "wheel"
    first = reserve_name(taken, stem, "Rim.te.txt", "trailing_edge")
    second = reserve_name(taken, stem, "Rim.te.txt", "base")
    third = reserve_name(taken, stem, "RIM.te.txt", "base")
    assert first == "wheel.Rim.te.txt"
    assert second == "wheel.base.Rim.te.txt"
    assert len({first.casefold(), second.casefold(), third.casefold()}) == 3


# ----------------------------------------------- R1-IGES-008: the kernel runs in a worker


#: How the parent names the simulated fault: the access-violation status on Windows, the
#: segmentation signal elsewhere (a POSIX exit status keeps only the low byte of a code).
_FAULT_TEXT = "0xc0000005" if os.name == "nt" else "signal 11"


def worker_crash():
    """Stand in for a native kernel fault: the process ends at once, with no Python unwinding."""
    if os.name == "nt":
        os._exit(-1073741819)  # STATUS_ACCESS_VIOLATION, 0xC0000005
    os.kill(os.getpid(), signal.SIGSEGV)


def worker_ok(value=1):
    import warnings

    from pyflightstream._errors import NotApplicableWarning

    warnings.warn("careful", NotApplicableWarning, stacklevel=1)
    return {"value": value}


def worker_refuses():
    raise InputArtifactError("bad surface. Nothing was written.", kind="geometry")


def worker_hangs():
    import time

    time.sleep(60)


_HERE = "tests.tier1_offline.test_p0570_iges_decisions"


@pytest.mark.requirement("FR-3705")
def test_p0570_a_kernel_fault_ends_the_worker_and_reports_its_cause_then_a_fresh_worker_works():
    from pyflightstream.workspace._gmsh_worker import run_isolated

    with pytest.raises(InputArtifactError) as raised:
        run_isolated(f"{_HERE}:worker_crash", {}, worker_crash)
    text = str(raised.value)
    assert _FAULT_TEXT in text.lower()
    assert "Nothing was written" in text
    assert "not reused" in text
    with pytest.warns(PyflightstreamWarning, match="careful"):
        assert run_isolated(f"{_HERE}:worker_ok", {"value": 7}, worker_ok) == {"value": 7}


@pytest.mark.requirement("FR-3705")
def test_p0570_a_refusal_in_the_worker_arrives_as_the_same_type_and_message():
    from pyflightstream.workspace._gmsh_worker import run_isolated

    with pytest.raises(InputArtifactError, match="bad surface. Nothing was written."):
        run_isolated(f"{_HERE}:worker_refuses", {}, worker_refuses)


@pytest.mark.requirement("FR-3705")
def test_p0570_a_hung_worker_is_ended_and_reported(monkeypatch):
    from pyflightstream.workspace._gmsh_worker import run_isolated

    monkeypatch.setenv("PYFLIGHTSTREAM_GMSH_TIMEOUT", "2")
    with pytest.raises(InputArtifactError, match="longer than 2 s"):
        run_isolated(f"{_HERE}:worker_hangs", {}, worker_hangs)


@pytest.mark.requirement("FR-3705")
def test_p0570_convert_never_initializes_the_kernel_in_the_calling_process(tmp_path, monkeypatch):
    from pyflightstream.workspace.iges_convert import convert_iges
    from tests.tier1_offline.test_p0560_iges import gmsh_or_skip, plate_and_flap

    gmsh = gmsh_or_skip()

    def refuse(*args, **kwargs):
        raise AssertionError("the calling process initialized the kernel")

    monkeypatch.setattr(gmsh, "initialize", refuse)
    record = convert_iges([plate_and_flap(tmp_path)], tmp_path / "out.igs")
    assert record["faces"] == 2
    assert (tmp_path / "out.igs").is_file()
