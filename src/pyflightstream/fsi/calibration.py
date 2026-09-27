# GEOVERSE_HEADER
# file_version: "1.0.0"
# last_modified_at: "2026-09-27T15:35:36.983207+00:00"
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementation-agent}
# dependencies: []
# status: active
# confidentiality: public
# change_summary: "One vocabulary for independent FSI calibration and matrix keys."
# revision_source: git
"""FSI-facing access to the dependency-free calibration vocabulary."""

from pyflightstream._fsi_calibration import (
    CALIBRATION_FACTORS,
    MATERIAL_FACTORS,
    MATRIX_FACTORS,
    PROPERTY_FACTORS,
)

__all__ = ["CALIBRATION_FACTORS", "MATERIAL_FACTORS", "MATRIX_FACTORS", "PROPERTY_FACTORS"]
