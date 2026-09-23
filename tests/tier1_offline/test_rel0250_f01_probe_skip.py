"""An unsteady point that ASKS for probes and gets no history is named, never silent.

F01 makes the plots history the only probe source of an unsteady point. Where that
history carries no whole probe group the table cannot be written, and the first
writing of F01 returned without writing the table AND without naming it: the product
was lost in silence, which is the failure this project spends its refusals on. A
point whose artifact declares NO probe is not missing a product and is not named.
"""

from __future__ import annotations

from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_post_products import _products_manifest, _unsteady_workspace

PROBED = (
    '[groups]\n"1" = "all"\n'
    "\n[[probes]]\n"
    'frame = "MRP"\n'
    'parameters = ["MACH", "VELOCITY"]\n'
    "[[probes.lines]]\n"
    "start = [0.0, 0.0, 0.0]\n"
    "end = [1.0, 0.0, 0.0]\n"
)


def _post(tmp_path, pproc: str | None):
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    if pproc is not None:
        (workspace.inputs_dir / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8")
    write_campaign_products(workspace)
    return _products_manifest(workspace)


def test_an_unsteady_point_asking_for_probes_without_history_is_named(tmp_path) -> None:
    manifest = _post(tmp_path, PROBED)
    key = "probes/AL-020_probes.csv"
    assert key not in manifest.get("products", {}), "this history has no whole probe group"
    reason = manifest.get("skipped", {}).get(key)
    assert reason, (
        f"the probes table vanished with no reason: {sorted(manifest.get('skipped', {}))}"
    )
    assert "fluid plots" in reason and "history" in reason


def test_an_unsteady_point_declaring_no_probe_is_not_named(tmp_path) -> None:
    manifest = _post(tmp_path, None)
    assert "probes/AL-020_probes.csv" not in manifest.get("skipped", {})
    assert "probes/AL-020_probes.csv" not in manifest.get("products", {})
