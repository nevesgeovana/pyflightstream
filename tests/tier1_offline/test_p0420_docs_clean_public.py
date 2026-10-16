"""Public-documentation requirements from the docs-clean owner instructions.

Reproduction: inspect the published Markdown and the generated API docstrings.
The base exposes a deferred dependency, release narration and duplicate navigation.
"""

import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def tracked_texts():
    paths = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"])
    for name in paths.decode("utf-8").split("\0"):
        if name:
            yield name, (ROOT / name).read_bytes().decode("utf-8", errors="replace")


def private_source_ids(sources):
    return [path for path, text in sources if re.search(r"\bSRC-\d+\b", text)]


def test_p0420_sweeps_no_private_source_ids():
    assert not (failures := private_source_ids(tracked_texts())), failures


def test_p0420_sweeps_private_source_id_planted_control(monkeypatch):
    planted = "SRC-" + "123"
    monkeypatch.setattr(sys.modules[__name__], "tracked_texts", lambda: [("fixture.txt", planted)])
    with pytest.raises(AssertionError, match="fixture.txt"):
        test_p0420_sweeps_no_private_source_ids()
    assert not private_source_ids([("fixture.txt", "FSM-26.125 p.12 and FSM-TEST p.1")])


LITERATURE = re.compile(
    r"\b10\.\d{4,9}/\S+|\bISBN(?:-1[03])?\s*:?\s*[\d-]+|"
    r"\b(?!(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Copyright)\b)"
    r"[A-Z][a-z'-]+(?:\s+(?:and|&)\s+[A-Z][a-z'-]+|\s+et al\.)?"
    r",?\s+\(?(?:18|19|20)\d{2}\b(?!-\d)|"
    r"\b(?:[A-Z]\.\s*)+[A-Z][a-z'-]+[^\n]{0,250}\b(?:18|19|20)\d{2}\b(?!-\d)|"
    r"\b(?:Gutin|Goldstein|Hanson|Farassat|Guyan|Steger|Bielawa|White)"
    r"[^\n]{0,100}\b(?:18|19|20)\d{2}\b(?!-\d)"
)

# These two files cite the package's own archived software, not literature.
SOFTWARE_CITATION_PATHS = frozenset(
    {"guide/LICENSE-AND-AUTHORSHIP.md", "guide/latex-sources/shared/info.tex"}
)


def citation_units(path, text):
    if path.endswith(".py"):
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if doc := ast.get_docstring(node):
                    yield from re.split(r"\n\s*\n", doc)
    elif path.endswith((".yaml", ".yml")):

        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)

        yield from strings(yaml.safe_load(text))
    else:
        yield from re.split(r"\n\s*\n|(?=\\bibitem\{|\\item\b)|\r?\n(?=\|)", text)


def uncited_literature(sources):
    failures = []
    for path, text in sources:
        if path == "docs/references.md":
            continue
        if not (
            path.startswith(("docs/", "guide/"))
            or path.startswith("src/")
            and path.endswith(".py")
            or path.startswith("src/pyflightstream/commands/")
        ) or not path.endswith((".md", ".tex", ".py", ".yaml", ".yml")):
            continue
        if path in SOFTWARE_CITATION_PATHS:
            text = text.replace("10.5281/zenodo.21482924", "software archive")
        if path == "guide/pyflightstream_user_guide.tex":
            # The title-page author is document metadata, not a literature citation.
            text = re.sub(r"\\author(?:\[[^\]]*\])?\{[^}]*\}", "", text)
        for unit in citation_units(path, text):
            if LITERATURE.search(" ".join(unit.split())) and not re.search(r"\[REF-\d{2}\]", unit):
                failures.append((path, unit.strip()[:180]))
    return failures


def test_p0420_sweeps_literature_has_public_reference():
    assert not (failures := uncited_literature(tracked_texts())), failures


@pytest.mark.parametrize(
    "citation",
    [
        "Smith (1999)",
        "Smith, 1999",
        "Smith 1999",
        "J. Smith, A book,\n1999",
        "DOI 10.1234/example",
        "ISBN 978-1-234-56789-0",
    ],
)
def test_p0420_sweeps_literature_guard_planted_controls(monkeypatch, citation):
    for path in (
        "docs/fixture.md",
        "guide/fixture.tex",
        "src/fixture.py",
        "src/pyflightstream/commands/fixture.yaml",
    ):

        def content(value, path=path):
            if path.endswith(".py"):
                return f'"""{value}"""'
            if path.endswith(".yaml"):
                return yaml.safe_dump({"description": value})
            return value

        monkeypatch.setattr(
            sys.modules[__name__],
            "tracked_texts",
            lambda path=path, content=content: [(path, content(citation))],
        )
        with pytest.raises(AssertionError):
            test_p0420_sweeps_literature_has_public_reference()
        assert not uncited_literature([(path, content(citation + " [REF-01]"))])
    assert not uncited_literature([("docs/references.md", citation)])


def published_pages():
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text(encoding="utf-8"))
    excluded = config["exclude_docs"].split()
    for path in [
        ROOT / "README.md",
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "docs/examples/_sources").glob("*.py")),
    ]:
        relative = path.relative_to(ROOT).as_posix().removeprefix("docs/")
        if relative != "srs/architecture-srs.md" and any(
            relative == entry.strip("/") or relative.startswith(entry.lstrip("/"))
            for entry in excluded
        ):
            continue
        yield path, path.read_text(encoding="utf-8")


def test_p0420_docs_clean_no_deferred_dependency_in_published_pages():
    failures = [
        str(path.relative_to(ROOT))
        for path, text in published_pages()
        if "itaca" in text.casefold()
    ]
    assert not failures, failures


RELEASE = re.compile(
    r"(?<![\w.])v0\.\d+\b|(?<![\w.])0\.\d+\.(?:\d+|x)\b|"
    r"\b(?:since|added in|release|version|as of)\s+v?0\.[1-9]\d?\b",
    re.IGNORECASE,
)


def api_docstrings(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    return "\n".join(
        doc
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        if (doc := ast.get_docstring(node))
    )


# Sources covered by the public-prose cleanup; private re-export sources are separate work.
REFERENCE_SOURCES = (
    "src/pyflightstream/__init__.py",
    "src/pyflightstream/_errors.py",
    "src/pyflightstream/cases/__init__.py",
    "src/pyflightstream/cases/acoustics.py",
    "src/pyflightstream/cases/corrections.py",
    "src/pyflightstream/cases/freestream.py",
    "src/pyflightstream/cases/fsi_workspace.py",
    "src/pyflightstream/cases/matrix.py",
    "src/pyflightstream/cases/mesh.py",
    "src/pyflightstream/cases/naming.py",
    "src/pyflightstream/cases/pproc.py",
    "src/pyflightstream/cases/qsteady.py",
    "src/pyflightstream/cases/reference_blocks.py",
    "src/pyflightstream/cases/selection.py",
    "src/pyflightstream/cases/settings.py",
    "src/pyflightstream/cases/setup_surfaces.py",
    "src/pyflightstream/cases/sixdof.py",
    "src/pyflightstream/cases/windows.py",
    "src/pyflightstream/cases/workflows/__init__.py",
    "src/pyflightstream/commands/__init__.py",
    "src/pyflightstream/commands/_meta.yaml",
    "src/pyflightstream/commands/acoustics.yaml",
    "src/pyflightstream/commands/base_regions.yaml",
    "src/pyflightstream/commands/boundary_conditions.yaml",
    "src/pyflightstream/commands/cad.yaml",
    "src/pyflightstream/commands/ccs_fuselage_mesh.yaml",
    "src/pyflightstream/commands/ccs_wing_mesh.yaml",
    "src/pyflightstream/commands/mesh_import_export.yaml",
    "src/pyflightstream/commands/motion_definitions.yaml",
    "src/pyflightstream/commands/scenes.yaml",
    "src/pyflightstream/commands/solver_export.yaml",
    "src/pyflightstream/commands/solver_settings.yaml",
    "src/pyflightstream/commands/sweeper.yaml",
    "src/pyflightstream/exceptions.py",
    "src/pyflightstream/farfield/__init__.py",
    "src/pyflightstream/farfield/fields.py",
    "src/pyflightstream/fsi/README.md",
    "src/pyflightstream/fsi/__init__.py",
    "src/pyflightstream/fsi/centrifugal.py",
    "src/pyflightstream/fsi/config.py",
    "src/pyflightstream/fsi/driver.py",
    "src/pyflightstream/fsi/errors.py",
    "src/pyflightstream/fsi/external.py",
    "src/pyflightstream/fsi/loads.py",
    "src/pyflightstream/fsi/nodes.py",
    "src/pyflightstream/fsi/state.py",
    "src/pyflightstream/fsi/wing.py",
    "src/pyflightstream/overview.py",
    "src/pyflightstream/post/__init__.py",
    "src/pyflightstream/post/axes.py",
    "src/pyflightstream/post/corrections.py",
    "src/pyflightstream/post/custom_polar.py",
    "src/pyflightstream/post/disc_maps.py",
    "src/pyflightstream/post/glossary.py",
    "src/pyflightstream/post/guides.py",
    "src/pyflightstream/post/harmonics.py",
    "src/pyflightstream/post/inflow_tools.py",
    "src/pyflightstream/post/point_tables.py",
    "src/pyflightstream/post/polar.py",
    "src/pyflightstream/post/products.py",
    "src/pyflightstream/post/provenance.py",
    "src/pyflightstream/post/qsteady.py",
    "src/pyflightstream/post/qsteady_noise.py",
    "src/pyflightstream/post/reductions.py",
    "src/pyflightstream/post/rotor_table.py",
    "src/pyflightstream/post/section_distributions.py",
    "src/pyflightstream/post/series.py",
    "src/pyflightstream/post/settings_table.py",
    "src/pyflightstream/post/streamlines.py",
    "src/pyflightstream/post/superfile.py",
    "src/pyflightstream/post/surfaces.py",
    "src/pyflightstream/post/unsteady_polar.py",
    "src/pyflightstream/qa/__init__.py",
    "src/pyflightstream/qa/cost.py",
    "src/pyflightstream/qa/drift.py",
    "src/pyflightstream/qa/physics.py",
    "src/pyflightstream/results/__init__.py",
    "src/pyflightstream/results/core.py",
    "src/pyflightstream/results/exports.py",
    "src/pyflightstream/results/loads.py",
    "src/pyflightstream/results/log.py",
    "src/pyflightstream/results/native_surface.py",
    "src/pyflightstream/results/sectional_loads.py",
    "src/pyflightstream/results/surface.py",
    "src/pyflightstream/results/tables.py",
    "src/pyflightstream/run/__init__.py",
    "src/pyflightstream/run/cli.py",
    "src/pyflightstream/run/collect.py",
    "src/pyflightstream/run/matrix.py",
    "src/pyflightstream/run/records.py",
    "src/pyflightstream/script/__init__.py",
    "src/pyflightstream/script/entities.py",
    "src/pyflightstream/script/helpers.py",
    "src/pyflightstream/support.py",
    "src/pyflightstream/utils/__init__.py",
    "src/pyflightstream/utils/manual.py",
    "src/pyflightstream/versions.py",
    "src/pyflightstream/workspace/__init__.py",
    "src/pyflightstream/workspace/actuator_profiles.py",
    "src/pyflightstream/workspace/builds.py",
    "src/pyflightstream/workspace/cli.py",
    "src/pyflightstream/workspace/costs.py",
    "src/pyflightstream/workspace/fields.py",
    "src/pyflightstream/workspace/flight_condition.py",
    "src/pyflightstream/workspace/fsi_external_setup.py",
    "src/pyflightstream/workspace/hpc.py",
    "src/pyflightstream/workspace/inputs.py",
    "src/pyflightstream/workspace/ledger.py",
    "src/pyflightstream/workspace/manifest.py",
    "src/pyflightstream/workspace/matrix.py",
    "src/pyflightstream/workspace/migrate.py",
    "src/pyflightstream/workspace/naming.py",
    "src/pyflightstream/workspace/selections.py",
    "src/pyflightstream/workspace/setup_inspection.py",
    "src/pyflightstream/workspace/sidecars.py",
    "src/pyflightstream/workspace/sixdof_setup.py",
    "src/pyflightstream/workspace/storage.py",
    "src/pyflightstream/workspace/trailing_edges.py",
)


def reference_prose():
    for relative in REFERENCE_SOURCES:
        path = ROOT / relative
        if not relative.startswith("src/"):
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            text = (
                api_docstrings(relative)
                + "\n"
                + "\n".join(
                    token.string
                    for token in tokenize.generate_tokens(io.StringIO(text).readline)
                    if token.type == tokenize.COMMENT and token.string.startswith("#:")
                )
            )
        elif path.suffix == ".yaml":

            def descriptions(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in ("description", "note", "notes") and isinstance(child, str):
                            yield child
                        else:
                            yield from descriptions(child)
                elif isinstance(value, list):
                    for child in value:
                        yield from descriptions(child)

            text = "\n".join(descriptions(yaml.safe_load(text)))
        # Example record values and executable examples are data, not narration.
        text = "\n".join(
            line
            for line in text.splitlines()
            if not re.search(r">>>|\.\.\.|(?:package_version|schema_version)\s*[=:]", line)
        )
        yield relative, text


def test_p0420_docs_clean_generated_release_narration():
    failures = [path for path, text in reference_prose() if RELEASE.search(text)]
    assert not failures, failures


def test_p0420_docs_clean_release_narration():
    failures = []
    for path, text in published_pages():
        if path.name == "upgrading.md" or path.name.startswith("migrating-to-"):
            continue
        if RELEASE.search(text):
            failures.append(path.relative_to(ROOT).as_posix())
    assert not failures, failures
    assert not RELEASE.search(api_docstrings("src/pyflightstream/post/input_template.py"))


def test_p0420_docs_clean_release_guard_controls(monkeypatch):
    for text in ("since 0.29", "in 0.38.0", "added in 0.40.0", "as of 0.41"):
        assert RELEASE.search(text), text
        monkeypatch.setattr(
            sys.modules[__name__], "published_pages", lambda text=text: [(ROOT / "README.md", text)]
        )
        with pytest.raises(AssertionError):
            test_p0420_docs_clean_release_narration()
    for text in (
        "Mach 0.3",
        "radius 0.38 m",
        "FlightStream 26.124",
        "Chrome 151.0.7922.76",
        "since 0.05 cannot be a number of steps",
    ):
        assert not RELEASE.search(text), text


HISTORY = re.compile(
    r"\b(?:narrowed on|reworded on|decided on|changed on|amended|chosen|adopted|"
    r"decision of|rule of|dates from|since)\s+20\d{2}-\d{2}-\d{2}\b|"
    r"\b(?:used to say|renamed in)\s+(?:20\d{2}|v?0\.\d+)|"
    r"\buntil\s+20\d{2}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)


def test_p0420_docs_clean_dated_narration():
    failures = [
        path.relative_to(ROOT).as_posix()
        for path, text in published_pages()
        if HISTORY.search(text)
    ]
    assert not failures, failures
    assert not HISTORY.search(api_docstrings("src/pyflightstream/probes/geometry.py"))


def test_p0420_docs_clean_generated_dated_narration():
    failures = [path for path, text in reference_prose() if HISTORY.search(text)]
    assert not failures, failures


def test_p0420_docs_clean_history_guard_controls(monkeypatch):
    for phrase in ("narrowed on", "reworded on", "decided on", "changed on", "renamed in"):
        text = f"The rule was {phrase} 2026-08-19."
        monkeypatch.setattr(
            sys.modules[__name__], "published_pages", lambda text=text: [(ROOT / "README.md", text)]
        )
        with pytest.raises(AssertionError):
            test_p0420_docs_clean_dated_narration()
    for text in ('"deleted_at": "2026-09-28T10:15:00+00:00"', "report_2026-09-27.md"):
        assert not HISTORY.search(text), text


# Match development chronology, not bare version values, build tables or
# deprecation deadlines. Whitespace normalization also covers wrapped prose.
SOURCE_HISTORY = re.compile(
    r"\b(?:since|until|added in|introduced in|before|as of)\s+(?:the\s+)?v?0\.\d+\.\d+\b|"
    r"\b(?:added|introduced|corrected|rewritten|measured)\s+20\d{2}-\d{2}-\d{2}\b|"
    r"\b(?:measured|verified)(?:\s+against the solver)?(?:\s+on)?[, ]+20\d{2}-\d{2}-\d{2}\b|"
    r"\b(?:used to|previously)\s+(?:accept|carry|return|write|read|raise|emit|"
    r"name|report|compare|hardcode|overwrite|replace|drop|sit|live|say)\b|"
    r"\b(?:first version|first repair)\b|\bcorrection of\s+20\d{2}\b",
    re.IGNORECASE,
)


def source_history(sources):
    failures = []
    for path, text in sources:
        if not path.startswith("src/") or not path.endswith(".py"):
            continue
        tree = ast.parse(text)
        prose = [
            (node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        prose.extend(
            (token.start[0], token.string)
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT
        )
        for line, value in prose:
            normalized = " ".join(value.split())
            if path in {"src/pyflightstream/fsi/cli.py", "src/pyflightstream/workspace/cli.py"}:
                normalized = normalized.replace("deprecated since 0.40.0", "deprecated")
            if SOURCE_HISTORY.search(normalized) or HISTORY.search(normalized):
                # These are recorded provenance values, not development prose.
                if (path, value) in {
                    (
                        "src/pyflightstream/script/motion.py",
                        "decision of 2026-10-01, not measured",
                    ),
                    (
                        "src/pyflightstream/post/field_frames.py",
                        "decision of 2026-10-01, not measured",
                    ),
                }:
                    continue
                failures.append((path, line, normalized[:180]))
    return failures


def test_p0420_sweeps_source_history_narration():
    assert not (failures := source_history(tracked_texts())), failures


@pytest.mark.parametrize(
    "phrase",
    [
        "Added in 0.24.0",
        "since the 0.24.0 review",
        "until 0.26.0 this returned a value",
        "Measured 2026-08-04",
        "measured against the solver on 2026-08-08",
        "verified 2026-10-12",
        "The first version used to accept a path",
    ],
)
def test_p0420_sweeps_source_history_planted_control(monkeypatch, phrase):
    for source in (f'"""{phrase}"""', f"raise ValueError({phrase!r})", f"# {phrase}\n"):
        monkeypatch.setattr(
            sys.modules[__name__],
            "tracked_texts",
            lambda source=source: [("src/fixture.py", source)],
        )
        with pytest.raises(AssertionError):
            test_p0420_sweeps_source_history_narration()
    for allowed in (
        "Migrate a 0.38.0 workspace",
        "Will be removed in 0.43.0",
        "FlightStream 26.125 build 10052026",
        "package_version = '0.42.0'",
    ):
        assert not source_history([("src/fixture.py", f'"""{allowed}"""')])


def nav_entries(items):
    for item in items:
        if isinstance(item, dict):
            for title, target in item.items():
                if isinstance(target, list):
                    yield from nav_entries(target)
                else:
                    yield title, target


def test_p0420_sweeps_reference_page_and_private_dataset_boundary():
    path = ROOT / "docs/references.md"
    assert path.is_file(), "The public reference register is missing"
    text = path.read_text(encoding="utf-8")
    ids = re.findall(r"^### (REF-\d+)$", text, re.MULTILINE)
    assert ids == [f"REF-{number:02}" for number in range(1, 58) if number != 37]
    for build in (
        "25.000",
        "25.100",
        "26.000",
        "26.100",
        "26.101",
        "26.120",
        "26.121",
        "26.122",
        "26.123",
        "26.124",
        "26.125",
    ):
        assert f"**FSM-{build}**" in text
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text(encoding="utf-8"))
    reference = next(item["Reference"] for item in config["nav"] if "Reference" in item)
    assert ("References", "references.md") in list(nav_entries(reference))
    for directory in ("docs", "guide", "src"):
        for source in (ROOT / directory).rglob("*"):
            if source.is_file() and source.suffix in (".md", ".tex", ".py", ".yaml"):
                assert "XPROP" not in source.read_text(encoding="utf-8"), source


def test_p0420_docs_clean_one_architecture_page():
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text(encoding="utf-8"))
    entries = list(nav_entries(config["nav"]))
    architecture = [(title, target) for title, target in entries if "architecture" in title.lower()]
    assert architecture == [("Architecture", "architecture.md")], architecture
    contributing = next(item["Contributing"] for item in config["nav"] if "Contributing" in item)
    assert (
        "Contributor rules",
        config["site_url"] + "architecture/#architectural-decisions",
    ) in list(nav_entries(contributing))
    assert "/srs/architecture-srs.md" in config["exclude_docs"].split()
    core = (ROOT / "docs/srs/architecture-srs.md").read_text(encoding="utf-8")
    assert "## Architectural decisions" in core
