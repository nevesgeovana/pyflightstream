# %% [markdown]
# # Workspace FSI calibration
#
# This offline example creates two complete f-prefixed inputs for a synthetic,
# solid rectangular blade. One derives properties from the existing Grade5
# material; the other supplies those same distributions. A matrix factor1.15
# overrides the file factor1.05 exactly once. No aerodynamic or coupled solve
# is performed. Use a new destination: existing files are preserved.
#
# Run: python workspace_fsi_calibration.py /absolute/path/to/new-workspace

# %%
"""Compare calculated and supplied FSI inputs with a single matrix override."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from pyflightstream._cli import cli_entrypoint
from pyflightstream.workspace.fsi_setup import (
    FSI_TEMPLATE,
    resolve_fsi_setup,
    resolve_row_fsi,
)


def run_example(workspace: Path) -> dict[str, object]:
    """Compare both input modes and return the effective, traceable quantities."""
    inputs = workspace.resolve() / "inputs"
    directory = inputs / "fsi"
    calculated_path = directory / "f_calculated.toml"
    supplied_path = directory / "f_supplied.toml"
    if any(path.exists() for path in (calculated_path, supplied_path)):
        raise FileExistsError("Choose a destination without the example's two FSI inputs.")
    directory.mkdir(parents=True, exist_ok=True)
    calculated_path.write_text(
        FSI_TEMPLATE.replace("bending_stiffness_n_m2 = 1.0", "bending_stiffness_n_m2 = 1.05"),
        encoding="utf-8",
    )
    base = resolve_fsi_setup(calculated_path).base
    # Use unscaled distributions. Reusing the effective properties here would
    # silently apply the calibration a second time when loading the supplied input.
    distributions = base.blade.model_dump(exclude={"provenance"})
    lines = [
        "# Synthetic distributions computed from f_calculated; no native validation.",
        'mode = "supplied"',
        "[calibration]",
        "bending_stiffness_n_m2 = 1.05",
        "[config]",
        "blade_count = 2",
        "omega_rad_per_s = 0.0",
        "[config.blade]",
        *(f"{key} = {json.dumps(value, allow_nan=False)}" for key, value in distributions.items()),
    ]
    supplied_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    resolved = [
        resolve_row_fsi(
            inputs,
            {"FSI": stem, "FSI_BENDING_STIFFNESS_N_M2_FACTOR": "1.15"},
        )
        for stem in ("f_calculated", "f_supplied")
    ]
    calculated, supplied = resolved
    assert calculated is not None and supplied is not None
    for key in distributions:
        assert getattr(calculated.effective.blade, key) == getattr(supplied.effective.blade, key)
    for raw, effective in zip(
        base.blade.bending_stiffness_n_m2,
        calculated.effective.blade.bending_stiffness_n_m2,
        strict=True,
    ):
        assert math.isclose(effective, raw * 1.15, rel_tol=1e-12)
    assert calculated.origins["bending_stiffness_n_m2"] == "matrix"
    return {
        "mode_equivalence": "verified for every supplied blade distribution",
        "base_EI_N_m2": base.blade.bending_stiffness_n_m2,
        "effective_EI_N_m2": calculated.effective.blade.bending_stiffness_n_m2,
        "file_factor": 1.05,
        "matrix_factor": 1.15,
        "factor_origin": calculated.origins["bending_stiffness_n_m2"],
        "input_sha256": {item.mode: item.source_sha256 for item in (calculated, supplied)},
        "solver_executed": False,
    }


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Write the two new inputs and print their verified calibration comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(run_example(args.workspace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
