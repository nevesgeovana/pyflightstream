"""Generate the docs reference and compatibility pages at build time.

Executed by the mkdocs-gen-files plugin (configured in mkdocs.yml).
Every page is virtual: nothing generated here is committed, so the
published site can never drift from the command database. The single
rendering source is ``pyflightstream.reference``, shared with the
``pyflightstream.help()`` offline HTML fallback.
"""

from pathlib import Path

import mkdocs_gen_files

from pyflightstream.overview import markdown_overview
from pyflightstream.reference import (
    markdown_compatibility_matrix,
    markdown_reference_pages,
    percent_script_markdown,
)

EXAMPLES = ["steady_polar.py"]

for path, content in markdown_reference_pages().items():
    with mkdocs_gen_files.open(f"reference/{path}", "w") as page:
        page.write(content)

# The architecture overview shares its rendering source with
# pyflightstream.overview(): live module docstrings, read at build time.
with mkdocs_gen_files.open("architecture.md", "w") as page:
    page.write(markdown_overview())

with mkdocs_gen_files.open("compatibility.md", "w") as page:
    page.write(markdown_compatibility_matrix())

for script_name in EXAMPLES:
    source = (Path("examples") / script_name).read_text(encoding="utf-8")
    stem = script_name.removesuffix(".py")
    with mkdocs_gen_files.open(f"examples/{stem}.md", "w") as page:
        page.write(percent_script_markdown(source))
