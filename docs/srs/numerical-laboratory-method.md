# Numerical laboratory method

pyflightstream formalizes FlightStream as a numerical laboratory: a numerical
experiment is defined in a run matrix and carried out with the rigor and provenance
required to trust a simulation result. The method below states solver-independent
requirements; the FlightStream requirements instantiate them through `Derives from`.

The protocol is the design of a numerical experiment, decided and recorded before
any run: what is tested, under which conditions, with which variables and controls,
and what is measured. In pyflightstream it is the run matrix, the setup standard
and the post-processing declaration (stage DEXP).

The procedure is the sequence of operations on the instrument that carries the
protocol out: the generated solver script and the plan, run and collect steps
(stages PROC and EXEC). The researcher writes the protocol and never the procedure;
the library derives and checks the procedure from the protocol, so two engineers
with the same protocol obtain the same procedure.

| UID | Status | Level | Radical | Statement | Rationale |
| --- | --- | --- | --- | --- | --- |
| NL-INST | pending | L0 | INST | A numerical laboratory driver shall know every command of every registered solver build, each with its evidence, and refuse what a build does not support. | Know the instrument. |
| NL-DEXP | pending | L0 | DEXP | A numerical laboratory driver shall let an experiment be defined as a run matrix of cases, each with its flight condition, inputs and setup standard. | Design the experiment. |
| NL-SPCM | pending | L0 | SPCM | A numerical laboratory driver shall bring geometry and meshes into an experiment and operate on them reproducibly. | Prepare the specimen. |
| NL-PHYS | pending | L0 | PHYS | A numerical laboratory driver shall configure the solver physics of a case: settings, rotors and actuators, fluid-structure interaction and motion. | Configure the physics. |
| NL-PROC | pending | L0 | PROC | A numerical laboratory driver shall emit the solver script of a case and check it before the solver runs. | Translate to the instrument. |
| NL-EXEC | pending | L0 | EXEC | A numerical laboratory driver shall plan, run, monitor, continue and recover the cases of an experiment on a workstation or a cluster. | Run the experiment. |
| NL-RECS | pending | L0 | RECS | A numerical laboratory driver shall record what each run was and produced, so it can be rebuilt and audited. | Record the experiment. |
| NL-DRED | pending | L0 | DRED | A numerical laboratory driver shall reduce solver outputs to defined products, each stating the condition it belongs to. | Reduce the data. |
| NL-TRST | pending | L0 | TRST | A numerical laboratory driver shall assess the validity of a result: convergence, build-to-build comparison and the evidence behind each claim. | Establish trust. |
| NL-WKSP | pending | L0 | WKSP | A numerical laboratory driver shall keep the inputs, runs and products of an experiment in one workspace whose governing files are plain text, so that the laboratory can be placed under version control and every change to a protocol or a record is reviewable. | Keep the laboratory. |
| NL-OPER | pending | L0 | OPER | A numerical laboratory driver shall be operable from the command line and from Python, and teach its own use. | Operate and learn. |
| NL-WKSP-1 | pending | L1 | WKSP | The laboratory state that governs an experiment (protocol, configuration, records) shall be held in plain-text files that a version control system can compare and merge; bulk solver outputs are referenced by hash and never edited. | Changes to the protocol and records remain reviewable under version control. |
