"""ProperDocs build hooks (configured in properdocs.yml).

The generated ``SUMMARY.md`` files (the solver command reference under
``reference/``, the Python API reference under ``api/`` and the
command-line reference under ``cli/``) exist only as navigation input
for the literate-nav plugin; this hook excludes them from the rendered
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

#: The generated folders whose navigation literate-nav reads from a SUMMARY.md.
NAV_FOLDERS = ("reference", "api", "cli")


def on_files(files: Files, config: object) -> Files:
    """Exclude the literate-nav input files from the rendered site."""
    for folder in NAV_FOLDERS:
        nav_file = files.get_file_from_path(f"{folder}/SUMMARY.md")
        if nav_file is not None:
            nav_file.inclusion = InclusionLevel.EXCLUDED
    return files
