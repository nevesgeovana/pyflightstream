"""Tier 1, the delivery of 0.29.0: what the release ships, read from the tree.

Four questions a release must answer before it is tagged, each asked of the
thing that answers it rather than of a restatement of it:

- the release wheel: setuptools itself, run on a copy of the tracked tree,
  computes the metadata and the file set the wheel is zipped from; the
  identity, the modules, the declared data and the console scripts are read
  back from what it wrote;
- the private payload: that same file set may hold the package's code and the
  data its configuration declares, and nothing else, so no geometry,
  spreadsheet, document, log or machine path can reach a public artifact;
- the documentation: every page the site's menu names exists (committed, or
  written by the generator the site runs), every committed page is reachable,
  and every page the release's CHANGELOG section cites is in the menu;
- the migration page: every reader-facing change the CHANGELOG lists under
  the release is named on ``docs/migrating-to-<release>.md`` (0.29.0 first,
  0.30.0 since its release commit), and every link on that page resolves to a
  page and a heading that exist.

Building the wheel needs setuptools in the environment that runs the test; a
job without it skips with that reason rather than passing on a guess.
"""

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

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
VERSION = PYPROJECT["project"]["version"]
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
#: The release these checks read the notes of. On a release tree it is the
#: version itself; on a development tree (X.Y.Z.devN, which has no section
#: and no migration page yet) it is the newest released section, so the
#: notes of the last release stay checked while the next is being built.
_NEWEST = re.search(r"^## \[(\d+\.\d+\.\d+)\]", CHANGELOG, flags=re.MULTILINE)
RELEASED = _NEWEST.group(1) if (_NEWEST and re.search(r"\.dev\d+$", VERSION)) else VERSION
MIGRATION = DOCS / f"migrating-to-{RELEASED}.md"

#: Suffixes that are never package payload: geometry, saved simulations,
#: spreadsheets, documents, archives, logs and the retired workbook macro.
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
#: An absolute machine path inside shipped data would name someone's disk.
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
    # The version the wheel carries is the version the CHANGELOG releases, and
    # the release workflow refuses a tag that differs from it.
    newest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", CHANGELOG, flags=re.MULTILINE)
    assert newest and newest.group(1) == RELEASED, (newest and newest.group(1), RELEASED)
    release = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    build_steps = " ".join(str(step.get("run", "")) for step in release["jobs"]["build"]["steps"])
    assert "python -m build" in build_steps
    assert "does not match pyproject.toml version" in build_steps
    assert set(release["jobs"]["publish"]["needs"]) >= {"build", "test-artifact", "gates"}

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
    stray, forbidden, leaked = [], [], []
    for name in built["files"]:
        path = Path(name)
        if path.suffix.lower() in _NEVER_SHIPPED or any(
            fnmatch.fnmatch(path.name, glob)
            for globs in PYPROJECT["tool"]["setuptools"]["exclude-package-data"].values()
            for glob in globs
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
        if _MACHINE_PATH.search((built["lib"] / name).read_text(encoding="utf-8")):
            leaked.append(name)
    assert not forbidden, f"files of a never-shipped kind in the wheel: {forbidden}"
    assert not stray, f"files in the wheel that no package-data rule declares: {stray}"
    assert not leaked, f"shipped data naming a machine path: {leaked}"
    # The check itself can see what it exists to refuse.
    probe = Path("pyflightstream/commands/blade.fsm")
    assert probe.suffix in _NEVER_SHIPPED
    # Assembled, so this tracked file carries no profile path of its own.
    assert _MACHINE_PATH.search("path: C:" + "\\" + "Us" + "ers" + "\\" + "someone" + "\\mesh.stl")


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
    committed = {p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md")}
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
    cited |= set(
        re.findall(r"\]\(([\w./-]+\.md)(?:#[\w-]+)?\)", MIGRATION.read_text(encoding="utf-8"))
    )
    assert f"migrating-to-{RELEASED}.md" in cited
    absent = sorted(page for page in cited if page not in targets)
    assert not absent, f"pages the {RELEASED} notes cite that the menu lacks: {absent}"


#: Each reader-facing change of the CHANGELOG's ``### Changed`` list, by its
#: bold head, and the words the migration page must say for a reader to act on it,
#: per release: the checks read the entry of the release under check, and a
#: release with no entry fails rather than passing on an empty list.
_MIGRATION_NAMES_0_29_0 = {
    "Steady sweeps start every point cold by default.": ("cold start", "warm"),
    "A volume section is sampled, not natively exported.": (
        "`[volume_section]`",
        "_vsec.vtk",
        "datapoints/DP-<point>/",
    ),
    "Nodal strength accompanies the VTK surface fields.": (
        "Singularity_strength",
        "_native_tecplot.dat",
    ),
    "Unsteady post-processing retains explicit time meaning.": (
        "Final section Cp",
        "final instant",
    ),
    "Execution and post logs report their stage and outcome.": (
        "--pproc-warnings",
        "post --diagnostics",
    ),
    "Continuation checks its recorded inputs.": (
        "Continuation and collection verify the recorded scripts",
    ),
    "`ROTOR_SHEDDING` is refused in 0.29.0.": ("`ROTOR_SHEDDING` is refused", "Remove the key"),
    "`legacy_solver_model` and `sonic_velocity_m_per_s` are refused in 0.29.0.": (
        "`legacy_solver_model`",
        "`sonic_velocity_m_per_s`",
        "state `solver_model` instead",
    ),
    "`farfield_layers` above 5 is refused.": ("`farfield_layers` above 5 is refused", "`s929`"),
}

_MIGRATION_NAMES_0_30_0 = {
    "FSI on `unsteady_rotor` is refused by the plan": (
        "`unsteady_rotor`",
        "still in debug on this release",
    ),
    "The structural nodes sit inside the blade": ("sit INSIDE", "`config_sha256`"),
    "The coupled blade route emits `AEROELASTIC_RBF_TYPE MULTI_QUADRATIC`": (
        "AEROELASTIC_RBF_TYPE MULTI_QUADRATIC",
        "State the kernel in the setup",
    ),
    "The rotating structural solve includes the in-plane centrifugal softening": (
        "in-plane centrifugal softening",
        "`flap_residual_m`",
    ),
    "A Tecplot surface no longer exports the native Tecplot by default.": (
        "singularity_strength = true",
        "`NOT_CARRIED`",
        "_native_tecplot.dat",
    ),
}

_MIGRATION_NAMES_0_31_0 = {
    "The AZIMUTH of blade blocks 2 to N of an unsteady rotor changes.": (
        "Blade blocks 2 to N of an unsteady rotor",
        "placed_blade_azimuth_deg",
    ),
    "The repeated-POL census reads the matrices `sync` reads.": (
        "The repeated-POL census reads both matrix folders",
        "inputs/matrices/*.fs",
    ),
    "The docs site navigation is grouped by stage.": (
        "menu is grouped by stage",
        "no page moved or was",
    ),
    "The quasi-steady record has one type, one reader and one refusal.": (
        "`QsteadyRecordError`",
        "`pyflightstream.cases.qsteady`",
        "read_qsteady_record",
    ),
    "The rotor table of a quasi-steady wheel is the mean of its clockings.": (
        "mean of k clockings",
        "Re-post a wheel point",
    ),
    "A wheel's thrust and torque shares are taken along the rotor's axis.": (
        "`THRUST_PCT_K_GT_0_1`",
        "the rotor's axis",
        "re-post those points",
    ),
    "A clocked quasi-steady wheel exports its sections at every clocking.": (
        "cut into sections at every clocking",
        "`_qs<i>`",
        "`section_exports`",
    ),
    "A wheel's `LOCAL_AXIS` distributions are cut.": ("`LOCAL_AXIS`", "`<ALIAS>_RMRP<k>`"),
    "The input template names the pproc's `[per_revolution]` and `[qsteady_correction]` tables": (
        "[per_revolution]",
        "[qsteady_correction]",
    ),
    "The clockings table of a left-hand wheel states blade one's azimuth in the sense it turns.": (
        "The clockings table of a left-hand wheel",
        "`datum - theta_i`",
    ),
    "The guide decks are eight, renamed `pyfts-guide-00` to `pyfts-guide-07`.": (
        "The guide decks are eight",
        "`pyfts-guide-00-fts-overview.pdf`",
    ),
    "The console of `pyfs-matrix plan` is laid out in titled blocks.": (
        "The console of `plan` reads as titled blocks",
        "`Warnings (n)`",
    ),
    "A wheel point's sections table holds every clocking.": (
        "`CLOCKING` column",
        "group by",
    ),
}

_MIGRATION_NAMES_0_32_0 = {
    (
        "Every capability bullet of the change log of 0.25.0 to 0.28.0 now ends with "
        "the id of the requirement that states it"
    ): (
        "0.25.0 to 0.28.0",
        "no behaviour changed",
    ),
}

_MIGRATION_NAMES_0_33_0 = {
    "Every unsteady row registers the step counter.": ("step counter", "26.122"),
}

_MIGRATION_NAMES_0_33_1 = {
    "The tier 1 suite runs in parallel.": ("pytest-xdist", "-n auto"),
}

# The heads are the bold heads of the ### Changed list of the 0.34.0 section; the
# integrator reconciles them with the change log when the section is written.
_MIGRATION_NAMES_0_34_0 = {
    "Every text file the package writes has LF line ends on every platform.": (
        "LF line ends",
        "str.splitlines()",
    ),
    "An actuator disc with `rpm_sign = 1` swirls the way a rotor with `rpm_sign = 1` turns.": (
        "SET_PROP_ACTUATOR_RPM",
        "`rpm_sign = 1`",
    ),
    "A rotor row that states no wake termination keeps 4 rotor radii of wake.": (
        "SET_WAKE_TERMINATION_TIME_STEPS",
        "`wake_termination_length`",
    ),
    # The old overview's name may not stand on this page, which is not one of
    # the historical records (test_p0340_guides, FR-329 R2), so the map is read
    # by the old cheatsheet name it carries and the new overview name.
    "The guides are numbered from 01 and the cheatsheet is guide 04.": (
        "`pyfts-cheatsheet-pyfs-matrix.pdf`",
        "`pyfts-guide-01-fts-overview.pdf`",
    ),
    "`pyfs-matrix run --sims` runs a selection and a second run names its command.": (
        "`--points`",
        "`--resume`",
    ),
    "Five switches that asked DISABLE now get DISABLE.": (
        "`valarezo_criterion`",
        "`vortex_ring_normalization`",
    ),
}

# The heads are the bold heads of the ### Changed list of the 0.35.0 section.
_MIGRATION_NAMES_0_35_0 = {
    "`pyfs-matrix post` writes no `archive/` folder unless `--archive` is given.": (
        "`--archive`",
        "archive=True",
    ),
    "A rotor march emits its vorticity drag list right before `START_SOLVER`.": (
        "SET_VORTICITY_DRAG_BOUNDARIES",
        "`START_SOLVER`",
    ),
}

_MIGRATION_NAMES_BY_RELEASE = {
    "0.38.0": {
        "`pyfs-matrix degenerate` calls the public `derive_thin_blade`.": (
            "`pyflightstream.workspace._degenerate`",
            "derive_thin_blade",
            "FR-429",
        ),
    },
    "0.37.0": {
        "The settings table and its codebook are default products.": (
            "settings_codebook = false",
            "FR-419",
        ),
        "The super content states each rotor's diameter.": (
            "DIAMETER_<alias>",
            "read by name",
            "FR-89",
        ),
        "A quasi-steady point's speed and clock come from its quasi-steady record.": (
            "RPM_CLOCK",
            "J_CLOCK",
            "quasi-steady record",
        ),
        "The plan's left-out line of a coupled steady or quasi-steady row names the remedy.": (
            "run these rows point by point",
            "left_out",
            "FR-421",
        ),
        "A bare matrix name is read from the workspace, whatever the working directory holds.": (
            "working directory",
            "absolute path",
            "FR-411",
        ),
        "Unknown keys of a `[[prune_step_exports]]` table are refused": (
            "keep_last",
            "delete_steps",
            "older_than_days",
            "FR-416",
        ),
        (
            "The installed-frame classification negates `Y`, `VY`, `VORTICITY_X` and "
            "`VORTICITY_Z`, and no longer `CREF`."
        ): (
            "`VORTICITY_X`",
            "`CREF`",
            "FR-420",
        ),
        "On 26.125 the emitter writes the forms its manual documents.": (
            "DETECT_TRAILING_EDGES_BY_SURFACE",
            "`EDGE_TYPE`",
            "byte-identical",
        ),
        "The output readers accept the 26.125 exports.": (
            "Simcenter Flightstream",
            "CDp, CDv",
            "`CDV`",
            "`CDP`",
        ),
    },
    "0.36.0": {
        "Grouped plans always name the acoustic polars that run in their own jobs": (
            "acoustic-isolation note",
            "FR-406",
        ),
        "The `--batch` and `--polar-sweep` help states which rows are left out.": (
            "`RESTART`",
            "`LEGACY`",
            "FR-362",
        ),
        "The campaign, point, sweep and loads-assessment run paths use private phases": (
            "no caller changes",
            "AD-22",
            "NFR-40",
        ),
    },
    "0.35.1": {
        "Repeated sweep values are refused before planning.": (
            "SWEEP_VALUES",
            "point name",
            "FR-408",
        ),
        "The refusal of a geometry carrying saved solver actions states its reason": (
            "saved solver actions",
            "pyfs-matrix inventory",
            "--clean",
            "FR-378",
        ),
    },
    "0.29.0": _MIGRATION_NAMES_0_29_0,
    "0.30.0": _MIGRATION_NAMES_0_30_0,
    "0.31.0": _MIGRATION_NAMES_0_31_0,
    "0.32.0": _MIGRATION_NAMES_0_32_0,
    "0.33.0": _MIGRATION_NAMES_0_33_0,
    "0.33.1": _MIGRATION_NAMES_0_33_1,
    "0.34.0": _MIGRATION_NAMES_0_34_0,
    "0.35.0": _MIGRATION_NAMES_0_35_0,
}

#: The inputs each release's summary refuses, each of which its section and
#: its migration page must name, and further words its page must carry.
_REFUSED_BY_RELEASE = {
    "0.38.0": ("--overwrite", "geom"),
    "0.37.0": ("older_than_days", "SOLVER_TIME_AVERAGING", "26.124"),
    "0.36.0": ("steady", "qsteady_rotor", "FR-410", "RPT-150"),
    "0.35.1": ("COLD_START",),
    "0.29.0": (
        "ROTOR_SHEDDING",
        "legacy_solver_model",
        "sonic_velocity_m_per_s",
        "farfield_layers",
    ),
    "0.30.0": ("unsteady_rotor",),
    "0.31.0": ("unsteady_rotor",),
    "0.32.0": ("unsteady_rotor",),
    "0.33.0": ("unsteady_rotor",),
    "0.33.1": ("unsteady_rotor",),
    "0.34.0": ("unsteady_rotor",),
    "0.35.0": ("unsteady_rotor",),
}
_PAGE_WORDS_BY_RELEASE = {
    "0.38.0": (
        "needs no changes",
        "pyfs-matrix refine",
        "pyfs-matrix audit-mesh",
        "refine_mesh",
        "RefinedMesh",
        "audit_mesh",
        "MeshAudit",
        "derive_thin_blade",
        "`[components]`",
        "`[periodic]`",
    ),
    "0.37.0": (
        "no changes to its inputs",
        "RAN_MISSING_LOG",
        "mark-converged",
        "--apply",
        "--batch",
        "--polar-sweep",
        "FR-412",
        "FR-413",
        "FR-414",
        "FR-415",
        "FR-417",
        "FR-422",
        "FR-423",
        "FR-341",
        "26.125",
    ),
    "0.36.0": (
        "no changes to its inputs",
        "--batch",
        "--polar-sweep",
        "FR-405",
        "FR-407",
        "FR-409",
        "__module__",
        "SETUP_RESET_LOG_PREFIXES",
        "read-only",
        "NFR-33",
        "NFR-34",
        "NFR-35",
        "NFR-36",
        "NFR-37",
        "upgrading.md",
    ),
    "0.35.1": ("--batch", "--polar-sweep", "FR-402", "FR-405", "FR-406", "FR-407"),
    # The unreleased sidecar form the 0.29.0 Added list says is refused.
    "0.29.0": ("[[inlets]]", "refused"),
    "0.30.0": ("PASSAGE_POSITIONS", "prune_step_exports", "--apply"),
    "0.31.0": ("PASSAGE_POSITIONS", "qsteady_rotor", "--apply"),
    "0.32.0": ("--apply", "REBUILT"),
    "0.33.0": ("FAILED_MARKED", "--clean", "inputs/matrices"),
    # The FSI refusal is a standing statement, not a change: its sentence is in
    # the section's Migration list (the review of 2026-10-01, TW-4), so its words
    # are held here rather than to a ### Changed head.
    "0.33.1": (
        "FAILED_INCOMPLETE_OUTPUT",
        "CONVERGED",
        "pyfs-matrix post",
        "`unsteady_rotor`",
        "still in debug on this release",
    ),
    "0.34.0": (
        "NFR-32",
        "FR-331",
        "FR-321",
        "`MESH_FACES`",
        "`PROFILE: <stem>`",
        "build 8242026",
    ),
    "0.35.0": ("FR-397", "FR-396", "FR-318", "--polar-sweep", "--batch", "FR-393"),
}
_MIGRATION_NAMES = _MIGRATION_NAMES_BY_RELEASE.get(RELEASED, {})


def _slug(heading: str) -> str:
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")


def test_the_migration_page_names_every_reader_facing_change():
    """Each change a reader must act on is on the migration page, and its links hold.

    GOAL033:delivery:checks:migration
    """
    assert MIGRATION.is_file(), f"{MIGRATION.name} is absent"
    page = MIGRATION.read_text(encoding="utf-8")
    section = _changelog_section(RELEASED)
    assert f"docs/migrating-to-{RELEASED}.md" in section, (
        "the CHANGELOG section does not cite the page"
    )
    changed = re.search(
        r"^### Changed\n(?P<body>.*?)(?=^### )", section, flags=re.MULTILINE | re.DOTALL
    )
    assert changed, "the CHANGELOG section has no ### Changed list"
    heads = re.findall(r"^- \*\*(.+?)\*\*", changed.group("body"), flags=re.MULTILINE)
    assert heads, "the ### Changed list has no entries"
    assert RELEASED in _MIGRATION_NAMES_BY_RELEASE, (
        f"no migration words are recorded for {RELEASED}; add its entry"
    )
    assert set(heads) == set(_MIGRATION_NAMES), (
        f"changes with no migration words here: {sorted(set(heads) - set(_MIGRATION_NAMES))}; "
        f"words kept for no listed change: {sorted(set(_MIGRATION_NAMES) - set(heads))}"
    )
    unnamed = {
        head: [word for word in words if word not in page]
        for head, words in _MIGRATION_NAMES.items()
        if any(word not in page for word in words)
    }
    assert not unnamed, f"changes the migration page does not name: {unnamed}"
    # The refused inputs the release summary lists are each on the page too,
    # and so are the words the release's page must carry.
    for refused in _REFUSED_BY_RELEASE[RELEASED]:
        assert refused in section and refused in page, refused
    for word in _PAGE_WORDS_BY_RELEASE[RELEASED]:
        assert word in page, word

    broken = []
    for target, anchor in re.findall(r"\]\(([\w./-]+\.md)(?:#([\w-]+))?\)", page):
        linked = DOCS / target
        if not linked.is_file():
            broken.append(target)
            continue
        if anchor:
            headings = re.findall(
                r"^#{1,6} (.+)$", linked.read_text(encoding="utf-8"), flags=re.MULTILINE
            )
            if anchor not in {_slug(heading) for heading in headings}:
                broken.append(f"{target}#{anchor}")
    assert not broken, f"migration links that resolve to nothing: {broken}"
    assert _slug("Uniform inlet and outlet boundaries") == "uniform-inlet-and-outlet-boundaries"


#: The Total row of every recorded solver loads export, as printed, each with
#: the sha256 of the export it was read from (scripts/extract_recorded_total_rows.py).
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
    assert len(rows) >= 40, f"{len(rows)} recorded exports; the oracle shrank"
    assert all(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in rows)
    assert len({row["export"] for row in rows}) == len(rows), "an export is recorded twice"
    lifting = [row for row in rows if abs(float(row["CL"])) > 0.05]
    sideslip = [row for row in rows if float(row["beta_deg"]) != 0.0]
    assert len(lifting) >= 28 and len(sideslip) >= 4, (len(lifting), len(sideslip))

    regressions = {
        row["export"]: misses
        for row in rows
        if (misses := _polar_misses(row, float(row["beta_deg"])))
    }
    assert not regressions, f"exports the release no longer reproduces: {regressions}"

    flipped = [row["export"] for row in sideslip if _polar_misses(row, -float(row["beta_deg"]))]
    assert flipped, "a reversed sideslip sign passed every recorded export"
