"""Driver of test_p0540_lanes: plan or run one lane of a matrix in its own OS process.

``python _p0540_lane_driver.py plan|run <workspace> <matrix> <stub folder> [<sim> ...]``.
The solver is the stand-in of the local-run tests; the run is `run_matrix`, the call
`pyfs-matrix run` makes, with ``sims`` as `--sims`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pyflightstream.run import CampaignErrors, LoadsAssessor
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_goal031_local_run_log import Solver
from tests.tier1_offline.test_matrix_run import RECIPES, workflow_registry


def main(argv: list[str]) -> int:
    mode, root, matrix, stub, *sims = argv
    workspace = CampaignWorkspace.open(root)
    common = {
        "name": "local",
        "default_fs_version": "26.120",
        "recipes": RECIPES,
        "recipe_registry": workflow_registry(),
        "sims": sims or None,
    }
    if mode == "plan":
        plan_matrix(matrix, workspace, **common)
        return 0
    Path(stub).mkdir(parents=True, exist_ok=True)
    try:
        run_matrix(
            matrix,
            workspace,
            assess=LoadsAssessor(),
            executor=Solver(Path(stub), forced_local=True, export_log=False),
            local=True,
            require_plan=True,
            **common,
        )
    except CampaignErrors:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
