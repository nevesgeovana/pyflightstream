"""Regression coverage grouped by subject."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.tier1_offline._docs_site import REQUIREMENTS_DIR as _CORE_SMALL_PARITY__REQUIREMENTS_DIR
from tests.tier1_offline.test_p0320_changelog_fragments import (
    CHANGELOG as _CORE_SMALL_CHANGELOG__CHANGELOG,
)
from tests.tier1_offline.test_p0320_changelog_fragments import (
    _checkout as _core_small_changelog___checkout,
)
from tests.tier1_offline.test_p0320_changelog_fragments import (
    _script as _core_small_changelog___script,
)


class TestCoreSmallChangelog:
    """P0400-FOLDWHOLE (PFS-2135.040): the change log fold compares whole lines, and names its page.

    A fragment bullet that was only the START of an existing bullet was judged
    already present by a substring test, skipped, and its fragment deleted; the
    migration page had the same test. A fold without ``--migration-page`` wrote
    into the 0.32.0 page whatever the release.
    """

    @staticmethod
    def test_p0400_foldwhole_a_bullet_that_prefixes_another_is_still_folded(tmp_path):
        """P0400-FOLDWHOLE: '- a fix' is folded beside '- a fix of the reader'."""
        changelog = _CORE_SMALL_CHANGELOG__CHANGELOG.replace(
            "### Owed\n", "### Fixed\n\n- a fix of the reader.\n\n### Owed\n"
        )
        repo = _core_small_changelog___checkout(tmp_path, changelog, A="## Fixed\n\n- a fix\n")
        report = _core_small_changelog___script().assemble(repo)
        assert report["changelog_entries"] == 1
        text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "- a fix of the reader.\n- a fix\n" in text

    @staticmethod
    def test_p0400_foldwhole_a_migration_block_inside_another_is_still_folded(tmp_path):
        """P0400-FOLDWHOLE: a migration sentence that is part of a longer one is appended."""
        repo = _core_small_changelog___checkout(tmp_path, A="## Migration\n\nRename the key\n")
        page = repo / "docs" / "migrating-to-0.40.0.md"
        page.parent.mkdir()
        page.write_text("# Migrating to 0.40.0\n\nRename the key twice.\n", encoding="utf-8")
        report = _core_small_changelog___script().assemble(repo, "docs/migrating-to-0.40.0.md")
        assert report["migration_entries"] == 1
        assert page.read_text(encoding="utf-8").endswith("\n\nRename the key\n")

    @staticmethod
    def test_p0400_foldwhole_a_migration_without_its_page_is_refused(tmp_path, capsys):
        """P0400-FOLDWHOLE: the command line refuses a Migration section with no page named."""
        repo = _core_small_changelog___checkout(
            tmp_path, A="## Added\n\n- x.\n\n## Migration\n\nWords.\n"
        )
        script = _core_small_changelog___script()
        assert script.main(["--repo", str(repo)]) == 2
        assert "--migration-page" in capsys.readouterr().err
        assert (repo / "changelog.d" / "A.md").exists()
        assert not (repo / "docs").exists()
        assert script.main(["--repo", str(repo), "--migration-page", "docs/m.md"]) == 0

    @staticmethod
    def test_p0400_foldwhole_srs_non_box_text_is_refused(tmp_path):
        """P0400-FOLDWHOLE: an SRS fragment cannot silently discard unindented prose."""
        spec = importlib.util.spec_from_file_location(
            "assemble_srs_p0400", Path(__file__).resolve().parents[2] / "scripts/assemble_srs.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        path = tmp_path / "fragment.md"
        path.write_text('Prose that must survive.\n\n!!! requirement "FR-999 A box"\n\n    Body.\n')
        with pytest.raises(module.FragmentError, match="non-box text"):
            module.parse_fragment(path)

    @staticmethod
    def test_p0400_foldwhole_srs_prefix_box_is_not_already_folded(tmp_path):
        """P0400-FOLDWHOLE: an existing longer requirement does not swallow a shorter box."""
        spec = importlib.util.spec_from_file_location(
            "assemble_srs_p0400", Path(__file__).resolve().parents[2] / "scripts/assemble_srs.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        box = '!!! requirement "FR-999 A box"\n\n    Body.'
        with pytest.raises(module.FragmentError, match="another text"):
            module.fold_page(box + " More text.\n", [(tmp_path / "fragment.md", [("FR-999", box)])])


_CORE_SMALL_COUNT_ROWS__REPO = Path(__file__).resolve().parents[2]


def _core_small_count_rows___load(name="count_manifest_key_rows"):
    spec = importlib.util.spec_from_file_location(
        name + "_p0400", _CORE_SMALL_COUNT_ROWS__REPO / "scripts" / (name + ".py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoreSmallCountRows:
    """P0400-COUNTROOT (PFS-2135.046): a root under a skipped folder name is still counted.

    json_files tested the skipped directory names against the ABSOLUTE path, so a
    root such as ``.../build/workspace`` yielded no file and a total of 0. The parts
    below the root are what the skip is about.
    """

    @staticmethod
    def test_p0400_countroot_a_root_inside_build_is_read(tmp_path: Path) -> None:
        """P0400-COUNTROOT: files under build/workspace are found; build/ below the root is skipped."""  # noqa: E501
        root = tmp_path / "build" / "workspace"
        (root / "post").mkdir(parents=True)
        (root / "post" / "a.json").write_text("{}", encoding="utf-8")
        (root / "build").mkdir()
        (root / "build" / "b.json").write_text("{}", encoding="utf-8")
        found = [
            path.relative_to(root).as_posix()
            for path in _core_small_count_rows___load().json_files(root)
        ]
        assert found == ["post/a.json"]

    @staticmethod
    def test_p0400_countroot_deprecated_spellings_use_only_relative_parts(
        tmp_path, monkeypatch, capsys
    ):
        """P0400-COUNTROOT: ancestor build/setups cannot suppress or reclassify a reference."""
        module = _core_small_count_rows___load("count_deprecated_spellings")
        root = tmp_path / "build" / "setups" / "workspace"
        root.mkdir(parents=True)
        reference = root / "reference.toml"
        reference.write_text("[aliases]\n", encoding="utf-8")
        assert list(module.walk(root)) == [reference]
        monkeypatch.setattr(module, "REPO", root)
        assert module.main([]) == 0
        assert "[aliases]               0 occurrence(s)" in capsys.readouterr().out
        assert module.main(["--root", str(root / "missing")]) == 1


_CORE_SMALL_GEN_GOLDENS__REPO = Path(__file__).resolve().parents[2]


class TestCoreSmallGenGoldens:
    """P0400-GOLDENSIMPORT (PFS-2135.076): gen_workflow_goldens.py imports in a fresh interpreter.

    The script put only tests/tier1_offline on sys.path and imported
    test_workflows, which imports ``tests.support_helpers``; run as its own guard
    tells a reader to run it, it ended in ``ModuleNotFoundError: No module named
    'tests'``. Run here in a child interpreter started outside the repository, so
    the pytest process's own path cannot hide the failure.
    """

    @staticmethod
    def test_p0400_goldensimport_the_script_starts_outside_pytest(tmp_path: Path) -> None:
        """P0400-GOLDENSIMPORT: ``--help`` exits 0, so every import at the top succeeded."""
        env = {**os.environ, "PYTHONPATH": str(_CORE_SMALL_GEN_GOLDENS__REPO / "src")}
        done = subprocess.run(
            [
                sys.executable,
                "-B",
                str(_CORE_SMALL_GEN_GOLDENS__REPO / "scripts" / "gen_workflow_goldens.py"),
                "--help",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert done.returncode == 0, done.stderr[-2000:]
        assert "--check" in done.stdout


_CORE_SMALL_PARITY__REPO = Path(__file__).resolve().parents[2]


_CORE_SMALL_PARITY__BASE = "SET_PROP_ACTUATOR_RPM 1 -500\n"


_CORE_SMALL_PARITY__REVERTED = "SET_PROP_ACTUATOR_RPM 1 500\n"


def _core_small_parity___load():
    spec = importlib.util.spec_from_file_location(
        "check_parity_p0400", _CORE_SMALL_PARITY__REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoreSmallParity:
    """Parity regressions, including the RV1 precision and schema cases."""

    @staticmethod
    def test_p0400_parityscope_a_revert_against_a_later_base_is_unnamed() -> None:
        """P0400-PARITYSCOPE: the FR-331 sign flip is named only against an older base."""
        module = _core_small_parity___load()
        defined = {"FR-331"}
        assert (
            module.name_difference(
                "scripts",
                "x",
                _CORE_SMALL_PARITY__BASE,
                _CORE_SMALL_PARITY__REVERTED,
                defined,
                "0.33.1",
            ).get("requirement")
            == "FR-331"
        )
        assert "requirement" not in module.name_difference(
            "scripts",
            "x",
            _CORE_SMALL_PARITY__BASE,
            _CORE_SMALL_PARITY__REVERTED,
            defined,
            "0.39.0",
        )

    @staticmethod
    def test_p0400_parityscope_a_mention_is_not_a_definition(tmp_path: Path) -> None:
        """P0400-PARITYSCOPE: an id the SRS only mentions is not defined; a box defines it."""
        srs = tmp_path / _CORE_SMALL_PARITY__REQUIREMENTS_DIR
        srs.mkdir(parents=True)
        (srs / "functional-requirements.md").write_text(
            '!!! requirement "FR-12 A box"\n\n    Text that mentions FR-331 in passing.\n',
            encoding="utf-8",
        )
        assert _core_small_parity___load().srs_ids(tmp_path) == {"FR-12"}

    @staticmethod
    @pytest.mark.parametrize("pattern", ["*/post.log", "*/post.log.json"])
    def test_p0400_parityeol_a_terminator_only_difference_is_unnamed(pattern: str) -> None:
        """P0400-PARITYEOL: a trailing newline added is not named under a lines-only entry."""
        module = _core_small_parity___load()
        name = pattern.replace("*", "m")
        defined = {named["requirement"] for named in module.NAMED_DIFFERENCES}
        old = "pyflightstream 0.39.0 post"
        entry = module.name_difference("post", name, old, old + "\n", defined)
        assert entry["state"] == "changed"
        assert "requirement" not in entry

    @staticmethod
    @pytest.mark.parametrize("tag", ["080", "0390", "01000", "123456"])
    def test_p0400_paritytag_any_digit_count_is_the_version(tag: str) -> None:
        """P0400-PARITYTAG: a report tag of three, four, five or more digits is normalised."""
        out = _core_small_parity___load().normalize(
            "m/products.json", f'{{"superfile_report": "reports/superfile-{tag}.json"}}'.encode()
        )
        assert out == b'{"superfile_report": "reports/superfile-<VERSION>.json"}'

    @staticmethod
    def test_p0400_paritytag_an_unrelated_path_is_left_alone() -> None:
        """P0400-PARITYTAG: a different folder or a non-digit tag keeps its name."""
        norm = _core_small_parity___load().normalize
        other = (
            b'{"superfile_report": "elsewhere/superfile-0390.json", '
            b'"x": "reports/superfile-a1.json"}'
        )
        assert norm("m/products.json", other) == other

    @staticmethod
    def test_p0410_par_export_includes_the_requirements_loader(tmp_path: Path) -> None:
        """P0410-PAR: exported tests can load their repository requirements helper."""
        module = _core_small_parity___load()
        tree = tmp_path / "export"
        module.export("HEAD", tree)
        assert (tree / "scripts" / "_requirements_paths.py").is_file()

    @staticmethod
    def test_p0410_par_retirements_are_scoped_to_the_module() -> None:
        """P0410-PAR: retiring a binding cannot exempt another module's same name."""
        exemptions = _core_small_parity___load().API_EXEMPT
        assert set(exemptions) == {
            "pyflightstream.cases.stamp_derived_campaign",
            "pyflightstream.farfield.rothalpy",
            "pyflightstream.farfield.irreversible_deficit",
            "pyflightstream.farfield.lattice_dataset",
            "pyflightstream.post.dataset_to_points",
            "pyflightstream.post.writers.dataset_to_points",
        }

    @staticmethod
    def test_p0410_par_only_public_module_paths_are_collected(tmp_path, monkeypatch) -> None:
        """P0410-PAR: private segments are excluded, including private parent packages."""
        module = _core_small_parity___load()
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

    @staticmethod
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

    @staticmethod
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
        module = _core_small_parity___load()
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

    @staticmethod
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
    def test_p0410_par_products_name_only_the_documented_release_change(
        path, old, new, requirement
    ):
        module = _core_small_parity___load()
        assert (
            module.name_difference("post", path, old, new, {requirement}, "0.39.0").get(
                "requirement"
            )
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

    @staticmethod
    def test_p0410_par_grouped_render_compares_one_complete_batch(tmp_path):
        """P0410-PAR: script parity is independent of cost-fit batch boundaries."""
        from tests.support_helpers import grouped_plan_fixture

        workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("1h", "1h"))
        result = _core_small_parity___load()._workspace_render(matrix, workspace.root, ["--batch"])
        assert len(result["scripts"]) == 1
        assert next(iter(result["scripts"])).startswith("BATCH-")

    @staticmethod
    @pytest.mark.parametrize(
        ("old", "new"),
        [("1", "1.4"), ("100", "100.4"), ("0", "0.1"), ("1e3", "1100")],
        ids=["P0410-RV1-integer", "P0410-RV1-count", "P0410-RV1-zero", "P0410-RV1-text"],
    )
    def test_p0410_par_literal_cells_have_no_rounding_allowance(old, new):
        """RV1-001: only the old writer's five-decimal floats lost precision."""
        module = _core_small_parity___load()
        found = module.name_difference(
            "post", "m/sections/p.csv", f"STEP\n{old}\n", f"STEP\n{new}\n", {"FR-124"}, "0.39.0"
        )
        assert "requirement" not in found

    @staticmethod
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
        found = _core_small_parity___load().name_difference(
            "post", "m/settings/m_settings.csv", old, new, {"FR-419"}, "0.39.0"
        )
        assert "requirement" not in found

    @staticmethod
    @pytest.mark.parametrize("kind", ["1", "2", "3", "4", "5", "6", "NA"])
    def test_p0410_par_settings_accepts_the_frozen_kind_codes(kind):
        """P0410-RV1: valid kind additions still pass the FR-419 exception."""
        old = "POL,f1_value,f1_prov\n1,4.00000,1\n"
        new = f"POL,f1_value,f1_prov,f1_kind\n1,4.0,1,{kind}\n"
        assert (
            _core_small_parity___load()
            .name_difference("post", "m/settings/m_settings.csv", old, new, {"FR-419"}, "0.39.0")
            .get("requirement")
            == "FR-419"
        )

    @staticmethod
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
        found = _core_small_parity___load().name_difference(
            "post", "m/settings/m_settings.csv", old, new, {"FR-419"}, "0.39.0"
        )
        assert found.get("requirement") == "FR-419", found
        assert "68755be9" in found["why"]
        assert "convergence" in found["why"]

    @staticmethod
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
        found = _core_small_parity___load().name_difference(
            "post",
            "m/settings/m_settings.csv",
            f"POL,f12_value,f12_prov\n1,{old},1\n",
            f"POL,f12_value,f12_prov,f12_kind\n1,{new},1,3\n",
            {"FR-419"},
            "0.39.0",
        )
        assert ("requirement" in found) is accepted, found


_CORE_SMALL_PROVE_EVIDENCE__REPO = Path(__file__).resolve().parents[2]


def _core_small_prove_evidence___load():
    spec = importlib.util.spec_from_file_location(
        "prove_evidence_guards_p0400",
        _CORE_SMALL_PROVE_EVIDENCE__REPO / "scripts" / "prove_evidence_guards.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoreSmallProveEvidence:
    """Retained runtime, privacy and link checks, with shared test support."""

    @staticmethod
    @pytest.mark.parametrize(
        ("returncode", "summary", "expected"),
        [
            (1, "3 passed, 1 error in 0.5s", "INCONCLUSIVE"),
            (2, "1 error in 0.5s", "INCONCLUSIVE"),
            (5, "no tests ran in 0.1s", "INCONCLUSIVE"),
            (1, "1 failed, 2 passed in 0.5s", "FAILED"),
            (0, "3 passed in 0.5s", "passed"),
        ],
    )
    def test_p0400_evidencebattery_score_reads_the_exit_code(
        returncode: int, summary: str, expected: str, monkeypatch
    ) -> None:
        """P0400-EVIDENCEBATTERY-SCORE: an error beside passes is inconclusive, not passed."""
        module = _core_small_prove_evidence___load()
        monkeypatch.setattr(
            module.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=returncode, stdout=summary, stderr=""
            ),
        )
        assert module.run("test_guard.py", "selection")[0] == expected


_CORE_SMALL_PROVE_EXTRAS__REPO = Path(__file__).resolve().parents[2]


def _core_small_prove_extras___load():
    spec = importlib.util.spec_from_file_location(
        "prove_extras_isolation_p0400",
        _CORE_SMALL_PROVE_EXTRAS__REPO / "scripts" / "prove_extras_isolation.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoreSmallProveExtras:
    """P0400-EXTRASBATTERY: scripts/prove_extras_isolation.py can pass, and leaves the tree as it was.

    P0400-EXTRASBATTERY-ANCHOR (PFS-2135.079): mutant M14 anchored on a CI install
    line that changed on 2026-09-27, so its anchor matched nothing and a full run
    always failed. Every ``patch`` anchor the battery offers is now held here to
    exactly one match in its file, which is the check the battery makes first.

    P0400-EXTRASBATTERY-EOL (PFS-2135.054): ``append`` and ``create`` wrote CRLF
    whatever the target's own line ends, and ``create`` left behind the folders it
    made. Runs are replaced by a recorder, so no pytest child is started.
    """  # noqa: E501

    @staticmethod
    def test_p0400_extrasbattery_anchor_every_patch_anchors_once(monkeypatch) -> None:
        """P0400-EXTRASBATTERY-ANCHOR: each patch anchor matches once, line ends normalised."""
        module = _core_small_prove_extras___load()
        patches: list[tuple[str, Path, str]] = []

        class Recorder:
            def __init__(self, target: str) -> None:
                self.failures: list[str] = []

            def patch(self, path, old, new, label, expect="KILLED"):
                patches.append((label, path, old))

            def append(self, *args, **kwargs):
                pass

            def create(self, *args, **kwargs):
                pass

        monkeypatch.setattr(module, "Battery", Recorder)
        monkeypatch.setattr(module, "run", lambda target: (0, "1 passed"))
        module.prove_guard_a()
        assert patches, "the battery offered no patch"
        counts = {
            label: path.read_bytes().decode("utf-8").replace("\r\n", "\n").count(old)
            for label, path, old in patches
        }
        assert {label: n for label, n in counts.items() if n != 1} == {}

    @staticmethod
    def test_p0400_extrasbattery_eol_append_keeps_lf_and_create_removes_its_folders(
        tmp_path, monkeypatch
    ) -> None:
        """P0400-EXTRASBATTERY-EOL: an LF file stays LF under append; create's folders go with it."""  # noqa: E501
        module = _core_small_prove_extras___load()
        monkeypatch.setattr(module, "REPO", tmp_path)
        monkeypatch.setattr(module, "BACKUP", tmp_path / ".backup")
        seen: dict[str, bytes] = {}
        target = tmp_path / "options.py"
        target.write_bytes(b"x = 1\n")
        created = tmp_path / "tests" / "deep" / "nest" / "zz.py"

        def run(guard: str) -> tuple[int, str]:
            seen["append"] = target.read_bytes()
            if created.exists():
                seen["create"] = created.read_bytes()
            return 1, "1 failed"

        monkeypatch.setattr(module, "run", run)
        battery = module.Battery("guard")
        battery.append(target, "\nimport pypdf\n", "N9 append")
        assert b"\r" not in seen["append"]
        assert target.read_bytes() == b"x = 1\n"
        battery.create(created, "import pypdf\n", "M99 create")
        assert seen["create"] == b"import pypdf\n"
        assert not (tmp_path / "tests").exists()


_CORE_SMALL_TRAILER_HOOK__HOOK = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_clean_room_trailer.py"
)


_CORE_SMALL_TRAILER_HOOK__TRAILERS = (
    "Clean-room: emitter specified from the official manual and probe evidence only; "
    "no code, structure or docstrings from the AGPL predecessor\n"
    "Co-Authored-By: Someone <someone@example.com>\n"
)


_CORE_SMALL_TRAILER_HOOK__VERBOSE = (
    "# Please enter the commit message for your changes.\n"
    "# ------------------------ >8 ------------------------\n"
    "# Do not modify or remove the line above.\n"
    "diff --git a/x.py b/x.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/x.py\n"
    "+++ b/x.py\n"
    "@@ -1 +1 @@\n"
    "-a = 1\n"
    "+a = 2\n"
)


def _core_small_trailer_hook___hook(tmp_path: Path, text: str) -> int:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_CORE_SMALL_TRAILER_HOOK__HOOK), str(message)],
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    ).returncode


class TestCoreSmallTrailerHook:
    """P0400-SCISSORS (PFS-2135.042): the trailer hook accepts a valid message under commit -v.

    The hook dropped every ``#`` line, the scissors line included, so the diff
    ``git commit -v`` writes below it became the message's last paragraph and git
    interpret-trailers no longer read the Clean-room trailer above it.
    """

    @staticmethod
    def test_p0400_scissors_a_valid_message_under_commit_v_passes(tmp_path: Path) -> None:
        """P0400-SCISSORS: the trailers stay the last paragraph; the diff below the cut is ignored."""  # noqa: E501
        assert (
            _core_small_trailer_hook___hook(
                tmp_path,
                f"subject\n\nbody.\n\n{_CORE_SMALL_TRAILER_HOOK__TRAILERS}\n{_CORE_SMALL_TRAILER_HOOK__VERBOSE}",
            )
            == 0
        )

    @staticmethod
    def test_p0400_scissors_a_misplaced_trailer_is_still_refused(tmp_path: Path) -> None:
        """P0400-SCISSORS: the control: a trailer followed by another paragraph is still refused."""
        assert (
            _core_small_trailer_hook___hook(
                tmp_path,
                f"subject\n\n{_CORE_SMALL_TRAILER_HOOK__TRAILERS}\nanother paragraph.\n\n{_CORE_SMALL_TRAILER_HOOK__VERBOSE}",  # noqa: E501
            )
            == 1
        )


class TestReviewR10PdfRecord:
    """REL10-001: pdf_release_record.py --repo must read that checkout's build logs.

    An offline typesetter stand-in writes distinct fresh logs in the selected
    checkout. A stale log beside the script must never enter its receipt.
    """

    @staticmethod
    @pytest.mark.requirement("NFR-46")
    @pytest.mark.parametrize("redirect", [False, True], ids=["default-repo", "selected-repo"])
    def test_pdf_receipt_reads_the_log_of_the_checkout_it_built(tmp_path, monkeypatch, redirect):
        source = Path(__file__).resolve().parents[2] / "scripts/pdf_release_record.py"
        original = tmp_path / "original"
        script = original / "scripts/pdf_release_record.py"
        script.parent.mkdir(parents=True)
        script.write_bytes(source.read_bytes())
        spec = importlib.util.spec_from_file_location("review_pdf_record", script)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        selected = tmp_path / "selected" if redirect else original
        guide = selected / "guide"
        guide.mkdir(parents=True)
        record = guide / "pdf-release-record.json"
        record.write_text(
            json.dumps({"cheatsheet_cut_approved": "existing approval"}), encoding="utf-8"
        )
        (guide / "pyflightstream_user_guide.tex").write_text("source", encoding="utf-8")
        log_relative = Path("guide/latex-sources/build/04-cheatsheet/pyfts-guide-04-cheatsheet.log")
        stale = original / log_relative
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"Output written on stale.pdf (99 pages, 1 byte).\n")
        raw = b"Output written on pyfts-guide-04-cheatsheet.pdf (10 pages, 2 bytes).\n"
        calls = []

        def git(*args):
            assert module.REPO == selected
            if args[0] in ("status", "ls-files"):
                return ""
            assert args[0] == "rev-parse"
            return ("a" if args[1] == "HEAD" else "b") * 40 + "\n"

        def build(command):
            assert module.REPO == selected
            calls.append(command)
            if command == module.CHEATSHEET_BUILD:
                target = selected / log_relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                (guide / "pyfts-guide-04-cheatsheet.pdf").write_bytes(b"fresh cheatsheet")
            else:
                assert command == module.USER_GUIDE_BUILD
                (guide / "pyflightstream_user_guide.log").write_bytes(
                    b"Output written on pyflightstream_user_guide.pdf (95 pages, 3 bytes).\n"
                )
                (guide / "pyflightstream_user_guide.pdf").write_bytes(b"fresh user guide")

        monkeypatch.setattr(module, "_git", git)
        monkeypatch.setattr(module, "_first_line", lambda *args: "offline typesetter stand-in")
        monkeypatch.setattr(module, "_run", build)
        monkeypatch.setattr(
            "sys.argv", [str(script), *(["--repo", str(selected)] if redirect else [])]
        )
        assert module.main() == 0
        assert calls == [module.CHEATSHEET_BUILD, module.USER_GUIDE_BUILD]
        receipt = json.loads(record.read_text(encoding="utf-8"))["receipts"][0]
        assert receipt["raw_build_log_sha256"] == hashlib.sha256(raw).hexdigest(), (
            "the receipt digests a log from another checkout"
        )
        assert receipt["page_count"] == 10
        assert (guide / receipt["name"]).read_bytes() == b"fresh cheatsheet"
        assert (selected / receipt["build_log"]).read_bytes() == raw
        if redirect:
            assert b"99 pages" in stale.read_bytes()
