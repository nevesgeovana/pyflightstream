"""Generate the docs reference and compatibility pages at build time.

Executed by the mkdocs-gen-files plugin (configured in properdocs.yml).
Every page is virtual: nothing generated here is committed, so the
published site can never drift from the command database. The single
rendering source is ``pyflightstream.reference``, shared with the
``pyflightstream.help()`` offline HTML fallback.
"""

import sys
from pathlib import Path

import mkdocs_gen_files

from pyflightstream.overview import markdown_overview
from pyflightstream.post.guides import input_glossary_markdown
from pyflightstream.reference import (
    conventions_markdown,
    markdown_build_table,
    markdown_compatibility_matrix,
    markdown_reference_pages,
    percent_script_markdown,
)

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

# The architecture overview shares its rendering source with
# pyflightstream.overview(): live module docstrings, read at build time.
with mkdocs_gen_files.open("architecture.md", "w") as page:
    page.write(markdown_overview())

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
    source = (Path("examples") / script_name).read_text(encoding="utf-8")
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
        page.write(content)

# The command-line reference (NFR-29 R3), from the tools' own argument parsers.
for path, content in cli_reference_pages().items():
    with mkdocs_gen_files.open(f"cli/{path}", "w") as page:
        page.write(content)

# The exceptions catalog (NFR-29 R6), from pyflightstream.exceptions.
with mkdocs_gen_files.open("exceptions.md", "w") as page:
    page.write(exceptions_catalog_markdown())
