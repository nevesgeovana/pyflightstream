# %% [markdown]
# # Inspect a continuation without a solver
#
# Supply a resolved case and recorded workspace to inspect whether a stopped
# run can continue. The output preserves the evidence and reasons for refusal;
# this example does not launch FlightStream.
#
# %%
"""Inspect recovery for a resolved named-workflow case, without a solver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyflightstream._cli import cli_entrypoint
from pyflightstream.cases import SimCase, point_name
from pyflightstream.cases.workflows import build_script
from pyflightstream.run import resolve_continuation
from pyflightstream.workspace import CampaignWorkspace


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Inspect a continuation and print its evidence without running it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("case_json", type=Path, help="resolved SimCase.model_dump_json()")
    parser.add_argument("--point", required=True, help='JSON point, such as {"alpha": 0.0}')
    parser.add_argument("--fs-version", required=True)
    args = parser.parse_args(argv)
    case = SimCase.model_validate_json(args.case_json.read_text(encoding="utf-8"))
    point = json.loads(args.point)
    if not isinstance(point, dict):
        parser.error("--point must be a JSON object")
    result = resolve_continuation(
        CampaignWorkspace(args.workspace),
        case,
        point,
        run_id=f"inspection/sim_{case.sim_id}/{point_name(case, point)}",
        recipe=build_script,
        fs_version=args.fs_version,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
