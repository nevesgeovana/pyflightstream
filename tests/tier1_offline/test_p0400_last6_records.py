"""The persisted threshold and stopped-step records have a shared declared type."""

import pytest

from pyflightstream.workspace import RunRecord

pytestmark = pytest.mark.requirement("P0400-LAST6-RECORDS")


def test_p0400_last6_threshold_record_has_a_declared_type():
    annotation = str(RunRecord.model_fields["export_window"].annotation)
    assert "ExportThresholdRecord" in annotation, "P0400-LAST6-RECORD-TYPE"


def test_p0400_last6_stopped_step_record_has_a_declared_type():
    annotation = str(RunRecord.model_fields["stopped_at"].annotation)
    assert "StoppedStepRecord" in annotation, "P0400-LAST6-STOPPED-TYPE"
