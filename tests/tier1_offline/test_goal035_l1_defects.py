"""Tier 1: the defects the short licensed runs of 0.30.0 (L1, RPT-090 to RPT-092) found.

1. A coupled row with the pproc's DEFAULT exports did not build: the
   aeroelastic post-processing script exported the loads the structural
   program reads, and the row's export block then updated the sections again,
   an analysis command after an export (``ScriptOrderError``), on the
   quasi-steady sector and on the fixed wing alike. The earlier tests built
   their coupled rows with a loads table and a log only, so they never
   declared a section export.

Every expected value is worked from the definitions and the fixture, never
read off the implementation.
"""

from __future__ import annotations

from pyflightstream.cases import SimCase
from pyflightstream.cases import fsi_workspace as ws
from tests.tier1_offline.test_fsig_fixed_wing import steady_wing_case
from tests.tier1_offline.test_goal035_qsteady_completion import _sector_fsi_case
from tests.tier1_offline.test_goal035_qsteady_rotor import _lines

#: The analysis commands the row's exports read (the phase order places every
#: one of them before the first export).
UPDATES = ("UPDATE_ALL_SURFACE_SECTIONS", "COMPUTE_SURFACE_SECTIONAL_LOADS", "UPDATE_PROBE_POINTS")


def _with_default_outputs(case: SimCase, stem: str = "DP") -> SimCase:
    """The row as the campaign renders it: its pproc's default outputs, named for the point."""
    assert case.pproc is not None
    names = [name.replace("{name}", stem) for name in case.pproc.outputs(False)]
    return case.model_copy(update={"outputs": names})


def _post_commands(case: SimCase) -> list[str]:
    """Plan the row and return the command lines of its post-processing script."""
    _, script = _lines(case)
    text = script.pending_input_files[ws.POST_FILE]
    return [line.split()[0] for line in text.splitlines() if line.strip() and line[0].isupper()]


def _assert_one_valid_order(commands: list[str]) -> None:
    exports = [
        at
        for at, command in enumerate(commands)
        if command.startswith(("EXPORT_", "SAVEAS", "SAVE_PLOT", "SET_PLOT_TYPE"))
    ]
    updates = [at for at, command in enumerate(commands) if command in UPDATES]
    # The sections are updated and their loads computed ONCE, the probe points
    # once, and every update precedes every export.
    assert [commands[at] for at in updates] == list(UPDATES)
    assert max(updates) < min(exports)


def _declares_the_section_kinds(case: SimCase) -> None:
    names = " ".join(case.outputs)
    for suffix in ("_cp.txt", "_sloads.txt", "_probes.txt", "_plot_cp_sections.txt"):
        assert suffix in names, suffix


def test_a_coupled_sector_with_the_default_exports_plans_in_one_valid_order(tmp_path):
    # P0300-QS-SECTOR-FSI
    case = _with_default_outputs(_sector_fsi_case(tmp_path))
    _declares_the_section_kinds(case)
    commands = _post_commands(case)
    _assert_one_valid_order(commands)
    text = _lines(case)[1].pending_input_files[ws.POST_FILE]
    # The loads the structural program reads come first, the row's own
    # section exports after them, each once.
    assert text.index(ws.LOADS_FILE) < min(text.index("DP_cp.txt"), text.index("DP_sloads.txt"))
    assert commands.count("EXPORT_SURFACE_SECTIONAL_LOADS") == 2
    assert commands.count("EXPORT_ALL_SURFACE_SECTIONS") == 1
    assert commands.count("EXPORT_PROBE_POINTS") == 1


def test_a_coupled_fixed_wing_with_the_default_exports_plans_in_one_valid_order(tmp_path):
    # P0300-FSIG-STEADY
    case = _with_default_outputs(steady_wing_case(tmp_path))
    _declares_the_section_kinds(case)
    commands = _post_commands(case)
    _assert_one_valid_order(commands)
    assert commands.count("EXPORT_ALL_SURFACE_SECTIONS") == 1
    assert commands.count("EXPORT_PROBE_POINTS") == 1
