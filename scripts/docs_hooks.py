"""Mkdocs build hooks (configured in mkdocs.yml).

The generated ``reference/SUMMARY.md`` exists only as navigation input
for the literate-nav plugin; this hook excludes it from the rendered
site. Hooks run after the plugins, so literate-nav has already read
the file when the exclusion lands.
"""

from mkdocs.structure.files import Files, InclusionLevel


def on_files(files: Files, config: object) -> Files:
    """Exclude the literate-nav input file from the rendered site."""
    nav_file = files.get_file_from_path("reference/SUMMARY.md")
    if nav_file is not None:
        nav_file.inclusion = InclusionLevel.EXCLUDED
    return files
