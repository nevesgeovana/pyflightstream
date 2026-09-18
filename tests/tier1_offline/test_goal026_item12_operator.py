"""Tier 1, v0.23.0 item 12: the provenance names WHO submitted the run.

THE OWNER'S WORDS, 2026-09-17:

    "No provenance, precisamos incluir o nome do usuário que rodou de alguma
    forma, isso sendo transparente para Linux e windows. Como fazer?"

THE ANSWER, and it is one call rather than two branches: `getpass.getuser()`
is standard library and resolves on both platforms, reading `LOGNAME`, `USER`,
`LNAME` and `USERNAME` in turn and falling back to the password database where
there is one. A pair of `if sys.platform` branches would be two code paths that
drift, and the goal's `platforms` arm exists to keep the post stage one path.

IT IS A `prov:Person`, not a string bolted onto the activity. The document is
W3C PROV and it already carries two `prov:SoftwareAgent`s; the operator is the
third agent the activity was associated with, which is what PROV is for and
what another tool will read without being told about this package.

THE RUNS SHE ALREADY HAS READ `NA`, which the goal names as this item's one
exception: `submitted_by` is a RUN-time fact and nobody recorded it for the
simulations that already finished. It cannot be recovered and no value is
invented. The field is PRESENT and reads `NA`, so a reader can tell a run that
predates this release from a document that forgot.
"""

from __future__ import annotations

from pyflightstream.post.products import NOT_APPLICABLE, operator_agent
from pyflightstream.workspace.naming import submitted_by


def test_the_operator_resolves_on_this_platform_whatever_it_is():
    """One call, not a platform branch. It must answer on any host."""
    who = submitted_by()
    assert who is None or (isinstance(who, str) and who), who


def test_an_environment_that_names_nobody_reads_not_applicable(monkeypatch):
    """A host that cannot say who is running is `NA`, never a guess and never blank.

    This is the path a cluster submission can genuinely take: a batch job with
    a scrubbed environment and no password entry. Inventing a name there would
    put a false claim into a provenance document, which is the one artifact
    whose whole purpose is to be believed.
    """
    for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("pyflightstream.workspace.naming._getuser", _raise)
    # None AT THIS LAYER, `NA` at the product layer. The resolver sits below
    # `post` because `run` captures it and `post` writes it, and `post`
    # imports `workspace` rather than the reverse; spelling the absence here
    # would have inverted the dependency direction to borrow a token.
    assert submitted_by() is None
    assert operator_agent(submitted_by())["pyfs:submitted_by"] == NOT_APPLICABLE


def _raise() -> str:
    raise OSError("no password entry and no environment")


def test_a_record_with_no_operator_reads_not_applicable_rather_than_being_absent():
    """The runs she already has. Present and `NA`, so the absence is visible."""
    agent = operator_agent(None)
    assert agent["prov:type"] == "prov:Person", agent
    assert agent["pyfs:submitted_by"] == NOT_APPLICABLE, agent


def test_a_record_that_names_its_operator_carries_that_name():
    agent = operator_agent("an.operator")
    assert agent["prov:type"] == "prov:Person", agent
    assert agent["pyfs:submitted_by"] == "an.operator", agent
