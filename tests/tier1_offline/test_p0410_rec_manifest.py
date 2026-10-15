"""P0410-REC: shared documents preserve every resolved record value."""


def test_p0410_rec_distinct_invocations_and_unrecorded_fields_survive():
    from pyflightstream.workspace.record_document import decode_document, encode_rows

    row = {
        "run_id": "run",
        "sim_id": "1",
        "status": "CONVERGED",
        "argv": ["requested"],
        "executor": {"class_name": "remote", "argv": ["observed"]},
        "outputs": ["b", "a", "b"],
        "outputs_sha256": {"c": "hash"},
        "solver_setup": {"flags": {"X": {"value": 3}}},
        "frame_motions": {"1": {"motion": "fixed"}},
    }
    assert decode_document(encode_rows([row])) == [row]


def test_p0410_rec_absent_executor_arguments_stay_absent():
    from pyflightstream.workspace.record_document import decode_document, encode_rows

    row = {"run_id": "run", "sim_id": "1", "status": "CONVERGED", "executor": {}}
    assert decode_document(encode_rows([row])) == [row]
