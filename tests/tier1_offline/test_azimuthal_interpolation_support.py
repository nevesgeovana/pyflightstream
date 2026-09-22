"""The azimuthal phase-locked average is judged over the samples it READS, at the product.

THIS IS THE COVERAGE `reports/RPT-056` REGISTERED, and the third independent reading of GitHub
main said it should hold the v0.25.1 tag. Every earlier case lived at the helper or on the
passage series, which does not interpolate; the azimuthal product is the one whose samples are
taken between plotted steps, and nothing committed exercised it.

THE DISTINCTION IT ASSERTS, measured here through `write_campaign_products`:

- with TWO steps per revolution and two blades, each blade's offset is a whole step, so every
  sample lands exactly on a plotted step and a step outside the window is not read. An unread
  step there costs nothing;
- with THREE, the second blade sits one and a half steps behind, so a sample at 59.5 is read
  from the plotted steps 59 and 60 -- and an unread 59 refuses the product by name.

The reader's own words for the defect this closes: "Bracketing the declared opening is still
broader than bracketing the actual samples."
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.cases.windows import AZIMUTHAL
from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_b01_frozen_solve import (
    _make_one_step_unreadable,
    _post_workspace,
    _products_manifest,
)

#: The per-rotor file an azimuthal phase-locked reduction writes.
PRODUCT = "probes/AL-020_phase_locked_PUSHER.csv"


def _azimuthal_campaign(tmp_path, steps_per_revolution: float, unread: int | None = None):
    """A rotor campaign whose phase-locked reduction is taken at each azimuth."""
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    recorded = json.loads((workspace.root / "runs.json").read_text(encoding="utf-8"))
    entry = {
        "windows": [[60, 61]],
        "shape": AZIMUTHAL,
        "revolutions": 1.0,
        "steps_per_revolution": steps_per_revolution,
    }
    reductions = recorded[0]["reductions"]
    reductions["phase_locked"] = entry
    reductions["blades"] = 2
    reductions["blade_families"] = ["Blade1", "Blade2"]
    reductions["rotors"] = {
        "PUSHER": {
            "rpm": 2200.0,
            "blade1_azimuth_deg": 0.0,
            "blades": 2,
            "blade_families": ["Blade1", "Blade2"],
            "steps_per_revolution": steps_per_revolution,
            "phase_locked": entry,
        }
    }
    (workspace.root / "runs.json").write_text(json.dumps(recorded, indent=1), encoding="utf-8")
    if unread is not None:
        _make_one_step_unreadable(workspace, unread)
    write_campaign_products(workspace, matrix_stem="products")
    return _products_manifest(workspace)


@pytest.mark.parametrize("steps_per_revolution", [2.0, 3.0])
def test_a_clean_azimuthal_campaign_writes_its_product(tmp_path, steps_per_revolution):
    """The control, without which a refusal proves nothing."""
    manifest = _azimuthal_campaign(tmp_path / str(steps_per_revolution), steps_per_revolution)
    assert PRODUCT in manifest["products"], manifest["skipped"]


def test_whole_step_samples_do_not_read_outside_the_window(tmp_path):
    """The third reading's finding: bracketing the opening refused a clean average.

    Two steps per revolution and two blades put every sample on a plotted step,
    so the average reads steps 60 and 61 and nothing else. The reader measured
    it: changing the step before the window leaves every result identical.
    """
    manifest = _azimuthal_campaign(tmp_path, 2.0, unread=59)
    assert PRODUCT in manifest["products"], (
        "a clean average was refused for a step its arithmetic does not read"
    )


def test_a_sample_taken_between_two_steps_is_judged_over_both(tmp_path):
    """And the guard still bites where the samples really do reach outside.

    Three steps per revolution put the second blade one and a half steps behind
    blade one, so a sample at 59.5 is read from the plotted steps 59 and 60.
    """
    manifest = _azimuthal_campaign(tmp_path, 3.0, unread=59)
    assert PRODUCT not in manifest["products"], "an unread step fed a published average"
    assert "59" in manifest["skipped"][PRODUCT], manifest["skipped"][PRODUCT]
