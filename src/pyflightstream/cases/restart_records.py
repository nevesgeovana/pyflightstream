"""Wire types for restart arithmetic, distinct from the public averaging ExportWindow.

The persisted export_window key is kept for compatibility. Its value records
the per-step export threshold and the march clock, not an averaging window.
"""

from typing_extensions import TypedDict

__all__ = ["ExportThresholdRecord", "StoppedStepRecord", "RESTART_STEP_OFFSET_VARIABLE"]

RESTART_STEP_OFFSET_VARIABLE = "RESTART_STEP_OFFSET"


class ExportThresholdRecord(TypedDict, total=False):
    """The clock and threshold stored under a run record's export_window key."""

    form: str
    stated: float
    stated_form: str
    stated_value: float
    first_step: int
    time_iterations: int
    delta_time_s: float
    step_deg: float | None
    rpm: float | None
    step_offset: int


class StoppedStepRecord(TypedDict, total=False):
    """The local march step and elapsed time where a march stopped.

    Add export_window.step_offset to recover the whole row's absolute step.
    """

    step: int
    elapsed_s: float
