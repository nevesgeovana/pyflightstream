# Software Requirements Specification

This internal specification states the current package contracts. Historical
evidence, release tasks and superseded narratives are retained outside the
product repository in the release SRS history archive.

## Sources

- [Functional requirements](functional-requirements.md)
- [Non-functional requirements](nonfunctional-requirements.md)
- [Introduction](../../srs/introduction.md)
- [Scope](../../srs/scope.md)
- [Data model](../../srs/data-model.md)
- [Architecture](../../srs/architecture-srs.md)
- [Engineering standards](../../srs/standards.md)

## Identity and generation

FR- and NFR- identifiers are permanent UIDs. Existing suffixes remain part of
their identity. Retired UIDs and unused allocations are never reused.
The last allocated functional number is FR-1203; allocate future children
from the same functional counter, including children of NFR requirements.
Parent links define hierarchy without encoding it in the UID.

Run `python scripts/gen_requirements_index.py` to generate
`build/requirements-index.json` and the area pages in `build/requirements/`.
Run it with `--check` to verify those outputs against these sources.
Each generated page displays a hierarchy identifier, AREA-n or AREA-n.m,
beside the stable UID. HIDs follow the current hierarchy and are never cited
as permanent identities. Code and tests cite UIDs.

Every live requirement supplies a module:symbol and a collecting test ID.
An anchor establishes traceability, not universal coverage: pending contracts
retain that status until their full acceptance guard is implemented.
Implemented means the stated behavior has code and a falsifying test;
deferred means an external acceptance gate remains. Retired means the UID
is reserved without a current normative obligation.

## Glossary

| Term | Meaning |
| --- | --- |
| Campaign | A declared collection of simulations and their workspace inputs. |
| SIM | A simulation case; a datapoint is one execution condition within it. |
| Manifest | The versioned record of run identities and their evidence. |
| Tidy table | One observation per row and one variable per column. |
| Clean-room | Implementation specified from the official manual and probe evidence. |
| Golden | A committed reference output used for exact comparison. |
| Round-trip | Writing and reading a value without changing its meaning. |
| Escape hatch | An explicitly recorded route around the curated interface. |
| Shim | A temporary compatibility name that warns about its replacement. |
