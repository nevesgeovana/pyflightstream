"""A boolean field of an HPC profile's descriptor is written bare (0.35.0).

A cluster whose launcher reads a switch from the job's yaml (``driveg: true``)
reads a quoted value as a string, not as the switch. The profile states the
field as a TOML boolean; the descriptor writes it bare and lower case in yaml and
toml, and a quoted string in the profile stays a quoted string (the control).
"""

from __future__ import annotations

from types import SimpleNamespace

from pyflightstream.run import render_descriptor

VALUES = {"sim": "mtx_b1", "ncpus": 8, "fs_build": "26.124"}


def _profile(fmt: str, driveg: object) -> SimpleNamespace:
    return SimpleNamespace(
        fields={
            "job_name": "FTS{sim}",
            "ncpus": "{ncpus}",
            "version": "{fs_build}",
            "driveg": driveg,
        },
        descriptor_format=fmt,
        path="h.toml",
    )


def test_p0350_descriptor_a_boolean_field_is_bare_in_yaml():
    """P0350-BATCH-SUBMIT (FR-372): ``driveg = true`` in the profile is ``driveg: true``."""
    text = render_descriptor(_profile("yaml", True), VALUES)
    assert "driveg: true\n" in text
    assert 'version: "26.124"' in text, "a build identifier stays quoted"
    assert "ncpus: 8" in text
    assert "driveg: false\n" in render_descriptor(_profile("yaml", False), VALUES)


def test_p0350_descriptor_a_boolean_field_is_bare_in_toml():
    """P0350-BATCH-SUBMIT (FR-372): the toml descriptor writes the boolean bare too."""
    assert "driveg = true\n" in render_descriptor(_profile("toml", True), VALUES)


def test_p0350_descriptor_a_quoted_string_stays_quoted():
    """The control: a profile that states the string "true" gets a quoted string."""
    assert 'driveg: "true"' in render_descriptor(_profile("yaml", "true"), VALUES)
