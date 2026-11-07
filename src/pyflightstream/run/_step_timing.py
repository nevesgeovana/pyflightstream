# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.0
# artifact_id: src/pyflightstream/run/_step_timing.py
# last_modified_at: 2026-11-07T14:42:20.865837-03:00
# last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
# dependencies: [PFS-2201.03]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Implement PFS-2201.03 acceptance for RT057.
# revision_source: git
# GEOVERSE_HEADER_END
"""Read callback timing evidence without changing legacy records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_step_timing(path: Path) -> dict[str, Any]:
    """Return timing fields when a complete counter snapshot is available."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = {
            key: data[key]
            for key in (
                "step_wall_timestamps_s",
                "step_wall_times_s",
                "step_wall_time_last20_mean_s",
            )
            if key in data
        }
        return fields
    except (OSError, ValueError, TypeError):
        return {}
