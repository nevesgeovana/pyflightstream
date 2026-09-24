"""PFS-2006.02: the tier-3 page states which induced-drag form each case uses.

A boundary on the vorticity induced-drag list takes its induced drag from the
vorticity it sheds, and one without a defined trailing edge reports zero there
(SRC-003 p.202); every other boundary takes it from surface pressure
integration. Which form a stored coefficient was made with is therefore part
of what the coefficient means, so the page carries a table of it and this
guard keeps the table in step with the committed golden scripts: a new golden
that puts a boundary on the list fails here until the table gains its row.

The goldens are read, not the generated sims under tests/tier3_licensed/sims,
because only the goldens are committed: a guard over an ignored directory
would pass on the machine that generated it and prove nothing anywhere else.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "tiers.md"
GOLDENS = ROOT / "tests" / "tier3_licensed" / "goldens"
HEADING = "### Which induced-drag form each case uses"
COMMAND = "SET_VORTICITY_DRAG_BOUNDARIES"


def _section() -> str:
    page = PAGE.read_text(encoding="utf-8")
    assert HEADING in page, f"docs/tiers.md carries no {HEADING!r} section"
    return page.split(HEADING, 1)[1].split("\n### ", 1)[0]


def _forms() -> dict[str, set[str]]:
    forms: dict[str, set[str]] = {}
    for script in sorted(GOLDENS.glob("*/P*.txt")):
        sim = re.match(r"P(\d{4})", script.name)
        assert sim, f"a golden script name carries no row id: {script.name}"
        for line in script.read_text(encoding="utf-8").splitlines():
            if line.startswith(COMMAND):
                forms.setdefault(sim.group(1), set()).add(line.split()[1])
    return forms


def test_every_golden_script_on_the_vorticity_list_is_disclosed_with_its_selection():
    """Each row whose golden carries the line has a table row naming its selection."""
    section = _section()
    forms = _forms()
    assert forms, "no golden script carries the line, so this guard proves nothing"
    rows = [line for line in section.splitlines() if line.startswith("|")]
    for sim, selections in sorted(forms.items()):
        row = next((line for line in rows if re.search(rf"\b{sim}\b", line)), None)
        assert row is not None, (
            f"row {sim}'s golden script emits {COMMAND} and the table on docs/tiers.md has "
            "no row for it; add one naming the selection and the geometry"
        )
        for selection in selections:
            assert f"{COMMAND} {selection}`" in row, (
                f"row {sim} emits `{COMMAND} {selection}` and its table row does not say so"
            )


def test_the_local_smi_cases_are_disclosed_with_the_form_their_builder_emits():
    """The SMI builder puts every boundary on the list, and the page says so."""
    from pyflightstream.qa.physics import build_smi_script

    source = inspect.getsource(build_smi_script)
    assert f'"{COMMAND}", -1' in source, "the SMI builder no longer emits -1; update the page"
    smi = next((line for line in _section().splitlines() if "SMI-01" in line), None)
    assert smi is not None and f"{COMMAND} -1" in smi
