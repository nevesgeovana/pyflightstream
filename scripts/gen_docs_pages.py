# GEOVERSE_HEADER
# file_version: 1.0.4
# artifact_id: documentation-generator
# last_modified_at: 2026-09-27T20:29:11.784Z
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: primary-agent}
# dependencies: [pyflightstream]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Publish the existing FSI tutorial from its single source.
# revision_source: git
"""Generate the docs reference and compatibility pages at build time.

Executed by the mkdocs-gen-files plugin (configured in properdocs.yml).
Every page is virtual: nothing generated here is committed, so the
published site can never drift from the command database. The single
rendering source is ``pyflightstream.reference``, shared with the
``pyflightstream.help()`` offline HTML fallback.
"""

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
