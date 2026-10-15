"""Plan-time inflow maps from the public workflow input resolver."""

from pathlib import Path
from typing import Any, cast

from pyflightstream.cases import SimCase
from pyflightstream.cases.workflows import qsteady_inflow_map_inputs
from pyflightstream.post.inflow_tools import inflow_harmonics_map, write_inflow_harmonics
from pyflightstream.workspace import register_plan_product_writer


def _write(case: SimCase, folder: Path) -> list[Path]:
    inputs = qsteady_inflow_map_inputs(case)
    if inputs is None:
        return []
    result = inflow_harmonics_map(**cast(dict[str, Any], inputs))
    return list(write_inflow_harmonics(folder, result, overwrite=True))


register_plan_product_writer(_write)
