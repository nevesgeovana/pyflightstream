"""Tier 1: the parity checker names the section-plot drop of 0.33.1 only where FR-51 states it.

P0331-SECTIONS-ABSENT-FAMILY (FR-51): a script that lost its section Cp plot is a named
difference only when the release script cuts no section, the difference is a pure removal
of the plot's lines, and FR-51 is defined in the release SRS.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_PLOT = "SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\nrow_plot_cp_sections.txt\n"
_SECTION = "NEW_SURFACE_SECTION_DISTRIBUTION\n"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_parity_under_test", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _name(old: str, new: str, defined: set[str]) -> dict:
    return _load().name_difference("scripts", "row.txt", old, new, defined)


def test_section_plot_drop_is_named_fr_51_only_where_the_release_cuts_no_section() -> None:
    """P0331-SECTIONS-ABSENT-FAMILY, FR-51: named only in its stated direction and state."""
    module = _load()
    assert any(n["requirement"] == "FR-51" for n in module.NAMED_DIFFERENCES)
    base = "OPEN\nSOLVE\n" + _PLOT + "\nCLOSE\n"
    dropped = "OPEN\nSOLVE\nCLOSE\n"
    defined = {"FR-51"}

    named = _name(base, dropped, defined)
    assert named.get("requirement") == "FR-51"

    # The release script still cuts a section: not the state FR-51 names.
    still_cuts = "OPEN\n" + _SECTION + "SOLVE\nCLOSE\n"
    kept = _name("OPEN\n" + _SECTION + "SOLVE\n" + _PLOT + "\nCLOSE\n", still_cuts, defined)
    assert "requirement" not in kept

    # A plot ADDED is the opposite direction.
    assert "requirement" not in _name(dropped, base, defined)

    # A drop together with another changed line is not wholly the named difference.
    assert "requirement" not in _name(base, "OPEN\nSOLVE\nEXTRA\nCLOSE\n", defined)

    # FR-51 absent from the release SRS: the drop stays unnamed, with the reason.
    unnamed = _name(base, dropped, set())
    assert "requirement" not in unnamed
    assert "FR-51" in unnamed["unnamed_because"]
