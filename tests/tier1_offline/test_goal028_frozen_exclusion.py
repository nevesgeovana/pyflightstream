"""The campaign instrument leaves a frozen or unreadable point out of the DRAG check too.

Two callers were wrong before the independent review of the 0.24.0 evidence: the drag
check judged the unsteady rows of a frozen point while the page claimed every verdict
excluded them, and matching a polar row to a log by the point NAME alone struck out a
live row with another simulation's freeze, since two rows of one campaign share a point
name. Both are exercised here through the caller, on a workspace written by hand.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "measure_campaign_coherence", ROOT / "scripts" / "measure_campaign_coherence.py"
)
coherence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coherence)  # type: ignore[union-attr]

POINT = "M144RE438AL+100BE+000"
LIVE = "+5.5597573E-4      \t+5.6313020E-4"
DEAD = "+0.0000000E+0      \t+0.0000000E+0"


def _log(kind: str) -> str:
    out = []
    for step in (1, 2, 3):
        rows = [LIVE, LIVE, LIVE] if kind == "clean" or step == 1 else [LIVE, DEAD, DEAD]
        out.append(f"Solving unsteady time-step iteration ({step}/3)...")
        out += [f"{100 * step + k}               \t{r}      \t-3.7E-5" for k, r in enumerate(rows)]
    return "\n".join(out) + "\n"


def _polar(sim: str, cdw: str = "0.02000") -> str:
    # One unsteady polar row: the window, the run it came from, and one axis pair the
    # drag check judges (CDW against the CD the solver plots for the same group).
    return (
        "FIRST_STEP,LAST_STEP,ALPHA,run_id,CDW_MRP_TOTAL,CD_MRP_TOTAL\n"
        f"1,3,10.00000,pfs0240/sim_{sim}/{POINT},{cdw},0.02000\n"
    )


def _workspace(
    tmp_path: Path, logs: dict[str, str], cdw: dict[str, str] | None = None
) -> tuple[Path, Path]:
    workspace = tmp_path / "campaign"
    out = workspace / "post" / "matriz"
    (out / "polars").mkdir(parents=True)
    for sim, kind in logs.items():
        datapoint = workspace / "sims" / f"sim_{sim}" / "datapoints" / f"DP-{POINT}"
        datapoint.mkdir(parents=True)
        if kind != "missing":
            text = "FlightStream version 26.1\n" if kind == "unreadable" else _log(kind)
            (datapoint / f"P{sim}-{POINT}_log.txt").write_text(text, encoding="latin-1")
        (out / "polars" / f"P{sim}_{POINT}_uns_avg.csv").write_text(
            _polar(sim, (cdw or {}).get(sim, "0.02000")), encoding="utf-8"
        )
    return workspace, out


def _left_out(workspace: Path, out: Path) -> dict[str, str]:
    check = coherence.steady_drag(workspace, out)
    return {
        str(row["polar"]): str(row["why"]) for row in check["measured"]["unsteady_rows_left_out"]
    }


def _measured(workspace: Path, out: Path) -> set[str]:
    """The polars whose rows actually reached the measurement, not the exclusion list.

    A row can be LISTED as excluded and measured anyway, and a row can be dropped from
    the measurement without being listed: two faults the first writing of these tests
    let through, because it read the exclusion list alone (the independent review of
    the evidence, round three).
    """
    check = coherence.steady_drag(workspace, out)
    return {str(row["polar"]) for row in check["measured"]["unsteady_polar_rows"]}


def test_the_drag_check_leaves_out_a_frozen_point_and_keeps_the_live_one(tmp_path: Path) -> None:
    workspace, out = _workspace(tmp_path, {"2412": "frozen", "2415": "clean"})
    left_out = _left_out(workspace, out)
    assert list(left_out) == [f"P2412_{POINT}_uns_avg.csv"]
    assert "froze at step 2" in left_out[f"P2412_{POINT}_uns_avg.csv"]
    # AND IT REACHED NO MEASUREMENT: being on the list is not being left out.
    assert _measured(workspace, out) == {f"P2415_{POINT}_uns_avg.csv"}


def test_a_point_is_matched_to_its_own_simulations_log(tmp_path: Path) -> None:
    # The two simulations share the point NAME; only 2412 froze. Matching on the name
    # alone struck 2415 out with 2412's log.
    workspace, out = _workspace(tmp_path, {"2412": "frozen", "2415": "clean"})
    assert f"P2415_{POINT}_uns_avg.csv" not in _left_out(workspace, out)
    assert f"P2415_{POINT}_uns_avg.csv" in _measured(workspace, out)


def test_a_frozen_row_that_disagrees_does_not_decide_the_verdict(tmp_path: Path) -> None:
    # The frozen row's CDW is a hundred times its plotted CD: judged, it would carry the
    # verdict on its own. Excluded, the live row decides and the check holds.
    workspace, out = _workspace(
        tmp_path, {"2412": "frozen", "2415": "clean"}, cdw={"2412": "2.00000"}
    )
    # The verdict itself reads could-not-measure here, since this workspace holds no
    # steady export for the rest of the check; what the exclusion decides is the worst
    # gap, which the frozen row would carry to 1.98 and which stays at the live row's.
    check = coherence.steady_drag(workspace, out)
    assert _measured(workspace, out) == {f"P2415_{POINT}_uns_avg.csv"}
    assert check["measured"]["worst_gap"] == 0.0


def test_an_unreadable_log_leaves_the_point_out(tmp_path: Path) -> None:
    workspace, out = _workspace(tmp_path, {"2415": "unreadable"})
    assert _left_out(workspace, out) == {f"P2415_{POINT}_uns_avg.csv": "log unreadable"}


def test_a_point_with_no_log_leaves_the_point_out(tmp_path: Path) -> None:
    # A workspace that KEEPS logs and has none for this point: the point is not judged.
    # (A workspace that keeps none at all cannot be asked at all, and the check says so
    # under `frozen_rule` instead of striking every point out for the same reason.)
    workspace, out = _workspace(tmp_path, {"2412": "clean", "2415": "missing"})
    assert _left_out(workspace, out) == {f"P2415_{POINT}_uns_avg.csv": "no native log"}


def test_a_workspace_that_keeps_no_log_says_the_rule_did_not_run(tmp_path: Path) -> None:
    workspace, out = _workspace(tmp_path, {"2415": "missing"})
    check = coherence.steady_drag(workspace, out)
    assert check["measured"]["unsteady_rows_left_out"] == []
    assert check["measured"]["frozen_rule"].startswith("NOT APPLIED")
