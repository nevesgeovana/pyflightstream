"""P0460 lane P: saved-state marking instruments, without a licensed process."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pyflightstream.qa.probes import generate_probe_script
from pyflightstream.qa.specs import PROBE_SPECS

COMMANDS = (
    "MARK_WAKE_TERMINATION_NODES",
    "AUTO_DETECT_WAKE_TERMINATION_NODES",
    "IMPORT_WAKE_EDGES_FROM_FILE",
    "CREATE_NEW_BASE_REGION",
    "SET_BASE_REGION_CP",
    "SET_BASE_REGION_TRAILING_EDGES",
)


@pytest.mark.parametrize("command", COMMANDS)
def test_p0460_saved_marking_registered(command):
    spec = PROBE_SPECS.get(command)
    assert spec is not None
    assert "unchanged control" in spec.effect_note
    assert spec.observe is not None


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("version", ["26.124", "26.125"])
def test_p0460_scripts_measure_initialization_and_control(tmp_path, command, version):
    text = generate_probe_script(PROBE_SPECS[command], version, tmp_path).render()
    text += "\n" + (tmp_path / "prepare.txt").read_text() + (tmp_path / "target.txt").read_text()
    assert "START_SOLVER" not in text
    assert "control.fsm" in text and "before.fsm" in text and "after.fsm" in text
    assert text.count("INITIALIZE_SOLVER\n") == (1 if version == "26.124" else 0)
    if version == "26.124":
        text += (tmp_path / "noinit_prepare.txt").read_text()
        assert "noinit_control.fsm" in text and "noinit_after.fsm" in text
        prepare = (tmp_path / "prepare.txt").read_text()
        assert prepare.index("INITIALIZE_SOLVER\n") < prepare.index("control.fsm")
    else:
        assert "noinit_" not in text


def _states():
    from pyflightstream.qa import _spec_0460_marking as m

    before = m._State(("Body", "Rim"), m._POINTS, 0, (), (), frozenset({(m._FIRST, 1)}))
    return m, before


def test_p0460_mark_judge_requires_record_and_unchanged_control():
    m, before = _states()
    after = replace(before, termination=1)
    assert m._verdict(m._MARK, before, after, before) is True
    assert m._verdict(m._MARK, before, before, before) is False
    assert m._verdict(m._MARK, before, after, after) is None
    assert m._verdict(m._MARK, None, after, before) is None


def test_p0460_autodetect_requires_detected_edges_and_a_record():
    m, before = _states()
    after = replace(before, termination=1)
    assert m._verdict(m._AUTO, before, after, before) is True
    assert m._verdict(m._AUTO, before, before, before) is None
    empty = replace(before, edges=frozenset())
    assert m._verdict(m._AUTO, empty, after, empty) is None
    assert m._verdict(m._AUTO, before, after, after) is None


def test_p0460_second_import_must_add_group_preserve_first_set_and_type():
    m, initial = _states()
    before = replace(initial, groups=("Body",))
    after = replace(before, groups=("Body", "Rim"), edges=before.edges | {(m._SECOND, 2)})
    assert m._verdict(m._IMPORT, before, after, before) is True
    for mutant in (
        before,
        replace(after, groups=("Rim",)),
        replace(after, edges=frozenset({(m._SECOND, 2)})),
        replace(after, edges=before.edges | {(m._SECOND, 1)}),
    ):
        assert m._verdict(m._IMPORT, before, mutant, before) is False
    assert m._verdict(m._IMPORT, before, after, after) is None


def test_p0460_base_region_creation_and_cp_require_named_saved_values():
    m, initial = _states()
    before = replace(initial, edges=frozenset())
    created = replace(before, bases=(("Rim", -0.2),))
    assert m._verdict(m._CREATE, before, created, before) is True
    assert m._verdict(m._CREATE, before, before, before) is False
    for bases in ((("Body", -0.2),), (("Rim", 0.0),)):
        assert m._verdict(m._CREATE, before, replace(created, bases=bases), before) is False
    base = replace(before, bases=(("Rim", 0.0),))
    changed = replace(base, bases=(("Rim", -0.35),))
    assert m._verdict(m._CP, base, changed, base) is True
    assert m._verdict(m._CP, base, base, base) is False
    assert m._verdict(m._CP, base, changed, changed) is None


def test_p0460_base_rim_requires_all_four_edges_and_preserved_region():
    m, initial = _states()
    before = replace(initial, bases=(("Rim", 0.0),), edges=frozenset())
    after = replace(before, edges=frozenset((point, 1) for point in m._RIM_POINTS), groups=("Rim",))
    assert m._verdict(m._RIM, before, after, before) is True
    assert m._verdict(m._RIM, before, before, before) is False
    assert m._verdict(m._RIM, before, replace(after, bases=()), before) is False
    assert m._verdict(m._RIM, before, replace(after, edges=initial.edges), before) is False


@pytest.mark.parametrize(
    "rows", [["1", "7,", "2,"], ["1", "7,8,", "2,", "1,"], ["1", "9,", "2,", "1,"], ["0", "junk"]]
)
def test_p0460_termination_refuses_malformed_records(rows):
    m, _ = _states()
    with pytest.raises(ValueError):
        m._termination(rows, 8)


def test_p0460_termination_does_not_compare_record_id_to_selected_id():
    m, _ = _states()
    assert m._termination(["1", "3,", "2,", "1,"], 8) == 1
    assert m._termination(["0"], 8) == 0


def _save(path, termination=("0",), cp=None, groups=(), kind=1):
    """Handwritten sized layout from WTN4/BASE, not a golden from the reader."""
    names = ["1, T, F, F", "Body", "0,0,0", "2, T, F, F", "Rim", "0,0,0"]
    rows = ["$MESH_START$", "2", "3", "2", *names, "2", "1,2,", "3,3,", "1,1,", "2,3,", "3,4,"]
    preliminary = ["0,0,"] * 15
    preliminary[6] = "1,2,"
    preliminary[7] = f"{kind},{kind},"
    rows += preliminary + [
        "T,T,",
        "T,F,",
        "F,F,",
        "F,F,",
        "T,T,",
        "0",
        "4",
        "0,2,2,0,",
        "0,0,1,1,",
        "0,0,0,0,",
        *termination,
        "$MESH_END$",
    ]
    rows += ["$PHYSICS_START$", "140", "45", "15", "0" if cp is None else "1"]
    if cp is not None:
        rows += ["Rim", "F,", f"{cp},", "0,", "0,", "0,"]
    rows += [str(len(groups)), *groups]
    if groups:
        rows += [",".join(str(i) for i in range(1, len(groups) + 1)) + ","]
    rows += ["0", "$PHYSICS_END$"]
    path.write_text("\n".join(rows) + "\n", encoding="ascii")


def test_p0460_reads_saved_records_and_types(tmp_path):
    m, _ = _states()
    path = tmp_path / "state.fsm"
    _save(path, ("1", "3,", "2,", "1,"), -0.35, ("Body", "Rim"), 2)
    state = m._state(path)
    assert state is not None
    assert state.termination == 1 and state.bases == (("Rim", -0.35),)
    assert state.groups == ("Body", "Rim")
    assert state.edges == frozenset({((1.0, 0.0, 0.0), 2)})
    path.write_text(path.read_text().replace("3,\n2,\n1,", "3,\n2,"))
    assert m._state(path) is None


@pytest.mark.parametrize("command", COMMANDS)
def test_p0460_missing_files_never_verify(tmp_path, command):
    spec = PROBE_SPECS[command]
    artifacts = SimpleNamespace(workdir=tmp_path)
    assert spec.assert_effect(artifacts) is None
    assert '"effect": null' in spec.observe(artifacts)
