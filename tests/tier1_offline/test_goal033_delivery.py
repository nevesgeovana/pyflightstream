"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from tests.tier1_offline._docs_site import site_pages

ROOT = Path(__file__).resolve().parents[2]


DOCS = ROOT / "docs"


PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


VERSION = PYPROJECT["project"]["version"]


CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


_NEWEST = re.search(r"^## \[(\d+\.\d+\.\d+)\]", CHANGELOG, flags=re.MULTILINE)


RELEASED = _NEWEST.group(1) if (_NEWEST and re.search(r"\.dev\d+$", VERSION)) else VERSION


MIGRATION = DOCS / f"migrating-to-{RELEASED}.md"


UPGRADING = DOCS / "upgrading.md"


def _migration_text() -> str:
    """The migration text of the release: its own page, or its section of the upgrading page."""
    if MIGRATION.is_file():
        return MIGRATION.read_text(encoding="utf-8")
    page = UPGRADING.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(RELEASED)}\n(?P<body>.*?)(?=^## \d|\Z)",
        page,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"docs/upgrading.md has no ## {RELEASED} section and {MIGRATION.name} is absent"
    return match.group("body")


_NEVER_SHIPPED = (
    ".fsm",
    ".stl",
    ".obj",
    ".igs",
    ".iges",
    ".stp",
    ".step",
    ".ccs",
    ".msh",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".csv",
    ".pdf",
    ".docx",
    ".pptx",
    ".zip",
    ".log",
    ".jsonl",
    ".bas",
    ".bin",
    ".vtk",
    ".dat",
    ".txt",
)


_MACHINE_PATH = re.compile(r"(?:\b[A-Za-z]:[\\/](?:Users|GeoverseGoddess|WORK)\b|/home/\w)")


def _changelog_section(version: str) -> str:
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(?P<body>.*?)(?=^## \[)",
        CHANGELOG,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"CHANGELOG.md has no [{version}] section"
    return match.group("body")


def _child_env() -> dict[str, str]:
    """The environment the build runs in: enough to start Python, nothing more."""
    keep = ("PATH", "SYSTEMROOT", "SystemRoot", "TEMP", "TMP", "HOME", "USERPROFILE")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return env


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Run setuptools on a copy of the tracked release inputs.

    The copy holds what the build reads (pyproject.toml, README.md, LICENSE
    and the tracked files under ``src``) so nothing the working copy happens
    to carry, and nothing the build writes, touches the checkout.
    """
    pytest.importorskip("setuptools", reason="building the wheel needs setuptools")
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", "pyproject.toml", "README.md", "LICENSE", "src"],
        capture_output=True,
        text=True,
        check=True,
        env=_child_env(),
    ).stdout.splitlines()
    assert any(name.startswith("src/pyflightstream/") for name in tracked), tracked
    base = tmp_path_factory.mktemp("release")
    tree, lib, meta = base / "tree", base / "lib", base / "meta"
    for name in tracked:
        target = tree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    meta.mkdir()
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "from setuptools import setup; setup()",
            "-q",
            "egg_info",
            "--egg-base",
            str(meta),
            "build_py",
            "--build-lib",
            str(lib),
        ],
        cwd=tree,
        capture_output=True,
        text=True,
        env=_child_env(),
    )
    assert done.returncode == 0, f"the build failed:\n{done.stdout}\n{done.stderr}"
    (info,) = meta.glob("*.egg-info")
    files = sorted(p.relative_to(lib).as_posix() for p in lib.rglob("*") if p.is_file())
    return {"tracked": tracked, "lib": lib, "info": info, "files": files}


def test_the_release_wheel_is_built_from_the_tree_with_the_release_identity(built):
    """The wheel's metadata, modules, data and commands, as setuptools computes them.

    GOAL033:delivery:checks:release_wheel
    """
    pkg_info = (built["info"] / "PKG-INFO").read_text(encoding="utf-8")
    assert re.search(r"^Name: pyflightstream$", pkg_info, flags=re.MULTILINE)
    assert re.search(rf"^Version: {re.escape(VERSION)}$", pkg_info, flags=re.MULTILINE), pkg_info[
        :400
    ]
    release = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    build_steps = " ".join(str(step.get("run", "")) for step in release["jobs"]["build"]["steps"])
    assert "python -m build" in build_steps
    assert "does not match pyproject.toml version" in build_steps
    assert set(release["jobs"]["publish"]["needs"]) >= {"build", "test-artifact", "ci-at-sha"}

    shipped = set(built["files"])
    modules = {
        name.removeprefix("src/")
        for name in built["tracked"]
        if name.startswith("src/") and name.endswith(".py")
    }
    missing = sorted(modules - shipped)
    assert not missing, f"modules the wheel would not carry: {missing}"
    for package, patterns in PYPROJECT["tool"]["setuptools"]["package-data"].items():
        folder = package.replace(".", "/")
        declared = [
            name.removeprefix("src/")
            for name in built["tracked"]
            if name.startswith(f"src/{folder}/")
            and any(
                fnmatch.fnmatch(name.removeprefix(f"src/{folder}/"), pattern)
                for pattern in patterns
            )
        ]
        assert declared, f"{package}: the declared data {patterns} matches no tracked file"
        absent = sorted(set(declared) - shipped)
        assert not absent, f"{package}: declared data the wheel would not carry: {absent}"

    entry_points = (built["info"] / "entry_points.txt").read_text(encoding="utf-8")
    scripts = dict(
        re.findall(
            r"^(\S+)\s*=\s*(\S+)$", entry_points.split("[console_scripts]", 1)[1], re.MULTILINE
        )
    )
    assert scripts == PYPROJECT["project"]["scripts"]
    for target in scripts.values():
        module = target.split(":", 1)[0].replace(".", "/") + ".py"
        assert module in shipped, f"a console script points at {module}, which the wheel lacks"


def test_no_private_payload_reaches_the_release_wheel(built):
    """The wheel holds code and declared data; geometry, data and paths stay out.

    GOAL033:delivery:checks:private_payload_excluded
    """
    patterns = {
        package.replace(".", "/"): globs
        for package, globs in PYPROJECT["tool"]["setuptools"]["package-data"].items()
    }
    forbidden, stray, leaked = _classify_wheel(
        built["files"],
        lambda name: (built["lib"] / name).read_text(encoding="utf-8"),
        patterns,
        PYPROJECT["tool"]["setuptools"]["exclude-package-data"],
    )
    assert not forbidden, f"files of a never-shipped kind in the wheel: {forbidden}"
    assert not stray, f"files in the wheel that no package-data rule declares: {stray}"
    assert not leaked, f"shipped data naming a machine path: {leaked}"


def _classify_wheel(files, read, patterns, excluded):
    """Sort a wheel's file list into never-shipped, undeclared and path-leaking files."""
    stray, forbidden, leaked = [], [], []
    for name in files:
        path = Path(name)
        if path.suffix.lower() in _NEVER_SHIPPED or any(
            fnmatch.fnmatch(path.name, glob) for globs in excluded.values() for glob in globs
        ):
            forbidden.append(name)
        if path.suffix in (".py", ".pyi") or path.name == "py.typed":
            continue
        folder = path.parent.as_posix()
        owner = next(
            (pkg for pkg in patterns if folder == pkg or folder.startswith(pkg + "/")),
            None,
        )
        if owner is None or not any(
            fnmatch.fnmatch(path.relative_to(owner).as_posix(), glob) for glob in patterns[owner]
        ):
            stray.append(name)
            continue
        if _MACHINE_PATH.search(read(name)):
            leaked.append(name)
    return forbidden, stray, leaked


def test_the_wheel_classification_refuses_what_it_exists_to_refuse():
    """The control of the payload check: a synthetic file list it must sort correctly.

    A defect in the classification (a list never appended to, a pattern that
    matches everything) turns the real check above green on any tree.
    """
    # Assembled, so this tracked file carries no profile path of its own.
    home = "path: C:" + "\\" + "Us" + "ers" + "\\" + "someone" + "\\mesh.stl"
    files = {
        "pyflightstream/__init__.py": "",
        "pyflightstream/data/table.csv": "a,b\n",
        "pyflightstream/data/undeclared.json": "{}",
        "pyflightstream/data/declared.json": "{}",
        "pyflightstream/data/leaky.json": home,
        "pyflightstream/commands/blade.fsm": "",
    }
    forbidden, stray, leaked = _classify_wheel(
        list(files),
        files.__getitem__,
        {"pyflightstream/data": ["declared.json", "leaky.json", "table.csv"]},
        {},
    )
    assert sorted(forbidden) == [
        "pyflightstream/commands/blade.fsm",
        "pyflightstream/data/table.csv",
    ]
    assert sorted(stray) == [
        "pyflightstream/commands/blade.fsm",
        "pyflightstream/data/undeclared.json",
    ]
    assert leaked == ["pyflightstream/data/leaky.json"]


def _nav_targets(nav) -> list[str]:
    targets: list[str] = []
    for entry in nav:
        if isinstance(entry, str):
            targets.append(entry)
        elif isinstance(entry, dict):
            for value in entry.values():
                targets.extend(_nav_targets(value) if isinstance(value, list) else [value])
    return targets


def _generated_pages() -> set[str]:
    """The pages scripts/gen_docs_pages.py writes, read from the script itself."""
    source = (ROOT / "scripts" / "gen_docs_pages.py").read_text(encoding="utf-8")
    pages = set(re.findall(r'mkdocs_gen_files\.open\("([^"{}]+\.md)"', source))
    examples = re.search(r"^EXAMPLES = \[(.*?)^\]", source, flags=re.MULTILINE | re.DOTALL)
    assert examples, "gen_docs_pages.py lists no EXAMPLES"
    for script in re.findall(r'"([\w-]+)\.py"', examples.group(1)):
        assert (ROOT / "examples" / f"{script}.py").is_file(), (
            f"examples/{script}.py is listed and absent"
        )
        pages.add(f"examples/{script}.md")
    return pages


def _config() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_multi_constructor("", lambda loader, suffix, node: None)
    return yaml.load((ROOT / "properdocs.yml").read_text(encoding="utf-8"), Loader=_Loader)


def test_every_documented_page_is_built_and_reachable():
    """The menu names only pages that exist, and names every committed page.

    GOAL033:delivery:checks:docs
    """
    targets = _nav_targets(_config()["nav"])
    generated = _generated_pages()
    committed = set(site_pages(DOCS, in_nav=True))
    unresolved = [
        target
        for target in targets
        if not target.endswith("/") and target not in committed and target not in generated
    ]
    assert not unresolved, f"menu entries with no page: {unresolved}"
    assert "reference/" in targets, "the generated command reference left the menu"
    orphans = sorted(committed - set(targets))
    assert not orphans, f"committed pages the menu does not reach: {orphans}"
    # Every page the release's own CHANGELOG section and migration page cite
    # is a page of the site.
    cited = set(re.findall(r"\]\(docs/([\w./-]+\.md)", _changelog_section(RELEASED)))
    cited |= set(re.findall(r"\]\(([\w./-]+\.md)(?:#[\w-]+)?\)", _migration_text()))
    if not MIGRATION.is_file():
        assert "upgrading.md" in site_pages(DOCS, in_nav=True), "the upgrading page left the menu"
    built = set(site_pages(DOCS)) | generated
    absent = sorted(page for page in cited if page not in built)
    assert not absent, f"pages the {RELEASED} notes cite that the site lacks: {absent}"


_RECORDED_TOTALS = Path(__file__).with_name("fixtures") / "recorded_total_rows.csv"


def _printed_decimals(printed: str) -> int:
    return len(printed.split(".")[1]) if "." in printed else 0


def _polar_misses(row: dict[str, str], beta_deg: float) -> list[str]:
    """What the release's polar row gets wrong about one recorded export."""
    from pyflightstream.post.products import GroupCoefficients, polar_row

    force = (float(row["Cx"]), float(row["Cy"]), float(row["Cz"]))
    group = GroupCoefficients(
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, float(row["CDo"]), float(row["CDi"]), ("Total",),
        force=force, moment=(0.0, 0.0, 0.0),
    )  # fmt: skip
    names = (
        "ALPHA BETA MACH RE CDB CYB CLB CRB CMB CNB CDS CYS CLS CRS CMS CNS "
        "CDW CYW CLW CRW CMW CNW CD0 CDI"
    ).split()
    emitted = dict(
        zip(
            names,
            polar_row(
                float(row["alpha_deg"]), 0.2, 1.0, group, cref_m=1.0, bref_m=1.0, beta_deg=beta_deg
            ),
            strict=True,
        )
    )
    misses = []
    digits = min(_printed_decimals(row[name]) for name in ("Cx", "Cz", "CDi", "CDo"))
    stated_drag = float(row["CDi"]) + float(row["CDo"])
    if abs(emitted["CDW"] - stated_drag) > 2.0 * 10.0 ** (-digits):
        misses.append(f"CDW {emitted['CDW']:+.8f} against CDi + CDo {stated_drag:+.8f}")
    for column, printed in (("CDB", "Cx"), ("CYB", "Cy"), ("CLB", "Cz")):
        if abs(emitted[column] - float(row[printed])) > 1e-12:
            misses.append(f"{column} is not the printed {printed}")
    solver_lift = float(row["CL"])
    if abs(solver_lift) > 0.05 and abs(solver_lift - emitted["CLW"]) > 0.01 * abs(solver_lift):
        misses.append(f"CLW {emitted['CLW']:+.6f} against the solver's CL {solver_lift:+.6f}")
    return misses


def test_the_release_reproduces_the_numbers_of_every_recorded_solver_export():
    """Numerical regression at the release: the package's polar numbers are the solver's.

    Every recorded loads export of the licensed workspace printed its total force
    vector ``(Cx, Cy, Cz)`` and, separately, its own drag ``CDi + CDo`` and lift
    ``CL``. The release's polar row, built from that vector at the export's angles,
    must give back the drag at the printed precision, the body-axis columns
    exactly, and the lift within one per cent wherever it exceeds 0.05. All
    exports are scored in one pass, so one numerical regression anywhere in the
    axes or the emitted row turns this red. The control scores the same rows
    with the sideslip sign reversed, and the check must refuse it: a numerical
    check that cannot see a flipped sign is not one.

    This is the offline half of the numerical regressions: the solver's recorded
    numbers against the package at this tree. The licensed re-run of the rows
    whose goldens changed (T43) is a separate obligation and is not claimed here.

    GOAL033:delivery:checks:numerical_regressions
    """
    import csv

    with _RECORDED_TOTALS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "no recorded exports to compare"
    assert all(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in rows)
    assert len({row["export"] for row in rows}) == len(rows), "an export is recorded twice"
    lifting = [row for row in rows if abs(float(row["CL"])) > 0.05]
    sideslip = [row for row in rows if float(row["beta_deg"]) != 0.0]
    assert lifting and sideslip, "the oracle needs lift and sideslip controls"

    regressions = {
        row["export"]: misses
        for row in rows
        if (misses := _polar_misses(row, float(row["beta_deg"])))
    }
    assert not regressions, f"exports the release no longer reproduces: {regressions}"

    flipped = [row["export"] for row in sideslip if _polar_misses(row, -float(row["beta_deg"]))]
    assert flipped, "a reversed sideslip sign passed every recorded export"
