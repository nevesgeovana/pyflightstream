"""A reader of an earlier post's plots reads time_history/, then probes/ with the warning.

THE REQUIREMENT (design of the post outputs, section 2.2): "A reader inside the
package (superfile union, series readers, pyfs-matrix collectors) reads the AFTER
path and falls back to the BEFORE path with the same warning, for one release";
the warning of the plots history ends with the pointer to the upgrade note.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.superfile import union_the_workspace_knows

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I1-EARLIER-PATH")])


def _known(root):
    return union_the_workspace_knows(
        root, root / "post", None, polars_dir="polars", probes_dir="probes", raw_records=[]
    )


def test_p0580_the_union_reads_the_plots_history_from_time_history(tmp_path):
    (tmp_path / "post" / "time_history").mkdir(parents=True)
    (tmp_path / "post" / "time_history" / "AL+000_plots.csv").write_text(
        "POL,NEW_COLUMN\n1,2\n", encoding="utf-8"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        assert "NEW_COLUMN" in _known(tmp_path)


def test_p0580_the_union_falls_back_to_probes_with_the_migration_warning(tmp_path):
    (tmp_path / "post" / "probes").mkdir(parents=True)
    (tmp_path / "post" / "probes" / "AL+000_plots.csv").write_text(
        "POL,OLD_COLUMN\n1,2\n", encoding="utf-8"
    )
    with pytest.warns(PyflightstreamWarning, match="moved from probes/ to time_history/") as said:
        known = _known(tmp_path)
    assert "OLD_COLUMN" in known
    assert any("docs/upgrading.md#0580-post-tree" in str(w.message) for w in said)
