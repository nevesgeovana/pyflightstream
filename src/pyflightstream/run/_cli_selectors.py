"""One argument grammar for simulation selectors across matrix commands."""

import argparse
from typing import Any

from pyflightstream.workspace.ledger import SIMS_IDS_HELP, listed_sims


class _SimulationIds(argparse.Action):
    def __call__(self, parser: Any, namespace: Any, values: Any, option_string: Any = None) -> None:
        setattr(namespace, self.dest, listed_sims(values))


def _add_sim_ids(parser: Any, *, help: str = SIMS_IDS_HELP, required: bool = False) -> None:
    """Add the shared --sims ID [ID ...] spelling, retaining comma/bracket input."""
    parser.add_argument(
        "--sims",
        nargs="+",
        metavar="ID",
        default=None,
        required=required,
        action=_SimulationIds,
        help="Use --sims ID [ID ...]; commas and brackets are also accepted. " + help,
    )
