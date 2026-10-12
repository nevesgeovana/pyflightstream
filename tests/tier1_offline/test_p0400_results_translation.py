"""Results regressions for 0.40.0."""

import pytest

from pyflightstream.results import translate_surface_exports
from tests.tier1_offline.test_p0400_results_surface import TRANSLATIONS, VTK

pytestmark = pytest.mark.requirement("P0400-RESULTS-SURFACE")


def test_p0400_results_a_stale_dat_with_no_native_source_is_preserved_not_written(tmp_path):
    """P0400-RESULTS (PFS-2105.024): the real translation, on a stale .dat beside a valid VTK."""
    (tmp_path / "surface.vtk").write_text(VTK, encoding="utf-8")
    (tmp_path / "surface.dat").write_text("stale", encoding="utf-8")
    [record] = translate_surface_exports(tmp_path, TRANSLATIONS)
    assert record["written"] == []
    assert record["problems"] == [
        "surface.dat is preserved: source, frame or output provenance changed"
    ]
    assert (tmp_path / "surface.dat").read_text(encoding="utf-8") == "stale"


def test_p0400_results_a_dat_this_translation_wrote_is_found_written(tmp_path):
    """P0400-RESULTS (PFS-2105.024): control, a second pass over its own output accepts it."""
    (tmp_path / "surface.vtk").write_text(VTK, encoding="utf-8")
    [first] = translate_surface_exports(tmp_path, TRANSLATIONS)
    assert (first["written"], first["problems"]) == (["surface.dat"], [])
    [again] = translate_surface_exports(tmp_path, TRANSLATIONS)
    assert (again["written"], again["problems"]) == (["surface.dat"], [])
    (tmp_path / "surface.vtk").write_text(VTK.replace("0.25", "0.75"), encoding="utf-8")
    [changed] = translate_surface_exports(tmp_path, TRANSLATIONS)
    assert changed["written"] == [] and "preserved" in changed["problems"][0]
