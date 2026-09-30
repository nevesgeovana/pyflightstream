"""Setup operations on a point's surfaces: removing surfaces, and the wake option it emits.

Pipeline role: the cases row, where a row's solver commands are emitted.
It emits the removal of surfaces a row names, with the renumbering of
the surface inventory that removal causes, and the slipstream wake
stabilization setting a row states.

Laid down by the 0.32.0 preparation step so work package H writes its
code here and touches :mod:`pyflightstream.cases.workflows` only through a
short hook.

The stub's name and signature are a placeholder: the module is what the
contract fixes, and its package may rename the stub when it fills it.
Until then it refuses with
:class:`~pyflightstream._errors.ContractNotImplementedError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyflightstream._errors import ContractNotImplementedError

if TYPE_CHECKING:
    from pyflightstream.cases import SimCase
    from pyflightstream.script import Script


def emit_setup_surfaces(script: Script, case: SimCase) -> None:
    """Emit the surface setup operations of one point.

    Parameters
    ----------
    script : Script
        The script being built for the point.
    case : SimCase
        The point's case, as the matrix row and its artifacts define it.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package H fills this body.
    """
    raise ContractNotImplementedError(
        "pyflightstream.cases.setup_surfaces.emit_setup_surfaces: "
        "not implemented yet (0.32.0 contract)"
    )
