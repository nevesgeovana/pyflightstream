"""PFS-2220 G15: ``kernel_or_skip`` skips where the kernel cannot load, fails where required."""

from __future__ import annotations

import importlib.abc
import os
import sys

import pytest

from tests.tier1_offline._kernel_support import REQUIRE_VARIABLE, kernel_or_skip


class _LibraryFails(importlib.abc.MetaPathFinder):
    """Make ``import gmsh`` raise OSError, as a missing shared library does."""

    def find_spec(self, name, path=None, target=None):
        if name == "gmsh":
            raise OSError("libGLU.so.1: cannot open shared object file")
        return None


@pytest.fixture
def library_fails(monkeypatch):
    monkeypatch.delitem(sys.modules, "gmsh", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_LibraryFails(), *sys.meta_path])


@pytest.fixture
def library_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "gmsh", None)


@pytest.mark.parametrize("broken", ["library_absent", "library_fails"])
def test_p0570_gm15_a_kernel_that_cannot_load_skips_by_default(broken, request, monkeypatch):
    request.getfixturevalue(broken)
    monkeypatch.delenv(REQUIRE_VARIABLE, raising=False)
    with pytest.raises(pytest.skip.Exception, match="cannot load"):
        kernel_or_skip()


@pytest.mark.parametrize("broken", ["library_absent", "library_fails"])
@pytest.mark.parametrize("value", ["1"])
def test_p0570_gm15_a_kernel_that_cannot_load_fails_when_required(
    broken, value, request, monkeypatch
):
    request.getfixturevalue(broken)
    monkeypatch.setenv(REQUIRE_VARIABLE, value)
    # BaseException: a skip raised in its place must read as a failure of this test, not a skip.
    with pytest.raises(BaseException, match="PYFS_REQUIRE_KERNEL=1 requires it") as raised:
        kernel_or_skip()
    assert isinstance(raised.value, pytest.fail.Exception), type(raised.value)


def test_p0570_gm15_a_value_other_than_one_does_not_require_the_kernel(library_absent, monkeypatch):
    monkeypatch.setenv(REQUIRE_VARIABLE, "0")
    with pytest.raises(pytest.skip.Exception):
        kernel_or_skip()


def test_p0570_gm15_a_loadable_kernel_is_returned():
    assert kernel_or_skip().__name__ == "gmsh"


# ---------------------------------------------------------------- the jobs that prove the kernel


def _workflow(name):
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def _steps(job):
    return job["steps"]


def _index(steps, fragment):
    found = [i for i, step in enumerate(steps) if fragment in step.get("name", "")]
    assert found, f"no step named like {fragment!r}"
    return found[0]


@pytest.mark.parametrize("job", ["test", "test-lean"])
def test_p0570_gm15_the_jobs_that_prove_the_kernel_require_it(job):
    steps = _steps(_workflow("ci.yml")[job])
    required = [s for s in steps if s.get("env", {}).get("PYFS_REQUIRE_KERNEL") == "1"]
    assert required, f"job {job} never sets PYFS_REQUIRE_KERNEL=1 on a pytest step"
    assert all("pytest" in s["run"] for s in required)


def test_p0570_gm15_no_install_line_names_the_retired_extra():
    for workflow in ("ci.yml", "release.yml"):
        for name, job in _workflow(workflow).items():
            for step in _steps(job):
                assert "gmsh]" not in step.get("run", "") and ",gmsh" not in step.get("run", ""), (
                    workflow,
                    name,
                )


def test_p0570_gm15_the_lean_probe_runs_before_the_system_libraries():
    steps = _steps(_workflow("ci.yml")["test-lean"])
    probe = _index(steps, "geometry path on a base install")
    libraries = _index(steps, "System libraries")
    tier1 = _index(steps, "Tier 1 with no user-facing extras")
    assert _index(steps, "Install the package") < probe < libraries < tier1
    text = steps[probe]["run"]
    assert "'gmsh' not in sys.modules" in text and "kernel.err" in text
    assert "Traceback" in text and "needs the CAD kernel library gmsh" in text


def test_p0570_gm15_the_wheel_job_installs_the_libraries_and_checks_the_wheel():
    steps = _steps(_workflow("release.yml")["test-artifact"])
    check = _index(steps, "names gmsh as a dependency")
    libraries = _index(steps, "System libraries")
    install = _index(steps, "Install the built wheel")
    assert check < install and libraries < install
    assert steps[libraries]["if"] == "runner.os == 'Linux'"
    assert "Requires-Dist: gmsh" in steps[check]["run"]


def _gmsh_skips_outside_the_helper(root):
    """Every test file under ``root`` that skips on gmsh by itself, not through the helper."""
    import ast
    from pathlib import Path

    def imports_gmsh(node):
        return any(
            (isinstance(n, ast.Import) and any(a.name.split(".")[0] == "gmsh" for a in n.names))
            or (isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "gmsh")
            for n in ast.walk(node)
        )

    def calls_skip(nodes):
        return any(
            isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "skip"
            for node in nodes
            for n in ast.walk(node)
        )

    found = []
    for path in sorted(Path(root).rglob("*.py")):
        if path.name == "_kernel_support.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            importorskip = (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", "") == "importorskip"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "gmsh"
            )
            guarded = (
                isinstance(node, ast.Try)
                and any(imports_gmsh(n) for n in node.body)
                and any(calls_skip(h.body) for h in node.handlers)
            )
            if importorskip or guarded:
                found.append(path.name)
                break
    return found


def test_r11_002_no_test_skips_on_gmsh_outside_the_helper():
    """A skip of its own on gmsh would stay a skip where PYFS_REQUIRE_KERNEL=1."""
    from pathlib import Path

    assert _gmsh_skips_outside_the_helper(Path(__file__).resolve().parents[1]) == []


def test_r11_002_the_scan_finds_both_spellings(tmp_path):
    (tmp_path / "a.py").write_text("import pytest\npytest.importorskip('gmsh')\n")
    (tmp_path / "b.py").write_text(
        "import pytest\ntry:\n    import gmsh\nexcept OSError:\n    pytest.skip('no')\n"
    )
    (tmp_path / "c.py").write_text("from tests.k import kernel_or_skip\nkernel_or_skip()\n")
    assert _gmsh_skips_outside_the_helper(tmp_path) == ["a.py", "b.py"]


#: A sentence that sends the reader to the extra for the kernel, in any markup of the tree.
_NEEDS_THE_EXTRA = (
    r"(optional|needs the|behind the)\s+(``|`|\\texttt\{)?gmsh(``|`|\})?\s+extra"
    r"|gmsh\s+extra\s+is\s+missing|gmsh\s+is\s+not\s+installed"
)


def _sentences_naming_the_extra(folders):
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    found = []
    for folder in folders:
        for path in sorted((root / folder).rglob("*")):
            if path.suffix not in {".md", ".tex", ".py", ".rst"}:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(_NEEDS_THE_EXTRA, text):
                found.append(path.relative_to(root).as_posix())
    return found


def test_r11_003_no_user_page_sends_the_reader_to_the_gmsh_extra():
    """gmsh installs with the package; the guide and the changelog of 0.57.0 say so."""
    assert _sentences_naming_the_extra(["guide/latex-sources", "changelog.d", "docs"]) == []


def test_r11_004_no_module_docstring_calls_the_kernel_an_optional_extra():
    """The rendered API pages read the module docstrings; they follow route A too."""
    assert _sentences_naming_the_extra(["src"]) == []


def _wheel_check_outcome(tmp_path, files):
    """Run the wheel check of release.yml, as written, on a wheel holding ``files``."""
    import subprocess
    import zipfile

    steps = _steps(_workflow("release.yml")["test-artifact"])
    text = steps[_index(steps, "names gmsh as a dependency")]["run"]
    script = text.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    (tmp_path / "dist").mkdir(parents=True)
    with zipfile.ZipFile(tmp_path / "dist" / "pyflightstream-0.57.0-py3-none-any.whl", "w") as w:
        for name, body in files.items():
            w.writestr(name, body)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )


_METADATA = (
    "pyflightstream-0.57.0.dist-info/METADATA",
    "Name: pyflightstream\nRequires-Dist: gmsh<5,>=4.13\n",
)


def test_r11_001_the_wheel_check_passes_the_package_own_kernel_module(tmp_path):
    """The package's workspace/_gmsh.py is not an embedded gmsh, and a real embed is refused."""
    own = dict([_METADATA, ("pyflightstream/workspace/_gmsh.py", "")])
    done = _wheel_check_outcome(tmp_path / "own", own)
    assert done.returncode == 0, done.stderr[-600:]
    embed = dict([_METADATA, ("pyflightstream/_vendor/gmsh.py", "")])
    refused = _wheel_check_outcome(tmp_path / "embed", embed)
    assert refused.returncode != 0 and "embeds gmsh files" in refused.stderr
