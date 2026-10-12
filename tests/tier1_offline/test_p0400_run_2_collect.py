"""Tier 1, 0.40.0 lane run-2: the collect stage and its records.

Every fixture is synthetic.
"""

from __future__ import annotations

import inspect
import typing

from pyflightstream.run import collect


def test_p0400_collect_and_post_declares_the_sims_keyword_of_its_callbacks():
    """P0400-COLLECT-CALLBACKS (PFS-2095.027): the annotation states the keyword it is called with.

    ``post`` and ``post_matrix`` were annotated without ``sims`` and called
    with it under ``type: ignore``, so a callback written to the annotation
    crashed after the records were written.
    """
    hints = typing.get_type_hints(collect.collect_and_post)
    for name in ("post", "post_matrix"):
        declared = next(a for a in typing.get_args(hints[name]) if a is not type(None))
        parameters = inspect.signature(declared.__call__).parameters
        assert "sims" in parameters, name
        assert parameters["sims"].kind is inspect.Parameter.KEYWORD_ONLY, name
    source = inspect.getsource(collect)
    assert "type: ignore[call-arg]" not in source
