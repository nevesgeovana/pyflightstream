"""Explicit launch resource requests; absence preserves the solver default."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class RuntimeSettings(BaseModel):
    """Thread count and optional affinity policy for the launch machine.

    Attributes
    ----------
    max_threads : int or str, optional
        Positive explicit thread count or auto for topology-based resolution.
    affinity : str, optional
        Auto selects the topology policy; all disables pinning. Unset adds no policy.
    parallel : int or str, optional
        Solver runs of one campaign alive at once: a positive count or auto. Unset is 1.
    licence_seats : int, optional
        Licence seats this machine may use at once, as configured (the licence server
        is not queried). Bounds auto; unset is 2.
    ram_floor_gb : float, optional
        Free memory in GB one more concurrent run needs before it starts. Unset is 1.0.
    """

    model_config = ConfigDict(extra="forbid")
    max_threads: Annotated[int, Field(strict=True, ge=1)] | Literal["auto"] | None = None
    affinity: Literal["auto", "all"] | None = None
    parallel: Annotated[int, Field(strict=True, ge=1)] | Literal["auto"] | None = None
    licence_seats: Annotated[int, Field(strict=True, ge=1)] | None = None
    ram_floor_gb: Annotated[float, Field(gt=0)] | None = None
    _resolved: dict | None = PrivateAttr(default=None)
