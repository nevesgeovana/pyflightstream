"""Strategy 1 boundary laws and measured surface-mesh policy.

Pipeline role: workspace mesh planning and acceptance, downstream of the pure
schema. Shared edges use one ordered node list. Measurements are made on the
realized mesh, independently of the requested controls.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pyflightstream._errors import InputValueError


def follower_edges(controls: Mapping[str, Any], edge_nodes: Mapping) -> dict:
    """Copy neighbour boundary divisions in dependency and declared priority order.

    Node identities and their order are preserved. A follower may not prescribe
    its own edge distribution; flexible interiors are handled after boundaries.
    """
    result = deepcopy(dict(edge_nodes))
    for name in controls["order"]:
        component = controls["components"][name]
        if component["role"] != "follower":
            result.setdefault(name, {})
            continue
        if result.get(name):
            raise InputValueError(f"{name}: follower cannot own a distribution")
        result[name] = {}
        for neighbour in component["follows"]:
            for edge, nodes in result.get(neighbour, {}).items():
                result[name].setdefault(edge, deepcopy(nodes))
    return result
