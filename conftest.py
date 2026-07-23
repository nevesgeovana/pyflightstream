"""Sybil configuration: executable examples in CI (INB-006 item 1e).

Pipeline role: test-collection config at the repository root. Sybil
turns the package's own examples into tests, following the author's
decision of 2026-07-23 (DECISION_QUEUE Q-007): the ``>>>`` doctests in
module and function docstrings, and the ``python`` code blocks in the
committed markdown (README plus ``docs/``), are executed so a stale
example fails CI instead of misleading a reader.

Three scoped Sybil instances (docstrings under ``src``, markdown under
``docs``, and the root README) keep this off the normal ``pytest`` run
(``testpaths = ["tests"]``): each carries an explicit ``path``, so a
plain ``pytest`` collects nothing here (asserted by
``tests/test_examples_isolation.py``). The examples run only when the
suite is pointed at the source and docs, which the CI "Executable
examples" step does with warnings promoted to errors::

    pytest src/pyflightstream README.md docs -W error

The active skiplist below keeps the deprecation shims out. They hold no
examples of their own (they re-export their replacement); the doctest
parser reads source text without importing, so the exclusion is a
precaution rather than a current need, kept active so a future doctest
added under a shim that imports it cannot drag its DeprecationWarning
into the warnings-as-errors run.

Sybil is a dev-only dependency; if it is not installed (a plain
checkout without the ``dev`` extra), this module registers no collector
so the Tier 1 suite still runs anywhere.
"""

try:
    from sybil import Sybil
    from sybil.parsers.markdown import PythonCodeBlockParser
    from sybil.parsers.rest import DocTestParser
    from sybil.sybil import SybilCollection

    _SYBIL = True
except ImportError:  # dev-only dependency absent: the examples step is skipped
    _SYBIL = False

#: Docstring doctests in the package source.
if _SYBIL:
    _docstring_examples = Sybil(
        parsers=[DocTestParser()],
        path="src/pyflightstream",
        patterns=["*.py"],
        # Active skiplist (per Q-007): the deprecation shims hold no
        # examples and importing them warns by design; excluded as a
        # precaution so a future doctest under a shim that imports it
        # cannot drag its DeprecationWarning into the -W error run.
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
    #: nested developer READMEs inside src/ (illustrative design
    #: snippets, not runnable user examples) out; Sybil matches names
    #: from the right, so ``*/README.md`` catches every nested one and
    #: spares the root file.
    _readme_examples = Sybil(
        parsers=[PythonCodeBlockParser()],
        path=".",
        patterns=["README.md"],
        excludes=["*/README.md"],
    )

    #: Exposed for the isolation test to assert path-scoping.
    EXAMPLE_SYBILS = (_docstring_examples, _docs_examples, _readme_examples)

    pytest_collect_file = SybilCollection(list(EXAMPLE_SYBILS)).pytest()
