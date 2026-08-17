"""The one renderer of a single-line YAML flow mapping.

Pipeline role: below every layer, imported by any of them. It defines two
functions and imports nothing from this package, which is the whole
reason it exists as a separate module, exactly as :mod:`._errors` does:
the command database's chapter files are written from two places that sit
on opposite sides of the dependency order, and a renderer living in
either one is unreachable from the other.

WHY IT IS NOT A CONVENIENCE. Escaping used to be a convention each call
site could reach for or not, and nothing observed whether it had: a
``note`` was interpolated between two literal quote characters at both
rendering sites for four releases, so a probe detail carrying a backslash
produced a chapter file YAML refuses, and a detail whose backslashes
happened to precede valid escapes wrote silently corrupted text
(``INC-20260811-1511-both``). That incident was closed by removing the
concept of a call site, in :mod:`pyflightstream.qa.compat`.

IT WAS RE-OPENED ON 2026-08-17 and this module is the second, wider
repair. ``pyfs-manual register`` writes ``documented`` rows into the same
chapter files from :mod:`pyflightstream.utils`, which sits BELOW
:mod:`pyflightstream.qa` and cannot import the helper that was the one
home. So it built the mapping by concatenation, and the class came back:
measured on the day, a note carrying a backslash or a quote character
made the chapter file unparsable and a note carrying a newline was
written silently truncated. Moving the renderer below both writers is
what makes "there is now no site" true of the package rather than of one
module.

The guard is ``tests/test_yamlflow.py``, which refuses a hand-built flow
mapping anywhere under ``src/`` but here, and it is proven by mutation
rather than by passing: ``scripts/prove_flow_mapping_guard.py`` restores
the concatenated form and requires a deny.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

__all__ = ["RAW_KEYS", "flow_mapping", "flow_scalar"]


#: Keys written WITHOUT quotes. `status` alone, and deliberately: it is
#: the shape every committed chapter file and every pinning test carries,
#: and a status is a closed vocabulary, so it cannot pick up the
#: boolean-coercion problem the quoting exists for.
RAW_KEYS = frozenset({"status"})


def flow_mapping(pairs: Mapping[str, object]) -> str:
    r"""Render an ordered mapping as one YAML flow mapping.

    THE ONE PLACE a value is written into a chapter file, which is the
    point of it. See this module's own docstring for the two incidents
    that produced the rule and for why it lives below every layer.

    Parameters
    ----------
    pairs : mapping of str to object
        Keys in the order they are written. Values go through
        :func:`flow_scalar` unless the key is in :data:`RAW_KEYS`.

    Returns
    -------
    str
        ``{key: value, ...}``, braces included.

    Examples
    --------
    >>> flow_mapping({"status": "documented", "note": "SRC-751 p.290"})
    '{status: documented, note: "SRC-751 p.290"}'

    A note carrying a quote character is escaped rather than emitted
    raw, which is the case that used to produce a file YAML refuses:

    >>> flow_mapping({"status": "documented", "note": 'the "new" text'})
    '{status: documented, note: "the \\"new\\" text"}'
    """
    rendered = ", ".join(
        f"{key}: {value if key in RAW_KEYS else flow_scalar(value)}" for key, value in pairs.items()
    )
    return "{" + rendered + "}"


def flow_scalar(value: object) -> str:
    """Render one value inside a single-line YAML flow mapping.

    Strings are quoted unconditionally rather than only where YAML would
    require it. ``status: documented`` reads more naturally unquoted, and
    deciding per value is how ``OFF`` or ``NO`` reaches the file as a
    boolean: this database already lost an argument default that way, so
    the rule here is the blunt one.

    Parameters
    ----------
    value : object
        Any scalar, list or mapping. Anything that is not a bool, a
        number, None, a list or a dict is rendered as its ``str``.

    Returns
    -------
    str
        The value as YAML would have to read it back.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) or value is None:
        return json.dumps(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return json.dumps(str(value))
