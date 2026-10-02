"""Tier 1: the cause of the REAL control-surface failure, separated by a probe (FR-336, RPT-126).

Marker P0340-CCS2-REAL. The fixture ``fixtures/rpt126/ccs2_real_arms.json`` is the record of the
seven control-surface arms of RPT-126 on FlightStream 26.124 (build 8172026): each arm's target
line, outcome, sentinels, return code, and whether each loft and the solved save were written;
no geometry and no path. ``fixtures/rpt126/arity_arms.json`` is the record of the five arity
forms of each CCS export of FR-335 (outcome, sentinel after the command, file written and its
digest), read here against the criterion fixed before the run.

RPT-126 measured `refusal_stays`: the REAL token is not the cause, the limits 2.0 and 3.6 end
the solver process in both spaces, and RPT-097's row neither solved nor saved. What this module
cannot hold, named so it is not forgotten: FR-336 R4's `refusal_stays` branch also asks that the
refusal's MESSAGE cite RPT-126. The message lives in ``src/pyflightstream/cases/ccs_wing.py``
and still cites RPT-097 (``test_p0320_ccs.py``); the citation and its test are owed to 0.35.0.
A `form_works` verdict would be the same: its re-admission is src, and the first test fails on
it by design.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from tests.tier1_offline.test_p0320_ccs import AILERON, _built, _real_case, _row_case

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "reports"
FIX = Path(__file__).resolve().parent / "fixtures" / "rpt126"
CS = "NEW_CCS_WING_CONTROL_SURFACE"
EXPORTS = ("EXPORT_FUSELAGE_CCS_FILE", "EXPORT_REVOLVE_CCS_FILE")
#: The pairs that change one thing (FR-336 R1): the arm, the arm it is compared with, what moves.
PAIRS = (
    ("R", "P", "space"),
    ("RL", "R", "limits"),
    ("PL", "P", "limits"),
    ("RX", "RL", "axis"),
    ("P_s", "P", "none"),
    ("RL_s", "RL", "none"),
)


def _front_matter(number: int) -> tuple[Path, dict[str, str]]:
    found = sorted(REPORTS.glob(f"RPT-{number}_*.md"))
    if not found:
        pytest.fail(f"RPT-{number} is not in reports/: its licensed run owes it")
    lines = found[0].read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in lines[1:]:
        pytest.fail(f"{found[0].name} opens with no front matter between two '---' lines")
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    return found[0], fields


def _arms() -> dict[str, dict]:
    return json.loads((FIX / "ccs2_real_arms.json").read_text(encoding="utf-8"))["arms"]


def _arity_arms() -> dict[str, dict]:
    return json.loads((FIX / "arity_arms.json").read_text(encoding="utf-8"))


def verdict_from(arms: dict[str, dict]) -> str:
    """FR-336 R4, fixed before the run: form_works only when RPT-097's row (RL_s) saved."""
    return "form_works" if arms["RL_s"]["solved_save"] else "refusal_stays"


def lofted(arm: dict) -> bool:
    """Return whether an arm ran past the command and wrote both lofts."""
    return bool(arm["sentinel_after"] and arm["reference_loft"] and arm["variant_loft"])


def arity_from(arms: dict[str, dict]) -> str:
    """FR-335, the criterion fixed before the run: six, four or undetermined from the five forms."""

    def ok(form: str) -> bool:
        return bool(arms[form]["written"] and arms[form]["sentinel_after"])

    def same(a: str, b: str) -> bool:
        return ok(a) and ok(b) and arms[a]["sha256"] == arms[b]["sha256"]

    if ok("A6") and ok("A6m") and not same("A6", "A6m"):
        return "six"
    if same("A6", "A6m") and same("A6", "A4") and ok("A4c") and not same("A4", "A4c"):
        return "four"
    return "undetermined"


def changed_tokens(a: str, b: str) -> list[int]:
    """Return the positions of the tokens that differ between two command lines."""
    ta, tb = a.split(" "), b.split(" ")
    return [
        i
        for i in range(max(len(ta), len(tb)))
        if (ta[i : i + 1] or [None]) != (tb[i : i + 1] or [None])
    ]


def test_rpt126_states_the_ccs2_real_verdict_and_the_plan_still_refuses_real_fr_336(tmp_path):
    """P0340-CCS2-REAL, FR-336 R2 and R3: `refusal_stays`, a cause stated, and the refusal holds."""
    report, fields = _front_matter(126)
    verdict = fields.get("ccs2_real_verdict")
    assert verdict in {"refusal_stays", "form_works"}, (
        f"{report.name}: ccs2_real_verdict is {verdict!r}; FR-336 accepts refusal_stays "
        "or form_works"
    )
    if verdict == "form_works":
        pytest.fail(
            f"{report.name} measures a REAL form that runs: its re-admission on the measured "
            "build, its "
            "tests and the amended FR-297 (FR-336 R2, R4) are src, owed to 0.35.0"
        )
    assert len(fields.get("ccs2_real_cause", "")) >= 20, (
        f"{report.name} states no cause, nor that none was separated (R3)"
    )
    with pytest.raises(CampaignConfigError, match="refus"):
        _built(_real_case(tmp_path))


def test_the_parametric_form_the_control_arm_ran_is_still_planned_fr_336(tmp_path):
    """P0340-CCS2-REAL, FR-336 R1: the control: arm P's PARAMETRIC line is the planned one."""
    case = _row_case(tmp_path, "wing", 'kind = "wing"\ncomponent = 1\n' + AILERON, ["WING"])
    _, lines = _built(case)
    assert f"{CS} AIL 0.5 0.9 0.25 0.25 0.5 20.0 1.0 PARAMETRIC Y" in lines
    assert (
        _arms()["P"]["line"].split(" ")[2:]
        == lines[lines.index(f"{CS} AIL 0.5 0.9 0.25 0.25 0.5 20.0 1.0 PARAMETRIC Y")].split(" ")[
            2:
        ]
    )


def test_the_recorded_arms_give_the_verdict_rpt126_states_fr_336():
    """P0340-CCS2-REAL, FR-336 R1 and R4: the control arms ran, and the verdict follows RL_s."""
    arms = _arms()
    assert arms["P"]["outcome"] == "verified", (
        "the PARAMETRIC control did not run: nothing is separated"
    )
    assert arms["P_s"]["solved_save"], (
        "the PARAMETRIC row did not solve and save: the solve arms separate nothing"
    )
    _, fields = _front_matter(126)
    assert verdict_from(arms) == fields.get("ccs2_real_verdict")


def test_the_recorded_arms_separate_the_limits_not_the_space_fr_336():
    """P0340-CCS2-REAL, FR-336 R1 and R3: the cause RPT-126 states is the one the arms record.

    REAL with 0.5 and 0.9 is lofted without error, as PARAMETRIC is (R against P); the limits
    2.0 and 3.6 write no loft in either space (RL against R, PL against P) nor along the
    other axis (RX against RL).
    """
    arms = _arms()
    assert lofted(arms["P"]) and lofted(arms["R"]), "the space alone stopped the loft"
    for name in ("RL", "PL", "RX", "RL_s"):
        assert arms[name]["sentinel_after"], f"{name} stopped at the command line"
        assert not lofted(arms[name]) and arms[name]["return_code"] != 0, (
            f"{name} with the limits 2.0 and 3.6 ran to the end: the limits separate nothing"
        )
    _, fields = _front_matter(126)
    cause = fields.get("ccs2_real_cause", "")
    assert "REAL token is not the cause" in cause and "2.0 and 3.6" in cause, cause


def test_each_arm_changes_one_thing_against_its_pair_fr_336():
    """P0340-CCS2-REAL, FR-336 R1: each probe changes one thing against the form that runs."""
    arms = _arms()
    for arm, pair, what in PAIRS:
        moved = changed_tokens(arms[arm]["line"], arms[pair]["line"])
        expected = {"space": [9], "limits": [2, 3], "axis": [10], "none": []}[what]
        assert moved == expected, f"{arm} against {pair}: tokens {moved} moved, {what} expected"


def test_a_planted_saved_real_row_reads_form_works_fr_336():
    """P0340-CCS2-REAL, FR-336 R4: the control of the verdict rule."""
    arms = {"RL_s": {"solved_save": False}}
    assert verdict_from(arms) == "refusal_stays"
    arms["RL_s"]["solved_save"] = True
    assert verdict_from(arms) == "form_works"


@pytest.mark.parametrize("command", EXPORTS)
def test_the_recorded_arity_forms_give_the_arity_rpt126_states_fr_335(command):
    """FR-335 R1: the five forms of each export give the arity RPT-126 states (undetermined)."""
    record = _arity_arms()[command]
    assert set(record["arms"]) == {"A6", "A6m", "A6c", "A4", "A4c"}
    wrote = [
        form for form, arm in record["arms"].items() if arm["written"] or arm["sha256"] is not None
    ]
    assert wrote == [], f"{command}: the measured fact is that no form wrote a file, got {wrote}"
    measured = arity_from(record["arms"])
    assert measured == record["verdict"], f"{command}: the forms give {measured}"
    report, _ = _front_matter(126)
    text = re.sub(r"\s+", " ", report.read_text(encoding="utf-8"))
    assert f"Measured: fuselage {_arity_arms()[EXPORTS[0]]['verdict']}, revolution " in text
    assert f"revolution {_arity_arms()[EXPORTS[1]]['verdict']}." in text


def test_a_planted_file_that_moves_with_the_two_tokens_reads_six_fr_335():
    """FR-335 R1: the control of the arity criterion, six and four are reachable."""
    form = {"outcome": "verified", "sentinel_after": True, "written": True, "sha256": "a"}
    arms = {name: dict(form) for name in ("A6", "A6m", "A6c", "A4", "A4c")}
    assert arity_from(arms) == "undetermined", "a control token that moves nothing proves nothing"
    arms["A4c"]["sha256"] = "b"
    assert arity_from(arms) == "four"
    arms["A6m"]["sha256"] = "c"
    assert arity_from(arms) == "six"
    arms["A6"]["written"] = False
    assert arity_from(arms) == "undetermined"
