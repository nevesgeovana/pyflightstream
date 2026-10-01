from hashlib import sha256

import pytest


def prepared(path, declaration, unit):
    from pyflightstream.cases.freestream import prepare_field

    return prepare_field(path, form="STRUCTURED", source_units=declaration, native_unit=unit)


@pytest.mark.parametrize(
    "unit,factor", [("METER", 1), ("MILLIMETER", 1000)], ids=["METER-1", "G49"]
)
def test_si_field_preserves_physical_vectors_and_original_bytes(tmp_path, unit, factor):
    # GOAL033:capability_ids:items:G49
    # GOAL033:scope:G49 GOAL033:scope:G50
    source = tmp_path / "field.txt"
    original = b"2 2\n0 -2 -1 11 3 5\n0 -2 1 12 4 6\n0 2 -1 13 5 7\n0 2 1 14 6 8\n"
    source.write_bytes(original)
    result = prepared(source, "SI", unit)
    assert source.read_bytes() == original
    assert result.path != str(source)
    rows = result.payload.splitlines()
    assert rows[0] == b"2 2"
    assert [float(x) for x in rows[1].split()] == [
        0,
        -2 * factor,
        -factor,
        11 * factor,
        3 * factor,
        5 * factor,
    ]
    assert result.provenance["source_sha256"] == sha256(original).hexdigest()
    assert result.provenance["effective_sha256"] == sha256(result.payload).hexdigest()
    assert result.provenance["rotation_applied"] is False
    assert result.provenance["native_length_unit"] == unit


def test_legacy_field_bytes_and_path_are_not_reinterpreted(tmp_path):
    source = tmp_path / "legacy.txt"
    original = b"2 2\r\n0 -2 -1 11 3 5\r\n0 -2 1 12 4 6\r\n0 2 -1 13 5 7\r\n0 2 1 14 6 8\r\n"
    source.write_bytes(original)
    result = prepared(source, None, "MILLIMETER")
    assert result.path == str(source)
    assert result.payload is None
    assert source.read_bytes() == original
    assert result.provenance["source_units"] == "undeclared"


def test_explicit_native_keeps_exact_file(tmp_path):
    source = tmp_path / "native.txt"
    source.write_bytes(b"2 2\n0 -2 -1 11 3 5\n0 -2 1 12 4 6\n0 2 -1 13 5 7\n0 2 1 14 6 8\n")
    result = prepared(source, "NATIVE", "MILLIMETER")
    assert result.path == str(source)
    assert result.payload is None
    assert result.provenance["source_units"] == "NATIVE"


@pytest.mark.parametrize("unit", [None, "INCH", "FOOT"])
def test_si_conversion_refuses_unmeasured_or_unknown_native_units(tmp_path, unit):
    from pyflightstream.cases import CampaignConfigError

    source = tmp_path / "field.txt"
    source.write_text("2 2\n0 -2 -1 11 3 5\n0 -2 1 12 4 6\n0 2 -1 13 5 7\n0 2 1 14 6 8\n")
    with pytest.raises(CampaignConfigError, match="METER.*MILLIMETER"):
        prepared(source, "SI", unit)


def test_unstructured_si_conversion_has_no_invented_header(tmp_path):
    from pyflightstream.cases.freestream import prepare_field

    source = tmp_path / "wake.dat"
    source.write_text("0 -2 -1 11 3 5\n0 -2 1 12 4 6\n0 2 -1 13 5 7\n0 2 1 14 6 8\n")
    result = prepare_field(source, form="UNSTRUCTURED", source_units="SI", native_unit="MILLIMETER")
    assert len(result.payload.splitlines()) == 4
    assert [float(x) for x in result.payload.splitlines()[0].split()] == [
        0,
        -2000,
        -1000,
        11000,
        3000,
        5000,
    ]


@pytest.mark.parametrize("declaration", ["SI", "NATIVE"])
def test_workflow_emits_declared_file_and_writer_hashes_both_inputs(tmp_path, declaration):
    import json

    from pyflightstream.cases.workflows._freestream import _free_stream, _the_custom_freestream
    from pyflightstream.run import _write_pending_files
    from pyflightstream.script import Script
    from tests.tier1_offline.test_g15_custom_freestream import field, with_field
    from tests.tier1_offline.test_workflows import steady_case

    source = field(tmp_path / "sources")
    original = source.read_bytes()
    case = with_field(steady_case(), source).model_copy(update={"freestream_units": declaration})
    custom = _the_custom_freestream(case)
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    _free_stream(case, script, {}, custom)
    pending = script.pending_input_files
    if declaration == "NATIVE":
        assert not pending
        assert str(source) in script.render()
        return
    assert len(pending) == 2
    payload_name = next(name for name in pending if name.endswith(".txt"))
    assert payload_name in script.render()
    assert str(source) not in script.render()
    work = tmp_path / "work"
    work.mkdir()
    recorded = {source.name: sha256(original).hexdigest()}
    written = _write_pending_files(script, work, case=case, recorded=recorded)
    assert written[payload_name] == sha256((work / payload_name).read_bytes()).hexdigest()
    provenance = json.loads((work / (payload_name + ".provenance.json")).read_text())
    assert provenance["source_sha256"] == recorded[source.name]
    assert provenance["effective_sha256"] == written[payload_name]
    assert source.read_bytes() == original
    source.write_text("changed after build")
    from pyflightstream.cases import CampaignConfigError

    with pytest.raises(CampaignConfigError, match="changed between preparation"):
        _write_pending_files(script, work, case=case, recorded=recorded)


def test_generated_field_provenance_carries_no_authoring_metadata(tmp_path):
    """GOAL-034 Q0-src-cases-1: the provenance file a run folder receives beside
    an SI-converted field is the field's own record. It carried a hard-coded
    authoring header naming a provider, a product and a fixed date into every
    user's run; nothing of that kind may reach a generated input."""
    import json

    from pyflightstream.cases.workflows._freestream import _free_stream, _the_custom_freestream
    from pyflightstream.script import Script
    from tests.tier1_offline.test_g15_custom_freestream import field, with_field
    from tests.tier1_offline.test_workflows import steady_case

    source = field(tmp_path / "sources")
    case = with_field(steady_case(), source).model_copy(update={"freestream_units": "SI"})
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    _free_stream(case, script, {}, _the_custom_freestream(case))
    [text] = [
        body
        for name, body in script.pending_input_files.items()
        if name.endswith(".provenance.json")
    ]
    # The header words come from the tracked-tree guard, so this file does not
    # itself spell the key that guard forbids.
    from tests.tier1_offline.test_no_estate_headers import FORBIDDEN

    for forbidden in (*FORBIDDEN, "OpenAI", "Codex"):
        assert forbidden not in text, (forbidden, text)
    record = json.loads(text)
    assert record["source_units"] == "SI"
    assert record["native_length_unit"] == "MILLIMETER"
    assert record["source_sha256"] == sha256(source.read_bytes()).hexdigest()


@pytest.mark.parametrize(("head", "factor"), [("1.0\n5", 1), ("0.001\n2", 1000)])
def test_si_field_on_an_opened_saved_simulation_reads_its_unit(tmp_path, head, factor):
    """GOAL-034 Q0-src-cases-3: a row opening a saved simulation and stating no
    unit, no reference, no frame and no disc reached the custom field before
    anything had read the `.fsm`'s unit, so an SI field was refused as having
    none. The saved unit is read first and the field converted into it."""
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from tests.tier1_offline.test_g15_custom_freestream import field, with_field
    from tests.tier1_offline.test_workflows import steady_case

    saved = tmp_path / "saved.fsm"
    saved.write_text(f"$GLOBAL_START$\n{head}\n$GLOBAL_END$\n", encoding="utf-8")
    source = field(tmp_path / "sources")
    case = with_field(steady_case(geometry=saved.as_posix()), source).model_copy(
        update={"freestream_units": "SI"}
    )
    script = Script("26.124")
    build_script(case, script)
    [payload] = [
        body
        for name, body in script.pending_input_files.items()
        if not name.endswith(".provenance.json")
    ]
    source_row = [float(x) for x in source.read_text().splitlines()[1].split()]
    written_row = [float(x) for x in payload.splitlines()[1].split()]
    assert written_row == pytest.approx([value * factor for value in source_row])


def test_matrix_unit_key_and_python_declaration_must_agree(tmp_path):
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows._freestream import _the_custom_freestream
    from tests.tier1_offline.test_g15_custom_freestream import field, with_field
    from tests.tier1_offline.test_workflows import steady_case

    source = field(tmp_path)
    case = with_field(steady_case(FREESTREAM_UNITS="SI"), source)
    assert _the_custom_freestream(case).source_units == "SI"
    case = case.model_copy(update={"freestream_units": "NATIVE"})
    with pytest.raises(CampaignConfigError, match="conflicts"):
        _the_custom_freestream(case)


def test_unit_declaration_without_field_is_refused():
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows._freestream import _the_custom_freestream
    from tests.tier1_offline.test_workflows import steady_case

    case = steady_case().model_copy(update={"freestream_units": "SI"})
    with pytest.raises(CampaignConfigError, match="requires a custom field"):
        _the_custom_freestream(case)


def test_public_custom_field_example_preserves_physical_vectors(tmp_path):
    import runpy
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "examples" / "prepare_custom_field.py"
    result = runpy.run_path(str(example))["demonstrate"](tmp_path)
    assert result["scale_from_source"] == 1000
    assert result["source_sha256"] != result["effective_sha256"]


def test_continuation_refuses_changed_unit_declaration_even_with_identical_bytes(tmp_path):
    from types import SimpleNamespace

    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.run import _refuse_a_field_the_stopped_run_did_not_read
    from tests.tier1_offline.test_g15_custom_freestream import field, with_field
    from tests.tier1_offline.test_workflows import steady_case

    source = field(tmp_path)
    case = with_field(steady_case(), source).model_copy(update={"freestream_units": "SI"})
    previous = SimpleNamespace(
        inputs_sha256={source.name: sha256(source.read_bytes()).hexdigest()},
        freestream_units="SI",
    )
    _refuse_a_field_the_stopped_run_did_not_read(case, "point", previous)
    previous.freestream_units = None
    with pytest.raises(CampaignConfigError, match="FREESTREAM_UNITS"):
        _refuse_a_field_the_stopped_run_did_not_read(case, "point", previous)


def test_undeclared_mm_field_warning_reaches_the_sink_despite_caller_filter(tmp_path):
    import warnings

    from pyflightstream._errors import PyflightstreamWarning, collecting_warnings
    from pyflightstream.cases.workflows._freestream import _free_stream, _the_custom_freestream
    from pyflightstream.script import Script
    from tests.tier1_offline.test_g15_custom_freestream import field, with_field
    from tests.tier1_offline.test_workflows import steady_case

    source = field(tmp_path)
    original = source.read_bytes()
    case = with_field(steady_case(), source)
    custom = _the_custom_freestream(case)
    assert custom.source_units is None and custom.extent is not None
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    with warnings.catch_warnings(), collecting_warnings() as caught:
        warnings.simplefilter("ignore", PyflightstreamWarning)
        _free_stream(case, script, {}, custom)
    relevant = [warning for warning in caught if "FREESTREAM_UNITS" in str(warning.message)]
    assert len(relevant) == 1
    assert relevant[0].category is PyflightstreamWarning
    assert "coverage is not checked" in str(relevant[0].message)
    assert source.read_bytes() == original
    assert not script.pending_input_files
    assert script.custom_field_extent_m is None
