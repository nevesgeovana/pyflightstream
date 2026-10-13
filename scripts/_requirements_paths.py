"""Where the requirement registers live, in one place (stdlib only).

Pipeline role: shared constant. The functional and non-functional requirement registers and
their index are kept in the repository but off the published site, in
``docs/unpublished/requirements``. Every script and every test that reads them takes the
location from here, so a later move changes one file.
"""

from pathlib import Path

#: Folder of the requirement registers, relative to the repository root.
REQUIREMENTS_DIR = Path("docs/unpublished/requirements")
#: The functional requirements register, relative to the repository root.
FUNCTIONAL_REQUIREMENTS = REQUIREMENTS_DIR / "functional-requirements.md"
#: The non-functional requirements register, relative to the repository root.
NONFUNCTIONAL_REQUIREMENTS = REQUIREMENTS_DIR / "nonfunctional-requirements.md"
#: The requirements index page, relative to the repository root.
REQUIREMENTS_INDEX = REQUIREMENTS_DIR / "index.md"
#: Fragments that ``scripts/assemble_srs.py`` folds into the functional register.
REQUIREMENTS_FRAGMENTS_DIR = REQUIREMENTS_DIR / "fr.d"


def absolute(root: Path, relative: Path) -> Path:
    """Return ``relative`` (one of the constants above) under the repository ``root``."""
    return Path(root) / relative
