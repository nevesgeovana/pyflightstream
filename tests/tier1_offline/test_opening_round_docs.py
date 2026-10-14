"""Retained runtime, privacy and link checks, with shared test support."""

import re
import tomllib

from pyflightstream.workspace.inputs import PprocArtifact
from tests.tier1_offline._workflow_docs import workflow_docs_text


def test_documented_group_values_validate_as_single_aliases():
    text = workflow_docs_text()
    for block in re.findall(r"```toml\n(.*?)```", text, re.S):
        if "[groups]" in block:
            groups = tomllib.loads(block)["groups"]
            assert all(isinstance(value, str) for value in groups.values()), groups
            PprocArtifact.model_validate({"groups": groups})
