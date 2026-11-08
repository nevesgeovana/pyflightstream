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
