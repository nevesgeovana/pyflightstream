"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import builtins
import json
import shutil
import warnings
from importlib.util import resolve_name
from pathlib import Path

import pytest
import yaml
from scripts.build_command_coverage import (
    BUILD,
    CHAPTERS,
    ROOT,
    STEM,
    _emissions,
    build_coverage,
    render_markdown,
)

import pyflightstream
import pyflightstream.farfield as ff
import tests.tier1_offline.test_conventions as _every_root_module_ranked__conv
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import _geometry_build as build
from tests.tier1_offline.test_goal028_module_level_layering import (
    _upward_module_level_imports as _every_root_module_ranked___upward_module_level_imports,
)
from tests.tier1_offline.test_house_style import (
    RECORDED_WAKE_FIXTURES as _RFIXA_GUARDS__RECORDED_WAKE_FIXTURES,
)
from tests.tier1_offline.test_house_style import (
    _geometry_offenses as _rfixa_guards___geometry_offenses,
)

_DECIDED_DOCS_1_EXAMPLES__EXAMPLES = Path(__file__).resolve().parents[2] / "docs/examples/_sources"


#: Private imports still owed a public home: the entry point decorator has no
#: public module yet.
_DECIDED_DOCS_1_EXAMPLES__OWED: set[tuple[str, str, str]] = set()


def _decided_docs_1_examples___private_imports() -> set[tuple[str, str, str]]:
    """Return (example, module, name) for every import of a private module or name."""
    found = set()
    for path in sorted(_DECIDED_DOCS_1_EXAMPLES__EXAMPLES.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module != "__future__":
                private_module = any(part.startswith("_") for part in node.module.split("."))
                for alias in node.names:
                    if private_module or alias.name.startswith("_"):
                        found.add((path.name, node.module, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(part.startswith("_") for part in alias.name.split(".")):
                        found.add((path.name, alias.name, ""))
    return found


class TestDecidedDocs1Examples:
    """Tier 1: the shipped examples import public names only (P0400-EXAMPLE-PUBLIC, PFS-2098.001).

    Pipeline role: quality gate on ``examples/``. An example is what a user
    copies, so a private name it imports becomes the user's dependency on
    something the package may rename without notice. The set below records the
    imports still owed a public home: it may only shrink, and a new private
    import in any example fails here.
    """

    @staticmethod
    def test_p0400_example_public_no_example_imports_a_private_name():
        """P0400-EXAMPLE-PUBLIC: every private import of an example is one owed above, no other."""
        assert _decided_docs_1_examples___private_imports() == _DECIDED_DOCS_1_EXAMPLES__OWED


def _every_root_module_ranked___tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "pyflightstream"
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _every_root_module_ranked___findings(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Everything the real guards say about the planted tree: unranked units and upward imports."""
    monkeypatch.setattr(_every_root_module_ranked__conv, "_SRC", root)
    out = [
        f"unranked {name}" for name in _every_root_module_ranked__conv._unranked_root_units(root)
    ]
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        dotted = ("pyflightstream." + rel).removesuffix(".__init__")
        source = path.read_text(encoding="utf-8")
        out += [
            f"{rel} module-level {t}"
            for t in _every_root_module_ranked___upward_module_level_imports(
                dotted, source, is_package=path.name == "__init__.py"
            )
        ]
        out += [
            f"{rel} deferred {o}"
            for o in _every_root_module_ranked__conv._upward_function_body_imports(path)
        ]
    return out


_EVERY_ROOT_MODULE_RANKED___CLEAN = {
    "__init__.py": "",
    "post/__init__.py": "",
    "run/__init__.py": "",
    "commands/__init__.py": "",
    "_errors.py": "",
    "_cli.py": "from pyflightstream import _errors\n",
    "utils/__init__.py": "from pyflightstream import commands\nfrom pyflightstream import _cli\n",
    "exceptions.py": "from pyflightstream import post, run\n",
}


class TestEveryRootModuleRanked:
    """PFS-2083.002: every root module has a layer, the guards check all of them, and a planted
    upward import through a root module is refused.

    The rows live in `test_conventions._ROOT_UNIT_ROWS`. These tests plant a package
    tree in `tmp_path` (never the real one) and run the real guards on it: the
    unranked-unit guard, the module-level scanner and the function-body scanner.
    """

    @staticmethod
    def test_the_planted_clean_tree_is_the_control(tmp_path, monkeypatch):
        """Downward edges and an exceptions catalog nobody imports: nothing is reported."""
        assert (
            _every_root_module_ranked___findings(
                _every_root_module_ranked___tree(tmp_path, _EVERY_ROOT_MODULE_RANKED___CLEAN),
                monkeypatch,
            )
            == []
        )

    @staticmethod
    @pytest.mark.parametrize(
        ("name", "text", "expected"),
        [
            (
                "_cli.py",
                "from pyflightstream.post import x\n",
                "_cli module-level pyflightstream.post",
            ),
            (
                "_cli.py",
                "def f():\n    from pyflightstream.run import x\n",
                "_cli deferred",
            ),
            (
                "extras.py",
                "from pyflightstream.exceptions import SomeError\n",
                "extras module-level pyflightstream.exceptions",
            ),
            (
                "utils/tool.py",
                "from pyflightstream.fsi import beam\n",
                "utils.tool module-level pyflightstream.fsi",
            ),
            (
                "options.py",
                "import pyflightstream.utils\n",
                "options module-level pyflightstream.utils",
            ),
        ],
    )
    def test_a_planted_upward_import_through_a_root_module_is_refused(
        tmp_path, monkeypatch, name, text, expected
    ):
        files = {
            **_EVERY_ROOT_MODULE_RANKED___CLEAN,
            "fsi/__init__.py": "",
            "fsi/beam.py": "",
            "extras.py": "",
            "options.py": "",
        }
        files[name] = text
        found = _every_root_module_ranked___findings(
            _every_root_module_ranked___tree(tmp_path, files), monkeypatch
        )
        assert any(f.startswith(expected) for f in found), found

    @staticmethod
    def test_a_planted_unranked_root_module_is_refused(tmp_path, monkeypatch):
        files = {**_EVERY_ROOT_MODULE_RANKED___CLEAN, "_brand_new.py": "", "newpkg/__init__.py": ""}
        found = _every_root_module_ranked___findings(
            _every_root_module_ranked___tree(tmp_path, files), monkeypatch
        )
        assert "unranked _brand_new" in found and "unranked newpkg" in found

    @staticmethod
    def test_a_root_module_with_a_row_is_not_reported_unranked(tmp_path, monkeypatch):
        """Control for the test above: a ranked unit and the named exception are not refused."""
        assert (
            _every_root_module_ranked___findings(
                _every_root_module_ranked___tree(tmp_path, _EVERY_ROOT_MODULE_RANKED___CLEAN),
                monkeypatch,
            )
            == []
        )
        assert (
            _every_root_module_ranked__conv._unranked_root_units(
                _every_root_module_ranked___tree(
                    tmp_path / "again", _EVERY_ROOT_MODULE_RANKED___CLEAN
                ),
                {"post": 0},
            )
            != []
        )

    @staticmethod
    def test_the_real_tree_has_no_unranked_unit_and_the_named_list_has_one_entry():
        assert (
            _every_root_module_ranked__conv._unranked_root_units(
                _every_root_module_ranked__conv._SRC
            )
            == []
        )
        assert list(_every_root_module_ranked__conv._NAMED_UNRANKED_ROOT_UNITS) == ["__init__"]

    @staticmethod
    def test_the_exceptions_catalog_is_imported_by_no_module_of_the_package():
        """It ranks at the top and imports every layer; that is safe only while nobody imports it."""  # noqa: E501
        importers = []
        for path in sorted(_every_root_module_ranked__conv._SRC.rglob("*.py")):
            if path.name == "exceptions.py" and path.parent == _every_root_module_ranked__conv._SRC:
                continue
            rel = path.relative_to(_every_root_module_ranked__conv._SRC).with_suffix("")
            package = ".".join(["pyflightstream", *rel.parts[:-1]])
            if (
                "pyflightstream.exceptions"
                in _every_root_module_ranked__conv._imported_module_names(
                    path.read_text(encoding="utf-8"), package
                )
            ):
                importers.append(rel.as_posix())
        assert importers == []


_FARFIELD_CORE__REPO = Path(__file__).resolve().parents[2]


_FARFIELD_CORE__CORE = _FARFIELD_CORE__REPO / "src" / "pyflightstream" / "farfield"


#: The packages the core may not import (FR-450 R2), including xarray.
_FARFIELD_CORE__FORBIDDEN_PACKAGES = (
    "pyflightstream.results",
    "pyflightstream.cases",
    "pyflightstream.workspace",
    "pyflightstream.run",
    "pyflightstream.post",
    "pyflightstream.script",
    "xarray",
)


#: Calls that reach a file or the environment.
_FARFIELD_CORE__FORBIDDEN_CALLS = {
    "open",
    "read_text",
    "write_text",
    "read_bytes",
    "write_bytes",
    "getenv",
}


_FARFIELD_CORE__FORBIDDEN_ATTRIBUTES = {"environ"}


_FARFIELD_CORE__ARRAY_FILE_APIS = {
    "numpy.load",
    "numpy.loadtxt",
    "numpy.genfromtxt",
    "numpy.fromfile",
    "numpy.memmap",
    "numpy.save",
    "numpy.savez",
    "numpy.savez_compressed",
    "numpy.savetxt",
}


def _farfield_core___imported_module(node: ast.ImportFrom, name: str) -> str:
    """Resolve relative imports from a path relative to the farfield package."""
    package = "pyflightstream.farfield"
    parents = Path(name).with_suffix("").parts[:-1]
    if parents:
        package += "." + ".".join(parents)
    target = "." * node.level + (node.module or "")
    return resolve_name(target, package) if node.level else target


def _farfield_core___call_name(node: ast.expr, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _farfield_core___call_name(node.value, aliases) + "." + node.attr
    return ""


def _farfield_core__core_problems(source: str, name: str) -> list[str]:
    """Check static imports and direct calls, including imported API aliases.

    Dynamic imports, runtime rebinding, getattr and wrappers are not proved by
    this bounded AST guard; ``name`` is relative to the farfield package.
    """
    problems: list[str] = []
    nodes = list(ast.walk(ast.parse(source)))
    aliases: dict[str, str] = {}
    for node in nodes:
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            module = _farfield_core___imported_module(node, name)
            modules = [module, *(module + "." + alias.name for alias in node.names)]
            for alias in node.names:
                aliases[alias.asname or alias.name] = module + "." + alias.name
        for module in modules:
            if any(
                module == p or module.startswith(p + ".")
                for p in _FARFIELD_CORE__FORBIDDEN_PACKAGES
            ):
                problems.append(f"{name} imports {module}")
    for node in nodes:
        if isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if (
                called in _FARFIELD_CORE__FORBIDDEN_CALLS
                or _farfield_core___call_name(func, aliases) in _FARFIELD_CORE__ARRAY_FILE_APIS
            ):
                problems.append(f"{name} calls {called}")
        if isinstance(node, ast.Attribute) and node.attr in _FARFIELD_CORE__FORBIDDEN_ATTRIBUTES:
            problems.append(f"{name} reads {node.attr}")
    return problems


class TestFarfieldCore:
    """P0400-FFAMILY (FR-450): one far-field home, a numpy core with no input or output.

    The guard reads every module of ``pyflightstream.farfield`` with ``ast`` and
    refuses an import of a layer above the core or of xarray, and any call that
    opens, reads or writes a file or reads the environment (FR-450 R2). Its
    controls plant each forbidden shape in a copy and show the guard refuses it.
    """

    @staticmethod
    @pytest.mark.requirement("FR-450")
    def test_p0400_ffamily_the_core_has_no_input_or_output_and_imports_no_upper_layer():
        """P0400-FFAMILY (FR-450 R2): every module of the far-field core, read with ast."""
        modules = sorted(_FARFIELD_CORE__CORE.rglob("*.py"))
        assert {path.stem for path in modules} >= {
            "__init__",
            "fields",
            "quadrature",
            "balances",
            "trefftz",
        }
        problems = [
            problem
            for path in modules
            for problem in _farfield_core__core_problems(
                path.read_text(encoding="utf-8"), path.relative_to(_FARFIELD_CORE__CORE).as_posix()
            )
        ]
        assert not problems, problems

    @staticmethod
    @pytest.mark.requirement("FR-450")
    @pytest.mark.parametrize(
        "planted",
        [
            "from pyflightstream.results.wake import parse_wake_export\n",
            "import pyflightstream.post.axes\n",
            "from pyflightstream.cases import SimCase\n",
            "import xarray as xr\n",
            "text = open('x').read()\n",
            "from pathlib import Path\nPath('x').read_text()\n",
            "import os\nos.environ['A']\n",
        ],
    )
    def test_p0400_ffamily_the_guard_refuses_each_forbidden_shape(planted):
        """P0400-FFAMILY (FR-450 R2): the control, a planted line in a copy of the core."""
        source = (_FARFIELD_CORE__CORE / "trefftz.py").read_text(encoding="utf-8") + "\n" + planted
        assert _farfield_core__core_problems(source, "trefftz.py")

    @staticmethod
    @pytest.mark.requirement("FR-450")
    def test_p0400_ffamily_the_facade_exports_every_analysis_from_one_home():
        """P0400-FFAMILY (FR-450 R1, R4; FR-459 R6): the root is a facade over the core."""
        for name in ff.__all__:
            value = getattr(ff, name)
            home = getattr(value, "__module__", "pyflightstream.farfield.trefftz")
            assert home.startswith("pyflightstream.farfield."), (name, home)
        tree = ast.parse((_FARFIELD_CORE__CORE / "__init__.py").read_text(encoding="utf-8"))
        defined = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        assert defined == ["__getattr__"], "the far-field root defines no analysis of its own"
        for name in (
            "trace_forces",
            "wake_crossings",
            "plane_induced_drag",
            "plane_vorticity_drag",
            "bernoulli_residual",
            "rotor_channels",
            "mass_closure",
            "crossflow_kinetic_energy",
        ):
            assert name in ff.__all__, name


def _g67_command_coverage___assert_twins(root: Path, report: dict) -> None:
    expected = {
        ".json": json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        ".md": render_markdown(report),
    }
    for suffix, regenerated in expected.items():
        path = root / "reports" / (STEM + suffix)
        assert path.read_text("utf-8") == regenerated, f"coverage twin differs: {path.name}"


class TestG67CommandCoverage:
    """Retained runtime, privacy and link checks, with shared test support."""

    @staticmethod
    def test_p0400_g67_every_command_has_one_column_and_twins_regenerate():
        """P0400-G67 (FR-151, FR-152): every setup/BC command has a route or a reason."""
        report = build_coverage()
        assert report["rows"]
        assert {row["chapter"] for row in report["rows"]} == set(CHAPTERS)
        assert len({row["command"] for row in report["rows"]}) == len(report["rows"])
        for row in report["rows"]:
            assert bool(row["reachable"]) != bool(row["not_offered"]), row
            assert row["evidence"], row
            if row["reachable"]:
                assert row["build_status"] in {"documented", "verified"}, row
            for evidence in row["evidence"]:
                assert (ROOT / evidence.split(":", 1)[0]).is_file(), evidence
        assert sum(report["counts"].values()) == len(report["rows"])
        _g67_command_coverage___assert_twins(ROOT, report)

    @staticmethod
    @pytest.fixture
    def copied_database(tmp_path: Path) -> Path:
        """Copy the database for mutation controls; no real command entry is touched."""
        return Path(shutil.copytree(ROOT / "src/pyflightstream/commands", tmp_path / "commands"))

    @staticmethod
    @pytest.mark.parametrize(
        "chapter", ["solver_settings", "advanced_settings", "boundary_conditions"]
    )
    @pytest.mark.parametrize("status", ["documented", "verified"])
    def test_p0400_g67_fake_supported_command_fails_the_partition(
        copied_database: Path, chapter: str, status: str
    ):
        """P0400-G67 control: a new supported command in either family fails the rebuild."""
        path = copied_database / f"{chapter}.yaml"
        entries = yaml.safe_load(path.read_text("utf-8"))
        command = "G67_FAKE_UNCOVERED_COMMAND"
        entries[command] = {
            "layout": "bare",
            "phase": "setup",
            "args": [],
            "manual_ref": "SRC-753 p.353",
            "versions": {
                BUILD: {
                    "status": status,
                    **(
                        {"report": "reports/compat/CMP-26125_2026-10-05_probe-campaign.yaml"}
                        if status == "verified"
                        else {}
                    ),
                }
            },
        }
        path.write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")
        with pytest.raises(ValueError, match=f"{command}: command in neither"):
            build_coverage(database=copied_database)
        assert command not in (ROOT / "src/pyflightstream/commands" / path.name).read_text("utf-8")

    @staticmethod
    @pytest.mark.parametrize("suffix", [".json", ".md"])
    def test_p0400_g67_stale_table_fails(tmp_path: Path, suffix: str):
        """P0400-G67 control: changing either filed representation is detected."""
        report = build_coverage()
        shutil.copytree(
            ROOT / "reports",
            tmp_path / "reports",
            ignore=lambda _, names: [name for name in names if not name.startswith(STEM)],
        )
        path = tmp_path / "reports" / (STEM + suffix)
        path.write_text(path.read_text("utf-8") + "stale coverage\n", encoding="utf-8")
        with pytest.raises(AssertionError, match="coverage twin differs"):
            _g67_command_coverage___assert_twins(tmp_path, report)

    @staticmethod
    def test_p0400_g67_emission_census_ignores_lookups_and_prose(tmp_path: Path):
        """P0400-G67 control: an entry lookup or a docstring cannot prove emission."""
        source = tmp_path / "src/pyflightstream/cases"
        source.mkdir(parents=True)
        path = source / "synthetic.py"
        command = "G67_SYNTHETIC_COMMAND"
        path.write_text(
            f'def route(script):\n    """{command}"""\n    script.entry("{command}")\n',
            encoding="utf-8",
        )
        assert _emissions(tmp_path, {command}) == {}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f'    script.emit("{command}")\n')
        assert command in _emissions(tmp_path, {command})

    @staticmethod
    def test_p0400_g67_lost_emitter_table_row_fails(tmp_path: Path):
        """P0400-G67 control: a live key/register without its actual emitter row fails."""
        copied_root = tmp_path / "repo"
        shutil.copytree(ROOT / "src/pyflightstream", copied_root / "src/pyflightstream")
        path = copied_root / "src/pyflightstream/script/_settings.py"
        text = path.read_text("utf-8")
        old = 'Row("convergence", "SOLVER_SET_CONVERGENCE")'
        assert old in text
        path.write_text(
            text.replace(old, 'Row("convergence", "G67_REMOVED_ROUTE")'), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="SOLVER_SET_CONVERGENCE:.*no executable emission"):
            build_coverage(root=copied_root)

    @staticmethod
    def test_p0400_g67_scope_matches_the_existing_database_chapter_register():
        """The existing setup/BC register supplies categories, with the 26.125 addition."""
        path = ROOT / "tests/tier1_offline/test_goal034_setup_operational_commands.py"
        for statement in ast.parse(path.read_text("utf-8")).body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SETUP_CHAPTERS" for t in statement.targets
            ):
                assert set(CHAPTERS) == set(ast.literal_eval(statement.value)) | {"free_surfaces"}
                break
        else:
            pytest.fail("the setup/BC chapter register is missing")


class TestLarch001ParallelFloor:
    """LARCH-001 (0.40.0 architect lens): without psutil the geometry build runs serially, saying why.

    psutil is not a dependency of the package. Before the fix the memory check
    answered True when it could not measure, so ``--parallel 2`` started a second solver
    run on an unmeasured machine.
    """  # noqa: E501

    @staticmethod
    def test_larch001_an_unmeasurable_memory_floor_runs_the_builds_serially(
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """P0400-LARCH001 (NFR-06): absent psutil refuses parallel work and warns."""
        real_import = builtins.__import__

        def no_psutil(name: str, *args: object, **kwargs: object) -> object:
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", no_psutil)
        with pytest.warns(PyflightstreamWarning, match="psutil"):
            assert build._room_for_a_second_run() is False


_PRIVATE_IMPORT_RATCHET___SRC = Path(pyflightstream.__file__).parent


_PRIVATE_IMPORT_RATCHET___FROZEN: tuple[tuple[str, str], ...] = (
    ("cases.windows", "script._surface_averaging"),
    ("cases.workflows._exports", "script._surface_averaging"),
    ("cases.workflows._skeleton", "script._settings"),
    ("post.farfield_fields", "cases._farfield_spec"),
    ("post.farfield_products", "cases._farfield_spec"),
    ("qa.matrix", "workspace._matrix_homes"),
    ("run._assemble", "workspace._batch_life"),
    ("run._batch_collect", "cases.workflows._batch_script"),
    ("run._batch_collect", "workspace._batch_relocate"),
    ("run._batch_collect", "workspace._batches"),
    ("run._batch_collect", "workspace._missing_log"),
    ("run._batch_exec", "workspace._batches"),
    ("run._batch_plan", "cases._unsteady_actions"),
    ("run._batch_plan", "cases.workflows._batch_actions"),
    ("run._batch_plan", "cases.workflows._batch_script"),
    ("run._batch_plan", "cases.workflows._rows"),
    ("run._batch_plan", "workspace._batches"),
    ("run._batch_plan", "workspace._geometry_clean"),
    ("run._batch_run", "cases._unsteady_actions"),
    ("run._batch_run", "cases.workflows._batch_actions"),
    ("run._batch_run", "cases.workflows._batch_script"),
    ("run._batch_run", "workspace._batches"),
    ("run._campaign", "workspace._settings_file"),
    ("run._cli_geometry", "workspace._geometry_build"),
    ("run._cli_geometry", "workspace._geometry_convert"),
    ("run._cli_mesh", "cases.workflows._vocabulary"),
    ("run._cli_mesh", "workspace._geometry_clean"),
    ("run._collect_logs", "workspace._batches"),
    ("run._grouped", "workspace._batches"),
    ("run._identity", "workspace._settings_file"),
    ("run._mark_converged", "workspace._verdicts"),
    ("run._plan", "cases._skipped_families"),
    ("run._plan", "cases.workflows._farfield"),
    ("run._plan", "cases.workflows._freestream"),
    ("run._plan", "workspace._batches"),
    ("run._plan", "workspace._settings_file"),
    ("run._points", "cases._skipped_families"),
    ("run._rebuild", "workspace._matrix_homes"),
    ("run._rebuild_evidence", "workspace._batches"),
    ("run._rebuild_evidence", "workspace._matrix_homes"),
    ("run._rebuild_evidence", "workspace._script_comparison"),
    ("run._rebuild_grouped", "workspace._batches"),
    ("run._sweep", "cases._skipped_families"),
    ("run._wake_edge_verdict", "workspace._missing_log"),
    ("run.cli", "workspace._matrix_homes"),
    ("run.collect", "workspace._batches"),
    ("run.collect", "workspace._missing_log"),
    ("run.matrix", "workspace._geometry_clean"),
    ("run.matrix", "workspace._matrix_homes"),
    ("workspace", "script._surface_averaging"),
    ("workspace._geometry_build", "cases._geometry_emit"),
    ("workspace._geometry_build", "cases._geometry_instruction"),
    ("workspace._geometry_convert", "cases._ccs"),
    ("workspace._geometry_convert", "cases._geometry_instruction"),
    ("workspace._geometry_instruction", "cases._ccs"),
    ("workspace._geometry_instruction", "cases._geometry_instruction"),
    ("workspace._geometry_record", "cases._ccs"),
    ("workspace._geometry_record", "cases._geometry_instruction"),
    ("workspace._row_setup", "cases.workflows._freestream"),
    ("workspace.manifest", "script._surface_averaging"),
    ("workspace.sidecars", "cases._ccs"),
    ("workspace.sidecars", "cases._geometry_instruction"),
    ("workspace.sidecars", "cases.workflows._vocabulary"),
)


def _private_import_ratchet___module_exists(root: Path, dotted: str) -> bool:
    parts = dotted.split(".")
    if parts[0] != "pyflightstream" or len(parts) < 2:
        return False
    target = root.joinpath(*parts[1:])
    return target.with_suffix(".py").is_file() or (target / "__init__.py").is_file()


def _private_import_ratchet__measure_private_cross_package_imports(
    root: Path,
) -> set[tuple[str, str]]:
    """Every (importer, imported) private cross-package module pair under ``root``."""
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if len(parts) < 2 and parts[-1] == "__init__":
            continue
        unit = parts[0]
        if not (root / unit).is_dir():
            continue  # a root-level module is not inside a package
        importer = ".".join(["pyflightstream", *[p for p in parts if p != "__init__"]])
        package = ["pyflightstream", *parts[:-1]]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base_parts = package[: len(package) - node.level + 1]
                    base = ".".join([*base_parts, *([node.module] if node.module else [])])
                else:
                    base = node.module or ""
                if base:
                    candidates = [base, *[f"{base}.{alias.name}" for alias in node.names]]
            for name in candidates:
                pieces = name.split(".")
                if len(pieces) < 3 or pieces[0] != "pyflightstream":
                    continue
                if pieces[1] == unit or not (root / pieces[1]).is_dir():
                    continue
                if not any(p.startswith("_") for p in pieces[2:]):
                    continue
                if _private_import_ratchet___module_exists(root, name):
                    found.add(
                        (
                            importer.removeprefix("pyflightstream."),
                            name.removeprefix("pyflightstream."),
                        )
                    )
    return found


def _private_import_ratchet__ratchet_verdict(
    measured: set[tuple[str, str]], frozen: set[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(new, gone): pairs measured but not frozen, and pairs frozen but no longer measured."""
    return sorted(measured - frozen), sorted(frozen - measured)


def _private_import_ratchet___plant(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "pyflightstream"
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


_PRIVATE_IMPORT_RATCHET___BASE_TREE = {
    "__init__.py": "",
    "run/__init__.py": "",
    "run/a.py": "",
    "workspace/__init__.py": "",
    "workspace/_priv.py": "VALUE = 1\n",
    "workspace/public.py": "",
}


class TestPrivateImportRatchet:
    """Retained runtime, privacy and link checks, with shared test support."""

    @staticmethod
    @pytest.mark.requirement("NFR-23")
    def test_private_cross_package_imports_are_frozen_and_shrink_only():
        """P0400-PRIVATEIMPORT: a new pair fails; a removed pair asks for the list to shrink."""
        measured = _private_import_ratchet__measure_private_cross_package_imports(
            _PRIVATE_IMPORT_RATCHET___SRC
        )
        # Non-vacuity: the three families the decision names are read.
        assert measured, "the import walk found no pairs"
        frozen = set(_PRIVATE_IMPORT_RATCHET___FROZEN)
        assert len(frozen) == len(_PRIVATE_IMPORT_RATCHET___FROZEN), "a pair is listed twice"
        new, gone = _private_import_ratchet__ratchet_verdict(measured, frozen)
        assert not new, (
            "NEW private cross-package imports (a package importing another package's private "
            "module); move the shared code to a public home or a module below both, do not add "
            f"to the list: {new}"
        )
        if gone:
            warnings.warn(
                f"P0400-PRIVATEIMPORT: these listed imports no longer exist, remove them from "
                f"_FROZEN so the freeze shrinks: {gone}",
                stacklevel=1,
            )

    @staticmethod
    def test_a_planted_new_private_import_is_refused_and_a_removed_one_asks_to_shrink(tmp_path):
        frozen: set[tuple[str, str]] = set()
        root = _private_import_ratchet___plant(
            tmp_path,
            {
                **_PRIVATE_IMPORT_RATCHET___BASE_TREE,
                "run/a.py": "from pyflightstream.workspace import _priv\n",
            },
        )
        measured = _private_import_ratchet__measure_private_cross_package_imports(root)
        assert measured == {("run.a", "workspace._priv")}
        new, gone = _private_import_ratchet__ratchet_verdict(measured, frozen)
        assert new == [("run.a", "workspace._priv")] and not gone

        # Other spellings of the same import are read: absolute module, relative, deferred.
        for text in (
            "import pyflightstream.workspace._priv\n",
            "from pyflightstream.workspace._priv import VALUE\n",
            "from ..workspace import _priv\n",
            "def f():\n    from pyflightstream.workspace._priv import VALUE\n",
        ):
            root = _private_import_ratchet___plant(
                tmp_path, {**_PRIVATE_IMPORT_RATCHET___BASE_TREE, "run/a.py": text}
            )
            assert _private_import_ratchet__measure_private_cross_package_imports(root) == {
                ("run.a", "workspace._priv")
            }, text

        # Not private cross-package imports: a public module, the own package, a private NAME.
        for text in (
            "from pyflightstream.workspace import public\n",
            "from pyflightstream.workspace.public import VALUE\n",
            "from pyflightstream.workspace import _not_a_module\n",
        ):
            root = _private_import_ratchet___plant(
                tmp_path, {**_PRIVATE_IMPORT_RATCHET___BASE_TREE, "run/a.py": text}
            )
            assert _private_import_ratchet__measure_private_cross_package_imports(root) == set(), (
                text
            )
        root = _private_import_ratchet___plant(
            tmp_path,
            {
                **_PRIVATE_IMPORT_RATCHET___BASE_TREE,
                "run/_own.py": "",
                "run/a.py": "from pyflightstream.run import _own\n",
            },
        )
        assert _private_import_ratchet__measure_private_cross_package_imports(root) == set()

        # Frozen, then removed: passes the ratchet and names the pair to delete.
        root = _private_import_ratchet___plant(tmp_path, _PRIVATE_IMPORT_RATCHET___BASE_TREE)
        new, gone = _private_import_ratchet__ratchet_verdict(
            _private_import_ratchet__measure_private_cross_package_imports(root),
            {("run.a", "workspace._priv")},
        )
        assert not new and gone == [("run.a", "workspace._priv")]


class TestRfixAGuards:
    """Positive and negative controls for the static core and recorded-byte guards."""

    pytestmark = pytest.mark.requirement("P0400-RFIXA-GUARDS")

    @staticmethod
    @pytest.mark.parametrize(
        "source,name",
        [
            ("from ..results import wake", "trefftz.py"),
            ("from ...results.wake import parse_wake_export", "nested/core.py"),
            ("from .. import results", "trefftz.py"),
            ("import numpy as np\nnp.load('x')", "trefftz.py"),
            ("from numpy import load as read\nread('x')", "trefftz.py"),
            ("import numpy as n\nn.loadtxt('x')", "trefftz.py"),
            ("from numpy import genfromtxt\ngenfromtxt('x')", "trefftz.py"),
        ],
    )
    def test_p0400_rfixa_core_guard_refuses_relative_imports_and_array_readers(source, name):
        assert _farfield_core__core_problems(source, name), source

    @staticmethod
    @pytest.mark.parametrize(
        "source,name",
        [
            ("from .fields import PlaneFields", "trefftz.py"),
            ("from ..fields import PlaneFields", "nested/core.py"),
            ("import numpy as np\nnp.array([1, 2])", "trefftz.py"),
            ("from numpy import array as build\nbuild([1])", "trefftz.py"),
            ("def load(x): return x\nload(1)", "trefftz.py"),
        ],
    )
    def test_p0400_rfixa_core_guard_accepts_pure_arrays_and_lower_imports(source, name):
        assert not _farfield_core__core_problems(source, name)

    @staticmethod
    @pytest.mark.parametrize("data", [b"replaced", None])
    def test_p0400_rfixa_compressed_wake_bytes_are_pinned(data):
        path = next(p for p in _RFIXA_GUARDS__RECORDED_WAKE_FIXTURES if p.endswith(".xz"))
        assert _rfixa_guards___geometry_offenses([path], read=lambda _: data) == [path]

    @staticmethod
    def test_p0400_rfixa_recorded_wakes_accept_captured_bytes():
        assert not _rfixa_guards___geometry_offenses(list(_RFIXA_GUARDS__RECORDED_WAKE_FIXTURES))
