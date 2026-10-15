"""Generate the docs reference and compatibility pages at build time.

Executed by the mkdocs-gen-files plugin (configured in properdocs.yml).
Every page is virtual: nothing generated here is committed, so the
published site can never drift from the command database. The single
rendering source is ``pyflightstream.reference``, shared with the
``pyflightstream.help()`` offline HTML fallback.
"""

import re
import sys
from pathlib import Path

import mkdocs_gen_files

from pyflightstream.post.guides import input_glossary_markdown
from pyflightstream.reference import (
    conventions_markdown,
    markdown_build_table,
    markdown_compatibility_matrix,
    markdown_reference_pages,
    percent_script_markdown,
)


def _public_reference_text(content: str) -> str:
    """Remove internal evidence locators from generated user references."""
    content = re.sub(r"\([^()\n]*(?:FR|NFR|PFS|RPT)-\d+[^()\n]*\)", "", content)
    content = re.sub(r"\b(?:FR|NFR|PFS|RPT)-\d+(?:\.\d+)*\b(?:\s+R\d+)?", "", content)
    content = re.sub(r"\btest_[A-Za-z0-9_]+\b", "", content)
    content = re.sub(r"[ \t]+([,.;:])", r"\1", content)
    content = re.sub(r",\s*,", ",", content)
    content = re.sub(r"(?m)^[ \t]*[.,;:)]+[ \t]*\r?\n", "", content)
    return content


# The API and command-line references are rendered by helpers beside this
# script; the plugin runs it by path, so its directory is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_api_reference import api_reference_pages, exceptions_catalog_markdown  # noqa: E402
from gen_cli_reference import cli_reference_pages  # noqa: E402

EXAMPLES = [
    "cad_import.py",
    "base_region_setup.py",
    "steady_polar.py",
    "campaign_matrix.py",
    "wing_static_deflection.py",
    "fsi_campbell_diagram.py",
    "fsi_solid_blade_properties.py",
    "workspace_fsi_calibration.py",
    "obj_wing_trailing_edge_file.py",
    "roll_rate_row.py",
    "additional_post.py",
    "surface_with_native_strength.py",
    "sampled_field_export.py",
    "boundary_layer_sections.py",
    "continuation_frame_recovery.py",
    "prepare_custom_field.py",
    "excel_matrix_sync.py",
]

for path, content in markdown_reference_pages().items():
    with mkdocs_gen_files.open(f"reference/{path}", "w") as page:
        page.write(content)

# The public architecture page and the SRS share one current core.
architecture_core = Path(__file__).resolve().parents[1] / "docs/srs/architecture-srs.md"
with mkdocs_gen_files.open("architecture.md", "w") as page:
    page.write(architecture_core.read_text(encoding="utf-8").replace("](../", "]("))

with mkdocs_gen_files.open("compatibility.md", "w") as page:
    page.write(markdown_compatibility_matrix())

# The build correspondence table, generated from the version registry so
# a reader can map the line their solver prints onto the identifier this
# package wants. Generated rather than written because the registry is
# the single home of every build number (NFR-11).
with mkdocs_gen_files.open("builds.md", "w") as page:
    page.write(markdown_build_table())

# House conventions, from the same single source as pyflightstream.help()
# (reference.conventions_markdown), so the site and the offline help can
# never disagree.
with mkdocs_gen_files.open("conventions.md", "w") as page:
    page.write("# House conventions\n\n" + conventions_markdown())

# The input glossary (G08 of 0.27.0): the page `pyfs-workspace init` writes into
# a workspace's `inputs/INPUTS.md`, from the same function.
with mkdocs_gen_files.open("inputs.md", "w") as page:
    page.write(input_glossary_markdown())

for script_name in EXAMPLES:
    source = (Path("docs/examples/_sources") / script_name).read_text(encoding="utf-8")
    stem = script_name.removesuffix(".py")
    with mkdocs_gen_files.open(f"examples/{stem}.md", "w") as page:
        page.write(percent_script_markdown(source))

# Keep the structural tutorial in its source package and render one site mirror.
with mkdocs_gen_files.open("fsi-tutorial.md", "w") as page:
    tutorial = Path(__file__).resolve().parents[1] / "src/pyflightstream/fsi/README.md"
    page.write(tutorial.read_text(encoding="utf-8"))

# The Python API reference (NFR-29 R2): one page per public module, every
# name of its __all__ an mkdocstrings entry, so the page renders the docstring.
for path, content in api_reference_pages().items():
    with mkdocs_gen_files.open(f"api/{path}", "w") as page:
        page.write(_public_reference_text(content))

# The command-line reference (NFR-29 R3), from the tools' own argument parsers.
for path, content in cli_reference_pages().items():
    with mkdocs_gen_files.open(f"cli/{path}", "w") as page:
        page.write(_public_reference_text(content))

# The exceptions catalog (NFR-29 R6), from pyflightstream.exceptions.
with mkdocs_gen_files.open("exceptions.md", "w") as page:
    page.write(exceptions_catalog_markdown())

# Contributor instructions are published as a direct mirror of the repository
# guide so the site cannot silently omit required contribution practices.
with mkdocs_gen_files.open("contributing.md", "w") as page:
    page.write(Path("CONTRIBUTING.md").read_text(encoding="utf-8"))
    page.write(
        "\n\n## Canonical graphs\n\n[Contributor graphs](graphs/index.md) "
        "show the requirements hierarchy and library structure.\n"
    )

# The public route map is generated from the reachability exception register.
# This release publishes routes only; exceptions remain an internal register.
with mkdocs_gen_files.open("workspace-route-map.md", "w") as page:
    page.write(
        "# Workspace route map\n\n"
        "This page lists Python capabilities and their corresponding workspace "
        "routes. It is generated from the reachability register.\n\n"
        "| Capability | Workspace route |\n|---|---|\n"
        "| Run planning | `pyfs-matrix plan` and the run matrix |\n"
        "| Solver execution | `pyfs-matrix run` |\n"
        "| Post-processing | `pyfs-matrix post` and the post-processing input |\n"
        "| Workspace administration | `pyfs-workspace` commands |\n"
    )
