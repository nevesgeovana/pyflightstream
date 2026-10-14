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
import types
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


def test_p0410_par_export_includes_the_requirements_loader(tmp_path: Path) -> None:
    """P0410-PAR: exported tests can load their repository requirements helper."""
    module = _load()
    tree = tmp_path / "export"
    module.export("HEAD", tree)
    assert (tree / "scripts" / "_requirements_paths.py").is_file()


def test_p0410_par_retirements_are_scoped_to_the_module() -> None:
    """P0410-PAR: retiring a binding cannot exempt another module's same name."""
    exemptions = _load().API_EXEMPT
    assert set(exemptions) == {
        "pyflightstream.cases.stamp_derived_campaign",
        "pyflightstream.farfield.rothalpy",
        "pyflightstream.farfield.irreversible_deficit",
        "pyflightstream.farfield.lattice_dataset",
        "pyflightstream.post.dataset_to_points",
        "pyflightstream.post.writers.dataset_to_points",
    }


def test_p0410_par_only_public_module_paths_are_collected(tmp_path, monkeypatch) -> None:
    """P0410-PAR: private segments are excluded, including private parent packages."""
    module = _load()
    root = tmp_path / "src" / "pyflightstream"
    for path in ("__init__.py", "public.py", "_private.py", "_internal/public.py"):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("__all__ = ['kept']\n", encoding="utf-8")
    imported = []

    def importing(name):
        imported.append(name)
        result = types.ModuleType(name)
        result.__all__ = ["kept"]
        return result

    monkeypatch.setattr(module.importlib, "import_module", importing)
    collected = module.collect_api(tmp_path)
    assert set(collected["exports"]) == {"pyflightstream", "pyflightstream.public"}
    assert set(imported) == set(collected["exports"])


@pytest.mark.parametrize(
    ("module_name", "name", "home"),
    [
        ("run.cli", "resolve_workflow", "cases.workflows"),
        ("run.cli", "workflow_names", "cases.workflows"),
        ("script.helpers", "one_file_key", "_digest"),
        ("script.helpers", "plain_decimal", "_decimal"),
    ],
    ids=["P0410-PAR-resolve", "P0410-PAR-workflows", "P0410-PAR-key", "P0410-PAR-decimal"],
)
def test_p0410_par_public_binding_keeps_its_object(module_name, name, home) -> None:
    module = importlib.import_module(f"pyflightstream.{module_name}")
    defining = importlib.import_module(f"pyflightstream.{home}")
    assert getattr(module, name, None) is getattr(defining, name)


@pytest.mark.parametrize(
    ("new", "accepted"),
    [
        ("POL,CL\n1,0.12345\n2,-0.00680\n", True),
        ("POL,CL\n1,0.123454\n2,-0.0068027\n", True),
        ("POL,CL\n1,0.12346\n2,-0.00680\n", False),
        ("POL,CL\n1,0.12345\n", False),
        ("POL,CL\n1,0.12345\n2,-0.00680\n3,0.5\n", False),
        ("CL,POL\n0.12345,1\n-0.00680,2\n", False),
        ("POL,CL,unknown\n1,0.12345,0\n2,-0.00680,0\n", False),
        ("POL,CL\n1,nan\n2,-0.00680\n", False),
        ("POL,CL\n1,inf\n2,-0.00680\n", False),
        ("POL,CL\n1,word\n2,-0.00680\n", False),
        ("POL,CL\n1,0.12345,0\n2,-0.00680\n", False),
        ("POL,f12_kind,CL\n1,0,0.12345\n2,1,-0.00680\n", False),
    ],
    ids=[
        "P0410-PAR-exact",
        "P0410-PAR-rounding",
        "P0410-PAR-regression",
        "P0410-PAR-dropped-row",
        "P0410-PAR-added-row",
        "P0410-PAR-reordered",
        "P0410-PAR-unknown-column",
        "P0410-PAR-nan",
        "P0410-PAR-inf",
        "P0410-PAR-text",
        "P0410-PAR-width",
        "P0410-PAR-unrelated-kind-column",
    ],
)
def test_p0410_par_csv_rounding_is_bounded(new, accepted, monkeypatch) -> None:
    """FR-124: naming a respelling cannot hide a changed value, row or column."""
    module = _load()
    monkeypatch.setattr(
        module,
        "NAMED_DIFFERENCES",
        [
            {
                "kind": "post",
                "pattern": "*.csv",
                "since": "0.40.0",
                "requirement": "FR-124",
                "why": "writer precision",
                "csv_rounding": "base",
                "csv_inserted_columns": r"f\d+_kind",
            }
        ],
    )
    old = "POL,CL\n1,0.12345\n2,-0.00680\n"
    found = module.name_difference("post", "table.csv", old, new, {"FR-124"}, "0.39.0")
    assert ("requirement" in found) is accepted


@pytest.mark.parametrize(
    ("path", "old", "new", "requirement"),
    [
        ("m/polars/p.csv", "POL,CL\n1,0.12345\n", "POL,CL\n1,0.123454\n", "FR-124"),
        ("m/sections/p.csv", "POL,CP\n1,0.00380\n", "POL,CP\n1,0.003802\n", "FR-124"),
        (
            "m/settings/m_settings.csv",
            "POL,f1_value,f1_prov\n1,4.00000,1\n",
            "POL,f1_value,f1_prov,f1_kind\n1,4.0,1,3\n",
            "FR-419",
        ),
    ],
    ids=["P0410-PAR-polars", "P0410-PAR-sections", "P0410-PAR-settings"],
)
def test_p0410_par_products_name_only_the_documented_release_change(path, old, new, requirement):
    module = _load()
    assert (
        module.name_difference("post", path, old, new, {requirement}, "0.39.0").get("requirement")
        == requirement
    )
    assert "requirement" not in module.name_difference("post", path, old, new, set(), "0.39.0")
    assert "requirement" not in module.name_difference(
        "post", path, old, new, {requirement}, "0.40.0"
    )
    if requirement == "FR-419":
        assert "requirement" not in module.name_difference(
            "post", path, old, new.replace("4.0", "4.00001"), {requirement}, "0.39.0"
        )


def test_p0410_par_grouped_render_compares_one_complete_batch(tmp_path):
    """P0410-PAR: script parity is independent of cost-fit batch boundaries."""
    from tests.support_helpers import grouped_plan_fixture

    workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("1h", "1h"))
    result = _load()._workspace_render(matrix, workspace.root, ["--batch"])
    assert len(result["scripts"]) == 1
    assert next(iter(result["scripts"])).startswith("BATCH-")


@pytest.mark.parametrize(
    ("old", "new"),
    [("1", "1.4"), ("100", "100.4"), ("0", "0.1"), ("1e3", "1100")],
    ids=["P0410-RV1-integer", "P0410-RV1-count", "P0410-RV1-zero", "P0410-RV1-text"],
)
def test_p0410_par_literal_cells_have_no_rounding_allowance(old, new):
    """RV1-001: only the old writer's five-decimal floats lost precision."""
    module = _load()
    found = module.name_difference(
        "post", "m/sections/p.csv", f"STEP\n{old}\n", f"STEP\n{new}\n", {"FR-124"}, "0.39.0"
    )
    assert "requirement" not in found


@pytest.mark.parametrize(
    "new",
    [
        "POL,f1_value,f1_prov,f1_kind\n1,4.0,1,garbage\n",
        "POL,f1_value,f1_prov,f1_kind\n1,4.0,1,7\n",
        "POL,f1_value,f1_prov,f999_kind\n1,4.0,1,3\n",
        "POL,f1_value,f1_prov\n1,4.0,1\n",
    ],
    ids=["P0410-RV1-text-kind", "P0410-RV1-kind-code", "P0410-RV1-flag", "P0410-RV1-no-kind"],
)
def test_p0410_par_settings_kind_additions_are_validated(new):
    """RV1-002: naming new kind columns does not excuse a malformed settings table."""
    old = "POL,f1_value,f1_prov\n1,4.00000,1\n"
    found = _load().name_difference(
        "post", "m/settings/m_settings.csv", old, new, {"FR-419"}, "0.39.0"
    )
    assert "requirement" not in found


@pytest.mark.parametrize("kind", ["1", "2", "3", "4", "5", "6", "NA"])
def test_p0410_par_settings_accepts_the_frozen_kind_codes(kind):
    """P0410-RV1: valid kind additions still pass the FR-419 exception."""
    old = "POL,f1_value,f1_prov\n1,4.00000,1\n"
    new = f"POL,f1_value,f1_prov,f1_kind\n1,4.0,1,{kind}\n"
    assert (
        _load()
        .name_difference("post", "m/settings/m_settings.csv", old, new, {"FR-419"}, "0.39.0")
        .get("requirement")
        == "FR-419"
    )


def test_p0410_rv1_the_documented_settings_precision_change_is_named(tmp_path):
    """RV1-003: convergence 1e-6 was printed as zero before 68755be9."""
    import csv

    from pyflightstream.post.settings_table import write_settings_table
    from pyflightstream.script import Script, helpers

    setup = helpers.solver_settings(Script(version="26.120"), convergence=1e-6)
    table, _ = write_settings_table(tmp_path / "settings.csv", [setup], wide=True)
    with table.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["f12_value"] == "1e-06"
    assert row["f12_kind"] == "3"
    old = "POL,f12_value,f12_prov\n1,0.00000,1\n"
    new = "POL,f12_value,f12_prov,f12_kind\n1,1e-06,1,3\n"
    found = _load().name_difference(
        "post", "m/settings/m_settings.csv", old, new, {"FR-419"}, "0.39.0"
    )
    assert found.get("requirement") == "FR-419", found
    assert "68755be9" in found["why"]
    assert "convergence" in found["why"]


@pytest.mark.parametrize(
    ("old", "new", "accepted"),
    [
        ("0.00000", "1e-06", True),
        ("0.00001", "2e-05", False),
        ("0.12346", "0.1235", True),
        ("0.12344", "0.1235", False),
        ("0.00001", "0.000015", False),
        ("0.00002", "0.000015", True),
        ("-0.00000", "-1e-06", True),
        ("1", "1.4", False),
        ("100", "100.4", False),
        ("0", "0.1", False),
        ("1e3", "1100", False),
        ("NA", "0.0", False),
        ("word", "other", False),
        ("0.00000", "NaN", False),
        ("0.00000", "Infinity", False),
        ("0.00000", "0_0", False),
    ],
)
def test_p0410_rv1_settings_compare_at_the_coarser_printed_precision(old, new, accepted):
    """RV1-003: both cells round alike; RV1-001 literals remain exact."""
    found = _load().name_difference(
        "post",
        "m/settings/m_settings.csv",
        f"POL,f12_value,f12_prov\n1,{old},1\n",
        f"POL,f12_value,f12_prov,f12_kind\n1,{new},1,3\n",
        {"FR-419"},
        "0.39.0",
    )
    assert ("requirement" in found) is accepted, found
