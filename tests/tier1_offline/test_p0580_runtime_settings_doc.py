"""P0580-RUNTIME-SETTINGS-DOC (PFS-2228): how a Python user builds runtime settings.

``RuntimeSettings`` is private (``cases/_runtime_settings.py``). Naming it public would put it
in ``cases.settings.__all__``, and the cases-cut rule (``test_p0340_cases_cut``) then requires
the root ``__all__``, which is pinned to the v0.33.0 list. So the choice recorded for 0.58.0 is
the documented route: a mapping, or the TOML ``[runtime]`` block, validated by
``SolverSettings(runtime=...)``. These tests keep that route working and stated.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.cases import SolverSettings

PAGE = Path(__file__).resolve().parents[2] / "docs" / "setup-standards.md"


def _runtime_section() -> str:
    text = PAGE.read_text(encoding="utf-8")
    start = text.index("## Launch runtime resources")
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_p0580_a_mapping_builds_the_runtime_settings_of_a_solver_setting():
    settings = SolverSettings(runtime={"max_threads": 4, "parallel": 2})
    assert settings.runtime is not None
    assert (settings.runtime.max_threads, settings.runtime.parallel) == (4, 2)
    assert SolverSettings().runtime is None


def test_p0580_a_wrong_runtime_key_is_refused_by_the_same_route():
    with pytest.raises(ValidationError, match="threads"):
        SolverSettings(runtime={"threads": 4})


def test_p0580_the_setup_page_states_the_python_route_and_that_the_type_is_private():
    section = _runtime_section()
    assert "SolverSettings(runtime=" in section, section
    assert re.search(r"RuntimeSettings.{0,80}(not|no) (a )?public", section, re.S), section


@pytest.mark.parametrize(
    "terms",
    [
        (
            "valarezo_separation_boundaries",
            "crossflow_separation_boundaries",
            "axial_separation_families",
            "26.101",
            "airfoil_separation",
        ),
        ("polar_axes", "W", "S", "B"),
        ("rotor_cn_slope", "not written"),
        ("FAM", "GRP", "P and a digit"),
        ("distinct `id`", "0 to 89", "default 0"),
    ],
)
def test_p0580_upgrade_section_names_the_changed_setup_and_product_contracts(terms):
    page = PAGE.with_name("upgrading.md").read_text(encoding="utf-8")
    section = page.split("## 0.58.0", 1)[1].split("## 0.57.0", 1)[0]
    assert all(term in section for term in terms), terms
