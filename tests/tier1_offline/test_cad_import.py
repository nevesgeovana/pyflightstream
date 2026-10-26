"""Offline CAD routing; these assertions do not establish native mesh quality or scale."""

import pytest

from pyflightstream import cases
from tests.tier1_offline.test_workflows import steady_case


def _case(tmp_path, suffix=".igs", **options):
    path = tmp_path / ("staged" + suffix)
    path.write_text("synthetic routing placeholder", encoding="utf-8")
    spec = cases.MeshImport(units="FILE", cad=options)
    return steady_case().model_copy(
        update={
            "geometry": str(path),
            "mesh_import": spec,
            "inventory": ("Wing",),
            "inventory_source": "sidecar",
        }
    )


@pytest.mark.parametrize(
    "options", [{"num_curvature": 0}, {"body_index": 0}, {"body_index": -2}, {"unrecognized": 1}]
)
def test_cad_options_refuse_invalid_values(tmp_path, options):
    with pytest.raises(ValueError):
        _case(tmp_path, **options)
