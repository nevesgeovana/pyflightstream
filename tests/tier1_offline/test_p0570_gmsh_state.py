"""P0570 geometry kernel: a read does not depend on the unit an earlier session asked for.

OpenCASCADE keeps the target unit of its last import in a process-wide static that outlives
``gmsh.finalize``, so these tests hold on every version and platform, in any test order.
"""

import pytest


def _leave_a_stale_unit(path):
    """Read ``path`` in metres in a session of its own, which outlives that session."""
    from pyflightstream.workspace._gmsh import session

    with session("a test") as gmsh:
        gmsh.option.setString("Geometry.OCCTargetUnit", "M")
        gmsh.model.add("stale")
        gmsh.model.occ.importShapes(str(path))


def _write_plate(gmsh, path):
    gmsh.model.add("write")
    gmsh.model.occ.addRectangle(0, 0, 0, 1.2, 1.2)
    gmsh.model.occ.synchronize()
    gmsh.write(str(path))


def test_p0570_a_read_after_a_session_that_asked_for_metres_stays_in_millimetres(tmp_path):
    pytest.importorskip("gmsh", reason="needs the optional extra: gmsh")
    from pyflightstream.workspace._gmsh import import_iges, session

    path = tmp_path / "plate.igs"
    with session("a test") as gmsh:
        _write_plate(gmsh, path)
    _leave_a_stale_unit(path)
    with session("a test") as gmsh:
        gmsh.model.add("read")
        faces = import_iges(gmsh, path)
        gmsh.model.occ.synchronize()
        assert gmsh.model.occ.getBoundingBox(2, faces[0])[3] == pytest.approx(1.2, abs=1e-3)


def test_p0570_a_read_keeps_the_unit_the_session_asked_for(tmp_path):
    pytest.importorskip("gmsh", reason="needs the optional extra: gmsh")
    from pyflightstream.workspace._gmsh import import_iges, session

    path = tmp_path / "plate.igs"
    with session("a test") as gmsh:
        _write_plate(gmsh, path)
        gmsh.option.setString("Geometry.OCCTargetUnit", "M")
        import_iges(gmsh, path)
        assert gmsh.option.getString("Geometry.OCCTargetUnit") == "M"


def test_p0570_a_generated_wing_identifies_at_its_span_after_a_stale_unit(tmp_path):
    pytest.importorskip("gmsh", reason="needs the optional extra: gmsh")
    pytest.importorskip("contourpy")
    from pyflightstream.workspace._geometry_generate import generate_iges
    from pyflightstream.workspace.geometry_pipeline import identify_lifting_surface

    from .test_p0570_geometry_reverse import WING

    path = tmp_path / "wing.igs"
    generate_iges(WING, path)
    _leave_a_stale_unit(path)
    identified = identify_lifting_surface(path, "WING", stations=61, grid=129)
    assert identified.planform["span_m"] == pytest.approx(1.2, abs=1e-3)
