"""One-release compatibility for the section helpers' keyword-only inputs."""

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from pyflightstream._deprecations import FSI_SECTION_POSITIONAL
from pyflightstream._errors import PyflightstreamDeprecationWarning, warn

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _section_keywords(*names: str) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Keep positional calls until 0.43.0, while publishing the keyword signature."""

    def decorate(function: Callable[_P, _R]) -> Callable[_P, _R]:
        @wraps(function)
        def compatible(*args: Any, **kwargs: Any) -> _R:
            if len(args) > 1:
                if len(args) > len(names) + 1:
                    raise TypeError(
                        f"{function.__name__} accepts at most {len(names) + 1} positional arguments"
                    )
                for name, value in zip(names, args[1:], strict=False):
                    if name in kwargs:
                        raise TypeError(f"{function.__name__} got multiple values for {name!r}")
                    kwargs[name] = value
                promise = next(
                    entry
                    for entry in FSI_SECTION_POSITIONAL
                    if entry.owner.endswith(function.__name__)
                )
                warn(promise.message(), PyflightstreamDeprecationWarning, stacklevel=2)
                args = args[:1]
            return function(*args, **kwargs)

        return compatible

    return decorate
