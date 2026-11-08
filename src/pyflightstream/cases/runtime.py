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
    """

    model_config = ConfigDict(extra="forbid")
    max_threads: Annotated[int, Field(strict=True, ge=1)] | Literal["auto"] | None = None
    affinity: Literal["auto", "all"] | None = None
    _resolved: dict | None = PrivateAttr(default=None)
