# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.0
# artifact_id: src/pyflightstream/cases/runtime.py
# last_modified_at: 2026-11-07T14:42:20.865837-03:00
# last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
# dependencies: [PFS-2201.01]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Implement PFS-2201.01 acceptance for RT057.
# revision_source: git
# GEOVERSE_HEADER_END
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
