"""An unsteady run plots each rotor's own history in the global frame, unless the pproc does.

THE REQUIREMENT (L6-04, the run half). The rotor table of an unsteady point is the
window average of the rotor's force and moment history in the global `MRP` frame,
over the rotor's OWN families, general and blades. A run whose pproc plots that for
no group could never state it, so the run adds the group itself, `ROTOR_<ALIAS>`,
the way it adds `MRP_TOTAL` for the axes. A pproc that already plots the six over
exactly those families renders the same script for that rotor.

`ROTOR_<ALIAS>` and not the bare alias: a pproc may name a group of its own after
the alias over OTHER families, and an expanding frame names its emissions `<alias>`
in the rotor's own turning axes. Neither is the rotor's global-frame history.
"""

from __future__ import annotations

from pyflightstream.cases import PprocSpec, ReferenceData
from pyflightstream.post.products import rotor_plot_source
from tests.tier1_offline.test_rotor_by_alias import LIFTER, PUSHER, rendered, two_rotor_case

SIX = ("FX", "FY", "FZ", "MX", "MY", "MZ")
PUSHER_FAMILIES = [*PUSHER.families_general, *PUSHER.families_blades]


def _case(tmp_path, plots: dict):
    pproc = PprocSpec.model_validate({"groups": {"1": ["W"]}, "plots": plots})
    reference = ReferenceData(area=16.0, length=1.6, span_m=10.0, moment_point_m=(0.0, 0.0, 0.0))
    return two_rotor_case(tmp_path).model_copy(
        update={"pproc": pproc, "pproc_id": "p001", "reference": reference}
    )


def _plots(text: str) -> dict[str, dict[str, str]]:
    lines = text.splitlines()
    found: dict[str, dict[str, str]] = {}
    for at, line in enumerate(lines):
        if line != "UNSTEADY_SOLVER_NEW_FORCE_PLOT":
            continue
        block: dict[str, str] = {}
        for entry in lines[at + 1 : at + 8]:
            if not entry.strip():
                break
            key, _, value = entry.partition(" ")
            block[key] = value
        found[block["NAME"]] = block
    return found


def test_each_rotor_the_row_turns_gets_its_six_components_over_its_own_families(tmp_path):
    plots = _plots(rendered(_case(tmp_path, {"parameters": ["CL"]})))
    for alias, rotor in (("LIFT_L1", LIFTER), ("PUSHER", PUSHER)):
        for part in SIX:
            block = plots.get(f"{part}_ROTOR_{alias}")
            assert block is not None, (alias, part, sorted(plots))
            assert block["UNITS"] == "NEWTONS"
            owned = len(rotor.families_general) + len(rotor.families_blades)
            assert block["BOUNDARIES"] == str(owned), block
    # The global frame: the one the package's own `MRP_TOTAL` group is plotted in.
    assert plots["FX_ROTOR_PUSHER"]["FRAME"] == plots["FX_MRP_TOTAL"]["FRAME"]


def test_a_pproc_that_already_plots_a_rotors_families_in_the_global_frame_adds_nothing(tmp_path):
    declared = {
        "parameters": list(SIX),
        "groups": [{"name": "HUB_PUSHER", "frame": "MRP", "families": PUSHER_FAMILIES}],
    }
    plots = _plots(rendered(_case(tmp_path, declared)))
    assert "FX_HUB_PUSHER" in plots
    assert "FX_ROTOR_PUSHER" not in plots, "the artifact already plots this rotor's history"
    assert "FX_ROTOR_LIFT_L1" in plots, "the other rotor still has none"


def test_a_group_over_the_rotors_families_in_its_own_frame_does_not_count(tmp_path):
    """The same surfaces in axes that turn with the rotor are not its global-frame history."""
    declared = {
        "parameters": list(SIX),
        "groups": [{"name": "OWN_PUSHER", "frame": "PUSHER_SMRP", "families": PUSHER_FAMILIES}],
    }
    plots = _plots(rendered(_case(tmp_path, declared)))
    assert "FX_OWN_PUSHER" in plots, "the artifact's own plot is still emitted"
    assert "FX_ROTOR_PUSHER" in plots, "and the run still adds the global-frame one"
    assert plots["FX_ROTOR_PUSHER"]["FRAME"] != plots["FX_OWN_PUSHER"]["FRAME"]


def test_a_group_that_only_shares_the_aliass_name_is_not_the_rotors_history():
    """`PUSHER` over the blades alone, while the rotor `PUSHER` owns a spinner too."""
    pproc = PprocSpec.model_validate(
        {
            "plots": {
                "parameters": list(SIX),
                "groups": [{"name": "PUSHER", "frame": "MRP", "families": PUSHER.families_blades}],
            }
        }
    )
    inventory = [*PUSHER_FAMILIES, "W"]
    candidates, _refused = rotor_plot_source(
        pproc, "PUSHER", rotor_families=PUSHER_FAMILIES, inventory=inventory
    )
    assert candidates == ["ROTOR_PUSHER"], candidates


def test_a_group_over_exactly_the_rotors_families_is_found_whatever_it_is_called():
    pproc = PprocSpec.model_validate(
        {
            "plots": {
                "parameters": list(SIX),
                "groups": [{"name": "HUB_PUSHER", "frame": "MRP", "families": PUSHER_FAMILIES}],
            }
        }
    )
    candidates, refused = rotor_plot_source(
        pproc, "PUSHER", rotor_families=PUSHER_FAMILIES, inventory=[*PUSHER_FAMILIES, "W"]
    )
    assert candidates == ["HUB_PUSHER", "ROTOR_PUSHER"] and refused is None
