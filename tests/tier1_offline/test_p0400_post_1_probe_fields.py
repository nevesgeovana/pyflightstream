"""P0400-FIELDREFUSAL (PFS-2096.021): an overwrite refusal arrives before any write.

write_probe_field tested each format's pair on its own, so an existing .dat
refused after the .vtk pair had already been written.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.post import OutputProvenance
from pyflightstream.post.probe_fields import write_probe_field
from pyflightstream.post.writers import OutputExistsError
from pyflightstream.script import Script, helpers


@pytest.mark.parametrize((), [pytest.param(id="P0400-FIELDREFUSAL")])
def test_p0400_fieldrefusal_writes_nothing_when_one_destination_exists(tmp_path):
    """P0400-FIELDREFUSAL: field.dat exists; field.vtk and its record are not written."""
    setup = helpers.solver_settings(Script(version="26.120"), velocity=30.0)
    provenance = OutputProvenance(run_id="probe/sim_1/a+00.0", setup=setup)
    source = tmp_path / "samples.csv"
    source.write_text("PROBE,X,Y,Z", encoding="utf-8")
    (tmp_path / "field.dat").write_text("earlier", encoding="utf-8")
    points = np.array([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    velocity = np.array([[30.0, 0.0, 0.0], [30.0, 0.0, 0.0]])
    with pytest.raises(OutputExistsError):
        write_probe_field(
            tmp_path / "field",
            points,
            velocity,
            source=source,
            provenance=provenance,
            formats=("vtk", "tecplot"),
        )
    assert sorted(path.name for path in tmp_path.iterdir()) == ["field.dat", "samples.csv"]
