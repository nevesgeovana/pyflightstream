"""ProperDocs build hooks (configured in properdocs.yml).

The generated ``reference/SUMMARY.md`` exists only as navigation input
for the literate-nav plugin; this hook excludes it from the rendered
site. Hooks run after the plugins, so literate-nav has already read
the file when the exclusion lands.
"""

# Dual-namespace assumption (recorded at the 2026-07-23 migration):
# the nav plugins declare both the mkdocs and properdocs backends and
# mkdocs stays installed transitively through mkdocs-material, so File
# objects may originate from either namespace during the ecosystem
# transition. The exclusion below is validated by the CI docs step,
# which asserts no rendered SUMMARY page reaches the site.
from properdocs.structure.files import Files, InclusionLevel


def on_files(files: Files, config: object) -> Files:
    """Exclude the literate-nav input file from the rendered site."""
    nav_file = files.get_file_from_path("reference/SUMMARY.md")
    if nav_file is not None:
        nav_file.inclusion = InclusionLevel.EXCLUDED
    return files
