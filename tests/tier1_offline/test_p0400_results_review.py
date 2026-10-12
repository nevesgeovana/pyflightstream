"""Review regressions: read_vtk_surface and repeated translate_surface_exports calls."""

import pytest

from pyflightstream.results import read_vtk_surface, translate_surface_exports
from pyflightstream.results.core import MalformedOutputError
from tests.tier1_offline.test_p0400_results_surface import TRANSLATIONS, VTK

pytestmark = pytest.mark.requirement("P0400-RESULTS-SURFACE")


@pytest.mark.parametrize("token", [str(2**63), str(-(2**63) - 1)])
def test_p0400_results_polygon_integer_overflow_is_catalogued(tmp_path, token):
    """An out-of-range node integer must not escape translation's error catalogue."""
    source = tmp_path / "surface.vtk"
    source.write_text(VTK.replace("3 0 1 2", f"3 0 1 {token}"), encoding="utf-8")
    with pytest.raises(MalformedOutputError, match="POLYGONS"):
        read_vtk_surface(source)
    [record] = translate_surface_exports(tmp_path, TRANSLATIONS)
    assert record["written"] == []
    assert "POLYGONS" in record["problems"][0]


@pytest.mark.parametrize("damage", ["truncated", "changed"])
def test_p0400_results_matching_translation_header_does_not_prove_payload(tmp_path, damage):
    """Keep the genuine provenance header, then damage its translated data."""
    (tmp_path / "surface.vtk").write_text(VTK, encoding="utf-8")
    [first] = translate_surface_exports(tmp_path, TRANSLATIONS)
    assert first["written"] == ["surface.dat"] and first["problems"] == []
    target = tmp_path / "surface.dat"
    lines = target.read_bytes().splitlines(keepends=True)
    zone = next(i for i, line in enumerate(lines) if line.startswith(b"ZONE"))
    if damage == "truncated":
        damaged = b"".join(lines[: zone + 1])
    else:
        lines[zone + 1] = b"999 " + lines[zone + 1]
        damaged = b"".join(lines)
    target.write_bytes(damaged)
    [again] = translate_surface_exports(tmp_path, [first])
    assert again["written"] == []
    assert "preserved" in again["problems"][0]
    assert target.read_bytes() == damaged
