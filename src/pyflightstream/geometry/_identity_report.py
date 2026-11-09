"""The identity report of a section: what the seed says against what was measured (stage S2).

Pipeline role: pure numerical stage of the geometry package. A designation named as the seed of a
section and the sections measured from an original are compared on two numbers, the maximum
thickness in chord lengths and the chord fraction where it lies. The report lists; it never fails,
because a mismatch is a finding for the owner, not a refusal.
"""

from __future__ import annotations

import numpy as np

from ._airfoils import naca_to_cst
from ._sections import SectionForm, section_from_stored

__all__ = ["identity_report", "thickness_profile"]

#: Differences below these are the same section for the report: thickness in chord lengths,
#: position in chord fractions.
THICKNESS_TOLERANCE = 2e-3
POSITION_TOLERANCE = 2e-2


def thickness_profile(section: SectionForm) -> dict:
    """Return the maximum thickness and its chord fraction of a section, on a dense grid."""
    x = (1 - np.cos(np.linspace(0, np.pi, 4001))) / 2
    upper, lower = section.evaluate(x)
    thickness = upper[:, 1] - lower[:, 1]
    index = int(np.argmax(thickness))
    return {"thickness": float(thickness[index]), "position": float(x[index])}


def identity_report(seed, measured=None) -> list[dict]:
    """Return one record per measured section: the seed's numbers against the measured ones.

    ``seed`` is a four or five digit designation, as written in the input (``"0012"`` or
    ``"NACA0012"``); ``measured`` is a mapping from a label to a ``SectionForm``. Without
    measured sections the report holds the seed alone. Each record has ``id``
    (``identity.listed``), ``status`` (``match``, ``mismatch`` or ``seed only``; never a
    failure), the two sets of numbers and the differences.
    """
    name = seed if str(seed).upper().startswith("NACA") else f"NACA{seed}"
    own = thickness_profile(section_from_stored(naca_to_cst(name.upper())))
    if not measured:
        return [{"id": "identity.listed", "section": str(name), "status": "seed only", "seed": own}]
    records = []
    for label, section in measured.items():
        found = thickness_profile(section)
        d_thickness = found["thickness"] - own["thickness"]
        d_position = found["position"] - own["position"]
        same = abs(d_thickness) <= THICKNESS_TOLERANCE and abs(d_position) <= POSITION_TOLERANCE
        records.append(
            {
                "id": "identity.listed",
                "section": str(label),
                "status": "match" if same else "mismatch",
                "seed": own,
                "measured": found,
                "difference": {"thickness": d_thickness, "position": d_position},
            }
        )
    return records
