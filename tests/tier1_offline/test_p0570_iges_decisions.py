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
def test_p0570_a_name_no_level_takes_is_not_decoded(tmp_path):
    """RL57B-2: a level-0 feature name, or a second NAME of a level, never refuses the file."""
    from pyflightstream.workspace._iges_names import read_iges_names

    iges = Iges()
    iges.patch(square(0, 0, 1, 1), level=1)
    iges.name(0, b"Pi\xe8ce".decode("latin-1"))  # a feature name in Latin-1, on no level
    iges.name(1, "Asa_ção".encode().decode("latin-1"))
    iges.name(1, b"Asa_\xe7".decode("latin-1"))  # a later NAME of level 1: not the level's name
    path = iges.write(tmp_path / "mixed.igs")
    assert read_iges_names(path, name_encoding="utf-8").faces == ("Asa_ção",)


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
@pytest.mark.parametrize("value", ["soon", "0", "-5", "nan", "inf"])
def test_p0570_a_time_limit_that_is_not_a_positive_number_is_refused(monkeypatch, value):
    """RL57B-4: the documented switch is refused by name, not as a parse error or instant end."""
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace._gmsh_worker import run_isolated

    monkeypatch.setenv("PYFLIGHTSTREAM_GMSH_TIMEOUT", value)
    with pytest.raises(InputValueError, match="PYFLIGHTSTREAM_GMSH_TIMEOUT.*positive number"):
        run_isolated(f"{_HERE}:worker_ok", {}, worker_ok)


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


@pytest.mark.requirement("FR-3705")
@pytest.mark.parametrize("verb", ["iges-grid", "iges-convert"])
def test_p0570_an_unknown_encoding_is_refused_by_name_before_any_work(tmp_path, capsys, verb):
    """RL57B-8: a file with no level NAME never decodes one, so the codec is looked up at entry."""
    from tests.tier1_offline.test_p0560_iges import cli, grid_file, plate_and_flap

    source = plate_and_flap(tmp_path)
    out = tmp_path / ("model.obj" if verb == "iges-grid" else "conv.igs")
    extra = (
        ["--grid", str(grid_file(tmp_path, "[defaults]\nsize = 0.25\n"))] if "grid" in verb else []
    )
    before = sorted(p.name for p in tmp_path.iterdir())
    code, _, stderr = cli(
        [
            "geometry",
            verb,
            str(source),
            *extra,
            "--out",
            str(out),
            "--name-encoding",
            "no-such-codec",
        ],
        capsys,
    )
    assert code != 0
    assert "no-such-codec" in stderr
    assert "pip install" not in stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == before


@pytest.mark.requirement("FR-3705")
def test_p0570_the_python_entry_points_refuse_an_unknown_encoding_by_name(tmp_path):
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace.iges_convert import convert_iges
    from pyflightstream.workspace.iges_grid import grid_iges

    with pytest.raises(InputValueError, match="no-such-codec"):
        grid_iges([], tmp_path / "g.toml", tmp_path / "m.obj", name_encoding="no-such-codec")
    with pytest.raises(InputValueError, match="no-such-codec"):
        convert_iges([], tmp_path / "c.igs", name_encoding="no-such-codec")


class _ReachedError(Exception):
    """Raised by the patched ``oriented`` once it has seen its argument."""


def _crossing_skin_mirror(monkeypatch, run):
    """Run ``run`` on three faces sharing an edge; return what ``oriented`` got."""
    import numpy as np

    from pyflightstream.workspace import _iges_skin

    seen: list[int | None] = []

    def oriented(self, mirror):
        seen.append(mirror)
        raise _ReachedError

    monkeypatch.setattr(_iges_skin._Assembly, "oriented", oriented)
    verts = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0, -1, 0]])
    families = {"a": [[0, 1, 2]], "b": [[0, 1, 3]], "c": [[0, 1, 4]]}
    with pytest.raises(_ReachedError):
        run(verts, families)
    return seen


@pytest.mark.requirement("FR-3705")
@pytest.mark.parametrize(("plane", "axis"), [("x", 0), ("y", 1), ("z", 2), ("none", None)])
def test_p0570_the_skin_mirrors_across_the_axis_its_plane_names(monkeypatch, plane, axis):
    """RL57B-3: each stated plane reaches the assembly as its own axis (x=0, y=1, z=2)."""
    from pyflightstream.workspace._iges_skin import outer_skin

    seen = _crossing_skin_mirror(monkeypatch, lambda v, f: outer_skin(v, f, symmetry=plane))
    assert seen == [axis]


@pytest.mark.requirement("FR-3705")
@pytest.mark.parametrize(("plane", "axis"), [("x", 0), ("y", 1), ("z", 2), ("none", None)])
def test_p0570_the_grid_hands_its_configured_symmetry_to_the_skin(monkeypatch, plane, axis):
    """RL57B-3: ``_inner`` passes ``config.symmetry`` on; a dropped argument mirrors nothing."""
    from types import SimpleNamespace

    from pyflightstream.workspace.iges_grid import _inner

    config = SimpleNamespace(remove_inner_faces=True, symmetry=plane)

    def run(verts, families):
        meshed = SimpleNamespace(nodes=verts, faces=families, record={})
        _inner(config, meshed, list(families), [])

    assert _crossing_skin_mirror(monkeypatch, run) == [axis]


def test_a_recorded_warning_replays_by_name_through_the_package_route():
    """R4-002: warn_by_name keeps a package category, else falls back, and collects."""
    from pyflightstream import _errors

    category = next(
        c
        for c in vars(_errors).values()
        if isinstance(c, type)
        and issubclass(c, _errors.PyflightstreamWarning)
        and c is not _errors.PyflightstreamWarning
    )
    with _errors.collecting_warnings() as caught:
        _errors.warn_by_name("named", category.__name__)
        _errors.warn_by_name("unnamed", "NoSuchWarning")
        _errors.warn_by_name("an exception, not a warning", "InputValueError")
    assert [(str(w.message), w.category) for w in caught] == [
        ("named", category),
        ("unnamed", _errors.PyflightstreamWarning),
        ("an exception, not a warning", _errors.PyflightstreamWarning),
    ]
    assert all(w.filename == __file__ for w in caught)
