"""P0400-PARITYSCOPE, P0400-PARITYEOL and P0400-PARITYTAG: three defects of scripts/check_parity.py.

P0400-PARITYSCOPE (PFS-2135.002): a named difference was permanent, so a
release that reverted the FR-331 actuator sign of 0.34.0 still passed PARITY
against a 0.39.0 base as "named". Each entry now carries the release that
introduced it and names a difference only against an older base; and a
requirement counts as defined only where an SRS page holds its box, not where
a page mentions it.

P0400-PARITYEOL (PFS-2135.043): a lines-only entry named a difference that
changes only a line terminator, because all() over no changed line is True.

P0400-PARITYTAG (PFS-2081.10): the products.json report-name rule matched a
release tag of exactly four digits; it now matches any digit run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.tier1_offline._docs_site import REQUIREMENTS_DIR

REPO = Path(__file__).resolve().parents[2]
BASE = "SET_PROP_ACTUATOR_RPM 1 -500\n"
REVERTED = "SET_PROP_ACTUATOR_RPM 1 500\n"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_parity_p0400", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0400_parityscope_every_entry_states_its_release() -> None:
    """P0400-PARITYSCOPE: every named entry carries ``since``, a release version."""
    module = _load()
    for named in module.NAMED_DIFFERENCES:
        assert module.release_version(named["since"]) >= (0, 33, 0), named["requirement"]


def test_p0400_parityscope_a_revert_against_a_later_base_is_unnamed() -> None:
    """P0400-PARITYSCOPE: the FR-331 sign flip is named against 0.33.1 and not against 0.39.0."""
    module = _load()
    defined = {"FR-331"}
    assert (
        module.name_difference("scripts", "x", BASE, REVERTED, defined, "0.33.1").get("requirement")
        == "FR-331"
    )
    assert "requirement" not in module.name_difference(
        "scripts", "x", BASE, REVERTED, defined, "0.39.0"
    )


def test_p0400_parityscope_a_mention_is_not_a_definition(tmp_path: Path) -> None:
    """P0400-PARITYSCOPE: an id the SRS only mentions is not defined; a box defines it."""
    srs = tmp_path / REQUIREMENTS_DIR
    srs.mkdir(parents=True)
    (srs / "functional-requirements.md").write_text(
        '!!! requirement "FR-12 A box"\n\n    Text that mentions FR-331 in passing.\n',
        encoding="utf-8",
    )
    assert _load().srs_ids(tmp_path) == {"FR-12"}


@pytest.mark.parametrize("pattern", ["*/post.log", "*/post.log.json"])
def test_p0400_parityeol_a_terminator_only_difference_is_unnamed(pattern: str) -> None:
    """P0400-PARITYEOL: a trailing newline added is not named under a lines-only entry."""
    module = _load()
    name = pattern.replace("*", "m")
    defined = {named["requirement"] for named in module.NAMED_DIFFERENCES}
    old = "pyflightstream 0.39.0 post"
    entry = module.name_difference("post", name, old, old + "\n", defined)
    assert entry["state"] == "changed"
    assert "requirement" not in entry


@pytest.mark.parametrize("tag", ["080", "0390", "01000", "123456"])
def test_p0400_paritytag_any_digit_count_is_the_version(tag: str) -> None:
    """P0400-PARITYTAG: a report tag of three, four, five or more digits is normalised."""
    out = _load().normalize(
        "m/products.json", f'{{"superfile_report": "reports/superfile-{tag}.json"}}'.encode()
    )
    assert out == b'{"superfile_report": "reports/superfile-<VERSION>.json"}'


def test_p0400_paritytag_an_unrelated_path_is_left_alone() -> None:
    """P0400-PARITYTAG: a different folder or a non-digit tag keeps its name."""
    norm = _load().normalize
    other = (
        b'{"superfile_report": "elsewhere/superfile-0390.json", "x": "reports/superfile-a1.json"}'
    )
    assert norm("m/products.json", other) == other
