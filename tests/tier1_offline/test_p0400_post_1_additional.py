"""P0400-STALEREMEDY (PFS-2100.003): the stale-extraction remedy names the matrix.

``pyfs-matrix post --additional-pproc`` without the matrix is refused by the
CLI (the ADDITIONAL_PPROC key is read from its rows), so a remedy printed
without it names a command that fails.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from pyflightstream.post._additional import _current_extraction


@pytest.mark.parametrize((), [pytest.param(id="P0400-STALEREMEDY")])
def test_p0400_staleremedy_names_the_matrix() -> None:
    """P0400-STALEREMEDY: a rerun point's remedy names its matrix stem."""
    extraction = SimpleNamespace(
        run_id="R1", fsm="P1.fsm", fsm_sha256="a" * 64, matrix_stem="wing", sim_id="S1"
    )
    point = SimpleNamespace(outputs_sha256={"P1.fsm": "b" * 64})
    reason = _current_extraction(cast(Any, None), cast(Any, extraction), cast(Any, point))
    assert reason is not None
    assert "pyfs-matrix post wing --additional-pproc" in reason
