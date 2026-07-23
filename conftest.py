"""Sybil configuration: executable examples in CI (INB-006 item 1e).

Pipeline role: test-collection config at the repository root. Sybil
turns the package's own examples into tests, following the author's
decision of 2026-07-23 (DECISION_QUEUE Q-007): the ``>>>`` doctests in
module and function docstrings, and the ``python`` code blocks in the
committed markdown (README plus ``docs/``), are executed so a stale
example fails CI instead of misleading a reader.

Two scoped Sybil instances keep this off the normal ``pytest`` run
(``testpaths = ["tests"]``): each carries an explicit ``path``, so a
plain ``pytest`` collects nothing here. The examples run only when the
suite is pointed at the source and docs, which the CI ``examples`` step
does with warnings promoted to errors::

    pytest src/pyflightstream README.md docs -W error

The commented skiplist below excludes the deprecation shims. They hold
no examples of their own (they re-export their replacement), and their
import warns by design; the doctest parser reads source text without
importing, so this is a documented precaution rather than a current
need: an example added under a shim later must not drag its
DeprecationWarning into the warnings-as-errors run.
"""

from sybil import Sybil
from sybil.parsers.markdown import PythonCodeBlockParser
from sybil.parsers.rest import DocTestParser
from sybil.sybil import SybilCollection

#: Docstring doctests in the package source.
_docstring_examples = Sybil(
    parsers=[DocTestParser()],
    path="src/pyflightstream",
    patterns=["*.py"],
    # Skiplist (commented, per Q-007): the deprecation shims hold no
    # examples and their import warns by design; kept out as a
    # precaution so a future example under a shim cannot drag its
    # DeprecationWarning into the warnings-as-errors run.
    excludes=[
        "files/__init__.py",
        "cases/matrix_legacy.py",
    ],
)

#: python code blocks in the docs tree (all user-facing pages).
_docs_examples = Sybil(
    parsers=[PythonCodeBlockParser()],
    path="docs",
    patterns=["*.md"],
)

#: python code blocks in the root README only. The exclude keeps the
#: nested developer READMEs inside src/ (illustrative design snippets,
#: not runnable user examples) out; Sybil matches names from the right,
#: so ``*/README.md`` catches every nested one and spares the root file.
_readme_examples = Sybil(
    parsers=[PythonCodeBlockParser()],
    path=".",
    patterns=["README.md"],
    excludes=["*/README.md"],
)

pytest_collect_file = SybilCollection(
    [_docstring_examples, _docs_examples, _readme_examples]
).pytest()
