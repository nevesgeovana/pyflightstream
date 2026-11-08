
# Launch runtime setup

Closest sibling: PHYS-3 in ../unpublished/requirements/phys.md (L2 setup schema).

| UID | Parent | HID | Level | Status | Verification method | Statement | Rationale | Derives from | Code | Test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FR-3770 | FR-3039 | PHYS-3.9 | L2 | implemented | test | pyflightstream shall accept a runtime setup block with a positive integer or auto max_threads and auto or all affinity, resolve it on the launch host, emit the resolved thread count and retain the selected affinity and source topology in the run evidence. | PFS-2201.01. Intel hybrid auto uses P-core logical processors with KMP_HW_SUBSET and compact KMP_AFFINITY; homogeneous single socket uses all logical processors without pinning; homogeneous multiple sockets or NUMA nodes uses one node with explicit affinity; all disables pinning. Absent settings preserve current behavior. | NL-PHYS | run._runtime; run._executors.LocalExecutor | tests/tier1_offline/test_rt057_runtime.py |

Homogeneous policies are inferred from GOAL-076, not measured. They are conservative
starting points for the study kit calibration to confirm on the target machine.
