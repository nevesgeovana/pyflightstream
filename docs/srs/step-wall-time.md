
# Per-step run timing

Closest sibling: RECS-1 in ../unpublished/requirements/recs.md (L2 run evidence).

| UID | Parent | HID | Level | Status | Verification method | Statement | Rationale | Derives from | Code | Test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FR-3769 | FR-3071 | RECS-1.5 | L2 | implemented | test | pyflightstream shall retain one wall timestamp and elapsed interval per completed unsteady step, together with the mean of available intervals in the last 20 steps, in the run record and cost evidence. | PFS-2201.03. Measure callbacks without changing solver behavior. The first local interval begins at launch and includes initialization; without a launch origin it is null, never invented. | NL-RECS-1 | run._actions_counter; run._step_timing | tests/tier1_offline/test_rt057_step_timing.py |
