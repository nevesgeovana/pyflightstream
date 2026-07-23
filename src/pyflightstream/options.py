"""Runtime options registry: the package's declared, validated knobs.

Pipeline role: cross-cutting support module (imports nothing from the
pipeline; any layer may consume it). Machine-dependent and
quality-assurance knobs (scratch roots, solver timeouts) live here as
registered options instead of scattered literals, following the pandas
``register_option`` model: every option is declared once with a
default, a docstring, and a validator, and every access goes through
:func:`get_option` / :func:`set_option`.

Three deliberate differences from pandas:

- Keys are exact, never pattern-matched: ``get_option("qa.probe")``
  does not resolve ``qa.probe_timeout_s``. Partial matching makes
  every new key a potential silent behavior change of existing code.
- The registry refuses unknown keys with the full known-key list
  (openmdao message contract: the error names the option, the value,
  and what would have been accepted).
- :func:`describe_option` returns the text instead of printing it;
  use ``print(describe_option())`` at the REPL.

The options serve programmatic drivers of the package (scripts,
notebooks, campaign code calling the qa entry points); a terminal user
of the CLIs tunes the same quantities per invocation through the
command-line flags whose defaults read from here.

Examples
--------
>>> from pyflightstream import options
>>> options.get_option("qa.probe_timeout_s")
120.0
>>> options.set_option("qa.probe_timeout_s", 60.0)
>>> with options.option_context("qa.scratch_root", "D:/scratch"):
...     pass  # runs launched here scratch under D:/scratch
>>> options.reset_option("qa.probe_timeout_s")

Options are process-wide state: they configure the machine the process
runs on (where scratch goes, how long a solver may take), never the
physics of a case. Anything that changes a result belongs in the case
definition or the workspace, where it is recorded by the manifest.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any


class OptionError(KeyError):
    """An option key is unknown, or a value fails its validator.

    Raised with the didactic message contract of the module: unknown
    keys list every registered key; rejected values name the option,
    the received value, and the accepted form.
    """

    def __str__(self) -> str:
        """Render the message as prose (KeyError would quote it)."""
        return str(self.args[0]) if self.args else ""


@dataclass(frozen=True)
class RegisteredOption:
    """Declaration of one option: identity, default, doc, validator.

    Attributes
    ----------
    key : str
        Exact dotted key, ``<area>.<name>`` (example:
        ``"qa.scratch_root"``).
    default : object
        Value returned until :func:`set_option` overrides it.
    doc : str
        One didactic sentence: what the knob does and its unit.
    validator : callable or None
        Called with a candidate value; raises ``ValueError`` naming
        the accepted form when the value does not fit. ``None`` accepts
        anything.
    """

    key: str
    default: Any
    doc: str
    validator: Callable[[Any], None] | None = None


_REGISTRY: dict[str, RegisteredOption] = {}
_VALUES: dict[str, Any] = {}


def _unknown_key_error(key: str) -> OptionError:
    known = ", ".join(sorted(_REGISTRY)) or "(none registered)"
    return OptionError(
        f"no option is registered under {key!r}. Keys are exact (this "
        f"registry never pattern-matches). Registered keys: {known}."
    )


def register_option(
    key: str,
    *,
    default: Any,
    doc: str,
    validator: Callable[[Any], None] | None = None,
) -> None:
    """Declare one option; every option is declared exactly once.

    Parameters
    ----------
    key : str
        Exact dotted key, lowercase ``<area>.<name>``.
    default : object
        Value served until a ``set_option`` overrides it. Must itself
        satisfy the validator. Keyword-only, like ``doc``: for a
        string-valued option the two would swap silently if passed
        positionally.
    doc : str
        One didactic sentence (what the knob does, unit included);
        rendered by :func:`describe_option`.
    validator : callable, optional
        Raises ``ValueError`` for unacceptable values.

    Raises
    ------
    OptionError
        If the key is already registered (a second registration would
        silently rebind existing readers) or the default fails its own
        validator.
    """
    if key in _REGISTRY:
        raise OptionError(
            f"option {key!r} is already registered; every option is declared "
            "exactly once (the package's own knobs at the bottom of "
            "pyflightstream.options)."
        )
    option = RegisteredOption(key=key, default=default, doc=doc, validator=validator)
    _check_value(option, default)
    _REGISTRY[key] = option


def _check_value(option: RegisteredOption, value: Any) -> None:
    if option.validator is None:
        return
    try:
        option.validator(value)
    except ValueError as error:
        raise OptionError(f"option {option.key!r} rejects value {value!r}: {error}") from error


def get_option(key: str) -> Any:
    """Return the current value of one option (exact key).

    Parameters
    ----------
    key : str
        Exact dotted key of a registered option.

    Returns
    -------
    object
        The value set by the latest :func:`set_option`, else the
        registered default.

    Raises
    ------
    OptionError
        If no option is registered under the exact key; the message
        lists every registered key.
    """
    if key not in _REGISTRY:
        raise _unknown_key_error(key)
    return _VALUES.get(key, _REGISTRY[key].default)


def set_option(key: str, value: Any) -> None:
    """Set one option after validation (exact key).

    Parameters
    ----------
    key : str
        Exact dotted key of a registered option.
    value : object
        New value; checked by the option's validator first.

    Raises
    ------
    OptionError
        Unknown key, or a value the validator refuses; the message
        names the option, the received value, and the accepted form.
    """
    if key not in _REGISTRY:
        raise _unknown_key_error(key)
    _check_value(_REGISTRY[key], value)
    _VALUES[key] = value


def reset_option(key: str) -> None:
    """Return one option to its registered default (exact key).

    Raises
    ------
    OptionError
        If no option is registered under the exact key; the message
        lists every registered key.
    """
    if key not in _REGISTRY:
        raise _unknown_key_error(key)
    _VALUES.pop(key, None)


def describe_option(key: str | None = None) -> str:
    """Render the declared options as readable text.

    Parameters
    ----------
    key : str, optional
        Exact key to describe; ``None`` describes every registered
        option, sorted by key.

    Returns
    -------
    str
        One block per option: key, current value, default, and doc.
        Returned, not printed: ``print(describe_option())`` at the
        REPL.

    Raises
    ------
    OptionError
        If the given key is not registered; the message lists every
        registered key.
    """
    if key is not None and key not in _REGISTRY:
        raise _unknown_key_error(key)
    keys = [key] if key is not None else sorted(_REGISTRY)
    blocks = []
    for name in keys:
        option = _REGISTRY[name]
        blocks.append(
            f"{name}: {get_option(name)!r} (default {option.default!r})\n    {option.doc}"
        )
    return "\n".join(blocks)


@contextmanager
def option_context(*pairs: Any) -> Iterator[None]:
    """Set options inside a ``with`` block, restoring them on exit.

    Parameters
    ----------
    *pairs : object
        Alternating key and value arguments, pandas style:
        ``option_context("qa.probe_timeout_s", 10.0, ...)``.

    Raises
    ------
    OptionError
        Unknown key or refused value, before anything is changed.
    """
    if len(pairs) % 2:
        raise OptionError(
            "option_context takes alternating key and value arguments "
            f"(got {len(pairs)} arguments); example: "
            "option_context('qa.probe_timeout_s', 10.0)."
        )
    items = [(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2)]
    for key, value in items:  # validate everything before touching state
        if key not in _REGISTRY:
            raise _unknown_key_error(key)
        _check_value(_REGISTRY[key], value)
    saved = {key: _VALUES.get(key, _MISSING) for key, _ in items}
    try:
        for key, value in items:
            _VALUES[key] = value
        yield
    finally:
        for key, previous in saved.items():
            if previous is _MISSING:
                _VALUES.pop(key, None)
            else:
                _VALUES[key] = previous


_MISSING = object()


# --- validators -------------------------------------------------------------


def positive_seconds(value: Any) -> None:
    """Accept a strictly positive real number of seconds."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError("a strictly positive number of seconds is required")


def non_empty_path_text(value: Any) -> None:
    """Accept a non-empty string or path-like filesystem path."""
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("a non-empty path string or pathlib.Path is required")


# --- the package's registered options ---------------------------------------
# Machine/QA knobs, the first consumers of the registry: the pyfs-qa
# CLI reads its scratch and timeout defaults here, so a programmatic
# driver of the qa entry points sets them once per process; terminal
# users tune the same quantities through the CLI flags.

register_option(
    "qa.scratch_root",
    default="runs",
    doc="Root directory of the gitignored local run scratch; the QA tiers "
    "use <root>/probes, <root>/physics, and <root>/drift under it.",
    validator=non_empty_path_text,
)
register_option(
    "qa.probe_timeout_s",
    default=120.0,
    doc="Per-probe wall-clock limit in seconds of the Tier 2 validity "
    "sweep; probes are tiny scripts, so minutes mean a hung solver.",
    validator=positive_seconds,
)
register_option(
    "qa.case_timeout_s",
    default=900.0,
    doc="Per-point wall-clock limit in seconds of the Tier 3 physics and "
    "drift runs; a converged steady point on the synthetic cases "
    "takes well under this on the reference machine.",
    validator=positive_seconds,
)
