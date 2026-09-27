# GEOVERSE_HEADER
# file_version: "1.0.1"
# file_role: measured-obj-import-regression-tests
# last_modified_at: "2026-09-27T20:54:56.328Z"
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementation-agent}
# dependencies: [pyflightstream.workspace.inputs]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: "Bind existing real assertions to exact GOAL-033 capability markers."
# revision_source: git
"""Synthetic controls measured on executable 68e64e...30c65, build 8172026."""

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace.inputs import obj_boundary_names

VERTICES = "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 1 1 0\nv 0 2 0\nv 1 2 0\n"


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        ("o First\nf 1 2 3\ng Second\nf 2 4 3\n", ("First", "Second")),
        (
            "g First\nf 1 2 3\ng Second\nf 2 4 3\ng First\nf 3 4 5\n",
            ("First", "Second", "First"),
        ),
        ("f 1 2 3\ng Named\nf 2 4 3\n", ("Boundary-1", "Named")),
    ],
)
def test_native_measured_sequences_keep_order_and_duplicate_names(tmp_path, groups, expected):
    # GOAL033:capability_ids:items:G48
    path = tmp_path / "control.obj"
    path.write_text(VERTICES + groups, encoding="utf-8")
    assert obj_boundary_names(path) == expected


def test_native_multiname_g_uses_first_name_and_reports_that_choice(tmp_path):
    path = tmp_path / "control.obj"
    path.write_text(
        VERTICES + "g Main Wing\nf 1 2 3\ng Tail Plane\nf 2 4 3\n",
        encoding="utf-8",
    )
    with pytest.warns(PyflightstreamWarning, match="only the first") as caught:
        names = obj_boundary_names(path)
    assert names == ("Main", "Tail")
    assert len(caught) == 2
