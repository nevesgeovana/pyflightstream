"""PFS-2217 (0.57.0): a row with airfoil separation on is told its section Cp is attached-flow."""

from __future__ import annotations

import warnings
from pathlib import Path

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import _steady, build_script
from pyflightstream.script import Script
from pyflightstream.script.solver_setup import AirfoilSeparation
from tests.tier1_offline.test_workflows import steady_case


def _case(*, separation: bool, sections: bool):
    case = steady_case()
    solver = case.solver.model_copy(
        update={
            "airfoil_separation": (
                [AirfoilSeparation(name="W", leading_edge_type="SHARP", boundaries=[1])]
                if separation
                else None
            )
        }
    )
    spec = {
        "sections": (
            {
                "count": 20,
                "include_symmetry": False,
                "distributions": [{"families": ["Wing"], "frame": "MRP", "planes": ["XZ"]}],
            }
            if sections
            else {}
        ),
        "exports": {"sections": sections},
    }
    outputs = ["loads_a+00.0.txt", *(["loads_a+00.0_cp.txt"] if sections else [])]
    return case.model_copy(
        update={
            "solver": solver,
            "pproc": PprocSpec.model_validate(spec),
            "inventory": ["Wing"],
            "outputs": outputs,
        }
    )


def _built(case, build: str = "26.127") -> tuple[str, list[str]]:
    script = Script(build)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build_script(case, script)
    return script.render(), [str(w.message) for w in caught]


def _cp_warnings(messages: list[str]) -> list[str]:
    return [text for text in messages if "attached-flow Cp" in text]


def test_p0570_fix6_separation_on_with_the_cp_export_warns():
    text, messages = _built(_case(separation=True, sections=True))
    assert "CREATE_AIRFOIL_SEPARATION" in text
    assert "EXPORT_ALL_SURFACE_SECTIONS" in text
    found = _cp_warnings(messages)
    assert len(found) == 1
    assert "_cp.txt" in found[0]


def test_p0570_fix6_separation_off_says_nothing():
    text, messages = _built(_case(separation=False, sections=True))
    assert "EXPORT_ALL_SURFACE_SECTIONS" in text
    assert _cp_warnings(messages) == []


def test_p0570_fix6_no_cp_export_says_nothing():
    text, messages = _built(_case(separation=True, sections=False))
    assert "CREATE_AIRFOIL_SEPARATION" in text
    assert "EXPORT_ALL_SURFACE_SECTIONS" not in text
    assert _cp_warnings(messages) == []


def test_p0570_fix6_the_warning_alters_no_line(monkeypatch):
    """The warning is the whole of the change: the script is the same without it."""
    warned = _built(_case(separation=True, sections=True))[0]
    monkeypatch.setattr(_steady, "_warn_of_an_attached_flow_cp", lambda *_: None)
    assert _built(_case(separation=True, sections=True))[0] == warned


def test_p0570_fix6_the_definitions_page_says_so():
    page = Path(__file__).resolve().parents[2] / (
        "docs/definitions/the-sections-table-and-which-row-is-which.md"
    )
    text = page.read_text(encoding="utf-8")
    assert "**Section Cp with separation on.**" in text
    assert "attached-flow Cp" in text
    assert "_cp.txt" in text
