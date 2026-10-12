"""P0400 section-distribution defects (post-1 lane).

P0400-EXTENDEDSTRIPS (PFS-2081.40): the integrated sectional loads put the
strip edges half a spacing beyond the end stations, which the export places at
strip centers; a uniform load integrates to its whole span.
P0400-BUILDERQUIET (PFS-2100.014): the export builder's run-time warnings are
collected at every builder call of the section-distribution matching, never
written by the post stage.
"""

from __future__ import annotations

import warnings

import pytest

import pyflightstream.post.section_distributions as distributions
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.post.section_distributions import _integrated_strips
from tests.tier1_offline.test_integrated_sectional_loads import _case, _table


@pytest.mark.parametrize((), [pytest.param(id="P0400-EXTENDEDSTRIPS")])
def test_p0400_extendedstrips_a_uniform_load_integrates_to_its_span():
    """P0400-EXTENDEDSTRIPS: four stations at strip centers of [0, 1], Fx = 1 N/m: 1 N."""
    stations = [[r, 1.0, 0.25, 0.0, 1.0, 2.0, 0.5] for r in (0.125, 0.375, 0.625, 0.875)]
    strips = _integrated_strips(stations)
    assert [strip[0] for strip in strips] == pytest.approx([0.25] * 4)
    assert sum(strip[1] for strip in strips) == pytest.approx(1.0)
    assert sum(strip[2] for strip in strips) == pytest.approx(2.0)
    assert sum(strip[3] for strip in strips) == pytest.approx(0.5)


@pytest.mark.parametrize((), [pytest.param(id="P0400-WINDOWSTEPS")])
def test_p0400_windowsteps_a_stamped_step_outside_the_window_is_named_not_tabled(
    tmp_path, monkeypatch
):
    """P0400-WINDOWSTEPS (PFS-2105.039): window 3 to 5; a leftover step 9 is skipped by name."""
    from tests.tier1_offline.test_f07_section_distributions import _post, _workspace

    workspace, _record = _workspace(tmp_path, monkeypatch, stamped=True)
    sim = workspace.sim_dir("7001")
    for kind in ("_sloads", "_cp"):
        stamped = sim / f"AL-020{kind}_iteration=5.txt"
        (sim / f"AL-020{kind}_iteration=9.txt").write_text(
            stamped.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out, manifest = _post(workspace)
    tables = sorted((out / "sections").glob("AL-020_sloads_*.csv"))
    assert tables
    from pyflightstream.post.products import read_csv_table

    for table in tables:
        steps = {row["STEP"] for row in read_csv_table(table)[1]}
        assert steps == {"3", "4", "5"}, (table.name, steps)
    named = [key for key in manifest["skipped"] if key.endswith("#step=9")]
    assert named and all(
        "outside the record's export window" in manifest["skipped"][k] for k in named
    )


@pytest.mark.parametrize((), [pytest.param(id="P0400-BUILDERQUIET")])
def test_p0400_builderquiet_no_builder_warning_reaches_the_post(tmp_path, monkeypatch):
    """P0400-BUILDERQUIET: a warning the builder raises during matching stays the builder's."""
    real_emissions = distributions.pproc_emissions
    real_select = distributions.select_families
    said: list[str] = []

    def emissions(*args, **kwargs):
        said.append("emissions")
        warn("BUILDER-WARNING emissions", PyflightstreamWarning)
        return real_emissions(*args, **kwargs)

    def select(*args, **kwargs):
        said.append("select")
        warn("BUILDER-WARNING select", PyflightstreamWarning)
        return real_select(*args, **kwargs)

    monkeypatch.setattr(distributions, "pproc_emissions", emissions)
    monkeypatch.setattr(distributions, "select_families", select)
    workspace = _case(tmp_path, monkeypatch)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        path, _columns, _rows = _table(workspace)
    assert said, "the matching reached no builder call"
    log = (path.parent.parent / "post.log").read_text(encoding="utf-8")
    assert "BUILDER-WARNING" not in log
    assert not [w for w in caught if "BUILDER-WARNING" in str(w.message)]
