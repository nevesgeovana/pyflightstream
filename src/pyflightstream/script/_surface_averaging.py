"""The resolved surface-window contracts shared by builders and recorded runs.

Two windows, because two different things averaged a surface. The first,
:data:`SurfaceAveragingWindow`, is the window a run before 0.28.0 handed the
solver's ``SOLVER_TIME_AVERAGING``, whose bounds' meaning was never measured
(``verification: UNVERIFIED``). The second, :data:`SurfaceAverageWindow`, is
the window the package itself averages the per-step surface exports over
(G25 of 0.28.0): its bounds are the time steps the package counts and the
solver stamps, so it carries no verification to qualify them.
"""

from typing import Annotated, Literal, NotRequired, TypedDict

from pydantic import AfterValidator, Field, StrictInt


class _ResolvedWindow(TypedDict):
    """Inclusive time-step bounds and the request that resolved them."""

    iterations: Annotated[
        list[Annotated[StrictInt, Field(gt=0)]], Field(min_length=2, max_length=2)
    ]
    iteration_unit: Literal["time_steps"]
    verification: Literal["UNVERIFIED"]
    last_iters: NotRequired[Annotated[StrictInt, Field(gt=0)]]
    last_revs: NotRequired[Annotated[float, Field(gt=0, allow_inf_nan=False)]]
    steps_per_revolution: NotRequired[Annotated[float, Field(gt=0, allow_inf_nan=False)]]


def _validate(window: _ResolvedWindow) -> _ResolvedWindow:
    if window["iterations"][0] > window["iterations"][1]:
        raise ValueError("iterations must be increasing inclusive bounds [first, last]")
    if ("last_iters" in window) == ("last_revs" in window):
        raise ValueError("state exactly one of last_iters or last_revs in the recorded window")
    if "last_revs" in window and "steps_per_revolution" not in window:
        raise ValueError("last_revs requires recorded steps_per_revolution")
    return window


SurfaceAveragingWindow = Annotated[_ResolvedWindow, AfterValidator(_validate)]


class _PackageWindow(TypedDict):
    """Inclusive time-step bounds the package averages its surface exports over (G25)."""

    iterations: Annotated[
        list[Annotated[StrictInt, Field(gt=0)]], Field(min_length=2, max_length=2)
    ]
    iteration_unit: Literal["time_steps"]
    last_iters: NotRequired[Annotated[StrictInt, Field(gt=0)]]
    last_revs: NotRequired[Annotated[float, Field(gt=0, allow_inf_nan=False)]]
    steps_per_revolution: NotRequired[Annotated[float, Field(gt=0, allow_inf_nan=False)]]


def _validate_package(window: _PackageWindow) -> _PackageWindow:
    return _validate(window)  # type: ignore[arg-type,return-value]


SurfaceAverageWindow = Annotated[_PackageWindow, AfterValidator(_validate_package)]
