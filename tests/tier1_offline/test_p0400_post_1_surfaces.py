"""P0400 surface-average defects (post-1 lane).

P0400-REVERSEDWINDOW (PFS-2095.045): a reversed window is a ProductError,
never a bare IndexError.
P0400-HALFPAIR (PFS-2096.022): write_surface_average tests both destinations
before it writes either, so a refusal leaves nothing behind.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import ProductError, ProductExistsError
from pyflightstream.post.surfaces import average_surface_exports, write_surface_average
from pyflightstream.results import SurfaceFrame
from tests.tier1_offline.test_g25_surface_time_average import MRP, _exports


@pytest.mark.parametrize((), [pytest.param(id="P0400-REVERSEDWINDOW")])
def test_p0400_reversedwindow_is_refused(tmp_path):
    """P0400-REVERSEDWINDOW: (6, 3) is refused, naming the window."""
    _exports(tmp_path, range(1, 8))
    files = {step: tmp_path / f"p_iteration={step}.vtk" for step in range(1, 8)}
    with pytest.raises(ProductError, match=r"\(6, 3\) ends before it starts"):
        average_surface_exports(files, window=(6, 3), frame=SurfaceFrame.from_record(MRP))


@pytest.mark.parametrize((), [pytest.param(id="P0400-HALFPAIR")])
def test_p0400_halfpair_a_refusal_writes_nothing(tmp_path):
    """P0400-HALFPAIR: the VTK exists; the Tecplot is not written either."""
    _exports(tmp_path, range(1, 8))
    files = {step: tmp_path / f"p_iteration={step}.vtk" for step in range(1, 8)}
    average = average_surface_exports(files, window=(3, 6), frame=SurfaceFrame.from_record(MRP))
    (tmp_path / "avg.vtk").write_text("earlier", encoding="utf-8")
    with pytest.raises(ProductExistsError):
        write_surface_average(tmp_path / "avg.dat", average, vtk=tmp_path / "avg.vtk")
    assert not (tmp_path / "avg.dat").exists()
