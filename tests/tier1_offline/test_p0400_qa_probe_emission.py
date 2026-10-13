"""P0400-PROBEEMIT: the probe import and export entry points of ``pyflightstream.probes``.

PFS-2100.023: the import's ``units`` names the unit the csv was written in.
PFS-2104.015: the import takes a frame label like ``helpers.probes_from_file``.
PFS-2081.26: a refused export collision names the entry point the caller used.
"""

from __future__ import annotations

import typing

import pytest

from pyflightstream.probes import emit_probe_export, emit_probe_import
from pyflightstream.script import CommandArgumentError, Script


def test_p0400_probeemit_units_doc_names_the_simulation_length_unit():
    """P0400-PROBEEMIT (PFS-2100.023) the units parameter says which unit the csv is in."""
    doc = emit_probe_import.__doc__ or ""
    units_section = doc.split("units : str", 1)[1].split("frame :", 1)[0]
    assert "simulation length unit" in units_section, (
        "the units parameter does not tell the reader that the csv write_probe_csv "
        "writes is in the case's simulation length unit"
    )


def test_p0400_probeemit_import_takes_a_frame_label():
    """P0400-PROBEEMIT (PFS-2104.015) a created frame is cited by its label, as in the helper."""
    hints = typing.get_type_hints(emit_probe_import)
    assert hints["frame"] == int | str, "emit_probe_import still types frame as an index only"
    script = Script(version="26.120")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM", label="wake_frame")
    emit_probe_import(script, "C:/probes/lattice.txt", units="METER", frame="wake_frame")
    assert "PROBE_POINTS_IMPORT\nUNITS METER\nFRAME 2\n" in script.render()


def test_p0400_probeemit_collision_remedy_names_emit_probe_export():
    """P0400-PROBEEMIT (PFS-2081.26) the remedy names the function the caller called."""
    script = Script(version="26.120")
    emit_probe_export(script, "survey.csv")
    with pytest.raises(CommandArgumentError) as refused:
        emit_probe_export(script, "survey.csv", update=False)
    message = str(refused.value)
    assert "Give emit_probe_export a path" in message, message
    assert "Give export_probes" not in message, message
    assert script.render().count("EXPORT_PROBE_POINTS") == 1
