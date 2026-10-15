"""Regression coverage grouped by subject."""

from __future__ import annotations

import importlib.util
import inspect
import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest

import pyflightstream.utils.manual as manual
from pyflightstream._errors import InputArtifactError
from pyflightstream._expressions import evaluate_expression, parse_expression
from pyflightstream._fsm import MeshReadError, names_of, resolve_family
from pyflightstream.commands import (
    _PROBE_REF_PATTERN,
    ArgSpec,
    ArgType,
    CommandEntry,
    CommandNotInVersionError,
    CommandRegistry,
    Layout,
    Phase,
    Status,
    VersionStatus,
)
from pyflightstream.farfield import (
    FarfieldInputError,
    LatticeFields,
    axial_force,
    in_plane_moment,
    lattice_fields,
    spurious_diagnostic,
    to_counts,
)
from pyflightstream.options import OptionError, get_option, option_context, set_option
from pyflightstream.probes import build_lattice
from pyflightstream.qa import ProbeOutcome, probe_version
from pyflightstream.utils import insert_version_row
from tests.tier1_offline.test_qa_probes import (
    FakeFlightStream as _CoreSmallReviewQaFakeFlightStream,
)
from tests.tier1_offline.test_qa_probes import run_pilot as _core_small_review_qa__run_pilot

_CORE_SMALL_CHM_TO_PDF__REPO = Path(__file__).resolve().parents[2]


def _core_small_chm_to_pdf___load():
    spec = importlib.util.spec_from_file_location(
        "chm_to_pdf_p0400", _CORE_SMALL_CHM_TO_PDF__REPO / "scripts" / "chm_to_pdf.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoreSmallChmToPdf:
    """P0400-CHMEMPTY (PFS-2135.044): chm_to_pdf.py fails when the package reader finds no command.

    The tool printed "the package reader finds NO command; the page numbers are
    not citable" and exited 0. The archive reading, the Chrome render and the pdf
    reader are replaced, so the test reaches that branch without Chrome or pypdf.
    """

    @staticmethod
    @pytest.mark.parametrize(
        ("found", "code"), [({}, 1), ({"X": types.SimpleNamespace(page=3)}, 0)]
    )
    def test_p0400_chmempty_no_command_found_is_a_failure(
        tmp_path, monkeypatch, found, code
    ) -> None:
        """P0400-CHMEMPTY: no command found exits 1; the control, one found, exits 0."""
        module = _core_small_chm_to_pdf___load()
        out = tmp_path / "out.pdf"
        monkeypatch.setattr(sys, "argv", ["chm_to_pdf.py", str(tmp_path), str(out), "chrome.exe"])
        reader = types.SimpleNamespace(PdfReader=lambda path: types.SimpleNamespace(pages=[1]))
        monkeypatch.setattr(module, "_pypdf", lambda: reader)
        monkeypatch.setattr(module, "combine", lambda root: (root / "c.html", 0, 0))
        monkeypatch.setattr(
            module, "render", lambda combined, target, chrome: target.write_bytes(b"x")
        )
        monkeypatch.setattr(manual, "read_pdf_pages", lambda path, *, first, last: {})
        monkeypatch.setattr(manual, "parse_signatures", lambda pages: found)
        assert module.main() == code


_CORE_SMALL_COMMANDS__REPORT = "reports/RPT-018_separation-family-across-builds_2026-08-05.md"


def _core_small_commands___entry(
    versions: dict[str, VersionStatus], **citation: str
) -> CommandEntry:
    return CommandEntry(
        name="X_CMD",
        layout=Layout.INLINE,
        phase=Phase.GEOMETRY,
        args=(ArgSpec(name="mode", type=ArgType.ENUM, values=("A", "B")),),
        versions=versions,
        **citation,
    )


class TestCoreSmallCommands:
    """P0400-CMDREMOVED and P0400-CMDPROBEREF: two refusals of the per-version command view.

    P0400-CMDREMOVED (PFS-2135.020): the removal refusal named the newest
    non-removed row over every registered build as "Last documented", so a
    command removed on 26.124 and first documented on 26.125 read "Last documented
    in 26.125". Only an earlier build is now "last documented"; a later one is
    named as a later build.

    P0400-CMDPROBEREF (PFS-2102.024): a per-version grammar override on a
    probe-cited entry wrote "<report>, the <ver> grammar" into ``probe_ref``
    through ``model_copy``, which runs no validator, so the copy carried a
    ``probe_ref`` its own path rule refuses.
    """

    @staticmethod
    def test_p0400_cmdremoved_a_later_build_is_not_last_documented() -> None:
        """P0400-CMDREMOVED: removed on 26.124, documented on 26.125 only."""
        entry = _core_small_commands___entry(
            {
                "26.124": VersionStatus(
                    status=Status.REMOVED, probe_ref=_CORE_SMALL_COMMANDS__REPORT, note="Probed."
                ),
                "26.125": VersionStatus(status=Status.DOCUMENTED),
            },
            manual_ref="FSM-26.125 p.388",
        )
        registry = CommandRegistry(commands={"X_CMD": entry})
        with pytest.raises(CommandNotInVersionError) as refused:
            registry.for_version("26.124")["X_CMD"]
        message = str(refused.value)
        assert "Last documented in 26.125" not in message
        assert "Documented in the later build(s) 26.125." in message

    @staticmethod
    def test_p0400_cmdremoved_an_earlier_build_is_still_last_documented() -> None:
        """P0400-CMDREMOVED: an earlier documented build is still the last one before removal."""
        entry = _core_small_commands___entry(
            {
                "26.100": VersionStatus(status=Status.DOCUMENTED),
                "26.124": VersionStatus(
                    status=Status.REMOVED, probe_ref=_CORE_SMALL_COMMANDS__REPORT, note="Probed."
                ),
                "26.125": VersionStatus(status=Status.DOCUMENTED),
            },
            manual_ref="FSM-26.125 p.388",
        )
        registry = CommandRegistry(commands={"X_CMD": entry})
        with pytest.raises(CommandNotInVersionError, match=r"Last documented in 26\.100\. "):
            registry.for_version("26.124")["X_CMD"]

    @staticmethod
    def test_p0400_cmdprobref_override_keeps_a_valid_probe_ref() -> None:
        """P0400-CMDPROBEREF: a probe-cited entry with an args override keeps its probe_ref."""
        entry = _core_small_commands___entry(
            {
                "26.100": VersionStatus(
                    status=Status.DOCUMENTED,
                    note="FSM-26.000 p.301, this edition's own grammar",
                    args=(ArgSpec(name="mode", type=ArgType.ENUM, values=("A",)),),
                ),
                "26.120": VersionStatus(status=Status.DOCUMENTED),
            },
            probe_ref=_CORE_SMALL_COMMANDS__REPORT,
        )
        resolved = CommandRegistry(commands={"X_CMD": entry}).for_version("26.100")["X_CMD"]
        assert resolved.args[0].values == ("A",)
        assert resolved.manual_ref == ""
        assert resolved.probe_ref == _CORE_SMALL_COMMANDS__REPORT
        assert _PROBE_REF_PATTERN.match(resolved.probe_ref)


class TestCoreSmallExpressions:
    """P0400-EXPRARITY (PFS-2097.001): an [equations] call with the wrong arity is refused when read.

    A call with the wrong number of arguments used to pass the read-time grammar
    and then fail with a TypeError on every row at post. A negative base raised to
    a non-integer power used to return a Python complex, which ``float`` then
    refused with the interpreter's text; it is now a named ValueError.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize(
        "expression",
        ["min(CT)", "max(CT)", "sqrt(CT, CP)", "abs(CT, CP)", "sin(CT, 1)", "degrees(1, 2, 3)"],
    )
    def test_p0400_exprarity_wrong_arity_is_refused_when_read(expression: str) -> None:
        """P0400-EXPRARITY: the read-time check names the function and the count it takes."""
        called = expression.split("(")[0]
        with pytest.raises(InputArtifactError, match=rf"calls {called}\(\) with \d argument"):
            parse_expression(expression)

    @staticmethod
    @pytest.mark.parametrize("expression", ["min(CT, CP)", "max(CT, CP, 1)", "sqrt(CT)", "abs(CT)"])
    def test_p0400_exprarity_right_arity_is_accepted(expression: str) -> None:
        """P0400-EXPRARITY: the arities the functions really take still parse."""
        parse_expression(expression)

    @staticmethod
    def test_p0400_exprarity_negative_base_non_integer_power_is_named() -> None:
        """P0400-EXPRARITY: a complex power is a ValueError naming the base and the power."""
        with pytest.raises(
            ValueError, match="negative base -0.25 raised to the non-integer power 1.5"
        ):
            evaluate_expression("CT**1.5", {"CT": -0.25}.__getitem__)
        assert evaluate_expression("CT**2", {"CT": -0.5}.__getitem__) == 0.25


_CORE_SMALL_FSM__BLADES = ["Hub", "Blade_1", "Blade_2", "Blade_3"]


class TestCoreSmallFsm:
    """P0400-FSMTOKEN (PFS-2104.001): a boundary token that differs from a label only in case names it.

    ``blade_1`` against ``Blade_1, Blade_2, Blade_3`` used to fail the
    case-sensitive exact test and fall through to the family reading, which
    returned all three blades. A case-folded exact match is now tried before the
    family, so the token answers that one surface.
    """  # noqa: E501

    @staticmethod
    def test_p0400_fsmtoken_case_differs_selects_the_one_surface() -> None:
        """P0400-FSMTOKEN: a case-folded exact match wins over the family."""
        assert names_of("blade_1", _CORE_SMALL_FSM__BLADES) == ["Blade_1"]
        assert names_of("BLADE_2", _CORE_SMALL_FSM__BLADES) == ["Blade_2"]
        assert resolve_family(
            "blade_3", {name: i for i, name in enumerate(_CORE_SMALL_FSM__BLADES, 1)}
        ) == (4,)

    @staticmethod
    def test_p0400_fsmtoken_family_word_and_exact_label_still_resolve() -> None:
        """P0400-FSMTOKEN: the family word still selects the family, an exact label itself."""
        assert names_of("blade", _CORE_SMALL_FSM__BLADES) == ["Blade_1", "Blade_2", "Blade_3"]
        assert names_of("Blade", _CORE_SMALL_FSM__BLADES) == ["Blade_1", "Blade_2", "Blade_3"]
        assert names_of("Blade_2", _CORE_SMALL_FSM__BLADES) == ["Blade_2"]
        assert names_of("hub", _CORE_SMALL_FSM__BLADES) == ["Hub"]
        assert names_of("Wing_1", _CORE_SMALL_FSM__BLADES) == []


class TestCoreSmallOptions:
    """P0400-SECONDSFINITE (PFS-2097.006): the positive_seconds validator refuses NaN and infinity.

    ``nan <= 0`` is False, so set_option('qa.probe_timeout_s', float('nan')) was
    accepted and every later probe timed out against NaN.
    """

    @staticmethod
    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_p0400_secondsfinite_nan_and_infinity_are_refused(value: float) -> None:
        """P0400-SECONDSFINITE: NaN and both infinities raise OptionError and change nothing."""
        before = get_option("qa.probe_timeout_s")
        with option_context("qa.probe_timeout_s", get_option("qa.probe_timeout_s")):
            with pytest.raises(OptionError, match="finite"):
                set_option("qa.probe_timeout_s", value)
            assert get_option("qa.probe_timeout_s") == before

    @staticmethod
    def test_p0400_secondsfinite_a_finite_positive_value_is_kept() -> None:
        """P0400-SECONDSFINITE: the control: 30.5 seconds is accepted."""
        with option_context("qa.probe_timeout_s", get_option("qa.probe_timeout_s")):
            set_option("qa.probe_timeout_s", 30.5)
            assert get_option("qa.probe_timeout_s") == 30.5
            for value in (math.nan, math.inf, -math.inf):
                with pytest.raises(OptionError, match="finite"):
                    set_option("qa.probe_timeout_s", value)
                assert get_option("qa.probe_timeout_s") == 30.5


def _core_small_review___field(
    p_prime_outlet=None, stations: tuple[float, ...] = (0.0, 0.3)
) -> LatticeFields:
    lattice = build_lattice(tip_radius=1.0, stations=stations, lateral_radius=None)
    shape = (len(stations), lattice.n_r, lattice.n_psi)
    p_prime = np.zeros(shape)
    if p_prime_outlet is not None:
        p_prime[1] = p_prime_outlet
    return lattice_fields(
        lattice,
        fields={"u": np.ones(shape), "v": np.ones(shape), "w": np.ones(shape), "p_prime": p_prime},
    )


class TestCoreSmallReview:
    """P0400 review: reproduce incomplete fixes and byte-preservation regressions."""

    @staticmethod
    def test_p0400_indexed_boundary_never_expands_to_family() -> None:
        labels = {"Blade_1": 1, "Blade_2": 2}
        assert names_of("blade_1", list(labels)) == ["Blade_1"]
        assert names_of("blade", list(labels)) == list(labels)
        assert names_of("Tail_7", list(labels)) == []
        with pytest.raises(MeshReadError, match="Blade_9.*Blade_1.*Blade_2"):
            resolve_family("Blade_9", labels)

    @staticmethod
    def test_p0400_station_roundoff_is_resolved_without_nearest_guess() -> None:
        fields = _core_small_review___field(2.0)
        expected = axial_force(fields, 1.0, 1.0, inlet=0.0, outlet=0.3)
        assert expected > 0
        assert axial_force(fields, 1.0, 1.0, inlet=0.0, outlet=0.1 * 3) == expected
        with pytest.raises(FarfieldInputError, match="0.4.*available.*0.3"):
            axial_force(fields, 1.0, 1.0, inlet=0.0, outlet=0.4)

    @staticmethod
    @pytest.mark.parametrize("method", ["quadrature", "harmonic"])
    @pytest.mark.parametrize("axis,sign", [("y", 1), ("z", -1)])
    def test_p0400_moments_follow_right_handed_cross_product(method, axis, sign) -> None:
        psi = _core_small_review___field().psi
        loading = np.cos(psi) if axis == "y" else np.sin(psi)
        fields = _core_small_review___field(
            np.broadcast_to(loading, _core_small_review___field().shape[1:])
        )
        result = in_plane_moment(fields, 1.0, 1.0, inlet=0.0, outlet=0.3, axis=axis, method=method)
        assert float(result.loading_term) * sign > 0
        edges = fields.ring_edges
        area = float(edges[-1] ** 2 - edges[0] ** 2) * np.pi
        assert float(result.moment_arm_term) == pytest.approx(-sign * 0.3 * area)

    @staticmethod
    @pytest.mark.parametrize("function", [to_counts, spurious_diagnostic])
    def test_p0400_counts_require_an_explicit_reference_area(function) -> None:
        assert inspect.signature(function).parameters["s_ref"].default is inspect.Parameter.empty

    @staticmethod
    @pytest.mark.parametrize("key", ["rho_inf", "v_inf", "s_ref"])
    @pytest.mark.parametrize("value", [0.0, -1.0, np.nan, np.inf])
    def test_p0400_counts_refuse_undefined_scales(key, value) -> None:
        values = {"rho_inf": 1.2, "v_inf": 30.0, "s_ref": 2.0, key: value}
        with pytest.raises(FarfieldInputError, match=key):
            to_counts(1.0, **values)

    @staticmethod
    def test_p0400_counts_use_the_stated_area() -> None:
        assert to_counts(1.0, rho_inf=2.0, v_inf=10.0, s_ref=4.0) == 25.0
        assert spurious_diagnostic(2.0, 1.0, rho_inf=2.0, v_inf=10.0, s_ref=4.0) == 25.0

    @staticmethod
    @pytest.mark.parametrize("ending", ["\n", "\r\n", ""])
    def test_p0400_version_splice_preserves_final_terminator(ending) -> None:
        text = 'X:\n  versions:\n    "26.120": {status: documented}' + ending
        result = insert_version_row(
            text, command="X", canonical="26.123", status="documented", note="FSM-26.123 p.1"
        )
        row = '    "26.123": {status: documented, note: "FSM-26.123 p.1"}'
        assert result == text.removesuffix(ending) + (ending or "\n") + row + ending

    @staticmethod
    def test_p0400_quiet_post_diagnostics_preserves_requested_data(tmp_path: Path, capsys) -> None:
        from pyflightstream.run.cli import main
        from pyflightstream.workspace import CampaignWorkspace
        from tests.tier1_offline.test_matrix_cli import _record_a_converged_polar
        from tests.tier1_offline.test_post_products import LOADS

        workspace = CampaignWorkspace.init(tmp_path / "camp")
        _record_a_converged_polar(workspace, "3207", {"alpha": -2.0}, LOADS)
        (workspace.root / "pyfs.toml").write_text('[log]\nconsole = "quiet"\n', encoding="utf-8")
        args = ["post", "--workspace", str(workspace.root), "--diagnostics"]
        assert main([*args, "--log-level", "normal"]) == 0
        normal = capsys.readouterr().out
        assert normal.strip()
        assert main(args) == 0
        assert capsys.readouterr().out == normal


class TestCoreSmallReviewQa:
    """P0400 review: probes must use configured timeouts and prove continued execution."""

    @staticmethod
    @pytest.mark.parametrize("explicit,expected", [(None, 7.0), (11.0, 11.0)])
    def test_p0400_probe_timeout_uses_option_unless_explicit(tmp_path, explicit, expected):
        seen = []

        class TimedSolver(_CoreSmallReviewQaFakeFlightStream):
            def run_script(self, script_path, working_dir, timeout_s=None):
                seen.append(timeout_s)
                return super().run_script(script_path, working_dir, timeout_s)

        with option_context("qa.probe_timeout_s", 7.0):
            kwargs = {} if explicit is None else {"timeout_s": explicit}
            probe_version(
                "26.120", workroot=tmp_path, executor=TimedSolver(), commands=[], **kwargs
            )
        assert seen == [expected]

    @staticmethod
    def test_p0400_unused_case_timeout_is_not_advertised():
        with pytest.raises(OptionError, match="no option is registered"):
            get_option("qa.case_timeout_s")

    @staticmethod
    def test_p0400_missing_end_sentinel_cannot_verify_an_observed_effect(tmp_path: Path):
        class MissingEnd(_CoreSmallReviewQaFakeFlightStream):
            def _say(self, message):
                if message == "PYFS_PROBE_END_PRINT":
                    return
                super()._say(message)

        results, _ = _core_small_review_qa__run_pilot(tmp_path, MissingEnd(), commands=["PRINT"])
        result = results["PRINT"]
        assert result.outcome is ProbeOutcome.BROKEN
        assert "END sentinel" in result.detail

    @staticmethod
    def test_p0400_section_export_requires_a_filename_and_is_not_verified():
        from pyflightstream.commands import CommandRegistry, Status

        entry = CommandRegistry.load().commands["EXPORT_SURFACE_SECTIONS"]
        assert [(arg.name, arg.own_line) for arg in entry.args] == [
            ("index", False),
            ("filename", True),
        ]
        assert entry.versions["26.125"].status is Status.DOCUMENTED
