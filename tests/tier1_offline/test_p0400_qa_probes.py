"""P0400-PROBEHARNESS: the tier-2 probe harness and the specifications it judges.

PFS-2102.013: fsm_gained keeps the exponent, so a value at the wrong power of ten fails.
PFS-2102.027: a probe that could not be built leaves a directory the next run may wipe.
PFS-2102.033: a prelude this edition's grammar refuses downgrades its tier.
PFS-2102.014: the settings dumps sit outside the sentinels; a missing dump is unprobed.
PFS-2102.028: an instrument that raises makes the target unprobed, not the run fatal.
PFS-2102.001: the deletion probes need their positive control to verify.
PFS-2102.005: a cambered NACA code with a zero camber position is refused.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.qa import PROBE_SPECS, _spec_ccs_noise
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.geometry import BladeSpec, WingSpec
from pyflightstream.qa.probes import (
    DEFAULT_ERROR_PATTERNS,
    ProbeArtifacts,
    ProbeOutcome,
    ProbeSpec,
    Requires,
    _judge,
    _run_probe,
    _validate_tiers,
    dump_gained,
    fsm_gained,
    generate_probe_script,
)
from pyflightstream.run import ExecutionResult
from pyflightstream.script import CommandArgumentError
from pyflightstream.versions import known_versions, resolve


def _states(before: str, after: str):
    return SimpleNamespace(saved_before=lambda: before, saved_after=lambda: after)


def test_p0400_probeharness_a_value_at_the_wrong_power_of_ten_is_not_found():
    """P0400-PROBEHARNESS (PFS-2102.013) 0.1 is not on a changed line holding 1.0."""
    check = fsm_gained("0.1")
    assert check(_states("x\n0\n", "x\n1.00000000000000000E+00\n")) is False
    assert check(_states("x\n0\n", "x\n1.00000000000000006E-01\n")) is True
    assert fsm_gained("37")(_states("x\n15\n", "x\n3.70000000000000000E-01\n")) is False


def test_p0400_probeharness_an_unbuildable_probe_can_be_built_again(tmp_path):
    """P0400-PROBEHARNESS (PFS-2102.027) the second run on the workroot is not refused."""

    def prelude(script, workdir: Path) -> None:
        (workdir / "support.stl").write_text("solid s\nendsolid s\n", encoding="utf-8")

    def refuses(script, workdir: Path) -> None:
        raise CommandArgumentError("this edition's grammar refuses the probe's value")

    spec = ProbeSpec(
        command="PRINT",
        build_target=refuses,
        prelude=prelude,
        assert_effect=lambda artifacts: True,
        effect_note="not reached",
    )
    for _ in range(2):
        result = _run_probe(spec, resolve("26.120"), None, tmp_path, 60.0, (), None)
        assert result.outcome is ProbeOutcome.UNPROBED, result.detail


def test_p0400_probeharness_a_refused_prelude_line_downgrades_its_tier(tmp_path):
    """P0400-PROBEHARNESS (PFS-2102.033) 25.000's AIR_ALTITUDE grammar does not end the run."""
    planned = [SimpleNamespace(requires=Requires.SOLVER)]
    failures = _validate_tiers(
        planned, resolve("25.000"), None, tmp_path, tmp_path / "x.fsm", 60.0, None
    )
    assert Requires.SOLVER in failures
    assert "cannot be emitted" in failures[Requires.SOLVER]


@pytest.mark.parametrize("version", known_versions(), ids=str)
@pytest.mark.parametrize("tier", [tier for tier in Requires if tier is not Requires.NONE])
def test_p0400_probeharness_each_registered_prelude_builds_or_downgrades(tmp_path, version, tier):
    """P0400-PROBEHARNESS (PFS-2102.033) every edition and tier reaches a verdict."""
    emitted = []

    def run_script(script_path, **kwargs):
        emitted.append(script_path.read_text(encoding="utf-8"))
        return SimpleNamespace(diagnosis=lambda: "offline instrument has no log")

    failures = _validate_tiers(
        [SimpleNamespace(requires=tier)],
        version,
        SimpleNamespace(run_script=run_script),
        tmp_path,
        tmp_path / "x.fsm",
        60.0,
        None,
    )
    assert tier in failures
    if not emitted:
        assert "cannot be emitted" in failures[tier]
    else:
        assert "prelude did not reach its sentinel" in failures[tier]


def test_p0400_probeharness_the_dumps_bracket_the_target_from_outside(tmp_path):
    """P0400-PROBEHARNESS (PFS-2102.014) no dump line between the sentinels; no dump, no verdict."""
    command = "FLUID_PROPERTIES"
    spec = PROBE_SPECS[command]
    assert spec.dump_state
    lines = generate_probe_script(spec, "26.120", tmp_path, fsm=tmp_path / "x.fsm").render()
    lines = lines.splitlines()
    begin = lines.index(f"PRINT PYFS_PROBE_BEGIN_{command}")
    end = lines.index(f"PRINT PYFS_PROBE_END_{command}")
    assert "OUTPUT_SETTINGS_AND_STATUS" not in lines[begin:end]
    assert lines.count("OUTPUT_SETTINGS_AND_STATUS") == 2
    missing = SimpleNamespace(dump_after=lambda: None)
    assert dump_gained("7.2531", strict=True)(missing) is None


def _reached(workdir: Path) -> ProbeArtifacts:
    return ProbeArtifacts(
        workdir=workdir,
        log_before="PYFS_B",
        log_after="PYFS_E",
        begin_marker="PYFS_B",
        end_marker="PYFS_E",
        execution=ExecutionResult(
            return_code=0, wall_time_s=1.0, timed_out=False, log_text="", stdout="", stderr=""
        ),
    )


def test_p0400_probeharness_an_instrument_that_raises_leaves_the_target_unprobed(tmp_path):
    """P0400-PROBEHARNESS (PFS-2102.028) DELETE_SURFACES on a run whose SAVEAS wrote nothing."""
    spec = PROBE_SPECS["DELETE_SURFACES"]
    result = _judge(spec, _reached(tmp_path), DEFAULT_ERROR_PATTERNS, "sha", 60.0)
    assert result.outcome is ProbeOutcome.UNPROBED, result.detail

    def raising(artifacts):
        raise RuntimeError("the reader fell over")

    other = ProbeSpec(
        command="PRINT", build_target=lambda s, w: None, assert_effect=raising, effect_note="x"
    )
    result = _judge(other, _reached(tmp_path), DEFAULT_ERROR_PATTERNS, "sha", 60.0)
    assert result.outcome is ProbeOutcome.UNPROBED
    assert "RuntimeError: the reader fell over" in result.detail


def test_p0400_probeharness_a_deletion_needs_its_positive_control(tmp_path):
    """P0400-PROBEHARNESS (PFS-2102.001) absence alone verifies nothing."""
    check = PROBE_SPECS["DELETE_VOLUME_SECTION"].assert_effect
    artifacts = SimpleNamespace(workdir=tmp_path)
    assert check(artifacts) is None, "no export at all is an instrument that proved nothing"
    (tmp_path / "vsection_2.vtk").write_text("vtk", encoding="utf-8")
    assert check(artifacts) is True, "the survivor kept index 2"
    (tmp_path / "vsection.vtk").write_text("vtk", encoding="utf-8")
    assert check(artifacts) is False, "both sections export: nothing was deleted"
    (tmp_path / "vsection_2.vtk").unlink()
    assert check(artifacts) is True, "the survivor renumbered to 1"

    observers = PROBE_SPECS["DELETE_ALL_ACOUSTIC_OBSERVERS"].assert_effect
    path = tmp_path / _spec_ccs_noise._SIGNALS
    path.write_text("", encoding="utf-8")
    assert observers(artifacts) is None, "an empty signals file proves no deletion"
    path.write_text("Observer: PYFS_CTRL\n0.0 1.0\n", encoding="utf-8")
    assert observers(artifacts) is True
    path.write_text("Observer: PYFS_CTRL\n0.0 1.0\nObserver: PYFS_OBS1\n0.0 1.0\n", "utf-8")
    assert observers(artifacts) is False


@pytest.mark.parametrize("make", [lambda: WingSpec(naca="2012"), lambda: BladeSpec(naca="4012")])
def test_p0400_probeharness_a_cambered_section_needs_its_camber_position(make):
    """P0400-PROBEHARNESS (PFS-2102.005) refused at construction, not by a ZeroDivisionError."""
    with pytest.raises(QaEvidenceError, match="position digit 0"):
        make()
    WingSpec(naca="0012")
    WingSpec(naca="2412")
