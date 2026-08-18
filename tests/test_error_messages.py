"""Tier 1: wording pins of the main didactic refusals.

Pipeline role: quality gate on the didactic policy (CLAUDE.md item 8:
error messages name the physical or version cause). Following the
xarray ``test_error_messages`` pattern, every test here triggers a
refusal through the public API and pins the operative content of the
message with ``pytest.raises(match=...)``: the cause the user must
understand and the remedy the message offers. A refactor that keeps
the exception type but drops the explanation fails here, not in a
user's terminal.

Scope: the refusals users meet first (versions, solver_settings, the
workspace input library, the run-matrix reader). Behavioral tests for
the same code paths live with their subsystems; this module owns only
the wording.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases.matrix import MatrixError, read_matrix
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.versions import FsVersion, UnknownVersionError, resolve
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError

MATRIX_FIXTURE = Path(__file__).parent / "fixtures" / "matrix.fs"


# --- versions ---------------------------------------------------------------


def test_unregistered_version_lists_the_known_versions_and_the_authority():
    """The refusal teaches where versions come from, not just that one is missing."""
    with pytest.raises(
        UnknownVersionError,
        match=r"'27\.000' is not registered\. Known versions, in release order:"
        r".*commands/_meta\.yaml, which is the only ordering authority",
    ):
        resolve("27.000")


def test_malformed_canonical_identifier_names_the_scheme():
    """A two-digit fraction is refused with the scheme and a worked example."""
    with pytest.raises(
        UnknownVersionError,
        match=r"canonical YY\.XXX scheme, the vendor major with exactly three "
        r"fractional digits \(example: 26\.120\)",
    ):
        FsVersion(canonical="26.12", alias="26.12", index=0)


# --- solver_settings --------------------------------------------------------


def test_solver_settings_empty_vorticity_selection_names_the_two_drag_methods():
    """An empty list is refused by naming the omission that means the default."""
    script = Script(version="26.120")
    with pytest.raises(
        CommandArgumentError,
        match=r"vorticity_drag_boundaries is an empty sequence.*Omit the argument "
        r"\(or pass None\).*surface pressure integration \(SRC-003 p\.202\).*"
        r"selection filter matched no boundary",
    ):
        helpers.solver_settings(script, vorticity_drag_boundaries=[])


def test_solver_settings_toggle_refusal_names_both_vocabularies():
    """A flag written in the solver's words is read, anything else refused."""
    script = Script(version="26.120")
    with pytest.raises(
        CommandArgumentError,
        match=r"solver_settings: viscous_coupling takes True or False, or the solver's "
        r"own ENABLE or DISABLE; got 'YES'",
    ):
        helpers.solver_settings(script, viscous_coupling="YES")


def test_solver_settings_mode_refusal_names_both_regimes():
    script = Script(version="26.120")
    with pytest.raises(
        CommandArgumentError,
        match=r"mode takes STEADY or UNSTEADY, got 'CRUISE': the solver time regime "
        r"is one of the two \(SRC-003 p\.341\)",
    ):
        helpers.solver_settings(script, mode="CRUISE")


def test_unsteady_without_time_stepping_names_both_missing_parameters():
    """Physical time stepping needs the step count and the step size together."""
    script = Script(version="26.120")
    with pytest.raises(
        CommandArgumentError,
        match=r"mode='UNSTEADY' needs both time_iterations and delta_time: physical "
        r"time stepping is defined by the step count and the step size "
        r"\(SRC-003 p\.341\)",
    ):
        helpers.solver_settings(script, mode="UNSTEADY")


def test_time_stepping_outside_unsteady_mode_offers_both_remedies():
    script = Script(version="26.120")
    with pytest.raises(
        CommandArgumentError,
        match=r"time_iterations and delta_time belong to the unsteady solver; pass "
        r"mode='UNSTEADY' with them, or drop them for a steady run",
    ):
        helpers.solver_settings(script, time_iterations=10)


# --- workspace input library ------------------------------------------------


def test_path_like_artifact_id_teaches_the_id_model(tmp_path):
    """Ids select files inside the library; they are never paths."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    with pytest.raises(
        InputArtifactError,
        match=r"not a valid artifact id: ids are file name stems.*never a path",
    ):
        workspace.resolve_reference("../outside")


def test_missing_artifact_in_an_empty_library_offers_the_init_remedy(tmp_path):
    """An empty library points at the tool that creates it, not at a bare miss."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    with pytest.raises(
        InputArtifactError,
        match=r"no reference artifact with id 'wing_v9'.*holds no reference artifacts "
        r"yet.*pyfs-workspace init",
    ):
        workspace.resolve_reference("wing_v9")


def test_missing_artifact_lists_what_the_library_holds(tmp_path):
    """The miss message enumerates the ids that would have worked."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "references" / "wing_v2.toml").write_text("", encoding="utf-8")
    with pytest.raises(
        InputArtifactError,
        match=r"no reference artifact with id 'wing_v9'; available reference ids: wing_v2",
    ):
        workspace.resolve_reference("wing_v9")


# --- run-matrix reader ------------------------------------------------------


def test_unknown_sweep_code_states_the_evidence_rule(tmp_path):
    """Extending the sweep mapping is an evidence question, and the message says so."""
    munged = tmp_path / "matrix.fs"
    munged.write_text(
        MATRIX_FIXTURE.read_text(encoding="utf-8").replace("AL/BE", "ZZ/BE"),
        encoding="utf-8",
    )
    with pytest.raises(
        MatrixError,
        match=r"SWEEP_TYPE code\(s\) ZZ are not among the verified codes "
        r"\(AL, BE\); extending the mapping needs evidence",
    ):
        read_matrix(munged)


def test_foreign_header_names_the_verified_layout(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("POL | ANGLE\n9001 | 4.0\n", encoding="utf-8")
    with pytest.raises(
        MatrixError,
        match=r"header does not match the verified 15-column layout; expected ",
    ):
        read_matrix(bad)


def test_contentless_matrix_file_is_named_as_such(tmp_path):
    empty = tmp_path / "matrix.fs"
    empty.write_text("\n----\n\n", encoding="utf-8")
    with pytest.raises(MatrixError, match=r"holds no matrix content"):
        read_matrix(empty)


# --- the diagnosis composer (INC-20260809-2230) -----------------------------
#
# A solver that never reaches the script writes no log, so every channel
# the harness read was empty and the one channel that carried the answer
# was discarded. These pin the message that misled, from the outside.


def _pre_script_failure():
    """The 2026-08-09 run, reconstructed field for field.

    Timed out and killed, no exported log, no FlightStreamLog.txt, empty
    stderr, and a banner plus a licence report on standard output. Every
    value here is what the real run produced.
    """
    from pyflightstream.run import ExecutionResult

    return ExecutionResult(
        return_code=None,
        wall_time_s=120.2,
        timed_out=True,
        log_text=None,
        stdout=(
            "FlightStream version \x0025.0, build #12162024\n"
            "Software copyrights: Altair, 2024.\n"
            "Attempting feature license checkout...Not available. "
            "Attempting EDU feature checkout...Success!\n"
        ),
        stderr="",
        timeout_s=120.0,
    )


def test_a_run_that_never_reached_the_script_still_says_what_the_solver_said():
    """Standard output is the only channel a pre-script failure leaves."""
    diagnosis = _pre_script_failure().diagnosis()
    assert "timed out" in diagnosis
    assert "120.2" in diagnosis
    assert "EDU feature checkout...Success!" in diagnosis, (
        "the diagnosis drops standard output, which is the only channel a run that "
        "never reached the script writes to"
    )
    assert "\x00" not in diagnosis, "a NUL byte reaches the reader as an invisible space"


def test_the_baseline_refusal_quotes_the_solver_instead_of_naming_suspects(tmp_path):
    """The refusal that sent a day after a licence that was never held.

    It used to say the environment was unusable and offer three causes,
    one of them the licence checkout, while holding the line that said
    the checkout succeeded. Naming candidate causes it cannot rank is
    the defect; quoting the solver is the fix.
    """
    import pytest

    from pyflightstream.qa import probe_version
    from pyflightstream.qa.probes import ProbeEnvironmentError

    class SilentSolver:
        """Starts, banners, accepts nothing, and is killed at the limit."""

        def run_script(self, script_path, working_dir, timeout_s=None):
            return _pre_script_failure()

    with pytest.raises(ProbeEnvironmentError) as excinfo:
        probe_version("26.120", workroot=tmp_path / "probes", executor=SilentSolver(), commands=[])
    message = str(excinfo.value)
    assert "EDU feature checkout...Success!" in message, (
        "the refusal does not quote what the solver said, so a reader cannot rule out the licence"
    )
    assert "license checkout, or log export" not in message, (
        "the refusal still offers candidate causes it cannot rank, and one of them is "
        "contradicted by the output it now quotes"
    )


def test_no_module_composes_its_own_diagnosis_from_the_captured_channels():
    """One composer, enforced, because four sites each wrote their own.

    Four independent authors reached for
    ``log_text or stderr or return code`` and all four omitted stdout.
    That is an absent abstraction rather than four oversights, so the
    guard is on the shape and not on the four sites: reading two or more
    captured channels in one expression is composing a diagnosis, and
    there is one place for that.
    """
    import ast
    from pathlib import Path

    channels = {"log_text", "stderr", "stdout", "return_code"}
    home = Path("src/pyflightstream/run/__init__.py")
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in sorted((root / "src" / "pyflightstream").rglob("*.py")):
        if path.name == home.name and path.parent.name == "run":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.BoolOp):
                continue
            read = {
                child.attr
                for child in ast.walk(node)
                if isinstance(child, ast.Attribute) and child.attr in channels
            }
            if len(read) >= 2:
                offenders.append(f"{path.relative_to(root)}:{node.lineno} reads {sorted(read)}")
    assert not offenders, (
        "these compose a diagnosis from the captured channels by hand:\n  "
        + "\n  ".join(offenders)
        + "\n\nCall ExecutionResult.diagnosis(). Every hand-rolled chain so far has "
        "omitted standard output, which is the only channel a run that never reached "
        "the script writes to (INC-20260809-2230)."
    )


def test_the_diagnosis_carries_every_channel_and_not_the_first_one_it_finds():
    """First-match was the defect, in its general form.

    The four chains this composer replaced were `a or b or c`, which
    stops at the first non-empty channel. That is why standard output
    never appeared even on runs that had all three: an exported log
    existed, so nothing looked further. A composer that kept the
    or-chain's short circuit would read as fixed and behave the same
    way on every run that writes a log.
    """
    from pyflightstream.run import ExecutionResult

    result = ExecutionResult(
        return_code=3,
        wall_time_s=2.0,
        timed_out=False,
        log_text="Unknown command SET_NOTHING",
        stdout="license feature checkout SUCCESS",
        stderr="warning: deprecated flag",
        timeout_s=60.0,
    )
    diagnosis = result.diagnosis()
    for expected in (
        "return code 3",
        "Unknown command SET_NOTHING",
        "warning: deprecated flag",
        "license feature checkout SUCCESS",
    ):
        assert expected in diagnosis, f"{expected!r} missing from {diagnosis!r}"


# --- the class: a library refusal never names a flag ALONE -------------------


def _library_refusals_naming_a_flag() -> list[tuple[str, str, str]]:
    """Return every raise site under src/ whose message carries a --flag.

    Yields ``(site, flag, message)``. The CLI modules are excluded by
    name: a CLI is exactly the layer that OWNS its flags, and
    ``pyflightstream/qa/cli.py`` translates library parameter names into
    them deliberately.
    """
    import ast
    import re

    flag_pattern = re.compile(r"--[a-z][a-z0-9-]*")
    src = Path(__file__).resolve().parents[1] / "src"
    found: list[tuple[str, str, str]] = []
    for module in sorted(src.rglob("*.py")):
        if module.name.endswith("cli.py"):
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if node.__class__.__name__ != "Raise" or node.exc is None:
                continue
            # ONE PASS, NOT TWO. `ast.walk` already descends into a
            # JoinedStr and visits its Constant children, so expanding
            # the JoinedStr as well counted every f-string message twice
            # and reported one defect as two.
            message = " ".join(
                piece.value
                for piece in ast.walk(node.exc)
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str)
            )
            for flag in flag_pattern.findall(message):
                site = f"{module.relative_to(src).as_posix()}:{node.lineno}"
                found.append((site, flag, message))
    return found


def test_no_library_refusal_names_a_command_line_flag_alone():
    """A message a Python caller cannot act on is a message that misleads.

    `run_physics` was corrected on 2026-08-17 to name `cases` and
    `smi_root` rather than `--cases` and `--smi-root`, and the fix was
    made at the two sites the review named. The CLASS was not swept, and
    one live instance sat one screen below the corrected one: an SMI case
    runner telling a caller to "pass --smi-root", a flag that exists only
    on a command line the library knows nothing about.

    THE RULE IS MECHANICAL AND CARRIES NO EXEMPTION LIST, which is the
    second version of this guard. The first held a set of modules allowed
    to name a flag, and a module in that set could then name a flag alone
    anywhere in it: restoring the original defect, in the very module the
    defect came from, would have passed. A per-module exemption cannot
    express a per-message rule.

    So the message itself is asked: a refusal naming ``--some-flag`` must
    also name ``some_flag``, the parameter a Python caller can actually
    pass. That is the shape `qa/probes.py` and `cases/matrix.py` already
    used, and it needs nobody's permission to stay true.
    """
    offenders = []
    for site, flag, message in _library_refusals_naming_a_flag():
        if not _names_the_parameter(flag, message):
            parameter = flag.lstrip("-").replace("-", "_")
            offenders.append(f"{site}: names {flag} but never {parameter}")
    assert not offenders, (
        f"{len(offenders)} library raise site(s) name a command-line flag and not the "
        "parameter behind it. A library message is read by a Python caller first: name "
        "the PARAMETER, and put the flag beside it for the reader who arrived through a "
        "CLI.\n  " + "\n  ".join(sorted(offenders))
    )


def _names_the_parameter(flag: str, message: str) -> bool:
    """Does ``message`` name the PARAMETER behind ``flag``, not just the flag?

    THE OBVIOUS PREDICATE IS VACUOUS, which is why this is a function
    with tests of its own rather than one line inside the walk. The
    first version asked ``parameter in message`` where ``parameter`` is
    ``flag.lstrip("-").replace("-", "_")``. For any flag whose body has
    no hyphen that string is a SUBSTRING OF THE FLAG ITSELF: ``"cases"``
    is in ``"--cases"`` and ``"fsm"`` is in ``"--fsm"``. So the predicate
    was satisfied by the defect, and of the three raise sites the walk
    reaches it genuinely checked exactly one, ``--smi-root``, which is
    the site the same commit had just repaired.

    Measured by the review pass that found it: rewriting
    ``qa/probes.py``'s refusal from "pass fsm (CLI: --fsm)" to
    "pass --fsm", which is the exact defect class, left 116 tests green.

    Blanking the flags out of the message first is necessary and is not
    sufficient, which the SECOND version of this predicate learned the
    same hour. A parameter name is often an ordinary English word, so
    ``--cases X (SMI cases need smi_root)`` contains "cases" in prose and
    passed a substring test while naming the flag alone.

    So the two SANCTIONED SHAPES are asked for by name, and there are
    exactly two in this repository:

    * ``smi_root (CLI: --smi-root)``, the parameter with its flag beside
      it, which is what a message written for a Python caller and read by
      a CLI user needs;
    * ``cases=['PHY-01']``, the keyword form, which shows the call rather
      than describing it.

    Anything else is an offender, including prose that happens to contain
    the word. A message wanting a third shape should add it here rather
    than rely on a coincidence of vocabulary.

    ONE PLURAL IS ADMITTED, narrowly and on purpose. Deriving the
    parameter from the flag by de-hyphenating is a heuristic, and it
    fails on the one place where this package's flag is singular and its
    parameter is not: ``--recipe`` against ``recipes=`` in
    ``cases/matrix.py``. A trailing ``s`` on the keyword form is
    therefore accepted. That is a stated exception rather than a silent
    loosening, and the alternative, renaming a released flag, is a
    breaking change for a message.
    """
    import re

    parameter = flag.lstrip("-").replace("-", "_")
    if f"{parameter} (CLI: {flag})" in message:
        return True
    # THE KEYWORD ARM MUST BE AN INSTRUCTION, not a mention. The second
    # version accepted any `parameter=` anywhere in the message, and a
    # review sabotage got past it with "pass --fsm. The default is
    # fsm=None.": the flag alone as the instruction and the parameter only
    # as a remark about a default. So the keyword form has to sit inside an
    # imperative clause, which is how both real messages already write it,
    # "name it: cases=[...]" and "map the code with recipes={...}".
    imperative = rf"(?:pass|name it|map (?:it|the code) with|give)[^.]*?\b{re.escape(parameter)}s?="
    return re.search(imperative, message) is not None


@pytest.mark.parametrize(
    ("flag", "message", "expected", "why"),
    [
        ("--fsm", "pass fsm (CLI: --fsm)", True, "the accepted shape, parameter beside flag"),
        ("--fsm", "pass --fsm", False, "the defect, and the vacuous predicate passed it"),
        ("--cases", "name it: cases=['A'] or --cases A", True, "parameter present as a keyword"),
        ("--cases", "to run a subset, pass --cases", False, "flag alone, single word"),
        ("--smi-root", "pass smi_root (CLI: --smi-root)", True, "hyphenated flag, accepted"),
        ("--smi-root", "pass --smi-root", False, "hyphenated flag, the original defect"),
        (
            "--cases",
            "--cases ['PHY-01'] (SMI cases need smi_root)",
            False,
            "the English word 'cases' in prose is not the parameter, and a substring "
            "test called this accepted",
        ),
        (
            "--recipe",
            "map it with recipes={code: 'mod:fn'} in Python, or --recipe CODE=mod:fn",
            True,
            "the keyword form, which is how cases/matrix.py writes it",
        ),
        (
            "--fsm",
            "pass --fsm. The default is fsm=None.",
            False,
            "the flag alone as the instruction and the parameter only as a remark "
            "about a default; the second version of this predicate accepted it",
        ),
    ],
)
def test_the_flag_predicate_can_tell_the_defect_from_the_accepted_shape(
    flag, message, expected, why
):
    """The predicate is driven by fixtures, not only by the live tree.

    A guard whose only cases come from the tree goes green the day the
    tree happens to hold nothing it can judge, and says nothing about
    whether it COULD judge. These nine cases give it red cases that do not
    move when the source does, and each is a shape some version of the
    predicate got wrong.
    """
    assert _names_the_parameter(flag, message) is expected, why
