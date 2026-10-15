"""Plan the quasi steady rotor using the public Python API."""

import argparse
from pathlib import Path

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import CampaignPlan
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import CampaignWorkspace


def dry_run(workspace: Path) -> CampaignPlan:
    """Build every point without launching FlightStream.

    Parameters
    ----------
    workspace : Path
        Prepared copy of the matching CLI workspace.

    Returns
    -------
    CampaignPlan
        The points and their readiness; no solver results are claimed.
    """
    return plan_matrix(
        workspace / "matrix.fs",
        CampaignWorkspace(workspace),
        name=workspace.resolve().name,
        name_from="directory",
        recipes={},
        recipe_registry=workflow_registry(),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    plan = dry_run(parser.parse_args().workspace)
    print(plan.summary())
    raise SystemExit(0 if all(p.status.value == "READY" for p in plan.points) else 2)
