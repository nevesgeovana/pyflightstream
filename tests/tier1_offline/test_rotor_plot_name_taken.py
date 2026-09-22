"""A pproc group that takes the rotor plot's NAME in the rotor's own frame must say so.

MEASURED ON A REAL CAMPAIGN, 2026-09-22. A pproc declared::

    [[plots.groups]]
    name = "ROTOR_{family}"
    frame = "SMRP"
    families = "all"

and the script the run wrote created `FX_ROTOR_PUSHER` under the frame it defines as
`PUSHER_SMRP`, the rotor's own. The package saw the name was taken and did not add its automatic
global-MRP plot of that name -- right at emission, since two plots cannot share a name -- found
no MRP group over the rotor, and returned NO candidate at all. The post stage then printed
"looked for none", which names nothing anyone can act on, and eight rotor tables across two
campaigns were refused that way.

No post-processing can recover those tables: the global-frame history was never written. What
this asserts is that the refusal SAYS which group took the name and what to rename.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.products import rotor_plot_source
from pyflightstream.workspace.inputs import resolve_pproc

PPROC = """
[groups]
"1" = "all"

[sections]
count = 10

[plots]
parameters = ["CL", "CD", "FX", "FY", "FZ", "MX", "MY", "MZ"]

[[plots.groups]]
name = "MRP_TOTAL"
frame = "MRP"
families = "all"

[[plots.groups]]
name = "ROTOR_{family}"
frame = "SMRP"
families = "all"
"""

INVENTORY = ["W", "B", "G", "J", "Blade1", "Blade2"]
ALIASES = {"all": INVENTORY, "airframe": ["W", "B"], "Blades": ["Blade1", "Blade2"]}
ROTOR = ["Blade1", "Blade2", "G", "J"]


@pytest.fixture
def pproc(tmp_path):
    inputs = tmp_path / "inputs"
    (inputs / "pproc").mkdir(parents=True)
    (inputs / "pproc" / "p001.toml").write_text(PPROC, encoding="utf-8")
    return resolve_pproc(inputs, "p001")


def test_the_refusal_names_the_group_that_took_the_name(pproc):
    """Not "looked for none": the group, its frame, and what to rename it to."""
    candidates, refused = rotor_plot_source(
        pproc, "PUSHER", rotor_families=ROTOR, inventory=INVENTORY, aliases=ALIASES
    )
    assert candidates == [], "a rotor-frame emission is never a source for the rotor table"
    assert refused is not None, "the rotor table was refused with nothing a reader can act on"
    assert "ROTOR_{family}" in refused, refused
    assert "SMRP" in refused, refused
    assert "ROTOR_PUSHER" in refused, refused
    assert "Rename" in refused or "rename" in refused, refused


def test_a_pproc_that_leaves_the_name_free_still_gets_the_automatic_plot(tmp_path):
    """The guard must not fire where nothing took the name: the candidate is still offered."""
    inputs = tmp_path / "inputs"
    (inputs / "pproc").mkdir(parents=True)
    (inputs / "pproc" / "p001.toml").write_text(
        PPROC.replace('name = "ROTOR_{family}"', 'name = "SHAFT_{family}"'), encoding="utf-8"
    )
    free = resolve_pproc(inputs, "p001")
    candidates, refused = rotor_plot_source(
        free, "PUSHER", rotor_families=ROTOR, inventory=INVENTORY, aliases=ALIASES
    )
    assert candidates == ["ROTOR_PUSHER"], candidates
    assert refused is None, refused


@pytest.mark.parametrize("frame", ["PUSHER_SMRP", "PUSHER_RMRP1"])
def test_a_qualified_rotor_frame_is_named_as_the_rotors_own(tmp_path, frame):
    """The closing round's second fix.

    A rotor's own frames are `<ALIAS>_SMRP` and `<ALIAS>_RMRP<k>`, which is
    exactly why an alias may not carry that radical. A pproc naming one of them
    must give the group a fixed name, since `{family}` only expands in a frame
    that expands. Reading only the bare radicals called such a group a FAMILY
    mismatch, which names the wrong cause: the frame is the cause.
    """
    inputs = tmp_path / "inputs"
    (inputs / "pproc").mkdir(parents=True)
    (inputs / "pproc" / "p001.toml").write_text(
        PPROC.replace(
            'name = "ROTOR_{family}"\nframe = "SMRP"', f'name = "ROTOR_PUSHER"\nframe = "{frame}"'
        ),
        encoding="utf-8",
    )
    pproc = resolve_pproc(inputs, "p001")
    _, refused = rotor_plot_source(
        pproc, "PUSHER", rotor_families=ROTOR, inventory=INVENTORY, aliases=ALIASES
    )
    assert refused is not None, "the rotor table was refused with nothing to act on"
    assert "which is the rotor's own" in refused, refused
    assert "not exactly the rotor's" not in refused, refused
