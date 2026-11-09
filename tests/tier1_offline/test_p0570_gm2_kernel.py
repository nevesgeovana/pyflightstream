"""The named IGES writer is deterministic and carries no account name (PFS-2220, lane G2)."""

from __future__ import annotations

import getpass
import hashlib
import subprocess
import sys
import time

import pytest

from pyflightstream.workspace._iges_write import (
    FIXED_STAMP,
    normalize_global,
    read_iges,
    serialize_iges,
)

_WRITE = (
    "import sys\n"
    "from pyflightstream.workspace._gmsh import session\n"
    "from pyflightstream.workspace._iges_write import write_iges\n"
    "with session('test') as g:\n"
    "    t = g.model.occ.addRectangle(0, 0, 0, 1, 2)\n"
    "    g.model.occ.synchronize()\n"
    "    write_iges(g, {'PANEL': [t]}, sys.argv[1])\n"
)


def _write_in_fresh_process(path):
    done = subprocess.run(
        [sys.executable, "-c", _WRITE, str(path)], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-400:]
    return path.read_bytes()


def test_normalize_global_fixes_stamps_and_empties_the_author():
    values = [""] * 26
    values[17], values[20], values[24] = "15H20261109.114612", "5Hgeova", "15H20261109.114612"
    out = normalize_global(values)
    assert out[17] == out[24] == FIXED_STAMP
    assert out[20] == ""
    assert values[20] == "5Hgeova"  # the input is not changed


def test_serialize_iges_without_stamp_positions_is_left_alone():
    document = {"start": ["x"], "global": ["", "", "1HA"], "entities": []}
    assert "1HA" in serialize_iges(document)


def _need_gmsh():
    try:
        import gmsh  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("gmsh is not usable here")


def test_two_fresh_processes_write_byte_identical_iges_with_no_login(tmp_path):
    _need_gmsh()
    first = _write_in_fresh_process(tmp_path / "a.igs")
    time.sleep(1.1)  # the kernel's own stamp has a resolution of one second
    second = _write_in_fresh_process(tmp_path / "b.igs")
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    text = first.decode("ascii")
    assert getpass.getuser() not in text
    document = read_iges(tmp_path / "a.igs")
    assert document["global"][17] == document["global"][24] == FIXED_STAMP
    assert document["global"][20] == ""
    assert any(e["type"] == 406 for e in document["entities"])


# --- the kernel adapter ----------------------------------------------------------------------


def _flat_net(size=3.0, z=0.0, x0=0.0):
    return [[(x0 + size * i / 3, size * j / 3, z) for j in range(4)] for i in range(4)]


def _bicubic(kernel, net):
    return kernel.add_bspline_surface(net, [0.0, 1.0], [0.0, 1.0], [4, 4], [4, 4], 3, 3)


@pytest.fixture
def kernel():
    _need_gmsh()
    from pyflightstream.workspace._gmsh import open_kernel

    k = open_kernel("test")
    try:
        yield k
    finally:
        k.close()


def test_the_kernel_satisfies_the_protocol(kernel):
    from pyflightstream.workspace._cad import CadKernel

    assert isinstance(kernel, CadKernel)
    assert kernel.name == "gmsh"
    assert kernel.version.count(".") >= 1


def test_a_bicubic_face_answers_the_geometric_queries(kernel):
    face = _bicubic(kernel, _flat_net(3.0))
    assert kernel.area(face) == pytest.approx(9.0, rel=1e-9)
    assert kernel.centroid(face) == pytest.approx((1.5, 1.5, 0.0), abs=1e-9)
    low, high = kernel.bbox(face)
    assert low == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert high == pytest.approx((3.0, 3.0, 0.0), abs=1e-6)
    (u0, v0), (u1, v1) = kernel.uv_bounds(face)
    assert (u1 - u0) > 0 and (v1 - v0) > 0
    mid = ((u0 + u1) / 2, (v0 + v1) / 2)
    assert kernel.value(face, mid) == pytest.approx((1.5, 1.5, 0.0), abs=1e-9)
    assert abs(kernel.normal(face, mid)[2]) == pytest.approx(1.0, abs=1e-9)
    du, dv = kernel.derivative(face, mid)
    assert du[2] == pytest.approx(0.0, abs=1e-9) and dv[2] == pytest.approx(0.0, abs=1e-9)
    ((xyz, _),) = kernel.closest(face, [(1.0, 2.0, 5.0)])
    assert xyz == pytest.approx((1.0, 2.0, 0.0), abs=1e-6)
    assert kernel.is_inside(face, mid)
    assert len(kernel.boundary(face)) == 4
    assert kernel.faces() == (face,)


def test_fragment_imprints_a_crossing_pair_and_reports_what_each_became(kernel):
    a = _bicubic(kernel, _flat_net(3.0))
    corners = [(1.5, -1.0, -1.0), (1.5, 4.0, -1.0), (1.5, 4.0, 1.0), (1.5, -1.0, 1.0)]
    b = kernel.add_planar_face(corners)
    result = kernel.fragment([a], [b])
    assert len(result.from_a) == 1 and len(result.from_b) == 1
    assert len(result.from_a[0]) == 2  # the plate is cut in two along the crossing
    assert sum(kernel.area(f) for f in result.from_a[0]) == pytest.approx(9.0, rel=1e-6)
    halves = set(result.from_a[0])
    joined = [e for e in kernel.boundary(result.from_a[0][0]) if set(kernel.adjacent(e)) == halves]
    assert len(joined) == 1, "the two halves meet along exactly one imprinted edge"


def test_copy_transform_and_remove_edit_the_model(kernel):
    face = _bicubic(kernel, _flat_net(3.0))
    (twin,) = kernel.copy([face])
    kernel.transform([twin], [[1, 0, 0, 10], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    assert kernel.centroid(twin) == pytest.approx((11.5, 1.5, 0.0), abs=1e-9)
    kernel.remove([twin])
    assert kernel.faces() == (face,)


def test_ribbon_and_triangulation(kernel):
    pts = [(float(i), 0.0, 0.0) for i in range(5)]
    ribbon = kernel.add_ribbon(pts, [(0.0, 1.0, 0.0)] * 5)
    assert kernel.area(ribbon) == pytest.approx(4.0, rel=1e-6)
    nodes, triangles = kernel.triangulate([ribbon], 1.0)
    assert nodes and triangles
    assert all(0 <= i < len(nodes) for t in triangles for i in t)


def test_export_then_import_keeps_the_group_names_and_the_area(kernel, tmp_path):
    a = _bicubic(kernel, _flat_net(3.0))
    b = _bicubic(kernel, _flat_net(2.0, z=5.0, x0=10.0))
    path = tmp_path / "two.igs"
    kernel.export_iges({"ALPHA": [a], "BETA": [b]}, path)
    named = kernel.import_iges(path)
    assert sorted(named.names) == ["ALPHA", "BETA"]
    areas = {n: kernel.area(f) for n, f in zip(named.names, named.faces, strict=True)}
    assert areas["ALPHA"] == pytest.approx(9.0, rel=1e-6)
    assert areas["BETA"] == pytest.approx(4.0, rel=1e-6)


def test_the_kernel_initializes_off_the_main_thread():
    _need_gmsh()
    import threading

    from pyflightstream.workspace._gmsh import open_kernel

    box = {}

    def work():
        try:
            k = open_kernel("thread")
            box["area"] = k.area(_bicubic(k, _flat_net(3.0)))
            k.close()
        except Exception as error:  # noqa: BLE001
            box["error"] = error

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert "error" not in box, box.get("error")
    assert box["area"] == pytest.approx(9.0, rel=1e-9)


def _block_gmsh(monkeypatch, error):
    import importlib.abc

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name == "gmsh":
                raise error
            return None

    monkeypatch.delitem(sys.modules, "gmsh", raising=False)
    monkeypatch.setattr(sys, "meta_path", [Finder(), *sys.meta_path])


@pytest.mark.parametrize(
    ("error", "word"),
    [
        (ImportError("No module named 'gmsh'"), "No module named"),
        (OSError("libGLU.so.1: cannot open shared object file"), "libGLU.so.1"),
    ],
)
def test_an_unusable_kernel_library_gives_one_named_error(monkeypatch, error, word):
    from pyflightstream.extras import KernelUnavailableError, MissingExtraError
    from pyflightstream.workspace._gmsh import gmsh_module

    _block_gmsh(monkeypatch, error)
    with pytest.raises(KernelUnavailableError) as caught:
        gmsh_module("the test")
    assert isinstance(caught.value, MissingExtraError)
    message = str(caught.value)
    assert word in message and "libglu1-mesa" in message and "S0 to S9" in message
    assert caught.value.__cause__ is error


def test_the_unavailable_error_pickles_and_is_catalogued():
    import pickle

    from pyflightstream.exceptions import KernelUnavailableError

    error = KernelUnavailableError(purpose="p", reason="r")
    clone = pickle.loads(pickle.dumps(error))
    assert str(clone) == str(error) and clone.reason == "r"
