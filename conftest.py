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

    pytest src/pyflightstream README.md docs -W error::pyflightstream._errors.PyflightstreamWarning

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
    from sybil.parsers.markdown import PythonCodeBlockParser, SkipParser
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
        # The skiplist held the two deprecation shims and is empty since
        # v0.4.0 removed them (Q-007). Kept as a named absence rather than
        # deleted: the next shim needs the same exclusion, because a doctest
        # under one would drag its DeprecationWarning into the -W error run.
        excludes=[],
    )

    #: python code blocks in the docs tree (all user-facing pages).
    #:
    #: SkipParser is here so a page can hold an illustrative block that
    #: needs a licensed solver or a populated workspace, marked
    #: ``<!-- skip: next -->`` and still syntax highlighted. Without it
    #: the only way to publish such a block was to drop its ``python``
    #: tag, which costs the highlighting on exactly the pages a new
    #: reader opens first. Every block NOT marked is executed, so the
    #: default stays "checked" and skipping is the deliberate act.
    _docs_examples = Sybil(
        parsers=[PythonCodeBlockParser(), SkipParser()],
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
