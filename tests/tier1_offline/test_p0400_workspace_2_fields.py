"""P0400-SUBTRACTMATCH: subtract_fields pairs the two grids one to one, never by an assert."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pyflightstream.workspace.fields import Field, subtract_fields

_CHECK = """
from pyflightstream.workspace.fields import Field, subtract_fields
total = Field("UNSTRUCTURED", ((0.0, 0, 0, 1.0, 0, 0), (1.8e-6, 0, 0, 2.0, 0, 0)))
other = Field("UNSTRUCTURED", ((0.9e-6, 0, 0, 10.0, 0, 0), (2.7e-6, 0, 0, 20.0, 0, 0)))
rows = subtract_fields(total, other, reference_m_s=(0.0, 0.0, 0.0), tolerance_m=1e-6).rows
print([row[3] for row in rows])
"""


def test_p0400_subtractmatch_a_point_near_two_takes_the_one_left():
    """P0400-SUBTRACTMATCH (PFS-2086.001): total x = [0, 1.8e-6] and other x = [0.9e-6, 2.7e-6]
    at 1e-6 m pair 0-0 and 1-1 (the only pairing), where the first-candidate rule paired both
    with other's first point and raised a bare AssertionError."""
    total = Field("UNSTRUCTURED", ((0.0, 0, 0, 1.0, 0, 0), (1.8e-6, 0, 0, 2.0, 0, 0)))
    other = Field("UNSTRUCTURED", ((0.9e-6, 0, 0, 10.0, 0, 0), (2.7e-6, 0, 0, 20.0, 0, 0)))
    rows = subtract_fields(total, other, reference_m_s=(0.0, 0.0, 0.0), tolerance_m=1e-6).rows
    assert [row[3] for row in rows] == [-9.0, -18.0]


def test_p0400_subtractmatch_the_same_outcome_under_python_o():
    """P0400-SUBTRACTMATCH (PFS-2086.001): under python -O, where an assert does not run, the
    pairing is the same and no row is subtracted from the wrong partner."""
    src = Path(__file__).resolve().parents[2] / "src"
    done = subprocess.run(
        [sys.executable, "-O", "-c", f"import sys; sys.path.insert(0, {str(src)!r})\n{_CHECK}"],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    assert done.stdout.strip() == "[-9.0, -18.0]", done.stdout + done.stderr
