"""Post the untouched wake exports through the public far-field product stage."""
# ruff: noqa: N999 - the assigned lane name is litB.

import csv
import lzma
import shutil
import warnings
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.post.farfield_products import farfield_products
from pyflightstream.post.products import ReferenceValues
from pyflightstream.results import parse_loads
from tests.tier1_offline.test_post_products import LOADS

pytestmark = pytest.mark.requirement("P0400-LITB-POST")
FIXTURES = Path(__file__).parent / "fixtures"


def post_wake(root, fixture, *, cl=0.3400367):
    root.mkdir(exist_ok=True)
    if fixture.endswith(
        ".xz"
    ):  # recorded exports over the repository size limit are stored xz-compressed
        (root / "point_wakes.vtk").write_bytes(lzma.decompress((FIXTURES / fixture).read_bytes()))
    else:
        shutil.copyfile(FIXTURES / fixture, root / "point_wakes.vtk")
    (root / "point.fsm").write_text("$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n", "utf-8")
    loads = replace(parse_loads(LOADS), freestream_velocity_m_s=34.03, angle_of_attack_deg=4.0)
    loads.total["CL"] = cl
    point = SimpleNamespace(
        name="point",
        loads=loads,
        state=SimpleNamespace(density_kg_m3=1.2250122659906946),
        vorticity_selection=None,
    )
    products = {}

    def target(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    ctx = SimpleNamespace(
        pproc=PprocSpec.model_validate(
            {
                "farfield": {"families": "all", "trefftz": {"variant": "wake"}},
            }
        ),
        workspace=SimpleNamespace(sim_dir=lambda sim: root),
        record_of={
            "point": SimpleNamespace(
                outputs=["point.vtk", "point.fsm"],
                package_version="0.40.0",
                recipe="steady",
            )
        },
        sim_id="1",
        points=[point],
        reference=ReferenceValues(4.934802200544679, 1.0, 6.283185307179586),
        matrix_row=SimpleNamespace(variables={"SYMMETRY": "MIRROR"}),
        sources={"point": ["recorded"]},
        skipped={},
        out=root / "post",
        table_name="point",
        condition=lambda point: {},
        target=target,
        add=lambda path, entry: products.update(
            {
                str(path): entry,
            }
        ),
        farfield_super={},
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        farfield_products(ctx)
    paths = list((root / "post" / "farfield").glob("*_trefftz.csv"))
    assert len(paths) == 1, ctx.skipped
    with paths[0].open(encoding="utf-8", newline="") as handle:
        (row,) = list(csv.DictReader(handle))
    return row, [str(w.message) for w in caught], ctx.skipped


@pytest.mark.parametrize("build", ["26124", "26125"])
def test_p0400_litb_real_mirror_wake_reaches_post(tmp_path, build):
    row, messages, skipped = post_wake(tmp_path, f"p0400_litB_wake_{build}.vtk")
    assert row["VARIANT"] == "B" and row["E_T"] != "NA", skipped
    assert float(row["CL_T"]) == pytest.approx(0.3400367, abs=1e-5)
    assert any("collapsed wake lines" in message for message in messages) == (build == "26124")
