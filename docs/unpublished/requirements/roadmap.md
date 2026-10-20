# Roadmap candidates

Former requirements parked at the 0.43.0 trim because nothing implements them by the 0.43.0 tag and no
0.43.0 planning node schedules them. This page makes no claim: nothing here is a requirement of any
release. A row returns to the SRS only as a new decision, under its own UID, with a planning node.
The UIDs stay reserved and are never reused. The columns keep the register layout so the
former row can be read back; Parent, Level and Status are the former values, and the
Rationale says why the row was parked.

| UID | Parent | HID | Level | Status | Verification method | Statement | Rationale | Derives from | Code | Test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FR-1617 | FR-3009 | - | L2 | pending | test | The library shall refuse a harmonic request whose declared azimuth sample count is insufficient to resolve the requested order. | Parked at the 0.43.0 trim: pending with no 0.43.0 planning node (@no linked node/); leaves the SRS as a roadmap candidate; planning nodes cited: PFS-2130.031 | - | - | - |
| FR-1609 | FR-3055 | - | L2 | pending | test | The library shall recognize a solver completion marker on either standard output or standard error when determining the local execution outcome. | Parked at the 0.43.0 trim: pending with no 0.43.0 planning node (@no linked node/); leaves the SRS as a roadmap candidate; planning nodes cited: PFS-2120.001 | - | - | - |
| FR-3082 | - | - | L1 | pending | analysis | The library shall store workspace input artifacts in documented UTF-8 text formats. | Parked at the 0.43.0 trim: pending with no 0.43.0 planning node (@no linked node/); leaves the SRS as a roadmap candidate | - | - | - |
| FR-3093 | - | - | L1 | pending | analysis | The library shall represent excluded bulk solver artifacts in shared records by content hash. | Parked at the 0.43.0 trim: pending with no 0.43.0 planning node (@no linked node/); leaves the SRS as a roadmap candidate | - | - | - |
| FR-3138 | - | - | L1 | pending | analysis | The library shall report elapsed time and peak memory for a workload measured under a declared execution configuration. | Parked at the 0.43.0 trim: no child and no implementation: the elapsed-time and peak-memory report is aspirational; FR-3165 (implemented log monitoring) stays the QPEFF feature instead of merging into it | - | - | - |
| FR-3149 | - | - | L1 | pending | analysis | The library shall state the permitted use and prohibited safety-critical uses of simulation results in the published user guidance. | Parked at the 0.43.0 trim: no child and no implementation: the safety-use statement is pending with no planning node | - | - | - |
| NFR-304 | NFR-30 | - | L3 | pending | inspection | The library's structural documentation shall describe CG offsets as fixed-wing weight inputs rather than a source of centrifugal bend-twist coupling in the rotor static solve. | Parked at the 0.43.0 trim: L3 pending without test anchor and without 0.43.0 node; planning nodes cited: PFS-2110.110 | - | - | - |
