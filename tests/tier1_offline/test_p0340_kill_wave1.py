"""Tier 1, 0.34.0 wave 1: the kill tests of the deep QA mutation pass.

The pass (45 mutants over the wave 1 range) left eleven real gaps. Each test
here is the one the pass named as missing, and each was shown red against its
mutant, with the original bytes restored, before it was committed.

* P1 to P5: the argparse surface of every ``pyfs-*`` console parser is held to
  a golden made from v0.33.1 (``fixtures/cli_actions_0331.json``). A 0.33.1
  action must exist unchanged; an added action passes.
* Q2, Q3, Q5: the QA spec catalog's rendered build lines and requires levels
  are held to a reviewed golden (``fixtures/qa_spec_builds.json``), each
  effect needle occurs in its own build line, and a transform spec whose
  effect is a changed mesh is not an identity.
* F2: the signed tip column keeps the sign of the largest magnitude, through
  the public coupling step (the helper that builds the column is private and
  the private-name baseline may not rise). The first-wins rule for exactly
  equal magnitudes of opposite sign cannot be built through that route, since
  two solved blades never deflect by bit-equal amounts.
* C3, C4: the ``body_axes`` refusals name their cause.

C1 (PortBoundary dropped from the cases root) is not repeated here:
``test_p0340_cases_cut.py`` already carries it in the parametrization of
``test_a_moved_name_is_one_object_at_both_paths``, and the mutant makes the
whole package unimportable, which no assertion can outlive.

To regenerate the CLI golden from an export of v0.33.1, run with that
checkout's ``src`` on ``PYTHONPATH``::

    python -c "import json, sys; sys.path.insert(0, 'tests/tier1_offline');
    import test_p0340_kill_wave1 as t; print(json.dumps(t.dump_every_parser(),
    indent=1, sort_keys=True))"
"""

from __future__ import annotations

import argparse
import csv
import importlib
import io
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.cases.settings import ReferenceData
from pyflightstream.fsi import driver
from pyflightstream.fsi.loads import SectionFamilyMap
from tests.tier1_offline.test_fsi_driver import CALL2, driver_config, stage_run

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

# --------------------------------------------------------------- the CLI surface

_ENTRY_POINTS = {
    "pyfs-qa": "pyflightstream.qa.cli",
    "pyfs-fsi": "pyflightstream.fsi.cli",
    "pyfs-workspace": "pyflightstream.workspace.cli",
    "pyfs-matrix": "pyflightstream.run.cli",
}


class _Captured(BaseException):
    """Raised by the patched parse call to hand the built parser out."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__("parser captured")
        self.parser = parser


def _capture_parser(module_name: str) -> argparse.ArgumentParser:
    """Return the parser the entry point builds, through its own main()."""
    module = importlib.import_module(module_name)
    real_parse_args = argparse.ArgumentParser.parse_args
    real_parse_known = argparse.ArgumentParser.parse_known_args

    def grab(self, *args, **kwargs):
        raise _Captured(self)

    argparse.ArgumentParser.parse_args = grab  # type: ignore[method-assign]
    argparse.ArgumentParser.parse_known_args = grab  # type: ignore[method-assign]
    try:
        module.main(["--help"])
    except _Captured as caught:
        return caught.parser
    finally:
        argparse.ArgumentParser.parse_args = real_parse_args  # type: ignore[method-assign]
        argparse.ArgumentParser.parse_known_args = real_parse_known  # type: ignore[method-assign]
    raise AssertionError(f"{module_name}.main never parsed its arguments")


def _plain(value):
    """A JSON-safe form of a default or a choice, stable across runs."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    # A default taken from the working directory when the parser is built
    # (pyfs-fsi --dir) is recorded as that, not as the machine's path, so the
    # golden reads the same on every checkout and platform.
    if isinstance(value, Path) and value == Path.cwd():
        return "<CWD>"
    if isinstance(value, list | tuple | set | frozenset):
        items = [_plain(v) for v in value]
        return sorted(items, key=repr) if isinstance(value, set | frozenset) else items
    return repr(value)


def _walk(parser: argparse.ArgumentParser, path: str, out: dict[str, dict]) -> None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                _walk(sub, f"{path} {name}".strip(), out)
            continue
        key = f"{path}|{action.dest}|{','.join(action.option_strings)}"
        out[key] = {
            "action": type(action).__name__,
            "dest": action.dest,
            "option_strings": list(action.option_strings),
            "default": _plain(action.default),
            "choices": None if action.choices is None else _plain(list(action.choices)),
            "nargs": _plain(action.nargs),
            "type": getattr(action.type, "__name__", None) if action.type else None,
            "required": bool(action.required),
        }


def dump_every_parser() -> dict[str, dict[str, dict]]:
    """Every argparse action of every console parser, keyed by program and path."""
    dump: dict[str, dict[str, dict]] = {}
    for program, module_name in _ENTRY_POINTS.items():
        actions: dict[str, dict] = {}
        _walk(_capture_parser(module_name), "", actions)
        dump[program] = actions
    return dump


_GOLDEN_0331 = json.loads((FIXTURES / "cli_actions_0331.json").read_text(encoding="utf-8"))
_CURRENT = None


def _current() -> dict[str, dict[str, dict]]:
    global _CURRENT
    if _CURRENT is None:
        _CURRENT = dump_every_parser()
    return _CURRENT


_GOLDEN_KEYS = [(p, k) for p, actions in sorted(_GOLDEN_0331.items()) for k in sorted(actions)]


def test_the_golden_is_not_empty_and_covers_every_console_parser():
    # A golden that read nothing would pass every comparison below.
    assert set(_GOLDEN_0331) == set(_ENTRY_POINTS)
    assert len(_GOLDEN_KEYS) > 200


@pytest.mark.parametrize(("program", "key"), _GOLDEN_KEYS)
def test_a_0331_cli_action_exists_unchanged(program, key):
    # P0340-KILL-P1..P5: a changed default, a dropped choice or a dropped
    # option fails; an action the release adds is not in the golden and passes.
    current = _current()[program]
    assert key in current, f"{program}: the 0.33.1 action {key!r} is gone"
    want = _GOLDEN_0331[program][key]
    got = current[key]
    assert got == want, f"{program}: {key!r} changed from {want} to {got}"


def test_the_comparison_would_see_a_changed_default_and_a_dropped_choice():
    # The control: the same comparison refuses a doctored copy of the current
    # surface, so a comparison that accepted everything cannot pass.
    doctored = json.loads(json.dumps(_current()["pyfs-matrix"]))
    with_default = next(k for k, v in doctored.items() if v["default"] == 10)
    doctored[with_default]["default"] = 5
    with_choices = next(k for k, v in doctored.items() if v["choices"] and len(v["choices"]) > 1)
    doctored[with_choices]["choices"] = doctored[with_choices]["choices"][1:]
    changed = [k for k, v in doctored.items() if v != _current()["pyfs-matrix"][k]]
    assert sorted(changed) == sorted([with_default, with_choices])


def test_the_matrix_parser_parses_the_choices_and_defaults_the_pass_named():
    # P0340-KILL-P2/P4/P5: the surface the golden pins, parsed end to end.
    parser = _capture_parser("pyflightstream.run.cli")
    assert parser.parse_args(["sync", "fsm"]).level == "fsm"
    deleted = parser.parse_args(["delete-sims", "1", "--matrix-products", "regenerate"])
    assert deleted.matrix_products == "regenerate"
    assert parser.parse_args(["delete-sims", "1"]).matrix_products is None
    assert parser.parse_args(["space-in-use"]).top == 15


# ------------------------------------------------------------------ the QA specs

_SPEC_GOLDEN_PATH = FIXTURES / "qa_spec_builds.json"


def _spec_version(command: str) -> str:
    """The build a spec is rendered on, chosen as the existing probe test chooses it."""
    from pyflightstream.commands import CommandRegistry

    registry = CommandRegistry.load()
    if command in registry.for_version("26.120"):
        return "26.120"
    if command in registry.for_version("26.124"):
        return "26.124"
    # A command the 26.125 manual documents first (FR-423) is built on 26.125;
    # a command the manual dropped at 26.12 on the last build that holds it.
    return "26.125" if command in registry.for_version("26.125") else "26.101"


_INSTRUMENT_FILES = (
    "log_before.txt",
    "log_after.txt",
    "dump_before.txt",
    "dump_after.txt",
)


# A path inside the probe's work folder, up to the next blank or quote.
_WORKDIR_PATH = re.compile(r"<WORKDIR>[^\s\"]*")


def _target_lines(lines: list[str], workdir: Path) -> list[str]:
    """The lines of the target command alone: the log and dump instruments are dropped.

    An instrument is a command line followed by the path of one of the
    probe's own files, so the pair is dropped; blank separators are dropped.
    The work folder becomes ``<WORKDIR>`` and every separator in a path under
    it becomes ``/``, so the golden is the same on Windows and on Linux.
    """
    here = str(workdir.resolve())
    kept: list[str] = []
    skip_next = False
    for index, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if line in ("EXPORT_LOG", "OUTPUT_SETTINGS_AND_STATUS") and following.endswith(
            _INSTRUMENT_FILES
        ):
            skip_next = True
            continue
        if line:
            masked = line.replace(here, "<WORKDIR>").replace(here.replace("\\", "/"), "<WORKDIR>")
            kept.append(_WORKDIR_PATH.sub(lambda m: m.group(0).replace("\\", "/"), masked))
    return kept


def _render_specs(workroot: Path) -> dict[str, dict]:
    """Each spec's target lines as the probe script renders them, and its requires level."""
    from pyflightstream.qa import PROBE_SPECS
    from pyflightstream.qa.probes import generate_probe_script

    fsm = workroot / "dummy.fsm"
    out: dict[str, dict] = {}
    for command, spec in sorted(PROBE_SPECS.items()):
        workdir = workroot / command
        workdir.mkdir()
        script = generate_probe_script(spec, _spec_version(command), workdir, fsm=fsm)
        lines = script.render().splitlines()
        begin = next(i for i, ln in enumerate(lines) if ln == f"PRINT PYFS_PROBE_BEGIN_{command}")
        end = next(i for i, ln in enumerate(lines) if ln == f"PRINT PYFS_PROBE_END_{command}")
        target = _target_lines(lines[begin + 1 : end], workdir)
        out[command] = {
            "version": _spec_version(command),
            "requires": getattr(spec.requires, "name", str(spec.requires)),
            "build": target,
        }
    return out


@pytest.fixture(scope="module")
def rendered_specs(tmp_path_factory):
    return _render_specs(tmp_path_factory.mktemp("specs"))


def test_every_qa_spec_renders_the_reviewed_build_line_and_requires_level(rendered_specs):
    # P0340-KILL-Q2/Q5: an edited argument value or prelude tier of a spec is
    # a reviewed golden diff, not a silent change that only a licensed probe
    # (after the seat is spent) would show.
    golden = json.loads(_SPEC_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert len(golden) > 100
    assert set(rendered_specs) >= set(golden), sorted(set(golden) - set(rendered_specs))
    for command, want in golden.items():
        assert rendered_specs[command] == want, command


def _needles() -> dict[str, str]:
    """The regex each sheet_matches spec looks for, read off the assertion's closure."""
    from pyflightstream.qa import PROBE_SPECS

    found: dict[str, str] = {}
    for command, spec in PROBE_SPECS.items():
        check = spec.assert_effect
        if getattr(check, "__qualname__", "").startswith("sheet_matches."):
            patterns = [
                c.cell_contents for c in check.__closure__ if isinstance(c.cell_contents, str)
            ]
            assert len(patterns) == 1, command
            found[command] = patterns[0]
    return found


def _value_digits(text: str) -> str:
    """The significant digits of a number written as 12.5, 0.1250E+02 or .012."""
    mantissa = re.split(r"[eE]", text)[0]
    return re.sub(r"\D", "", mantissa).lstrip("0")


def _needle_value(pattern: str) -> str | None:
    """The numeric value a sheet needle waits for, or None for a word."""
    tail = re.split(r"\\s\+", pattern)[-1]
    tail = tail.replace("\\.", ".").replace("\\+", "+").replace("\\b", "")
    return tail if re.fullmatch(r"-?\d*\.?\d+([eE][+-]?\d+)?", tail) else None


# The count this needle waits for is the row count of the lattice file the
# spec writes beside the command (two rows), not an argument of the command.
_COUNT_FROM_A_FILE = {"PROBE_POINTS_IMPORT"}


def test_every_numeric_effect_needle_is_the_value_its_build_line_writes(rendered_specs):
    # P0340-KILL-Q3: NEW_PROBE_POINT's build said 1.3345 while its needle
    # waited for 0.1234E+01, a probe that could only break. The digits of a
    # numeric needle are a prefix of the digits of a number in the build line.
    checked = []
    for command, pattern in _needles().items():
        value = _needle_value(pattern)
        if value is None or command in _COUNT_FROM_A_FILE:
            continue
        digits = _value_digits(value)
        line_numbers = re.findall(
            r"-?\d*\.?\d+(?:[eE][+-]?\d+)?", " ".join(rendered_specs[command]["build"])
        )
        if not digits:
            continue  # a count of zero is state the target leaves, not a value it writes
        assert any(_value_digits(n).startswith(digits) for n in line_numbers), (
            f"{command}: the needle {pattern!r} waits for a value that "
            f"{rendered_specs[command]['build']} does not write"
        )
        checked.append(command)
    assert {"NEW_PROBE_POINT", "SOLVER_SET_AOA", "SOLVER_SET_CONVERGENCE"} <= set(checked)
    assert len(checked) >= 10


def test_the_needle_comparison_refuses_a_needle_its_line_does_not_write():
    # The control for the test above: the 1.3345 mutant is refused by the digits rule.
    assert _value_digits("0.1234E+01").startswith("1234")
    assert not _value_digits("1.3345").startswith(_value_digits("0.1234E+01"))
    assert _needle_value(r"Number of Probe Points:\s+3\b") == "3"
    assert _needle_value(r"Solver mode:\s+Steady") is None


@pytest.mark.parametrize("command", ["ROTATE_SURFACE", "SURFACE_ROTATE"])
def test_a_transform_spec_that_asserts_a_changed_mesh_is_not_an_identity(rendered_specs, command):
    # P0340-KILL-Q2: a rotation by 0 degrees leaves the saved mesh as it was,
    # so a probe asserting that the mesh changed could only break.
    from pyflightstream.qa import PROBE_SPECS

    assert PROBE_SPECS[command].assert_effect.__qualname__.startswith("fsm_changed")
    build = rendered_specs[command]["build"]
    if command == "ROTATE_SURFACE":
        tokens = build[0].split()
        angle = float(tokens[next(i for i, t in enumerate(tokens) if t in {"X", "Y", "Z"}) + 1])
    else:
        angle = float(next(ln.split()[1] for ln in build if ln.startswith("ANGLE ")))
    assert angle != 0.0
    assert abs(angle) % 360.0 != 0.0


# ------------------------------------------------------------------------ FSI tip


def _mixed_sign_loads(iteration: int) -> str:
    """The real export of call 2 with its second family a second blade loaded the other way.

    The first 50 rows are blade one as the fixture has them; the last 50 are
    the same rows with Fx, Fz and the moment multiplied by minus 1.5, so blade
    two deflects the opposite way by a larger amount.
    """
    lines = CALL2.splitlines()
    rows = [i for i, line in enumerate(lines) if re.match(r"\s+-?\d\.\d+E[-+]\d+,", line)]
    assert len(rows) == 100, len(rows)
    for blade_row, other_row in zip(rows[:50], rows[50:], strict=True):
        values = [float(v) for v in lines[blade_row].strip().rstrip(",").split(",")]
        values[4:7] = [-1.5 * v for v in values[4:7]]
        lines[other_row] = "      " + ", ".join(f"{v:.4E}" for v in values) + ","
    text = "\n".join(lines) + "\n"
    return re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{iteration}", text)


def test_the_signed_tip_keeps_the_sign_of_the_blade_with_the_largest_magnitude(tmp_path):
    # P0340-KILL-F2, through the public coupling step: blade one bends one way
    # and blade two bends the other way by more. A max over the signed values
    # would write blade one's positive tip as the signed column.
    stage_run(tmp_path, driver_config().model_copy(update={"blade_count": 2}))
    (tmp_path / driver.FAMILY_MAP_FILE).write_text(
        SectionFamilyMap.uniform(blade_count=2, sections_per_blade=50).model_dump_json(indent=2)
        + "\n",
        encoding="utf-8",
    )
    solved = []
    for call in range(4):
        (tmp_path / driver.LOADS_FILE).write_text(
            _mixed_sign_loads(100 + 40 * call), encoding="utf-8"
        )
        result = driver.coupling_step(tmp_path)
        if result.solutions is not None:
            solved.append(result)
    assert solved, "no call of the two-blade run solved"
    text = (tmp_path / driver.LOG_FILE).read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    rows = list(csv.DictReader(io.StringIO(body)))
    for result, row in zip(solved, rows[-len(solved) :], strict=True):
        tips = [sol.flap_deflection_m[-1] for sol in result.solutions]
        assert tips[0] > 0.0 > tips[1] and abs(tips[1]) > abs(tips[0]), tips
        assert row["tip_flap_signed_m"] == f"{tips[1]:.6e}"
        assert row["tip_flap_m"] == f"{abs(tips[1]):.6e}"


# -------------------------------------------------------------------- body axes


def _reference_with_axes(axes):
    return ReferenceData(area=1.0, length=1.0, body_axes=axes)


def test_body_axes_refuse_an_unknown_rate_and_name_it():
    # P0340-KILL-C4
    with pytest.raises(ValidationError, match=r"surge.*one of roll, pitch or yaw"):
        _reference_with_axes({"surge": "X"})


def test_body_axes_refuse_one_axis_given_twice_and_say_so():
    # P0340-KILL-C3
    with pytest.raises(ValidationError, match=r"one axis twice.*same axis"):
        _reference_with_axes({"roll": "X", "pitch": "X", "yaw": "Z"})


def test_body_axes_accept_three_distinct_axes_and_normalise_them():
    # The control: the refusals above are not a validator that refuses everything.
    got = _reference_with_axes({" Roll ": "x", "pitch": "Y", "yaw": "z"}).body_axes
    assert got == {"roll": "X", "pitch": "Y", "yaw": "Z"}
